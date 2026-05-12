# RAG Quality & Embedding Recommendations

This document summarizes how the Backoffice AI system retrieves and uses document chunks and databank data, and provides concrete recommendations to improve **quality** and **scalability** when searching across 200+ documents.

---

## Does it work when I need a value from "all documents" or 192 countries?

**It depends where the value comes from.**

| Source | Supports 192 countries/documents? | How |
|--------|-----------------------------------|-----|
| **Databank / indicators** | **Yes** | `get_indicator_values_for_all_countries` returns one row per country (capped at 250). Use for "volunteers for all countries", "list indicator X by country", etc. |
| **UPR KPIs (from documents)** | **Yes** | `get_upr_kpi_values_for_all_countries(metric)` returns one row per country that has UPR KPI data in document metadata (branches, volunteers, staff, local_units). No per-country limit. |
| **Document search (chunks)** | **Partial** | `search_documents(return_all_countries=True)` is capped at `AI_DOCUMENT_SEARCH_MAX_TOP_K_LIST` chunks (default **500**). With diversity (e.g. 10 chunks per doc), you get coverage from many documents, but not literally "read all 192 documents". Raise the cap if you need more chunks. |

So for questions like "volunteers in all countries" or "list branches by country", the agent uses the **bulk databank tools** first; those **do** work for 192 countries. Document search is then used only to **supplement** with evidence; it does not scan every one of 192 documents.

---

## 1. Current Architecture (Summary)

### Retrieval pipeline

- **Vector store**: pgvector with cosine similarity on `ai_embeddings.embedding`.
- **Search entry points**:
  - **Agent tool**: `search_documents` → `AIVectorStore.hybrid_search()` (default).
  - **Document Q&A / answer endpoint**: same `hybrid_search`, then `_score_retrieval_results` → `_apply_min_score` → `_dedupe_retrieval_results` → LLM with snippets.
- **Hybrid search** (`ai_vector_store.py`):
  - Vector: `_search_similar_with_embedding` (top_k × 2) + `_get_system_document_results_with_embedding` (top_k).
  - Keyword: `_keyword_search` (top_k × 2) via PostgreSQL FTS (`to_tsvector('simple', content)` with GIN index).
  - Merge: `_combine_search_results` (vector_weight=0.7, keyword_weight=0.3, system_doc boost, keyword_match_boost).
  - Final result: top_k chunks (default 5; up to 20 single-country; up to `AI_DOCUMENT_SEARCH_MAX_TOP_K_LIST` when `return_all_countries=True`, default 500).

### Chunking

- **Strategy**: Semantic (paragraph/sentence boundaries), configurable `AI_CHUNK_SIZE` (default 512 tokens), `AI_CHUNK_OVERLAP` (50).
- **Extras**: Table extraction → structured table chunks; UPR visual chunking for KPIs; page/section metadata preserved.

### Embeddings

- **Provider**: `AI_EMBEDDING_PROVIDER` = `openai` (default) or `local`.
- **Models**: OpenAI `text-embedding-3-small` (1536 dims) or `text-embedding-3-large` (3072); local `all-MiniLM-L6-v2` (384 dims).
- **Dimensions**: Must match pgvector column (`AI_EMBEDDING_DIMENSIONS`); changing requires migration and re-embedding.

### Scaling for 200+ documents

- List-style queries: `return_all_countries=True` + `top_k` up to `AI_DOCUMENT_SEARCH_MAX_TOP_K_LIST` (default 500).
- Answer endpoint: `retrieval_top_k = min(200, max(top_k, max_docs * 50))` when `max_docs` is set.
- **Optional document-level diversity**: `AI_DOCUMENT_DIVERSITY_MAX_CHUNKS_PER_DOC` (default **10**) caps chunks per document via `_apply_diversity_cap()` after hybrid merge.
- **Optional reranking**: when `AI_RERANK_ENABLED=true`, `hybrid_search` runs `rerank_chunks()` (`app/services/ai_rerank_service.py`; Cohere or local cross-encoder). Off by default until keys/models are configured.

---

## 2. Quality: How Chunks and Data Are Chosen

### What works well

- **Hybrid search**: Vector + keyword + system-document boost improves recall for exact terms (e.g. "10,000 volunteers") and prioritizes country-uploaded docs.
- **Query planning**: `_plan_query_with_llm` rewrites the user question into a retrieval query and sets focus country when appropriate.
- **Score filtering**: `min_score` (e.g. 0.35) drops low-relevance chunks before building the LLM context.
- **Deduplication**: `_dedupe_retrieval_results` removes duplicate chunk hits from hybrid merge.
- **Contextual snippets**: `_build_contextual_snippet` centers the snippet on query terms instead of a naive prefix.

