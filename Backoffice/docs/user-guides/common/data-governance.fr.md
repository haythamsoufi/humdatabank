# Gouvernance des données : comment le système la soutient

Ce document décrit comment la Banque de données humanitaires soutient la **gouvernance des données** : les politiques et contrôles qui garantissent que les données collectées sont accessibles uniquement aux parties autorisées, cohérentes et fiables, traçables et traitées de manière sécurisée. Elle s’adresse aux administrateurs, aux points de contact et à d’autres personnes qui doivent comprendre comment la plateforme soutient la gouvernance des données qu’elle collecte.

## Portée de ce document

- **Propriété des données** — Propriétaires de modèles et propriétaires de données avec une responsabilité explicite par assignation
- **Contrôle d’accès et portée des données** — Qui peut visualiser et modifier quelles données, grâce à la détection d’accès fantôme
- **Qualité et cohérence des données** — Validation, définitions standard, suivi des retards et flux de travail de soumission
- **Responsabilité et audit** — Attribution des actions administratives, suivi de la soumission/approbation et audit d’activation
- **Conformité** — Suivi de la conformité aux documents FDRS
- **Métadonnées** — Définitions d’indicateurs, étiquettes de formulaires et détection de la suggestion obsolète
- **Cycle de vie des données** — Du brouillon à l’approbation, et comment les changements sont contrôlés
- **Manipulation sécurisée** — Exportations, liens publics et pratiques de confidentialité
- **Pratiques opérationnelles** — Gestion des cycles de reporting et maintien de la gouvernance dans l’usage quotidien
- **Tableau de bord de gouvernance** — Une page d’administration dédiée qui met en avant des métriques, des indicateurs et un score de santé pour tous les piliers

---

## Propriété des données

La plateforme met en œuvre un **modèle de propriété des données à deux niveaux** qui distingue la responsabilité à différents niveaux.

### Niveau 1 : Propriétaire du modèle (niveau modèle)

Un **Propriétaire du Modèle** est responsable de la *norme ou définition* des données — ce qui est mesuré et comment.

- **Propriétaire du modèle** (`FormTemplate.owned_by`) — Chaque modèle de formulaire peut avoir un propriétaire : la personne responsable de la norme de données qu’il définit. Seuls les utilisateurs disposant d’autorisations de modèle au niveau administrateur apparaissent dans le menu déroulant du propriétaire du modèle. Réglez cela sous **Panneau d’administration → Constructeur de formulaires → Modifier le modèle**.

### Niveau 2 : Propriétaire des données (niveau d’affectation)

Un **Propriétaire des Données** est responsable des *données réellement collectées* dans un cycle de reporting spécifique.

- **Propriétaire des données d’affectation** (`AssignedForm.data_owner_id`) — Chaque attribution peut avoir un propriétaire désigné : la personne responsable de la qualité des données durant ce cycle de collecte. Seuls les utilisateurs disposant d’autorisations d’attribution au niveau administrateur apparaissent dans le menu déroulant du propriétaire des données (les points focaux sont exclus puisqu’ils sont des soumissionnaires, et non des propriétaires). Réglez cela sous **Panneau d’administration → Assignations → Créer/Modifier une mission**.
- Lorsqu’une nouvelle assignation est créée et qu’un modèle est sélectionné, le système peut pré-remplir le propriétaire des données depuis le propriétaire du modèle (`owned_by`).

### Niveau 3 : Point focal (niveau pays)

**Les points focaux** sont la responsabilité existante au niveau de l’entité. Un point focal est attribué à un ou plusieurs pays et est responsable de la saisie et de la soumission des données pour ces pays. Les points focaux ne sont pas les propriétaires des données ; ce sont les utilisateurs opérationnels qui collectent et soumettent.

### Données organisationnelles (pays, sociétés nationales, structure des sociétés nationales)

Les données organisationnelles sont la **référence autoritaire** pour la portée géographique et structurelle à travers la plateforme : pays, sociétés nationales, et — lorsque la fonctionnalité est activée — structure des sociétés nationales (branches, sous-branches, unités locales).

