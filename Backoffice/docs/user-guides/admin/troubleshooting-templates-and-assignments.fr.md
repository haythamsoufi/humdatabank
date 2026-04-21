# Dépannage des modèles et missions (administrateur)

Utilisez ce guide lorsque quelque chose semble incorrect avec les modèles/missions (mauvaise version, pays manquants, soumissions bloquées, exports confus).

## Problèmes de modèle

### "Mes modifications de modèle n'apparaissent pas pour les points focaux"

Causes courantes :
- vous avez modifié un brouillon mais ne l'avez pas publié (si la publication existe dans votre configuration)
- la mission est liée à un modèle/version plus ancien

Que faire :
- Confirmez quel modèle/version la mission utilise.
- Pour les changements majeurs, créez une nouvelle mission et communiquez le changement.

### "Les utilisateurs ne peuvent pas soumettre après avoir mis à jour le modèle"

Causes courantes :
- de nouveaux champs requis ont été ajoutés
- les règles de validation sont trop strictes
- une matrice/tableau a des cellules requises

Que faire :
- Testez en tant que point focal sur une petite mission.
- Réduisez les champs requis et ajoutez un texte d'aide plus clair.

Voir : [Générateur de formulaires (avancé)](form-builder-advanced.md)

## Problèmes de mission

### "Un pays manque de la mission"

Causes courantes :
- le pays n'a pas été sélectionné lors de la création
- le pays a été supprimé plus tard
- le pays est filtré par les paramètres de statut/vue

Que faire :
- Vérifiez les paramètres de la mission et ajoutez le pays si nécessaire.
- Confirmez que les points focaux pour ce pays ont l'accès au pays.

### "Un point focal dit qu'il ne peut pas voir la mission"

Raisons les plus courantes :
- rôle de mission manquant (saisie de données/vue)
- accès au pays manquant
- la mission n'est pas active pour cette période

Vérifications initiales :
- confirmez les rôles de l'utilisateur (voir [Rôles et permissions utilisateur](user-roles.md))
- confirmez l'accès au pays de l'utilisateur
- confirmez que la mission inclut ce pays

### "Nous devons corriger les données après soumission"

Approches typiques :
- Rouvrir/renvoyer la soumission (si votre flux de travail le prend en charge)
- Demander au point focal de corriger et de re-soumettre

Voir : [Examiner et approuver les soumissions](review-approve-submissions.md) et [Statuts de soumission et ce que vous pouvez faire](../common/submission-statuses-and-permissions.md)

## Problèmes d'export

### "L'export manque des données ou a des colonnes inattendues"

Causes courantes :
- exportation de la mauvaise mission/période
- version du modèle changée
- filtre d'export excluant certains statuts/pays

Voir : [Exports : comment interpréter les fichiers](exports-how-to-interpret.md)

## Liens connexes

- [Cycle de vie d'une mission](assignment-lifecycle.md)
- [Gérer les missions](manage-assignments.md)
- [Générateur de formulaires (avancé)](form-builder-advanced.md)
