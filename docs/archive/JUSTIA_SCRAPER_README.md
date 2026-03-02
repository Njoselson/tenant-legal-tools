# Justia Case Law Scraper - Quick Start

## What's New

The system can now scrape and ingest NYC tenant law cases from Justia (law.justia.com) with automatic relevance filtering.

## Quick Start (3 Steps)

### 1. Create a seed file with Justia URLs

```bash
# Create data/my_cases.txt with one URL per line
cat > data/my_cases.txt << 'EOF'
https://law.justia.com/cases/new-york/other-courts/2025/2025-ny-slip-op-33306-u.html
EOF
```

**How to get URLs:**
- Search Justia: https://law.justia.com/cases/new-york/
- Use search terms: "rent stabilization", "eviction", "housing court", "habitability"
- Ask a search LLM (Perplexity/ChatGPT) for 20-30 relevant case URLs

### 2. Build manifest with filtering

```bash
python -m tenant_legal_guidance.scripts.build_manifest \
  --justia data/my_cases.txt \
  --output data/manifests/tenant_cases.jsonl \
  --filter-relevance \
  --include-stats
```

This will:
- Scrape each case from Justia
- Extract metadata (case name, court, date, full text)
- Filter for tenant law relevance
- Create a manifest file for ingestion

### 3. Ingest the cases

```bash
python -m tenant_legal_guidance.scripts.ingest \
  --manifest data/manifests/tenant_cases.jsonl \
  --deepseek-key $DEEPSEEK_API_KEY \
  --concurrency 2
```

Done! Cases are now in your knowledge graph.

## What Gets Filtered

### ✓ RELEVANT Cases (automatically included):
- Rent stabilization disputes
- Eviction proceedings (non-payment, holdover)
- Warranty of habitability claims
- Housing Court decisions
- Tenant harassment cases
- NYCHA/public housing matters

### ✗ NOT RELEVANT Cases (automatically excluded):
- Commercial lease disputes
- Condo/co-op matters (unless tenant-related)
- Real estate transactions
- Foreclosure proceedings
- Non-housing disputes

## Key Features

1. **Smart Filtering**: Two-stage filtering (keyword + optional LLM)
2. **Rate Limiting**: Respectful scraping (2 second delays)
3. **Error Recovery**: Automatic retries and detailed logging
4. **Metadata Extraction**: Case name, court, date, citations, full text
5. **Statistics**: Detailed reports on scraping and filtering results

## File Structure

```
tenant_legal_guidance/
├── services/
│   ├── justia_scraper.py           # Main scraper
│   └── case_relevance_filter.py    # Filtering logic
└── scripts/
    └── build_manifest.py            # Manifest builder (updated)

docs/
└── JUSTIA_SCRAPING_GUIDE.md         # Detailed documentation

data/
├── seed_urls.txt                    # Your input (create this)
└── manifests/
    └── justia_cases.jsonl           # Output manifest
```

## Examples

### Test the Scraper

```bash
# Quick test with example URL
python test_justia_scraper.py
```

### Build Manifest with LLM Filter

```bash
# More accurate but slower
python -m tenant_legal_guidance.scripts.build_manifest \
  --justia data/my_cases.txt \
  --output data/manifests/tenant_cases.jsonl \
  --filter-relevance \
  --use-llm-filter \
  --deepseek-key $DEEPSEEK_API_KEY \
  --include-stats
```

### Review Results

```bash
# Check statistics
cat data/manifests/tenant_cases_stats.json

# Preview manifest
head -5 data/manifests/tenant_cases.jsonl | jq
```

## Troubleshooting

### All cases filtered out
- Verify your seed URLs are actually tenant law cases
- Check the stats file to see why they were filtered
- Try `--use-llm-filter` for more nuanced classification

### Scraping failures
- Check network connectivity
- Verify URLs are valid Justia links
- Check logs: `tail -f logs/manifest_build.log`

### Need more cases
- Expand your seed list with more URLs
- Search Justia with different keywords
- Include cases from different years (2020-2025)

## Advanced Options

```bash
# All available options
python -m tenant_legal_guidance.scripts.build_manifest --help

Key options:
  --justia FILE               Seed URLs file
  --output FILE               Output manifest path
  --filter-relevance          Apply tenant law filtering
  --use-llm-filter           Use LLM for uncertain cases
  --deepseek-key KEY         DeepSeek API key
  --include-stats            Write statistics file
```

## Next Steps

1. **Generate seed list**: Use Justia search or ask a search LLM for 20-30 URLs
2. **Run manifest builder**: Filter for relevant tenant cases
3. **Review manifest**: Check that relevant cases passed filter
4. **Ingest**: Add to your knowledge graph
5. **Repeat**: Add more cases over time as you find them

## Full Documentation

See `docs/JUSTIA_SCRAPING_GUIDE.md` for:
- Detailed filtering logic
- Advanced usage patterns
- Batch processing
- Troubleshooting guide
- Integration strategies

## Need Help?

1. Run test: `python test_justia_scraper.py`
2. Check guide: `docs/JUSTIA_SCRAPING_GUIDE.md`
3. Review logs: `logs/` directory
4. Examine source: `tenant_legal_guidance/services/justia_scraper.py`


