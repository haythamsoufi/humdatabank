"""Unit tests for UPR visuals formatters, catalog, and HTML render."""

from __future__ import annotations

from datetime import date

import pytest

from plugins.upr_visuals.catalog import (
    PLAN_TEMPLATE_ID,
    REACH_CODES,
    REPORT_TEMPLATE_ID,
    SUPPORT_DOT_COLORS,
    dashboards_for_kind,
    display_ns_name,
    kind_for_template,
    section_to_area,
)
from plugins.upr_visuals.formatters import (
    appeal_number,
    document_subtitle,
    format_chf,
    format_compact_chf,
    format_count,
    format_header_date,
    period_to_round,
    planning_years,
    to_number,
)
from plugins.upr_visuals.render import render_dashboard_html, render_dashboards_html


@pytest.mark.unit
def test_kind_for_template():
    assert kind_for_template(PLAN_TEMPLATE_ID) == "plan"
    assert kind_for_template(REPORT_TEMPLATE_ID) == "report"


@pytest.mark.unit
def test_dashboards_for_plan_exclude_emergencies():
    ids = [spec.id for spec in dashboards_for_kind("plan")]
    assert "combined" in ids
    assert "in_support" in ids
    assert "network_funding" in ids
    assert "financial" in ids
    assert "emergency_1" not in ids
    assert "strategic_priorities" not in ids
    assert "enabling_functions" not in ids
    assert ids[-1] == "support"


@pytest.mark.unit
def test_dashboards_for_report_include_emergencies():
    ids = [spec.id for spec in dashboards_for_kind("report")]
    assert "emergency_1" in ids
    assert "emergency_3" in ids
    assert "strategic_priorities" in ids
    assert "enabling_functions" in ids
    assert "network_funding" not in ids
    assert ids.index("emergency_1") < ids.index("strategic_priorities")
    assert ids.index("emergency_3") < ids.index("strategic_priorities")
    assert ids.index("strategic_priorities") < ids.index("enabling_functions")
    assert ids[-1] == "support"


@pytest.mark.unit
def test_dashboards_omit_empty_emergency_slots():
    ids = {spec.id for spec in dashboards_for_kind("report", emergency_slots=set())}
    assert "emergency_1" not in ids
    assert "emergency_2" not in ids
    assert "financial" in ids
    only_first = {spec.id for spec in dashboards_for_kind("report", emergency_slots={1})}
    assert "emergency_1" in only_first
    assert "emergency_2" not in only_first


@pytest.mark.unit
def test_display_ns_name_aliases():
    assert display_ns_name("The Netherlands Red Cross") == "Netherlands Red Cross"
    assert display_ns_name("Afghan Red Crescent Society") == "Afghan Red Crescent Society"


@pytest.mark.unit
def test_section_to_area():
    assert section_to_area("Resilience - Climate and environment") == "SP1"
    assert section_to_area("Cross Cutting") == "CC1"
    assert section_to_area("Unknown section") is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        ("", None),
        ("1,234", 1234.0),
        (12, 12.0),
        ("Not reported", None),
    ],
)
def test_to_number(raw, expected):
    assert to_number(raw) == expected


@pytest.mark.unit
def test_format_count_and_chf():
    assert format_count(26000) == "26,000"
    assert format_count(None) == "Not reported"
    assert format_chf(1500000) == "1,500,000"


@pytest.mark.unit
def test_format_compact_chf_matches_tableau():
    assert format_compact_chf(0) == ""
    assert format_compact_chf(500) == "500"
    assert format_compact_chf(242000) == "242,000"
    assert format_compact_chf(1_000) == "1,000"
    assert format_compact_chf(6_700_000) == "6.7M"
    assert format_compact_chf(2_000_000) == "2M"


