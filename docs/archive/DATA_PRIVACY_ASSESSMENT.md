# Data Privacy & PII Risk Assessment

**Date**: 2025-01-27  
**Status**: ⚠️ **MODERATE-HIGH RISK** - PII stored without anonymization

## Executive Summary

The application stores potentially sensitive personal data in multiple databases without anonymization. Case law documents contain real names (parties, addresses), and user case descriptions may include PII. Currently, **no anonymization** is applied before storage.

## Data Storage Analysis

### What Gets Stored

#### 1. **Document Ingestion (ArangoDB + Qdrant)**

**Storage Locations:**
- `text_blobs` collection (ArangoDB) - Full document text
- `legal_chunks` collection (Qdrant) - Chunked text with embeddings
- `entities` collection (ArangoDB) - Extracted entities including:
  - Case names: `"756 Liberty Realty LLC v Garcia"`
  - Party names: `parties: {"plaintiff": [...], "defendant": [...]}`
  - Case metadata: docket numbers, courts, decision dates
  - Quotations: Direct quotes from documents containing names

**PII Risk**: **HIGH**
- Court case documents contain real names of parties
- Case names include landlord/tenant names: `"Landlord Corp v John Doe"`
- Addresses may appear in case documents
- Full text stored in Qdrant with no redaction

#### 2. **User Case Analysis (SQLite Cache)**

**Storage Location:**
- `data/analysis_cache.sqlite` - Cached analysis results

**What's Cached:**
- User's case description text (`case_text`)
- Analysis results (summary, recommendations, etc.)
- Cache key includes case text (hashed but original text stored in cache entry)

**PII Risk**: **HIGH**
- User case descriptions may include:
  - Names (tenant, landlord, neighbors)
  - Addresses (apartment numbers, building addresses)
  - Phone numbers, email addresses
  - Specific dates and events
  - Financial information (rent amounts, damages)

**Retention**: Cache has TTL expiration (default 1 hour), but data remains until expiration.

#### 3. **Entity Extraction (ArangoDB)**

**Storage:**
- `entities` collection stores extracted entities from user cases (if entity extraction runs on user input)
- Currently unclear if user case text triggers entity ingestion

**PII Risk**: **MEDIUM**
- If user cases are processed for entity extraction, names/addresses could be stored as entities

### Data Types Identified

Based on codebase analysis:

1. **Court Case Data** (Public but sensitive):
   - Case names with real party names
   - Plaintiff/defendant names
   - Addresses (if mentioned in cases)
   - Docket numbers

2. **User Input Data**:
   - Case descriptions (free-form text)
   - Evidence lists
   - Situation descriptions

3. **Extracted Entities**:
   - Tenant names (if extracted from cases)
   - Building addresses
   - Specific dates and locations

## Security Risks

### Risk 1: Database Breach

**Scenario**: Attacker gains access to databases (ArangoDB, Qdrant, SQLite)

**Impact**:
- **HIGH**: Full case documents with party names accessible
- **HIGH**: User case descriptions with PII accessible
- **MEDIUM**: Cache may contain recent user submissions

**Attack Vectors**:
- Unauthorized database access
- SQL injection (mitigated but not eliminated)
- Exposed database credentials
- Backup files containing PII

### Risk 2: Data Exfiltration via API

**Scenario**: Attacker uses API to extract stored data

**Current Protections**:
- ✅ Rate limiting (re-enabled)
- ✅ Input validation (partial)
- ❌ No access controls on cached data
- ❌ No data redaction in responses

**Vulnerability**: 
- Cache may be accessible if cache keys are predictable
- Entity queries may return names/addresses from stored data

### Risk 3: LLM Data Leakage

**Scenario**: User case text sent to external LLM (DeepSeek API)

**Impact**:
- **MEDIUM**: Third-party service processes PII
- User has no control over third-party data retention
- Potential for data exposure at LLM provider

**Current State**:
- Case text is sanitized but **not anonymized**
- Full user input sent to DeepSeek API
- No data use agreement visible for external API

## Current Protections

### ✅ Implemented
1. **Input sanitization** - Removes injection patterns (not PII)
2. **Rate limiting** - Reduces bulk data extraction
3. **Request size limits** - Prevents extremely large submissions
4. **Cache TTL** - Limits retention time (default 1 hour)

### ❌ Missing
1. **No anonymization** - Names, addresses stored as-is
2. **No encryption at rest** - Databases store plaintext
3. **No access controls** - No authentication/authorization for data access
4. **No data redaction** - Full text stored including PII
5. **No audit logging** - No tracking of who accesses what data
6. **No data retention policy** - No automatic deletion of old data

## Recommendations

