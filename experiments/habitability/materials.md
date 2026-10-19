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
  Exception (statutory text as quoted in Park West, 47 N.Y.2d at 325 n.1): a condition "caused by the misconduct of the
  tenant or lessee or persons under his direction or control" is not a breach. [opinion]
- Subdivision 2: any waiver or modification of the tenant's rights is void as contrary to public policy. [opinion]
- Subdivision 3: in determining the tenant's damages, the court need not require expert testimony. [opinion]
  (The first version of this file wrongly described subdivision 3 as a strike/labor-dispute damages limit. The statute
  text quoted in Park West has no such provision.)
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

### 1. Park West Management Corp. v. Mitchell, 47 N.Y.2d 316 (1979), NY Court of Appeals [opinion]

Chief Judge Cooke, unanimous. Facts: for 17 days in May 1976 the entire maintenance and janitorial staff of a seven-building
Manhattan complex struck. Incinerators were wired shut, uncollected trash piled to the first-floor windows, the city declared
a health emergency, extermination stopped and rats, roaches and vermin flourished. (Doorman and elevator were not at issue.)
The parties stipulated the facts for about 400 tenants. Civil Court found a breach and reduced the June rent bill by 10%;
Appellate Term and Appellate Division affirmed; the Court of Appeals affirmed ("The record here amply supports the 10%
reduction ... Given the severity of the conditions ... and the feeble attempts by petitioner to alleviate the dangers").
Holdings: the statute "places an unqualified obligation on the landlord to keep the premises habitable"; conditions from
"ordinary deterioration, work stoppages by employees, acts of third parties or natural disaster are within the scope of the
warranty"; the duty is nondelegable and nonwaivable. A landlord is not required to ensure "perfect or even aesthetically
pleasing condition", but warrants that there are no conditions that "materially affect the health and safety of tenants",
e.g. insect or rodent infestation, insufficient heat and plumbing, dangerous wiring, inadequate sanitation. Test: "If, in the
eyes of a reasonable person, defects in the dwelling deprive the tenant of those essential functions which a residence is
expected to provide, a breach ... has occurred." Housing code: substantial violation is "prima facie evidence" that the
premises are not habitable, but a violation may be "de minimis or ha[ve] no impact upon habitability", so once shown the
parties must produce evidence on the extent of the breach, its impact on health, safety or welfare, and the landlord's
measures; code violation is not the exclusive determinant, since threats to health and safety "determine the reach" of the
warranty. Damages: the difference between the fair market value as warranted (measured by the rent reserved) and the value
during the breach; a sum in a plenary action or a percentage reduction of rent as a setoff in a nonpayment proceeding
where the tenant counterclaims or pleads breach as a defense. The fact-finder "must weigh the severity of the violation and
duration of the conditions ... as well as the effectiveness of steps taken by the landlord to abate"; no expert testimony
needed. The opinion does not discuss tenant notice as an element.

### 2. Solow v. Wellner, 86 N.Y.2d 582 (1995), NY Court of Appeals [opinion, via Cornell LII text]

Judge Levine. About 65 tenants of a Manhattan building withheld rent; the landlord sued for nonpayment (Oct 1987 to May 1988).
Civil Court (trial level) applied a "reasonable expectations" standard from lease terms and building rents and awarded 10% for
common areas plus 1% to 11% for individual apartments. Appellate Term rejected that standard, found only elevator service
problems warranted abatement, cut the common-area abatement to 5%, denied additional abatements for 16 apartments and
remanded the rest for recalculation. The Appellate Division modified the remand in part and otherwise affirmed. The Court of
Appeals AFFIRMED that order. It rejected the lease-based reasonable-expectations standard: the warranty is a minimum, objective
standard tied to essential residential functions, and operable elevator service is essential in a high-rise. The Court of
Appeals did NOT review or endorse any percentage (10%, 1-11% or 5%); those were left to be recalculated on remand. The
three covenants of § 235-b(1) (habitation, intended use, no danger to life, health or safety) are quoted from the statute.

### 3. Eastside Exhibition Corp. v. 210 East 86th St. Corp., 18 N.Y.3d 617 (2012), NY Court of Appeals [opinion]

(Corrected citation; the first version cited 18 N.Y.3d 1035.) Judge Ciparick. A COMMERCIAL lease case about actual partial
eviction, not the warranty of habitability. A movie-theater tenant stopped paying rent after the landlord installed about
12 square feet of cross-bracing in a 15,000-19,000 sq ft premises. Held: a minimal intrusion with no demonstrable effect on
the tenant's use is de minimis and does not warrant the traditional remedy of total rent abatement; damages are the remedy.
It does not address RPL § 235-b, housing code violations or residential habitability. It is a general de minimis case, not
authority for the Park West code-violation de minimis point.

### 4. Jangla Realty Co. v. Gravagna, 112 Misc. 2d 642, 447 N.Y.S.2d 338 (Civ. Ct. N.Y. Co. 1981), Milano, J. [opinion]

Trial-level decision, persuasive only. Facts: on Sept 3, 1981 a burglar jimmied both locks of a senior tenant's door in a
Maspeth, Queens building. She told the superintendent about 7 p.m.; he said replacement would take two to three days. About
noon the next day she called a locksmith; the landlord's office employee told her to make the repair and send the bill. The
landlord's agents never said they would repair. The tenant claimed $120 for a replacement lock and installation. Issue: whether
18 hours after notice is a sufficient opportunity to repair for an "exigent" inoperable lock. The court, drawing on Jackson v
Rivera (65 Misc 2d 468), held a tenant may repair and deduct the reasonable cost when (1) the condition creates an emergency
seriously affecting habitability, (2) the landlord has refused or not repaired in reasonable time after reasonable
opportunity, and (3) the condition cannot reasonably continue until code enforcement runs its course; notice to the landlord
is required; the cost must be reasonable. It found an emergency, notice to the super, ample opportunity, and $120 reasonable,
and set off $120 against $203.83 owed. The decision cites Park West at 329 for the rent-abatement remedy and notes other
remedies "were not excluded". The statutory basis cited is former Admin Code § D26-20.05 (door locks).

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
