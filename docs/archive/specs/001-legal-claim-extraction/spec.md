# Feature Specification: Legal Claim Proving System

**Feature Branch**: `001-legal-claim-extraction`  
**Created**: 2025-01-27  
**Status**: Draft  
**Input**: User description: "Create a legal claim proving system that can extract and describe the legal procedings in the text below... using this format: Extract entities from this text: legal claims, Evidence, Damages, Outcomes. With the following relationships: Legal claims REQUIRE evidence, Evidence SUPPORTS outcomes, Outcomes IMPLY damages, Damages RESOLVE legal claims"

## Clarifications

### Session 2025-01-27

- Q: Should extraction be claim-centric (identify claims first, then extract required evidence for each claim) or entity-centric (extract all entities independently, then establish relationships)? → A: Claim-centric sequential extraction - Extract claims first, then for each claim identify required evidence, then outcomes, then damages. This creates complete proof chains per claim.
- Q: How should the system determine if evidence is sufficient to prove a claim? → A: Match extracted evidence against required elements from multiple sources: (1) statutes/regulations define legal elements that must be proven, (2) self-help guides explicitly list practical evidence requirements (e.g., "bring 311 complaint numbers, photos, heat logs"), (3) case law shows what evidence was sufficient/insufficient in precedent cases.
- Q: How should the system present claim provability to users? → A: Structured proof chain with gaps highlighted - show the complete proof chain (claim → required elements → evidence present/missing → outcome → damages) with explicit highlighting of gaps/missing evidence.
- Q: How should entities be linked across different document types (statutes, guides, cases)? → A: Hybrid claim-type taxonomy - start with core housing court claim types (HP Action, Rent Overcharge, etc.) but allow new claim types to be created when statutes/cases reference new violations. Taxonomy grows organically as new sources are ingested.
- Q: How should the system validate that adding sources improves knowledge coherence? → A: Test case validation - define 5-10 real tenant scenarios (756 Liberty case, HP Action examples, etc.) and measure how well the system can build proof chains for these. Score should improve as sources are added. This validates coherence before scaling ingestion.
- Q: Should "loss" (actual harm suffered) be modeled as a distinct entity separate from "damages" (compensation awarded)? → A: No - loss is implicitly captured in claim descriptions and evidence. The claim description asserts what loss occurred; evidence proves it; damages compensates for it. A separate LOSS entity would add complexity without changing extraction or visualization. The distinction is terminological, not structural.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Extract Legal Claims from Case Documents (Priority: P1)

A legal professional or tenant advocate needs to identify all legal claims asserted in a court case or legal document. They provide a legal text (such as a court opinion, complaint, or case document) and the system extracts structured information about each legal claim, including what the claim is, who asserted it, and what it seeks.

**Why this priority**: This is the foundational capability - without identifying claims, the system cannot establish the proof structure. It delivers immediate value by providing a structured view of legal arguments.

**Independent Test**: Can be fully tested by providing a court case document and verifying that all legal claims are correctly identified and extracted with their key attributes (claimant, claim type, relief sought).

**Acceptance Scenarios**:

1. **Given** a court opinion document, **When** the system processes it, **Then** it extracts all legal claims with their descriptions, parties asserting them, and the relief or remedy sought
2. **Given** a legal document with multiple claims, **When** the system processes it, **Then** it distinguishes between different claims and associates each with the correct party
3. **Given** a document with no explicit claims, **When** the system processes it, **Then** it reports that no claims were found or identifies implicit claims based on context

---

### User Story 2 - Extract Evidence Supporting Claims (Priority: P1)

A user needs to understand what evidence is presented or required to support each legal claim. The system identifies evidence mentioned in the document, categorizes it by type (documents, testimony, facts, etc.), and links it to the specific claims it supports.

**Why this priority**: Evidence extraction is critical for understanding claim strength and is required to establish the REQUIRE relationship between claims and evidence.

**Independent Test**: Can be fully tested by providing a case document and verifying that evidence is extracted, categorized, and correctly linked to the claims it supports.

**Acceptance Scenarios**:

1. **Given** a case document with evidence mentioned, **When** the system processes it, **Then** it extracts all evidence items with their types (documentary, testimonial, factual) and links them to relevant claims
2. **Given** evidence that supports multiple claims, **When** the system processes it, **Then** it correctly associates the evidence with all relevant claims
3. **Given** a document where evidence is implied but not explicitly stated, **When** the system processes it, **Then** it identifies what evidence would be required based on the claim type

