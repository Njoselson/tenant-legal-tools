# Feature Specification: Canonical Legal Library

**Feature Branch**: `002-canonical-legal-library`  
**Created**: 2025-01-27  
**Status**: Draft  
**Input**: User description: "Build a canonical library of cases and legal text and legal interpretative text that can underpin an even larger tenant_legal_guidance system. There might be some things implemented with a justia.com scraper, or searcher. We also have some case or legal text saving system already. Make good data hygiene decisions."

**Architectural Context**: This feature provides **manifest curation tools** to make it easier to discover and add legal documents to the canonical library. The existing system already supports manifest-based ingestion with deduplication. This feature adds tools to search Justia.com, export search results to manifest entries, and add entries for documents that may appear on multiple websites (e.g., same case on Justia.com and court website). The system's existing deduplication (content hash check) handles duplicates automatically.

## Clarifications

### Session 2025-01-27

- Q: When the same document is found in multiple sources with conflicting metadata, how should the system resolve these conflicts? → A: Skip duplicate document with "already ingested X" message - no metadata conflict resolution needed
- Q: How should the system handle near-duplicates found via vector similarity search? → A: [DEFERRED] Near-duplicate detection deferred to future enhancement - focus on exact duplicate detection (SHA256) for initial implementation
- Q: When a legal document is updated or corrected, how should the system store and link versions? → A: [DEFERRED] Version linking deferred to future enhancement - corrected documents will be stored as separate documents with different content_hash (no explicit version linking metadata)
- Q: How should the canonical library integrate with the existing knowledge graph and vector store architecture? → A: The canonical library must be inextricably linked to the existing system: graph entities (laws, remedies, cases, evidence) go into ArangoDB, text chunks go into Qdrant, with bidirectional links. The system must maintain coherence as data scales, requiring curation and management to prevent field explosion in the knowledge graph and vector proliferation in Qdrant
- Q: How should deduplication work across the different data levels? → A: Deduplication must occur at three levels: (1) document level using content hash (SHA256) to prevent duplicate documents from multiple sources, (2) entity level using entity resolution (BM25 + LLM) to consolidate duplicate entities in ArangoDB, and (3) chunk level using content hash to prevent duplicate chunks in Qdrant. Since sources are curated via manifest files, curation is part of the ingestion structure

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Search Justia.com and Add Results to Manifest (Priority: P1)

A legal researcher needs to search Justia.com for relevant cases and easily add them to the manifest file for ingestion. The system should provide a search tool that queries Justia.com and exports results as manifest entries.

**Why this priority**: Justia.com is a primary source for case law discovery. Enabling efficient search and export streamlines the curation workflow.

**Independent Test**: Can be fully tested by searching Justia.com for a specific case topic, verifying search results are returned, and confirming exported manifest entries are properly formatted.

**Acceptance Scenarios**:

1. **Given** a user wants to find cases about "rent stabilization" in New York, **When** they use the Justia search tool with query "rent stabilization New York", **Then** the system searches Justia.com and returns a list of case URLs with titles, courts, and decision dates
2. **Given** search results from Justia.com are displayed, **When** a user selects cases to add, **Then** the system exports selected URLs as manifest entries with appropriate metadata (document_type: court_opinion, authority: binding_legal_authority, jurisdiction auto-detected from URL)
3. **Given** a user wants to add a case that appears on both Justia.com and the court website, **When** they add both URLs to the manifest, **Then** during ingestion the system detects they are duplicates (same content hash) and skips the duplicate with "already ingested X" log message

---

### User Story 2 - Add Manifest Entries with URL Validation (Priority: P1)

A legal researcher needs to easily add document URLs to the manifest, with validation that URLs are accessible and preview of what will be ingested. The system should check if URLs already exist in the manifest or database to prevent accidental duplicates.

**Why this priority**: Manual entry of URLs is error-prone. Validation and duplicate checking streamlines curation.

**Independent Test**: Can be fully tested by attempting to add a URL, verifying it's validated, checking for duplicates, and confirming it's added to manifest in correct format.

**Acceptance Scenarios**:

1. **Given** a user wants to add a case URL to the manifest, **When** they provide a URL, **Then** the system validates the URL is accessible, extracts metadata (title, document type), and checks if URL already exists in manifest or database
2. **Given** a URL already exists in the manifest or was previously ingested, **When** the user attempts to add it again, **Then** the system warns them it's a duplicate and optionally adds it anyway (duplicate will be skipped during ingestion)
3. **Given** a user provides a URL that appears on multiple websites (e.g., Justia.com and court website), **When** they add both URLs, **Then** the system allows both entries; during ingestion, the system detects duplicate content and skips the second one

