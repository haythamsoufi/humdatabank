#!/usr/bin/env python3
"""Fail when duplicated Backoffice Python or JavaScript grows, and say where it is.

Detection is token-normalized ("type-2" clones). Each source line is reduced to
its shape: comments, docstrings and blank lines are dropped, string literals
become ``S``, numbers become ``0`` and every identifier that is not a language
keyword becomes ``I``. A run of ``WINDOW`` consecutive normalized lines that
also appears somewhere else (another file, or the same file at least ``WINDOW``
lines away) is duplicated. Because names and literals are ignored, a copy whose
variables, routes, messages or table names were renamed is still found. That is
the usual way "the same logic written twice" shows up. Import-only windows are
ignored. Tests, migrations, vendor libraries, generated catalogs and the sample
plugin scaffold are not scanned.

``scripts/ci/duplicate_code_budget.txt`` is the maximum number of duplicated
lines. The check fails when the tree is over budget. ``--base-ref`` fails when
the budget number itself increased, so a pull request cannot raise the ceiling
to hide a new copy. Lowering the budget after a real dedupe is allowed.

When the check fails it prints the duplicated blocks (``file:first-last`` for
every copy). With ``--base-ref`` it prints the blocks that have a copy inside
lines added by the branch first, which are the ones to share or extract.

Usage (from Backoffice/ or the repo root):

    python scripts/ci/check_duplicate_code.py
    python scripts/ci/check_duplicate_code.py --list --top 30
    python Backoffice/scripts/ci/check_duplicate_code.py --base-ref origin/main
"""
from __future__ import annotations

import argparse
import keyword
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

BACKOFFICE = Path(__file__).resolve().parents[2]
REPO = BACKOFFICE.parent
BUDGET_PATH = Path(__file__).resolve().with_name("duplicate_code_budget.txt")
GIT_BUDGET = "Backoffice/scripts/ci/duplicate_code_budget.txt"
WINDOW = 20
MOD = 1 << 64
BASE = 131
ZERO_SHA = "0000000000000000000000000000000000000000"
REPORT_LIMIT = 15

SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".venv",
    "coverage",
    "generated",
    "htmlcov",
    "libs",
    "migrations",
    "node_modules",
    "sample_plugin_package",
    "tests",
    "tinymce",
    "venv",
}
SCAN_SUFFIXES = {".py", ".js"}

JS_KEYWORDS = frozenset(
    """
    async await break case catch class const continue debugger default delete do
    else export extends false finally for from function if import in instanceof
    let new null of return static super switch this throw true try typeof
    undefined var void while with yield
    """.split()
)
PY_KEYWORDS = frozenset(keyword.kwlist) | {"self", "cls"}

_STRING = re.compile(r"""(?:[rRbBuUfF]{0,2})("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)""")
_NUMBER = re.compile(r"\b(?:0[xX][0-9a-fA-F]+|\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?)\b")
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")
_DOCSTRING_START = re.compile(r"""^[rRbBuUfF]*("{3}|'{3})""")


@dataclass(frozen=True)
class Block:
    """One duplicated run: every copy as (file, first_line, last_line), 1-based."""

    lines: int
    copies: tuple[tuple[str, int, int], ...]

    @property
    def weight(self) -> int:
        return self.lines * len(self.copies)

    def describe(self) -> str:
        shown = ", ".join(f"{path}:{first}-{last}" for path, first, last in self.copies[:6])
        extra = len(self.copies) - 6
        if extra > 0:
            shown += f", +{extra} more"
        return f"{self.lines} lines x {len(self.copies)}: {shown}"


def _shape(line: str, keywords: frozenset[str]) -> str:
    """Reduce a code line to its shape: names, strings and numbers are erased."""
    line = _STRING.sub("\x00", line)
    line = _NUMBER.sub("0", line)
    line = _IDENT.sub(lambda match: match.group(0) if match.group(0) in keywords else "I", line)
    return re.sub(r"\s+", " ", line.replace("\x00", '"S"')).strip()


def normalize_numbered(text: str, suffix: str) -> list[tuple[int, str]]:
    """Return (1-based source line number, normalized line) for each code line."""
    kept: list[tuple[int, str]] = []
    if suffix == ".py":
        closing = ""
        for number, raw in enumerate(text.splitlines(), start=1):
            stripped = raw.strip()
            if closing:
                if closing in stripped:
                    closing = ""
                continue
            if not stripped or stripped.startswith("#"):
                continue
            opener = _DOCSTRING_START.match(stripped)
            if opener:
                if opener.group(1) not in stripped[opener.end() :]:
                    closing = opener.group(1)
                continue
            shaped = _shape(stripped, PY_KEYWORDS)
            shaped = re.sub(r"\s*#.*$", "", shaped)
            if shaped:
                kept.append((number, shaped))
        return kept
    in_block = False
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if in_block:
            if "*/" in stripped:
                in_block = False
            continue
        if stripped.startswith("/*"):
            in_block = "*/" not in stripped
            continue
        if not stripped or stripped.startswith("*") or stripped.endswith("*/"):
            continue
        shaped = _shape(stripped, JS_KEYWORDS)
        shaped = re.sub(r"\s*//.*$", "", shaped)
        if shaped:
            kept.append((number, shaped))
    return kept


