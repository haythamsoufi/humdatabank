---
id: create-template
title: Créer un modèle de formulaire
description: Guide pour créer un nouveau modèle de formulaire avec sections et champs
roles: [admin]
category: template-management
keywords: [nouveau modèle, générateur de formulaires, créer formulaire, concevoir formulaire, construire modèle]
pages:
  - /admin/templates
  - /admin/templates/new
---

# Créer un modèle de formulaire

Ce flux de travail guide les administrateurs dans la création d'un nouveau modèle de formulaire en utilisant le générateur de formulaires.

## Prérequis

- Rôle d'administrateur requis
- Accès à la section Gestion des formulaires et données
- Compréhension des données que vous voulez collecter

## Étapes

### Étape 1 : Naviguer vers la gestion des modèles
- **Page** : `/admin/templates`
- **Sélecteur** : `a[href="/admin/templates/new"], .create-template-btn`
- **Action** : Cliquez sur "Créer un modèle"
- **Aide** : Cliquez sur le bouton "Créer un modèle" pour commencer à construire un nouveau modèle de formulaire.
- **Texte d'action** : Continuer

### Étape 2 : Définir les détails du modèle
- **Page** : `/admin/templates/new`
- **Sélecteur** : `#template-details, .template-info-panel`
- **Action** : Entrez le nom et la description du modèle
- **Aide** : Donnez à votre modèle un nom clair et descriptif et ajoutez une description expliquant son objectif. Cela aide les utilisateurs à comprendre à quoi sert le formulaire.
- **Champs** :
  - Nom du modèle (requis) : Nom clair et descriptif
  - Description : Expliquez l'objectif du modèle
  - Accès au modèle : Choisissez qui peut voir/modifier ce modèle (propriétaire et administrateurs partagés)

### Étape 3 : Ajouter des sections
- **Page** : `/admin/templates/new`
- **Sélecteur** : `.add-section-btn, [data-action="add-section"]`
- **Action** : Cliquez sur "Ajouter une section"
- **Aide** : Les sections organisent votre formulaire en groupes logiques. Ajoutez une section pour chaque sujet ou catégorie de questions.
- **Texte d'action** : Suivant

### Étape 4 : Configurer la section
- **Page** : `/admin/templates/new`
- **Sélecteur** : `.section-config, .section-panel`
- **Action** : Nommez la section et configurez les paramètres
- **Aide** : Donnez à chaque section un titre et une description optionnelle. Vous pouvez également définir des conditions de visibilité et des permissions.
- **Champs** :
  - Titre de la section (requis) : Nom pour cette section
  - Description : Instructions optionnelles pour les utilisateurs
  - Repliable : Si les utilisateurs peuvent replier la section

### Étape 5 : Ajouter des éléments de formulaire
- **Page** : `/admin/templates/new`
- **Sélecteur** : `.add-item-btn, [data-action="add-item"]`
- **Action** : Ajoutez des champs à la section
- **Aide** : Ajoutez des éléments de formulaire comme des champs texte, nombres, listes déroulantes et plus. Liez les éléments aux indicateurs de la Banque d'indicateurs pour une collecte de données standardisée.
- **Texte d'action** : Suivant

### Étape 6 : Configurer les éléments de formulaire
- **Page** : `/admin/templates/new`
- **Sélecteur** : `.item-config, .form-item-panel`
- **Action** : Configurez chaque élément de formulaire
- **Aide** : Définissez le libellé, le type de champ, les règles de validation et liez à un indicateur si applicable. Les champs requis doivent être remplis par les utilisateurs.
- **Champs** :
  - Libellé (requis) : Question ou libellé de champ
  - Type de champ : Texte, Nombre, Date, Liste déroulante, etc.
  - Requis : Si ce champ doit être rempli
  - Indicateur : Lien vers la Banque d'indicateurs pour la standardisation

### Étape 7 : Aperçu et enregistrement
- **Page** : `/admin/templates/new`
- **Sélecteur** : `button[type="submit"], .save-template-btn`
- **Action** : Enregistrez le modèle
- **Aide** : Examinez la structure de votre modèle dans l'aperçu, puis cliquez sur "Enregistrer le modèle" pour le créer. Vous pouvez modifier le modèle plus tard si nécessaire.
- **Texte d'action** : Compris

## Conseils

- Utilisez la Banque d'indicateurs pour lier les champs aux indicateurs standardisés
- Groupez les questions connexes en sections pour une meilleure organisation
- Ajoutez des descriptions pour aider les utilisateurs à comprendre ce qu'il faut entrer
- Testez le modèle en créant une mission de test avant le déploiement
- Les modèles peuvent être dupliqués pour créer des variations

## Flux de travail connexes

- [Gérer les missions](manage-assignments.md) - Assigner des modèles aux pays
