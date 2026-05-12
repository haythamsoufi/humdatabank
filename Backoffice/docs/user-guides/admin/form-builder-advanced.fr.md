# Générateur de formulaires (avancé) : types de champs, validation et modifications sûres

Utilisez ce guide lorsque vous devez concevoir des modèles qui sont cohérents entre les pays et faciles à soumettre.

## Avant de commencer

- Vous avez besoin d'un accès **Administrateur** avec des permissions de modèle.
- Si le modèle est déjà utilisé dans des missions actives, préférez des **modifications petites et sûres** et testez soigneusement.

## Comment choisir le bon type de champ

### Texte

Utilisez pour les noms, les courtes descriptions et les réponses "expliquer pourquoi".

Bons exemples :
- "Décrivez le défi principal (1-2 phrases)"

Évitez :
- Utiliser du texte pour les nombres ("10") ou les dates ("Jan 2026") lorsque vous pouvez utiliser un champ structuré.

### Nombre

Utilisez pour les comptages, totaux et quantités.

Bons exemples :
- "Total des bénévoles (nombre)"
- "Budget (monnaie locale)"

Conseils :
- Décidez à l'avance si vous acceptez les décimales.
- Soyez explicite sur les unités dans le libellé (par exemple "(personnes)", "(CHF)").

### Date

Utilisez lorsque la valeur est une date, pas un commentaire.

Conseils :
- Si vous avez besoin d'une période (début/fin), utilisez deux champs de date avec des libellés clairs.

### Choix unique (liste déroulante / bouton radio)

Utilisez lorsque les réponses doivent être cohérentes entre les pays.

Conseils :
- Gardez les libellés d'options courts.
- Évitez les significations qui se chevauchent (par exemple "Partiellement" vs "Quelque peu").

### Sélection multiple

Utilisez lorsque plusieurs options peuvent s'appliquer.

Conseils :
- Ajoutez une option "Autre (préciser)" seulement si vous en avez vraiment besoin, et associez-la à un champ texte.

### Matrice / tableau (lignes répétées)

Utilisez lorsque la même mesure est collectée entre plusieurs catégories (lignes).

Bon exemple :
- Lignes : "Femmes", "Hommes", "Filles", "Garçons"
- Colonnes : "Personnes atteintes"

Meilleures pratiques :
- Gardez la matrice petite (les utilisateurs ont du mal avec les tableaux très larges).
- Assurez-vous que chaque libellé de ligne est sans ambiguïté.
- Préférez les champs numériques dans les matrices lorsque vous attendez des totaux et une validation.

## Validation et champs requis (ce qui bloque la soumission)

### Champs requis

Marquez un champ comme **requis** uniquement lorsque vous ne pouvez pas accepter une soumission sans lui.

Si les utilisateurs sont souvent bloqués à **Soumettre** :
- Réduisez les champs requis, surtout dans les formulaires longs.
- Ajoutez du texte d'aide pour expliquer à quoi ressemble "assez bon".

### Règles de validation courantes (si disponibles)

Si votre Générateur de formulaires les prend en charge, utilisez des règles de validation pour éviter les erreurs courantes :
- Nombre minimum/maximum (par exemple "doit être ≥ 0")
- Formats autorisés (par exemple année)
- Cellules de matrice requises (seulement si nécessaire)

Astuce : Si les règles de validation sont strictes, les utilisateurs auront besoin de libellés et d'exemples plus clairs.

## Logique conditionnelle (quand l'utiliser)

Si votre Générateur de formulaires prend en charge l'affichage conditionnel (afficher/masquer les champs) :
- Utilisez-le pour réduire l'encombrement (posez des questions de suivi seulement si nécessaire).
- Évitez les arbres de branchement profonds ; ils sont difficiles à tester et faciles à casser.

Ajoutez toujours du texte d'aide sur la question "parent" pour que les utilisateurs comprennent pourquoi les suivis apparaissent.

## Versioning de modèle et modifications "sûres vs risquées"

### Modifications sûres (généralement OK pendant une collecte en direct)

- Corriger les fautes de frappe et la formulation dans les libellés/texte d'aide
- Réorganiser les sections/champs (lorsque cela ne change pas la signification)
- Ajouter un nouveau champ optionnel

### Modifications risquées (peuvent casser les comparaisons ou confondre les utilisateurs)

- Changer un type de champ (texte → nombre, liste déroulante → sélection multiple)
- Changer la signification d'une question mais garder le même libellé
- Supprimer des champs (peut supprimer le contexte historique)
- Changer les règles requises en milieu de collecte

Approche recommandée pour les modifications risquées :
1. Créez un nouveau brouillon/version (si pris en charge).
2. Testez sur une petite mission (un pays).
3. Déployez via une nouvelle mission (préféré) et communiquez le changement.

## Liaison à la Banque d'indicateurs (règles pratiques)

Lie une question à un indicateur lorsque vous avez besoin de :
- définitions standardisées
- reporting cohérent entre les pays

Évitez :
- Lier différentes questions au même indicateur sauf si elles représentent vraiment la même mesure.
- Forcer les noms techniques d'indicateurs dans les libellés orientés utilisateur (gardez les libellés lisibles par l'homme).

## Plan de test (liste de contrôle rapide)

Avant de publier/utiliser un modèle :
- Complétez le formulaire vous-même en tant que point focal.
- Confirmez que les champs requis sont raisonnables.
- Essayez de soumettre avec des erreurs intentionnelles (requis manquant, mauvais formats).
- Exportez une soumission de test et confirmez que les colonnes de données ont du sens.

## Problèmes courants

- **Les points focaux ne peuvent pas soumettre** : trop de champs requis ou validation stricte ; ajoutez du texte d'aide et réduisez les requis.
- **Les données sont incohérentes entre les pays** : les options de liste déroulante ne sont pas claires ; resserrez les définitions et liez aux indicateurs où c'est approprié.
- **La mauvaise version de modèle est utilisée** : les missions peuvent être liées à des versions plus anciennes ; créez une nouvelle mission lors du déploiement de changements majeurs.

## Liens connexes

- [Modifier un modèle (Générateur de formulaires)](edit-template.md)
- [Créer un modèle de formulaire](create-template.md)
- [Cycle de vie d'une mission](assignment-lifecycle.md)
- [Dépannage (Point focal)](../focal-point/troubleshooting.md)