### Remaining gaps (especially for large corpora)

1. **Reranking optional / off by default**

   When `AI_RERANK_ENABLED=false`, initial ordering is embedding + keyword score only. Turn reranking on where you have `COHERE_API_KEY` or a local cross-encoder available if precision is insufficient.

2. **No MMR**

   Diversity is a **per-document chunk cap**, not maximal marginal relevance; very similar chunks from different documents can still dominate context.

3. **Fixed hybrid weights**

   Vector/keyword weights (0.7/0.3) and system_doc boost are fixed; they are not tuned per query type (e.g. list vs. single-country fact).

4. **List-style limits**

   Very large `top_k` is bounded by `AI_DOCUMENT_SEARCH_MAX_TOP_K_LIST` (default 500). For "cover every document", consider doc-level first-pass retrieval (see recommendations below) rather than only raising the cap.

---

## 3. Embedding Method: Efficiency and Upgrades

### Current setup: efficient and adequate

- **OpenAI text-embedding-3-small**: Good quality/cost balance, 1536 dimensions, low latency. Suitable for production.
- **Batch embedding**: `generate_embeddings_batch` (batch_size=100) is used for indexing; single query embedding is reused for vector + system-doc search in one request.
- **Local fallback**: `all-MiniLM-L6-v2` (384 dims) avoids API cost but is lower quality and not multilingual; acceptable for dev or small corpora.

### When to consider upgrading

- **Multilingual / cross-lingual**: If many documents are in Arabic, French, Spanish, etc., consider OpenAI multilingual behaviour, dedicated multilingual embeddings, or self-hosted models if you migrate off OpenAI embeddings.
- **Higher precision**: `text-embedding-3-large` (3072 dims) often improves retrieval at higher cost; requires a DB migration and re-embedding.
- **Dimension reduction**: OpenAI supports `dimensions` (e.g. 512) for 3-small/3-large for storage/Speed tradeoffs.

### Recommendation

- Keep **text-embedding-3-small** as the default; it is efficient and sufficient for most cases.
- Enable **reranking** (see below) before investing in a larger embedding model.

---

## 4. Recommendations (Prioritized)

### High impact

1. **Enable and tune reranking in production (when feasible)**

   Set `AI_RERANK_ENABLED=true`, `AI_RERANK_PROVIDER`, and `COHERE_API_KEY` or `AI_RERANK_LOCAL_MODEL` as documented in `config.py` / `env.example`. Retrieve more candidates first (e.g. larger `top_k` or `AI_RERANK_TOP_K`) so rerank has headroom.

2. **Tune per-document diversity**

   Adjust `AI_DOCUMENT_DIVERSITY_MAX_CHUNKS_PER_DOC` (default 10). Optional future work: **MMR** if redundancy remains.

3. **Tune list-style retrieval**

   Optionally higher `top_k` when intent is clearly tabular; optional **document-level first pass**. Keep `AI_DOCUMENT_SEARCH_MAX_TOP_K_LIST` as a safety cap.

### Medium impact

4. **Query expansion / multi-query**
5. **Chunk size / overlap** A/B tests
6. **Score calibration** from logged relevance

### Lower priority

7. **Embedding model upgrade** after rerank/diversity tuning
8. **Structured filters** via metadata exposed to agent tools

---

## 5. Implementation Notes (Code)

- **Rerank**: `app/services/ai_rerank_service.py`; `AI_RERANK_ENABLED`, `cohere` or `local` provider.
- **Diversity**: `AIVectorStore._apply_diversity_cap()`; `AI_DOCUMENT_DIVERSITY_MAX_CHUNKS_PER_DOC`.

---

## 6. Summary Table

| Area | Current state | Recommendation |
|------|---------------|----------------|
| Embedding model | text-embedding-3-small (1536) default | Keep; upgrade only with evidence |
| Chunk selection | Hybrid score, optional rerank + per-doc diversity cap | Turn on reranking where keys/models exist; tune diversity |
| Large corpora | `AI_DOCUMENT_SEARCH_MAX_TOP_K_LIST` caps list-style retrieval | Diversity + optional doc-level first pass before raising caps |
| Reranking | Behind `AI_RERANK_ENABLED` | Enable/tune for higher precision workloads |
| Query handling | Query planner + hybrid search | Optional multi-query for ambiguous questions |
