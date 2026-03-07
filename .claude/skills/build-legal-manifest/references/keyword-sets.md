# Justia Search Keyword Sets by Topic

Use these as starting points for `build_manifest.py --justia-search --keywords`. Adapt as needed.

## Habitability / Heat / Mold / Repairs

Search 1 — legal standard:
```
"warranty of habitability" "New York" "HPD violations"
```

Search 2 — HP Actions and repairs:
```
"HP Action" "New York" "heat" "repairs"
```

Search 3 — remedies:
```
"rent abatement" "habitability" "New York"
```

## Harassment

Search 1 — landlord conduct:
```
"landlord harassment" "New York" "tenant"
```

Search 2 — HP action for harassment:
```
"HP Action" "harassment" "New York" "Housing Court"
```

Search 3 — harassment + damages:
```
"tenant harassment" "damages" "New York" "Admin Code"
```

## Rent Destabilization / Illegal Deregulation

Search 1 — illegal removal:
```
"deregulation" "illegal" "rent stabilization" "New York"
```

Search 2 — high-income / high-rent deregulation:
```
"high income deregulation" "rent stabilization" "New York" "DHCR"
```

Search 3 — HSTPA / ETPA:
```
"HSTPA" "rent stabilization" "New York" "Housing Stability"
```

## Rent Overcharge / Treble Damages

Search 1 — overcharge:
```
"rent overcharge" "New York" "DHCR" "tenant"
```

Search 2 — treble damages:
```
"treble damages" "rent overcharge" "New York"
```

Search 3 — willful overcharge:
```
"willful" "rent overcharge" "New York" "Housing Court"
```

## Combined Harassment + Destabilization

Search 1:
```
"landlord harassment" "New York" "tenant"
```

Search 2:
```
"deregulation" "illegal" "rent stabilization" "New York"
```

Search 3:
```
"treble damages" "rent overcharge" "New York"
```

## General Tips

- Always include `"New York"` to scope results
- For Housing Court decisions, add `"Housing Court"` or `"Civil Court"`
- For appellate precedent, add `"Appellate Term"` or `"Appellate Division"`
- After getting results, prefer cases with clear outcomes (tenant win/loss) over procedural rulings
