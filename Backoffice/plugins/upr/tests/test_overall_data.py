"""FDRS + Unified Reporting merge: FDRS first, then annual, then mid-year."""

from __future__ import annotations

from plugins.upr.overall_data import (
    OVERALL_COLUMNS,
    SOURCE_FDRS,
    SOURCE_PNS_REPORTING,
    SOURCE_UNIFIED_REPORTING,
    _COLLAPSE_KEY_FIELDS,
    _finish,
    _planning_data_source,
    fdrs_role,
    merge_facts,
)
from plugins.upr.upr_data import (
    ItemView,
    collapse_breakdowns,
    data_status_label,
    fill_entity,
    fill_section_b,
)

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


def test_columns_follow_requested_order():
    assert list(OVERALL_COLUMNS) == [
        "submission_id",
        "ISO3",
        "Year",
        "Round",
        "Data source",
        "Data status",
        "Region",
        "Country",
        "NS",
        "Section",
        "SectionB",
        "Entity",
        "Attribute",
        "Breakdown",
        "SP/EF",
        "EA Code",
        "Applicable/Data not available",
        "Indicator",
        "Indicator ID",
        "Value",
        "ValueNum",
        "FDRS Value",
        "UPR Value",
        "PNS Value",
        "PNS reported",
    ]
    assert "Source" not in OVERALL_COLUMNS
    assert "Country Value" not in OVERALL_COLUMNS


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
    assert fdrs_role(_item(bank_id=1131)) == "skip"
    assert fdrs_role(_item(bank_id=1132)) == "skip"
    assert fdrs_role(_item(id=943, item_type="matrix", bank_id=None, label="Income Sources")) == "fdrs_income_sources"
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


def test_planning_and_pns_rows_get_their_own_data_source():
    assert _planning_data_source({"Round": "P27", "Source": "Country Data"}) == "Unified Planning"
    assert _planning_data_source({"Round": "P26", "Source": "PNS Data"}) == "PNS Planning"
    assert _planning_data_source({"Round": "MYR26", "Source": "PNS Data"}) == "PNS Reporting"


def test_data_status_is_title_cased():
    assert data_status_label("pending") == "Pending"
    assert data_status_label("approved") == "Approved"
    assert data_status_label("in_progress") == "In Progress"
    assert data_status_label("requires_revision") == "Requires Revision"
    assert data_status_label(None) is None


SOURCES = (1, 2024, ("funding_sources",))


def _source(value, entity):
    row = _fact(value, attribute="Funding Source", indicator="Funding (CHF)")
    row.update({"Entity": entity, "Section": "Funding", "SectionB": "Funding"})
    return row


def test_funding_sources_are_all_or_nothing_fdrs_wins():
    tagged = [
        (SOURCES, FDRS, _source(10, "IFRC Secretariat")),
        (SOURCES, FDRS, _source(20, "Other National Society")),
        (SOURCES, FDRS, _source(5, "Home Government")),
        (SOURCES, ANNUAL, _source(100, "IFRC Secretariat")),
        (SOURCES, ANNUAL, _source(200, "Other National Society")),
        (SOURCES, ANNUAL, _source(300, "HNS other sources")),
    ]
    rows = [row for row, _ in merge_facts(tagged)]
    assert sorted(r["Entity"] for r in rows) == [
        "Home Government",
        "IFRC Secretariat",
        "Other National Society",
    ]
    by_entity = {r["Entity"]: r for r in rows}
    assert by_entity["IFRC Secretariat"]["ValueNum"] == 10
    assert by_entity["IFRC Secretariat"]["UPR Value"] == 100
    assert by_entity["Other National Society"]["UPR Value"] == 200
    assert "HNS other sources" not in by_entity


def test_funding_sources_ur_wins_when_fdrs_has_none():
    rows = [
        row
        for row, _ in merge_facts(
            [
                (SOURCES, ANNUAL, _source(100, "IFRC Secretariat")),
                (SOURCES, ANNUAL, _source(200, "Other National Society")),
                (SOURCES, ANNUAL, _source(300, "HNS other sources")),
            ]
        )
    ]
    assert sorted(r["Entity"] for r in rows) == [
        "HNS other sources",
        "IFRC Secretariat",
        "Other National Society",
    ]


