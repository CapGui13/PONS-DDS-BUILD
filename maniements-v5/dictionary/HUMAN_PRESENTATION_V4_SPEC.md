# MANIEMENTS V5 — Human presentation V4

Status: PILOT / review-first. The exact V3 solver remains the oracle; this document replaces the idea that the raw policy automaton is itself a user-facing explanation.

## Product contract

A dictionary entry must answer a bridge player's question, in this order:

1. **Holding + goal + exact probability.** Example: `X98 / ARD7`, goal `4 levées`, `60,90 %`.
2. **Standard assumption.** Unless the user constrains entries, assume enough outside entries to return to either hand between rounds of the suit. Say this explicitly whenever the line uses such a return.
3. **Maniement.** Give an imperative bridge line: `jouer petit vers le Valet`, `tirer l'As puis...`, `faire l'impasse au 10`, etc.
4. **Observable branches only.** Branch on what a player can actually see: an honour appears, a defender shows out, a card is covered, a finesse wins/loses. Never expose internal policy-state counts.
5. **Why.** Explain which relevant layouts the recommended line gains or protects against. Prefer comparisons such as `cette ligne gagne aussi contre ...`, `jouer l'As d'abord perd contre ...`.
6. **Expert details (collapsed by default).** Exact fraction, exhaustive layouts, raw public policy, internal contexts, hashes. These are evidence, not the explanation.

## Language rules

- French notation: A, R, D, V, X (=10); lowercase `x` means an irrelevant small card, only when the whole family has been certified.
- Prefer `petit` when several low spot cards are genuinely equivalent. Never arbitrarily promote one pip (for example `le 8`) into the pedagogical line merely because the deterministic solver chose it as a tie-break.
- `Revenir en Nord/Sud` means an outside entry is required. Do not write a sequence that silently assumes impossible suit-only communication.
- If several first plays are co-optimal but strategically different, say so. Pick one as the reference line only after validating that its continuation is complete.
- Do not use `politique`, `contexte de décision`, `automate`, `état`, `masque`, or `witness` in the main bridge explanation.
- A raw exact policy that has not yet been humanized is displayed as **calcul exact disponible — explication en cours de certification**, not as machine-generated prose.

## Complex lines: interactive play, not giant prose

For a non-trivial exact policy, the preferred interface follows the SuitPlay idea:

- show the recommended first action;
- let the user step through defender cards/voids;
- at every declarer turn, show the good card(s) in bridge notation;
- if a new round requires returning to the other hand, display `Revenir en ... (entrée extérieure nécessaire)`;
- group defender cards only when they lead to the same declarer decision and the same future policy;
- keep a short `Pourquoi ?` paragraph next to the interactive line.

The exact public policy is replayed underneath. The human presentation is accepted only if replay against all defender layouts preserves the solver's exact success fraction.

## Certification levels

- `REFERENCE_VERIFIED`: line taken from a trusted bridge reference and checked against the exact solver for the concrete holding/goal.
- `HUMAN_TREE_EXACT`: generated human decision tree replayed exhaustively with the same exact success set/fraction as the solver.
- `SEMANTIC_EXACT`: compact success condition proved from the exact winning worlds (e.g. pure distribution condition).
- `RAW_EXACT_ONLY`: exact probability/policy exists, but no user-facing bridge explanation is certified yet.

Only the first three may be presented as a finished `maniement`.

## Pilot corpus

Before any new large semantic rollout, qualify the presentation on roughly twenty published combinations covering:

- direct and repeated finesses;
- safety plays;
- different goals on the same holding;
- useful intermediate spots (9/8/10);
- honour appearances and void branches;
- lines needing outside re-entries;
- a few exact V3 cases already materialized.

The pilot is a human review gate. Production expansion of exact probabilities can remain useful, but semantic generation must not be scaled until the presentation is approved.

## Reference style surveyed

- Jeroen Warmerdam, SuitPlay Main Help: results separate goals/probabilities from lines of play; the Play pane lets the user step through cards and shows the good declarer cards. https://jeroenwarmerdam.pythonanywhere.com/suitplay/help/MainHelp.html
- Jeroen Warmerdam, SuitPlay combination help: entries can be constrained; if unrestricted, new rounds may be led from either hand. https://jeroenwarmerdam.pythonanywhere.com/suitplay/help/Combo.html
- Brian Senior, “Know your suit combinations”: imperative lines followed by the bridge reason and relevant layouts; explicitly assumes all required entries. https://csbnews.org/en/know-your-suit-combinations-by-brian-senior/
- Jean-Marc Roudinesco examples quoted in bridge literature: numbered/conditional procedures such as `run the jack; if it loses, cash the ace; if it holds or is covered, finesse the nine`.
- BridgeHands suit-combination tables: holding + goal + percentage + concise practical instruction. https://www.bridgehands.com/S/Suit_Combination_4.htm

## Two regression rules prompted by the V3 pilot

### `54 / V632`, goal 1

The exact success condition is useful, but the sentence `jouer petit trois fois en conservant le Valet` is ambiguous. A valid human explanation must state the entry assumption, for example:

> Une levée n'est possible que si A-R-D sont secs dans la même main adverse. Ne jouez pas le Valet avant d'avoir forcé ces trois honneurs. Avec les communications extérieures nécessaires, jouez trois petites cartes de la main du Valet, en revenant dans cette main entre les tours; le Valet est alors maître.

### `X98 / ARD7`, goal 4

`14 contextes de décision` is forbidden user-facing output. Until the exact policy has been compiled into observable bridge branches, the entry is `RAW_EXACT_ONLY`. The UI may offer an interactive exact-play explorer, but must not pretend the automaton count is an explanation.
