# Tenant Legal Guidance — Curated Taxonomy

This directory contains the hand-curated NYC-first legal taxonomy that is the authoritative source of truth for the knowledge graph. LLM extraction's only job is to *tag* documents against these IDs — it does not invent new nodes during steady-state ingestion (it proposes them for review).

---

## File overview

| File | Contents | ~Count |
|------|----------|--------|
| `claim_types.yaml` | NYC tenant claim types | 25 |
| `evidence_types.yaml` | Concrete, obtainable proof types | 40 |
| `procedures.yaml` | NYC procedural paths | 15 |
| `laws.yaml` | NYC + NYS statutes applicable in NYC | 50 |
| `requires_evidence.yaml` | ClaimType → Evidence edges (`critical: bool`) | ~80 |
| `typically_uses.yaml` | ClaimType → Procedure edges | ~50 |

---

## Node schema

All canonical nodes (`claim_types`, `evidence_types`, `procedures`, `laws`) share this structure:

```yaml
- id: slug_id_max_30_chars      # lowercase_underscores, ≤30 chars — ArangoDB _key
  name: Human Readable Name
  description: One or two sentence description.
  jurisdiction: NYC             # NYC | NYS
  status: canonical             # canonical | proposed
  aliases:                      # Alternative names the LLM may use
    - alternate name
    - another alias
```

**Additional fields by type:**

- `evidence_types.yaml`: `how_to_obtain` (string, brief note on how a tenant gets this)
- `procedures.yaml`: `filing_body` (string), `typical_duration` (string)
- `laws.yaml`: `citation` (canonical citation string), `effective_date` (ISO date, optional)

---

## Edge schema

### `requires_evidence.yaml`
Each entry maps a `ClaimTypeNode` to an `EvidenceNode` it requires:

```yaml
- claim_type_id: rent_overcharge   # ClaimTypeNode.id
  evidence_id: dhcr_rent_history   # EvidenceNode.id
  critical: true                   # true → missing this likely defeats the claim
```

### `typically_uses.yaml`
Each entry maps a `ClaimTypeNode` to a `ProcedureNode` typically used to pursue it:

```yaml
- claim_type_id: habitability_violation
  procedure_id: hp_action_repairs
```

---

## ID conventions

- **Slug format**: `lowercase_underscores`, ≤ 30 characters
- **Uniqueness**: IDs must be globally unique within their kind (`claim_type_id`, `evidence_id`, `procedure_id`, `law_id`)
- **Stability**: once an ID is in `canonical` status and `seed_taxonomy.py` has run, do **not** rename it — rename only via the curation UI which handles edge remapping
- **Cross-references**: `requires_evidence.yaml` and `typically_uses.yaml` reference IDs from the node files; `seed_taxonomy.py --dry-run` validates referential integrity

---

## Adding / editing entries

### Adding a new canonical entry
1. Add the YAML entry with `status: canonical` to the appropriate file
2. Run `make seed-taxonomy` — the seeder is idempotent, adding only the new node

### Promoting a proposed entry
Use the curation UI at `/curate` (Phase 5) or manually:
1. Find the proposed node in ArangoDB
2. Set `status` from `proposed` to `canonical`
3. Run `make seed-taxonomy --diff` to confirm

### Renaming an ID (rare)
Use `gitnexus_rename` + a migration script — do not find-and-replace. All edges referencing the old ID must be updated atomically.

---

## Curation workflow

**Bootstrap (one-time, Phase 1b/1c):**
1. Run `scripts/bootstrap_taxonomy.py` over existing manifests → produces `data/taxonomy/*.yaml.draft`
2. Review drafts in the curation UI (cluster mode)
3. Promote clusters → merges variants as aliases → writes final YAML entries
4. Check in final `*.yaml` files

**Steady-state:**
- During ingestion, `case_tagger.py` tags documents against canonical IDs
- Items not found in the taxonomy go to the proposed queue (`status: proposed`) with `proposal_metadata.{source_ids, sample_quotes, justification}`
- Review proposals at `/curate` — promote, merge as alias, or reject

---

## Validation

```bash
# Dry run — validate referential integrity, no DB writes
uv run python -m tenant_legal_guidance.scripts.seed_taxonomy --dry-run

# Show what would change vs. current DB state
uv run python -m tenant_legal_guidance.scripts.seed_taxonomy --diff

# Seed (idempotent)
make seed-taxonomy
```

Invariants checked by `validate_graph.py`:
- Every `requires_evidence` edge source/target maps to a canonical node
- Every `typically_uses` edge source/target maps to a canonical node
- No canonical node lacks an `id`, `name`, or `jurisdiction`
