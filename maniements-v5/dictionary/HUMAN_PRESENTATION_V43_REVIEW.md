# MANIEMENTS V5 — Human presentation V4.3 review freeze

Status: REVIEWED BASE / bridge-first.

This document freezes the presentation rules validated during the September 12 review. The exact V3 solver remains the oracle; human text is a separate certified layer.

## Display

- Show the two holdings one above the other, centered as opposing hands. If the lengths differ, center the shorter holding under the longer one (for example the singleton `2` under the middle of `RV98765`).
- French notation: `A R D V X`; `X = 10`. Lowercase `x` is only used for a certified family of irrelevant small cards.
- Do not expose North/South/East/West unless the seat name is genuinely needed to describe an observable branch.
- Do not show the raw exact-policy explorer in the normal entry. It belongs in expert/debug details only.

## What a finished entry must explain

1. Holding, goal and exact success probability.
2. A short, directly playable line: what to lead, what to cover, when to repeat the play.
3. **Why the line works:** name the relevant defender holding/distribution that the line is trying to exploit.
4. If an alternative natural play is inferior, state which useful position it loses.
5. Mention outside entries only when the recommended line genuinely requires returning to a hand.

A phrase such as `this gains more cases` is not enough. Prefer bridge statements such as `this makes four tricks when the jack is bare offside` or `cash the ace next, hoping to crush the other honour now bare or doubleton`.

## Language rules validated in review

- Say `jouer petit vers le 10`, not `faire l'impasse au 10`, when the 10 is our card and the actual action is simply to lead toward it.
- Prefer `Commencer par petit vers le 9` over unnecessary seat names.
- Prefer `ne permet pas de profiter de cette position de cartes` over `ne récupère pas cette position`.
- Do not mention the work process (`après relecture de la source`, `le moteur dit`, etc.) in the bridge explanation. Sources/certification live separately.
- A finished explanation should identify the card position hoped for, not merely recite a sequence of plays.

## Reviewed regression examples

### `54 / V632` — 1 trick

A trick is possible only when A-R-D are bare together in one defender hand. In that position the order of the small cards is irrelevant; the jack eventually becomes master. Do **not** invent a need to return repeatedly to the jack hand.

### `AV32 / R954` — 4 tricks

Play small immediately toward the jack; do not cash the king first. The immediate finesse preserves the extra case of the bare queen onside with the 10 fourth on the other side. Both lines already work against queen doubleton onside.

### `AX42 / 953` — 2 tricks

Start small toward the 9. If the 9 is taken, cash the ace next, hoping to crush the other defender honour now bare or doubleton. If second hand plays an honour before the 9, keep the 9 and later lead it as a forcing card; if that is taken, play small toward the 10.

### `R432 / DX5` — 3 tricks

Play small toward the 10; cover the jack with the queen if it appears. Return to the king hand and play small toward the 10 again. The second passage toward Q-10 wins notably when A-J are doubleton in front of Q-10. Starting with the king does not allow declarer to profit from that card position.

### `ADX32 / 654` — 4 tricks

Start with the finesse against the king by playing small toward the queen. Return to `654` and then play toward the 10. This order makes four tricks when the jack is bare offside. Starting with the 10 — the finesse against the jack — loses that possibility.

## `X98 / ARD7` — 4 tricks: exact human qualification

The reviewed intuition `two top-card probes, then finesse the jack` is close but not optimal.

- Exact optimum: `1961/3220 = 60.900621...%`.
- Two-probe candidate: `83/140 = 59.285714...%`.
- Certified human line: `1961/3220` — exactly equal to the solver optimum.

Certified line:

1. Lead successively from `X98` toward `ARD7`: first the 8 toward the queen, then the 9 toward the king, then the 10 toward the ace.
2. If the jack appears in second hand, cover it with the available higher honour.
3. If the defender who plays **after** `ARD7` has already shown out and the jack has not appeared, play the 7 instead of spending the next honour: this lets the 8/9/10 run and is the finesse against the jack now known to be in second hand.
4. Otherwise continue with queen, king, ace in that order.

Why this beats the two-probe line: after two top cards, `4-2 is more likely than 3-3` is not the relevant conditional comparison. The two-probe line gains the branch where the jack is fourth in the second-hand defender, but loses the opposite 3-3 branch where the jack is third in fourth hand. Exact weights are about 16.15% versus 17.76%, so the guess loses about 1.62 percentage points overall.

The qualification is encoded in `qualify_human_x98_ard7_v43.py`. It replays the human strategy against every legal defensive false-card branch and requires exact equality with the frozen solver probability.

## Certification policy

A normal user-facing `Maniement` may only be shown when one of these holds:

- `REFERENCE_VERIFIED`
- `HUMAN_TREE_EXACT`
- `SEMANTIC_EXACT`

Otherwise display `calcul exact disponible — explication en cours de certification` and keep raw policy data hidden under expert details.
