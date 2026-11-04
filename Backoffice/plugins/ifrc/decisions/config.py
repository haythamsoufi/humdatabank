"""Decision Support configuration: code defaults plus a versioned database override.

Defaults below are version 1 of each record. Publishing a change stores a new
immutable version in ``ifrc_decision_config_version``; the highest published
version is live and every earlier version stays readable for audit.

All thresholds are PROVISIONAL examples from the FDS handoff brief. They are not
approved policy and are labelled as such wherever they are shown.
"""

from __future__ import annotations

import copy
import re
from typing import Any

LANGUAGES = ("en", "fr", "es", "ar")
SEVERITIES = ("information", "review", "important", "urgent")
FLAG_STATUSES = ("new", "acknowledged", "under_review", "resolved", "dismissed")
FEEDBACK_VERDICTS = ("useful", "not_useful", "incorrect", "expected")
VISIBILITY_LEVELS = (
    "public",
    "network_authenticated",
    "ifrc_internal",
    "restricted_process",
    "restricted_country_or_ns",
    "admin",
)
OPERATORS = (
    "absolute_percent_change_gte",
    "metric_present_other_missing",
    "share_of_total_gte",
    "validation_pending_with_data",
    "stalled_days_gte",
    "overdue_days_gte",
    "unavailable_count_gte",
    "coverage_below_pct",
)
DATA_QUALITY_LEVELS = ("any", "reviewable", "validated")
ENTITY_TYPES = ("country", "scope")

_TEMPLATE_VAR = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")

PROVISIONAL_NOTE = "Provisional threshold: not approved policy until validated by FDS."


def tr(value: Any, lang: str | None, fallback: str = "en") -> str:
    """Pick a translation from ``{"en": ...}``; plain strings pass through."""
    if isinstance(value, dict):
        for code in (lang, fallback):
            if code and value.get(code):
                return str(value[code])
        return next((str(v) for v in value.values() if v), "")
    return "" if value is None else str(value)


def render_template(template: str, values: dict[str, Any]) -> str:
    """Replace ``{{name}}`` placeholders. Unknown names are left blank; nothing is evaluated."""

    def _sub(match: re.Match) -> str:
        found = values.get(match.group(1))
        return "" if found is None else str(found)

    return _TEMPLATE_VAR.sub(_sub, template)


