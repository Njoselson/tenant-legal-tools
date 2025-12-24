"""
LLM prompts for the Tenant Legal Guidance System.

This module centralizes all prompts used throughout the system, making them
easier to maintain, version, and experiment with.
"""

from tenant_legal_guidance.models.entities import EntityType
from tenant_legal_guidance.models.relationships import RelationshipType


def get_simple_entity_extraction_prompt(
    text: str,
    context: str = "ingestion",
) -> str:
    """
    Generate a simplified entity extraction prompt for query/case analysis.

    This is used by entity_service.py for extracting entities from user queries
    or case descriptions where we don't have formal source metadata.

    Args:
        text: The text to analyze (will be truncated to 8000 chars)
        context: Either "query" (user case) or "ingestion" (document analysis)

    Returns:
        Formatted prompt string
    """
    types_list = "|".join([e.name for e in EntityType])

    # Adapt intro based on context
    if context == "query":
        intro = """Analyze this tenant's case description and extract the key entities and issues.
Focus on identifying: what problems they're experiencing, what laws might apply, and what remedies they might pursue.

"""
    else:
        intro = """Analyze this legal text and extract structured information about tenants, buildings, issues, and legal concepts.

"""

    return f"""{intro}Text: {text[:8000]}

Extract the following information in JSON format:

1. Entities (must use these exact types):
   # Core legal entities (proof chain focused)
   - LAW: Legal statutes, regulations, or case law
   - REMEDY: Available legal remedies or actions
   - LEGAL_PROCEDURE: Court processes, administrative procedures
   - LEGAL_CLAIM: Assertion of a legal right or cause of action (claims made in cases)
   - EVIDENCE: Proof, documentation, facts supporting claims
   - LEGAL_OUTCOME: Court decisions, settlements, legal victories
   - DAMAGES: Monetary compensation or penalties
   - CASE_DOCUMENT: Court case opinions/decisions as whole documents
   
   # Context entities (for user queries and case analysis)
   - TENANT_ISSUE: Housing problems, violations, tenant situations
   - JURISDICTION: Geographic areas, court systems

2. Relationships (MUST use ONLY these exact types):
   - VIOLATES, ENABLES, AWARDS, APPLIES_TO, PROHIBITS, REQUIRES, AVAILABLE_VIA, FILED_IN, PROVIDED_BY, SUPPORTED_BY, RESULTS_IN
   
   CRITICAL: Use ONLY the relationship types listed above. Do not create new types like PROVIDES, AUTHORIZES, EMPOWERS, BENEFITS, etc.

For each entity, include:
- Type (must be one of: [{types_list}])
- Name (be specific and descriptive)
- Description (brief but informative)
- Jurisdiction (e.g., 'NYC', 'New York State', 'Federal')
- Relevant attributes

For relationships:
- Source entity name
- Target entity name  
- Relationship type (MUST be one of the exact types listed above)

IMPORTANT: Relationship types are strictly validated. Invalid types will be rejected.

Return ONLY valid JSON:
{{
    "entities": [
        {{
            "type": "...",
            "name": "...",
            "description": "...",
            "jurisdiction": "...",
            "attributes": {{}}
        }}
    ],
    "relationships": [
        {{
            "source_id": "...",
            "target_id": "...",
            "type": "..."
        }}
    ]
}}"""


def get_chunk_enrichment_prompt(chunk_texts: list[str], doc_title: str) -> str:
    """
    Generate prompt for enriching chunk metadata with LLM analysis.

    Args:
        chunk_texts: List of chunk text strings
        doc_title: Title of the document

    Returns:
        Formatted prompt string
    """
    chunks_text = ""
    for idx, chunk_text in enumerate(chunk_texts):
        chunks_text += f"\n--- Chunk {idx + 1} ---\n{chunk_text[:600]}...\n"

    return f"""Analyze these legal text chunks from "{doc_title}" and provide metadata for each.

{chunks_text}

For EACH chunk, provide:
1. description: 1-sentence summary of what this chunk covers
2. proves: What legal facts/claims this chunk establishes (or "N/A" if none)
3. references: What laws/cases/entities it cites (or "N/A" if none)

Return ONLY valid JSON array (no markdown):
[
  {{"description": "...", "proves": "...", "references": "..."}},
  {{"description": "...", "proves": "...", "references": "..."}}
]

Ensure array has exactly {len(chunk_texts)} objects."""


