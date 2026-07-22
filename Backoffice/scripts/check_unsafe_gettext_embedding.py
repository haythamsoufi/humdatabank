"""Scan git diffs for unsafe gettext embedding in JS strings and HTML attributes.

Translated strings from ``{{ _(...) }}`` are Markup-safe and never autoescaped by
Jinja. Embedding them raw inside quoted JS literals or HTML attribute values can
break parsing when translations contain apostrophes or quotes (common in French).

Safe patterns:
  - JS: ``{{ _('Label')|tojson|safe }}`` (standalone, not inside a quoted literal)
  - HTML attributes: ``{{ _('Label')|forceescape }}`` (or ``|tojson|safe`` / ``|e``)

Suppress on a line with an inline comment: ``{# i18n-embed-ok #}``
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys

logger = logging.getLogger(__name__)

SUPPRESS_MARK = "i18n-embed-ok"

GETTEXT_CALL = re.compile(
    r"\b_\(|gettext\s*\(|ngettext\s*\(|pgettext\s*\(|npgettext\s*\(",
    re.IGNORECASE,
)

SAFE_FILTER = re.compile(r"\|\s*(?:tojson|forceescape|e)\b")

JINJA_EXPR = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)

# gettext call embedded inside a same-line quoted literal (JS or HTML attribute).
UNSAFE_IN_SINGLE_QUOTES = re.compile(
    r"'(?:[^'\\]|\\.)*\{\{[^}]+\}\}(?:[^'\\]|\\.)*'",
    re.DOTALL,
)
UNSAFE_IN_DOUBLE_QUOTES = re.compile(
    r'"(?:[^"\\]|\\.)*\{\{[^}]+\}\}(?:[^"\\]|\\.)*"',
    re.DOTALL,
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


def _expr_is_unsafe_gettext(expr: str) -> bool:
    inner = expr.strip()
    if not GETTEXT_CALL.search(inner):
        return False
    if SAFE_FILTER.search(inner):
        return False
    return True


def _quoted_literal_has_unsafe_gettext(literal: str) -> bool:
    if "{{" not in literal or "}}" not in literal:
        return False
    for match in JINJA_EXPR.finditer(literal):
        if _expr_is_unsafe_gettext(match.group(1)):
            return True
    return False


def find_unsafe_embeddings(line: str) -> list[str]:
    if SUPPRESS_MARK in line:
        return []

    findings: list[str] = []
    for label, pattern in (
        ("single-quoted literal with raw gettext", UNSAFE_IN_SINGLE_QUOTES),
        ("double-quoted literal with raw gettext", UNSAFE_IN_DOUBLE_QUOTES),
    ):
        for match in pattern.finditer(line):
            if _quoted_literal_has_unsafe_gettext(match.group(0)):
                findings.append(label)
                break
    return findings


def scan_added_lines(diff: str) -> list[str]:
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
        for label in find_unsafe_embeddings(content):
            findings.append(f"{current_file}: {label}: {content.strip()}")

    return findings


def scan_file(path: str, text: str) -> list[str]:
    findings: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if SUPPRESS_MARK in line:
            continue
        for label in find_unsafe_embeddings(line):
            findings.append(f"{path}:{line_no}: {label}: {line.strip()}")
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
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "app" / "templates"
        findings: list[str] = []
        for path in sorted(root.rglob("*.html")):
            rel = path.relative_to(root.parents[1]).as_posix()
            findings.extend(scan_file(rel, path.read_text(encoding="utf-8")))
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
            "  - Rare intentional cases: add {# i18n-embed-ok #} on the same line\n"
            "See: docs/DEVELOPER-HANDBOOK.md (Template Safety Checklist)"
        )
        return 1

    logger.info("OK: No unsafe gettext embedding found.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
