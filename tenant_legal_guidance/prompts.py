"""
LLM prompts for the Tenant Legal Guidance System.

This module centralizes all prompts used throughout the system, making them
easier to maintain, version, and experiment with.
"""

from tenant_legal_guidance.models.entities import EntityType, SourceMetadata
from tenant_legal_guidance.models.relationships import RelationshipType


def get_entity_extraction_prompt(
    chunk: str,
    metadata: SourceMetadata,
    chunk_num: int,
    total_chunks: int,
    include_quotes: bool = True,
) -> str:
    """
    Generate prompt for extracting entities and relationships from legal text.
    
    This prompt instructs the LLM to extract structured entities with supporting
    quotes directly from the source text.
    
    Args:
        chunk: The text chunk to analyze
        metadata: Source metadata
        chunk_num: Current chunk number
        total_chunks: Total number of chunks
        include_quotes: Whether to request supporting quotes (default: True)
        
    Returns:
        Formatted prompt string
    """
    types_list = "|".join([e.name for e in EntityType])
    rel_types_list = "|".join([r.name for r in RelationshipType])
    
    # Supporting quote fields (optional)
    quote_field = '"supporting_quote": "Direct quote from the text that best describes this entity (1-3 sentences)",' if include_quotes else ""
    quote_instruction = """- Supporting quote: A direct quote from the text (1-3 sentences) that best describes or defines this entity
""" if include_quotes else ""
    quote_guidelines = """
IMPORTANT: For each entity's supporting_quote, extract the most relevant sentence(s) from the actual text that:
- Directly mentions, defines, or explains the entity
- Is a complete, grammatically correct sentence
- Is 1-3 sentences long (prefer shorter)
- Provides clear context about what the entity is or does
""" if include_quotes else ""
    
    return f"""Analyze this legal text and extract structured information about tenants, buildings, issues, and legal concepts.

Text: {chunk}
Source: {metadata.source}
Chunk: {chunk_num} of {total_chunks}

Extract the following information in JSON format:

1. Entities (must use these exact types):
   # Legal entities
   - LAW: Legal statutes, regulations, or case law
   - REMEDY: Available legal remedies or actions
   - COURT_CASE: Specific court cases and decisions
   - LEGAL_PROCEDURE: Court processes, administrative procedures
   - DAMAGES: Monetary compensation or penalties
   - LEGAL_CONCEPT: Legal concepts and principles

   # Organizing entities
   - TENANT_GROUP: Associations, unions, block groups
   - CAMPAIGN: Specific organizing campaigns
   - TACTIC: Rent strikes, protests, lobbying, direct action

   # Parties
   - TENANT: Individual or family tenants
   - LANDLORD: Property owners, management companies
   - LEGAL_SERVICE: Legal aid, attorneys, law firms
   - GOVERNMENT_ENTITY: Housing authorities, courts, agencies

   # Outcomes
   - LEGAL_OUTCOME: Court decisions, settlements, legal victories
   - ORGANIZING_OUTCOME: Policy changes, building wins, power building

   # Issues and events
   - TENANT_ISSUE: Housing problems, violations
   - EVENT: Specific incidents, violations, filings

   # Documentation and evidence
   - DOCUMENT: Legal documents, evidence
   - EVIDENCE: Proof, documentation

   # Geographic and jurisdictional
   - JURISDICTION: Geographic areas, court systems

2. Relationships (must use these exact types):
   - VIOLATES: When an ACTOR violates a LAW
   - ENABLES: When a LAW enables a REMEDY
   - AWARDS: When a REMEDY awards DAMAGES
   - APPLIES_TO: When a LAW applies to a TENANT_ISSUE
   - AVAILABLE_VIA: When a REMEDY is available via a LEGAL_PROCEDURE
   - REQUIRES: When a LAW requires EVIDENCE/DOCUMENT

For each entity, include:
- Type (must be one of: [{types_list}])
- Name
- Description
- Jurisdiction (e.g., 'NYC', 'California', 'Federal', '9th Circuit', 'New York State', 'Los Angeles')
- Relevant attributes (dates, amounts, status, etc.)
{quote_instruction}- Source reference: {metadata.source}

For each relationship, include:
- Source entity name (must match an entity name exactly)
- Target entity name (must match an entity name exactly)
- Type (must be one of: [{rel_types_list}])
- Attributes (conditions, weight, etc.)
{quote_guidelines}
Return a JSON object with this structure:
{{
    "entities": [
        {{
            "type": "LAW|REMEDY|COURT_CASE|LEGAL_PROCEDURE|DAMAGES|LEGAL_CONCEPT|TENANT_GROUP|CAMPAIGN|TACTIC|TENANT|LANDLORD|LEGAL_SERVICE|GOVERNMENT_ENTITY|LEGAL_OUTCOME|ORGANIZING_OUTCOME|TENANT_ISSUE|EVENT|DOCUMENT|EVIDENCE|JURISDICTION",
            "name": "Entity name",
            "description": "Brief description",
            "jurisdiction": "Applicable jurisdiction",
            {quote_field}
            "attributes": {{
                // Type-specific attributes
            }}
        }}
    ],
    "relationships": [
        {{
            "source_id": "source_entity_name",
            "target_id": "target_entity_name",
            "type": "VIOLATES|ENABLES|AWARDS|APPLIES_TO|AVAILABLE_VIA|REQUIRES",
            "attributes": {{
                // Relationship attributes
            }}
        }}
    ]
}}"""


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
   # Legal entities
   - LAW: Legal statutes, regulations, or case law
   - REMEDY: Available legal remedies or actions
   - COURT_CASE: Specific court cases and decisions
   - LEGAL_PROCEDURE: Court processes, administrative procedures
   - DAMAGES: Monetary compensation or penalties
   - LEGAL_CONCEPT: Legal concepts and principles

   # Organizing entities
   - TENANT_GROUP: Associations, unions, block groups
   - CAMPAIGN: Specific organizing campaigns
   - TACTIC: Rent strikes, protests, lobbying, direct action

   # Parties
   - TENANT: Individual or family tenants
   - LANDLORD: Property owners, management companies
   - LEGAL_SERVICE: Legal aid, attorneys, law firms
   - GOVERNMENT_ENTITY: Housing authorities, courts, agencies

   # Outcomes
   - LEGAL_OUTCOME: Court decisions, settlements, legal victories
   - ORGANIZING_OUTCOME: Policy changes, building wins, power building

   # Issues and events
   - TENANT_ISSUE: Housing problems, violations
   - EVENT: Specific incidents, violations, filings

   # Documentation and evidence
   - DOCUMENT: Legal documents, evidence
   - EVIDENCE: Proof, documentation

   # Geographic and jurisdictional
   - JURISDICTION: Geographic areas, court systems

2. Relationships between entities:
   - VIOLATES, ENABLES, AWARDS, APPLIES_TO, AVAILABLE_VIA, REQUIRES, etc.

For each entity, include:
- Type (must be one of: [{types_list}])
- Name (be specific and descriptive)
- Description (brief but informative)
- Jurisdiction (e.g., 'NYC', 'New York State', 'Federal')
- Relevant attributes

For relationships:
- Source entity name
- Target entity name
- Relationship type

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

