# AI services review — handoff (2026-11-08)

**Status:** Open — continue in a new chat  
**Scope:** `Backoffice/app/services/ai/` security / reliability review  
**Prior chat:** review of access policy + tool registry, then executor deep-dive; fixes landed for findings 1–2, 4, 7 and four executor bugs  
**Audience:** next agent continuing the review (do **not** re-litigate closed items below unless regressions appear)

---

## 1. Executive summary

Access control around AI documents and tool execution is generally solid (`documents/access.py` + `policies/access_policy.py` + `execute_tool` allow-list). This session fixed a privilege-escalation footgun (role-string → internal principal), wired the unused `allows_tool` gate, raised silent ACL degradation to warnings, added an allow-list drift test, and patched four executor bugs (non-object tool args, ReAct nested-JSON parse, mid-turn tool-cap bypass, misleading LLM timing log).

**Next priority (highest risk remaining):** write-capable tools in `tools/registry.py` (form builder + indicator bank mgmt) and `chat/dlp.py`.

---

## 2. Working tree caution

The repo working tree is **dirty with unrelated AI changes** beyond this review. Treat only the files in §3 as this session’s deliverable. Diff carefully before committing; do not assume every modified file under `services/ai/` belongs to this review.

Known unrelated / pre-existing dirt (non-exhaustive at handoff time):  
`chat/engine.py`, `chat/request.py`, `data/form_retrieval.py`, `planning/query_intent_helpers.py`, `policies/prompt_policy.py`, `providers/formatting.py`, `quality/answer_verifier.py`, `quality/grounding_evaluator.py`, `runtime/step_ux.py`, `runtime/tool_observation.py`, and untracked `runtime/chat_debug_runner.py`, `runtime/turn_digest.py`.

---

## 3. Changes landed this session

| File | What |
|------|------|
| `documents/access.py` | `internal_document_access()` ContextVar; `principal_for_legacy_args` **never** trusts `user_role`; role/admin failures → `warning` |
| `translation/glossary_llm.py` | Uses `with internal_document_access():` instead of `user_role="system_manager"` |
| `tools/registry.py` | `execute_tool` calls `allows_tool` before rebuilding exposed set |
| `agent/executor.py` | Tool args must be a JSON object; empty args → `{}`; mid-turn `max_tools_per_query` enforcement + skip replies; ReAct `Action Input` via `JSONDecoder.raw_decode`; LLM timing uses call start not wall start |
| `tests/.../test_ai_access_policy.py` | String role no longer internal; context manager grants internal; allow-list ⊆ registry methods (`search_documents_hybrid` allow-listed but not LLM-exposed — whitelisted as internal-only) |
| `tests/.../test_ai_services.py` | Nested ReAct JSON + non-object Action Input tests |

### Tests run

```text
pytest tests/unit/test_services/test_ai_access_policy.py -q          # 25 passed
pytest tests/unit/test_services/test_ai_services.py -q -k "Executor or ToolsRegistry or ToolRouting"  # 23 passed
```

Full suite **not** run.

### Explicitly deferred

- **Finding 3 (per-call tool-def rebuild in `execute_tool`):** left alone — cache risks privilege leak / staleness across form-builder + source toggles. Only revisit with a measured hot path.
- Executor structural refactors (dedupe skip blocks, shared native/ReAct loops, hung-tool timeout, per-call vs cumulative token logs).

---

## 4. Closed findings (do not re-open without new evidence)

1. ~~`principal_for_legacy_args` trusts `"system_manager"` string~~ → context manager  
2. ~~`allows_tool` dead~~ → called from `execute_tool`  
4. ~~Silent ACL degradation at debug~~ → warnings for role codes / doc-admin check  
7. ~~Allow-list drift~~ → test + documented `search_documents_hybrid` internal-only exception  
Executor: non-object args, ReAct nested JSON, mid-turn tool cap, LLM elapsed log  

Access matrix + SQL/Python ACL parity in `documents/access.py` was reviewed and looks sound. No f-string SQL injection found in this package.

---

## 5. Executor follow-ups (still open)

File: `agent/executor.py` (~3.2k lines).

