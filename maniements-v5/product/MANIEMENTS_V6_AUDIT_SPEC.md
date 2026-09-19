# MANIEMENTS V6 — AUDIT ET CAHIER DES CHARGES PRODUIT

Date: 2026-09-19

## 1. But produit

Pour une combinaison de couleur donnée, le produit doit raisonner par objectif de levées.

Exemple:
- Main 1: AKT92 (affichage français ARX92)
- Main 2: 765

Le produit doit:
1. calculer la probabilité optimale de faire au moins N levées;
2. générer plusieurs maniements complets et nommables plausibles;
3. rejouer exhaustivement chaque maniement contre toutes les distributions et toutes les défenses légales;
4. calculer la probabilité exacte de chaque maniement;
5. décrire exactement les distributions contre lesquelles chaque maniement réussit/échoue;
6. comparer les maniements pour l'objectif N;
7. recommencer indépendamment pour N-1, N-2, etc.;
8. arrêter les explications sous le plus grand objectif garanti à 100%.

Le solveur exact est la référence. Le texte humain n'est jamais une source de vérité.

## 2. Audit du solveur exact existant

Runtime gelé:
a0b580531f3c9e8bb00710b9c3e1c183b27cbfe9231c9d584e29a374ba88835d

integrated_engine.Engine2(north, south, target):
- target signifie bien au moins target levées;
- les états du déclarant sont publics: cartes restantes, cartes adverses déjà vues, chicanes révélées, levées gagnées;
- les allocations adverses cachées ne sont pas dans la clé de décision;
- la stratégie ne peut donc pas voir les cartes cachées;
- chaque action adverse légale est traitée comme une branche: une stratégie n'est gagnante dans une distribution que si elle résiste à toute défense légale;
- WorldModel.weight() utilise les poids combinatoires exacts compatibles avec 13 cartes par adversaire.

Conclusion: le solveur exact est réutilisable tel quel comme oracle de probabilité et de validation.

### Hypothèse importante

À chaque nouveau tour de couleur, Engine2 autorise un départ depuis Main 1 ou Main 2. Le modèle est donc un modèle de maniement de couleur avec communications extérieures disponibles (entry-neutral), ce qui est la convention adaptée à un outil de suit combinations.

Cette hypothèse doit être affichée/documentée. Une éventuelle version future pourra ajouter des contraintes de rentrée, mais elle ne doit pas polluer le produit initial.

## 3. Vérification sur ARX92 / 765

Courbe exacte actuelle:
- 5 levées: 507/2300 = 22.043478 %
- 4 levées: 103/115 = 89.565217 %
- 3 levées: 451/460 = 98.043478 %
- 2 levées: 1/1 = 100 %

Donc l'interface normale doit expliquer 5, 4 et 3 levées, puis s'arrêter:
"2 levées sont assurées."

Analyse du premier coup par l'oracle:
- objectif 5:
  - commencer depuis Main 2: 507/2300 = 22.043478 %
  - commencer par As ou Roi de Main 1: 52/575 = 9.043478 %
- objectif 4:
  - commencer depuis Main 2: 103/115 = 89.565217 %
  - commencer par As ou Roi: 403/460 = 87.608696 %
- objectif 3:
  - tous les premiers coups testés atteignent 451/460 = 98.043478 %

Pour 5 levées, le masque de succès du départ direct depuis Main 2 est exactement:
Dame et Valet réunis chez l'adversaire en deuxième, avec une longueur de couleur <= 4.
Sa probabilité vaut exactement 507/2300.

Cela confirme que l'oracle et les masques de mondes peuvent produire exactement le type d'explication demandé par le produit.

## 4. Ce qui existe déjà et est réutilisable

### A. Oracle optimal
integrated_engine.py
À conserver.

### B. Évaluation exacte d'un maniement imposé
human_motif_search_v57.evaluate() et familles dérivées.

Principe:
- un programme de maniement choisit les cartes du déclarant;
- toutes les réponses adverses légales sont explorées;
- la fonction retourne le masque exact des distributions gagnantes et sa probabilité exacte.

C'est exactement la brique nécessaire pour comparer deux maniements.

### C. Générateurs de maniements
Déjà disponibles sous plusieurs formes:
- PLAY_TOP
- FINESSE_SEQUENCE
- CASH_THEN_FINESSE_SEQUENCE
- repeated finesse
- honor probe / safety variants
- DROP_SWITCH
- SAFETY_FORCE
- PROGRESSIVE_SHORTAGE

Ces modules sont des prototypes précieux mais doivent être unifiés derrière une même interface.

### D. Explication des distributions gagnantes
human_layout_reason_v58.py, human_layout_reason_v581.py, human_world_reason_v58.py.

Ils savent déjà:
- travailler à partir du masque exact de distributions gagnantes;
- rechercher des formules exactes en termes de placement, longueur, partage, honneurs réunis/séparés;
- refuser une explication si aucune formule courte exacte n'est trouvée.

C'est également la bonne architecture.

## 5. Ce qui était faux dans l'ancienne architecture

### A. Filtre seulement-si-optimal

Les anciens analyze() font typiquement:
if prob != opt: continue

Donc un maniement humain parfaitement légitime mais inférieur à l'optimum est jeté.

C'est incompatible avec le produit souhaité.

Nouveau principe:
on conserve chaque maniement distinct et sa probabilité, puis on les compare.

