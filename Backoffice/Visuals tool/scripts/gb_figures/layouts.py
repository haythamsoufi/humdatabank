"""Per-section dashboard layout config (mirrors Tableau)."""

# Manual sort orders (kept here to avoid circular imports with charts.py)
EF1_ID_ORDER = ["Pascale", "640", "Katya02"]
SP1_ID_ORDER = ["612", "613", "615", "616"]
SP1_DISTINCT_IDS = {"615": "SP1.2", "616": "SP1.1"}

# Line charts that show the year row only (no reporting / implementing breakdown).
NO_NS_BREAKDOWN_INDICATOR_IDS = frozenset({"615", "616", "638", "DREF"})
# Backwards-compatible alias used in tests and imports.
NS_COUNT_INDICATOR_IDS = NO_NS_BREAKDOWN_INDICATOR_IDS

# Temporarily hidden indicators by section.
# Remove an ID from the frozenset (or delete the section key) to restore it in outputs.
# Documented in README.md → Maintenance.
TEMPORARILY_HIDDEN: dict[str, frozenset[str]] = {
    "SP2": frozenset({"Katya01"}),  # Funds mobilized
}


def visible_indicator_ids(section: str, ids: list[str]) -> list[str]:
    hidden = TEMPORARILY_HIDDEN.get(section, frozenset())
    return [indicator_id for indicator_id in ids if indicator_id not in hidden]


def visible_donut_rows(section: str, rows: list[dict]) -> list[dict]:
    hidden = TEMPORARILY_HIDDEN.get(section, frozenset())
    return [row for row in rows if row.get("id") not in hidden]


def visible_donut_pair(section: str, ids: list[str] | None) -> list[str] | None:
    if not ids:
        return None
    hidden = TEMPORARILY_HIDDEN.get(section, frozenset())
    filtered = [indicator_id for indicator_id in ids if indicator_id not in hidden]
    return filtered or None


def show_ns_breakdown(indicator_id: str) -> bool:
    """Whether to show reporting / implementing rows under the year table."""
    return indicator_id not in NO_NS_BREAKDOWN_INDICATOR_IDS

SP_LAYOUTS: dict[str, dict] = {
    "SP1": {
        # Cumulative people-reached + distinct NS counts (Tableau SP1.1/1.2 are year tables → line charts).
        "cumulative_ids": SP1_ID_ORDER,
        "donut_rows": [],
        "footnote_key": "sp1",
        "cumulative_weight": 6.4,
    },
    "SP2": {
        # Tableau SP2 worksheet manual sort (753 is legacy; not in current data).
        "cumulative_ids": ["619", "618", "622", "DREF"],
        "donut_rows": [{"id": "Katya01"}],
        "footnote_key": "sp2",
        "cumulative_weight": 4.5,
        "donut_weight": 0.7,
    },
    "SP3": {
        "cumulative_ids": ["623", "624", "625", "627"],
        "donut_rows": [],
        "footnote_key": "default",
        "cumulative_weight": 4.5,
    },
    "SP4": {
        "cumulative_ids": ["629"],
        # Latest-year snapshot donuts (Tableau SP4.1/4.2 pies).
        "donut_pair": ["KPI_ReachM_IntegratedPlan", "630"],
        "footnote_key": "default",
        "cumulative_weight": 1.5,
        "donut_weight": 0.75,
    },
    "SP5": {
        # 638 is multi-year NS count (Tableau SP5.1) — line chart, not a donut.
        "cumulative_ids": ["633", "635", "638"],
        "donut_rows": [],
        "footnote_key": "default",
        "cumulative_weight": 3.3,
    },
}

SECTION_FOOTNOTE_KEYS: dict[str, str] = {
    "SP1": "sp1",
    "SP2": "sp2",
    "EF4": "ef4",
}

EF_ID_ORDERS: dict[str, list[str]] = {
    "EF1": EF1_ID_ORDER,
    "EF2": ["642", "644", "643", "645"],
    "EF3": ["646", "647"],
    "EF4": ["637", "636", "650", "648", "649", "706"],
}

# Canonical ordered list of all dashboard sections.
SECTION_CODES: list[str] = list(EF_ID_ORDERS.keys()) + list(SP_LAYOUTS.keys())
