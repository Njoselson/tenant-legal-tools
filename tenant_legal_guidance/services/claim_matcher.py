"""
Claim Matcher Service - Match user situations to claim types and assess evidence.

This service implements the "Analyze My Case" functionality:
1. Match user's situation description to relevant claim types
2. Assess which required evidence they have vs. need
3. Identify evidence gaps with actionable advice
4. Generate next steps
"""

import logging
from dataclasses import dataclass

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.services.deepseek import DeepSeekClient


@dataclass
class EvidenceMatch:
    """Evidence matching result."""

    evidence_id: str
    evidence_name: str
    match_score: float
    user_evidence_description: str | None = None
    is_critical: bool = False
    status: str = "matched"  # "matched", "partial", "missing"


@dataclass
class ClaimTypeMatch:
    """Claim type matching result."""

    claim_type_id: str
    claim_type_name: str
    canonical_name: str
    match_score: float
    evidence_matches: list[EvidenceMatch]
    evidence_strength: str  # "strong", "moderate", "weak"
    evidence_gaps: list[dict]
    completeness_score: float  # 0.0-1.0


@dataclass
class AnalysisResult:
    """Complete analysis result."""

    possible_claims: list[ClaimTypeMatch]
    next_steps: list[str]
    similar_cases: list[dict] | None = None


