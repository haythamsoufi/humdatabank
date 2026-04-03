# Indicator Resolution: From Keyword to Semantic + LLM

This document describes how we resolve a **user phrase** (e.g. "volunteers", "blood donations", "number of staff") to the correct **Indicator Bank** entry so that data tools return the right form_data.

## Why the old method was weak

- **Keyword/ILIKE**: "Volunteers" did not match "Number of people volunteering" (volunteer**ing**). We added manual variants (volunteer/volunteering), but that does not scale.
- **Hard-coded relevance** (`score_indicator_relevance`): Tuned for a few terms (branch, volunteer, staff); fails for synonyms, translations, and paraphrases.
- **No semantics**: "staff count" vs "number of staff" vs "personnel" are the same intent but string match fails.

## Recommended approach: hybrid (vector + optional LLM)

| Layer | Role | When |
|-------|------|------|
| **1. Vector search** | Embed the Indicator Bank (name + definition + unit). Embed the user’s indicator phrase. Return top‑k by cosine similarity. | Always when embeddings exist; fast, handles synonyms and paraphrases. |
| **2. LLM disambiguation** (optional) | Given user query + top‑k indicators (id, name, definition), LLM picks the best match or "none". | When `AI_INDICATOR_LLM_DISAMBIGUATE=true`; handles ambiguity and multi-indicator questions. |
| **3. Keyword fallback** | If vector DB is empty or resolution is disabled, use existing ILIKE + name variants. | Backward compatibility and no-embedding setups. |

Result: **semantic recall** (vector) + **precision** (LLM when enabled) + **safe fallback** (keyword).

## Alternatives considered

- **LLM-only (full bank in context)**: Good for small banks; token limit and cost grow with bank size. Not ideal for hundreds of indicators.
- **Keyword-only with better rules**: Better than raw ILIKE but still no true semantics; high maintenance.
- **Vector-only (no LLM)**: Simple and fast; for ambiguous queries ("volunteers" vs "people volunteering") returning top‑1 by score is usually enough; LLM adds clarity when needed.

## Setup

1. Run migration: `flask db upgrade` (creates `indicator_bank_embeddings` table).
2. Set config: `AI_INDICATOR_RESOLUTION_METHOD=vector` or `vector_then_llm`, and optionally `AI_INDICATOR_LLM_DISAMBIGUATE=true`, `AI_INDICATOR_TOP_K=10`.
3. Populate embeddings once: `flask sync-indicator-embeddings` (uses same embedding model as RAG; costs a few cents for hundreds of indicators).
4. Re-run sync when the Indicator Bank changes (new/edited indicators).

## Implementation summary

1. **Indicator Bank embeddings**
   - Table: `indicator_bank_embeddings` (indicator_bank_id, embedding vector, text_embedded, model, dimensions).
   - Text per indicator: `name` + `definition` + `unit` (and optional translation snippets) so "volunteers" / "people volunteering" / "staff" map to the right indicator.
   - Same embedding model/dimensions as RAG (`AI_EMBEDDING_*`) so one service and consistent behaviour.

2. **Resolution service** (`indicator_resolution_service.py`)
   - `resolve(query: str, top_k: int) -> List[Tuple[IndicatorBank, float]]`: embed query → vector search → return top‑k with scores.
   - `resolve_with_llm(user_query: str, top_k_indicators: List) -> Optional[IndicatorBank]`: call LLM to pick one or none.
   - Sync job / admin action to (re)build embeddings when the Indicator Bank changes.

3. **Config**
   - `AI_INDICATOR_RESOLUTION_METHOD`: `"vector"` | `"vector_then_llm"` | `"keyword"`.
   - `AI_INDICATOR_LLM_DISAMBIGUATE`: if true and method is vector_then_llm, run LLM on top‑k.
   - `AI_INDICATOR_TOP_K`: number of vector candidates (e.g. 5).

4. **Integration**
   - In `get_value_breakdown` and `get_indicator_values_for_all_countries`, when `indicator_identifier` is a string: call the resolver instead of (or before) keyword path; use returned indicator id(s) for form item and data lookup.

## Making it "the most powerful"

- **Vectorise the Indicator Bank** so the model can "look up" by meaning, not just by substring.
- **Let the LLM decide** when disambiguation is enabled: pass top‑k and the user query; LLM chooses the intended indicator or says none.
- **Keep keyword fallback** so the system works without embeddings and remains robust.

Together this gives: **semantic search** (vector) + **LLM choice** (when enabled) + **safe fallback** (keyword).
