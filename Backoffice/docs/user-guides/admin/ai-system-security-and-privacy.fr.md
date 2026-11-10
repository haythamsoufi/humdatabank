# Système d’IA : sécurité et confidentialité

Ce document explique comment fonctionne l’assistant IA Backoffice, quelles données peuvent être traitées par des fournisseurs externes, et quels contrôles techniques sont en place pour réduire les fuites accidentelles d’informations sensibles.

## Portée

- **Dans le champ d’application** : chat IA (`/api/ai/v2/*`), base de connaissances IA / RAG, questions-réponses workflow-doc, et les contrôles de sécurité qui les entourent (DLP, nettoyage des PII, événements d’audit).
- **Hors champ de contrôle** : sécurité générale de la plateforme (authentisation, RBAC, sauvegardes), sauf lorsque cela affecte directement le système d’IA.

## Architecture de haut niveau

- **Frontend** : interface de chat (widget flottant + vue immersive) dans `app/static/js/chatbot/` (modules ES ; boîte de dialogue DLP dans `dlp-policy.js`).
- **Backend** : points de terminaison Flask API pour le chat IA dans `app/routes/ai.py` (HTTP + SSE) et `app/routes/ai_ws.py` (WebSocket).
- **Orchestration** : `app/services/ai/chat/engine.py` gère le flux de discussion (historique, récupération, appels fournisseurs).
- **Providers** : LLM/embeddings externes (par exemple, OpenAI/Gemini/Azure OpenAI selon l’environnement) plus des composants locaux optionnels.

## Quelles données peuvent être envoyées à des fournisseurs externes

Selon le type de requête et les fonctionnalités activées, le backend peut envoyer une combinaison de :

- **Texte de message utilisateur**
- **Historique des conversations** (messages récents, si nécessaire pour la continuité)
- **Contexte de page aseptifié** (État/contexte de l’interface utilisateur pour aider l’assistant ; certains champs à haut risque sont supprimés)
- **Fragments de documents/flux de travail récupérés** (pour les réponses RAG)

Important : certaines fonctionnalités d’IA nécessitent des appels API externes (par exemple, complétion de chat, réécriture de requêtes, intégrations), donc **empêcher l’envoi de données sensibles** est un objectif principal de sécurité.

## Contrôles fondamentaux de la vie privée/sécurité

### 1) La prévention de la perte de données (DLP) protège les messages sortants

Avant qu’un message puisse être envoyé à un fournisseur d’IA externe, le backend exécute un scan DLP de meilleure volonté (basé sur des regex) pour détecter des motifs sensibles courants, tels que :

- E-mails, numéros de téléphone
- JWT / jetons porteurs (Bearer) / identifiants Basic auth
- clés privées (tout bloc de clé privée PEM ou PGP, y compris un bloc collé sans sa ligne END)
- mots de passe / phrases secrètes, secrets / clés API — sous forme d’affectations `clé: valeur` ou `CLÉ=valeur` (fichiers env, JSON, YAML, chaînes de connexion comme `AccountKey=`), mots de passe intégrés dans les URL de connexion aux bases de données (par exemple une URL postgres avec des identifiants utilisateur) et formats de clés de fournisseurs connus (par exemple OpenAI `sk-…`, AWS `AKIA…`, GitHub `ghp_…`)
- IBAN (somme de contrôle vérifiée) et numéros de carte de paiement (vérification Luhn) pour réduire les faux positifs

La détection des numéros de téléphone ignore les formes de nombres courantes dans les questions sur les données : listes d’années, chiffres élevés ou groupés par milliers, dates, adresses IP et colonnes de tableaux.

**Expérience utilisateur**

