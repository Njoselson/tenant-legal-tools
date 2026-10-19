# Habitability materials (experiment fixture)

Source key: **[repo]** = text held in this repo (`data/taxonomy/laws.yaml`, `data/case_ground_truth.json`).
**[secondary]** = summarized from the maintainer's notes and general knowledge; the opinion was not fetched or read.
Treat every [secondary] holding as unverified.
**[opinion]** = checked against the full opinion text fetched from CourtListener (`opinions/`) or Cornell LII.

v2 (corrected): the first run's materials had errors found by reading the opinions: the Solow holding, the Park West
facts, the § 235-b(3) text, the Eastside description and citation. See RUN.md.

## Statutes and code

### RPL § 235-b: Warranty of Habitability [repo + secondary]

- Implied in every residential lease, written or oral. Citation: NY Real Property Law § 235-b.
- Subdivision 1: the landlord warrants that (1) the premises and common areas are fit for human habitation,
  (2) the premises are fit for the uses reasonably intended by the parties, and (3) occupants will not be
  subjected to conditions that are dangerous, hazardous or detrimental to life, health or safety.
  Exception: the condition was caused by the tenant or someone under the tenant's control.
- Subdivision 2: any waiver of the warranty is void as against public policy.
- Subdivision 3: damages are limited where the condition results from a strike or labor dispute not primarily
  caused by the landlord, to the extent of the landlord's net savings, if the landlord made good-faith efforts to cure.
- The duty is nondelegable (the landlord cannot blame a managing agent or contractor).

### NYC Housing Maintenance Code (Admin Code Title 27, Ch. 2) [repo + secondary]

- **§ 27-2005**: owner's general duty to maintain the premises in good repair and habitable condition. [repo]
- **§ 27-2006**: tenant duties regarding code violations; owner obligations are not relieved. [repo]
- **§ 27-2007**: prohibited tenant acts, such as removing self-closing doors or obstructing fire escapes. [repo]
- **§ 27-2013**: painting. [repo; title only]
- **§ 27-2028**: central heating (or an approved alternative) required in multiple dwellings. [repo]
- **§ 27-2029 (Heat)**: from Oct 1 to May 31, 68°F from 6 a.m. to 10 p.m. when outside is below 55°F,
  and 62°F from 10 p.m. to 6 a.m. regardless of outside temperature. [repo]
- **§ 27-2031 (Hot water)**: at least 120°F, 6 a.m. to midnight. [repo]
- **§ 27-2017.3 (mold)** and **§ 27-2017.4 (pests)**: per the maintainer's notes, mold and pest infestation are
  addressed here, and pests are classed immediately hazardous. [secondary; section numbers unverified]
- **Violation classes**: Class A (non-hazardous) 90 days to correct; Class B (hazardous) 30 days;
  Class C (immediately hazardous, e.g. no heat or hot water, gas leak, exposed wiring) 24 hours. [secondary]
- **§ 27-2115**: civil penalties for uncorrected violations. [secondary]
- HPD violations are on the public record (HPD Online) after a 311 complaint and inspection. [secondary]

### Procedure statutes [secondary]

- **RPAPL § 711(2)**: nonpayment proceeding, conditioned on a proper written rent demand.
- **RPAPL § 735**: service of the rent demand and petition.
- **Written 14-day rent demand** (HSTPA 2019; oral demands abolished). The demand must be a good-faith, reasonably
  accurate accounting; an overstated demand is a dismissal ground.
- **RPAPL § 731 / § 749(3)**: payment in full before the hearing moots the case; payment in full after judgment but
  before the eviction is executed voids the warrant (absent bad-faith withholding).
- **RPAPL §§ 110, 117 and CCA § 110(a)**: Housing Part jurisdiction. An HP proceeding seeks an Order to Correct,
  civil penalties, and in severe cases a 7-A Administrator (RPAPL Art. 7-A, §§ 769-783).

## Cases

All six are binding or persuasive only as described. Court and year are given for each.

### 1. Park West Management Corp. v. Mitchell, 47 N.Y.2d 316 (1979), NY Court of Appeals [secondary]

Foundational. A building-employee strike left tenants without doorman, elevator and garbage services. Held: the
§ 235-b duty runs to the tenant regardless of who caused the diminished services (subject to the strike carve-out in
subdivision 3). Habitability can be raised as a defense or counterclaim in a nonpayment case. Damages are the
difference between the fair market value of the premises as warranted and their value during the breach, in practice a
percentage rent abatement. The fact-finder weighs severity, duration, and the landlord's remedial promptness and
effectiveness. A Housing Maintenance Code violation is not strictly required to prove breach and does not automatically
establish breach; it is strong evidence, but trivial (de minimis) violations may not breach. A 10% abatement was affirmed.

