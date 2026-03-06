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
import re
from dataclasses import dataclass, field

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.claim_types import ClaimType
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
    claim_type: ClaimType | None = None  # Validated ClaimType enum
    relief_sought: list[str] = field(default_factory=list)
    claim_status: str = "asserted"
    source_quote: str | None = None
    case_id: str | None = None  # Link to source CASE_DOCUMENT


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
    linked_claim_type: ClaimType | None = None  # For required evidence (links to ClaimType)
    case_id: str | None = None  # Link to source CASE_DOCUMENT


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
    source_quote: str | None = None


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
    # Typed prompt entity types (no full dataclass — stored as raw dicts)
    laws: list[dict] = field(default_factory=list)
    procedures: list[dict] = field(default_factory=list)


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

    def _generate_document_id(self, text: str, metadata: SourceMetadata | None) -> str:
        """Generate a unique document ID."""
        import hashlib

        content_hash = hashlib.sha256(text[:1000].encode()).hexdigest()[:12]
        if metadata and metadata.title:
            title_slug = metadata.title.lower().replace(" ", "_")[:30]
            return f"doc:{title_slug}_{content_hash}"
        return f"doc:{content_hash}"

    def _parse_json_response(self, response: str) -> dict | None:
        """Parse JSON from LLM response with multiple fallback strategies."""

        # Try direct parsing first
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try extracting from code block without language specifier
        json_match = re.search(r"```\s*([\s\S]*?)\s*```", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try finding JSON object between first { and last }
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(response[start:end])
            except json.JSONDecodeError as e:
                self.logger.warning(f"Failed to parse JSON: {e}")

        # Try to fix common JSON issues and retry
        try:
            # Remove trailing commas before } or ]
            fixed = re.sub(r",\s*}", "}", response)
            fixed = re.sub(r",\s*]", "]", fixed)
            # Try parsing the fixed version
            start = fixed.find("{")
            end = fixed.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(fixed[start:end])
        except (json.JSONDecodeError, Exception):
            pass

        self.logger.warning("Failed to parse JSON response after all fallback strategies")
        return None

    @staticmethod
    def _make_entity_id(entity_type: str, name: str) -> str:
        """Generate a stable, source-independent entity ID from type + name.

        Uses the same algorithm as EntityService.generate_entity_id so entities
        extracted by either path produce the same ID for the same concept.
        Format: {type}:{sha256[:8]}
        """
        import hashlib
        hash_input = f"{entity_type}:{name}".lower()
        return f"{entity_type}:{hashlib.sha256(hash_input.encode()).hexdigest()[:8]}"

    def _parse_claim_data(self, data: dict, doc_id: str, index: int) -> ExtractedClaim | None:
        """Parse a claim from extracted data."""
        try:
            name = data.get("name", f"Claim {index + 1}")

            # Convert string claim_type to ClaimType enum
            claim_type_str = data.get("claim_type", data.get("claim_type_id"))
            claim_type = ClaimType.from_string(claim_type_str) if claim_type_str else None

            return ExtractedClaim(
                id=self._make_entity_id("legal_claim", name),
                name=name,
                claim_description=data.get("description", data.get("claim_description", "")),
                claimant=data.get("claimant", "Unknown"),
                respondent_party=data.get("respondent", data.get("respondent_party")),
                claim_type=claim_type,
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
            return ExtractedEvidence(
                id=self._make_entity_id("evidence", name),
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

            return ExtractedOutcome(
                id=self._make_entity_id("legal_outcome", name),
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

            return ExtractedDamages(
                id=self._make_entity_id("damages", name),
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

        # Route to the correct typed prompt based on document_type
        from tenant_legal_guidance.models.entities import LegalDocumentType
        from tenant_legal_guidance.prompts import (
            get_case_extraction_prompt,
            get_guide_extraction_prompt,
            get_statute_extraction_prompt,
        )

        GUIDE_TYPES = {
            LegalDocumentType.LEGAL_GUIDE,
            LegalDocumentType.TENANT_HANDBOOK,
            LegalDocumentType.ADVOCACY_DOCUMENT,
        }

        doc_type = metadata.document_type if metadata else None

        if doc_type == LegalDocumentType.STATUTE:
            prompt = get_statute_extraction_prompt(text)
        elif doc_type in GUIDE_TYPES:
            prompt = get_guide_extraction_prompt(text)
        elif doc_type == LegalDocumentType.COURT_OPINION:
            prompt = get_case_extraction_prompt(text)
        else:
            raise ValueError(
                f"document_type is required for extraction; got: {doc_type!r}. "
                "Set document_type in the manifest entry (statute, court_opinion, "
                "legal_guide, tenant_handbook, or advocacy_document)."
            )

        try:
            response = await self.llm_client.chat_completion(prompt)
            data = self._parse_json_response(response)

            if not data:
                self.logger.warning("Failed to parse typed prompt response")
                return result

            result = self._parse_typed_response(data, doc_id, result)

            elapsed = time.time() - start_time
            self.logger.info(
                f"Single-call extraction complete in {elapsed:.1f}s: "
                f"{len(result.claims)} claims, {len(result.evidence)} evidence, "
                f"{len(result.outcomes)} outcomes, {len(result.relationships)} relationships"
            )

        except ValueError:
            raise
        except Exception as e:
            self.logger.error(f"Single-call extraction failed: {e}", exc_info=True)

        return result

    def _parse_typed_response(
        self,
        data: dict,
        doc_id: str,
        result: "ClaimExtractionResult",
    ) -> "ClaimExtractionResult":
        """
        Parse the 5-type typed prompt response into a ClaimExtractionResult.

        Handles output from get_statute/guide/case_extraction_prompt(), which share
        the same schema: laws, claims, evidence, procedures, outcomes, relationships.

        Relationship IDs use the short LLM IDs (e.g. "c1", "e2") that are mapped
        to our internal IDs before appending to result.relationships.
        """
        # Build per-type ID maps: llm short id → our internal id
        claim_id_map: dict[str, str] = {}
        evid_id_map: dict[str, str] = {}
        outcome_id_map: dict[str, str] = {}
        procedure_id_map: dict[str, str] = {}
        law_id_map: dict[str, str] = {}

        # Parse claims
        for i, claim_data in enumerate(data.get("claims", [])):
            orig_id = claim_data.get("id", f"claim_{i}")
            name = claim_data.get("name", f"Claim {i + 1}")
            our_id = self._make_entity_id("legal_claim", name)
            claim_id_map[orig_id] = our_id

            claim = ExtractedClaim(
                id=our_id,
                name=name,
                claim_description=claim_data.get("description", ""),
                claimant=claim_data.get("claimant", "Unknown"),
                respondent_party=claim_data.get("respondent"),
                relief_sought=claim_data.get("relief_sought", []),
                claim_status=claim_data.get("status", "asserted"),
                source_quote=claim_data.get("source_quote"),
            )
            result.claims.append(claim)

        # Parse evidence
        for i, evid_data in enumerate(data.get("evidence", [])):
            orig_id = evid_data.get("id", f"evid_{i}")
            name = evid_data.get("name", f"Evidence {i + 1}")
            our_id = self._make_entity_id("evidence", name)
            evid_id_map[orig_id] = our_id

            linked_claims = [
                claim_id_map[cid]
                for cid in evid_data.get("claim_ids", [])
                if cid in claim_id_map
            ]

            evidence = ExtractedEvidence(
                id=our_id,
                name=name,
                evidence_type=evid_data.get("type", "documentary"),
                description=evid_data.get("description", ""),
                evidence_context=evid_data.get("evidence_context", "required"),
                evidence_source_type=evid_data.get("evidence_source_type", "statute"),
                source_quote=evid_data.get("source_quote"),
                is_critical=evid_data.get("is_critical", False),
                linked_claim_ids=linked_claims,
            )
            result.evidence.append(evidence)

        # Parse outcomes (subsumes old damages — monetary outcomes use outcome_type='monetary')
        for i, out_data in enumerate(data.get("outcomes", [])):
            orig_id = out_data.get("id", f"outcome_{i}")
            name = out_data.get("name", f"Outcome {i + 1}")
            our_id = self._make_entity_id("legal_outcome", name)
            outcome_id_map[orig_id] = our_id

            linked_claims = [
                claim_id_map[cid]
                for cid in out_data.get("claim_ids", [])
                if cid in claim_id_map
            ]

            outcome = ExtractedOutcome(
                id=our_id,
                name=name,
                outcome_type=out_data.get("outcome_type", out_data.get("type", "judgment")),
                disposition=out_data.get("disposition", "unknown"),
                description=out_data.get("description", ""),
                decision_maker=out_data.get("decision_maker"),
                linked_claim_ids=linked_claims,
                source_quote=out_data.get("source_quote"),
            )
            result.outcomes.append(outcome)

        # Parse procedures
        for i, proc_data in enumerate(data.get("procedures", [])):
            orig_id = proc_data.get("id", f"proc_{i}")
            name = proc_data.get("name", f"Procedure {i + 1}")
            our_id = self._make_entity_id("legal_procedure", name)
            procedure_id_map[orig_id] = our_id
            result.procedures.append({
                "id": our_id,
                "name": name,
                "description": proc_data.get("description", ""),
                "steps": proc_data.get("steps", []),
                "source_quote": proc_data.get("source_quote", ""),
            })

        # Parse laws — use citation as hash key when available so "RPL § 235-b"
        # from a statute and "Warranty of Habitability (RPL § 235-b)" from a case
        # both map to the same entity ID.
        for i, law_data in enumerate(data.get("laws", [])):
            orig_id = law_data.get("id", f"law_{i}")
            name = law_data.get("name", f"Law {i + 1}")
            key_text = law_data.get("citation") or name
            our_id = self._make_entity_id("law", key_text)
            law_id_map[orig_id] = our_id
            result.laws.append({
                "id": our_id,
                "name": name,
                "description": law_data.get("description", ""),
                "citation": law_data.get("citation", ""),
                "source_quote": law_data.get("source_quote", ""),
            })

        # Build unified ID lookup for relationship resolution
        all_id_maps = {**claim_id_map, **evid_id_map, **outcome_id_map,
                       **procedure_id_map, **law_id_map}

        # Parse relationships — typed prompt uses "from"/"to" keys
        for rel_data in data.get("relationships", []):
            from_orig = rel_data.get("from") or rel_data.get("source")
            to_orig = rel_data.get("to") or rel_data.get("target")
            rel_type = rel_data.get("type", "")

            from_id = all_id_maps.get(from_orig, from_orig)
            to_id = all_id_maps.get(to_orig, to_orig)

            result.relationships.append(
                {
                    "source_id": from_id,
                    "target_id": to_id,
                    "type": rel_type,
                }
            )

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