- Un message n’est jamais envoyé ni enregistré avec une valeur détectée : lorsqu’il passe, chaque valeur est remplacée par un substitut tel que `[REDACTED_EMAIL]`.
- En mode `confirm` (par défaut), les e-mails et numéros de téléphone sont masqués automatiquement (configurable). Les identifiants, clés et identifiants financiers ouvrent une boîte de dialogue : **Masquer et envoyer** envoie le message masqué, **Annuler** rend le message à l’utilisateur pour modification et ne conserve rien.
- En mode `block`, le message est rejeté quel que soit son contenu ; la boîte de dialogue propose seulement de le modifier.
- Les clients Website et mobile reçoivent une erreur indiquant ce qui a été détecté (par exemple « Sensitive information detected (password). Remove it and send your message again. »).
- Les messages du panneau IA du générateur de formulaires conservent leurs adresses e-mail et numéros de téléphone (les questionnaires importés en contiennent légitimement), mais sont analysés pour tous les autres types.

**Implémentation**

- Logique DLP : `app/services/ai/chat/dlp.py` (`screen_ai_message`, `evaluate_ai_message`, `mask_sensitive_text`, `mask_conversation_history`)
- DLP est appliqué de manière cohérente entre les transports :
  - Chat JSON HTTP
  - Streaming SSE
  - Streaming WebSocket
- L’historique de conversation fourni par le client (modification ou relance d’un message précédent, chat anonyme) est masqué côté serveur avant d’être enregistré ou envoyé à un fournisseur.

**Configuration**

DLP est configuré directement dans le code (et non dans les variables d’environnement) :

- `Backoffice/config/config.py`
  - `AI_DLP_ENABLED`
  - `AI_DLP_MODE` : `warn` (tout masquer et envoyer), `confirm` (par défaut ; voir ci-dessus), `block`
  - `AI_DLP_AUTO_MASK_KINDS` : types que le mode `confirm` masque sans demander (par défaut : `email`, `phone`)
  - `AI_DLP_MAX_SCAN_CHARS`

### 2) Nettoyage / expurgation des informations personnelles avant appels externes

En plus du DLP (qui peut arrêter une requête), le système applique également un **nettoyage des PII** (censurage) pour réduire l’exposition lorsque le contenu doit être envoyé à l’extérieur (par exemple, pour aider le modèle à répondre). Le nettoyage utilise les mêmes motifs que le DLP, plus les longs jetons opaques.

Le nettoyage s’applique à :

- texte des messages utilisateurs
- les messages de l’utilisateur dans l’historique de conversation (les réponses de l’assistant sont la sortie du modèle lui-même et sont envoyées telles quelles)
- contexte de page (récursivement)
- quelques entrées et journaux réécrivant les requêtes

Les requêtes du panneau IA du générateur de formulaires ne passent pas par ce nettoyage, afin que le texte des questionnaires importés soit reproduit fidèlement ; le DLP continue de les analyser pour les identifiants et les identifiants financiers.

Mise en œuvre :

- `app/services/ai/providers/formatting.py` : `scrub_pii_text`, `scrub_pii_context`
- `app/services/ai/chat/engine.py` : applique le nettoyage avant les appels du fournisseur

### 3) Minimisation du contexte de la page

La interface peut envoyer le contexte de la page pour aider à répondre aux questions liées à l’interface. Le backend aseptifie et efface ces données et supprime intentionnellement les champs à haut risque (par exemple, les URL ou de gros blobs bruts) afin de réduire les fuites accidentelles.

Mise en œuvre :

- `app/utils/ai_utils.py` : aides partagées telles que la salubrisation du contexte
- `app/services/ai/providers/formatting.py` : nettoyage récursif du contexte

### 4) Audit de la journalisation des événements DLP (sans stocker le contenu du message)

Lorsque le DLP détecte des schémas sensibles, le backend écrit un **événement d’audit de sécurité** afin que les administrateurs puissent surveiller la fréquence de déclenchement de la garde et réagir à des comportements risqués.

Propriétés de sécurité :