@pytest.mark.unit
def test_period_to_round():
    assert period_to_round("2026", "plan") == "P26"
    assert period_to_round("2025", "report") == "AR25"
    assert period_to_round("Jan-Jun 2026", "report") == "MYR26"
    assert planning_years("2026") == [2026, 2027, 2028]
    assert "CC1" not in REACH_CODES
    assert format_header_date(date(2026, 7, 2)) == "2 July 2026"
    assert document_subtitle("plan", "2026") == "2026-2028 IFRC network country plan"
    assert document_subtitle("report", "2025") == "2025 IFRC network annual report, Jan-Dec"
    assert document_subtitle("report", "Jan-Jun 2026") == "2026 IFRC network mid-year report, Jan-Jun"
    assert appeal_number("UG") == "MAAUG001"
    assert appeal_number("bd") == "MAABD001"
    assert appeal_number("UGA") == ""
    assert appeal_number("") == ""


def _payload():
    return {
        "meta": {
            "aes_id": 4428,
            "kind": "plan",
            "period_name": "2026",
            "round_code": "P26",
            "country_name": "Uganda",
            "iso2": "UG",
            "national_society": "Uganda Red Cross Society",
            "year": 2026,
            "plan_years": [2026, 2027, 2028],
            "people_title": "People to be reached in 2026",
            "support_title": "Participating National Societies bilateral support",
            "header_prefix": "In support of",
            "header_date": "2 July 2026",
            "document_subtitle": "2026-2028 IFRC network country plan",
        },
        "kpis": {
            "branches": {"label": "Branches", "display": "34"},
            "staff": {"label": "Staff", "display": "4,000"},
            "volunteers": {"label": "Volunteers", "display": "26,000"},
            "local_units": {"label": "Local units", "display": "329"},
        },
        "people_reached": [
            {"code": "SP1", "label": "Climate and environment", "display": "50,000", "has_value": True},
            {"code": "SP2", "label": "Disasters and crises", "display": "200,000", "has_value": True},
            {
                "code": "TOTAL",
                "label": "People to be reached",
                "display": "91,000",
                "has_value": True,
                "is_total": True,
            },
        ],
        "financial": {
            "ifrc_network": {"funding_requirement": 20_200_000, "funding_requirement_display": "20.2M"},
            "cover_sources": [
                {
                    "entity": "HNS",
                    "label": "Through Host National Society",
                    "display": "19.1M",
                    "value": 19_100_000,
                },
                {
                    "entity": "IFRC Secretariat",
                    "label": "Through the IFRC",
                    "display": "1.1M",
                    "value": 1_100_000,
                },
            ],
            "sources": [
                {"entity": "IFRC Secretariat", "label": "IFRC Secretariat", "display": "1.1M", "value": 1_100_000},
            ],
            "years": [
                {"year": 2026, "total": 20_200_000, "total_display": "20.2M"},
                {"year": 2027, "total": 6_700_000, "total_display": "6.7M"},
                {"year": 2028, "total": 4_200_000, "total_display": "4.2M"},
            ],
            "area_years": [
                {
                    "year": 2026,
                    "by_entity": {
                        "HNS": {
                            "SP1": 1_000_000,
                            "SP2": 500_000,
                            "SP3": 0,
                            "SP4": 0,
                            "SP5": 0,
                            "EFs": 200_000,
                            "emergency": 0,
                            "total": 1_700_000,
                        },
                        "IFRC Secretariat": {
                            "SP1": 100_000,
                            "SP2": 0,
                            "SP3": 0,
                            "SP4": 0,
                            "SP5": 0,
                            "EFs": 0,
                            "emergency": 30_000_000,
                            "total": 100_000,
                        },
                    },
                },
                {
                    "year": 2027,
                    "by_entity": {
                        "HNS": {
                            "SP1": 800_000,
                            "SP2": 0,
                            "SP3": 0,
                            "SP4": 0,
                            "SP5": 0,
                            "EFs": 0,
                            "total": 800_000,
                        },
                        "IFRC Secretariat": {
                            "SP1": 0,
                            "SP2": 0,
                            "SP3": 0,
                            "SP4": 0,
                            "SP5": 0,
                            "EFs": 0,
                            "total": 0,
                        },
                    },
                },
            ],
        },
        "support": [
            {
                "ns_id": 7,
                "name": "Netherlands Red Cross",
                "year": 2026,
                "funding_display": "1.2M",
                "confirmed_display": "",
                "areas": {"SP1": True, "SP2": False, "SP3": True, "SP4": False, "SP5": False, "EFs": True},
                "area_amounts": {"SP1": 1_200_000, "SP3": None, "EFs": None},
            }
        ],
        "emergencies": [],
        "dashboards": [{"id": "combined", "title": "Country visual"}],
    }


