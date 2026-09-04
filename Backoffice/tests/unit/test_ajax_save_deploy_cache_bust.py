"""Force-reload contract for assignment form static files.

A user who already opened /assignment/1593 before the WAF ajax-save fix
must receive the new module on the next visit. Saving then posts to
/assignment/1593?ajax=1 with the WAF wrap instead of a 403.

These tests do not need Flask or Postgres.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path
from types import SimpleNamespace

BACKOFFICE = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKOFFICE.parent
SW_PATH = BACKOFFICE / "app" / "static" / "js" / "sw.js"
UPLOAD_SCRIPT = BACKOFFICE / "azure" / "upload-static-assets.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-to-webapp.yml"
STATIC_SERVING = BACKOFFICE / "app" / "static_serving.py"
LAYOUT = BACKOFFICE / "app" / "templates" / "core" / "layout.html"
ENTRY_FORM = BACKOFFICE / "app" / "templates" / "forms" / "entry_form" / "entry_form.html"
IMPORT_MAP_PY = BACKOFFICE / "app" / "static_import_map.py"
STATIC_VERSION_PY = BACKOFFICE / "app" / "static_version.py"

AJAX_SAVE_REL = "js/forms/modules/ajax-save.js"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_import_map_module():
    existing = sys.modules.get("app")
    if existing is not None and hasattr(existing, "create_app"):
        from app import static_import_map
        return static_import_map

    sv = _load_module("static_version_standalone", STATIC_VERSION_PY)
    pkg = existing if isinstance(existing, types.ModuleType) else types.ModuleType("app")
    if existing is None:
        pkg.__path__ = [str(BACKOFFICE / "app")]
        sys.modules["app"] = pkg
    sys.modules["app.static_version"] = sv
    pkg.static_version = sv
    return _load_module("static_import_map_under_test", IMPORT_MAP_PY)


class BrowserHttpCache:
    """Client cache that will not revalidate a fresh ``immutable`` response."""

    def __init__(self, now: int = 0) -> None:
        self.now = now
        self.entries: dict[str, dict] = {}

    def store(self, url: str, *, body: str, cache_control: str, stored_at: int | None = None) -> None:
        match = re.search(r"max-age=(\d+)", cache_control or "")
        self.entries[url] = {
            "body": body,
            "cache_control": cache_control,
            "stored_at": self.now if stored_at is None else stored_at,
            "max_age": int(match.group(1)) if match else 0,
        }

    def lookup(self, url: str) -> dict | None:
        entry = self.entries.get(url)
        if not entry:
            return None
        if (self.now - entry["stored_at"]) >= entry["max_age"]:
            return None
        return entry

    def fetch(self, url: str, origin: dict) -> tuple[str, str]:
        cached = self.lookup(url)
        if cached is not None:
            return cached["body"], "cache"
        self.store(url, body=origin["body"], cache_control=origin["cache_control"])
        return origin["body"], "network"


class TestAssignment1593ContentChangeBustsAjaxSaveUrl:
    """Returning visitor on /assignment/1593 must request a new ajax-save.js URL."""

    def test_content_hash_changes_query_when_file_bytes_change(self, tmp_path):
        sv = _load_module("static_version_under_test", STATIC_VERSION_PY)
        ajax = tmp_path / "js" / "forms" / "modules" / "ajax-save.js"
        ajax.parent.mkdir(parents=True)
        ajax.write_text("export function initAjaxSave(){ /* pre-WAF */ }\n", encoding="utf-8")
        app = SimpleNamespace(
            static_folder=str(tmp_path),
            root_path=str(tmp_path),
            config={"ASSET_VERSION": "pinned-sha"},
        )
        before = sv.asset_query_version(app, AJAX_SAVE_REL)
        ajax.write_text("export function initAjaxSave(){ /* WAF b64 wrap */ }\n", encoding="utf-8")
        sv.clear_static_version_cache()
        after = sv.asset_query_version(app, AJAX_SAVE_REL)
        assert before.startswith("pinned-sha.")
        assert after.startswith("pinned-sha.")
        assert before != after, (
            "A returning /assignment/1593 visitor already has ajax-save.js "
            "cached as immutable. If ?v= stays the same when the file changes, "
            "they keep posting ?ajax=1 without the WAF wrap and get 403."
        )

    def test_import_map_ajax_save_url_includes_content_hash(self):
        module = _load_import_map_module()
        module.clear_import_map_cache()
        app = SimpleNamespace(
            static_folder=str(BACKOFFICE / "app" / "static"),
            root_path=str(BACKOFFICE / "app"),
            config={
                "ASSET_VERSION": "deploy-waf-fix",
                "STATIC_CDN_URL": "https://cdn.example/static",
            },
        )
        result = module.forms_module_import_map(app, "https://databank.example/")
        mapped = []
        for imports in result.get("scopes", {}).values():
            for specifier, url in imports.items():
                if specifier.endswith("ajax-save.js"):
                    mapped.append(url)
        assert mapped, "import map must mention ajax-save.js so nested imports get ?v="
        assert all("?v=deploy-waf-fix." in url for url in mapped)
        assert any(url.startswith("https://cdn.example/static/") for url in mapped)
        assert any(url.startswith("https://databank.example/static/") for url in mapped)

    def test_new_query_string_misses_immutable_http_cache(self):
        cache = BrowserHttpCache(now=0)
        cache.store(
            f"https://cdn.example/static/{AJAX_SAVE_REL}",
            body="OLD_PRE_WAF",
            cache_control="max-age=31536000, public, immutable",
        )
        cache.now = 3600
        body, via = cache.fetch(
            f"https://cdn.example/static/{AJAX_SAVE_REL}?v=pinned-sha.newhash",
            {"body": "NEW_WAF_FIX", "cache_control": "max-age=31536000, public, immutable"},
        )
        assert body == "NEW_WAF_FIX"
        assert via == "network"


class TestUploadScriptRewritesJsHeadersEveryDeploy:
    def test_incremental_path_rewrites_js_css_when_bytes_match(self):
        script = UPLOAD_SCRIPT.read_text(encoding="utf-8")
        assert "_list_local_js_css" in script
        assert "Always rewrite JS/CSS Cache-Control" in script
        assert "skipping sync and Cache-Control pass" not in script


class TestDeployWorkflowAlwaysUploadsStatic:
    def test_workflow_always_marks_static_changed(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        assert 'echo "changed=true" >> "$GITHUB_OUTPUT"' in workflow
        assert "No static file changes in latest commit; skipping static upload." not in workflow
        assert "git diff --name-only HEAD^..HEAD -- Backoffice/app/static" not in workflow

    def test_ajax_save_change_in_parent_commit_still_uploads(self, tmp_path):
        """The live workflow no longer diffs HEAD^; upload always runs."""
        workflow = WORKFLOW.read_text(encoding="utf-8")
        detect = workflow.split("- name: Detect static asset changes", 1)[1]
        detect = detect.split("- name: Set deployment target", 1)[0]
        assert "changed=true" in detect
        assert "changed=false" not in detect


class TestServiceWorkerDoesNotReusePathnameOnlyCache:
    def test_sw_keeps_query_string_in_cache_key(self):
        source = SW_PATH.read_text(encoding="utf-8")
        assert "u.search" in source
        assert "stripping query/hash" not in source
        assert "cache-first and ignore querystring" not in source
        assert "cache: 'reload'" in source
        assert "isCodeAsset" in source


class TestFlaskVersionedJsIsContentAddressed:
    def test_static_serving_documents_content_hash_bust(self):
        source = STATIC_SERVING.read_text(encoding="utf-8")
        assert "content-hash" in source or "content hash" in source


class TestEntryFormImportMapOrder:
    def test_entry_form_head_starts_with_import_map(self):
        text = ENTRY_FORM.read_text(encoding="utf-8")
        head = text.split("{% block head %}", 1)[1].split("{% endblock %}", 1)[0]
        assert 'type="importmap"' in head
        import_at = head.index('type="importmap"')
        module_match = re.search(r'type=["\']module["\']', head)
        assert module_match is None or import_at < module_match.start()

    def test_layout_has_no_module_script_before_head_block(self):
        text = LAYOUT.read_text(encoding="utf-8")
        before_head = text.split("{% block head %}", 1)[0]
        assert not re.search(r'<script\b[^>]*\btype=["\']module["\']', before_head)