- L’événement d’audit **ne stocke pas le message de l’utilisateur**.
- Il ne stocke que les **comptes et types** de résultats (par exemple, `{"kind":"jwt","count":1}`), ainsi que des métadonnées telles que le transport, le point de terminaison et les identifiants.
- `context_data.action` indique ce qui s’est passé : `auto_masked` (masqué et envoyé sans demander), `confirm_required` (la boîte de dialogue a été affichée), `sent_masked` (l’utilisateur a choisi Masquer et envoyer) ou `blocked`.
- La gravité est `high` pour les identifiants, clés et identifiants financiers lorsque l’utilisateur a été arrêté ou a choisi d’envoyer, et `medium` lorsqu’ils ont été masqués automatiquement (par exemple en mode `warn`). Les coordonnées sont `medium` et `low` selon le même principe.

Mise en œuvre :

- `app/services/ai/chat/dlp.py` : `log_dlp_audit_event`
- Modèle : `app/models/system.py` (`SecurityEvent`, `context_data` JSON)
- Interface d’administration :
  - Tableau de bord de sécurité : `/admin/security/dashboard`
  - Liste des événements de sécurité : `/admin/security/events`

Pour filtrer les événements DLP liés à l’IA, recherchez :

- `event_type = "ai_dlp_sensitive_detected"`

### 5) Auth et contrôle d’accès

- Les points d’accès IA sont protégés par les mêmes mécanismes d’authentification Backoffice (connexion basée sur la session et flux de jetons porteurs lorsque cela est applicable).
- Les pages réservées aux administrateurs (tableaux de bord de sécurité/événements) nécessitent des autorisations appropriées (voir `app/routes/admin/security_dashboard.py`).

## Directives opérationnelles (administrateurs)

### Politique recommandée

- Traiter l’assistant IA comme **non fiable pour les données sensibles**.
- Encourager les utilisateurs à :
  - éviter d’envoyer des identifiants, des jetons, des clés privées et des données personnelles
  - remplacer les identifiants réels par des substituts lors de la demande d’aide (par exemple, « <TOKEN>», « <EMAIL>»)

### Gestion d’un pic ou d’un incident DLP

1. Examiner les événements de sécurité récents sous `/admin/security/events` et filtrer par `ai_dlp_sensitive_detected`.
2. Vérifier les métadonnées dans `context_data` pour les motifs (transport, client, fréquence, comptes affectés).
3. Envisagez de resserrer temporairement le mode DLP à `block` dans `Backoffice/config/config.py` et de redéployer si nécessaire.
4. Si des secrets ont pu être exposés, faire pivoter les identifiants (clés API, jetons) et examiner les journaux d’accès.

## Limites et attentes

- DLP est basé sur le **meilleur effort** et basé sur des motifs ; Elle peut manquer des éléments sensibles et aussi produire des faux positifs.
- Le nettoyage des PII est aussi un meilleur effort ; Cela réduit le risque mais ne garantit pas son retrait total.
- La sortie IA peut être incorrecte ; les utilisateurs doivent vérifier les informations importantes (l’interface utilisateur met en garde à ce sujet).

## Emplacements des codes de touche (référence)

| Zone | Chemin |
|------|------|
| Points de terminaison de chat IA (HTTP + SSE) | `app/routes/ai.py` |
| Point de terminaison de chat IA (WebSocket) | `app/routes/ai_ws.py` |
| Orchestration par chat | `app/services/ai/chat/engine.py` |
| DLP garde + événements d’audit | `app/services/ai/chat/dlp.py` |
| Boîte de dialogue DLP (interface de chat) | `app/static/js/chatbot/dlp-policy.js` |
| Aides à la récure des PII | `app/services/ai/providers/formatting.py` |
| Modèle des événements de sécurité | `app/models/system.py` |
| Pages de sécurité admin | `app/routes/admin/security_dashboard.py` |

## Documentation associée

- [Politique d’utilisation IA](../common/ai-use-policy.md) — Politique destinée aux utilisateurs (utilisation acceptable, responsabilités)
- [Chatbot IA](../common/ai-chatbot.md) — Utilisation du chatbot, niveaux d’accès, RBAC et confidentialité des documents
- [Base de connaissances IA et embeddings](ai-document-library-and-embeddings.md)
- [Gestion des données et confidentialité](../../data-reporting/data-handling-and-privacy.md)

