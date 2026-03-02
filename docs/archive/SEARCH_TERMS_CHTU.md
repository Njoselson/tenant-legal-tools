# Top 10 Search Terms from Crown Heights Tenant Union Resources

Based on the CHTU resource directory, here are the best search terms for finding relevant NYC tenant legal cases:

## Recommended Search Terms

### 1. **"rent stabilization" "good cause eviction"**
   - **Why**: Good Cause Eviction protection for rent-stabilized tenants
   - **Case types**: Eviction defense, lease renewals, harassment

### 2. **"HP action" "repairs" "housing part"**
   - **Why**: HP (Housing Part) actions are the primary way tenants sue for repairs
   - **Case types**: Warranty of habitability, repair orders, HPD violations

### 3. **"rent abatement" "repairs" "nonpayment"**
   - **Why**: Tenants can get rent reductions for repair issues
   - **Case types**: Rent reduction orders, DHCR complaints, repair disputes

### 4. **"tenant harassment" "NYC" "HSTPA"**
   - **Why**: Housing Stability and Tenant Protection Act of 2019 strengthened harassment protections
   - **Case types**: Harassment claims, landlord conduct, construction harassment

### 5. **"rent stabilized" "succession rights"**
   - **Why**: Family members have rights to continue tenancy after primary tenant
   - **Case types**: Succession disputes, family member eviction defenses

### 6. **"Major Capital Improvement" "MCI" "rent stabilized"**
   - **Why**: MCIs can improperly increase rent-stabilized rents
   - **Case types**: MCI challenges, rent overcharge, deregulation attempts

### 7. **"DHCR" "rent reduction" "services"**
   - **Why**: DHCR handles rent reduction orders for service reductions
   - **Case types**: Rent reduction applications, service reduction complaints

### 8. **"warranty of habitability" "heat" "repairs"**
   - **Why**: Fundamental tenant right to habitable conditions
   - **Case types**: Heat cases, repair disputes, habitability claims

### 9. **"rent history" "rent overcharge" "rent stabilized"**
   - **Why**: Rent history determines legal rent and overcharge claims
   - **Case types**: Rent overcharge, illegal increases, deregulation challenges

### 10. **"HSTPA" "rent stabilization" "tenant protection"**
   - **Why**: 2019 law that strengthened tenant protections significantly
   - **Case types**: Various - post-2019 cases interpreting new protections

---

## Additional Search Strategies

### By Court Type:
- **"Housing Court"** - NYC Housing Court cases
- **"Civil Court"** - NYC Civil Court housing cases  
- **"Supreme Court"** - Appellate cases and complex matters

### By Issue:
- **"construction harassment"** - Landlords using construction to harass
- **"bedbugs" "mold" "habitability"** - Specific repair issues
- **"lease renewal" "rent stabilized"** - Lease renewal rights

### By Statute/Law:
- **"RPAPL"** - Real Property Actions and Proceedings Law
- **"RPL"** - Real Property Law
- **"MDL"** - Multiple Dwelling Law
- **"HSTPA"** - Housing Stability and Tenant Protection Act

---

## Suggested Justia Search Command

```bash
# Search with multiple CHTU-relevant terms
python -m tenant_legal_guidance.scripts.build_manifest \
  --justia-search \
  --keywords \
    "rent stabilization" \
    "HP action repairs" \
    "rent abatement" \
    "tenant harassment" \
    "succession rights" \
    "Major Capital Improvement" \
    "warranty of habitability" \
    "rent overcharge" \
    "HSTPA" \
    "construction harassment" \
  --years 2019-2025 \
  --max-results 100 \
  --output data/manifests/chtu_inspired_cases.jsonl \
  --filter-relevance
```

## Why These Terms Work

1. **Specific NYC legal concepts**: HP actions, MCI, succession rights are NYC-specific
2. **Recent legislation**: HSTPA 2019 changed many rules - recent cases are most relevant
3. **Common tenant issues**: Heat, repairs, harassment are frequent problems
4. **Actionable rights**: These terms find cases about rights tenants can assert

---

*Based on Crown Heights Tenant Union Resource Directory analysis*

