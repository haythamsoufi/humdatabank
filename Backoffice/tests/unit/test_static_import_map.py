"""Tests for scoped ES module import map generation."""

import re
from pathlib import Path

from app.static_import_map import (
    FORM_BUILDER_TEMPLATE_MODULES,
    build_scoped_import_map,
    clear_import_map_cache,
    form_builder_import_map,
    forms_module_import_map,
)

BACKOFFICE = Path(__file__).resolve().parents[2]
FORM_BUILDER_TEMPLATE = BACKOFFICE / "app" / "templates" / "forms" / "form_builder" / "form_builder.html"


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
        unversioned_url_for=lambda rel: f"https://cdn.example/static/{rel}",
    )

    scopes = result["scopes"]
    forms_scope = scopes["https://cdn.example/static/js/forms/"]
    modules_scope = scopes["https://cdn.example/static/js/forms/modules/"]

    assert forms_scope["https://cdn.example/static/js/forms/main.js"] == "https://cdn.example/static/js/forms/main.js?v=test"
    assert forms_scope["https://cdn.example/static/js/forms/modules/debug.js"] == "https://cdn.example/static/js/forms/modules/debug.js?v=test"
    assert forms_scope["https://cdn.example/static/js/forms/modules/matrix-handler.js"] == "https://cdn.example/static/js/forms/modules/matrix-handler.js?v=test"
    assert modules_scope["https://cdn.example/static/js/forms/modules/debug.js"] == "https://cdn.example/static/js/forms/modules/debug.js?v=test"


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


def test_import_map_keys_are_absolute_urls(app):
    """Relative keys never match (resolved against the document URL) -> stale imports."""
    clear_import_map_cache()
    app.config["STATIC_CDN_URL"] = "https://blob.example/static"
    app.config["ASSET_VERSION"] = "deploy1"

    with app.test_request_context("/"):
        result = forms_module_import_map(app, "http://localhost:5000/")

    cdn_scope = result["scopes"]["https://blob.example/static/js/forms/modules/"]
    key = "https://blob.example/static/js/forms/modules/matrix/formatting.js"
    assert key in cdn_scope
    assert cdn_scope[key].startswith(key + "?v=deploy1.")
    for scope in result["scopes"].values():
        assert not any(k.startswith(".") for k in scope)


def _form_builder_map(app, cdn=""):
    clear_import_map_cache()
    app.config["STATIC_CDN_URL"] = cdn
    app.config["ASSET_VERSION"] = "fbdeploy"
    with app.test_request_context("/"):
        return form_builder_import_map(app, "http://localhost:5000/")


def test_form_builder_map_versions_form_submit_modules(app):
    """form-submit-ui.js / form-submit.js are relative imports of the versioned main.js."""
    result = _form_builder_map(app, "https://blob.example/static")
    # main.js (versioned entry) imports ./modules/form-submit-ui.js
    entry_scope = result["scopes"]["https://blob.example/static/js/form_builder/"]
    ui_key = "https://blob.example/static/js/form_builder/modules/form-submit-ui.js"
    assert entry_scope[ui_key].startswith(ui_key + "?v=fbdeploy.")
    modal = result["scopes"]["https://blob.example/static/js/form_builder/modules/modal/"]
    submit_key = "https://blob.example/static/js/form_builder/modules/modal/form-submit.js"
    assert modal[submit_key].startswith(submit_key + "?v=fbdeploy.")


def test_form_builder_map_covers_lib_and_components(app):
    result = _form_builder_map(app, "https://blob.example/static")
    lib_url = "https://blob.example/static/js/lib/waf-json-body.js"
    imported_from_ui = result["scopes"]["https://blob.example/static/js/form_builder/modules/"]
    assert imported_from_ui[lib_url].startswith(lib_url + "?v=fbdeploy.")
    components = [
        url
        for scope in result["scopes"].values()
        for key, url in scope.items()
        if key.endswith("/js/components/translation-modal.js")
    ]
    assert components and all("?v=fbdeploy." in url for url in components)


def test_form_builder_map_has_app_origin_fallback_scopes(app):
    result = _form_builder_map(app, "https://blob.example/static")
    assert "http://localhost:5000/static/js/form_builder/modules/" in result["scopes"]


