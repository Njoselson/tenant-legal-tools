# Knowledge Graph Schema — Design Decisions

> Written 2026-04-15. Supersedes the entity model sections in ARCHITECTURE.md.
> Context: after live graph audit revealed structural problems (overcrowded claim nodes, case-specific
> evidence as permanent nodes, dynamic claim types mapped to OTHER). This doc records the decisions
> made and why — don't relitigate them without a concrete reason.

---

## The Problem This Solves

The graph was trying to be two things at once:

1. A **legal schema** — what claims exist, what must be proven, what laws apply, what procedures to follow
2. A **case evidence database** — what specific evidence Scherley submitted in 2005, what the court in Jourdain considered in 2018

These don't belong in the same layer. Case-specific evidence is noise from the schema perspective. It accumulates with every ingested case, crowding claim nodes with dozens of named artifacts ("Scherley's Marriage Certificate", "Johnsie Lee's Hospitalization Proof") that have no `case_id`, no reusability, and obscure the actual legal requirements.

Separately: claim types were a hardcoded Python enum. When `SUCCESSION_RIGHTS` wasn't in the enum, it silently fell back to `OTHER`, breaking all retrieval for succession rights queries. Hardcoded taxonomies are an antipattern — they break silently and require developer intervention for every new claim type.

---

## Core Design Decisions

### 1. Claim types are dynamic graph nodes, not a hardcoded enum

**Decision:** Remove the `ClaimType` Python enum as a validation gate. Claim types are nodes in the `entities` collection (`type="claim_type"`). They are created automatically at ingestion time from whatever the LLM extracts, normalized (uppercase + underscores), and deduplicated using the existing embedding similarity pipeline (BM25 + cosine, same thresholds as entity dedup).

**What this means:**
- `SUCCESSION_RIGHTS` gets created as a node the first time it's extracted from any document
- New claim types never fail silently — they just become new nodes
- The LLM extraction prompt receives a dynamic list of known claim type names at runtime (fetched from DB), not a hardcoded string. This gives the model context without constraining it.
- If the LLM outputs a near-duplicate name (`SUCCESSION_RIGHTS_CLAIM` vs. `SUCCESSION_RIGHTS`), the embedding dedup pipeline collapses them

**The old `ClaimType` enum** in `models/claim_types.py` may be kept as a reference comment but is no longer used in code logic (not in prompts, not in validation, not in retrieval).

---

### 2. The graph is a schema of legal reasoning, not a case evidence database

**Decision:** ArangoDB stores the *structure* of legal reasoning. Qdrant stores the *content* of legal documents and cases.

**ArangoDB nodes (what lives here permanently):**
- `law` — statutes, regulations, administrative code sections
- `claim_type` — causes of action (SUCCESSION_RIGHTS, HABITABILITY_VIOLATION, etc.)
- `evidence` (canonical only) — what must be proven, as defined by statutes, guides, and case-established standards
- `legal_procedure` — how to pursue a claim (DHCR application, HP Action, holdover defense)
- `case_document` — metadata for a court opinion (name, court, date, outcome, holdings) — NOT the full text
- `legal_claim` — a specific claim as asserted in a specific case, linked to its case_document and claim_type
- `legal_outcome` — what the court ordered

**Qdrant (what lives here as text + embeddings):**
- All document text — statute text, guide text, case opinions — split into chunks
- Case-specific evidence is text in the case opinion's chunks, not a separate graph node
- Entity embeddings for canonical ArangoDB nodes (for semantic search into the graph)

---

### 3. Evidence nodes are canonical, not case-specific

**Decision:** An EVIDENCE node in ArangoDB represents a *type of proof required by law*, not a specific artifact submitted in a specific case.

**Canonical evidence (what belongs in ArangoDB):**
- "Proof of 2-year co-primary residence" — required by RSC § 2523.5(b)(1)
- "Proof of qualifying family relationship" — required by RSC § 2520.6(o)
- "Proof tenant of record permanently vacated" — standard clarified by EB Bedford LLC v Lee (2019)
- "Written notice of rent increase" — required by RSC § 2522.5

