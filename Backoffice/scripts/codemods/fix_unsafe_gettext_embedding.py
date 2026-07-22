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
SAFE_FILTER = re.compile(r"\|\s*(?:tojson|forceescape|e|js)\b")
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


def _skip_jinja_block(text: str, start: int) -> int:
    """Return index after ``}}`` starting at ``{{`` (start points at first ``{``)."""
    if text[start : start + 2] != "{{":
        return start + 1
    depth = 0
    i = start + 2
    n = len(text)
    while i < n:
        if text[i : i + 2] == "{{":
            depth += 1
            i += 2
        elif text[i : i + 2] == "}}":
            if depth == 0:
                return i + 2
            depth -= 1
            i += 2
        else:
            i += 1
    return n


def _find_js_string_literals(line: str) -> list[tuple[int, int, str]]:
    """Find JS string/template literal spans, treating ``{{ }}`` as opaque."""
    segments: list[tuple[int, int, str]] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch in ("'", '"', "`"):
            quote = ch
            start = i
            i += 1
            while i < n:
                if line[i] == "\\":
                    i += 2
                    continue
                if line[i : i + 2] == "{{":
                    i = _skip_jinja_block(line, i)
                    continue
                if line[i] == quote:
                    segments.append((start, i + 1, quote))
                    i += 1
                    break
                i += 1
        else:
            i += 1
    return segments


def _fix_js_line(line: str) -> tuple[str, bool]:
    """Fix unsafe gettext inside quoted literals on a single line."""
    segments = _find_js_string_literals(line)
    if not segments:
        return line, False

    changed = False
    parts: list[str] = []
    cursor = 0
    for start, end, quote in segments:
        parts.append(line[cursor:start])
        literal = line[start:end]
        if _quoted_literal_has_unsafe_gettext(literal):
            fixed = _fix_js_quoted_literal(literal, quote)
            if fixed != literal:
                changed = True
            parts.append(fixed)
        else:
            parts.append(literal)
        cursor = end
    parts.append(line[cursor:])
    return "".join(parts), changed


def _quoted_literal_has_unsafe_gettext(literal: str) -> bool:
    if "{{" not in literal or "}}" not in literal:
        return False
    for match in JINJA_EXPR.finditer(literal):
        if _is_unsafe_gettext_expr(match.group(1)):
            return True
    return False


def _fix_script_block(script: str) -> tuple[str, int]:
    lines = script.split("\n")
    out: list[str] = []
    changes = 0
    for line in lines:
        fixed_line, changed = _fix_js_line(line)
        if changed:
            changes += 1
        out.append(fixed_line)
    return "\n".join(out), changes


def fix_template(text: str) -> tuple[str, int]:
    total_changes = 0

    def script_repl(match: re.Match[str]) -> str:
        nonlocal total_changes
        open_tag, body, close_tag = match.group(1), match.group(2), match.group(3)
        fixed_body, changes = _fix_script_block(body)
        total_changes += changes
        return open_tag + fixed_body + close_tag

    updated = SCRIPT_BLOCK.sub(script_repl, text)

    def attr_repl(match: re.Match[str]) -> str:
        nonlocal total_changes
        value = match.group("value")
        fixed_value = _fix_attribute_value(value)
        if fixed_value == value:
            return match.group(0)
        total_changes += 1
        return (
            f"{match.group('prefix')}{match.group('quote')}"
            f"{fixed_value}{match.group('quote')}"
        )

    updated = ATTR_VALUE.sub(attr_repl, updated)
    return updated, total_changes


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
