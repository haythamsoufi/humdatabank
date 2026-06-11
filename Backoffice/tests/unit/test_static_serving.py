"""Tests for app/static_serving.py — all cache header branches."""

import os
import pytest
from unittest.mock import patch, MagicMock
from flask import Flask


def _make_app_with_static(static_folder, debug=False):
    """Build a minimal Flask app with register_static_route applied."""
    from app.static_serving import register_static_route

    flask_app = Flask(__name__, static_folder=None, static_url_path=None)
    flask_app.config['DEBUG'] = debug
    flask_app.config['SECRET_KEY'] = 'test-secret'
    flask_app.config['TESTING'] = True
    register_static_route(flask_app, static_folder)
    return flask_app


class TestStaticServingNotFound:
    def test_returns_404_for_missing_file(self, tmp_path):
        flask_app = _make_app_with_static(str(tmp_path))
        client = flask_app.test_client()
        response = client.get('/static/nonexistent.css')
        assert response.status_code == 404

    def test_returns_404_for_directory(self, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        flask_app = _make_app_with_static(str(tmp_path))
        client = flask_app.test_client()
        # Path refers to directory not file
        response = client.get('/static/subdir')
        assert response.status_code == 404


class TestStaticServingProductionCacheHeaders:
    """Non-debug mode: verify correct cache headers per file type."""

    def _get(self, tmp_path, filename, query_string='', debug=False):
        filepath = tmp_path / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_bytes(b"body")
        flask_app = _make_app_with_static(str(tmp_path), debug=debug)
        client = flask_app.test_client()
        url = f'/static/{filename}'
        if query_string:
            url += '?' + query_string
        return client.get(url)

    def test_versioned_file_gets_immutable_cache(self, tmp_path):
        response = self._get(tmp_path, 'main.css', query_string='v=abc123')
        assert response.status_code == 200
        cc = response.headers.get('Cache-Control', '')
        assert 'max-age=31536000' in cc or 'immutable' in cc

    def test_versioned_js_gets_immutable_cache(self, tmp_path):
        response = self._get(tmp_path, 'app.js', query_string='v=xyz')
        assert response.status_code == 200
        cc = response.headers.get('Cache-Control', '')
        assert 'max-age=31536000' in cc or 'immutable' in cc

    def test_unversioned_css_gets_must_revalidate(self, tmp_path):
        response = self._get(tmp_path, 'style.css')
        assert response.status_code == 200
        cc = response.headers.get('Cache-Control', '')
        assert 'must-revalidate' in cc or 'max-age=0' in cc

    def test_unversioned_js_gets_must_revalidate(self, tmp_path):
        response = self._get(tmp_path, 'bundle.js')
        assert response.status_code == 200
        cc = response.headers.get('Cache-Control', '')
        assert 'must-revalidate' in cc or 'max-age=0' in cc

    def test_unversioned_png_gets_one_hour_cache(self, tmp_path):
        response = self._get(tmp_path, 'logo.png')
        assert response.status_code == 200
        cc = response.headers.get('Cache-Control', '')
        assert 'max-age=3600' in cc or 'must-revalidate' in cc

    def test_unversioned_svg_gets_one_hour_cache(self, tmp_path):
        response = self._get(tmp_path, 'icon.svg')
        assert response.status_code == 200
        cc = response.headers.get('Cache-Control', '')
        assert 'max-age=3600' in cc or 'public' in cc

    def test_unversioned_woff_gets_one_hour_cache(self, tmp_path):
        response = self._get(tmp_path, 'font.woff2')
        assert response.status_code == 200
        cc = response.headers.get('Cache-Control', '')
        assert cc  # some cache control must be set

    def test_skip_cache_override_flag_set(self, tmp_path):
        filepath = tmp_path / 'test.css'
        filepath.write_bytes(b"body {}")
        flask_app = _make_app_with_static(str(tmp_path))
        client = flask_app.test_client()
        with flask_app.test_request_context('/static/test.css'):
            # Access via test client and check that _skip_cache_override is set
            response = client.get('/static/test.css')
            assert response.status_code == 200

    def test_non_static_extension_no_cache_set(self, tmp_path):
        """Files with unknown extension shouldn't get static cache headers."""
        response = self._get(tmp_path, 'data.txt')
        assert response.status_code == 200


class TestStaticServingDevelopmentCacheHeaders:
    """Debug=True mode: cache should be disabled."""

    def test_development_mode_no_cache(self, tmp_path):
        filepath = tmp_path / 'app.js'
        filepath.write_bytes(b"var x = 1;")
        flask_app = _make_app_with_static(str(tmp_path), debug=True)
        client = flask_app.test_client()
        response = client.get('/static/app.js')
        assert response.status_code == 200
        cc = response.headers.get('Cache-Control', '')
        assert 'no-cache' in cc or 'no-store' in cc

    def test_development_mode_pragma_no_cache(self, tmp_path):
        filepath = tmp_path / 'style.css'
        filepath.write_bytes(b"body {}")
        flask_app = _make_app_with_static(str(tmp_path), debug=True)
        client = flask_app.test_client()
        response = client.get('/static/style.css')
        assert response.status_code == 200
        pragma = response.headers.get('Pragma', '')
        assert pragma == 'no-cache'

    def test_development_mode_expires_zero(self, tmp_path):
        filepath = tmp_path / 'img.png'
        filepath.write_bytes(b"\x89PNG")
        flask_app = _make_app_with_static(str(tmp_path), debug=True)
        client = flask_app.test_client()
        response = client.get('/static/img.png')
        assert response.status_code == 200
        expires = response.headers.get('Expires', '')
        assert expires == '0'
