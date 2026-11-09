"""Unit tests for Global Plan aggregation and overlay (no database needed)."""

from __future__ import annotations

from plugins.upr.analysis.global_plan import aggregate_global_plan, prioritisation_group_label
from plugins.upr.analysis.global_plan_overlay import normalize_overlay, year_overlay
from plugins.upr.analysis.global_plan_views import build_global_plan_views


def _master(**kw):
    row = {
        "ISO3": "AAA",
        "Country": "Aland",
        "Round": "P27",
        "Year": 2027,
        "Section": "Funding",
        "Entity": "HNS",
        "NS": "Aland RC",
        "Source": "Country Data",
        "Area": "Total",
        "Attribute": "Total",
        "Indicator": "Funding Requirement",
        "ValueNum": 1000,
        "Region": "Europe",
    }
    row.update(kw)
    return row


def test_prioritisation_group_labels():
    assert prioritisation_group_label(0).startswith("0")
    assert prioritisation_group_label(5).startswith("5")


def test_normalize_overlay_cleans_iso3_and_years():
    overlay = normalize_overlay(
        {
            "years": {
                "2027": {
                    "special_purpose_funds": "12.5",
                    "new_emergency_appeals_estimate": 100,
                    "emergency_appeals_rollover": "298.7e6",
                    "use_manual_ea_rollover": "true",
                }
            },
            "large_emergency_iso3": "ukr, SDN\nxx",
            "appeals": [{"year": 2027, "name": "Test", "amount_requested": 10}],
            "divisions": [{"year": 2027, "division": "NSDOC", "value": 50, "area": "EFs"}],
        }
    )
    assert overlay["years"]["2027"]["special_purpose_funds"] == 12.5
    assert overlay["years"]["2027"]["use_manual_ea_rollover"] is True
    assert overlay["years"]["2027"]["emergency_appeals_rollover"] == 298.7e6
    assert overlay["large_emergency_iso3"] == ["UKR", "SDN"]
    assert len(overlay["appeals"]) == 1
    assert overlay["divisions"][0]["division"] == "NSDOC"
    assert year_overlay(overlay, 2027)["new_emergency_appeals_estimate"] == 100


def test_aggregate_funding_by_entity_and_theme():
    rows = [
        _master(Entity="HNS", Attribute="Total", Area="Total", ValueNum=1000),
        _master(Entity="HNS", Attribute="SP Breakdown", Area="SP1", ValueNum=600),
        _master(Entity="HNS", Attribute="SP Breakdown", Area="SP2", ValueNum=400),
        _master(Entity="IFRC Secretariat", Attribute="Total", Area="Total", ValueNum=500),
        _master(Entity="IFRC Secretariat", Attribute="SP Breakdown", Area="SP1", ValueNum=500),
        # Live extracts often store each theme as Attribute=Total (not Area=Total).
        _master(Entity="PNS", NS="Danish RC", Attribute="Total", Area="SP1", ValueNum=120),
        _master(Entity="PNS", NS="Danish RC", Attribute="Total", Area="SP2", ValueNum=80),
        # Total-only partner (not disaggregated by theme).
        _master(Entity="PNS", NS="British RC", Attribute="Total", Area="Total", ValueNum=50),
        _master(
            Section="Reach",
            Indicator="People to be reached",
            Attribute="SP Breakdown",
            Area="SP1",
            ValueNum=9000,
            Entity="HNS",
        ),
    ]
    out = aggregate_global_plan(
        rows,
        [{"Round": "P27", "ISO3": "AAA", "status": "submitted", "Region": "Europe"}],
        countries={"AAA": {"name": "Aland", "region": "Europe"}},
        ns_flags={"AAA": {"country": "Aland", "nsif": True, "oda": False}},
        inform={"AAA": "Very High"},
        overlay={"large_emergency_iso3": ["AAA"], "years": {}, "appeals": [], "divisions": []},
        eas_sprm={"P27": {"AAA": 25}},
        year=2027,
    )
    assert out["has_data"] is True
    assert out["year"] == 2027
    assert out["funding"]["selected_entity"]["HNS"] == 1000
    assert out["funding"]["selected_entity"]["IFRC Secretariat"] == 500
    assert out["funding"]["selected_entity"]["PNS"] == 250  # 120+80 + 50
    assert out["funding"]["selected_theme"]["SP1"] == 1220  # HNS 600 + IFRC 500 + PNS 120
    assert out["funding"]["selected_theme"]["SP2"] == 480  # HNS 400 + PNS 80
    assert out["funding"]["selected_theme"]["Total"] == 50  # British RC Total-only
    assert out["reach"]["selected_theme"]["SP1"] == 9000
    assert out["ea_source"] == "country"
    assert out["pns"]["provider_count"] == 2
    prio = out["prioritisation"]["rows"][0]
    assert prio["iso3"] == "AAA"
    assert prio["flags"]["inform"] == 1
    assert prio["flags"]["nsif"] == 1
    assert prio["flags"]["large_emergency"] == 1
    assert prio["flags"]["pns"] == 1
    assert prio["prioritisation_score"] == 4