_DEFAULT_DECISIONS: dict[str, dict[str, Any]] = {
    "DEC-002": {
        "id": "DEC-002",
        "slug": "strategic-planning-resource-prioritization",
        "title": {
            "en": "Inform strategic planning and resource prioritization",
            "fr": "Éclairer la planification stratégique et la priorisation des ressources",
            "es": "Orientar la planificación estratégica y la priorización de recursos",
            "ar": "دعم التخطيط الاستراتيجي وتحديد أولويات الموارد",
        },
        "question": {
            "en": "What priorities, targets and resource requirements should inform planning discussions?",
            "fr": "Quelles priorités, cibles et besoins en ressources devraient éclairer les discussions de planification ?",
            "es": "¿Qué prioridades, metas y necesidades de recursos deberían orientar los debates de planificación?",
            "ar": "ما الأولويات والأهداف ومتطلبات الموارد التي ينبغي أن تسترشد بها مناقشات التخطيط؟",
        },
        "description": {
            "en": (
                "Funding requirements and people to be reached from Unified Plans, by country, region and "
                "funding source, with round-on-round change and the validation status of each submission."
            ),
            "fr": (
                "Besoins de financement et personnes à atteindre issus des plans unifiés, par pays, région et "
                "source de financement, avec l'évolution d'un cycle à l'autre et l'état de validation."
            ),
        },
        "owner_team": "FDS",
        "status": "active",
        "visibility": "ifrc_internal",
        "allowed_roles": ["system_manager", "admin", "user"],
        "audience": ["IFRC leadership", "Regional PMER/QA", "FDS", "Authorized PNS users"],
        "dimensions": ["year", "round", "region", "country", "funding_source", "strategic_priority"],
        "metric_ids": [
            "funding_requirement",
            "funding_requirement_by_priority",
            "people_targeted",
            "submission_coverage",
        ],
        "rule_ids": [
            "RULE-YOY-CHANGE",
            "RULE-MISSING-TARGET",
            "RULE-CONCENTRATION",
            "RULE-UNVALIDATED-REQUIREMENT",
        ],
        "default_round_kind": "plan",
        "methodology_markdown": (
            "**Evidence.** Funding requirements are summed from the Unified Plan (template 24) total columns, "
            "by host National Society, IFRC Secretariat and each Participating National Society. Where a PNS has "
            "submitted its own plan, its figure replaces the host's entry for that PNS.\n\n"
            "**Attention view, not a ranking.** Flags show the contributing facts and threshold. No composite "
            "score is calculated. Missing or unavailable data is reported as such and is never treated as a low value.\n\n"
            "**Round-on-round change** compares the first planning year of the selected round with the first "
            "planning year of the previous comparable round.\n\n"
            "**Provisional.** Thresholds are examples pending FDS approval."
        ),
        "version": 1,
        "effective_from": "2026-11-04",
    },
    "DEC-004": {
        "id": "DEC-004",
        "slug": "trends-gaps-inconsistencies",
        "title": {
            "en": "Identify trends, gaps and inconsistencies requiring management attention",
            "fr": "Repérer les tendances, lacunes et incohérences nécessitant l'attention de la direction",
            "es": "Identificar tendencias, brechas e incoherencias que requieren atención de la dirección",
            "ar": "تحديد الاتجاهات والفجوات والتناقضات التي تتطلب اهتمام الإدارة",
        },
        "question": {
            "en": "Which data changes, gaps, anomalies or process bottlenecks require review?",
            "fr": "Quels changements, lacunes, anomalies ou goulets d'étranglement des processus nécessitent un examen ?",
            "es": "¿Qué cambios en los datos, brechas, anomalías o cuellos de botella del proceso requieren revisión?",
            "ar": "ما التغييرات أو الفجوات أو الحالات الشاذة أو اختناقات العمليات في البيانات التي تتطلب المراجعة؟",
        },
        "description": {
            "en": (
                "Submission and validation pipeline for Unified Plans and Reports: stalled reviews, overdue "
                "submissions, indicators with data unavailable, large round-on-round changes and reporting coverage."
            ),
            "fr": (
                "Circuit de soumission et de validation des plans et rapports unifiés : examens bloqués, "
                "soumissions en retard, indicateurs sans données, variations importantes et couverture."
            ),
        },
        "owner_team": "FDS",
        "status": "active",
        "visibility": "ifrc_internal",
        "allowed_roles": ["system_manager", "admin", "user"],
        "audience": ["FDS", "Regional PMER/QA", "Data owners"],
        "dimensions": ["round", "region", "country", "validation_state"],
        "metric_ids": [
            "submission_coverage",
            "submissions_stalled_days",
            "submissions_overdue_days",
            "indicators_data_unavailable",
            "funding_requirement",
        ],
        "rule_ids": [
            "RULE-YOY-CHANGE",
            "RULE-STALLED-REVIEW",
            "RULE-OVERDUE-SUBMISSION",
            "RULE-DATA-UNAVAILABLE",
            "RULE-LOW-COVERAGE",
        ],
        "default_round_kind": "plan",
        "methodology_markdown": (
            "**Evidence.** Assignment status, due and submission dates from Unified Plan and Report assignments; "
            "indicator availability flags from Unified Plan answers.\n\n"
            "**Workflow rules** use the assignment status only: *stalled* means submitted or sent for review for "
            "longer than the threshold; *overdue* means still open after the due date plus the threshold.\n\n"
            "**Not covered yet.** Cross-process reconciliation (Unified Reporting vs FDRS) and source-API "
            "synchronization windows need approved data contracts.\n\n"
            "**Provisional.** Thresholds are examples pending FDS approval."
        ),
        "version": 1,
        "effective_from": "2026-11-04",
    },
}