def normalize_lines(text: str, suffix: str) -> list[str]:
    return [line for _, line in normalize_numbered(text, suffix)]


def _line_hash(text: str) -> int:
    value = 0
    for byte in text.encode("utf-8"):
        value = (value * BASE + byte) & (MOD - 1)
    return value or 1


def _window_hashes(line_hashes: list[int], window: int) -> list[int]:
    if len(line_hashes) < window:
        return []
    base_pow = pow(BASE, window - 1, MOD)
    value = 0
    for item in line_hashes[:window]:
        value = (value * BASE + item) & (MOD - 1)
    hashes = [value]
    for index in range(window, len(line_hashes)):
        value = (value - line_hashes[index - window] * base_pow) % MOD
        value = (value * BASE + line_hashes[index]) % MOD
        hashes.append(value)
    return hashes


def _boilerplate(lines: list[str], start: int, window: int) -> bool:
    """Import blocks and repetitive data tables are not worth sharing.

    Names and literals are erased, so a table of ``"key": "value",`` rows looks
    like the same line repeated. Real logic has varied line shapes.
    """
    chunk = lines[start : start + window]
    imports = sum(1 for line in chunk if line.startswith(("import ", "from ", "} from ")))
    if imports * 2 >= window:
        return True
    return len(set(chunk)) * 2 < window


def _iter_sources(root: Path) -> list[Path]:
    found: list[Path] = []
    for folder_name in ("app", "plugins"):
        folder = root / folder_name
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                continue
            if path.name.endswith(".min.js"):
                continue
            rel_parts = path.relative_to(root).parts
            if any(part in SKIP_DIR_NAMES or part.startswith(".") for part in rel_parts):
                continue
            if path.stat().st_size > 400_000:
                continue
            found.append(path)
    return sorted(found)


def _real_duplicate(positions: list[tuple[int, int]], window: int) -> bool:
    for index, (file_a, start_a) in enumerate(positions):
        for file_b, start_b in positions[index + 1 :]:
            if file_a != file_b or abs(start_a - start_b) >= window:
                return True
    return False


