# MANIEMENTS V5 — Product V0

Première version fonctionnelle du cache exact P1.

## Ce que fait V0

- consolide les **20 branches durables P1** dans un snapshot SQLite unique ;
- vérifie les invariants de comptage (`2 × completed_orbits`, différés, absence de chevauchement) ;
- indexe chaque position ordonnée par `state_id` ;
- distingue `EXACT`, `DEFERRED`, `ACTIVE`, `PENDING` et `OUTSIDE_P1` ;
- permet une requête immédiate `Nord / Sud` en CLI ;
- fournit une petite interface web locale.

Les résultats `EXACT` sont ceux déjà produits par le runtime V5 gelé. V0 **ne recalcule et n'approxime rien**.

## Démarrage rapide

Dans le ZIP produit par GitHub Actions :

```bash
python server.py
```

Puis ouvrir `http://127.0.0.1:8765`.

Exemple CLI :

```bash
python query.py --db maniements_v5_p1_v0.sqlite --north 42 --south 653
python query.py --db maniements_v5_p1_v0.sqlite --north J963 --south AQ2 --json
```

`10` et `T` sont tous les deux acceptés.

## Limite volontaire de V0

Le cache P1 actuel stocke la **courbe exacte** et les empreintes SHA-256 des politiques, mais pas encore un objet de ligne de jeu directement navigable dans le snapshot. La prochaine étape produit est le **replay/reconstruction de politique** puis son affichage coup par coup.

Aucun résultat différé n'est remplacé par une approximation.
