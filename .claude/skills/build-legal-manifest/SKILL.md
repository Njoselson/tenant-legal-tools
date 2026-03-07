---
name: build-legal-manifest
description: This skill should be used when the user asks to "build a manifest", "research laws for", "ingest statutes for", "add cases for", "research and ingest", or "build manifests for" a legal topic. Handles the full workflow of web research, Justia case searches, manifest file creation, and optional ingestion for any NYC/NY tenant law topic.
version: 1.0.0
disable-model-invocation: false
allowed-tools: WebSearch, WebFetch, Read, Write, Edit, Bash, Glob
---

# Build Legal Manifest

Research laws, statutes, and cases for a tenant law topic, build JSONL manifest files, and optionally ingest them.

## Input

`$ARGUMENTS` = topic description, e.g. `"habitability/heat/mold"` or `"harassment and destabilization"`

If no arguments given, ask the user: "What legal topic should I research? (e.g. 'habitability/heat', 'harassment', 'rent overcharge')"

## Workflow

Run all 4 phases in order. Do not skip phases.

---

### Phase 1: Research statutes and guides

Use `WebSearch` to find authoritative sources for the topic. Run these searches:

1. `site:nysenate.gov OR site:law.justia.com/codes/new-york {topic} tenant`
2. `site:codelibrary.amlegal.com NYCadmin {topic} tenant`
3. `site:metcouncilonhousing.org {topic}`
4. `site:legalaidnyc.org {topic} tenant`
5. `site:hcr.ny.gov {topic}` (for rent stabilization topics)
6. `site:nyc.gov/site/hpd {topic}` (for repairs/housing topics)
7. `site:nycourts.gov {topic}` (for HP actions, procedures)

For each result that looks relevant, use `WebFetch` to confirm the page exists and contains useful content. Discard 404s and pages without substantive legal text.

Classify each source:
- `document_type`: `statute` | `legal_guide`
- `authority`: `binding_legal_authority` | `practical_self_help` | `official_interpretive`
  - `binding_legal_authority`: statutes, regulations (nysenate.gov, amlegal.com, justia codes)
  - `official_interpretive`: government agency guides (hcr.ny.gov, nyc.gov, nycourts.gov)
  - `practical_self_help`: tenant advocacy orgs (metcouncilonhousing.org, legalaidnyc.org)
- `jurisdiction`: `NYC` | `New York State`

Target: 6–15 statutes + guides total.

---

### Phase 2: Search Justia for case law

Use `build_manifest.py --justia-search` for 3 targeted searches. The topic determines the keywords.

For each search, run:
```bash
uv run python -m tenant_legal_guidance.scripts.build_manifest \
  --justia-search \
  --keywords {keyword1} {keyword2} "New York" \
  --max-results 50 \
  --output data/manifests/_tmp_{slug}_{n}.jsonl \
  --filter-relevance
```

Choose 3 keyword sets that cover different angles of the topic (e.g. legal standard, evidence type, remedy sought). See [references/keyword-sets.md](references/keyword-sets.md) for examples by topic.

After all 3 searches, deduplicate by `locator` across the temp files:
```bash
# Print all locators to check for dups — no code needed, just read the files
```

Review the deduplicated results. Keep cases that have:
- A clear plaintiff/defendant and outcome (tenant win or loss)
- Evidence-to-outcome chain mentioned (not purely procedural)
- Relevance to the topic

Target: ~25 keeper cases. Discard the rest.

---

### Phase 3: Write manifest files

**Statutes + guides** → `data/manifests/{slug}_statutes.jsonl`
**Cases** → `data/manifests/{slug}_cases.jsonl`

Where `{slug}` is a snake_case identifier for the topic (e.g. `habitability`, `harassment_destabilization`).

Each line must be valid JSON in this exact format. See [references/manifest-format.md](references/manifest-format.md) for the complete spec and field rules.

**Statute/guide entry:**
```json
{"locator": "https://...", "kind": "url", "title": "Full title with section number", "document_type": "statute", "authority": "binding_legal_authority", "jurisdiction": "NYC", "organization": "City of New York", "tags": ["topic_tag", "subtopic_tag"]}
```

**Case entry:**
```json
{"locator": "https://law.justia.com/cases/...", "kind": "url", "title": "Party A v Party B", "document_type": "court_opinion", "authority": "binding_legal_authority", "jurisdiction": "New York", "tags": ["housing_court", "topic_tag"], "metadata": {"court": "Housing Court", "decision_date": "YYYY-MM-DD", "citation": "..."}}
```

Rules:
- `document_type` MUST NOT be `"unknown"` — ingestion will reject it
- `title` must be specific enough to identify the source (include section numbers for statutes)
- `tags` should include the topic slug and any relevant subtopics
- Delete the temp files after writing the final manifests

---

### Phase 4: Validate and optionally ingest

**Validate** both manifests:
```bash
uv run python -m tenant_legal_guidance.scripts.validate_manifest \
  data/manifests/{slug}_statutes.jsonl

uv run python -m tenant_legal_guidance.scripts.validate_manifest \
  data/manifests/{slug}_cases.jsonl
```

If validate_manifest doesn't exist, spot-check by reading the files and confirming valid JSON on each line.

**Ask the user** before ingesting:
> "Manifests ready: {n_statutes} statutes/guides and {n_cases} cases. Ingest now? (requires `make services-up`)"

If yes, ingest:
```bash
make services-up  # remind user to run this first if not already up

uv run python -m tenant_legal_guidance.scripts.ingest_all_manifests \
  --skip-existing \
  --concurrency 3 \
  --report data/ingestion_report_{slug}.json
```

Check the report for failures:
```bash
# Read data/ingestion_report_{slug}.json and summarize: how many succeeded, failed, skipped
```

**Update ROADMAP.md**: mark the relevant M2/M3 session as complete.

---

## Output Summary

Report to the user:
- Files created: `data/manifests/{slug}_statutes.jsonl` (N entries), `data/manifests/{slug}_cases.jsonl` (N entries)
- What was discarded and why (404s, procedural-only cases, etc.)
- Ingestion result if run (N ingested, N failed, N skipped)
- Any manual follow-up needed (e.g. cases that need closer review)
