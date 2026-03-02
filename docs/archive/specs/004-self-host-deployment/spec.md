# Feature Specification: Independent Hosting Deployment

**Feature Branch**: `004-self-host-deployment`  
**Created**: 2025-01-27  
**Updated**: 2025-01-27  
**Status**: Draft  
**Input**: User description: "How do we host this app online in as local and free of big tech way as possible."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deploy Application on Independent Infrastructure (Priority: P1)

A system administrator needs to deploy the tenant legal guidance application on infrastructure that avoids major cloud providers (AWS, Google Cloud, Azure, Microsoft). The system should support multiple deployment options including: independent VPS providers (DigitalOcean, Linode, Hetzner, Vultr, OVH), self-hosted servers, community cloud services, cooperative hosting providers, or personal hardware. This enables full control over data and avoids dependency on big tech platforms while potentially offering managed services that reduce operational overhead.

**Why this priority**: This is the core requirement - the application must be deployable without relying on big tech cloud services, giving users flexibility to choose from various independent hosting options that balance control, convenience, and cost.

**Independent Test**: Can be fully tested by successfully deploying the application on at least two different independent hosting scenarios (e.g., independent VPS provider and self-hosted server) and verifying all services (application, database, vector store) are accessible and functioning correctly.

**Acceptance Scenarios**:

1. **Given** infrastructure from an independent provider (VPS, managed hosting, or self-hosted, not AWS/GCP/Azure), **When** following deployment instructions, **Then** the application and all required services (ArangoDB, Qdrant, application server) can be installed and configured to run successfully
2. **Given** a deployment on independent infrastructure, **When** the application starts, **Then** all components communicate correctly and users can access the application via web browser
3. **Given** a deployment on independent infrastructure, **When** data is stored, **Then** all data remains on the independent infrastructure without being transmitted to big tech services
4. **Given** deployment documentation, **When** reviewed, **Then** it identifies both fully self-hosted options (requiring server management) and managed options (VPS providers with managed services) that avoid big tech

---

### User Story 2 - Provide Deployment Documentation and Automation (Priority: P1)

A system administrator needs clear, step-by-step documentation and automated deployment scripts to set up the application on independent infrastructure (self-hosted or managed VPS) without requiring deep technical expertise or big tech cloud services. The deployment process should be straightforward, support both fully-managed and self-managed options, and avoid proprietary deployment tools from major cloud providers.

**Why this priority**: Without clear documentation and automation, self-hosting becomes prohibitively difficult, potentially forcing users toward big tech solutions for convenience.

**Independent Test**: Can be fully tested by following the deployment documentation on a fresh server and successfully completing the deployment without consulting external big tech cloud documentation or using proprietary deployment tools.

**Acceptance Scenarios**:

1. **Given** deployment documentation and scripts, **When** a system administrator follows them on a fresh Linux server, **Then** they can complete the deployment successfully without requiring AWS/GCP/Azure accounts or services
2. **Given** deployment automation scripts, **When** executed on a compatible system, **Then** they install and configure all required services (Docker, databases, application) without manual intervention
3. **Given** deployment documentation, **When** reviewed by someone with basic server administration knowledge, **Then** they can understand what infrastructure requirements are needed (hardware, OS, network)

---

### User Story 3 - Ensure Data Sovereignty and Privacy (Priority: P1)

A user deploying the application needs assurance that legal case data, user queries, and all sensitive information remains under their control and is not transmitted to or stored by big tech services. The system should operate entirely within the self-hosted infrastructure for data storage and processing, with external API calls (like LLM services) being optional and clearly documented.

**Why this priority**: Legal data requires privacy and control - users must trust that their sensitive information is not being shared with big tech companies through the hosting infrastructure.

**Independent Test**: Can be fully tested by monitoring network traffic and data storage during normal operation and verifying that no data is transmitted to big tech cloud services beyond optional, explicitly configured external APIs.

**Acceptance Scenarios**:

1. **Given** a self-hosted deployment, **When** users submit legal case data, **Then** all data is stored locally on the self-hosted infrastructure and not transmitted to big tech cloud storage or analytics services
2. **Given** network monitoring capabilities, **When** the application processes requests, **Then** no connections are made to AWS/GCP/Azure infrastructure unless explicitly configured by the user for optional services
3. **Given** a deployment without external API keys configured, **When** users attempt to use features requiring external APIs, **Then** the system clearly indicates which features are unavailable and does not silently fail or send data elsewhere

---

### User Story 4 - Support Multiple Independent Hosting Options (Priority: P2)

A system administrator needs flexibility in choosing hosting infrastructure that avoids big tech, including options like: independent VPS providers with managed services (DigitalOcean, Linode, Hetzner, Vultr, OVH), fully self-hosted personal hardware, community cloud services, cooperative hosting providers, or open-source platform-as-a-service tools (Coolify, CapRover, Dokku). The deployment process should support various common hosting scenarios without being tied to specific infrastructure providers, allowing users to choose based on their technical expertise, budget, and desired level of management.

