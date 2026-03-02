# Data Acquisition Strategy: Historical Case Data & Court Records

**Date**: 2025-01-27  
**Feature**: 002-canonical-legal-library

## Executive Summary

**Key Finding**: **NO PUBLIC APIs** exist for bulk historical case data. All data acquisition requires **web scraping, manual curation, or FOIL requests**. This document outlines specific, actionable strategies for each data source.

## Data Source Inventory

### ✅ Available via Web Scraping (Implemented/Possible)

#### 1. Justia.com - Case Law Database
**Status**: ✅ **IMPLEMENTED**  
**Method**: Web scraping  
**Capabilities**:
- **Search**: Keyword search with filters (state, court, date range)
- **Historical Coverage**: Cases from 1900s-present
- **Update Frequency**: Regular updates as cases are published
- **Rate Limiting**: 2 seconds between requests (respectful)
- **Limitations**: Only published court opinions, not all filings
- **Current Implementation**: `JustiaScraper` class exists, can search and scrape cases

**What We Can Get**:
- Published court opinions (NYC Housing Court, Civil Court, etc.)
- Metadata: case name, court, date, docket number, citation
- Full opinion text
- Historical cases going back decades

**Strategy**:
- ✅ Use existing `JustiaScraper.search_cases()` to discover cases
- ✅ Scrape individual case pages for full text
- ✅ Export to manifest for ingestion

---

#### 2. NYC Administrative Code (readthedocs.io)
**Status**: ✅ **IMPLEMENTABLE**  
**Method**: Web scraping (ReadTheDocs HTML)  
**Capabilities**:
- **Structure**: Well-organized documentation site
- **Coverage**: All NYC statutes (Title 26 = Housing and Buildings)
- **Update Frequency**: Updated when laws change
- **No Rate Limits**: ReadTheDocs is permissive

**What We Can Get**:
- All NYC Administrative Code sections
- Title 26 (Housing and Buildings) - primary tenant-landlord code
- Other relevant titles (if needed)
- Metadata: title, chapter, section numbers

**Strategy**:
- Browse/index ReadTheDocs navigation structure
- Extract all Title 26 section URLs
- Parse HTML to extract section text
- Export to manifest

---

### ⚠️ Partially Available via Web Scraping (Complex)

#### 3. NYSCEF (New York State Courts Electronic Filing)
**Status**: ⚠️ **RESEARCH NEEDED**  
**Method**: Web scraping (form-based search, likely requires Selenium)  
**Capabilities**:
- **URL**: `https://iapps-train.courts.state.ny.us/nyscef/CaseSearch` (training site)
- **Coverage**: Electronically filed Supreme Court cases
- **Access**: Guest access available (may require registration)
- **Limitations**: Only e-filed cases, not all cases are e-filed

**What We Can Get** (to be verified):
- Case filings and documents
- Docket information
- Court orders and decisions
- Metadata: docket numbers, filing dates, case names

**Challenges**:
- Form-based interface (POST requests or JavaScript)
- May require authentication/registration
- Complex HTML structure to parse
- Rate limiting unknown (likely restrictive)
- Training site may differ from production

**Strategy**:
1. **Manual Inspection**: Test the actual site, document form structure
2. **Proof of Concept**: Build test scraper for single search
3. **Implement**: Form submission + result parsing
4. **Legal Review**: Verify ToS allows automated access

---

#### 4. eCourts / WebCivil (NY Unified Court System)
**Status**: ⚠️ **MANUAL SEARCH ONLY**  
**Method**: Manual search or targeted scraping  
**URLs**:
- WebCivil Local: City courts, NYC Civil Court (including Housing Court)
- WebCivil Supreme: County Supreme Courts
- WebCrims: Criminal cases (not relevant for tenant law)

**Capabilities**:
- **Search**: By party name or index number
- **Coverage**: Current and disposed cases
- **Historical Limitation**: Housing court cases leave system ~2 weeks after disposition