def test_form_builder_map_versions_absolute_static_imports(app):
    """Inline/absolute ``/static/...`` imports resolve unversioned unless mapped globally."""
    result = _form_builder_map(app, "https://blob.example/static")
    imports = result["imports"]
    assert imports, "absolute /static/ imports must be mapped"
    for rel in FORM_BUILDER_TEMPLATE_MODULES:
        key = f"http://localhost:5000/static/{rel}"
        assert key in imports, rel
        assert imports[key].startswith(key + "?v=fbdeploy.")
    page_key = "http://localhost:5000/static/js/components/translation-utils.js"
    assert page_key in imports  # discovered from js/form_builder/modules/translation/page.js


def test_form_builder_template_modules_match_inline_imports():
    html = FORM_BUILDER_TEMPLATE.read_text(encoding="utf-8")
    inline = set(re.findall(r"""from\s+['"]/static/(js/[^'"]+\.js)['"]""", html))
    assert inline, "expected inline module imports in form_builder.html"
    assert inline <= set(FORM_BUILDER_TEMPLATE_MODULES), (
        "Add these to FORM_BUILDER_TEMPLATE_MODULES so they get ?v=: "
        f"{sorted(inline - set(FORM_BUILDER_TEMPLATE_MODULES))}"
    )


def test_form_builder_import_map_is_first_in_head():
    html = FORM_BUILDER_TEMPLATE.read_text(encoding="utf-8")
    head = html.split("{% block head %}", 1)[1].split("{% endblock %}", 1)[0]
    assert 'type="importmap"' in head
    assert "form_builder_import_map()" in head
    module_match = re.search(r"""type=["']module["']""", head)
    assert module_match is None or head.index('type="importmap"') < module_match.start()


def test_layout_map_versions_chatbot_modules_and_shared_lib(app):
    """Chatbot modules load on every page via layout.html; transport.js imports ../lib/."""
    from app.static_import_map import layout_import_map

    clear_import_map_cache()
    app.config["STATIC_CDN_URL"] = "https://blob.example/static"
    app.config["ASSET_VERSION"] = "layoutdeploy"
    with app.test_request_context("/"):
        result = layout_import_map(app, "http://localhost:5000/")

    chatbot = result["scopes"]["https://blob.example/static/js/chatbot/"]
    for name in ("core.js", "structured-payloads.js", "transport.js", "state.js"):
        key = f"https://blob.example/static/js/chatbot/{name}"
        assert key in chatbot, name
        assert chatbot[key].startswith(key + "?v=layoutdeploy.")
    waf_key = "https://blob.example/static/js/lib/waf-json-body.js"
    assert chatbot[waf_key].startswith(waf_key + "?v=layoutdeploy.")


def test_page_maps_include_layout_trees():
    """Pages that set page_import_map replace the layout map, so they must cover chatbot too."""
    from app.static_import_map import (
        FORM_BUILDER_IMPORT_TREES,
        FORMS_IMPORT_TREES,
        LAYOUT_IMPORT_TREES,
    )

    for tree in LAYOUT_IMPORT_TREES:
        assert tree in FORMS_IMPORT_TREES
        assert tree in FORM_BUILDER_IMPORT_TREES


def test_pages_with_own_import_map_opt_out_of_layout_map():
    layout = (BACKOFFICE / "app" / "templates" / "core" / "layout.html").read_text(encoding="utf-8")
    assert "layout_import_map()" in layout
    assert "page_import_map" in layout.split("{% block head %}", 1)[0]
    entry_form = (BACKOFFICE / "app" / "templates" / "forms" / "entry_form" / "entry_form.html").read_text(encoding="utf-8")
    for html in (entry_form, FORM_BUILDER_TEMPLATE.read_text(encoding="utf-8")):
        assert "{% set page_import_map = true %}" in html


def test_layout_renders_exactly_one_import_map_before_modules(app):
    clear_import_map_cache()
    app.config["STATIC_CDN_URL"] = ""
    with app.test_request_context("/"):
        from flask import render_template_string

        html = render_template_string(
            "{% extends 'core/layout.html' %}{% block content %}x{% endblock %}"
        )
    assert html.count('type="importmap"') == 1
    assert html.index('type="importmap"') < html.index('type="module"')
