# RAG Quality & Embedding Recommendations

This document summarizes how the Backoffice AI system retrieves and uses document chunks and databank data, and provides concrete recommendations to improve **quality** and **scalability** when searching across 200+ documents.

---

## Does it work when I need a value from “all documents” or 192 countries?

**It depends where the value comes from.**

| Source | Supports 192 countries/documents? | How |
|--------|-----------------------------------|-----|
| **Databank / indicators** | **Yes** | `get_indicator_values_for_all_countries` returns one row per country (capped at 250). Use for “volunteers for all countries”, “list indicator X by country”, etc. |
| **UPR KPIs (from documents)** | **Yes** | `get_upr_kpi_values_for_all_countries(metric)` returns one row per country that has UPR KPI data in document metadata (branches, volunteers, staff, local_units). No per-country limit. |
| **Document search (chunks)** | **Partial** | `search_documents(return_all_countries=True)` is capped at `AI_DOCUMENT_SEARCH_MAX_TOP_K_LIST` chunks (default **500**). With diversity (e.g. 10 chunks per doc), you get coverage from many documents, but not literally “read all 192 documents”. Raise the cap if you need more chunks. |

So for questions like “volunteers in all countries” or “list branches by country”, the agent uses the **bulk databank tools** first; those **do** work for 192 countries. Document search is then used only to **supplement** with evidence; it does not scan every one of 192 documents.

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
- **No document-level diversity**: retrieval can return many chunks from few documents and none from others.
- **No reranking**: `AI_RERANK_ENABLED` exists in config but is not implemented; results are used in retrieval order after combined score.

---

## 2. Quality: How Chunks and Data Are Chosen

### What works well
- **Hybrid search**: Vector + keyword + system-document boost improves recall for exact terms (e.g. "10,000 volunteers") and prioritizes country-uploaded docs.
- **Query planning**: `_plan_query_with_llm` rewrites the user question into a retrieval query and sets focus country when appropriate.
- **Score filtering**: `min_score` (e.g. 0.35) drops low-relevance chunks before building the LLM context.
- **Deduplication**: `_dedupe_retrieval_results` removes duplicate chunk hits from hybrid merge.
- **Contextual snippets**: `_build_contextual_snippet` centers the snippet on query terms instead of a naive prefix.

### Gaps (especially for 200+ documents)
1. **No reranking**  
   Initial retrieval is by embedding + keyword score only. A cross-encoder or LLM reranker can significantly improve precision (typical +10–40% in RAG benchmarks) by scoring query–chunk pairs directly.

2. **No diversity across documents**  
   With a high top_k, results can be dominated by one or two very similar documents. There is no MMR (Maximal Marginal Relevance) or “max chunks per document” cap, so the model may see redundant context and miss other relevant countries/documents.

3. **Fixed weights**  
   Vector/keyword weights (0.7/0.3) and system_doc boost are fixed; they are not tuned per query type (e.g. list vs. single-country fact).

4. **List-style cap**  
   For “all countries” or “list from every country”, top_k is capped at 100. If the corpus has 200+ documents and the user expects coverage, some relevant documents may never appear in the candidate set.

---

## 3. Embedding Method: Efficiency and Upgrades

### Current setup: efficient and adequate
- **OpenAI text-embedding-3-small**: Good quality/cost balance, 1536 dimensions, low latency. Suitable for production.
- **Batch embedding**: `generate_embeddings_batch` (batch_size=100) is used for indexing; single query embedding is reused for vector + system-doc search in one request.
- **Local fallback**: `all-MiniLM-L6-v2` (384 dims) avoids API cost but is lower quality and not multilingual; acceptable for dev or small corpora.

### When to consider upgrading
- **Multilingual / cross-lingual**: If many documents are in Arabic, French, Spanish, etc., consider:
  - **OpenAI**: Same models handle multiple languages reasonably well.
  - **Dedicated multilingual**: e.g. `text-embedding-3-large` with explicit multilingual use, or a dedicated multilingual model (e.g. `intfloat/multilingual-e5-large`) if you move to a local/self-hosted embedding service.
- **Higher precision**: For critical use cases, `text-embedding-3-large` (3072 dims) often improves retrieval quality at higher cost; requires a DB migration and re-embedding.
- **Dimension reduction**: OpenAI supports `dimensions` parameter (e.g. 512) for 3-small/3-large to reduce storage and speed up similarity search; quality may drop slightly.

### Recommendation
- Keep **text-embedding-3-small** as the default; it is efficient and sufficient for most cases.
- Enable **reranking** (see below) before investing in a larger embedding model; reranking usually gives a bigger accuracy gain per engineering effort.
- If you need better cross-lingual retrieval, test **text-embedding-3-large** on a subset and/or add a reranker; only then consider a full re-embed with a different model and migration.

