"""One approved National Society key-figure row per country and year."""

from __future__ import annotations

import json
from datetime import datetime

from flask import Flask

from plugins.upr import api_cache
from plugins.upr import upr_data_routes
from plugins.upr.catalog import KPI_BANK_IDS, PLAN_TEMPLATE_ID, REPORT_TEMPLATE_ID
from plugins.upr.ns_key_data import build_ns_key_rows
from app.utils.data_quality_constants import FDRS_TEMPLATE_ID

VOLUNTEERS = KPI_BANK_IDS["volunteers"]
STAFF = KPI_BANK_IDS["staff"]
BRANCHES = KPI_BANK_IDS["branches"]
LOCAL_UNITS = KPI_BANK_IDS["local_units"]


def _assignment(**overrides):
    row = {
        "aes_id": 1,
        "country_id": 10,
        "country_name": "Kenya",
        "iso2": "KE",
        "iso3": "KEN",
        "template_id": FDRS_TEMPLATE_ID,
        "period_name": "Annual 2024",
        "status": "approved",
        "approved_at": datetime(2025, 3, 1, 9, 0, 0),
    }
    row.update(overrides)
    return row


def _value(aes_id, bank_id, number, form_data_id=1, **overrides):
    row = {
        "aes_id": aes_id,
        "form_data_id": form_data_id,
        "bank_id": bank_id,
        "numeric_value": number,
        "value": None if number is None else str(number),
        "not_available": False,
        "not_applicable": False,
    }
    row.update(overrides)
    return row


def _kenya(rows, year=2024):
    return [row for row in rows if row["ISO3"] == "KEN" and row["Year"] == year]


def test_most_recent_approval_wins_across_the_three_templates():
    rows = build_ns_key_rows(
        [
            _assignment(aes_id=1, template_id=FDRS_TEMPLATE_ID, period_name="Annual 2024",
                        approved_at=datetime(2025, 3, 1)),
            _assignment(aes_id=2, template_id=PLAN_TEMPLATE_ID, period_name="2025 planning",
                        approved_at=datetime(2023, 11, 1)),
            _assignment(aes_id=3, template_id=REPORT_TEMPLATE_ID, period_name="2024 annual reporting",
                        approved_at=datetime(2025, 6, 1)),
            _assignment(aes_id=4, template_id=REPORT_TEMPLATE_ID, period_name="Jan-Jun 2024",
                        approved_at=datetime(2024, 8, 1)),
        ],
        [
            _value(1, VOLUNTEERS, 1000),
            _value(1, STAFF, 40),
            _value(2, VOLUNTEERS, 900),
            _value(3, VOLUNTEERS, 1100),
            _value(3, STAFF, 45),
            _value(3, BRANCHES, 12),
            _value(3, LOCAL_UNITS, 80),
            _value(4, VOLUNTEERS, 1050),
        ],
    )
    row = _kenya(rows)[0]
    assert row["Source"] == "Annual reporting"
    assert row["Volunteers"] == 1100
    assert row["Staff"] == 45
    assert row["Branches"] == 12
    assert row["LocalUnits"] == 80
    assert row["ApprovedAt"] == "2025-06-01 00:00:00"


def test_a_later_planning_approval_beats_an_earlier_annual_report():
    rows = build_ns_key_rows(
        [
            _assignment(aes_id=1, template_id=REPORT_TEMPLATE_ID, period_name="2024 annual reporting",
                        approved_at=datetime(2025, 2, 1)),
            _assignment(aes_id=2, template_id=PLAN_TEMPLATE_ID, period_name="P25",
                        approved_at=datetime(2025, 8, 1)),
        ],
        [
            _value(1, VOLUNTEERS, 1100),
            _value(2, VOLUNTEERS, 900),
        ],
    )
    row = _kenya(rows)[0]
    assert row["Source"] == "Planning"
    assert row["Year"] == 2024
    assert row["Volunteers"] == 900


def test_unapproved_submissions_are_ignored():
    rows = build_ns_key_rows(
        [
            _assignment(aes_id=1, status="submitted", approved_at=datetime(2025, 9, 1)),
            _assignment(aes_id=2, template_id=PLAN_TEMPLATE_ID, period_name="2025",
                        status="approved", approved_at=datetime(2023, 10, 1)),
        ],
        [
            _value(1, VOLUNTEERS, 5000),
            _value(2, VOLUNTEERS, 800),
        ],
    )
    row = _kenya(rows)[0]
    assert row["Source"] == "Planning"
    assert row["Volunteers"] == 800


def test_an_approved_blank_falls_through_to_the_previous_approved_source():
    rows = build_ns_key_rows(
        [
            _assignment(aes_id=1, approved_at=datetime(2025, 1, 1)),
            _assignment(aes_id=2, template_id=REPORT_TEMPLATE_ID, period_name="2024 annual reporting",
                        approved_at=datetime(2025, 7, 1)),
        ],
        [
            _value(1, VOLUNTEERS, 1000, form_data_id=1),
            _value(1, STAFF, 40),
            _value(2, VOLUNTEERS, None, not_available=True),
        ],
    )
    row = _kenya(rows)[0]
    assert row["Source"] == "FDRS"
    assert row["Volunteers"] == 1000
    assert row["Staff"] == 40


