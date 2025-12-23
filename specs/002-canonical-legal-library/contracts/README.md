# API Contracts

**Feature**: 002-canonical-legal-library  
**Date**: 2025-01-27

## Status

No new API contracts required for this feature.

The canonical library extends existing ingestion infrastructure:
- **CLI**: `tenant_legal_guidance/scripts/ingest.py` (existing, enhanced)
- **Programmatic**: `DocumentProcessor.ingest_document()` (existing, enhanced)
- **Storage**: ArangoDB and Qdrant interfaces (existing, extended schemas)

## Future Enhancements

Future curation API for reviewing near-duplicates may require new endpoints:
- `GET /api/v1/canonical-library/near-duplicates` - List pending near-duplicates
- `POST /api/v1/canonical-library/near-duplicates/{id}/review` - Approve/reject merge
- `GET /api/v1/canonical-library/versions/{source_id}` - Get version chain

These are out of scope for initial implementation.

