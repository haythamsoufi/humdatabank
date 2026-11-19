"""Uploaded NSD workbooks keep the original file name on disk."""
import json

from plugins.nsd_report_forms import routes


def test_list_disk_files_shows_the_original_name(tmp_path, monkeypatch):
    monkeypatch.setattr(routes, "_upload_dir", lambda: tmp_path)
    file_id = "a" * 32
    (tmp_path / f"{file_id}.xlsx").write_bytes(b"PK")
    (tmp_path / f"{file_id}.meta.json").write_text(
        json.dumps({
            "filename": "CBF master.xlsx",
            "size": 12,
            "uploaded_at": "2026-11-18T10:15:00+00:00",
        }),
        encoding="utf-8",
    )
    rows = routes.list_disk_files()
    assert len(rows) == 1
    assert rows[0]["name"] == "CBF master.xlsx"
    assert rows[0]["note"] == "Uploaded master workbook"
    assert rows[0]["file_id"] == file_id
    assert rows[0]["size_label"] == "12 B"
    assert rows[0]["modified_label"] == "2026-11-18 10:15 UTC"


def test_list_disk_files_hides_the_storage_id_when_the_name_was_not_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(routes, "_upload_dir", lambda: tmp_path)
    file_id = "b" * 32
    (tmp_path / f"{file_id}.xlsx").write_bytes(b"PK")
    rows = routes.list_disk_files()
    assert rows[0]["name"] == "Uploaded workbook"
    assert file_id not in rows[0]["name"]
    assert "not stored" in rows[0]["note"]
    assert rows[0]["file_id"] == file_id
    assert rows[0]["size_label"] == "2 B"
