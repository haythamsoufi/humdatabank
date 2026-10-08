"""Status and refresh of Everyone Counts external snapshots."""

from plugins.fdrs.services import ecr_external
from plugins.fdrs.services.ecr_external import describe_sources, refresh_source


def test_missing_files_are_listed_as_not_saved():
    rows = describe_sources({}, None)
    by_id = {row["id"]: row for row in rows}
    assert by_id["wgi"]["available"] is False
    assert by_id["wgi"]["count"] == 0
    assert by_id["world_bank"]["available"] is False
    assert "World Giving Index" == by_id["wgi"]["label"]


def test_saved_files_report_their_size_and_date():
    rows = describe_sources(
        {"wgi": {"fetched_at": "2026-10-05T12:00:00+00:00", "rows": [{}, {}]}},
        {
            "fetched_at": "2026-10-01T00:00:00+00:00",
            "population": [{"iso3": "KEN"}],
            "income_groups": [],
        },
    )
    by_id = {row["id"]: row for row in rows}
    assert by_id["wgi"]["available"] is True
    assert by_id["wgi"]["count"] == 2
    assert by_id["wgi"]["fetched_at"] == "2026-10-05"
    assert by_id["world_bank"]["available"] is True
    assert by_id["world_bank"]["count"] == 1
    assert by_id["go"]["available"] is False


def test_unknown_source_is_rejected():
    try:
        refresh_source("not-a-source")
    except KeyError:
        return
    raise AssertionError("unknown source should raise KeyError")


def test_refresh_keeps_the_saved_file_when_the_download_fails(monkeypatch):
    def fail():
        raise RuntimeError("down")

    monkeypatch.setattr(ecr_external, "_refresh_wgi", fail)
    monkeypatch.setattr(ecr_external, "load_sources", lambda: {})
    row = refresh_source("wgi")
    assert row["id"] == "wgi"
    assert row["error"]
    assert row["available"] is False


def test_refresh_reports_a_world_bank_failure_without_dropping_the_file(monkeypatch):
    def fail():
        return "The World Bank snapshot could not be refreshed. The saved snapshot is still in use."

    monkeypatch.setattr(ecr_external, "_refresh_world_bank", fail)
    monkeypatch.setattr(
        ecr_external,
        "load_snapshot",
        lambda name: {"fetched_at": "2026-10-01T00:00:00+00:00", "population": [{"iso3": "KEN"}]}
        if name == "world_bank"
        else None,
    )
    row = refresh_source("world_bank")
    assert row["available"] is True
    assert row["count"] == 1
    assert "still in use" in row["error"]
