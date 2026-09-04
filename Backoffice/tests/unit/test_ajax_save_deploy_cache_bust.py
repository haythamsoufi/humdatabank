"""Why a deploy did not force-reload the WAF-fixed ajax-save.js.

These tests do not need Flask or Postgres. They exercise the real deploy
workflow snippet, the Azure upload script, the import-map builder, and a
browser HTTP-cache model that matches RFC 8246 ``immutable``.

A passing suite here would mean a returning visitor gets the new module
without clearing site data. Failures are the reason the last deploy did not.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKOFFICE = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKOFFICE.parent
SW_PATH = BACKOFFICE / "app" / "static" / "js" / "sw.js"
UPLOAD_SCRIPT = BACKOFFICE / "azure" / "upload-static-assets.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-to-webapp.yml"
STATIC_SERVING = BACKOFFICE / "app" / "static_serving.py"
LAYOUT = BACKOFFICE / "app" / "templates" / "core" / "layout.html"
ENTRY_FORM = BACKOFFICE / "app" / "templates" / "forms" / "entry_form" / "entry_form.html"
IMPORT_MAP_PY = BACKOFFICE / "app" / "static_import_map.py"

AJAX_SAVE_REL = "js/forms/modules/ajax-save.js"
OLD_MODULE = "export function initAjaxSave(){ /* pre-WAF */ }"
NEW_MODULE = "export function initAjaxSave(){ /* WAF b64 wrap */ }"


def _load_import_map_module():
    spec = importlib.util.spec_from_file_location("static_import_map_under_test", IMPORT_MAP_PY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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
            "immutable": "immutable" in (cache_control or ""),
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


# ---------------------------------------------------------------------------
# 1. The deploy's "self-heal" cannot evict an already-cached immutable copy
# ---------------------------------------------------------------------------

class TestImmutableCacheSurvivesHeaderOnlyDeploy:
    def test_upload_script_documents_self_heal_via_must_revalidate(self):
        script = UPLOAD_SCRIPT.read_text(encoding="utf-8")
        assert "self-heals on the next request" in script
        assert "CACHE_CONTROL_REVALIDATE" in script
        assert "max-age=31536000, public, immutable" in script

    def test_same_url_must_receive_waf_fix_after_origin_flips_to_must_revalidate(self):
        url = f"https://cdn.example/static/{AJAX_SAVE_REL}"
        cache = BrowserHttpCache(now=0)
        cache.store(
            url,
            body=OLD_MODULE,
            cache_control="max-age=31536000, public, immutable",
        )
        cache.now = 3600
        body, via = cache.fetch(
            url,
            {"body": NEW_MODULE, "cache_control": "max-age=0, public, must-revalidate"},
        )
        assert body == NEW_MODULE, (
            "Returning browsers that already stored unversioned ajax-save.js "
            "as Cache-Control: immutable will not revalidate for up to a year. "
            "Flipping the Azure blob to must-revalidate only affects new fetches "
            "— it cannot evict the cached pre-WAF module. That is why the "
            "deploy did not force-reload it."
        )
        assert via == "network"

    def test_query_string_change_is_a_new_cache_key(self):
        cache = BrowserHttpCache(now=0)
        cache.store(
            f"https://cdn.example/static/{AJAX_SAVE_REL}?v=oldsha",
            body=OLD_MODULE,
            cache_control="max-age=31536000, public, immutable",
        )
        cache.now = 3600
        body, via = cache.fetch(
            f"https://cdn.example/static/{AJAX_SAVE_REL}?v=newsha",
            {"body": NEW_MODULE, "cache_control": "max-age=0, public, must-revalidate"},
        )
        assert body == NEW_MODULE
        assert via == "network"


# ---------------------------------------------------------------------------
# 2. Incremental AzCopy never rewrites Cache-Control on unchanged JS blobs
# ---------------------------------------------------------------------------

class TestUploadScriptSkipsHeaderRewriteWhenBytesMatch:
    def test_incremental_path_must_rewrite_js_headers_even_when_dry_run_is_empty(self):
        script = UPLOAD_SCRIPT.read_text(encoding="utf-8")
        incremental_bails = (
            "no static files differ from blob storage; skipping sync and Cache-Control pass."
            in script
        )
        assert incremental_bails is False, (
            "upload-static-assets.sh returns early when AzCopy dry-run finds no "
            "byte changes, so a Cache-Control policy change never reaches the "
            "existing ajax-save.js blob. That blob keeps "
            "max-age=31536000, immutable — the header that froze the old module."
        )


# ---------------------------------------------------------------------------
# 3. Deploy workflow only diffs HEAD^..HEAD for static upload
# ---------------------------------------------------------------------------

_WORKFLOW_DETECT = r"""
set -euo pipefail
if git rev-parse --verify HEAD^ >/dev/null 2>&1; then
  changed_files="$(git diff --name-only HEAD^..HEAD -- Backoffice/app/static || true)"
  if [ -n "${changed_files}" ]; then
    echo "changed=true"
  else
    echo "changed=false"
  fi