**What We Can Get**:
- Current and recent Housing Court cases
- Case status and basic metadata
- **CANNOT GET**: Historical Housing Court cases (>2 weeks old)

**Challenges**:
- No bulk download capability
- No API
- Requires individual case searches
- Historical data not available online

**Strategy**:
- **Limited Value**: Only useful for current/recent cases
- **Alternative**: Use Justia for historical published opinions
- **For Historical Data**: See FOIL Request section below

---

### ❌ Not Available Online (Requires FOIL/Manual Requests)

#### 5. Historical Housing Court Records
**Status**: ❌ **NOT AVAILABLE ONLINE**  
**Reason**: Housing court cases are removed from eCourts ~2 weeks after disposition

**What We Need**:
- Historical Housing Court decisions and orders
- Precedent cases from Housing Court
- Landmark tenant law decisions

**How to Get**:
1. **FOIL Request**: File Freedom of Information Law request with court clerk
   - Specify date ranges, case types, courts
   - May require fees for copying
   - Delivery may be slow (weeks to months)
2. **Court Clerk Contact**: Direct request to specific Housing Court
   - Kings County Housing Court (Brooklyn)
   - Bronx Housing Court
   - Manhattan Housing Court, etc.
3. **Case-by-Case**: Search eCourts for current cases, save before they expire

**Strategy**:
- **Short-term**: Focus on Justia (published opinions)
- **Long-term**: File FOIL requests for specific historical periods/case types
- **Manual Curation**: Collect known landmark cases manually

---

#### 6. NY State Law Reporting Bureau - Official Reports
**Status**: ⚠️ **PUBLISHED DECISIONS ONLY**  
**URL**: `https://nycourts.gov/reporter/`

**What's Available**:
- Official Reports of NY State Court Decisions
- Appellate Division Reports
- Court of Appeals decisions
- Selected trial court decisions

**What's NOT Available**:
- Unpublished decisions
- Trial court decisions not selected for publication
- Most Housing Court decisions (rarely published)

**How to Get**:
- Published volumes are available
- May need to purchase PDF volumes
- Some may be online in searchable format

**Strategy**:
- **Low Priority**: Justia already has most published cases
- **Gap Filling**: Use if Justia is missing specific published cases

---

### ✅ Alternative Sources (Curated Databases)

#### 7. CourtListener / Casetext / Other Legal Databases
**Status**: ⚠️ **MAY REQUIRE SUBSCRIPTION**  
**Sources**:
- CourtListener (free, limited coverage)
- Casetext (subscription required)
- Westlaw/Lexis (expensive subscriptions)
- Google Scholar (free, limited coverage)

**What We Can Get**:
- Some cases not on Justia
- Additional metadata and citations
- Cross-referenced cases

**Strategy**:
- **Research**: Check if free APIs available (CourtListener has API)
- **Evaluate**: Cost vs. value of subscription services
- **Defer**: Focus on free sources first (Justia)

---

## Specific Acquisition Strategies by Data Type

### A. Historical Case Data (Past 5-10 Years)

**Primary Strategy: Justia.com**
- ✅ Use existing scraper to search by keywords
- ✅ Filter by date range (e.g., 2015-2025)
- ✅ Focus on NYC Housing Court, Civil Court, Appellate Division
- ✅ Estimated: 500-2000 relevant cases available

**Gap Filling**:
- **FOIL Requests**: For specific landmark cases not on Justia
- **Manual Collection**: Known important cases (e.g., 756 Liberty case)

**Timeline**: 
- Justia scraping: 2-4 weeks (respectful rate limiting)
- FOIL requests: 2-6 months (government response time)

---

### B. Current/Recent Housing Court Cases

**Strategy 1: eCourts WebCivil** (Limited)
- Search for current cases by keywords
- Save results before they expire (~2 weeks)
- **Limitation**: Cannot get historical data

**Strategy 2: NYSCEF** (If Implementable)
- Search for e-filed Housing Court cases
- Extract documents and orders
- **Limitation**: Only e-filed cases (not all cases)

