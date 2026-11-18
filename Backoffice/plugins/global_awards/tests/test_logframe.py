"""Parser and indicator-bank matching for the MARC logframe. No database."""

from __future__ import annotations

import openpyxl
import pytest

import datetime as dt
import json

from plugins.global_awards.constants import DEFAULT_WORKBOOK
from plugins.global_awards.importer.countries import CountryIndex, CountryRef
from plugins.global_awards.importer.match import BankIndex, BankRow, question_type_for
from plugins.global_awards.importer.schedule import (
    AWARD_END,
    AWARD_START,
    official_cycles,
    quarterly_cycles,
    relevance_for_countries,
)
from plugins.global_awards.importer.societies import pick_national_society
from plugins.global_awards.importer.workbook import load_logframe, parse_workbook

pytestmark = pytest.mark.unit


def _sheet(rows):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Logframe_Mastersheet"
    for row in rows:
        sheet.append(row)
    return workbook


def _header():
    return [
        "Code",
        "Indicator",
        "Scope",
        "Indicator source",
        "Indicator reference",
        "Definition",
        "Bangladesh",
        "Syria",
        "Total",
        "Unit of measurement",
        "Disaggregation",
        "Collection / reporting frequency",
    ]


def test_parse_places_indicators_under_the_current_heading():
    workbook = _sheet(
        [
            ["title"],
            [],
            [],
            [],
            [],
            _header(),
            ["", "Goal: Life-saving assistance.", "", "", "", "", "", "", "", "", "", ""],
            ["1", "Total number of people reached", "", "Custom", "Custom", "Unique people.", 100000, None, 100000, "People", "", ""],
            ["", "Objective 1 (Pillar 1) Rapid response: Improved preparedness.", "", "", "", "", "", "", "", "", "", ""],
            ["", "Outcome 1.1: Enhanced preparedness systems.", "", "", "", "", "", "", "", "", "", ""],
            ["", "Preparedness, Readiness and Anticipatory Action", "", "", "", "", "", "", "", "", "", ""],
            ["1.1.1", "Number of National Societies with updated plans", "", "Custom", "NA", "Plans.", 1, None, 1, "National Societies", "", ""],
            ["", "Number of National Societies able to deliver cash assistance.", "", "IFRC indicator bank", "606", "Cash capability.", None, 1, 1, "National Societies", "", ""],
            ["", "Notes to self", "", "", "", "", "", "", "", "", "", ""],
            ["", "This note must not become an indicator", "", "", "", "", "", "", "", "", "", ""],
        ]
    )
    parsed = parse_workbook(workbook)

    assert parsed.countries == ["Bangladesh", "Syria"]
    assert [section.key for section in parsed.sections] == [
        "goal",
        "outcome-1-1:preparedness-readiness-and-anticipatory-action",
    ]
    by_code = {item.display_code: item for item in parsed.indicators}
    assert by_code["1"].section_key == "goal"
    assert by_code["1"].targets["Bangladesh"] == "100000"
    assert "Syria" not in by_code["1"].targets
    assert by_code["1.1.1"].section_name.startswith("Outcome 1.1 ·")
    assert by_code["606"].cited_bank_id == 606
    assert by_code["606"].targets == {"Syria": "1"}
    assert all("note" not in item.label.casefold() for item in parsed.indicators)


def test_annex_logframe_keeps_bank_ids_and_country_targets():
    if not DEFAULT_WORKBOOK.is_file():
        pytest.skip("MARC annex workbook is not in the repository root")
    parsed = load_logframe(DEFAULT_WORKBOOK)
    codes = {item.display_code for item in parsed.indicators}
    references = {item.reference for item in parsed.indicators}
    bank_ids = {item.cited_bank_id for item in parsed.indicators if item.cited_bank_id}
    by_code = {item.display_code: item for item in parsed.indicators}

    assert "1" in codes
    assert "1.1.1" in codes
    assert "PROP-01" in codes
    assert "S01" in codes
    assert any(ref.startswith("H01") for ref in references)
    assert bank_ids == {606, 1124, 627, 624, 969}
    assert by_code["1"].targets["Bangladesh"] == "100000"
    assert "Total" not in parsed.countries
    assert "Bangladesh" in parsed.countries
    assert "Syria" in parsed.countries
    assert "Panama" in parsed.countries
    assert len(parsed.countries) == 38
    assert parsed.timeframe_note == "12 months"
    assert parsed.award is not None
    assert parsed.award.start == dt.date(2026, 9, 1)
    assert parsed.award.end == dt.date(2027, 9, 30)
    assert "Panama" not in by_code["1"].targets
    cycles = quarterly_cycles(parsed.award.start, parsed.award.end)
    assert [cycle.slot for cycle in cycles] == ["Y1Q1", "Y1Q2", "Y1Q3", "Y1Q4", "Y2Q1"]
    assert cycles[0].start == dt.date(2026, 9, 1) and cycles[0].end == dt.date(2026, 11, 30)
    assert cycles[-1].start == dt.date(2027, 9, 1) and cycles[-1].end == dt.date(2027, 9, 30)
    assert len({item.key for item in parsed.indicators}) == len(parsed.indicators)
    assert all(item.section_key for item in parsed.indicators)
    assert not any(item.label.casefold().startswith("notes to self") for item in parsed.indicators)


