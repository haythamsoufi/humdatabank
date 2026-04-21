---
id: manage-assignments
title: Gérer les missions
description: Guide pour voir, modifier et gérer les missions de formulaires existantes
roles: [admin]
category: assignment-management
keywords: [modifier mission, voir missions, surveiller progression, prolonger date limite, supprimer mission, statut mission]
pages:
  - /admin/assignments
  - /admin/assignments/edit
---

# Gérer les missions

Ce flux de travail guide les administrateurs pour voir, modifier et gérer les missions de formulaires existantes aux pays et aux points focaux.

## Prérequis

- Rôle d'administrateur requis
- Au moins une mission existante dans le système

## Étapes

### Étape 1 : Naviguer vers la gestion des missions
- **Page** : `/admin/assignments`
- **Sélecteur** : `.assignments-list, [data-testid="assignments-grid"]`
- **Action** : Voir la liste de toutes les missions
- **Aide** : La page Missions affiche toutes les missions actuelles et passées. Vous pouvez voir le nom de période, le modèle, le statut de soumission et le statut de l'URL publique de chaque mission.
- **Texte d'action** : Suivant

### Étape 2 : Voir les détails de la mission
- **Page** : `/admin/assignments`
- **Sélecteur** : `.assignment-row, [data-assignment-id]`
- **Action** : Examinez les informations de la mission
- **Aide** : Chaque ligne de mission montre le nom de période, le nom du modèle et la progression des soumissions. Utilisez cela pour identifier les missions qui nécessitent une attention.
- **Texte d'action** : Suivant

### Étape 3 : Surveiller la progression des soumissions
- **Page** : `/admin/assignments`
- **Sélecteur** : `.progress-indicator, .submission-status`
- **Action** : Vérifiez le statut d'achèvement
- **Aide** : Voir quels pays ont soumis, lesquels sont en cours et lesquels sont en retard. Cela vous aide à identifier où un suivi est nécessaire.
- **Texte d'action** : Suivant

## Modifier une mission

### Étape 1 : Ouvrir le formulaire de modification
- **Page** : `/admin/assignments`
- **Sélecteur** : `a[href*="/admin/assignments/edit"], .edit-assignment-btn`
- **Action** : Cliquez sur l'icône de modification à côté de la mission
- **Aide** : Cliquez sur l'icône de modification (crayon) à côté de la mission que vous voulez modifier. Cela ouvre le formulaire de modification de la mission.
- **Texte d'action** : Continuer

### Étape 2 : Mettre à jour les détails de la mission
- **Page** : `/admin/assignments/edit/<assignment_id>`
- **Sélecteur** : `#assignment-details-panel, form`
- **Action** : Modifiez les informations de la mission
- **Aide** : Vous pouvez mettre à jour le modèle, le nom de période et la date limite. Les modifications de la date limite s'appliqueront à tous les pays de la mission.
- **Champs** :
  - Modèle : Changez le modèle de formulaire (si nécessaire)
  - Nom de période : Mettez à jour le nom de la mission
  - Date limite : Prolongez ou modifiez la date limite de soumission

### Étape 3 : Ajouter des pays à la mission
- **Page** : `/admin/assignments/edit/<assignment_id>`
- **Sélecteur** : `.add-countries-section, #add-countries-btn`
- **Action** : Ajoutez des pays supplémentaires
- **Aide** : Si vous devez ajouter plus de pays à une mission existante, utilisez la section "Ajouter des pays". Sélectionnez les pays et cliquez sur "Ajouter" pour les inclure.
- **Texte d'action** : Suivant

### Étape 4 : Enregistrer les modifications
- **Page** : `/admin/assignments/edit/<assignment_id>`
- **Sélecteur** : `button[type="submit"], .save-btn`
- **Action** : Cliquez sur Enregistrer les modifications
- **Aide** : Cliquez sur "Enregistrer les modifications" pour appliquer vos mises à jour. Les points focaux seront notifiés si de nouveaux pays sont ajoutés.
- **Texte d'action** : Compris

## Gérer les URL publiques

