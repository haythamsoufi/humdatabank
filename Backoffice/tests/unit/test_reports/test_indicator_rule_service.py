"""Tests for dynamic Indicator Bank rule resolution."""

from __future__ import annotations

import pytest

from app.models import IndicatorBank
from app.services.reports.indicator_rule_service import (
    preview_indicator_rule,
    resolve_indicator_bank_ids,
)

pytestmark = pytest.mark.unit


def test_resolve_by_related_programme(db_session):
    indicator = IndicatorBank(
        name="PB dynamic test indicator",
        type="number",
        unit="people",
        archived=False,
    )
    indicator.related_programs_list = ["PB27-28", "Other"]
    db_session.add(indicator)
    db_session.commit()

    ids = resolve_indicator_bank_ids({"related_programs_any": ["PB27-28"]})
    assert indicator.id in ids


def test_preview_indicator_rule_returns_count(db_session):
    indicator = IndicatorBank(name="Tagged indicator", type="number", unit="x", archived=False)
    indicator.related_programs_list = ["PB27-28"]
    db_session.add(indicator)
    db_session.commit()

    preview = preview_indicator_rule({"related_programs_any": ["PB27-28"]})
    assert preview["count"] >= 1
    assert preview["sample"]
