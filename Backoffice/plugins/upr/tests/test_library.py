"""Stored UPR visuals used by the Generate table."""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from plugins.upr.errors import UprError


class _Store:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    def upload(self, category, key, data):
        assert category == "upr"
        self.files[key] = bytes(data)
        return key

    def download(self, category, key):
        return self.files[key]

    def exists(self, category, key):
        return key in self.files


@pytest.fixture
def store(monkeypatch):
    fake = _Store()
    monkeypatch.setattr("plugins.upr.library.storage_service", fake)
    return fake


@pytest.mark.unit
def test_library_round_trip(store, tmp_path):
    from plugins.upr.library import library_status, store_rendered_country

    combined = tmp_path / "combined.png"
    combined.write_bytes(b"combined-v1")
    reach = tmp_path / "reach.png"
    reach.write_bytes(b"reach-v1")
    other = tmp_path / "other.png"
    other.write_bytes(b"bgd")

    store_rendered_country(
        assigned_form_id=7,
        export_format="PNG",
        lang="en",
        aes_id=11,
        files=[("combined", combined, "AFG_combined.png")],
        package_filename="AFG_2024.zip",
    )
    store_rendered_country(
        assigned_form_id=7,
        export_format="png",
        lang="en",
        aes_id=22,
        files=[("reach", other, "BGD_reach.png")],
        package_filename="BGD_2024.zip",
    )
    reach.write_bytes(b"reach-v2")
    store_rendered_country(
        assigned_form_id=7,
        export_format="png",
        lang="en",
        aes_id=11,
        files=[("reach", reach, "AFG_reach.png")],
        package_filename="AFG_2024.zip",
    )

    status = library_status(7, "png", "en")
    assert set(status) == {"11", "22"}
    assert set(status["11"]["dashboards"]) == {"combined", "reach"}
    assert status["11"]["dashboards"]["combined"]["filename"] == "AFG_combined.png"
    assert status["11"]["zip"]["filename"] == "AFG_2024.zip"
    assert status["11"]["generated_at"]
    assert status["22"]["dashboards"]["reach"]["filename"] == "BGD_reach.png"

    package = zipfile.ZipFile(io.BytesIO(store.files["library/7/png/en/11/package.zip"]))
    assert package.read("AFG_combined.png") == b"combined-v1"
    assert package.read("AFG_reach.png") == b"reach-v2"
    assert store.files["library/7/png/en/11/combined.png"] == b"combined-v1"
    assert store.files["library/7/png/en/11/reach.png"] == b"reach-v2"

    index = json.loads(store.files["library/7/png/en/index.json"])
    assert set(index["countries"]) == {"11", "22"}


@pytest.mark.unit
def test_store_rejects_unknown_dashboard_without_writing(store, tmp_path):
    from plugins.upr.library import store_rendered_country

    path = tmp_path / "x.png"
    path.write_bytes(b"nope")
    with pytest.raises(UprError, match="Unknown dashboard"):
        store_rendered_country(
            assigned_form_id=7,
            export_format="png",
            lang="en",
            aes_id=11,
            files=[("../combined", path, "x.png")],
            package_filename="AFG.zip",
        )
    assert store.files == {}


@pytest.mark.unit
def test_empty_store_does_not_clear_existing(store, tmp_path):
    from plugins.upr.library import library_status, store_rendered_country

    path = tmp_path / "combined.png"
    path.write_bytes(b"png")
    store_rendered_country(
        assigned_form_id=3,
        export_format="png",
        lang="fr",
        aes_id=5,
        files=[("combined", path, "FRA.png")],
        package_filename="FRA.zip",
    )
    store_rendered_country(
        assigned_form_id=3,
        export_format="png",
        lang="fr",
        aes_id=5,
        files=[],
        package_filename="FRA.zip",
    )
    status = library_status(3, "png", "fr")
    assert "combined" in status["5"]["dashboards"]
    assert library_status(3, "pdf", "fr") == {}


@pytest.mark.unit
def test_library_archive_includes_every_stored_country(store, tmp_path):
    from plugins.upr.library import build_library_archive, store_rendered_country

    afg = tmp_path / "afg.png"
    afg.write_bytes(b"afg-png")
    bgd = tmp_path / "bgd.png"
    bgd.write_bytes(b"bgd-png")
    store_rendered_country(
        assigned_form_id=7,
        export_format="png",
        lang="en",
        aes_id=11,
        files=[("combined", afg, "AFG_combined.png")],
        package_filename="AFG_2024.zip",
    )
    store_rendered_country(
        assigned_form_id=7,
        export_format="png",
        lang="en",
        aes_id=22,
        files=[("reach", bgd, "BGD_reach.png")],
        package_filename="BGD_2024.zip",
    )
    data, filename = build_library_archive(7, "png", "en")
    assert filename == "upr-png-all-countries.zip"
    archive = zipfile.ZipFile(io.BytesIO(data))
    assert archive.read("AFG_2024/AFG_combined.png") == b"afg-png"
    assert archive.read("BGD_2024/BGD_reach.png") == b"bgd-png"


@pytest.mark.unit
def test_library_status_ignores_corrupt_index(store):
    from plugins.upr.library import library_status

    store.files["library/1/png/en/index.json"] = b"not-json"
    assert library_status(1, "png", "en") == {}
