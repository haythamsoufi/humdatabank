"""Unit tests for UPR visuals formatters, catalog, and HTML render."""

from __future__ import annotations

import pytest

from plugins.upr_visuals.catalog import (
    PLAN_TEMPLATE_ID,
    REACH_CODES,
    REPORT_TEMPLATE_ID,
    dashboards_for_kind,
    display_ns_name,
    kind_for_template,
    section_to_area,
)
from plugins.upr_visuals.formatters import (
    format_chf,
    format_compact_chf,
    format_count,
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
    ids = {spec.id for spec in dashboards_for_kind("plan")}
    assert "combined" in ids
    assert "in_support" in ids
    assert "network_funding" in ids
    assert "financial" in ids
    assert "emergency_1" not in ids
    assert "strategic_priorities" not in ids
    assert "enabling_functions" not in ids


@pytest.mark.unit
def test_dashboards_for_report_include_emergencies():
    ids = {spec.id for spec in dashboards_for_kind("report")}
    assert "emergency_1" in ids
    assert "emergency_3" in ids
    assert "strategic_priorities" in ids
    assert "enabling_functions" in ids
    assert "network_funding" not in ids


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
    assert "CC1" in REACH_CODES


def _payload():
    return {
        "meta": {
            "aes_id": 4428,
            "kind": "plan",
            "period_name": "2026",
            "round_code": "P26",
            "country_name": "Uganda",
            "national_society": "Uganda Red Cross Society",
            "year": 2026,
            "plan_years": [2026, 2027, 2028],
            "people_title": "People to be reached in 2026",
            "support_title": "Participating National Societies bilateral support",
            "header_prefix": "In support of",
        },
        "kpis": {
            "branches": {"label": "National Society branches", "display": "34"},
            "staff": {"label": "National Society staff", "display": "4,000"},
            "volunteers": {"label": "National Society volunteers", "display": "26,000"},
            "local_units": {"label": "National Society local units", "display": "329"},
        },
        "people_reached": [
            {"code": "SP1", "label": "Climate and environment", "display": "50,000", "has_value": True},
            {"code": "SP2", "label": "Disasters and crises", "display": "200,000", "has_value": True},
            {"code": "CC1", "label": "Cross-cutting", "display": "12,000", "has_value": True},
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
                            "total": 1_700_000,
                        },
                        "IFRC Secretariat": {
                            "SP1": 100_000,
                            "SP2": 0,
                            "SP3": 0,
                            "SP4": 0,
                            "SP5": 0,
                            "EFs": 0,
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
                "name": "Netherlands Red Cross",
                "funding_display": "1.2M",
                "areas": {"SP1": True, "SP2": False, "SP3": True, "SP4": False, "SP5": False, "EFs": True},
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
    assert html.find("National Society branches") < html.find("National Society staff")
    assert html.find("National Society staff") < html.find("National Society volunteers")
    assert html.find("National Society volunteers") < html.find("National Society local units")
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
    assert "upr-reach-headline" in html
    assert "91,000" in html
    assert "Climate and environment" in html
    assert "Cross-cutting" in html
    assert "upr-reach-band--labels" in html
    assert "upr-reach-band--icons" in html
    assert "upr-reach-band--values" in html
    assert "upr-reach-divider" not in html
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
    catalog = _payload()
    catalog["people_reached"][0]["icon_src"] = "https://example.test/sp1.png"
    catalog_html = render_dashboard_html(catalog, "reach")
    assert "upr-reach-icon--img" in catalog_html
    assert "https://example.test/sp1.png" in catalog_html
    support = render_dashboard_html(_payload(), "support")
    assert "Netherlands Red Cross" in html or "Netherlands Red Cross" in support
    assert "Participating National Societies bilateral support" in support
    assert "upr-dot--on" in support
    assert "Funding Requirement" in support
    report_payload = _payload()
    report_payload["meta"]["kind"] = "report"
    report_payload["meta"]["people_title"] = "People reached"
    report_payload["meta"]["support_title"] = "IFRC Network-Supported Activities"
    report_payload["meta"]["support_funding_label"] = "Funding Reported"
    report_payload["support_total"] = {"value": 1_200_000, "display": "1.2M"}
    report_html = render_dashboard_html(report_payload, "support")
    assert "Funding Reported" in report_html
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
    empty_funding = _payload()
    empty_funding["support"][0]["funding_display"] = ""
    empty_html = render_dashboard_html(empty_funding, "support")
    assert "<td class='upr-num'>&nbsp;</td>" in empty_html
    assert "upr-support-total" in empty_html
    report_reach = render_dashboard_html(report_payload, "reach")
    assert "PEOPLE REACHED" in report_reach
    assert "upr-reach-headline" not in report_reach


@pytest.mark.unit
def test_render_plan_combined_matches_inp_cover():
    html = render_dashboard_html(_payload(), "combined")
    assert "UGANDA" in html
    assert "2026-2028 IFRC network country plan" in html
    assert "In support of Uganda Red Cross Society" in html
    assert "People to be reached in 2026" in html
    assert "IFRC network Funding Requirements" in html
    assert "Through Host National Society" in html
    assert "Through the IFRC" in html
    assert "Projected funding requirements" in html
    assert "19.1M CHF" in html
    assert "Participating National Societies" in html
    assert "IFRC Network-Supported Activities" in html
    assert "Enabling local actors" in html
    assert "FINANCIAL OVERVIEW" not in html
    assert "Strategic Priorities" not in html
    assert html.count("upr-combined-section") >= 6


@pytest.mark.unit
def test_render_report_combined_keeps_tableau_overview():
    payload = _payload()
    payload["meta"]["kind"] = "report"
    payload["meta"]["header_prefix"] = "IN SUPPORT OF"
    payload["meta"]["people_title"] = "People reached"
    html = render_dashboard_html(payload, "combined")
    assert "IN SUPPORT OF UGANDA RED CROSS SOCIETY" in html
    assert "FINANCIAL OVERVIEW" in html
    assert "IFRC network Funding Requirements" not in html
    assert "2026-2028 IFRC network country plan" not in html


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
        {"code": "SP1", "label": "People reached with climate activities", "value": 50000, "display": "50,000", "kind": "number"},
        {"code": "SP2", "label": "People reached with livelihoods support", "value": 12000, "display": "12,000", "kind": "number"},
    ]
    html = render_dashboard_html(payload, "strategic_priorities")
    assert "Strategic Priorities" in html
    assert "upr-bar-fill" in html
    assert "People reached with climate activities" in html


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
