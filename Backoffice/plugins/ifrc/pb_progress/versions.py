"""P&B report version definitions (separate Excel + output packages per version)."""

from __future__ import annotations

from typing import TypedDict


class ReportVersion(TypedDict):
    id: str
    label: str
    report_year: str
    description: str
    related_program_tag: str


REPORT_VERSIONS: dict[str, ReportVersion] = {
    "2025-2026": {
        "id": "2025-2026",
        "label": "P&B 2025-2026",
        "report_year": "2026",
        "description": "",
        "related_program_tag": "PB25-26",
    },
    "2027-2028": {
        "id": "2027-2028",
        "label": "P&B 2027-2028",
        "report_year": "2027",
        "description": "",
        "related_program_tag": "PB27-28",
    },
}

VERSION_ORDER: tuple[str, ...] = ("2025-2026", "2027-2028")
DEFAULT_VERSION = "2025-2026"

LEGACY_EXCEL_REL_PATH = "source/SG_Report.xlsx"
LEGACY_STATUS_REL_PATH = "status.json"
LEGACY_OUTPUT_PREFIX = "output/"


def resolve_requested_version(requested: str | None, *, active_tab: str) -> str:
    """Pick the P&B version to show when the explore page loads."""
    if active_tab != "pb-progress":
        return DEFAULT_VERSION
    key = (requested or "").strip()
    if key in REPORT_VERSIONS:
        return key
    return DEFAULT_VERSION


def validate_version(version: str) -> str:
    key = (version or "").strip()
    if key not in REPORT_VERSIONS:
        raise ValueError(f"Unknown report version: {version!r}")
    return key


def version_storage_prefix(version: str) -> str:
    validate_version(version)
    return f"versions/{version}/"
