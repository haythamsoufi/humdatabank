# Versions de modèle : brouillon, déploiement et retour arrière

Toute modification qui affecte la façon de remplir un formulaire passe par une **version**. Ce guide explique ce qu'il advient des données soumises lorsque vous créez, déployez, annulez ou supprimez une version, et ce que le système vérifie pour vous.

## En bref

- Vous ne modifiez jamais le formulaire en ligne pendant que des personnes le remplissent. Vous travaillez sur un **brouillon**, puis vous le **déployez**.
- Au déploiement, les réponses déjà soumises sont **reportées** vers les mêmes champs de la nouvelle version.
- Les champs supprimés ne sont **pas effacés**. Leurs données restent sur la version archivée.
- En cas de problème, vous pouvez **revenir en arrière** en redéployant la version archivée.

## États d'une version

| État | Signification | Qui la voit |
|---|---|---|
| **Brouillon** | Travail en cours. Un seul brouillon par modèle. | Les administrateurs dans le Form Builder |
| **Publiée** | La version en ligne. Exactement une par modèle. | Les points focaux qui remplissent les affectations |
| **Archivée** | Une ancienne version en ligne. Sa structure et ses données sont conservées. | Les administrateurs (peut être redéployée) |

## Créer une nouvelle version

1. Ouvrez le modèle dans le Form Builder et cliquez sur **Versions**.
2. Cliquez sur **Add New Version**. Le brouillon est une copie complète de la version consultée : structure, règles, variables, traductions et paramètres.
3. Modifiez le brouillon librement. Rien ne change pour les points focaux avant le déploiement.

Remarques :

- Un seul brouillon peut exister à la fois. Déployez ou abandonnez d'abord le brouillon en cours.
- Les règles, conditions, filtres de liste, champs « libellé d'entrée » des sections et variables du brouillon continuent de fonctionner : ils sont redirigés vers les champs copiés.

## Identité des champs : comment le système sait que deux champs sont « les mêmes »

Chaque champ et chaque section possède une **clé d'identité** cachée. Une copie conserve la clé de l'original ; après le déploiement, le système sait donc que « Nombre de volontaires » de la version 3 est le même champ que dans la version 2, même s'il a été renommé ou déplacé.

- Si vous **renommez, déplacez ou reformulez** un champ, l'identité reste et les données suivent.
- Si vous **supprimez un champ et en ajoutez un nouveau**, le nouveau champ a une nouvelle identité et démarre vide.
- Les clés ne sont jamais écrasées en fonction de la position. La position ne sert qu'à réparer d'anciens modèles créés avant les clés d'identité.

## Vérifier la correspondance des champs avant de déployer

Ouvrez **Versions → Review field mapping** (icône de lien) sur le brouillon.

| Badge | Signification | Effet au déploiement |
|---|---|---|
| **Linked** (Lié) | Même identité qu'un champ en ligne | Les données sont reportées |
| **Suggested** (Suggéré) | Correspondance supposée par la position | Confirmez ou choisissez un autre champ |
| **New field** (Nouveau champ) | Aucun équivalent en ligne | Démarre vide |
| **Orphaned** (Orphelin) | Champ en ligne sans correspondance dans le brouillon | Les données restent sur la version archivée |

### Lier un champ du brouillon à un champ en ligne

Utilisez cette option lorsque vous avez remplacé un champ et que vous voulez que ses réponses le suivent.

- **Des types de champs différents ne peuvent pas être liés** (par exemple une question et une matrice, ou une section standard et une section répétable). Leurs données sont stockées différemment.
- Si les types correspondent mais que le **type de données** (par exemple nombre ou texte) ou l'**indicateur** diffère, une confirmation vous est demandée. Les réponses existantes sont reportées telles quelles : un champ numérique lié à un champ texte peut afficher des valeurs inattendues.
- Si le champ en ligne est déjà lié à un autre champ du brouillon, il vous est demandé si le lien doit être déplacé. L'autre champ du brouillon devient un nouveau champ.
- **Mark as new field** supprime un lien : le champ démarre vide.

## Déployer

Cliquez sur **Deploy**. Le système :

