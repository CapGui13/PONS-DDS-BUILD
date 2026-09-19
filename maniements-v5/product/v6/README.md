# MANIEMENTS V6.0 — comparateur de maniements

Prototype de validation de la nouvelle architecture.

Pour chaque objectif non garanti, il:
- calcule l'optimum exact avec le solveur gelé;
- génère plusieurs familles de maniements structurés;
- rejoue exhaustivement chaque maniement;
- conserve aussi les maniements sous-optimaux;
- déduplique les comportements ayant exactement le même masque de réussite;
- marque comme optimal uniquement un maniement qui égale exactement l'oracle;
- tente une explication exacte des répartitions gagnantes.

Le cas de régression initial est ARX92 / 765:
5, 4 et 3 levées sont comparées; 2 levées sont garanties.

Cette V6.0 est un prototype de moteur de comparaison. Les phrases procédurales restent provisoires.
