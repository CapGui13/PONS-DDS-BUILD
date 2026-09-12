# MANIEMENTS V5 — Human presentation V5.9

Status: PILOT / motif-first / review-first.

The exact V3 solver is the immutable oracle. Raw policy states and exhaustive trees are proof/debug data only; they are never the normal user-facing explanation.

## Product contract

A dictionary entry is keyed by the **holding**, with one independent record for every trick objective.

For each holding + target:
1. show the two partnership holdings vertically;
2. show the exact success probability;
3. show a short playable bridge procedure;
4. explain the concrete adverse layout(s) the procedure is exploiting or protecting against;
5. expose exact proof only in expert/debug details.

The target is a first-class dimension. Never infer that a higher target is impossible from the optimal line for a lower target. Query every target independently, even when the probability is very small.

## Motif-first architecture

The human layer no longer tries to shorten an arbitrary exact policy until it looks like bridge.

Instead:
1. generate a small library of recognisable bridge motifs (play in head, finesse sequence, repeated finesse, cash-then-finesse, safety duck, honour probe, shortage-revealed switch, etc.);
2. instantiate each motif on the concrete holding;
3. replay that complete human strategy exhaustively against every defender layout and every legal defence;
4. promote the motif only when its exact success fraction equals the solver optimum;
5. among several exact motifs, prefer the one with the lowest human complexity.

A motif that merely has the same rounded percentage is not certified. Equality must be exact.

## Exact explanation layer

The `Pourquoi ?` is mined from the exact success/failure world set of the **certified human strategy**, not from a generic statistical sentence.

Preferred explanations identify, in bridge language:
- a missing honour placed / badly placed;
- one or more honours dry or doubleton;
- two honours together or split;
- a specific 3–2, 4–1, 5–0, etc. split;
- a precise exceptional losing/winning layout;
- a conjunction/disjunction of a small number of such conditions.

Only an exact Boolean characterisation of the replayed world set may be labelled `SEMANTIC_EXACT`. If no short exact layout formula exists, keep the explanation pending rather than inventing one.

## Language rules

- French notation: A, R, D, V, X (=10); lowercase `x` only after family invariance is certified.
- Prefer relational language: `petit vers le 9`, `si l’adversaire prend`, `si l’adversaire joue fort en deuxième`.
- Avoid Nord/Sud/Est/Ouest unless orientation is genuinely necessary.
- Name a finesse by the missing card being finessed: with `ADX32 / 654`, playing toward the Dame is an **impasse au Roi**.
- `Pourquoi ?` must name real layouts whenever possible: `Dame sèche placée`, `A-V seconds`, `10 quatrième`, `partage 4–1`, etc.
- Do not expose `politique`, `contexte de décision`, `automate`, `état`, `masque`, `witness`, or raw solver coordinates in normal text.
- If the exact probability exists but the human line is not certified, display: **Calcul exact disponible — maniement humain en cours de certification.**

## Certification levels

- `REFERENCE_VERIFIED`: published human line rechecked against its source and the exact solver when available.
- `HUMAN_TREE_EXACT`: complete human procedure exhaustively replayed and equal to the solver optimum.
- `SEMANTIC_EXACT`: short layout condition proved to describe exactly the success/failure world set of the certified procedure.
- `RAW_EXACT_ONLY`: exact calculation exists but no finished human procedure is certified.

A finished public card requires a certified procedure (`REFERENCE_VERIFIED` or `HUMAN_TREE_EXACT`). `SEMANTIC_EXACT` strengthens its `Pourquoi ?`; it does not replace the need for a playable procedure.

## Complexity preference among exact strategies

When several strategies are exactly optimal, choose the human-simplest one. In order of preference:
- recognised bridge motif;
- fewer strategic decisions;
- fewer conditional branches;
- no dependence on irrelevant spot cards;
- no seat names unless required;
- no hidden-state wording;
- shortest natural French description.

Do not let an arbitrary engine tie-break determine the published maniement.

## Regression rules from review

### `54 / V632`, goal 1

> Une levée n'est possible que si A-R-D sont secs dans la même main adverse. Dans cette position, le maniement est indifférent : quel que soit l'ordre dans lequel on joue les petites cartes, le Valet finit maître.

Do not invent a need to return repeatedly to the Valet hand.

### `AV32 / R954`, goal 4

Start immediately with a small card toward the Jack; do not cash the King first. The extra gain includes the **singleton Queen onside**, with the 10 fourth in the other defender's hand. Both lines already succeed against Queen doubleton onside.

### `AX42 / 953`, goal 2

> Commencer par petit vers le 9. Si l'adversaire prend, tirer ensuite l'As. Si un adversaire joue fort en deuxième avant le 9, repartir ensuite du 9 en forçante. S'il prend, jouer ensuite petit vers le 10.

Do not call the last action an “impasse au 10”: the 10 belongs to declarer.

### `X98 / ARD7`, goal 4

Certified progressive line: 8 toward the Queen, 9 toward the King, then 10 toward the Ace; cover the Jack if it appears in second seat, and use a revealed shortage to localise and finesse the Jack when appropriate. Exhaustive replay equals the exact solver at `1961/3220 = 60.90%`.

## Current experimental gates

The 20-holding / 35-nontrivial-target qualification corpus is deliberately unseen by the reviewed reference corpus. It remains a development benchmark only; passing it does not itself authorise mass publication.

The frozen runtime SHA-256 remains:
`a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d`

Mass generation of human explanations is gated on motif coverage, exact replay, and explanation quality. The exact dictionary may continue materialising independently while the human layer improves.
