"""Chatbot tools for Decision Support.

The model never queries tables or writes SQL. Each tool calls the same service functions as the UI, with
the requesting user's access context, and returns presentation-ready objects with provenance. A user who
cannot see Decision Support gets no tools and a refusal if a call is forced.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

PLUGIN_ID = "ifrc"
MAX_ROWS = 60
MAX_FLAGS = 25

ANSWER_GUIDANCE = (
    "Answer only from this result. Give the direct answer, then the scope and filters used, the data round and "
    "refresh time, the key figures or flags, evidence references, and any coverage or validation caveats. "
    "Separate calculated findings from your own interpretation. Flags are prompts for human review, not "
    "conclusions: say 'requires review', never 'poor performance', and do not rank National Societies. "
    "Missing, unavailable and not applicable data are not zero. If the result is empty or limited, say the "
    "evidence is incomplete instead of inferring. Offer to open the decision view using 'open_view'."
)

_FILTER_PROPERTIES: dict[str, Any] = {
    "region": {"type": "string", "description": "Region name, for example 'MENA'. Optional."},
    "country": {"type": "string", "description": "ISO3 country code, for example 'TUR'. Optional."},
    "round": {
        "type": "string",
        "description": "Plan round code such as 'P27'. Omit to use the latest plan round in the user's scope.",
    },
    "validation_state": {
        "type": "string",
        "enum": ["validated", "provisional", "draft"],
        "description": "Restrict to one validation state. Optional.",
    },
}


def _spec(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required or []},
        },
    }


DECISION_TOOL_SPECS: list[dict[str, Any]] = [
    _spec(
        "list_decisions",
        "List the Decision Support decisions the user may see, each with its question, data readiness, coverage "
        "and number of open attention flags. Use first when the user asks what decisions or decision views exist.",
        {k: _FILTER_PROPERTIES[k] for k in ("region", "round")},
    ),
    _spec(
        "get_decision_definition",
        "Get one decision's definition, metrics, rules, thresholds (marked provisional until FDS approves them) and "
        "methodology. Use to explain how a flag or metric is calculated.",
        {"decision_id": {"type": "string", "description": "Decision id such as 'DEC-002' or its slug."}},
        ["decision_id"],
    ),
    _spec(
        "get_decision_summary",
        "Evidence summary for a decision: key metrics, funding by source, trend by round, a country table with "
        "round-on-round percent change and people targeted, flag counts, coverage and data-quality caveats. "
        "For a custom threshold (for example 'changed by more than 40%') filter the country table's percent_change "
        "yourself and say that it differs from the configured rule.",
        {"decision_id": {"type": "string", "description": "Decision id such as 'DEC-002' or 'DEC-004'."}, **_FILTER_PROPERTIES},
        ["decision_id"],
    ),
    _spec(
        "get_decision_metrics",
        "Metric values for a decision, optionally grouped (country, region, round, year, funding_source, "
        "strategic_priority, validation_state). Use for shares and totals, for example which Strategic Priorities "
        "account for most of the requirement (metric 'funding_requirement_by_priority', group_by 'strategic_priority').",
        {
            "decision_id": {"type": "string", "description": "Decision id."},
            "metric": {"type": "string", "description": "One metric id from the decision. Omit for all."},
            "group_by": {"type": "string", "description": "Comma-separated dimensions, at most three."},
            **_FILTER_PROPERTIES,
        },
        ["decision_id"],
    ),
    _spec(
        "get_decision_flags",
        "Rule-based attention flags for a decision with exact trigger values, rule, threshold, comparison period, "
        "validation state and evidence ids. Use for 'which countries were flagged', 'why was X flagged', or for "
        "incomplete or unvalidated plans (DEC-004). Flags are review prompts, not conclusions.",
        {
            "decision_id": {"type": "string", "description": "Decision id."},
            "rule_id": {"type": "string", "description": "Only flags from this rule, for example 'RULE-YOY-CHANGE'."},
            "severity": {"type": "string", "enum": ["information", "review", "important", "urgent"]},
            "flag_status": {"type": "string", "enum": ["new", "acknowledged", "under_review", "resolved", "dismissed"]},
            **_FILTER_PROPERTIES,
        },
        ["decision_id"],
    ),
    _spec(
        "get_flag_evidence",
        "Get one flag with its rule and the evidence records behind it. Use to answer 'why was this flagged'.",
        {"flag_id": {"type": "string", "description": "Flag id from get_decision_flags, starting with 'FLAG-'."}},
        ["flag_id"],
    ),
    _spec(
        "get_source_record",
        "Open one evidence or source record by reference: an evidence id ('EVID-...') or 'submission:<id>'.",
        {"reference": {"type": "string", "description": "Evidence id or submission reference."}},
        ["reference"],
    ),
]

DECISION_TOOL_NAMES = frozenset(spec["function"]["name"] for spec in DECISION_TOOL_SPECS)


def tools_available() -> bool:
    """True when the plugin is active and the request user may use Decision Support."""
    try:
        from flask import current_app

        from app.services.data_retrieval.shared import get_effective_request_user
        from plugins.ifrc.decisions.access import resolve_access_context

        manager = getattr(current_app, "plugin_manager", None)
        if manager is None:
            return False
        manager.sync_activation_state()
        if not manager.is_plugin_active(PLUGIN_ID):
            return False
        return resolve_access_context(get_effective_request_user()).can_view
    except Exception:
        logger.debug("Decision tools unavailable", exc_info=True)
        return False


def _access():
    from app.services.data_retrieval.shared import get_effective_request_user
    from plugins.ifrc.decisions.access import resolve_access_context

    return resolve_access_context(get_effective_request_user())


def _filters(kwargs: dict[str, Any]):
    from plugins.ifrc.decisions.facts import Filters

    allowed = ("region", "country", "round", "validation_state", "severity", "flag_status", "year")
    return Filters.from_args({k: kwargs.get(k) for k in allowed if kwargs.get(k) not in (None, "")})


def _open_view(slug: str, filters) -> str:
    from urllib.parse import urlencode

    params = {k: v for k, v in filters.as_scope().items() if k in ("region", "country", "round", "validation_state")}
    base = f"/decisions/{slug}"
    return f"{base}?{urlencode(params)}" if params else base


def _truncate(rows: list[Any], limit: int) -> tuple[list[Any], bool]:
    return (rows[:limit], len(rows) > limit)


def _wrap(payload: dict[str, Any], *, open_view: str | None = None, evidence_ids: list[str] | None = None) -> dict[str, Any]:
    out = dict(payload)
    out["success"] = True
    out["answer_guidance"] = ANSWER_GUIDANCE
    if open_view:
        out["open_view"] = open_view
    if evidence_ids:
        out["evidence_links"] = [f"/api/decision-evidence/{eid}" for eid in evidence_ids[:50]]
        logger.info("decision_support ai_evidence ids=%s", evidence_ids[:50])
    return out


def _refused(reason: str = "You do not have access to Decision Support data.") -> dict[str, Any]:
    return {"success": False, "error": reason}


def _call(fn: Callable[[Any], dict[str, Any]]) -> dict[str, Any]:
    from plugins.ifrc.decisions import service

    access = _access()
    if not access.authenticated or not access.can_view:
        return _refused()
    try:
        return fn(access)
    except service.NotFound:
        return _refused("No such decision, flag or record in your scope.")
    except ValueError as exc:
        return {"success": False, "error": str(exc)}


def list_decisions(**kwargs: Any) -> dict[str, Any]:
    from plugins.ifrc.decisions import service

    def run(access):
        filters = _filters(kwargs)
        body = service.list_decisions(access, filters)
        return _wrap(
            {
                "decisions": body["data"]["decisions"],
                "refreshed_at": body.get("refreshed_at"),
                "permission_context": body["permission_context"],
            }
        )

    return _call(run)


def get_decision_definition(decision_id: str = "", **kwargs: Any) -> dict[str, Any]:
    from plugins.ifrc.decisions import service

    def run(access):
        resolved = service.resolve_decision_id(str(decision_id), access)
        return _wrap({"definition": service.get_definition(resolved, access), "methodology": service.methodology(resolved, access)["data"]["methodology_markdown"]})

    return _call(run)


def get_decision_summary(decision_id: str = "", **kwargs: Any) -> dict[str, Any]:
    from plugins.ifrc.decisions import service

    def run(access):
        resolved = service.resolve_decision_id(str(decision_id), access)
        filters = _filters(kwargs)
        body = service.decision_summary(resolved, filters, access)
        data = body["data"]
        entities, truncated = _truncate(data["entities"], MAX_ROWS)
        evidence = [eid for f in data["top_flags"] for eid in f["evidence_ids"]]
        return _wrap(
            {
                "decision": {"id": data["decision"]["id"], "title": data["decision"]["title"], "question": data["decision"]["question"]},
                "scope": body["scope"],
                "coverage": body["coverage"],
                "data_quality": body["data_quality"],
                "refreshed_at": body["refreshed_at"],
                "key_metrics": data["key_metrics"],
                "funding_by_source": data["funding_by_source"],
                "trend": data["trend"],
                "countries": entities,
                "countries_truncated": truncated,
                "flag_counts": data["flag_counts"],
                "top_flags": data["top_flags"][:10],
                "permission_context": body["permission_context"],
            },
            open_view=_open_view(data["decision"]["slug"], filters),
            evidence_ids=evidence,
        )

    return _call(run)


def get_decision_metrics(decision_id: str = "", metric: str = "", group_by: str = "", **kwargs: Any) -> dict[str, Any]:
    from plugins.ifrc.decisions import service

    def run(access):
        resolved = service.resolve_decision_id(str(decision_id), access)
        filters = _filters(kwargs)
        dims = tuple(p.strip() for p in str(group_by or "").split(",") if p.strip())[:3]
        body = service.decision_metrics(resolved, filters, access, group_by=dims, metric_id=(metric or None))
        results = []
        for result in body["data"]:
            groups, truncated = _truncate(result["groups"], MAX_ROWS)
            results.append({**result, "groups": groups, "truncated": truncated})
        slug = service.get_definition(resolved, access)["slug"]
        return _wrap(
            {
                "metrics": results,
                "scope": body["scope"],
                "coverage": body["coverage"],
                "data_quality": body["data_quality"],
                "refreshed_at": body["refreshed_at"],
                "permission_context": body["permission_context"],
            },
            open_view=_open_view(slug, filters),
        )

    return _call(run)


def get_decision_flags(decision_id: str = "", rule_id: str = "", **kwargs: Any) -> dict[str, Any]:
    from plugins.ifrc.decisions import service

    def run(access):
        resolved = service.resolve_decision_id(str(decision_id), access)
        filters = _filters(kwargs)
        body = service.decision_flags(resolved, filters, access)
        flags = body["data"]["flags"]
        if rule_id:
            flags = [f for f in flags if f["rule_id"] == str(rule_id)]
        shown, truncated = _truncate(flags, MAX_FLAGS)
        slug = service.get_definition(resolved, access)["slug"]
        return _wrap(
            {
                "flags": shown,
                "flags_total": len(flags),
                "flags_truncated": truncated,
                "counts": body["data"]["counts"],
                "rules": body["data"]["rules"],
                "scope": body["scope"],
                "coverage": body["coverage"],
                "data_quality": body["data_quality"],
                "refreshed_at": body["refreshed_at"],
                "permission_context": body["permission_context"],
            },
            open_view=_open_view(slug, filters),
            evidence_ids=[eid for f in shown for eid in f["evidence_ids"]],
        )

    return _call(run)


def get_flag_evidence(flag_id: str = "", **kwargs: Any) -> dict[str, Any]:
    from plugins.ifrc.decisions import service

    def run(access):
        body = service.flag_detail(str(flag_id), access)
        data = body["data"]
        return _wrap(
            {"flag": data["flag"], "evidence": data["evidence"], "rule": data["rule"], "refreshed_at": body["refreshed_at"]},
            evidence_ids=[e["id"] for e in data["evidence"]],
        )

    return _call(run)


def get_source_record(reference: str = "", **kwargs: Any) -> dict[str, Any]:
    from plugins.ifrc.decisions import service

    def run(access):
        body = service.get_source_record(str(reference), access)
        return _wrap({"record": body["data"], "refreshed_at": body.get("refreshed_at")})

    return _call(run)


TOOL_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "list_decisions": list_decisions,
    "get_decision_definition": get_decision_definition,
    "get_decision_summary": get_decision_summary,
    "get_decision_metrics": get_decision_metrics,
    "get_decision_flags": get_decision_flags,
    "get_flag_evidence": get_flag_evidence,
    "get_source_record": get_source_record,
}
