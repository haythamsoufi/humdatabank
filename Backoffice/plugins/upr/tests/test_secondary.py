import json
from pathlib import Path

import pytest


def test_write_and_load_population(tmp_path, monkeypatch):
    from plugins.upr.secondary import paths
    from plugins.upr.secondary import imports as imp
    from plugins.upr.secondary.loaders import load_population
    from plugins.upr.secondary.registry import list_sources, touch_source

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "GLOBAL_FILES", {**paths.GLOBAL_FILES, "population": tmp_path / "population.json"})
    monkeypatch.setattr(imp, "population_latest_by_iso3", lambda: ({"KEN": 1.0, "UGA": 2.0}, 2024))
    monkeypatch.setattr(imp, "touch_source", lambda *a, **k: {"id": "population", **k})

    result = imp.refresh_population()
    assert result["row_count"] == 2
    assert result["year"] == 2024
    assert load_population()["KEN"] == 1.0
    payload = json.loads((tmp_path / "population.json").read_text(encoding="utf-8"))
    assert payload["year"] == 2024


def test_import_multilateral_and_eas(tmp_path, monkeypatch):
    from plugins.upr.secondary import paths
    from plugins.upr.secondary import imports as imp
    from plugins.upr.secondary.loaders import load_eas_sprm_ops, load_multilateral

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "MULTILATERAL_DIR", tmp_path / "multilateral")
    monkeypatch.setattr(paths, "EAS_SPRM_OPS_DIR", tmp_path / "eas")
    monkeypatch.setattr(imp, "touch_source", lambda *a, **k: k)

    csv_multi = b"iso3,ns\nAFG,Austrian Red Cross\nAFG,Danish Red Cross\n"
    result = imp.import_multilateral("P27", "multi.csv", csv_multi, year=2026)
    assert result["row_count"] == 2
    assert load_multilateral("P27")["AFG"] == ["Austrian Red Cross", "Danish Red Cross"]

    csv_eas = b"iso3,value\nAFG,1000\nAFG,500\nKEN,0\n"
    result = imp.import_eas_sprm_ops("P27", "eas.csv", csv_eas, year=2027)
    assert result["row_count"] == 1
    assert load_eas_sprm_ops("P27")["AFG"] == 1500
    assert "KEN" not in load_eas_sprm_ops("P27")