else
  echo "changed=true"
fi
"""


class TestDeployWorkflowMissesAjaxSaveInEarlierCommit:
    def test_workflow_still_uses_tip_commit_only_diff(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        assert "HEAD^..HEAD" in workflow
        assert "Backoffice/app/static" in workflow
        assert "fetch-depth: 2" in workflow

    def test_ajax_save_change_in_parent_commit_must_still_trigger_static_upload(self, tmp_path):
        repo = tmp_path / "deploy"
        repo.mkdir()
        static_file = repo / "Backoffice" / "app" / "static" / "js" / "forms" / "modules" / "ajax-save.js"
        static_file.parent.mkdir(parents=True)
        static_file.write_text("old\n", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)

        static_file.write_text("waf-fix\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "WAF ajax-save fix"], cwd=repo, check=True, capture_output=True)

        (repo / "ci.txt").write_text("unrelated\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "CI fix"], cwd=repo, check=True, capture_output=True)

        result = subprocess.run(
            ["bash", "-lc", _WORKFLOW_DETECT],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "changed=true" in result.stdout, (
            "deploy-to-webapp.yml diffs only HEAD^..HEAD (and checks out "
            "fetch-depth: 2). A deploy whose tip commit is unrelated CI/docs "
            "skips the Azure static upload even when an earlier commit in the "
            "same push updated ajax-save.js. The app ships a new ASSET_VERSION "
            "but the CDN blob stays on the pre-WAF module."
        )


# ---------------------------------------------------------------------------
# 4. Service worker cannot bust the production CDN copy
# ---------------------------------------------------------------------------

class TestServiceWorkerCannotRefreshCdnAjaxSave:
    def test_sw_precache_list_includes_unversioned_ajax_save(self):
        source = SW_PATH.read_text(encoding="utf-8")
        assert "'/static/js/forms/modules/ajax-save.js'" in source
        assert "cacheKeyForUrl" in source
        assert "stripping query/hash" in source or "stripping query" in source

    def test_sw_skips_cross_origin_so_cdn_immutable_copies_are_untouched(self):
        source = SW_PATH.read_text(encoding="utf-8")
        assert "url.origin !== self.location.origin" in source
        assert "Do not intercept cross-origin requests" in source

    def test_sw_static_handler_must_not_treat_query_string_as_the_same_cache_key(self):
        source = SW_PATH.read_text(encoding="utf-8")
        strips_query = (
            "return new Request(`${u.origin}${u.pathname}`)" in source
            or 'return new Request(`${u.origin}${u.pathname}`)' in source
        )
        cache_first_static = "Static assets: cache-first and ignore querystring" in source
        assert not (strips_query and cache_first_static), (
            "sw.js stores /static/ assets under a pathname-only key and serves "
            "them cache-first. A new ?v=<ASSET_VERSION> on ajax-save.js still "
            "returns the previously cached pre-WAF body for same-origin "
            "requests (CDN fallback / no STATIC_CDN_URL)."
        )


# ---------------------------------------------------------------------------
# 5. Flask still freezes versioned JS for a year (same ASSET_VERSION = stuck)
# ---------------------------------------------------------------------------

class TestFlaskVersionedJsStillImmutable:
    def test_versioned_js_must_not_be_immutable_if_the_url_can_be_reused(self):
        source = STATIC_SERVING.read_text(encoding="utf-8")
        marks_versioned_immutable = (
            "if 'v=' in query_string:" in source
            and "_IMMUTABLE" in source
            and "max-age=31536000, public, immutable" in source
        )
        assert marks_versioned_immutable is False, (
            "app/static_serving.py still sends Cache-Control: immutable for "
            "any /static/*.js?v=… response. If ASSET_VERSION is pinned (Azure "
            "App Setting overriding the image ENV) or a static-only upload "
            "keeps the same ?v=, browsers will keep the old ajax-save.js for "
            "a year even after the file on disk changes."
        )


# ---------------------------------------------------------------------------
# 6. Import map actually names ajax-save.js (so a working map *would* bust)
# ---------------------------------------------------------------------------

class TestImportMapNamesAjaxSave:
    def test_forms_import_map_rewrites_ajax_save_relative_imports(self):
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
        assert all("?v=deploy-waf-fix" in url for url in mapped)
        assert any(url.startswith("https://cdn.example/static/") for url in mapped)
        # App-origin scopes exist so CDN-fallback entry-form.js still cache-busts.
        assert any(url.startswith("https://databank.example/static/") for url in mapped)


# ---------------------------------------------------------------------------
# 7. Template order — import map must precede type=module (regression lock)
# ---------------------------------------------------------------------------

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
