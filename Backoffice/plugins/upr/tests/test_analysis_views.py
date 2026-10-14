"""Tests for the renderer-independent Analysis views (no database needed)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from plugins.upr.analysis_labels import analysis_labels, analysis_ui_labels, fill
from plugins.upr.analysis_spec import (
    FINDING_TONES,
    country_rows,
    delta_view,
    midyear_cell,
    pct_text,
    round_int,
    with_abs_change,
    year_label,
)
from plugins.upr.impact import aggregate_impact
from plugins.upr.impact_views import build_impact_view
from plugins.upr.narrative import aggregate_participation
from plugins.upr.narrative_views import VIEW_TRACKS, build_narrative_view, build_narrative_views

LABELS = analysis_labels()
FIXTURE = Path(__file__).parent / "fixtures" / "analysis_views.json"


def _master(**kw):
    row = {
        "ISO3": "AAA",
        "Country": "Aland",
        "Round": "AR25",
        "Section": None,
        "Entity": "HNS",
        "NS": "Aland RC",
        "Source": "Country Data",
        "Attribute": "Total",
        "Indicator": None,
        "ValueNum": None,
        "Region": "Africa",
    }
    row.update(kw)
    return row


def _sub(**kw):
    row = {"Round": "AR25", "ISO3": "AAA", "Region": "Africa", "status": "approved", "fds_validated": "Validated"}
    row.update(kw)
    return row


@pytest.fixture()
def impact_payload():
    master = [
        _master(Round="P24", Section="Funding", Indicator="Funding Requirement", ValueNum=1000),
        _master(Round="P25", Section="Funding", Indicator="Funding Requirement", ValueNum=1500),
        _master(Round="P25", ISO3="BBB", Country="Bland", Section="Funding", Indicator="Funding Requirement", ValueNum=500),
        _master(Round="AR24", Section="Funding", Indicator="Funding", Source="PNS Data", Entity="PNS", ValueNum=800),
        _master(Round="MYR25", Section="Funding", Indicator="Funding", Source="PNS Data", Entity="PNS", ValueNum=300),
        _master(Round="P25", Section="Reach", Indicator="People to be reached", Attribute="Area", ValueNum=40000),
        _master(Round="AR24", Section="Activities", Entity="PNS", NS="Cland RC", Indicator="x", ValueNum=1),
        _master(Round="AR24", Section="NS Data", Indicator="Number of volunteers", ValueNum=1200),
        _master(Round="AR24", Section="NS Data", Indicator="Number of branches", ValueNum=30),
    ]
    subs = [
        _sub(Round="P24"),
        _sub(Round="P25"),
        _sub(Round="P25", ISO3="BBB"),
        _sub(Round="AR24"),
        _sub(Round="AR24", ISO3="BBB"),
        _sub(Round="MYR25"),
        _sub(Round="MYR25", ISO3="BBB", status="assigned"),
        _sub(Round="MYR25", ISO3="CCC", status="assigned"),
    ]
    return aggregate_impact(master, subs)


@pytest.fixture()
def narrative_payload():
    countries = {
        "AAA": {"name": "Aland", "region": "Africa"},
        "BBB": {"name": "Bland", "region": "Africa"},
        "CCC": {"name": "Cland", "region": "Asia"},
    }
    internal = [
        {"round": "P24", "iso3": "AAA"},
        {"round": "P24", "iso3": "BBB"},
        {"round": "P25", "iso3": "AAA"},
        {"round": "P25", "iso3": "BBB"},
        {"round": "P25", "iso3": "CCC"},
        {"round": "AR24", "iso3": "AAA"},
    ]
    public = [{"round": "P24", "iso3": "AAA"}, {"round": "P25", "iso3": "AAA"}]
    subs = [
        {"Round": "P24", "ISO3": "AAA", "status": "approved"},
        {"Round": "P25", "ISO3": "AAA", "status": "approved"},
        {"Round": "P25", "ISO3": "BBB", "status": "submitted"},
        {"Round": "AR24", "ISO3": "AAA", "status": "approved"},
        {"Round": "AR24", "ISO3": "BBB", "status": "approved"},
    ]
    payload = aggregate_participation(internal=internal, public=public, submissions=subs, countries=countries)
    payload["sources"] = {"internal": {"available": True, "documents": 6}, "public": {"available": False, "documents": 0, "message": "down"}}
    return payload


def _walk_charts(view):
    for vis in view["visuals"]:
        if vis["kind"] == "chart":
            yield vis, vis["chart"]
        for panel in vis.get("panels") or []:
            yield vis, panel["chart"]


def test_contract_fixture_matches_the_view_builders(impact_payload, narrative_payload):
    """The browser tests (tests/js/plugins/upr-analysis.test.js) render this file.

    Regenerate after changing a view:
    ``UPR_UPDATE_FIXTURES=1 pytest plugins/upr/tests/test_analysis_views.py``
    """
    current = {
        "impact": build_impact_view(impact_payload),
        "narrative": build_narrative_views(narrative_payload),
    }
    rendered = json.dumps(current, indent=1, ensure_ascii=False) + "\n"
    if os.environ.get("UPR_UPDATE_FIXTURES"):
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(rendered, encoding="utf-8")
    assert FIXTURE.read_text(encoding="utf-8") == rendered, (
        "analysis_views.json is stale; run with UPR_UPDATE_FIXTURES=1 to regenerate"
    )


# -- schema invariants -------------------------------------------------------


def test_views_are_json_serialisable(impact_payload, narrative_payload):
    json.dumps(build_impact_view(impact_payload))
    json.dumps(build_narrative_views(narrative_payload))


def test_every_chart_series_matches_its_categories(impact_payload, narrative_payload):
    views = [build_impact_view(impact_payload), *build_narrative_views(narrative_payload).values()]
    seen = 0
    for view in views:
        for vis, chart in _walk_charts(view):
            for s in chart["series"]:
                assert len(s["data"]) == len(chart["categories"]), (vis["id"], s["name"])
                assert s["axis"] in chart["axes"], (vis["id"], s["name"])
            seen += 1
    assert seen >= 10


def test_every_visual_has_an_id_title_and_table(impact_payload, narrative_payload):
    ids = []
    for view in [build_impact_view(impact_payload), build_narrative_view(narrative_payload, "ALL")]:
        for vis in view["visuals"]:
            assert vis["id"] and vis["title"]
            assert vis["table"] and vis["table"]["columns"]
            ids.append(vis["id"])
    assert len(ids) == len(set(ids))


def test_table_rows_match_column_count(impact_payload, narrative_payload):
    views = [build_impact_view(impact_payload), *build_narrative_views(narrative_payload).values()]
    for view in views:
        for vis in view["visuals"]:
            tables = [vis["table"], *[g["table"] for g in vis.get("gaps") or []]]
            for tbl in tables:
                width = len(tbl["columns"])
                for row in tbl["rows"]:
                    assert len(row["cells"]) == width, (vis["id"], tbl["title"])
                    for detail in row["countries"]:
                        assert len(detail["cells"]) == width, (vis["id"], tbl["title"])


# -- data section ------------------------------------------------------------


def test_impact_view_has_the_five_visuals_in_order(impact_payload):
    view = build_impact_view(impact_payload)
    assert view["has_data"] is True
    assert [v["id"] for v in view["visuals"]] == ["coverage", "funding", "reach", "partners", "capacity"]
    assert [k["id"] for k in view["kpis"]] == ["coverage", "plan_requirement", "reach", "partners", "partner_funding"]
    assert view["visuals"][0]["wide"] and view["visuals"][4]["wide"]


def test_impact_view_is_empty_without_submissions():
    view = build_impact_view(aggregate_impact([], []))
    assert view["has_data"] is False
    assert view["visuals"] == [] and view["kpis"] == []
    assert build_impact_view(None)["has_data"] is False


def test_open_years_are_starred_and_noted(impact_payload):
    view = build_impact_view(impact_payload)
    assert 2025 in impact_payload["in_progress_years"]
    cats = view["visuals"][0]["chart"]["categories"]
    assert cats == ["2024", "2025 *"]
    assert any("2025" in note and "*" in note for note in view["notes"])
    assert view["notes"][-1] == LABELS["impact_footnote"]


def test_funding_series_follow_the_year_axis_and_mark_midyear(impact_payload):
    view = build_impact_view(impact_payload)
    funding = next(v for v in view["visuals"] if v["id"] == "funding")
    plan, reported, spent = funding["chart"]["series"]
    assert funding["chart"]["categories"] == ["2024", "2025 *"]
    assert plan["data"] == [1000, 2000]
    assert reported["data"] == [800, 300]  # 2025 falls back to the mid-year report
    assert spent["dashed"] is True
    assert all(s["format"] == "money" for s in (plan, reported, spent))

    rows = {r["cells"][0]: r for r in funding["table"]["rows"]}
    assert [r["cells"][0] for r in funding["table"]["rows"]] == ["2025 *", "2024"]  # newest first
    assert rows["2025 *"]["cells"][2] == {"value": 300, "midyear": True}
    assert rows["2024"]["cells"][2] == 800
    assert funding["table"]["legend"] == LABELS["midyear_legend"]


def test_country_rows_drop_empty_lines_and_rank_by_largest_figure(impact_payload):
    view = build_impact_view(impact_payload)
    funding = next(v for v in view["visuals"] if v["id"] == "funding")
    row_2025 = next(r for r in funding["table"]["rows"] if r["cells"][0] == "2025 *")
    names = [c["cells"][0] for c in row_2025["countries"]]
    assert names == ["Aland", "Bland"]  # Aland 1500 plan outranks Bland 500


def test_capacity_panels_are_separate_charts_with_a_latest_figure(impact_payload):
    view = build_impact_view(impact_payload)
    capacity = next(v for v in view["visuals"] if v["id"] == "capacity")
    panels = {p["id"]: p for p in capacity["panels"]}
    assert list(panels) == ["volunteers", "staff", "branches", "local_units"]
    assert panels["volunteers"]["value"] == 1200 and panels["volunteers"]["year"] == 2024
    assert panels["staff"]["value"] is None
    assert panels["staff"]["chart"]["series"][0]["data"] == [None, None]  # zero is shown as a gap


def test_partner_chart_uses_a_secondary_axis(impact_payload):
    view = build_impact_view(impact_payload)
    chart = next(v for v in view["visuals"] if v["id"] == "partners")["chart"]
    assert [s["axis"] for s in chart["series"]] == ["primary", "secondary"]
    assert chart["axes"]["secondary"]["opposite"] is True


def test_kpi_label_does_not_claim_participation():
    # "Participating" means data or narrative; the data-only KPI must not use it.
    assert "articipating" not in LABELS["kpi_coverage"]
    assert "articipating" in LABELS["narr_kpi_any"]


# -- participation section ---------------------------------------------------


def test_narrative_views_cover_the_overview_and_each_round_type(narrative_payload):
    views = build_narrative_views(narrative_payload)
    assert list(views) == list(VIEW_TRACKS) == ["ALL", "P", "MYR", "AR"]
    for track, view in views.items():
        assert view["track"] == track
        assert [v["id"] for v in view["visuals"]] == ["narr_stage", "narr_mix", "narr_pub", "narr_ret", "narr_gaps"]
        assert len(view["kpis"]) == 5


def test_overview_charts_use_round_codes_and_plan_view_uses_years(narrative_payload):
    overview = build_narrative_view(narrative_payload, "ALL")
    plans = build_narrative_view(narrative_payload, "P")
    assert overview["visuals"][0]["chart"]["categories"] == ["P24", "AR24", "P25"]
    assert plans["visuals"][0]["chart"]["categories"][0] == "2024"


def test_retention_card_swaps_between_histogram_and_year_on_year(narrative_payload):
    overview = build_narrative_view(narrative_payload, "ALL")
    plans = build_narrative_view(narrative_payload, "P")
    ret_all = overview["visuals"][3]
    ret_plans = plans["visuals"][3]
    assert ret_all["title"] == LABELS["narr_eng_title"]
    assert ret_all["chart"]["data_labels"] is True
    assert ret_plans["title"] == LABELS["narr_ret_title"]
    assert ret_plans["chart"]["stacked"] is True
    assert ret_plans["chart"]["axes"]["primary"]["format"] == "abs_int"
    lapsed = ret_plans["chart"]["series"][3]["data"]
    assert all(v is None or v <= 0 for v in lapsed)


def test_gap_lists_are_resolved_into_drill_down_tables(narrative_payload):
    plans = build_narrative_view(narrative_payload, "P")
    gaps = plans["visuals"][4]
    assert [g["id"] for g in gaps["gaps"]] == ["narrative_only", "data_only", "unpublished", "lapsed"]
    narrative_only = gaps["gaps"][0]
    assert narrative_only["count"] == len(narrative_only["table"]["rows"])
    assert narrative_only["table"]["title"].startswith(LABELS["narr_narrative_only"])
    assert " — " in narrative_only["table"]["title"]
    overview = build_narrative_view(narrative_payload, "ALL")["visuals"][4]
    assert [g["id"] for g in overview["gaps"]] == ["always", "intermittent", "planned_not_reported", "never"]
    matrix = overview["table"]
    assert matrix["columns"][:2] == [LABELS["narr_country"], LABELS["narr_region"]]
    assert matrix["columns"][2:] == narrative_payload["rounds"]


def test_source_outage_surfaces_as_a_warning(narrative_payload):
    view = build_narrative_view(narrative_payload, "ALL")
    assert view["warnings"] == [f"{LABELS['narr_public']}: down"]
    assert any("6" in note for note in view["notes"])


def test_empty_narrative_payload_still_builds_every_track():
    views = build_narrative_views(None)
    assert set(views) == set(VIEW_TRACKS)
    assert all(not v["has_data"] and v["visuals"] == [] for v in views.values())


# -- helpers -----------------------------------------------------------------


def test_round_int_matches_browser_rounding():
    assert [round_int(x) for x in (0.5, 1.5, 2.5, -0.5, None, True)] == [1, 2, 3, 0, None, None]


def test_year_label_and_pct_text():
    assert year_label(2025, [2025]) == "2025 *"
    assert year_label(2024, [2025]) == "2024"
    assert pct_text(12.34) == "12.3%" and pct_text(12.0) == "12%" and pct_text(None) == "—"


def test_midyear_cell_only_marks_present_values():
    assert midyear_cell(5, True) == {"value": 5, "midyear": True}
    assert midyear_cell(None, True) is None
    assert midyear_cell(5, False) == 5


def test_country_rows_filter_and_sort():
    rows = country_rows([["Zed", None, 5], ["Amy", None, 5], ["Zero", None, 0], ["Big", None, 9]])
    assert [r["cells"][0] for r in rows] == ["Big", "Amy", "Zed"]


def test_delta_view_directions_and_context():
    labels = analysis_labels()
    up = delta_view({"latest": 12, "latest_year": 2025, "previous": 10, "previous_year": 2024, "change_pct": 20.0}, labels)
    assert up == {"direction": "up", "text": "+20%", "context": fill(labels["vs_previous"], year=2024), "note": False}
    down = delta_view({"latest": 8, "previous": 10, "previous_year": 2024, "change_pct": -12.5}, labels)
    assert down["direction"] == "down" and down["text"] == "-12.5%"
    first = delta_view({"latest": 8, "change_pct": None}, labels)
    assert first["text"] == labels["no_previous"] and first["context"] is None
    assert delta_view({"latest": None}, labels) is None
    assert delta_view({"latest": 5, "note": "n"}, labels) == {"direction": "flat", "text": "n", "context": None, "note": True}


def test_with_abs_change_reads_rates_as_differences():
    labels = analysis_labels()
    delta = with_abs_change({"latest": 62.5, "previous": 60.0, "previous_year": 2024}, " pts")
    view = delta_view(delta, labels)
    assert view["text"] == "+2.5 pts" and view["direction"] == "up"


def test_ui_labels_expose_the_strings_the_browser_needs():
    ui = analysis_ui_labels()
    assert {"show_countries", "midyear_cell", "load_failed", "close", "view_table", "gaps_select"} <= set(ui)


def test_ui_labels_cover_the_presentation_and_a4_report():
    ui = analysis_ui_labels()
    assert {
        "export_generated", "export_region", "export_all_regions", "export_page", "export_notes",
        "export_tables_heading", "export_more", "export_print", "export_print_hint",
        "export_pdf_working", "export_pdf_failed", "export_nothing",
        "export_unavailable", "export_prev", "export_next", "export_fullscreen", "section_data",
        "track_ALL", "track_P", "track_MYR", "track_AR",
    } <= set(ui)
    # The browser fills these placeholders itself (UprAnalysis.format.fill).
    assert "{date}" in ui["export_generated"] and "{region}" in ui["export_region"]
    assert "{n}" in ui["export_page"] and "{total}" in ui["export_page"] and "{n}" in ui["export_more"]


def test_visual_hints_describe_the_data_and_leave_interaction_hints_to_the_tab(narrative_payload):
    # The presentation and the printed report reuse these hints; "select a list"
    # only makes sense on the tab, which adds it from the ui labels.
    for view in build_narrative_views(narrative_payload).values():
        for vis in view["visuals"]:
            assert "select" not in vis["hint"].lower()


def test_analysis_service_builds_payloads_and_views_for_every_consumer(monkeypatch, impact_payload, narrative_payload):
    from plugins.upr import analysis_service

    seen = []
    monkeypatch.setattr(analysis_service, "build_upr_impact", lambda *, region=None: seen.append(("impact", region)) or impact_payload)
    monkeypatch.setattr(
        analysis_service,
        "build_narrative_participation",
        lambda *, region=None: seen.append(("narrative", region)) or narrative_payload,
    )

    bundle = analysis_service.build_analysis_bundle(region="Africa")

    assert seen == [("impact", "Africa"), ("narrative", "Africa")]
    assert bundle["region"] == "Africa"
    assert bundle["impact"]["payload"] is impact_payload
    assert bundle["impact"]["view"]["has_data"] is True
    assert bundle["narrative"]["payload"] is narrative_payload
    assert set(bundle["narrative"]["views"]) == set(VIEW_TRACKS)


# -- findings -----------------------------------------------------------------


def test_finding_helper_builds_the_documented_shape():
    from plugins.upr.analysis_spec import finding

    plain = finding("growth", "Participation doubled.")
    assert plain == {"id": "growth", "title": None, "text": "Participation doubled.", "tone": "info", "focus": None}

    focused = finding("dip", "Fewer reports.", title="A dip", tone="attention", categories=["2024", 2025])
    assert focused["focus"] == {"categories": ["2024", "2025"]}
    assert focused["tone"] == "attention" and focused["title"] == "A dip"
    json.dumps(focused)


def test_finding_helper_rejects_unknown_tones():
    from plugins.upr.analysis_spec import finding

    with pytest.raises(ValueError):
        finding("x", "text", tone="shouting")


def test_visual_carries_its_findings_and_defaults_to_none():
    from plugins.upr.analysis_spec import finding, visual

    assert visual("v", "T", "h")["findings"] == []
    found = finding("a", "text")
    assert visual("v", "T", "h", findings=[found])["findings"] == [found]


def test_every_visual_lists_findings_that_the_renderers_can_place(impact_payload, narrative_payload):
    # A finding's focus names chart categories; a typo would silently highlight nothing.
    views = [build_impact_view(impact_payload), *build_narrative_views(narrative_payload).values()]
    for view in views:
        for vis in view["visuals"]:
            assert isinstance(vis["findings"], list)
            ids = [f["id"] for f in vis["findings"]]
            assert len(ids) == len(set(ids)), vis["id"]
            for found in vis["findings"]:
                assert found["tone"] in FINDING_TONES and found["text"]
                if found["focus"]:
                    assert vis["kind"] == "chart", vis["id"]
                    assert set(found["focus"]["categories"]) <= set(vis["chart"]["categories"]), vis["id"]
