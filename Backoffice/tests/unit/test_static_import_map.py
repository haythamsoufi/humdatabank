"""Tests for scoped ES module import map generation."""

from app.static_import_map import build_scoped_import_map, clear_import_map_cache, forms_module_import_map


def test_build_scoped_import_map_maps_relative_imports(tmp_path):
    forms_dir = tmp_path / "js" / "forms"
    modules_dir = forms_dir / "modules"
    modules_dir.mkdir(parents=True)
    (forms_dir / "entry-form.js").write_text(
        "import './main.js';\nimport './modules/debug.js';\n",
        encoding="utf-8",
    )
    (forms_dir / "main.js").write_text(
        "import './modules/debug.js';\nimport('./modules/matrix-handler.js');\n",
        encoding="utf-8",
    )
    (modules_dir / "debug.js").write_text("// debug\n", encoding="utf-8")
    (modules_dir / "matrix-handler.js").write_text("// matrix\n", encoding="utf-8")
    (modules_dir / "pdf-export.js").write_text(
        "import { debugLog } from '../modules/debug.js';\n",
        encoding="utf-8",
    )

    def url_for(rel: str) -> str:
        return f"https://cdn.example/static/{rel}?v=test"

    result = build_scoped_import_map(
        static_root=tmp_path,
        tree_relative="js/forms",
        cdn_base="https://cdn.example/static",
        origin="https://app.example/",
        versioned_url_for=url_for,
    )

    scopes = result["scopes"]
    forms_scope = scopes["https://cdn.example/static/js/forms/"]
    modules_scope = scopes["https://cdn.example/static/js/forms/modules/"]

    assert forms_scope["./main.js"] == "https://cdn.example/static/js/forms/main.js?v=test"
    assert forms_scope["./modules/debug.js"] == "https://cdn.example/static/js/forms/modules/debug.js?v=test"
    assert forms_scope["./modules/matrix-handler.js"] == "https://cdn.example/static/js/forms/modules/matrix-handler.js?v=test"
    assert modules_scope["../modules/debug.js"] == "https://cdn.example/static/js/forms/modules/debug.js?v=test"


def test_forms_module_import_map_uses_flask_static_without_cdn(app):
    clear_import_map_cache()
    app.config["STATIC_CDN_URL"] = ""
    app.config["ASSET_VERSION"] = "abc123"

    with app.test_request_context("/"):
        result = forms_module_import_map(app, "http://localhost:5000/")

    assert "scopes" in result
    assert result["scopes"]
    sample_scope = next(iter(result["scopes"].values()))
    sample_url = next(iter(sample_scope.values()))
    assert "?v=abc123." in sample_url
    assert sample_url.startswith("http://localhost:5000/static/")


def test_forms_module_import_map_uses_cdn_when_configured(app):
    clear_import_map_cache()
    app.config["STATIC_CDN_URL"] = "https://blob.example/static"
    app.config["ASSET_VERSION"] = "deploy1"

    with app.test_request_context("/"):
        result = forms_module_import_map(app, "http://localhost:5000/")

    sample_scope = next(iter(result["scopes"].values()))
    sample_url = next(iter(sample_scope.values()))
    assert sample_url.startswith("https://blob.example/static/")
    assert "?v=deploy1." in sample_url
