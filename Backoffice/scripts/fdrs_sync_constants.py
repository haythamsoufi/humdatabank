"""
Shared FDRS sync mappings for import_fdrs_form_data.py (template 21).

KPI / document type → form_item_id links that are not resolved via indicator bank.
"""

from typing import Any, Optional

from app.services.data_quality.catalogs.fdrs_v1_catalog import INCOME_SOURCE_KPI_CODES

# IFRC data-availability logical KPI suffixes (API uses mixed casing).
_FDRS_DATA_AVAILABILITY_SUFFIXES = (
    "_IsDataNotAvailable",
    "_isDataNotAvailable",
    "_IsDataNotCollected",
    "_isDataNotCollected",
)


def fdrs_kpi_data_availability_kind(kpi: str) -> Optional[str]:
    """
    Classify FDRS availability KPI suffix.
    Returns ``data_not_available``, ``not_applicable``, or None.
    """
    k = (kpi or "").strip()
    if not k:
        return None
    kl = k.lower()
    if kl.endswith("isdatanotavailable"):
        return "data_not_available"
    if kl.endswith("isdatanotcollected"):
        return "not_applicable"
    return None


def fdrs_kpi_has_data_availability_suffix(kpi: str) -> bool:
    return fdrs_kpi_data_availability_kind(kpi) is not None


def fdrs_kpi_strip_data_availability_suffix(kpi: str) -> str:
    """Remove availability suffix so BaseKPI resolves to the parent indicator KPI."""
    k = (kpi or "").strip()
    if not k:
        return k
    kl = k.lower()
    for pattern in ("_isdatanotavailable", "_isdatanotcollected"):
        if kl.endswith(pattern):
            return k[: len(k) - len(pattern)]
    return k


def fdrs_kpi_availability_value_truthy(val: Any) -> bool:
    """
    Whether an FDRS availability KPI Value means the flag is set.
    Null/empty value with a present row is treated as set (IFRC convention).
    """
    if val is True or (isinstance(val, (int, float)) and val != 0):
        return True
    if val is not None and str(val).strip():
        s = str(val).strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        return False
    return True

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

# ApprovalStatus / Public values treated as importable.
# FDRS ``Public`` codes (observed on GET /api/documents):
#   0 = Validated (Private)
#   1 = Validated (Public)
#   2 = Under Validation (Public)
#   3 = Rejected (Public)
#   4 = Under Validation (Private) — not imported yet (pending-only; separate Public code)
FDRS_DOCUMENT_APPROVAL_OK = frozenset(
    {
        "Validated (Public)",
        "Validated (Private)",
        "Under Validation (Public)",
        "Rejected (Public)",
        "Rejected (Private)",
    }
)
FDRS_DOCUMENT_PUBLIC_OK = frozenset({0, 1, 2, 3})


def fdrs_document_approval_rank(approval_status: str | None) -> int:
    """Higher rank wins dedupe within (iso3, year, document_type)."""
    approval = (approval_status or "").strip()
    if approval == "Validated (Public)":
        return 4
    if approval == "Validated (Private)":
        return 3
    if approval in ("Under Validation (Public)", "Under Validation (Private)"):
        return 2
    if approval.lower().startswith("reject"):
        return 1
    return 0


def fdrs_document_status_from_approval(approval_status: str | None) -> str:
    """Map FDRS ``ApprovalStatus`` to ``SubmittedDocument.status``."""
    approval = (approval_status or "").strip()
    if approval in ("Validated (Public)", "Validated (Private)"):
        return "approved"
    if approval in ("Under Validation (Public)", "Under Validation (Private)"):
        return "pending"
    if approval in ("Rejected (Public)", "Rejected (Private)") or approval.lower().startswith("reject"):
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
