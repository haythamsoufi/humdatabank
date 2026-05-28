#!/usr/bin/env python3
"""Migrate inline nonce scripts from a template to static JS + bootstrap."""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

SCRIPT_START = re.compile(
    r'<script\s+nonce="\{\{\s*csp_nonce\(\)\s*\}\}">\s*',
    re.IGNORECASE,
)
SCRIPT_MODULE = re.compile(
    r'<script\s+type="module"\s+nonce="\{\{\s*csp_nonce\(\)\s*\}\}">\s*',
    re.IGNORECASE,
)
SCRIPT_END = re.compile(r"</script>", re.IGNORECASE)

JINJA_EXPR = re.compile(r"\{\{([^}]+)\}\}")
TRANS_TOJSON = re.compile(
    r"_\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\|\s*tojson",
)
TRANS_PLAIN = re.compile(r"_\(\s*['\"]([^'\"]+)['\"]\s*\)")
URL_FOR = re.compile(r"url_for\(([^)]+)\)")


def key_for_text(text: str) -> str:
    h = hashlib.md5(text.encode()).hexdigest()[:8]
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")[:40]
    return f"{slug}_{h}" if slug else f"k_{h}"


def build_bootstrap(js: str) -> tuple[str, dict]:
    translations: dict[str, str] = {}
    urls: dict[str, str] = {}

    def repl(m: re.Match) -> str:
        full = m.group(0)
        inner = m.group(1).strip()
        tm = TRANS_TOJSON.search(inner)
        if tm:
            text = tm.group(1)
            k = key_for_text(text)
            translations[k] = text
            return f"cfg.t.{k}"
        tm2 = TRANS_PLAIN.search(inner)
        if tm2 and "_(" in inner:
            text = tm2.group(1)
            k = key_for_text(text)
            translations[k] = text
            if "|tojson" in inner:
                return f"cfg.t.{k}"
            return f"cfg.t.{k}"  # caller may need string concat
        if "url_for" in inner:
            k = key_for_text(inner)
            urls[k] = inner
            if "|tojson" in inner:
                return f"cfg.urls.{k}"
            return f"cfg.urls.{k}"
        if inner == "csp_nonce()":
            return full
        return full

    new_js = JINJA_EXPR.sub(repl, js)
    new_js = postprocess_cfg_refs(new_js)
    return new_js, {"translations": translations, "urls": urls}


def postprocess_cfg_refs(js: str) -> str:
    """Turn quoted cfg.t.* placeholders into real property reads."""
    js = re.sub(r"'cfg\.t\.(\w+)'", r"cfg.t.\1", js)
    js = re.sub(r'"cfg\.t\.(\w+)"', r"cfg.t.\1", js)
    js = re.sub(r"'cfg\.urls\.(\w+)'", r"cfg.urls.\1", js)
    js = re.sub(r'"cfg\.urls\.(\w+)"', r"cfg.urls.\1", js)
    return js


JINJA_BLOCK = re.compile(r"{%.*?%}", re.DOTALL)


def strip_jinja_blocks(js: str) -> tuple[str, bool]:
    """Remove {% %} blocks; return whether any were removed."""
    if not JINJA_BLOCK.search(js):
        return js, False
    cleaned = JINJA_BLOCK.sub("", js)
    cleaned = re.sub(r",\s*,", ",", cleaned)
    cleaned = re.sub(r"\[\s*,", "[", cleaned)
    cleaned = re.sub(r",\s*\]", "]", cleaned)
    return cleaned, True


def extract_scripts(html: str) -> list[tuple[int, int, str, bool]]:
    results = []
    pos = 0
    while pos < len(html):
        m_mod = SCRIPT_MODULE.search(html, pos)
        m_std = SCRIPT_START.search(html, pos)
        if not m_mod and not m_std:
            break
        use_mod = bool(m_mod and (not m_std or m_mod.start() < m_std.start()))
        m = m_mod if use_mod else m_std
        end_m = SCRIPT_END.search(html, m.end())
        if not end_m:
            break
        results.append((m.start(), end_m.end(), html[m.end() : end_m.start()], use_mod))
        pos = end_m.end()
    return results


def render_bootstrap_jinja(cfg: dict, var_name: str) -> str:
    lines = [f'<script nonce="{{{{ csp_nonce() }}}}">', f"window.{var_name} = window.{var_name} || {{}};"]
    if cfg.get("translations"):
        lines.append(f"window.{var_name}.t = {{")
        for k, text in cfg["translations"].items():
            lines.append(f"  {k}: {{{{ _('{text.replace(chr(39), chr(92)+chr(39))}')|tojson }}}},")
        lines.append("};")
    if cfg.get("urls"):
        lines.append(f"window.{var_name}.urls = {{")
        for k, expr in cfg["urls"].items():
            lines.append(f"  {k}: {{{{ {expr}|tojson }}}},")
        lines.append("};")
    lines.append("</script>")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("template", type=Path)
    p.add_argument("output_js", type=Path)
    p.add_argument("--config-var", default="pageConfig")
    p.add_argument("--in-place", action="store_true", help="Replace scripts in template")
    p.add_argument("--script-src", default=None, help="static_url path e.g. js/admin/foo.js")
    args = p.parse_args()

    html = args.template.read_text(encoding="utf-8")
    scripts = extract_scripts(html)
    if not scripts:
        print("No scripts", file=sys.stderr)
        return 1

    combined_cfg: dict = {"translations": {}, "urls": {}}
    js_parts = []
    module_parts = []

    for i, (_, _, content, is_mod) in enumerate(scripts):
        if is_mod:
            module_parts.append(content)
            continue
        new_js, cfg = build_bootstrap(content)
        new_js, had_jinja = strip_jinja_blocks(new_js)
        if had_jinja:
            print(f"  block {i + 1}: stripped Jinja control tags (use pageData bootstrap)", file=sys.stderr)
        combined_cfg["translations"].update(cfg["translations"])
        combined_cfg["urls"].update(cfg["urls"])
        js_parts.append(f"/* block {i + 1} */\n{new_js}")

    out_js = (
        f"(function() {{\n  'use strict';\n  var cfg = window.{args.config_var} || {{}};\n  "
        + "\n  ".join(js_parts)
        + "\n})();\n"
    )
    args.output_js.parent.mkdir(parents=True, exist_ok=True)
    args.output_js.write_text(out_js, encoding="utf-8")

    bootstrap = render_bootstrap_jinja(combined_cfg, args.config_var)
    print(f"Wrote {args.output_js} ({len(js_parts)} blocks, {len(combined_cfg['translations'])} strings)")

    if args.in_place and args.script_src:
        # Remove inline scripts (non-module), add bootstrap + src at first script position
        new_html = html
        for start, end, _, is_mod in reversed(scripts):
            if not is_mod:
                new_html = new_html[:start] + new_html[end:]
        first_start = min(s[0] for s in scripts if not s[3])
        injection = (
            bootstrap
            + f'\n<script src="{{{{ static_url(\'{args.script_src}\') }}}}"></script>\n'
        )
        for start, end, content, is_mod in scripts:
            if is_mod:
                injection += (
                    f'<script type="module" nonce="{{{{ csp_nonce() }}}}">\n{content}</script>\n'
                )
        new_html = new_html[:first_start] + injection + new_html[first_start:]
        args.template.write_text(new_html, encoding="utf-8")
        print(f"Updated {args.template}")
    else:
        print("\n--- Bootstrap snippet ---\n")
        print(bootstrap[:3000])

    return 0


if __name__ == "__main__":
    sys.exit(main())
