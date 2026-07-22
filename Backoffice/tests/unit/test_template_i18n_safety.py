"""Guardrails for safe gettext embedding in inline JS and HTML attributes."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

BACKOFFICE_ROOT = Path(__file__).resolve().parents[2]
CHECK_SCRIPT = BACKOFFICE_ROOT / "scripts" / "check_unsafe_gettext_embedding.py"
SCRIPT_TAG = re.compile(
    r"<script\b([^>]*)>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
NON_JS_SCRIPT_TYPE = re.compile(
    r"""type\s*=\s*["'](?:application/json|application/ld\+json|text/template)["']""",
    re.IGNORECASE,
)


def _extract_inline_scripts(html: str) -> list[str]:
    scripts: list[str] = []
    for match in SCRIPT_TAG.finditer(html):
        attrs = match.group(1) or ""
        if NON_JS_SCRIPT_TYPE.search(attrs):
            continue
        body = match.group(2).strip()
        if body:
            scripts.append(body)
    return scripts


def _node_available() -> bool:
    try:
        subprocess.run(
            ["node", "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _assert_scripts_parse(script_bodies: list[str]) -> None:
    if not script_bodies:
        return
    if not _node_available():
        pytest.skip("Node.js not available for inline script syntax validation")

    for index, body in enumerate(script_bodies):
        proc = subprocess.run(
            ["node", "--check"],
            input=body,
            text=True,
            capture_output=True,
        )
        assert proc.returncode == 0, (
            f"Inline script block #{index + 1} failed JS syntax check:\n{proc.stderr}"
        )


class TestGettextEmbedStaticGuard:
    def test_all_templates_pass_static_gettext_embed_check(self):
        proc = subprocess.run(
            [sys.executable, str(CHECK_SCRIPT), "--all-templates"],
            cwd=str(BACKOFFICE_ROOT),
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr


class TestGettextEmbedRenderSmoke:
    FRENCH_ROUTES = (
        "/admin/access-requests",
        "/login",
    )

    @pytest.fixture
    def french_client(self, logged_in_admin_client):
        with logged_in_admin_client.session_transaction() as sess:
            sess["language"] = "fr"
        logged_in_admin_client.set_cookie("ui_language", "fr")
        return logged_in_admin_client

    @pytest.mark.parametrize("path", FRENCH_ROUTES)
    def test_french_rendered_inline_scripts_parse(self, path, french_client, client):
        if path.startswith("/admin/"):
            test_client = french_client
        else:
            test_client = client
            with test_client.session_transaction() as sess:
                sess.pop("_user_id", None)
                sess["language"] = "fr"
            test_client.set_cookie("ui_language", "fr")

        response = test_client.get(path)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        _assert_scripts_parse(_extract_inline_scripts(html))

    def test_check_script_flags_unsafe_js_embedding(self):
        from scripts.check_unsafe_gettext_embedding import find_unsafe_embeddings

        unsafe_line = "showError('{{ _(\"Job title is required.\") }}');"
        assert find_unsafe_embeddings(unsafe_line)

        safe_line = "showError({{ _('Job title is required.')|tojson|safe }});"
        assert not find_unsafe_embeddings(safe_line)

    def test_check_script_flags_unsafe_attribute_embedding(self):
        from scripts.check_unsafe_gettext_embedding import scan_template_text

        snippet = '<div data-confirm="{{ _(\'Send now?\') }}"></div>'
        findings = scan_template_text("sample.html", snippet)
        assert findings

        safe_snippet = '<div data-confirm="{{ _(\'Send now?\')|forceescape }}"></div>'
        assert not scan_template_text("sample.html", safe_snippet)
