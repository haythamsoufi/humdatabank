"""
Apply common Tailwind action-control class blobs → .btn design system across templates.
Run from Backoffice: python scripts/apply_btn_migration_patterns.py
"""
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1] / "app" / "templates"

# (old_substring, new_substring) — order matters (longest/specific first).
REPLACEMENTS: list[tuple[str, str]] = [
    (
        'class="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 disabled:opacity-50 disabled:cursor-not-allowed"',
        'class="btn btn-secondary btn-sm disabled:opacity-50 disabled:cursor-not-allowed"',
    ),
    (
        'class="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"',
        'class="btn btn-secondary btn-sm"',
    ),
    (
        'class="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500"',
        'class="btn btn-secondary btn-sm"',
    ),
    (
        'class="inline-flex items-center px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"',
        'class="btn btn-secondary btn-sm"',
    ),
    (
        'class="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"',
        'class="btn btn-secondary btn-sm"',
    ),
    (
        'class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"',
        'class="btn btn-secondary btn-sm"',
    ),
]


def main() -> None:
    n_files = 0
    grand = 0
    for path in sorted(ROOT.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        orig = text
        file_repl = 0
        for old, new in REPLACEMENTS:
            c = text.count(old)
            if c:
                text = text.replace(old, new)
                file_repl += c
        if text != orig:
            path.write_text(text, encoding="utf-8", newline="\n")
            n_files += 1
            grand += file_repl
            print(f"updated {path.relative_to(ROOT.parent)} (+{file_repl})")
    print(f"Done. Files changed: {n_files}, total replacements: {grand}")


if __name__ == "__main__":
    main()
