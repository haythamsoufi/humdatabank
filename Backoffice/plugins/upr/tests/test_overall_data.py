"""FDRS + Unified Reporting merge: FDRS first, then annual, then mid-year."""

from __future__ import annotations

from plugins.upr.overall_data import (
    OVERALL_COLUMNS,
    SOURCE_FDRS,
    SOURCE_UNIFIED_REPORTING,
    _finish,
    fdrs_role,
    merge_facts,
)
from plugins.upr.upr_data import FACT_COLUMNS, ItemView

FDRS, ANNUAL, MIDYEAR = 0, 1, 2


def _fact(value, attribute="Total", indicator="Volunteers"):
    return {
        "ISO3": "KEN",
        "Year": 2024,
        "Indicator": indicator,
        "Attribute": attribute,
        "ValueNum": value,
        "Value": value,
    }


def _item(**overrides):
    base = dict(
        id=1,
        template_id=21,
        item_type="indicator",
        label="x",
        section_name="s",
        bank_id=724,
        bank_name="Number of people volunteering.",
        bank_area=None,
    )
    base.update(overrides)
    return ItemView(**base)


def _merged(tagged):
    return [(row["ValueNum"], row["Attribute"]) for row, _rank in merge_facts(tagged)]


KEY = (1, 2024, 724)


def test_columns_rename_source_only():
    assert "Source" not in OVERALL_COLUMNS
    assert "Country Value" not in OVERALL_COLUMNS
    expected = []
    for column in FACT_COLUMNS:
        expected.extend({"Source": ["Data source"], "Country Value": ["FDRS Value", "UPR Value"]}.get(column, [column]))
    assert list(OVERALL_COLUMNS) == expected


def test_fdrs_wins_when_both_reported():
    tagged = [
        (KEY, ANNUAL, _fact(900)),
        (KEY, FDRS, _fact(1000)),
        (KEY, MIDYEAR, _fact(800)),
    ]
    assert _merged(tagged) == [(1000, "Total")]


def test_annual_beats_midyear_when_fdrs_missing():
    tagged = [(KEY, MIDYEAR, _fact(800)), (KEY, ANNUAL, _fact(900))]
    assert _merged(tagged) == [(900, "Total")]


def test_midyear_used_when_it_is_the_only_source():
    assert _merged([(KEY, MIDYEAR, _fact(800))]) == [(800, "Total")]


def test_fdrs_without_a_number_loses_to_unified_reporting_with_one():
    tagged = [(KEY, FDRS, _fact(None)), (KEY, ANNUAL, _fact(900))]
    assert _merged(tagged) == [(900, "Total")]


def test_flag_only_rows_kept_when_nobody_has_a_number():
    tagged = [(KEY, ANNUAL, _fact(None)), (KEY, FDRS, _fact(None))]
    assert len(merge_facts(tagged)) == 1


def test_winning_source_is_taken_whole_without_mixing_attributes():
    tagged = [
        (KEY, FDRS, _fact(1000, "Total")),
        (KEY, ANNUAL, _fact(900, "Total")),
        (KEY, ANNUAL, _fact(400, "Male")),
    ]
    assert _merged(tagged) == [(1000, "Total")]


def test_other_countries_years_and_indicators_do_not_compete():
    other_country = (2, 2024, 724)
    other_year = (1, 2025, 724)
    other_bank = (1, 2024, 727)
    tagged = [
        (KEY, FDRS, _fact(1)),
        (other_country, ANNUAL, _fact(2)),
        (other_year, ANNUAL, _fact(3)),
        (other_bank, ANNUAL, _fact(4)),
    ]
    assert sorted(v for v, _ in _merged(tagged)) == [1, 2, 3, 4]


def test_unkeyed_facts_always_pass_through():
    tagged = [(None, ANNUAL, _fact(5, indicator="Funding")), (KEY, FDRS, _fact(1))]
    assert len(merge_facts(tagged)) == 2


def test_finish_labels_data_source_and_drops_internal_keys():
    fact = _fact(1)
    fact["_bank_id"] = 724
    fact["Source"] = "Country Data"
    fdrs = _finish(dict(fact), FDRS)
    ur = _finish(dict(fact), ANNUAL)
    assert fdrs["Data source"] == SOURCE_FDRS
    assert ur["Data source"] == SOURCE_UNIFIED_REPORTING
    assert list(fdrs) == list(OVERALL_COLUMNS)


def test_fdrs_role_only_carries_bank_indicators():
    assert fdrs_role(_item(bank_id=724)) == "ns_data"
    assert fdrs_role(_item(bank_id=618, bank_name="Number of people reached")) == "core"
    assert fdrs_role(_item(bank_id=733)) == "fdrs_funding"
    assert fdrs_role(_item(bank_id=734, bank_name="Total expenditure of the National Society.")) == "expenditure"
    assert fdrs_role(_item(item_type="question", bank_id=None)) == "skip"
    assert fdrs_role(_item(item_type="matrix", bank_id=None)) == "skip"


def _by_source(tagged):
    return {rank: row for row, rank in merge_facts(tagged)}


def test_both_sources_are_shown_and_value_is_the_final_one():
    row = next(iter(merge_facts([(KEY, ANNUAL, _fact(900)), (KEY, FDRS, _fact(1000))])))[0]
    assert (row["Value"], row["FDRS Value"], row["UPR Value"]) == (1000, 1000, 900)


def test_upr_value_prefers_annual_over_midyear():
    row = next(iter(merge_facts([(KEY, MIDYEAR, _fact(800)), (KEY, ANNUAL, _fact(900)), (KEY, FDRS, _fact(1000))])))[0]
    assert row["UPR Value"] == 900


def test_fdrs_value_blank_when_only_unified_reporting_reported():
    row = next(iter(merge_facts([(KEY, ANNUAL, _fact(900))])))[0]
    assert (row["Value"], row["FDRS Value"], row["UPR Value"]) == (900, None, 900)


def test_loser_value_matches_by_attribute():
    tagged = [(KEY, FDRS, _fact(10, "Total")), (KEY, ANNUAL, _fact(7, "Total")), (KEY, ANNUAL, _fact(3, "Male"))]
    rows = [row for row, _ in merge_facts(tagged)]
    assert len(rows) == 1 and rows[0]["UPR Value"] == 7


def test_unkeyed_rows_fill_their_own_source_column():
    row = merge_facts([(None, ANNUAL, _fact(5))])[0][0]
    assert (row["FDRS Value"], row["UPR Value"]) == (None, 5)
