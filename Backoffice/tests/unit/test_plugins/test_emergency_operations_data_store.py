"""Emergency Operations appeals cache uses storage_service, not the plugin package dir."""

from plugins.emergency_operations import data_store as ds
from plugins.emergency_operations.data_store import (
    CACHE_REL_PATH,
    STORAGE_CATEGORY,
    EmergencyOperationsDataStore,
)


def test_save_and_load_round_trip_via_storage(app, tmp_path):
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    app.config["UPLOAD_FOLDER"] = str(upload_root)
    app.config["UPLOAD_STORAGE_PROVIDER"] = "filesystem"

    ds._invalidate_mem_cache()
    store = EmergencyOperationsDataStore()

    with app.app_context():
        assert store.save(
            [{"code": "MDRAF019", "name": "Test"}],
            {"format": "json"},
            source="appealgroupchild",
        )
        cached = store.load_cached()
        assert cached is not None
        assert cached["record_count"] == 1
        assert cached["source"] == "appealgroupchild"
        assert cached["results"][0]["code"] == "MDRAF019"

        on_disk = upload_root / STORAGE_CATEGORY / CACHE_REL_PATH
        assert on_disk.is_file()
        assert b"MDRAF019" in on_disk.read_bytes()


def test_legacy_plugin_data_file_is_migrated_into_storage(app, tmp_path, monkeypatch):
    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    app.config["UPLOAD_FOLDER"] = str(upload_root)
    app.config["UPLOAD_STORAGE_PROVIDER"] = "filesystem"

    legacy = tmp_path / "legacy_appeals_cache.json"
    legacy.write_text(
        '{"fetched_at":"2024-01-01T00:00:00+00:00","record_count":1,'
        '"query_params":{},"results":[{"code":"LEGACY1"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(ds, "_LEGACY_CACHE_FILE", legacy)
    ds._invalidate_mem_cache()

    with app.app_context():
        store = EmergencyOperationsDataStore()
        data = store.load()
        assert data is not None
        assert data["results"][0]["code"] == "LEGACY1"
        assert (upload_root / STORAGE_CATEGORY / CACHE_REL_PATH).is_file()
