# Documentation

Complete documentation for the Tenant Legal Guidance System.

## 📚 Core Guides

| Guide | What's Inside | Read When... |
|-------|--------------|--------------|
| **[GETTING_STARTED.md](GETTING_STARTED.md)** | Setup, installation, first steps | You're new to the project |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | System design, data flow, components | You want to understand how it works |
| **[DATA_INGESTION.md](DATA_INGESTION.md)** | Manifests, scraping, ETL pipeline | You need to add/manage data |
| **[DEPLOYMENT.md](DEPLOYMENT.md)** | Production deploy, Docker, CI/CD | You're deploying to production |
| **[DEVELOPMENT.md](DEVELOPMENT.md)** | Dev setup, testing, contributing | You're developing features |
| **[SECURITY.md](SECURITY.md)** | Security features, PII anonymization | You need to secure the system |
| **[ENTITY_MANAGEMENT.md](ENTITY_MANAGEMENT.md)** | Entities, resolution, deduplication | You're working with knowledge graph |
| **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** | Common issues, fixes, debugging | Something isn't working |

## 🔍 Reference Docs

| Document | Purpose |
|----------|---------|
| **[API_REQUEST_FLOW.md](API_REQUEST_FLOW.md)** | How requests flow through the system |
| **[DEPENDENCY_GRAPH.md](DEPENDENCY_GRAPH.md)** | Service dependencies (Mermaid diagrams) |
| **[PROJECT_ORGANIZATION.md](PROJECT_ORGANIZATION.md)** | Repository structure, file organization |

## 🎯 Quick Navigation

**I want to...**

- **Get started** → [GETTING_STARTED.md](GETTING_STARTED.md)
- **Understand the architecture** → [ARCHITECTURE.md](ARCHITECTURE.md)
- **Add data sources** → [DATA_INGESTION.md](DATA_INGESTION.md#manifest-format)
- **Deploy to production** → [DEPLOYMENT.md](DEPLOYMENT.md#production-checklist)
- **Run tests** → [DEVELOPMENT.md](DEVELOPMENT.md#testing)
- **Fix an issue** → [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Secure the app** → [SECURITY.md](SECURITY.md#security-best-practices)
- **Manage entities** → [ENTITY_MANAGEMENT.md](ENTITY_MANAGEMENT.md)

## 📖 Documentation Overview

### Getting Started (Start Here!)
1. Read [GETTING_STARTED.md](GETTING_STARTED.md) - 15 min setup
2. Ingest sample data
3. Try the web UI at http://localhost:8000
4. Read [ARCHITECTURE.md](ARCHITECTURE.md) to understand internals

### For Developers
1. [DEVELOPMENT.md](DEVELOPMENT.md) - Set up dev environment
2. [ARCHITECTURE.md](ARCHITECTURE.md) - Understand system design
3. [API_REQUEST_FLOW.md](API_REQUEST_FLOW.md) - Trace request paths
4. [DEPENDENCY_GRAPH.md](DEPENDENCY_GRAPH.md) - See service relationships

### For Operators/DevOps
1. [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment guide
2. [SECURITY.md](SECURITY.md) - Security hardening
3. [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues

### For Data Managers
1. [DATA_INGESTION.md](DATA_INGESTION.md) - Ingestion pipeline
2. [ENTITY_MANAGEMENT.md](ENTITY_MANAGEMENT.md) - Knowledge graph management

## 🆘 Need Help?

1. **Check docs above** for your topic
2. **Search troubleshooting** → [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
3. **Review logs** → `logs/tenant_legal_*.log`
4. **Check GitHub Issues** → https://github.com/Njoselson/tenant_legal_guidance/issues

## 🔗 External Links

- **Main README:** [../README.md](../README.md)
- **Repository Guide:** [../CLAUDE.md](../CLAUDE.md)
- **API Docs:** http://localhost:8000/docs (when running)

---

**Documentation:** 8 core guides + 3 reference docs + 1 index = 12 total (simplified from 41!)
