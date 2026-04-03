# Dépannage d'accès (Administrateur)

Utilisez cette page lorsqu'un utilisateur signale qu'il ne peut pas se connecter ou ne peut pas voir les pages/données dont il a besoin.

## Un utilisateur ne peut pas se connecter

Liste de contrôle :

- Confirmez que l'adresse e-mail est correcte.
- Confirmez que le compte est **actif** (non désactivé).
- Si votre flux de travail utilise des réinitialisations de mot de passe, définissez un nouveau mot de passe et partagez-le **de manière sécurisée**.

## Un point focal peut se connecter, mais ne peut pas voir les missions

Cause la plus courante : il n'est **pas assigné à un pays/organisation** ou il manque des rôles de mission.

Ce qu'il faut vérifier :

1. Ouvrez **Panneau d'administration → Gestion des utilisateurs → Gérer les utilisateurs**.
2. Ouvrez l'utilisateur.
3. Allez dans l'onglet **Détails de l'utilisateur** et confirmez :
   - Il a un **rôle de mission** (par exemple `assignment_editor_submitter` ou `assignment_viewer`)
4. Allez dans l'onglet **Permissions d'entité** et confirmez :
   - Au moins un **pays** (ou organisation) est assigné
5. Confirmez qu'il existe une mission créée pour ce pays/organisation.

## Un utilisateur dit "Accès refusé" pour une page d'administration

Cela signifie généralement qu'il manque les permissions requises.

Que faire :

- Confirmez si l'utilisateur devrait avoir des **rôles d'administration** ou des **rôles de mission** (ou les deux).
- S'il devrait être administrateur, assignez les rôles d'administration appropriés (par exemple `admin_full`, `admin_core`, ou des rôles de gestionnaire spécifiques).
- Seuls les Gestionnaires système peuvent assigner des rôles - contactez un Gestionnaire système pour mettre à jour les rôles utilisateur.

## Un utilisateur ne peut pas voir un pays spécifique

Causes courantes :

- L'utilisateur n'est pas assigné à ce pays.
- Le rôle de l'utilisateur n'autorise pas l'accès à cette zone.

Que faire :

1. Allez dans l'onglet **Permissions d'entité** de l'utilisateur et confirmez qu'il est assigné au(x) pays correct(s) (ou organisations).
2. Si c'est un flux de travail d'administration, confirmez qu'il a le(s) rôle(s) d'administration pertinent(s) (par exemple `admin_countries_manager` pour la gestion des pays).

## Liens connexes

- [Rôles et permissions utilisateur](user-roles.md) - Comprendre les différents rôles et permissions
- [Gérer les utilisateurs](manage-users.md)
- [Ajouter un utilisateur](add-user.md)
- [Obtenir de l'aide](../common/getting-help.md)
