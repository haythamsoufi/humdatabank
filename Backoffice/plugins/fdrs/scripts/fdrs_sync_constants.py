"""
Shared FDRS sync mappings for import_fdrs_form_data.py (template 21).

KPI / document type → form_item_id links that are not resolved via indicator bank.
"""


from form_row_upsert import ImportRowsCancelled as FdrsSyncCancelled  # noqa: E402


from typing import Any, Optional

from plugins.fdrs.data_quality.fdrs_v1_catalog import INCOME_SOURCE_KPI_CODES

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
#   4 = Under Validation (Private)
FDRS_DOCUMENT_APPROVAL_OK = frozenset(
    {
        "Validated (Public)",
        "Validated (Private)",
        "Under Validation (Public)",
        "Under Validation (Private)",
        "Rejected (Public)",
        "Rejected (Private)",
    }
)
FDRS_DOCUMENT_PUBLIC_OK = frozenset({0, 1, 2, 3, 4})

# FDRS ``Public`` codes where the file may be fetched from ``url`` (metadata import still
# includes private codes in FDRS_DOCUMENT_PUBLIC_OK above).
FDRS_DOCUMENT_DOWNLOAD_PUBLIC_CODES = frozenset({1, 2, 3})


# Public integer → SubmittedDocument.status. Used when ApprovalStatus text is missing.
FDRS_PUBLIC_CODE_STATUS = {
    0: "approved",  # Validated (Private)
    1: "approved",  # Validated (Public)
    2: "pending",  # Under Validation (Public)
    3: "rejected",  # Rejected (Public)
    4: "pending",  # Under Validation (Private)
}


def fdrs_clean_approval_text(raw: Any) -> str:
    """ApprovalStatus label. Numeric codes are not labels; those live on ``Public``."""
    if raw is None or isinstance(raw, bool):
        return ""
    if isinstance(raw, (int, float)):
        return ""
    return " ".join(str(raw).split())


def fdrs_public_code(raw: Any) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _status_from_approval_text(text: str) -> str | None:
    key = (text or "").casefold()
    if not key:
        return None
    if key in ("validated (public)", "validated (private)", "validated", "approved"):
        return "approved"
    if key.startswith("validat") or key.startswith("approv"):
        return "approved"
    if "under validation" in key or key == "pending":
        return "pending"
    if key.startswith("reject"):
        return "rejected"
    return None


def _approval_code(approval_status: Any, public_code: Any) -> int | None:
    code = fdrs_public_code(public_code)
    if code is None and isinstance(approval_status, (int, float)) and not isinstance(approval_status, bool):
        return int(approval_status)
    return code


def fdrs_document_is_public_visibility(
    approval_status: str | None = None,
    *,
    public_code: Any = None,
) -> bool:
    """
    Whether FDRS document bytes may be downloaded from ``url``.

    Private (Validated Private, Public code 0) → metadata only, no file fetch.
    Public codes 1–3 or ApprovalStatus ending in ``(Public)`` → fetch allowed.
    """
    approval = fdrs_clean_approval_text(approval_status)
    if approval.endswith("(Private)"):
        return False
    if approval.endswith("(Public)"):
        return True
    code = _approval_code(approval_status, public_code)
    if code is not None:
        if code == 0:
            return False
        if code in FDRS_DOCUMENT_DOWNLOAD_PUBLIC_CODES:
            return True
    return False


def fdrs_document_approval_rank(approval_status: str | None = None, *, public_code: Any = None) -> int:
    """Higher rank wins dedupe within (iso3, year, document_type)."""
    approval = fdrs_clean_approval_text(approval_status)
    if approval == "Validated (Public)":
        return 4
    if approval == "Validated (Private)":
        return 3
    if approval in ("Under Validation (Public)", "Under Validation (Private)"):
        return 2
    if approval.lower().startswith("reject"):
        return 1
    mapped = _status_from_approval_text(approval)
    if mapped == "approved" and approval.casefold().endswith("(private)"):
        return 3
    if mapped == "approved":
        return 4
    if mapped == "pending":
        return 2
    if mapped == "rejected":
        return 1
    code = _approval_code(approval_status, public_code)
    return {1: 4, 0: 3, 2: 2, 4: 2, 3: 1}.get(code if code is not None else -1, 0)


def fdrs_document_status_from_approval(
    approval_status: str | None = None,
    *,
    public_code: Any = None,
) -> str:
    """Map FDRS ``ApprovalStatus`` / ``Public`` to ``SubmittedDocument.status``.

    The label wins when it is recognized. Otherwise the ``Public`` code is used
    (0/1 approved, 2/4 pending, 3 rejected). Missing both stays pending.
    """
    mapped = _status_from_approval_text(fdrs_clean_approval_text(approval_status))
    if mapped is not None:
        return mapped
    code = _approval_code(approval_status, public_code)
    if code in FDRS_PUBLIC_CODE_STATUS:
        return FDRS_PUBLIC_CODE_STATUS[code]
    return "pending"


def fdrs_approval_is_importable(approval_status: Any = None, public_code: Any = None) -> bool:
    """False only when a status was sent and neither the label nor the Public code is known."""
    text = fdrs_clean_approval_text(approval_status)
    if _status_from_approval_text(text) is not None:
        return True
    code = _approval_code(approval_status, public_code)
    if code in FDRS_DOCUMENT_PUBLIC_OK:
        return True
    if not text and code is None:
        return True
    return False


# Network Support matrices (template 21)
FDRS_NETWORK_SUPPORT_GIVEN_ITEM_ID = 919
FDRS_NETWORK_SUPPORT_GIVEN_COLUMN = "Funding provided"
FDRS_NETWORK_SUPPORT_RECEIVED_ITEM_ID = 929
FDRS_NETWORK_SUPPORT_RECEIVED_COLUMN = "Funding Received"
FDRS_NETWORK_SUPPORT_SLOT_COUNT = 10

# Slot N: {prefix}{N} = DonCode CSV, {prefix}{N}_amount = amount CSV
FDRS_NETWORK_SUPPORT_GIVEN_CODE_PREFIX = "supported"
FDRS_NETWORK_SUPPORT_RECEIVED_CODE_PREFIX = "received_support"

# FDRS section workflow KPIs. ``page_name`` is the published template 21 form page
# (match by name; page ids differ per database). Today the importer still rolls
# these flags up to assignment_entity_status. Once every FDRS assignment has
# enable_page_submission, each prefix should be written to assignment_page_status
# for that page. See docs/runbooks/fdrs-page-submission.md.
FDRS_SECTION_WORKFLOW_SPECS = (
    {"prefix": "KPI_NSGS", "label": "Governance", "page_name": "NS Governance & Structure"},
    {"prefix": "KPI_NSFP", "label": "Finance", "page_name": "NS Finance & Partnerships"},
    {"prefix": "KPI_NSR", "label": "Reach", "page_name": "NS Reach"},
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
