"""Unit tests for the UPR Power BI extract. No database."""

from __future__ import annotations

from plugins.upr import upr_data
from plugins.upr.catalog import (
    PLAN_TEMPLATE_ID,
    PNS_REPORT_TEMPLATE_ID,
    REPORT_TEMPLATE_ID,
)
from plugins.upr.upr_data import (
    ItemView,
    assignment_year,
    attribute_label,
    classify_item,
    dynamic_facts,
    facts_for_item,
    iter_measure_points,
    master_comment_row,
    master_dynamic_rows,
    master_rows_for_item,
    spef_label,
    submission_row,
    system_facts_from_snapshot,
)

_PLACE = {
    "round": "MYR26",
    "iso3": "AFG",
    "country": "Afghanistan",
    "ns": "Afghan Red Crescent Society",
    "region": "Asia Pacific",
    "assigned_form_id": 10,
    "submission_id": 99,
    "template": "report",
    "period_name": "Jan-Jun 2026",
    "source": "Country Data",
}


def _item(**overrides) -> ItemView:
    fields = dict(
        id=1,
        template_id=REPORT_TEMPLATE_ID,
        item_type="indicator",
        label="People reached",
        section_name="Disasters and crises",
        bank_id=10,
        bank_name="People reached.",
        bank_area="SP2",
    )
    fields.update(overrides)
    return ItemView(**fields)


def test_assignment_year_is_an_integer_for_all_rounds():
    assert assignment_year({"period_name": "Jan-Jun 2026", "round": "MYR26"}) == 2026
    assert assignment_year({"period_name": "2025", "round": "AR25"}) == 2025
    assert assignment_year({"period_name": "2026", "round": "P26"}) == 2026
    assert assignment_year({"round": "MYR26"}) == 2026
    assert assignment_year({"round": "AR25"}) == 2025
    assert assignment_year({"round": "P26"}) == 2026
    assert isinstance(assignment_year({"round": "MYR26"}), int)


def test_classify_report_roles():
    assert classify_item(_item(bank_id=724, label="National Society volunteers")) == "ns_data"
    assert classify_item(_item(bank_name="Total expenditure of the National Society.")) == "expenditure"
    assert classify_item(_item(label="Received support", item_type="matrix", id=1407)) == "support"
    assert classify_item(_item(label="NS total funding (CHF)", item_type="matrix", id=1403)) == "funding"
    assert classify_item(_item(item_type="question", section_name="Comments")) == "comment"
    assert classify_item(_item()) == "core"


def test_classify_plan_prefers_emergency_over_reach_wording():
    emergency = _item(
        template_id=PLAN_TEMPLATE_ID,
        item_type="matrix",
        id=960,
        label="People to be reached by emergency appeal",
        bank_id=None,
        bank_name=None,
        bank_area=None,
    )
    reach = _item(
        template_id=PLAN_TEMPLATE_ID,
        item_type="matrix",
        id=954,
        label="People to be reached by longer term programme",
        bank_id=None,
        bank_name=None,
        bank_area=None,
    )
    funding = _item(
        template_id=PLAN_TEMPLATE_ID,
        item_type="matrix",
        id=967,
        label="Funding requirement [assignment_period]",
        bank_id=None,
        bank_name=None,
        bank_area=None,
    )
    assert classify_item(emergency) == "emergency"
    assert classify_item(reach) == "reach"
    assert classify_item(funding) == "plan_funding"


def test_classify_pns_matrix_and_skip_staff():
    matrix = _item(
        template_id=PNS_REPORT_TEMPLATE_ID,
        item_type="matrix",
        label="",
        bank_id=None,
        bank_name=None,
        bank_area=None,
    )
    staff = _item(template_id=PNS_REPORT_TEMPLATE_ID, item_type="matrix", label="PNS staff on delegates")
    assert classify_item(matrix) == "pns_funding"
    assert classify_item(staff) == "skip"


def test_disagg_total_is_not_duplicated_and_labels_are_stable():
    points = list(
        iter_measure_points(
            "12",
            {"mode": "sex", "values": {"total": 12, "male": 7, "female__5": 2}},
        )
    )
    assert points == [("Total", 12.0), ("Total male", 7.0), ("Female <5", 2.0)]
    assert attribute_label("male_50_") == "Male 50+"