def _t(en: str, fr: str | None = None, es: str | None = None, ar: str | None = None) -> dict[str, str]:
    out = {"en": en}
    for code, text in (("fr", fr), ("es", es), ("ar", ar)):
        if text:
            out[code] = text
    return out


_DEFAULT_RULES: dict[str, dict[str, Any]] = {
    "RULE-YOY-CHANGE": {
        "id": "RULE-YOY-CHANGE",
        "name": _t("Material round-on-round change", "Variation importante d'un cycle à l'autre"),
        "version": 1,
        "type": "deterministic",
        "enabled": True,
        "metric_id": "funding_requirement",
        "comparison": "previous_comparable_round",
        "condition": {"operator": "absolute_percent_change_gte", "value": 30},
        "minimum_data_quality": "reviewable",
        "severity": "review",
        "entity_type": "country",
        "message_template": _t(
            "{{entity_name}}: funding requirement changed by {{percent_change}}% "
            "({{baseline_value}} to {{current_value}} {{currency}}) compared with {{baseline_period}}.",
            "{{entity_name}} : le besoin de financement a varié de {{percent_change}} % "
            "({{baseline_value}} à {{current_value}} {{currency}}) par rapport à {{baseline_period}}.",
        ),
        "recommended_follow_up": _t(
            "Review the submission comments and confirm the change with the responsible focal point.",
            "Examiner les commentaires de la soumission et confirmer la variation avec le point focal responsable.",
        ),
        "visibility": "ifrc_internal",
        "owner_team": "FDS",
        "provisional": True,
    },
    "RULE-MISSING-TARGET": {
        "id": "RULE-MISSING-TARGET",
        "name": _t("Funding requirement without people-to-be-reached target"),
        "version": 1,
        "type": "deterministic",
        "enabled": True,
        "metric_id": "funding_requirement",
        "other_metric_id": "people_targeted",
        "comparison": "same_round",
        "condition": {"operator": "metric_present_other_missing", "value": 0},
        "minimum_data_quality": "reviewable",
        "severity": "review",
        "entity_type": "country",
        "message_template": _t(
            "{{entity_name}} reports a funding requirement of {{current_value}} {{currency}} but no "
            "people-to-be-reached target is available for {{current_period}}.",
            "{{entity_name}} déclare un besoin de financement de {{current_value}} {{currency}} mais aucune "
            "cible de personnes à atteindre n'est disponible pour {{current_period}}.",
        ),
        "recommended_follow_up": _t(
            "Check whether targets were entered or marked not applicable, and contact the data owner if not.",
            "Vérifier si les cibles ont été saisies ou marquées non applicables, sinon contacter le responsable des données.",
        ),
        "visibility": "ifrc_internal",
        "owner_team": "FDS",
        "provisional": True,
    },
    "RULE-CONCENTRATION": {
        "id": "RULE-CONCENTRATION",
        "name": _t("Concentration of requirements"),
        "version": 1,
        "type": "deterministic",
        "enabled": True,
        "metric_id": "funding_requirement",
        "comparison": "same_round",
        "condition": {"operator": "share_of_total_gte", "value": 20, "min_entities": 5},
        "minimum_data_quality": "reviewable",
        "severity": "information",
        "entity_type": "country",
        "message_template": _t(
            "{{entity_name}} accounts for {{share_pct}}% of the funding requirement in the selected scope "
            "({{current_value}} of {{scope_total}} {{currency}}).",
            "{{entity_name}} représente {{share_pct}} % du besoin de financement du périmètre sélectionné "
            "({{current_value}} sur {{scope_total}} {{currency}}).",
        ),
        "recommended_follow_up": _t(
            "Consider whether regional or global totals should be read with this concentration in mind.",
            "Tenir compte de cette concentration dans la lecture des totaux régionaux ou mondiaux.",
        ),
        "visibility": "ifrc_internal",
        "owner_team": "FDS",
        "provisional": True,
    },
    "RULE-UNVALIDATED-REQUIREMENT": {
        "id": "RULE-UNVALIDATED-REQUIREMENT",
        "name": _t("Requirement not yet validated"),
        "version": 1,
        "type": "deterministic",
        "enabled": True,
        "metric_id": "funding_requirement",
        "comparison": "same_round",
        "condition": {"operator": "validation_pending_with_data", "value": 0},
        "minimum_data_quality": "reviewable",
        "severity": "information",
        "entity_type": "country",
        "message_template": _t(
            "{{entity_name}}: a funding requirement of {{current_value}} {{currency}} is included but the "
            "submission is {{validation_state}} (status: {{status}}).",
            "{{entity_name}} : un besoin de financement de {{current_value}} {{currency}} est inclus mais la "
            "soumission est {{validation_state}} (statut : {{status}}).",
        ),
        "recommended_follow_up": _t(
            "Treat the figure as provisional until the submission is approved.",
            "Considérer ce chiffre comme provisoire jusqu'à l'approbation de la soumission.",
        ),
        "visibility": "ifrc_internal",
        "owner_team": "FDS",
        "provisional": True,
    },
    "RULE-STALLED-REVIEW": {
        "id": "RULE-STALLED-REVIEW",
        "name": _t("Submission awaiting review", "Soumission en attente d'examen"),
        "version": 1,
        "type": "deterministic",
        "enabled": True,
        "metric_id": "submissions_stalled_days",
        "comparison": "none",
        "condition": {"operator": "stalled_days_gte", "value": 14, "lookback_years": 1},
        "minimum_data_quality": "any",
        "severity": "review",
        "entity_type": "country",
        "message_template": _t(
            "{{entity_name}} ({{current_period}}): submission has been {{status}} for {{days}} days.",
            "{{entity_name}} ({{current_period}}) : la soumission est « {{status}} » depuis {{days}} jours.",
        ),
        "recommended_follow_up": _t(
            "Check who holds the next workflow step and whether validation questions are open.",
            "Vérifier qui détient la prochaine étape du circuit et si des questions de validation restent ouvertes.",
        ),
        "visibility": "ifrc_internal",
        "owner_team": "FDS",
        "provisional": True,
    },
    "RULE-OVERDUE-SUBMISSION": {
        "id": "RULE-OVERDUE-SUBMISSION",
        "name": _t("Submission overdue", "Soumission en retard"),
        "version": 1,
        "type": "deterministic",
        "enabled": True,
        "metric_id": "submissions_overdue_days",
        "comparison": "none",
        "condition": {"operator": "overdue_days_gte", "value": 1, "lookback_years": 1},
        "minimum_data_quality": "any",
        "severity": "important",
        "entity_type": "country",
        "message_template": _t(
            "{{entity_name}} ({{current_period}}): submission is {{days}} days past its due date "
            "(status: {{status}}).",
            "{{entity_name}} ({{current_period}}) : la soumission a {{days}} jours de retard "
            "(statut : {{status}}).",
        ),
        "recommended_follow_up": _t(
            "Contact the country or delegation focal point to confirm the expected submission date.",
            "Contacter le point focal du pays ou de la délégation pour confirmer la date de soumission prévue.",
        ),
        "visibility": "ifrc_internal",
        "owner_team": "FDS",
        "provisional": True,
    },
    "RULE-DATA-UNAVAILABLE": {
        "id": "RULE-DATA-UNAVAILABLE",
        "name": _t("Applicable indicators with data unavailable"),
        "version": 1,
        "type": "deterministic",
        "enabled": True,
        "metric_id": "indicators_data_unavailable",
        "comparison": "same_round",
        "condition": {"operator": "unavailable_count_gte", "value": 1},
        "minimum_data_quality": "reviewable",
        "severity": "review",
        "entity_type": "country",
        "message_template": _t(
            "{{entity_name}} ({{current_period}}): {{count}} applicable indicator value(s) are marked data not available.",
            "{{entity_name}} ({{current_period}}) : {{count}} valeur(s) d'indicateur applicable(s) marquée(s) « donnée non disponible ».",
        ),
        "recommended_follow_up": _t(
            "Confirm whether the data can be provided or the indicator should be marked not applicable.",
            "Confirmer si les données peuvent être fournies ou si l'indicateur doit être marqué non applicable.",
        ),
        "visibility": "ifrc_internal",
        "owner_team": "FDS",
        "provisional": True,
    },
    "RULE-LOW-COVERAGE": {
        "id": "RULE-LOW-COVERAGE",
        "name": _t("Insufficient reporting coverage"),
        "version": 1,
        "type": "deterministic",
        "enabled": True,
        "metric_id": "submission_coverage",
        "comparison": "same_round",
        "condition": {"operator": "coverage_below_pct", "value": 80},
        "minimum_data_quality": "any",
        "severity": "important",
        "entity_type": "scope",
        "message_template": _t(
            "{{current_period}}: {{submitted}} of {{expected}} expected submissions are in "
            "({{coverage_pct}}%), below the {{threshold}}% coverage threshold. Aggregates are incomplete.",
            "{{current_period}} : {{submitted}} soumissions sur {{expected}} attendues sont reçues "
            "({{coverage_pct}} %), sous le seuil de couverture de {{threshold}} %. Les agrégats sont incomplets.",
        ),
        "recommended_follow_up": _t(
            "Caveat any regional or global total derived from this round until coverage improves.",
            "Assortir d'une réserve tout total régional ou mondial dérivé de ce cycle tant que la couverture ne progresse pas.",
        ),
        "visibility": "ifrc_internal",
        "owner_team": "FDS",
        "provisional": True,
    },
}


