---
id: create-assignment
title: Créer une nouvelle mission
description: Guide pour créer une nouvelle mission de formulaire pour distribuer des modèles aux pays
roles: [admin]
category: assignment-management
keywords: [créer mission, assigner formulaire, distribuer, tâche, date limite, assignation pays, nouvelle mission]
pages:
  - /admin/assignments
  - /admin/assignments/new
---

# Créer une nouvelle mission

Ce flux de travail guide les administrateurs dans la création d'une nouvelle mission de formulaire pour distribuer des modèles aux pays et aux points focaux.

## Prérequis

- Rôle d'administrateur requis
- Au moins un modèle de formulaire actif avec une version publiée
- Pays configurés dans le système

## Étapes

### Étape 1 : Naviguer vers la gestion des missions
- **Page** : `/admin/assignments`
- **Sélecteur** : `a[href="/admin/assignments/new"], .create-assignment-btn`
- **Action** : Cliquez sur "Créer une mission"
- **Aide** : La page Missions affiche toutes les missions actuelles et passées. Cliquez sur "Créer une mission" pour distribuer un formulaire aux pays.
- **Texte d'action** : Continuer

### Étape 2 : Sélectionner le modèle
- **Page** : `/admin/assignments/new`
- **Sélecteur** : `#template-select, select[name="template"]`
- **Action** : Choisissez le modèle de formulaire à assigner
- **Aide** : Sélectionnez le modèle de formulaire que vous voulez distribuer. Seuls les modèles actifs avec des versions publiées apparaissent dans cette liste.
- **Texte d'action** : Suivant

### Étape 3 : Sélectionner les pays
- **Page** : `/admin/assignments/new`
- **Sélecteur** : `#country-select, .country-selection`
- **Action** : Choisissez les pays qui recevront la mission
- **Aide** : Sélectionnez un ou plusieurs pays pour recevoir cette mission. Vous pouvez sélectionner tous les pays ou en choisir des spécifiques.
- **Texte d'action** : Suivant

### Étape 4 : Définir le nom de période
- **Page** : `/admin/assignments/new`
- **Sélecteur** : `#period-name, input[name="period_name"]`
- **Action** : Entrez un nom de période pour cette mission
- **Aide** : Donnez à cette mission un nom de période descriptif (par exemple "Collecte de données T1 2024" ou "Rapport annuel 2024"). Cela aide à identifier la mission plus tard.
- **Texte d'action** : Suivant

### Étape 5 : Définir la date limite
- **Page** : `/admin/assignments/new`
- **Sélecteur** : `#deadline-input, input[type="date"], .deadline-picker`
- **Action** : Définissez la date limite de soumission
- **Aide** : Choisissez une date limite pour la soumission des données. Les points focaux verront cette date limite et recevront des rappels à l'approche.
- **Champs** :
  - Date limite (requis) : Quand les soumissions sont dues
  - Paramètres de rappel : Configurez les rappels automatiques

### Étape 6 : Ajouter des instructions
- **Page** : `/admin/assignments/new`
- **Sélecteur** : `#instructions, textarea[name="instructions"]`
- **Action** : Ajoutez des instructions spécifiques à la mission
- **Aide** : Fournissez toutes instructions spéciales ou contexte pour cette mission. Ce message sera affiché aux points focaux.
- **Texte d'action** : Suivant

### Étape 7 : Configurer l'URL publique (Optionnel)
- **Page** : `/admin/assignments/new`
- **Sélecteur** : `#generate-public-url, input[name="generate_public_url"]`
- **Action** : Activez l'URL publique si nécessaire
- **Aide** : Si vous voulez autoriser les soumissions publiques sans connexion, cochez cette option. Vous pouvez activer ou désactiver l'URL publique plus tard.
- **Texte d'action** : Suivant

### Étape 8 : Examiner et créer
- **Page** : `/admin/assignments/new`
- **Sélecteur** : `button[type="submit"], .create-btn`
- **Action** : Créez la mission
- **Aide** : Examinez les détails de la mission et cliquez sur "Créer une mission". Les points focaux seront notifiés et verront la nouvelle tâche dans leur tableau de bord.
- **Texte d'action** : Compris

## Conseils

- Définissez des dates limites réalistes en tenant compte des fuseaux horaires et des vacances
- Utilisez des instructions claires et spécifiques dans les messages de mission
- Choisissez un nom de période descriptif qui facilite l'identification de la mission plus tard
- Seuls les modèles avec des versions publiées peuvent être assignés
- Vous pouvez ajouter plus de pays à une mission après création en la modifiant

## Flux de travail connexes

- [Gérer les missions](manage-assignments.md) - Voir, modifier et gérer les missions existantes
- [Créer un modèle](create-template.md) - Concevoir des formulaires avant de les assigner
- [Voir les missions](../focal-point/view-assignments.md) - Perspective du point focal