- **Pays** — La liste des pays est maintenue sous **Panneau d’administration → Gestion organisationnelle** (onglet Pays). Seuls les utilisateurs disposant des autorisations requises peuvent créer, modifier ou supprimer des pays. Cette liste sous-tend la portée de l’attribution (quels pays sont inclus dans une assignation), l’accès par pays utilisateur (quels pays un point focal peut consulter) et la déclaration (par exemple, les exportations par pays).
- **Sociétés nationales** — Chaque société nationale est associée à un seul pays. Les Sociétés nationales sont gérées sous **Gestion organisationnelle → Sociétés nationales**, et sont utilisées lorsque les rapports ou les affectations sont définis par la Société nationale plutôt que, ou en complément de, pays.
- **Structure de la Société Nationale (branches, sous-branches, unités locales)** — Lorsque la structure de la Société Nationale est activée, la hiérarchie est **Branche → Société nationale → Sous-branche → unité locale**. Les branches et sous-branches sont associées à un pays ; les unités locales appartiennent à une branche ou sous-branche. Cette structure est maintenue sous **Gestion organisationnelle → structure de la Société Nationale** et fournit la liste canonique des branches et unités locales utilisées dans les formulaires, les affectations et les rapports.

**Propriétaire des données et maintenance.** Le **propriétaire des données** pour toutes les données de l’organisation est l'**équipe des systèmes de données (FDS) à l’échelle de la Fédération**. Le FDS est responsable de la précision et de la gouvernance de ces listes maîtresses. Seuls les utilisateurs disposant des autorisations requises peuvent modifier les données dans le système : **Modifier les pays** (`admin.countries.edit`) pour les pays, et **Gérer l’organisation** (`admin.organization.manage`) pour la structure complète. L’accès en lecture seule utilise **Voir les pays** (`admin.countries.view`). Les administrateurs désignés (sous la gouvernance FDS) maintiennent les données afin que les données de formulaires, les affectations et les exportations restent alignées sur une seule hiérarchie.

Maintenir l’exactitude des données organisationnelles garantit une attribution correcte, un contrôle d’accès conforme à la structure prévue, ainsi que des exportations et rapports respectant les limites organisationnelles.

*Voir :* [Rôles et permissions d’utilisateur](../admin/user-roles.md) (pour les rôles incluant la gestion des pays et des organisations)

### Banque d’indicateurs (glossaire des définitions standard)

La **Banque d’Indicateurs** est un **glossaire d’entreprise** centralisé des définitions des indicateurs (nom, unité, définition et, optionnellement, règles de calcul). Il ne stocke pas les valeurs soumises — celles-ci sont des données en format et sont liées à des attributions et entités (par exemple, pays ou société nationale).

Seuls les utilisateurs disposant des autorisations de la Banque d’indicateurs (par exemple **gestionnaire de la Banque d’indicateurs**) peuvent consulter, créer, modifier, archiver ou examiner les suggestions d’indicateurs. La Banque d’Indicateurs définit *ce qui* est mesuré ; formulez des enregistrements de données *qui* a déclaré *laquelle* valeur et *quand*. Garder les définitions stables au fil du temps ; Lorsque la signification d’une mesure change, ajoutez un nouvel indicateur afin que les données historiques restent interprétables.

La gestion centrale des définitions évite les interprétations contradictoires entre pays et périodes et soutient des rapports comparables.

*Voir :* [Banque d’indicateurs (admin)](../admin/indicator-bank.md)

### Résumé

| Type de données | Propriétaire | Où maintenu | Rôle dans la gouvernance |
|-----------|-------|------------------|---------------------|
| Pays, Sociétés nationales, structure des Sociétés nationales | **FDS** (Équipe des systèmes de données à l’échelle de la Fédération) | Panneau d’administration → Gestion organisationnelle | Portée faisant autorité pour les attributions, l’accès utilisateur et le reporting |
| Définitions des indicateurs (termes du glossaire) | **Directeurs de banques indicatrices** | Panneau d’administration → Banque d’indicateurs | Définitions standard utilisées entre modèles et affectations |
| Normes de modèles de formulaire | **Propriétaire du modèle** (utilisateur unique par modèle) | Panneau d’administration → Constructeur de formulaires | Définit quelles données sont collectées et comment |
| Données d’attribution (cycle de collecte) | **Propriétaire des données** (utilisateur unique par attribution) | Panneau d’administration → Affectations | Responsable de la qualité des données pendant le cycle de reporting |
| Valeurs de soumission de formulaires | **Point focal** (par pays/entité) | Formulaires d’inscription, soumissions, exportations | Données attribuées à l’entité soumise |

### Filtrage déroulant pour les rôles de propriétaire

Pour maintenir une séparation claire des préoccupations, la plateforme filtre les menus déroulants des utilisateurs selon leur rôle :

| Déroulant | Émissions | Exclut | Raison |
|----------|-------|----------|--------|
| Propriétaire du modèle | Utilisateurs avec des permissions de modèles administrateur | Points focaux, utilisateurs uniquement en vue | Seuls les administrateurs doivent posséder les normes de données |
| Propriétaire des données d’attribution | Utilisateurs avec des permissions d’attribution admin | Points focaux, utilisateurs uniquement en vue | Les points focaux soumettent des données ; Les propriétaires en sont responsables |
| Accès partagé (modèle) | Utilisateurs avec des rôles d’administrateur | Utilisateurs non administrateurs | Le partage de modèles est une préoccupation au niveau administrateur |

