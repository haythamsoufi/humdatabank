"""Bundle visual merge: add country figures, average percents, keep labels."""

from __future__ import annotations

import pytest

from plugins.upr.bundle import merge_upr_payloads


def _payload(**overrides):
    base = {
        "meta": {
            "kind": "report",
            "country_name": "Fiji",
            "document_title": "Fiji — Annual Report 2024",
            "document_subtitle": "Jan–Dec 2024",
            "iso2": "FJ",
            "iso3": "FJI",
            "ns_logo_src": "/logo.png",
            "appeal_code": "MAAFJ001",
        },
        "kpis": {
            "volunteers": {"key": "volunteers", "label": "Volunteers", "value": 10, "display": "10"},
        },
        "people_reached": [
            {"code": "TOTAL", "label": "Total", "value": 100, "display": "100", "has_value": True},
        ],
        "financial": {
            "ifrc_network": {"funding": 1000, "funding_display": "1,000"},
            "years": [{"year": 2024, "hns": 10, "ifrc": 20, "pns": 0, "total": 30}],
            "sources": [],
            "cover_sources": [],
            "breakdown": [{"code": "SP1", "label": "SP1", "funding": 5, "expenditure": 1}],
            "area_years": [],
            "network_entities": [],
        },
        "support": [
            {"ns_id": 1, "name": "American Red Cross", "year": 2024, "funding": 50, "confirmed": 10, "areas": {}, "area_amounts": {}},
        ],
        "core_indicators": [
            {"code": "SP1", "label": "People reached", "kind": "number", "value": 4, "display": "4"},
            {"code": "SP1", "label": "Coverage", "kind": "percent", "value": 40, "display": "40%"},
            {"code": "SP1", "label": "Has a plan", "kind": "yesno", "value": 1, "display": "Yes"},
        ],
        "enabling_indicators": [],
        "emergencies": [
            {"slot": 1, "name": "Cyclone", "code": "MDRFJ001", "people_reached": 20, "indicators": []},
        ],
        "dashboards": [],
    }
    base.update(overrides)
    return base


@pytest.mark.unit
def test_merge_upr_payloads_sums_counts_and_retitles():
    other = _payload()
    other["meta"] = dict(other["meta"])
    other["meta"]["country_name"] = "Samoa"
    other["kpis"] = {
        "volunteers": {"key": "volunteers", "label": "Volunteers", "value": 5, "display": "5"},
    }
    other["people_reached"] = [
        {"code": "TOTAL", "label": "Total", "value": 25, "display": "25", "has_value": True},
    ]
    other["core_indicators"] = [
        {"code": "SP1", "label": "People reached", "kind": "number", "value": 6, "display": "6"},
        {"code": "SP1", "label": "Coverage", "kind": "percent", "value": 60, "display": "60%"},
        {"code": "SP1", "label": "Has a plan", "kind": "yesno", "value": 0, "display": "No"},
    ]
    other["emergencies"] = [
        {"slot": 2, "name": "Other name", "code": "MDRFJ001", "people_reached": 7, "indicators": []},
    ]
    other["support"] = [
        {"ns_id": 1, "name": "American Red Cross", "year": 2024, "funding": 25, "confirmed": 0, "areas": {}, "area_amounts": {}},
    ]
    other["financial"] = {
        "ifrc_network": {"funding": 500, "funding_display": "500"},
        "years": [{"year": 2024, "hns": 1, "ifrc": 2, "pns": 3, "total": 6}],
        "sources": [],
        "cover_sources": [],
        "breakdown": [{"code": "SP1", "label": "SP1", "funding": 2, "expenditure": 2}],
        "area_years": [],
        "network_entities": [],
    }

    merged = merge_upr_payloads(
        [_payload(), other],
        bundle_name="Pacific Islands",
        country_names=["Fiji", "Samoa"],
    )

    meta = merged["meta"]
    assert meta["country_name"] == "Pacific Islands"
    assert meta["national_society"] == "Pacific Islands"
    assert meta["iso2"] == ""
    assert meta["ns_logo_src"] == ""
    assert meta["appeal_code"] == ""
    assert meta["iso3"] == "PACIFICISLANDS"
    assert "2 countries" in meta["document_subtitle"]
    assert merged["kpis"]["volunteers"]["value"] == 15
    assert merged["people_reached"][0]["value"] == 125
    by_label = {row["label"]: row for row in merged["core_indicators"]}
    assert by_label["People reached"]["value"] == 10
    assert by_label["Coverage"]["value"] == 50
    assert by_label["Has a plan"]["display"] == "1 of 2"
    assert merged["emergencies"][0]["people_reached"] == 27
    assert merged["emergencies"][0]["slot"] == 1
    assert merged["support"][0]["funding"] == 75
    assert merged["financial"]["ifrc_network"]["funding"] == 1500
    assert merged["financial"]["years"][0]["total"] == 36
    assert merged["financial"]["breakdown"][0]["funding"] == 7
    assert merged["dashboards"]
