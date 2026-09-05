# MANIEMENTS V5 — PASS/ORBIT cloud runner

Ce dossier héberge le pilote cloud gratuit sur GitHub Actions pour les lanes 00 à 06.

- Runtime frozen/orchestration V2 : contenu byte-identique au ZIP qualifié SHA-256 `a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d`, vérifié par `SHA256SUMS.txt`.
- Le solveur et le générateur frozen ne sont pas modifiés.
- Une PASS calcule environ 20 minutes (`1320 s` budget total, `120 s` réservées à la fermeture).
- Chaque lane possède une branche durable `maniements-v5-lane-XX`.
- Après chaque PASS, `state/latest.zip` est vérifié puis committé. Le commit Git est la version durable.
- Le workflow enchaîne plusieurs PASS dans un même job, puis se redéclenche automatiquement avant la limite de durée GitHub.
- `STATUS.md` contient l’avancement agrégé.

Pour suspendre la relance automatique, créer le fichier `maniements-v5/STOP` sur `main`. La passe en cours termine proprement avant l’arrêt du cycle suivant.

Le pilote GitHub démarre sur une lignée cloud propre à PASS000000 pour les 7 lanes. Les anciens PASS de la Library sont conservés séparément comme preuves/audits et ne sont pas écrasés.
