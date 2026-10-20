"""Reporting-currency / Swiss-franc pairing."""

from plugins.fdrs.services.fdrs_currency import (
    chf_matrix_key,
    end_date_from_items,
    exchange_rate_date,
    normalize_rate_date,
    income_source_slot,
    is_chf_currency,
    local_to_chf,
    merge_income_matrix_chf,
    mirror_chf_currency_rows,
    parse_chf_exchange_rate,
    rate_for_date,
    resolve_reported_amounts,
)


def test_chf_currency_fills_both_sides_from_either_kpi():
    assert resolve_reported_amounts(10, 10, "CHF") == (10, 10)
    assert resolve_reported_amounts(None, 10, "chf") == (10, 10)
    assert resolve_reported_amounts(10, None, "CHF") == (10, 10)


def test_local_currency_keeps_the_entered_amount_separate():
    assert resolve_reported_amounts(1000, 25, "AFN") == (1000, 25)
    assert resolve_reported_amounts(None, 25, "AFN") == (25, 25)
    assert resolve_reported_amounts(1000, None, "AFN") == (1000, None)


_INCOME_ROWS = {
    "h_gov_CHF": "Home Government",
    "KPI_incomeFromNSsLC_CHF": "Other National Society",
}


def test_income_source_slot_recognises_local_and_chf_codes():
    assert income_source_slot("h_gov_CHF", _INCOME_ROWS) == ("Home Government", "chf")
    assert income_source_slot("h_gov", _INCOME_ROWS) == ("Home Government", "local")
    assert income_source_slot("KPI_incomeFromNSsLC", _INCOME_ROWS) == ("Other National Society", "local")
    assert income_source_slot("KPI_PeopleVol", _INCOME_ROWS) is None


def test_rate_uses_the_financial_reporting_end_date():
    assert normalize_rate_date("2025-12-31") == "2025-12-31"
    assert normalize_rate_date("31/12/2025") == "2025-12-31"
    assert exchange_rate_date("2026") is None
    assert parse_chf_exchange_rate({"chfExchangeRate": 0.0024076259330484528}) == 0.0024076259330484528
    assert parse_chf_exchange_rate({}) is None
    assert rate_for_date("2025-12-31", "CHF") is None
    assert rate_for_date("", "AFN") is None

    class _Item:
        def __init__(self, item_id, label):
            self.id = item_id
            self.item_type = "question"
            self.label = label

    items = [_Item(937, "Financial reporting end date")]
    assert end_date_from_items(items, {"field_value[937]": "2025-06-30"}) == "2025-06-30"
    assert end_date_from_items(items, {"field_value[937]": ""}) == ""


def test_local_to_chf_multiplies_by_francs_per_local_unit():
    assert local_to_chf(1000, "0.025") == 25
    assert local_to_chf(1000, 0.025) == 25
    assert local_to_chf(1000, None) is None
    assert local_to_chf(None, 0.025) is None


def test_merge_keeps_stored_chf_when_the_rate_is_missing_and_the_cell_is_unchanged():
    existing = {"Home Government_Funding": 1000, chf_matrix_key("Home Government_Funding"): 25}
    merged = merge_income_matrix_chf(
        {"Home Government_Funding": 1000},
        existing,
        "AFN",
        None,
    )
    assert merged["Home Government_Funding"] == 1000
    assert merged[chf_matrix_key("Home Government_Funding")] == 25


def test_merge_converts_when_a_rate_is_loaded_and_copies_when_currency_is_chf():
    converted = merge_income_matrix_chf(
        {"Home Government_Funding": 1000},
        {},
        "AFN",
        0.025,
    )
    assert converted[chf_matrix_key("Home Government_Funding")] == 25

    same = merge_income_matrix_chf(
        {"Home Government_Funding": 80},
        {},
        "CHF",
        None,
    )
    assert same["Home Government_Funding"] == 80
    assert same[chf_matrix_key("Home Government_Funding")] == 80


def test_mirror_copies_the_missing_side_only_when_currency_is_chf():
    local = {"assignment_entity_status_id": "7", "item_id": "939", "value": "50"}
    chf_only = {"assignment_entity_status_id": "8", "item_id": "1400", "value": "60"}
    rows = mirror_chf_currency_rows(
        [local, chf_only],
        [(939, 1400)],
        {"7": "CHF", "8": "AFN"},
    )
    by_item = {(row["assignment_entity_status_id"], row["item_id"]): row["value"] for row in rows}
    assert by_item[("7", "939")] == "50"
    assert by_item[("7", "1400")] == "50"
    assert ("8", "939") not in by_item
    assert by_item[("8", "1400")] == "60"
    assert is_chf_currency(" CHF ")

