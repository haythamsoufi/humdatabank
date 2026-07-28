"""Scan git diffs for unsafe gettext embedding in JS strings and HTML attributes.

Translated strings from ``{{ _(...) }}`` are Markup-safe and never autoescaped by
Jinja. Embedding them raw inside quoted JS literals or HTML attribute values can
break parsing when translations contain apostrophes or quotes (common in French).

Safe patterns:
  - JS: ``{{ _('Label')|tojson|safe }}`` or ``{{ _('Label')|js }}`` (standalone)
  - HTML attributes: ``{{ _('Label')|forceescape }}`` (or ``|tojson|safe`` / ``|e``)

Suppress on a line with an inline comment: ``{# i18n-embed-ok #}``
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPRESS_MARK = "i18n-embed-ok"

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


def run_git_diff(base_ref: str | None = None) -> str:
    if base_ref:
        return subprocess.check_output(
            ["git", "diff", f"{base_ref}...HEAD", "--unified=0"],
            text=True,
        )
    try:
        staged = subprocess.check_output(
            ["git", "diff", "--cached", "--unified=0"],
            text=True,
        )
    except Exception as exc:
        logger.debug("git diff --cached failed: %s", exc)
        staged = ""
    if staged.strip():
        return staged
    return subprocess.check_output(["git", "diff", "--unified=0"], text=True)


def _is_unsafe_gettext_expr(expr: str) -> bool:
    inner = expr.strip()
    if not GETTEXT_CALL.search(inner):
        return False
    return not SAFE_FILTER.search(inner)


def _quoted_literal_has_unsafe_gettext(literal: str) -> bool:
    if "{{" not in literal or "}}" not in literal:
        return False
    for match in JINJA_EXPR.finditer(literal):
        if _is_unsafe_gettext_expr(match.group(1)):
            return True
    return False


def _skip_jinja_block(text: str, start: int) -> int:
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


def _scan_js_line(line: str) -> list[str]:
    findings: list[str] = []
    for start, end, _quote in _find_js_string_literals(line):
        literal = line[start:end]
        if _quoted_literal_has_unsafe_gettext(literal):
            findings.append("quoted JS literal with raw gettext")
    return findings


def _scan_attribute_value(value: str) -> list[str]:
    if _quoted_literal_has_unsafe_gettext(f'"{value}"') or _quoted_literal_has_unsafe_gettext(
        f"'{value}'"
    ):
        return ["HTML attribute value with raw gettext"]
    return []


def find_unsafe_embeddings(line: str) -> list[str]:
    """Public helper for tests: return finding labels for one source line."""
    if SUPPRESS_MARK in line:
        return []
    return _scan_js_line(line)


def scan_template_text(path: str, text: str) -> list[str]:
    findings: list[str] = []

    for script_match in SCRIPT_BLOCK.finditer(text):
        script_body = script_match.group(2)
        script_start = text[: script_match.start(2)].count("\n") + 1
        for offset, line in enumerate(script_body.splitlines()):
            line_no = script_start + offset
            if SUPPRESS_MARK in line:
                continue
            for label in _scan_js_line(line):
                findings.append(f"{path}:{line_no}: {label}: {line.strip()}")

    for attr_match in ATTR_VALUE.finditer(text):
        value = attr_match.group("value")
        if SUPPRESS_MARK in value:
            continue
        attr_line = text[: attr_match.start()].count("\n") + 1
        for label in _scan_attribute_value(value):
            snippet = attr_match.group(0).strip()
            findings.append(f"{path}:{attr_line}: {label}: {snippet}")

    return findings


def scan_added_lines(diff: str) -> list[str]:
    """Diff-mode heuristic: flag added lines that introduce unsafe embed patterns."""
    findings: list[str] = []
    current_file: str | None = None

    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[len("+++ b/") :].strip()
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        if not current_file or not current_file.endswith(".html"):
            continue

        content = line[1:]
        if SUPPRESS_MARK in content:
            continue

        for label in _scan_js_line(content):
            findings.append(f"{current_file}: {label}: {content.strip()}")
            break

        if any(findings) and findings[-1].startswith(current_file):
            continue

        attr_line = re.compile(
            r"\b(?:data-[a-z0-9_-]+|title|aria-[a-z0-9_-]+|placeholder|alt)\s*=\s*"
            r"['\"][^'\"]*\{\{[^}]+\}\}[^'\"]*['\"]",
            re.IGNORECASE,
        )
        if not attr_line.search(content):
            continue
        for match in JINJA_EXPR.finditer(content):
            if _is_unsafe_gettext_expr(match.group(1)):
                findings.append(
                    f"{current_file}: HTML attribute with raw gettext: {content.strip()}"
                )
                break

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan for unsafe gettext embedding in JS strings / HTML attributes.",
    )
    parser.add_argument(
        "--base-ref",
        default=None,
        metavar="SHA",
        help="Base commit SHA for PR diff mode (default: staged/working-tree diff).",
    )
    parser.add_argument(
        "--all-templates",
        action="store_true",
        help="Scan all Backoffice/app/templates/**/*.html instead of git diff.",
    )
    args = parser.parse_args()

    if args.all_templates:
        root = Path(__file__).resolve().parents[2] / "app" / "templates"
        findings: list[str] = []
        for path in sorted(root.rglob("*.html")):
            rel = path.relative_to(root.parents[1]).as_posix()
            findings.extend(scan_template_text(rel, path.read_text(encoding="utf-8")))
    else:
        try:
            diff = run_git_diff(args.base_ref)
        except subprocess.CalledProcessError as exc:
            logger.error("Failed to run git diff: %s", exc)
            return 2
        findings = scan_added_lines(diff)

    if findings:
        logger.error("ERROR: Unsafe gettext embedding detected:")
        for item in findings[:200]:
            logger.error("- %s", item)
        if len(findings) > 200:
            logger.error("... and %d more", len(findings) - 200)
        logger.error(
            "Fix by:\n"
            "  - JS: use {{ _('Label')|tojson|safe }} outside quoted literals\n"
            "    e.g. '<i></i>' + {{ _('Label')|tojson|safe }} + ' suffix'\n"
            "  - HTML attributes: {{ _('Label')|forceescape }}\n"
            "  - Batch fix: python Backoffice/scripts/codemods/fix_unsafe_gettext_embedding.py --apply\n"
            "  - Rare intentional cases: add {# i18n-embed-ok #} on the same line\n"
            "See: docs/DEVELOPER-HANDBOOK.md (Template Safety Checklist)"
        )
        return 1

    logger.info("OK: No unsafe gettext embedding found.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
