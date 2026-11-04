"""Decision Maker configuration: decisions and rules hardcoded as code defaults.

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
    "pns_unreported_gte",
    "priority_signals_gte",
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


def _rule(
    rule_id: str,
    name: dict[str, str],
    metric_id: str,
    condition: dict[str, Any],
    severity: str,
    message: dict[str, str],
    follow_up: dict[str, str],
    **extra: Any,
) -> dict[str, Any]:
    return {
        "id": rule_id,
        "name": name,
        "version": 1,
        "type": "deterministic",
        "enabled": True,
        "metric_id": metric_id,
        "comparison": "same_round",
        "condition": condition,
        "minimum_data_quality": "reviewable",
        "severity": severity,
        "entity_type": "country",
        "message_template": message,
        "recommended_follow_up": follow_up,
        "visibility": "ifrc_internal",
        "owner_team": "FDS",
        "provisional": True,
        **extra,
    }


_MISSING_OTHER = {"operator": "metric_present_other_missing", "value": 0}

_DEFAULT_RULES.update(
    {
        rule["id"]: rule
        for rule in (
            _rule(
                "RULE-NO-PNS-SUPPORT",
                _t("Requirement with no Participating National Society support recorded"),
                "funding_requirement",
                _MISSING_OTHER,
                "information",
                _t(
                    "{{entity_name}} has a funding requirement of {{current_value}} {{currency}} for {{current_period}} "
                    "but no Participating National Society contribution or bilateral support is recorded.",
                    "{{entity_name}} a un besoin de financement de {{current_value}} {{currency}} pour {{current_period}} "
                    "mais aucune contribution ni aucun appui bilatéral d'une société nationale participante n'est enregistré.",
                ),
                _t(
                    "Check whether PNS support exists but is unrecorded, then consider whether wider Federation support is needed.",
                    "Vérifier si un appui existe mais n'est pas enregistré, puis examiner si un soutien plus large de la Fédération est nécessaire.",
                ),
                other_metric_id="pns_support_count",
            ),
            _rule(
                "RULE-PNS-UNREPORTED",
                _t("PNS contribution based on the host's entry"),
                "funding_requirement",
                {"operator": "pns_unreported_gte", "value": 1},
                "information",
                _t(
                    "{{entity_name}}: {{count}} Participating National Society entry(ies) worth {{current_value}} {{currency}} "
                    "come from the host's plan; the PNS has not submitted its own plan.",
                    "{{entity_name}} : {{count}} entrée(s) de sociétés nationales participantes d'une valeur de "
                    "{{current_value}} {{currency}} proviennent du plan de l'hôte ; la société participante n'a pas soumis son propre plan.",
                ),
                _t(
                    "Treat the PNS share as an estimate until the PNS submits its own plan.",
                    "Considérer la part des SNP comme une estimation jusqu'à la soumission de leur propre plan.",
                ),
            ),
            _rule(
                "RULE-NO-CORE-INDICATORS",
                _t("Requirement with no core or capacity indicators reported"),
                "funding_requirement",
                _MISSING_OTHER,
                "review",
                _t(
                    "{{entity_name}} has a funding requirement of {{current_value}} {{currency}} for {{current_period}} "
                    "but no core or capacity indicator value is reported.",
                    "{{entity_name}} a un besoin de financement de {{current_value}} {{currency}} pour {{current_period}} "
                    "mais aucune valeur d'indicateur de base ou de capacité n'est renseignée.",
                ),
                _t(
                    "Confirm whether the indicators were completed or marked not applicable.",
                    "Confirmer si les indicateurs ont été renseignés ou marqués non applicables.",
                ),
                other_metric_id="core_indicators_reported",
            ),
            _rule(
                "RULE-EMERGENCY-TARGET-NO-FUNDING",
                _t("Emergency people target without emergency funding requirement"),
                "emergency_people_targeted",
                _MISSING_OTHER,
                "review",
                _t(
                    "{{entity_name}} plans to reach {{current_value}} {{currency}} through emergency operations in "
                    "{{current_period}} but states no emergency operations funding requirement.",
                    "{{entity_name}} prévoit d'atteindre {{current_value}} {{currency}} via des opérations d'urgence en "
                    "{{current_period}} mais n'indique aucun besoin de financement pour ces opérations.",
                ),
                _t(
                    "Check whether emergency funding was entered under another column.",
                    "Vérifier si le financement d'urgence a été saisi dans une autre colonne.",
                ),
                other_metric_id="emergency_funding_requirement",
            ),
            _rule(
                "RULE-EMERGENCY-FUNDING-NO-TARGET",
                _t("Emergency funding requirement without people target"),
                "emergency_funding_requirement",
                _MISSING_OTHER,
                "review",
                _t(
                    "{{entity_name}} states an emergency operations requirement of {{current_value}} {{currency}} for "
                    "{{current_period}} but no emergency people-to-be-reached target.",
                    "{{entity_name}} indique un besoin de {{current_value}} {{currency}} pour les opérations d'urgence en "
                    "{{current_period}} mais aucune cible de personnes à atteindre en urgence.",
                ),
                _t(
                    "Check whether emergency targets were entered, marked not applicable, or left out.",
                    "Vérifier si les cibles d'urgence ont été saisies, marquées non applicables ou omises.",
                ),
                other_metric_id="emergency_people_targeted",
            ),
            _rule(
                "RULE-PRIORITY-COUNTRY",
                _t("Country to consider for greater Federation-wide support", "Pays à envisager pour un soutien accru de la Fédération"),
                "funding_requirement",
                {
                    "operator": "priority_signals_gte",
                    "value": 2,
                    "growth_pct": 30,
                    "share_pct": 10,
                    "min_entities": 5,
                    "emergency_share_pct": 25,
                    "max_pns_partners": 1,
                },
                "review",
                _t(
                    "{{entity_name}} shows {{count}} of {{assessed}} signals for {{current_period}}. {{reasons}}",
                    "{{entity_name}} présente {{count}} signaux sur {{assessed}} pour {{current_period}}. {{reasons}}",
                ),
                _t(
                    "Discuss with the National Society and the regional office whether Federation-wide support or attention should be stepped up, and what would be needed.",
                    "Échanger avec la société nationale et le bureau régional sur l'opportunité de renforcer le soutien ou l'attention de la Fédération, et sur les besoins.",
                ),
                reasons={
                    "growth": _t(
                        "Funding requirement up {{percent_change}}% on {{baseline_period}} ({{baseline_value}} to {{current_value}} CHF).",
                        "Besoin de financement en hausse de {{percent_change}} % par rapport à {{baseline_period}} ({{baseline_value}} à {{current_value}} CHF).",
                    ),
                    "share": _t(
                        "Carries {{share_pct}}% of the network's requirement in scope ({{current_value}} of {{scope_total}} CHF).",
                        "Représente {{share_pct}} % du besoin du réseau dans le périmètre ({{current_value}} sur {{scope_total}} CHF).",
                    ),
                    "emergency": _t(
                        "Emergency operations are {{emergency_share_pct}}% of its requirement ({{emergency_value}} of {{current_value}} CHF).",
                        "Les opérations d'urgence représentent {{emergency_share_pct}} % de son besoin ({{emergency_value}} sur {{current_value}} CHF).",
                    ),
                    "support": _t(
                        "Limited partner support: {{partners}} Participating National Society(ies) recorded.",
                        "Appui limité des partenaires : {{partners}} société(s) nationale(s) participante(s) enregistrée(s).",
                    ),
                },
            ),
        )
    }
)


def _decision(
    decision_id: str,
    slug: str,
    title: dict[str, str],
    question: dict[str, str],
    description: dict[str, str],
    audience: list[str],
    dimensions: list[str],
    metric_ids: list[str],
    rule_ids: list[str],
    methodology: str,
) -> dict[str, Any]:
    return {
        "id": decision_id,
        "slug": slug,
        "title": title,
        "question": question,
        "description": description,
        "owner_team": "FDS",
        "status": "active",
        "visibility": "ifrc_internal",
        "allowed_roles": ["system_manager", "admin", "user"],
        "audience": audience,
        "dimensions": dimensions,
        "metric_ids": metric_ids,
        "rule_ids": rule_ids,
        "default_round_kind": "plan",
        "methodology_markdown": methodology,
        "version": 1,
        "effective_from": "2026-11-04",
    }


_DEFAULT_DECISIONS.update(
    {
        d["id"]: d
        for d in (
            _decision(
                "DEC-001",
                "prioritize-countries-for-support",
                {
                    "en": "Prioritise countries and National Societies requiring greater Federation-wide support and attention",
                    "fr": "Prioriser les pays et sociétés nationales nécessitant un soutien et une attention accrus de la Fédération",
                    "es": "Priorizar los países y Sociedades Nacionales que requieren mayor apoyo y atención de la Federación",
                    "ar": "تحديد أولويات البلدان والجمعيات الوطنية التي تحتاج إلى دعم واهتمام أكبر من الاتحاد الدولي",
                },
                {
                    "en": "Which countries should leadership consider prioritising for greater Federation-wide support, and why?",
                    "fr": "Quels pays la direction devrait-elle envisager de prioriser pour un soutien accru de la Fédération, et pourquoi ?",
                    "es": "¿Qué países debería considerar priorizar la dirección para un mayor apoyo de la Federación, y por qué?",
                    "ar": "ما البلدان التي ينبغي للقيادة النظر في إعطائها الأولوية لدعم أكبر من الاتحاد الدولي، ولماذا؟",
                },
                {
                    "en": (
                        "A shortlist of countries that meet at least two published signals in the latest plan round: a fast-growing "
                        "requirement, a large share of the network's requirement, a heavy emergency load, or limited partner "
                        "support. Each country is listed with its reasons."
                    ),
                    "fr": (
                        "Une liste restreinte de pays qui répondent à au moins deux signaux publiés dans le dernier cycle de "
                        "planification : besoin en forte hausse, part importante du besoin du réseau, forte charge d'urgence ou "
                        "appui limité des partenaires. Chaque pays est présenté avec ses raisons."
                    ),
                },
                ["IFRC leadership", "Regional PMER/QA", "FDS"],
                ["round", "region", "country", "validation_state"],
                [
                    "funding_requirement",
                    "people_targeted",
                    "emergency_funding_requirement",
                    "pns_support_count",
                ],
                ["RULE-PRIORITY-COUNTRY"],
                (
                    "**What this shows.** A shortlist of countries that meet at least two of four published signals in the "
                    "latest plan round, each with its reasons in plain terms. It is a basis for leadership discussion, "
                    "not a decision.\n\n"
                    "**The four signals.** Funding requirement up 30% or more on the previous round. A large share (10% or more) "
                    "of the network's total requirement. Emergency operations making up 25% or more of the country's "
                    "requirement. Limited partner support: one or no Participating National Society recorded.\n\n"
                    "**How the list is ordered.** By the number of signals met, then by size of requirement. No weighted "
                    "score is calculated, so every reason can be read and challenged. Countries meeting three or more "
                    "signals are marked Important.\n\n"
                    "**Read with care.** Countries without a usable plan are not assessed, which does not mean they need less "
                    "support. Check data coverage before using the list. Draft submissions are excluded.\n\n"
                    "**Not covered yet.** Crisis severity, hazard exposure, income, capacity assessments and live operational "
                    "data (GO, ERP) are not in the Databank. The signals reflect what National Societies planned, so they show "
                    "where requirements and support are concentrated, not who is most in need. Confirm with regional "
                    "offices before acting.\n\n"
                    "**Provisional.** Thresholds are examples pending FDS approval."
                ),
            ),
            _decision(
                "DEC-003",
                "global-footprint-capacity-reach-resources",
                {
                    "en": "Understand the global footprint, capacity, reach and resources of the IFRC network",
                    "fr": "Comprendre l'empreinte mondiale, la capacité, la portée et les ressources du réseau de la FICR",
                    "es": "Comprender la huella global, la capacidad, el alcance y los recursos de la red de la FICR",
                    "ar": "فهم البصمة العالمية وقدرات شبكة الاتحاد الدولي ونطاق وصولها وموارده",
                },
                {
                    "en": "What is the footprint, capacity, reach and resource base of the network, and how complete is the evidence?",
                    "fr": "Quelle est l'empreinte, la capacité, la portée et la base de ressources du réseau, et dans quelle mesure les données sont-elles complètes ?",
                    "es": "¿Cuál es la huella, la capacidad, el alcance y la base de recursos de la red, y cuán completa es la evidencia?",
                    "ar": "ما بصمة الشبكة وقدراتها ونطاق وصولها وقاعدة مواردها، وما مدى اكتمال الأدلة؟",
                },
                {
                    "en": (
                        "Countries covered, funding requirements, people to be reached, Participating National Society "
                        "support and core and capacity indicators, with the completeness of each."
                    ),
                    "fr": (
                        "Pays couverts, besoins de financement, personnes à atteindre, appui des sociétés participantes "
                        "et indicateurs de base et de capacité, avec le degré de complétude de chacun."
                    ),
                },
                ["IFRC leadership", "FDS", "Regional PMER/QA"],
                ["round", "region", "country", "funding_source", "validation_state"],
                [
                    "funding_requirement",
                    "people_targeted",
                    "pns_support_count",
                    "core_indicators_reported",
                    "submission_coverage",
                ],
                [
                    "RULE-LOW-COVERAGE",
                    "RULE-UNVALIDATED-REQUIREMENT",
                    "RULE-NO-CORE-INDICATORS",
                    "RULE-CONCENTRATION",
                ],
                (
                    "**Evidence.** Footprint is the set of countries with a Unified Plan submission in scope. Resources are "
                    "stated funding requirements, not income or expenditure. Capacity is the number of core and National "
                    "Society capacity indicators with a reported value.\n\n"
                    "**Read with coverage.** Totals only cover submissions received. Check coverage and the validation "
                    "mix before quoting a network-wide figure.\n\n"
                    "**Not covered yet.** Membership, volunteers, staff and branch counts are not part of the Unified Plan "
                    "extract. Income and expenditure are not read from Unified Reports.\n\n"
                    "**Provisional.** Thresholds are examples pending FDS approval."
                ),
            ),
            _decision(
                "DEC-005",
                "emergencies-and-global-initiatives",
                {
                    "en": "Inform Federation-wide planning, monitoring and reporting for major emergencies and global initiatives",
                    "fr": "Éclairer la planification, le suivi et le rapportage à l'échelle de la Fédération pour les grandes urgences et initiatives mondiales",
                    "es": "Orientar la planificación, el seguimiento y la presentación de informes de la Federación sobre grandes emergencias e iniciativas globales",
                    "ar": "دعم التخطيط والرصد والإبلاغ على مستوى الاتحاد الدولي بشأن حالات الطوارئ الكبرى والمبادرات العالمية",
                },
                {
                    "en": "What do plans say about emergency operations, and are their targets and funding requirements complete and consistent?",
                    "fr": "Que disent les plans sur les opérations d'urgence, et leurs cibles et besoins de financement sont-ils complets et cohérents ?",
                    "es": "¿Qué dicen los planes sobre las operaciones de emergencia y son completas y coherentes sus metas y necesidades de financiación?",
                    "ar": "ماذا تقول الخطط عن عمليات الطوارئ، وهل أهدافها ومتطلبات تمويلها مكتملة ومتسقة؟",
                },
                {
                    "en": (
                        "Emergency operations funding requirements and people to be reached from Unified Plans, by "
                        "country and region, with checks that each is matched by the other."
                    ),
                    "fr": (
                        "Besoins de financement et personnes à atteindre des opérations d'urgence issus des plans unifiés, "
                        "par pays et région, avec vérification de leur correspondance."
                    ),
                },
                ["IFRC leadership", "Emergency operations", "FDS", "Regional PMER/QA"],
                ["round", "region", "country", "funding_source", "validation_state"],
                [
                    "emergency_funding_requirement",
                    "emergency_people_targeted",
                    "funding_requirement",
                    "submission_coverage",
                ],
                [
                    "RULE-EMERGENCY-TARGET-NO-FUNDING",
                    "RULE-EMERGENCY-FUNDING-NO-TARGET",
                    "RULE-LOW-COVERAGE",
                ],
                (
                    "**Evidence.** Emergency funding is the Emergency Operations column of the Unified Plan funding matrix. "
                    "People to be reached come from the plan's emergency matrix, using the largest figure per operation.\n\n"
                    "**Not covered yet.** Live emergency appeals, operational reporting, DREF and global initiative "
                    "progress come from GO and ERP, which are not integrated. This view reflects what National Societies "
                    "planned, not what is happening on the ground.\n\n"
                    "**Provisional.** Thresholds and the people-to-be-reached mapping are pending FDS confirmation."
                ),
            ),
            _decision(
                "DEC-006",
                "host-partner-secretariat-contribution",
                {
                    "en": "Understand the collective contribution of Host National Societies, Partner National Societies and the IFRC Secretariat",
                    "fr": "Comprendre la contribution collective des sociétés nationales hôtes, des sociétés nationales partenaires et du Secrétariat de la FICR",
                    "es": "Comprender la contribución colectiva de las Sociedades Nacionales anfitrionas, las Sociedades Nacionales asociadas y la Secretaría de la FICR",
                    "ar": "فهم المساهمة الجماعية للجمعيات الوطنية المضيفة والجمعيات الوطنية الشريكة وأمانة الاتحاد الدولي",
                },
                {
                    "en": "How is the funding requirement shared between host National Societies, Participating National Societies and the Secretariat, and how reliable is each share?",
                    "fr": "Comment le besoin de financement est-il réparti entre sociétés nationales hôtes, sociétés participantes et Secrétariat, et quelle est la fiabilité de chaque part ?",
                    "es": "¿Cómo se reparte la necesidad de financiación entre las Sociedades Nacionales anfitrionas, las participantes y la Secretaría, y cuán fiable es cada parte?",
                    "ar": "كيف يتوزع الاحتياج التمويلي بين الجمعيات الوطنية المضيفة والجمعيات المشاركة والأمانة، ومدى موثوقية كل حصة؟",
                },
                {
                    "en": (
                        "Funding requirement by funding source (host National Society, Participating National Societies, "
                        "IFRC Secretariat) and by Strategic Priority, with how many PNS support each country and whether "
                        "the PNS entered their own figures."
                    ),
                    "fr": (
                        "Besoin de financement par source (société hôte, sociétés participantes, Secrétariat de la FICR) "
                        "et par priorité stratégique, avec le nombre de sociétés participantes par pays et l'origine des chiffres."
                    ),
                },
                ["IFRC leadership", "FDS", "Authorized PNS users"],
                ["round", "region", "country", "funding_source", "strategic_priority", "validation_state"],
                [
                    "funding_requirement",
                    "funding_requirement_by_priority",
                    "pns_support_count",
                    "emergency_funding_requirement",
                ],
                [
                    "RULE-PNS-UNREPORTED",
                    "RULE-NO-PNS-SUPPORT",
                    "RULE-UNVALIDATED-REQUIREMENT",
                ],
                (
                    "**Evidence.** Each funding source is read from the Unified Plan funding matrix. Where a Participating "
                    "National Society has submitted its own plan, its figure replaces the host's entry for that PNS.\n\n"
                    "**Reliability.** A PNS figure that comes only from the host's plan is an estimate and is flagged. "
                    "Requirements are plans, not confirmed income, so this view shows who plans to contribute, not who gave.\n\n"
                    "**Not covered yet.** Actual contributions, in-kind support and non-financial contributions "
                    "need approved sources before they can be compared with plans.\n\n"
                    "**Provisional.** Thresholds are examples pending FDS approval."
                ),
            ),
            _decision(
                "DEC-007",
                "accountability-and-strategic-dialogue",
                {
                    "en": "Support accountability and strategic dialogue with consistent Federation-wide evidence",
                    "fr": "Soutenir la redevabilité et le dialogue stratégique grâce à des données cohérentes à l'échelle de la Fédération",
                    "es": "Apoyar la rendición de cuentas y el diálogo estratégico con evidencia coherente de toda la Federación",
                    "ar": "دعم المساءلة والحوار الاستراتيجي بأدلة متسقة على مستوى الاتحاد الدولي",
                },
                {
                    "en": "Is the evidence complete, validated and consistent enough to use with National Societies, leadership and governance?",
                    "fr": "Les données sont-elles suffisamment complètes, validées et cohérentes pour être utilisées avec les sociétés nationales, la direction et la gouvernance ?",
                    "es": "¿Es la evidencia lo bastante completa, validada y coherente para usarla con las Sociedades Nacionales, la dirección y la gobernanza?",
                    "ar": "هل الأدلة مكتملة ومصدّق عليها ومتسقة بما يكفي لاستخدامها مع الجمعيات الوطنية والقيادة والحوكمة؟",
                },
                {
                    "en": (
                        "Readiness of the evidence base: reporting coverage, validation status, overdue and stalled "
                        "submissions, indicators without data and large unexplained changes."
                    ),
                    "fr": (
                        "Niveau de préparation des données : couverture, état de validation, soumissions en retard ou "
                        "bloquées, indicateurs sans données et fortes variations non expliquées."
                    ),
                },
                ["IFRC leadership", "Governance support", "FDS", "Regional PMER/QA"],
                ["round", "region", "country", "validation_state"],
                [
                    "submission_coverage",
                    "funding_requirement",
                    "submissions_overdue_days",
                    "submissions_stalled_days",
                    "indicators_data_unavailable",
                ],
                [
                    "RULE-LOW-COVERAGE",
                    "RULE-UNVALIDATED-REQUIREMENT",
                    "RULE-OVERDUE-SUBMISSION",
                    "RULE-STALLED-REVIEW",
                    "RULE-DATA-UNAVAILABLE",
                    "RULE-YOY-CHANGE",
                ],
                (
                    "**Purpose.** Before a figure is used in a dialogue with a National Society or in a governance paper, "
                    "this view shows whether it is complete, validated and comparable, and keeps the exact evidence behind it.\n\n"
                    "**Evidence.** Assignment status and dates, validation state and the indicator availability flags of Unified "
                    "Plans and Reports. Every figure links to its evidence record.\n\n"
                    "**Not covered yet.** Accountability commitments, decisions taken and follow-up actions are not "
                    "tracked here. Use the notes on each flag for informal follow-up.\n\n"
                    "**Provisional.** Thresholds are examples pending FDS approval."
                ),
            ),
            _decision(
                "DEC-008",
                "cross-cutting-strategic-questions",
                {
                    "en": "Answer cross-cutting strategic questions with comparable data from across the IFRC network",
                    "fr": "Répondre aux questions stratégiques transversales avec des données comparables de tout le réseau de la FICR",
                    "es": "Responder preguntas estratégicas transversales con datos comparables de toda la red de la FICR",
                    "ar": "الإجابة عن الأسئلة الاستراتيجية الشاملة ببيانات قابلة للمقارنة من مختلف أنحاء شبكة الاتحاد الدولي",
                },
                {
                    "en": "What do comparable plan data show across countries, regions, rounds and funding sources?",
                    "fr": "Que montrent les données de plan comparables entre pays, régions, cycles et sources de financement ?",
                    "es": "¿Qué muestran los datos comparables de los planes entre países, regiones, rondas y fuentes de financiación?",
                    "ar": "ماذا تُظهر بيانات الخطط القابلة للمقارنة عبر البلدان والأقاليم والدورات ومصادر التمويل؟",
                },
                {
                    "en": (
                        "One place to compare funding, reach, emergency, support and capacity data from Unified Plans "
                        "across any combination of country, region, round, funding source and Strategic Priority."
                    ),
                    "fr": (
                        "Un point d'accès pour comparer financement, portée, urgence, appui et capacité issus des plans "
                        "unifiés selon pays, région, cycle, source de financement et priorité stratégique."
                    ),
                },
                ["IFRC leadership", "FDS", "Regional PMER/QA", "Authorized PNS users"],
                ["year", "round", "region", "country", "funding_source", "strategic_priority", "validation_state"],
                [
                    "funding_requirement",
                    "funding_requirement_by_priority",
                    "people_targeted",
                    "emergency_funding_requirement",
                    "emergency_people_targeted",
                    "pns_support_count",
                    "core_indicators_reported",
                    "submission_coverage",
                ],
                [
                    "RULE-YOY-CHANGE",
                    "RULE-MISSING-TARGET",
                    "RULE-CONCENTRATION",
                    "RULE-LOW-COVERAGE",
                ],
                (
                    "**How to use.** Pick the metric and the dimensions you want to compare. The assistant can run the same "
                    "grouped queries (for example funding by Strategic Priority and region) and cite the evidence.\n\n"
                    "**Comparable by design.** Every metric has one registered definition, unit, source precedence and set "
                    "of valid dimensions, so the same number is used in the page, exports and the assistant.\n\n"
                    "**Not covered yet.** Questions that need data outside Unified Plans and Reports (GO, ERP, FDRS) cannot "
                    "be answered here until those sources are integrated.\n\n"
                    "**Provisional.** Thresholds are examples pending FDS approval."
                ),
            ),
        )
    }
)


def default_decisions() -> dict[str, dict[str, Any]]:
    return copy.deepcopy(dict(sorted(_DEFAULT_DECISIONS.items())))


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
