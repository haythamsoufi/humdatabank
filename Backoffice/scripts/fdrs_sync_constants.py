"""
Shared FDRS sync mappings for import_fdrs_form_data.py (template 21).

KPI / document type → form_item_id links that are not resolved via indicator bank.
"""

from app.services.data_quality.catalogs.fdrs_v1_catalog import INCOME_SOURCE_KPI_CODES

# Template 21 form items (published)
FDRS_INCOME_SOURCES_MATRIX_ITEM_ID = 943
FDRS_INCOME_SOURCES_MATRIX_COLUMN = "Funding"

# Question KPIs → form_item_id (no indicator bank row)
FDRS_QUESTION_KPI_TO_ITEM = {
    "KPI_pr_sex": 924,
    "KPI_sg_sex": 934,
    "KPI_CUR_Code": 918,
    "KPI_StartDate": 928,
    "KPI_EndDate": 937,
}

# FDRS income-source KPI (BaseKPI) → Income Sources matrix row label (item 943)
FDRS_INCOME_KPI_TO_MATRIX_ROW = {
    "h_gov_CHF": "Home Government",
    "f_gov_CHF": "Foreign Government",
    "ind_CHF": "Individuals",
    "corp_CHF": "Corporations",
    "found_CHF": "Foundations",
    "un_CHF": "UN Agencies & other Multilateral Agencies",
    "pooled_f_CHF": "Pooled funds",
    "ngo_CHF": "Non-governmental organizations",
    "si_CHF": "Service income",
    "iga_CHF": "Income generating activity",
    "KPI_incomeFromNSsLC_CHF": "Other National Society",
    "ifrc_CHF": "IFRC",
    "icrc_CHF": "ICRC",
    "other_CHF": "Other",
}

# Keep in sync with fdrs_v1_catalog.INCOME_SOURCE_KPI_CODES
assert set(FDRS_INCOME_KPI_TO_MATRIX_ROW) == set(INCOME_SOURCE_KPI_CODES)

# FDRS documents API document_type → template document_field item_id
FDRS_DOCUMENT_TYPE_TO_ITEM = {
    "Our Annual Report": 923,
    "Our Audited Financial Statements": 933,
    "Our Strategic Plan": 1309,
    "Our Unaudited Financial Statement": 1310,
}

# Map to form item config document_type string
FDRS_DOCUMENT_TYPE_TO_CONFIG_LABEL = {
    "Our Annual Report": "Annual Report",
    "Our Audited Financial Statements": "Audited Financial Statement",
    "Our Strategic Plan": "Strategic Plan",
    "Our Unaudited Financial Statement": "Unaudited Financial Statement",
}

# ApprovalStatus / Public values treated as importable (metadata-only until file URLs work)
FDRS_DOCUMENT_APPROVAL_OK = frozenset(
    {
        "Validated (Public)",
        "Validated (Private)",
        "Under Validation (Public)",
    }
)
FDRS_DOCUMENT_PUBLIC_OK = frozenset({0, 1, 2})


def fdrs_document_status_from_approval(approval_status: str | None) -> str:
    """Map FDRS ``ApprovalStatus`` to ``SubmittedDocument.status``."""
    approval = (approval_status or "").strip()
    if approval in ("Validated (Public)", "Validated (Private)"):
        return "approved"
    if approval in ("Under Validation (Public)", "Under Validation (Private)"):
        return "pending"
    if approval.lower().startswith("reject"):
        return "rejected"
    return "pending"


# Network Support matrices (template 21)
FDRS_NETWORK_SUPPORT_GIVEN_ITEM_ID = 919
FDRS_NETWORK_SUPPORT_GIVEN_COLUMN = "Funding provided"
FDRS_NETWORK_SUPPORT_RECEIVED_ITEM_ID = 929
FDRS_NETWORK_SUPPORT_RECEIVED_COLUMN = "Funding Received"
FDRS_NETWORK_SUPPORT_SLOT_COUNT = 10

# Slot N: {prefix}{N} = DonCode CSV, {prefix}{N}_amount = amount CSV
FDRS_NETWORK_SUPPORT_GIVEN_CODE_PREFIX = "supported"
FDRS_NETWORK_SUPPORT_RECEIVED_CODE_PREFIX = "received_support"

# FDRS section workflow KPIs (Governance, Finance, Reach) → assignment_entity_status
FDRS_SECTION_WORKFLOW_SPECS = (
    {"prefix": "KPI_NSGS", "label": "Governance"},
    {"prefix": "KPI_NSFP", "label": "Finance"},
    {"prefix": "KPI_NSR", "label": "Reach"},
)

FDRS_SECTION_WORKFLOW_SUFFIXES = (
    "WasStarted",
    "WasSubmitted",
    "WasValidated",
    "WasPublished",
    "ValidationDate",
    "PublishDate",
)


def fdrs_section_workflow_kpi_codes() -> tuple[str, ...]:
    codes: list[str] = []
    for spec in FDRS_SECTION_WORKFLOW_SPECS:
        prefix = spec["prefix"]
        for suffix in FDRS_SECTION_WORKFLOW_SUFFIXES:
            codes.append(f"{prefix}_{suffix}")
    return tuple(codes)