These come from statutes and guides. They are stable, reusable across cases, and define the boundaries of what must be proven.

**Case-specific evidence (what does NOT belong in ArangoDB):**
- "Scherley's 2005 Lease Renewal Form"
- "Johnsie Lee's Hospitalization Records"
- "Affidavit of Caroline K."

These are ephemeral case artifacts. They live as text in Qdrant chunks under their source CASE_DOCUMENT. They are never ArangoDB nodes.

**How the graph gets smarter from cases:**

When a court opinion is ingested:
1. Extract evidence items from the case (using canonical vocabulary in the prompt — "Proof of family relationship", not "Scherley's Marriage Certificate")
2. Embed each evidence item and search existing canonical evidence nodes
3. If similarity ≥ threshold: link the Qdrant chunk containing that evidence to the canonical node (`chunk_ids` accumulates), and add `LEGAL_CLAIM → HAS_EVIDENCE → canonical_node` edge
4. If similarity < threshold AND evidence_context is "required" (court established a new standard): create a new canonical evidence node
5. If similarity < threshold AND evidence_context is "presented" (case-specific artifact): skip — stays in Qdrant text only

Over time, canonical evidence nodes accumulate `chunk_ids` from every case where that type of proof was evaluated. A tenant asking "what counts as proof of co-residency?" gets the full picture: statutory definition + how courts have evaluated it across 8 cases.

---

### 4. The CLAIM_TYPE node is the hub

**Decision:** CLAIM_TYPE nodes are the primary traversal hub. All roads lead to/from the claim type.

```
CLAIM_TYPE node  ← the hub
  ← IS_TYPE_OF   ← LEGAL_CLAIM instances (from cases — what this claim looked like in practice)
  ← ADDRESSES    ← LAW nodes (statutes that authorize this claim, deduplicated)
  ← ADDRESSES    ← CASE_DOCUMENT nodes (cases that addressed this claim type)
  ← ADDRESSES    ← LEGAL_PROCEDURE nodes (how to pursue it)
  → REQUIRED_FOR → EVIDENCE nodes (canonical — what must be proven)
```

This means: given a claim type, a single graph traversal can return everything a tenant needs:
- What laws authorize this claim
- What must be proven
- What procedures to follow
- Which cases have addressed it

**Edge deduplication:** All edges are deduplicated at insert time via `(from_id, type, to_id)` uniqueness check. A law that appears in 5 ingested cases still produces exactly one `LAW → ADDRESSES → CLAIM_TYPE` edge.

---

### 5. Cases to cite: graph + Qdrant, two different jobs

**Decision:** Use both the graph and Qdrant for surfacing relevant cases, because they answer different questions.

**Graph edge (CASE_DOCUMENT → ADDRESSES → CLAIM_TYPE):** "Which cases have ever addressed SUCCESSION_RIGHTS?" Exact membership. Written at ingestion time.

**Qdrant semantic search:** "Which of those cases is most relevant to THIS specific tenant's situation?" Re-ranks by vector similarity to the query. A tenant who hasn't been living in the apartment needs cases where non-residency was specifically litigated — not just any succession rights case.

The flow: graph traversal finds all cases for the claim type → Qdrant re-ranks by relevance to the specific query → top N cases cited in the response.

---

## The Graph in Practice: Succession Rights Query

Query: "Can I take over my dad's rent-stabilized apartment? I haven't been living there but I've been on the lease for 2 years."

**Step 1 — Claim type routing:** Semantic search finds CLAIM_TYPE node `succession_rights`

