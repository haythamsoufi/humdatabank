# Statuts de soumission et ce que vous pouvez faire (guide des permissions)

Utilisez ce guide pour comprendre pourquoi un bouton est manquant/désactivé (par exemple **Modifier**, **Soumettre**, **Approuver**, ou **Rouvrir**).

## Deux choses contrôlent ce que vous pouvez faire

1. **Votre(s) rôle(s)** (permissions)
2. **Le statut actuel** de la mission/soumission

Si l'un ou l'autre n'autorise pas une action, vous ne la verrez pas (ou elle sera désactivée).

## Rôles courants (langage simple)

- **Point focal (saisie de données)** : peut saisir des données et soumettre (généralement `assignment_editor_submitter`)
- **Approbateur** : peut approuver et rouvrir (généralement `assignment_approver`)
- **Administrateur** : peut gérer les utilisateurs/modèles/missions (varie selon les rôles d'administrateur)

## Statuts courants (ce qu'ils signifient généralement)

Les noms de statut peuvent varier légèrement selon le flux de travail, mais ils correspondent généralement à :

- **Non commencé** : aucune réponse enregistrée (ou l'utilisateur ne l'a pas ouvert)
- **En cours / Brouillon** : certaines réponses sont enregistrées, non soumises
- **Soumis** : envoyé pour examen (la modification peut être verrouillée)
- **Approuvé** : accepté/finalisé (la modification est généralement verrouillée)
- **Rouvert / Retourné** : renvoyé pour correction (la modification est à nouveau autorisée)
- **Fermé / Archivé** (si utilisé) : période de collecte terminée ; les modifications peuvent être bloquées

## Ce que vous pouvez faire (matrice rapide)

Ce tableau montre le comportement *typique*.

| Statut | Point focal (saisie de données) | Approbateur | Administrateur (gestion des missions) |
|---|---|---|---|
| Non commencé | Modifier | Voir | Voir / Gérer |
| En cours / Brouillon | Modifier / Soumettre | Voir | Voir / Gérer |
| Soumis | Voir (modification généralement verrouillée) | Approuver / Rouvrir | Voir / Gérer |
| Approuvé | Voir | Voir (peut encore rouvrir) | Voir / Gérer |
| Rouvert / Retourné | Modifier / Re-soumettre | Voir / Approuver | Voir / Gérer |

Notes :
- Si vous ne pouvez pas **voir** une mission du tout, c'est généralement un problème d'**accès au pays** ou de **rôle**.
- Certaines configurations permettent aux administrateurs/approbateurs de modifier après soumission ; d'autres non.

## Quand les boutons sont manquants (causes courantes)

### "Soumettre" est manquant ou désactivé

Causes probables :
- Un champ requis est manquant
- Des messages de validation existent
- La mission est déjà soumise/approuvée et est verrouillée

Que faire :
- Corrigez les messages requis/de validation et réessayez
- Si elle est verrouillée, demandez à un approbateur/administrateur de **Rouvrir** (si votre flux de travail le prend en charge)

### "Approuver" est manquant

Causes probables :
- Vous n'avez pas le rôle d'approbateur (`assignment_approver`)
- La soumission n'est pas encore dans un état "Soumis"

### "Rouvrir" est manquant

Causes probables :
- Le flux de travail n'autorise pas la réouverture, ou seuls certains rôles peuvent rouvrir
- La soumission est déjà en cours (non soumise)

### "Modifier" est manquant

Causes probables :
- Vous n'avez qu'un rôle de visualisation
- Le statut est soumis/approuvé et la modification est verrouillée

## Si vous êtes toujours bloqué

- [Dépannage (Point focal)](../focal-point/troubleshooting.md)
- [Obtenir de l'aide](getting-help.md)
- Demandez à votre administrateur si le problème concerne l'accès, les rôles ou la configuration du flux de travail.