# ============================================================================
# LEGAL CLAIM PROVING SYSTEM PROMPTS
# ============================================================================


def get_claim_extraction_prompt(text: str) -> str:
    """
    Generate prompt for extracting legal claims from a document.

    This is step 1 of claim-centric sequential extraction.

    Args:
        text: The full legal document text

    Returns:
        Formatted prompt string
    """
    return f"""Analyze this legal document and extract ALL legal claims made by any party.

Document:
{text[:15000]}

A legal claim is an assertion of a legal right or cause of action. For each claim, identify:
1. The party making the claim (claimant)
2. The party the claim is against (respondent)
3. What the claim asserts
4. What relief/outcome is sought
5. The current status of the claim in the document

Return ONLY valid JSON with this structure:
{{
    "claims": [
        {{
            "name": "Short descriptive name for the claim",
            "description": "Full description of what the claim asserts",
            "claimant": "Party asserting the claim",
            "respondent": "Party the claim is against",
            "relief_sought": ["List of", "relief items", "being sought"],
            "status": "asserted|proven|unproven|dismissed|settled",
            "source_quote": "Direct quote from document that best describes this claim"
        }}
    ]
}}

Important:
- Include ALL claims, including counterclaims
- Be specific about what each claim asserts
- Use exact party names from the document
- Status should reflect the outcome if the document contains a decision"""


def get_evidence_extraction_prompt(text: str, claim_name: str, claim_description: str) -> str:
    """
    Generate prompt for extracting evidence supporting a specific claim.

    This is step 2 of claim-centric sequential extraction.

    Args:
        text: The full legal document text
        claim_name: Name of the claim to find evidence for
        claim_description: Description of the claim

    Returns:
        Formatted prompt string
    """
    return f"""Analyze this legal document and extract ALL evidence relevant to this specific claim.

Document:
{text[:15000]}

CLAIM TO FIND EVIDENCE FOR:
Name: {claim_name}
Description: {claim_description}

Evidence types to look for:
- Documentary: Written documents, records, registrations, leases, receipts
- Testimonial: Witness statements, depositions, testimony
- Factual: Undisputed facts, admissions, stipulations
- Expert opinion: Expert testimony or analysis

For each piece of evidence, determine:
1. What type of evidence it is
2. What it proves or disproves
3. Whether it supports or undermines the claim
4. Any direct quote from the document

Return ONLY valid JSON with this structure:
{{
    "evidence": [
        {{
            "name": "Short descriptive name",
            "type": "documentary|testimonial|factual|expert_opinion",
            "description": "What this evidence shows or proves",
            "supports_claim": true,
            "is_critical": false,
            "source_quote": "Direct quote from document referencing this evidence"
        }}
    ]
}}

Important:
- Include both evidence that supports AND undermines the claim
- Set is_critical=true if this evidence is essential to prove/disprove the claim
- Be specific about what each piece of evidence demonstrates"""


def get_outcome_extraction_prompt(text: str, claim_names: list[str]) -> str:
    """
    Generate prompt for extracting outcomes and linking to claims.

    This is step 3 of claim-centric sequential extraction.

    Args:
        text: The full legal document text
        claim_names: List of claim names to link outcomes to

    Returns:
        Formatted prompt string
    """
    claims_list = "\\n".join([f"- {name}" for name in claim_names])

    return f"""Analyze this legal document and extract ALL legal outcomes/decisions.

Document:
{text[:15000]}

CLAIMS IN THIS CASE:
{claims_list}

An outcome is a decision, ruling, or determination made by the court or decision-maker.
For each outcome, identify:
1. What was decided
2. The disposition (granted, denied, dismissed, etc.)
3. Which claim(s) it resolves
4. Who made the decision

Return ONLY valid JSON with this structure:
{{
    "outcomes": [
        {{
            "name": "Short descriptive name for the outcome",
            "type": "judgment|order|settlement|dismissal|directed_verdict",
            "disposition": "granted|denied|dismissed|dismissed_with_prejudice|settled|partially_granted",
            "description": "Full description of what was decided",
            "decision_maker": "Name of judge or decision-maker",
            "linked_claims": ["List of claim names this outcome addresses"]
        }}
    ]
}}

Important:
- Match linked_claims to the exact claim names provided above
- Include ALL decisions, even interim rulings
- Be specific about the disposition"""


