from datetime import datetime, timezone

import pytest


class _LogoEntity:
    def __init__(self, *, entity_id, logo_filename=None, updated_at=None):
        self.id = entity_id
        self.logo_filename = logo_filename
        self.updated_at = updated_at


def test_sector_logo_url_uses_cdn_when_configured(app):
    from app.utils.sector_logo_urls import sector_logo_url

    sector = _LogoEntity(
        entity_id=3,
        logo_filename="Health.png",
        updated_at=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
    )
    app.config["STATIC_CDN_URL"] = "https://cdn.example/static"
    app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
    app.config["AZURE_STORAGE_CONNECTION_STRING"] = "DefaultEndpointsProtocol=https;AccountName=test;AccountKey=dGVzdA==;EndpointSuffix=core.windows.net"

    url = sector_logo_url(sector)
    expected_version = str(int(sector.updated_at.timestamp()))
    assert url == f"https://cdn.example/static/system/sectors/Health.png?v={expected_version}"


def test_sector_logo_url_falls_back_to_admin_route(app, client):
    from app.utils.sector_logo_urls import sector_logo_url

    sector = _LogoEntity(entity_id=7, logo_filename="Health.png")
    app.config["STATIC_CDN_URL"] = ""
    app.config["UPLOAD_STORAGE_PROVIDER"] = "filesystem"

    with app.test_request_context("/"):
        url = sector_logo_url(sector)
    assert url.endswith("/admin/sectors/7/logo")


def test_spef_icon_url_falls_back_to_admin_route(app, client):
    from app.utils.sector_logo_urls import spef_icon_url

    class _Spef:
        id = 4
        icon_filename = "SP1.png"
        updated_at = None

    app.config["STATIC_CDN_URL"] = ""
    app.config["UPLOAD_STORAGE_PROVIDER"] = "filesystem"

    with app.test_request_context("/"):
        url = spef_icon_url(_Spef())
    assert url.endswith("/admin/indicator-bank/spef-lookups/4/icon")


def test_spef_icon_url_none_without_icon(app):
    from app.utils.sector_logo_urls import spef_icon_url

    class _Spef:
        id = 1
        icon_filename = None

    assert spef_icon_url(_Spef()) is None