@pytest.mark.unit
def test_render_in_support_header():
    html = render_dashboard_html(_payload(), "in_support")
    assert "In support of Uganda Red Cross Society" in html
    assert "IN SUPPORT OF UGANDA RED CROSS SOCIETY" not in html
    assert html.find("Branches") < html.find("Staff")
    assert html.find("Staff") < html.find("Volunteers")
    assert html.find("Volunteers") < html.find("Local units")
    assert "&lt;" not in html
    assert "26,000" in html
    assert "icons/kpi-independence.png" in html
    assert "icons/kpi-unity.png" in html
    assert "icons/kpi-voluntary-service.png" in html
    assert "fas fa-" not in html


@pytest.mark.unit
def test_render_report_in_support_header():
    payload = _payload()
    payload["meta"]["kind"] = "report"
    payload["meta"]["header_prefix"] = "IN SUPPORT OF"
    payload["kpis"] = {
        "branches": {"label": "Local Branches", "display": "34"},
        "local_units": {"label": "Local Units", "display": "329"},
        "volunteers": {"label": "Volunteers", "display": "26,000"},
        "staff": {"label": "Paid Staff", "display": "4,000"},
    }
    html = render_dashboard_html(payload, "in_support")
    assert "IN SUPPORT OF UGANDA RED CROSS SOCIETY" in html
    assert html.find("Local Branches") < html.find("Local Units")
    assert html.find("Local Units") < html.find("Volunteers")
    assert html.find("Volunteers") < html.find("Paid Staff")


@pytest.mark.unit
def test_render_reach_and_support():
    html = render_dashboard_html(_payload(), "reach")
    assert "People to be reached in 2026" in html
    assert "upr-block--reach" in html
    assert "upr-reach-headline" in html
    assert "91,000" in html
    assert "Climate and environment" in html
    assert "Disasters and crises" in html
    assert "Cross-cutting" not in html
    assert "upr-reach-band--labels" in html
    assert "upr-reach-band--icons" in html
    assert "upr-reach-band--values" in html
    assert "upr-reach-divider" not in html
    assert "upr-reach-row--full" not in html
    with_eo = _payload()
    with_eo["people_reached"].insert(
        0,
        {
            "code": "EO",
            "label": "Emergency Operations",
            "display": "8,000",
            "has_value": True,
            "icon_src": "/upr-visuals/static/icons/eo-emergency.png",
        },
    )
    eo_html = render_dashboard_html(with_eo, "reach")
    assert "upr-reach-row--eo-split" in eo_html
    assert "upr-reach-divider" in eo_html
    assert "upr-reach-cell--eo" in eo_html
    assert eo_html.find("Emergency Operations") < eo_html.find("upr-reach-divider")
    assert eo_html.find("upr-reach-divider") < eo_html.find("Climate and environment")