### Voir le statut de l'URL publique
- **Page** : `/admin/assignments`
- **Sélecteur** : `.public-url-status, [data-public-url]`
- **Action** : Vérifiez si la mission a une URL publique
- **Aide** : La liste des missions montre si chaque mission a une URL publique activée. Les URL publiques permettent les soumissions sans connexion.

### Générer une URL publique
- **Page** : `/admin/assignments`
- **Sélecteur** : `.generate-public-url-btn, [data-action="generate-url"]`
- **Action** : Cliquez sur "Générer une URL publique"
- **Aide** : Si une mission n'a pas d'URL publique, vous pouvez en générer une. Cela permet les soumissions publiques sans exiger de connexion.

### Basculer le statut de l'URL publique
- **Page** : `/admin/assignments`
- **Sélecteur** : `.toggle-public-url, [data-action="toggle-public"]`
- **Action** : Activez ou désactivez l'URL publique
- **Aide** : Basculez l'URL publique activée ou désactivée. Lorsqu'elle est active, l'URL publique est accessible. Lorsqu'elle est inactive, les soumissions sont désactivées.

### Copier l'URL publique
- **Page** : `/admin/assignments`
- **Sélecteur** : `.copy-url-btn, [data-action="copy-url"]`
- **Action** : Cliquez pour copier l'URL
- **Aide** : Copiez l'URL publique pour la partager avec des utilisateurs externes qui doivent soumettre des données sans se connecter.

## Voir les soumissions publiques

### Voir toutes les soumissions publiques
- **Page** : `/admin/assignments`
- **Sélecteur** : `a[href="/admin/assignments/public-submissions"], .view-public-submissions-btn`
- **Action** : Cliquez sur "Voir toutes les soumissions publiques"
- **Aide** : Voir toutes les soumissions publiques à travers toutes les missions. Cela vous aide à surveiller les soumissions externes.

### Voir les soumissions spécifiques à une mission
- **Page** : `/admin/assignments`
- **Sélecteur** : `.view-submissions-btn, [data-action="view-submissions"]`
- **Action** : Cliquez sur "Voir les soumissions" pour une mission spécifique
- **Aide** : Voir et gérer les soumissions publiques pour une mission spécifique. Vous pouvez approuver, rejeter ou examiner les soumissions.

## Supprimer une mission

### Étape 1 : Confirmer la suppression
- **Page** : `/admin/assignments`
- **Sélecteur** : `.delete-assignment-btn, [data-action="delete"]`
- **Action** : Cliquez sur l'icône de suppression
- **Aide** : Cliquez sur l'icône de suppression (corbeille) à côté de la mission que vous voulez supprimer. Il vous sera demandé de confirmer.

### Étape 2 : Confirmer la suppression
- **Page** : `/admin/assignments`
- **Sélecteur** : `.confirm-delete-btn, [data-confirm="delete"]`
- **Action** : Confirmez la suppression
- **Aide** : Confirmez que vous voulez supprimer la mission. Cela supprimera la mission et tous les statuts de pays et données associés. Cette action ne peut pas être annulée.
- **Texte d'action** : Compris

## Vue chronologique

### Accéder au diagramme de Gantt
- **Page** : `/admin/assignments`
- **Sélecteur** : `a[href="/admin/assignments/gantt"], .timeline-view-btn`
- **Action** : Cliquez sur "Vue chronologique"
- **Aide** : Voir toutes les missions sur un graphique chronologique/Gantt. Cela aide à visualiser les dates limites et les missions qui se chevauchent.

## Conseils

- Surveillez régulièrement le tableau de bord pour les soumissions en retard
- Utilisez la vue chronologique pour éviter les conflits de planification
- Prolongez les dates limites de manière proactive si de nombreux pays ont des difficultés
- Les URL publiques sont utiles pour la collecte de données externes mais nécessitent une surveillance
- Examinez régulièrement les soumissions publiques pour assurer la qualité des données
- Envisagez d'envoyer des rappels avant que les dates limites approchent

## Flux de travail connexes

- [Créer une nouvelle mission](create-assignment.md) - Créer une nouvelle mission
- [Créer un modèle](create-template.md) - Concevoir des formulaires avant de les assigner
- [Voir les missions](../focal-point/view-assignments.md) - Perspective du point focal
