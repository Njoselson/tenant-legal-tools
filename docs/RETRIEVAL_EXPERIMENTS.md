# Retrieval Quality Test Results

**Test script:** `scripts/retrieval_test.py`
**5 queries:** heat, mold, harassment, deregulation, rent overcharge — based on tenant's real situation

---

## Run 2: Post M2/M3 Data Ingestion (2026-03-07)

**Graph:** 659 entities, 1,113 edges, 45 unique sources (25 statutes/guides + 17 cases + 3 prior)

### Overall Scores

| Metric | Run 1 (pre-cases) | Run 2 (post-cases) | Change |
|--------|-------------------|-------------------|--------|
| **Law coverage** | 6/16 (38%) | 8/16 (50%) | +12% |
| **Type coverage** | 18/18 (100%) | 18/18 (100%) | — |
| **Topic coverage** | 18/19 (95%) | 18/19 (95%) | — |
| **Combined** | **77%** | **82%** | **+5%** |
| **Avg entities/query** | 70 | 89 | +27% |

### Per-Query Results

#### Q1: Heat (habitability)
- **Chunks:** 10, top score 0.681
- **Entities:** 80 (17 claims, 14 laws, 23 evidence, 11 outcomes, 9 procedures, 4 case docs)
- **Strengths:** Heat laws, HP action procedures, HPD complaint process, temperature measurement evidence
- **Gap:** RPL § 235-b section number not in entity names/descriptions; § 27-2029 same issue

#### Q2: Mold (habitability)
- **Chunks:** 10, top score 0.616
- **Entities:** 80 (10 claims, 11 laws, 26 evidence, 16 outcomes, 13 procedures)
- **Strengths:** § 27-2017.3 found, mold-specific entities surfaced, repair procedures present
- **Gap:** RPL § 235-b / MDL § 78 in graph but not surfaced for this query

#### Q3: Harassment
- **Chunks:** 10, top score 0.739
- **Entities:** 70 (19 claims, 7 laws, 18 evidence, 15 outcomes, 11 procedures)
- **Improvement:** New chunk "Tenant harassment law — Prohibits harassment" at 0.704. More evidence entities (8 → 18)
- **Gap:** § 27-2004/2005 section numbers still not in entity names (ingested via Article 1 page). "threatening" keyword not found in retrieved text.

#### Q4: Deregulation
- **Chunks:** 10, top score 0.754 (was 0.666)
- **Entities:** 114 (19 claims, 37 laws, 35 evidence, 8 case docs) — richest result set
- **Improvement:** Top score jumped +0.088. ETPA now found. Case-specific evidence: "Last publicly registered rent from 2003", "Defendant's Failure to Register Apartments in 2012". 8 case documents surfaced.
- **Gap:** RSC abbreviation still not matched

#### Q5: Rent Overcharge
- **Chunks:** 10, top score 0.734 (was 0.729)
- **Entities:** 101 (19 claims, 31 laws, 22 evidence, 10 case docs)
- **Improvement:** HSTPA now found. Case-specific evidence: "Registered Legal Regulated Rent (2002)", "Annual Rent Registration Statement". 10 case documents surfaced.
- **Gap:** RSC abbreviation still not matched

### Impact of Case Law Ingestion

The biggest improvements from adding 17 court opinions:
1. **Case documents in results** — Q4 gets 8 case docs, Q5 gets 10. Before: 0–2.
2. **Real evidence examples** — entities now include actual evidence cited in cases (rent histories, registration statements, tenant affidavits) instead of only generic evidence types from guides.
3. **Higher top scores** — Q4 deregulation jumped from 0.666 to 0.754, showing that case-extracted chunks are more semantically relevant than statute text alone.
4. **More entities per query** — average went from 70 to 89 (+27%), providing richer context for the case analyzer.

---

## Run 1: Post M1 Session 5 — Entity Search Fix (2026-03-07)

**Graph:** 359 entities, 579 edges, 28 unique sources (statutes + guides only, no case law)

### Overall Scores

| Metric | Score | Notes |
|--------|-------|-------|
| **Law coverage** | 6/16 (38%) | Most misses are data gaps, not retrieval bugs |
| **Type coverage** | 18/18 (100%) | All expected entity types present in every query |
| **Topic coverage** | 18/19 (95%) | Only "threatening" missed in Q3 |
| **Combined** | **77%** | Passing threshold (70%) met |

### Bug Found and Fixed

**Entity search returning 0 results through HybridRetriever** — the `types` filter in `search_entities_by_text()` was placed inside the `SEARCH ANALYZER(...)` block in AQL, which caused it to be treated as a text-analyzed condition instead of an exact-match filter. Moved to a `FILTER` clause outside `SEARCH`. This was a critical bug — entity retrieval was completely broken for the case analyzer.

---

## Remaining Law Coverage Gaps

| Missing Law | Root Cause | Status |
|-------------|-----------|--------|
| RPL § 235-b | Entity named "Warranty of Habitability" — no section number | Extraction prompt issue |
| § 27-2029 | Entity "Heat and Hot Water Requirements" — no section number | Same |
| § 27-2004/2005 | Ingested via Article 1 page but entity names are descriptive | Same |
| § 27-2115 | Found in Run 1 and Run 2 | Resolved |
| ETPA | Found in Run 2 after HCR overview page ingested | Resolved |
| HSTPA | Found in Run 2 after case law ingested | Resolved |
| RSC | "Rent Stabilization Code Part 2520" — abbreviation not matched | Abbreviation alias needed |

## Scraping Availability (as of 2026-03-07)

| Source | Status | Notes |
|--------|--------|-------|
| nycourts.gov/reporter | Works | Use for case law (browser UA via requests) |
| nycadmincode.readthedocs.io | Works | NYC Admin Code statutes (article-level pages) |
| metcouncilonhousing.org | Works | Tenant guides |
| legalaidnyc.org | Works | Legal aid guides |
| hcr.ny.gov | Works | DHCR fact sheets and overviews |
| nyc.gov (HPD) | Works | City agency pages |
| law.justia.com | **403** | Blocked as of 2026-03-07 |
| codelibrary.amlegal.com | **403** | Blocked |
| nysenate.gov | **Empty** | Serves blank content to bots |

## Conclusions

1. **Retrieval mechanism is solid.** Vector search returns relevant chunks (0.62–0.75). Entity search returns 70–114 entities with correct type distribution. KG expansion adds useful neighbors.

2. **Case law dramatically improves results.** Real evidence examples, higher semantic scores, and case documents appearing in results give the case analyzer much richer context to work with.

3. **Remaining gaps are extraction-level.** Entity names use descriptive text ("Warranty of Habitability") instead of including section numbers ("RPL § 235-b"). This is an extraction prompt issue, not a retrieval issue.

4. **Abbreviation matching is a nice-to-have.** RSC is the only remaining unmatched abbreviation. Could add aliases to law entities.