def test_aggregate_uses_data_extract_attribute_spef_and_pns_source():
    """Global Plan reads /data shape: Indicator=Funding Requirement, Attribute+SP/EF, Source=PNS Data."""
    rows = [
        _master(
            Entity="PNS",
            NS="Spanish RC",
            Indicator="Funding Requirement",
            Source="PNS Data",
            Attribute="Total",
            Area=None,
            ValueNum=160,
            **{"SP/EF": None, "PNS Value": 160, "Country Value": 500, "PNS reported": "Yes"},
        ),
        _master(
            Entity="PNS",
            NS="Spanish RC",
            Indicator="Funding Requirement",
            Source="PNS Data",
            Attribute="Longer-term",
            Area=None,
            ValueNum=120,
            **{"SP/EF": "SP1"},
        ),
        _master(
            Entity="PNS",
            NS="Spanish RC",
            Indicator="Funding Requirement",
            Source="PNS Data",
            Attribute="Longer-term",
            Area=None,
            ValueNum=40,
            **{"SP/EF": "SP2"},
        ),
    ]
    out = aggregate_global_plan(
        rows,
        [{"Round": "P27", "ISO3": "AAA", "status": "submitted", "Region": "Europe"}],
        countries={"AAA": {"name": "Aland", "region": "Europe"}},
        year=2027,
    )
    assert out["funding"]["selected_entity"]["PNS"] == 160
    assert out["funding"]["selected_theme"]["SP1"] == 120
    assert out["funding"]["selected_theme"]["SP2"] == 40
    assert out["pns"]["providers"][0]["name"] == "Spanish RC"
    assert out["pns"]["providers"][0]["value"] == 160


def test_default_year_is_immediate_plan_year_not_horizon():
    """P27 plans optionally hold 2027–2029; Global Plan defaults to 2027."""
    rows = [
        _master(Year=2027, ValueNum=100),
        _master(Year=2028, ValueNum=110),
        _master(Year=2029, ValueNum=120),
    ]
    out = aggregate_global_plan(
        rows,
        [{"Round": "P27", "ISO3": "AAA", "status": "submitted", "Region": "Europe"}],
        countries={"AAA": {"name": "Aland", "region": "Europe"}},
        year=None,
    )
    assert out["immediate_year"] == 2027
    assert out["year"] == 2027
    assert out["years"] == [2027, 2028, 2029]
    assert out["funding"]["selected_total"] == 100

    out_2029 = aggregate_global_plan(
        rows,
        [{"Round": "P27", "ISO3": "AAA", "status": "submitted", "Region": "Europe"}],
        countries={"AAA": {"name": "Aland", "region": "Europe"}},
        year=2029,
    )
    assert out_2029["year"] == 2029
    assert out_2029["funding"]["selected_total"] == 120