@pytest.mark.unit
def test_reach_full_row_packs_when_all_icons_present():
    payload = _payload()
    payload["people_reached"] = [
        {"code": "EO", "label": "Emergency Operations", "display": "1", "has_value": True},
        {"code": "SP1", "label": "Climate and environment", "display": "3", "has_value": True},
        {"code": "SP2", "label": "Disasters and crises", "display": "4", "has_value": True},
        {"code": "SP3", "label": "Health and wellbeing", "display": "5", "has_value": True},
        {"code": "SP4", "label": "Migration and displacement", "display": "6", "has_value": True},
        {"code": "SP5", "label": "Values, power and inclusion", "display": "7", "has_value": True},
    ]
    html = render_dashboard_html(payload, "reach")
    assert "upr-reach-row--full" in html
    assert "upr-reach-row--eo-split" in html
    catalog = _payload()
    catalog["people_reached"][0]["icon_src"] = "https://example.test/sp1.png"
    catalog_html = render_dashboard_html(catalog, "reach")
    assert "upr-reach-icon--img" in catalog_html
    assert "https://example.test/sp1.png" in catalog_html
    support = render_dashboard_html(_payload(), "support")
    assert "Netherlands Red Cross" in html or "Netherlands Red Cross" in support
    assert "Participating National Societies bilateral support" in support
    assert "upr-dot--on" not in support
    assert "upr-support-fill--on" in support
    assert "upr-support-table--plan" in support
    assert ">Year</th>" in support
    assert "Confirmed<br>Funding" in support
    assert "2026" in support
    assert "Funding<br>Requirement" in support
    report_payload = _payload()
    report_payload["meta"]["kind"] = "report"
    report_payload["meta"]["people_title"] = "People reached"
    report_payload["meta"]["support_title"] = "IFRC Network-Supported Activities"
    report_payload["meta"]["support_funding_label"] = "Funding Reported"
    report_payload["support_total"] = {"value": 1_200_000, "display": "1.2M"}
    report_html = render_dashboard_html(report_payload, "support")
    assert "Funding<br>Reported" in report_html
    assert "1.2M" in report_html
    assert "Total Funding Reported" not in report_html
    assert "CHF 1.2M" in report_html
    assert "upr-support-total" in report_html
    assert "upr-support-total-row" in report_html
    assert "upr-support-total-gap" not in report_html
    assert "<td class='upr-ns'>Total</td>" in report_html
    assert "upr-num" in report_html
    assert "<tfoot>" in report_html
    assert "upr-support-totals" not in report_html
    assert "upr-dot--on" in report_html
    assert "upr-support-fill--on" not in report_html
    assert ">Year</th>" not in report_html
    assert "Confirmed Funding" not in report_html
    empty_funding = _payload()
    empty_funding["support"][0]["funding_display"] = ""
    empty_html = render_dashboard_html(empty_funding, "support")
    assert "<td class='upr-num'>&nbsp;</td>" in empty_html
    assert "upr-support-total" in empty_html
    report_reach = render_dashboard_html(report_payload, "reach")
    assert "PEOPLE REACHED" in report_reach
    assert "upr-reach-headline" not in report_reach


@pytest.mark.unit
def test_support_table_uses_spef_dot_colors():
    payload = _payload()
    payload["meta"]["kind"] = "report"
    payload["support"][0]["areas"] = {
        "SP1": True,
        "SP2": True,
        "SP3": True,
        "SP4": True,
        "SP5": True,
        "EFs": True,
    }
    html = render_dashboard_html(payload, "support")
    assert "upr-dot--on" in html
    assert "Climate and<br>environment" in html
    assert "upr-support-th--plan" not in html
    assert "upr-support-fill--on" not in html
    for code, color in SUPPORT_DOT_COLORS.items():
        assert f"background:{color}" in html, code
    assert "#6ba543" not in html
    assert "#e30613" not in html


@pytest.mark.unit
def test_plan_support_fills_cells_and_years():
    payload = _payload()
    payload["support"] = [
        {
            "ns_id": 1,
            "name": "British Red Cross",
            "year": 2026,
            "funding_display": "1M",
            "confirmed_display": "400,000",
            "confirmed": 400_000,
            "areas": {"SP1": True, "SP2": False, "SP3": False, "SP4": False, "SP5": False, "EFs": False},
            "area_amounts": {"SP1": 1_000_000},
        },
        {
            "ns_id": 1,
            "name": "British Red Cross",
            "year": 2027,
            "funding_display": "2M",
            "confirmed_display": "",
            "areas": {"SP1": True, "SP2": False, "SP3": False, "SP4": False, "SP5": False, "EFs": False},
            "area_amounts": {},
        },
        {
            "ns_id": 49,
            "name": "Danish Red Cross",
            "year": 2026,
            "funding_display": "5.2M",
            "confirmed_display": "",
            "areas": {"SP1": True, "SP2": True, "SP3": True, "SP4": True, "SP5": True, "EFs": True},
            "area_amounts": {},
        },
    ]
    payload["support_total"] = {"value": 8_200_000, "display": "8.2M"}
    html = render_dashboard_html(payload, "support")
    assert "rowspan='2'" in html
    assert html.count("British Red Cross") == 1
    assert html.count("Danish Red Cross") == 1
    assert ">2026<" in html or "2026" in html
    assert "2027" in html
    assert "upr-support-fill--on" in html
    assert "upr-dot--on" not in html
    assert ">-</td>" in html
    assert "1M" in html
    assert "400,000" in html
    assert "CHF 8.2M" in html
    for color in SUPPORT_DOT_COLORS.values():
        assert f"background:{color}" in html


