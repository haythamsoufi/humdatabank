"""Planning vs reporting comparison for volunteers, staff, branches, and local units."""

from plugins.upr.capacity_comparison import (
    build_capacity_comparison,
    rows_to_observations,
)
from plugins.upr.catalog import KPI_BANK_IDS, PLAN_TEMPLATE_ID, REPORT_TEMPLATE_ID

VOLUNTEERS = KPI_BANK_IDS["volunteers"]
STAFF = KPI_BANK_IDS["staff"]


def _assignment(**overrides):
    row = {
        "aes_id": 1,
        "country_id": 10,
        "country_name": "Kenya",
        "iso3": "KEN",
        "region": "Africa",
        "template_id": PLAN_TEMPLATE_ID,
        "period_name": "2025",
        "status": "submitted",
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


def _compare(assignments, values):
    return build_capacity_comparison(rows_to_observations(assignments, values))


def _kenya_volunteers(payload):
    return [
        row for row in payload["rows"]
        if row["country_id"] == 10 and row["measure"] == "volunteers"
    ]


def test_same_year_gap_of_25_percent_needs_attention():
    payload = _compare(
        [
            _assignment(aes_id=1, template_id=PLAN_TEMPLATE_ID, period_name="2025"),
            _assignment(aes_id=2, template_id=REPORT_TEMPLATE_ID, period_name="2025"),
        ],
        [
            _value(1, VOLUNTEERS, 12000),
            _value(2, VOLUNTEERS, 9000),
        ],
    )
    row = _kenya_volunteers(payload)[0]
    assert row["year"] == 2025
    assert row["plan"] == 12000
    assert row["annual"] == 9000
    assert row["severity"] == "attention"
    assert row["flags"][0]["kind"] == "discrepancy"
    assert "25%" in row["flags"][0]["text"]
    assert set(row["hot"]) == {"plan", "annual"}
    assert payload["summary"]["discrepancies"] == 1
    assert payload["summary"]["attention_rows"] == 1


def test_gap_under_25_percent_is_a_variation_to_review():
    payload = _compare(
        [
            _assignment(aes_id=1),
            _assignment(aes_id=2, template_id=REPORT_TEMPLATE_ID),
        ],
        [_value(1, VOLUNTEERS, 10000), _value(2, VOLUNTEERS, 8800)],
    )
    row = _kenya_volunteers(payload)[0]
    assert row["severity"] == "review"
    assert row["flags"][0]["kind"] == "discrepancy"
    assert payload["summary"]["attention_rows"] == 0
    assert payload["summary"]["review_rows"] == 1


def test_matching_figures_are_aligned():
    payload = _compare(
        [
            _assignment(aes_id=1),
            _assignment(aes_id=2, template_id=REPORT_TEMPLATE_ID),
        ],
        [_value(1, VOLUNTEERS, 10000), _value(2, VOLUNTEERS, 10000)],
    )
    row = _kenya_volunteers(payload)[0]
    assert row["severity"] == "aligned"
    assert row["flags"] == []


def test_year_to_year_drop_of_half_or_more_needs_attention():
    payload = _compare(
        [
            _assignment(aes_id=1, template_id=REPORT_TEMPLATE_ID, period_name="2024"),
            _assignment(aes_id=2, template_id=REPORT_TEMPLATE_ID, period_name="2025"),
        ],
        [_value(1, VOLUNTEERS, 10000), _value(2, VOLUNTEERS, 4000)],
    )
    row = next(row for row in _kenya_volunteers(payload) if row["year"] == 2025)
    assert row["severity"] == "attention"
    assert row["flags"][0]["kind"] == "variation"
    assert "60% lower" in row["flags"][0]["text"]
    assert "2024" in row["flags"][0]["text"]


def test_smaller_year_to_year_change_is_a_review():
    payload = _compare(
        [
            _assignment(aes_id=1, template_id=REPORT_TEMPLATE_ID, period_name="2024"),
            _assignment(aes_id=2, template_id=REPORT_TEMPLATE_ID, period_name="2025"),
        ],
        [_value(1, VOLUNTEERS, 10000), _value(2, VOLUNTEERS, 7500)],
    )
    row = next(row for row in _kenya_volunteers(payload) if row["year"] == 2025)
    assert row["severity"] == "review"
    assert "25% lower" in row["flags"][0]["text"]


def test_blank_on_an_in_progress_report_is_a_review():
    payload = _compare(
        [
            _assignment(aes_id=1, template_id=PLAN_TEMPLATE_ID),
            _assignment(aes_id=2, template_id=REPORT_TEMPLATE_ID, status="in_progress"),
        ],
        [_value(1, VOLUNTEERS, 5000)],
    )
    row = _kenya_volunteers(payload)[0]
    assert row["annual"] is None
    assert row["severity"] == "review"
    assert row["flags"][0]["kind"] == "missing"
    assert "left this figure blank" in row["flags"][0]["text"]


def test_blank_on_a_submitted_report_needs_attention():
    payload = _compare(
        [
            _assignment(aes_id=1, template_id=PLAN_TEMPLATE_ID),
            _assignment(aes_id=2, template_id=REPORT_TEMPLATE_ID, status="submitted"),
        ],
        [_value(1, VOLUNTEERS, 5000)],
    )
    row = _kenya_volunteers(payload)[0]
    assert row["severity"] == "attention"
    assert payload["summary"]["missing"] == 1


def test_pending_blank_is_not_a_discrepancy():
    payload = _compare(
        [
            _assignment(aes_id=1),
            _assignment(aes_id=2, template_id=REPORT_TEMPLATE_ID, status="pending"),
        ],
        [_value(1, VOLUNTEERS, 5000)],
    )
    row = _kenya_volunteers(payload)[0]
    assert row["severity"] == "single"
    assert row["flags"] == []


def test_no_reporting_assignment_stays_a_single_source():
    payload = _compare(
        [_assignment(aes_id=1)],
        [_value(1, VOLUNTEERS, 5000)],
    )
    row = _kenya_volunteers(payload)[0]
    assert row["severity"] == "single"
    assert row["flags"] == []
    assert payload["summary"]["countries"] == 1


def test_not_available_is_a_review_not_a_hard_flag():
    payload = _compare(
        [
            _assignment(aes_id=1),
            _assignment(aes_id=2, template_id=REPORT_TEMPLATE_ID),
        ],
        [
            _value(1, VOLUNTEERS, 5000),
            _value(2, VOLUNTEERS, None, not_available=True),
        ],
    )
    row = _kenya_volunteers(payload)[0]
    assert row["severity"] == "review"
    assert "not available" in row["flags"][0]["text"]


def test_annual_and_midyear_disagree():
    payload = _compare(
        [
            _assignment(aes_id=1, template_id=REPORT_TEMPLATE_ID, period_name="2025"),
            _assignment(aes_id=2, template_id=REPORT_TEMPLATE_ID, period_name="Jan-Jun 2025"),
        ],
        [_value(1, VOLUNTEERS, 100), _value(2, VOLUNTEERS, 40)],
    )
    row = _kenya_volunteers(payload)[0]
    assert row["annual"] == 100
    assert row["midyear"] == 40
    assert row["severity"] == "attention"
    assert row["flags"][0]["kind"] == "discrepancy"
    assert "annual report" in row["flags"][0]["text"]
    assert "mid-year" in row["flags"][0]["text"]


def test_zero_against_a_reported_number_needs_attention():
    payload = _compare(
        [
            _assignment(aes_id=1),
            _assignment(aes_id=2, template_id=REPORT_TEMPLATE_ID),
        ],
        [_value(1, VOLUNTEERS, 0), _value(2, VOLUNTEERS, 80)],
    )
    row = _kenya_volunteers(payload)[0]
    assert row["severity"] == "attention"


def test_later_blank_does_not_wipe_an_earlier_number():
    payload = _compare(
        [_assignment(aes_id=1)],
        [
            _value(1, VOLUNTEERS, 10, form_data_id=1),
            _value(1, VOLUNTEERS, None, form_data_id=2),
        ],
    )
    assert _kenya_volunteers(payload)[0]["plan"] == 10


def test_later_number_replaces_an_earlier_one():
    payload = _compare(
        [_assignment(aes_id=1)],
        [
            _value(1, VOLUNTEERS, 10, form_data_id=1),
            _value(1, VOLUNTEERS, 25, form_data_id=2),
        ],
    )
    assert _kenya_volunteers(payload)[0]["plan"] == 25


def test_assignment_with_a_number_wins_over_a_later_blank_assignment():
    payload = _compare(
        [
            _assignment(aes_id=1, period_name="2025"),
            _assignment(aes_id=9, period_name="P25", status="submitted"),
        ],
        [_value(1, VOLUNTEERS, 10)],
    )
    assert _kenya_volunteers(payload)[0]["plan"] == 10


def test_cancelled_assignment_is_ignored():
    payload = _compare(
        [_assignment(aes_id=1, status="cancelled")],
        [_value(1, VOLUNTEERS, 10)],
    )
    assert payload["rows"] == []


def test_attention_rows_sort_ahead_of_aligned_ones():
    payload = _compare(
        [
            _assignment(aes_id=1, country_id=1, country_name="Zambia", iso3="ZMB"),
            _assignment(aes_id=2, country_id=1, template_id=REPORT_TEMPLATE_ID),
            _assignment(aes_id=3, country_id=2, country_name="Kenya", iso3="KEN"),
            _assignment(aes_id=4, country_id=2, template_id=REPORT_TEMPLATE_ID),
        ],
        [
            _value(1, VOLUNTEERS, 100),
            _value(2, VOLUNTEERS, 100),
            _value(3, VOLUNTEERS, 100),
            _value(4, VOLUNTEERS, 50),
        ],
    )
    assert payload["rows"][0]["country_name"] == "Kenya"
    assert payload["rows"][0]["severity"] == "attention"
    assert payload["rows"][1]["country_name"] == "Zambia"
    assert payload["measures"][0]["key"] == "volunteers"
    assert payload["years"] == [2025]


def test_staff_uses_its_own_bank_id():
    payload = _compare(
        [
            _assignment(aes_id=1),
            _assignment(aes_id=2, template_id=REPORT_TEMPLATE_ID),
        ],
        [_value(1, STAFF, 200), _value(2, STAFF, 100)],
    )
    row = next(row for row in payload["rows"] if row["measure"] == "staff")
    assert row["measure_label"] == "Staff"
    assert row["severity"] == "attention"
    assert row["plan"] == 200
    assert row["annual"] == 100
