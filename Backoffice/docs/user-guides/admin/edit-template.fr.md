# Modifier un modèle de formulaire (Générateur de formulaires)

Utilisez ce guide lorsque vous devez mettre à jour un modèle existant (les questions et sections que les points focaux rempliront).

## Avant de commencer

- Vous avez besoin d'un accès **Administrateur** avec des permissions de modèle.
- Confirmez si le modèle est déjà utilisé (a des missions actives).
- Décidez du type de changement dont vous avez besoin :
  - **Sûr** : corrections de libellé/texte d'aide, ajout de champs optionnels, réorganisation des sections.
  - **Risqué** : changer les types de champs, changer les règles requises, supprimer des champs (peut casser la cohérence entre les pays).

## Ouvrir le modèle

1. Ouvrez **Panneau d'administration** → **Gestion des formulaires et données** → **Gérer les modèles**.
2. Trouvez le modèle et ouvrez-le.
3. Si le système affiche plusieurs versions (brouillon/publié), commencez par le **dernier brouillon** (ou créez une nouvelle version brouillon si nécessaire).

## Modifications courantes (étape par étape)

### Ajouter une nouvelle section

1. Cliquez sur **Ajouter une section**.
2. Donnez à la section un nom clair (cela devient un élément de navigation pour les points focaux).
3. Enregistrez.

### Ajouter un nouveau champ

1. Ouvrez la section où vous voulez le champ.
2. Cliquez sur **Ajouter un champ**.
3. Choisissez le type de champ (texte/nombre/date/liste déroulante, etc.).
4. Définissez le **libellé** (exactement ce que les utilisateurs verront).
5. Si disponible, ajoutez un **texte d'aide** (une courte phrase).
6. Définissez **Requis** uniquement lorsque c'est vraiment nécessaire.
7. Enregistrez.

### Mettre à jour un libellé ou un texte d'aide

1. Ouvrez le champ.
2. Changez le libellé/texte d'aide pour correspondre au sens que vous voulez.
3. Enregistrez.

### Réorganiser les sections ou les champs

1. Utilisez la poignée de glissement (ou les contrôles de déplacement) pour réorganiser.
2. Enregistrez.

## Types de champs (quoi choisir)

- **Texte** : noms, notes, courtes explications.
- **Nombre** : comptages et quantités. Préférez le nombre lorsque vous avez besoin de totaux ou de validation.
- **Date** : dates (pas de texte libre).
- **Liste déroulante / choix unique** : lorsque les réponses doivent être cohérentes entre les pays.
- **Sélection multiple** : lorsque plusieurs réponses peuvent s'appliquer.
- **Matrice / tableau** (si disponible) : valeurs répétées entre catégories. Utilisez lorsque les utilisateurs doivent entrer la même mesure pour plusieurs lignes.

## Validation et champs requis

- Marquez un champ comme **requis** uniquement lorsqu'il doit être présent pour qu'une soumission soit utilisable.
- Si les utilisateurs sont souvent bloqués à **Soumettre**, réduisez les champs requis ou ajoutez des instructions plus claires.
- Lorsque vous changez les règles de validation, testez d'abord l'impact avec une petite mission.

## Liaison à la Banque d'indicateurs (si applicable)

Si votre flux de travail utilise la **Banque d'indicateurs** :

- Liez un champ à un indicateur lorsque vous avez besoin de définitions standardisées et de rapports cohérents.
- Gardez le libellé du champ convivial, même si le nom de l'indicateur est technique.
- Évitez de lier plusieurs questions différentes au même indicateur sauf si elles représentent vraiment la même mesure.

## Publication et test

1. Enregistrez vos modifications de brouillon.
2. Si votre système nécessite une publication, **publiez** la nouvelle version.
3. Créez une petite mission de test (un pays) et complétez-la vous-même.
4. Corrigez les libellés confus et supprimez les champs requis inutiles.

## Problèmes courants

- **Mes modifications n'apparaissent pas pour les points focaux** : la version du modèle peut ne pas être publiée ou la mission peut utiliser une version publiée plus ancienne.
- **Les utilisateurs ne peuvent pas soumettre après ma modification** : un champ requis ou une nouvelle validation bloque la soumission—testez le formulaire en tant que point focal.
- **Les données semblent incohérentes entre les pays** : évitez de changer les types de champs/signification en milieu de collecte ; créez un nouveau modèle/version et communiquez le changement.

## Liens connexes

- [Créer un modèle de formulaire](create-template.md)
- [Créer une nouvelle mission](create-assignment.md)
- [Gérer les missions](manage-assignments.md)
- [Soumettre des données de formulaire (Point focal)](../focal-point/submit-data.md)
- [Générateur de formulaires (avancé)](form-builder-advanced.md)