@pytest.mark.unit
def test_render_plan_combined_matches_inp_cover():
    html = render_dashboard_html(_payload(), "combined")
    assert "upr-doc-header" in html
    assert "/static/IFRC_logo_square.svg" in html
    assert "upr-doc-header__logo" in html
    assert "ns-logo" not in html
    assert "UGANDA" in html
    assert "2026-2028 IFRC network country plan" in html
    assert "2 July 2026" in html
    assert "In support of Uganda Red Cross Society" in html
    assert "People to be reached in 2026" in html
    assert "IFRC network Funding Requirements" in html
    assert "Through Host National Society" in html
    assert "Through the IFRC" in html
    assert "Projected funding requirements" in html
    assert "19.1M CHF" in html
    assert "Participating National Societies" in html
    assert "Detailed funding requirements" in html
    assert "IFRC Network-Supported Activities" not in html
    assert "Enabling local actors" in html
    assert "FINANCIAL OVERVIEW" not in html
    assert "Strategic Priorities" not in html
    assert html.count("upr-combined-section") >= 6
    assert html.find("Detailed funding requirements") < html.find("upr-support-table")
    assert "ONGOING EMERGENCY INDICATORS" not in html
    assert "font-size:3.15rem" in html
    assert "upr-doc-header__country--long" not in html


@pytest.mark.unit
def test_cover_country_type_shrinks_long_names():
    from plugins.upr_visuals.render import _cover_country_type

    short_size, _, short_extra = _cover_country_type("UGANDA")
    mid_size, _, _ = _cover_country_type("BOSNIA AND HERZEGOVINA")
    long_size, _, long_extra = _cover_country_type("LAO PEOPLE'S DEMOCRATIC REPUBLIC")
    wrap_size, _, wrap_extra = _cover_country_type(
        "UNITED KINGDOM OF GREAT BRITAIN AND NORTHERN IRELAND"
    )
    assert short_size == "3.15rem"
    assert float(mid_size.removesuffix("rem")) < float(short_size.removesuffix("rem"))
    assert float(long_size.removesuffix("rem")) < float(mid_size.removesuffix("rem"))
    assert not short_extra
    assert "upr-doc-header__country--long" in wrap_extra
    payload = _payload()
    payload["meta"]["country_name"] = "Democratic Republic of the Congo"
    html = render_dashboard_html(payload, "combined")
    assert "DEMOCRATIC REPUBLIC OF THE CONGO" in html
    assert "font-size:3.15rem" not in html
    assert "font-size:" in html
    assert "upr-doc-footer" in html
    assert "Appeal number <strong>MAAUG001</strong>" in html
    assert "*Information on data scope and limitations is available on the back page" in html
    assert "International Federation of Red Cross and Red Crescent Societies" in html


@pytest.mark.unit
def test_render_combined_includes_ns_logo_when_src_set():
    payload = _payload()
    payload["meta"]["ns_logo_src"] = "/api/v1/uploads/ns/UGA.png"
    html = render_dashboard_html(payload, "combined")
    assert "upr-doc-header__ns-logo" in html
    assert "/api/v1/uploads/ns/UGA.png" in html
    assert "upr-doc-header__logo" in html