def test_import_multilateral_pledges_excel(tmp_path, monkeypatch):
    from io import BytesIO

    from openpyxl import Workbook

    from plugins.upr.secondary import paths
    from plugins.upr.secondary import imports as imp
    from plugins.upr.secondary import registry
    from plugins.upr.secondary.loaders import load_multilateral
    from plugins.upr.secondary.preview import preview_source

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "MULTILATERAL_DIR", tmp_path / "multilateral")
    monkeypatch.setattr(paths, "EAS_SPRM_OPS_DIR", tmp_path / "eas")
    monkeypatch.setattr(imp, "touch_source", lambda *a, **k: k)
    # Preview reads source status from PluginData. This test only has the files it just wrote.
    monkeypatch.setattr(registry, "load_secondary_meta", lambda: {"sources": {}})
    monkeypatch.setattr(
        imp,
        "country_name_to_iso3",
        lambda: {
            "kenya": "KEN",
            "djibouti": "DJI",
            "democratic republic of congo": "COD",
            "congo democratic of republic the": "COD",
        },
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Export"
    ws.append(
        [
            "Appeal code",
            "Geographical focus",
            "Donor name",
            "Donor type",
            "Year",
            "Amount (CHF)",
        ]
    )
    ws.append(["MAADJ002", "Djibouti", "Japanese Red Cross Society", "National Society", 2027, 98410])
    ws.append(["PS1006", "Kenya", "Nestle", "Corporate", 2027, 400000])
    ws.append(["MAA60005", "Kenya", "British Red Cross", "National Society", 2026, 12000])
    ws.append(["MAA000", "Democratic Republic of Congo", "Danish Red Cross", "National Society", 2026, 100])
    ws.append(["MAA000", "Kenya", "British Red Cross", "National Society", 2023, 50])  # outside year window
    buf = BytesIO()
    wb.save(buf)

    result = imp.import_multilateral("P27", "Multilateral support.xlsx", buf.getvalue())
    assert result["row_count"] == 3
    loaded = load_multilateral("P27")
    assert loaded["DJI"] == ["Japanese Red Cross Society"]
    assert loaded["KEN"] == ["British Red Cross"]
    assert loaded["COD"] == ["Danish Red Cross"]

    preview = preview_source("multilateral", round_code="P27", limit=10)
    assert preview["total"] == 3
    assert preview["columns"] == ["iso3", "ns"]
    assert {row["iso3"] for row in preview["rows"]} == {"COD", "DJI", "KEN"}


def test_import_multilateral_rejects_unreadable_sheet(tmp_path, monkeypatch):
    from plugins.upr.secondary import paths
    from plugins.upr.secondary import imports as imp

    monkeypatch.setattr(paths, "MULTILATERAL_DIR", tmp_path / "multilateral")
    monkeypatch.setattr(imp, "touch_source", lambda *a, **k: k)
    monkeypatch.setattr(imp, "country_name_to_iso3", lambda: {})

    with pytest.raises(ValueError, match="No multilateral rows found"):
        imp.import_multilateral("P27", "bad.csv", b"foo,bar\n1,2\n")


def test_import_income_and_hdi(tmp_path, monkeypatch):
    from plugins.upr.secondary import paths
    from plugins.upr.secondary import imports as imp
    from plugins.upr.secondary.loaders import load_hdi, load_income_groups

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        paths,
        "GLOBAL_FILES",
        {
            **paths.GLOBAL_FILES,
            "income_groups": tmp_path / "income_groups.json",
            "hdi": tmp_path / "hdi.json",
        },
    )
    monkeypatch.setattr(imp, "touch_source", lambda *a, **k: k)

    imp.import_income_groups("income.csv", b"iso3,income_group\nKEN,Lower middle income\n")
    assert load_income_groups()["KEN"] == "Lower middle income"

    imp.import_hdi("hdi.csv", b"iso3,hdi_score,hdi_rank,hdi_tier\nKEN,0.601,143,Medium\n")
    hdi = load_hdi()["KEN"]
    assert hdi["score"] == 0.601
    assert hdi["rank"] == 143
    assert hdi["tier"] == "Medium"


def test_climate_discovery_matches_percent_encoded_urls():
    from plugins.upr.secondary import inform as inform_mod

    encoded = "https://drmkc.jrc.ec.europa.eu/inform-index/portals/0/InfoRM/2022/INFORM%20CC%20Risk%20Index%20all%20scenarios.xlsx"
    assert inform_mod._climate_link_rank(encoded)[0] == 0
    monkey_html = f'<a href="/inform-index/portals/0/InfoRM/2022/INFORM CC Risk Index all scenarios.xlsx">x</a>'
    links = inform_mod._xlsx_links(monkey_html)
    assert links
    preferred = [u for u in links if inform_mod._climate_link_rank(u)[0] < 9]
    assert preferred


def test_refresh_income_and_hdi(tmp_path, monkeypatch):
    from plugins.upr.secondary import paths
    from plugins.upr.secondary import imports as imp
    from plugins.upr.secondary.loaders import load_hdi, load_income_groups

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        paths,
        "GLOBAL_FILES",
        {
            **paths.GLOBAL_FILES,
            "income_groups": tmp_path / "income_groups.json",
            "hdi": tmp_path / "hdi.json",
        },
    )
    monkeypatch.setattr(imp, "income_groups_by_iso3", lambda: {"KEN": "Lower middle income"})
    monkeypatch.setattr(
        imp,
        "hdi_latest_by_iso3",
        lambda: ({"KEN": {"score": 0.628, "rank": 143, "tier": "Medium"}}, 2023),
    )
    monkeypatch.setattr(imp, "touch_source", lambda *a, **k: k)

    assert imp.refresh_income_groups()["row_count"] == 1
    assert load_income_groups()["KEN"] == "Lower middle income"
    assert imp.refresh_hdi()["year"] == 2023
    assert load_hdi()["KEN"]["tier"] == "Medium"