**Why this priority**: Users have different resources, technical skills, and preferences - supporting multiple hosting paths (from fully managed VPS to self-hosted) ensures the application is accessible to a wider range of users while maintaining independence from big tech.

**Independent Test**: Can be fully tested by successfully deploying the application on at least three different hosting scenarios (e.g., independent managed VPS, self-hosted server, and community cloud) and verifying functionality is equivalent.

**Acceptance Scenarios**:

1. **Given** a personal server or home lab setup, **When** following deployment instructions, **Then** the application can be deployed successfully with appropriate networking configuration
2. **Given** an independent VPS provider with managed services, **When** following deployment instructions, **Then** the application deploys successfully without requiring additional big tech services and leverages provider-managed features where available
3. **Given** deployment documentation, **When** reviewed, **Then** it describes multiple hosting options (independent managed VPS, self-hosted hardware, community cloud, platform-as-a-service) with appropriate guidance for each, including trade-offs between control and convenience
4. **Given** a user with minimal server administration experience, **When** they review deployment documentation, **Then** they can identify which hosting options require less technical expertise (managed VPS) versus more (self-hosted)

---

### User Story 5 - Minimize Ongoing Operational Costs (Priority: P2)

A user deploying the application wants to minimize ongoing hosting costs while avoiding big tech services. The deployment should provide guidance on cost-effective independent hosting options, comparing managed VPS providers, self-hosted solutions, and community cloud services, including free or low-cost alternatives where possible, and avoid requirements for paid big tech services.

**Why this priority**: Cost is a barrier to self-hosting - providing affordable options makes self-hosting accessible while maintaining independence from big tech.

**Independent Test**: Can be fully tested by identifying the total monthly cost of running the application on recommended self-hosting infrastructure and verifying it does not require paid big tech services.

**Acceptance Scenarios**:

1. **Given** deployment documentation, **When** reviewed, **Then** it identifies free or low-cost self-hosting options and estimated monthly costs
2. **Given** a deployment on low-cost infrastructure, **When** the application runs normally, **Then** it functions correctly without requiring paid services from big tech providers
3. **Given** cost comparison documentation, **When** reviewed, **Then** users can understand the cost difference between self-hosting options and big tech cloud alternatives

---

### Edge Cases

