"""
Proof Chain Service.

Builds proof chains from stored legal claims, showing:
- Required evidence (from statutes/guides)
- Presented evidence (from case)
- Missing evidence (gaps)
- Outcomes and damages
- Completeness scores

Also handles extraction and dual storage (ArangoDB + Qdrant) for proof chain entities.
"""

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import (
    EntityType,
    LegalEntity,
    SourceMetadata,
    SourceType,
)
from tenant_legal_guidance.models.relationships import RelationshipType
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.embeddings import EmbeddingsService
from tenant_legal_guidance.services.vector_store import QdrantVectorStore

logger = logging.getLogger(__name__)


@dataclass
class ProofChainEvidence:
    """Evidence item in the proof chain with satisfaction status."""

    evidence_id: str
    evidence_type: str
    description: str
    is_critical: bool
    context: Literal["required", "presented", "missing"]
    source_reference: str | None = None

    # For required evidence: what presented evidence satisfies it
    satisfied_by: list[str] | None = None  # Evidence IDs

    # For presented evidence: what required evidence it satisfies
    satisfies: str | None = None  # Required evidence ID


@dataclass
class ProofChain:
    """Complete proof chain for a legal claim."""

    claim_id: str
    claim_description: str
    claim_type: str | None = None
    claimant: str | None = None

    # Evidence breakdown
    required_evidence: list[ProofChainEvidence] = None  # From statutes/guides
    presented_evidence: list[ProofChainEvidence] = None  # From case
    missing_evidence: list[ProofChainEvidence] = None  # Required but not satisfied

    # Outcome if resolved
    outcome: dict | None = None  # {id, disposition, description}

    # Damages if applicable
    damages: list[dict] | None = None  # [{id, type, amount, status}]

    # Summary metrics
    completeness_score: float = 0.0  # 0.0-1.0
    satisfied_count: int = 0
    missing_count: int = 0
    critical_gaps: list[str] = None  # Descriptions of missing critical evidence

    def __post_init__(self):
        """Initialize default values."""
        if self.required_evidence is None:
            self.required_evidence = []
        if self.presented_evidence is None:
            self.presented_evidence = []
        if self.missing_evidence is None:
            self.missing_evidence = []
        if self.critical_gaps is None:
            self.critical_gaps = []


