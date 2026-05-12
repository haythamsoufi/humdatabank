"""
Fail if Jinja templates reference __consoleSaved.* — that handle is the pre-guard native
console and ignores CLIENT_CONSOLE_LOGGING. Inline scripts must use window.__clientLog etc.

Run from repo root or Backoffice/:
  python Backoffice/scripts/check_no_console_saved_bypass.py
  python scripts/check_no_console_saved_bypass.py   # if cwd is Backoffice/
"""
from __future__ import annotations

import pathlib
import re
import sys

SCRIPT = pathlib.Path(__file__).resolve()
BACKOFFICE = SCRIPT.parents[1]
TEMPLATES = BACKOFFICE / "app" / "templates"
ALLOWED_NAME = "_client_console_guard.html"

# Property access on the saved handle (not the assignment `window.__consoleSaved =`)
PATTERN = re.compile(r"__consoleSaved\.\s*\w+")


def main() -> int:
    if not TEMPLATES.is_dir():
        print(f"ERROR: templates dir not found: {TEMPLATES}", file=sys.stderr)
        return 2

    bad: list[tuple[pathlib.Path, int, str]] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        if path.name == ALLOWED_NAME:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if PATTERN.search(line):
                bad.append((path, i, line.strip()))

    if not bad:
        print("OK: no __consoleSaved.* usage outside", ALLOWED_NAME)
        return 0

    print(
        "ERROR: __consoleSaved.* bypasses CLIENT_CONSOLE_LOGGING. "
        "Use window.__clientLog / __clientWarn / … (see components/_client_console_guard.html).\n",
        file=sys.stderr,
    )
    for path, line_no, text in bad:
        rel = path.relative_to(BACKOFFICE)
        print(f"  {rel}:{line_no}: {text}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
