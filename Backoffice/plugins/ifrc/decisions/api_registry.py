"""Decision Support routes for Admin -> API Management. Browser-session endpoints only; no API-key access."""

from __future__ import annotations

_COMMON = [
    {"name": "region", "type": "text", "description": "Region name."},
    {"name": "country", "type": "select", "option_source": "country_iso3", "description": "ISO3 country code."},
    {"name": "round", "type": "text", "placeholder": "P27", "description": "Round code, for example P27."},
    {"name": "validation_state", "type": "select", "options": ["validated", "provisional", "draft"], "description": "Narrow to one validation state."},
    {"name": "lang", "type": "select", "options": ["en", "fr", "es", "ar"], "description": "Language for titles and messages."},
]


def _row(path: str, methods: list[str], description: str, *, params: list | None = None) -> dict:
    return {
        "group": "Decision Support",
        "path": path,
        "methods": methods,
        "auth": "session",
        "rate_limited": True,
        "description": description,
        "consumers": "Backoffice UI, chatbot tools",
        "paginated": False,
        "query_params": params if params is not None else [],
    }


API_ENDPOINTS = [
    _row("/api/decisions", ["GET"], "Decision catalogue visible to the signed-in user, with coverage and open flag counts.", params=_COMMON),
    _row("/api/decisions/<decision_id>", ["GET"], "One decision definition with its metrics and rules."),
    _row("/api/decisions/<decision_id>/summary", ["GET"], "Evidence summary, key metrics, trend and country table.", params=_COMMON),
    _row(
        "/api/decisions/<decision_id>/metrics",
        ["GET"],
        "Metric values grouped by dimensions. Zero, not applicable, unavailable and not reported stay distinct.",
        params=_COMMON + [
            {"name": "metric", "type": "text", "description": "One metric id from the decision."},
            {"name": "group_by", "type": "text", "placeholder": "country,year", "description": "Comma-separated dimensions."},
        ],
    ),
    _row(
        "/api/decisions/<decision_id>/flags",
        ["GET"],
        "Rule-based flags with trigger values, thresholds and evidence ids.",
        params=_COMMON + [
            {"name": "flag_status", "type": "select", "options": ["new", "acknowledged", "under_review", "resolved", "dismissed"], "description": "Review status."},
            {"name": "severity", "type": "select", "options": ["information", "review", "important", "urgent"], "description": "Severity."},
        ],
    ),
    _row("/api/decision-flags/<flag_id>", ["GET"], "One flag with its rule and evidence records."),
    _row("/api/decision-flags/<flag_id>/acknowledge", ["POST"], "Mark a flag acknowledged."),
    _row("/api/decision-flags/<flag_id>/review", ["POST"], "Mark a flag under review."),
    _row("/api/decision-flags/<flag_id>/resolve", ["POST"], "Resolve or dismiss a flag."),
    _row("/api/decision-flags/<flag_id>/feedback", ["POST"], "Record whether a flag was useful, incorrect or expected."),
    _row("/api/decision-evidence/<evidence_id>", ["GET"], "One evidence record with provenance."),
    _row("/api/decision-sources/<path:reference>", ["GET"], "Source record, by evidence id or submission:<id>."),
    _row("/api/metric-definitions", ["GET"], "Metric registry with definitions, units and disclosure rules.", params=_COMMON[-1:]),
    _row("/api/decision-methodologies/<decision_id>", ["GET"], "Published methodology, metrics and rule thresholds.", params=_COMMON[-1:]),
    _row("/api/admin/decisions", ["GET"], "Administration overview of decisions, rules and metrics."),
    _row("/api/admin/decisions/<decision_id>", ["PUT"], "Publish a new decision version."),
    _row("/api/admin/decision-rules/<rule_id>", ["PUT"], "Publish a new rule version (threshold, severity, enabled)."),
    _row("/api/admin/decision-rules/<rule_id>/history", ["GET"], "All published versions of a rule."),
    _row("/api/admin/decision-runs", ["GET"], "Recent rule executions."),
    _row("/api/admin/decision-feedback", ["GET"], "Flag feedback counts by rule version."),
    _row("/api/admin/decision-integrations", ["GET"], "Source freshness and integration health."),
]