**Strategy 3: Justia** (Published Only)
- Published Housing Court decisions
- **Limitation**: Many Housing Court decisions are not published

---

### C. State Court Data (Appellate, Supreme)

**Strategy: Justia.com** ✅
- Comprehensive coverage of published decisions
- Appellate Division decisions
- Court of Appeals decisions
- Some Supreme Court decisions

**Additional**: 
- NY State Law Reporting Bureau (if gaps in Justia)

---

### D. Statutes and Regulations

**Strategy: Web Scraping** ✅
1. **NYC Administrative Code**: ReadTheDocs.io (implementable)
2. **NY State Laws**: NYS Legislature website (`nysenate.gov`)
   - Real Property Law (RPL)
   - Multiple Dwelling Law (MDL)
   - RPAPL (Real Property Actions and Proceedings Law)
3. **DHCR Regulations**: DHCR website (future enhancement)
4. **HPD Housing Maintenance Code**: HPD website (future enhancement)

**Priority**: 
1. NYC Admin Code (Title 26) - **HIGH PRIORITY**
2. NYS RPL §235-b (Warranty of Habitability) - **HIGH PRIORITY**
3. Other relevant sections - Medium priority

---

## Implementation Roadmap

### Phase 1: Immediate (Already Available)
- ✅ **Justia.com**: Use existing scraper for case discovery and scraping
- **Scope**: Published court opinions, historical cases
- **Coverage**: Thousands of cases, decades of history

### Phase 2: Next 2-4 Weeks
- 🔨 **NYC Admin Code**: Implement ReadTheDocs scraper
- **Scope**: All Title 26 sections, other relevant titles
- **Coverage**: Complete NYC housing statutes

### Phase 3: Next 1-2 Months
- 🔨 **NYSCEF**: Research and implement (if feasible)
- **Scope**: E-filed Supreme Court cases
- **Coverage**: Recent cases with documents

### Phase 4: Ongoing
- 📋 **eCourts Monitoring**: Manual/automated monitoring of current cases
- **Scope**: Current Housing Court cases before they expire
- **Coverage**: Recent cases only

### Phase 5: Long-term (3-6 Months)
- 📋 **FOIL Requests**: File requests for specific historical data
- **Scope**: Landmark cases, specific time periods
- **Coverage**: Depends on request specifics

---

## Data Acquisition Methods Matrix

| Source | Method | Historical? | Bulk? | Automated? | Cost | Status |
|--------|--------|-------------|-------|------------|------|--------|
| Justia.com | Web Scraping | ✅ Yes | ✅ Yes | ✅ Yes | Free | ✅ Implemented |
| NYC Admin Code | Web Scraping | ✅ Yes | ✅ Yes | ✅ Yes | Free | 🔨 Planned |
| NYSCEF | Web Scraping | ⚠️ Recent | ⚠️ Limited | ⚠️ Complex | Free | ⚠️ Research |
| eCourts | Manual Search | ❌ No | ❌ No | ❌ No | Free | ⚠️ Limited Value |
| Housing Court Historical | FOIL Request | ✅ Yes | ⚠️ Per Request | ❌ No | Fees | 📋 Long-term |
| NYS Legislature | Web Scraping | ✅ Yes | ✅ Yes | ✅ Yes | Free | 📋 Future |
| DHCR/HPD | Web Scraping | ⚠️ Varies | ⚠️ Limited | ⚠️ Possible | Free | 📋 Future |

**Legend**:
- ✅ = Available/Implemented
- 🔨 = In Progress/Planned
- ⚠️ = Limited/Complex
- ❌ = Not Available
- 📋 = Future/Long-term

---

## Recommendations

### Immediate Actions (Next 2 Weeks)
1. ✅ **Use Justia.com scraper** for historical case discovery
   - Search keywords: "rent stabilization", "eviction", "habitability"
   - Date range: 2015-2025 (or broader if needed)
   - Estimated: 500-2000 relevant cases

