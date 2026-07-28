"""
Agent routing policy — single source of truth for AI agent orchestration decisions.

CONTRACT (mandatory for all new AI routing code)
================================================
1. The LLM chooses which tools to call from system prompts and conversation
   history. Application code MUST NOT route tools based on query keywords,
   regex phrase lists, or heuristic intent classifiers that bypass the LLM.

2. Code MAY enforce STRUCTURAL guards only:
   - UI source toggles (databank vs documents disabled)
   - Form-builder panel context (template tools when in the builder)
   - Loop prevention (duplicate search, pagination caps, circuit breakers)
   - Explicit user source directives ("databank only", "no documents")
   - Output formatting (table payload, sanitization)

3. Code MUST NOT:
   - Force ``tool_choice="required"`` based on query phrasing
   - Block ``finish`` or inject nudges to force ``search_documents`` on keyword match
   - Run fast path without an explicit LLM ``execution_mode=\"fast_path\"`` decision
   - Rewrite user queries via regex follow-up matchers

4. Import routing decisions from THIS MODULE — do not add new query-regex tool
   routing in executor, query_planner, query_rewriter, or tool_routing_policy.

Fast path is opt-in: ``decide_fast_path_plan()`` calls the LLM with full
conversation context; default is full ReAct agent.

LLM-facing guidance lives in ``app.services.ai.policies.prompt_policy``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.ai.planning.query_planner import AIQueryPlanner, SimplePlan

from flask import current_app

from app.services.ai.policies.response_policy import user_expects_full_table
from app.services.ai.policies.tool_routing_policy import (
    docs_only_sources_enabled,
    docs_sources_enabled,
    user_forbids_documents,
)

ToolChoice = Union[str, Dict[str, Any]]

logger = logging.getLogger(__name__)


class AgentRoutingPolicy:
    """Structural agent routing — not query-keyword routing."""

    @staticmethod
    def first_turn_tool_choice(
        *,
        query: str,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> ToolChoice:
        """
        Return OpenAI ``tool_choice`` for iteration 1.

        Only form-builder panel context may force a specific tool. Otherwise
        ``"auto"`` so the LLM decides from prompts and history.
        """
        _ = query  # reserved for future structural (non-keyword) context
        _ = user_context
        try:
            from app.services.ai.tools._utils import resolve_form_builder_context

            fb_ctx = resolve_form_builder_context() or {}
        except Exception:
            fb_ctx = {}

        if fb_ctx:
            if not fb_ctx.get("template_id"):
                return {
                    "type": "function",
                    "function": {"name": "create_form_template"},
                }
            return "required"

        return "auto"

    @staticmethod
    def turn_system_prompt_supplement(
        *,
        query: str,
        conversation_history: Optional[List[Dict[str, Any]]],
        user_context: Optional[Dict[str, Any]],
    ) -> str:
        """
        Optional per-turn system prompt additions.

        Uses page context, explicit table requests, and source toggles only —
        never query-keyword tool routing.
        """
        parts: List[str] = []

        if user_expects_full_table(query, conversation_history):
            parts.append(
                "CRITICAL FOR THIS TURN: The user has requested a table (or confirmed they want it). "
                "Your reply MUST be a markdown table of countries you identified by reading the full "
                "'content' of every chunk. If you have not yet fetched all batches (offset < total_count), "
                "fetch the rest first, then answer. Do NOT ask for confirmation. Output the table now."
            )

        page_type = AgentRoutingPolicy._page_type(user_context)
        if page_type in ("user_dashboard", "admin_dashboard"):
            parts.append(
                "PAGE CONTEXT: The user is on the dashboard. Questions about the country list or "
                "why they see only certain countries refer to their assigned countries / dashboard "
                "country selector — not document filters. Answer from USER CONTEXT when possible; "
                "do not call document search tools unless the user explicitly asks about documents."
            )

        if docs_only_sources_enabled() and docs_sources_enabled():
            parts.append(
                "SOURCE CONTEXT: Document sources are enabled and structured databank tools are "
                "disabled for this request. Use document tools as appropriate."
            )
        elif user_forbids_documents(query):
            parts.append(
                "SOURCE CONTEXT: The user asked to use databank/structured data only — do not search documents."
            )

        return "\n\n".join(parts)

    @staticmethod
    def fast_path_enabled() -> bool:
        """Fast path is available only when enabled and the LLM explicitly opts in."""
        return bool(current_app.config.get("AI_AGENT_FAST_PATH_ENABLED", True))

    @staticmethod
    def decide_fast_path_plan(
        *,
        query_planner: "AIQueryPlanner",
        query: str,
        tool_names: Set[str],
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional["SimplePlan"]:
        """
        Ask the LLM (with full conversation context) whether to use fast path.

        Returns a validated plan only when the LLM sets execution_mode=fast_path
        with sufficient confidence. Otherwise None → full ReAct agent.
        """
        if not AgentRoutingPolicy.fast_path_enabled():
            logger.info("Fast path disabled by config; using full ReAct agent")
            return None
        if not tool_names or not str(query or "").strip():
            return None
        return query_planner.plan_simple(
            query=query,
            tool_names=tool_names,
            conversation_history=conversation_history,
        )

    @staticmethod
    def should_skip_payload_inference(*, form_builder_assistant: bool) -> bool:
        """Skip chart/table payload inference for structural contexts only."""
        return bool(form_builder_assistant)

    @staticmethod
    def _page_type(user_context: Optional[Dict[str, Any]]) -> str:
        if not user_context or not isinstance(user_context, dict):
            return ""
        page_ctx = user_context.get("page_context") or {}
        if not isinstance(page_ctx, dict):
            return ""
        page_data = page_ctx.get("pageData") or {}
        if isinstance(page_data, dict):
            return str(page_data.get("pageType") or "").strip().lower()
        return ""


def decide_fast_path_plan(**kwargs: Any) -> Optional["SimplePlan"]:
    return AgentRoutingPolicy.decide_fast_path_plan(**kwargs)


def first_turn_tool_choice(**kwargs: Any) -> ToolChoice:
    return AgentRoutingPolicy.first_turn_tool_choice(**kwargs)


def turn_system_prompt_supplement(**kwargs: Any) -> str:
    return AgentRoutingPolicy.turn_system_prompt_supplement(**kwargs)
