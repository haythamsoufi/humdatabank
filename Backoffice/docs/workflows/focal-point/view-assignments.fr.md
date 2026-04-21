---
id: view-assignments
title: Voir vos missions
description: Guide pour les points focaux pour voir et gérer leurs missions en attente
roles: [focal_point, admin]
category: data-entry
keywords: [mes tâches, en attente, date limite, missions, tableau de bord, à faire]
pages:
  - /
---

# Voir vos missions

Ce flux de travail guide les points focaux pour voir leurs missions en attente et comprendre leurs tâches.

## Prérequis

- Rôle de point focal requis
- Assigné à au moins un pays

## Étapes

### Étape 1 : Accéder à votre tableau de bord
- **Page** : `/`
- **Sélecteur** : `.bg-white.p-6.rounded-lg.shadow-md, .grid.gap-4`
- **Action** : Voir votre tableau de bord
- **Aide** : Votre tableau de bord affiche toutes vos missions en attente. Chaque carte montre le nom du formulaire, la date d'échéance, le statut d'achèvement et le pourcentage de progression.
- **Texte d'action** : Suivant

### Étape 2 : Examiner les cartes de missions
- **Page** : `/`
- **Sélecteur** : `.p-4.rounded-lg.shadow-md, .bg-gray-50.border`
- **Action** : Examinez chaque mission
- **Aide** : Chaque carte de mission montre le nom du modèle, la période, la date d'échéance et le statut actuel. Les missions en retard ont une bordure rouge et un badge "En retard".
- **Texte d'action** : Suivant

### Étape 3 : Ouvrir une mission
- **Page** : `/`
- **Sélecteur** : `a[href*="/forms/assignment/"], .p-4.rounded-lg a`
- **Action** : Cliquez pour ouvrir le formulaire
- **Aide** : Cliquez sur le titre de la mission pour ouvrir le formulaire de saisie de données. Vous pouvez voir le pourcentage d'achèvement et le statut avant de cliquer.
- **Texte d'action** : Cliquez sur une mission

## Comprendre le statut de la mission

| Statut | Signification |
|--------|---------------|
| **En attente** | Pas encore commencé |
| **En cours** | Commencé mais non soumis |
| **Soumis** | Terminé et soumis |
| **En retard** | Date limite dépassée, non soumis |

## Conseils

- Vérifiez votre tableau de bord régulièrement pour les nouvelles missions
- Commencez tôt pour éviter les problèmes de dernière minute
- Votre progression est enregistrée automatiquement pendant que vous travaillez
- Vous pouvez contacter votre administrateur si vous avez des questions sur une mission
- Utilisez le panneau de notifications pour voir les mises à jour récentes

## Flux de travail connexes

- [Soumettre des données](submit-data.md) - Compléter et soumettre un formulaire
