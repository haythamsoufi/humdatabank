# Exécuter un cycle de reporting (guide administrateur)

Utilisez ce guide lorsque vous devez exécuter un tour de collecte de bout en bout (de la préparation d'un modèle à l'exportation des données approuvées).

## Avant de commencer

- Vous avez besoin d'un accès **Administrateur** pour les modèles et les missions.
- Convenez en interne de :
  - le nom de la période de reporting (exemple : "2026 T1")
  - la liste des pays participants
  - ce que signifie "bonne qualité" (documents requis, attentes de validation)

## Étape 1 — Préparer le modèle

1. Ouvrez **Panneau d'administration** → **Gestion des formulaires et données** → **Gérer les modèles**.
2. Ouvrez le modèle que vous utiliserez.
3. Confirmez que le modèle est :
   - clair (libellés/texte d'aide)
   - pas trop strict (champs requis raisonnables)
   - cohérent (options de liste déroulante standardisées)
4. Si vous avez fait des modifications, testez avec une petite mission brouillon.

Astuce : Pour les modifications complexes, suivez [Générateur de formulaires (avancé)](form-builder-advanced.md).

## Étape 2 — Créer la mission

1. Ouvrez **Panneau d'administration** → **Gestion des formulaires et données** → **Gérer les missions**.
2. Cliquez sur **Créer** (ou similaire).
3. Sélectionnez :
   - le modèle
   - les pays (ou organisations) inclus
   - la date de début et la date limite
4. Ajoutez un court message d'instructions :
   - ce dont vous avez besoin
   - la date limite
   - qui contacter pour les questions

## Étape 3 — Confirmer l'accès (avant le lancement)

Pour chaque pays :
- Confirmez que les points focaux ont :
  - le rôle de mission correct (saisie de données)
  - l'accès au pays correct

Si vous attendez des documents justificatifs :
- Confirmez que les bons utilisateurs ont un rôle qui autorise les téléchargements (voir [Documents justificatifs (administrateur)](supporting-documents.md)).

## Étape 4 — Surveiller la progression pendant la collecte

Pendant la période ouverte, surveillez :
- non commencé
- en cours
- soumis
- en retard

Que faire lorsque la progression est faible :
- envoyer des rappels (courts + spécifiques)
- clarifier les champs confus (libellés/texte d'aide)
- prolonger la date limite si votre flux de travail le permet

## Étape 5 — Examiner et approuver les soumissions

1. Ouvrez la mission.
2. Examinez les soumissions pour :
   - les valeurs manquantes qui devraient exister
   - les valeurs aberrantes (valeurs bien en dehors de la plage attendue)
   - les documents requis (si applicable)
3. Approuvez les soumissions qui répondent au minimum de qualité.
4. Rouvrez/renvoyez les soumissions qui ont besoin de correction (avec une courte explication de ce qu'il faut corriger).

Astuce : Utilisez [Statuts de soumission et ce que vous pouvez faire](../common/submission-statuses-and-permissions.md) pour expliquer pourquoi "Modifier/Soumettre" est verrouillé/déverrouillé.

## Étape 6 — Exporter les données pour le reporting

1. Naviguez vers la page du formulaire d'entrée pour chaque mission/pays que vous voulez exporter :
   - Ouvrez la mission depuis **Gérer les missions**.
   - Cliquez sur un pays/entité pour ouvrir le formulaire d'entrée.
2. Utilisez les options d'export disponibles sur la page du formulaire d'entrée :
   - **Exporter le modèle Excel** (si activé) : Télécharge un fichier Excel avec la structure du formulaire et les données.
   - **Exporter PDF** (si activé) : Télécharge une version PDF du formulaire avec les données actuelles.
3. Enregistrez les fichiers exportés avec une convention de nommage cohérente :
   - `2026-Q1_TemplateName_CountryName.xlsx` (pour les exports de pays individuels)
   - Note : Les exports sont par pays/entité, pas pour tous les pays à la fois depuis la liste des missions.
4. Si vous avez besoin d'une analyse répétable, gardez les ID/codes dans l'export (ne les supprimez pas).

Pour des conseils d'interprétation, voir [Exports : comment interpréter les fichiers](exports-how-to-interpret.md).

## Étape 7 — Fermer et documenter les décisions

À la fin du cycle :
- Enregistrez tous les changements en milieu de cycle (prolongations de date limite, mises à jour de modèle).
- Enregistrez votre règle pour les doublons (surtout pour les soumissions publiques).
- Capturez les problèmes connus pour améliorer le prochain cycle.

## Problèmes courants

- **Un pays ne peut pas voir la mission** : les rôles et l'accès au pays sont manquants.
- **Les utilisateurs ne peuvent pas soumettre** : trop de champs requis ou validation stricte ; ajoutez du texte d'aide et réduisez les requis.
- **Les modifications de modèle ont causé de la confusion** : évitez les grandes modifications en milieu de cycle ; déployez via une nouvelle mission.
- **L'export ne correspond pas aux attentes** : confirmez que vous avez exporté la bonne mission et la bonne version du modèle.

## Liens connexes

- [Cycle de vie d'une mission](assignment-lifecycle.md)
- [Gérer les missions](manage-assignments.md)
- [Examiner et approuver les soumissions](review-approve-submissions.md)
- [Exporter et télécharger les données](export-download-data.md)
