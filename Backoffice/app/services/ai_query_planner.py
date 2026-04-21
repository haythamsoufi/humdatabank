"""
AI Query Planner

Centralized planner that decides whether a user query is simple enough
for a one-tool (or one-tool + light extraction) execution path.
Uses rule-based fast path for obvious document list/count queries to save an LLM call.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from flask import current_app

from app.utils.ai_utils import openai_model_supports_sampling_params
from app.services.upr.tool_specs import UPR_PLANNER_ENTRIES

logger = logging.getLogger(__name__)

# Phrases that indicate a "list/count from documents" query → one search_documents + synthesize.
_DOCUMENT_LIST_PATTERNS = (
    "how many plans",
    "how many countries",
    "which countries mention",
    "which plans mention",
    "which plans have",
    "which countries have",
    "countries that mention",
    "plans that mention",
    "well-informed",
    "pgi minimum standards",
    "minimum standards",
    "list countries",
    "plans with ",
    "countries with ",
)

# Phrases that indicate a thematic Unified Plans coverage query — should route to
# analyze_unified_plans_focus_areas, not to a structured indicator lookup.
_UNIFIED_PLAN_THEME_PATTERNS = (
    "included in unified plan",
    "included in their unified plan",
    "include in unified plan",
    "in their unified plan",
    "in their 20",           # "in their 2026 Unified Plans"
    "unified plans that include",
    "unified plans that mention",
    "unified plans include",
    "unified plans mention",
    "unified plans cover",
    "which unified plans",
    "ns include",
    "national societ",        # "national societies that include/mention"
    # Substring of "unified plans" / matches "(UPL)"-style rewrites, e.g.
    # "List countries whose Unified Plans (UPL) prioritize…" (must not fall through
    # to document_list + search_documents + an extra synthesis LLM).
    "unified plan",
    "(upl",
    "upl)",
    "whose unified",
    "upl-",
)

# Queries containing these phrases need LLM-depth analysis and should NOT
# be handled by the deterministic fast path, even if they also match a
# theme pattern above.  The fast path cannot extract activity details,
# build custom table columns, or assess whether a topic is *substantively*
# addressed (vs merely mentioned in a boilerplate header).
_UNIFIED_PLAN_FORCE_LLM_RE = re.compile(
    r"(?:"
    r"details?\s+on\s+(?:the\s+)?(?:activity|activities|plan|plans|programme|program)"
    r"|activity\s+(?:detail|plans?|description)"
    r"|table\s+with\s+columns?"
    r"|create\s+a\s+table"
    r"|columns?\s+on\s+detail"
    r"|specific\s+activit"
    r"|what\s+(?:specific|concrete)\s+(?:activit|plan|programme)"
    r"|descri(?:be|ption)\s+(?:of\s+)?(?:the\s+)?(?:migration|activit)"
    r"|budget|timeframe|partner|implementing\s+partner"
    r"|target\s+population|geographic\s+focus"
    r"|how\s+(?:do|are)\s+(?:they|these|the\s+ns)"
    r"|compare\s+(?:the\s+)?(?:activit|plan|approach)"
    r"|breakdown\s+(?:of|by)"
    r")",
    re.IGNORECASE,
)


@dataclass
class SimplePlan:
    """Lightweight generic fast-path plan."""
    kind: str
    tool_name: str
    tool_args: Dict[str, Any] = field(default_factory=dict)
    output_hint: str = "text"


class AIQueryPlanner:
    """LLM planner that emits validated SimplePlan objects."""

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
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _validate_simple_plan_dict(plan: Dict[str, Any], tool_names: Set[str]) -> Optional[SimplePlan]:
        if not isinstance(plan, dict):
            return None
        if not bool(plan.get("is_simple", True)):
            return None
        try:
            confidence = float(plan.get("confidence", 0.0))
        except (ValueError, TypeError):
            confidence = 0.0
        if confidence < 0.45:
            return None

        kind = str(plan.get("kind") or "").strip()
        tool_name = str(plan.get("tool_name") or "").strip()
        tool_args = plan.get("tool_args") if isinstance(plan.get("tool_args"), dict) else {}
        output_hint = str(plan.get("output_hint") or "text").strip().lower()

        if tool_name not in tool_names:
            return None
        if output_hint not in {"map", "chart", "table", "text"}:
            output_hint = "text"

        required_by_tool = {
            "get_indicator_value": {"country_identifier", "indicator_name"},
            "get_indicator_timeseries": {"country_identifier", "indicator_name"},
            "list_documents": set(),
            "search_documents": {"query"},
            "get_indicator_values_for_all_countries": {"indicator_name"},
            "compare_countries": {"country_identifiers", "indicator_name"},
            "get_assignment_indicator_values": {"country_identifier", "template_identifier"},
            "get_form_field_value": {"country_identifier", "field_label_or_name"},
        }
        required_by_tool.update(UPR_PLANNER_ENTRIES["required_by_tool"])
        required = required_by_tool.get(tool_name, set())
        if any(k not in tool_args or tool_args.get(k) in ("", None, []) for k in required):
            return None

        # Normalize high-impact args.
        for k, v in list(tool_args.items()):
            if isinstance(v, str):
                tool_args[k] = v.strip()
        if tool_name == "search_documents":
            tool_args["return_all_countries"] = bool(tool_args.get("return_all_countries", False))
            try:
                tk = int(tool_args.get("top_k", 5))
            except (ValueError, TypeError):
                tk = 5
            max_top_k = int(current_app.config.get("AI_DOCUMENT_SEARCH_MAX_TOP_K_LIST", 500))
            tool_args["top_k"] = max(1, min(tk, max_top_k))
        if tool_name == "list_documents":
            try:
                tool_args["limit"] = max(1, min(int(tool_args.get("limit", 200)), 500))
            except (ValueError, TypeError):
                tool_args["limit"] = 200
            try:
                tool_args["offset"] = max(0, int(tool_args.get("offset", 0)))
            except (ValueError, TypeError):
                tool_args["offset"] = 0
        if tool_name == "analyze_unified_plans_focus_areas":
            tool_args.setdefault("areas", ["cash", "cea", "livelihoods", "social_protection"])
            try:
                tool_args["limit"] = max(1, min(int(tool_args.get("limit", 500)), 1000))
            except (ValueError, TypeError):
                tool_args["limit"] = 500

        if not kind:
            kind_map = {
                "get_indicator_value": "single_value",
                "get_indicator_timeseries": "timeseries",
                "list_documents": "document_inventory",
                "search_documents": "per_country_docs" if bool(tool_args.get("return_all_countries")) else "document_search",
            }
            kind_map.update(UPR_PLANNER_ENTRIES["kind_map"])
            kind = kind_map.get(tool_name, "simple")

        return SimplePlan(kind=kind, tool_name=tool_name, tool_args=tool_args, output_hint=output_hint or "text")

    @staticmethod
    def _extract_theme_areas_from_query(query: str) -> List[str]:
        """
        Extract likely focus-area keys from a thematic Unified Plans query.
        Returns a list of snake_case area keys for analyze_unified_plans_focus_areas.
        """
        q = (query or "").lower()
        detected: List[str] = []
        _THEME_MAP = [
            (["migration", "displacement", "migrant", "refugee", "idp", "asylum", "forced migration", "mixed migration"], "migration_displacement"),
            (["climate change", "climate adaptation", "climate risk", "climate resilience", "climate"], "climate"),
            (["mhpss", "mental health", "psychosocial"], "mhpss"),
            (["pgi", "protection gender inclusion", "gender-based violence", "gbv", "gender equality", "disability inclusion"], "pgi"),
            (["livelihood", "livelihoods", "food security", "economic security"], "livelihoods"),
            (["cash assistance", "cash transfer", "cash and voucher", "cva", "cash-based"], "cash"),
            (["community engagement", "accountability", "cea", "aap"], "cea"),
            (["social protection", "social assistance", "social safety net"], "social_protection"),
            (["health", "primary health care", "community health", "epidemic", "pandemic"], "health"),
            (["disaster risk reduction", "drr", "disaster preparedness", "early warning"], "disaster_risk_reduction"),
        ]
        seen: set = set()
        for keywords, area_key in _THEME_MAP:
            if area_key in seen:
                continue
            for kw in keywords:
                if kw in q:
                    detected.append(area_key)
                    seen.add(area_key)
                    break
        return detected or ["migration_displacement"]  # safe default for unrecognised themes

    @staticmethod
    def try_rule_based_document_list(query: str, tool_names: Set[str]) -> Optional[SimplePlan]:
        """
        If the query clearly asks for a list/count from document content, return a simple plan
        without calling the LLM. Saves one planner call and forces a single search + synthesis.
        """
        q = (query or "").strip().lower()
        if not q or len(q) < 10:
            return None

        # Thematic Unified Plans queries (e.g. "migration in Unified Plans") must go to
        # analyze_unified_plans_focus_areas, not to a structured indicator tool.
        # However, queries that ask for activity details, custom table columns,
        # budgets, partners etc. need the full LLM path because the deterministic
        # fast path cannot assess substantive activity coverage.
        if "analyze_unified_plans_focus_areas" in tool_names and any(p in q for p in _UNIFIED_PLAN_THEME_PATTERNS):
            if _UNIFIED_PLAN_FORCE_LLM_RE.search(q):
                logger.info(
                    "Query planner: unified_plans_focus theme matched but query "
                    "requests activity details / custom table — deferring to LLM path."
                )
                return None
            areas = AIQueryPlanner._extract_theme_areas_from_query(query)
            plan = SimplePlan(
                kind="unified_plans_focus",
                tool_name="analyze_unified_plans_focus_areas",
                tool_args={"areas": areas, "limit": 500},
                output_hint="table",
            )
            logger.info("Query planner: rule-based unified_plans_focus plan (skip LLM), areas=%s", areas)
            return plan

        if "search_documents" not in tool_names:
            return None
        if not any(p in q for p in _DOCUMENT_LIST_PATTERNS):
            return None
        # Derive search query: use original query, truncated (tool expects a short query).
        search_query = (query or "").strip()[:200]
        max_top_k = int(current_app.config.get("AI_DOCUMENT_SEARCH_MAX_TOP_K_LIST", 500))
        plan = SimplePlan(
            kind="document_list",
            tool_name="search_documents",
            tool_args={
                "query": search_query,
                "return_all_countries": True,
                "top_k": max_top_k,
                "limit": max(100, min(200, max_top_k)),
            },
            output_hint="table",
        )
        logger.info("Query planner: rule-based document_list plan (skip LLM)")
        return plan

    def plan_simple(self, *, query: str, tool_names: Set[str]) -> Optional[SimplePlan]:
        """Return a validated SimplePlan for simple queries, or None."""
        q = str(query or "").strip()
        if not q or not tool_names:
            return None

        # Rule-based fast path for obvious document list/count queries (saves 1 LLM call).
        rule_plan = self.try_rule_based_document_list(q, tool_names)
        if rule_plan is not None:
            return rule_plan

        allowed = {
            "get_indicator_value",
            "get_indicator_timeseries",
            "get_indicator_values_for_all_countries",
            "list_documents",
            "search_documents",
            "compare_countries",
            "get_assignment_indicator_values",
            "get_form_field_value",
        }
        allowed.update(UPR_PLANNER_ENTRIES["allowed_tools"])
        allowed = sorted(t for t in tool_names if t in allowed)
        if not allowed:
            return None

        sys = (
            "You are a routing planner for a data assistant.\n"
            "Decide if the user query can be solved with ONE tool call (or one tool call + lightweight extraction), "
            "without full multi-step ReAct.\n"
            "Return ONLY valid JSON with shape:\n"
            "{"
            "\"is_simple\": true|false, "
            "\"kind\": \"single_value|timeseries|document_inventory|per_country_docs|unified_plans_focus|complex\", "
            "\"tool_name\": \"<tool>\", "
            "\"tool_args\": { ... }, "
            "\"output_hint\": \"map|chart|table|text\", "
            "\"confidence\": 0.0-1.0"
            "}\n"
            "Rules:\n"
            "- If unsure, set is_simple=false and kind='complex'.\n"
            "- Choose tool_name ONLY from allowed tools.\n"
            "- Provide required args for chosen tool.\n"
            "- Do not invent tools or fields.\n"
            "- For per-country docs use search_documents with return_all_countries=true.\n"
            "- For simple trends use timeseries tools.\n"
            "- For document inventory requests use list_documents.\n"
            "- CRITICAL: For any query asking which Unified Plans include, mention, cover, prioritise, or address a theme or focus area "
            "(e.g. 'migration and displacement included in Unified Plans', 'which Unified Plans mention climate', "
            "'NSs that include MHPSS in their plan') use analyze_unified_plans_focus_areas with kind='unified_plans_focus'. "
            "Pass the theme(s) as snake_case strings in tool_args.areas "
            "(e.g. areas=['migration_displacement'] or areas=['climate'] or areas=['pgi']). "
            "NEVER route these to get_indicator_value — thematic Unified Plan content is stored in documents, not structured indicators.\n"
            "- Output only JSON."
        )
        user = json.dumps({"query": q, "allowed_tools": allowed}, ensure_ascii=False)

        try:
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": sys},
                    {"role": "user", "content": user},
                ],
                "max_completion_tokens": 350,
            }
            if openai_model_supports_sampling_params(str(self.model)):
                kwargs["temperature"] = 0.0
            resp = self.client.chat.completions.create(**kwargs)
            text = str((resp.choices[0].message.content or "")).strip()
            obj = self._extract_json_object(text)
            return self._validate_simple_plan_dict(obj or {}, tool_names=tool_names) if obj else None
        except Exception as e:
            logger.warning("LLM query planner failed: %s", e)
            return None

