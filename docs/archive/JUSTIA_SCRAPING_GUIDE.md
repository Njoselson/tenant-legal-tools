# Justia Case Law Scraping Guide

## Overview

The system can now scrape and ingest tenant law cases from Justia (law.justia.com) with automatic relevance filtering.

## Features

1. **HTML Parsing**: Extracts case metadata and full opinion text from Justia pages
2. **Relevance Filtering**: Two-stage filtering (keyword + optional LLM) to identify tenant law cases
3. **Manifest Building**: Converts scraped cases to manifest format for ingestion
4. **Rate Limiting**: Respectful scraping with configurable delays
5. **Error Handling**: Robust error recovery and detailed logging

## Quick Start

### Step 1: Generate Seed URLs

Create a text file with Justia case URLs (one per line):

```bash
# data/seed_urls.txt
https://law.justia.com/cases/new-york/other-courts/2025/2025-ny-slip-op-33306-u.html
https://law.justia.com/cases/new-york/other-courts/2024/...
...
```

**How to Find Tenant Law Cases:**

#### Option A: Manual Search on Justia
1. Go to https://law.justia.com/cases/new-york/
2. Search for terms like:
   - "rent stabilization"
   - "eviction housing court"
   - "warranty habitability"
   - "tenant landlord new york"
   - "NYCHA"
3. Copy URLs from relevant results

#### Option B: Use Search LLM (Perplexity/ChatGPT)
Ask an LLM with web access:
```
"Find me 30 URLs from law.justia.com for New York tenant law cases 
from 2020-2025 covering rent stabilization, eviction, habitability, 
and housing court. Provide just the URLs."
```

#### Option C: Use Existing Databases
- Search NYS Unified Court System decisions
- Check Housing Court bulletins
- Review tenant advocacy newsletters for cited cases

### Step 2: Build Manifest from Seeds

Run the manifest builder with relevance filtering:

```bash
python -m tenant_legal_guidance.scripts.build_manifest \
  --justia data/seed_urls.txt \
  --output data/manifests/justia_cases.jsonl \
  --filter-relevance \
  --include-stats
```

**Options:**
- `--filter-relevance`: Apply keyword-based filtering (recommended)
- `--use-llm-filter`: Enable LLM-based filtering (slower, more accurate)
- `--deepseek-key KEY`: DeepSeek API key (required for LLM filter)
- `--include-stats`: Write statistics file

**Output:**
- `justia_cases.jsonl`: Manifest file with relevant cases
- `justia_cases_stats.json`: Statistics about scraping/filtering

### Step 3: Ingest Cases

Use the standard ingestion pipeline:

```bash
python -m tenant_legal_guidance.scripts.ingest \
  --manifest data/manifests/justia_cases.jsonl \
  --deepseek-key $DEEPSEEK_API_KEY \
  --concurrency 3 \
  --archive data/archive \
  --checkpoint data/justia_checkpoint.json
```

## Relevance Filtering

### Keyword-Based Filter (Fast)

The system automatically filters cases based on tenant law keywords:

**High-Priority Keywords** (90% confidence):
- rent stabilization, rent control, rent regulated
- eviction, non-payment proceeding, holdover
- warranty of habitability, habitability violations
- housing court, NYCHA, DHCR, HPD
- rent reduction, illegal eviction

**Medium-Priority Keywords** (60% confidence, need 2+ matches):
- tenant, landlord, lease, rental agreement
- repairs, maintenance, heat, hot water
- harassment, section 8, violations
- security deposit, overcharge

**Exclusion Patterns** (automatically rejected):
- commercial tenant, commercial lease
- condo, condominium, co-op
- foreclosure, mortgage, deed

### LLM-Based Filter (Accurate)

For uncertain cases (confidence < 0.7), the system can use LLM classification:

```bash
python -m tenant_legal_guidance.scripts.build_manifest \
  --justia data/seed_urls.txt \
  --output data/manifests/justia_cases.jsonl \
  --filter-relevance \
  --use-llm-filter \
  --deepseek-key $DEEPSEEK_API_KEY
```

The LLM analyzes:
- Case name and court
- Opinion excerpt (first 500 chars)
- Legal context and parties
- Procedural history indicators

## Example Workflow

### Complete End-to-End Example

```bash
# 1. Create seed file
cat > data/tenant_case_seeds.txt << EOF
https://law.justia.com/cases/new-york/other-courts/2025/2025-ny-slip-op-33306-u.html
EOF

# 2. Build manifest with filtering
python -m tenant_legal_guidance.scripts.build_manifest \
  --justia data/tenant_case_seeds.txt \
  --output data/manifests/tenant_cases.jsonl \
  --filter-relevance \
  --include-stats

# 3. Review stats
cat data/manifests/tenant_cases_stats.json

# 4. Ingest relevant cases
python -m tenant_legal_guidance.scripts.ingest \
  --manifest data/manifests/tenant_cases.jsonl \
  --deepseek-key $DEEPSEEK_API_KEY \
  --concurrency 2 \
  --checkpoint data/ingestion_checkpoint.json
```

## Monitoring and Debugging

### Check Scraping Logs

```bash
# View detailed logs
tail -f logs/ingestion.log | grep -i justia
```

### Test Single URL

```bash
# Quick test with one case
python test_justia_scraper.py
```

