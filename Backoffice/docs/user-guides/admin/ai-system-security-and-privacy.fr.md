# Système d’IA : sécurité et confidentialité

Ce document explique comment fonctionne l’assistant IA Backoffice, quelles données peuvent être traitées par des fournisseurs externes, et quels contrôles techniques sont en place pour réduire les fuites accidentelles d’informations sensibles.

## Portée

- **Dans le champ d’application** : chat IA (`/api/ai/v2/*`), bibliothèque de documents IA / RAG, questions-réponses workflow-doc, et les contrôles de sécurité qui les entourent (DLP, nettoyage des PII, événements d’audit).
- **Hors champ de contrôle** : sécurité générale de la plateforme (authentisation, RBAC, sauvegardes), sauf lorsque cela affecte directement le système d’IA.

## Architecture de haut niveau

- **Frontend** : interface de chat (widget flottant + vue immersive) dans `app/static/js/chatbot.js`.
- **Backend** : points de terminaison Flask API pour le chat IA dans `app/routes/ai.py` (HTTP + SSE) et `app/routes/ai_ws.py` (WebSocket).
- **Orchestration** : `app/services/ai_chat_engine.py` gère le flux de discussion (historique, récupération, appels fournisseurs).
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
- JWT / Jetons porteurs
- clés privées
- mots de passe / secrets / clés API
- IBAN et numéros de carte de paiement (avec la vérification Luhn pour réduire les faux positifs)

**Expérience utilisateur**

- Si des motifs sensibles sont détectés, l’assistant peut exiger une **confirmation utilisateur** (« Envoyer quand même ») ou **bloquer** le message selon la configuration.
- L’interface explique le risque et encourage la suppression du texte sensible.

**Implémentation**

- Logique DLP : `app/services/ai_dlp.py` (`analyze_text`, `evaluate_ai_message`)
- DLP est appliqué de manière cohérente entre les transports :
  - Chat JSON HTTP
  - Streaming SSE
  - Streaming WebSocket

**Configuration**

DLP est configuré directement dans le code (et non dans les variables d’environnement) :

- `Backoffice/config/config.py`
  - `AI_DLP_ENABLED`
  - `AI_DLP_MODE` (valeurs typiques : `warn`, `confirm`, `block`)
  - `AI_DLP_MAX_SCAN_CHARS`

### 2) Nettoyage / expurgation des informations personnelles avant appels externes

En plus du DLP (qui peut arrêter une requête), le système applique également un **nettoyage des PII** (censurage) pour réduire l’exposition lorsque le contenu doit être envoyé à l’extérieur (par exemple, pour aider le modèle à répondre).

Le frottement s’applique à :

- texte des messages utilisateurs
- Extraits d’historique de conversation
- contexte de page (récursivement)
- quelques entrées et journaux réécrivant les requêtes

Mise en œuvre :

- `app/services/ai/providers/formatting.py` : `scrub_pii_text`, `scrub_pii_context`
- `app/services/ai_chat_engine.py` : applique le nettoyage avant les appels du fournisseur

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

Mise en œuvre :

- `app/services/ai_dlp.py` : `log_dlp_audit_event`
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
| Orchestration par chat | `app/services/ai_chat_engine.py` |
| DLP garde + événements d’audit | `app/services/ai_dlp.py` |
| Aides à la récure des PII | `app/services/ai/providers/formatting.py` |
| Modèle des événements de sécurité | `app/models/system.py` |
| Pages de sécurité admin | `app/routes/admin/security_dashboard.py` |

## Documentation associée

- [Politique d’utilisation IA](../common/ai-use-policy.md) — Politique destinée aux utilisateurs (utilisation acceptable, responsabilités)
- [Chatbot IA](../common/ai-chatbot.md) — Utilisation du chatbot, niveaux d’accès, RBAC et confidentialité des documents
- [Bibliothèque de documents IA et embeddings](ai-document-library-and-embeddings.md)
- [Gestion des données et confidentialité](../../data-reporting/data-handling-and-privacy.md)