@pytest.mark.unit
def test_render_report_combined_keeps_tableau_overview():
    payload = _payload()
    payload["meta"]["kind"] = "report"
    payload["meta"]["header_prefix"] = "IN SUPPORT OF"
    payload["meta"]["people_title"] = "People reached"
    payload["meta"]["document_subtitle"] = "2025 IFRC network annual report, Jan-Dec"
    payload["meta"]["header_date"] = "2 July 2026"
    html = render_dashboard_html(payload, "combined")
    assert "IN SUPPORT OF UGANDA RED CROSS SOCIETY" in html
    assert "upr-doc-header" in html
    assert "AFGHANISTAN" not in html
    assert "UGANDA" in html
    assert "2025 IFRC network annual report, Jan-Dec" in html
    assert "/static/IFRC_logo_square.svg" in html
    assert "upr-doc-header__logo" in html
    assert html.count("upr-doc-header__logo") == 1
    assert "FINANCIAL OVERVIEW" in html
    assert "upr-combined-section--finance" in html
    assert "upr-fin-cover" in html
    assert "IFRC network Funding Requirements" not in html
    assert "2026-2028 IFRC network country plan" not in html
    in_support = render_dashboard_html(payload, "in_support")
    assert "upr-doc-header" not in in_support
    assert "upr-doc-footer" not in in_support


@pytest.mark.unit
def test_render_report_combined_orders_emergency_before_indicators_and_support_last():
    payload = _payload()
    payload["meta"]["kind"] = "report"
    payload["meta"]["support_title"] = "IFRC Network-Supported Activities"
    payload["core_indicators"] = [
        {"code": "SP1", "label": "People reached with climate activities", "value": 100, "display": "100", "kind": "number"},
    ]
    payload["enabling_indicators"] = [
        {"code": "EF1", "label": "NSD support", "value": 1, "display": "1", "kind": "number"},
    ]
    payload["emergencies"] = [
        {"slot": 1, "name": "Afghanistan Earthquake", "code": "MDRAF007", "indicators": []},
    ]
    html = render_dashboard_html(payload, "combined")
    heading_at = html.find("ONGOING EMERGENCY INDICATORS")
    emergency_at = html.find("upr-block--emergency")
    sp_at = html.find("Strategic Priorities")
    ef_at = html.find("Enabling Functions")
    support_at = html.find("upr-support-table")
    assert heading_at != -1
    assert emergency_at != -1
    assert heading_at < emergency_at < sp_at < ef_at < support_at
    assert html.count("upr-combined-section--indicators") == 2
    assert "upr-combined-section--page-start" in html
    sp_section = html[html.find("Strategic Priorities") - 200 : html.find("Strategic Priorities")]
    assert "upr-combined-section--page-start" in sp_section
    assert html.find("upr-combined-section--page-start") < sp_at
    assert "upr-combined-section--page-start" not in html[ef_at:]
    payload["emergencies"] = []
    assert "upr-combined-section--page-start" not in render_dashboard_html(payload, "combined")
    payload["emergencies"] = [
        {"slot": 1, "name": "Afghanistan Earthquake", "code": "MDRAF007", "indicators": []},
    ]
    assert "ONGOING EMERGENCY INDICATORS" not in render_dashboard_html(payload, "emergency_1")


@pytest.mark.unit
def test_render_dashboards_html_includes_each_chip():
    payload = _payload()
    payload["dashboards"] = [
        {"id": "combined", "title": "Country visual"},
        {"id": "reach", "title": "People to be reached"},
        {"id": "financial", "title": "Funding requirements"},
        {"id": "network_funding", "title": "Network-supported activities"},
    ]
    by_id = render_dashboards_html(payload)
    assert set(by_id) == {"combined", "reach", "financial", "network_funding"}
    assert "People to be reached in 2026" in by_id["reach"]
    assert "IFRC network Funding Requirements" in by_id["financial"]
    assert "FINANCIAL OVERVIEW" not in by_id["financial"]
    assert "Host National Society" in by_id["network_funding"]
    assert "upr-dashboard--combined" in by_id["combined"]