### B. Sélection d'une seule politique optimale brute

Le calculateur direct V1 affiche la politique optimale du solveur.

Cette politique est une preuve, pas une explication de bridge.

Elle reste disponible en diagnostic, mais ne doit plus être l'objet principal affiché.

### C. Texte avant modèle sémantique sûr

Toute phrase libre dérivée d'un spec approximatif peut mentir sur les cartes réellement disponibles.

Nouveau principe:
programme de maniement structuré -> rejeu exact -> masque de succès -> explication -> français.

Jamais l'inverse.

## 6. Nouvelle architecture cible

### Couche 1 — ExactObjectiveOracle
Entrée: deux mains exactes + objectif N.
Sortie: probabilité optimale exacte, masque optimal, politique technique de preuve.

### Couche 2 — ManeuverGenerator
Génère des programmes structurés:
- jeu en tête;
- coup de sonde puis suite conditionnelle;
- impasse simple;
- impasse répétée;
- double impasse;
- laisser courir;
- couvrir au plus juste;
- jeu de sécurité;
- variantes conditionnelles selon chute d'un honneur, chicane, etc.

Chaque candidat a un identifiant canonique, un nom de motif, un programme exécutable et une complexité humaine.

### Couche 3 — ManeuverEvaluator
Pour chaque objectif N et chaque candidat:
- rejeu exhaustif;
- probabilité exacte;
- masque exact des distributions gagnantes;
- signature de comportement.

Aucun candidat n'est supprimé parce qu'il est sous-optimal.

### Couche 4 — ManeuverDeduplicator
Regroupement:
- même programme/comportement -> un représentant;
- même masque de succès -> un représentant simple + variantes équivalentes;
- même probabilité mais masques différents -> conserver séparément.

### Couche 5 — LayoutExplainer
À partir du masque exact:
- produit une formule exacte lisible;
- idéalement une union de cas disjoints;
- calcule le pourcentage de chaque cas;
- vérifie que l'union des cas est exactement le masque de succès.

À ajouter à l'ancien langage d'atomes:
- honneur sec/second/...
- paire d'honneurs dans la même main;
- paire d'honneurs dans une main de longueur <= k / >= k;
- longueur adverse <= k / >= k;
- deux honneurs placés / mal placés;
- unions disjointes de cas.

### Couche 6 — ObjectiveReport
Pour chaque objectif non trivial:
- probabilité oracle optimale;
- tableau des maniements pertinents;
- probabilité exacte de chacun;
- cas gagnants exacts;
- marque optimal si probabilité = oracle;
- écart en points de pourcentage par rapport au meilleur.

Les objectifs sont traités indépendamment.

### Couche 7 — HumanRenderer
Le français décrit uniquement des objets structurés déjà certifiés.

## 7. Règles d'affichage

Soit:
guaranteed = max(target tel que P(target)=100%)
possible = max(target tel que P(target)>0)

Afficher seulement:
possible, possible-1, ..., guaranteed+1

Puis une ligne:
guaranteed levées sont assurées.

Ne pas expliquer les objectifs déjà garantis.

## 8. Critères de certification

Un maniement peut être affiché comme certifié uniquement si:
1. son programme est exécutable sur toutes les branches atteintes;
2. son rejeu exhaustif termine;
3. le masque de succès et la probabilité sont exacts;
4. son texte procédural est généré à partir du programme, sans carte impossible;
5. l'explication des répartitions, si affichée comme exacte, recompose exactement le masque de succès.

Un maniement est optimal uniquement si candidate_probability == oracle_probability.

## 9. Cache

La base pré-calculée n'est plus une condition de disponibilité.

Cache recommandé:
runtime_sha + normalized_hands + target + candidate_registry_version

Stocker:
- courbe oracle;
- candidats évalués;
- masques/signatures;
- explications certifiées.

## 10. Ordre de développement

1. créer une API unifiée de programme de maniement;
2. porter V57/V591/V512/V513/V514 dans un registre commun;
3. modifier le pipeline pour conserver toutes les probabilités;
4. dédupliquer les candidats;
5. enrichir LayoutExplainer avec <= k, >= k, paire+longueur et DNF disjointe;
6. construire ObjectiveReport;
7. brancher le calculateur direct dessus;
8. ajouter x générique seulement après validation sur cartes exactes;
9. ajouter progressivement d'autres familles de maniements.

## 11. Cas de régression obligatoires

ARX92 / 765:
- objectifs affichés: 5,4,3; 2 assuré;
- 5 levées: oracle 507/2300;
- départ direct Main 2: 507/2300;
- départ As/Roi: 52/575.

AR98 / VX2:
- ne jamais produire une procédure qui réutilise une petite carte disparue;
- toute phrase doit être dérivée du programme exécutable.

Plus une batterie de cas:
- impasse simple;
- impasse répétée;
- double impasse;
- coup de sonde;
- honneur sec;
- jeu de sécurité;
- choix différent selon objectif N.

## 12. Invariants de produit

- aucune dépendance à une base exhaustive;
- aucun classement fondé sur une heuristique: la probabilité décide;
- aucune explication de répartition approximative marquée exacte;
- aucun texte humain non rejouable;
- l'objectif N est toujours traité indépendamment;
- l'arbre brut du solveur reste diagnostic, jamais interface principale.