def test_parse_inform_excel_bytes():
    from io import BytesIO

    from openpyxl import Workbook

    from plugins.upr.secondary import inform as inform_mod

    risk_wb = Workbook()
    about = risk_wb.active
    about.title = "About"
    about.append([None])
    about.append(["release:"])
    about.append(["1 September 2026 v 0.7.3"])
    risk = risk_wb.create_sheet("INFORM Risk 2026 (a-z)")
    risk.append([None] * 4)
    risk.append(["COUNTRY", "ISO3", "INFORM RISK", "RISK CLASS"])
    risk.append(["(a-z)", "(a-z)", "(0-10)", "(Very Low-Very High)"])
    risk.append(["Kenya", "KEN", 5.8, "High"])
    risk.append(["Afghanistan", "AFG", 7.8, "Very High"])
    risk_buf = BytesIO()
    risk_wb.save(risk_buf)
    scores, classes, edition = inform_mod.parse_inform_risk_xlsx(risk_buf.getvalue())
    assert scores["KEN"] == 5.8
    assert classes["AFG"] == "very_high"
    assert "2026" in (edition or "")

    sev_wb = Workbook()
    sev = sev_wb.active
    sev.title = "INFORM Severity - country"
    sev.append(["INFORM Severity Index - all countries. Release: October 2026"])
    sev.append(["CRISIS", "CRISIS ID", "COUNTRY", "ISO3", "DRIVERS", "INFORM Severity Index", "INFORM Severity category", "INFORM Severity category"])
    sev.append(["Weights"])
    sev.append(["(a-z)", None, None, "(a-z)", None, "(1-10)", "(1-5)", "(Very Low-Very High)"])
    sev.append(["Crisis A", "KEN001", "Kenya", "KEN", "x", 6.8, 4, "High"])
    sev.append(["Crisis B", "KEN002", "Kenya", "KEN", "x", 3.0, 2, "Low"])
    sev_buf = BytesIO()
    sev_wb.save(sev_buf)
    severity, sev_edition = inform_mod.parse_inform_severity_xlsx(sev_buf.getvalue())
    assert severity["KEN"] == "High"
    assert "October 2026" in (sev_edition or "")

    climate_wb = Workbook()
    climate = climate_wb.active
    climate.title = "INFORM CC Risk Components"
    climate.append(["Iso3", "IndicatorId", "IndicatorScore", "Year", "Scenario"])
    climate.append(["KEN", "INFORM", 4.2, 2022, "INFORM Climate Change Risk 2022"])
    climate.append(["KEN", "INFORM", 5.1, 2050, "INFORM Climate Change Risk 2050 RCP85-SSP3"])
    climate.append(["UGA", "HA.NAT", 1.0, 2022, "INFORM Climate Change Risk 2022"])
    climate_buf = BytesIO()
    climate_wb.save(climate_buf)
    climate_values, _edition = inform_mod.parse_inform_climate_xlsx(climate_buf.getvalue())
    assert climate_values["KEN"] == 4.2
    assert "UGA" not in climate_values


def test_bundle_value_reads_bundle_not_planning_bundle(monkeypatch):
    from plugins.upr.secondary import planning_bundle as pb

    monkeypatch.setattr(pb, "bundle_category_name", lambda: "Bundle")
    assert pb.bundle_value_from_texts({"Bundle": "Pacific Islands"}) == "Pacific Islands"
    assert pb.bundle_value_from_texts({"bundle": "Mekong countries"}) == "Mekong countries"
    assert pb.bundle_value_from_texts({"planning_bundle": "Pacific Islands"}) is None
    assert pb.bundle_value_from_texts({}) is None


def test_list_sources_includes_secondary_keys(monkeypatch):
    from plugins.upr.secondary import registry

    monkeypatch.setattr(registry, "load_secondary_meta", lambda: {"sources": {}})
    monkeypatch.setattr(registry, "list_round_files", lambda kind: [])
    sources = registry.list_sources()
    ids = [item["id"] for item in sources]
    assert ids[0] == "population"
    assert "multilateral" in ids
    assert "eas_sprm_ops" in ids
    assert "planning_bundle" not in ids


def test_settings_status_includes_secondary(monkeypatch):
    from plugins.upr import routes as upr_routes

    monkeypatch.setattr(
        "plugins.upr.secondary.registry.list_sources",
        lambda: [{"id": "population", "label": "Total Population", "status": "empty"}],
    )
    status = upr_routes.upr_settings_status()
    assert status["secondary_sources"][0]["id"] == "population"
    assert status["secondary_by_id"]["population"]["id"] == "population"
    assert "planning_bundle_tagged" not in status
