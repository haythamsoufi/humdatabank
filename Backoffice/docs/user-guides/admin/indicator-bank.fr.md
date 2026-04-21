# Banque d'indicateurs (guide administrateur)

Utilisez ce guide si vous gérez des définitions d'indicateurs standard et voulez un reporting cohérent entre les modèles et les missions.

## Qu'est-ce que la Banque d'indicateurs

La **Banque d'indicateurs** est une bibliothèque d'indicateurs standardisés (noms, définitions et parfois règles de calcul). Lier les champs de formulaire aux indicateurs aide à maintenir la cohérence des données entre :

- les pays
- les périodes temporelles
- les différents modèles

## Quand lier un champ à un indicateur

Lie un champ de formulaire à un indicateur lorsque :

- vous voulez que la même mesure soit rapportée de la même manière partout
- vous prévoyez d'exporter et de comparer les données entre les pays/périodes
- vous voulez une définition stable qui ne change pas avec la formulation locale

Ne liez pas lorsque :

- le champ est du texte purement opérationnel (notes, explications libres)
- la question est temporaire ou spécifique à une mission

## Bonnes pratiques

- Gardez les définitions d'indicateurs stables dans le temps.
- Si vous devez changer la signification, créez un nouvel indicateur plutôt que de "réutiliser" l'ancien.
- Utilisez des unités cohérentes (personnes, ménages, pourcentage, etc.).
- Rendez les libellés de champs conviviaux même si les noms d'indicateurs sont techniques.

## Dépannage

- **Les exports semblent incohérents** : confirmez que les modèles sont liés aux bons indicateurs et que les définitions d'indicateurs n'ont pas changé en milieu de période.
- **Plusieurs champs liés au même indicateur** : vérifiez s'ils représentent la même mesure ; sinon, divisez en indicateurs séparés.

## Liens connexes

- [Créer un modèle de formulaire](create-template.md)
- [Modifier un modèle de formulaire (Générateur de formulaires)](edit-template.md)
