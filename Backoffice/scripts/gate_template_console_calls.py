"""
One-off maintenance: replace console.log/debug/info/warn/group* in Jinja templates
with window.__client* helpers defined in components/_client_console_guard.html so
verbose output respects CLIENT_CONSOLE_LOGGING even when native console is not nooped.

Does not modify console.error.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1] / "app" / "templates"
SKIP_NAMES = {"_client_console_guard.html"}

# Longer patterns first (apply) before simple (.(
APPLY_REPLACEMENTS: list[tuple[str, str]] = [
    ("console.groupCollapsed.apply(console,", "window.__clientGroupCollapsed && window.__clientGroupCollapsed.apply(null,"),
    ("console.groupEnd.apply(console,", "window.__clientGroupEnd && window.__clientGroupEnd.apply(null,"),
    ("console.group.apply(console,", "window.__clientGroup && window.__clientGroup.apply(null,"),
    ("console.debug.apply(console,", "window.__clientDebug && window.__clientDebug.apply(null,"),
    ("console.info.apply(console,", "window.__clientInfo && window.__clientInfo.apply(null,"),
    ("console.trace.apply(console,", "window.__clientTrace && window.__clientTrace.apply(null,"),
    ("console.table.apply(console,", "window.__clientTable && window.__clientTable.apply(null,"),
    ("console.dir.apply(console,", "window.__clientDir && window.__clientDir.apply(null,"),
    ("console.log.apply(console,", "window.__clientLog && window.__clientLog.apply(null,"),
    ("console.warn.apply(console,", "window.__clientWarn && window.__clientWarn.apply(null,"),
]

CALL_REPLACEMENTS: list[tuple[str, str]] = [
    ("console.groupCollapsed(", "window.__clientGroupCollapsed && window.__clientGroupCollapsed("),
    ("console.groupEnd(", "window.__clientGroupEnd && window.__clientGroupEnd("),
    ("console.group(", "window.__clientGroup && window.__clientGroup("),
    ("console.debug(", "window.__clientDebug && window.__clientDebug("),
    ("console.info(", "window.__clientInfo && window.__clientInfo("),
    ("console.trace(", "window.__clientTrace && window.__clientTrace("),
    ("console.table(", "window.__clientTable && window.__clientTable("),
    ("console.dir(", "window.__clientDir && window.__clientDir("),
    ("console.log(", "window.__clientLog && window.__clientLog("),
    ("console.warn(", "window.__clientWarn && window.__clientWarn("),
]


def main() -> int:
    changed = 0
    for path in sorted(ROOT.rglob("*.html")):
        if path.name in SKIP_NAMES:
            continue
        text = path.read_text(encoding="utf-8")
        orig = text
        for old, new in APPLY_REPLACEMENTS:
            text = text.replace(old, new)
        for old, new in CALL_REPLACEMENTS:
            text = text.replace(old, new)
        if text != orig:
            path.write_text(text, encoding="utf-8", newline="\n")
            changed += 1
            print(path.relative_to(ROOT.parent.parent))
    print(f"Updated {changed} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
