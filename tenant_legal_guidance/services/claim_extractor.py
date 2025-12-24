"""
Claim Extractor Service - Extract legal claims and evidence from legal documents.

This service implements claim-centric sequential extraction:
1. Extract all legal claims from the document first
2. For each claim, extract related evidence
3. Extract outcomes and link to claims
4. Extract damages and link to outcomes
"""

import json
import logging
from dataclasses import dataclass, field

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import (
    EntityType,
    LegalEntity,
    SourceMetadata,
    SourceType,
)
from tenant_legal_guidance.models.relationships import LegalRelationship, RelationshipType
from tenant_legal_guidance.services.deepseek import DeepSeekClient


@dataclass
class ExtractedClaim:
    """A legal claim extracted from a document."""

    id: str
    name: str
    claim_description: str
    claimant: str
    respondent_party: str | None = None
    claim_type: str | None = None  # Claim type string (e.g., "DEREGULATION_CHALLENGE")
    relief_sought: list[str] = field(default_factory=list)
    claim_status: str = "asserted"
    source_quote: str | None = None


@dataclass
class ExtractedEvidence:
    """Evidence extracted from a document."""

    id: str
    name: str
    evidence_type: str  # documentary, testimonial, factual, expert_opinion
    description: str
    evidence_context: str = "presented"  # required, presented, missing
    evidence_source_type: str = "case"  # statute, guide, case
    source_quote: str | None = None
    is_critical: bool = False
    linked_claim_ids: list[str] = field(default_factory=list)


@dataclass
class ExtractedOutcome:
    """An outcome extracted from a document."""

    id: str
    name: str
    outcome_type: str  # judgment, order, settlement, dismissal
    disposition: str  # granted, denied, dismissed, dismissed_with_prejudice, settled
    description: str
    decision_maker: str | None = None
    linked_claim_ids: list[str] = field(default_factory=list)


@dataclass
class ExtractedDamages:
    """Damages extracted from a document."""

    id: str
    name: str
    damage_type: str  # monetary, injunctive, declaratory
    amount: float | None = None
    status: str = "claimed"  # claimed, awarded, denied
    description: str = ""
    linked_outcome_id: str | None = None


@dataclass
class ClaimExtractionResult:
    """Complete result of claim extraction from a document."""

    document_id: str
    claims: list[ExtractedClaim] = field(default_factory=list)
    evidence: list[ExtractedEvidence] = field(default_factory=list)
    outcomes: list[ExtractedOutcome] = field(default_factory=list)
    damages: list[ExtractedDamages] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)