class ClaimMatcher:
    """Match user situations to claim types and assess evidence."""

    def __init__(
        self,
        knowledge_graph: ArangoDBGraph,
        llm_client: DeepSeekClient,
    ):
        self.kg = knowledge_graph
        self.llm_client = llm_client
        self.logger = logging.getLogger(__name__)

    async def extract_evidence_from_situation(
        self,
        situation: str,
    ) -> list[str]:
        """
        Automatically extract evidence items from user's situation description.

        Uses LLM to identify what evidence the user has based on what they mention.

        Args:
            situation: User's description of their legal situation

        Returns:
            List of evidence items extracted from the description
        """
        prompt = f"""Analyze the following tenant situation and extract all evidence items that the tenant mentions having or could have.

TENANT SITUATION:
{situation}

Extract evidence items that are:
1. Explicitly mentioned (e.g., "I have my lease", "I have photos")
2. Implied from context (e.g., "My lease shows $2,200/month" → "Lease document")
3. Documents/records they likely have (e.g., "I've been here since 2015" → "Lease history")

Return a JSON array of evidence items, one per line. Be specific and descriptive.

Example output:
[
  "Lease document showing $2,200/month rent",
  "Building registration showing pre-1974 construction",
  "DHCR registration history",
  "No rent stabilization rider in lease",
  "Letters from landlord"
]

Return ONLY the JSON array, nothing else.
"""

        try:
            response = await self.llm_client.chat_completion(prompt)
            import json

            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                evidence = json.loads(response[start:end])
                self.logger.info(f"Extracted {len(evidence)} evidence items from situation")
                return evidence
        except Exception as e:
            self.logger.warning(f"Failed to extract evidence from situation: {e}")

        return []

    async def match_situation_to_claim_types(
        self,
        situation: str,
        evidence_i_have: list[str] | None = None,
        auto_extract_evidence: bool = True,
        jurisdiction: str = "NYC",
    ) -> tuple[list[ClaimTypeMatch], list[str]]:
        """
        Match user's situation to relevant claim types using a single megaprompt.

        This is faster and more coherent than sequential calls because the LLM
        can reason about the entire situation holistically.

        Args:
            situation: User's description of their legal situation
            evidence_i_have: Optional list of evidence items (will be included in prompt)
            auto_extract_evidence: If True, evidence will be auto-extracted in the megaprompt
            jurisdiction: Jurisdiction (default: "NYC")

        Returns:
            List of matching claim types with evidence assessment
        """
        # Early return for empty/whitespace-only inputs to avoid expensive API calls
        if not situation or not situation.strip():
            return [], []

        # Get all unique claim types from stored claims
        all_claim_types = self.kg.get_all_claim_types()

        if not all_claim_types:
            self.logger.warning("No claim types found in stored claims")
            # Fallback to common claim types
            all_claim_types = [
                "DEREGULATION_CHALLENGE",
                "RENT_OVERCHARGE",
                "HP_ACTION_REPAIRS",
                "HARASSMENT",
                "SECURITY_DEPOSIT_RETURN",
            ]

        # Build claim types with required evidence
        claim_types_data = []
        for claim_type_item in all_claim_types:
            # Handle both string and dict formats
            if isinstance(claim_type_item, dict):
                claim_type_str = claim_type_item.get("canonical_name") or claim_type_item.get(
                    "name", ""
                )
            else:
                claim_type_str = str(claim_type_item)

            required_evidence = self.kg.get_required_evidence_for_claim_type(claim_type_str)
            claim_types_data.append(
                {
                    "canonical_name": claim_type_str,
                    "display_name": claim_type_str.replace("_", " ").title(),
                    "required_evidence": [
                        {
                            "name": ev.get("name", ""),
                            "description": ev.get("description", ""),
                            "is_critical": ev.get("is_critical", False),
                        }
                        for ev in required_evidence
                    ],
                }
            )

        if not claim_types_data:
            self.logger.warning("No claim types with evidence found")
            return [], []

        # Use megaprompt for everything in one call
        self.logger.info("Using megaprompt for analyze-my-case (extract + match + assess)")

        from tenant_legal_guidance.prompts import get_analyze_my_case_megaprompt

        prompt = get_analyze_my_case_megaprompt(
            situation=situation,
            claim_types=claim_types_data,
            user_evidence=evidence_i_have if evidence_i_have else None,
        )

        try:
            response = await self.llm_client.chat_completion(prompt)

            # Parse JSON response
            import json

            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])

                # Get extracted evidence (for logging/display)
                extracted_evidence = data.get("extracted_evidence", [])
                if extracted_evidence:
                    self.logger.info(
                        f"Megaprompt extracted {len(extracted_evidence)} evidence items"
                    )

                # Process matched claim types
                matched_claims = data.get("matched_claim_types", [])
                results = []

                for match_data in matched_claims:
                    canonical = match_data.get("claim_type_canonical", "").upper()

                    # Find the claim type data
                    claim_type_data = next(
                        (
                            ct
                            for ct in claim_types_data
                            if ct.get("canonical_name", "").upper() == canonical
                        ),
                        None,
                    )
                    if not claim_type_data:
                        self.logger.warning(f"Could not find claim type for canonical: {canonical}")
                        continue

                    # Get required evidence for this claim type
                    required_evidence = self.kg.get_required_evidence_for_claim_type(canonical)

                    # Convert evidence assessment to EvidenceMatch objects
                    evidence_assessment = []
                    for ev_assess in match_data.get("evidence_assessment", []):
                        req_evid_name = ev_assess.get("required_evidence_name")

                        # Find the required evidence entity
                        req_evid = next(
                            (ev for ev in required_evidence if ev.get("name") == req_evid_name),
                            None,
                        )
                        if req_evid:
                            evidence_assessment.append(
                                EvidenceMatch(
                                    evidence_id=req_evid.get("_key", ""),
                                    evidence_name=req_evid_name,
                                    match_score=ev_assess.get("match_score", 0.0),
                                    user_evidence_description=ev_assess.get("user_evidence_match"),
                                    is_critical=ev_assess.get("is_critical", False),
                                    status=ev_assess.get("status", "missing"),
                                )
                            )

                    # Calculate completeness
                    completeness = self._calculate_completeness(evidence_assessment)

                    # Identify gaps
                    gaps = self._identify_evidence_gaps(evidence_assessment)

                    results.append(
                        ClaimTypeMatch(
                            claim_type_id=canonical,  # Use claim_type string as ID
                            claim_type_name=claim_type_data.get("display_name", canonical),
                            canonical_name=canonical,
                            match_score=match_data.get("match_score", 0.0),
                            evidence_matches=evidence_assessment,
                            evidence_strength=self._determine_strength(
                                completeness, evidence_assessment
                            ),
                            evidence_gaps=gaps,
                            completeness_score=completeness,
                        )
                    )

                # Sort by match score
                results.sort(key=lambda x: x.match_score, reverse=True)
                return results, extracted_evidence

        except json.JSONDecodeError as e:
            self.logger.warning(f"Failed to parse megaprompt JSON: {e}, response: {response[:200]}")
        except Exception as e:
            self.logger.warning(f"Megaprompt analysis failed: {e}, falling back to sequential")
            # Fallback to sequential if megaprompt fails
            matches, extracted = await self._match_situation_sequential(
                situation=situation,
                evidence_i_have=evidence_i_have or [],
                claim_types=claim_types_data,
            )
            return matches, extracted

        return [], []

    async def _match_situation_sequential(
        self,
        situation: str,
        evidence_i_have: list[str],
        claim_types: list[dict],
    ) -> tuple[list[ClaimTypeMatch], list[str]]:
        """Fallback sequential matching if megaprompt fails."""
        # Extract evidence first
        extracted_evidence = await self.extract_evidence_from_situation(situation)
        if not evidence_i_have:
            evidence_i_have = extracted_evidence
        # Use LLM to match situation to claim types
        matched_types = await self._llm_match_situation(
            situation=situation,
            claim_types=claim_types,
        )

        # Fallback: if no LLM matches, try keyword matching
        if not matched_types:
            self.logger.info("LLM matching returned no results, trying keyword fallback")
            matched_types = self._keyword_match_situation(situation, claim_types)

        # For each matched type, assess evidence
        results = []
        for match in matched_types:
            claim_type = next(
                (ct for ct in claim_types if ct["_key"] == match["claim_type_id"]), None
            )
            if not claim_type:
                continue

            # Assess evidence strength
            evidence_assessment = await self._assess_evidence_strength(
                user_evidence=evidence_i_have,
                required_evidence=claim_type.get("required_evidence", []),
                claim_type_name=claim_type.get("display_name", claim_type.get("name")),
            )

            # Calculate completeness
            completeness = self._calculate_completeness(evidence_assessment)

            # Identify gaps
            gaps = self._identify_evidence_gaps(evidence_assessment)

            results.append(
                ClaimTypeMatch(
                    claim_type_id=claim_type["_key"],
                    claim_type_name=claim_type.get("display_name", claim_type.get("name")),
                    canonical_name=claim_type.get("canonical_name", ""),
                    match_score=match["match_score"],
                    evidence_matches=evidence_assessment,
                    evidence_strength=self._determine_strength(completeness, evidence_assessment),
                    evidence_gaps=gaps,
                    completeness_score=completeness,
                )
            )

        # Sort by match score
        results.sort(key=lambda x: x.match_score, reverse=True)
        return results, extracted_evidence

    async def _llm_match_situation(
        self,
        situation: str,
        claim_types: list[dict],
    ) -> list[dict]:
        """Use LLM to match situation to claim types."""
        types_list = "\n".join(
            [
                f"- {ct.get('canonical_name', 'N/A')}: {ct.get('display_name', ct.get('name', ''))} - {ct.get('description', '')[:150]}"
                for ct in claim_types
            ]
        )

        prompt = f"""You are a legal claim classifier. Analyze the following tenant situation and identify which claim types are relevant.

AVAILABLE CLAIM TYPES:
{types_list}

TENANT SITUATION:
{situation}

Respond with a JSON array of matches, each with:
- claim_type_id: The canonical_name from the list above
- match_score: 0.0-1.0 indicating how well this claim type matches
- reasoning: Brief explanation

Example:
[
  {{"claim_type_id": "RENT_OVERCHARGE", "match_score": 0.85, "reasoning": "Tenant mentions rent amount issues"}},
  {{"claim_type_id": "DEREGULATION_CHALLENGE", "match_score": 0.70, "reasoning": "Landlord claiming deregulation"}}
]

Return ONLY the JSON array, nothing else.
"""

        try:
            response = await self.llm_client.chat_completion(prompt)
            self.logger.debug(f"LLM response: {response[:200]}")

            # Parse JSON from response
            import json

            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                matches = json.loads(response[start:end])
                self.logger.debug(f"Parsed {len(matches)} matches from LLM")

                # Convert canonical_name to claim_type_id
                for match in matches:
                    canonical = match.get("claim_type_id", "").upper()
                    claim_type = next(
                        (
                            ct
                            for ct in claim_types
                            if ct.get("canonical_name", "").upper() == canonical
                        ),
                        None,
                    )
                    if claim_type:
                        match["claim_type_id"] = claim_type["_key"]
                        self.logger.debug(f"Matched {canonical} to {claim_type['_key']}")
                    else:
                        self.logger.warning(f"Could not find claim type for canonical: {canonical}")

                # Filter out matches without valid claim_type_id
                valid_matches = [m for m in matches if m.get("claim_type_id")]
                return valid_matches
        except json.JSONDecodeError as e:
            self.logger.warning(
                f"Failed to parse LLM JSON response: {e}, response: {response[:200]}"
            )
        except Exception as e:
            self.logger.warning(f"LLM matching failed: {e}")

        return []

    def _keyword_match_situation(
        self,
        situation: str,
        claim_types: list[dict],
    ) -> list[dict]:
        """Fallback keyword-based matching."""
        situation_lower = situation.lower()

        # Keyword patterns for each claim type
        keyword_patterns = {
            "DEREGULATION_CHALLENGE": [
                "deregulated",
                "deregulation",
                "decontrol",
                "high rent vacancy",
                "rent stabilized",
            ],
            "RENT_OVERCHARGE": ["overcharge", "illegal rent", "rent too high", "rent stabilized"],
            "HP_ACTION_REPAIRS": [
                "repairs",
                "violations",
                "habitability",
                "hp action",
                "broken",
                "leak",
            ],
            "HARASSMENT": ["harassment", "harass", "intimidate"],
            "SECURITY_DEPOSIT_RETURN": ["security deposit", "deposit return", "deposit"],
        }

        matches = []
        for ct in claim_types:
            canonical = ct.get("canonical_name", "").upper()
            keywords = keyword_patterns.get(canonical, [])

            if keywords:
                # Count keyword matches
                matches_count = sum(1 for kw in keywords if kw in situation_lower)
                if matches_count > 0:
                    # Score based on number of keyword matches
                    score = min(0.9, 0.5 + (matches_count * 0.1))
                    matches.append(
                        {
                            "claim_type_id": ct["_key"],
                            "match_score": score,
                            "reasoning": f"Matched {matches_count} keywords",
                        }
                    )

        return matches

    async def _assess_evidence_strength(
        self,
        user_evidence: list[str],
        required_evidence: list[dict],
        claim_type_name: str,
    ) -> list[EvidenceMatch]:
        """
        Assess which required evidence the user has.

        Returns:
            List of EvidenceMatch objects for each required evidence item
        """
        if not required_evidence:
            return []

        # Use LLM to match user evidence to required evidence
        required_list = "\n".join(
            [
                f"- {ev.get('name', 'Unknown')}: {ev.get('description', '')[:100]} (Critical: {ev.get('is_critical', False)})"
                for ev in required_evidence
            ]
        )

        user_evidence_str = "\n".join([f"- {ev}" for ev in user_evidence])

        prompt = f"""Match the user's evidence to the required evidence for a {claim_type_name} claim.

REQUIRED EVIDENCE:
{required_list}

USER'S EVIDENCE:
{user_evidence_str}

For each required evidence item, determine:
1. Does the user have it? (match_score: 1.0 = yes, 0.5 = partial, 0.0 = no)
2. Which user evidence item matches it? (or null if none)

Respond with JSON array:
[
  {{
    "evidence_name": "IAI Documentation",
    "match_score": 0.0,
    "user_evidence": null,
    "status": "missing"
  }},
  {{
    "evidence_name": "DHCR Registration History",
    "match_score": 1.0,
    "user_evidence": "DHCR registration history showing inconsistent records",
    "status": "matched"
  }}
]

Return ONLY the JSON array.
"""

        try:
            response = await self.llm_client.chat_completion(prompt)
            import json

            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                matches_data = json.loads(response[start:end])

                # Convert to EvidenceMatch objects
                evidence_matches = []
                for match_data in matches_data:
                    # Find the required evidence item
                    req_evid = next(
                        (
                            ev
                            for ev in required_evidence
                            if ev.get("name") == match_data["evidence_name"]
                        ),
                        None,
                    )
                    if req_evid:
                        evidence_matches.append(
                            EvidenceMatch(
                                evidence_id=req_evid.get("_key", ""),
                                evidence_name=match_data["evidence_name"],
                                match_score=match_data.get("match_score", 0.0),
                                user_evidence_description=match_data.get("user_evidence"),
                                is_critical=req_evid.get("is_critical", False),
                                status=match_data.get("status", "missing"),
                            )
                        )

                return evidence_matches
        except Exception as e:
            self.logger.warning(f"Evidence assessment failed: {e}")

        # Fallback: mark all as missing
        return [
            EvidenceMatch(
                evidence_id=ev.get("_key", ""),
                evidence_name=ev.get("name", "Unknown"),
                match_score=0.0,
                is_critical=ev.get("is_critical", False),
                status="missing",
            )
            for ev in required_evidence
        ]

    def _calculate_completeness(self, evidence_matches: list[EvidenceMatch]) -> float:
        """Calculate evidence completeness score (0.0-1.0)."""
        if not evidence_matches:
            return 0.0

        # Weight critical evidence more heavily
        total_weight = 0.0
        matched_weight = 0.0

        for match in evidence_matches:
            weight = 2.0 if match.is_critical else 1.0
            total_weight += weight
            matched_weight += match.match_score * weight

        return matched_weight / total_weight if total_weight > 0 else 0.0

    def _determine_strength(
        self,
        completeness: float,
        evidence_matches: list[EvidenceMatch],
    ) -> str:
        """Determine evidence strength category."""
        if completeness >= 0.8:
            return "strong"
        elif completeness >= 0.5:
            return "moderate"
        else:
            return "weak"

    def _identify_evidence_gaps(self, evidence_matches: list[EvidenceMatch]) -> list[dict]:
        """Identify missing evidence with actionable advice."""
        gaps = []

        for match in evidence_matches:
            if match.match_score < 0.5:  # Missing or partial
                gap = {
                    "evidence_name": match.evidence_name,
                    "is_critical": match.is_critical,
                    "status": match.status,
                    "how_to_get": self._generate_how_to_get_advice(match.evidence_name),
                }
                gaps.append(gap)

        return gaps

    def _generate_how_to_get_advice(self, evidence_name: str) -> str:
        """Generate actionable advice on how to obtain missing evidence."""
        # Simple rule-based advice (can be enhanced with LLM)
        advice_map = {
            "IAI Documentation": "Request from landlord via certified mail. If landlord cannot provide, this strengthens your case.",
            "DHCR Registration History": "Request from DHCR online portal or via FOIL request. Free and available to all tenants.",
            "Rent Stabilization Rider": "Landlord is required to provide this. If missing, file complaint with DHCR.",
            "Photos/Video of Conditions": "Take timestamped photos/videos. Document dates and conditions clearly.",
            "311 Complaint Records": "File complaint at 311.nyc.gov or call 311. Keep complaint numbers.",
            "Violation Records": "Check HPD website for open violations. Request violation history if needed.",
        }

        return advice_map.get(
            evidence_name,
            f"Contact your local tenant advocacy organization for help obtaining {evidence_name}.",
        )

    async def generate_next_steps(
        self,
        claim_matches: list[ClaimTypeMatch],
        situation: str,
    ) -> list[str]:
        """Generate actionable next steps for the user."""
        if not claim_matches:
            return ["Consult with a tenant attorney or legal aid organization."]

        # Get top match
        top_match = claim_matches[0]

        steps = []

        # If strong evidence, suggest filing
        if top_match.evidence_strength == "strong":
            steps.append(
                f"Consider filing a {top_match.claim_type_name} claim. You have strong evidence."
            )
        else:
            steps.append(
                f"Gather missing evidence before filing {top_match.claim_type_name} claim."
            )

        # Add specific gap-filling steps
        critical_gaps = [g for g in top_match.evidence_gaps if g["is_critical"]]
        if critical_gaps:
            steps.append(
                f"Priority: Obtain {critical_gaps[0]['evidence_name']} - {critical_gaps[0]['how_to_get']}"
            )

        # Add general steps
        steps.append("Document everything: dates, communications, photos, receipts.")
        steps.append("Consider consulting with a tenant attorney before filing.")

        return steps
