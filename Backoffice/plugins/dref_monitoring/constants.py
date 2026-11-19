"""Identifiers, GO sectors, and default settings for DREF monitoring."""

from __future__ import annotations

PLUGIN_ID = "dref_monitoring"
VERSION = "0.2.0"
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
PROMPT_VERSION = "1"

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
    "go": {"base_url": GO_DREF3_URL},
    "schedule": {
        "plan_validation_days": 14,
        "reminder_days_before": 3,
        "escalation_validate_days": 3,
        "escalation_review_days": 7,
        "escalation_portfolio_days": 14,
    },
    "ai": {"enabled": False, "prompt_version": PROMPT_VERSION},
}