def test_ur_source_entity_maps_pns_to_other_national_society():
    from plugins.upr.overall_data import _ur_source_entity

    assert _ur_source_entity("PNSs") == "Other National Society"
    assert _ur_source_entity("PNS") == "Other National Society"
    assert _ur_source_entity("IFRC Secretariat") == "IFRC Secretariat"
    assert _ur_source_entity("HNS other sources") == "HNS other sources"


def _finished_row(**overrides):
    row = {column: None for column in OVERALL_COLUMNS}
    row.update(
        {
            "submission_id": 1,
            "ISO3": "AFG",
            "Year": 2024,
            "Round": "FDRS24",
            "Data source": SOURCE_FDRS,
            "Section": "Core indicators",
            "SectionB": "Core indicators",
            "Entity": "HNS",
            "Attribute": "Total",
            "Indicator": "People reached",
            "Value": 100,
            "ValueNum": 100,
        }
    )
    row.update(overrides)
    return row


def test_disaggregation_attributes_collapse_into_breakdown_on_total():
    rows = collapse_breakdowns(
        [
            _finished_row(Attribute="Total", Value=22152, ValueNum=22152),
            _finished_row(Attribute="Direct", Value=2275, ValueNum=2275),
            _finished_row(Attribute="Indirect", Value=19887, ValueNum=19887),
            _finished_row(Attribute="Total female", Value=9000, ValueNum=9000),
            _finished_row(Attribute="Total male", Value=11000, ValueNum=11000),
            _finished_row(Attribute="Female 18-49", Value=4000, ValueNum=4000),
            _finished_row(Attribute="Other/Unknown 18-49", Value=12, ValueNum=12),
            _finished_row(Section="Support", Attribute="Supported", Indicator="Bilateral Support", Value=1, ValueNum=1),
        ],
        columns=OVERALL_COLUMNS,
        key_fields=_COLLAPSE_KEY_FIELDS,
        blank_value_fields=("Value", "ValueNum", "FDRS Value", "UPR Value"),
    )
    core = [row for row in rows if row["Indicator"] == "People reached"]
    support = [row for row in rows if row["Indicator"] == "Bilateral Support"]
    assert len(core) == 1
    assert core[0]["Attribute"] == "Total"
    assert core[0]["ValueNum"] == 22152
    assert core[0]["Breakdown"] == {
        "Direct": 2275,
        "Indirect": 19887,
        "Total female": 9000,
        "Total male": 11000,
        "Female 18-49": 4000,
        "Other/Unknown 18-49": 12,
    }
    assert len(support) == 1 and support[0]["Breakdown"] is None


def test_section_b_uses_ea_code_when_present_otherwise_section():
    funding = {"Section": "Funding", "SectionB": None}
    fill_section_b(funding)
    assert funding["SectionB"] == "Funding"

    plan = {"Section": "Activities", "SectionB": None}
    fill_section_b(plan)
    assert plan["SectionB"] == "Activities"

    emergency = {"Section": "Emergency 1", "SectionB": None, "EA Code": "MDRAF007"}
    fill_section_b(emergency)
    assert emergency["SectionB"] == "MDRAF007"

    # Plan emergency funding stays in Section Funding but SectionB is the appeal code.
    ea_funding = {
        "Section": "Funding",
        "SectionB": "Funding",
        "EA Code": "MDRIR018",
        "Attribute": "Emergency Operations",
        "SP/EF": "EA1",
    }
    fill_section_b(ea_funding)
    assert ea_funding["SectionB"] == "MDRIR018"

    reach = {
        "Section": "Reach",
        "SectionB": "Reach",
        "EA Code": "MDRIR018",
        "Attribute": "Total People to be reached",
        "SP/EF": "EA1",
    }
    fill_section_b(reach)
    assert reach["SectionB"] == "MDRIR018"

    no_code = {"Section": "Emergency 1", "SectionB": None, "EA Code": None}
    fill_section_b(no_code)
    assert no_code["SectionB"] == "Emergency 1"


def test_blank_entity_defaults_to_hns_or_pns():
    country = {"Entity": None, "Source": "Country Data"}
    fill_entity(country)
    assert country["Entity"] == "HNS"

    fdrs = {"Entity": None, "Source": "Country Data"}
    fill_entity(fdrs)
    assert fdrs["Entity"] == "HNS"

    pns = {"Entity": None, "Source": "PNS Data"}
    fill_entity(pns)
    assert pns["Entity"] == "PNS"

    kept = {"Entity": "IFRC Secretariat", "Source": "Country Data"}
    fill_entity(kept)
    assert kept["Entity"] == "IFRC Secretariat"
