# MANIEMENTS V5 — Human presentation V4.1

Status: PILOT / review-first. The exact V3 solver remains the oracle; raw policy states are evidence, never the user-facing explanation.

## Product contract

A dictionary entry must answer a bridge player's question in this order:

1. **Holding, vertically displayed + goal + exact probability.** The two partnership hands are shown one above the other, never only as `hand1 / hand2`.
2. **Maniement.** Give the shortest playable bridge instruction: `petit vers le 9`, `tirer l'As puis petit vers la Dame`, `impasse au Roi en jouant vers la Dame`.
3. **Why / position sought.** Always say what layout is being targeted or protected against. A line without its bridge reason is incomplete.
4. **Observable branches only.** Branch only on what a player can see: an honour appears, a defender shows out, an opponent takes, a finesse holds/fails.
5. **Standard assumptions only when needed.** Outside entries are assumed available in classical isolated-suit analysis, but mention an outside return only if the recommended line actually uses it.
6. **Expert evidence collapsed.** Exact fraction, exhaustive layouts, public policy and hashes remain available as proof, but never replace the human line.

## Language rules learned from pilot review

- French notation: A, R, D, V, X (=10); lowercase `x` is an irrelevant small card only after family certification.
- Prefer `petit` when low spot cards are equivalent.
- Avoid Nord/Sud/Est/Ouest when direction is obvious from the holding. Prefer `petit vers le 9`, `si l'adversaire prend`, `si l'adversaire joue fort en deuxième`.
- Name a finesse by the **missing card being finessed**, not by the card we own: with `ADX32 / 654`, `jouer vers la Dame` is an **impasse au Roi**, not an “impasse à la Dame”.
- A `Pourquoi ?` must identify concrete winning/losing layouts whenever possible: `Dame sèche placée`, `A-V seconds`, `Dame seconde`, `10 quatrième`, `partage 4–1`, etc.
- Do not say merely `cette ligne gagne plus de cas` when the relevant cases can be named.
- Do not expose `politique`, `contexte de décision`, `automate`, `état`, `masque`, or `witness` in the main explanation.
- If the exact solver is available but the human line is not yet certified, display **calcul exact disponible — maniement humain en cours de certification**.

## Complex lines

The first pilot showed that a full interactive replay of the exact policy is too complex for the normal dictionary view.

For a non-trivial policy:
- first produce a short human procedure with only bridge-relevant branches;
- explain the layout/probability logic behind each branch;
- keep any exhaustive interactive replay hidden in expert/debug tooling;
- certify the human procedure by replaying it against all defender layouts and requiring the exact same success fraction/set as the solver.

## Certification levels

- `REFERENCE_VERIFIED`: published human line rechecked against the cited source and exact solver when available.
- `HUMAN_TREE_EXACT`: generated human decision procedure exhaustively replayed with the same exact success set/fraction.
- `SEMANTIC_EXACT`: compact success condition proved directly from exact winning worlds.
- `RAW_EXACT_ONLY`: exact calculation exists but no finished human maniement is certified.

Only the first three may be presented as a finished maniement.

## Regression rules from user review

### `54 / V632`, goal 1

Correct human statement:

> Une levée n'est possible que si A-R-D sont secs dans la même main adverse. Dans cette position, le maniement est indifférent : quel que soit l'ordre dans lequel on joue les petites cartes, le Valet finit maître.

Do **not** invent a need to return repeatedly to the Valet hand.

### `AV32 / R954`, goal 4

Start immediately with a small card toward the Jack; do not cash the King first. The explanation must identify the layouts gained by the immediate finesse rather than merely saying that it “wins extra cases”.

After source recheck, Brian Senior explicitly says both lines already succeed against a doubleton Queen; the extra gain of the immediate finesse includes the **singleton Queen onside**, which corresponds to the 10 being fourth in the other defender's hand.

### `AX42 / 953`, goal 2

Current reviewed wording:

> Commencer par petit vers le 9. Si l'adversaire prend, tirer ensuite l'As. Si un adversaire joue fort en deuxième avant le 9, repartir ensuite du 9 en forçante. S'il prend, jouer ensuite petit vers le 10.

Do not call the last action an “impasse au 10”: the 10 belongs to declarer.

### `X98 / ARD7`, goal 4

The raw interactive exact replay is not acceptable as the normal presentation. Current hypothesis to certify is a short line based on two probes and the third-round information about the missing Jack. Until exhaustive replay validates the exact branch structure, keep this entry explicitly provisional.

## Reference corpus gate

The 15 Brian Senior examples/quiz solutions are rechecked against the original article. Roudinesco examples are checked against online quotations, and BridgeHands examples against its tables. Any line whose public source has not been directly re-located remains marked as such rather than silently promoted to `REFERENCE_VERIFIED`.
