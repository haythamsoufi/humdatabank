---
id: manage-users
title: Gérer les utilisateurs existants
description: Guide pour modifier, désactiver et gérer les comptes utilisateur
roles: [admin]
category: user-management
keywords: [modifier utilisateur, mettre à jour utilisateur, désactiver, réinitialiser mot de passe, changer rôle, modifier compte]
pages:
  - /admin/users
  - /admin/users/edit
---

# Gérer les utilisateurs existants

Ce flux de travail guide les administrateurs dans la gestion des comptes utilisateur existants, y compris la modification, la désactivation et la réinitialisation des mots de passe.

## Prérequis

- Rôle d'administrateur requis
- Accès à la section Gestion des utilisateurs et accès

## Étapes

### Étape 1 : Naviguer vers la gestion des utilisateurs
- **Page** : `/admin/users`
- **Sélecteur** : `.user-list, [data-testid="user-list"], table`
- **Action** : Voir la liste de tous les utilisateurs
- **Aide** : La page Gestion des utilisateurs affiche tous les utilisateurs du système. Vous pouvez rechercher, filtrer et trier les utilisateurs à partir d'ici.
- **Texte d'action** : Suivant

### Étape 2 : Trouver l'utilisateur à gérer
- **Page** : `/admin/users`
- **Sélecteur** : `input[type="search"], .search-input, [data-testid="search"]`
- **Action** : Recherchez l'utilisateur
- **Aide** : Utilisez la boîte de recherche pour trouver un utilisateur spécifique par nom ou e-mail. Vous pouvez également utiliser des filtres pour affiner la liste.
- **Texte d'action** : Suivant

### Étape 3 : Ouvrir le formulaire de modification d'utilisateur
- **Page** : `/admin/users`
- **Sélecteur** : `a[href*="/admin/users/edit"], .edit-user-btn, [data-action="edit"]`
- **Action** : Cliquez sur l'icône de modification à côté de l'utilisateur
- **Aide** : Cliquez sur l'icône de modification (crayon) à côté de l'utilisateur que vous voulez modifier. Cela ouvre le formulaire de modification d'utilisateur.
- **Texte d'action** : Continuer

### Étape 4 : Modifier les détails de l'utilisateur
- **Page** : `/admin/users/edit`
- **Sélecteur** : `#user-details-panel, form`
- **Action** : Mettez à jour les informations de l'utilisateur selon les besoins
- **Aide** : Vous pouvez mettre à jour le nom, l'e-mail, le rôle et le mot de passe de l'utilisateur. Les modifications prennent effet immédiatement après l'enregistrement.
- **Champs** :
  - Nom complet : Mettez à jour le nom de l'utilisateur
  - E-mail : Changez l'e-mail de connexion (l'utilisateur devra vérifier)
  - Rôle : Basculez entre Administrateur et Point focal
  - Mot de passe : Laissez vide pour garder le courant, ou entrez un nouveau mot de passe

### Étape 5 : Mettre à jour les permissions
- **Page** : `/admin/users/edit`
- **Sélecteur** : `#entity-permissions-tab`
- **Action** : Modifiez les assignations de pays
- **Aide** : Ajoutez ou supprimez des pays pour les Points focaux. Les Administrateurs ont automatiquement accès à tous les pays.
- **Texte d'action** : Suivant

### Étape 6 : Enregistrer les modifications
- **Page** : `/admin/users/edit`
- **Sélecteur** : `form button[type="submit"], .fixed button[type="submit"]`
- **Action** : Cliquez sur Enregistrer les modifications
- **Aide** : Cliquez sur "Enregistrer les modifications" pour appliquer vos mises à jour. L'utilisateur sera notifié si son accès a changé.
- **Texte d'action** : Compris

## Actions supplémentaires

### Désactiver un utilisateur
Pour désactiver un compte utilisateur :
1. Trouvez l'utilisateur dans la liste
2. Cliquez sur le bouton de bascule de statut ou le bouton de désactivation
3. Confirmez la désactivation

Les utilisateurs désactivés ne peuvent pas se connecter mais leurs données sont préservées.

### Réinitialiser le mot de passe
Pour réinitialiser le mot de passe d'un utilisateur :
1. Ouvrez le formulaire de modification d'utilisateur
2. Entrez un nouveau mot de passe dans le champ mot de passe
3. Enregistrez les modifications
4. Partagez le nouveau mot de passe avec l'utilisateur de manière sécurisée

## Conseils

- Désactiver un utilisateur préserve toutes ses données et soumissions
- Les changements de rôle prennent effet lors de la prochaine connexion de l'utilisateur
- Envisagez d'utiliser le tableau de bord Analytiques pour examiner l'activité utilisateur avant d'apporter des modifications
- Les journaux d'audit suivent toutes les actions de gestion des utilisateurs

## Flux de travail connexes

- [Ajouter un nouvel utilisateur](add-user.md) - Créer de nouveaux comptes utilisateur
