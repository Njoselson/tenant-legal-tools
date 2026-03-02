# Feature Specification: Cloud Database Ingestion with Web Interface and Manifest Management

**Feature Branch**: `006-cloud-ingestion-manifest`  
**Created**: 2025-01-27  
**Status**: Draft  
**Input**: User description: "How to manage a database in the cloud that I need to ingest data into. I want to be able to take any url, pdf etc. and just drop it in the web page on the ingest side, but then I want that data to be saved to a manifest."

## Clarifications

### Session 2025-01-27

- Q: Should all users be able to configure database settings, or should this be restricted to administrators only? → A: Only administrators can view or configure database settings. Database status viewing is not needed on the website.
- Q: Should failed ingestion attempts be recorded in the manifest by default, or should only successful ingestions be recorded? → A: Record failed attempts in manifest with error details.
- Q: Where should the manifest be stored, and should it be a single file or multiple files? → A: Single JSONL file on local filesystem (e.g., `data/manifests/sources.jsonl`) with file locking for concurrent writes.
- Q: Should automatic backup of the manifest file be included in this feature, or is it out of scope? → A: Out of scope - backup handled by external system/infrastructure.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Web-Based Document Ingestion (Priority: P1)

A legal professional or system administrator needs to add legal documents (URLs, PDFs, text files) to the knowledge graph through a simple web interface. They should be able to drag and drop files or paste URLs directly into a web page, and the system should automatically process and ingest the documents into the cloud database.

**Why this priority**: This is the primary user-facing feature - enabling easy document ingestion through a web interface is the core value proposition. Without this, users must use command-line tools or manually edit manifest files.

**Independent Test**: Can be fully tested by accessing the web ingestion interface, dropping a PDF file or pasting a URL, and verifying that the document is successfully processed and stored in the cloud database.

**Acceptance Scenarios**:

1. **Given** a user accesses the web ingestion interface, **When** they drag and drop a PDF file, **Then** the system uploads the file, processes it, extracts entities and proof chains, stores data in the cloud database, and displays a success confirmation
2. **Given** a user accesses the web ingestion interface, **When** they paste a URL into the input field and submits it, **Then** the system fetches the content from the URL, processes it, extracts entities and proof chains, stores data in the cloud database, and displays a success confirmation
3. **Given** a user submits multiple documents (mix of URLs and files), **When** they submit them together, **Then** the system processes each document independently, shows progress for each item, and stores all successfully processed documents in the cloud database
4. **Given** a user submits a document that fails processing (invalid format, network error, etc.), **When** the system encounters the error, **Then** it displays a clear error message indicating what went wrong and allows the user to retry or skip that document

---

### User Story 2 - Automatic Manifest Generation (Priority: P1)

When documents are ingested through the web interface, the system must automatically create or update a manifest file that records all ingestion attempts (both successful and failed). This manifest should contain complete metadata about each source (URL, file path, processing status, timestamps, error details for failures) and can be used for re-ingestion, auditing, or exporting the source list.

**Why this priority**: Manifests are essential for data management, auditing, and re-processing. Automatic manifest generation ensures all ingested data is tracked without requiring manual manifest file management.

**Independent Test**: Can be fully tested by ingesting a document through the web interface and verifying that a manifest entry is automatically created with correct metadata, and that the manifest file can be used to re-ingest or export the source list.

**Acceptance Scenarios**:

1. **Given** a user ingests a document through the web interface, **When** the ingestion completes successfully, **Then** the system automatically adds an entry to the manifest file with complete metadata (locator, kind, title, jurisdiction, authority, document_type, organization, tags, notes, processing timestamp, status)
2. **Given** a user ingests multiple documents, **When** all documents are processed, **Then** the system adds all successful ingestions to the manifest, maintaining a chronological record of all sources
3. **Given** a manifest file already exists, **When** new documents are ingested, **Then** the system appends new entries to the existing manifest without overwriting previous entries
4. **Given** a user views the manifest, **When** they access it, **Then** they can see all ingested sources with their metadata, processing status, and timestamps in a readable format
5. **Given** a document fails ingestion, **When** the failure occurs, **Then** the system records the failed attempt in the manifest with error details, processing status set to "failed", and a timestamp of when the failure occurred

---

### User Story 3 - Cloud Database Management (Priority: P1)

