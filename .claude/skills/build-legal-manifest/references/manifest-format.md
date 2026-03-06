# Manifest Format Reference

Every line in a `.jsonl` manifest must be a single valid JSON object.

## Required Fields (all entries)

| Field | Type | Values |
|-------|------|--------|
| `locator` | string | Full URL |
| `kind` | string | Always `"url"` |
| `title` | string | Human-readable; include section number for statutes |
| `document_type` | string | See below — NEVER `"unknown"` |
| `authority` | string | See below |

## Conditional Fields

| Field | When required |
|-------|--------------|
| `jurisdiction` | Always include; `"NYC"` or `"New York State"` or `"New York"` |
| `organization` | Include for statutes/guides; publishing org name |
| `tags` | Always include; array of snake_case strings |
| `metadata` | Required for `court_opinion`; optional for others |

## document_type Values

| Value | Use for |
|-------|---------|
| `statute` | Statutes, codes, regulations (nysenate.gov, amlegal.com, justia codes, regulations.justia.com) |
| `legal_guide` | Tenant advocacy guides, court self-help pages, government agency explainers |
| `court_opinion` | Case law (Justia cases, court decisions) |

**CRITICAL: `document_type` must NEVER be `"unknown"`. The ingestion pipeline rejects entries with unknown type.**

## authority Values

| Value | Use for |
|-------|---------|
| `binding_legal_authority` | Statutes, regulations, court opinions |
| `official_interpretive` | Agency guides (hcr.ny.gov, nyc.gov/hpd, nycourts.gov) |
| `practical_self_help` | Tenant org guides (metcouncilonhousing.org, legalaidnyc.org) |

## metadata Object (court_opinion)

```json
{
  "court": "Housing Court",
  "decision_date": "YYYY-MM-DD",
  "citation": "2025-NY-SLIP-OP-12345"
}
```

`decision_date` must be ISO format. If unknown, omit the field rather than guessing.

## Tag Conventions

Always include the primary topic tag (e.g. `"habitability"`, `"harassment"`, `"rent_stabilization"`).

Secondary tags by type:
- Statutes: `"heat"`, `"mold"`, `"repairs"`, `"destabilization"`
- Cases: `"housing_court"`, `"rent_abatement"`, `"treble_damages"`
- Guides: `"hp_action"`, `"tenant_rights"`

## Complete Examples

### Statute
```json
{"locator": "https://law.justia.com/codes/new-york/rpp/article-7/235-b/", "kind": "url", "title": "RPL § 235-b — Warranty of Habitability", "document_type": "statute", "authority": "binding_legal_authority", "jurisdiction": "New York State", "organization": "New York State Legislature", "tags": ["habitability", "repairs", "warranty_of_habitability"]}
```

### Legal guide
```json
{"locator": "https://www.metcouncilonhousing.org/help-answers/getting-repairs/", "kind": "url", "title": "Met Council — Getting Repairs", "document_type": "legal_guide", "authority": "practical_self_help", "jurisdiction": "NYC", "organization": "Met Council on Housing", "tags": ["habitability", "repairs"]}
```

### Court opinion
```json
{"locator": "https://law.justia.com/cases/new-york/other-courts/2025/2025-ny-slip-op-25282.html", "kind": "url", "title": "Yorkville Plaza Assoc. LLC v Guo", "document_type": "court_opinion", "authority": "binding_legal_authority", "jurisdiction": "New York", "tags": ["housing_court", "habitability"], "metadata": {"court": "Housing Court", "decision_date": "2025-12-26", "citation": "2025-NY-SLIP-OP-25282"}}
```
