"""Parser and indicator-bank matching for the MARC logframe. No database."""

from __future__ import annotations

import openpyxl
import pytest

from plugins.us_macro_awards.constants import DEFAULT_WORKBOOK
from plugins.us_macro_awards.importer.countries import CountryIndex, CountryRef
from plugins.us_macro_awards.importer.match import BankIndex, BankRow, question_type_for
from plugins.us_macro_awards.importer.workbook import load_logframe, parse_workbook

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


def test_country_aliases():
    index = CountryIndex(
        [
            CountryRef(1, "Türkiye", "TUR"),
            CountryRef(2, "Viet Nam", "VNM"),
            CountryRef(3, "Congo, Democratic Republic of the", "COD"),
            CountryRef(4, "Micronesia, Federated States of", "FSM"),
            CountryRef(5, "Syrian Arab Republic", "SYR"),
        ]
    )
    assert index.match("Türkiye").iso3 == "TUR"
    assert index.match("Turkey").iso3 == "TUR"
    assert index.match("Vietnam").iso3 == "VNM"
    assert index.match("Democratic Republic of the Congo").iso3 == "COD"
    assert index.match("Federated States of Micronesia").iso3 == "FSM"
    assert index.match("Syria").iso3 == "SYR"
    assert index.match("Not a country") is None


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
        "plugins.us_macro_awards.importer.workbook.open_workbook",
        fake_open,
    )
    parsed = load_logframe(b"not-a-real-xlsx")
    assert called["bytes"] == b"not-a-real-xlsx"
    assert parsed.indicators[0].display_code == "1"