---

### User Story 3 - Extract Outcomes and Link to Claims (Priority: P2)

A user needs to understand the outcomes of legal proceedings - what decisions were made, what was ordered, and how claims were resolved. The system extracts outcomes (judgments, orders, settlements) and links them back to the claims they address.

**Why this priority**: Outcomes provide closure to the legal narrative and are necessary for understanding how claims were resolved, but can be derived after claims and evidence are established.

**Independent Test**: Can be fully tested by providing a case document with a decision or outcome and verifying that outcomes are extracted and correctly linked to the claims they resolve.

**Acceptance Scenarios**:

1. **Given** a court opinion with a final decision, **When** the system processes it, **Then** it extracts the outcome (granted, denied, dismissed, etc.) and links it to the relevant claims
2. **Given** multiple outcomes for different claims, **When** the system processes it, **Then** it correctly associates each outcome with its specific claim
3. **Given** a document with partial outcomes or ongoing proceedings, **When** the system processes it, **Then** it identifies what has been decided and what remains pending

---

### User Story 4 - Extract Damages and Link to Outcomes (Priority: P2)

A user needs to understand what damages were awarded, claimed, or implied in the legal proceedings. The system extracts monetary damages, non-monetary relief, and other forms of compensation, linking them to the outcomes that produced them.

**Why this priority**: Damages are a key component of legal outcomes and are necessary for the complete proof chain, but depend on outcomes being identified first.

**Independent Test**: Can be fully tested by providing a case document with damages mentioned and verifying that damages are extracted with amounts/types and correctly linked to outcomes.

**Acceptance Scenarios**:

1. **Given** a case document mentioning damages or relief, **When** the system processes it, **Then** it extracts the type and amount of damages (if specified) and links them to the relevant outcomes
2. **Given** damages that are implied but not explicitly stated, **When** the system processes it, **Then** it identifies what damages would typically result from the outcome
3. **Given** a document with no damages mentioned, **When** the system processes it, **Then** it reports that no damages were identified or extracts non-monetary relief if applicable

---

### User Story 5 - Establish Claim-Evidence-Outcome-Damage Relationships (Priority: P1)

A user needs to understand the logical flow of how claims are proven through evidence, how evidence leads to outcomes, and how outcomes result in damages. The system establishes and presents the relationships: claims REQUIRE evidence, evidence SUPPORTS outcomes, outcomes IMPLY damages, and damages RESOLVE claims.

**Why this priority**: The relationship structure is the core value proposition - it creates a proof chain that shows how legal arguments are constructed and resolved.

**Independent Test**: Can be fully tested by providing a complete case document and verifying that all four relationship types are correctly established between the extracted entities.

**Acceptance Scenarios**:

1. **Given** extracted claims, evidence, outcomes, and damages, **When** the system establishes relationships, **Then** it creates REQUIRE links from claims to their required evidence, SUPPORT links from evidence to outcomes, IMPLY links from outcomes to damages, and RESOLVE links from damages back to claims
2. **Given** a claim with insufficient evidence, **When** the system establishes relationships, **Then** it identifies missing evidence requirements or marks the claim as unproven
3. **Given** multiple claims in a document, **When** the system establishes relationships, **Then** it creates separate relationship chains for each claim and correctly distinguishes between them

---

### Edge Cases