### 2. Solow v. Wellner, 86 N.Y.2d 582 (1995), NY Court of Appeals [secondary]

Clarified that § 235-b(1) contains three distinct covenants (habitation, intended use, no danger to life, health or
safety). Protection covers conditions affecting health, safety or functional habitability, not aesthetic or amenity
complaints. Applying the Park West method, upheld a 10% abatement for common-area failures plus additional abatements of
1% to 11% for individual apartment issues, within a six-year limitations period.

### 3. Eastside Exhibition Corp. v. 210 East 86th St. Corp., 18 N.Y.3d 1035 (2012), NY Court of Appeals [secondary]

A commercial lease case, frequently cited for the Park West de minimis principle: not every technical code violation
is a substantive breach of the warranty if it has no real impact on use.

### 4. Jangla Realty Co. v. Gravagna, 112 Misc. 2d 642, 447 N.Y.S.2d 338 (Civ. Ct. Queens Co. 1981) [secondary, weakest]

Trial-level decision, persuasive only. The standard citation for repair-and-deduct. A burglar jimmied the tenant's door
locks; the landlord had not repaired them about 18 hours after notice; the court treated that as sufficient opportunity to
repair and allowed the tenant to deduct the locksmith's cost. Summarized from secondary sources; the opinion has not been read.
Repair-and-deduct conditions drawn from it and from guidance: notice to the landlord, no repair within a reasonable time,
a necessary repair (ideally of a code violation), a reasonable cost, and kept bids, receipts and communications.

### 5. 100 W 174 LLC v Haskins, 2014 NY Slip Op 51673(U) [repo: `data/case_ground_truth.json`]

Tenant situation (ground truth text): over a year of severe, chronic problems including a persistent rodent infestation,
multiple broken facilities and hazardous conditions; notice given; landlord failed to repair.
Outcome: tenant win. The court found a breach of the warranty of habitability and awarded a **40% rent abatement for a
14-month period**. Evidence that mattered: chronic rodent infestation; broken facilities and hazardous violations;
conditions persisting over a year; notice to the landlord and failure to repair timely. The court level is not stated in the repo.

### 6. Poyck v Bryant, 2006 NY Slip Op 26343 [repo: `data/case_ground_truth.json`]

Tenant situation (ground truth text): a condominium unit; a neighbor's secondhand smoke seeped in through walls and
ventilation, causing health problems; the tenant complained repeatedly to management and the landlord, who said they could
not control another owner and took no action. Outcome: tenant win. The court held that the secondhand smoke constituted a
breach of the warranty of habitability and could support a constructive eviction claim, and that the landlord had a duty to
take reasonable steps to abate the nuisance. No abatement amount was granted in the ground truth. Evidence that mattered:
the tenant's testimony and complaints about the smoke, and the landlord's refusal or failure to act. The court level is not stated in the repo.

## Evidence

### What proves breach

- The tenant's own testimony about the condition, its effect on health, safety or use, and its duration. (Poyck: testimony and complaints sufficed.)
- Notice: dated complaints to the landlord or agent (letters, texts, emails, rent-portal messages) and the landlord's response or silence. Notice and a failure to repair within a reasonable time are part of what mattered in Haskins.
- HPD violations on the public record after a 311 complaint and inspection. Strong evidence (Park West) but neither required nor automatically dispositive; de minimis violations may not count.
- Photos and video with dates; expert or inspector reports; medical records where health impact is claimed; witness statements.
- Evidence the condition affects health, safety or functional habitability, not merely appearance (Solow).

### What proves the abatement amount

- The rent actually charged for the period, so the percentage reduction can be turned into dollars.
- The dates the condition began and ended (duration), because the abatement runs for the period of breach.
- Severity and which parts of the premises were affected (whole apartment, one room, common areas), since courts have set percentages from roughly 1% to 40% in the cases above.
- The landlord's remedial efforts: how fast and how effectively it responded.
- The tenant's repair receipts, if any, which are direct evidence of cost (relevant to repair-and-deduct).
- Comparable abatements in similar cases (Park West 10%, Solow 10% plus 1-11%, Haskins 40% for 14 months).

### Defenses and limits

- Tenant-caused condition (RPL § 235-b(1) exception; HMC § 27-2006).
- De minimis or aesthetic conditions (Solow, Park West, Eastside).
- Withholding rent without documentation does not prevent a nonpayment suit; the tenant must then prove breach and the abatement, and failing risks judgment for full rent and eviction exposure.
- Full payment of arrears at any point up to the eviction cures a nonpayment case; a defective rent demand can defeat it.
