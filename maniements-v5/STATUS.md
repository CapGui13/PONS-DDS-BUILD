# MANIEMENTS V5 — progression cloud

Dernière mise à jour : `2026-09-07T18:45:16+00:00`

**Global 64 lanes : 3 060 / 797 161 orbites — 0.384%**
Lanes initialisées : **7/64** — terminées : **0** — non démarrées : **57**
Hard stalls : **6** — lanes encore exécutables : **58**

| Lane | PASS | Statut | Mode | Next | Stall | Orbites | Total lane | % | Targets | Active target | Dernier progrès |
|---:|---:|:---|:---|:---|---:|---:|---:|---:|---:|:---|:---|
| 00 | 000075 | BUDGET_STOP | RESCUE_MAX | HARD_STALL | 5 | 720 | 12613 | 5.71% | 3837 | 132840 / 1/4 | 2026-09-07T06:53:12+00:00 |
| 01 | 000069 | BUDGET_STOP | NORMAL | NORMAL | 0 | 633 | 12635 | 5.01% | 3366 | 127422 / 1/4 | — |
| 02 | 000071 | BUDGET_STOP | RESCUE_MAX | HARD_STALL | 69 | 296 | 12354 | 2.40% | 1532 | 48456 / 1/4 | 2026-09-05T10:23:08+00:00 |
| 03 | 000071 | BUDGET_STOP | RESCUE_MAX | HARD_STALL | 69 | 352 | 12745 | 2.76% | 1807 | 50950 / 1/4 | 2026-09-05T10:23:09+00:00 |
| 04 | 000071 | BUDGET_STOP | RESCUE_MAX | HARD_STALL | 68 | 325 | 12373 | 2.63% | 1658 | 48362 / 1/4 | 2026-09-05T10:43:14+00:00 |
| 05 | 000071 | BUDGET_STOP | RESCUE_MAX | HARD_STALL | 67 | 401 | 12356 | 3.25% | 2085 | 55190 / 1/4 | 2026-09-05T11:03:17+00:00 |
| 06 | 000071 | BUDGET_STOP | RESCUE_MAX | HARD_STALL | 68 | 333 | 12475 | 2.67% | 1724 | 50760 / 1/4 | 2026-09-05T10:43:14+00:00 |

Pool roulante : seules les lanes exécutables sont planifiées; une lane `HARD_STALL` est conservée intacte mais ne consomme plus de runner. Une lane terminée libère automatiquement une place pour la suivante.

Chaque commit sur `maniements-v5-lane-XX` correspond à un PASS durable. `state/latest.zip` est le prédécesseur exact du PASS suivant.
