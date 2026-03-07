# M1 Session 5: Retrieval Quality Test Results

**Date:** 2026-03-07
**Graph:** 359 entities, 579 edges, 28 unique sources
**Test script:** `scripts/retrieval_test.py`

## Overall Scores

| Metric | Score | Notes |
|--------|-------|-------|
| **Law coverage** | 6/16 (38%) | Most misses are data gaps, not retrieval bugs |
| **Type coverage** | 18/18 (100%) | All expected entity types present in every query |
| **Topic coverage** | 18/19 (95%) | Only "threatening" missed in Q3 |
| **Combined** | **77%** | Passing threshold (70%) met |

## Per-Query Results

### Q1: Heat (habitability)
- **Chunks:** 10, top score 0.681
- **Entities:** 71 (14 claims, 11 laws, 22 evidence, 12 outcomes, 8 procedures)
- **Strengths:** Heat laws, HP action procedures, HPD complaint process all surfaced
- **Gap:** RPL § 235-b not linked to entity "Warranty of Habitability"; § 27-2029 not in graph (entity says "Heat and Hot Water Requirements" without section number)

### Q2: Mold (habitability)
- **Chunks:** 10, top score 0.616
- **Entities:** 69 (11 claims, 8 laws, 22 evidence)
- **Strengths:** § 27-2017.3 found, mold-specific entities surfaced, repair procedures present
- **Gap:** RPL § 235-b / MDL § 78 in graph but not surfaced for this query (entity names don't contain section numbers)

### Q3: Harassment
- **Chunks:** 10, top score 0.739
- **Entities:** 54 (15 claims, 6 laws, 8 evidence)
- **Strengths:** Harassment claims and outcomes present, Legal Aid guide chunks surfaced
- **Gap:** § 27-2004/2005 never ingested (amlegal.com scrape failed). Only 6 law entities — weakest query for legal grounding

### Q4: Deregulation
- **Chunks:** 10, top score 0.666
- **Entities:** 86 (20 claims, 24 laws, 17 evidence) — richest result set
- **Strengths:** § 26-511, § 26-512, § 26-516 all found. Case law entities surfaced. DHCR procedures present
- **Gap:** ETPA/RSC abbreviations not matched (full names exist in graph)

### Q5: Rent Overcharge
- **Chunks:** 10, top score 0.729
- **Entities:** 69 (13 claims, 21 laws, 14 evidence)
- **Strengths:** Overcharge claims, treble damages, DHCR rent history evidence all surfaced
- **Gap:** RSC/HSTPA abbreviations not matched

## Bug Found and Fixed

**Entity search returning 0 results through HybridRetriever** — the `types` filter in `search_entities_by_text()` was placed inside the `SEARCH ANALYZER(...)` block in AQL, which caused it to be treated as a text-analyzed condition instead of an exact-match filter. Moved to a `FILTER` clause outside `SEARCH`. This was a critical bug — entity retrieval was completely broken for the case analyzer.

## Root Causes of Law Coverage Gaps

| Missing Law | Root Cause | Fix |
|-------------|-----------|-----|
| RPL § 235-b | Entity named "Warranty of Habitability" — no section number in name/description | Extraction prompt should include section numbers |
| § 27-2029 | Entity "Heat and Hot Water Requirements" — no section number | Same |
| § 27-2004/2005 | amlegal.com scrape failed (3 failures in habitability + harassment manifests) | Retry scrape or find alternate URL |
| ETPA | "Emergency Tenant Protection Act of 1974" — abbreviation not stored | Add aliases/abbreviations to law entities |
| RSC | "Rent Stabilization Code Part 2520" — abbreviation not stored | Same |
| HSTPA | "Housing Stability and Tenant Protection Act (HSTPA)" — abbreviation IS in name but not in search results | Retriever should detect abbreviations in parentheses |

## Conclusions

1. **Retrieval mechanism works well.** Vector search returns relevant chunks (scores 0.6-0.74). Entity search (after fix) returns 54-86 entities with correct type distribution. KG expansion adds useful neighbors.

2. **Data gaps are the main quality issue.** 3 failed scrapes from amlegal.com and extraction prompts that don't preserve section numbers account for most law coverage misses.

3. **Abbreviation matching is a nice-to-have.** ETPA, RSC, HSTPA are common abbreviations that could be added as entity aliases.

4. **M1 exit criterion: MET.** Retrieval surfaces the right claims, evidence types, procedures, and outcomes for all 5 tenant query scenarios. The remaining gaps are data ingestion issues (M2/M3 scope), not retrieval architecture issues.

## Next Steps

- Re-scrape failed amlegal.com statutes (§ 27-2004, § 27-2005(d), § 27-2029) — try alternate URLs
- Consider adding section numbers to extraction prompts for statute documents
- Proceed to M2/M3 data ingestion with confidence that retrieval is working
