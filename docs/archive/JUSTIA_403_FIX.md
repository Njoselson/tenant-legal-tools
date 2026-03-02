# Justia 403 Forbidden Error - Analysis & Solutions

## Problem

Justia.com is blocking requests after ~48-50 successful scrapes with `403 Forbidden` errors. This is anti-bot protection.

## Why This Happens

1. **Rate Limiting Detection**: Even with 2-second delays, scraping 100 cases in ~4 minutes triggers Justia's rate limiting
2. **Pattern Detection**: Making many sequential requests from the same IP/user agent looks like a bot
3. **No Cookie/Session**: Missing session cookies that a real browser would have
4. **Request Fingerprinting**: Headers alone aren't enough - Justia can detect automated behavior

## Current Status

Your first run succeeded because it was likely the first batch. The second run got blocked because:
- Your IP/session was flagged from the first run
- Justia has a cooldown period after detecting automated scraping

## Solutions

### Option 1: Wait and Resume (Quick Fix)

Wait 10-30 minutes, then resume from where it failed:

```bash
# The manifest file from first run has 6 cases
# Wait a bit, then continue with remaining cases
```

### Option 2: Increase Rate Limiting (Recommended)

Slow down significantly - 5-10 seconds between requests:

```python
# In justia_scraper.py, increase default rate limit:
JustiaScraper(rate_limit_seconds=5.0)  # or 10.0
```

Or use longer delays in build_manifest:

```bash
# Would need to modify the script to accept rate_limit parameter
# Or edit justia_scraper.py directly
```

### Option 3: Use Proxy Rotation

Use rotating proxies to avoid IP-based blocking (complex, requires proxy service).

### Option 4: Batch Processing

Break into smaller batches (10-20 cases at a time) with long pauses between:

```bash
# Run with max-results 20, wait 10 min, run again
python -m tenant_legal_guidance.scripts.build_manifest \
  --justia-search \
  --keywords "rent stabilization" \
  --max-results 20 \
  --output data/manifests/batch1.jsonl
# Wait 10 minutes
# Run again for batch 2, etc.
```

### Option 5: Use LLM Filter Earlier

Instead of scraping then filtering, search with more specific terms that return fewer, more relevant results (but this is limited by Justia's search capabilities).

### Option 6: Accept Lower Volume

Since you got 6 relevant cases from the first 48 scraped, you could:
1. Use those 6 cases
2. Manually browse Justia and copy case URLs
3. Create a smaller, curated manifest manually

## Immediate Action

**For now**: Use the 6 cases you already have! They're in `data/manifests/justia_100_cases.jsonl` (from first run) or `data/manifests/chtu_cases.jsonl` (if it exists).

Check what you have:
```bash
wc -l data/manifests/justia_100_cases.jsonl
wc -l data/manifests/chtu_cases.jsonl 2>/dev/null || echo "File not created yet"
```

## Long-term Solution

1. **Implement exponential backoff** on 403 errors
2. **Add random delays** (jitter) to make requests less predictable  
3. **Resume capability** to continue from where it failed
4. **Better error handling** to skip blocked cases and continue
5. **Respect robots.txt** and add delays after seeing 403

## Quick Code Fix (Add to justia_scraper.py)

Add exponential backoff for 403 errors:

```python
def fetch(self, url: str, retry_count: int = 0) -> Optional[str]:
    """Fetch HTML with retry on 403."""
    self._rate_limit()
    
    try:
        response = self.session.get(url, timeout=30)
        
        if response.status_code == 403:
            if retry_count < 3:
                wait_time = (2 ** retry_count) * 10  # 10s, 20s, 40s
                self.logger.warning(f"403 Forbidden, waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                return self.fetch(url, retry_count + 1)
            else:
                self.logger.error(f"403 Forbidden after {retry_count} retries - IP may be blocked")
                return None
                
        response.raise_for_status()
        return response.text
    except Exception as e:
        # ... existing error handling
```

