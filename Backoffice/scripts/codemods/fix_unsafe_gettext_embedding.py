"""Codemod: fix unsafe gettext embedding in Jinja templates.

Rewrites raw ``{{ _(...) }}`` inside quoted JS literals to ``|tojson|safe`` and
inside HTML attribute values to ``|forceescape``.

Usage:
  python Backoffice/scripts/codemods/fix_unsafe_gettext_embedding.py --dry-run
  python Backoffice/scripts/codemods/fix_unsafe_gettext_embedding.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

GETTEXT_CALL = re.compile(
    r"\b_\(|gettext\s*\(|ngettext\s*\(|pgettext\s*\(|npgettext\s*\(",
    re.IGNORECASE,
)
SAFE_FILTER = re.compile(r"\|\s*(?:tojson|forceescape|e)\b")
JINJA_EXPR = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)

SCRIPT_BLOCK = re.compile(
    r"(<script\b[^>]*>)(.*?)(</script>)",
    re.IGNORECASE | re.DOTALL,
)
ATTR_VALUE = re.compile(
    r"(?P<prefix>\b(?:data-[a-z0-9_-]+|title|aria-[a-z0-9_-]+|placeholder|alt)\s*=\s*)"
    r"(?P<quote>['\"])"
    r"(?P<value>(?:\\.|(?!\2).)*?)"
    r"(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)


def _is_unsafe_gettext_expr(expr: str) -> bool:
    inner = expr.strip()
    if not GETTEXT_CALL.search(inner):
        return False
    return not SAFE_FILTER.search(inner)


def _add_filter(expr: str, filter_name: str) -> str:
    inner = expr.strip()
    if SAFE_FILTER.search(inner):
        return inner
    return f"{inner}|{filter_name}"


def _fix_js_quoted_literal(literal: str, quote: str) -> str:
    """Split a JS quoted literal that contains raw gettext into safe concatenation."""
    content = literal[1:-1]
    parts: list[str] = []
    last = 0
    changed = False

    for match in JINJA_EXPR.finditer(content):
        if not _is_unsafe_gettext_expr(match.group(1)):
            continue
        before = content[last : match.start()]
        if before:
            parts.append(f"{quote}{before}{quote}")
        fixed = "{{ " + _add_filter(match.group(1), "tojson|safe") + " }}"
        parts.append(fixed)
        last = match.end()
        changed = True

    if not changed:
        return literal

    after = content[last:]
    if after:
        parts.append(f"{quote}{after}{quote}")

    if len(parts) == 1:
        return parts[0]

    return " + ".join(parts)


def _fix_attribute_value(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        expr = match.group(1)
        if not _is_unsafe_gettext_expr(expr):
            return match.group(0)
        return "{{ " + _add_filter(expr, "forceescape") + " }}"

    return JINJA_EXPR.sub(repl, value)


def _fix_script_block(script: str) -> str:
    result = script
    for quote in ("'", '"'):
        pattern = re.compile(
            rf"{re.escape(quote)}(?:[^\\{quote}]|\\.)*{re.escape(quote)}",
            re.DOTALL,
        )

        def repl(match: re.Match[str]) -> str:
            literal = match.group(0)
            if "{{" not in literal:
                return literal
            return _fix_js_quoted_literal(literal, quote)

        result = pattern.sub(repl, result)
    return result


def fix_template(text: str) -> tuple[str, int]:
    changes = 0

    def script_repl(match: re.Match[str]) -> str:
        nonlocal changes
        open_tag, body, close_tag = match.group(1), match.group(2), match.group(3)
        fixed_body = _fix_script_block(body)
        if fixed_body != body:
            changes += 1
        return open_tag + fixed_body + close_tag

    updated = SCRIPT_BLOCK.sub(script_repl, text)

    def attr_repl(match: re.Match[str]) -> str:
        nonlocal changes
        value = match.group("value")
        fixed_value = _fix_attribute_value(value)
        if fixed_value == value:
            return match.group(0)
        changes += 1
        return (
            f"{match.group('prefix')}{match.group('quote')}"
            f"{fixed_value}{match.group('quote')}"
        )

    updated = ATTR_VALUE.sub(attr_repl, updated)
    return updated, changes


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix unsafe gettext embedding in templates.")
    parser.add_argument("--apply", action="store_true", help="Write changes to disk.")
    parser.add_argument("--dry-run", action="store_true", help="Report files that would change.")
    parser.add_argument(
        "--path",
        default=None,
        help="Single template file or directory (default: app/templates).",
    )
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        parser.error("Specify --apply or --dry-run")

    root = Path(__file__).resolve().parents[2]
    templates_root = root / "app" / "templates"
    if args.path:
        target = Path(args.path)
        if not target.is_absolute():
            target = root / target
        paths = [target] if target.is_file() else sorted(target.rglob("*.html"))
    else:
        paths = sorted(templates_root.rglob("*.html"))

    total_files = 0
    total_changes = 0
    for path in paths:
        original = path.read_text(encoding="utf-8")
        updated, changes = fix_template(original)
        if changes:
            total_files += 1
            total_changes += changes
            rel = path.relative_to(root).as_posix()
            print(f"{rel}: {changes} block(s) updated")
            if args.apply:
                path.write_text(updated, encoding="utf-8")

    mode = "Updated" if args.apply else "Would update"
    print(f"{mode} {total_files} file(s), {total_changes} block(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
