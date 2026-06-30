# Chatbot IA

Ce guide explique comment utiliser le chatbot IA, ce qu’il peut faire, comment fonctionnent les accès et les permissions, et comment les contrôles de confidentialité des documents influencent ce que l’assistant peut trouver et référencer.

## Aperçu

Le chatbot IA est un assistant intégré au Backoffice qui peut répondre à vos questions sur vos données, rechercher les documents téléchargés et vous aider à naviguer sur la plateforme. Il est disponible sous forme de **widget flottant** sur la plupart des pages et en *vue immersive plein écran** pour des conversations plus longues.

Le chatbot utilise la génération augmentée par récupération (RAG) : lorsque vous posez une question, il peut rechercher dans la base de données, les documents téléchargés et les guides de workflow, puis utiliser ces résultats comme contexte pour sa réponse.

## Avant que tu commences

- Il faut un compte dans le Backoffice pour utiliser le chatbot. L’accès anonyme est limité (voir [Niveaux d’accès](#access-levels) ci-dessous).
- Le chatbot nécessite qu’au moins un fournisseur d’IA soit configuré par votre administrateur (par exemple OpenAI, Gemini ou Azure OpenAI).
- Les réponses IA peuvent être incorrectes. Vérifiez toujours les informations importantes.

---

## Utilisation du chatbot

### Lancer une conversation

1. Ouvrez le widget chatbot en cliquant sur l’icône de chat en bas à droite de n’importe quelle page, ou naviguez vers la vue immersive en plein écran** depuis le tableau de bord.
2. Tapez votre question dans le champ de saisie et appuyez sur **Envoyer** (ou appuyez sur Entrée).
3. L’assistant traitera votre question — vous pouvez voir un indicateur « réflexion » pendant qu’il récupère des données ou effectue des recherches dans des documents.

### Prompts rapides

La vue immersive propose des exemples d’idées pour vous aider à démarrer :

- « Combien de volontaires au Bangladesh ? »
- « Volontaires en Syrie au fil du temps »
- « Carte thermique mondiale des bénévoles par pays »
- « Nombre d’agences au Kenya »
- « État-major et unités locales au Nigeria »

### Gestion de la conversation

- **Nouvelle discussion** — Commence une nouvelle conversation à tout moment.
- **Recherche** — Trouvez les conversations précédentes par mot-clé.
- **Supprimer** — Supprimer une seule conversation ou effacer toutes les conversations. La suppression est permanente.

### Contrôles de source de données

La zone d’entrée comprend un bouton **sources de données** (icône curseur) qui vous permet de choisir les sources que l’assistant recherche :

| Source | Ce qu’elle inclut |
|--------|-----------------|
| **Banque de données** | Valeurs des indicateurs, données par pays et soumissions de formulaires stockées sur la plateforme |
| **Documents système** | Documents téléchargés dans la bibliothèque de documents IA par les administrateurs |
| **Documents UPR** | Documents unifiés de planification et de rapport |

Vous pouvez activer ou désactiver chaque source par message. Désactiver une source signifie que l’assistant ne recherchera ni ne récupérera cette requête.

### Édition et réessai

- **Édit** un message envoyé pour reformuler votre question. L’assistant régénère sa réponse à partir du texte édité.
- **Réessayer** une réponse d’assistant si la réponse était insatisfaisante.
- **Copie** toute réponse d’assistant à ton clipboard.

### Retour d’information

Utilisez les boutons **J’aime** et **J’aime pas** sur n’importe quel message d’assistant pour donner un retour. Cela aide les administrateurs à surveiller la qualité et à améliorer le système.

---

## Niveaux d’accès et rôles (RBAC)

Le chatbot respecte le contrôle d’accès basé sur les rôles de la plateforme. Votre rôle détermine quelles données l’assistant peut accéder en votre nom.

### Niveaux d’accès

| Niveau d’accès | Qui | Capacités des chatbots |
|--------------|-----|---------------------|
| **Gestionnaire système** | Administrateur à l’échelle de la plateforme | Accès complet à toutes les données, documents, pays et outils. Exempté des plafonds de tarif journaliers par utilisateur. |
| **Admin** | Administrateur d’organisation | Accès complet à toutes les données, documents et pays. Des limites de taux standard s’appliquent. |
| **Utilisateur** (point focal, vue uniquement, etc.) | Utilisateur authentifié régulier | L’accès est limité aux pays assignés. Documents filtrés par paramètres de confidentialité (voir ci-dessous). Des limites de taux standard s’appliquent. |
| **Public** (anonyme) | Visiteur non authentifié via le site web | Seuls les documents publics sont visibles. Aucune persévérance dans la conversation. Des limites de taux plus strictes. |

### Ce que chaque rôle peut voir à travers le chatbot

#### Gestionnaire système et administrateur

- Toutes les données des indicateurs pour tous les pays
- Tous les documents, quels que soient les paramètres de confidentialité
- Tous les modèles de formulaires, devoirs et soumissions
- Statistiques système et informations utilisateur
- Tous les guides de workflow

#### Focal Point et autres utilisateurs authentifiés

- Données indicatrices pour **pays assignés uniquement** — l’assistant ne retournera pas les données pour les pays auxquels vous n’êtes pas assigné
- Documents marqués comme **publics**, documents que vous **possédez**, et documents dont votre rôle est inclus dans la liste **autorisée** du document
- Devoirs et soumissions pour les pays qui vous sont assignés
- Guides de flux de travail disponibles pour votre poste

#### Anonymes / Utilisateurs publics

- Uniquement les documents explicitement marqués comme **publics** (sans restriction de rôle, ou avec `public` dans la liste des rôles autorisés)
- Données générales d’indicateurs (non limitées à des affectations spécifiques)
- Aucune persistance de conversation — l’historique n’existe que dans la session du navigateur

### Permissions transmises à l’assistant

Lorsque vous envoyez un message, le système construit un **contexte d’accès** qui inclut :

- Votre rôle et votre niveau d’accès
- Vos identifiants de pays assignés (le cas applicable)
- Un ensemble de drapeaux d’autorisation (par exemple, si vous pouvez consulter des modèles, des affectations, des documents, des utilisateurs)

Ce contexte circule avec chaque requête, donc l’assistant et ses outils appliquent les mêmes limites que le reste de la plateforme. L’assistant ne peut pas contourner vos permissions — si vous ne pouvez pas voir certaines données dans l’interface Backoffice, l’assistant ne peut pas les voir non plus.

---

## Confidentialité des documents

Les documents de la bibliothèque de documents IA disposent de contrôles de confidentialité qui déterminent qui peut les trouver via le chatbot. Ces contrôles sont définis par les administrateurs lors du téléchargement ou de la gestion de documents.

### Champs de confidentialité

Chaque document dispose de deux paramètres de visibilité :

| Champ | Valeurs | Effet |
|-------|--------|--------|
| **Public** (`is_public`) | Oui / Non | Si **Oui**, le document est visible pour tous les utilisateurs (y compris les visiteurs anonymes), sous réserve du filtre des rôles autorisés. Si **Non**, seuls le propriétaire du document, les utilisateurs dont le rôle correspond à `allowed_roles` et les administrateurs peuvent le voir. |
| **Rôles autorisés** (`allowed_roles`) | Une liste de rôles, ou vide | Si **vide** (nulle), tout utilisateur qui passe le contrôle public/propriété peut voir le document. Si elle est activée (par exemple `admin`, `focal_point`), seuls les utilisateurs ayant un rôle correspondant (plus le propriétaire et les administrateurs) peuvent la voir. |

### Visibilité effective par combinaison

| `is_public` | `allowed_roles` | Qui peut trouver ce document |
|-------------|-----------------|---------------------------|
| Oui | Vide | Tout le monde, y compris les utilisateurs anonymes |
| Oui | `[admin, focal_point]` | Utilisateurs anonymes et tout utilisateur authentifié dont le rôle figure dans la liste (plus les administrateurs/gestionnaires système) |
| Non | Vide | Propriétaire du document + administrateurs uniquement/gestionnaires système |
| Non | `[focal_point]` | Propriétaire du document + points focales + administrateurs/gestionnaires système |

**Règles clés :**

- **Les administrateurs et gestionnaires système voient toujours tous les documents**, quels que soient les paramètres de confidentialité.
- **Les propriétaires de documents voient toujours leurs propres documents**, quels que soient les paramètres de confidentialité.
- **Les utilisateurs anonymes** ne voient que les documents où `is_public = Yes` et soit `allowed_roles` est vide, soit incluent `public`.

### Comment la vie privée affecte les réponses des chatbots

Lorsque vous posez une question impliquant la recherche de documents, l’assistant effectue une recherche de similarité (vectorielle ou hybride) avec la bibliothèque de documents IA. Avant de retourner les résultats, le système applique un **filtre d’autorisation** qui applique les règles ci-dessus. Les documents que vous n’êtes pas autorisé à consulter sont totalement exclus des résultats de recherche — l’assistant ne citera pas, ne résumera pas ou ne citera pas le contenu de documents hors de votre accédre.

Cela signifie que deux utilisateurs posant la même question peuvent recevoir des réponses différentes s’ils ont accès à des ensembles de documents différents.

---

## Ce que l’assistant peut faire (outils)

Le chatbot a accès à un ensemble d’outils qu’il peut utiliser pour répondre à vos questions. Ces outils interrogent des données en direct de la plateforme — ils ne reposent pas uniquement sur des connaissances pré-entraînées.

### Outils de recherche de données

| Outil | Ce que ça fait |
|------|-------------|
| **Obtenir la valeur de l’indicateur** | Récupère une valeur indicatrice spécifique pour un pays et une période |
| **Obtenir une série temporelle indicatrice** | Récupère les valeurs historiques d’un indicateur sur plusieurs années |
| **Obtenir des métadonnées indicatrices** | Retourne la définition, l’unité et d’autres détails concernant un indicateur |
| **Obtenir les valeurs indicatrices pour tous les pays** | Récupère un indicateur spécifique pour tous les pays (utile pour les comparaisons et les cartes) |
| **Obtenir des informations sur le pays** | Retour de détails sur un pays (Société nationale, région, etc.) |
| **Comparer les pays** | Comparaison côte à côte de plusieurs pays sur des indicateurs sélectionnés |

### Outils de formulaires et d’attribution

| Outil | Ce que ça fait |
|------|-------------|
| **Obtenir la valeur du champ forme** | Récupère une valeur de champ spécifique à partir d’une soumission de formulaire |
| **Obtenir les valeurs des indicateurs d’affectation** | Récupère les valeurs des indicateurs d’une affectation spécifique |
| **Obtenir des attributions d’utilisateurs** | Liste vos attributions (ou toutes les affectations pour les administrateurs) |
| **Obtenez les détails du modèle** | Retourne la structure et les champs d’un modèle de formulaire |

### Outils de recherche de documents

| Outil | Ce que ça fait |
|------|-------------|
| **Liste des documents** | Liste des documents disponibles (filtrés selon vos permissions) |
| **Recherchez des documents** | Recherche sémantique (vectoriel) à travers le contenu du document |
| **Rechercher des documents (hybride)** | Recherche combinée mot-clé + sémantique pour un meilleur rappel |

### Outils UPR

| Outil | Ce que ça fait |
|------|-------------|
| **Obtenez la valeur du KPI UPR** | Récupère une valeur d’un KPI unifié de planification et de reporting |
| **Obtenez des séries temporelles KPI UPR** | Valeurs historiques des KPI UPR au fil du temps |
| **Obtenez les valeurs des KPI UPR pour tous les pays** | Valeurs des KPI du RPU dans tous les pays |
| **Analyser les domaines d’intervention des plans unifiés** | Analyse les domaines d’intervention à travers les plans unifiés |

### Flux de travail et outils système

| Outil | Ce que ça fait |
|------|-------------|
| **Obtenez le guide du flux de travail** | Récupère un guide de workflow étape par étape (filtré par votre rôle) |
| **Rechercher des documents de workflow** | Recherche dans la documentation du workflow (filtrée par votre poste) |
| **Valider selon les directives** | Valide les données selon les directives de la plateforme |
| **Obtenir les informations utilisateur actuelles** | Informations de retour concernant votre compte et permissions |
| **Obtenir les statistiques système** | Statistiques à l’échelle de la plateforme (administration uniquement) |

Tous les outils respectent votre niveau d’accès. Par exemple, les outils de récupération de données ne retourneront que les données des pays auxquels vous êtes affecté (sauf si vous êtes administrateur), et les outils documentaires ne retourneront que les documents que vous êtes autorisé à consulter.

---

## Limites de taux

Pour garantir l’utilisation équitable et la stabilité du système, le chatbot applique des limites de débit :

| Limite | Utilisateurs authentifiés | Gestionnaires système | Anonyme |
|-------|-------------------|-----------------|-----------|
| **Par minute** | 120 requêtes | 120 requêtes | 60 requêtes |
| **Par jour (utilisateur)** | 1 000 000 | Exempté | N/A |
| **Par jour (à l’échelle du système)** | 5 000 000 au total pour tous les utilisateurs | — | — |

Si vous atteignez une limite de débit, attendez un instant avant d’envoyer un autre message. La limite se réinitialise après la fenêtre de temps concernée.

---

## Avis de confidentialité et de sécurité

Le chatbot affiche deux avis importants :

1. **« Ne partagez pas d’informations sensibles. » ** — Le système envoie vos messages à des fournisseurs d’IA externes pour traitement. Évitez d’inclure des mots de passe, des jetons, des clés API, des données personnelles ou d’autres identifiants.
2. **« L’IA peut faire des erreurs. Vérifiez les informations importantes. » ** — Les réponses générées par l’IA peuvent être inexactes. Vérifiez toujours les données critiques par rapport à la source.

### Protections intégrées

La plateforme comprend plusieurs couches de protection pour réduire l’exposition accidentelle d’informations sensibles :

- **Prévention de la perte de données (DLP)** — Les messages sortants sont scannés à la recherche de schémas sensibles courants (emails, jetons, clés, numéros de carte). Selon la configuration, le système peut vous avertir, demander une confirmation ou bloquer le message.
- **Nettoyage des PII** — Avant que le contenu ne soit envoyé à des fournisseurs externes, le système expurge des informations personnelles identifiables détectées.
- **Minimisation du contexte de la page** — Lorsque le chatbot envoie le contexte de la page pour aider à répondre à des questions liées à l’interface utilisateur, les champs à haut risque (comme les URL) sont supprimés.

Pour un résumé de l’utilisation acceptable et des garanties, voir la [Politique d’utilisation IA](ai-use-policy.md). Demandez à votre administrateur si vous avez besoin de plus de détails sur la configuration des contrôles de sécurité.

---

## Conseils

- **Soyez précis** — Incluez le pays, l’indicateur et la période dans votre question pour des réponses plus précises.
- **Utilisez des contrôles de source de données** — Si vous ne souhaitez que des réponses provenant de documents téléchargés, désactivez la source de la base de données (et vice versa).
- **Vérifier la source** — Lorsque l’assistant fait référence au contenu du document, vérifiez-le par rapport au document original.
- **Utilisez la vue immersive** pour des conversations analytiques plus longues — la mise en page plein écran est meilleure pour lire des graphiques, des tableaux et des réponses détaillées.
- **Exporter les conversations importantes** avant de les effacer — la suppression est permanente.

## Problèmes courants

| Problème | Que vérifier |
|---------|--------------|
| Le chatbot n’est pas disponible | Demandez à votre administrateur si un fournisseur d’IA est configuré et activé. |
| Erreur « Aucun fournisseur configuré » | Au moins une clé fournisseur d’IA (OpenAI, Gemini ou Azure) doit être configurée dans l’environnement. |
| L’assistant ne trouve pas un document que j’ai téléchargé | Vérifiez les paramètres de confidentialité du document sur la mission ou le formulaire (s’il est marqué comme consultable) et si le traitement est terminé. Si cela doit être consultable et que cela n’apparaît toujours pas, demandez à votre administrateur. |
| L’assistant retourne les données du mauvais pays | Reformulez votre question avec le nom complet du pays. Vérifiez que vous êtes affecté à ce pays. |
| Limite de taux atteinte | Attends une minute et essaie encore. Si le problème persiste, contactez votre administrateur. |
| Avertissement DLP sur mon message | Le système a détecté un schéma qui ressemble à des données sensibles. Supprimez ou remplacez le contenu sensible et réenvoyez-le. |
| L’historique des conversations manque | Si vous utilisez le mode public/anonyme, les conversations ne sont pas sauvegardées. Connectez-vous pour poursuivre les conversations. |

## Liés

- [Politique d’utilisation de l’IA](ai-use-policy.md) — Utilisation acceptable, gestion des données et responsabilités
- [Gestion des données et confidentialité](data-handling-and-privacy.md) — Directives de base pour la gestion et le partage sécurisé des données
