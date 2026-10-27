"""Manual tentative end-date overrides for Emergency Operations."""

from plugins.emergency_operations import end_date_overrides as edo
from plugins.emergency_operations.end_date_overrides import (
    PLUGIN_DATA_ID,
    apply_end_date_overrides,
    delete_override,
    get_overrides_map,
    list_overrides_with_source,
    source_end_dates_from_cache,
    upsert_override,
)
from plugins.emergency_operations.routes import _snapshot_preview_row


def test_upsert_apply_and_sync_status(app):
    with app.app_context():
        entry, err = upsert_override("mdraf019", "2026-12-31", note="ERP pending")
        assert err is None
        assert entry["code"] == "MDRAF019"
        assert entry["end_date"] == "2026-12-31"
        assert get_overrides_map()["MDRAF019"]["note"] == "ERP pending"

        raw = [
            {"code": "MDRAF019", "name": "Flood", "end_date": "2025-06-01T00:00:00Z"},
            {"code": "MDRXX001", "name": "Other", "end_date": "2025-01-01"},
        ]
        applied = apply_end_date_overrides(raw)
        assert applied[0]["end_date"] == "2026-12-31"
        assert applied[0]["source_end_date"] == "2025-06-01"
        assert applied[0]["end_date_overridden"] is True
        assert applied[1]["end_date"] == "2025-01-01"
        assert "end_date_overridden" not in applied[1]
        # Original cache row untouched
        assert raw[0]["end_date"] == "2025-06-01T00:00:00Z"

        source_map = source_end_dates_from_cache(raw)
        rows = list_overrides_with_source(source_map)
        assert len(rows) == 1
        assert rows[0]["sync_status"] == "pending"
        assert rows[0]["can_remove"] is False

        # Source catches up to the tentative date
        source_map["MDRAF019"] = "2026-12-31"
        rows = list_overrides_with_source(source_map)
        assert rows[0]["sync_status"] == "matched"
        assert rows[0]["can_remove"] is True

        ok, err = delete_override("MDRAF019")
        assert ok and err is None
        assert get_overrides_map() == {}


def test_source_ahead_allows_remove(app):
    with app.app_context():
        upsert_override("MDRKE001", "2026-01-01")
        rows = list_overrides_with_source({"MDRKE001": "2026-06-01"})
        assert rows[0]["sync_status"] == "source_ahead"
        assert rows[0]["can_remove"] is True
        delete_override("MDRKE001")


def test_snapshot_preview_row_marks_override():
    row = _snapshot_preview_row(
        {
            "code": "MDRAF019",
            "name": "Flood",
            "end_date": "2026-12-31",
            "source_end_date": "2025-06-01",
            "end_date_overridden": True,
            "country": {"iso": "AF", "name": "Afghanistan"},
        }
    )
    assert row["end_date"] == "2026-12-31"
    assert row["source_end_date"] == "2025-06-01"
    assert row["end_date_overridden"] is True


def test_invalid_code_rejected(app):
    with app.app_context():
        entry, err = upsert_override("", "2026-01-01")
        assert entry is None
        assert err

        entry, err = upsert_override("BAD CODE!", "2026-01-01")
        assert entry is None

        entry, err = upsert_override("OKCODE", "not-a-date")
        assert entry is None


def test_plugin_data_id_is_dedicated():
    assert PLUGIN_DATA_ID == "emergency_operations_end_date_overrides"
    assert PLUGIN_DATA_ID != "emergency_operations"