---

### User Story 3 - Maintain Data Hygiene Through Deduplication (Priority: P1)

The system must maintain data quality through deduplication: documents (content hash check - already exists), entities (EntityResolver - already exists), and text chunks (content hash check - enhancement needed). Document and entity deduplication already work; chunk deduplication needs to be added.

**Why this priority**: Data quality is critical for a canonical library - duplicates at any level (documents, entities, or chunks) lead to confusion, waste storage, degrade search results, and fragment the knowledge graph. Multi-level deduplication is essential for maintaining coherence as the library scales.

**Independent Test**: Can be fully tested by ingesting documents from multiple sources that reference the same legal concepts, verifying deduplication occurs at document level (content hash), entity level (entity resolution), and chunk level (chunk content hash).

**Acceptance Scenarios**:

1. **Given** the same legal document is ingested from multiple sources (e.g., Justia.com and court website), **When** the system processes them, **Then** it detects duplicate documents using content hashing (SHA256) and skips the duplicate with "already ingested X" log message
2. **Given** multiple documents reference the same legal entity (e.g., "Warranty of Habitability"), **When** the system processes them, **Then** it uses entity resolution (BM25 search + LLM confirmation) to consolidate duplicate entities into a single entity node in ArangoDB, linking all source documents and chunks
3. **Given** text chunks are created from documents, **When** chunks with identical or near-identical content are generated, **Then** the system detects duplicate chunks using content hashing and consolidates them, preventing unnecessary vector proliferation in Qdrant while maintaining proper entity-chunk linkages

---

### User Story 3 - Archive and Preserve Legal Text (Priority: P2)

A system administrator may optionally maintain canonical text archives (file system storage by SHA256 hash) as a backup or independent reference, separate from the primary storage in ArangoDB and Qdrant. This provides an additional preservation layer but is not required for core library functionality.

**Why this priority**: While archival storage can provide additional preservation guarantees, the primary storage (ArangoDB text_blobs, Qdrant chunks) already provides canonical text storage. Archive functionality is optional and can be enabled when needed for backup or compliance purposes.

**Independent Test**: Can be fully tested by ingesting documents with archive enabled, verifying archived files are created, and checking retrieval by content hash.

**Acceptance Scenarios**:

1. **Given** archive storage is enabled and a legal document is successfully ingested, **When** the system processes it, **Then** it optionally creates a canonical text archive file (by SHA256 hash) in addition to storing in the knowledge graph and vector store
2. **Given** an archived document needs to be retrieved, **When** a user requests it by content hash, **Then** the system can retrieve the archived text file if archive storage is enabled and the file exists

---

### User Story 4 - Chunk Deduplication Enhancement (Priority: P1)

The system must detect and consolidate duplicate text chunks using content hashing to prevent unnecessary vector proliferation in Qdrant. When chunks with identical content are generated, reuse existing chunk IDs instead of creating duplicates, while maintaining proper entity-chunk linkages.

**Why this priority**: Prevents vector store bloat as the library grows. Chunk deduplication is a technical enhancement to complement existing document and entity deduplication.

**Independent Test**: Can be fully tested by ingesting documents with overlapping text content, verifying duplicate chunks are detected by content hash, and confirming chunks are reused rather than duplicated in Qdrant.

**Acceptance Scenarios**:

1. **Given** multiple documents contain identical text passages (e.g., quoted statutes), **When** chunks are created, **Then** the system detects duplicate chunks using content hash and reuses existing chunk IDs instead of creating duplicates
2. **Given** duplicate chunks are consolidated, **When** entities reference these chunks, **Then** entity-chunk bidirectional links are maintained correctly (entities reference chunks, chunks reference entities)

---

### User Story 5 - Search and Discover Legal Cases in Library (Priority: P2)

A legal researcher needs to find relevant cases from the canonical library based on various criteria (case name, court, jurisdiction, date range, legal topics). The system should provide search capabilities that leverage the structured metadata and content indexing.

**Why this priority**: Discovery is useful for library utility, but depends on having a well-populated collection first. This is lower priority than curation tools.

**Independent Test**: Can be fully tested by populating the library with a set of known cases and verifying that searches by various criteria return the expected results.

**Acceptance Scenarios**:

1. **Given** a library containing cases from multiple jurisdictions, **When** a user searches for cases in a specific jurisdiction, **Then** the system returns only cases from that jurisdiction with accurate metadata
2. **Given** a library containing cases from different time periods, **When** a user searches for cases within a date range, **Then** the system returns cases with decision dates within that range
3. **Given** a library with cases covering various legal topics, **When** a user searches by topic or keyword, **Then** the system returns relevant cases ranked by relevance to the search terms