---

## 1. Contrôle d’accès et portée des données

Le système restreint l’accès afin que les utilisateurs ne puissent consulter et agir uniquement sur les données auxquelles ils sont autorisés à accéder.

### Contrôle d’accès basé sur les rôles (RBAC)

- Les utilisateurs se voient attribuer des **rôles** qui définissent les actions autorisées (voir, modifier, soumettre, approuver, gérer les modèles, etc.).
- **Les rôles d’attribution** (par exemple visualiseur, éditeur/soumissionnaire, approver) déterminent si un utilisateur ne peut que voir les données, les saisir et les soumettre, ou les approuver.
- **Les rôles administratifs** régissent l’accès aux modèles, attributions, utilisateurs, pays, indicateurs, contenu, analyses et fonctionnalités de sécurité/audit.
- Les actions non autorisées par le rôle d’un utilisateur ne sont pas disponibles ; Les boutons et pages pertinents sont cachés ou désactivés.

*Voir :* [Rôles et permissions utilisateur](../admin/user-roles.md)

### Pays et portée de l’affectation

- **Attribution de pays (ou d’entité)** détermine *lesquelles* assignations et données de soumission un utilisateur peut voir.
- Un point focal n’a généralement accès qu’aux missions des pays auxquels il est affecté.
- Les administrateurs disposant d’un accès à la gestion des affectations voient les affectations selon leurs autorisations ; La portée peut être encore plus limitée par la configuration.
- Si un utilisateur ne peut pas accéder à une affectation, la cause est généralement **accès au pays** ou **rôle**, plutôt que les données elles-mêmes.

*Voir :* [Statuts de soumission et ce que vous pouvez faire](submission-statuses-and-permissions.md), [Dépannage de l’accès (Admin)](../admin/troubleshooting-access.md)

### Détection d’accès fantôme

Le **Tableau de bord de gouvernance** détecte l'**accès fantôme** : utilisateurs inactifs (désactivés) qui occupent encore des rôles RBAC. C’est un risque de sécurité car les subventions de rôle peuvent persister après le départ d’un utilisateur de l’organisation. Le tableau de bord signale ces utilisateurs et renvoie directement à la gestion des utilisateurs pour la correction.

De plus, le tableau de bord affiche :
- **Utilisateurs avec des permissions d’entité (pays) mais sans rôle RBAC** — ils peuvent se connecter mais ne peuvent rien faire d’utile
- **Autorisations orphelines** — autorisations non attribuées à un rôle ou à une concession
- **Rôles sans aucun utilisateur** — rôles existant mais sans membres

### Résumé

| Préoccupation | Comment le système le supporte |
|---------|----------------------------|
| Qui peut consulter les données | Rôles et affectation pays/entité ; Les utilisateurs ne voient que les données auxquelles ils sont autorisés |
| Qui peut modifier les données | Les utilisateurs ayant des rôles d’édition/soumission ou d’administrateur ; les approbateurs peuvent rouvrir pour corrections |
| Qui peut exporter | Les utilisateurs ayant accès au formulaire d’attribution et d’inscription ; L’exportation peut être activée par modèle |
| Accès fantôme | Le tableau de bord de gouvernance signale les utilisateurs inactifs ayant des rôles RBAC actifs |
| Rôles non utilisés | Le tableau de bord de gouvernance signale les rôles sans aucun utilisateur assigné |

---

## 2. Qualité et cohérence des données

Le système prend en charge des données cohérentes et adaptées à l’usage via des définitions standard (Indicator Bank), des champs de validation et d’exigence, ainsi qu’un flux de travail clair de soumission et d’approbation.

### Banque d’indicateurs (définitions standard)

