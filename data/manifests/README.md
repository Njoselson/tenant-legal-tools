# Manifests Directory

This directory contains JSONL manifest files for ingestion.

## Manifest Format

Each line in a manifest file should be a JSON object with the following structure:

```json
{
  "locator": "https://example.com/document.pdf",
  "kind": "URL",
  "title": "Document Title",
  "jurisdiction": "NYC",
  "authority": "PRACTICAL_SELF_HELP",
  "document_type": "SELF_HELP_GUIDE",
  "organization": "Organization Name",
  "tags": ["tag1", "tag2"],
  "notes": "Optional notes"
}
```

## Required Fields

- `locator`: URL or file path to the source document

## Optional Fields

- `kind`: Source type (default: "URL")
- `title`: Document title
- `jurisdiction`: Legal jurisdiction (e.g., "NYC", "NY State", "Federal")
- `authority`: Source authority level
  - `PRIMARY_LAW`: Statutes, regulations
  - `BINDING_PRECEDENT`: Case law
  - `ADMINISTRATIVE_GUIDANCE`: Agency guidance
  - `PRACTICAL_SELF_HELP`: Tenant guides
  - `INFORMATIONAL_ONLY`: General information
- `document_type`: Type of legal document
  - `STATUTE`, `REGULATION`, `CASE_LAW`, `SELF_HELP_GUIDE`, etc.
- `organization`: Publishing organization
- `tags`: Array of categorization tags
- `notes`: Additional context or notes

## Document Type Classification

The `document_type` field determines how the document is processed:

### Court Opinions (Creates CASE_DOCUMENT entity)
- `COURT_OPINION`: Court decisions, opinions (extracts case metadata, parties, holdings)
  - Example: "756 Liberty Realty LLC v Garcia.pdf"
  - Triggers: Case name extraction, holdings, procedural history

### Statutes & Regulations
- `STATUTE`: Laws, codes (e.g., NYC Admin Code)

### Guides & Handbooks  
- `LEGAL_GUIDE`: General legal guides
- `TENANT_HANDBOOK`: Tenant organization materials

### Other Types
- `LEGAL_MEMO`: Legal analysis memos
- `ADVOCACY_DOCUMENT`: Policy papers, reports
- `UNKNOWN`: Auto-detect (default)

## Example: Ingesting Case Law

```json
{
  "locator": "https://example.com/756_liberty_v_garcia.pdf",
  "kind": "URL",
  "title": "756 Liberty Realty LLC v Garcia",
  "document_type": "COURT_OPINION",
  "jurisdiction": "NYC",
  "authority": "BINDING_LEGAL_AUTHORITY",
  "tags": ["housing_court", "habitability", "rent_reduction"]
}
```

## Auto-Detection

The ingestion system can automatically detect metadata based on URL patterns:
- Court websites → case law
- Government agencies → administrative guidance
- Tenant unions → self-help guides

See `tenant_legal_guidance/models/metadata_schemas.py` for more details.

## Creating Manifests

### From Existing Database

```bash
make build-manifest
```

This creates `sources.jsonl` with all unique sources from the current database.

### Manually

Create a JSONL file with one JSON object per line:

```bash
echo '{"locator": "https://example.com/doc.pdf", "title": "My Document"}' > custom_manifest.jsonl
```

### From URL List

You can ingest directly from a text file with URLs (one per line):

```bash
python -m tenant_legal_guidance.scripts.ingest --deepseek-key $KEY --urls urls.txt
```

The system will create a temporary manifest and auto-detect metadata.