def default_decisions() -> dict[str, dict[str, Any]]:
    return copy.deepcopy(_DEFAULT_DECISIONS)


def default_rules() -> dict[str, dict[str, Any]]:
    return copy.deepcopy(_DEFAULT_RULES)


class ConfigError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def validate_rule_payload(payload: dict[str, Any], *, known_metrics: set[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["Rule must be an object."]
    condition = payload.get("condition")
    if not isinstance(condition, dict):
        errors.append("condition is required.")
    else:
        if condition.get("operator") not in OPERATORS:
            errors.append(f"condition.operator must be one of: {', '.join(OPERATORS)}.")
        value = condition.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
            errors.append("condition.value must be a number.")
        elif value < 0 or value > 100000:
            errors.append("condition.value is out of range.")
    if payload.get("severity") not in SEVERITIES:
        errors.append(f"severity must be one of: {', '.join(SEVERITIES)}.")
    if payload.get("minimum_data_quality", "any") not in DATA_QUALITY_LEVELS:
        errors.append(f"minimum_data_quality must be one of: {', '.join(DATA_QUALITY_LEVELS)}.")
    if payload.get("metric_id") not in known_metrics:
        errors.append("metric_id is not in the metric registry.")
    if payload.get("entity_type") not in ENTITY_TYPES:
        errors.append(f"entity_type must be one of: {', '.join(ENTITY_TYPES)}.")
    if not isinstance(payload.get("enabled", True), bool):
        errors.append("enabled must be true or false.")
    message = payload.get("message_template")
    if not (isinstance(message, dict) and message.get("en")) and not (isinstance(message, str) and message):
        errors.append("message_template needs at least an English text.")
    return errors


def validate_decision_payload(payload: dict[str, Any], *, known_metrics: set[str], known_rules: set[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["Decision must be an object."]
    if not (isinstance(payload.get("title"), dict) and payload["title"].get("en")):
        errors.append("title needs an English text.")
    if payload.get("status") not in ("active", "paused", "archived", "draft"):
        errors.append("status must be active, paused, archived or draft.")
    if payload.get("visibility") not in VISIBILITY_LEVELS:
        errors.append(f"visibility must be one of: {', '.join(VISIBILITY_LEVELS)}.")
    roles = payload.get("allowed_roles")
    if not isinstance(roles, list) or not roles or not set(roles) <= {"system_manager", "admin", "user"}:
        errors.append("allowed_roles must be a non-empty list of system_manager, admin, user.")
    if not set(payload.get("metric_ids") or []) <= known_metrics:
        errors.append("metric_ids contains an unknown metric.")
    if not set(payload.get("rule_ids") or []) <= known_rules:
        errors.append("rule_ids contains an unknown rule.")
    return errors
