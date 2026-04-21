#!/usr/bin/env python3
"""
Guard: discourage raw hex [Color] literals in UI layers.

Scans added lines in git diff under lib/screens/ and lib/widgets/ for patterns
like Color(0xFF...). Use ThemeColors, AppShellTokens, or theme palettes instead.

Allowlist substrings on the line suppress the warning (e.g. theme comments).

Usage (from MobileApp/):
  python scripts/check_raw_hex_in_ui.py --git-diff
  python scripts/check_raw_hex_in_ui.py --git-diff --base origin/main

Without --git-diff: exit 0.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


RAW_HEX = re.compile(r"Color\s*\(\s*0x[0-9A-Fa-f]{8}\s*\)")

SCAN_PREFIXES = (
    "lib/screens/",
    "lib/widgets/",
    "MobileApp/lib/screens/",
    "MobileApp/lib/widgets/",
)

ALLOWLIST_SUBSTRINGS = (
    "raw-hex-ok",
    "ColorScheme",
    "Color.lerp",
    "Color.alphaBlend",
    "withValues",
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
        print("check_raw_hex_in_ui: git not found; skip", file=sys.stderr)
        return ""
    if r.returncode != 0 and r.stderr:
        print(r.stderr, file=sys.stderr)
    return r.stdout or ""


def _parse_added_lines(diff_text: str) -> list[tuple[str, str]]:
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
        help="Scan added lines in working tree diff",
    )
    p.add_argument(
        "--base",
        default=None,
        help="Optional ref for git diff",
    )
    args = p.parse_args()
    if not args.git_diff:
        return 0

    diff = _git_diff_unified0(args.base)
    if not diff.strip():
        return 0

    violations: list[tuple[str, str]] = []
    for path, body in _parse_added_lines(diff):
        if RAW_HEX.search(body) is None:
            continue
        if any(s in body for s in ALLOWLIST_SUBSTRINGS):
            continue
        violations.append((path, body.strip()))

    if not violations:
        return 0

    print(
        "check_raw_hex_in_ui: avoid Color(0xFF...) literals in screens/widgets.",
        file=sys.stderr,
    )
    print(
        "Use context.theme / ThemeColors / AppShellTokens, or add // raw-hex-ok.",
        file=sys.stderr,
    )
    for path, body in violations:
        print(f"  {path}: {body[:220]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
