"""UPR visual catalog — dashboards, colours, labels, and form-item mappings.

Mirrors the Tableau workbook ``UPR Visuals.twb`` (country/round dashboards)
using Unified Country Plan (template 24) and Reporting (template 33) data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet

from app.utils.data_quality_constants import (
    UPR_PLANNING_TEMPLATE_ID,
    UPR_REPORTING_TEMPLATE_ID,
)

PLAN_TEMPLATE_ID = UPR_PLANNING_TEMPLATE_ID
REPORT_TEMPLATE_ID = UPR_REPORTING_TEMPLATE_ID
# Reporting — International Bilateral Support (PNS self-report).
PNS_REPORT_TEMPLATE_ID = 23
# PNS planning / confirmed funding for a host country (row = host Country.id).
PNS_PLAN_TEMPLATE_ID = 22
UPR_VISUAL_TEMPLATE_IDS: FrozenSet[int] = frozenset({PLAN_TEMPLATE_ID, REPORT_TEMPLATE_ID})

# NS key figures (same bank ids on T24 and T33).
KPI_BANK_IDS = {
    "branches": 1117,
    "local_units": 723,
    "volunteers": 724,
    "staff": 727,
}

KPI_ORDER = ("branches", "local_units", "volunteers", "staff")

KPI_LABELS = {
    "branches": "Local Branches",
    "local_units": "Local Units",
    "volunteers": "Volunteers",
    "staff": "Paid Staff",
}

PLAN_KPI_ORDER = ("branches", "staff", "volunteers", "local_units")

PLAN_KPI_LABELS = {
    "branches": "Branches",
    "staff": "Staff",
    "volunteers": "Volunteers",
    "local_units": "Local units",
}

# T24 fallback item ids (published version; label lookup wins when available).
PLAN_ITEM_FALLBACKS = {
    "reach_longer_term": 954,
    "reach_emergency": 960,
    "support": 955,
    "funding_y0": 967,
    "funding_y1": 968,
    "funding_y2": 974,
}

# T33 fallback item ids.
REPORT_ITEM_FALLBACKS = {
    "funding_sources": 1403,
    "expenditure": 1404,
    "sp_breakdown": 1405,
    "support": 1407,
}

# T22 fallback item ids (PNS assignments; rows keyed by host Country.id).
PNS_PLAN_ITEM_FALLBACKS = {
    "funding": 1303,
}

PNS_PLAN_LABEL_NEEDLES = {
    "funding": ("funding requirement",),
}

PLANNING_EA_FUNDING_AREAS = frozenset({"EA1", "EA2", "EA3"})
NETWORK_ENTITY_ORDER = ("Total", "IFRC Secretariat", "PNS")

PLAN_LABEL_NEEDLES = {
    "reach_longer_term": ("longer term programme", "longer-term programme", "people to be reached"),
    "reach_emergency": ("emergency appeal",),
    "support": ("planned bilateral support", "bilateral support"),
    "funding_y0": ("funding requirement",),
}

REPORT_LABEL_NEEDLES = {
    "funding_sources": (
        "ns total funding",
        "ns 2025 total funding",
        "ns 2026 total funding",
        "assignment_year] funding",
        "funding (chf)",
    ),
    "expenditure": (
        "ns total expenditure",
        "ns 2025 total expenditure",
        "ns 2026 total expenditure",
        "assignment_year] expenditure",
        "expenditure (chf)",
    ),
    "sp_breakdown": ("optional breakdown by sp/ef",),
    "support": ("received support",),
}

PNS_REPORT_LABEL_NEEDLES = {
    "funding": ("pns funding", "funding matrix", "international bilateral"),
}

SP_CODES = ("SP1", "SP2", "SP3", "SP4", "SP5")
EF_CODES = ("EF1", "EF2", "EF3", "EF4")
SUPPORT_AREA_CODES = (*SP_CODES, "EFs")
# Temporary: hide Cross-cutting on People reached. Emergency-response reach
# is remapped to SP2; long-term services reach is dropped.
# How to change or revert: docs/people-reached.md
REACH_CODES = ("EO", *SP_CODES)
REACH_EMERGENCY_TO_SP2_NEEDLES = ("emergency response and early recovery",)
REACH_DROP_LONG_TERM_NEEDLES = (
    "long-term services and programmes",
    "longer-term services and programmes",
    "longer term services and programmes",
    "long term services and programmes",
)
# T33 Cross Cutting bank id for emergency response / early recovery.
REACH_EMERGENCY_BANK_ID = 619

AREA_LABELS = {
    "EO": "Emergency Operations",
    "CC1": "Cross-cutting",
    "SP1": "Climate and environment",
    "SP2": "Disasters and crises",
    "SP3": "Health and wellbeing",
    "SP4": "Migration and displacement",
    "SP5": "Values, power and inclusion",
    "EFs": "Enabling Functions",
    "EF1": "Strategic and operational coordination",
    "EF2": "National Society development",
    "EF3": "Humanitarian diplomacy",
    "EF4": "Accountability and agility",
}

# Two-line support-table headers (WeasyPrint cannot rotate writing-mode text).
SUPPORT_AREA_HEADER_LINES = {
    "SP1": ("Climate and", "environment"),
    "SP2": ("Disasters and", "crises"),
    "SP3": ("Health and", "wellbeing"),
    "SP4": ("Migration and", "displacement"),
    "SP5": ("Values, power", "and inclusion"),
    "EFs": ("Enabling", "Functions"),
}

# Tableau plan "Detailed funding requirements" shortenings (ampersands).
PLAN_DETAIL_SP_LABELS = {
    "SP1": "Climate and environment",
    "SP2": "Disasters & crises",
    "SP3": "Health & wellbeing",
    "SP4": "Migration & displacement",
    "SP5": "Values, power & inclusion",
}

# T33 Page 1: static core indicators live under this section (and its children).
# Dynamic extras are the sibling "Other Indicators" section — not Emergency Appeals.
OVERALL_ACTION_SECTION_NEEDLE = "overall action"
OTHER_INDICATORS_SECTION_NAME = "other indicators"

# Form section name fragments → SP/EF code (T33 core indicators).
SECTION_AREA_HINTS = (
    ("climate and environment", "SP1"),
    ("disasters and crises", "SP2"),
    ("health and wellbeing", "SP3"),
    ("migration and displacement", "SP4"),
    ("values, power and inclusion", "SP5"),
    ("cross cutting", "CC1"),
    ("cross-cutting", "CC1"),
    ("strategic and operational coordination", "EF1"),
    ("national society development", "EF2"),
    ("humanitarian diplomacy", "EF3"),
    ("accountability and agility", "EF4"),
)

REPORTING_SP_BREAKDOWN_AREA_TO_ROW = {
    "SP1": "Resilience - Climate and environment",
    "SP2": "Response - Disasters and crises",
    "SP3": "Resilience - Health and wellbeing",
    "SP4": "Resilience - Migration and displacement",
    "SP5": "Respect - Values, power and inclusion",
    "EFs": "Enabling functions",
}

FUNDING_ENTITY_LABELS = {
    "HNS": "Host National Society",
    "IFRC Secretariat": "IFRC Secretariat",
    "IFRC": "IFRC Secretariat",
    "PNS": "Participating National Societies",
    "PNSs": "Participating National Societies",
    "Other sources": "HNS other funding sources",
    "HNS other sources": "HNS other funding sources",
}

# Tableau workbook display-name shortenings for PNS rows.
NS_DISPLAY_ALIASES = {
    "red crescent society of the islamic republic of iran": "Iranian Red Crescent Society",
    "red crescent society of the united arab emirates": "United Arab Emirates Red Crescent",
    "red cross of monaco": "Monaco Red Cross",
    "the canadian red cross society": "Canadian Red Cross Society",
    "the netherlands red cross": "Netherlands Red Cross",
    "the republic of korea national red cross": "Republic of Korea National Red Cross",
    "the gambia red cross society": "Gambia Red Cross Society",
    "the south african red cross society": "South African Red Cross Society",
    "the thai red cross society": "Thai Red Cross Society",
    "turkish red crescent society": "Turkish Red Crescent",
}

# IFRC Strategy 2030 / UPR print colours (Tableau-faithful).
IFRC_RED = "#d22730"
IFRC_RED_BRIGHT = "#f63441"
IFRC_NAVY = "#011e41"
IFRC_GREY = "#58595b"

AREA_COLORS = {
    "EO": "#c22526",
    "CC1": "#011e41",
    "SP1": "#6ba543",
    "SP2": "#f39200",
    "SP3": "#e30613",
    "SP4": "#3d7edb",
    "SP5": "#8b5a9e",
    "EFs": "#58595b",
    "EF1": "#58595b",
    "EF2": "#58595b",
    "EF3": "#58595b",
    "EF4": "#58595b",
    "multilateral": "#011e41",
    "funding_requirement": "#011e41",
    "funding": "#f39200",
    "expenditure": "#e30613",
    "source": "#2a9d8f",
}

# Planned-support legend (INP / SPEF dots — distinct from Tableau AREA_COLORS).
SUPPORT_DOT_COLORS = {
    "SP1": "#58a04f",
    "SP2": "#226092",
    "SP3": "#8fd2ef",
    "SP4": "#ffb15b",
    "SP5": "#512c6c",
    "EFs": "#883a67",
}

KPI_ICON_FILES = {
    "branches": "icons/kpi-independence.png",
    "local_units": "icons/kpi-independence.png",
    "staff": "icons/kpi-unity.png",
    "volunteers": "icons/kpi-voluntary-service.png",
}

# GitHub originals — used only if a local plugin file is missing.
KPI_ICON_URLS = {
    "branches": "https://raw.githubusercontent.com/FDRS-ifrc/general/main/ifrc_icons/IFRC-icons-colour_Independence.png",
    "local_units": "https://raw.githubusercontent.com/FDRS-ifrc/general/main/ifrc_icons/IFRC-icons-colour_Independence.png",
    "staff": "https://raw.githubusercontent.com/FDRS-ifrc/general/main/ifrc_icons/IFRC-icons-colour_Unity.png",
    "volunteers": "https://raw.githubusercontent.com/FDRS-ifrc/general/main/ifrc_icons/IFRC-icons-colour_Voluntary-service.png",
}


def kpi_icon_src(key: str) -> str:
    """Local plugin icon when present; otherwise the public IFRC fallback URL."""
    rel = KPI_ICON_FILES.get(key)
    if rel:
        path = Path(__file__).resolve().parent / "static" / rel
        if path.is_file():
            return f"/upr-visuals/static/{rel}"
    return (KPI_ICON_URLS.get(key) or "").strip()


# A4 landscape at 96 CSS px (WeasyPrint default). Single-chip export uses this.
A4_PAGE_WIDTH_PX = 1123
A4_PAGE_HEIGHT_PX = 794
A4_MARGIN_MM = 6
A4_COMBINED_MARGIN_MM = 0  # first page — navy header bleeds to the page edge
A4_COMBINED_FOLLOWING_MARGIN_MM = 10  # later pages — keep content off the paper edge
A4_CONTENT_WIDTH_PX = 1047  # 297mm − 20mm margins
# A4 portrait — All visuals (combined) PDF.
A4_PORTRAIT_WIDTH_PX = A4_PAGE_HEIGHT_PX
A4_PORTRAIT_HEIGHT_PX = A4_PAGE_WIDTH_PX


@dataclass(frozen=True)
class DashboardSpec:
    id: str
    title: str
    plan: bool
    report: bool
    width: int
    height: int
    description: str


DASHBOARDS: tuple[DashboardSpec, ...] = (
    DashboardSpec(
        "combined",
        "All visuals",
        True,
        True,
        A4_CONTENT_WIDTH_PX,
        1600,
        "Full stacked visual: In Support Of, People reached, finance, emergencies, SP/EF indicators, then support across portrait A4 pages.",
    ),
    DashboardSpec(
        "in_support",
        "In Support of",
        True,
        True,
        A4_CONTENT_WIDTH_PX,
        250,
        "National Society header plus four key figures. Plans use INP order (branches, staff, volunteers, local units).",
    ),
    DashboardSpec(
        "reach",
        "People reached",
        True,
        True,
        A4_CONTENT_WIDTH_PX,
        280,
        "People reached / to be reached by Strategic Priority and Emergency Operations.",
    ),
    DashboardSpec(
        "financial",
        "Financial Overview",
        True,
        True,
        A4_CONTENT_WIDTH_PX,
        900,
        "Plans: IFRC network funding requirements by year. Reports: network actuals vs requirement.",
    ),
    DashboardSpec(
        "network_funding",
        "Network funding",
        True,
        False,
        A4_CONTENT_WIDTH_PX,
        500,
        "Plan-year detailed funding: Host National Society vs IFRC, with ongoing emergencies, longer-term needs, and enabling local actors.",
    ),
    DashboardSpec(
        "emergency_1",
        "Emergency 1",
        False,
        True,
        A4_CONTENT_WIDTH_PX,
        320,
        "First emergency appeal indicators (reporting).",
    ),
    DashboardSpec(
        "emergency_2",
        "Emergency 2",
        False,
        True,
        A4_CONTENT_WIDTH_PX,
        320,
        "Second emergency appeal indicators (reporting).",
    ),
    DashboardSpec(
        "emergency_3",
        "Emergency 3",
        False,
        True,
        A4_CONTENT_WIDTH_PX,
        320,
        "Third emergency appeal indicators (reporting).",
    ),
    DashboardSpec(
        "strategic_priorities",
        "Strategic Priorities",
        False,
        True,
        A4_CONTENT_WIDTH_PX,
        1400,
        "Core numeric indicators as horizontal bars, grouped by Strategic Priority.",
    ),
    DashboardSpec(
        "enabling_functions",
        "Enabling Functions",
        False,
        True,
        A4_CONTENT_WIDTH_PX,
        900,
        "Enabling Function indicators (bars for numbers, Yes for qualitative).",
    ),
    DashboardSpec(
        "support",
        "Bilateral Support",
        True,
        True,
        A4_CONTENT_WIDTH_PX,
        620,
        "Participating National Society support by Strategic Priority. Plans add year rows and coloured amount cells.",
    ),
)

DASHBOARD_BY_ID = {spec.id: spec for spec in DASHBOARDS}


def emergency_slot_for_dashboard(dashboard_id: str) -> int | None:
    if not (dashboard_id or "").startswith("emergency_"):
        return None
    try:
        return int(dashboard_id.rsplit("_", 1)[-1])
    except (TypeError, ValueError):
        return None


def dashboards_for_kind(kind: str, *, emergency_slots: set[int] | frozenset[int] | None = None) -> list[DashboardSpec]:
    if kind == "plan":
        specs = [spec for spec in DASHBOARDS if spec.plan]
    else:
        specs = [spec for spec in DASHBOARDS if spec.report]
    if emergency_slots is None:
        return specs
    return [
        spec
        for spec in specs
        if (slot := emergency_slot_for_dashboard(spec.id)) is None or slot in emergency_slots
    ]


def kind_for_template(template_id: int) -> str:
    if template_id == PLAN_TEMPLATE_ID:
        return "plan"
    return "report"


def display_ns_name(name: str | None) -> str:
    raw = (name or "").strip()
    if not raw:
        return ""
    return NS_DISPLAY_ALIASES.get(raw.lower(), raw)


def section_to_area(section_name: str | None) -> str | None:
    text = (section_name or "").strip().lower()
    if not text:
        return None
    for needle, code in SECTION_AREA_HINTS:
        if needle in text:
            return code
    return None
