"""World Bank snapshot parsing and the save-once refresh rule."""

import tempfile
from pathlib import Path

from plugins.fdrs.services.world_bank_snapshot import (
    ensure_world_bank_snapshot,
    parse_income_rows,
    parse_latest_gni,
    parse_population_rows,
)


def test_population_rows_skip_blanks_and_keep_iso3():
    rows = parse_population_rows([
        {"countryiso3code": "KEN", "date": "2024", "value": 55339003},
        {"countryiso3code": "", "date": "2024", "value": 100},
        {"countryiso3code": "AFE", "date": "2024", "value": None},
        {"countryiso3code": "ken", "date": "2023", "value": "1000.4"},
    ])
    assert rows == [
        {"iso3": "KEN", "year": 2023, "population": 1000},
        {"iso3": "KEN", "year": 2024, "population": 55339003},
    ]


def test_income_rows_map_classifications_and_skip_aggregates():
    rows = parse_income_rows([
        {"id": "KEN", "region": {"id": "SSF"}, "incomeLevel": {"id": "LMC", "value": "Lower middle income"}},
        {"id": "WLD", "region": {"id": "NA"}, "incomeLevel": {"id": "NA", "value": ""}},
        {"id": "USA", "region": {"id": "NAC"}, "incomeLevel": {"id": "HIC", "value": "High income"}},
    ])
    assert {row["iso3"]: row["income_group"] for row in rows} == {"KEN": "LM", "USA": "H"}


def test_gni_keeps_the_latest_year():
    rows = parse_latest_gni([
        {"countryiso3code": "KEN", "date": "2022", "value": 1800},
        {"countryiso3code": "KEN", "date": "2024", "value": 2100},
        {"countryiso3code": "KEN", "date": "2023", "value": None},
    ])
    assert rows == [{"iso3": "KEN", "year": 2024, "gni_per_capita_usd": 2100}]


def test_snapshot_is_saved_once_and_refresh_replaces_it():
    tmp_path = Path(tempfile.mkdtemp())
    calls = {"n": 0}

    def fake_get(url):
        calls["n"] += 1
        if "SP.POP.TOTL" in url:
            return [{"page": 1, "pages": 1}, [{"countryiso3code": "KEN", "date": "2024", "value": 100}]]
        if "NY.GNP.PCAP.CD" in url:
            return [{"page": 1, "pages": 1}, [{"countryiso3code": "KEN", "date": "2024", "value": 50}]]
        return [{"page": 1, "pages": 1}, [
            {"id": "KEN", "region": {"id": "SSF"}, "incomeLevel": {"id": "LMC", "value": "Lower middle income"}},
        ]]

    first = ensure_world_bank_snapshot(directory=tmp_path, get_json=fake_get)
    assert first["population"][0]["population"] == 100
    saved_calls = calls["n"]
    second = ensure_world_bank_snapshot(directory=tmp_path, get_json=fake_get)
    assert calls["n"] == saved_calls
    assert second["population"][0]["iso3"] == "KEN"

    def failing_get(url):
        raise OSError("offline")

    kept = ensure_world_bank_snapshot(directory=tmp_path, refresh=True, get_json=failing_get)
    assert kept["population"][0]["population"] == 100
    assert kept["refresh_error"]
