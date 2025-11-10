"""
Case analysis prompts for the Tenant Legal Guidance System.

This module contains all prompts used specifically for analyzing tenant cases,
including main case analysis, issue identification, evidence extraction, etc.
"""


def get_main_case_analysis_prompt(case_text: str, context: str, json_spec: str) -> str:
    """
    Generate the main comprehensive legal case analysis prompt.
    
    Args:
        case_text: The tenant's case description
        context: Relevant legal context from knowledge graph
        json_spec: JSON specification for citations
        
    Returns:
        Formatted prompt string
    """
    return f"""You are a legal expert specializing in tenant rights and housing law.
Analyze the following tenant case and provide comprehensive legal guidance.

Case Description:
{case_text}

Relevant Legal Context:
{context}

Cite your claims using inline citation markers like [S1], [S2], etc. Each substantive claim should have at least one citation.
{json_spec}

Please provide a structured analysis with the following sections. Use clear markdown formatting:

## CASE SUMMARY
Provide a clear, concise summary of the case and the main legal issues.

## LEGAL ISSUES
List the key legal issues identified in this case. Use bullet points and be specific.
- Issue 1
- Issue 2
- Issue 3

## RELEVANT LAWS
Identify relevant laws, regulations, and legal precedents that apply to this case.
- Law 1
- Law 2
- Law 3

## RECOMMENDED ACTIONS
Provide specific, actionable recommendations for the tenant.
- Action 1
- Action 2
- Action 3

## EVIDENCE NEEDED
Outline what evidence or documentation the tenant should gather.
- Evidence 1
- Evidence 2
- Evidence 3

## RESOURCES
Suggest relevant resources, organizations, or services that can help.
- Resource 1
- Resource 2
- Resource 3

## RISK ASSESSMENT
Assess the risks and potential outcomes for the tenant. Include both positive and negative scenarios.

## NEXT STEPS
Provide a clear action plan with immediate next steps.
- Step 1
- Step 2
- Step 3

Be thorough but accessible. Use specific legal terminology when appropriate."""


def get_evidence_extraction_prompt(case_text: str) -> str:
    """
    Generate prompt for extracting evidence mentioned in a case.
    
    Args:
        case_text: The tenant's case description
        
    Returns:
        Formatted prompt string
    """
    return f"""Extract all evidence mentioned in this tenant case:

{case_text}

Return ONLY valid JSON (no markdown, no explanation):
{{
    "documents": ["lease agreement", "rent receipts"],
    "photos": ["photos of mold in bathroom"],
    "communications": ["text messages from landlord"],
    "witnesses": ["neighbor testimony"],
    "official_records": ["HPD complaint #12345"]
}}

If a category has no items, use an empty array []."""


def get_graph_chain_analysis_prompt(case_text: str, chain_context: list[str]) -> str:
    """
    Generate prompt for analyzing how a legal chain from the KG applies to a case.
    
    Args:
        case_text: The tenant's case description
        chain_context: List of formatted chain steps from knowledge graph
        
    Returns:
        Formatted prompt string
    """
    chain_str = '\n'.join(['• ' + c for c in chain_context])
    
    return f"""You are analyzing how this verified legal chain applies to the tenant's specific case.

TENANT'S CASE: {case_text[:2000]}

VERIFIED LEGAL CHAIN (from knowledge graph):
{chain_str}

Your task: Explain how each step of this chain applies to the tenant's specific case. Reference exact facts from the case (dates, amounts, descriptions).

Return ONLY valid JSON:
{{
    "evidence_present": ["List what tenant mentioned they have"],
    "evidence_needed": ["List what evidence is needed but not mentioned"],
    "reasoning": "Explain how the graph chain applies to THIS specific case, citing tenant's own words"
}}"""