---

### User Story 6 - Maintain Source Provenance and Attribution (Priority: P1)

A legal researcher needs to know where each document in the library originated, when it was ingested, and what the original source URL was. This provenance information is essential for verification, citation, and understanding data lineage.

**Why this priority**: Legal research requires proper attribution and the ability to verify sources - provenance tracking is fundamental to library credibility.

**Independent Test**: Can be fully tested by ingesting a document and verifying that all source information (URL, ingestion date, source type) is correctly recorded and retrievable.

**Acceptance Scenarios**:

1. **Given** a legal document is ingested from a specific URL, **When** the system stores it, **Then** it records the original source URL, ingestion timestamp, and source type in retrievable metadata
2. **Given** the same document exists in multiple sources, **When** the system processes them, **Then** it maintains provenance records for all source URLs that reference the same canonical document
3. **Given** a user needs to verify a document's source, **When** they query the provenance information, **Then** the system returns complete source attribution including original URL, ingestion date, and any updates to the document

---

### Edge Cases

- What happens when a legal document is updated or corrected after initial ingestion (e.g., corrected court opinions)?
- How does the system handle documents that are very similar but not identical (e.g., different pagination or formatting)?
- What happens when a source URL changes but the content remains the same?
- How does the system handle documents that are split across multiple URLs (e.g., multi-part opinions)?
- What happens when ingestion fails partway through processing a large batch of documents?
- How does the system handle documents in different formats (PDF, HTML, plain text)?
- What happens when metadata extraction fails or is incomplete?
- How does the system handle rate limiting or access restrictions from source websites?
- What happens when a document is deleted from the original source after ingestion?
- How does the system handle documents that require authentication or special access to retrieve?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a search tool that queries Justia.com and returns case URLs with metadata (title, court, decision date, jurisdiction) that can be exported to manifest entries
- **FR-002**: System MUST provide tools to add manifest entries with URL validation, metadata extraction, and duplicate checking (check if URL exists in manifest or database)
- **FR-002b**: System MUST detect duplicate documents using content-based hashing (SHA256 of canonicalized text) and skip ingestion if document already exists, logging "already ingested X" message (already implemented)
- **FR-002a**: System MUST detect and consolidate duplicate entities using entity resolution (BM25 search + LLM confirmation) to prevent entity proliferation in ArangoDB (already implemented via EntityResolver)
- **FR-002c**: System MUST detect and consolidate duplicate text chunks using content hashing to prevent unnecessary vector proliferation in Qdrant, ensuring chunks with identical content are stored once while maintaining proper entity-chunk bidirectional links
- **FR-022**: [DEFERRED] Near-duplicate detection using vector similarity search may be added in future enhancement if needed for managing formatting variations (not required for initial implementation)
- **FR-003**: System MUST support optional canonical text archive storage (file system by SHA256 hash) as an additional preservation layer, separate from primary storage in ArangoDB and Qdrant (archive storage is optional and not required for core functionality)
- **FR-004**: System MUST extract and store metadata for each legal document including: case name, court, jurisdiction, decision date, docket number (when available), document type, and source URL
- **FR-005**: System MUST maintain complete provenance information for each document including original source URL(s), ingestion timestamp, source type, and any updates or corrections applied
- **FR-006**: System MUST normalize document content before storage (e.g., whitespace normalization, encoding standardization) to ensure consistent duplicate detection and archival
- **FR-007**: System MUST handle ingestion failures gracefully, logging errors and continuing processing of remaining documents without halting the entire ingestion process
- **FR-008**: System MUST support ingestion from curated manifest files (JSONL format) (already implemented via scripts/ingest.py)
- **FR-009**: System MUST preserve original document formatting and structure in archives while also supporting normalized search and analysis
- **FR-010**: System MUST support idempotent ingestion where processing the same manifest entry (same URL) multiple times recognizes existing documents by content hash and skips processing or updates metadata without creating duplicates (checkpoint system enables skip-existing functionality for resumed ingestion runs)
- **FR-011**: System MUST provide search capabilities across the canonical library by case name, court, jurisdiction, date range, and content keywords
- **FR-012**: [REMOVED] Multiple source references not needed - if same document found, skip ingestion
- **FR-021**: [REMOVED] Metadata conflict resolution not needed - if document already exists (same content hash), skip with "already ingested" message
- **FR-013**: System MUST handle different document formats (PDF, HTML, plain text) by converting to canonical text representation while preserving essential structure
- **FR-014**: System MUST validate ingested documents meet minimum quality thresholds (e.g., minimum length, readable text, valid legal content) before archiving
- **FR-015**: System MUST track ingestion statistics including success/failure rates, duplicate detection counts, and library growth metrics
- **FR-016**: System MUST support incremental ingestion where new documents are added to the library without requiring full re-processing of existing documents
- **FR-017**: System MUST maintain data integrity through checksums and content verification to detect corruption or accidental modification of archived documents
- **FR-018**: System MUST provide export capabilities to generate manifests or catalogs of all documents in the library with their metadata and provenance
- **FR-019**: System MUST handle rate limiting and respect robots.txt or similar access policies when fetching documents from external sources
- **FR-020**: [DEFERRED] Document versioning for corrected/updated documents may be added in future enhancement if needed (not required for initial implementation - corrected documents will be stored as separate documents with different content_hash)
- **FR-023**: System MUST integrate ingested documents with the existing knowledge graph (ArangoDB) and vector store (Qdrant) architecture: extracted graph entities (laws, remedies, cases, evidence, procedures) MUST be stored in ArangoDB, text chunks MUST be stored in Qdrant with embeddings, and bidirectional links MUST be maintained between entities and chunks
- **FR-024**: System MUST maintain coherence of the knowledge graph and vector store as data scales by detecting and consolidating duplicate or near-duplicate entities using entity resolution (semantic matching, LLM confirmation) to prevent field explosion in ArangoDB
- **FR-025**: System MUST manage vector store growth by ensuring chunks are properly linked to entities and deduplicated, preventing unnecessary vector proliferation in Qdrant while maintaining complete text coverage for all ingested documents
- **FR-026**: System MUST provide curation capabilities (entity merging, chunk consolidation, coherence validation) to manage knowledge graph quality and prevent degradation as the library grows, enabling administrators to review and approve consolidation decisions