The system must manage data storage in cloud-hosted databases (graph database for structured relationships, vector database for semantic search). Administrators need the ability to manage database connections and configurations through an administrative interface (not exposed to regular users on the website).

**Why this priority**: Cloud database management is foundational - without proper database connectivity and management, ingestion cannot succeed. Administrators need to configure and manage database connections, but this functionality should not be exposed to regular users.

**Independent Test**: Can be fully tested by accessing the administrative database management interface (as an administrator) and verifying that database connection settings can be viewed and updated with appropriate security measures.

**Acceptance Scenarios**:

1. **Given** an administrator accesses the database management interface, **When** they view the configuration page, **Then** they can see and update database connection settings (hosts, credentials, database names) with appropriate security measures
2. **Given** database connection issues occur during ingestion, **When** the system detects connectivity problems, **Then** it displays clear error messages to users indicating that ingestion failed due to database connectivity issues, without exposing database configuration details
3. **Given** a non-administrator user attempts to access database configuration, **When** they try to access the administrative interface, **Then** they are denied access or redirected appropriately

---

### User Story 4 - Manifest Export and Management (Priority: P2)

Users need to export, view, and manage manifest files. They should be able to download manifests, view manifest contents in the web interface, filter and search manifest entries, and use manifests for batch operations like re-ingestion.

**Why this priority**: Manifest management enables data portability, auditing, and batch operations, but is secondary to the core ingestion workflow.

**Independent Test**: Can be fully tested by accessing the manifest management interface, viewing manifest entries, downloading the manifest file, and verifying that the downloaded manifest can be used for re-ingestion operations.

**Acceptance Scenarios**:

1. **Given** a user accesses the manifest management interface, **When** they view the manifest, **Then** they can see all manifest entries in a table or list format with search and filter capabilities (by date, status, document type, jurisdiction)
2. **Given** a user wants to export the manifest, **When** they request a download, **Then** the system provides the manifest file in JSONL format that can be used for re-ingestion or backup purposes
3. **Given** a user wants to re-ingest sources from the manifest, **When** they select manifest entries and request re-ingestion, **Then** the system processes the selected sources again, updating the database with any changes
4. **Given** a user wants to remove entries from the manifest, **When** they delete entries, **Then** the system updates the manifest file and optionally provides options to remove associated data from the databases

---

### User Story 5 - Ingestion UI Cleanup and Simplification (Priority: P2)

Users need a clean, simplified data ingestion interface without deprecated pages or unnecessary UI elements. Old or duplicate ingestion pages should be consolidated or removed, and the current ingestion page should be streamlined to focus on essential functionality, removing clutter and unnecessary elements at the bottom of the page.

**Why this priority**: A clean, focused ingestion interface reduces confusion and makes it easier for users to ingest documents. Removing deprecated pages prevents users from accessing outdated functionality, and simplifying the UI reduces cognitive load and improves task completion.

**Independent Test**: Can be fully tested by accessing the ingestion interface, verifying that only one active ingestion page exists, confirming that unnecessary UI elements have been removed, and ensuring users can successfully ingest documents through the simplified interface.

**Acceptance Scenarios**:

1. **Given** old or deprecated ingestion pages exist in the codebase, **When** the system is deployed, **Then** deprecated ingestion pages are removed or consolidated into a single active ingestion interface, and no deprecated ingestion routes are accessible
2. **Given** a user accesses the data ingestion page, **When** they view the page, **Then** they see only essential UI elements needed for ingestion (file upload, URL input, metadata fields), with unnecessary elements at the bottom removed
3. **Given** multiple ingestion interfaces exist, **When** users access ingestion functionality, **Then** they are directed to a single, unified ingestion page that consolidates all ingestion features
4. **Given** a user wants to ingest a document, **When** they use the simplified ingestion interface, **Then** they can complete the task without being distracted by unnecessary UI elements or confusing deprecated options

---

### Edge Cases

