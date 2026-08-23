# R7 FIXED MB04 — delayed four-card Spade fit audit

Baseline: `R7_FIXED_MB03_D9_D13_BRANCHK_GREEN`  
Reference: fresh paired 500K v2.61 original vs MB02/MB03 classifications with true DDS + DealerPar.

## Revalidation on MB03

The 1,774 cases rooted at `branch-e-pass4-1S-four-fit-delayed-2over1` were replayed with MB03. MB03 changes none of them, so the v2.61 ↔ MB03 result remains exactly:

- 1,774 differences
- 203 BETTER
- 377 WORSE
- 1,194 EQUIVALENT
- cumulative candidate − baseline absolute DealerPar gap: **+97,190**

## Independent audit A — deferred fit → RKCB

376/1,774 cases later use `wave2c-rkcb-deferred-spade-response-producer`:

- 53 BETTER / 144 WORSE / 179 EQUIVALENT
- net DealerPar impact: **+52,640**
- 293 cases reach `wave2c-rkcb-captain-public-signoff`, accounting for **+51,240**.

No safe broad patch is authorized here. The public 30-41 classes are genuinely ambiguous in important nodes: identical public auction prefixes with a 5C response and two asker keys occur with both 0 and 3 responder keys. Resolving those cases by the actual partner hand would therefore be hidden-card leakage. Audit A is **NO_PATCH** for MB04.

## Independent audit B — no deferred RKCB producer

1,398/1,774 cases do not use that RKCB producer:

- 150 BETTER / 233 WORSE / 1,015 EQUIVALENT
- net DealerPar impact: **+44,550**.

The largest contract transition is 6S(v2.61) → 4S(MB03): 147 cases, **+41,680**. A broad reopening of every delayed-fit 4S with high HLD was tested and rejected because it increased the DealerPar gap.

A narrower public family is materially cleaner:

`1S - P - 2C/2D - P - 3S - P - 4S`

Among the audited root cases this family has 95 cases and **+24,050** net impact. The candidate micro-rule is restricted to the responder's own hand and public auction only:

- exactly four Spades;
- initial natural 2C/2D side suit still has 3+ cards;
- Chailley/SEF fit evaluation >=17 HLD;
- responder owns at least two RKCB keycards (own cards only);
- uncontested exact public prefix above;
- replace native 4S closure by 4NT RKCB.

Replay against MB03 on the old 500K root corpus:

- 47 auctions changed;
- 18 are closer to DealerPar than MB03;
- 28 tie MB03;
- 1 is farther by only 10 points;
- cumulative candidate − MB03 absolute DealerPar gap: **−10,350**;
- the full 1,774-case root aggregate improves from **+97,190** to **+86,840**.

Threshold probes showed 17 HLD + 2 own keys is better than the tested 16 or 18 HLD variants on this corpus.

A fresh 3,000-deal smoke produced zero hits, consistent with the rule's low frequency, and therefore no observed collateral. This smoke is not large enough to qualify the micro-build.

## Candidate

`R7_FIXED_MB04_DELAYED_SPADES_RKCB_AFTER_OPENER_3S`

Candidate critic SHA-256: `0838c8bba44bea70a7faf719d180683de45c7d5a8c5753483eed5bbdd68c7e8c`  
Patch SHA-256: `562f2f40e6730c081c7189373ab8c8f5acd2ad29e2d2733db1389c6ad52b41d3`

Status before fresh gate: **CANDIDATE_NOT_GREEN**.
