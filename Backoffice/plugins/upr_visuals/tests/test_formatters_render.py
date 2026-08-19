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
    assert "emergency_1" not in ids


@pytest.mark.unit
def test_dashboards_for_report_include_emergencies():
    ids = {spec.id for spec in dashboards_for_kind("report")}
    assert "emergency_1" in ids
    assert "emergency_3" in ids
    assert "strategic_priorities" in ids
    assert "enabling_functions" in ids


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
            "national_society": "Uganda Red Cross Society",
            "people_title": "People to be reached",
            "support_title": "IFRC network bilateral-supported activities",
        },
        "kpis": {
            "branches": {"label": "Local Branches", "display": "34"},
            "local_units": {"label": "Local Units", "display": "329"},
            "volunteers": {"label": "Volunteers", "display": "26,000"},
            "staff": {"label": "Paid Staff", "display": "4,000"},
        },
        "people_reached": [
            {"code": "SP1", "label": "Climate and environment", "display": "50,000", "has_value": True},
            {"code": "SP2", "label": "Disasters and crises", "display": "200,000", "has_value": True},
            {"code": "CC1", "label": "Cross-cutting", "display": "12,000", "has_value": True},
        ],
        "financial": {
            "ifrc_network": {"funding_requirement_display": "10M"},
            "sources": [
                {"entity": "IFRC Secretariat", "label": "IFRC Secretariat", "display": "4,000,000"},
            ],
            "years": [{"year": 2026, "total_display": "10M"}],
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
    assert "IN SUPPORT OF" in html
    assert "UGANDA RED CROSS SOCIETY" in html
    assert "IN SUPPORT OF UGANDA RED CROSS SOCIETY" in html
    assert "&lt;" not in html
    assert "26,000" in html
    assert "<svg" in html
    assert "fas fa-" not in html


@pytest.mark.unit
def test_render_reach_and_support():
    html = render_dashboard_html(_payload(), "reach")
    assert "PEOPLE TO BE REACHED" in html
    assert "Climate and environment" in html
    assert "Cross-cutting" in html
    assert "upr-reach-band--labels" in html
    assert "upr-reach-band--icons" in html
    assert "upr-reach-band--values" in html
    catalog = _payload()
    catalog["people_reached"][0]["icon_src"] = "https://example.test/sp1.png"
    catalog_html = render_dashboard_html(catalog, "reach")
    assert "upr-reach-icon--img" in catalog_html
    assert "https://example.test/sp1.png" in catalog_html
    support = render_dashboard_html(_payload(), "support")
    assert "Netherlands Red Cross" in html or "Netherlands Red Cross" in support
    assert "upr-dot--on" in support
    assert "Funding Requirement" in support
    report_payload = _payload()
    report_payload["meta"]["kind"] = "report"
    report_payload["meta"]["support_funding_label"] = "Funding Reported"
    report_payload["support_total"] = {"value": 1_200_000, "display": "1.2M"}
    report_html = render_dashboard_html(report_payload, "support")
    assert "Funding Reported" in report_html
    assert "1.2M" in report_html
    assert "Total Funding Reported" not in report_html
    assert "CHF 1.2M" in report_html
    assert "upr-support-total" in report_html
    assert "upr-num" in report_html
    assert "<tfoot>" in report_html
    assert "upr-support-totals" not in report_html
    empty_funding = _payload()
    empty_funding["support"][0]["funding_display"] = ""
    empty_html = render_dashboard_html(empty_funding, "support")
    assert "<td class='upr-num'>&nbsp;</td>" in empty_html
    assert "upr-support-total" in empty_html


@pytest.mark.unit
def test_render_combined_includes_blocks():
    html = render_dashboard_html(_payload(), "combined")
    assert "IN SUPPORT OF" in html
    assert "FINANCIAL OVERVIEW" in html
    assert "PEOPLE TO BE REACHED" in html
    assert html.count("upr-combined-section") >= 4


@pytest.mark.unit
def test_render_dashboards_html_includes_each_chip():
    payload = _payload()
    payload["dashboards"] = [
        {"id": "combined", "title": "Country visual"},
        {"id": "reach", "title": "People reached"},
        {"id": "financial", "title": "Financial Overview"},
    ]
    by_id = render_dashboards_html(payload)
    assert set(by_id) == {"combined", "reach", "financial"}
    assert "PEOPLE TO BE REACHED" in by_id["reach"]
    assert "FINANCIAL OVERVIEW" in by_id["financial"]
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
        ".upr-bar-value",
        ".upr-num",
        ".upr-support-total",
    ):
        assert cls in number_block
    assert 'font-family: "Montserrat"' in number_block
    assert "Montserrat" in _font_css()