def test_other_indicator_yes_becomes_one_and_no_is_dropped():
    yes = dynamic_facts(
        _PLACE,
        indicator="A custom indicator.",
        area="CC1",
        value="yes",
        disagg=None,
        data_not_available=False,
        not_applicable=False,
        section_name="Other indicators",
        appeal_code=None,
        slot=None,
    )
    no = dynamic_facts(
        _PLACE,
        indicator="A custom indicator",
        area=None,
        value="no",
        disagg=None,
        data_not_available=False,
        not_applicable=False,
        section_name="Other indicators",
        appeal_code=None,
        slot=None,
    )
    assert yes[0]["Table"] == "Other indicators"
    assert yes[0]["Value"] == 1
    assert yes[0]["SP/EF"] == "Cross-cutting"
    assert yes[0]["Indicator"] == "A custom indicator"
    assert no == []
    assert spef_label("CC1") == "Cross-cutting"


def test_emergency_dynamic_uses_appeal_code_not_section_order_guess():
    rows = dynamic_facts(
        _PLACE,
        indicator="People reached",
        area="SP2",
        value="4",
        disagg=None,
        data_not_available=False,
        not_applicable=False,
        section_name="Emergency operations",
        appeal_code="MDRAF015",
        slot=2,
    )
    assert rows[0]["Table"] == "Emergency 2"
    assert rows[0]["SectionB"] == "MDRAF015"
    assert rows[0]["EA Code"] == "MDRAF015"
    assert rows[0]["SP/EF"] == "SP2"


def test_not_applicable_emits_a_status_row_without_a_value():
    rows = facts_for_item(
        _item(),
        "core",
        _PLACE,
        value=None,
        disagg=None,
        not_applicable=True,
    )
    assert len(rows) == 1
    assert rows[0]["Applicable/Data not available"] == "Not Applicable"
    assert rows[0]["Value"] is None
    assert rows[0]["Table"] == "Core indicators"
    assert rows[0]["Indicator"] == "People reached"
    assert rows[0]["Year"] == 2026


def test_support_matrix_splits_column_and_skips_total():
    rows = facts_for_item(
        _item(id=1407, item_type="matrix", label="Received support"),
        "support",
        _PLACE,
        value=None,
        disagg={"mode": "matrix", "values": {"7_SP1 Supported": 1, "7_Total": 5, "8_SP2 Supported": 0}},
        ns_by_id={7: "German Red Cross"},
    )
    assert len(rows) == 1
    assert rows[0]["NS"] == "German Red Cross"
    assert rows[0]["Entity"] == "PNS"
    assert rows[0]["SP/EF"] == "SP1"
    assert rows[0]["Attribute"] == "Supported"
    assert rows[0]["Table"] == "Support"
    assert rows[0]["Value"] == 1


def test_funding_matrix_maps_entity_and_sp_breakdown():
    rows = facts_for_item(
        _item(id=1403, item_type="matrix", label="NS total funding (CHF)"),
        "funding",
        _PLACE,
        value=None,
        disagg={
            "mode": "matrix",
            "values": {
                "IFRC Secretariat_Funding (CHF)": 1000,
                "Resilience - Climate and environment_Funding (CHF)": 250,
                "_Total": 9,
            },
        },
    )
    by_attr = {row["Attribute"]: row for row in rows}
    assert by_attr["Funding Source"]["Entity"] == "IFRC Secretariat"
    assert by_attr["Funding Source"]["Indicator"] == "Funding"
    assert by_attr["Funding Source"]["Value"] == 1000
    assert by_attr["SP Breakdown"]["SP/EF"] == "SP1"
    assert by_attr["SP Breakdown"]["Value"] == 250


def test_plan_funding_year_follows_the_item_when_the_label_has_no_offset():
    place = {**_PLACE, "template": "plan", "round": "P26", "period_name": "2026"}
    item = _item(
        template_id=PLAN_TEMPLATE_ID,
        item_type="matrix",
        id=968,
        label="Funding requirement",
        bank_id=None,
        bank_name=None,
        bank_area=None,
    )
    rows = facts_for_item(
        item,
        "plan_funding",
        place,
        value=None,
        disagg={"mode": "matrix", "values": {"HNS_SP1": 80}},
    )
    assert rows[0]["Table"] == "FR_Country"
    assert rows[0]["Year"] == 2027
    assert rows[0]["Entity"] == "HNS"
    assert rows[0]["NS"] == "Afghan Red Crescent Society"
    assert rows[0]["SP/EF"] == "SP1"


