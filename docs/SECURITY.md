# Security & Privacy

Security features, privacy compliance, and best practices for the Tenant Legal Guidance System.

## Table of Contents
- [Security Features](#security-features)
- [PII Anonymization](#pii-anonymization)
- [Privacy Compliance](#privacy-compliance)
- [Threat Model](#threat-model)
- [Security Best Practices](#security-best-practices)

## Security Features

### Input Validation

**Prompt Injection Detection:**
```python
from tenant_legal_guidance.services.security import detect_prompt_injection

if detect_prompt_injection(user_input):
    raise HTTPException(400, "Invalid input detected")
```

**Patterns detected:**
- SQL injection attempts
- JavaScript/XSS payloads
- Command injection
- LLM jailbreak attempts
- Unusual encoding (base64, hex)

**Sanitization:**
```python
from tenant_legal_guidance.services.security import sanitize_for_llm

safe_input = sanitize_for_llm(user_input)
```

**Sanitizes:**
- Removes dangerous characters
- Escapes special sequences
- Limits input length
- Normalizes whitespace

### Rate Limiting

**Per-IP limits:**
- 100 requests per minute (default)
- Configurable in `config.py`
- Returns 429 Too Many Requests when exceeded

**Implementation:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/analyze-case")
@limiter.limit("10/minute")
async def analyze_case(request: Request):
    ...
```

### Request Size Limits

**Maximum body size:** 10MB (configurable)

**Prevents:**
- DoS via large payloads
- Memory exhaustion
- Timeout attacks

### Authentication (Optional)

**Not enabled by default.** For production, add:

```python
from fastapi.security import HTTPBearer
from tenant_legal_guidance.services.auth import verify_token

security = HTTPBearer()

@app.post("/api/analyze-case")
async def analyze_case(token: str = Depends(security)):
    user = verify_token(token)
    ...
```

## PII Anonymization

### Overview

The system can automatically anonymize Personally Identifiable Information (PII) before processing or storage.

**Configurable in `.env`:**
```bash
ANONYMIZE_PII_ENABLED=true
ANONYMIZE_NAMES=true
ANONYMIZE_EMAILS=true
ANONYMIZE_PHONES=true
ANONYMIZE_ADDRESSES=true
ANONYMIZE_SSN=true
ANONYMIZE_DATES=true
ANONYMIZE_FINANCIAL=true
```

### What Gets Anonymized

| PII Type | Detection | Replacement |
|----------|-----------|-------------|
| **Names** | NER (spaCy) | `[PERSON_1]`, `[PERSON_2]` |
| **Emails** | Regex pattern | `[EMAIL]` |
| **Phones** | Regex pattern | `[PHONE]` |
| **Addresses** | NER + patterns | `[ADDRESS]` |
| **SSN** | Regex (XXX-XX-XXXX) | `[SSN]` |
| **Dates** | Date parser | `[DATE]` |
| **Financial** | Dollar amounts | `[AMOUNT]` |

### Example

**Before:**
```
My name is John Smith. I live at 123 Main St, New York, NY 10001.
My landlord owes me $1,500 in rent overcharge. You can reach me at
john.smith@email.com or 212-555-1234.
```

**After:**
```
My name is [PERSON_1]. I live at [ADDRESS].
My landlord owes me [AMOUNT] in rent overcharge. You can reach me at
[EMAIL] or [PHONE].
```

### Usage

```python
from tenant_legal_guidance.services.anonymization import anonymize_pii

anonymized = anonymize_pii(
    text=user_input,
    anonymize_names=True,
    anonymize_emails=True,
    anonymize_phones=True,
    anonymize_addresses=True
)
```

### Implementation Details

**Name detection:**
- Uses spaCy NER model (`en_core_web_lg`)
- Detects PERSON entities
- Maps to consistent IDs (`[PERSON_1]`, `[PERSON_2]`)

**Pattern matching:**
- Emails: RFC 5322 compliant regex
- Phones: US/international formats
- SSN: XXX-XX-XXXX pattern
- Addresses: Street, city, state, zip

**Preservation:**
- Legal terms NOT anonymized (e.g., "landlord", "tenant")
- Case names preserved for reference
- Dates in legal contexts may be kept

## Privacy Compliance

### Data Collection

**What we collect:**
- User case descriptions (anonymized if enabled)
- Search queries
- API usage logs
- Error logs

**What we DON'T collect:**
- IP addresses (not stored)
- User accounts (no auth system)
- Cookies or tracking
- Third-party analytics

### Data Storage

**ArangoDB:**
- Entities, relationships, sources
- PII anonymized before storage
- No user-specific data

**Qdrant:**
- Document chunks with embeddings
- Text anonymized before vectorization
- No personal identifiers

**SQLite Cache:**
- Analysis results
- Keyed by example ID (not user ID)
- Expires after TTL (24 hours default)

**Logs:**
- Request IDs (random UUIDs)
- Error messages (sanitized)
- No PII in logs

### Data Retention

| Data Type | Retention | Justification |
|-----------|-----------|---------------|
| Case analyses (cache) | 24 hours | Performance |
| Logs | 30 days | Debugging |
| Ingested documents | Permanent | Core knowledge |
| User queries | Not stored | Privacy |

### GDPR Compliance

**Right to erasure:**
```bash
# Delete cached analysis
curl -X DELETE http://localhost:8000/api/cache/{cache_key}

# Logs are auto-deleted after 30 days
```

**Data minimization:**
- Only collect what's necessary
- Anonymize by default
- No tracking or profiling

**Data portability:**
```bash
# Export knowledge graph
make build-manifest
# Result: data/manifests/sources.jsonl
```

## Threat Model

### Threats Addressed

| Threat | Mitigation | Status |
|--------|------------|--------|
| **SQL Injection** | Parameterized queries, input validation | ✅ Implemented |
| **XSS** | Input sanitization, CSP headers | ✅ Implemented |
| **Prompt Injection** | LLM input filtering, output validation | ✅ Implemented |
| **DoS** | Rate limiting, request size limits | ✅ Implemented |
| **PII Leakage** | Anonymization, log sanitization | ✅ Implemented |
| **SSRF** | URL validation, restricted hosts | ✅ Implemented |

### Threats NOT Addressed

| Threat | Recommendation |
|--------|---------------|
| **Authentication** | Implement JWT or OAuth2 |
| **Authorization** | Add role-based access control |
| **Network Security** | Deploy behind VPN or firewall |
| **Data Encryption** | Enable TLS for all connections |
| **Audit Logging** | Implement security event logging |

### Security Layers

```
┌─────────────────────────────────────┐
│ Reverse Proxy (Nginx)               │  ← HTTPS, rate limiting
│ - SSL/TLS termination               │
│ - Request filtering                 │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│ FastAPI Middleware                  │  ← Input validation
│ - Request size limits               │
│ - Rate limiting (SlowAPI)           │
│ - CORS configuration                │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│ Application Logic                   │  ← Sanitization
│ - Prompt injection detection        │
│ - PII anonymization                 │
│ - LLM output validation             │
└────────────┬────────────────────────┘
             ↓
┌─────────────────────────────────────┐
│ Database Layer                      │  ← Parameterized queries
│ - ArangoDB (AQL)                    │
│ - Qdrant (API)                      │
└─────────────────────────────────────┘
```

## Security Best Practices

### Production Deployment

**Required:**
1. ✅ Change default passwords
2. ✅ Enable HTTPS/SSL
3. ✅ Set up firewall rules
4. ✅ Enable PII anonymization
5. ✅ Configure rate limiting
6. ✅ Use secrets manager (not `.env`)
7. ✅ Enable log rotation
8. ✅ Set up monitoring/alerting

**Recommended:**
1. Add authentication/authorization
2. Implement audit logging
3. Enable WAF (Web Application Firewall)
4. Set up IDS/IPS
5. Regular security audits
6. Penetration testing

### Secret Management

**Development:**
```bash
# .env file (gitignored)
DEEPSEEK_API_KEY=sk-dev-key
```

**Production:**
```bash
# Use AWS Secrets Manager, HashiCorp Vault, etc.
export DEEPSEEK_API_KEY=$(aws secretsmanager get-secret-value ...)
```

**Never:**
- Commit secrets to Git
- Log secrets
- Include in error messages
- Send in response bodies

### Database Security

**ArangoDB:**
```bash
# Change default password
docker exec -it arangodb arango-secure-installation

# Restrict network access
# In docker-compose.yml, remove exposed ports
# Use internal Docker network only
```

**Qdrant:**
```bash
# Enable API key
QDRANT_API_KEY=your-secure-key

# Restrict collections
# Use collection-level access control
```

### LLM Security

**Input validation:**
- Limit input length (5000 chars max)
- Detect jailbreak attempts
- Sanitize special characters

**Output validation:**
- Filter sensitive data
- Validate JSON structure
- Check for hallucinations

**API Key security:**
- Rotate keys regularly
- Use separate keys for dev/prod
- Monitor usage/spend

### Logging Security

**Don't log:**
- API keys or passwords
- User PII
- Session tokens
- Full request/response bodies

**Do log:**
- Request IDs (UUIDs)
- Error types (not messages)
- Performance metrics
- Security events

**Example:**
```python
# ❌ Bad
logger.info(f"User {user.email} logged in")

# ✅ Good
logger.info(f"Login successful", extra={"request_id": request.id})
```

## Security Checklist

### Before Deployment

- [ ] Review all environment variables
- [ ] Change default passwords
- [ ] Enable HTTPS/SSL
- [ ] Configure firewall
- [ ] Enable PII anonymization
- [ ] Set up rate limiting
- [ ] Review CORS settings
- [ ] Enable security headers
- [ ] Set up monitoring
- [ ] Configure backups

### Regular Maintenance

- [ ] Update dependencies (monthly)
- [ ] Review logs for anomalies (weekly)
- [ ] Rotate API keys (quarterly)
- [ ] Test backup restoration (monthly)
- [ ] Review access logs (weekly)
- [ ] Check for CVEs (automated)

## Incident Response

### If Breach Detected

1. **Isolate:** Take system offline
2. **Investigate:** Review logs, identify scope
3. **Notify:** Inform affected users (if PII exposed)
4. **Fix:** Patch vulnerability
5. **Restore:** From clean backup
6. **Monitor:** Watch for re-infection

### If API Key Compromised

1. **Revoke:** Immediately revoke compromised key
2. **Rotate:** Generate new key
3. **Update:** Deploy new key to production
4. **Review:** Check usage logs for abuse
5. **Notify:** Alert DeepSeek support if needed

## Reporting Security Issues

**Email:** security@yourproject.com

**PGP Key:** (if available)

**Please include:**
- Description of vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

**Response time:** Within 48 hours

## Next Steps

- **Deploy securely:** See `DEPLOYMENT.md`
- **Monitor system:** Set up alerts
- **Regular audits:** Quarterly security reviews
- **Stay updated:** Subscribe to security mailing lists
