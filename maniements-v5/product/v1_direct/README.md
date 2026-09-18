# MANIEMENTS V5 — Calcul direct V1

Premier pivot du produit vers un calcul à la demande.

## Principe

- l'utilisateur saisit deux mains exactes ;
- le runtime V5 gelé calcule directement la courbe de probabilités ;
- pour les objectifs non triviaux, le programme tente de matérialiser l'arbre exact de politique ;
- le résultat est mis en cache dans `direct_cache.sqlite` ;
- le résumé français automatique est affiché séparément et **n'est pas qualifié de maniement humain**.

La source de vérité est l'arbre exact, jamais la phrase générée.

## Démarrage Windows

Double-cliquer `START.bat`. Le programme choisit automatiquement un port local libre et ouvre le navigateur.

Ou :

```bash
python server.py --open
```

Puis tester par exemple :

- Main 1 : `ARX92`
- Main 2 : `765`

Dans cette V1, `X` signifie 10 et les petites cartes doivent être données exactement.
Le support du `x` générique sera ajouté après validation de la voie de calcul direct.
