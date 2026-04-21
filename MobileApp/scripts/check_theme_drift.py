#!/usr/bin/env python3
"""
Optional guard: fail when new Colors.white / Colors.black appear on added lines
in lib/screens/ or lib/widgets/ (git diff).

Usage (from repo root):
  python MobileApp/scripts/check_theme_drift.py --git-diff
  python MobileApp/scripts/check_theme_drift.py --git-diff --base origin/main

Without --git-diff: exit 0 immediately.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


BAD = re.compile(r"\bColors\.(white|black)\b")

# Paths relative to MobileApp/ or monorepo root including MobileApp/
SCAN_PREFIXES = (
    "lib/screens/",
    "lib/widgets/",
    "MobileApp/lib/screens/",
    "MobileApp/lib/widgets/",
)

ALLOWLIST_SUBSTRINGS = (
    "theme-drift-ok",
    "Colors.black87",
    "Colors.black12",
    "Colors.black26",
    "Colors.black38",
    "Colors.black45",
    "Colors.black54",
    "Colors.white10",
    "Colors.white12",
    "Colors.white24",
    "Colors.white30",
    "Colors.white38",
    "Colors.white54",
    "Colors.white60",
    "Colors.white70",
    "Colors.transparent",
)


def _mobile_app_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _git_diff_unified0(base: str | None) -> str:
    mobile = _mobile_app_root()
    cmd = ["git", "diff", "--unified=0"]
    if base:
        cmd.append(base)
    try:
        r = subprocess.run(
            cmd,
            cwd=mobile,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print("check_theme_drift: git not found; skip", file=sys.stderr)
        return ""
    if r.returncode != 0 and r.stderr:
        print(r.stderr, file=sys.stderr)
    return r.stdout or ""


def _parse_added_lines(diff_text: str) -> list[tuple[str, str]]:
    """Return (path, line) for added content lines in the diff."""
    out: list[tuple[str, str]] = []
    current_file = ""
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        if current_file and not any(
            current_file.replace("\\", "/").startswith(p) for p in SCAN_PREFIXES
        ):
            continue
        body = line[1:]
        out.append((current_file, body))
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--git-diff",
        action="store_true",
        help="Compare working tree to index/commit and scan added lines",
    )
    p.add_argument(
        "--base",
        default=None,
        help="Optional ref passed to git diff (e.g. origin/main)",
    )
    args = p.parse_args()
    if not args.git_diff:
        return 0

    diff = _git_diff_unified0(args.base)
    if not diff.strip():
        return 0

    violations: list[tuple[str, str]] = []
    for path, body in _parse_added_lines(diff):
        if BAD.search(body) is None:
            continue
        if any(s in body for s in ALLOWLIST_SUBSTRINGS):
            continue
        violations.append((path, body.strip()))

    if not violations:
        return 0

    print("check_theme_drift: avoid raw Colors.white / Colors.black on new lines.", file=sys.stderr)
    print("Use ThemeColors, ColorScheme, or add // theme-drift-ok with justification.", file=sys.stderr)
    for path, body in violations:
        print(f"  {path}: {body[:200]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
