# Feature Specification: Proof Chain Processing Unification

**Feature Branch**: `005-proof-chain-unification`  
**Created**: 2025-01-27  
**Status**: Draft  
**Input**: User description: "Simplify all legal processing to use the proof chain processing for ingestion, claim analysis and retrieval from the tenant legal knowledge graph. Simplify and centralize the structures for doing this in the repo."

## Clarifications

### Session 2025-01-27

- Q: How are entities and vectors linked on ingestion? → A: Entities in ArangoDB store `chunk_ids` list; chunks in Qdrant store `entities` list in payload (bidirectional via ID references). This enables trivial retrieval: entities can reference their chunks via chunk_ids, and chunks can reference their entities via the entities list in payload.
- Q: What chunk size should be used for proof chain processing? → A: 3000 characters (with 200 character overlap), matching current default configuration. This balances context preservation with embedding efficiency and semantic search quality.
- Q: How should text be chunked to avoid splitting concepts? → A: Use recursive character splitting that respects sentence and paragraph boundaries, ensuring concepts are not artificially separated across chunk boundaries. Chunks should target 3000 characters but break at natural boundaries (sentences, paragraphs) rather than fixed positions.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Unified Proof Chain Ingestion (Priority: P1)

A system administrator or legal professional needs to ingest legal documents (statutes, case law, guides) into the knowledge graph using a consistent proof chain structure. When documents are ingested, they should be processed through the same proof chain extraction pipeline that identifies claims, evidence, outcomes, and damages, creating a unified data model across all source types.

**Why this priority**: Ingestion is the foundation - all downstream processing depends on consistent data structures. Unifying ingestion through proof chains ensures all legal information follows the same logical structure.

**Independent Test**: Can be fully tested by ingesting a legal document and verifying that it produces proof chain structures (claims with evidence, outcomes, damages) that match the expected format, regardless of document type.

**Acceptance Scenarios**:

1. **Given** a legal document (statute, case law, or guide), **When** the system ingests it, **Then** it extracts entities using proof chain structure (claims → evidence → outcomes → damages), stores them in the knowledge graph database (ArangoDB), creates vector embeddings and stores them in the vector database (Qdrant), and maintains links between both storage systems
2. **Given** multiple document types (statute, case, guide), **When** the system ingests them, **Then** all documents produce proof chain structures that can be queried and analyzed using the same unified interface
3. **Given** a document with incomplete information (e.g., claims without outcomes), **When** the system ingests it, **Then** it creates partial proof chains that can be completed when additional information becomes available

---

### User Story 2 - Proof Chain-Based Claim Analysis (Priority: P1)

A tenant or legal advocate needs to analyze their legal situation and understand what claims they might have, what evidence is required, and what outcomes are possible. The system should analyze their case using proof chain structures retrieved from the knowledge graph, showing them complete proof chains with required vs. presented evidence, potential outcomes, and associated damages.

**Why this priority**: Claim analysis is the primary user-facing feature. Using proof chain structures ensures users see consistent, complete information about their legal options and requirements.

**Independent Test**: Can be fully tested by providing a tenant situation and verifying that the system retrieves and presents relevant proof chains showing claims, required evidence, potential outcomes, and damages in a unified format.

**Acceptance Scenarios**:

