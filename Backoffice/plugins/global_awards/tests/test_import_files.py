"""Files the Global Awards importer lists, and the before/after text of its change log."""

from __future__ import annotations

import pytest

from plugins.global_awards.importer import files
from plugins.global_awards.importer.apply import _Changes, _shown_change

pytestmark = pytest.mark.unit


@pytest.fixture
def folders(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(files, "upload_dir", lambda: uploads)
    monkeypatch.setattr(files, "REPO_ROOT", repo)
    return uploads, repo


def test_uploads_and_repository_workbooks_are_all_listed(folders):
    _uploads, repo = folders
    (repo / "Annex 4_IFRC Global Award Framework.xlsx").write_bytes(b"PK1")
    (repo / "Annex_IFRC MARC_Logframe (work in progress).xlsx").write_bytes(b"PK22")
    (repo / "Service income analysis.xlsx").write_bytes(b"PK")
    first = files.store_upload(b"PK-first", "First upload.xlsx")
    second = files.store_upload(b"PK-second", "Second upload.xlsx")

    rows = files.list_disk_files()

    names = [row["name"] for row in rows]
    assert {"First upload.xlsx", "Second upload.xlsx"} <= set(names)
    assert "Annex 4_IFRC Global Award Framework.xlsx" in names
    assert "Annex_IFRC MARC_Logframe (work in progress).xlsx" in names
    assert "Service income analysis.xlsx" not in names
    assert len(rows) == 4
    refs = {row["ref"] for row in rows}
    assert f"stored:{first}" in refs and f"stored:{second}" in refs


def test_the_same_upload_is_kept_once(folders):
    uploads, _repo = folders
    first = files.store_upload(b"PK-same", "Framework.xlsx")
    again = files.store_upload(b"PK-same", "Framework v2.xlsx")

    assert first == again
    assert len(list(uploads.glob("*.xlsx"))) == 1
    assert files.stored_name(first) == "Framework v2.xlsx"


def test_resolve_ref_only_returns_listed_files(folders):
    _uploads, repo = folders
    (repo / "Global Award annex.xlsx").write_bytes(b"PK")
    (repo / "secret.xlsx").write_bytes(b"PK")
    file_id = files.store_upload(b"PK-upload", "Mine.xlsx")

    path, name = files.resolve_ref(f"stored:{file_id}")
    assert path.read_bytes() == b"PK-upload" and name == "Mine.xlsx"
    path, name = files.resolve_ref("repo:Global Award annex.xlsx")
    assert path.name == name == "Global Award annex.xlsx"

    assert files.resolve_ref("repo:secret.xlsx") is None
    assert files.resolve_ref("repo:../Global Award annex.xlsx") is None
    assert files.resolve_ref("stored:../../etc/passwd") is None
    assert files.resolve_ref("stored:" + "0" * 32) is None
    assert files.resolve_ref("") is None


def test_unchanged_rows_are_not_logged_and_changes_carry_a_before_value():
    changes = _Changes()
    state = {"Wording": "People reached", "Type": "question · number", "Applies to": "BGD, SYR"}

    changes.diff("items", dict(state), dict(state), label="G-01", kpi="G-01")
    assert changes.rows == []
    assert changes.tally["items"] == {"new": 0, "changed": 0, "unchanged": 1}

    changes.diff(
        "items",
        dict(state),
        {**state, "Wording": "People reached with aid"},
        label="G-01",
        kpi="G-01",
    )
    (row,) = changes.rows
    assert row["op"] == "update"
    assert row["old_value"] == "People reached"
    assert row["new_value"] == "People reached with aid"
    assert row["kpi"] == "G-01"

    changes.diff("items", None, state, label="G-02", kpi="G-02", insert_value="question · number")
    assert changes.rows[-1]["op"] == "insert"
    assert changes.rows[-1]["old_value"] is None


def test_country_list_changes_show_what_was_added_and_removed():
    old, new = _shown_change("Applies to", "BGD, SYR", "BGD, PAN")
    assert old == "2 countries"
    assert new == "2 countries (added PAN; removed SYR)"


def test_long_text_is_cut_around_the_first_difference():
    shared = "word " * 80
    old, new = _shown_change("Definition", shared + "old ending", shared + "new ending")
    assert old != new
    assert "old" in old and "new" in new
    assert len(old) < 200 and len(new) < 200
