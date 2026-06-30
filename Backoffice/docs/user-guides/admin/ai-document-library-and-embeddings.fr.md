# Bibliothèque de documents IA et Embeddings

Ce document décrit le fonctionnement de la bibliothèque de documents IA : comment les documents sont traités, comment les embeddings (vecteurs) sont générés, et comment ils sont utilisés pour la recherche sémantique et la génération augmentée par récupération (RAG).

## Aperçu

La bibliothèque de documents IA permet aux administrateurs de télécharger des documents (PDF, Word, etc.) afin que le chatbot et les outils d’IA puissent répondre aux questions en utilisant ce contenu. Les documents sont :

1. **Extrait** — le texte, les pages, les sections et, éventuellement, les tableaux sont extraits du fichier.
2. **Chunked** — divisé en petits blocs de texte pour le contexte et les limites de jetons.
3. **Embarqué** — chaque morceau est transformé en vecteur (plongement) par un modèle d’immersion.
4. **Stocké** — les vecteurs sont stockés dans la base de données (pgvector) et reliés à des chunks.

Lorsqu’un utilisateur pose une question, la requête est intégrée avec le même modèle, et le système trouve les morceaux les plus similaires (recherche vectorielle ou hybride) et les utilise comme contexte pour la réponse.

## Pipeline de traitement documentaire

Le traitement s’exécute lorsque vous :

- **Télécharger** un document sur la page de la bibliothèque de documents IA (`/admin/ai/documents`).
- **Traiter les documents sélectionnés** importés depuis le système de gestion documentaire.
- **Retraiter** un document existant (réextraction, re-chunk, ré-intégration).

Étapes de pipeline (voir `app/routes/ai_documents.py`, `_process_document_sync`) :

| Étape | Que se passe-t-il ?
|------|----------------|
| **1. Extrait** | `AIDocumentProcessor` lit le fichier et extrait le texte, les limites des pages, les sections et (éventuellement) les tableaux. |
| **2. Chunk** | `AIChunkingService` divise le texte en morceaux (par défaut : fragmentation sémantique, ~512 jetons par chunk, chevauchement de 50 jetons). Optionnel : blocs de table et blocs visuels UPR. |
| **3. Générer des embeddings** | Seulement si le document est marqué *searchable*. `AIEmbeddingService` transforme le texte de chaque segment en vecteur (voir [Fournisseurs d’intégration](#embedding-providers) ci-dessous). |
| **4. Magasin** | `AIVectorStore` sauvegarde chaque vecteur dans la table `AIEmbedding` (pgvector), liée au `AIDocumentChunk` correspondant. |

Les enregistrements de blocs (`AIDocumentChunk`) sont toujours créés ; Les embeddings ne sont créés que lorsque le document est consultable.

## Fournisseurs d’intégration

Les embeddings sont générés par `app/services/ai_embedding_service.py`. Deux prestataires sont pris en charge.

### OpenAI (par défaut)

- **Provider :** `AI_EMBEDDING_PROVIDER=openai` (par défaut).
- **Model :** `AI_EMBEDDING_MODEL` — par défaut `text-embedding-3-small`.
- **Dimensions :** `AI_EMBEDDING_DIMENSIONS` — par défaut `1536` (doit correspondre à la colonne pgvector).
- **Où il s’exécute :** Sur **les serveurs d’OpenAI**. Votre application envoie du texte en blocs à l’API OpenAI et reçoit des vecteurs. Vous devez `OPENAI_API_KEY` configuré.
- **Coût :** Facturé par jeton par OpenAI (par exemple, text-embedding-3-small est un coût faible par 1M de jetons).

Ainsi, **`text-embedding-3-small` n’est pas exécuté localement** — il est utilisé via l’API OpenAI.

### Local (Transformateurs de Phrase)

- **Fournisseur :** `AI_EMBEDDING_PROVIDER=local`.
- **Modèle :** `all-MiniLM-L6-v2` (fixe dans le service) — 384 dimensions.
- **Où il tourne :** **Sur votre machine**. L’application charge le modèle avec la bibliothèque `sentence_transformers` ; aucune API externe n’est appelée.
- **Coût :** Pas de coût par jeton ; nécessite `pip install sentence-transformers` et suffisamment de RAM/CPU.

Si vous utilisez des embeddings locaux, vous devez :

- Set `AI_EMBEDDING_DIMENSIONS=384`.
- S’assurer que la colonne pgvector de la base de données compte 384 dimensions (une migration peut être nécessaire). Le schéma par défaut est 1536 pour OpenAI.

## Référence de configuration

| Variable | Par défaut | Description |
|----------|---------|-------------|
| `AI_EMBEDDING_PROVIDER` | `openai` | `openai` ou `local`. |
| `AI_EMBEDDING_MODEL` | `text-embedding-3-small` | Nom du modèle (OpenAI uniquement ; ignoré pour `local`). |
| `AI_EMBEDDING_DIMENSIONS` | `1536` | Taille du vecteur. Doit correspondre à la colonne de la base de données et au modèle (1536 pour text-embedding-3-small, 384 pour tout-MiniLM-L6-v2). |
| `OPENAI_API_KEY` | — | Obligatoire lorsque `AI_EMBEDDING_PROVIDER=openai`. |
| `AI_CHUNK_SIZE` | `512` | Ciblez la taille du chunk en jetons. |
| `AI_CHUNK_OVERLAP` | `50` | Chevauchement entre des chunks consécutifs (jetons). |
| `AI_MAX_DOCUMENT_SIZE_MB` | `50` | Taille maximale de fichier pour le traitement. |
| `AI_TOP_K_RESULTS` | `5` | Nombre de morceaux retournés pour la recherche. |

Voir `Backoffice/config/config.py` pour la section complète AI/RAG et toutes options supplémentaires.

## Comment les vecteurs sont utilisés

- **Recherche vectorielle :** La requête utilisateur est intégrée au même service d’intégration ; L’application effectue une recherche de similarité (par exemple Cosinus) dans PGVECTOR et retourne les chunks du top.
- **Recherche hybride :** Combine similarité vectorielle et recherche par mots-clés pour une meilleure mémoire.
- **RAG :** Les chunks récupérés sont transmis en contexte au LLM lors de la réponse aux questions (chatbot, Q&R de la bibliothèque de documents IA, documents de workflow).

La page de la bibliothèque de documents IA vous permet de choisir **Vector uniquement** ou **Hybride (mots-clés et embeddings)** pour la fonction « Demander ».

## Emplacements des codes de touche

| Composant | Chemin |
|-----------|------|
| Pipeline de traitement documentaire | `app/routes/ai_documents.py` — `_process_document_sync` |
| Fragmentation | `app/services/ai_chunking_service.py` |
| Génération d’intégration | `app/services/ai_embedding_service.py` |
| Stockage vectoriel et recherche | `app/services/ai_vector_store.py` |
| UI de bibliothèque de documents IA | `app/templates/admin/ai/documents.html` |

## Documentation associée

- [Chatbot IA](../common/ai-chatbot.md) — Utilisation du chatbot, niveaux d’accès, RBAC et confidentialité des documents
- [Documentation de workflow](../../workflows/AUTHORING_GUIDE.md) — les fichiers markdown de workflow sont également synchronisés avec le magasin vectoriel pour RAG.
- [Workflow schema](../../workflows/_schema.md) — mentionne la génération d’intégration pour les documents de workflow.