Lier les champs de formulaire aux indicateurs dans la Banque d’indicateurs garantit que la même mesure est rapportée de la même manière à travers les pays, les périodes et les modèles. Voir [Propriété des données](#data-ownership) pour savoir qui les entretient.

*Voir :* [Banque d’indicateurs (admin)](../admin/indicator-bank.md)

### Validation et champs requis

**Les champs obligatoires** et les **règles de validation** (par exemple format numérique, plages) empêchent la soumission tant que le formulaire n’atteint pas la qualité minimale. Les messages de validation apparaissent dans le formulaire et bloquent la soumission jusqu’à ce que cela soit résolu. Les administrateurs définissent ces éléments dans le Constructeur de formulaires.

*Voir :* [Constructeur de formulaires (avancé)](../admin/form-builder-advanced.md), [Modifier un modèle](../admin/edit-template.md)

### Flux de travail de soumission et d’approbation

Les données passent par des **statuts** (par exemple, non commencées → en cours → soumises → approuvées). **Soumet** envoie pour révision ; **Approuve** l’accepte ; **Réouverture** le ramène pour correction. Lorsque le verrou d’édition est utilisé, les données ne sont considérées comme définitives qu’après approbation.

Le système enregistre **qui a soumis** (`submitted_by_user_id`) et **qui a approuvé** ({`approved_by_user_id`) chaque changement de statut d’entité, fournissant ainsi une trace d’audit claire de la responsabilité.

*Voir :* [Statuts des soumissions et ce que vous pouvez faire](submission-statuses-and-permissions.md), [Examiner et approuver les soumissions](../admin/review-approve-submissions.md)

### Suivi en retard et gravité

Le **Tableau de bord de gouvernance** suit les soumissions en retard selon des fourchettes de gravité :

| Gravité | Seuil | Signification |
|----------|-----------|---------|
| **Critique** | > 30 jours en retard | Nécessite une attention immédiate |
| **Haut** | > 8 jours en retard | Besoin d’un suivi |
| **Moyen** | > 1 jour de retard | Récemment en retard |

Le tableau de bord détecte également les **assignations jamais lancées** (affectations actives où chaque entité est toujours en état « En attente ») et les **assignations sans entité** (créées mais jamais assignées à un pays).

### Résumé

| Préoccupation | Comment le système le supporte |
|---------|----------------------------|
| Définitions cohérentes | Banque d’indicateurs ; Champs de formulaire liés aux indicateurs |
| Complétude minimale | Les champs obligatoires et les règles de validation bloquent la soumission jusqu’à ce que ce soit satisfait |
| Nettoyer l’état final | Flux de travail de soumission et d’approbation ; statuts et, lorsqu’utilisés, verrou d’édition après soumission |
| Suivi en retard | Tableau de bord de gouvernance avec des catégories de sévérité (critique/élevé/moyen) |
| Détection jamais lancée | Le tableau de bord signale les affectations actives où aucun pays n’a commencé à travailler |
| Attribution | `submitted_by` et `approved_by` suivis par changement d’état d’entité |

---

## 3. Responsabilité et audit

### Journal des actions d’administrateur et niveaux de risque

Le système enregistre les actions administratives (qui a fait quoi, quand) et attribue à chacune un **niveau de risque** (élevé, moyen, bas). Les actions **à haut risque** (par exemple, suppression d’utilisateur, changements de rôle du gestionnaire système) créent automatiquement des **événements de sécurité** et sont mises en évidence pour examen. Toutes les actions font partie de la **piste d’audit** pour la conformité et le dépannage.

*Voir :* [Niveaux de risque d’action admin](../../workflows/admin/admin-action-risk-levels.md)

Les actions à haut et critique risque apparaissent dans le **Tableau de bord de sécurité** et dans les journaux d’actions d’administration ; Les actions peuvent être filtrées selon le niveau de risque.

### Audit du cycle de vie des affectations

Le système suit qui a activé et désactivé les affectations :

- `activated_by_user_id` — enregistré lorsqu’une affectation est activée ou rouverte
- `deactivated_by_user_id` — enregistré lorsqu’une affectation est désactivée ou fermée

Cela garantit que chaque changement du cycle de vie est attribué à un utilisateur spécifique.

### Responsabilité des soumissions

Pour chaque statut pays/entité au sein d’une cession :

- `submitted_by_user_id` — enregistré lorsqu’un point focal soumet des données
- `approved_by_user_id` — enregistré lorsqu’un administrateur approuve la soumission

Ces champs sont définis automatiquement au moment de l’action et ne peuvent pas être modifiés, ce qui permet une attribution résistante à la falsification.

### Résumé

| Préoccupation | Comment le système le supporte |
|---------|----------------------------|
| Attribution des modifications | Actions admin enregistrées avec utilisateur, type d’action, description et cible |
| Revue des actions sensibles | Niveaux de risque ; les actions à haut risque génèrent des événements de sécurité et apparaissent dans le tableau de bord de sécurité |
| Cycle de vie des affectations | `activated_by` et `deactivated_by` suivis pour chaque affectation |
| Attribution de la soumission | `submitted_by` et `approved_by` suivis par changement d’état d’entité |
| Conformité | Suivi complet des actions administratives pour examen et rapport |

---

## 4. Conformité (Documents FDRS)

Le tableau de bord de gouvernance suit la **conformité aux documents FDRS** : si les pays ont soumis les documents requis (rapport annuel et état financier audité) au cours des périodes de rapport récentes.

- **Taux de conformité** — pourcentage de pays ayant soumis les documents requis
- **Pays non conformes** — signalés avec une liste pouvant être étendue pour voir les pays individuels
- **Seuil de conformité** — le tableau de bord considère 70% or au-dessus comme « OK » pour le score de santé

---

## 5. Complétude des métadonnées

De bonnes métadonnées favorisent la découverte et la cohérence. Le tableau de bord de gouvernance suit :

- **Indicateurs avec définition** — pourcentage d’indicateurs actifs ayant un champ de définition non vide
- **Éléments de formulaire avec étiquette** — pourcentage d’éléments de formulaire sur tous les modèles ayant une étiquette d’affichage
- **Indicateurs archivés** — nombre d’indicateurs déplacés au statut d’archive
- **Modèles publiés jamais attribués** — modèles qui ont été publiés mais jamais utilisés dans une mission (potentiel de gaspillage ou d’oubli)
- **Suggestions obsolètes** — suggestions d’indicateurs soumises il y a plus de 30 jours qui n’ont pas été examinées

---

## 6. Cycle de vie des données et contrôle des changements

Lorsque le chemin du projet à l’approbation est clair et que les changements sont contrôlés, la gouvernance devient plus facile à maintenir.

### Statuts et permissions

Chaque soumission a un **statut** (par exemple non commencée, en cours, soumise, approuvée, rouverte). Ce qu’un utilisateur peut faire (modifier, soumettre, approuver, rouvrir) dépend du **rôle** et du **statut actuel**. Cela empêche des modifications ad hoc après la soumission, sauf si le flux de travail permet une réouverture.

*Voir :* [Statuts de soumission et ce que vous pouvez faire](submission-statuses-and-permissions.md)

### Réouverture et corrections

**La réouverture** (par les approbateurs ou les administrateurs) renvoie une soumission afin que le point focal puisse la corriger et la soumettre à nouveau. Le choix entre rouvrir et créer une nouvelle affectation relève d’une décision de processus ; Documenter les réouvertures (par exemple dans les commentaires ou les procédures) afin que la piste d’audit reste claire.

*Voir :* [Examiner et approuver les soumissions](../admin/review-approve-submissions.md)

### Doublons et soumissions publiques

Pour les soumissions d’URL **publiques**, le système n’empêche pas les doublons. Définissez et documentez comment les doublons sont gérés (par exemple, conserver les derniers, conserver les meilleurs, revoir manuellement) et ce que signifie la « qualité minimale » (champs obligatoires, documents), puis appliquer de manière cohérente le flux de validation et d’approbation.

*Voir :* [Soumissions d’URL publiques](../admin/public-url-submissions.md)

### Résumé

| Préoccupation | Comment le système le supporte |
|---------|----------------------------|
| Cycle de vie clair | Statuts (brouillon → soumis → approuvé) et actions basées sur les rôles |
| Modifications contrôlées après soumission | Réouverture par l’approbateur ; modifier le verrou là où configuré |
| Doublons et qualité des URL publiques | Liste de contrôle de gouvernance et processus cohérents ; Validation et examen dans la plateforme |

---

## 7. Gestion sécurisée des données

La gouvernance inclut la manière dont les données sont exportées, partagées et protégées.

### Exportations (Excel, PDF)

Les exportations sont accessibles aux utilisateurs ayant accès au formulaire d’attribution et d’inscription ; le modèle détermine si Excel ou PDF est activé. Considérez les exportations comme sensibles : ne pas partager via des liens publics, stockez dans des lieux approuvés, conservez une copie non modifiée des exportations brutes, et documentez tout nettoyage manuel.

*Voir :* [Exporter et télécharger les données](../admin/export-download-data.md), [Exports : comment interpréter les fichiers](../admin/exports-how-to-interpret.md)

### Soumissions d’URL publiques

Les URL publiques permettent la soumission sans connexion et peuvent être largement partagées, ce qui leur permet de comporter un risque plus élevé.
Avant utilisation : définissez qui peut soumettre et comment l’URL est partagée, comment les doublons sont gérés, ce que signifie « qualité minimale », et quand le lien sera désactivé (par exemple après la date limite). Surveillez les soumissions et désactivez le lien lorsque la période de collecte se termine.

*Voir :* [Soumissions d’URL publiques](../admin/public-url-submissions.md)

### Gestion des données et confidentialité

Réduisez les risques en évitant les identifiants personnels inutiles dans les soumissions et pièces jointes, et en définissant qui peut accéder aux données sensibles, combien de temps elles sont conservées et comment elles sont partagées. La plateforme assure le contrôle d’accès et l’audit ; Votre organisation définit ce qu’il faut collecter et comment stocker et partager les exportations.

*Voir :* [Gestion des données et confidentialité](data-handling-and-privacy.md)

### Résumé

| Préoccupation | Comment le système le supporte |
|---------|----------------------------|
| Qui peut exporter | Accès au formulaire d’attribution et d’inscription ; Export activé sur le modèle |
| Utilisation sûre des exportations | Documentation et pratiques ; la plateforme fournit le contrôle d’accès et l’audit |
| URLs publiques | Liste de contrôle de gouvernance, surveillance et désactivation lorsqu’elle n’est pas utilisée |
| Confidentialité et sensibilité | Conseils pour la gestion des données ; Contrôle d’accès et audit sur la plateforme |

---

## 8. Tableau de bord de gouvernance

Le **Tableau de bord de gouvernance** (Panneau d’administration → Gouvernance) est une page d’administration dédiée qui met en avant des métriques, des indicateurs et des liens exploitables à travers tous les piliers de gouvernance. Il nécessite la permission `admin.governance.view`.

### Score de santé

Un score de santé de gouvernance **0–100** est calculé à partir de scores pondérés de piliers :

| Pilier | Poids | Ce qu’il mesure |
|--------|--------|------------------|
| Propriété | 18 % | Couverture des points focales, attribution du propriétaire des données |
| Contrôle d’accès | 23 % | Couverture RBAC, accès fantôme, autorisations orphelines |
| Qualité | 23 % | Taux de soumission, suivi en retard |
| Conformité | 23 % | Taux de conformité aux documents FDRS |
| Métadonnées | 13 % | Définitions d’indicateurs, étiquettes d’éléments de type |

Notes : A (≥ 90), B (≥ 75), C (≥ 60), D (≥ 45), F (< 45).

### KPI Strip

Cinq indicateurs clés sont affichés en haut du tableau de bord :

1. **Point focal %** — pourcentage de pays ayant au moins un point focal assigné
2. **Actif sans propriétaire** — nombre d’affectations actives sans propriétaire de données désigné
3. **Accès fantôme** — nombre d’utilisateurs inactifs occupant encore des rôles RBAC
4. **Taux de soumission** — pourcentage des statuts d’entités soumis ou approuvés
5. **Conformité** — Taux de conformité aux documents FDRS

### Panneaux de section

Chaque pilier de gouvernance dispose d’un panneau détaillé avec des barres de progression, des décomptes de drapeaux et des liens vers les pages d’administration concernées :

- **Propriété des données** — couverture des points focaux, couverture des propriétaires des données d’affectation (liens vers les assignations avec filtre `?no_data_owner=1`)
- **Contrôle d’accès** — statistiques RBAC, détection d’utilisateurs fantômes, permissions orphelines, rôles vides
- **Normes de qualité** — taux de soumission, répartition de la sévérité en retard (critique/élevé/moyen), devoirs jamais lancés, tableau de distribution du statut
- **Conformité** — Taux de conformité aux documents FDRS, liste des pays non conformes
- **Métadonnées** — couverture des définitions d’indicateurs, couverture des labels d’éléments du formulaire, modèles publiés et jamais attribués, suggestions obsolètes

### Politiques et Responsabilités

Une matrice de synthèse associe chaque pilier de gouvernance à :
- Ce que ça couvre
- Qui est responsable
- Comment gérer cela
- Statut actuel (OK ou Gaps)

### Liens croisés avec d’autres pages d’administration

Le tableau de bord de gouvernance renvoie directement aux pages administratives concernées avec des filtres pré-appliqués :

| Métrique du tableau de bord | Liens vers | Filtre appliqué |
|-----------------|----------|----------------|
| Affectations actives sans propriétaire de données | Affectations | `?no_data_owner=1` (affiche uniquement les affectations avec propriétaire de données vide) |
| Pays sans point focal | Gestion des affectations | Lien direct |
| Utilisateurs fantômes | Gestion des utilisateurs → Modifier utilisateur | Lien direct par utilisateur |
| Utilisateurs ayant accès à l’entité mais sans rôle | Gestion des utilisateurs → Modifier utilisateur | Lien direct par utilisateur |

---

## 9. Pratiques opérationnelles soutenant la gouvernance

Les pratiques suivantes contribuent à maintenir la gouvernance dans l’usage quotidien.

### Exécution d’un cycle de rapports

- **Avant le lancement :** Convenir de la période de rapport, des pays participants et de ce que signifie « bonne qualité » (documents requis, attentes de validation). Assignez un **propriétaire des données** pour la mission.
- **Accès :** Confirmer que les points focaux ont les bons rôles et accès au pays avant l’ouverture de la mission.
- **Pendant la collecte :** Surveillez la progression (non commencée, en cours, soumise, en retard) et utilisez des validations et des rappels pour améliorer la complétude. Utilisez le tableau de bord de gouvernance pour suivre la gravité des retards.
- **Révision :** Utilisez une liste de contrôle cohérente (par exemple champs obligatoires, valeurs aberrantes, cohérence) lors de l’approbation des soumissions.
- **Après le cycle :** Document les décisions (par exemple, prolongations de délai, règle du doublon pour les soumissions publiques, problèmes connus) pour le cycle suivant. Consultez le tableau de bord de gouvernance pour la santé globale.

*Voir :* [Lancer un cycle de rapport (manuel administratif)](../admin/run-a-reporting-cycle.md)

### Modèles et régularité

- Utiliser la Banque d’indicateurs et lier les champs de formulaire aux indicateurs lorsque des données comparables entre pays et périodes sont requises.
- Attribuer un **Propriétaire du Modèle** à chaque modèle publié afin qu’il y ait un propriétaire clair pour la norme de données.
- Éviter des changements substantiels de gabarit en cours de cycle ; Utilisez une nouvelle affectation ou une nouvelle version lorsque les définitions ou la structure changent significativement.
- Validation des tests et champs requis (par exemple avec une petite affectation) avant le déploiement complet.

*Voir :* [Créer un modèle](../admin/create-template.md), [Modifier un modèle (Constructeur de formulaires)](../admin/edit-template.md)

### Gestion des utilisateurs et des rôles

- Attribuer les rôles selon les besoins ; Évitez de trop subventionner (par exemple, gérer le système uniquement pour le personnel nécessitant un contrôle total).
- Documenter la justification des subventions d’accès au rôle et aux pays afin que les examens et audits d’accès soient simples.
- Utiliser la trace d’audit et le tableau de bord de sécurité pour examiner les actions à haut risque (par exemple, suppression d’utilisateurs, changements de rôle).
- Réviser régulièrement le **Tableau de bord de gouvernance** pour détecter les accès fantômes (utilisateurs inactifs avec des rôles) et corriger rapidement.
- Examiner les utilisateurs ayant des autorisations d’entité mais sans rôle RBAC — ils peuvent avoir besoin d’un rôle assigné ou de supprimer leur accès à l’entité.

*Voir :* [Rôles et permissions utilisateur](../admin/user-roles.md), [Gérer les utilisateurs](../admin/manage-users.md)

---

## Référence rapide : fonctionnalités de gouvernance dans la plateforme

| Zone | Fonctionnalité | Référence |
|------|---------|-----------|
| **Tableau de bord de gouvernance** | Score de santé, bande KPI, panneaux de piliers, drapeaux | Panneau d’administration → Gouvernance |
| **Propriété des données** | Propriétaire du modèle (par modèle) | Panneau d’administration → Constructeur de formulaires → Modifier le modèle |
| **Propriété des données** | Propriétaire des données (par attribution) | Panneau d’administration → Assignations → Créer/Modifier |
| **Propriété des données** | Données organisationnelles (FDS) | Ce document — [Propriété des données](#data-ownership) |
| Accès | Rôles (RBAC), assignation pays/entité | [Rôles et permissions utilisateur](../admin/user-roles.md) |
| Accès | Détection d’accès fantôme | Tableau de bord de gouvernance → Contrôle d’accès |
| Accès | Actions autorisées par statut | [Statuts et autorisations de soumissions](submission-statuses-and-permissions.md) |
| Qualité | Définitions standard | [Banque d’indicateurs](../admin/indicator-bank.md) |
| Qualité | Validation, champs obligatoires | [Constructeur de formulaires (avancé)](../admin/form-builder-advanced.md), [Modifier le modèle](../admin/edit-template.md) |
| Qualité | Suivi en retard avec sévérité | Tableau de bord de gouvernance → Normes de qualité |
| Qualité | Examen et approbation | [Examiner et approuver les soumissions](../admin/review-approve-submissions.md) |
| Responsabilité | Journal d’actions admin, niveaux de risque | [Admin action risk levels](../../workflows/admin/admin-action-risk-levels.md) |
| Responsabilité | `submitted_by` / `approved_by` suivi | Automatique sur les changements de statut |
| Responsabilité | `activated_by` / `deactivated_by` suivi | Changements automatiques du cycle de vie sur assignation |
| Conformité | Taux de conformité aux documents FDRS | Tableau de bord de gouvernance → conformité |
| Métadonnées | Couverture de la définition des indicateurs | Tableau de bord de gouvernance → métadonnées |
| Métadonnées | Détection de suggestion obsolète | Tableau de bord de gouvernance → métadonnées |
| Cycle de vie | Statuts, réouverture | [Statuts de soumissions](submission-statuses-and-permissions.md), [Examiner et approuver](../admin/review-approve-submissions.md) |
| Manipulation sécurisée | Exportations | [Exporter et télécharger les données](../admin/export-download-data.md) |
| Manipulation sécurisée | URLs publiques | [Soumissions d’URL publiques](../admin/public-url-submissions.md) |
| Manipulation sécurisée | Confidentialité et sensibilité | [Gestion des données et confidentialité](data-handling-and-privacy.md) |
| Opérations | Cycle de bout en bout | [Exécuter un cycle de rapport](../admin/run-a-reporting-cycle.md) |

---

## Champs de bases de données soutenant la gouvernance

Les champs suivants ont été ajoutés pour soutenir la responsabilité en matière de gouvernance :

### `AssignedForm` (niveau d’affectation)

| Champ | But |
|-------|---------|
| `data_owner_id` | Utilisateur responsable de la qualité des données pendant ce cycle de collecte |
| `activated_by_user_id` | Utilisateur qui a activé ou rouvert l’attribution |
| `deactivated_by_user_id` | Utilisateur qui a désactivé ou fermé l’attribution |

### `AssignmentEntityStatus` (statut par pays au sein d’une affectation)

| Champ | But |
|-------|---------|
| `submitted_by_user_id` | Utilisateur qui a soumis les données pour cette entité |
| `approved_by_user_id` | Utilisateur ayant approuvé la soumission pour cette entité |

---

## Annexe : Alignement avec Microsoft View.

Pour les organisations utilisant ou évaluant **Microsoft Champview**, la cartographie suivante montre comment la structure et le langage de ce document s’alignent avec le cadre de gouvernance des données de Purview.

| Concept de champ d’action | Équivalent de la Banque de données humanitaire |
|-----------------|----------------------------------|
| **Propriétaire des données** (individu ou groupe responsable de la gestion d’un actif de données) | **Propriétaire du modèle** (niveau modèle) ; **Propriétaire des données** (niveau d’affectation) ; **FDS** (données de l’organisation) |
| **Responsable des données** (maintien de la nomenclature, des normes de qualité des données et des règles) | **Gestionnaires de la Banque Indicatrice** ; administrateurs qui définissent la validation et les champs obligatoires |
| **Glossaire / Termes du glossaire** (vocabulaire et définitions commerciales) | Banque d’indicateurs comme glossaire commercial des définitions standard des indicateurs |
| **Domaine de gouvernance** (frontière pour la gouvernance, la propriété, la découverte) | Limite de gouvernance au niveau de la plateforme (données organisationnelles, Banque d’Indicateurs) et portée d’attribution/entité pour les données collectées |
| **Contrôle d’accès / RBAC** | Rôles et permissions ; l’attribution de pays et d’entités ; contrôles à l’exportation ; Détection d’accès fantôme |
| **Classification / Sensibilité** (étiquettes de sensibilité, traitement des données sensibles) | la gestion des données et les conseils sur la confidentialité ; Traitement des données sensibles dans les soumissions et exportations |
| **Trace d’audit** | Journalisation des actions administratives avec les niveaux de risque ; `submitted_by` / `approved_by` / `activated_by` / `deactivated_by` attribution ; Tableau de bord de sécurité pour les actions à haut risque |
| **Qualité des données** (complétude, cohérence, conformité, etc.) | Champs obligatoires, règles de validation, définitions standard, flux de travail de soumission et d’approbation, suivi en retard avec des catégories de sévérité |
| **Flux de travail** (validation et approbation) | Statut des soumissions ; approuver ; Réouverture |
| **Évaluation santé / Conformité** | Score de santé du tableau de bord de gouvernance (0–100) avec scores piliers pondérés |

*Voir :* [Glossaire de gouvernance des données Microsoft Purview](https://learn.microsoft.com/en-us/purview/data-governance-glossary), [Commencez avec la gouvernance des données dans Microsoft Purview](https://learn.microsoft.com/en-us/purview/data-governance-get-started)

---

## Documentation associée

- [Gestion des données et confidentialité](data-handling-and-privacy.md) — Pratiques pour les soumissions, exportations et URL publiques
- [Comment fonctionne la plateforme](../getting-started/how-it-works.md) — Modèles, devoirs et flux de soumission
- [Obtenir de l’aide](getting-help.md)
