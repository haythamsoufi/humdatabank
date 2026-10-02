"""Cover-page MAA codes from the appealgroupchild catalogue."""

from __future__ import annotations

import pytest

from plugins.upr.maa_codes import (
    appeal_code_for_cover,
    choose_maa_code,
    load_appeal_catalogue,
    resolve_appeal_number,
)
from plugins.upr.render import _doc_footer


def _row(code, *, iso="SY", status="Active", start="2023-01-01", end="2026-12-31", **extra):
    row = {
        "code": code,
        "status": status,
        "status_display": status,
        "start_date": start,
        "end_date": end,
        "country": {"iso": iso} if iso else None,
    }
    row.update(extra)
    return row


@pytest.mark.unit
def test_choose_maa_code_prefers_the_appeal_that_covers_the_document_year():
    records = [
        _row("MAASY001", status="Closed", start="2019-01-01", end="2022-12-31"),
        _row("MAASY002", status="Active", start="2023-01-01", end="2026-12-31"),
        _row("MDRSY016", status="Active", start="2024-01-01", end="2026-12-31"),
        _row("MAA65001", iso="", status="Active", start="2023-01-01", end="2026-12-31"),
    ]
    assert choose_maa_code(records, "sy", year=2026) == "MAASY002"
    assert choose_maa_code(records, "SY", year=2021) == "MAASY001"
    assert choose_maa_code(records, "SY") == "MAASY002"


@pytest.mark.unit
def test_choose_maa_code_keeps_the_active_code_when_dates_overlap():
    records = [
        _row("MAAVN001", iso="VN", status="Closed", start="2020-01-01", end="2026-12-31"),
        _row("MAAVN002", iso="VN", status="Active", start="2024-01-01", end="2028-12-31"),
    ]
    assert choose_maa_code(records, "VN", year=2026) == "MAAVN002"


@pytest.mark.unit
def test_choose_maa_code_rejects_a_country_mismatch_and_unknown_iso():
    records = [_row("MAASY002", iso="SD")]
    assert choose_maa_code(records, "SY", year=2026) == ""
    assert choose_maa_code(records, "SYR", year=2026) == ""
    assert choose_maa_code(records, "", year=2026) == ""


@pytest.mark.unit
def test_choose_maa_code_reads_raw_appealgroupchild_fields():
    records = [
        {
            "Appeal_Id": "maaug002",
            "Geographical_Code": "ug",
            "Status": "Active",
            "Start_Date": "2024-01-01T00:00:00",
            "End_Date": "2027-12-31T00:00:00",
        }
    ]
    assert choose_maa_code(records, "UG", year=2026) == "MAAUG002"


@pytest.mark.unit
def test_resolve_appeal_number_uses_catalogue_rows_and_falls_back():
    records = [_row("MAABD002", iso="BD", start="2025-01-01", end="2028-12-31")]
    assert resolve_appeal_number("bd", year=2026, records=records) == "MAABD002"
    assert resolve_appeal_number("UG", year=2026, records=records) == "MAAUG001"
    assert resolve_appeal_number("UG", year=2026, records=[]) == "MAAUG001"
    assert resolve_appeal_number("UGA", records=records) == ""


@pytest.mark.unit
def test_load_appeal_catalogue_uses_the_emergency_operations_cache(monkeypatch):
    payload = {
        "source": "appealgroupchild",
        "fetched_at": "2026-10-01T00:00:00+00:00",
        "results": [_row("MAAEE001", iso="EE")],
    }

    class Store:
        def load_cached(self):
            return payload

        def is_refresh_due(self, *_args, **_kwargs):
            return False

    monkeypatch.setattr(
        "plugins.emergency_operations.data_store.get_data_store",
        lambda: Store(),
    )
    monkeypatch.setattr(
        "plugins.upr.maa_codes._schedule_refresh_once",
        lambda: None,
    )
    assert load_appeal_catalogue() == payload["results"]
    assert resolve_appeal_number("EE", year=2025) == "MAAEE001"


@pytest.mark.unit
def test_load_appeal_catalogue_ignores_a_legacy_cache(monkeypatch):
    class Store:
        def load_cached(self):
            return {"source": None, "results": [_row("MAAEE001", iso="EE")]}

    monkeypatch.setattr(
        "plugins.emergency_operations.data_store.get_data_store",
        lambda: Store(),
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("credentials missing")

    monkeypatch.setattr(
        "plugins.emergency_operations.appeal_group.fetch_appeal_group_records",
        _boom,
    )
    import plugins.upr.maa_codes as maa_codes

    maa_codes._live_rows = None
    maa_codes._live_loaded_at = 0.0
    maa_codes._catalogue_warned = True
    assert load_appeal_catalogue() is None


@pytest.mark.unit
def test_live_fetch_warms_an_empty_emergency_operations_cache(monkeypatch):
    saved: dict = {}

    class Store:
        def load_cached(self):
            return None

        def save(self, results, query_params, source=None):
            saved["results"] = results
            saved["query_params"] = query_params
            saved["source"] = source
            return True

    monkeypatch.setattr(
        "plugins.emergency_operations.data_store.get_data_store",
        lambda: Store(),
    )
    monkeypatch.setattr(
        "plugins.emergency_operations.appeal_group.fetch_appeal_group_records",
        lambda *_args, **_kwargs: [_row("MAASY002")],
    )
    import plugins.upr.maa_codes as maa_codes

    maa_codes._live_rows = None
    maa_codes._live_loaded_at = 0.0
    rows = load_appeal_catalogue()
    assert rows[0]["code"] == "MAASY002"
    assert saved["source"] == "appealgroupchild"
    assert saved["results"][0]["code"] == "MAASY002"
    # A filled cache must not be fetched again on the next lookup.
    monkeypatch.setattr(
        "plugins.emergency_operations.appeal_group.fetch_appeal_group_records",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("refetched")),
    )
    maa_codes._live_rows = None
    maa_codes._live_loaded_at = 0.0

    class WarmStore(Store):
        def load_cached(self):
            return {"source": "appealgroupchild", "results": saved["results"]}

    monkeypatch.setattr(
        "plugins.emergency_operations.data_store.get_data_store",
        lambda: WarmStore(),
    )
    monkeypatch.setattr("plugins.upr.maa_codes._schedule_refresh_once", lambda: None)
    assert load_appeal_catalogue()[0]["code"] == "MAASY002"


@pytest.mark.unit
def test_cover_prints_the_catalogue_code_instead_of_the_static_suffix():
    meta = {"iso2": "SY", "appeal_code": "MAASY002"}
    html = _doc_footer({"meta": meta})
    assert appeal_code_for_cover(meta) == "MAASY002"
    assert "Appeal number <strong>MAASY002</strong>" in html
    assert "MAASY001" not in html


@pytest.mark.unit
def test_cover_without_a_catalogue_code_keeps_the_static_number():
    assert appeal_code_for_cover({"iso2": "UG"}) == "MAAUG001"
    assert appeal_code_for_cover({"iso2": "UG", "appeal_code": "not-a-code"}) == "MAAUG001"
