#!/usr/bin/env python3
"""Write CodeQL's pr-diff-range.json from a local git diff.

The CodeQL action builds this file from the GitHub compare API, which returns
at most 300 changed files. Above that it skips diff-informed analysis and the
pull-request check treats every existing alert as new. A local ``git diff``
has no such cap. The analyze step reads ``$RUNNER_TEMP/pr-diff-range.json``
if it is present, including when init could not create it.

Usage (from the repository root, after the CodeQL init step):

    python .github/codeql/write_pr_diff_ranges.py <base-sha>
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def added_ranges(diff_text: str) -> list[dict]:
    """Return added line ranges in the same shape the CodeQL action writes."""
    ranges: list[dict] = []
    path: str | None = None
    current: int | None = None
    addition_start: int | None = None
    saw_hunk = False
    renamed = False

    def close_addition() -> None:
        nonlocal addition_start
        if path and addition_start is not None and current is not None:
            ranges.append(
                {
                    "path": path,
                    "startLine": addition_start,
                    "endLine": current - 1,
                }
            )
        addition_start = None

    def close_file() -> None:
        nonlocal path, current, saw_hunk
        close_addition()
        # A changed file with no hunk (binary, or a patch the diff omitted)
        # covers the whole file. CodeQL uses 0,0 for that case.
        # A rename with no hunk has no content change. A missing patch on a
        # file that was not renamed (binary, or a diff that was omitted)
        # covers the whole file, which is what the CodeQL action does.
        if path and not saw_hunk and not renamed:
            ranges.append({"path": path, "startLine": 0, "endLine": 0})
        path = None
        current = None
        saw_hunk = False
        renamed = False

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            close_file()
            continue
        if line.startswith("rename from ") or line.startswith("rename to "):
            renamed = True
            continue
        if line.startswith("+++ "):
            name = line[4:]
            if name.startswith("b/"):
                name = name[2:]
            path = None if name == "/dev/null" else name
            continue
        if path is None:
            continue
        hunk = HUNK.match(line)
        if hunk:
            close_addition()
            current = int(hunk.group(1))
            saw_hunk = True
            continue
        if current is None:
            continue
        if line.startswith("+"):
            if addition_start is None:
                addition_start = current
            current += 1
            continue
        if line.startswith("-") or line.startswith("\\"):
            continue
        close_addition()
        current += 1
    close_file()
    return ranges


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: write_pr_diff_ranges.py <base-sha>", file=sys.stderr)
        return 2
    base = sys.argv[1]
    repo = Path(__file__).resolve().parents[2]
    diff = subprocess.run(
        ["git", "diff", "-U0", "--find-renames", base, "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    ranges = added_ranges(diff.stdout)
    destination = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "pr-diff-range.json"
    destination.write_text(json.dumps(ranges), encoding="utf-8")
    files = len({item["path"] for item in ranges})
    print(f"Wrote {len(ranges)} diff range(s) across {files} file(s) to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
