# Exports : comment interpréter les fichiers (administrateur)

Utilisez ce guide lorsque vous avez téléchargé un export (CSV/Excel) et que vous voulez comprendre ce que signifient les colonnes et comment éviter les erreurs courantes.

## Avant de commencer

- Le contenu de l'export dépend du modèle et de votre flux de travail.
- Si votre export prend en charge les "filtres" (statut, pays, période), notez ce que vous avez sélectionné pour pouvoir le reproduire.

## Ce que vous obtenez généralement dans un export

La plupart des exports incluent un mélange de :

- **Colonnes de métadonnées** (contexte)
  - nom de mission / ID de mission
  - pays / organisation
  - statut de soumission
  - horodatages soumis/mis à jour
  - soumis par (utilisateur)
- **Colonnes de réponses** (vos champs de modèle)
  - une colonne par champ, ou plusieurs colonnes pour les champs complexes (comme les matrices)
- **Codes/ID**
  - ID internes, codes d'indicateurs ou ID de questions qui aident à joindre les ensembles de données de manière fiable

## Comment les champs matrice/tableau s'exportent généralement

Les réponses de matrice deviennent souvent plusieurs colonnes, par exemple :
- une colonne par ligne (si c'est une colonne numérique unique), ou
- combinaisons ligne × colonne (si c'est une matrice multi-colonnes)

Astuce : Gardez les en-têtes de colonnes tels quels jusqu'à ce que vous ayez terminé de nettoyer votre ensemble de données ; les renommer trop tôt rend difficile la comparaison entre les périodes.

## Comment éviter les erreurs "mauvais export"

### Confirmez que vous avez exporté la bonne portée

Avant l'analyse, confirmez :
- le nom de la mission et la période sont corrects
- la liste des pays correspond à votre portée prévue
- le filtre de statut correspond à votre intention (par exemple uniquement "Approuvé")

### Attention aux changements de version de modèle

Si les versions de modèle ont changé entre les périodes, les exports peuvent différer :
- de nouvelles colonnes apparaissent
- d'anciennes colonnes disparaissent
- les significations changent (pire cas)

Recommandation :
- Pour les changements majeurs, traitez-le comme un nouvel instrument de reporting et documentez clairement le changement.

## Approche de nettoyage recommandée (simple et sûre)

1. **Gardez une copie brute** de l'export (ne la modifiez pas).
2. Faites une copie de travail et ajoutez vos étapes de nettoyage là.
3. Gardez les ID/codes :
   - ils aident avec les fusions et la déduplication
4. Si vous avez besoin d'une seule ligne "pays-période", décidez comment vous gérerez :
   - les soumissions multiples
   - les entrées rouvertes/re-soumises

## Problèmes courants

- **L'export manque un pays** : le pays peut ne pas être inclus dans la mission, n'a pas soumis, ou vous devez l'exporter séparément depuis la page du formulaire d'entrée.
- **Les chiffres ne correspondent pas au formulaire** : vérifiez la version du modèle/période et si l'arrondi ou le formatage est appliqué.
- **Lignes en double** : vous avez exporté plusieurs statuts (brouillon + soumis + approuvé) ou plusieurs soumissions existent.
- **L'export prend trop de temps** : exportez des portées plus petites (une mission à la fois).

## Liens connexes

- [Exporter et télécharger les données](export-download-data.md)
- [Exécuter un cycle de reporting](run-a-reporting-cycle.md)
- [Statuts de soumission et ce que vous pouvez faire](../common/submission-statuses-and-permissions.md)