- What happens when a document contains claims but no explicit evidence is mentioned?
- How does the system handle contradictory evidence or conflicting claims?
- What happens when outcomes are partial (some claims granted, others denied)?
- How does the system handle documents where damages are claimed but not awarded?
- What happens when a claim is dismissed without reaching an outcome on the merits?
- How does the system handle implicit claims that are not explicitly stated?
- What happens when evidence supports multiple claims or outcomes?
- How does the system handle documents with ongoing proceedings (no final outcome yet)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST extract legal claims from legal text documents first, identifying the claim description, the party asserting it, and the type of relief sought
- **FR-002**: System MUST extract evidence from legal text for each identified claim sequentially, categorizing it by type (documentary, testimonial, factual, expert opinion) and identifying what it proves for that specific claim
- **FR-003**: System MUST extract outcomes from legal documents for each claim, identifying decisions, orders, judgments, and their disposition (granted, denied, dismissed, settled) as they relate to each claim's evidence
- **FR-004**: System MUST extract damages and relief from legal documents for each outcome, including monetary amounts, non-monetary relief, and other forms of compensation, creating complete proof chains per claim
- **FR-005**: System MUST establish REQUIRE relationships between legal claims and the evidence needed to prove them as part of the claim-centric extraction process
- **FR-006**: System MUST establish SUPPORT relationships between evidence and the outcomes it supports within each claim's proof chain
- **FR-007**: System MUST establish IMPLY relationships between outcomes and the damages they produce for each claim
- **FR-008**: System MUST establish RESOLVE relationships between damages and the claims they resolve, completing the proof chain for each claim
- **FR-009**: System MUST handle documents where not all entity types are present (e.g., claims without outcomes, evidence without explicit damages)
- **FR-010**: System MUST preserve source attribution, linking each extracted entity to the specific text passages from which it was derived
- **FR-011**: System MUST handle multiple claims in a single document and maintain separate relationship chains for each
- **FR-012**: System MUST identify when evidence is required but missing or insufficient to support a claim by matching against required elements extracted from: (1) statutes/regulations (legal elements), (2) self-help guides (practical evidence lists), and (3) case law precedent (sufficiency patterns)
- **FR-013**: System MUST distinguish between claimed damages and awarded damages when both are present
- **FR-014**: System MUST handle implicit relationships (e.g., when evidence supports an outcome that is not explicitly stated but can be inferred)
- **FR-015**: System MUST extract proof requirements from self-help legal guides (e.g., "bring 311 complaint numbers", "photos of conditions", "heat logs") and link them to claim types as required evidence templates
- **FR-016**: System MUST extract legal elements from statutes/regulations that define what must be proven for each claim type (e.g., "owner must provide rent stabilization rider to first tenant after deregulation")
- **FR-017**: System MUST support ingestion of three document types for building proof frameworks: statutes/regulations, self-help guides, and case law
- **FR-018**: System MUST output a structured proof chain for each claim showing: claim → required elements → evidence present/missing → outcome → damages
- **FR-019**: System MUST explicitly highlight gaps in the proof chain (missing evidence, unmet required elements) so users can see what's needed to strengthen a claim
- **FR-020**: System MUST distinguish between "evidence present" and "evidence missing" for each required element in the proof chain visualization
- **FR-021**: System MUST maintain a claim-type taxonomy that starts with core housing court types (HP Action, Rent Overcharge, Harassment, Illegal Eviction, DHCR Complaint) and expands as new sources are ingested
- **FR-022**: System MUST automatically create new claim types when statutes or cases reference violations not in the existing taxonomy, linking them to the source that defined them
- **FR-023**: System MUST link entities across document types (statutes, guides, cases) through the shared claim-type taxonomy, enabling cross-referencing of legal requirements, evidence needs, and precedent for each claim type
- **FR-024**: System MUST maintain a validation test suite of 5-10 real tenant scenarios (including 756 Liberty case) to measure proof chain completeness
- **FR-025**: System MUST track coherence metrics (proof chain completeness per scenario) as sources are added, enabling validation that new sources improve the knowledge graph before scaling ingestion
- **FR-026**: System MUST support diverse source types including: statutes/regulations, case law, self-help guides, legal clinic recordings, tenant organizing recordings, checklists, DHCR fact sheets, court forms, and practitioner training materials

### Key Entities *(include if feature involves data)*

- **Claim Type**: Represents a canonical category of legal claim (e.g., HP_ACTION_REPAIRS, RENT_OVERCHARGE, DEREGULATION_CHALLENGE). Key attributes: name, description, jurisdiction, source document that defined it. Starts with core housing court types, expands as new sources are ingested. Acts as the linking key across statutes, guides, and cases.

- **Legal Claim**: Represents a specific assertion of a legal right or cause of action in a document. Key attributes: claim description, claimant (party asserting), claim_type (links to Claim Type taxonomy), relief sought, status (asserted, proven, dismissed). Relationships: REQUIRES evidence (required), HAS_EVIDENCE (presented), RESOLVED_BY damages, IS_TYPE_OF claim_type.

- **Evidence** (extended): Represents proof, documentation, or facts - both what's required (from statutes/guides) and what's presented (from cases). Key attributes: evidence type (documentary, testimonial, factual), description, **context (required/presented/missing)**, source_type (statute/guide/case), is_critical flag. Relationships: REQUIRED_BY claims (if required), SUPPORTS outcomes (if presented), SATISFIES evidence (when presented matches required).

