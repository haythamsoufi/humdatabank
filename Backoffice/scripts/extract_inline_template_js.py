#!/usr/bin/env python3
"""
Extract inline <script nonce> blocks from a Jinja template into a static JS file
and a JSON bootstrap block. Replaces {{ _('...')|tojson }} and similar with config refs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Patterns for Jinja expressions commonly embedded in JS
JINJA_PATTERNS = [
    (re.compile(r"\{\{\s*_\(\s*'([^']*)'\s*\)\s*\|\s*tojson\s*\}\}"), "t"),
    (re.compile(r'\{\{\s*_\(\s*"([^"]*)"\s*\)\s*\|\s*tojson\s*\}\}'), "t"),
    (re.compile(r'\{\{\s*_\(\s*"([^"]*)"\s*\)\s*\|\s*tojson\s*\}\}'), "t"),
    (re.compile(r"\{\{\s*_\(\s*'([^']*)'\s*\)\s*\}\}"), "t_raw"),
    (re.compile(r'\{\{\s*url_for\(([^}]+)\)\s*\|\s*tojson\s*\}\}'), "url"),
    (re.compile(r"\{\{\s*url_for\(([^}]+)\)\s*\}\}"), "url_raw"),
    (re.compile(r"\{\{\s*static_url\('([^']+)'\)\s*\}\}"), "static"),
    (re.compile(r'\{\{\s*csp_nonce\(\)\s*\}\}'), "skip"),
]

SCRIPT_START = re.compile(
    r'<script\s+nonce="\{\{\s*csp_nonce\(\)\s*\}\}">',
    re.IGNORECASE,
)
SCRIPT_END = re.compile(r"</script>", re.IGNORECASE)
SCRIPT_MODULE = re.compile(
    r'<script\s+type="module"\s+nonce="\{\{\s*csp_nonce\(\)\s*\}\}">',
    re.IGNORECASE,
)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return s[:60] if s else "key"


def extract_scripts(html: str) -> list[tuple[int, int, str, bool]]:
    """Return list of (start, end, content, is_module) for inline nonce scripts."""
    results = []
    pos = 0
    while pos < len(html):
        m_mod = SCRIPT_MODULE.search(html, pos)
        m_std = SCRIPT_START.search(html, pos)
        if not m_mod and not m_std:
            break
        use_mod = False
        if m_mod and m_std:
            use_mod = m_mod.start() < m_std.start()
            m = m_mod if use_mod else m_std
        elif m_mod:
            use_mod = True
            m = m_mod
        else:
            m = m_std
        start_tag_end = m.end()
        end_m = SCRIPT_END.search(html, start_tag_end)
        if not end_m:
            break
        content = html[start_tag_end : end_m.start()]
        results.append((m.start(), end_m.end(), content, use_mod))
        pos = end_m.end()
    return results


def collect_jinja(expr: str) -> dict:
    expr = expr.strip()
    if expr.startswith("_("):
        inner = expr[3:-1].strip("'\"")
        return {"type": "t", "value": inner}
    if "url_for" in expr:
        return {"type": "url", "value": expr}
    if "static_url" in expr:
        m = re.search(r"static_url\('([^']+)'\)", expr)
        return {"type": "static", "value": m.group(1) if m else expr}
    return {"type": "raw", "value": expr}


def replace_jinja_in_js(js: str, config: dict, counters: dict) -> str:
    """Replace {{ ... }} with cfg references; populate config dict."""

    def replacer(match: re.Match) -> str:
        full = match.group(0)
        inner = match.group(1) if match.lastindex else ""
        # Generic {{ ... }}
        expr = inner.strip()
        info = collect_jinja(expr)
        if info["type"] == "t":
            key = slugify(info["value"])
            if key in counters:
                counters[key] += 1
                key = f"{key}_{counters[key]}"
            else:
                counters[key] = 0
            config.setdefault("translations", {})[key] = info["value"]
            return f"cfg.translations.{key}"
        if info["type"] == "url":
            key = slugify(info["value"].replace(" ", ""))
            if key in counters:
                counters[key] += 1
                key = f"{key}_{counters[key]}"
            else:
                counters[key] = 0
            config.setdefault("urls", {})[key] = f"PLACEHOLDER:{info['value']}"
            return f"cfg.urls.{key}"
        if info["type"] == "static":
            key = slugify(info["value"].replace("/", "_"))
            config.setdefault("static", {})[key] = info["value"]
            return f"cfg.static.{key}"
        return full

    pattern = re.compile(r"\{\{([^}]+)\}\}")
    return pattern.sub(replacer, js)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("template", type=Path)
    parser.add_argument("output_js", type=Path)
    parser.add_argument("--config-var", default="pageConfig")
    args = parser.parse_args()

    html = args.template.read_text(encoding="utf-8")
    scripts = extract_scripts(html)
    if not scripts:
        print("No inline nonce scripts found", file=sys.stderr)
        return 1

    all_js_parts = []
    config: dict = {"translations": {}, "urls": {}, "static": {}}
    counters: dict = {}

    for i, (_, _, content, is_module) in enumerate(scripts):
        if is_module:
            all_js_parts.append(
                f"/* module block {i + 1} — keep in template or convert separately */\n"
                + content
            )
            continue
        cleaned = replace_jinja_in_js(content, config, counters)
        all_js_parts.append(f"/* --- block {i + 1} --- */\n" + cleaned)

    header = f"""(function() {{
  'use strict';
  var cfg = window.{args.config_var} || {{}};
"""
    footer = "\n})();\n"

    args.output_js.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(all_js_parts)
    # Wrap each IIFE block - many files already have (function(){...})();
    # For combined file, append blocks sequentially
    args.output_js.write_text(
        header + body + footer,
        encoding="utf-8",
    )
    print(f"Wrote {args.output_js} ({len(scripts)} blocks)")
    print("Config skeleton (fill urls in template bootstrap):")
    print(json.dumps(config, indent=2, ensure_ascii=False)[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