def test_one_year_one_round_does_not_stack_horizons():
    """P25 Year=2027 must not stack on top of P27 Year=2027."""
    rows = [
        _master(Round="P25", Year=2027, Entity="PNS", NS="Danish RC", ValueNum=50),
        _master(Round="P26", Year=2027, Entity="PNS", NS="Danish RC", ValueNum=60),
        _master(Round="P27", Year=2027, Entity="PNS", NS="Danish RC", ValueNum=70),
        _master(Round="P27", Year=2028, Entity="PNS", NS="Danish RC", ValueNum=80),
    ]
    out = aggregate_global_plan(
        rows,
        [{"Round": "P27", "ISO3": "AAA", "status": "submitted"}],
        countries={"AAA": {"name": "Aland", "region": "Europe"}},
        year=2027,
    )
    assert out["funding"]["selected_entity"]["PNS"] == 70
    assert out["plan_by_year"]["2027"] == "P27"
    out_2028 = aggregate_global_plan(
        rows,
        [{"Round": "P27", "ISO3": "AAA", "status": "submitted"}],
        countries={"AAA": {"name": "Aland", "region": "Europe"}},
        year=2028,
    )
    assert out_2028["funding"]["selected_entity"]["PNS"] == 80


def test_manual_ea_rollover_replaces_ifrc_country_eas():
    rows = [
        _master(Entity="IFRC Secretariat", Attribute="Total", Area="Total", ValueNum=800),
        _master(Entity="IFRC Secretariat", Attribute="SP Breakdown", Area="SP1", ValueNum=500),
        _master(Entity="IFRC Secretariat", Attribute="SP Breakdown", Area="EAs", ValueNum=300),
    ]
    out = aggregate_global_plan(
        rows,
        [{"Round": "P27", "ISO3": "AAA", "status": "submitted"}],
        countries={"AAA": {"name": "Aland", "region": "Europe"}},
        overlay={
            "years": {
                "2027": {
                    "use_manual_ea_rollover": True,
                    "emergency_appeals_rollover": 250,
                }
            }
        },
        year=2027,
    )
    assert out["ea_source"] == "manual_rollover"
    assert out["funding"]["selected_theme"]["EAs"] == 250
    assert out["funding"]["selected_entity"]["IFRC Secretariat"] == 750  # 800 - 300 + 250
    assert out["overlay"]["year"]["country_ea_ifrc"] == 300


def test_region_filter_via_prefiltered_rows():
    rows = [
        _master(ISO3="AAA", Region="Europe", ValueNum=100),
        _master(ISO3="BBB", Country="Benin", Region="Africa", ValueNum=200),
    ]
    africa = [r for r in rows if r["Region"] == "Africa"]
    out = aggregate_global_plan(
        africa,
        [],
        countries={"BBB": {"name": "Benin", "region": "Africa"}},
        year=2027,
    )
    assert out["funding"]["selected_total"] == 200
    assert out["countries_with_fr"] == 1