def get_issue_identification_prompt(case_text: str, sources_text: str) -> str:
    """
    Generate prompt for identifying legal issues in a case (Stage 1).
    
    Args:
        case_text: The tenant's case description
        sources_text: Available legal sources
        
    Returns:
        Formatted prompt string
    """
    return f"""Identify all tenant legal issues in this case. Focus on specific, actionable legal issues.

Case: {case_text[:1500]}

Available Sources:
{sources_text[:1000] if sources_text else "No specific sources available"}

CRITICAL: Return ONLY a JSON array of issue names. Be specific and concrete.
Example: ["harassment", "rent_overcharge", "failure_to_repair", "illegal_lockout"]

Return JSON array:"""


def get_issue_analysis_prompt(
    issue: str,
    case_text: str,
    relevant_context: str,
    is_retry: bool = False
) -> str:
    """
    Generate prompt for analyzing a specific issue with applicable laws.
    
    Args:
        issue: The specific issue to analyze
        case_text: The tenant's case description
        relevant_context: Relevant sources with [S#] markers
        is_retry: Whether this is a shorter retry version
        
    Returns:
        Formatted prompt string
    """
    if is_retry:
        # Shorter version for retry
        return f"""Analyze "{issue}" in this case using provided sources.

Case (key facts): {case_text[:2000]}

Sources: {relevant_context[:1500]}

Return JSON:
{{
    "applicable_laws": [{{"name": "...", "citation": "S#", "key_provision": "...", "how_it_applies_to_this_case": "Specific to this case..."}}],
    "evidence_present": ["From case: ..."],
    "evidence_needed": ["Missing: ..."],
    "strength_assessment": "strong|moderate|weak",
    "reasoning": "Brief..."
}}"""
    
    # Full version
    return f"""Analyze the issue of "{issue}" in this tenant case using ONLY the provided sources.

Case: {case_text[:3500]}

Relevant Sources (cite using [S#]):
{relevant_context}

CRITICAL INSTRUCTIONS:
1. GROUND IN CASE FACTS: For each law/remedy, explain HOW it applies to the SPECIFIC facts in the case
   - Reference exact dates, amounts, actions, names, addresses from the case
   - Quote the tenant's own words when explaining how laws apply
   - Connect each legal point to concrete details the tenant mentioned

2. CITE SOURCES: Use [S#] notation for every legal claim
   
3. BE SPECIFIC: Don't say "repairs required" - say "the broken heating for 2 months mentioned by tenant violates NYC Admin Code §27-2029 [S3]"

4. EVIDENCE FROM CASE: List what the tenant actually said they have, not generic evidence types

Return ONLY valid JSON (no markdown):
{{
    "applicable_laws": [
        {{
            "name": "Law name [S#]",
            "citation": "S#",
            "key_provision": "What the law says",
            "how_it_applies_to_this_case": "SPECIFIC application to THIS case with exact facts from tenant's description"
        }}
    ],
    "remedies_available": [
        {{
            "name": "Remedy name [S#]",
            "citation": "S#",
            "description": "What it is",
            "how_to_pursue": "Concrete steps grounded in THIS case"
        }}
    ],
    "elements_required": ["element1", "element2"],
    "evidence_present": ["Tenant mentioned: broken heating for 2 months", "Tenant mentioned: filed DHCR complaint"],
    "evidence_needed": ["Documentation of repair requests", "Photos proving no heat", "Timeline with specific dates"],
    "strength_assessment": "strong|moderate|weak",
    "reasoning": "Tenant's specific facts about [mention exact fact] combined with [law from S#] create [strong/weak] claim because..."
}}"""


def get_case_summary_prompt(
    case_text: str,
    issues_summary: str,
    overall_strength: str,
    sources_text: str
) -> str:
    """
    Generate prompt for creating a final case summary.
    
    Args:
        case_text: The tenant's case description
        issues_summary: Summary of identified issues
        overall_strength: Overall assessment of case strength
        sources_text: Available sources with [S#] markers
        
    Returns:
        Formatted prompt string
    """
    return f"""Provide a concise summary of this tenant case for documentation.

Case: {case_text[:2000]}

Identified Issues: {issues_summary}
Overall Case Strength: {overall_strength}

Sources (cite with [S#]):
{sources_text[:1000] if sources_text else "Limited sources"}

Summary (cite sources):"""


