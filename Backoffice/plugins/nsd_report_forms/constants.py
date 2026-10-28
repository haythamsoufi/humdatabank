"""NSD-specific constants on top of core project reporting."""

from app.models.enums import EntityType

# AES / EntityService type — core project entity
ENTITY_TYPE = EntityType.project.value

# Shared AssignedForm.period_name slots for CBF relative clocks
FINAL_SLOT = "Final"
PROFILE_SLOT = "Project"  # legacy profile period suffix

MAX_QUARTER_YEARS = 3
MAX_QUARTERS_PER_YEAR = 4

QUARTER_TEMPLATE_KEY = "CBF quarter"
FINAL_TEMPLATE_KEY = "CBF final report"
PROFILE_TEMPLATE_KEY = "profile"


def quarter_slot(year: int, quarter: int) -> str:
    return f"Y{int(year)}Q{int(quarter)}"


def all_quarter_slots(max_years: int = MAX_QUARTER_YEARS) -> list:
    return [
        quarter_slot(y, q)
        for y in range(1, max_years + 1)
        for q in range(1, MAX_QUARTERS_PER_YEAR + 1)
    ]


def parse_quarter_slot(period: str):
    """Return (year, quarter) for ``Y1Q2``, else None."""
    import re

    m = re.match(r"^Y(\d+)Q(\d+)$", (period or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))
