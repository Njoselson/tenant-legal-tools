# Feature Specification: Entity Relationships Clarification and Strengthening

**Feature Branch**: `007-entity-relationships`  
**Created**: 2025-01-27  
**Status**: Draft  
**Input**: User description: "Clarify and strengthen the relationships between legal entities. Right now I don't see any relationships in kg-view."

## Clarifications

### Session 2025-01-27

- Q: When the same two entities have conflicting relationships across documents (e.g., Document 1: "LAW A ENABLES REMEDY B", Document 2: "REMEDY B ENABLES LAW A"), how should the system handle this? → A: Allow both relationships to exist, storing source/document provenance for each so users can see which document asserted each relationship
- Q: When there are many relationships (hundreds or thousands of edges), how should the graph view handle performance and usability? → A: Display all relationships for all loaded entities at once, relying on graph visualization library performance optimizations
- Q: When entities are consolidated/merged (e.g., two similar entities are identified as duplicates and merged), what should happen to their relationships? → A: Merge relationships by redirecting all relationships from both entities to the canonical entity, preserving all relationship types and metadata

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Relationships Between Entities in Knowledge Graph (Priority: P1)

A user viewing the knowledge graph needs to see how legal entities are connected to each other. When they load the knowledge graph view, relationships between entities should be visible as edges connecting nodes, showing what types of relationships exist and how entities relate to each other.

**Why this priority**: This is the core problem - relationships exist but aren't visible. Without visible relationships, users cannot understand the connections between legal concepts, laws, remedies, evidence, and other entities. This makes the knowledge graph appear as disconnected nodes rather than an interconnected knowledge structure.

**Independent Test**: Can be fully tested by loading the knowledge graph view with entities that have known relationships and verifying that edges appear between related entities, showing relationship types and allowing users to explore connections.

**Acceptance Scenarios**:

1. **Given** entities exist in the knowledge graph with relationships between them, **When** a user loads the knowledge graph view, **Then** edges/connections are visible between related entities
2. **Given** entities with multiple relationship types (e.g., LAW ENABLES REMEDY, EVIDENCE SUPPORTS OUTCOME), **When** a user views the graph, **Then** different relationship types are distinguishable (via labels, colors, or styling)
3. **Given** a user selects an entity in the graph, **When** they view entity details, **Then** they can see all relationships connected to that entity (both incoming and outgoing)

---

### User Story 2 - Ensure Relationships Are Created During Document Ingestion (Priority: P1)

During document ingestion, the system should reliably extract and store relationships between entities. When legal documents are processed, relationships defined in the text (or inferred from entity patterns) must be properly created and persisted to the knowledge graph.

**Why this priority**: Relationships must be created correctly during ingestion for them to be visible later. This addresses the root cause - ensuring relationships are extracted and stored properly from the start.

**Independent Test**: Can be fully tested by ingesting a document with known relationships (e.g., a case document with claims, evidence, outcomes, damages) and verifying that all expected relationships are created and stored in the graph database.

**Acceptance Scenarios**:

1. **Given** a document containing entities with explicit relationship statements, **When** the document is ingested, **Then** all relationships are extracted and stored in the graph
2. **Given** entities that match relationship inference patterns (e.g., LAW and REMEDY entities in same document), **When** the document is ingested, **Then** appropriate inferred relationships are created
3. **Given** relationships extracted from proof chains during case analysis, **When** case documents are processed, **Then** all proof chain relationships (CLAIM REQUIRES EVIDENCE, EVIDENCE SUPPORTS OUTCOME, etc.) are stored

---

### User Story 3 - Strengthen Relationship Extraction Accuracy (Priority: P2)

The system should accurately identify relationships between entities, using improved extraction logic to correctly classify relationship types and validate that relationships make semantic sense (e.g., a LAW should ENABLE a REMEDY, not the reverse).

**Why this priority**: While visibility is critical, ensuring relationships are accurate and meaningful improves the quality of the knowledge graph. This enhances trust and usability once relationships are visible.

**Independent Test**: Can be fully tested by ingesting documents with clear legal relationships and verifying that relationship types are correctly classified and semantically valid.

**Acceptance Scenarios**:

1. **Given** a document describing a legal framework (e.g., "Warranty of Habitability enables rent reduction remedy"), **When** entities are extracted, **Then** relationships are correctly typed (LAW ENABLES REMEDY, not REMEDY ENABLES LAW)
2. **Given** entities extracted from different document types (statutes, cases, guides), **When** relationships are established, **Then** relationship types are appropriate for the entity types involved
3. **Given** a document with ambiguous relationship statements, **When** relationships are extracted, **Then** the system uses context and entity types to disambiguate and choose the most appropriate relationship type

---

### User Story 4 - Clarify Relationship Semantics and Display (Priority: P2)

Users need to understand what each relationship type means. When viewing relationships in the knowledge graph, users should see clear labels and descriptions that explain the semantic meaning of each connection.

**Why this priority**: Visible relationships are only useful if users understand what they mean. Clear labeling and documentation enables users to interpret the knowledge graph correctly.

**Independent Test**: Can be fully tested by viewing relationships in the graph and verifying that labels are clear, meaningful, and help users understand the connection between entities.

**Acceptance Scenarios**:

1. **Given** a relationship edge visible in the graph, **When** a user views it, **Then** they see a clear label indicating the relationship type (e.g., "ENABLES", "REQUIRES", "SUPPORTS")
2. **Given** a user wants to understand what a relationship type means, **When** they view relationship details, **Then** they see a description explaining the semantic meaning
3. **Given** relationship metadata (conditions, weight, attributes), **When** available, **Then** users can access this information to understand relationship nuances

---

### Edge Cases

- What happens when entities exist but no relationships are defined between them in the source document?
- How does the system handle conflicting relationships (e.g., entity A ENABLES entity B in one document, but entity B ENABLES entity A in another)? → **Resolved**: Both relationships are stored with source provenance, allowing users to see which document asserted each relationship
- What happens when relationship extraction fails or produces invalid relationships (e.g., relationship between non-existent entities)?
- How does the system handle relationships between entities that are later merged or consolidated? → **Resolved**: All relationships from both entities are redirected to the canonical entity, preserving relationship types and metadata
- What happens when the graph view loads but relationships fail to retrieve (network errors, database issues)?
- How does the system display relationships when there are hundreds or thousands of edges in the visible graph? → **Resolved**: All relationships for loaded entities are displayed at once, relying on the graph visualization library's performance optimizations to handle rendering
- What happens when relationship type definitions change over time (versioning of relationship semantics)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST display relationships as visible edges/connections in the knowledge graph view between related entities
- **FR-002**: System MUST retrieve and return all relationships between currently loaded entities when graph data is requested (relationships for entities within the current pagination/view)
- **FR-003**: System MUST store relationships in the graph database when entities are created during document ingestion
- **FR-004**: System MUST extract relationships from documents during ingestion, both explicit relationships and inferred relationships based on entity patterns
- **FR-005**: System MUST validate that both source and target entities exist before creating a relationship
- **FR-006**: System MUST handle relationship extraction errors gracefully without blocking document ingestion
- **FR-007**: System MUST label relationship edges clearly in the graph view so users understand the connection type
- **FR-008**: System MUST support displaying relationship metadata (conditions, weight, attributes) when available
- **FR-009**: System MUST distinguish between different relationship types visually (via labels, colors, or styling)
- **FR-010**: System MUST show relationships when viewing individual entity details (both incoming and outgoing relationships)
- **FR-011**: System MUST ensure relationships are preserved when entities are consolidated or merged by redirecting all relationships from both the canonical and merged entities to the canonical entity, preserving all relationship types and metadata
- **FR-012**: System MUST use appropriate relationship types based on entity types involved (e.g., LAW ENABLES REMEDY, not REMEDY ENABLES LAW)
- **FR-013**: System MUST extract proof chain relationships (REQUIRES, SUPPORTS, IMPLY, RESOLVE) from case documents
- **FR-014**: System MUST extract legal framework relationships (APPLIES_TO, ENABLES, VIOLATES, PROHIBITS) from statutory and guidance documents
- **FR-015**: System MUST handle cases where relationships are inferred from entity co-occurrence patterns
- **FR-016**: System MUST prevent duplicate relationships (same source, target, and type) from being created
- **FR-017**: System MUST provide clear error messages when relationship creation fails (e.g., entity not found)
- **FR-018**: System MUST allow conflicting relationships between the same entities to coexist when they originate from different documents, storing source/document provenance for each relationship so users can identify which document asserted each relationship

### Key Entities *(include if feature involves data)*

- **Legal Relationship**: Represents a connection between two legal entities. Key attributes: source entity ID, target entity ID, relationship type (e.g., ENABLES, REQUIRES, SUPPORTS), conditions (optional context), weight (optional strength), attributes (optional metadata), source document provenance (identifies which document asserted this relationship). Relationships are directional (source → target) and typed to indicate semantic meaning. Multiple relationships between the same entities are allowed when they originate from different documents.

- **Relationship Type**: Enumeration of valid relationship types that define how entities can be connected. Examples: ENABLES (law enables remedy), REQUIRES (claim requires evidence), SUPPORTS (evidence supports outcome), VIOLATES (action violates law), APPLIES_TO (law applies to issue). Each type has semantic meaning that should be validated based on entity types involved.

- **Entity**: Legal concepts stored in the knowledge graph (laws, remedies, evidence, claims, outcomes, damages, etc.). Relationships connect entities to form the knowledge structure. When entities are displayed in the graph view, their relationships should be visible as edges.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can see relationship edges in the knowledge graph view for all entities that have relationships defined
- **SC-002**: When a document with known relationships is ingested, at least 80% of expected relationships are successfully created and stored
- **SC-003**: Relationship retrieval completes successfully when loading graph data, with no silent failures
- **SC-004**: Users can distinguish between at least 5 different relationship types visually in the graph view
- **SC-005**: When viewing an entity with relationships, users can see all connected relationships (incoming and outgoing) within 2 seconds
- **SC-006**: Relationship extraction fails gracefully without blocking document ingestion for at least 95% of error cases
- **SC-007**: Relationships displayed in the graph view match relationships stored in the database (no data inconsistency)

## Assumptions

- Relationships are stored in an edges collection in the graph database and can be queried
- The frontend graph visualization library supports displaying edges between nodes
- Existing relationship types (ENABLES, REQUIRES, SUPPORTS, etc.) are semantically appropriate and don't need redefinition
- Relationships should be directional (source → target) rather than bidirectional
- Relationship extraction can leverage both explicit text mentions and entity co-occurrence patterns
- The knowledge graph view should handle displaying relationships even when there are many entities and edges