**Step 2 — Graph traversal from CLAIM_TYPE:**
- → REQUIRED_FOR → "Proof of 2-year co-primary residence", "Proof of qualifying family relationship", "Proof tenant permanently vacated" (canonical evidence — what to prove)
- ← ADDRESSES ← RSC § 2523.5(b)(1), RSC § 2520.6(o) (applicable laws)
- ← ADDRESSES ← "DHCR Succession Application", "Holdover Defense" (procedures)
- ← ADDRESSES ← Jourdain 2018, EB Bedford 2019, 1234 Broadway 2015 (cases to cite)

**Step 3 — Qdrant semantic search:** Chunks semantically similar to "on the lease but not co-residing" — surfaces the RSC text distinguishing licensees from successors, and the DHCR guide clarifying that lease signature ≠ co-residency

**Step 4 — LLM synthesis:** "Your situation does not qualify for succession rights. Succession requires 2 years of co-primary residence, not just being named on the lease. Being on the lease makes you a licensee, not a successor. Here are the relevant cases..."

---

---

## Query-Informed Extraction — The Core Ingestion Loop

**Old approach:** Extract entities from document → then try to deduplicate against existing graph.

**New approach:** Query the graph first → inject what we know into the extraction prompt → LLM reuses existing entities by ID → only genuinely novel entities need dedup.

```
For each document:
  1. Identify claim type(s) — from manifest tags, or cheap first-pass LLM call
  2. Query graph: fetch existing nodes for those claim types
     (canonical evidence, laws, procedures, claim_type node itself)
  3. Inject into extraction prompt:
     "These entities already exist — reference them by ID if they apply to this document"
  4. LLM extracts — outputs existing_entity_id for recognized entities, null for new ones
  5. Post-extraction:
     - existing_entity_id present → enrich existing node (append chunk_ids, merge description, add edges)
     - existing_entity_id absent → embedding dedup safety net → merge or create new node
```

The LLM is better at semantic matching than cosine similarity ("this marriage certificate is an instance of 'Proof of qualifying family relationship'"). Embedding dedup becomes a safety net for stragglers, not the primary mechanism.

The extraction output schema gains one optional field per entity:
```json
{
  "id": "e1",
  "existing_entity_id": "evidence:abc123",  // null if genuinely new
  "name": "Proof of qualifying family relationship",
  "evidence_context": "presented"
}
```

---

## Per-Document-Type Behavior

### Statutes — seed the canonical schema

First statute on a claim type: graph is empty for this topic. LLM creates everything fresh — CLAIM_TYPE node, canonical evidence requirements, law node, procedure node.

Second statute on same claim type: pre-extraction query returns what the first statute created. LLM recognizes overlap, outputs `existing_entity_id` for matching entities. Existing nodes get enriched: new chunk added, description merged with attribution from both sources, new edges added if needed.

**Statutes rarely create duplicate nodes.** They do create new ones when they cover a genuinely different angle (Public Housing Law succession rights vs. RSC succession rights — same claim type, different procedural path).

### Guides — enrich with practical detail

Guides almost never create new canonical nodes. They explain *how* to satisfy statutory requirements. Their evidence is `evidence_context="recommended"` — practical suggestions that reference existing canonical requirements.

Pre-extraction query returns existing canonical nodes. LLM maps guide advice to existing entities:
- "Utility bills, voter registration, bank statements" → `existing_entity_id` of "Proof of 2-year co-primary residence" → guide chunk added to that node
- "File Form RTP-8 within 90 days" → `existing_entity_id` of DHCR procedure node → procedural detail chunk added

Result: canonical nodes accumulate practical chunks. "What documents should I gather for co-residency?" is answered by the canonical evidence node's chunk from the DHCR guide.

### Court Opinions — three outcomes per extracted entity

Pre-extraction query returns all canonical entities for the document's claim type(s).

**Outcome 1 — Matches existing canonical node:** LLM outputs `existing_entity_id`. We append the case chunk to that canonical node's `chunk_ids`, add `LEGAL_CLAIM → HAS_EVIDENCE → canonical_node` edge. No new node. The canonical node now has a case example showing how courts evaluated that type of proof.