def test_views_cover_all_sections():
    payload = aggregate_global_plan(
        [
            _master(ValueNum=100),
            _master(Entity="PNS", NS="Danish RC", ValueNum=50),
        ],
        [{"Round": "P27", "ISO3": "AAA", "status": "approved"}],
        countries={"AAA": {"name": "Aland", "region": "Europe"}},
        ns_flags={"AAA": {"nsif": True, "oda": True, "country": "Aland"}},
        inform={"AAA": "High"},
        overlay={
            "years": {"2027": {"special_purpose_funds": 10}},
            "appeals": [{"year": 2027, "name": "EA", "amount_requested": 1}],
            "divisions": [{"year": 2027, "division": "NSDOC", "value": 5}],
            "large_emergency_iso3": [],
        },
        year=2027,
    )
    views = build_global_plan_views(payload)
    assert set(views) >= {
        "overview",
        "secretariat",
        "pns",
        "yearly",
        "regional",
        "divisional",
        "geo",
        "people_reached",
        "emergencies",
        "countries",
        "prioritisation",
    }
    assert views["overview"]["has_data"] is True
    assert views["overview"]["kpis"]
    hero = views["overview"]["visuals"][0]
    assert hero["id"] == "gp_overview_hero"
    assert hero["kind"] == "overview"
    assert hero["overview"]["year"] == 2027
    assert {row["id"] for row in hero["overview"]["rows"]} == {"ifrc", "hns", "pns"}
    from plugins.upr.analysis.analysis_labels import analysis_labels

    pns_label = analysis_labels()["gp_overview_pns"]
    pns_row = next(r for r in hero["table"]["rows"] if r["cells"][0] == pns_label)
    assert pns_row["countries"]
    assert pns_row["countries"][0]["cells"][0] == "Danish RC"
    assert pns_row["countries"][0]["cells"][1] == 50
    assert views["prioritisation"]["visuals"]


def _visual(views, section, visual_id):
    return next(item for item in views[section]["visuals"] if item["id"] == visual_id)


def test_regional_bars_are_percent_stacked_and_nsif_splits_are_pies():
    payload = aggregate_global_plan(
        [
            _master(Entity="HNS", Attribute="SP Breakdown", Area="SP1", ValueNum=600, Region="Europe"),
            _master(
                ISO3="BBB",
                Country="Benin",
                Entity="HNS",
                Attribute="SP Breakdown",
                Area="SP2",
                ValueNum=400,
                Region="Africa",
            ),
            _master(Entity="IFRC Secretariat", Attribute="SP Breakdown", Area="SP1", ValueNum=250, Region="Europe"),
            _master(
                Section="Reach",
                Indicator="People to be reached",
                Attribute="SP Breakdown",
                Area="SP1",
                ValueNum=9000,
                Entity="HNS",
                Region="Europe",
            ),
            _master(
                ISO3="BBB",
                Country="Benin",
                Section="Reach",
                Indicator="People to be reached",
                Attribute="SP Breakdown",
                Area="SP2",
                ValueNum=1000,
                Entity="HNS",
                Region="Africa",
            ),
        ],
        [
            {"Round": "P27", "ISO3": "AAA", "status": "approved"},
            {"Round": "P27", "ISO3": "BBB", "status": "approved"},
        ],
        countries={
            "AAA": {"name": "Aland", "region": "Europe"},
            "BBB": {"name": "Benin", "region": "Africa"},
        },
        ns_flags={"AAA": {"nsif": True, "country": "Aland"}},
        year=2027,
    )
    views = build_global_plan_views(payload)

    for section, visual_id in (("geo", "gp_geo_region"), ("people_reached", "gp_people_region")):
        item = _visual(views, section, visual_id)
        assert item["chart"]["horizontal"] is True
        assert item["chart"]["stacked"] is True
        assert item["chart"]["stack_type"] == "100%"
        assert [mode["id"] for mode in item["modes"]] == ["share", "values"]
        assert item["modes"][0]["chart"] is item["chart"]
        values = item["modes"][1]["chart"]
        assert values["horizontal"] is True
        assert values["stacked"] is True
        assert "stack_type" not in values
        assert values["categories"] == item["chart"]["categories"]
        assert item["chart"]["series"]

    submit = _visual(views, "overview", "gp_submit_priority")
    assert submit["chart"]["pie"] is True
    assert submit["chart"]["series"][0]["kind"] == "pie"
    assert submit["chart"]["series"][0]["data"] == [1, 1]
    assert len(submit["chart"]["colors"]) == 2

    share = _visual(views, "secretariat", "gp_sec_share")
    assert share["chart"]["pie"] is True
    assert share["chart"]["series"][0]["format"] == "money"
    assert share["chart"]["series"][0]["data"] == [250, 0]