@pytest.mark.unit
def test_render_plan_network_funding_matches_tableau_detail():
    html = render_dashboard_html(_payload(), "network_funding")
    assert "Detailed funding requirements" in html
    assert "IFRC Network-Supported Activities" not in html
    assert "Longer-term needs in Swiss francs" not in html
    assert "upr-detail-fund-wrap" in html
    assert html.find("Ongoing emergencies") < html.find("Longer-term needs")
    assert html.find("Longer-term needs") < html.find("Climate and environment")
    assert html.find("Climate and environment") < html.find("Disasters &amp; crises")
    assert html.find("Disasters &amp; crises") < html.find("Health &amp; wellbeing")
    assert html.find("Values, power &amp; inclusion") < html.find("Enabling local actors")
    assert html.find("Enabling local actors") < html.find("Total")
    assert "upr-detail-fund__child" in html
    assert "upr-detail-fund__pill" in html
    assert "30M" in html
    assert "1.7M" in html
    assert "30.1M" in html
    climate = html.find("Climate and environment")
    emergencies = html.find("Ongoing emergencies")
    child_slice = html[climate:html.find("Enabling local actors")]
    assert "upr-detail-fund__pill" not in child_slice
    assert "upr-detail-fund__pill" in html[emergencies:climate]
    assert "upr-netfund-year" not in html
    assert ">2027<" not in html


@pytest.mark.unit
def test_render_report_financial_breakdown():
    payload = _payload()
    payload["meta"]["kind"] = "report"
    payload["financial"]["ifrc_network"] = {
        "funding_display": "4.2M",
        "expenditure_display": "3.1M",
    }
    payload["financial"]["national_society"] = {
        "funding": 4_200_000,
        "funding_display": "4.2M",
        "expenditure": 3_100_000,
        "expenditure_display": "3.1M",
    }
    payload["financial"]["breakdown"] = [
        {"code": "SP1", "label": "Climate and environment", "funding": 1000, "expenditure": 800},
    ]
    payload["financial"]["network_entities"] = [
        {
            "entity": "Country",
            "label": "Country",
            "buckets": [
                {
                    "key": "overall",
                    "label": "",
                    "metrics": [
                        {
                            "key": "funding_requirement",
                            "label": "Funding requirement",
                            "value": 10_000_000,
                            "display": "10M",
                        },
                    ],
                }
            ],
        },
        {
            "entity": "IFRC Secretariat",
            "label": "IFRC Secretariat",
            "buckets": [
                {
                    "key": "longer_term",
                    "label": "Longer-term",
                    "metrics": [
                        {
                            "key": "funding_requirement",
                            "label": "Funding requirement",
                            "value": 25_000_000,
                            "display": "25M",
                        },
                        {
                            "key": "funding",
                            "label": "Funding",
                            "value": 0,
                            "display": "Not reported",
                        },
                    ],
                },
                {
                    "key": "emergency",
                    "label": "Emergency Operations",
                    "metrics": [
                        {
                            "key": "funding_requirement",
                            "label": "Funding requirement",
                            "value": 5_000_000,
                            "display": "5M",
                        },
                    ],
                },
            ],
        },
        {
            "entity": "PNS",
            "label": "Participating National Societies",
            "buckets": [
                {
                    "key": "overall",
                    "label": "",
                    "metrics": [
                        {"key": "funding", "label": "Funding", "value": 90, "display": "90"},
                    ],
                }
            ],
        },
        {
            "entity": "Other sources",
            "label": "HNS other funding sources",
            "buckets": [
                {
                    "key": "overall",
                    "label": "",
                    "metrics": [
                        {"key": "funding", "label": "Funding", "value": 986000, "display": "986,000"},
                    ],
                }
            ],
        },
    ]
    html = render_dashboard_html(payload, "financial")
    assert "FINANCIAL OVERVIEW" in html
    assert "in Swiss francs (CHF)" in html
    assert "upr-fin-hero" in html
    assert "upr-fin-cover" in html
    assert "upr-fin-grid" in html
    assert "upr-fin-col-source-label" in html
    assert "upr-fin-grid--with-sources" in html
    assert "Overview" in html
    assert "Funding Sources" in html
    assert "upr-bar-fill" in html
    assert "Expenditure" in html
    assert "Funding requirement" in html
    assert "Participating National Societies" in html
    assert "HNS other funding sources" in html
    assert "IFRC network" in html
    assert "Longer-term" in html
    assert "Emergency Operations" in html
    assert "upr-fin-net" in html
    assert "upr-fin-net-col-metric" in html
    assert "upr-fin-net__entity" in html
    assert "upr-fin-net__bucket" in html
    assert "rowspan=" in html
    assert "upr-fin-net__bucket-start" in html
    assert "Not reported" in html
    assert "upr-not-reported" in html
    assert "National Society by Strategic Priority" not in html


