---
id: navigation
title: Navigation de la plateforme
description: Guide pour naviguer dans les sections principales de la plateforme
roles: [admin, focal_point]
category: navigation
keywords: [menu, naviguer, trouver, où, emplacement, sections, tableau de bord]
pages:
  - /
  - /admin
---

# Navigation de la plateforme

Ce guide vous aide à naviguer dans les sections et fonctionnalités principales de la plateforme.

## Prérequis

- Connecté au système

## Zones de navigation principales

### Pour tous les utilisateurs

#### Tableau de bord
- **Page** : `/`
- **Sélecteur** : `a[href="/"], .sidebar-item-container[href="/"]`
- **Aide** : Votre page d'accueil personnalisée affichant les missions en attente, l'activité récente et l'accès rapide aux tâches courantes.

#### Paramètres du compte
- **Page** : `/account-settings`
- **Sélecteur** : `a[href*="account-settings"], a[href*="account_settings"], .profile-dropdown`
- **Aide** : Mettez à jour votre profil, changez votre mot de passe et définissez vos préférences de notification.

### Pour les points focaux

#### Mes missions
- **Page** : `/`
- **Sélecteur** : `.bg-white.p-6.rounded-lg.shadow-md, .grid.gap-4`
- **Aide** : Voir toutes vos soumissions de formulaires en attente et terminées sur votre tableau de bord.

#### Saisie de données
- **Page** : `/forms/assignment`
- **Sélecteur** : `a[href*="/forms/assignment/"]`
- **Aide** : Cliquez sur une mission pour accéder au formulaire de saisie de données pour vos pays assignés.

### Pour les administrateurs

#### Gestion des utilisateurs et accès
- **Page** : `/admin/users`
- **Sélecteur** : `a[href="/admin/users"], .nav-users`
- **Aide** : Gérez les comptes utilisateur, les rôles et les permissions. Ajoutez de nouveaux utilisateurs ou modifiez les existants.

#### Gestion des formulaires et données
- **Page** : `/admin/templates`
- **Sélecteur** : `a[href="/admin/templates"], .nav-templates`
- **Aide** : Créez et gérez les modèles de formulaires. Concevez des formulaires avec sections et champs.

#### Gérer les missions
- **Page** : `/admin/assignments`
- **Sélecteur** : `a[href="/admin/assignments"], .nav-assignments`
- **Aide** : Créez et suivez les missions de formulaires. Surveillez la progression des soumissions entre les pays.

#### Données de référence
- **Page** : `/admin/indicators`
- **Sélecteur** : `a[href="/admin/indicators"], .nav-indicators`
- **Aide** : Gérez la Banque d'indicateurs avec des définitions de données et des métriques standardisées.

#### Pays
- **Page** : `/admin/countries`
- **Sélecteur** : `a[href="/admin/countries"], .nav-countries`
- **Aide** : Configurez les pays, régions et informations de la Société nationale.

#### Analytiques et surveillance
- **Page** : `/admin/analytics`
- **Sélecteur** : `a[href="/admin/analytics"], .nav-analytics`
- **Aide** : Voir les tableaux de bord, rapports et visualisations de données. Surveillez l'utilisation de la plateforme et la qualité des données.

## Conseils de navigation rapide

### Utiliser la barre latérale
La barre latérale principale fournit l'accès à toutes les sections majeures. Cliquez sur une catégorie pour l'étendre et voir les sous-éléments.

### Utiliser la recherche
- Appuyez sur `/` ou cliquez sur l'icône de recherche pour ouvrir la recherche rapide
- Tapez pour trouver des pages, utilisateurs, modèles ou pays
- Appuyez sur Entrée pour naviguer vers le premier résultat

### Raccourcis clavier
| Raccourci | Action |
|----------|--------|
| `?` | Afficher les raccourcis clavier |
| `/` | Ouvrir la recherche |
| `g d` | Aller au Tableau de bord |
| `g s` | Aller aux Paramètres |

### Fil d'Ariane
Utilisez le fil d'Ariane en haut des pages pour naviguer vers les sections parentes.

## Conseils

- Ajoutez des signets aux pages fréquemment utilisées pour un accès rapide
- Utilisez le bouton de réduction de la barre latérale pour plus d'espace d'écran
- Vérifiez la cloche de notification pour les mises à jour et rappels
- Le chatbot peut vous aider à trouver n'importe quelle fonctionnalité - demandez simplement !

## Obtenir de l'aide

Si vous ne trouvez pas quelque chose :
1. Utilisez la fonctionnalité de recherche
2. Demandez au chatbot "Où est [fonctionnalité] ?"
3. Consultez la documentation d'aide
4. Contactez votre administrateur
