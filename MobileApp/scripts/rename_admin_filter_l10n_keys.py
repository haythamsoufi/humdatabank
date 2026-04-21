#!/usr/bin/env python3
"""
Rename shared admin filter-sheet localization keys and getters.

Originally these strings lived under session_logs_* because they were introduced
on Session Logs. They are reused by multiple admin screens, so identifiers are
now admin_filters* / adminFilters*.

Mappings applied:
  Translation map keys (in lib/l10n/app_localizations.dart):
    session_logs_filters  -> admin_filters
    session_logs_apply      -> admin_filters_apply
    session_logs_clear      -> admin_filters_clear

  Dart getters (same file + all call sites under lib/):
    sessionLogsFilters -> adminFilters
    sessionLogsApply     -> adminFiltersApply
    sessionLogsClear     -> adminFiltersClear

Usage (from MobileApp/):
  python scripts/rename_admin_filter_l10n_keys.py --dry-run
  python scripts/rename_admin_filter_l10n_keys.py

Safe to run multiple times: after a successful run, replacements are no-ops.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Order: map keys first (longest / most specific), then Dart identifiers (longest first).
REPLACEMENTS: list[tuple[str, str]] = [
    ("session_logs_filters", "admin_filters"),
    ("session_logs_apply", "admin_filters_apply"),
    ("session_logs_clear", "admin_filters_clear"),
    ("sessionLogsFilters", "adminFilters"),
    ("sessionLogsApply", "adminFiltersApply"),
    ("sessionLogsClear", "adminFiltersClear"),
]

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "lib"


def replace_in_text(text: str) -> tuple[str, int]:
    """Return (new_text, number of non-overlapping replacements)."""
    total = 0
    out = text
    for old, new in REPLACEMENTS:
        count = out.count(old)
        if count:
            out = out.replace(old, new)
            total += count
    return out, total


def process_file(path: Path, dry_run: bool) -> int:
    raw = path.read_text(encoding="utf-8")
    new, n = replace_in_text(raw)
    if n == 0 or new == raw:
        return 0
    if not dry_run:
        path.write_text(new, encoding="utf-8", newline="\n")
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without writing files",
    )
    args = parser.parse_args()

    if not LIB.is_dir():
        print(f"Expected lib/ at {LIB}", file=sys.stderr)
        return 1

    changed_files = 0
    total_repls = 0
    for path in sorted(LIB.rglob("*.dart")):
        n = process_file(path, dry_run=args.dry_run)
        if n:
            changed_files += 1
            total_repls += n
            print(f"{'Would update' if args.dry_run else 'Updated'} {path.relative_to(ROOT)} ({n} replacement(s))")

    if changed_files == 0:
        print("No files needed changes (already migrated or no matches).")
    else:
        print(f"Done: {changed_files} file(s), {total_repls} replacement(s) total.")
        if args.dry_run:
            print("Re-run without --dry-run to write.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