- What happens when a user uploads a file that is too large (exceeds size limits)?
- How does the system handle duplicate URLs or files that have already been ingested?
- What happens when network connectivity is lost during URL fetching?
- How does the system handle corrupted PDF files or unsupported file formats?
- What happens when the manifest file becomes corrupted or unreadable?
- How does the system handle concurrent ingestion requests from multiple users?
- What happens when database storage is full or approaching capacity limits?
- How does the system handle partial ingestion failures (some documents succeed, others fail)?
- What happens when a user tries to ingest the same document multiple times in quick succession?
- How does the system handle very long URLs or file paths that exceed system limits?
- What happens when the cloud database connection is temporarily unavailable during ingestion?
- How does the system handle manifest file write conflicts when multiple users ingest simultaneously?
- What happens when a user uploads a file with special characters or non-ASCII characters in the filename?
- How does the system handle timeouts during document processing (very large files, slow network)?
- What happens when users have bookmarks or links to deprecated ingestion pages?
- How does the system handle redirects from old ingestion routes to the new consolidated interface?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a web interface where users can upload files (PDFs, text files) by dragging and dropping them or using file selection dialogs
- **FR-002**: System MUST provide a web interface where users can paste URLs and submit them for ingestion
- **FR-003**: System MUST support ingestion of multiple documents (files and URLs) in a single submission
- **FR-004**: System MUST process uploaded files and fetched URLs through the existing ingestion pipeline (chunking, entity extraction, proof chain building, database storage)
- **FR-005**: System MUST automatically create or update a manifest file whenever a document is ingested through the web interface (both successful and failed attempts)
- **FR-006**: System MUST record complete metadata in manifest entries, including: locator (URL or file path), kind (URL, FILE, etc.), title, jurisdiction, authority, document_type, organization, tags, notes, processing timestamp, processing status, and source hash (SHA256)
- **FR-007**: System MUST append new manifest entries to existing manifest files without overwriting previous entries
- **FR-008**: System MUST store ingested data in cloud-hosted databases (graph database for structured relationships, vector database for semantic search)
- **FR-009**: System MUST provide database connection management for administrators only, allowing administrators to view and configure database connection settings (hosts, credentials, database names) through an administrative interface
- **FR-010**: System MUST restrict database configuration access to administrators only, preventing regular users from viewing or modifying database settings
- **FR-011**: System MUST handle ingestion errors gracefully, displaying clear error messages to users and recording failed attempts in the manifest with error details
- **FR-012**: System MUST prevent duplicate ingestion by checking source hashes (SHA256) before processing
- **FR-013**: System MUST provide progress indicators during document processing, showing status for each submitted document
- **FR-014**: System MUST validate file types and sizes before processing, rejecting unsupported formats or files exceeding size limits with clear error messages
- **FR-015**: System MUST provide a manifest viewing interface where users can see all manifest entries with search and filter capabilities
- **FR-016**: System MUST allow users to export manifest files in JSONL format for backup, re-ingestion, or external use
- **FR-017**: System MUST support re-ingestion of sources listed in the manifest, allowing users to select entries and reprocess them
- **FR-018**: System MUST maintain manifest file integrity, ensuring that concurrent writes do not corrupt the manifest file by using file locking mechanisms when appending entries to the single JSONL manifest file
- **FR-019**: System MUST handle network timeouts and retries when fetching content from URLs
- **FR-020**: System MUST provide appropriate security measures for database credential management (encryption, access controls)
- **FR-021**: System MUST support both single document ingestion and batch ingestion workflows
- **FR-022**: System MUST preserve existing manifest functionality (command-line ingestion, manual manifest editing) while adding web interface capabilities
- **FR-023**: System MUST consolidate or remove all deprecated data ingestion pages, ensuring only one active ingestion interface exists
- **FR-024**: System MUST remove unnecessary UI elements from the data ingestion page, focusing the interface on essential functionality (file upload, URL input, basic metadata)
- **FR-025**: System MUST remove or hide deprecated ingestion routes and endpoints from user-accessible interfaces
- **FR-026**: System MUST simplify the ingestion page layout, removing clutter and unnecessary elements that appear at the bottom or in secondary sections of the page

### Key Entities *(include if feature involves data)*

- **Ingestion Request**: Represents a user's request to ingest a document through the web interface. Key attributes: request_id, source_type (URL or FILE), source_value (URL string or file reference), metadata (title, jurisdiction, authority, document_type, organization, tags, notes), submission_timestamp, user_id (if authentication is implemented), status (pending, processing, completed, failed). This entity tracks the ingestion workflow from submission to completion.

- **Manifest Entry**: Represents a record in the manifest file for an ingested source. Key attributes: locator (URL or file path), kind (URL, FILE, etc.), title, jurisdiction, authority, document_type, organization, tags, notes, source_hash (SHA256 for deduplication), ingestion_timestamp, processing_status (success, failed, partial), error_details (if failed), entity_count (number of entities extracted), vector_count (number of vectors created). This entity provides a complete audit trail of all ingested sources.

