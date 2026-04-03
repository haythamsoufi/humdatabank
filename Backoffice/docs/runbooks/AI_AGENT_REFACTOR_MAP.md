# AI Agent Refactor Map

This is a quick index of the AI-agent refactor so future changes stay modular and do not grow `app/services/ai_agent_executor.py` again.

## Current role of `ai_agent_executor.py`

`app/services/ai_agent_executor.py` is now primarily responsible for:

- orchestrating path selection (simple plan vs ReAct vs fallback),
- executing the tool loop with limits/timeouts/cost guards,
- coordinating traces and returning normalized result payloads,
- delegating policy/formatting/inference to focused helper modules.

## Extracted modules (single-purpose boundaries)

| Module | Responsibility | Main public functions | Current callers |
|---|---|---|---|
| `app/services/ai_prompt_policy.py` | Agent system prompt construction | `build_agent_system_prompt()` | `ai_agent_executor.py` |
| `app/services/ai_tool_routing_policy.py` | Tool/source routing heuristics and doc-search dedupe | `is_redundant_document_search()`, `is_value_question()`, `docs_sources_enabled()`, `docs_only_sources_enabled()`, `should_force_docs_tool_first_turn()`, `user_forbids_documents()` | `ai_agent_executor.py` |
| `app/services/ai_payload_inference.py` | Map/chart payload inference from tool outputs | `build_linechart_payload_from_timeseries()`, `infer_map_payload_from_steps()`, `infer_chart_payload_from_steps()` | `ai_agent_executor.py` |
| `app/services/ai_step_ux.py` | User-facing step labels/details for progress UI | `step_display_message()`, `format_tool_args_detail()`, `format_plan_for_step()`, `document_query_for_display()` | `ai_agent_executor.py` |
| `app/services/ai_tool_observation.py` | Compaction of large tool observations before sending back to LLM | `compact_tool_observation_for_llm()` | `ai_agent_executor.py` |
| `app/services/ai_response_policy.py` | Response-level heuristics and output sanitization | `user_expects_full_table()`, `wants_reasoning_evidence()`, `sanitize_agent_answer()` | `ai_agent_executor.py`, `ai_chat_integration.py` |
| `app/services/ai_query_intent_helpers.py` | Query intent helpers and reasoning-query builders | `is_assignment_form_question()`, `build_reasoning_doc_query_from_steps()`, `infer_metric_label_from_query()`, `build_per_country_values_text_response()`, `bulk_tool_call_signature()` | `ai_agent_executor.py` |
| `app/services/ai_runtime_utils.py` | Runtime helpers not tied to orchestration | `estimate_openai_cost()`, `synthesize_partial_answer()` | `ai_agent_executor.py` |
| `app/services/ai_fastpaths/unified_plans_focus_fastpath.py` | Dedicated deterministic fast path for unified-plans review | `run_unified_plans_focus_fastpath()` | `ai_agent_executor.py` |

## Change routing rule (important)

When adding behavior, use this rule of thumb:

- prompt/instruction text changes -> `ai_prompt_policy.py`
- tool/source selection changes -> `ai_tool_routing_policy.py`
- response text hygiene/table-intent heuristics -> `ai_response_policy.py`
- map/chart shaping -> `ai_payload_inference.py`
- progress-step wording -> `ai_step_ux.py`
- LLM observation size/shape -> `ai_tool_observation.py`
- fast path specialization -> `app/services/ai_fastpaths/`
- only orchestration/loop/lifecycle -> `ai_agent_executor.py`

## Guardrails for future PRs

- Avoid adding new large regex/prompt blocks directly in `ai_agent_executor.py`.
- Prefer adding helper functions to the owning module and importing them in executor.
- Keep behavior changes testable by module (policy/inference/fastpath) before integration.