---

## 4. Recommendations (Prioritized)

### High impact

1. **Add reranking (two-stage retrieval)**  
   - **Retrieve** more candidates (e.g. top_k × 2 or 3).  
   - **Rerank** with a cross-encoder or API (e.g. Cohere Rerank, or open-source like `cross-encoder/ms-marco-MiniLM-L-6-v2`).  
   - **Return** top_k after rerank.  
   - **Config**: Use existing `AI_RERANK_ENABLED`; add `AI_RERANK_PROVIDER` (e.g. `cohere` / `local`), `COHERE_API_KEY`, and optional model name.  
   - Typical gain: +10–40% on relevance; especially helpful when scanning 200+ documents with a single query.

2. **Enforce diversity across documents**  
   - After hybrid merge (or after rerank), apply a **max chunks per document** cap (e.g. 5–10 per document).  
   - Optionally implement **MMR** (Maximal Marginal Relevance): balance similarity to the query with dissimilarity to already-selected chunks, to spread results across documents and reduce redundancy.  
   - This improves coverage when many documents are relevant (e.g. “volunteers in all countries”) and prevents one or two docs from dominating the context.

3. **Tune list-style retrieval**  
   - For agent calls with `return_all_countries=True`, consider:
     - Slightly higher default top_k (e.g. 50–80) when the agent detects a list/table intent.
     - Optional **document-level first pass**: retrieve top N *documents* by aggregate chunk score, then take top chunks per document (bounded), so more countries appear in the final set.
   - Keep `AI_DOCUMENT_SEARCH_MAX_TOP_K_LIST` (default 500) as a safety cap; document diversity (point 2) matters more than raising this cap blindly.

### Medium impact

4. **Query expansion / multi-query**  
   - For important queries, run 2–3 query variants (e.g. from query planner) and merge results (with dedupe and optional rerank). Improves recall for ambiguous or multi-facet questions.

5. **Chunk size / overlap**  
   - Current 512/50 is reasonable. If answers often span two chunks, try increasing overlap (e.g. 75–100 tokens) or slightly larger chunk size (e.g. 768) and A/B test.

6. **Score calibration**  
   - Log and periodically review `combined_score` / `__filter_score` vs. human relevance; adjust `min_score` and/or hybrid weights (e.g. keyword_weight for fact-heavy queries).

### Lower priority

7. **Embedding model upgrade**  
   - Only after reranking and diversity are in place; consider `text-embedding-3-large` or a multilingual model if you have evidence that semantic recall is the main bottleneck.

8. **Structured filters**  
   - You already filter by country, file_type, etc. Adding more metadata (e.g. year, document_type) and exposing them in the agent tool can help narrow the search space for 200+ docs.

---

## 5. Implementation Notes (Code)

- **Rerank**: Implemented in `app/services/ai_rerank_service.py`. When `AI_RERANK_ENABLED=true`, `hybrid_search` calls `rerank_chunks()` after combining results. Supports `AI_RERANK_PROVIDER=cohere` (requires `COHERE_API_KEY`) or `local` (sentence-transformers cross-encoder). Cohere and local implementations are optional (graceful fallback if dependencies missing).
- **Diversity**: Implemented in `AIVectorStore._apply_diversity_cap()`. When `AI_DOCUMENT_DIVERSITY_MAX_CHUNKS_PER_DOC` > 0 (default 10), hybrid results are capped to that many chunks per document so more documents appear in the result set.
- **Config**: See `config.py` and `env.example`: `AI_RERANK_ENABLED`, `AI_RERANK_PROVIDER`, `AI_RERANK_TOP_K`, `AI_RERANK_LOCAL_MODEL`, `AI_DOCUMENT_DIVERSITY_MAX_CHUNKS_PER_DOC`, and `COHERE_API_KEY`.

---

## 6. Summary Table

| Area              | Current state                         | Recommendation                                      |
|-------------------|----------------------------------------|-----------------------------------------------------|
| Embedding model   | text-embedding-3-small (1536)          | Keep; upgrade to 3-large only if needed + rerank   |
| Chunk selection   | Hybrid score, top_k, min_score        | Add reranking + max chunks per document (diversity) |
| 200+ documents    | top_k up to 100, no doc diversity     | Diversity cap; optional doc-level first pass       |
| Reranking         | Config present, not implemented        | Implement with Cohere or local cross-encoder      |
| Query handling    | Query planner + single hybrid call   | Optional multi-query for list-style                |

Implementing **reranking** and **document diversity** will have the largest impact on “getting the right info” when searching across 200+ documents; the current embedding method is efficient and can be upgraded later if needed.
