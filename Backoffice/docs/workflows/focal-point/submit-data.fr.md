---
id: submit-data
title: Soumettre des données de formulaire
description: Guide pour les points focaux pour remplir et soumettre des données de formulaire
roles: [focal_point, admin]
category: data-entry
keywords: [remplir formulaire, saisir données, soumettre, compléter mission, saisie données]
pages:
  - /
  - /forms/assignment
---

# Soumettre des données de formulaire

Ce flux de travail guide les points focaux pour remplir et soumettre des données de formulaire pour leurs missions.

## Prérequis

- Rôle de point focal requis
- Une mission active pour votre pays
- Données prêtes à saisir

## Étapes

### Étape 1 : Trouver votre mission sur le tableau de bord
- **Page** : `/`
- **Sélecteur** : `.bg-white.p-6.rounded-lg.shadow-md, .grid.gap-4`
- **Action** : Localisez votre formulaire assigné
- **Aide** : Votre tableau de bord affiche tous les formulaires qui vous sont assignés. Recherchez les formulaires avec le statut "En cours" ou "Non commencé". Cliquez sur un formulaire pour commencer à saisir des données.
- **Texte d'action** : Continuer

### Étape 2 : Ouvrir le formulaire de saisie de données
- **Page** : `/`
- **Sélecteur** : `a[href*="/forms/assignment/"], a[href*="view_edit_form"], .p-4.rounded-lg.shadow-md a`
- **Action** : Cliquez pour ouvrir le formulaire
- **Aide** : Cliquez sur le titre de la mission (mis en évidence ci-dessus) pour ouvrir le formulaire de saisie de données. La visite guidée continuera sur la page du formulaire.
- **Texte d'action** : Cliquez sur une mission

### Étape 3 : Naviguer dans les sections du formulaire
- **Page** : `/forms/assignment`
- **Sélecteur** : `#section-navigation-sidebar, .section-link`
- **Action** : Voir les sections disponibles
- **Aide** : Le formulaire est organisé en sections affichées dans la barre latérale gauche. Cliquez sur un nom de section pour y accéder. Chaque section affiche un indicateur d'achèvement.
- **Texte d'action** : Suivant

### Étape 4 : Remplir les champs requis
- **Page** : `/forms/assignment`
- **Sélecteur** : `#main-form-area, #sections-container`
- **Action** : Entrez vos données
- **Aide** : Remplissez chaque champ avec les données appropriées. Les champs requis sont marqués d'un astérisque (*). Vos modifications sont enregistrées automatiquement pendant que vous travaillez.
- **Texte d'action** : Suivant

### Étape 5 : Soumettre le formulaire
- **Page** : `/forms/assignment`
- **Sélecteur** : `button[value="submit"], #fab-submit-btn, button.bg-green-600`
- **Action** : Cliquez sur Soumettre
- **Aide** : Une fois tous les champs requis complétés, cliquez sur le bouton Soumettre vert pour finaliser vos données. Sur mobile, utilisez le bouton d'action flottant. Vous recevrez un message de confirmation.
- **Texte d'action** : Compris

## Enregistrer votre progression

- Vos données sont enregistrées automatiquement pendant que vous travaillez
- Vous pouvez partir et revenir à tout moment
- Recherchez l'indicateur "Dernière sauvegarde" pour confirmer les sauvegardes
- Utilisez "Enregistrer brouillon" pour enregistrer explicitement votre progression actuelle

## Conseils

- Rassemblez toutes vos données avant de commencer pour éviter les interruptions
- Utilisez les champs de commentaires pour documenter les sources de données
- Vérifiez les messages de validation attentivement avant de soumettre
- Vous pouvez modifier les données soumises si votre administrateur l'autorise
- Exportez votre soumission en PDF pour vos archives

## Flux de travail connexes

- [Voir les missions](view-assignments.md) - Voir toutes vos tâches en attente
