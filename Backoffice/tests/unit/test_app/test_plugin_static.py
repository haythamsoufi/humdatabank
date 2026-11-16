"""Tests for app/assets/plugin_static.py: shared versioning and cache policy for plugin static routes."""

import os

import pytest
from flask import Flask

from app.assets.plugin_static import (
    plugin_asset_version,
    plugin_static_url,
    send_plugin_static,
)


def _make_app(static_dir, *, debug=False, private=False, asset_version="d1"):
    app = Flask(__name__, static_folder=None, static_url_path=None)
    app.config.update(DEBUG=debug, TESTING=True, SECRET_KEY="test", ASSET_VERSION=asset_version)

    @app.route("/demo/static/<path:filename>", endpoint="demo.static_file")
    def static_file(filename):
        return send_plugin_static(static_dir, filename, private=private)

    return app


class TestVersion:
    def test_token_is_deploy_version_plus_content_hash(self, tmp_path):
        (tmp_path / "js").mkdir()
        (tmp_path / "js" / "a.js").write_text("one", encoding="utf-8")
        app = _make_app(tmp_path)
        with app.app_context():
            version = plugin_asset_version(tmp_path, "js/a.js")
        deploy, _, token = version.partition(".")
        assert deploy == "d1"
        assert len(token) == 12

    def test_content_change_changes_token_even_when_mtime_is_unchanged(self, tmp_path):
        script = tmp_path / "a.js"
        script.write_text("one", encoding="utf-8")
        mtime = script.stat().st_mtime_ns
        app = _make_app(tmp_path)
        with app.app_context():
            first = plugin_asset_version(tmp_path, "a.js")
            script.write_text("two-changed", encoding="utf-8")
            os.utime(script, ns=(mtime, mtime))
            second = plugin_asset_version(tmp_path, "a.js")
        assert first != second

    def test_deploy_version_change_changes_token(self, tmp_path):
        (tmp_path / "a.js").write_text("same", encoding="utf-8")
        with _make_app(tmp_path, asset_version="d1").app_context():
            first = plugin_asset_version(tmp_path, "a.js")
        with _make_app(tmp_path, asset_version="d2").app_context():
            second = plugin_asset_version(tmp_path, "a.js")
        assert first.split(".")[1] == second.split(".")[1]
        assert first != second

    def test_missing_file_falls_back_to_deploy_version(self, tmp_path):
        with _make_app(tmp_path).app_context():
            assert plugin_asset_version(tmp_path, "missing.js") == "d1"

    def test_token_has_a_hash_part_for_an_existing_file(self, tmp_path):
        (tmp_path / "a.js").write_text("x", encoding="utf-8")
        deploy, _, token = plugin_asset_version(tmp_path, "a.js").partition(".")
        assert deploy and len(token) == 12

    def test_url_includes_version(self, tmp_path):
        (tmp_path / "a.js").write_text("x", encoding="utf-8")
        app = _make_app(tmp_path)
        with app.test_request_context("/"):
            url = plugin_static_url("demo.static_file", tmp_path, "a.js")
        assert url.startswith("/demo/static/a.js?v=d1.")


class TestCacheHeaders:
    def _get(self, tmp_path, name, query="", **options):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"body")
        client = _make_app(tmp_path, **options).test_client()
        return client.get(f"/demo/static/{name}{query}")

    def test_versioned_is_immutable(self, tmp_path):
        response = self._get(tmp_path, "a.js", "?v=d1.abc")
        cc = response.headers["Cache-Control"]
        assert "max-age=31536000" in cc and "immutable" in cc and "public" in cc

    def test_versioned_is_immutable_in_debug_too(self, tmp_path):
        response = self._get(tmp_path, "a.js", "?v=d1.abc", debug=True)
        assert "immutable" in response.headers["Cache-Control"]
        assert "no-store" not in response.headers["Cache-Control"]

    def test_unversioned_code_revalidates(self, tmp_path):
        response = self._get(tmp_path, "a.css")
        cc = response.headers["Cache-Control"]
        assert "max-age=0" in cc and "must-revalidate" in cc

    def test_unversioned_other_files_get_one_hour(self, tmp_path):
        response = self._get(tmp_path, "logo.png")
        assert "max-age=3600" in response.headers["Cache-Control"]

    def test_unversioned_in_debug_is_not_stored(self, tmp_path):
        response = self._get(tmp_path, "a.js", debug=True)
        assert "no-store" in response.headers["Cache-Control"]
        assert response.headers["Pragma"] == "no-cache"

    def test_login_gated_files_are_private(self, tmp_path):
        response = self._get(tmp_path, "a.js", "?v=d1.abc", private=True)
        cc = response.headers["Cache-Control"]
        assert "private" in cc and "public" not in cc

    def test_security_headers_middleware_is_told_to_leave_cache_control_alone(self, tmp_path):
        target = tmp_path / "a.js"
        target.write_bytes(b"body")
        app = _make_app(tmp_path)
        with app.test_request_context("/demo/static/a.js?v=d1.abc"):
            response = send_plugin_static(tmp_path, "a.js")
        assert response._skip_cache_override is True

    def test_missing_file_is_404(self, tmp_path):
        client = _make_app(tmp_path).test_client()
        assert client.get("/demo/static/nope.js").status_code == 404

    def test_path_traversal_is_rejected(self, tmp_path):
        (tmp_path.parent / "secret.txt").write_text("secret", encoding="utf-8")
        client = _make_app(tmp_path).test_client()
        assert client.get("/demo/static/../secret.txt").status_code == 404
        assert client.get("/demo/static/..%2fsecret.txt").status_code == 404


@pytest.mark.parametrize(
    "module_path",
    [
        "plugins/upr/routes.py",
        "plugins/fdrs/currency_routes.py",
        "plugins/ifrc/routes.py",
        "plugins/ifrc/decisions/routes.py",
        "plugins/ifrc/pb_progress/routes.py",
    ],
)
def test_plugin_static_routes_use_the_shared_helper(module_path):
    """Plugins must not grow their own versioning or cache rules again."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[3] / module_path).read_text(encoding="utf-8")
    assert "send_plugin_static" in source or "apply_plugin_static_cache" in source
    assert "plugin_static_url" in source or "plugin_asset_version" in source
    assert "send_from_directory" not in source
    assert "st_mtime" not in source