@pytest.mark.unit
def test_render_strategic_priority_bars():
    payload = _payload()
    payload["core_indicators"] = [
        {"code": "SP1", "label": "People reached with climate activities", "value": 1_573_911, "display": "1,573,911", "kind": "number"},
        {"code": "SP2", "label": "People reached with livelihoods support", "value": 58_264, "display": "58,264", "kind": "number"},
    ]
    html = render_dashboard_html(payload, "strategic_priorities")
    assert "Strategic Priorities" in html
    assert html.count("class='upr-bar-group'") == 2
    assert "Climate and environment" in html
    assert "Disasters and crises" in html
    assert "upr-bar-fill" in html
    assert "People reached with climate activities" in html
    assert "width:100.0%" in html
    assert "width:3.7%" in html
    assert html.count("width:100.0%") == 1


@pytest.mark.unit
def test_emergency_title_is_code_slash_name():
    payload = _payload()
    payload["meta"]["kind"] = "report"
    payload["emergencies"] = [
        {
            "slot": 1,
            "name": "Afghanistan Earthquake",
            "code": "MDRAF007",
            "indicators": [],
        }
    ]
    html = render_dashboard_html(payload, "emergency_1")
    assert "<span class='upr-code'>MDRAF007</span> / <span class='upr-emergency-name'>Afghanistan Earthquake</span>" in html
    assert "Afghanistan Earthquake <span" not in html


@pytest.mark.unit
def test_number_styles_use_montserrat():
    from pathlib import Path

    from plugins.upr_visuals.raster import _font_css

    css = (
        Path(__file__).resolve().parents[1] / "static" / "css" / "upr-visuals.css"
    ).read_text(encoding="utf-8")
    number_block = css.split(".upr-visual-report__toolbar", 1)[0]
    for cls in (
        ".upr-kpi__value",
        ".upr-fin-kpi__value",
        ".upr-reach-value",
        ".upr-reach-headline",
        ".upr-bar-value",
        ".upr-num",
        ".upr-support-total",
        ".upr-plan-cover__country",
        ".upr-plan-fund__source-value",
        ".upr-plan-fund__projected-value",
    ):
        assert cls in number_block
    assert 'font-family: "Montserrat"' in number_block
    font_css = _font_css()
    assert "Open Sans" in font_css
    assert "file:" in font_css
    assert "OpenSans-Regular" in font_css


@pytest.mark.unit
def test_bar_track_keeps_fill_and_value_on_one_line():
    from pathlib import Path

    css = (
        Path(__file__).resolve().parents[1] / "static" / "css" / "upr-visuals.css"
    ).read_text(encoding="utf-8")
    track = css.split(".upr-bar-track {", 1)[1].split(".upr-bar-fill {", 1)[0]
    fill = css.split(".upr-bar-fill {", 1)[1].split(".upr-bar-value {", 1)[0]
    value = css.split(".upr-bar-value {", 1)[1].split("}", 1)[0]
    assert "flex-wrap: nowrap" in track
    assert "white-space: nowrap" in track
    assert "flex: 0 1 auto" in fill
    assert "white-space: nowrap" in value
    assert "flex: 0 0 auto" in value