### Key Entities *(include if feature involves data)*

- **Canonical Document**: Represents a deduplicated legal document in the library. Key attributes: content_hash (SHA256), canonical_text, document_type (court_opinion, statute, guide, etc.), normalized_title, first_ingested_date, last_updated_date. Relationships: HAS_SOURCE source documents, HAS_METADATA document metadata. (Note: Version linking deferred to future enhancement - corrected documents stored as separate documents with different content_hash)

- **Source Document**: Represents an original source reference for a canonical document. Key attributes: source_url, source_type (justia, court_website, legal_database), ingestion_date, fetch_status (success, failed, pending), http_status_code, fetch_error_message. Relationships: REFERENCES canonical document.

- **Document Metadata**: Represents extracted structured information about a legal document. Key attributes: case_name, court, jurisdiction, decision_date, docket_number, parties (plaintiff/defendant), document_type, authority_level, tags, organization, authoritative_source (source that provided the canonical metadata), manual_override_flag. Relationships: DESCRIBES canonical document.

- **Ingestion Record**: Represents a single ingestion attempt or batch operation. Key attributes: ingestion_id, batch_id, start_time, end_time, total_documents, successful_count, failed_count, duplicate_count, status (running, completed, failed). Relationships: CONTAINS source documents.

- **Archive Entry**: Represents a stored canonical text archive. Key attributes: content_hash, archive_path, file_size, creation_date, format (txt, pdf), compression_type, checksum. Relationships: STORES canonical document text.

