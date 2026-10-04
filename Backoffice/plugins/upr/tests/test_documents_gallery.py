"""Public UPR documents gallery: IFRC parsing, filters, and the Power BI HTML page."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from flask import Flask

from app.plugins.jinja_plugin_loader import PluginTemplateLoader
from plugins.upr import bp
from plugins.upr import documents_gallery as gallery

_TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


@pytest.fixture(autouse=True)
def _clear_cache():
    gallery.reset_gallery_cache_for_tests()
    yield
    gallery.reset_gallery_cache_for_tests()


def _doc(**overrides):
    payload = {
        "url": "https://go.ifrc.org/DownloadFile/10/kenya.pdf",
        "title": "Kenya Unified Plan",
        "country_code": "KE",
        "country_name": "Kenya",
        "appeals_type_id": 1851,
        "document_type_label": "Plan",
        "year": 2026,
        "published_at": datetime(2026, 3, 4, tzinfo=timezone.utc),
    }
    payload.update(overrides)
    return gallery.UprGalleryDocument(**payload)


def _item(**overrides):
    payload = {
        "Hidden": False,
        "BaseDirectory": "https://go.ifrc.org/",
        "BaseFileName": "DownloadFile/10/kenya.pdf",
        "AppealsTypeId": 1851,
        "AppealOrigType": "INP_2026_KE",
        "AppealsName": "Kenya Unified Plan",
        "LocationCountryCode": "ke",
        "LocationCountryName": "Kenya (KE)",
        "AppealsDate": "2026-03-04T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_parse_matches_mobile_catalogue_rules():
    items = [
        _item(),
        _item(BaseFileName="DownloadFile/10/duplicate.pdf", AppealsName="Duplicate row"),
        _item(Hidden=True, BaseFileName="DownloadFile/11/hidden.pdf", AppealsName="Hidden plan"),
        _item(BaseDirectory="http://go.ifrc.org/", BaseFileName="DownloadFile/12/plain.pdf"),
        _item(BaseFileName="", AppealsName="Missing file"),
        _item(
            BaseFileName="DownloadFile/13/haiti.pdf",
            AppealsTypeId=10009,
            AppealOrigType="MYR",
            AppealsName="Haiti mid-year INP_2024_HT",
            LocationCountryCode="HT",
            LocationCountryName="Haiti (HT)",
            AppealsDate="/Date(1710000000000)/",
        ),
        {
            "Hidden": False,
            "BaseDirectory": "https://evil.example/",
            "BaseFileName": "DownloadFile/99/phish.pdf",
            "AppealsName": "<script>alert(1)</script>",
            "AppealsTypeId": 1851,
        },
    ]

    docs = gallery.parse_ifrc_appeals(
        items,
        url_ok=lambda url: url.startswith("https://go.ifrc.org/"),
    )

    assert [doc.title for doc in docs] == ["Kenya Unified Plan", "Haiti mid-year INP_2024_HT"]
    kenya, haiti = docs
    assert kenya.country_name == "Kenya"
    assert kenya.country_code == "KE"
    assert kenya.year == 2026
    assert kenya.document_type_label == "Plan"
    assert kenya.published_at == datetime(2026, 3, 4, tzinfo=timezone.utc)
    assert haiti.appeals_type_id == 10009
    assert haiti.document_type_label == "Mid-Year Report"
    assert haiti.country_name == "Haiti"
    assert haiti.year == 2024
    assert haiti.published_at is not None
    assert haiti.published_at.year == 2024


def test_filters_sort_and_fresh_window():
    older = _doc(
        url="https://go.ifrc.org/DownloadFile/2/old.pdf",
        title="Older plan",
        country_name="Zambia",
        country_code="ZM",
        year=2024,
        published_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
    )
    undated = _doc(
        url="https://go.ifrc.org/DownloadFile/3/none.pdf",
        title="No date",
        country_name=None,
        country_code=None,
        year=None,
        published_at=None,
        appeals_type_id=10011,
        document_type_label="Annual Report",
    )
    kenya = _doc()
    filters = gallery.filters_from_args({"country": " kenya ", "sort": "nope", "year": "1999", "q": "  plan  "})
    assert filters.country == "kenya"
    assert filters.sort == gallery.SORT_NEWEST
    assert filters.year is None
    assert filters.q == "plan"

    assert gallery.document_matches(kenya, gallery.GalleryFilters(country="KENYA"))
    assert not gallery.document_matches(older, gallery.GalleryFilters(country="Kenya"))
    assert gallery.document_matches(kenya, gallery.GalleryFilters(q="Kenya plan"))
    assert not gallery.document_matches(older, gallery.GalleryFilters(type_id=10011))

    newest = gallery.sort_documents([older, undated, kenya], gallery.SORT_NEWEST)
    assert [doc.title for doc in newest] == ["Kenya Unified Plan", "Older plan", "No date"]
    by_country = gallery.sort_documents([undated, older, kenya], gallery.SORT_COUNTRY_ZA)
    assert [doc.country_name for doc in by_country] == ["Zambia", "Kenya", None]

    now = datetime(2026, 10, 4, tzinfo=timezone.utc)
    assert gallery.is_published_recently(datetime(2026, 10, 2, tzinfo=timezone.utc), now)
    assert gallery.is_published_recently(datetime(2026, 10, 5, tzinfo=timezone.utc), now)
    assert not gallery.is_published_recently(datetime(2026, 10, 1, tzinfo=timezone.utc), now)
    assert not gallery.is_published_recently(None, now)


def test_catalogue_cache_and_stale_fallback(monkeypatch):
    calls = {"n": 0}
    docs = [_doc()]

    def fetch():
        calls["n"] += 1
        if calls["n"] > 1:
            raise gallery.UprGalleryUnavailable("upstream")
        return docs

    monkeypatch.setattr(gallery, "_fetch_from_ifrc", fetch)
    monkeypatch.setattr(gallery, "_CACHE_TTL_SECONDS", 600)
    assert gallery.load_gallery_documents() == docs
    assert gallery.load_gallery_documents() == docs
    assert calls["n"] == 1

    monkeypatch.setattr(gallery, "_CACHE_TTL_SECONDS", 0)
    assert gallery.load_gallery_documents() == docs
    assert calls["n"] == 2


def test_fetch_keeps_allowlisted_pdfs_and_maps_auth_failure(monkeypatch):
    app = Flask(__name__)
    app.config["IFRC_API_USER"] = "api-user"
    app.config["IFRC_API_PASSWORD"] = "secret-value"
    app.config["IFRC_DOCUMENT_ALLOWED_HOSTS"] = ["go.ifrc.org"]

    class Response:
        def __init__(self, status, payload):
            self.status_code = status
            self._payload = payload

        def raise_for_status(self):
            if self.status_code >= 400:
                error = requests.HTTPError(str(self.status_code))
                error.response = self
                raise error

        def json(self):
            return self._payload

    monkeypatch.setattr(
        gallery.requests,
        "get",
        lambda *args, **kwargs: Response(
            200,
            [
                _item(),
                _item(
                    BaseDirectory="https://evil.example/",
                    BaseFileName="DownloadFile/99/phish.pdf",
                    AppealsName="Not listed",
                ),
            ],
        ),
    )
    with app.app_context():
        docs = gallery._fetch_from_ifrc()
    assert [doc.title for doc in docs] == ["Kenya Unified Plan"]
    assert docs[0].url.startswith("https://go.ifrc.org/")
    assert "secret-value" not in docs[0].url

    monkeypatch.setattr(gallery.requests, "get", lambda *args, **kwargs: Response(401, []))
    with app.app_context():
        with pytest.raises(gallery.UprGalleryUnavailable) as caught:
            gallery._fetch_from_ifrc()
    assert caught.value.code == "auth"


def _gallery_app():
    app = Flask(__name__)
    app.config.update(TESTING=True, DEBUG=True, SECRET_KEY="test", RATE_LIMIT_SKIP_DEBUG=True)
    app.jinja_loader = PluginTemplateLoader(lambda pid: _TEMPLATES if pid == "upr" else None)
    app.register_blueprint(bp)
    return app


def test_gallery_page_escapes_titles_and_applies_dropdown_filters(monkeypatch):
    malicious = _doc(
        url="https://go.ifrc.org/DownloadFile/8/x.pdf",
        title='<img src=x onerror=alert(1)>',
        country_name="Kenya",
        year=2026,
        published_at=datetime.now(timezone.utc),
    )
    other = _doc(
        url="https://go.ifrc.org/DownloadFile/9/old.pdf",
        title="Zambia Annual Report",
        country_name="Zambia",
        country_code="ZM",
        appeals_type_id=10011,
        document_type_label="Annual Report",
        year=2020,
        published_at=datetime(2020, 5, 1, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(gallery, "load_gallery_documents", lambda: [malicious, other])
    client = _gallery_app().test_client()
    response = client.get("/api/v1/upr/documents?year=2026")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert "<img src=x" not in html
    assert "&lt;img" in html
    assert 'name="country"' in html
    assert 'name="type"' in html
    assert 'name="year"' in html
    assert 'name="sort"' in html
    assert "All Countries" in html
    assert "Mid-Year Report" not in html
    assert "Fresh" in html
    assert 'value="2026" selected' in html
    assert "IFRC GO" not in html
    assert "url_b64=" in html
    assert 'loading="lazy"' in html
    assert "data-thumb" not in html

    hidden_at = html.index('data-year="2020"')
    tag = html[html.rfind("<a", 0, hidden_at): html.index(">", hidden_at)]
    assert "hidden" in tag
    visible_at = html.index('data-year="2026"')
    visible_tag = html[html.rfind("<a", 0, visible_at): html.index(">", visible_at)]
    assert "hidden" not in visible_tag


def test_powerbi_snippet_is_an_iframe_and_does_not_fetch(monkeypatch):
    def explode():
        raise AssertionError("gallery fetch should not run for the snippet")

    monkeypatch.setattr(gallery, "load_gallery_documents", explode)
    client = _gallery_app().test_client()
    response = client.get('/api/v1/upr/documents?format=powerbi&country="><script>')
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert body.startswith("<!-- Power BI HTML visual:")
    assert "<iframe" in body
    assert 'title="Unified plans and reports"' in body
    assert "<script>" not in body
    assert "format=powerbi" not in body
    assert "country=" in body
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"


def test_gallery_error_page_has_filters_and_no_secret(monkeypatch):
    def fail():
        raise gallery.UprGalleryUnavailable("credentials")

    monkeypatch.setattr(gallery, "load_gallery_documents", fail)
    response = _gallery_app().test_client().get("/api/v1/upr/documents")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Documents are not available" in html
    assert "IFRC GO" not in html
    assert "Documents unavailable" in html
    assert 'name="country"' in html
    assert "secret" not in html.lower()


def test_gallery_headers_allow_power_bi_framing():
    from types import SimpleNamespace

    from flask import Flask

    from app.middleware.security_headers import add_security_headers
    from plugins.upr.plugin import UprPlugin

    override = next(
        item for item in UprPlugin().get_csp_overrides()
        if item.endpoint == "upr.upr_documents_gallery"
    )
    app = Flask(__name__)
    app.plugin_manager = SimpleNamespace(
        get_csp_override=lambda endpoint, path: override,
    )
    with app.test_request_context("/api/v1/upr/documents"):
        response = app.response_class("ok")
        response.mimetype = "text/html"
        headers = add_security_headers(response).headers
    assert "X-Frame-Options" not in headers
    assert headers["Cross-Origin-Resource-Policy"] == "cross-origin"
    assert "frame-ancestors" not in headers["Content-Security-Policy"]


def test_thumbnail_get_uses_url_b64_and_serves_cached_jpeg():
    import base64
    from hashlib import sha256

    from plugins.upr.mobile import (
        _UNIFIED_PLANNING_THUMB_JPEG,
        _UNIFIED_PLANNING_THUMB_LOCK,
        _decode_thumbnail_url_b64,
        unified_planning_thumbnail,
    )

    pdf_url = "https://go.ifrc.org/DownloadFile/10/kenya.pdf"
    src = gallery._thumbnail_src(pdf_url)
    token = src.split("url_b64=", 1)[1]
    decoded, error = _decode_thumbnail_url_b64(token, 32768)
    assert error is None
    assert decoded == pdf_url
    assert "go.ifrc.org" not in token
    assert base64.urlsafe_b64decode(token + "=" * ((-len(token)) % 4)).decode() == pdf_url

    cache_key = sha256(pdf_url.encode("utf-8")).hexdigest()
    jpeg = b"\xff\xd8\xff\xe0cached-cover"
    app = Flask(__name__)
    app.config["IFRC_DOCUMENT_ALLOWED_HOSTS"] = ["go.ifrc.org"]
    with _UNIFIED_PLANNING_THUMB_LOCK:
        _UNIFIED_PLANNING_THUMB_JPEG[cache_key] = jpeg
    try:
        with app.test_request_context("/api/mobile/v1/data/unified-planning-thumbnail?" + src.split("?", 1)[1]):
            response = unified_planning_thumbnail()
        assert response.status_code == 200
        assert response.mimetype == "image/jpeg"
        assert response.get_data() == jpeg
    finally:
        with _UNIFIED_PLANNING_THUMB_LOCK:
            _UNIFIED_PLANNING_THUMB_JPEG.pop(cache_key, None)


def test_api_docs_list_the_public_gallery():
    from plugins.upr.upr_data_routes import upr_api_documentation

    by_path = {item["path"]: item for item in upr_api_documentation()["endpoints"]}
    gallery_doc = by_path["/api/v1/upr/documents"]
    assert gallery_doc["auth"] == "public"
    names = {param["name"] for param in gallery_doc["parameters"]}
    assert names == {"format", "q", "country", "type", "year", "sort"}
    sort = next(param for param in gallery_doc["parameters"] if param["name"] == "sort")
    assert sort["values"] == ["newest", "oldest", "country_az", "country_za"]