2. 🔨 **Implement NYC Admin Code scraper**
   - Focus on Title 26 (Housing and Buildings)
   - All sections in a few days of work

3. ⚠️ **Research NYSCEF** feasibility
   - Manual test of actual site
   - Document form structure
   - Determine if implementation is worth it

### Medium-term (1-3 Months)
4. 📋 **File FOIL Requests** for specific historical data
   - Identify gap cases not on Justia
   - Request specific time periods/courts
   - Plan for 2-6 month response time

5. 📋 **Monitor eCourts** for current cases
   - Automated or manual monitoring
   - Save cases before they expire

### Long-term (3-6 Months)
6. 📋 **Evaluate subscription services** if needed
   - CourtListener API (if free tier sufficient)
   - Other databases if gaps remain

---

## Specific Answers to Your Questions

### Q: How do we get historical case data?
**A**: 
- **Primary**: Justia.com web scraping (already implemented) - covers published cases from 1900s-present
- **Gap Filling**: FOIL requests for specific landmark cases not on Justia
- **Timeline**: Justia scraping can start immediately; FOIL requests take months

### Q: How do we get housing court data?
**A**:
- **Published Decisions**: Justia.com (published Housing Court opinions)
- **Recent Cases**: eCourts WebCivil (expires after ~2 weeks)
- **Historical Cases**: NOT available online - requires FOIL requests or manual collection
- **E-filed Cases**: NYSCEF (if we can implement scraper)

### Q: How do we get state court data?
**A**:
- **Appellate/Published**: Justia.com (comprehensive coverage)
- **Trial Court**: Justia has some; eCourts has current cases only
- **Historical**: Justia for published; FOIL for unpublished

### Q: Do we get an API?
**A**: 
- **NO** - No public APIs for NYS courts, Housing Court, or eCourts
- **Exception**: CourtListener may have free API (research needed)
- **Strategy**: Web scraping is the only viable automated method

### Q: Do we scrape everything?
**A**:
- **Justia.com**: Yes, scrape search results for relevant cases
- **NYC Admin Code**: Yes, scrape all Title 26 sections
- **NYSCEF**: Research feasibility first (complex form-based interface)
- **eCourts**: Limited value (no historical data), skip for now
- **NOT scraping**: Everything - only targeted, relevant legal documents

---

## Scope Clarification

### What We ARE Building (Spec 002)
1. **Search Tools**: CLI tools to search Justia, NYSCEF (if feasible), NYC Admin Code
2. **Manifest Management**: Add URLs with validation
3. **Curated Ingestion**: Manual curation → manifest → ingestion (not bulk scraping everything)

### What We ARE NOT Building
1. **Bulk Historical Archive**: Not scraping all historical cases automatically
2. **Complete Court Database**: Not building a complete NYS court database
3. **Real-time Monitoring**: Not monitoring all courts in real-time

### The Curation Model
- **Manual Discovery**: Use search tools to find relevant cases
- **Selective Addition**: Add specific cases to manifest
- **Controlled Ingestion**: Ingest curated manifest entries
- **Quality over Quantity**: Focus on relevant, high-quality cases

---

## Conclusion

**Bottom Line**:
1. ✅ **Justia.com** is our primary source for historical published cases (implemented)
2. 🔨 **NYC Admin Code** is easily scrapable (next implementation)
3. ⚠️ **NYSCEF** may be possible but needs research (complex)
4. ❌ **Historical Housing Court** requires FOIL requests (long-term)
5. 📋 **Everything else** is manual curation or future enhancement

**The Right Track**:
- ✅ Focus on free, scrapable sources (Justia, NYC Admin Code)
- ✅ Manual curation model (search → select → add to manifest → ingest)
- ✅ Quality over quantity (curated library, not bulk archive)
- ✅ Fill gaps with FOIL requests for specific important cases

This aligns with Spec 002's "manifest curation tools" approach - not bulk scraping everything, but making it easy to discover and add relevant legal documents to the library.