class ClaimExtractor:
    """Service for extracting legal claims and building proof chains from documents."""

    def __init__(
        self,
        llm_client: DeepSeekClient,
        knowledge_graph: ArangoDBGraph | None = None,
    ):
        self.llm_client = llm_client
        self.kg = knowledge_graph
        self.logger = logging.getLogger(__name__)

    async def extract_claims(
        self,
        text: str,
        metadata: SourceMetadata | None = None,
    ) -> ClaimExtractionResult:
        """
        Extract all legal claims from a document.

        This is the first step in claim-centric extraction.

        Args:
            text: The full text of the legal document
            metadata: Optional source metadata

        Returns:
            ClaimExtractionResult with extracted claims
        """
        self.logger.info(f"Extracting claims from document ({len(text)} chars)")

        # Generate document ID
        doc_id = self._generate_document_id(text, metadata)
        result = ClaimExtractionResult(document_id=doc_id)

        # Get claim extraction prompt
        from tenant_legal_guidance.prompts import get_claim_extraction_prompt

        prompt = get_claim_extraction_prompt(text)

        try:
            response = await self.llm_client.chat_completion(prompt)
            claims_data = self._parse_json_response(response)

            if claims_data and "claims" in claims_data:
                for i, claim_data in enumerate(claims_data["claims"]):
                    claim = self._parse_claim_data(claim_data, doc_id, i)
                    if claim:
                        result.claims.append(claim)

            self.logger.info(f"Extracted {len(result.claims)} claims")

        except Exception as e:
            self.logger.error(f"Claim extraction failed: {e}", exc_info=True)

        return result

    async def extract_evidence_for_claim(
        self,
        text: str,
        claim: ExtractedClaim,
        metadata: SourceMetadata | None = None,
    ) -> list[ExtractedEvidence]:
        """
        Extract evidence supporting a specific claim.

        Args:
            text: The full text of the legal document
            claim: The claim to find evidence for
            metadata: Optional source metadata

        Returns:
            List of evidence items linked to the claim
        """
        self.logger.info(f"Extracting evidence for claim: {claim.name}")

        from tenant_legal_guidance.prompts import get_evidence_extraction_prompt

        prompt = get_evidence_extraction_prompt(text, claim.name, claim.claim_description)

        evidence_list = []

        try:
            response = await self.llm_client.chat_completion(prompt)
            evidence_data = self._parse_json_response(response)

            if evidence_data and "evidence" in evidence_data:
                for i, evid_data in enumerate(evidence_data["evidence"]):
                    evidence = self._parse_evidence_data(evid_data, claim.id, i)
                    if evidence:
                        evidence_list.append(evidence)

            self.logger.info(
                f"Extracted {len(evidence_list)} evidence items for claim '{claim.name}'"
            )

        except Exception as e:
            self.logger.error(f"Evidence extraction failed: {e}", exc_info=True)

        return evidence_list

    async def extract_outcomes(
        self,
        text: str,
        claims: list[ExtractedClaim],
        metadata: SourceMetadata | None = None,
    ) -> list[ExtractedOutcome]:
        """
        Extract outcomes and link them to claims.

        Args:
            text: The full text of the legal document
            claims: Previously extracted claims to link outcomes to
            metadata: Optional source metadata

        Returns:
            List of outcomes linked to claims
        """
        self.logger.info("Extracting outcomes from document")

        from tenant_legal_guidance.prompts import get_outcome_extraction_prompt

        claim_names = [c.name for c in claims]
        prompt = get_outcome_extraction_prompt(text, claim_names)

        outcomes = []

        try:
            response = await self.llm_client.chat_completion(prompt)
            outcome_data = self._parse_json_response(response)

            if outcome_data and "outcomes" in outcome_data:
                for i, out_data in enumerate(outcome_data["outcomes"]):
                    outcome = self._parse_outcome_data(out_data, claims, i)
                    if outcome:
                        outcomes.append(outcome)

            self.logger.info(f"Extracted {len(outcomes)} outcomes")

        except Exception as e:
            self.logger.error(f"Outcome extraction failed: {e}", exc_info=True)

        return outcomes

    async def extract_damages(
        self,
        text: str,
        outcomes: list[ExtractedOutcome],
        metadata: SourceMetadata | None = None,
    ) -> list[ExtractedDamages]:
        """
        Extract damages and link them to outcomes.

        Args:
            text: The full text of the legal document
            outcomes: Previously extracted outcomes to link damages to
            metadata: Optional source metadata

        Returns:
            List of damages linked to outcomes
        """
        self.logger.info("Extracting damages from document")

        from tenant_legal_guidance.prompts import get_damages_extraction_prompt

        outcome_names = [o.name for o in outcomes]
        prompt = get_damages_extraction_prompt(text, outcome_names)

        damages_list = []

        try:
            response = await self.llm_client.chat_completion(prompt)
            damages_data = self._parse_json_response(response)

            if damages_data and "damages" in damages_data:
                for i, dmg_data in enumerate(damages_data["damages"]):
                    damages = self._parse_damages_data(dmg_data, outcomes, i)
                    if damages:
                        damages_list.append(damages)

            self.logger.info(f"Extracted {len(damages_list)} damages items")

        except Exception as e:
            self.logger.error(f"Damages extraction failed: {e}", exc_info=True)

        return damages_list

    async def extract_full_proof_chain(
        self,
        text: str,
        metadata: SourceMetadata | None = None,
    ) -> ClaimExtractionResult:
        """
        Extract complete proof chains: claims → evidence → outcomes → damages.

        This is the main entry point for claim-centric sequential extraction.

        Args:
            text: The full text of the legal document
            metadata: Optional source metadata

        Returns:
            Complete ClaimExtractionResult with all entities and relationships
        """
        self.logger.info("Starting full proof chain extraction")

        # Step 1: Extract claims
        result = await self.extract_claims(text, metadata)

        # Step 2: For each claim, extract evidence
        for claim in result.claims:
            evidence = await self.extract_evidence_for_claim(text, claim, metadata)
            result.evidence.extend(evidence)

            # Create HAS_EVIDENCE relationships
            for evid in evidence:
                result.relationships.append(
                    {"source_id": claim.id, "target_id": evid.id, "type": "HAS_EVIDENCE"}
                )

        # Step 3: Extract outcomes
        result.outcomes = await self.extract_outcomes(text, result.claims, metadata)

        # Create SUPPORTS relationships (evidence → outcome)
        for outcome in result.outcomes:
            for evid in result.evidence:
                if any(cid in outcome.linked_claim_ids for cid in evid.linked_claim_ids):
                    result.relationships.append(
                        {"source_id": evid.id, "target_id": outcome.id, "type": "SUPPORTS"}
                    )

        # Step 4: Extract damages
        result.damages = await self.extract_damages(text, result.outcomes, metadata)

        # Create IMPLY relationships (outcome → damages)
        for dmg in result.damages:
            if dmg.linked_outcome_id:
                result.relationships.append(
                    {"source_id": dmg.linked_outcome_id, "target_id": dmg.id, "type": "IMPLY"}
                )

                # Create RESOLVE relationships (damages → claim)
                for outcome in result.outcomes:
                    if outcome.id == dmg.linked_outcome_id:
                        for claim_id in outcome.linked_claim_ids:
                            result.relationships.append(
                                {"source_id": dmg.id, "target_id": claim_id, "type": "RESOLVE"}
                            )

        self.logger.info(
            f"Extraction complete: {len(result.claims)} claims, "
            f"{len(result.evidence)} evidence, {len(result.outcomes)} outcomes, "
            f"{len(result.damages)} damages, {len(result.relationships)} relationships"
        )

        return result

    def _generate_document_id(self, text: str, metadata: SourceMetadata | None) -> str:
        """Generate a unique document ID."""
        import hashlib

        content_hash = hashlib.sha256(text[:1000].encode()).hexdigest()[:12]
        if metadata and metadata.title:
            title_slug = metadata.title.lower().replace(" ", "_")[:30]
            return f"doc:{title_slug}_{content_hash}"
        return f"doc:{content_hash}"

    def _parse_json_response(self, response: str) -> dict | None:
        """Parse JSON from LLM response."""
        try:
            # Try to find JSON in the response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except json.JSONDecodeError as e:
            self.logger.warning(f"Failed to parse JSON: {e}")
        return None

    def _parse_claim_data(self, data: dict, doc_id: str, index: int) -> ExtractedClaim | None:
        """Parse a claim from extracted data."""
        try:
            name = data.get("name", f"Claim {index + 1}")
            # Use prefix matching EntityType.LEGAL_CLAIM.value = "legal_claim"
            return ExtractedClaim(
                id=f"legal_claim:{doc_id}:{index}",
                name=name,
                claim_description=data.get("description", data.get("claim_description", "")),
                claimant=data.get("claimant", "Unknown"),
                respondent_party=data.get("respondent", data.get("respondent_party")),
                claim_type=data.get(
                    "claim_type", data.get("claim_type_id")
                ),  # Support both for migration
                relief_sought=data.get("relief_sought", []),
                claim_status=data.get("status", data.get("claim_status", "asserted")),
                source_quote=data.get("source_quote"),
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse claim: {e}")
            return None

    def _parse_evidence_data(
        self, data: dict, claim_id: str, index: int, doc_id: str = ""
    ) -> ExtractedEvidence | None:
        """Parse evidence from extracted data."""
        try:
            name = data.get("name", f"Evidence {index + 1}")
            # Use prefix matching EntityType.EVIDENCE.value = "evidence"
            return ExtractedEvidence(
                id=f"evidence:{doc_id}:{index}",
                name=name,
                evidence_type=data.get("type", data.get("evidence_type", "documentary")),
                description=data.get("description", ""),
                evidence_context="presented",
                evidence_source_type="case",
                source_quote=data.get("source_quote", data.get("quote")),
                is_critical=data.get("is_critical", False),
                linked_claim_ids=[claim_id],
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse evidence: {e}")
            return None

    def _parse_outcome_data(
        self, data: dict, claims: list[ExtractedClaim], index: int, doc_id: str = ""
    ) -> ExtractedOutcome | None:
        """Parse an outcome from extracted data."""
        try:
            name = data.get("name", f"Outcome {index + 1}")

            # Link to claims by name matching
            linked_claim_ids = []
            linked_claims = data.get("linked_claims", data.get("claims", []))
            for claim in claims:
                if claim.name in linked_claims or any(
                    claim.name.lower() in lc.lower() for lc in linked_claims
                ):
                    linked_claim_ids.append(claim.id)

            # Use prefix matching EntityType.LEGAL_OUTCOME.value = "legal_outcome"
            return ExtractedOutcome(
                id=f"legal_outcome:{doc_id}:{index}",
                name=name,
                outcome_type=data.get("type", data.get("outcome_type", "judgment")),
                disposition=data.get("disposition", "unknown"),
                description=data.get("description", ""),
                decision_maker=data.get("decision_maker", data.get("judge")),
                linked_claim_ids=linked_claim_ids,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse outcome: {e}")
            return None

    def _parse_damages_data(
        self, data: dict, outcomes: list[ExtractedOutcome], index: int, doc_id: str = ""
    ) -> ExtractedDamages | None:
        """Parse damages from extracted data."""
        try:
            name = data.get("name", f"Damages {index + 1}")

            # Link to outcome by name matching
            linked_outcome_id = None
            linked_outcome_name = data.get("linked_outcome", data.get("outcome", ""))
            for outcome in outcomes:
                if (
                    outcome.name.lower() in linked_outcome_name.lower()
                    or linked_outcome_name.lower() in outcome.name.lower()
                ):
                    linked_outcome_id = outcome.id
                    break

            # Parse amount
            amount = data.get("amount")
            if isinstance(amount, str):
                # Try to extract numeric value
                import re

                match = re.search(r"[\d,]+\.?\d*", amount.replace(",", ""))
                if match:
                    amount = float(match.group())
                else:
                    amount = None

            # Use prefix matching EntityType.DAMAGES.value = "damages"
            return ExtractedDamages(
                id=f"damages:{doc_id}:{index}",
                name=name,
                damage_type=data.get("type", data.get("damage_type", "monetary")),
                amount=amount,
                status=data.get("status", "claimed"),
                description=data.get("description", ""),
                linked_outcome_id=linked_outcome_id,
            )
        except Exception as e:
            self.logger.warning(f"Failed to parse damages: {e}")
            return None

    async def extract_full_proof_chain_single(
        self,
        text: str,
        metadata: SourceMetadata | None = None,
    ) -> ClaimExtractionResult:
        """
        Extract complete proof chains in a SINGLE LLM call.

        This is faster and produces better-connected results because the LLM
        can reason about the entire document holistically.

        Args:
            text: The full text of the legal document
            metadata: Optional source metadata

        Returns:
            Complete ClaimExtractionResult with all entities and relationships
        """
        import time

        start_time = time.time()

        self.logger.info("Starting single-call proof chain extraction")

        # Generate document ID
        doc_id = self._generate_document_id(text, metadata)
        result = ClaimExtractionResult(document_id=doc_id)

        # Get the megaprompt
        from tenant_legal_guidance.prompts import get_full_proof_chain_prompt

        prompt = get_full_proof_chain_prompt(text)

        try:
            response = await self.llm_client.chat_completion(prompt)
            data = self._parse_json_response(response)

            if not data:
                self.logger.warning("Failed to parse megaprompt response")
                return result

            # Build ID mapping for relationship linking
            claim_id_map = {}  # original_id -> our_id
            evid_id_map = {}
            outcome_id_map = {}
            damages_id_map = {}

            # Parse claims - use prefix matching EntityType.LEGAL_CLAIM.value
            for i, claim_data in enumerate(data.get("claims", [])):
                orig_id = claim_data.get("id", f"claim_{i}")
                our_id = f"legal_claim:{doc_id}:{i}"
                claim_id_map[orig_id] = our_id

                claim = ExtractedClaim(
                    id=our_id,
                    name=claim_data.get("name", f"Claim {i + 1}"),
                    claim_description=claim_data.get("description", ""),
                    claimant=claim_data.get("claimant", "Unknown"),
                    respondent_party=claim_data.get("respondent"),
                    relief_sought=claim_data.get("relief_sought", []),
                    claim_status=claim_data.get("status", "asserted"),
                    source_quote=claim_data.get("source_quote"),
                )
                result.claims.append(claim)

            # Parse evidence - use prefix matching EntityType.EVIDENCE.value
            for i, evid_data in enumerate(data.get("evidence", [])):
                orig_id = evid_data.get("id", f"evid_{i}")
                our_id = f"evidence:{doc_id}:{i}"
                evid_id_map[orig_id] = our_id

                # Map claim IDs
                linked_claims = []
                for cid in evid_data.get("claim_ids", []):
                    if cid in claim_id_map:
                        linked_claims.append(claim_id_map[cid])

                evidence = ExtractedEvidence(
                    id=our_id,
                    name=evid_data.get("name", f"Evidence {i + 1}"),
                    evidence_type=evid_data.get("type", "documentary"),
                    description=evid_data.get("description", ""),
                    evidence_context="presented",
                    evidence_source_type="case",
                    source_quote=evid_data.get("source_quote"),
                    is_critical=evid_data.get("is_critical", False),
                    linked_claim_ids=linked_claims,
                )
                result.evidence.append(evidence)

            # Parse outcomes - use prefix matching EntityType.LEGAL_OUTCOME.value
            for i, out_data in enumerate(data.get("outcomes", [])):
                orig_id = out_data.get("id", f"outcome_{i}")
                our_id = f"legal_outcome:{doc_id}:{i}"
                outcome_id_map[orig_id] = our_id

                # Map claim IDs
                linked_claims = []
                for cid in out_data.get("claim_ids", []):
                    if cid in claim_id_map:
                        linked_claims.append(claim_id_map[cid])

                outcome = ExtractedOutcome(
                    id=our_id,
                    name=out_data.get("name", f"Outcome {i + 1}"),
                    outcome_type=out_data.get("type", "judgment"),
                    disposition=out_data.get("disposition", "unknown"),
                    description=out_data.get("description", ""),
                    decision_maker=out_data.get("decision_maker"),
                    linked_claim_ids=linked_claims,
                )
                result.outcomes.append(outcome)

            # Parse damages - use prefix matching EntityType.DAMAGES.value
            for i, dmg_data in enumerate(data.get("damages", [])):
                orig_id = dmg_data.get("id", f"dmg_{i}")
                our_id = f"damages:{doc_id}:{i}"
                damages_id_map[orig_id] = our_id

                # Map outcome ID
                linked_outcome = None
                out_id = dmg_data.get("outcome_id")
                if out_id and out_id in outcome_id_map:
                    linked_outcome = outcome_id_map[out_id]

                # Parse amount
                amount = dmg_data.get("amount")
                if isinstance(amount, str):
                    import re

                    match = re.search(r"[\d,]+\.?\d*", amount.replace(",", ""))
                    amount = float(match.group()) if match else None

                damages = ExtractedDamages(
                    id=our_id,
                    name=dmg_data.get("name", f"Damages {i + 1}"),
                    damage_type=dmg_data.get("type", "monetary"),
                    amount=amount,
                    status=dmg_data.get("status", "claimed"),
                    description=dmg_data.get("description", ""),
                    linked_outcome_id=linked_outcome,
                )
                result.damages.append(damages)

            # Parse relationships from LLM output
            for rel_data in data.get("relationships", []):
                source_orig = rel_data.get("source")
                target_orig = rel_data.get("target")
                rel_type = rel_data.get("type")

                # Map to our IDs
                source_id = (
                    claim_id_map.get(source_orig)
                    or evid_id_map.get(source_orig)
                    or outcome_id_map.get(source_orig)
                    or damages_id_map.get(source_orig)
                    or source_orig
                )
                target_id = (
                    claim_id_map.get(target_orig)
                    or evid_id_map.get(target_orig)
                    or outcome_id_map.get(target_orig)
                    or damages_id_map.get(target_orig)
                    or target_orig
                )

                result.relationships.append(
                    {
                        "source_id": source_id,
                        "target_id": target_id,
                        "type": rel_type,
                    }
                )

            # Store proof gaps as metadata (optional extension)
            proof_gaps = data.get("proof_gaps", [])
            if proof_gaps:
                self.logger.info(f"Found {len(proof_gaps)} proof gaps")

            elapsed = time.time() - start_time
            self.logger.info(
                f"Single-call extraction complete in {elapsed:.1f}s: "
                f"{len(result.claims)} claims, {len(result.evidence)} evidence, "
                f"{len(result.outcomes)} outcomes, {len(result.damages)} damages, "
                f"{len(result.relationships)} relationships"
            )

        except Exception as e:
            self.logger.error(f"Single-call extraction failed: {e}", exc_info=True)

        return result

    async def _extract_claim_type(
        self,
        claim: ExtractedClaim,
    ) -> str | None:
        """
        Extract claim type string from claim.

        Returns:
            claim_type string (e.g., "DEREGULATION_CHALLENGE") or None
        """
        # If claim already has a claim_type, use it
        if claim.claim_type:
            return claim.claim_type

        # Try to infer from claim name/description using keyword matching
        claim_name_lower = claim.name.lower()
        claim_desc_lower = (claim.claim_description or "").lower()
        combined = f"{claim_name_lower} {claim_desc_lower}"

        # Key terms for common claim types
        type_keywords = {
            "RENT_OVERCHARGE": ["rent overcharge", "overcharge", "illegal rent", "rent too high"],
            "DEREGULATION_CHALLENGE": [
                "deregulation",
                "decontrol",
                "high rent vacancy",
                "rent stabilized",
                "deregulated",
            ],
            "HP_ACTION_REPAIRS": [
                "hp action",
                "repairs",
                "violations",
                "habitability",
                "housing part",
            ],
            "HARASSMENT": ["harassment", "harass", "intimidate"],
            "SECURITY_DEPOSIT_RETURN": ["security deposit", "deposit return"],
        }

        for claim_type, keywords in type_keywords.items():
            if any(keyword in combined for keyword in keywords):
                self.logger.info(f"Inferred claim type '{claim_type}' for '{claim.name}'")
                return claim_type

        # Fallback: generate from claim name
        claim_type = claim.name.upper().replace(" ", "_").replace("-", "_")[:50]
        self.logger.info(f"Generated claim type '{claim_type}' from claim name '{claim.name}'")
        return claim_type

    async def store_to_graph(
        self,
        result: ClaimExtractionResult,
        source_metadata: SourceMetadata | None = None,
    ) -> dict:
        """
        Store extracted entities and relationships to the knowledge graph.

        Args:
            result: The ClaimExtractionResult to persist
            source_metadata: Optional source metadata for provenance

        Returns:
            dict with counts of stored entities and relationships
        """
        if not self.kg:
            self.logger.warning("No knowledge graph configured, skipping storage")
            return {"stored": False, "reason": "no_knowledge_graph"}

        self.logger.info(f"Storing extraction results to graph: {result.document_id}")

        stored = {
            "claims": 0,
            "evidence": 0,
            "outcomes": 0,
            "damages": 0,
            "relationships": 0,
        }

        # Build source metadata for provenance
        if source_metadata is None:
            source_metadata = SourceMetadata(
                source=result.document_id,
                source_type=SourceType.FILE,
            )

        # Store claims as LEGAL_CLAIM entities
        for claim in result.claims:
            # Extract claim type string
            claim_type = await self._extract_claim_type(claim)

            entity = LegalEntity(
                id=claim.id,
                entity_type=EntityType.LEGAL_CLAIM,
                name=claim.name,
                description=claim.claim_description,
                source_metadata=source_metadata,
                # Legal claim specific fields
                claim_description=claim.claim_description,
                claimant=claim.claimant,
                respondent_party=claim.respondent_party,
                claim_type=claim_type,  # Claim type string
                relief_sought=claim.relief_sought,
                claim_status=claim.claim_status,
            )
            if self.kg.add_entity(entity, overwrite=True):
                stored["claims"] += 1

        # Store evidence as EVIDENCE entities
        for evid in result.evidence:
            entity = LegalEntity(
                id=evid.id,
                entity_type=EntityType.EVIDENCE,
                name=evid.name,
                description=evid.description,
                source_metadata=source_metadata,
                # Evidence specific fields
                evidence_context=evid.evidence_context,
                evidence_source_type=evid.evidence_source_type,
                is_critical=evid.is_critical,
                attributes={
                    "evidence_type": evid.evidence_type,
                    "source_quote": evid.source_quote or "",
                    "linked_claim_ids": ",".join(evid.linked_claim_ids),
                },
            )
            if self.kg.add_entity(entity, overwrite=True):
                stored["evidence"] += 1

        # Store outcomes as LEGAL_OUTCOME entities
        for outcome in result.outcomes:
            entity = LegalEntity(
                id=outcome.id,
                entity_type=EntityType.LEGAL_OUTCOME,
                name=outcome.name,
                description=outcome.description,
                source_metadata=source_metadata,
                # Outcome specific fields
                outcome=outcome.disposition,
                ruling_type=outcome.outcome_type,
                attributes={
                    "decision_maker": outcome.decision_maker or "",
                    "linked_claim_ids": ",".join(outcome.linked_claim_ids),
                },
            )
            if self.kg.add_entity(entity, overwrite=True):
                stored["outcomes"] += 1

        # Store damages as DAMAGES entities
        for dmg in result.damages:
            entity = LegalEntity(
                id=dmg.id,
                entity_type=EntityType.DAMAGES,
                name=dmg.name,
                description=dmg.description,
                source_metadata=source_metadata,
                # Damages specific fields
                damages_awarded=dmg.amount,
                attributes={
                    "damage_type": dmg.damage_type,
                    "status": dmg.status,
                    "linked_outcome_id": dmg.linked_outcome_id or "",
                },
            )
            if self.kg.add_entity(entity, overwrite=True):
                stored["damages"] += 1

        # Store relationships
        for rel in result.relationships:
            try:
                rel_type = RelationshipType[rel["type"]]
                relationship = LegalRelationship(
                    source_id=rel["source_id"],
                    target_id=rel["target_id"],
                    relationship_type=rel_type,
                )
                if self.kg.add_relationship(relationship):
                    stored["relationships"] += 1
            except (KeyError, ValueError) as e:
                self.logger.warning(f"Failed to store relationship {rel}: {e}")

        self.logger.info(
            f"Stored to graph: {stored['claims']} claims, {stored['evidence']} evidence, "
            f"{stored['outcomes']} outcomes, {stored['damages']} damages, "
            f"{stored['relationships']} relationships"
        )

        return stored

    async def extract_and_store(
        self,
        text: str,
        metadata: SourceMetadata | None = None,
    ) -> tuple[ClaimExtractionResult, dict]:
        """
        Extract claims and store to graph in one operation.

        Args:
            text: The legal document text
            metadata: Optional source metadata

        Returns:
            Tuple of (extraction_result, storage_counts)
        """
        result = await self.extract_full_proof_chain_single(text, metadata)
        stored = await self.store_to_graph(result, metadata)
        return result, stored

    def get_stored_claims(self, document_id: str) -> list[dict]:
        """
        Retrieve claims stored for a document.

        Args:
            document_id: The document ID to query

        Returns:
            List of claim documents from the graph
        """
        if not self.kg:
            return []

        try:
            aql = """
            FOR doc IN entities
                FILTER doc.type == "legal_claim"
                FILTER STARTS_WITH(doc._key, @doc_prefix)
                RETURN doc
            """
            cursor = self.kg.db.aql.execute(aql, bind_vars={"doc_prefix": document_id})
            return list(cursor)
        except Exception as e:
            self.logger.error(f"Failed to retrieve claims: {e}")
            return []

    def get_stored_evidence(self, claim_id: str) -> list[dict]:
        """
        Retrieve evidence linked to a claim.

        Args:
            claim_id: The claim ID to query

        Returns:
            List of evidence documents from the graph
        """
        if not self.kg:
            return []

        try:
            # Find evidence linked via HAS_EVIDENCE relationship
            aql = """
            FOR edge IN edges
                FILTER edge._from == CONCAT("entities/", @claim_id)
                FILTER edge.type == "HAS_EVIDENCE"
                LET evid = DOCUMENT(edge._to)
                RETURN evid
            """
            cursor = self.kg.db.aql.execute(aql, bind_vars={"claim_id": claim_id})
            return list(cursor)
        except Exception as e:
            self.logger.error(f"Failed to retrieve evidence: {e}")
            return []
