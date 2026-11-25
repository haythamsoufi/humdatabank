"""Identifiers, GO sectors, and default settings for DREF monitoring."""

from __future__ import annotations

PLUGIN_ID = "dref_monitoring"
VERSION = "0.13.0"
DISPLAY_NAME = "DREF Monitoring"

TEMPLATE_NAME = "DREF operational monitoring"
FIELD_TYPE = "dref_operational_report"
PORTFOLIO = "DREF"

MANAGE_PERMISSION = "admin.dref_monitoring.manage"
ENTER_PERMISSION = "admin.dref_monitoring.enter"
VALIDATE_PERMISSION = "admin.dref_monitoring.validate"
REVIEW_PERMISSION = "admin.dref_monitoring.review"
PORTFOLIO_PERMISSION = "admin.dref_monitoring.portfolio"
EXPLORE_PERMISSION = "admin.data_explore.dref_monitoring"

MANAGE_ROLE = "admin_dref_monitoring"
ENTER_ROLE = "dref_monitoring_entry"
VALIDATE_ROLE = "dref_monitoring_validation"
REVIEW_ROLE = "dref_monitoring_review"
PORTFOLIO_ROLE = "dref_monitoring_portfolio"

EXPLORE_TAB_ID = "dref-monitoring"

GO_DREF3_URL = "https://goadmin.ifrc.org/api/v2/dref3/"
# Emergency Appeals are not in dref3 as operations. GO keeps them as appeals (``atype`` 1).
GO_APPEAL_URL = "https://goadmin.ifrc.org/api/v2/appeal/"
GO_APPEAL_TYPE_EA = 1
# Stage name and id prefix of an Emergency Appeal read from the appeal API (dref3 stage ids start with ``Dref``).
APPEAL_STAGE = "Emergency Appeal"
APPEAL_STAGE_PREFIX = "Appeal-"
EA_DEFAULT_SINCE_YEAR = 2025
PROMPT_VERSION = "6"
REPORT_LANGUAGES = ("en", "fr", "es", "ar")
# How a generated report treats narrative: figures only, chapters the National Society writes, or chapters the model drafts.
NARRATIVE_NONE = "none"
NARRATIVE_MANUAL = "manual"
NARRATIVE_AI = "ai"
NARRATIVE_MODES = (NARRATIVE_NONE, NARRATIVE_MANUAL, NARRATIVE_AI)
LANGUAGE_NAMES = {"en": "English", "fr": "French", "es": "Spanish", "ar": "Arabic"}
SECTION_KEYS = (
    "what_happened",
    "scope_and_scale",
    "summary_of_changes",
    "ifrc_actions",
    "icrc_actions",
    "other_actors",
    "needs",
    "overall_objective",
    "strategy_rationale",
    "who_targeted",
    "selection_criteria",
    "achievements",
    "challenges",
)
SECTION_LABELS = {
    "what_happened": "What happened, where and when?",
    "scope_and_scale": "Scope and scale",
    "summary_of_changes": "Summary of changes",
    "ifrc_actions": "IFRC network actions related to the current event",
    "icrc_actions": "ICRC actions related to the current event",
    "other_actors": "Other actors actions related to the current event",
    "needs": "Needs (gaps) identified",
    "overall_objective": "Overall objective of the operation",
    "strategy_rationale": "Operation strategy rationale",
    "who_targeted": "Who was targeted",
    "selection_criteria": "Explain the selection criteria for the targeted population",
    "achievements": "Progress and achievements",
    "challenges": "Challenges",
}
DRAFT_OPEN = "draft"
DRAFT_VALIDATED = "validated"
DRAFT_SUBMITTED = "submitted"
GO_API_ROOT = "https://goadmin.ifrc.org/api/v2/"

SIGN_OFF_NS = "ns"
SIGN_OFF_DELEGATION = "delegation"

FREQ_BIWEEKLY = "biweekly"
FREQ_MONTHLY = "monthly"

WORKFLOW_STUB = "stub"
WORKFLOW_PLAN_DRAFT = "plan_draft"
WORKFLOW_MONITORING = "monitoring"
WORKFLOW_CLOSURE = "closure"

PLAN_DRAFT = "draft"
PLAN_VALIDATED = "validated"

REPORT_DRAFT = "draft"
REPORT_SUBMITTED = "submitted"
REPORT_VALIDATED = "validated"
REPORT_REVIEWED = "reviewed"

ACTIVITY_PLANNED = "planned"
ACTIVITY_ONGOING = "ongoing"
ACTIVITY_COMPLETED = "completed"
ACTIVITY_BLOCKED = "blocked"
ACTIVITY_DELAYED = "delayed"

ACTIVITY_TYPES: tuple[tuple[str, str], ...] = (
    ("preparedness_design", "Preparedness & Design"),
    ("procurement", "Procurement & Logistics"),
    ("direct_delivery", "Direct Delivery"),
    ("community_engagement_training", "Community Engagement & Training"),
    ("quality_review", "Quality & Review"),
)

CARRIED_OUT_BY: tuple[tuple[str, str], ...] = (
    ("national_society", "Host National Society"),
    ("ifrc", "IFRC"),
)

CHANGE_PENDING = "pending"
CHANGE_APPROVED = "approved"
CHANGE_REJECTED = "rejected"

# GO dref3 sector suffixes. Labels match the public data dictionary.
SECTORS: tuple[tuple[str, str], ...] = (
    ("shelter_and_basic_household_items", "Shelter and basic household items"),
    ("livelihoods", "Livelihoods"),
    ("multi_purpose_cash_grants", "Multi-purpose cash grants"),
    ("health", "Health"),
    ("water_sanitation_and_hygiene", "Water, sanitation and hygiene"),
    ("protection_gender_and_inclusion", "Protection, gender and inclusion"),
    ("education", "Education"),
    ("migration_and_displacement", "Migration and displacement"),
    ("risk_reduction_climate_adaptation_and_recovery", "Risk reduction, climate adaptation and recovery"),
    ("community_engagement_and_accountability", "Community engagement and accountability"),
    ("environmental_sustainability", "Environmental sustainability"),
    ("coordination_and_partnerships", "Coordination and partnerships"),
    ("secretariat_services", "Secretariat services"),
    ("national_society_strengthening", "National Society strengthening"),
)

SECTOR_LABELS = dict(SECTORS)

PROCUREMENT_MILESTONES = (
    "not_started",
    "requested",
    "ordered",
    "received",
    "distributed",
)

RISK_LEVELS = ("low", "medium", "high")
RISK_STATUSES = ("open", "mitigated", "closed")

DEFAULT_CONFIG = {
    "go": {"base_url": GO_DREF3_URL, "appeal_url": GO_APPEAL_URL},
    # Active Emergency Appeals are always read. Closed ones from this year on are read too.
    "emergency_appeals": {"enabled": True, "closed_since_year": EA_DEFAULT_SINCE_YEAR},
    "schedule": {
        "plan_validation_days": 14,
        "reminder_days_before": 3,
        "escalation_validate_days": 3,
        "escalation_review_days": 7,
        "escalation_portfolio_days": 14,
    },
    "ai": {
        "enabled": False,
        "prompt_version": PROMPT_VERSION,
        "language": "en",
        "model": "",
        "final_report_model": "",
    },
}