def get_full_proof_chain_prompt(text: str) -> str:
    """
    Generate a single comprehensive prompt for extracting complete proof chains.

    This megaprompt extracts claims, evidence, outcomes, damages, AND relationships
    in a single LLM call, enabling holistic legal reasoning.

    Args:
        text: The full legal document text

    Returns:
        Formatted prompt string
    """
    return f"""Analyze this legal document and extract a complete proof chain showing how legal claims are supported by evidence, leading to outcomes and damages.

DOCUMENT:
{text[:20000]}

TASK: Extract ALL of the following in a single structured response:

1. LEGAL CLAIMS - Every assertion of a legal right or cause of action
   - Include claims by ALL parties (petitioner, respondent, counterclaims)
   - Note who asserts each claim and against whom
   - Identify the status: asserted, proven, unproven, dismissed

2. EVIDENCE - Every piece of proof mentioned
   - Types: documentary (documents, records), testimonial (witness statements), factual (undisputed facts)
   - Note which claims each piece of evidence relates to
   - Mark evidence as "critical" if the case outcome depends on it

3. OUTCOMES - Every decision, ruling, or determination
   - Types: judgment, order, dismissal, directed_verdict, settlement
   - Disposition: granted, denied, dismissed, dismissed_with_prejudice
   - Link to which claims each outcome addresses

4. DAMAGES - Every form of relief or compensation
   - Types: monetary (dollar amounts), injunctive (orders to do/stop something), declaratory (legal status declarations)
   - Status: claimed, awarded, denied, potential
   - Link to which outcome determined each

5. RELATIONSHIPS - How entities connect:
   - HAS_EVIDENCE: claim → evidence (what evidence supports this claim)
   - SUPPORTS: evidence → outcome (what evidence led to this outcome)
   - IMPLY: outcome → damages (what damages result from this outcome)
   - RESOLVE: damages → claim (how damages resolve the claim)

IMPORTANT GUIDELINES:
- Extract evidence ONCE and link to multiple claims if applicable (avoid duplication)
- Follow the legal reasoning: claim assertion → evidence presented → court analysis → outcome → relief
- For each claim, trace the complete chain: what was claimed, what evidence was shown, what the court decided, what relief resulted
- Identify GAPS: required evidence that was missing (especially important for understanding why claims failed)

Return ONLY valid JSON with this structure:
{{
    "claims": [
        {{
            "id": "claim_1",
            "name": "Short descriptive name",
            "description": "Full description of the claim",
            "claimant": "Party asserting",
            "respondent": "Party against",
            "relief_sought": ["list of relief items"],
            "status": "asserted|proven|unproven|dismissed"
        }}
    ],
    "evidence": [
        {{
            "id": "evid_1",
            "name": "Short name",
            "type": "documentary|testimonial|factual",
            "description": "What this evidence shows",
            "is_critical": true/false,
            "source_quote": "Direct quote if available",
            "claim_ids": ["claim_1", "claim_2"]
        }}
    ],
    "outcomes": [
        {{
            "id": "outcome_1",
            "name": "Short name",
            "type": "judgment|order|dismissal|directed_verdict|settlement",
            "disposition": "granted|denied|dismissed|dismissed_with_prejudice",
            "description": "What was decided",
            "decision_maker": "Judge name if mentioned",
            "claim_ids": ["claim_1"]
        }}
    ],
    "damages": [
        {{
            "id": "dmg_1",
            "name": "Short name",
            "type": "monetary|injunctive|declaratory",
            "amount": 45900.00 or null,
            "status": "claimed|awarded|denied|potential",
            "description": "Description of relief",
            "outcome_id": "outcome_1"
        }}
    ],
    "relationships": [
        {{"source": "claim_1", "target": "evid_1", "type": "HAS_EVIDENCE"}},
        {{"source": "evid_1", "target": "outcome_1", "type": "SUPPORTS"}},
        {{"source": "outcome_1", "target": "dmg_1", "type": "IMPLY"}},
        {{"source": "dmg_1", "target": "claim_1", "type": "RESOLVE"}}
    ],
    "proof_gaps": [
        {{
            "claim_id": "claim_1",
            "missing_evidence": "Description of what evidence was needed but not provided",
            "impact": "How this gap affected the outcome"
        }}
    ]
}}

Focus on accuracy and completeness. Trace the full legal reasoning from claims through to final outcomes."""