1. Vérifie que chaque champ indicateur a un indicateur valide.
2. Vérifie que deux champs du brouillon ne partagent pas la même identité (sinon le déploiement s'arrête et rien ne change).
3. Déplace les réponses, lignes répétées, données d'indicateurs dynamiques, documents téléversés et statuts de workflow de page vers les champs et pages correspondants de la nouvelle version.
4. Redirige les variables du modèle qui lisent un champ.
5. Archive la version précédente et publie la nouvelle.
6. Recalcule les taux de complétion et vide le cache de structure du formulaire.

Si une étape échoue, le déploiement est annulé en entier : la version précédente reste en ligne.

### Champs contenant des données mais supprimés du brouillon

Si des champs en ligne contenant des données soumises n'ont aucune correspondance dans le brouillon, vous devez le **reconnaître** :

- Dans le Form Builder, la boîte de confirmation indique le nombre de champs concernés. Confirmer lance le déploiement.
- Sur la page de correspondance des champs, cochez la case située à côté de **Deploy**.

Rien n'est supprimé. Les données restent sur la version archivée, mais n'apparaissent plus dans le formulaire de saisie ni dans les exports de la version en ligne. Si ce n'est pas voulu, liez les champs (voir ci-dessus) ou retournez dans le Form Builder.

### Pendant que des personnes saisissent des données

- Un déploiement attend la fin d'un enregistrement en cours, afin que les réponses enregistrées soient reportées.
- Un point focal qui a ouvert le formulaire **avant** le déploiement et clique sur **Enregistrer** **après** voit : *« This form was updated while you were working on it. Reload the page… »*. Son enregistrement est refusé au lieu d'être perdu en silence ; après rechargement, il ressaisit les modifications non enregistrées.
- Planifiez les gros déploiements en dehors des heures de forte activité et demandez aux points focaux d'enregistrer avant de déployer.

## Revenir en arrière

Ouvrez **Versions** et déployez une version **archivée**. Les réponses saisies depuis sont reportées en arrière, et les champs archivés par un déploiement précédent sont restaurés. La même confirmation s'applique si des champs ajoutés après cette version contiennent des données.

## Abandonner un brouillon ou supprimer une version

- **Discard draft** supprime le brouillon et sa structure. La version en ligne n'est jamais touchée.
- **Delete version** n'est disponible que pour les versions non publiées. Elle est **bloquée** tant que des données soumises, instances répétées, documents téléversés, validations IA ou statuts de page sont liés à la version. Archivez plutôt que de supprimer.
- La suppression d'une version ne renumérote pas les autres. Un nouveau brouillon prend toujours le prochain numéro libre.

## Pages

Si le modèle est paginé, une page qui a déjà une progression de workflow (par exemple « soumise ») **ne peut pas être supprimée** de la version en ligne. Créez un brouillon, supprimez-y la page et déployez-le. Les pages sans progression peuvent être supprimées librement.

## Dupliquer un modèle

**Duplicate** crée un modèle indépendant à partir de la version en ligne. Les variables qui lisent un champ sont redirigées vers la copie de ce champ : le nouveau modèle ne lit jamais les données de l'ancien.

## Déploiement bloqué : signification des messages

| Message | Cause | Que faire |
|---|---|---|
| *The selected version was not found for this template.* | Page périmée ou mauvais lien | Rechargez le Form Builder |
| *Cannot deploy this version: N indicator item(s) have missing/invalid indicator references.* | Champs indicateur sans indicateur | Corrigez les champs signalés |
| *N field(s) in the live version hold submitted data but have no match…* | Champs supprimés contenant des données | Vérifiez la correspondance, puis confirmez |
| *Cannot deploy: N field/section identity key(s) are shared by more than one…* | Deux champs partagent une identité | Demandez à un développeur d'exécuter l'audit des versions de modèle (voir le runbook) |
| *Cannot deploy: N submission row(s) exist on the previous version but no fields could be matched…* | Ancien modèle sans clés d'identité | Demandez à un développeur d'exécuter le remplissage des clés d'identité |
| *Cannot delete this version: N data record(s) are linked…* | Des données existent sur cette version | Gardez la version archivée |
| *Cannot remove page …* | La page a une progression de workflow | Supprimez-la dans un nouveau brouillon |

## Bonnes pratiques

- Faites **un déploiement par changement de collecte** et testez d'abord le brouillon avec une affectation à un seul pays.
- Vérifiez la page de correspondance des champs chaque fois que vous renommez ou restructurez des champs.
- Préférez **renommer** un champ plutôt que de le supprimer puis le recréer, afin que les données suivent.
- Évitez de changer le **type de données** d'un champ qui contient déjà des données. Ajoutez plutôt un nouveau champ.
- Ne supprimez pas les versions archivées vers lesquelles vous pourriez devoir revenir.

## Voir aussi

- [Modifier un modèle (Form Builder)](edit-template.md)
- [Form Builder (avancé)](form-builder-advanced.md)
- [Dépannage des modèles et affectations](troubleshooting-templates-and-assignments.md)
