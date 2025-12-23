"""
Proof Chain Service.

Builds proof chains from stored legal claims, showing:
- Required evidence (from statutes/guides)
- Presented evidence (from case)
- Missing evidence (gaps)
- Outcomes and damages
- Completeness scores
"""

from dataclasses import dataclass
from typing import Literal
import logging

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.relationships import RelationshipType


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
    
    def __init__(self, knowledge_graph: ArangoDBGraph):
        """
        Initialize the proof chain service.
        
        Args:
            knowledge_graph: ArangoDB graph connection
        """
        self.kg = knowledge_graph
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
        
        if claim.get("entity_type") != "LEGAL_CLAIM":
            self.logger.warning(f"Entity {claim_id} is not a LEGAL_CLAIM")
            return None
        
        # Get claim type string
        claim_type_str = claim.get("claim_type")
        
        # Get required evidence for this claim type
        required_evidence = []
        if claim_type_str:
            required_evidence_list = self.kg.get_required_evidence_for_claim_type(claim_type_str)
            for ev in required_evidence_list:
                required_evidence.append(ProofChainEvidence(
                    evidence_id=ev.get("_key", ""),
                    evidence_type=ev.get("evidence_type", "documentary"),
                    description=ev.get("name", ev.get("description", "")),
                    is_critical=ev.get("is_critical", False),
                    context="required",
                    source_reference=ev.get("source_reference"),
                ))
        
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
            if ev and ev.get("entity_type") == "EVIDENCE":
                presented_evidence_ids.append(ev_id)
                presented_evidence.append(ProofChainEvidence(
                    evidence_id=ev_id,
                    evidence_type=ev.get("evidence_type", "documentary"),
                    description=ev.get("name", ev.get("description", "")),
                    is_critical=ev.get("is_critical", False),
                    context="presented",
                    source_reference=ev.get("source_reference"),
                ))
        
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
            if outcome_entity and outcome_entity.get("entity_type") == "LEGAL_OUTCOME":
                outcome = {
                    "id": outcome_id,
                    "disposition": outcome_entity.get("disposition", "unknown"),
                    "description": outcome_entity.get("name", outcome_entity.get("description", "")),
                    "outcome_type": outcome_entity.get("outcome_type", "judgment"),
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
                if damage_entity and damage_entity.get("entity_type") == "DAMAGES":
                    damages.append({
                        "id": damage_id,
                        "type": damage_entity.get("damage_type", "monetary"),
                        "amount": damage_entity.get("amount"),
                        "status": damage_entity.get("status", "claimed"),
                        "description": damage_entity.get("name", damage_entity.get("description", "")),
                    })
        
        # Calculate completeness
        completeness_score = self.compute_completeness_score(
            required_evidence=required_evidence,
            satisfied_evidence=satisfied_evidence,
            missing_evidence=missing_evidence,
        )
        
        # Identify critical gaps
        critical_gaps = [
            ev.description
            for ev in missing_evidence
            if ev.is_critical
        ]
        
        return ProofChain(
            claim_id=claim_id,
            claim_description=claim.get("name", claim.get("description", "")),
            claim_type=claim_type_str,
            claimant=claim.get("claimant"),
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
                        (ev for ev in presented_evidence if ev.evidence_id == pres_ev_id),
                        None
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