- **Outcome**: Represents the result or decision in a legal proceeding. Key attributes: outcome type (judgment, order, settlement), disposition (granted, denied, dismissed), decision maker, date. Relationships: SUPPORTED_BY evidence, IMPLIES damages.

- **Damages**: Represents monetary compensation, relief, or other forms of remedy awarded or claimed. Key attributes: damage type (monetary, injunctive, declaratory), amount (if monetary), description, status (claimed, awarded). Relationships: IMPLIED_BY outcomes, RESOLVES claims.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: System extracts at least 90% of explicitly stated legal claims from court opinions and legal documents when evaluated against human-annotated ground truth
- **SC-002**: System correctly establishes REQUIRE relationships between claims and evidence with at least 85% accuracy when evidence is explicitly linked to claims in the source text
- **SC-003**: System extracts evidence items with sufficient detail (type, description, source) such that users can identify the evidence in 95% of cases without referring back to the source document
- **SC-004**: System correctly links outcomes to their supporting evidence (SUPPORT relationship) with at least 80% accuracy when the relationship is inferable from the document
- **SC-005**: System extracts damages information (amount, type, status) with at least 90% accuracy when damages are explicitly mentioned in the document
- **SC-006**: System establishes complete relationship chains (claim → evidence → outcome → damages → claim) for at least 70% of claims in documents where all components are present
- **SC-007**: Users can understand the proof structure of a legal case (which evidence supports which claims leading to which outcomes) without reading the full source document in 90% of test cases
- **SC-008**: System processes a standard-length court opinion (10-20 pages) and extracts all entities and relationships in under 60 seconds
- **SC-009**: System handles documents with missing entity types gracefully, reporting what was found and what relationships could be established, without errors in 95% of cases
- **SC-010**: For each claim, users can see a complete proof chain visualization showing required elements and which have evidence vs. which are missing, with 95% of gaps correctly identified
- **SC-011**: Users can identify what additional evidence would strengthen a claim based on the gaps highlighted in the proof chain in 90% of test cases
- **SC-012**: System maintains a validation test suite of 5-10 real tenant scenarios; proof chain completeness score for these scenarios improves measurably as new sources are ingested
- **SC-013**: Before scaling to bulk ingestion, the system demonstrates at least 70% proof chain completeness on validation scenarios using only core sources (key statutes + 2-3 self-help guides + 2-3 case law examples)

## Assumptions

- Legal documents are provided in text format or can be converted to text (PDFs, Word documents, plain text)
- The system focuses on civil legal proceedings, particularly housing/tenant law cases, but should be extensible to other legal domains
- Users have basic familiarity with legal terminology and concepts
- Source documents contain sufficient detail to identify claims, evidence, outcomes, and damages (may not always be explicit)
- The system operates on complete documents or substantial excerpts, not isolated sentences
- Relationship extraction may require inference when relationships are not explicitly stated in the text
- The system may identify implicit claims, evidence requirements, or damages based on legal context and patterns
- Extraction follows a claim-centric sequential approach: claims are identified first, then for each claim the system extracts required evidence, then outcomes, then damages, creating complete proof chains per claim
- Multiple source types contribute to proof frameworks: statutes/regulations (legal elements), self-help guides (practical evidence requirements), case law (precedent), legal clinic recordings, tenant organizing recordings, checklists, DHCR fact sheets, court forms, and practitioner training materials
- Self-help legal guides (e.g., JustFix HP Action guide) explicitly list evidence requirements and can be ingested as "proof requirement templates"
- Recordings (audio/video) require transcription before extraction; transcripts are treated as text sources
- Coherence validation using real tenant scenarios must show improvement before scaling to bulk ingestion
- "Loss" (actual harm suffered) is implicitly modeled within claim descriptions and evidence, not as a separate entity; "damages" represents compensation for that loss

## Dependencies

- Access to legal document processing capabilities (text extraction, parsing)
- Entity extraction and relationship modeling infrastructure (existing knowledge graph system)
- Natural language processing capabilities for understanding legal text
- Legal domain knowledge for identifying implicit relationships and claims

## Out of Scope

- Real-time processing of live court proceedings or streaming legal data
- Automatic generation of legal briefs or arguments based on extracted entities
- Validation of legal claims against actual law (only extraction, not legal analysis)
- Multi-document claim tracking across case files or dockets
- Integration with court filing systems or legal databases
- Translation of legal documents from other languages
- Extraction of entities from non-legal documents or general text