def test_figures_are_not_mixed_across_sources():
    rows = build_ns_key_rows(
        [
            _assignment(aes_id=1, approved_at=datetime(2025, 1, 1)),
            _assignment(aes_id=2, template_id=REPORT_TEMPLATE_ID, period_name="Jan-Jun 2024",
                        approved_at=datetime(2024, 8, 1)),
        ],
        [
            _value(1, VOLUNTEERS, 1000),
            _value(2, VOLUNTEERS, 700),
            _value(2, STAFF, 30),
            _value(2, BRANCHES, 8),
            _value(2, LOCAL_UNITS, 50),
        ],
    )
    row = _kenya(rows)[0]
    assert row["Source"] == "FDRS"
    assert row["Volunteers"] == 1000
    assert row["Staff"] is None
    assert row["Branches"] is None
    assert row["LocalUnits"] is None


def test_midyear_reporting_is_named_when_it_is_the_latest_approval():
    rows = build_ns_key_rows(
        [
            _assignment(aes_id=1, approved_at=datetime(2024, 4, 1)),
            _assignment(aes_id=2, template_id=REPORT_TEMPLATE_ID, period_name="Jan-Jun 2024",
                        approved_at=datetime(2024, 9, 15, 8, 30)),
        ],
        [
            _value(1, VOLUNTEERS, 1000),
            _value(2, VOLUNTEERS, 700),
            _value(2, LOCAL_UNITS, 50),
        ],
    )
    row = _kenya(rows)[0]
    assert row["Source"] == "Mid-year reporting"
    assert row["Volunteers"] == 700
    assert row["LocalUnits"] == 50
    assert row["Staff"] is None


def test_planning_round_belongs_to_the_year_it_was_reported():
    rows = build_ns_key_rows(
        [
            _assignment(aes_id=1, template_id=PLAN_TEMPLATE_ID, period_name="P27",
                        approved_at=datetime(2026, 10, 1)),
        ],
        [_value(1, VOLUNTEERS, 1400), _value(1, STAFF, 60)],
    )
    row = _kenya(rows, year=2026)[0]
    assert row["Year"] == 2026
    assert row["Source"] == "Planning"
    assert row["Volunteers"] == 1400
    assert row["Staff"] == 60
    assert _kenya(rows, year=2027) == []


def test_years_stay_separate_and_zero_is_kept():
    rows = build_ns_key_rows(
        [
            _assignment(aes_id=1, period_name="2023", approved_at=datetime(2024, 3, 1)),
            _assignment(aes_id=2, period_name="2024", approved_at=datetime(2025, 3, 1)),
            _assignment(aes_id=3, country_id=11, country_name="Albania", iso2="AL", iso3="ALB",
                        period_name="2024", approved_at=datetime(2025, 4, 1)),
        ],
        [
            _value(1, VOLUNTEERS, 10),
            _value(2, VOLUNTEERS, 0),
            _value(3, STAFF, 4),
        ],
    )
    assert [(row["ISO3"], row["Year"], row["Volunteers"]) for row in rows] == [
        ("ALB", 2024, None),
        ("KEN", 2024, 0),
        ("KEN", 2023, 10),
    ]
    albania = rows[0]
    assert albania["Staff"] == 4
    assert albania["Source"] == "FDRS"


def test_nskeydata_route_filters_iso3_and_year(monkeypatch):
    api_cache.reset_upr_api_cache_for_tests()
    monkeypatch.setattr(api_cache, "get_upr_cache_revision", lambda: None)
    monkeypatch.setattr(
        upr_data_routes,
        "load_ns_key_rows",
        lambda: [
            {"ISO2": "KE", "ISO3": "KEN", "Year": 2024, "Source": "FDRS", "Volunteers": 1},
            {"ISO2": "KE", "ISO3": "KEN", "Year": 2023, "Source": "Planning", "Volunteers": 2},
            {"ISO2": "AL", "ISO3": "ALB", "Year": 2024, "Source": "Annual reporting", "Volunteers": 3},
        ],
    )
    app = Flask(__name__)
    with app.test_request_context("/api/v1/nskeydata?iso3=ken&year=2024"):
        response = upr_data_routes.get_ns_key_data.__wrapped__()

    body = json.loads(response.get_data(as_text=True))
    assert body["data"] == [{"ISO2": "KE", "ISO3": "KEN", "Year": 2024, "Source": "FDRS", "Volunteers": 1}]
    assert body["meta"]["total"] == 1
    assert "Source" in body["meta"]["columns"]
    assert response.headers["Cache-Control"] == "no-store"
    api_cache.reset_upr_api_cache_for_tests()


def test_nskeydata_route_filters_iso2(monkeypatch):
    api_cache.reset_upr_api_cache_for_tests()
    monkeypatch.setattr(api_cache, "get_upr_cache_revision", lambda: None)
    monkeypatch.setattr(
        upr_data_routes,
        "load_ns_key_rows",
        lambda: [
            {"ISO2": "KE", "ISO3": "KEN", "Year": 2024, "Volunteers": 1},
            {"ISO2": "AL", "ISO3": "ALB", "Year": 2024, "Volunteers": 3},
        ],
    )
    app = Flask(__name__)
    with app.test_request_context("/api/v1/nskeydata?iso2=ke"):
        response = upr_data_routes.get_ns_key_data.__wrapped__()

    body = json.loads(response.get_data(as_text=True))
    assert body["data"] == [{"ISO2": "KE", "ISO3": "KEN", "Year": 2024, "Volunteers": 1}]
    api_cache.reset_upr_api_cache_for_tests()


def test_nskeydata_route_rejects_a_bad_iso2():
    app = Flask(__name__)
    with app.test_request_context("/api/v1/nskeydata?iso2=KEN"):
        response = upr_data_routes.get_ns_key_data.__wrapped__()
    assert response.status_code == 400


def test_nskeydata_route_rejects_a_bad_year():
    app = Flask(__name__)
    with app.test_request_context("/api/v1/nskeydata?year=24"):
        response = upr_data_routes.get_ns_key_data.__wrapped__()
    assert response.status_code == 400
