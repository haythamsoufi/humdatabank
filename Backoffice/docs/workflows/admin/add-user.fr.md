---
id: add-user
title: Ajouter un Nouvel Utilisateur
description: Guide pour créer un nouveau compte utilisateur dans le système
roles: [admin]
category: user-management
keywords: [créer utilisateur, nouveau compte, inscription, personnel, membre]
pages:
  - /admin/users
  - /admin/users/new
---

# Ajouter un Nouvel Utilisateur

Ce guide accompagne les administrateurs dans la création d'un nouveau compte utilisateur dans le système.

## Prérequis

- Rôle d'administrateur requis
- Accès à la section Gestion des Utilisateurs et des Accès

## Étapes

### Step 1: Accéder à la Gestion des Utilisateurs
- **Page**: `/admin/users`
- **Selector**: `a[href="/admin/users/new"]`
- **Action**: Cliquez sur le bouton "Ajouter un Nouvel Utilisateur"
- **Help**: Cliquez sur le bouton "Ajouter un Nouvel Utilisateur" dans le coin supérieur droit pour commencer à créer un nouveau compte.
- **ActionText**: Continuer

### Step 2: Remplir les Détails de l'Utilisateur
- **Page**: `/admin/users/new`
- **Selector**: `#user-details-panel`
- **Action**: Remplissez les informations requises
- **Help**: Entrez l'email, le nom, le rôle de l'utilisateur et définissez un mot de passe initial. Tous les champs marqués d'un * sont obligatoires.
- **ActionText**: Suivant

### Step 3: Configurer les Permissions d'Entité
- **Page**: `/admin/users/new`
- **Selector**: `#entity-permissions-tab, #entity-permissions-panel`
- **Action**: Cliquez sur l'onglet Permissions d'Entité
- **Help**: Attribuez des pays ou des entités organisationnelles à l'utilisateur. Les Points Focaux doivent avoir au moins un pays assigné pour accéder aux données.
- **ActionText**: Suivant

### Step 4: Enregistrer le Nouvel Utilisateur
- **Page**: `/admin/users/new`
- **Selector**: `form button[type="submit"], .fixed button[type="submit"]`
- **Action**: Cliquez sur Créer l'Utilisateur
- **Help**: Vérifiez toutes les informations et cliquez sur "Créer l'Utilisateur" pour terminer. L'utilisateur recevra ses identifiants de connexion.
- **ActionText**: Compris

## Conseils

- Les utilisateurs devront changer leur mot de passe lors de leur première connexion pour des raisons de sécurité
- Les Points Focaux sont limités aux données de leurs pays assignés uniquement
- Les administrateurs ont un accès complet au système dans tous les pays
- Vous pouvez toujours modifier les détails de l'utilisateur ultérieurement depuis la page de Gestion des Utilisateurs

## Guides Associés

- [Gérer les Utilisateurs](manage-users.md) - Modifier et désactiver les utilisateurs existants