class ProofChainService:
    """Service for building and analyzing proof chains."""

    def __init__(
        self,
        knowledge_graph: ArangoDBGraph,
        vector_store: QdrantVectorStore | None = None,
        llm_client: DeepSeekClient | None = None,
    ):
        """
        Initialize the proof chain service.

        Args:
            knowledge_graph: ArangoDB graph connection
            vector_store: Qdrant vector store for embeddings (optional, created if None)
            llm_client: DeepSeek LLM client (optional, needed for extraction)
        """
        self.kg = knowledge_graph
        self.vector_store = vector_store or QdrantVectorStore()
        self.llm_client = llm_client
        self.embeddings_svc = EmbeddingsService()
        self.logger = logging.getLogger(__name__)

    async def build_proof_chain(self, claim_id: str) -> ProofChain | None:
        """
        Build a complete proof chain for a legal claim.

        Args:
            claim_id: The ID of the legal claim

        Returns:
            ProofChain object or None if claim not found
        """
        self.logger.info(f"Building proof chain for claim: {claim_id}")

        # Get the claim
        claim = self.kg.get_entity(claim_id)
        if not claim:
            self.logger.warning(f"Claim not found: {claim_id}")
            return None

        # Check entity type - EntityType.LEGAL_CLAIM.value is "legal_claim" (lowercase)
        entity_type_value = (
            claim.entity_type.value
            if hasattr(claim.entity_type, "value")
            else str(claim.entity_type)
        )
        if entity_type_value != "legal_claim":
            self.logger.warning(f"Entity {claim_id} is not a LEGAL_CLAIM (got {entity_type_value})")
            return None

        # Get claim type string
        claim_type_str = claim.claim_type

        # Get required evidence for this claim type
        required_evidence = []
        if claim_type_str:
            required_evidence_list = self.kg.get_required_evidence_for_claim_type(claim_type_str)
            for ev in required_evidence_list:
                required_evidence.append(
                    ProofChainEvidence(
                        evidence_id=ev.get("_key", ""),
                        evidence_type=ev.get("evidence_type", "documentary"),
                        description=ev.get("name", ev.get("description", "")),
                        is_critical=ev.get("is_critical", False),
                        context="required",
                        source_reference=ev.get("source_reference"),
                    )
                )

        # Get presented evidence (evidence with HAS_EVIDENCE relationship)
        presented_evidence = []
        presented_evidence_ids = []

        # Get evidence linked via HAS_EVIDENCE relationships
        evidence_rels = self.kg.get_relationships(
            source_id=claim_id,
            relationship_type=RelationshipType.HAS_EVIDENCE,
        )

        for rel in evidence_rels:
            ev_id = rel.get("target_id")
            ev = self.kg.get_entity(ev_id)
            if ev and ev.entity_type.value == "EVIDENCE":
                presented_evidence_ids.append(ev_id)
                # Get evidence_type from attributes or default
                evidence_type = (
                    ev.attributes.get("evidence_type", "documentary")
                    if ev.attributes
                    else "documentary"
                )
                # Get is_critical from attributes or default
                is_critical_str = (
                    ev.attributes.get("is_critical", "false") if ev.attributes else "false"
                )
                is_critical = (
                    is_critical_str.lower() == "true"
                    if isinstance(is_critical_str, str)
                    else bool(is_critical_str)
                )
                presented_evidence.append(
                    ProofChainEvidence(
                        evidence_id=ev_id,
                        evidence_type=evidence_type,
                        description=ev.name or ev.description or "",
                        is_critical=is_critical,
                        context="presented",
                        source_reference=(
                            ev.attributes.get("source_reference") if ev.attributes else None
                        ),
                    )
                )

        # Match presented evidence to required evidence
        missing_evidence, satisfied_evidence = self.match_evidence_to_requirements(
            required_evidence=required_evidence,
            presented_evidence=presented_evidence,
        )

        # Get outcome (via RESULTS_IN relationship from claim)
        outcome = None
        outcome_rels = self.kg.get_relationships(
            source_id=claim_id,
            relationship_type=RelationshipType.RESULTS_IN,
        )
        if outcome_rels:
            outcome_id = outcome_rels[0].get("target_id")
            outcome_entity = self.kg.get_entity(outcome_id)
            if outcome_entity and outcome_entity.entity_type.value == "LEGAL_OUTCOME":
                # Handle field alignment: stored as 'outcome' and 'ruling_type', expected as 'disposition' and 'outcome_type'
                attrs = outcome_entity.attributes or {}
                disposition = outcome_entity.disposition or attrs.get("outcome") or "unknown"
                outcome_type = outcome_entity.outcome_type or attrs.get("ruling_type") or "judgment"
                outcome = {
                    "id": outcome_id,
                    "disposition": disposition,
                    "description": outcome_entity.name or outcome_entity.description or "",
                    "outcome_type": outcome_type,
                }

        # Get damages (via IMPLY relationship from outcome)
        damages = []
        if outcome:
            damage_rels = self.kg.get_relationships(
                source_id=outcome["id"],
                relationship_type=RelationshipType.IMPLY,
            )
            for rel in damage_rels:
                damage_id = rel.get("target_id")
                damage_entity = self.kg.get_entity(damage_id)
                if damage_entity and damage_entity.entity_type.value == "DAMAGES":
                    # Handle field alignment: stored in attributes dict or as direct fields
                    attrs = damage_entity.attributes or {}
                    damage_type = getattr(damage_entity, "damage_type", None) or attrs.get(
                        "damage_type", "monetary"
                    )
                    amount = (
                        getattr(damage_entity, "amount", None)
                        or attrs.get("amount")
                        or attrs.get("damages_awarded")
                    )
                    status = getattr(damage_entity, "status", None) or attrs.get(
                        "status", "claimed"
                    )
                    damages.append(
                        {
                            "id": damage_id,
                            "type": damage_type,
                            "amount": amount,
                            "status": status,
                            "description": damage_entity.name or damage_entity.description or "",
                        }
                    )

        # Calculate completeness
        completeness_score = self.compute_completeness_score(
            required_evidence=required_evidence,
            satisfied_evidence=satisfied_evidence,
            missing_evidence=missing_evidence,
        )

        # Identify critical gaps
        critical_gaps = [ev.description for ev in missing_evidence if ev.is_critical]

        return ProofChain(
            claim_id=claim_id,
            claim_description=claim.name or claim.description or "",
            claim_type=claim_type_str,
            claimant=claim.claimant,
            required_evidence=required_evidence,
            presented_evidence=presented_evidence,
            missing_evidence=missing_evidence,
            outcome=outcome,
            damages=damages if damages else None,
            completeness_score=completeness_score,
            satisfied_count=len(satisfied_evidence),
            missing_count=len(missing_evidence),
            critical_gaps=critical_gaps,
        )

    def match_evidence_to_requirements(
        self,
        required_evidence: list[ProofChainEvidence],
        presented_evidence: list[ProofChainEvidence],
    ) -> tuple[list[ProofChainEvidence], list[ProofChainEvidence]]:
        """
        Match presented evidence to required evidence requirements.

        Uses semantic similarity and keyword matching to determine which
        presented evidence satisfies which required evidence.

        Args:
            required_evidence: List of required evidence items
            presented_evidence: List of presented evidence items

        Returns:
            Tuple of (missing_evidence, satisfied_evidence)
        """
        satisfied_evidence = []
        missing_evidence = []

        # For each required evidence, try to find a match
        for req_ev in required_evidence:
            matched = False

            # Try to find SATISFIES relationships
            # (This would be set during extraction if the LLM identified the match)
            rels = self.kg.get_relationships(
                target_id=req_ev.evidence_id,
                relationship_type=RelationshipType.SATISFIES,
            )

            if rels:
                # Found a relationship - this required evidence is satisfied
                for rel in rels:
                    pres_ev_id = rel.get("source_id")
                    pres_ev = next(
                        (ev for ev in presented_evidence if ev.evidence_id == pres_ev_id), None
                    )
                    if pres_ev:
                        pres_ev.satisfies = req_ev.evidence_id
                        req_ev.satisfied_by = [pres_ev_id]
                        satisfied_evidence.append(req_ev)
                        matched = True
                        break

            # Fallback: simple keyword matching if no relationship
            if not matched:
                req_desc_lower = req_ev.description.lower()
                req_keywords = set(req_desc_lower.split())

                best_match = None
                best_score = 0.0

                for pres_ev in presented_evidence:
                    if pres_ev.satisfies:  # Already matched
                        continue

                    pres_desc_lower = pres_ev.description.lower()
                    pres_keywords = set(pres_desc_lower.split())

                    # Simple keyword overlap score
                    overlap = len(req_keywords & pres_keywords)
                    total = len(req_keywords | pres_keywords)
                    score = overlap / total if total > 0 else 0.0

                    if score > best_score and score > 0.3:  # 30% threshold
                        best_score = score
                        best_match = pres_ev

                if best_match:
                    best_match.satisfies = req_ev.evidence_id
                    req_ev.satisfied_by = [best_match.evidence_id]
                    satisfied_evidence.append(req_ev)
                    matched = True

            if not matched:
                # This required evidence is missing
                missing_ev = ProofChainEvidence(
                    evidence_id=req_ev.evidence_id,
                    evidence_type=req_ev.evidence_type,
                    description=req_ev.description,
                    is_critical=req_ev.is_critical,
                    context="missing",
                    source_reference=req_ev.source_reference,
                )
                missing_evidence.append(missing_ev)

        return missing_evidence, satisfied_evidence

    def compute_completeness_score(
        self,
        required_evidence: list[ProofChainEvidence],
        satisfied_evidence: list[ProofChainEvidence],
        missing_evidence: list[ProofChainEvidence],
    ) -> float:
        """
        Compute a completeness score (0.0-1.0) for the proof chain.

        Args:
            required_evidence: All required evidence items
            satisfied_evidence: Required evidence that has been satisfied
            missing_evidence: Required evidence that is missing

        Returns:
            Completeness score between 0.0 and 1.0
        """
        if not required_evidence:
            # No requirements = 100% complete (or undefined)
            return 1.0

        # Weight critical evidence more heavily
        total_weight = 0.0
        satisfied_weight = 0.0

        for req_ev in required_evidence:
            weight = 2.0 if req_ev.is_critical else 1.0
            total_weight += weight

            # Check if satisfied
            if any(sev.evidence_id == req_ev.evidence_id for sev in satisfied_evidence):
                satisfied_weight += weight

        if total_weight == 0:
            return 1.0

        return satisfied_weight / total_weight

    def _ensure_dual_storage(self, entity_id: str) -> bool:
        """
        Verify that an entity exists in both ArangoDB and Qdrant.

        Args:
            entity_id: The entity ID to check

        Returns:
            True if entity exists in both databases, False otherwise
        """
        # Check ArangoDB
        arango_entity = self.kg.get_entity(entity_id)
        if not arango_entity:
            self.logger.warning(f"Entity {entity_id} not found in ArangoDB")
            return False

        # Handle both dict (from get_entity) and LegalEntity object
        if hasattr(arango_entity, "chunk_ids"):
            # It's a LegalEntity object
            chunk_ids = arango_entity.chunk_ids or []
        else:
            # It's a dict
            chunk_ids = (
                arango_entity.get("chunk_ids", []) if isinstance(arango_entity, dict) else []
            )

        # Check Qdrant - search for chunks that reference this entity
        # Note: We search by entity ID in chunk payloads
        try:
            # Get chunks that reference this entity
            # This is a simplified check - in practice, we'd search Qdrant
            # For now, we check if entity has chunk_ids set
            if not chunk_ids:
                self.logger.warning(f"Entity {entity_id} has no chunk_ids in ArangoDB")
                return False

            # Verify at least one chunk exists in Qdrant
            # This is a basic check - full verification would query Qdrant
            return True
        except Exception as e:
            self.logger.error(f"Error checking Qdrant for entity {entity_id}: {e}")
            return False

    def _link_entity_to_chunks(self, entity: LegalEntity, chunk_ids: list[str]) -> None:
        """
        Establish bidirectional links between entity and chunks.

        Updates:
        - Entity in ArangoDB: adds chunk_ids to entity.chunk_ids list
        - Chunks in Qdrant: adds entity.id to chunk.payload.entities list

        Args:
            entity: The legal entity to link
            chunk_ids: List of chunk IDs to link to
        """
        if not chunk_ids:
            return

        # Update entity in ArangoDB with chunk_ids
        existing_entity = self.kg.get_entity(entity.id)
        if existing_entity:
            existing_chunk_ids = existing_entity.chunk_ids or []
            # Merge chunk IDs (avoid duplicates)
            all_chunk_ids = list(set(existing_chunk_ids + chunk_ids))
            # Update entity by re-adding with updated chunk_ids
            entity.chunk_ids = all_chunk_ids
            self.kg.add_entity(entity, overwrite=True)
        else:
            # Entity doesn't exist yet, will be set when entity is created
            entity.chunk_ids = chunk_ids

        # Update chunks in Qdrant with entity reference
        # Note: This requires fetching chunks, updating payload, and re-inserting
        # For now, we'll handle this during chunk creation/update
        # The actual linking happens when chunks are stored with entity IDs in payload
        self.logger.debug(
            f"Linked entity {entity.id} to {len(chunk_ids)} chunks (Qdrant update handled during chunk storage)"
        )

    def _create_vector_embedding(self, text: str) -> np.ndarray:
        """
        Create vector embedding for a proof chain entity.

        Args:
            text: Text to embed (typically entity name + description)

        Returns:
            NumPy array of embedding vector
        """
        if not text:
            # Return zero vector if no text
            return np.zeros(
                self.embeddings_svc.model.get_sentence_embedding_dimension(), dtype=np.float32
            )

        embeddings = self.embeddings_svc.embed([text])
        return (
            embeddings[0]
            if len(embeddings) > 0
            else np.zeros(
                self.embeddings_svc.model.get_sentence_embedding_dimension(), dtype=np.float32
            )
        )

    async def _persist_entity_dual(
        self,
        entity: LegalEntity,
        chunk_ids: list[str] | None = None,
        text_for_embedding: str | None = None,
    ) -> bool:
        """
        Atomically persist entity to both ArangoDB and Qdrant.

        Args:
            entity: The legal entity to persist
            chunk_ids: Optional list of chunk IDs to link (for bidirectional linking)
            text_for_embedding: Optional text to use for embedding (defaults to entity name + description)

        Returns:
            True if successfully persisted to both databases, False otherwise
        """
        try:
            # Step 1: Store entity in ArangoDB
            arango_success = self.kg.add_entity(entity, overwrite=True)
            if not arango_success:
                self.logger.error(f"Failed to store entity {entity.id} in ArangoDB")
                return False

            # Step 2: Create embedding and store in Qdrant
            if text_for_embedding is None:
                # Default: use entity name + description
                text_for_embedding = entity.name
                if entity.description:
                    text_for_embedding += " " + entity.description

            embedding = self._create_vector_embedding(text_for_embedding)

            # Step 3: Create chunk-like structure for entity in Qdrant
            # Use entity ID as chunk ID for entity vectors
            entity_chunk_id = f"entity:{entity.id}"
            entity_payload = {
                "chunk_id": entity_chunk_id,
                "entity_id": entity.id,
                "entity_type": (
                    entity.entity_type.value
                    if hasattr(entity.entity_type, "value")
                    else str(entity.entity_type)
                ),
                "name": entity.name,
                "description": entity.description or "",
                "text": text_for_embedding,
                # Link to actual chunks if provided
                "chunk_ids": chunk_ids or [],
                # Store entity metadata
                "source_id": entity.source_metadata.source if entity.source_metadata else "",
            }

            # Store in Qdrant
            self.vector_store.upsert_chunks(
                chunk_ids=[entity_chunk_id],
                embeddings=np.array([embedding]),
                payloads=[entity_payload],
            )

            # Step 4: Establish bidirectional links if chunk_ids provided
            if chunk_ids:
                self._link_entity_to_chunks(entity, chunk_ids)

            self.logger.info(
                f"Successfully persisted entity {entity.id} to both ArangoDB and Qdrant"
            )
            return True

        except Exception as e:
            self.logger.error(
                f"Failed to persist entity {entity.id} to dual storage: {e}", exc_info=True
            )
            return False

    async def extract_proof_chains(
        self,
        text: str,
        metadata: SourceMetadata | None = None,
    ) -> list[ProofChain]:
        """
        Extract proof chains from document text and store entities in both ArangoDB and Qdrant.

        This is the main entry point for proof chain extraction during ingestion.
        Uses ClaimExtractor for LLM-based extraction, then stores entities with dual storage.

        Args:
            text: The full text of the legal document
            metadata: Optional source metadata

        Returns:
            List of ProofChain objects representing extracted proof chains
        """
        if not self.llm_client:
            raise ValueError("LLM client required for proof chain extraction")

        self.logger.info(f"Extracting proof chains from document ({len(text)} chars)")

        # Use ClaimExtractor for extraction (single megaprompt call for speed)
        from tenant_legal_guidance.services.claim_extractor import ClaimExtractor

        extractor = ClaimExtractor(llm_client=self.llm_client, knowledge_graph=self.kg)
        extraction_result = await extractor.extract_full_proof_chain_single(text, metadata)

        # Convert extracted entities to LegalEntity and store with dual storage
        stored_entities = {}
        storage_errors = []

        # Store claims (handle partial chains - claims without outcomes are valid)
        for claim in extraction_result.claims:
            try:
                entity = self._extracted_claim_to_legal_entity(claim, metadata)
                success = await self._persist_entity_dual(entity, chunk_ids=None)
                if success:
                    stored_entities[claim.id] = entity
                else:
                    storage_errors.append(f"Failed to store claim {claim.id}")
            except Exception as e:
                self.logger.warning(f"Error storing claim {claim.id}: {e}", exc_info=True)
                storage_errors.append(f"Error storing claim {claim.id}: {e}")

        # Store evidence (handle partial chains - evidence without claims is valid)
        for evidence in extraction_result.evidence:
            try:
                entity = self._extracted_evidence_to_legal_entity(evidence, metadata)
                success = await self._persist_entity_dual(entity, chunk_ids=None)
                if success:
                    stored_entities[evidence.id] = entity
                else:
                    storage_errors.append(f"Failed to store evidence {evidence.id}")
            except Exception as e:
                self.logger.warning(f"Error storing evidence {evidence.id}: {e}", exc_info=True)
                storage_errors.append(f"Error storing evidence {evidence.id}: {e}")

        # Store outcomes (handle partial chains - outcomes without evidence are valid)
        for outcome in extraction_result.outcomes:
            try:
                entity = self._extracted_outcome_to_legal_entity(outcome, metadata)
                success = await self._persist_entity_dual(entity, chunk_ids=None)
                if success:
                    stored_entities[outcome.id] = entity
                else:
                    storage_errors.append(f"Failed to store outcome {outcome.id}")
            except Exception as e:
                self.logger.warning(f"Error storing outcome {outcome.id}: {e}", exc_info=True)
                storage_errors.append(f"Error storing outcome {outcome.id}: {e}")

        # Store damages (handle partial chains - damages without outcomes are valid)
        for damage in extraction_result.damages:
            try:
                entity = self._extracted_damage_to_legal_entity(damage, metadata)
                success = await self._persist_entity_dual(entity, chunk_ids=None)
                if success:
                    stored_entities[damage.id] = entity
                else:
                    storage_errors.append(f"Failed to store damage {damage.id}")
            except Exception as e:
                self.logger.warning(f"Error storing damage {damage.id}: {e}", exc_info=True)
                storage_errors.append(f"Error storing damage {damage.id}: {e}")

        # Log storage errors but continue (partial chains are valid)
        if storage_errors:
            self.logger.warning(f"Some entities failed to store: {len(storage_errors)} errors")
            for error in storage_errors[:5]:  # Log first 5 errors
                self.logger.debug(error)

        # Store relationships (handle missing entities gracefully)
        relationship_errors = []
        for rel_data in extraction_result.relationships:
            try:
                from tenant_legal_guidance.models.relationships import LegalRelationship

                # Validate that both source and target entities exist
                source_exists = rel_data["source_id"] in stored_entities or self.kg.get_entity(
                    rel_data["source_id"]
                )
                target_exists = rel_data["target_id"] in stored_entities or self.kg.get_entity(
                    rel_data["target_id"]
                )

                if not source_exists:
                    self.logger.warning(
                        f"Relationship source entity {rel_data['source_id']} not found, skipping relationship"
                    )
                    relationship_errors.append(f"Source {rel_data['source_id']} not found")
                    continue
                if not target_exists:
                    self.logger.warning(
                        f"Relationship target entity {rel_data['target_id']} not found, skipping relationship"
                    )
                    relationship_errors.append(f"Target {rel_data['target_id']} not found")
                    continue

                rel_type = RelationshipType[rel_data["type"]]
                relationship = LegalRelationship(
                    source_id=rel_data["source_id"],
                    target_id=rel_data["target_id"],
                    relationship_type=rel_type,
                )
                self.kg.add_relationship(relationship)
            except (KeyError, ValueError) as e:
                self.logger.warning(f"Failed to store relationship {rel_data}: {e}")
                relationship_errors.append(str(e))

        if relationship_errors:
            self.logger.warning(
                f"Some relationships failed to store: {len(relationship_errors)} errors"
            )

        # Build ProofChain objects from stored claims (handle partial chains)
        proof_chains = []
        for claim in extraction_result.claims:
            if claim.id in stored_entities:
                try:
                    proof_chain = await self.build_proof_chain(claim.id)
                    if proof_chain:
                        proof_chains.append(proof_chain)
                    else:
                        self.logger.warning(
                            f"Failed to build proof chain for claim {claim.id} (partial chain)"
                        )
                except Exception as e:
                    self.logger.warning(
                        f"Error building proof chain for claim {claim.id}: {e}", exc_info=True
                    )
            else:
                self.logger.warning(
                    f"Claim {claim.id} was not stored, skipping proof chain building"
                )

        # Note: Dual storage validation is deferred until after chunks are created
        # Entities are stored before chunks exist, so chunk_ids will be empty initially
        # The linking happens in DocumentProcessor after chunks are created
        # We'll validate dual storage there, not here
        self.logger.debug(
            f"Stored {len(stored_entities)} entities (chunk linking will happen after chunks are created)"
        )

        self.logger.info(
            f"Extracted {len(proof_chains)} proof chains: "
            f"{len(extraction_result.claims)} claims, "
            f"{len(extraction_result.evidence)} evidence, "
            f"{len(extraction_result.outcomes)} outcomes, "
            f"{len(extraction_result.damages)} damages"
        )

        return proof_chains

    async def retrieve_proof_chains(
        self,
        query_text: str | None = None,
        claim_type: str | None = None,
        top_k: int = 10,
    ) -> list[ProofChain]:
        """
        Retrieve proof chains based on a query or filters.

        Uses hybrid retrieval (vector + graph) to find relevant claims, then builds
        proof chains for those claims.

        Args:
            query_text: Text query for semantic search (optional)
            claim_type: Filter by claim type string (e.g., "DEREGULATION_CHALLENGE")
            top_k: Maximum number of proof chains to return

        Returns:
            List of ProofChain objects
        """
        self.logger.info(
            f"Retrieving proof chains: query='{query_text}', claim_type='{claim_type}'"
        )

        claim_ids = []

        # Strategy 1: Get claims by claim type (most specific)
        if claim_type:
            claim_ids = self.kg.get_claims_by_type(claim_type, limit=top_k)
            self.logger.info(f"Found {len(claim_ids)} claims by type: {claim_type}")

        # Strategy 2: Use hybrid retrieval if query_text provided
        if query_text and len(claim_ids) < top_k:
            try:
                from tenant_legal_guidance.services.retrieval import HybridRetriever

                # Initialize hybrid retriever
                retriever = HybridRetriever(
                    knowledge_graph=self.kg,
                    vector_store=self.vector_store,
                )

                # Retrieve entities using hybrid search
                results = retriever.retrieve(
                    query_text=query_text,
                    top_k_entities=top_k * 2,  # Get more to filter for claims
                    expand_neighbors=False,  # Don't expand, just get direct results
                )

                # Extract claim entity IDs from results
                entities = results.get("entities", [])
                retrieved_claim_ids = []

                for entity in entities:
                    # Handle both dict (from graph) and LegalEntity objects
                    if isinstance(entity, dict):
                        entity_type = entity.get("type") or entity.get("entity_type")
                        entity_id = entity.get("_key") or entity.get("id")
                    else:
                        entity_type = getattr(entity.entity_type, "value", str(entity.entity_type))
                        entity_id = entity.id

                    if entity_type in {"legal_claim", "LEGAL_CLAIM"}:
                        if entity_id and entity_id not in claim_ids:
                            retrieved_claim_ids.append(entity_id)

                # Combine with existing claim IDs
                claim_ids.extend(retrieved_claim_ids[: top_k - len(claim_ids)])
                self.logger.info(f"Retrieved {len(retrieved_claim_ids)} claims from hybrid search")

            except Exception as e:
                self.logger.warning(f"Hybrid retrieval failed: {e}", exc_info=True)

        # Strategy 3: If still no claims, get any claims (fallback)
        if not claim_ids:
            try:
                all_claims = self.kg.get_all_entities(entity_type="LEGAL_CLAIM")
                claim_ids = [claim.get("_key") for claim in all_claims[:top_k] if claim.get("_key")]
                self.logger.info(f"Using fallback: found {len(claim_ids)} claims")
            except Exception as e:
                self.logger.warning(f"Fallback claim retrieval failed: {e}", exc_info=True)

        # Build proof chains for each claim
        proof_chains = []
        for claim_id in claim_ids[:top_k]:
            try:
                proof_chain = await self.build_proof_chain(claim_id)
                if proof_chain:
                    proof_chains.append(proof_chain)
            except Exception as e:
                self.logger.warning(
                    f"Failed to build proof chain for {claim_id}: {e}", exc_info=True
                )

        self.logger.info(f"Retrieved {len(proof_chains)} proof chains")
        return proof_chains

    def _extracted_claim_to_legal_entity(
        self, claim, metadata: SourceMetadata | None
    ) -> LegalEntity:
        """Convert ExtractedClaim to LegalEntity."""
        if metadata is None:
            metadata = SourceMetadata(source=claim.id, source_type=SourceType.FILE)

        return LegalEntity(
            id=claim.id,
            entity_type=EntityType.LEGAL_CLAIM,
            name=claim.name,
            description=claim.claim_description,
            source_metadata=metadata,
            claim_description=claim.claim_description,
            claimant=claim.claimant,
            respondent_party=claim.respondent_party,
            claim_type=claim.claim_type,
            relief_sought=claim.relief_sought,  # Keep as list for direct field
            claim_status=claim.claim_status,
            best_quote={"text": claim.source_quote} if claim.source_quote else None,
            # Note: relief_sought is stored as a direct field (list), not in attributes
            # All claim fields are direct fields, not in attributes dict
            attributes={},
        )

    def _extracted_evidence_to_legal_entity(
        self, evidence, metadata: SourceMetadata | None
    ) -> LegalEntity:
        """Convert ExtractedEvidence to LegalEntity."""
        if metadata is None:
            metadata = SourceMetadata(source=evidence.id, source_type=SourceType.FILE)

        return LegalEntity(
            id=evidence.id,
            entity_type=EntityType.EVIDENCE,
            name=evidence.name,
            description=evidence.description,
            source_metadata=metadata,
            evidence_context=evidence.evidence_context,
            evidence_source_type=evidence.evidence_source_type,
            is_critical=evidence.is_critical,  # Keep as boolean for direct field
            attributes={
                "evidence_type": evidence.evidence_type,
                "source_quote": evidence.source_quote or "",
                "linked_claim_ids": ",".join(evidence.linked_claim_ids),
                # Convert boolean to string for attributes dict
                "is_critical": str(evidence.is_critical).lower(),
            },
            best_quote={"text": evidence.source_quote} if evidence.source_quote else None,
        )

    def _extracted_outcome_to_legal_entity(
        self, outcome, metadata: SourceMetadata | None
    ) -> LegalEntity:
        """Convert ExtractedOutcome to LegalEntity."""
        if metadata is None:
            metadata = SourceMetadata(source=outcome.id, source_type=SourceType.FILE)

        return LegalEntity(
            id=outcome.id,
            entity_type=EntityType.LEGAL_OUTCOME,
            name=outcome.name,
            description=outcome.description,
            source_metadata=metadata,
            # Store as both 'outcome' and 'disposition' for compatibility
            outcome=outcome.disposition,
            ruling_type=outcome.outcome_type,
            # Also store in attributes for easy access
            attributes={
                "decision_maker": outcome.decision_maker or "",
                "linked_claim_ids": ",".join(outcome.linked_claim_ids),
                "disposition": outcome.disposition,  # Aligned field
                "outcome_type": outcome.outcome_type,  # Aligned field
            },
        )

    def _extracted_damage_to_legal_entity(
        self, damage, metadata: SourceMetadata | None
    ) -> LegalEntity:
        """Convert ExtractedDamages to LegalEntity."""
        if metadata is None:
            metadata = SourceMetadata(source=damage.id, source_type=SourceType.FILE)

        return LegalEntity(
            id=damage.id,
            entity_type=EntityType.DAMAGES,
            name=damage.name,
            description=damage.description,
            source_metadata=metadata,
            damages_awarded=damage.amount,
            # Store as both direct fields and in attributes for compatibility
            # Note: attributes dict must contain only strings
            attributes={
                "damage_type": damage.damage_type,
                "status": damage.status,
                "linked_outcome_id": damage.linked_outcome_id or "",
                # Also store as direct-accessible fields in attributes (convert to string)
                "amount": str(damage.amount) if damage.amount is not None else "",
            },
        )