| Item | Notes |
|------|--------|
| Triple overlap | `execute` / `_execute_openai_native` / `_execute_custom_react` duplicate guardrails |
| Skip-block copy-paste | ~5× “append skipped step + tool message” in native + again in ReAct → extract `_skip_tool_call(...)` |
| Dual search-docs limits | Cap + dedupe implemented twice; drift risk |
| Hung tool | Timeout only between iterations; in-flight call bounded only by HTTP timeout |
| Token log | “LLM call done” still logs **cumulative** tokens, not per-call |

---

## 6. Unreviewed map (suggested next chats)

Prefer **one area per chat**. Suggested order:

| Priority | Area | Paths | Look for |
|----------|------|-------|----------|
| **P0** | Write tools + RBAC | `tools/registry.py` (form builder, `_indicator_bank_mgmt.py`, `form_template_specs.py`), `_utils.py` | Who can mutate templates / indicator bank; `trusted_form_builder_context` vs client `page_context` |
| **P0** | DLP / retention / telemetry | `chat/dlp.py`, `retention.py`, `telemetry.py` | PII leakage, deletion correctness, logs |
| **P1** | Chat orchestration | `chat/engine.py`, `helpers.py`, `request.py`, `integration.py`, `fastpath.py` | Policy binding on every entry; anonymous proxy path |
| **P1** | Form retrieval / validation | `data/form_retrieval.py`, `validation/formdata_validation.py`, `ui_payload.py`, `assignment_review.py`, `parsers.py` | Data-layer access; N+1; draft vs submitted leakage |
| **P1** | Documents pipeline | `vector_store.py`, `processor.py`, `chunking.py`, `ingest.py`, `duplicates.py`, `metadata.py`, `country_detection*.py`, `embedding.py`, `multistep_retrieval.py` | Upload/parse safety; ACL on every search path; leftover `user_role` plumbing (now ignored) |
| **P2** | Planning vs routing rule | `planning/*`, especially `query_rewriter.py`, `payload_inference.py` | Must obey `.cursor/rules/ai-agent-routing.mdc` (no keyword/regex tool forcing) |
| **P2** | Policies | `prompt_policy.py`, `agent_routing.py`, `response_policy.py`, `tool_routing_policy.py`, `usage_budget.py` | Prompt injection; budget enforcement; keyword routing |
| **P2** | Quality | `grounding_evaluator.py`, `answer_verifier.py`, `reasoning_trace.py`, `trace_privacy.py`, `regression_test.py` | Fail-open vs fail-closed; redaction |
| **P3** | Runtime / jobs / providers | `runtime/*` (esp. **`chat_debug_runner.py` prod reachability**), `ai_job_runner.py`, `terminology_service.py`, `providers/` | Debug endpoint exposure; broad `except Exception` (7 in job runner); secrets in logs |
| **P3** | Cross-cutting | ~28 files with broad `except Exception` | Triage swallows that change ACL / tool / money behaviour |

Canonical routing rule: `.cursor/rules/ai-agent-routing.mdc`.  
Handbook pointer: `docs/DEVELOPER-HANDBOOK.md` (AI access policy section referenced from `access_policy.py` docstring).

---

## 7. How to resume (paste into next chat)

```text
Continue the AI services review from docs/handovers/2026-11-08-ai-services-review-handoff.md.

Start with P0: write-capable tools in Backoffice/app/services/ai/tools/
(registry form-builder + _indicator_bank_mgmt) and chat/dlp.py.

Do not re-do closed findings in §4. Working tree has unrelated dirty AI files — only
touch files needed for the new review/fixes. Prefer small security fixes over large
refactors unless I ask.
```

---

## 8. Quick reference — key symbols

| Symbol | Role |
|--------|------|
| `DocumentPrincipal` / `can_read_ai_document` / `ai_document_read_filter` | Single document ACL |
| `internal_document_access()` | Only way to get `INTERNAL_PRINCIPAL` without a user |
| `AIAccessPolicy` / `PUBLIC_TOOL_ALLOWLIST` / `allows_tool` / `filter_tool_definitions` | Tool + source clamping |
| `resolve_ai_access_policy()` | Request policy (fail → public) |
| `trusted_form_builder_context()` | Server-validated form-builder only |
| `AIToolsRegistry.execute_tool` | Final tool gate |
| `AIAgentExecutor._execute_openai_native` / `_execute_custom_react` | Agent loops |
