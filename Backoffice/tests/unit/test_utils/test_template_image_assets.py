"""Tests for template image asset helpers."""

import pytest

from app.utils.template_image_assets import (
    normalize_image_config,
    resolve_display_url,
    resolve_locale_image_source,
    validate_image_url,
)


class TestValidateImageUrl:
    def test_accepts_https(self):
        assert validate_image_url("https://example.org/logo.png") == "https://example.org/logo.png"

    def test_accepts_static_path(self):
        assert validate_image_url("/static/img/logo.png") == "/static/img/logo.png"

    def test_rejects_javascript(self):
        assert validate_image_url("javascript:alert(1)") is None

    def test_rejects_data_uri(self):
        assert validate_image_url("data:image/png;base64,abc") is None


class TestNormalizeImageConfig:
    def test_normalizes_sources(self, app):
        app.config["SUPPORTED_LANGUAGES"] = ["en", "fr"]
        raw = {
            "image": {
                "alignment": "left",
                "max_width": "50%",
                "sources": {
                    "en": {"source_type": "url", "url": "https://example.org/en.png"},
                    "fr": {"source_type": "upload", "storage_path": "1/v1/items/2/fr/a.png"},
                },
            }
        }
        result = normalize_image_config(raw)
        assert result["image"]["alignment"] == "left"
        assert result["image"]["sources"]["en"]["url"] == "https://example.org/en.png"
        assert result["image"]["sources"]["fr"]["storage_path"].endswith("a.png")


class TestResolveLocaleImageSource:
    def test_prefers_requested_locale(self):
        config = {
            "image": {
                "sources": {
                    "en": {"source_type": "url", "url": "https://example.org/en.png"},
                    "fr": {"source_type": "url", "url": "https://example.org/fr.png"},
                }
            }
        }
        src = resolve_locale_image_source(config, "fr", fallback_locales=["en"])
        assert src["url"] == "https://example.org/fr.png"

    def test_falls_back_to_english(self):
        config = {
            "image": {
                "sources": {
                    "en": {"source_type": "url", "url": "https://example.org/en.png"},
                }
            }
        }
        src = resolve_locale_image_source(config, "de", fallback_locales=["en"])
        assert src["url"] == "https://example.org/en.png"


class TestResolveDisplayUrl:
    def test_url_source_passthrough(self):
        url = resolve_display_url({"source_type": "url", "url": "https://example.org/x.png"})
        assert url == "https://example.org/x.png"

    def test_upload_source_builds_entry_url(self, app):
        with app.test_request_context():
            url = resolve_display_url(
                {"source_type": "upload", "storage_path": "1/v1/items/5/en/a.png"},
                item_id=5,
                language="en",
                for_entry=True,
            )
            assert "/forms/template-image/5/" in url