- **Database Connection Configuration**: Represents settings for cloud database connections. Key attributes: database_type (graph_database, vector_database), host, port, database_name, collection_name (for vector databases), credentials (encrypted), connection_status (active, inactive, error), last_verified_timestamp, storage_statistics (entity counts, vector counts, storage_size). This entity enables database management and monitoring.

- **Processing Status**: Represents the state of document processing. Key attributes: document_id, current_stage (uploaded, fetched, chunked, entities_extracted, proof_chains_built, stored_in_graph_db, stored_in_vector_db, completed), progress_percentage, error_messages (if any), timestamps for each stage. This entity enables progress tracking and error diagnosis.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can successfully ingest documents (URLs and PDFs) through the web interface, with at least 95% of valid submissions completing successfully
- **SC-002**: All successfully ingested documents are automatically recorded in the manifest file within 5 seconds of ingestion completion
- **SC-003**: Manifest entries contain complete metadata (all required and optional fields) for at least 90% of ingested documents
- **SC-004**: Administrators can access and update database connection settings through the administrative interface, with configuration changes taking effect within 30 seconds
- **SC-005**: The system processes documents and stores them in cloud databases with at least 95% success rate for valid documents
- **SC-006**: Users can export manifest files in JSONL format, and exported manifests can be used for re-ingestion with 100% compatibility
- **SC-007**: The web interface provides clear error messages for at least 90% of failure scenarios, helping users understand and resolve issues
- **SC-008**: The system prevents duplicate ingestion by detecting existing source hashes, with 100% accuracy in duplicate detection
- **SC-009**: Users can view and search manifest entries through the web interface, with search results returning in under 2 seconds for manifests with up to 10,000 entries
- **SC-010**: The system handles concurrent ingestion requests from multiple users without data corruption or manifest file conflicts
- **SC-011**: The web interface displays progress indicators during document processing, updating at least every 5 seconds to show current processing stage
- **SC-012**: All deprecated data ingestion pages are removed or consolidated, with zero deprecated ingestion routes accessible to users in the production system
- **SC-013**: The data ingestion page contains only essential UI elements, with at least 50% reduction in visible UI elements compared to the previous version (removing unnecessary sections at the bottom)
- **SC-014**: Users can successfully ingest documents through the simplified ingestion interface, with at least 95% of users able to complete ingestion without confusion or errors

## Assumptions

- The system already has existing ingestion pipeline components (chunking, entity extraction, proof chain building, database storage) that can be reused
- Cloud databases (ArangoDB and Qdrant) are already configured and accessible
- The existing manifest file format (JSONL) will be maintained for compatibility
- File upload size limits will be configured based on system resources (assumed reasonable default: 50MB per file)
- The web interface will be accessible to authorized users (authentication/authorization details are out of scope for this feature)
- Network connectivity is generally available, with appropriate timeout and retry handling for transient failures
- The system will support common file formats (PDF, TXT, HTML) with extensibility for additional formats
- Manifest files will be stored as a single JSONL file on the local filesystem (e.g., `data/manifests/sources.jsonl`) accessible to both web interface and command-line tools, with file locking used to handle concurrent writes safely
- Database credentials will be managed securely (encryption at rest, secure transmission)
- Deprecated ingestion pages can be identified and safely removed without breaking existing functionality
- Removing unnecessary UI elements from the ingestion page will not affect core ingestion functionality

## Dependencies

- Existing ingestion pipeline components (chunking, entity extraction, proof chain processing, database storage)
- Cloud database infrastructure (ArangoDB, Qdrant) with network connectivity
- Web application framework (FastAPI) for serving the web interface
- File upload and processing capabilities
- Manifest file management system

## Out of Scope

- User authentication and authorization (assumed to be handled by existing system)
- Advanced document format support beyond PDF, TXT, and HTML
- Real-time collaborative editing of manifest files
- Automatic document classification and metadata extraction (basic metadata entry is in scope)
- Database migration or data transformation tools
- Advanced analytics or reporting on ingested data
- Integration with external document management systems
- Automated document discovery or crawling from URLs
- Automatic backup and recovery of manifest files (handled by external infrastructure/system backups)