def get_damages_extraction_prompt(text: str, outcome_names: list[str]) -> str:
    """
    Generate prompt for extracting damages and linking to outcomes.

    This is step 4 of claim-centric sequential extraction.

    Args:
        text: The full legal document text
        outcome_names: List of outcome names to link damages to

    Returns:
        Formatted prompt string
    """
    outcomes_list = "\\n".join([f"- {name}" for name in outcome_names])

    return f"""Analyze this legal document and extract ALL damages, relief, or remedies.

Document:
{text[:15000]}

OUTCOMES IN THIS CASE:
{outcomes_list}

Damages/relief can be:
- Monetary: Dollar amounts awarded or denied
- Injunctive: Orders to do or stop doing something
- Declaratory: Declarations of rights or legal status

For each damages item, identify:
1. What type of damages/relief
2. The amount (if monetary)
3. Whether it was awarded, denied, or is potential
4. Which outcome it relates to

Return ONLY valid JSON with this structure:
{{
    "damages": [
        {{
            "name": "Short descriptive name",
            "type": "monetary|injunctive|declaratory",
            "amount": 45900.00,
            "status": "awarded|denied|potential|claimed",
            "description": "Description of the damages/relief",
            "linked_outcome": "Name of outcome that determined this"
        }}
    ]
}}

Important:
- amount should be null if not monetary or not specified
- Match linked_outcome to exact outcome names provided above
- Include both awarded AND denied damages"""


def get_analyze_my_case_megaprompt(
    situation: str,
    claim_types: list[dict],
    user_evidence: list[str] | None = None,
) -> str:
    """
    Single megaprompt for Analyze My Case that does everything in one call:
    1. Extract evidence from situation
    2. Match situation to claim types
    3. Assess evidence matches
    4. Identify gaps

    This is faster and more coherent than multiple sequential calls.
    """
    # Build claim types list
    types_list = "\n".join(
        [
            f"- {ct.get('canonical_name', 'N/A')}: {ct.get('display_name', ct.get('name', ''))}"
            f"\n  Description: {ct.get('description', '')[:200]}"
            f"\n  Required Evidence: {', '.join([ev.get('name', '') for ev in ct.get('required_evidence', [])[:5]])}"
            for ct in claim_types
        ]
    )

    evidence_context = ""
    if user_evidence:
        evidence_context = "\n\nUSER'S EXPLICIT EVIDENCE LIST:\n" + "\n".join(
            [f"- {ev}" for ev in user_evidence]
        )

    return f"""You are a legal analysis assistant helping a tenant understand their legal situation and what claims they can make.

TENANT SITUATION:
{situation}
{evidence_context}

AVAILABLE CLAIM TYPES:
{types_list}

Analyze this situation and provide a complete analysis in ONE JSON response with:

1. **Extract Evidence**: Identify all evidence items mentioned or implied in the situation
2. **Match Claim Types**: Determine which claim types are relevant (with match scores)
3. **Assess Evidence**: For each matched claim type, assess which required evidence the tenant has
4. **Identify Gaps**: List missing critical evidence with actionable advice

Return a JSON object with this structure:
{{
    "extracted_evidence": [
        "Evidence item 1 from situation",
        "Evidence item 2 from situation"
    ],
    "matched_claim_types": [
        {{
            "claim_type_canonical": "DEREGULATION_CHALLENGE",
            "match_score": 0.95,
            "reasoning": "Tenant mentions deregulation claim by landlord",
            "evidence_assessment": [
                {{
                    "required_evidence_name": "IAI Documentation",
                    "match_score": 0.0,
                    "user_evidence_match": null,
                    "status": "missing",
                    "is_critical": true
                }},
                {{
                    "required_evidence_name": "DHCR Registration History",
                    "match_score": 1.0,
                    "user_evidence_match": "DHCR registration history showing inconsistent records",
                    "status": "matched",
                    "is_critical": true
                }}
            ]
        }}
    ]
}}

Guidelines:
- extracted_evidence: List ALL evidence items mentioned or implied (documents, records, communications, facts)
- match_score: 0.0-1.0, how well the situation matches this claim type
- evidence_assessment: For EACH required evidence item for this claim type, assess if tenant has it
- match_score in evidence_assessment: 1.0 = has it, 0.5 = partial, 0.0 = missing
- user_evidence_match: Which extracted evidence item matches this required evidence (or null)
- status: "matched", "partial", or "missing"
- Only include claim types with match_score >= 0.5

Return ONLY the JSON object, nothing else."""