def test_planning_emergency_numbers_and_ea_code():
    place = {**_PLACE, "template": "plan", "round": "P26", "period_name": "2026"}
    item = _item(
        template_id=PLAN_TEMPLATE_ID,
        item_type="matrix",
        id=960,
        label="People to be reached by emergency appeal",
        bank_area=None,
    )
    index: dict[tuple[int, str], int] = {}
    disagg = {
        "mode": "matrix",
        "values": {
            "Floods (MDRAF015)_SP2": 10,
            "Earthquake (MDRAF016)_SP1": 4,
        },
    }
    rows = facts_for_item(item, "emergency", place, value=None, disagg=disagg, emergency_index=index)
    assert [row["Attribute"] for row in rows] == ["E1", "E2"]
    assert [row["EA Code"] for row in rows] == ["MDRAF015", "MDRAF016"]
    assert rows[0]["Table"] == "Emergencies"
    assert rows[0]["Year"] == 2026
    assert rows[0]["SectionB"] is None


def test_submission_round_comes_from_period_and_approved_is_validated():
    approved = submission_row(_PLACE, status="approved", submitted_at=None, due_date=None)
    pending = submission_row({**_PLACE, "round": "AR25"}, status="submitted", submitted_at=None, due_date=None)
    assert approved["Round"] == "MYR26"
    assert approved["fds_validated"] == "Validated"
    assert pending["fds_validated"] is None


def test_build_submissions_returns_sorted_country_statuses_for_all_rounds(monkeypatch):
    places = [
        {
            **_PLACE,
            "round": "MYR26",
            "status": "submitted",
            "country_id": 1,
            "ns": None,
        },
        {
            **_PLACE,
            "round": "AR25",
            "status": "approved",
            "assigned_form_id": 9,
            "submission_id": 98,
            "country_id": 1,
            "ns": None,
        },
    ]
    monkeypatch.setattr(upr_data, "_load_places", lambda *args, **kwargs: places)
    monkeypatch.setattr(
        upr_data,
        "_load_national_societies",
        lambda: ({}, {1: "Afghan Red Crescent Society"}, {}),
    )

    rows = upr_data.build_upr_submissions()["data"]

    assert [row["Round"] for row in rows] == ["AR25", "MYR26"]
    assert [row["status"] for row in rows] == ["approved", "submitted"]
    assert rows[0]["fds_validated"] == "Validated"
    assert all(row["NS"] == "Afghan Red Crescent Society" for row in rows)


def test_system_snapshot_skips_small_amounts_and_repeats_each_round():
    payload = {
        "rounds": ["MYR26", "AR26"],
        "period_names": ["Jan-Jun 2026"],
        "by_iso2": {
            "AF": {
                "country": "Afghanistan",
                "iso3": "AFG",
                "longer_term": {"funding": 500, "expenditure": 2200},
                "emergency": {"funding": 3000},
            },
            "TS": {"country": "Testland", "iso3": "TST", "longer_term": {"funding": 9000}},
        },
    }
    rows = system_facts_from_snapshot(payload, regions_by_iso3={"AFG": "Asia Pacific"})
    assert {(row["Round"], row["Indicator"], row["Attribute"], row["Value"]) for row in rows} == {
        ("MYR26", "Expenditure", "Longer-term", 2200),
        ("MYR26", "Funding", "Emergency Operations", 3000),
        ("AR26", "Expenditure", "Longer-term", 2200),
        ("AR26", "Funding", "Emergency Operations", 3000),
    }
    assert all(row["ISO3"] == "AFG" for row in rows)
    assert all(row["Entity"] == "IFRC Secretariat" for row in rows)
    assert all(row["Source"] == "IFRC System" for row in rows)
    assert rows[0]["Region"] == "Asia Pacific"
    filtered = system_facts_from_snapshot(payload, rounds=["AR26"])
    assert {row["Round"] for row in filtered} == {"AR26"}


def test_master_sheet_keeps_one_total_and_uses_area():
    rows = master_rows_for_item(
        _item(bank_id=619),
        "core",
        _PLACE,
        value="12",
        disagg={"mode": "sex", "values": {"total": 12, "male": 7, "female": 5}},
    )
    assert len(rows) == 1
    assert rows[0]["Section"] == "Core indicators"
    assert rows[0]["Area"] == "SP2"
    assert rows[0]["Attribute"] == "Total"
    assert rows[0]["ValueNum"] == 12
    assert rows[0]["indicatorId"] == 619
    assert rows[0]["Country Value"] is None
    assert rows[0]["Year"] == 2026
    assert "SP/EF" not in rows[0]


