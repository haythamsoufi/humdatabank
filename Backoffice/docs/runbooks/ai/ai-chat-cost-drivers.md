# AI Chat Cost Flaws

Summary of why the current setup is costly and where the main cost drivers are.

---

## 1. Document search observations are effectively unbounded

**Where:** `app/services/ai_tool_observation.py` — `compact_tool_observation_for_llm()` for `search_documents` / `search_documents_hybrid`.

**What:** For document search, the observation was previously unbounded (default 10M chars). **Fixed:** observation is now capped at `AI_TOOL_OBSERVATION_MAX_CHARS_DOCUMENT_SEARCH` (default **120_000**; clamped 50k–500k). When over the cap, each chunk’s `content` is truncated to `AI_TOOL_OBSERVATION_DOCUMENT_SEARCH_MAX_CONTENT_PER_CHUNK` (default 500 chars) so more chunks fit in the same budget.

**Impact:** One `search_documents` call with `limit=100` and 100 chunks of ~2k chars each ≈ 200k chars (~50k tokens). With **four** pagination rounds (offset 0, 100, 200, 300), the conversation holds four such observations, so **~200k–800k+ tokens** of tool results alone. Input cost scales with chunk count and number of rounds.

**Fix (implemented):** Cap at 120k chars default; when over, truncate each chunk’s content to 500 chars and add a note. Config: `AI_TOOL_OBSERVATION_MAX_CHARS_DOCUMENT_SEARCH`, `AI_TOOL_OBSERVATION_DOCUMENT_SEARCH_MAX_CONTENT_PER_CHUNK`.

---

## 2. Planner runs on every request but often returns None

**Where:** `app/services/ai_agent_executor.py` — `execute()` calls `query_planner.plan_simple()`; `app/services/ai_query_planner.py` uses an LLM to decide simple vs ReAct.

**What:** Every request pays for **one planner LLM call**. For document-heavy questions (e.g. “how many plans have well-informed PGI analysis?”), the planner frequently returns `None` (no simple plan), so we then run the full ReAct loop. So we pay: **1 planner + 4–5 ReAct rounds + 1 response revision**.

**Impact:** The planner call is “wasted” when it doesn’t yield a fast path. Document-only queries could be handled by a **simple plan** (one `search_documents` with `return_all_countries=True` and high `top_k`, then one synthesis call) instead of ReAct, but the planner either doesn’t classify them as simple or confidence is below the 0.45 threshold.

**Fix:** (a) Improve planner prompt/examples so “which countries / how many plans mention X” gets a `per_country_docs`-style simple plan with `search_documents`; or (b) add a cheap rule-based branch: if only document tools are enabled and query looks like a doc-inventory question, skip the planner and run a single `search_documents` + synthesis path.

---

## 3. ReAct sends full history; context grows every round

**Where:** `app/services/ai_agent_executor.py` — OpenAI native and custom ReAct build `messages` with every prior user/assistant/tool message.

**What:** Each round appends: assistant (Thought + Action) and tool (full observation). So after 4 tool calls we have **system + query + 4 × (assistant message + tool message)**. Tool messages for document search are huge (see #1), so **total input tokens** grow quickly and are dominated by repeated full chunk content.

**Impact:** High input token cost and risk of hitting context limits. Cost per request scales with number of rounds and size of each observation.

**Fix:** Reduce observation size (#1) and/or summarize previous tool results in later rounds instead of resending full content.

---

## 4. Multiple pagination calls for the same query

**Where:** Prompts tell the model to “fetch all batches” with `offset=0`, then `offset=limit`, etc. until `offset >= total_count`. Backend supports pagination cache (offset &gt; 0 reuses cached result), but the **agent still does multiple LLM rounds** (Thought → Action → Observation) per batch.

**What:** For “PGI minimum standards”–style queries we see: 4 × `search_documents` with the same query and offsets 0, 100, 200, 300. So **4 tool rounds** = 4 LLM calls with ever-growing context. Vector search runs once (first call); later calls are cache hits, but the **LLM still gets 4 separate observations** and does 4 reasoning steps.

**Impact:** Most of the cost is **LLM rounds**, not vector search. Fewer rounds (e.g. one large batch + “synthesize from this”) would cut cost and latency.

**Fix:** (a) Prefer a simple plan that does **one** `search_documents` with a high limit (e.g. 500) and instruct the model to synthesize from that single batch when possible; or (b) for ReAct, cap total `search_documents` batches (e.g. 1–2) and instruct the model to answer from the first batch(es) instead of “fetch all.”

---

## 5. Response revision adds an extra LLM call

**Where:** `app/services/ai_chat_engine.py` — `_revise_response_with_llm()`; default `AI_RESPONSE_REVISION_ENABLED=False` (changed to reduce cost).

**What:** After the agent (or fallback) returns, the final response text is sent to the LLM again for “clarity, consistency, and tone.” So every successful response pays for **one more** chat completion (input = system + user question + current response; output = revised response).

**Impact:** Non-trivial extra cost per request, especially for long answers (higher output tokens).

**Fix (implemented):** Default is now `False`. Set `AI_RESPONSE_REVISION_ENABLED=true` in env to re-enable.

---

## 6. Embedding reuse is good; pagination cache is good

**Where:** `app/services/ai_vector_store.py` — `hybrid_search()` generates the query embedding **once** and reuses it. `app/services/ai_tools_registry.py` — `search_documents()` with `offset > 0` can serve from `g.ai_search_documents_cache` (same request).

**What:** So we do **not** re-embed the query for each pagination call, and we do **not** re-run vector search for offset 100, 200, 300 when the cache is populated.

**Impact:** These are already optimized. The main cost is **LLM input** (huge observations) and **number of LLM rounds**, not embedding or vector search.

---

## Summary table

| Flaw | Cost type | Severity | Fix |
|------|-----------|----------|-----|
| Unbounded document search observation size | Input tokens (huge) | **High** | Cap/compact observation (chars or chunk count) |
| Planner often returns None for doc queries | 1 extra LLM call | Medium | Better simple plan for doc-only; or rule-based fast path |
| Full history in ReAct | Input tokens grow each round | **High** (with #1) | Reduce observation size; optional summarization |
| Multiple pagination rounds | 4–5 LLM rounds instead of 1–2 | **High** | One big batch + synthesize; or cap batches |
| Response revision | 1 extra LLM call per request | Medium | Disable by default or use smaller model |

Recommended first step: **cap/compact document search observations** (#1) and **prefer one large batch + synthesize** where possible (#4). That will cut input tokens and number of rounds without changing user-facing behavior drastically.