- What happens when the hosting infrastructure has limited resources (low RAM, CPU, storage) - how do managed VPS providers handle scaling versus self-hosted?
- How does the system handle network connectivity issues or intermittent internet access?
- What happens if an independent VPS provider goes out of business or discontinues service - how does migration differ from self-hosted?
- How does the system handle security updates and maintenance on different hosting options (managed VPS provider tools versus self-hosted manual updates)?
- What happens when users need to scale the application beyond a single server - what options exist for managed VPS versus self-hosted?
- How does the system handle backup and disaster recovery on different hosting options (provider-managed backups versus self-hosted)?
- What happens when external API services (like LLM APIs) are unavailable or rate-limited?
- How does the system handle domain name registration and SSL certificate management across different hosting providers (some offer managed services, others require manual setup)?
- What happens when a user wants to migrate from a managed VPS to self-hosted (or vice versa)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST be deployable on independent infrastructure (personal servers, independent VPS providers like DigitalOcean/Linode/Hetzner/Vultr/OVH, community cloud services, cooperative hosting) without requiring AWS, Google Cloud, Azure, or Microsoft services
- **FR-002**: System MUST provide deployment documentation that enables users to set up the application on Linux-based infrastructure using open-source tools, with separate guidance for fully managed VPS providers versus self-hosted options
- **FR-003**: System MUST support deployment using Docker and Docker Compose without requiring proprietary container orchestration services from big tech providers, while also supporting platform-as-a-service options like Coolify, CapRover, or Dokku where applicable
- **FR-004**: System MUST store all application data (legal documents, knowledge graph, vector embeddings) on independent infrastructure without transmitting to big tech services
- **FR-005**: System MUST NOT transmit user data, queries, or case information to big tech cloud services (AWS, GCP, Azure) for storage or analytics
- **FR-006**: System MUST clearly document any external API dependencies (like LLM services) and make them optional or easily replaceable
- **FR-007**: System MUST provide deployment scripts or automation that can run on standard Linux distributions without requiring big tech cloud CLI tools or SDKs
- **FR-008**: System MUST document minimum hardware requirements (CPU, RAM, storage) for independent hosting deployment, with separate recommendations for managed VPS versus self-hosted scenarios
- **FR-009**: System MUST support deployment on independent VPS providers (DigitalOcean, Linode, Hetzner, Vultr, OVH, etc.) and community cloud services that do not rely on big tech infrastructure
- **FR-010**: System MUST provide guidance on securing independent deployments (firewall configuration, SSL/TLS certificates, access control), with provider-specific instructions for managed VPS versus self-hosted setups
- **FR-011**: System MUST document how to configure networking for independent deployments (domain setup, port forwarding, reverse proxy configuration), including provider-managed networking options where available
- **FR-012**: System MUST provide backup and restore procedures that work with independent infrastructure, leveraging provider backup services for managed VPS when available
- **FR-013**: System MUST support deployment on common Linux distributions (Ubuntu, Debian, CentOS/RHEL) without requiring proprietary operating systems, and support provider-managed OS images for managed VPS deployments
- **FR-014**: System MUST document how to handle updates and maintenance on independent infrastructure, with different procedures for managed VPS (using provider tools) versus self-hosted (manual updates)
- **FR-015**: System MUST provide guidance on monitoring and logging that uses open-source tools, not big tech cloud monitoring services, while optionally leveraging provider monitoring features for managed VPS
- **FR-016**: System MUST clearly identify which components require internet connectivity and which can operate fully offline
- **FR-017**: System MUST provide cost estimates and comparisons for different independent hosting scenarios (managed VPS providers, personal hardware, community cloud), including trade-offs between cost, convenience, and control
- **FR-018**: System MUST document how to obtain and renew SSL/TLS certificates using free certificate authorities (Let's Encrypt) without requiring big tech certificate services

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with basic technical knowledge can complete deployment on independent infrastructure in under 2 hours following the provided documentation, with faster deployment times for managed VPS providers
- **SC-002**: Deployment documentation enables successful deployment on at least three different hosting scenarios (e.g., independent managed VPS, self-hosted server, community cloud) without requiring big tech services
- **SC-003**: All application data (databases, vector store, uploaded documents) remains on independent infrastructure with zero data transmission to AWS/GCP/Azure storage or analytics services during normal operation
- **SC-004**: Deployment scripts or automation successfully install and configure all required services (application, ArangoDB, Qdrant) on independent infrastructure without manual database or service configuration, with optional use of provider-managed services where available
- **SC-005**: Independent deployment supports at least 10 concurrent users with response times under 5 seconds for typical queries, with documented scaling options for both managed and self-hosted scenarios
- **SC-006**: System documentation identifies at least 4 independent hosting options (independent managed VPS, personal hardware, community cloud, platform-as-a-service) with cost comparisons and estimated monthly costs under $50 for small deployments
- **SC-007**: Users can access the application via web browser from the internet after deployment, with SSL/TLS encryption configured using free certificate authorities
- **SC-008**: Deployment documentation receives positive feedback from at least 2 independent reviewers who successfully complete deployment without prior knowledge of the application
- **SC-009**: Backup and restore procedures successfully preserve all application data (databases, configurations, uploaded files) and can restore to a new server within 1 hour
- **SC-010**: System provides clear guidance on monitoring and maintenance that does not require big tech cloud monitoring services, enabling administrators to maintain the deployment independently, with optional use of provider monitoring tools for managed VPS

## Assumptions

- Users have access to independent hosting infrastructure (physical hardware, VPS from independent providers like DigitalOcean/Linode/Hetzner/Vultr/OVH, community cloud services, or platform-as-a-service tools)
- Users may have varying levels of technical expertise - some may prefer fully managed VPS options requiring minimal server administration, while others may self-host requiring more technical knowledge
- Users have internet connectivity for initial setup and optional external API access (LLM services)
- Independent hosting infrastructure has sufficient resources (CPU, RAM, storage) to run Docker containers and required services, with managed VPS providers offering easier resource provisioning
- Users want to avoid big tech cloud services but may still use external APIs (like LLM providers) that are explicitly configured and documented
- SSL/TLS certificates can be obtained from free certificate authorities (Let's Encrypt), with some managed VPS providers offering automated certificate management
- Users have or can obtain a domain name for public access (or can use IP address access for private deployments), with some managed VPS providers offering domain management services
- Independent VPS providers, community cloud services, and platform-as-a-service tools exist and are accessible to users
- Docker and Docker Compose are available and can be installed on the target infrastructure, or platform-as-a-service tools provide container management
- Network configuration (firewall rules, port forwarding) can be managed by the user, system administrator, or provider (for managed VPS services)

## Dependencies

- Access to independent hosting infrastructure (personal hardware, managed VPS from independent providers, community cloud services, or platform-as-a-service tools)
- Docker and Docker Compose installation on target infrastructure (or platform-as-a-service providing container management)
- Internet connectivity for deployment downloads and optional external API access
- Domain name registration (for public access) or network configuration knowledge (for private access), with optional provider-managed domain services
- Varying levels of technical knowledge depending on hosting choice (minimal for managed VPS, more extensive for self-hosted deployments)

## Out of Scope

- Hosting the application as a managed service for users (users deploy themselves)
- Integration with big tech cloud services (AWS, GCP, Azure) even as optional features
- Development of custom hosting platform or infrastructure
- Support for proprietary operating systems or deployment platforms
- Automated scaling across multiple servers or data centers
- Managed database or storage services from big tech providers
- Integration with big tech analytics or monitoring services
- Development of mobile applications or native clients
- Multi-tenant hosting infrastructure where multiple users share a single deployment