**Note**: The canonical library does not introduce new storage systems. Documents are ingested into the existing architecture: graph entities (laws, remedies, cases, evidence, procedures) are stored in ArangoDB `entities` collection, text chunks are stored in Qdrant `legal_chunks` collection with embeddings, and bidirectional links are maintained between them. Source metadata is stored in ArangoDB `sources` collection. The "canonical library" is the organized, curated collection of all ingested legal documents within these existing storage systems.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: System successfully ingests at least 95% of valid legal documents from provided source URLs when sources are accessible and documents meet quality thresholds
- **SC-002**: System detects duplicate documents with at least 99% accuracy when the same content is ingested from different sources or at different times
- **SC-003**: All successfully ingested documents are archived and can be retrieved by content hash with 100% reliability (no data loss)
- **SC-004**: System extracts required metadata (case name, court, jurisdiction, date) with at least 90% accuracy for court opinions when metadata is present in the source document
- **SC-005**: System processes batch ingestions of 100 documents in under 30 minutes (excluding network fetch time, assuming average document size of 50KB)
- **SC-006**: Users can search the library by jurisdiction and retrieve only documents from that jurisdiction with 98% precision (no false positives)
- **SC-007**: System maintains complete provenance information (source URL, ingestion date) for 100% of ingested documents
- **SC-008**: System handles ingestion failures gracefully, with fewer than 1% of failures causing the entire batch to halt (99% of individual failures are isolated)
- **SC-009**: Canonical text archives preserve original document content with no loss of meaningful text content (formatting may differ, but all substantive text is retained)
- **SC-010**: System supports incremental ingestion where adding 10 new documents to a library of 1000 existing documents processes only the 10 new documents (no re-processing of existing documents)
- **SC-011**: Library export functionality generates complete manifests listing all documents with core metadata in under 5 seconds for libraries containing up to 10,000 documents
- **SC-012**: System tracks and reports ingestion statistics (success rate, duplicate rate, library size) accurately within 1% of actual values
- **SC-013**: System maintains bidirectional links between ArangoDB entities and Qdrant chunks with 100% accuracy (all entities reference their chunks, all chunks reference their entities)
- **SC-014**: Entity resolution prevents duplicate entity creation with at least 95% accuracy, consolidating semantically similar entities into single graph nodes to maintain knowledge graph coherence
- **SC-015**: System maintains knowledge graph coherence metrics (entity consolidation rate, cross-document entity linking accuracy) that improve or remain stable as library size increases from 100 to 10,000 documents

## Assumptions

- Legal documents are ingested from curated manifest files (JSONL format) that specify source URLs and metadata - curation of sources is part of the library structure and workflow
- Legal documents are publicly accessible via HTTP/HTTPS URLs specified in manifest files
- Source websites (like Justia.com) are accessible and their structure/format is relatively stable
- Documents can be converted to plain text format for canonical storage and analysis
- Content-based hashing (SHA256) provides sufficient uniqueness for duplicate detection across different sources and formats
- Legal documents are relatively static once published (court opinions, statutes) and don't change frequently
- Users have appropriate permissions to access and store legal documents for research purposes
- Network connectivity is available for fetching documents from external sources
- Storage capacity is sufficient for maintaining archives of all ingested documents
- Document metadata extraction may require natural language processing and may not be 100% accurate
- Some source URLs may become unavailable over time, but archived versions remain accessible
- Legal document formats (PDF, HTML) can be reliably converted to text with acceptable quality
- Batch ingestion may be interrupted and should be resumable using checkpoints
- The library will grow incrementally over time, requiring efficient incremental ingestion capabilities
- Different sources may provide the same document in slightly different formats (e.g., different HTML structures, different PDF renderings)
- The canonical library integrates directly with the existing knowledge graph (ArangoDB) and vector store (Qdrant) architecture - there is no separate "canonical library" storage system
- Graph entities and text chunks must remain inextricably linked through bidirectional references (entities → chunks, chunks → entities)
- As the system scales, entity resolution and curation are necessary to maintain coherence and prevent knowledge graph fragmentation
- Entity resolution (semantic matching with LLM confirmation) already exists in the system and must be leveraged for canonical library ingestion

## Dependencies

- Existing document ingestion infrastructure (document processor, knowledge graph storage)
- ArangoDB knowledge graph (for storing graph entities: laws, remedies, cases, evidence, procedures)
- Qdrant vector store (for storing text chunks with embeddings)
- Entity resolution service (for consolidating duplicate entities during incremental ingestion)
- Text extraction and conversion capabilities (PDF parsing, HTML parsing)
- Content hashing and canonicalization utilities
- Storage system for archives (file system or object storage)
- Metadata extraction capabilities (may leverage existing entity extraction services)
- Network access for fetching documents from external sources
- Existing manifest system for batch processing
- Bidirectional linkage between ArangoDB entities and Qdrant chunks (chunks reference entities, entities reference chunks)

## Out of Scope

- Real-time monitoring or alerting for new legal documents published online
- Automatic discovery of new legal documents (only processes provided URLs/manifests)
- Legal analysis or interpretation of document content (only ingestion and storage)
- User interface for browsing or viewing documents (focus on backend library infrastructure)
- Access control or authentication for library access
- Document editing or annotation capabilities
- Integration with commercial legal research databases that require subscription access
- Translation of documents from other languages
- OCR capabilities for scanned documents (assumes text-based sources)
- Quality assessment of legal reasoning or citation accuracy within documents
- Automatic classification or tagging beyond basic metadata extraction
- Version control or diff capabilities for tracking changes in re-ingested documents (beyond basic versioning metadata)