### Immediate (High Priority)

#### 1. **Implement PII Anonymization**

**For User Case Text:**
```python
def anonymize_case_text(text: str) -> str:
    """Anonymize PII in case text before storage/processing."""
    # Replace names with placeholders
    text = replace_names(text, "[TENANT]", "[LANDLORD]", "[NEIGHBOR]")
    # Replace addresses
    text = replace_addresses(text, "[ADDRESS]")
    # Replace phone/email
    text = replace_contact_info(text, "[PHONE]", "[EMAIL]")
    # Replace specific dates (keep relative timing)
    text = anonymize_dates(text)
    return text
```

**For Document Ingestion:**
- Option A: **Anonymize before storage** - Replace party names with placeholders
- Option B: **Flag PII fields** - Store with metadata indicating PII presence
- Option C: **Separate PII store** - Store PII separately with encryption, only link IDs

**Recommendation**: **Option A for user input, Option B for public case law**

#### 2. **Add Data Encryption**

- Enable encryption at rest for all databases
- Encrypt sensitive fields (names, addresses) separately
- Use field-level encryption for PII

#### 3. **Implement Access Controls**

- Add authentication for database access
- Implement row-level security if supported
- Add API authentication for data access endpoints

#### 4. **Add Audit Logging**

- Log all database access
- Log all API requests with case text
- Track data access patterns

### Short-term (Medium Priority)

#### 5. **Data Retention Policy**

- Auto-delete cache entries after TTL
- Archive old case law documents (if needed)
- Implement data lifecycle management

#### 6. **PII Detection & Flagging**

- Automatically detect PII patterns in input
- Flag documents containing PII
- Warn users before submission

#### 7. **Data Minimization**

- Don't store full user case text if not needed
- Store only extracted entities/relationships
- Use hashes instead of full text where possible

### Long-term (Lower Priority)

#### 8. **Differential Privacy**

- Add noise to queries
- Limit query result precision
- Implement privacy-preserving analytics

#### 9. **Compliance**

- GDPR compliance (if serving EU users)
- CCPA compliance (if serving CA users)
- Legal review of data handling practices

## Implementation Priority

### Phase 1: Critical (Do First)
1. ✅ Add PII anonymization to user case input
2. ✅ Add encryption at rest
3. ✅ Add access controls

### Phase 2: Important (Do Next)
4. Add PII detection/warning
5. Add audit logging
6. Review data retention policies

### Phase 3: Enhancement (Later)
7. Differential privacy
8. Compliance review
9. Advanced anonymization techniques

## Code Changes Needed

### 1. Add Anonymization Service

```python
# tenant_legal_guidance/services/anonymization.py
def anonymize_pii(text: str) -> str:
    """Anonymize PII in text before storage."""
    # Name detection and replacement
    # Address detection and replacement
    # Contact info replacement
    # Date anonymization
    pass
```

### 2. Update Case Analysis Endpoint

```python
@router.post("/api/analyze-case")
async def analyze_case(request: CaseAnalysisRequest, ...):
    # Anonymize before processing
    anonymized_text = anonymize_pii(request.case_text)
    # Store anonymized version in cache
    # Process anonymized text
```

### 3. Update Document Processor

```python
async def ingest_document(self, text: str, ...):
    # For case law: Flag PII but keep original (public record)
    # For user documents: Anonymize before storage
    if metadata.source_type == SourceType.INTERNAL:
        text = anonymize_pii(text)
```

## Questions to Resolve

1. **Public Case Law**: Should case law party names be anonymized?
   - **A**: Yes - Anonymize all names
   - **B**: No - Case law is public record, keep as-is
   - **C**: Flag but don't anonymize - Mark fields as PII

2. **User Case Text**: Should user case descriptions be stored at all?
   - **A**: Don't store - Process only, no persistence
   - **B**: Store anonymized - Remove PII before storage
   - **C**: Store with encryption - Keep PII but encrypt

3. **Cache Duration**: What's appropriate TTL?
   - **A**: Very short (15 minutes) - Minimize exposure
   - **B**: Current (1 hour) - Balance usability/risk
   - **C**: Configurable - Let users choose

4. **Entity Storage**: Should extracted entities from user cases be stored?
   - **A**: Yes - Needed for knowledge graph
   - **B**: No - Only process, don't store
   - **C**: Store anonymized - Remove names/addresses

## Conclusion

**Current Risk Level**: 🔴 **HIGH**

The application stores PII in multiple locations without anonymization. A database breach could expose:
- User case descriptions with personal details
- Court case documents with party names
- Extracted entities containing names/addresses

**Recommended Action**: Implement anonymization for user input **before** production deployment.

