"""
LLM evidence planner — decides which source families the agent must consult.

No keyword routing: a small pre-flight LLM call assesses the user's purpose and
returns required evidence layers (indicator_bank, documents, databank_values).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Set

from flask import current_app

from app.utils.ai_utils import openai_model_supports_sampling_params

logger = logging.getLogger(__name__)

SOURCE_FAMILIES = frozenset({"indicator_bank", "documents", "databank_values", "help_only"})

INDICATOR_BANK_TOOLS: FrozenSet[str] = frozenset({
    "search_indicator_bank",
    "get_indicator_metadata",
    "get_indicator_usage_stats",
    "browse_indicators",
    "get_indicator_bank_stats",
    "get_indicator_change_history",
    "list_indicator_suggestions",
})

DOCUMENT_TOOLS: FrozenSet[str] = frozenset({
    "search_documents",
    "search_documents_hybrid",
    "list_documents",
    "analyze_unified_plans_focus_areas",
})

DATABANK_VALUE_TOOLS: FrozenSet[str] = frozenset({
    "get_indicator_value",
    "get_indicator_timeseries",
    "get_indicator_values_for_all_countries",
    "get_form_field_value",
    "get_form_field_values_for_all_countries",
    "get_assignment_indicator_values",
    "compare_countries",
})

FAMILY_TOOL_HINTS: Dict[str, str] = {
    "indicator_bank": (
        "Indicator Bank definitions and metadata "
        "(search_indicator_bank, get_indicator_metadata, browse_indicators, etc.)"
    ),
    "documents": (
        "Uploaded plans and reports "
        "(search_documents, list_documents, analyze_unified_plans_focus_areas)"
    ),
    "databank_values": (
        "Reported submission values "
        "(get_indicator_value, get_indicator_values_for_all_countries, get_form_field_value, etc.)"
    ),
}


@dataclass
class EvidencePlan:
    """Required evidence source families for one agent run."""

    source_families: List[str] = field(default_factory=list)
    rationale: str = ""
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_families": list(self.source_families),
            "rationale": self.rationale,
            "confidence": self.confidence,
        }


class AIEvidencePlanner:
    """LLM router for multi-source evidence requirements."""

    def __init__(self, *, client: Any, model: str):
        self.client = client
        self.model = model

    @staticmethod
    def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
        raw = str(text or "").strip()
        if not raw:
            return None
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else None
        except (ValueError, TypeError):
            pass
        start = raw.find("{")
        if start >= 0:
            depth = 0
            for i in range(start, len(raw)):
                ch = raw[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            obj = json.loads(raw[start : i + 1])
                            return obj if isinstance(obj, dict) else None
                        except (ValueError, TypeError):
                            break
        return None

    @staticmethod
    def _family_available(family: str, tool_names: Set[str]) -> bool:
        if family == "indicator_bank":
            return bool(tool_names & INDICATOR_BANK_TOOLS)
        if family == "documents":
            return bool(tool_names & DOCUMENT_TOOLS)
        if family == "databank_values":
            return bool(tool_names & DATABANK_VALUE_TOOLS)
        return family == "help_only"

    @classmethod
    def validate_plan(
        cls,
        raw: Optional[Dict[str, Any]],
        *,
        tool_names: Set[str],
        documents_allowed: bool,
        databank_allowed: bool,
    ) -> Optional[EvidencePlan]:
        if not isinstance(raw, dict):
            return None
        try:
            confidence = float(raw.get("confidence", 0.0))
        except (ValueError, TypeError):
            confidence = 0.0
        min_conf = float(current_app.config.get("AI_AGENT_EVIDENCE_PLAN_MIN_CONFIDENCE", 0.7))
        if confidence < min_conf:
            logger.info(
                "Evidence planner: confidence %.2f below threshold %.2f — skipping plan",
                confidence,
                min_conf,
            )
            return None

        families_in = raw.get("source_families")
        if not isinstance(families_in, list):
            return None

        seen: Set[str] = set()
        families: List[str] = []
        for item in families_in:
            fam = str(item or "").strip().lower()
            if fam not in SOURCE_FAMILIES or fam in seen:
                continue
            if fam == "documents" and not documents_allowed:
                continue
            if fam in {"indicator_bank", "databank_values"} and not databank_allowed:
                continue
            if not cls._family_available(fam, tool_names):
                continue
            seen.add(fam)
            families.append(fam)

        if not families:
            return None
        if families == ["help_only"]:
            return EvidencePlan(
                source_families=["help_only"],
                rationale=str(raw.get("rationale") or "").strip(),
                confidence=confidence,
            )

        rationale = str(raw.get("rationale") or "").strip()
        return EvidencePlan(source_families=families, rationale=rationale, confidence=confidence)

    def plan(
        self,
        *,
        query: str,
        tool_names: Set[str],
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        documents_allowed: bool = True,
        databank_allowed: bool = True,
    ) -> Optional[EvidencePlan]:
        q = str(query or "").strip()
        if not q or not tool_names:
            logger.info("[EvidencePlan] plan() skipped: empty query or no tools")
            return None

        ib_avail = self._family_available("indicator_bank", tool_names)
        doc_avail = self._family_available("documents", tool_names)
        db_avail = self._family_available("databank_values", tool_names)
        logger.info(
            "[EvidencePlan] plan() family_available: indicator_bank=%s documents=%s databank_values=%s "
            "| documents_allowed=%s databank_allowed=%s",
            ib_avail,
            doc_avail,
            db_avail,
            documents_allowed,
            databank_allowed,
        )

        allowed_labels: List[str] = []
        if databank_allowed and ib_avail:
            allowed_labels.append("indicator_bank")
        if documents_allowed and doc_avail:
            allowed_labels.append("documents")
        if databank_allowed and db_avail:
            allowed_labels.append("databank_values")
        allowed_labels.append("help_only")
        if len(allowed_labels) <= 1:
            logger.info(
                "[EvidencePlan] plan() skipped: only 1 allowed label=%s (docs_in_tools=%s, docs_allowed=%s)",
                allowed_labels,
                doc_avail,
                documents_allowed,
            )
            return None

        sys = (
            "You are the evidence router for a humanitarian data assistant.\n"
            "Decide which SOURCE FAMILIES the agent must consult before it can answer.\n"
            "Return ONLY valid JSON:\n"
            "{"
            '"source_families": ["indicator_bank"|"documents"|"databank_values"|"help_only"], '
            '"rationale": "one sentence", '
            '"confidence": 0.0-1.0'
            "}\n"
            "Source families:\n"
            "- indicator_bank: formal Indicator Bank definitions, metadata, similarity search — "
            "what an indicator means and whether an activity fits its definition.\n"
            "- documents: text from uploaded National Society plans, reports, Unified Plans — "
            "how activities are described or applied in practice.\n"
            "- databank_values: numeric/country values from submitted form data and indicators.\n"
            "- help_only: greetings, platform navigation, no data retrieval needed.\n"
            "Rules:\n"
            "- Assess PURPOSE, not keywords. Some questions need multiple families because each "
            "answers a different question (rule vs practice vs reported numbers).\n"
            "- When the user needs BOTH formal definitions AND plan/report text, include "
            "indicator_bank AND documents — even if definitions alone seem sufficient.\n"
            "- Eligibility or reporting guidance ('can this be included', 'does this count', "
            "'check documentation and definitions') usually needs indicator_bank + documents.\n"
            "- Pure similarity lookup ('closest indicator to…') → indicator_bank only.\n"
            "- Pure country metric ('volunteers in Syria') → databank_values (add documents only "
            "if plan/report narrative is needed).\n"
            "- Choose the minimum set that fully answers the question — but do not omit a family "
            "when the user clearly needs that type of evidence.\n"
            f"- source_families values MUST be chosen only from: {allowed_labels}.\n"
            "- Output JSON only."
        )

        user_payload: Dict[str, Any] = {"query": q, "allowed_source_families": allowed_labels}
        if conversation_history:
            recent: List[Dict[str, str]] = []
            for entry in (conversation_history or [])[-4:]:
                if not isinstance(entry, dict):
                    continue
                is_user = entry.get("isUser")
                if is_user is None:
                    role = str(entry.get("role") or "").strip().lower()
                    is_user = role == "user"
                role = "user" if is_user else "assistant"
                content = (entry.get("message") or entry.get("content") or "").strip()
                if content:
                    recent.append({"role": role, "content": content[:300]})
            if recent:
                user_payload["recent_conversation"] = recent

        try:
            http_to = float(current_app.config.get("AI_HTTP_TIMEOUT_SECONDS", 120) or 120)
        except (TypeError, ValueError):
            http_to = 120.0
        try:
            planner_to = float(current_app.config.get("AI_AGENT_EVIDENCE_PLAN_TIMEOUT_SECONDS", 30) or 30)
        except (TypeError, ValueError):
            planner_to = 30.0
        timeout = max(5.0, min(planner_to, http_to))

        try:
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": sys},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                "max_completion_tokens": 250,
                "timeout": timeout,
            }
            if openai_model_supports_sampling_params(str(self.model)):
                kwargs["temperature"] = 0.0
            resp = self.client.chat.completions.create(**kwargs)
            text = str((resp.choices[0].message.content or "")).strip()
            obj = self._extract_json_object(text)
            validated = self.validate_plan(
                obj,
                tool_names=tool_names,
                documents_allowed=documents_allowed,
                databank_allowed=databank_allowed,
            )
            if validated is not None:
                logger.info(
                    "Evidence planner: families=%s confidence=%.2f",
                    validated.source_families,
                    validated.confidence,
                )
            elif obj is not None:
                logger.info(
                    "Evidence planner: rejected raw plan families=%s confidence=%s",
                    obj.get("source_families"),
                    obj.get("confidence"),
                )
            return validated
        except Exception as e:
            logger.warning("Evidence planner failed: %s", e)
            return None

    def assess_finish_evidence(
        self,
        *,
        query: str,
        tools_used: List[str],
        tool_names: Set[str],
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        documents_allowed: bool = True,
        databank_allowed: bool = True,
        evidence_plan: Optional[EvidencePlan] = None,
    ) -> Optional[EvidencePlan]:
        """
        Finish-time LLM check: given query + tools already run, which families
        still require tool calls? Returns a plan listing still-required families,
        or None when evidence is sufficient.
        """
        if not bool(current_app.config.get("AI_AGENT_EVIDENCE_FINISH_ASSESS_ENABLED", True)):
            logger.info("[EvidencePlan] assess_finish_evidence skipped: disabled by config")
            return None

        available = available_evidence_families(
            tool_names,
            documents_allowed=documents_allowed,
            databank_allowed=databank_allowed,
        )
        satisfied = families_satisfied_by_tools(tools_used)
        if not should_run_finish_evidence_assessment(
            tool_names=tool_names,
            tools_used=tools_used,
            documents_allowed=documents_allowed,
            databank_allowed=databank_allowed,
        ):
            return None

        still_available = sorted(available - satisfied)
        if not still_available:
            return None

        allowed_labels = list(still_available)
        sys = (
            "You are the evidence sufficiency checker for a humanitarian data assistant.\n"
            "The agent is about to finish. Given the user query and tools already executed, "
            "decide whether ADDITIONAL source families still need tool calls before answering.\n"
            "Return ONLY valid JSON:\n"
            "{"
            '"still_required": ["indicator_bank"|"documents"|"databank_values"], '
            '"rationale": "one sentence", '
            '"confidence": 0.0-1.0'
            "}\n"
            "Rules:\n"
            "- Assess PURPOSE, not keywords. Empty still_required means current evidence is enough.\n"
            "- Formal definitions (indicator_bank) and plan/report text (documents) answer different "
            "questions — if the user needs both types of evidence, still_required must include "
            "every missing family.\n"
            "- When the user asks to check documentation AND definitions, or eligibility/reporting "
            "guidance where practice matters, documents often remain required even if indicator "
            "definitions already look sufficient.\n"
            "- Pure metric lookup ('volunteers in Syria') after databank_values → still_required [].\n"
            "- Pure indicator similarity after indicator_bank → still_required [] unless documents "
            "were explicitly part of the question purpose.\n"
            f"- still_required values MUST be chosen only from: {allowed_labels}.\n"
            "- Output JSON only."
        )

        user_payload: Dict[str, Any] = {
            "query": str(query or "").strip(),
            "tools_executed": list(tools_used),
            "families_satisfied": sorted(satisfied),
            "families_still_available": still_available,
        }
        if evidence_plan is not None:
            user_payload["preflight_evidence_plan"] = evidence_plan.to_dict()
        if conversation_history:
            recent: List[Dict[str, str]] = []
            for entry in (conversation_history or [])[-4:]:
                if not isinstance(entry, dict):
                    continue
                is_user = entry.get("isUser")
                if is_user is None:
                    role = str(entry.get("role") or "").strip().lower()
                    is_user = role == "user"
                role = "user" if is_user else "assistant"
                content = (entry.get("message") or entry.get("content") or "").strip()
                if content:
                    recent.append({"role": role, "content": content[:300]})
            if recent:
                user_payload["recent_conversation"] = recent

        try:
            http_to = float(current_app.config.get("AI_HTTP_TIMEOUT_SECONDS", 120) or 120)
        except (TypeError, ValueError):
            http_to = 120.0
        try:
            planner_to = float(current_app.config.get("AI_AGENT_EVIDENCE_PLAN_TIMEOUT_SECONDS", 30) or 30)
        except (TypeError, ValueError):
            planner_to = 30.0
        timeout = max(5.0, min(planner_to, http_to))

        try:
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": sys},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                "max_completion_tokens": 250,
                "timeout": timeout,
            }
            if openai_model_supports_sampling_params(str(self.model)):
                kwargs["temperature"] = 0.0
            resp = self.client.chat.completions.create(**kwargs)
            text = str((resp.choices[0].message.content or "")).strip()
            obj = self._extract_json_object(text)
            if not isinstance(obj, dict):
                logger.info("Finish evidence assess: no JSON object in response")
                return None

            try:
                confidence = float(obj.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            min_conf = float(current_app.config.get("AI_AGENT_EVIDENCE_PLAN_MIN_CONFIDENCE", 0.7))
            if confidence < min_conf:
                logger.info(
                    "Finish evidence assess: confidence %.2f below threshold %.2f",
                    confidence,
                    min_conf,
                )
                return None

            still_in = obj.get("still_required")
            if not isinstance(still_in, list):
                return None

            seen: Set[str] = set()
            still: List[str] = []
            for item in still_in:
                fam = str(item or "").strip().lower()
                if fam not in still_available or fam in seen:
                    continue
                seen.add(fam)
                still.append(fam)

            if not still:
                logger.info("Finish evidence assess: sufficient (confidence=%.2f)", confidence)
                return None

            rationale = str(obj.get("rationale") or "").strip()
            logger.info(
                "Finish evidence assess: still_required=%s confidence=%.2f",
                still,
                confidence,
            )
            required = sorted(satisfied | set(still))
            return EvidencePlan(
                source_families=required,
                rationale=rationale or "Finish-time evidence assessment.",
                confidence=confidence,
            )
        except Exception as e:
            logger.warning("Finish evidence assess failed: %s", e)
            return None


def families_satisfied_by_tools(tools_used: List[str]) -> Set[str]:
    """Map executed tool names to satisfied evidence families."""
    used = {str(t or "").strip() for t in tools_used if t}
    satisfied: Set[str] = set()
    if used & INDICATOR_BANK_TOOLS:
        satisfied.add("indicator_bank")
    if used & DOCUMENT_TOOLS:
        satisfied.add("documents")
    if used & DATABANK_VALUE_TOOLS:
        satisfied.add("databank_values")
    return satisfied


def pending_evidence_families(
    plan: Optional[EvidencePlan],
    tools_used: List[str],
) -> List[str]:
    """Return required families not yet satisfied by tool calls."""
    if plan is None or not plan.source_families or plan.source_families == ["help_only"]:
        return []
    required = [f for f in plan.source_families if f in SOURCE_FAMILIES and f != "help_only"]
    satisfied = families_satisfied_by_tools(tools_used)
    return [f for f in required if f not in satisfied]


def available_evidence_families(
    tool_names: Set[str],
    *,
    documents_allowed: bool,
    databank_allowed: bool,
) -> Set[str]:
    """Source families the agent can still consult on this request."""
    available: Set[str] = set()
    if databank_allowed and bool(tool_names & INDICATOR_BANK_TOOLS):
        available.add("indicator_bank")
    if documents_allowed and bool(tool_names & DOCUMENT_TOOLS):
        available.add("documents")
    if databank_allowed and bool(tool_names & DATABANK_VALUE_TOOLS):
        available.add("databank_values")
    return available


def should_run_finish_evidence_assessment(
    *,
    tool_names: Set[str],
    tools_used: List[str],
    documents_allowed: bool,
    databank_allowed: bool,
) -> bool:
    """
    Structural gate: run finish-time LLM assessment when some (not all)
    available evidence families have been consulted.
    """
    available = available_evidence_families(
        tool_names,
        documents_allowed=documents_allowed,
        databank_allowed=databank_allowed,
    )
    satisfied = families_satisfied_by_tools(tools_used)
    logger.info(
        "[EvidencePlan] should_run_finish_assess: available=%s satisfied=%s "
        "docs_in_tools=%s documents_allowed=%s",
        sorted(available),
        sorted(satisfied),
        bool(tool_names & DOCUMENT_TOOLS),
        documents_allowed,
    )
    if len(available) <= 1:
        logger.info("[EvidencePlan] finish-assess gate: skip — only 1 family available")
        return False
    if not satisfied:
        logger.info("[EvidencePlan] finish-assess gate: skip — no families satisfied yet")
        return False
    if satisfied == available:
        logger.info("[EvidencePlan] finish-assess gate: skip — all available families already satisfied")
        return False
    logger.info(
        "[EvidencePlan] finish-assess gate: RUN — available=%s satisfied=%s missing=%s",
        sorted(available),
        sorted(satisfied),
        sorted(available - satisfied),
    )
    return True
