"""UPR validation-dashboard round codes."""

from plugins.upr.catalog import PLAN_TEMPLATE_ID, REPORT_TEMPLATE_ID
from plugins.upr.validation_dashboard import (
    choose_validation_rounds,
    round_display_label,
    round_for_assignment,
)


def test_reporting_midyear_period_is_myr():
    assert round_for_assignment(REPORT_TEMPLATE_ID, "Jan-Jun 2026") == "MYR26"


def test_reporting_year_period_is_ar():
    assert round_for_assignment(REPORT_TEMPLATE_ID, "2025") == "AR25"
    assert round_for_assignment(REPORT_TEMPLATE_ID, "AR25") == "AR25"


def test_planning_year_period_is_p():
    assert round_for_assignment(PLAN_TEMPLATE_ID, "2026") == "P26"
    assert round_for_assignment(PLAN_TEMPLATE_ID, "P26") == "P26"


def test_choose_validation_rounds_keeps_one_period_per_code():
    rounds = choose_validation_rounds([
        (REPORT_TEMPLATE_ID, "Jan-Jun 2026", 10),
        (REPORT_TEMPLATE_ID, "MYR26", 2),
        (PLAN_TEMPLATE_ID, "2026", 4),
        (REPORT_TEMPLATE_ID, "2025", 8),
    ])
    assert [item["code"] for item in rounds] == ["MYR26", "P26", "AR25"]
    myr = next(item for item in rounds if item["code"] == "MYR26")
    assert myr["period_name"] == "Jan-Jun 2026"
    assert myr["template_id"] == REPORT_TEMPLATE_ID
    assert myr["label"] == "2026 midyear reporting"
    assert next(item for item in rounds if item["code"] == "P26")["label"] == "2026 planning"
    assert next(item for item in rounds if item["code"] == "AR25")["label"] == "2025 annual reporting"


def test_round_display_label_uses_assignment_style_names():
    assert round_display_label("P26") == "2026 planning"
    assert round_display_label("MYR26") == "2026 midyear reporting"
    assert round_display_label("AR25") == "2025 annual reporting"