### Review Filter Results

The manifest builder shows real-time filtering:
```
✓ RELEVANT: Smith v ABC Realty (keyword, confidence: 0.90)
  Matched: rent stabilization, housing court, eviction
✗ NOT RELEVANT: Jones v XYZ Corp - commercial tenant dispute
```

## Metadata Extraction

For each case, the scraper extracts:

- **Case name**: "Landlord LLC v Tenant"
- **Court**: "NYC Housing Court", "Supreme Court", etc.
- **Decision date**: ISO format (YYYY-MM-DD)
- **Docket number**: "12345/2023"
- **Citation**: "2025 NY Slip Op 33306(U)"
- **Full opinion text**: Complete decision text
- **Judges**: Judge names when available

This metadata is stored in the manifest and used for:
- Entity extraction (case citations)
- Provenance tracking
- Search and filtering
- Legal analysis

## Tips for Building Seed Lists

### Focus on Relevant Courts

**High-value courts for tenant law:**
- NYC Housing Court (Civil Court Housing Part)
- Supreme Court (landlord-tenant matters)
- Appellate Division (precedent-setting cases)

**Lower priority:**
- Commercial courts (mostly business disputes)
- Family courts (usually not housing)
- Criminal courts (different jurisdiction)

### Date Range

- **Recent cases (2020-2025)**: Most relevant to current law
- **Landmark cases (pre-2020)**: Important precedents to include
- **Post-2019**: Rent law changes (HSTPA) make these critical

### Case Types to Prioritize

1. **Rent Stabilization**: RSL §26-504, overcharge, deregulation
2. **Eviction Defense**: Non-payment, holdover, good cause
3. **Habitability**: Warranty of habitability, repairs, HPD violations
4. **Harassment**: Tenant harassment, illegal evictions, lockouts
5. **NYCHA**: Public housing, Section 8, subsidy issues

### Search Strategies

**On Justia:**
```
site:law.justia.com "rent stabilization" "New York"
site:law.justia.com "housing court" eviction tenant
site:law.justia.com "warranty of habitability" landlord
```

**On Google:**
```
"housing court" tenant "2024" OR "2025" site:law.justia.com
"rent stabilization law" NYC site:law.justia.com
```

## Troubleshooting

### No Cases Pass Filter

**Problem**: All cases filtered as not relevant

**Solutions:**
1. Review seed URLs - ensure they're actually tenant cases
2. Check case text extraction - verify full text is captured
3. Try `--use-llm-filter` for more nuanced classification
4. Examine filter logs to see what keywords were checked

### Scraping Failures

**Problem**: Cases fail to scrape

**Solutions:**
1. Check network connectivity
2. Verify URLs are valid and accessible
3. Increase rate limit: modify `rate_limit_seconds` in scraper
4. Check for Justia site changes (HTML structure)

### Too Many False Positives

**Problem**: Non-tenant cases passing filter

**Solutions:**
1. Review matched keywords in logs
2. Add exclusion patterns to filter
3. Enable LLM filter for second-stage review
4. Manually review manifest before ingestion

### Rate Limiting / Blocking

**Problem**: Justia blocks requests

**Solutions:**
1. Increase rate limit (currently 2 seconds)
2. Use smaller batches
3. Run during off-peak hours
4. Add random delays between requests

## Advanced Usage

### Custom Keyword Lists

Edit `tenant_legal_guidance/services/case_relevance_filter.py`:

```python
HIGH_PRIORITY_KEYWORDS = {
    # Add your custom keywords
    "my_custom_term",
    ...
}
```

### Batch Processing

For large seed lists (100+ URLs):

```bash
# Split into smaller batches
split -l 20 data/large_seed_list.txt data/batch_

# Process each batch
for batch in data/batch_*; do
  python -m tenant_legal_guidance.scripts.build_manifest \
    --justia $batch \
    --output data/manifests/$(basename $batch).jsonl \
    --filter-relevance
done

# Combine manifests
cat data/manifests/batch_*.jsonl > data/manifests/combined.jsonl
```

### Integration with Other Sources

Combine Justia cases with other sources:

```bash
# Build Justia manifest
python -m tenant_legal_guidance.scripts.build_manifest \
  --justia data/justia_seeds.txt \
  --output data/manifests/justia.jsonl

# Combine with existing manifest
cat data/manifests/sources.jsonl data/manifests/justia.jsonl \
  > data/manifests/all_sources.jsonl

# Ingest combined
python -m tenant_legal_guidance.scripts.ingest \
  --manifest data/manifests/all_sources.jsonl \
  --deepseek-key $DEEPSEEK_API_KEY
```

## Future Enhancements

Not yet implemented (future phases):

1. **NYSCEF Integration**: Scrape court filings from NYSCEF
2. **Landlord-Based Search**: Track cases by known landlord entities
3. **Citation Crawling**: Follow case citations to discover related cases
4. **Automated Discovery**: Periodic search for new cases
5. **Appellate Tracking**: Monitor appeals and updates to ingested cases

## Support

For issues or questions:
1. Check logs in `logs/` directory
2. Run test script: `python test_justia_scraper.py`
3. Review this guide's troubleshooting section
4. Examine source code in `tenant_legal_guidance/services/justia_scraper.py`