**Outcome 2 — Establishes a new legal standard:** Court opinion clarifies what's legally required (not just what was presented). LLM outputs `existing_entity_id: null` with `evidence_context="required"` and a canonical name. Embedding dedup finds no match → new canonical node created with `REQUIRED_FOR → CLAIM_TYPE` edge. Example: EB Bedford LLC v Lee (2019) established "nursing home placement = permanent vacatur; hospitalization = temporary."

**Outcome 3 — Case-specific artifact, no canonical match:** Evidence that's case-specific and doesn't establish a new standard (e.g., `evidence_context="presented"`, similarity below threshold). No graph node created. Stays as text in Qdrant under its CASE_DOCUMENT.

**Case-level nodes always created from court opinions:**
- `CASE_DOCUMENT` (name, court, date, outcome, holdings)
- `LEGAL_CLAIM` (the specific claim, linked via IS_TYPE_OF to CLAIM_TYPE)
- `LEGAL_OUTCOME` (what the court ordered)
- `CASE_DOCUMENT → ADDRESSES → CLAIM_TYPE` edge

---

## How the Graph Gets Smarter Over Time

After ingesting 1 statute + 1 guide + 5 succession rights cases, the "Proof of 2-year co-primary residence" node has:

```
source_ids:  [rsc_statute_uuid, dhcr_guide_uuid, 5 case UUIDs]
chunk_ids:   [
  rsc_chunk_3     ← "tenant must reside as primary residence for 2 years prior to vacancy"
  dhcr_chunk_8    ← "acceptable proof: utility bills, voter registration, bank statements"
  jourdain_chunk_5 ← "affidavit alone insufficient; corroboration required"
  eb_bedford_chunk_12 ← "testimony + lease renewals satisfied co-residency"
  well_done_chunk_7  ← "non-primary residence established where tenant kept separate home"
]
```

A single canonical node surfaces statutory definition + practical guidance + 5 case examples. The LLM gets everything from one graph traversal + the linked chunks.

**On contradictions:** If a case applies a stricter standard than the statute (e.g., "3 years" vs. "2 years"), the LLM enriches the existing node's description rather than creating a contradictory node: "RSC requires 2 years; some courts have applied stricter standards in specific circumstances." The nuance lives in the description merge and in the associated chunks.

---

## When Does a New Node Get Created?

| Document type | Condition | New ArangoDB node? |
|---|---|---|
| Statute/guide | New legal concept, no similar node | **Yes** |
| Statute/guide | Same concept as existing node | **No** — enrich existing |
| Court opinion | New legal standard established by case | **Yes** (canonical, `context=required`) |
| Court opinion | Presented evidence matching existing canonical | **No** — link chunk to existing |
| Court opinion | Case-specific artifact, no canonical match | **No** — Qdrant only |

---

## What Changed From the Old Model

| Old | New |
|-----|-----|
| ClaimType Python enum (hardcoded, breaks silently) | Dynamic claim_type nodes (auto-created, embedding-deduped) |
| Case evidence as ArangoDB nodes (no case_id, clutters graph) | Case evidence as Qdrant text only — unless it establishes a new legal standard |
| Extract first, deduplicate after | Query graph first, inject into prompt, LLM reuses existing entities |
| Canonical evidence mixed with case artifacts in graph traversal | Canonical evidence nodes only in ArangoDB; chunk_ids link to all sources |
| Claim type is a string attribute | Claim type is a graph node (traversal hub) |
| Law → LEGAL_CLAIM edges duplicated per ingested case | Law → CLAIM_TYPE edges, deduplicated |
| No CASE_DOCUMENT → CLAIM_TYPE link | CASE_DOCUMENT → ADDRESSES → CLAIM_TYPE at ingestion |
| LLM constrained to hardcoded valid claim type list | LLM given dynamic existing-entity context, free to create new types |
