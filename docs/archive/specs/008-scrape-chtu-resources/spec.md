# Feature Specification: Scrape CHTU Resources and Compile Tenant Issues

**Feature Branch**: `008-scrape-chtu-resources`  
**Created**: 2025-01-27  
**Status**: Draft  
**Input**: User description: "Scrape Crown heights tenant union website https://www.crownheightstenantunion.org/resources and compile a list of tenant issues and a summary of them."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Extract Tenant Issues from CHTU Resources (Priority: P1)

As a system analyst, I need the system to scrape the Crown Heights Tenant Union resources page and automatically extract a comprehensive list of tenant issues mentioned across all resource categories, so that I can understand what problems tenants in Crown Heights are facing without manually reviewing hundreds of documents.

**Why this priority**: This is the core functionality - extracting structured data about tenant issues from the resources page. Without this, no analysis or summarization can occur.

**Independent Test**: Can be fully tested by running the scraper against the CHTU resources page and verifying that it produces a structured list of tenant issues organized by category, with each issue clearly identified and linked to its source resource.

**Acceptance Scenarios**:

1. **Given** the CHTU resources page is accessible, **When** the scraper is executed, **Then** the system extracts all resource links and content metadata from all 8 resource categories (Art/Flyers, Heat/Repairs, Organizing, Direct Action, Immigrant Rights, Rent Stabilized Housing, Land Use, Food Resources)
2. **Given** scraped resource content, **When** the system analyzes the content, **Then** it identifies specific tenant issues (e.g., heat problems, repair issues, bedbugs, mold, harassment, rent stabilization concerns, succession rights, MCI disputes, displacement concerns)
3. **Given** extracted tenant issues, **When** issues are categorized, **Then** each issue is associated with one or more resource categories and includes relevant context from the source material

---

### User Story 2 - Generate Structured Summary of Tenant Issues (Priority: P2)

As a user, I need a concise, structured summary of all identified tenant issues with categorization and frequency information, so that I can quickly understand the most common problems tenants face and their relative importance.

**Why this priority**: While extraction is foundational, summarization provides actionable intelligence that makes the data useful for decision-making and further analysis.

**Independent Test**: Can be fully tested by running the summary generation on extracted tenant issues and verifying that it produces a readable summary document that groups issues by category, provides counts, and highlights the most frequently mentioned issues.

**Acceptance Scenarios**:

1. **Given** a list of extracted tenant issues, **When** summary generation is executed, **Then** the system produces a structured summary document that groups issues by category and includes frequency counts
2. **Given** multiple issues within the same category, **When** summary is generated, **Then** issues are ranked by frequency of mention across resources
3. **Given** the summary document, **When** reviewed, **Then** it clearly identifies the most common tenant issues and provides context about where they appear in the CHTU resources

---

### User Story 3 - Export Tenant Issues in Machine-Readable Format (Priority: P3)

As a developer, I need the extracted tenant issues and summary exported in structured formats (JSON/CSV), so that I can integrate this data with other systems or perform additional analysis.

**Why this priority**: Export functionality enables downstream usage and integration, but is not required for initial value delivery.

**Independent Test**: Can be fully tested by running the export functionality and verifying that files are generated in the specified formats with all extracted issue data properly structured and accessible.

**Acceptance Scenarios**:

1. **Given** extracted tenant issues, **When** export to JSON is requested, **Then** the system generates a JSON file containing all issues with their metadata, categories, and source references
2. **Given** extracted tenant issues, **When** export to CSV is requested, **Then** the system generates a CSV file with issues, categories, frequencies, and resource links in tabular format
3. **Given** export files, **When** opened, **Then** they contain valid, well-structured data that can be imported into other tools

---

### Edge Cases

- What happens when the CHTU website is temporarily unavailable or returns an error?
- How does the system handle resources that require authentication or have restricted access?
- What happens when resource links are broken or return 404 errors?
- How does the system handle non-English content or resources in multiple languages?
- What happens when resource content is primarily images or videos that cannot be easily analyzed?
- How does the system handle duplicate issues mentioned across multiple resources?
- What happens when a resource category contains no identifiable tenant issues?
- How does the system handle dynamically loaded content that requires JavaScript execution?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST fetch and parse the CHTU resources page at https://www.crownheightstenantunion.org/resources
- **FR-002**: System MUST extract all resource links and metadata from all 8 resource categories on the page
- **FR-003**: System MUST identify and extract tenant issues from resource content (including linked documents where accessible)
- **FR-004**: System MUST categorize each identified tenant issue by topic (e.g., habitability, harassment, rent regulation, organizing, legal rights)
- **FR-005**: System MUST track the source resource(s) for each identified tenant issue
- **FR-006**: System MUST count the frequency of each issue across all resources
- **FR-007**: System MUST generate a human-readable summary document that groups issues by category with frequency information
- **FR-008**: System MUST handle network errors and retry failed requests with appropriate backoff
- **FR-009**: System MUST gracefully handle missing or inaccessible resources without failing entirely
- **FR-010**: System MUST de-duplicate identical issues mentioned across multiple resources
- **FR-011**: System MUST export extracted issues in structured formats (JSON and optionally CSV)
- **FR-012**: System MUST log scraping activity and extraction results for debugging and audit purposes

### Key Entities *(include if feature involves data)*

- **Tenant Issue**: Represents a specific problem or concern mentioned in CHTU resources. Attributes: issue name, category, description, frequency count, source resources, first identified date
- **Resource**: Represents a document, link, or resource referenced on the CHTU page. Attributes: title, URL, category, document type, accessibility status, extraction date
- **Issue Category**: Represents a classification grouping for tenant issues. Attributes: category name, issue count, most common issues, category description
- **Summary Document**: Represents the compiled analysis of all extracted issues. Attributes: generation date, total issues found, categories covered, top issues by frequency, full issue list

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: System successfully extracts tenant issues from at least 90% of accessible resources on the CHTU resources page within 5 minutes of execution
- **SC-002**: System identifies a minimum of 15 distinct tenant issues across at least 5 different categories
- **SC-003**: Summary document is generated within 1 minute after issue extraction completes
- **SC-004**: Summary document accurately categorizes at least 95% of identified issues (validated against manual review of a sample)
- **SC-005**: System handles network errors and inaccessible resources without failing, completing processing for all accessible resources
- **SC-006**: Export files (JSON/CSV) contain complete issue data and can be successfully imported into standard analysis tools
- **SC-007**: The generated summary clearly identifies the top 5 most frequently mentioned tenant issues

## Assumptions

- The CHTU resources page structure remains relatively stable (Squarespace-based layout)
- Most resources are publicly accessible without authentication
- Resource content is primarily text-based or can be converted to text for analysis
- The existing CHTUScraper service can be extended or used as a foundation for this feature
- Issue identification can be performed through pattern matching, keyword analysis, or content analysis techniques
- Network connectivity is available when the scraper runs
- Rate limiting and respectful scraping practices will be followed to avoid overwhelming the CHTU website