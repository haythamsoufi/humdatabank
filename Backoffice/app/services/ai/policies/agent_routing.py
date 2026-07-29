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
   - LLM evidence-plan finish deferral (block finish until required source families
     from ``decide_evidence_plan()`` are satisfied by tool calls — not keyword routing)

3. Code MUST NOT:
   - Force ``tool_choice="required"`` based on query phrasing
   - Block ``finish`` or inject nudges to force ``search_documents`` on keyword match
   - Run fast path without an explicit LLM ``execution_mode=\"fast_path\"`` decision
   - Rewrite user queries via regex follow-up matchers
   (Exception: defer ``finish`` when an LLM evidence plan lists required families
   not yet covered by prior tool calls in the same run.)

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
    from app.services.ai.planning.evidence_plan import AIEvidencePlanner, EvidencePlan
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
        evidence_plan: Optional["EvidencePlan"] = None,
    ) -> str:
        """
        Optional per-turn system prompt additions.

        Uses page context, explicit table requests, source toggles, and LLM
        evidence plans — never query-keyword tool routing.
        """
        parts: List[str] = []

        plan_block = AgentRoutingPolicy.evidence_plan_supplement(evidence_plan)
        if plan_block:
            parts.append(plan_block)

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
    def evidence_plan_enabled() -> bool:
        return bool(current_app.config.get("AI_AGENT_EVIDENCE_PLAN_ENABLED", True))

    @staticmethod
    def decide_evidence_plan(
        *,
        evidence_planner: "AIEvidencePlanner",
        query: str,
        tool_names: Set[str],
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional["EvidencePlan"]:
        """
        Ask the LLM (with conversation context) which evidence source families
        are required before answering. Returns None when disabled or inconclusive.
        """
        from app.services.ai.planning.evidence_plan import DOCUMENT_TOOLS, INDICATOR_BANK_TOOLS

        if not AgentRoutingPolicy.evidence_plan_enabled():
            logger.info("[EvidencePlan] pre-flight skipped: disabled by config")
            return None
        if not tool_names or not str(query or "").strip():
            logger.info("[EvidencePlan] pre-flight skipped: no tool_names or empty query")
            return None
        try:
            from app.services.ai.tools._utils import resolve_form_builder_context

            if resolve_form_builder_context():
                logger.info("[EvidencePlan] pre-flight skipped: form-builder context")
                return None
        except Exception:
            pass

        docs_in_tools = bool(tool_names & DOCUMENT_TOOLS)
        ib_in_tools = bool(tool_names & INDICATOR_BANK_TOOLS)
        documents_allowed = docs_sources_enabled() and not user_forbids_documents(query)
        databank_allowed = not docs_only_sources_enabled()
        logger.info(
            "[EvidencePlan] pre-flight starting: "
            "docs_in_tools=%s ib_in_tools=%s documents_allowed=%s databank_allowed=%s "
            "tool_count=%s",
            docs_in_tools,
            ib_in_tools,
            documents_allowed,
            databank_allowed,
            len(tool_names),
        )

        result = evidence_planner.plan(
            query=query,
            tool_names=tool_names,
            conversation_history=conversation_history,
            documents_allowed=documents_allowed,
            databank_allowed=databank_allowed,
        )
        if result is None:
            logger.info("[EvidencePlan] pre-flight returned None (single-family or low confidence)")
        else:
            logger.info(
                "[EvidencePlan] pre-flight result: families=%s confidence=%.2f rationale=%r",
                result.source_families,
                result.confidence,
                result.rationale,
            )
        return result

    @staticmethod
    def evidence_plan_supplement(evidence_plan: Optional["EvidencePlan"]) -> str:
        if evidence_plan is None or not evidence_plan.source_families:
            return ""
        if evidence_plan.source_families == ["help_only"]:
            return ""

        from app.services.ai.planning.evidence_plan import FAMILY_TOOL_HINTS

        families = evidence_plan.source_families
        lines = [
            "EVIDENCE PLAN FOR THIS TURN (mandatory — pre-flight LLM analysis):",
            f"Required source families: {', '.join(families)}.",
        ]
        if evidence_plan.rationale:
            lines.append(f"Rationale: {evidence_plan.rationale}")
        lines.append(
            "You MUST consult EACH required family with tools before finishing. "
            "Satisfying one family does not replace another — formal definitions "
            "(indicator_bank) and plan/report text (documents) answer different questions."
        )
        for fam in families:
            hint = FAMILY_TOOL_HINTS.get(fam)
            if hint:
                lines.append(f"- {fam}: {hint}")
        return "\n".join(lines)

    @staticmethod
    def pending_evidence_families(
        evidence_plan: Optional["EvidencePlan"],
        tools_used: List[str],
    ) -> List[str]:
        from app.services.ai.planning.evidence_plan import pending_evidence_families

        return pending_evidence_families(evidence_plan, tools_used)

    @staticmethod
    def build_evidence_defer_message(
        *,
        evidence_plan: "EvidencePlan",
        pending: List[str],
    ) -> str:
        from app.services.ai.planning.evidence_plan import FAMILY_TOOL_HINTS

        parts = [
            "Before finishing: your evidence plan requires "
            f"{', '.join(evidence_plan.source_families)}.",
            f"Still missing tool evidence from: {', '.join(pending)}.",
        ]
        for fam in pending:
            hint = FAMILY_TOOL_HINTS.get(fam)
            if hint:
                parts.append(f"For {fam}: use {hint}.")
        parts.append(
            "Gather the missing evidence, then finish with one answer that synthesizes all sources."
        )
        return " ".join(parts)

    @staticmethod
    def resolve_source_flags(query: str) -> tuple[bool, bool]:
        documents_allowed = docs_sources_enabled() and not user_forbids_documents(query)
        databank_allowed = not docs_only_sources_enabled()
        return documents_allowed, databank_allowed

    @staticmethod
    def should_defer_finish_for_evidence(
        *,
        evidence_planner: Optional["AIEvidencePlanner"] = None,
        evidence_plan: Optional["EvidencePlan"] = None,
        query: str = "",
        tools_used: List[str],
        tool_names: Optional[Set[str]] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        deferrals_used: int,
        documents_allowed: bool = True,
        databank_allowed: bool = True,
        finish_assessments: Optional[List[Dict[str, Any]]] = None,
    ) -> tuple[bool, List[str], str, Optional["EvidencePlan"]]:
        """
        Structural guard: defer finish when required evidence families are unsatisfied.

        Uses pre-flight evidence plan first; if inconclusive, runs a finish-time LLM
        sufficiency check when only a subset of available families were consulted.

        Returns (should_defer, pending_families, defer_message, effective_plan).
        """
        from app.services.ai.planning.evidence_plan import (
            DOCUMENT_TOOLS,
            should_run_finish_evidence_assessment,
        )

        max_def = int(current_app.config.get("AI_AGENT_EVIDENCE_PLAN_MAX_DEFERRALS", 2))
        if deferrals_used >= max(0, max_def):
            logger.info(
                "[EvidencePlan] finish-guard skipped: deferrals_used=%s >= max=%s",
                deferrals_used,
                max_def,
            )
            return False, [], "", evidence_plan

        effective_plan = evidence_plan
        pending = AgentRoutingPolicy.pending_evidence_families(effective_plan, tools_used)
        logger.info(
            "[EvidencePlan] finish-guard entry: preflight_plan=%s tools_used=%s pending=%s "
            "docs_in_tools=%s documents_allowed=%s databank_allowed=%s",
            effective_plan.source_families if effective_plan else None,
            list(tools_used),
            list(pending),
            bool(tool_names and tool_names & DOCUMENT_TOOLS),
            documents_allowed,
            databank_allowed,
        )

        if not pending:
            run_assess = (
                evidence_planner is not None
                and tool_names
                and str(query or "").strip()
                and should_run_finish_evidence_assessment(
                    tool_names=tool_names,
                    tools_used=tools_used,
                    documents_allowed=documents_allowed,
                    databank_allowed=databank_allowed,
                )
            )
            logger.info(
                "[EvidencePlan] finish-guard: no pending from preflight, run_finish_assess=%s",
                run_assess,
            )
            if run_assess:
                assessed = evidence_planner.assess_finish_evidence(
                    query=query,
                    tools_used=tools_used,
                    tool_names=tool_names,
                    conversation_history=conversation_history,
                    documents_allowed=documents_allowed,
                    databank_allowed=databank_allowed,
                    evidence_plan=effective_plan,
                )
                if finish_assessments is not None:
                    finish_assessments.append(
                        {
                            "assessed": assessed.to_dict() if assessed is not None else None,
                            "tools_used": list(tools_used),
                        }
                    )
                if assessed is not None:
                    effective_plan = assessed
                    pending = AgentRoutingPolicy.pending_evidence_families(
                        effective_plan, tools_used
                    )
                    logger.info(
                        "[EvidencePlan] finish-assess resolved plan=%s new_pending=%s",
                        effective_plan.source_families,
                        list(pending),
                    )
                else:
                    logger.info("[EvidencePlan] finish-assess returned None — no deferral")

        if not pending or effective_plan is None:
            logger.info("[EvidencePlan] finish-guard: no deferral (pending=%s)", list(pending))
            return False, [], "", effective_plan

        msg = AgentRoutingPolicy.build_evidence_defer_message(
            evidence_plan=effective_plan,
            pending=pending,
        )
        logger.info(
            "[EvidencePlan] DEFERRING finish: deferral=%s pending=%s",
            deferrals_used + 1,
            list(pending),
        )
        return True, pending, msg, effective_plan

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