def test_question_type_follows_the_unit():
    assert question_type_for("People", "Number of people reached") == "number"
    assert question_type_for("Percentage", "Percentage of households") == "percentage"
    assert question_type_for("Percent", "Percent of households with a Food Consumption Score") == "percentage"
    assert question_type_for("Mean rCSI score", "Mean and median Reduced Coping Strategy Index") == "textarea"


def test_bank_id_wins_and_wording_must_be_unambiguous():
    index = BankIndex(
        [
            BankRow(606, "Number of National Societies able to deliver scalable cash and voucher assistance"),
            BankRow(7, "Total number of people reached with life-saving humanitarian assistance through the award"),
            BankRow(8, "Total number of people reached with life-saving humanitarian assistance through another award"),
            BankRow(9, "Archived twin", archived=True),
        ]
    )
    cited = index.match(
        label="Number of National Societies able to deliver scalable, timely and accountable cash and voucher assistance.",
        source="IFRC indicator bank",
        reference="606",
        cited_bank_id=606,
    )
    assert cited.linked and cited.bank_id == 606 and cited.method == "bank_id"

    exact = index.match(
        label="Total number of people reached with life-saving humanitarian assistance through the award",
        source="Custom",
        reference="Custom",
        cited_bank_id=None,
    )
    assert exact.bank_id == 7 and exact.method == "name"

    missing = index.match(
        label="Number of health facilities supported",
        source="DHR Interim Indicator List",
        reference="H01",
        cited_bank_id=None,
    )
    assert not missing.linked

    gone = index.match(
        label="Something the bank does not have",
        source="IFRC indicator bank",
        reference="99999",
        cited_bank_id=99999,
    )
    assert not gone.linked
    assert "99999" in gone.note


def test_official_reporting_calendar():
    cycles = official_cycles()
    assert [cycle.slot for cycle in cycles] == ["Y1Q1", "Y1Q2", "Y1Q3", "Final"]
    assert cycles[0].start == dt.date(2026, 9, 17) and cycles[0].end == dt.date(2026, 12, 20)
    assert cycles[0].country_due == dt.date(2027, 1, 8)
    assert cycles[0].dhr_due == dt.date(2027, 1, 30)
    assert cycles[2].start == dt.date(2027, 3, 21) and cycles[2].end == dt.date(2027, 6, 20)
    final = cycles[-1]
    assert final.kind == "final"
    assert final.start == AWARD_START == dt.date(2026, 9, 17)
    assert final.end == AWARD_END == dt.date(2027, 9, 16)
    assert final.country_due == dt.date(2027, 10, 15)
    assert final.dhr_due == dt.date(2028, 1, 14)


def test_relevance_lists_only_the_countries_with_a_target():
    rule = json.loads(relevance_for_countries(["SYR", "bgd", "SYR", ""]))
    assert rule["logic"] == "OR"
    assert [item["value"] for item in rule["conditions"]] == ["SYR", "BGD"]
    hidden = json.loads(relevance_for_countries([]))
    assert hidden["conditions"] == [
        {"item_id": "country_iso", "condition_type": "equal_to", "value": ""}
    ]


def test_country_aliases():
    index = CountryIndex(
        [
            CountryRef(1, "Türkiye", "TUR"),
            CountryRef(2, "Viet Nam", "VNM"),
            CountryRef(3, "Congo, the Democratic Republic of the", "COD"),
            CountryRef(4, "Micronesia, Federated States of", "FSM"),
            CountryRef(5, "Syrian Arab Republic", "SYR"),
            CountryRef(6, "Eswatini, the Kingdom of", "SWZ"),
        ]
    )
    assert index.match("Türkiye").iso3 == "TUR"
    assert index.match("Turkey").iso3 == "TUR"
    assert index.match("Vietnam").iso3 == "VNM"
    assert index.match("Democratic Republic of the Congo").iso3 == "COD"
    assert index.match("Federated States of Micronesia").iso3 == "FSM"
    assert index.match("Syria").iso3 == "SYR"
    assert index.match("Eswatini").iso3 == "SWZ"
    assert index.match("Not a country") is None


def test_one_active_national_society_is_chosen():
    class Society:
        def __init__(self, name, active=True):
            self.name = name
            self.is_active = active

    only = Society("Bangladesh Red Crescent Society")
    assert pick_national_society([only]) is only
    assert pick_national_society([Society("Old", active=False), only]).name == only.name
    assert pick_national_society([only, Society("Second society")]) is None
    assert pick_national_society([]) is None


def test_workbook_without_the_mastersheet_is_rejected():
    workbook = openpyxl.Workbook()
    workbook.active.title = "Read Me"
    with pytest.raises(ValueError, match="Logframe_Mastersheet"):
        parse_workbook(workbook)


def test_load_logframe_reads_bytes_only_through_the_safe_opener(monkeypatch):
    """Uploaded bytes must not reach openpyxl until the safe opener has checked them."""
    called = {}

    def fake_open(source):
        called["bytes"] = source
        return _sheet(
            [
                _header(),
                ["1", "People reached", "", "Custom", "Custom", "Def", 5, None, 5, "People", "", ""],
            ]
        )

    monkeypatch.setattr(
        "plugins.global_awards.importer.workbook.open_workbook",
        fake_open,
    )
    parsed = load_logframe(b"not-a-real-xlsx")
    assert called["bytes"] == b"not-a-real-xlsx"
    assert parsed.indicators[0].display_code == "1"