1. **Given** a tenant describes their situation, **When** the system analyzes it, **Then** it retrieves relevant proof chains from the knowledge graph and presents them showing: claims that apply, required evidence (with what's missing highlighted), potential outcomes, and associated damages
2. **Given** a tenant situation matching multiple claim types, **When** the system analyzes it, **Then** it presents multiple proof chains, one for each applicable claim type, with consistent structure and formatting
3. **Given** a tenant situation with partial evidence, **When** the system analyzes it, **Then** it shows proof chains with gaps clearly identified, helping the tenant understand what additional evidence would strengthen their case

---

### User Story 3 - Unified Proof Chain Retrieval (Priority: P1)

A user or system component needs to retrieve legal information from the knowledge graph. All retrieval operations should return data in proof chain format, ensuring consistent structure whether retrieving by claim type, evidence type, outcome, or through search queries.

**Why this priority**: Retrieval is used by multiple components (analysis, visualization, API endpoints). Unifying retrieval through proof chains ensures all consumers get consistent data structures.

**Independent Test**: Can be fully tested by querying the knowledge graph for legal information and verifying that results are returned in proof chain format with claims, evidence, outcomes, and damages properly structured.

**Acceptance Scenarios**:

1. **Given** a query for a specific claim type, **When** the system retrieves information, **Then** it returns proof chains showing all relevant claims, their required evidence, outcomes, and damages in a unified structure
2. **Given** a search query for evidence or outcomes, **When** the system retrieves information, **Then** it returns complete proof chains that include the matching evidence/outcomes along with their associated claims and damages
3. **Given** a request for all information about a legal topic, **When** the system retrieves it, **Then** it returns multiple proof chains organized by claim type, all following the same structure

---

### User Story 4 - Centralized Proof Chain Processing (Priority: P2)

A developer maintaining the system needs to modify or extend proof chain processing logic. All proof chain operations should be centralized in a single location, making it easy to update the processing logic without changing multiple files.

**Why this priority**: Centralization improves maintainability and ensures consistency, but is primarily a developer concern rather than a user-facing feature.

**Independent Test**: Can be fully tested by verifying that all proof chain operations (extraction, building, matching, retrieval) use shared components from a centralized location.

**Acceptance Scenarios**:

1. **Given** a need to modify proof chain extraction logic, **When** a developer updates the code, **Then** they only need to change code in one centralized location, and all ingestion, analysis, and retrieval operations automatically use the updated logic
2. **Given** a need to add new proof chain features (e.g., new relationship types), **When** a developer implements it, **Then** they can add it to the centralized structure and all components automatically support it
3. **Given** multiple components need proof chain data, **When** they request it, **Then** they all use the same centralized service, ensuring consistency across the system

---

### Edge Cases

- What happens when a proof chain is incomplete (missing required evidence, no outcomes)?
- How does the system handle proof chains that span multiple documents or sources?
- What happens when the same claim appears in multiple documents with different evidence?
- How does the system handle conflicting proof chains (same claim type with different required evidence)?
- What happens when retrieval finds partial proof chains (evidence without claims, outcomes without evidence)?
- How does the system handle proof chains for claim types that don't exist in the taxonomy yet?
- What happens when ingestion produces proof chains that don't match existing structures?
- How does the system handle proof chain retrieval when the knowledge graph is empty or sparse?
- What happens when an entity is saved to ArangoDB but fails to be stored in Qdrant (or vice versa)?
- How does the system handle entities that exist in one database but not the other (data inconsistency)?
- What happens when vector embeddings fail to generate for proof chain entities?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST use proof chain structure (claims → evidence → outcomes → damages) for all legal document ingestion, regardless of document type (statutes, case law, guides, recordings)
- **FR-002**: System MUST use proof chain structure for all claim analysis operations, retrieving and presenting information in consistent proof chain format
- **FR-003**: System MUST use proof chain structure for all knowledge graph retrieval operations, returning data in unified proof chain format
- **FR-004**: System MUST centralize proof chain processing logic in a single, shared component that is used by ingestion, analysis, and retrieval operations
- **FR-005**: System MUST ensure that proof chains extracted during ingestion can be directly used by analysis and retrieval operations without transformation
- **FR-006**: System MUST maintain consistent proof chain data structures across all operations, ensuring that claims, evidence, outcomes, and damages have the same attributes and relationships regardless of where they are created or retrieved
- **FR-007**: System MUST support partial proof chains (e.g., claims without outcomes, evidence without claims) and allow them to be completed when additional information becomes available
- **FR-008**: System MUST handle proof chains that reference entities from multiple documents or sources, maintaining proper source attribution
- **FR-009**: System MUST provide a unified interface for proof chain operations (extraction, building, matching, retrieval) that can be used by all system components
- **FR-010**: System MUST ensure that proof chain structures are the single source of truth for legal information in the knowledge graph
- **FR-011**: System MUST support querying proof chains by any component (claim type, evidence type, outcome, damages) and return complete proof chain structures
- **FR-012**: System MUST handle proof chain merging when the same claim or evidence appears in multiple sources, consolidating information while preserving source attribution
- **FR-013**: System MUST validate proof chain completeness and identify gaps (missing required evidence, incomplete relationships) consistently across all operations
- **FR-014**: System MUST support proof chain visualization and presentation in a consistent format regardless of how the proof chain was created (ingestion, analysis, retrieval)
- **FR-015**: System MUST provide clear error handling when proof chain operations fail, with consistent error messages and recovery strategies
- **FR-017**: System MUST support proof chain operations at scale, handling large numbers of documents and complex proof chain structures efficiently
- **FR-018**: System MUST maintain proof chain relationships (REQUIRES, HAS_EVIDENCE, SUPPORTS, IMPLY, RESOLVES) consistently across all operations
- **FR-019**: System MUST support proof chain completeness scoring and gap identification using the same logic across ingestion, analysis, and retrieval
- **FR-020**: System MUST ensure that all proof chain operations use the same entity matching and relationship establishment logic
- **FR-021**: System MUST save all proof chain entities (claims, evidence, outcomes, damages) to the knowledge graph database (ArangoDB) as part of the unified processing pipeline
- **FR-022**: System MUST create vector embeddings for all proof chain entities and store them in the vector database (Qdrant), enabling semantic search and retrieval
- **FR-023**: System MUST maintain bidirectional links between entities in ArangoDB and their corresponding vectors in Qdrant: entities store `chunk_ids` list referencing chunks, and chunks store `entities` list in payload referencing entities, enabling trivial bidirectional retrieval
- **FR-024**: System MUST ensure that when proof chains are ingested, all entities are persisted to both ArangoDB and Qdrant as part of the same atomic operation
- **FR-025**: System MUST ensure that proof chain entities retrieved from ArangoDB can be used to find their corresponding vectors in Qdrant, and vice versa
- **FR-026**: System MUST use consistent chunk size (3000 characters with 200 character overlap) for all proof chain processing, ensuring uniform chunk boundaries and entity-chunk linkage across ingestion, analysis, and retrieval operations
- **FR-027**: System MUST use recursive character splitting that respects sentence and paragraph boundaries when creating chunks, ensuring legal concepts are not artificially separated across chunk boundaries and maintaining semantic coherence within each chunk
- **FR-028**: System MUST support re-ingestion of existing documents to update them with new proof chain structure (no data migration needed - old data can be replaced by re-ingesting sources)

### Key Entities *(include if feature involves data)*

- **Proof Chain**: The unified data structure representing legal claims and their supporting evidence, outcomes, and damages. Contains: claim information, required evidence, presented evidence, missing evidence, outcomes, damages, completeness scores, and relationship mappings. This is the central structure used across all operations. All entities within proof chains are stored in both ArangoDB (structured graph) and Qdrant (vector embeddings) with bidirectional links.

- **Claim**: Represents a legal claim within a proof chain. Key attributes: claim_id, claim_description, claim_type, claimant, status. Storage: Stored in ArangoDB entities collection and as vector embedding in Qdrant. Relationships: REQUIRES evidence, HAS_EVIDENCE (presented), RESULTS_IN outcomes, RESOLVED_BY damages.

- **Evidence**: Represents proof items within a proof chain. Key attributes: evidence_id, evidence_type, description, is_critical, context (required/presented/missing), source_reference. Storage: Stored in ArangoDB entities collection and as vector embedding in Qdrant. Relationships: REQUIRED_BY claims, SATISFIES evidence requirements, SUPPORTS outcomes.

- **Outcome**: Represents legal outcomes within a proof chain. Key attributes: outcome_id, disposition, description, outcome_type. Storage: Stored in ArangoDB entities collection and as vector embedding in Qdrant. Relationships: SUPPORTED_BY evidence, IMPLIES damages.

- **Damages**: Represents compensation or relief within a proof chain. Key attributes: damage_id, damage_type, amount, status, description. Storage: Stored in ArangoDB entities collection and as vector embedding in Qdrant. Relationships: IMPLIED_BY outcomes, RESOLVES claims.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All legal document ingestion operations produce proof chain structures with at least 95% consistency in data format and relationship types
- **SC-002**: All claim analysis operations retrieve and present proof chains in unified format, with users able to understand the structure without training in 90% of cases
- **SC-003**: All knowledge graph retrieval operations return proof chain structures, with at least 90% of queries returning complete or partial proof chains in the expected format
- **SC-004**: Proof chain processing logic is centralized such that 100% of proof chain operations (extraction, building, matching, retrieval) use shared components from a single location
- **SC-005**: Developers can modify proof chain processing logic in one location and have changes apply to all operations (ingestion, analysis, retrieval) without code duplication
- **SC-006**: Proof chains extracted during ingestion can be directly used by analysis and retrieval operations without transformation in 100% of cases
- **SC-007**: System processes proof chains consistently across all operations, with at least 95% of proof chains maintaining the same structure regardless of source or operation type
- **SC-008**: Users can query proof chains by any component (claim, evidence, outcome, damages) and receive complete proof chain structures in under 2 seconds for typical queries
- **SC-009**: System handles partial proof chains gracefully, identifying gaps and allowing completion when additional information becomes available in 95% of cases
- **SC-010**: Proof chain completeness scoring and gap identification use the same logic across all operations, producing consistent results in 100% of cases
- **SC-011**: System maintains proof chain relationships consistently, with at least 95% of relationships correctly established and maintained across ingestion, analysis, and retrieval operations
- **SC-012**: All proof chain operations use unified entity matching logic, reducing duplicate entities and improving relationship accuracy by at least 10% compared to previous implementation
- **SC-013**: All proof chain entities are saved to ArangoDB and have corresponding vectors in Qdrant, with 100% of entities having bidirectional links between both storage systems
- **SC-014**: Proof chain entities can be retrieved via both structured graph queries (ArangoDB) and semantic vector search (Qdrant), with consistent results in 95% of queries
- **SC-015**: When proof chains are ingested, all entities are persisted to both ArangoDB and Qdrant in a single operation, with at least 99% success rate for complete persistence

## Assumptions

- Proof chain structure (claims → evidence → outcomes → damages) is the appropriate unified model for all legal information
- Existing proof chain data structures can be preserved while unifying processing logic
- All document types (statutes, case law, guides, recordings) can be processed into proof chain format
- Centralizing proof chain processing will improve maintainability without significantly impacting performance
- Users and system components can work with unified proof chain structures regardless of how they were created
- Proof chain structures are sufficient for all legal information needs (ingestion, analysis, retrieval)
- Existing data can be re-ingested using new proof chain structure (no migration needed)
- Proof chain processing logic can be shared across ingestion, analysis, and retrieval without creating performance bottlenecks
- The knowledge graph database (ArangoDB) can efficiently store and query proof chain structures at scale
- The vector database (Qdrant) can efficiently store and search entity embeddings at scale
- Bidirectional links between ArangoDB entities and Qdrant vectors can be maintained reliably
- All proof chain entities require both structured storage (ArangoDB) and vector storage (Qdrant) for complete functionality

## Dependencies

- Existing proof chain service and data structures
- Knowledge graph database (ArangoDB) for storing structured entities and relationships
- Vector database (Qdrant) for storing entity embeddings and enabling semantic search
- Bidirectional linking infrastructure between ArangoDB entities and Qdrant vectors
- Entity extraction and relationship modeling capabilities
- Document processing and ingestion infrastructure
- Claim analysis and matching services
- Retrieval and search services (both graph-based and vector-based)

## Out of Scope

- Changing the fundamental proof chain data model (claims → evidence → outcomes → damages structure)
- Modifying the knowledge graph schema or database structure
- Creating new proof chain features beyond unification and centralization
- Performance optimization beyond what's needed for unification
- User interface changes beyond what's needed to display unified proof chains
- Integration with external systems or APIs
- Migration of existing data (assumes data is already in compatible format)

