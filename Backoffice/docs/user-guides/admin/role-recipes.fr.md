# Recettes de rôles (tâches administratives courantes)

Utilisez cette page lorsque vous n'êtes pas sûr des rôles à assigner pour une tâche spécifique.

## Avant de commencer

- Les rôles contrôlent **quelles pages/actions** un utilisateur peut accéder.
- De nombreux utilisateurs ont également besoin d'un **accès au pays** pour voir les missions pour des pays spécifiques.

## Recette : Point focal standard (saisie de données)

Donnez à l'utilisateur :

- Rôle : `assignment_editor_submitter`
- Accès au pays : assignez au moins un pays

Ils peuvent :
- voir les missions pour leurs pays
- saisir des données et soumettre

## Recette : Point focal qui approuve également

Donnez à l'utilisateur :

- Rôles : `assignment_editor_submitter`, `assignment_approver`
- Accès au pays : assignez les pays pertinents

## Recette : Visualiseur en lecture seule

Donnez à l'utilisateur :

- Rôle : `assignment_viewer`
- Accès au pays : optionnel (dépend de la configuration de votre système)

## Recette : Concepteur de modèles (pas de gestion d'utilisateurs)

Donnez à l'utilisateur :

- Un rôle de gestion de modèles (par exemple : `admin_templates_manager`)

Optionnellement aussi :

- `assignment_viewer` (pour qu'ils puissent voir comment les modèles sont utilisés)

## Recette : Gestionnaire de missions (pas de modifications de modèles)

Donnez à l'utilisateur :

- `admin_assignments_manager`

Optionnellement :

- `assignment_viewer` ou `assignment_approver` s'ils examinent également les soumissions

## Recette : Gestionnaire d'utilisateurs (RH / administrateur d'accès)

Donnez à l'utilisateur :

- `admin_users_manager`

Ils peuvent créer/gérer des utilisateurs et assigner des rôles (dans leur portée autorisée).

## Recette : Téléchargeur de documents uniquement

Donnez à l'utilisateur :

- `assignment_documents_uploader`
- Accès au pays (si requis par votre configuration)

Ils peuvent télécharger des documents justificatifs mais ne peuvent pas soumettre des données de formulaire.

## Problèmes courants

- **L'utilisateur ne peut pas voir les missions** : ils ont généralement besoin à la fois (1) d'un rôle de mission et (2) d'un accès au pays.
- **L'utilisateur voit "Accès refusé"** : il manque le rôle spécifique pour ce module d'administration.

## Liens connexes

- [Rôles et permissions utilisateur](user-roles.md)
- [Gérer les utilisateurs](manage-users.md)
- [Dépannage d'accès (Administrateur)](troubleshooting-access.md)