def find_duplicate_blocks(root: Path, window: int = WINDOW) -> tuple[list[Block], int]:
    """Return maximal duplicated blocks and the number of duplicated lines."""
    names: list[str] = []
    numbers: list[list[int]] = []
    shapes: list[list[str]] = []
    for path in _iter_sources(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
        numbered = normalize_numbered(text, path.suffix)
        if numbered:
            names.append(path.relative_to(root).as_posix())
            numbers.append([number for number, _ in numbered])
            shapes.append([line for _, line in numbered])

    positions: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for file_index, lines in enumerate(shapes):
        hashed = [_line_hash(line) for line in lines]
        for start, digest in enumerate(_window_hashes(hashed, window)):
            if _boilerplate(lines, start, window):
                continue
            positions[digest].append((file_index, start))

    covered: list[bytearray] = [bytearray(len(lines)) for lines in shapes]
    groups_by_locs: dict[tuple[tuple[int, int], ...], None] = {}
    for locs in positions.values():
        if len(locs) < 2 or not _real_duplicate(locs, window):
            continue
        groups: dict[tuple[str, ...], list[tuple[int, int]]] = defaultdict(list)
        for file_index, start in locs:
            key = tuple(shapes[file_index][start : start + window])
            groups[key].append((file_index, start))
        for group in groups.values():
            if not _real_duplicate(group, window):
                continue
            groups_by_locs[tuple(sorted(group))] = None
            for file_index, start in group:
                covered[file_index][start : start + window] = b"\x01" * window
    duplicated = sum(block.count(1) for block in covered)

    # Chain windows that slide in lock-step (every copy advances by one line).
    blocks: list[Block] = []
    for locs in groups_by_locs:
        previous = tuple((file_index, start - 1) for file_index, start in locs)
        if previous in groups_by_locs:
            continue
        run = 0
        current = locs
        while True:
            following = tuple((file_index, start + 1) for file_index, start in current)
            if following not in groups_by_locs:
                break
            current = following
            run += 1
        span = window + run
        copies = tuple(
            (names[file_index], numbers[file_index][start], numbers[file_index][start + span - 1])
            for file_index, start in locs
        )
        blocks.append(Block(lines=span, copies=copies))
    blocks.sort(key=lambda block: (-block.weight, block.copies))
    return blocks, duplicated


def duplicated_line_count(root: Path, window: int = WINDOW) -> int:
    """Count normalized lines that belong to a repeated window."""
    return find_duplicate_blocks(root, window)[1]


def parse_budget(text: str) -> tuple[int, int]:
    window = None
    duplicated = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if key == "window":
            window = int(value)
        elif key == "duplicated_lines":
            duplicated = int(value)
    if window is None or duplicated is None:
        raise ValueError("budget file must set window and duplicated_lines")
    return window, duplicated


def budget_increase(previous: str, current: str) -> int:
    """Return how many lines the budget grew, or 0 when it did not."""
    _, old_count = parse_budget(previous)
    _, new_count = parse_budget(current)
    return max(0, new_count - old_count)


def _git(args: list[str]) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _git_show(rev: str, git_path: str) -> str | None:
    if not rev or rev == ZERO_SHA:
        return None
    return _git(["show", f"{rev}:{git_path}"])


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_added_ranges(diff: str) -> dict[str, list[tuple[int, int]]]:
    """Map Backoffice-relative path -> inclusive (first, last) added line ranges."""
    added: dict[str, list[tuple[int, int]]] = defaultdict(list)
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            if target.startswith("b/Backoffice/"):
                current = target[len("b/Backoffice/") :]
            else:
                current = None
            continue
        match = _HUNK.match(line)
        if match and current:
            first = int(match.group(1))
            count = 1 if match.group(2) is None else int(match.group(2))
            if count:
                added[current].append((first, first + count - 1))
    return dict(added)


def touches_added(block: Block, added: dict[str, list[tuple[int, int]]]) -> bool:
    for path, first, last in block.copies:
        for low, high in added.get(path, ()):
            if first <= high and low <= last:
                return True
    return False


def _format_blocks(blocks: list[Block], limit: int) -> str:
    shown = [f"  - {block.describe()}" for block in blocks[:limit]]
    if len(blocks) > limit:
        shown.append(f"  ... and {len(blocks) - limit} more (run with --list --top N)")
    return "\n".join(shown)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-ref", default="", help="Fail if the budget increased since this git revision")
    parser.add_argument("--list", action="store_true", help="Print the largest duplicated blocks and exit 0")
    parser.add_argument("--top", type=int, default=REPORT_LIMIT, help="How many blocks --list prints")
    parser.add_argument("--root", type=Path, default=BACKOFFICE, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    root = args.root.resolve()
    blocks, measured = find_duplicate_blocks(root)
    if args.list:
        print(f"{measured} duplicated lines in {len(blocks)} blocks (window {WINDOW}).")
        print(_format_blocks(blocks, args.top))
        return 0
    if not BUDGET_PATH.is_file():
        print(f"ERROR: missing {BUDGET_PATH.name}. Measured duplicated_lines={measured}.", file=sys.stderr)
        return 1
    try:
        window, budget = parse_budget(BUDGET_PATH.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    problems: list[str] = []
    if window != WINDOW:
        problems.append(f"Budget window is {window}; this check uses {WINDOW}.")
    if measured > budget:
        problems.append(
            f"Duplicated lines are {measured}, over the budget of {budget}. "
            "Share the copy or, after a real dedupe, lower duplicated_lines."
        )
        new_blocks: list[Block] = []
        if args.base_ref and root == BACKOFFICE:
            diff = _git(["diff", "-U0", "--no-color", args.base_ref, "--", "Backoffice"])
            if diff:
                added = parse_added_ranges(diff)
                new_blocks = [block for block in blocks if touches_added(block, added)]
        if new_blocks:
            problems.append("Duplicated blocks with a copy in lines added by this branch:")
            problems.append(_format_blocks(new_blocks, REPORT_LIMIT))
        else:
            problems.append("Largest duplicated blocks (tokens normalized: names and literals ignored):")
            problems.append(_format_blocks(blocks, REPORT_LIMIT))
    if args.base_ref and root == BACKOFFICE:
        previous = _git_show(args.base_ref, GIT_BUDGET)
        if previous is not None:
            try:
                grown = budget_increase(previous, BUDGET_PATH.read_text(encoding="utf-8"))
            except ValueError as exc:
                problems.append(str(exc))
            else:
                if grown:
                    problems.append(
                        f"Duplicate-code budget may only shrink. duplicated_lines increased by {grown}."
                    )
    if problems:
        print("ERROR: duplicate-code check failed.", file=sys.stderr)
        print("\n".join(problems), file=sys.stderr)
        return 1
    print(f"OK: duplicate-code check passed ({measured} duplicated lines, budget {budget}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
