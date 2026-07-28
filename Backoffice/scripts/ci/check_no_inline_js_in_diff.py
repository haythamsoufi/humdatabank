from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys

logger = logging.getLogger(__name__)


PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("inline onclick", re.compile(r"\bonclick\s*=", re.IGNORECASE)),
    # Only flag inline HTML-style event attributes (on*= "..."), not JS property handlers (el.onclick = fn)
    ("inline on*= handler", re.compile(r"\bon[a-zA-Z]+\s*=\s*['\"]", re.IGNORECASE)),
    # Only flag literal javascript: usage in HTML/JS strings in diffs.
    # (We allow code that *mentions* "javascript:" as part of validation logic.)
    ("javascript: url", re.compile(r"javascript\s*:\s*['\"]", re.IGNORECASE)),
    ("eval(", re.compile(r"\beval\s*\(", re.IGNORECASE)),
    ("new Function(", re.compile(r"\bnew\s+Function\s*\(", re.IGNORECASE)),
    # Flag innerHTML assignments (XSS risk, CSP blocker)
    # Allow exceptions: third-party libraries (jspdf, html2pdf) and DOMParser usage
    ("innerHTML assignment", re.compile(r"\binnerHTML\s*=", re.IGNORECASE)),
    ("insertAdjacentHTML", re.compile(r"\binsertAdjacentHTML\s*\(", re.IGNORECASE)),
    ("document.write", re.compile(r"\bdocument\s*\.\s*write\s*\(", re.IGNORECASE)),
]


def run_git_diff(base_ref: str | None = None) -> str:
    if base_ref:
        # CI mode: diff PR branch against its merge base so we only inspect
        # lines actually introduced by the PR (not the full branch history).
        return subprocess.check_output(
            ["git", "diff", f"{base_ref}...HEAD", "--unified=0"], text=True
        )
    # Local mode: staged diff first (pre-commit hook), then working-tree diff.
    try:
        staged = subprocess.check_output(["git", "diff", "--cached", "--unified=0"], text=True)
    except Exception as e:
        logger.debug("git diff --cached failed: %s", e)
        staged = ""
    if staged.strip():
        return staged
    return subprocess.check_output(["git", "diff", "--unified=0"], text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan git diff for inline JS / CSP-risk patterns.")
    parser.add_argument(
        "--base-ref",
        default=None,
        metavar="SHA",
        help="Base commit SHA to diff against (e.g. PR base). "
             "Defaults to staged/working-tree diff for local use.",
    )
    args = parser.parse_args()

    try:
        diff = run_git_diff(args.base_ref)
    except subprocess.CalledProcessError as e:
        logger.error("Failed to run git diff: %s", e)
        return 2

    findings: list[str] = []

    current_file = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[len("+++ b/") :].strip()
            continue

        # Only evaluate added lines (ignore diff headers and removals)
        if not line.startswith("+") or line.startswith("+++"):
            continue

        content = line[1:]
        for label, rx in PATTERNS:
            if label == "javascript: url":
                # Ignore mentions used for validation logic (not emitted into HTML)
                if "startswith((" in content or "startswith((" in content.replace(" ", ""):
                    continue
            if rx.search(content):
                findings.append(f"{current_file or '?'}: {label}: {content.strip()}")

    if findings:
        logger.error("ERROR: Inline-JS/CSP-risk patterns introduced in diff:")
        for f in findings[:200]:
            logger.error("- %s", f)
        if len(findings) > 200:
            logger.error("... and %d more", len(findings) - 200)
        logger.error(
            "Fix by:"
            "\n  - Replacing inline handlers with data-action + delegated listeners"
            "\n  - Replacing innerHTML with DOM construction (createElement, textContent, etc.)"
            "\n  - Using DOMParser for safe HTML parsing when needed"
            "\nSee: Backoffice/docs/INLINE_JS_HARDENING_SUMMARY_AND_PLAN.md"
        )
        return 1

    logger.info("OK: No inline-JS/CSP-risk patterns found in diff.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
