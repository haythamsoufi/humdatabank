#!/usr/bin/env python3
"""Migrate admin/ai/_documents_script.html to static JS + bootstrap."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTIAL = ROOT / "app/templates/admin/ai/_documents_script.html"
OUT_JS = ROOT / "app/static/js/admin/ai-documents.js"
DOCUMENTS_HTML = ROOT / "app/templates/admin/ai/documents.html"


def key_for(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")[:40]
    h = hashlib.md5(text.encode()).hexdigest()[:8]
    return f"{slug}_{h}" if slug else f"k_{h}"


def main() -> None:
    text = PARTIAL.read_text(encoding="utf-8")

    data_pat = re.compile(r"const documentsData = \[.*?\];", re.DOTALL)
    text = data_pat.sub(
        """const documentsData = (function() {
  var el = document.getElementById('ai-documents-rows');
  if (!el) return [];
  try { return JSON.parse(el.textContent || '[]'); } catch (e) { return []; }
})();""",
        text,
        count=1,
    )

    translations: dict[str, str] = {}
    urls: dict[str, str] = {}

    def trans_repl(m: re.Match) -> str:
        t = m.group(1)
        k = key_for(t)
        translations[k] = t
        return f"cfg.t.{k}"

    text = re.sub(
        r"\{\{\s*_\(\s*['\"]([^'\"]+)['\"]\s*\)(?:\s*\|\s*tojson(?:\s*\|\s*safe)?)?\s*\}\}",
        trans_repl,
        text,
    )

    def url_repl(m: re.Match) -> str:
        expr = m.group(1).strip()
        k = "url_" + hashlib.md5(expr.encode()).hexdigest()[:10]
        urls[k] = expr
        if "|tojson" in expr:
            return f"cfg.urls.{k}"
        return f"cfg.urls.{k}"

    text = re.sub(r"\{\{\s*(url_for\([^}]+\)(?:\s*\|[^}]*)?)\s*\}\}", url_repl, text)
    text = re.sub(
        r"\{\{\s*static_url\('([^']+)'\)\s*\}\}",
        lambda m: f"cfg.static.{m.group(1).replace('/', '_')}",
        text,
    )

    header = "(function() {\n'use strict';\nvar cfg = window.aiDocumentsConfig || {};\n"
    footer = "\n})();\n"
    OUT_JS.parent.mkdir(parents=True, exist_ok=True)
    OUT_JS.write_text(header + text + footer, encoding="utf-8")

    # Build documents JSON block from original partial
    orig = PARTIAL.read_text(encoding="utf-8")
    m = re.search(r"const documentsData = (\[.*?\]);", orig, re.DOTALL)
    json_block = ""
    if m:
        json_block = (
            '<script type="application/json" id="ai-documents-rows">\n'
            + m.group(1).strip()
            + "\n</script>\n"
        )

    boot_lines = [
        '<script nonce="{{ csp_nonce() }}">',
        "window.aiDocumentsConfig = window.aiDocumentsConfig || {};",
        "window.aiDocumentsConfig.t = {",
    ]
    for k, v in sorted(translations.items()):
        esc = v.replace("'", "\\'")
        boot_lines.append(f"  {k}: {{{{ _('{esc}')|tojson }}}},")
    boot_lines.append("};")
    boot_lines.append("window.aiDocumentsConfig.urls = {")
    for k, expr in sorted(urls.items()):
        boot_lines.append(f"  {k}: {{{{ {expr}|tojson }}}},")
    boot_lines.append("};")
    boot_lines.append("</script>")
    bootstrap = "\n".join(boot_lines)

    html = DOCUMENTS_HTML.read_text(encoding="utf-8")
    old = """<script nonce="{{ csp_nonce() }}">
{# Documents grid, column defs, and all AI documents JS live in the partial below. #}
{% include "admin/ai/_documents_script.html" %}
</script>"""
    new = (
        json_block
        + bootstrap
        + '\n<script src="{{ static_url(\'js/admin/ai-documents.js\') }}"></script>'
    )
    if old not in html:
        raise SystemExit("documents.html pattern not found")
    DOCUMENTS_HTML.write_text(html.replace(old, new), encoding="utf-8")
    PARTIAL.unlink()
    print(f"Wrote {OUT_JS}, updated {DOCUMENTS_HTML}, removed {PARTIAL}")
    print(f"translations={len(translations)} urls={len(urls)}")


if __name__ == "__main__":
    main()
