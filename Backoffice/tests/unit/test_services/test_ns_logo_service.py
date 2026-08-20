"""Tests for FDRS ISO3 National Society logo sync (no live GitHub)."""
from __future__ import annotations

import json

import pytest

from app.models.organization import NationalSociety
from app.services.organization.ns_logo_service import (
    iso3_from_logo_filename,
    sync_ns_logos_from_github,
)
from tests.factories import create_test_country

pytestmark = [pytest.mark.unit]


def test_iso3_from_logo_filename():
    assert iso3_from_logo_filename("BGD.png") == "BGD"
    assert iso3_from_logo_filename("bgd.JPG") == "BGD"
    assert iso3_from_logo_filename("ns_logos/BGD.png") == "BGD"
    assert iso3_from_logo_filename("README.md") is None
    assert iso3_from_logo_filename("BG.png") is None
    assert iso3_from_logo_filename("") is None


def _github_listing(*names: str) -> bytes:
    rows = [
        {
            "name": name,
            "download_url": f"https://raw.githubusercontent.com/FDRS-ifrc/general/main/ns_logos/{name}",
        }
        for name in names
    ]
    return json.dumps(rows).encode("utf-8")


def _fetch_factory(listing: bytes, blobs: dict[str, bytes]):
    def fetch(url: str) -> bytes:
        if "api.github.com" in url:
            return listing
        for name, data in blobs.items():
            if url.endswith(name) or name in url:
                return data
        return b""

    return fetch


def test_sync_attaches_logo_by_country_iso3(app, db_session, monkeypatch):
    country = create_test_country(
        db_session, name="Zedland Logo Sync", iso3="QLX", iso2="QX"
    )
    ns = NationalSociety(name="Zedland Red Cross", country_id=country.id, is_active=True)
    db_session.add(ns)
    db_session.commit()

    monkeypatch.setattr(
        "app.services.organization.ns_logo_service.save_system_logo",
        lambda *_args, **_kwargs: "QLX.png",
    )
    fetch = _fetch_factory(_github_listing("QLX.png"), {"QLX.png": b"png-bytes"})
    result = sync_ns_logos_from_github(fetch=fetch)
    db_session.refresh(ns)
    assert result["updated"] == 1
    assert result["skipped"] == 0
    assert ns.logo_filename == "QLX.png"


def test_sync_skips_existing_unless_overwrite(app, db_session, monkeypatch):
    country = create_test_country(
        db_session, name="Zedland Logo Skip", iso3="QSK", iso2="QK"
    )
    ns = NationalSociety(
        name="Skip Red Cross",
        country_id=country.id,
        is_active=True,
        logo_filename="QSK.png",
    )
    db_session.add(ns)
    db_session.commit()

    called = []

    def _save(*args, **kwargs):
        called.append(1)
        return "QSK.png"

    monkeypatch.setattr("app.services.organization.ns_logo_service.save_system_logo", _save)
    fetch = _fetch_factory(_github_listing("QSK.png"), {"QSK.png": b"png-bytes"})
    result = sync_ns_logos_from_github(fetch=fetch)
    assert result["skipped"] == 1
    assert result["updated"] == 0
    assert not called


def test_sync_dry_run_does_not_write(app, db_session, monkeypatch):
    country = create_test_country(
        db_session, name="Zedland Logo Dry", iso3="QDR", iso2="QD"
    )
    ns = NationalSociety(name="Dry Red Cross", country_id=country.id, is_active=True)
    db_session.add(ns)
    db_session.commit()

    monkeypatch.setattr(
        "app.services.organization.ns_logo_service.save_system_logo",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not save")),
    )
    fetch = _fetch_factory(_github_listing("QDR.png"), {"QDR.png": b"png-bytes"})
    result = sync_ns_logos_from_github(dry_run=True, fetch=fetch)
    db_session.refresh(ns)
    assert result["dry_run"] is True
    assert result["updated"] == 1
    assert ns.logo_filename is None