def test_master_funding_source_sets_country_value():
    rows = master_rows_for_item(
        _item(id=1403, item_type="matrix", label="NS total funding (CHF)"),
        "funding",
        _PLACE,
        value=None,
        disagg={
            "mode": "matrix",
            "values": {
                "IFRC Secretariat_Funding (CHF)": 815093,
                "Resilience - Climate and environment_Expenditure (CHF)": 250,
            },
        },
    )
    by_attr = {(row["Attribute"], row["Indicator"]): row for row in rows}
    source = by_attr[("Funding Source", "Funding")]
    assert source["Area"] == "Total"
    assert source["Entity"] == "IFRC Secretariat"
    assert source["indicatorId"] == 733
    assert source["Country Value"] == 815093
    assert source["ValueNum"] == 815093
    breakdown = by_attr[("SP Breakdown", "Expenditure")]
    assert breakdown["Area"] == "SP1"
    assert breakdown["indicatorId"] == 734


def test_master_plan_funding_and_reach_emergency():
    place = {**_PLACE, "template": "plan", "round": "P26", "period_name": "2026"}
    funding = master_rows_for_item(
        _item(template_id=PLAN_TEMPLATE_ID, item_type="matrix", id=968, label="Funding requirement", bank_id=None, bank_name=None, bank_area=None),
        "plan_funding",
        place,
        value=None,
        disagg={"mode": "matrix", "values": {"HNS_SP1": 80}},
    )
    assert funding[0]["Section"] == "Funding"
    assert funding[0]["Indicator"] == "Funding Requirement"
    assert funding[0]["indicatorId"] == 2
    assert funding[0]["Year"] == 2027
    assert funding[0]["Area"] == "SP1"
    assert funding[0]["Country Value"] == 80

    index: dict[tuple[int, str], int] = {}
    reach = master_rows_for_item(
        _item(template_id=PLAN_TEMPLATE_ID, item_type="matrix", id=960, label="People to be reached by emergency appeal", bank_id=None, bank_area=None),
        "emergency",
        place,
        value=None,
        disagg={"mode": "matrix", "values": {"Floods (MDRAF015)_SP2": 10}},
        emergency_index=index,
    )
    assert reach[0]["Section"] == "Reach"
    assert reach[0]["Area"] == "EA1"
    assert reach[0]["EA Code"] == "MDRAF015"
    assert reach[0]["ValueNum"] == 10


def test_master_comment_and_other_indicator_and_pns_host():
    comment = master_comment_row(_PLACE, _item(item_type="question", label="Comments_reach", bank_id=None, bank_name=None), "Noted")
    assert comment["Section"] == "Comments"
    assert comment["Value"] == "Noted"
    assert comment["UPR Value"] == "Noted"
    assert comment["ValueNum"] is None
    assert comment["Year"] == 2026

    other = master_dynamic_rows(
        _PLACE,
        indicator="A custom indicator.",
        indicator_id=500,
        area="CC1",
        value="yes",
        disagg={"values": {"male": 1}},
        data_not_available=False,
        not_applicable=False,
        appeal_code=None,
        slot=None,
    )
    assert len(other) == 1
    assert other[0]["Section"] == "Other indicators"
    assert other[0]["Area"] == "Cross-cutting"
    assert other[0]["indicatorId"] == 500
    assert other[0]["ValueNum"] == 1
    assert other[0]["Year"] == 2026

    pns_place = {**_PLACE, "template": "pns", "iso3": "GBR", "country": "United Kingdom", "ns": "British Red Cross", "status": "approved", "source": "PNS Data"}
    pns = master_rows_for_item(
        _item(template_id=PNS_REPORT_TEMPLATE_ID, item_type="matrix", label="PNS funding", bank_id=None, bank_name=None, bank_area=None),
        "pns_funding",
        pns_place,
        value=None,
        disagg={"mode": "matrix", "values": {"42_Total Funding": 900}},
        ns_country_by_id={42: {"iso3": "AFG", "country": "Afghanistan"}},
    )
    assert pns[0]["ISO3"] == "AFG"
    assert pns[0]["Country"] == "Afghanistan"
    assert pns[0]["NS"] == "British Red Cross"
    assert pns[0]["Entity"] == "PNS"
    assert pns[0]["Source"] == "PNS Data"
    assert pns[0]["PNS Value"] == 900
    assert pns[0]["PNS reported"] == "Yes"
    assert pns[0]["indicatorId"] == 733
