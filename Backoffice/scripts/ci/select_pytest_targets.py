#!/usr/bin/env python3
"""Map a git diff to pytest targets so CI does not run the full suite.

Modes
-----
skip      No Python / test-infra change (CSS, templates, docs, …).
selected  Run only test files that match the changed paths.
fast      Shared fixtures, deps, app factory, migrations, or the CI workflow
          itself changed — run ``pytest -m "not slow"`` (not the 6-hour suite).

Usage (from repo root or Backoffice/):
    python Backoffice/scripts/ci/select_pytest_targets.py --base-ref "$BASE"
    python Backoffice/scripts/ci/select_pytest_targets.py --base-ref "$BASE" --github-output
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
BACKOFFICE_ROOT = SCRIPT_PATH.parents[2]
REPO_ROOT = BACKOFFICE_ROOT.parent

WORKFLOW_PATH = ".github/workflows/backoffice-ci.yml"

BLAST_RADIUS = frozenset(
    {
        "pytest.ini",
        "requirements.txt",
        "requirements-dev.txt",
        "app/__init__.py",
        "app/extensions.py",
        "app/config.py",
        "config.py",
        "tests/conftest.py",
    }
)

IGNORE_SUFFIXES = frozenset(
    {
        ".md",
        ".css",
        ".scss",
        ".map",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".html",
        ".jinja",
        ".j2",
        ".po",
        ".pot",
        ".mo",
        ".json",
        ".txt",
        ".yml",
        ".yaml",
        ".toml",
        ".cfg",
        ".ini",
        ".xml",
        ".idml",
        ".docx",
        ".xlsx",
        ".xls",
        ".csv",
    }
)

# These stay blast-radius even though the suffix is otherwise ignored.
KEEP_DESPITE_SUFFIX = frozenset(
    {
        "pytest.ini",
        "requirements.txt",
        "requirements-dev.txt",
    }
)

RENDER_PREFIXES = (
    "plugins/pb_progress/",
    "plugins/upr_visuals/",
)


@dataclass(frozen=True)
class PytestPlan:
    mode: str
    targets: tuple[str, ...]
    reason: str
    needs_render_libs: bool

    @property
    def skip(self) -> bool:
        return self.mode == "skip"


def _posix(path: str | Path) -> str:
    posix = str(path).replace("\\", "/")
    if posix.startswith("./"):
        return posix[2:]
    return posix


def to_backoffice_rel(raw: str) -> str | None:
    """Return a Backoffice-relative posix path, or a sentinel for repo CI files."""
    posix = _posix(raw)
    if posix == WORKFLOW_PATH:
        return WORKFLOW_PATH
    prefix = "Backoffice/"
    if posix.startswith(prefix):
        return posix[len(prefix) :]
    if posix.startswith("backoffice/"):
        return posix[len("backoffice/") :]
    return None


def is_blast_radius(rel: str) -> bool:
    if rel == WORKFLOW_PATH:
        return True
    if rel in BLAST_RADIUS or rel in KEEP_DESPITE_SUFFIX:
        return True
    if rel.startswith("migrations/"):
        return True
    if rel.endswith("/conftest.py") and (
        rel.startswith("tests/") or "/tests/" in rel
    ):
        return True
    return False


def is_pytest_file(rel: str) -> bool:
    name = Path(rel).name
    if not name.endswith(".py"):
        return False
    return name.startswith("test_") or name.endswith("_test.py")


def is_ignorable(rel: str) -> bool:
    if is_blast_radius(rel) or is_pytest_file(rel):
        return False
    suffix = Path(rel).suffix.lower()
    if rel in KEEP_DESPITE_SUFFIX:
        return False
    if suffix in IGNORE_SUFFIXES:
        return True
    # Static / template trees never have a pytest counterpart worth running.
    if rel.startswith("app/static/") or rel.startswith("app/templates/"):
        return True
    if "/static/" in rel and not rel.endswith(".py"):
        return True
    return False


def _iter_existing_tests(root: Path) -> list[Path]:
    found: list[Path] = []
    for base in ("tests", "plugins"):
        directory = root / base
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            name = path.name
            if name.startswith("test_") or name.endswith("_test.py"):
                found.append(path)
    return found


def _name_candidates(rel: str) -> set[str]:
    path = Path(rel)
    stem = path.stem
    names = {f"test_{stem}.py"}
    parts = path.with_suffix("").parts
    if parts and parts[0] == "app" and len(parts) >= 3:
        names.add(f"test_{'_'.join(parts[2:])}.py")
        names.add(f"test_{'_'.join(parts[1:])}.py")
    if parts and parts[0] == "scripts" and len(parts) >= 2:
        names.add(f"test_{stem}.py")
        names.add("test_scripts_layout.py")
    return names


def _plugin_targets(rel: str, root: Path, test_files: list[Path]) -> set[str]:
    parts = Path(rel).parts
    if len(parts) < 2 or parts[0] != "plugins":
        return set()
    plugin = parts[1]
    names = _name_candidates(rel)
    prefix = ("plugins", plugin)
    hits = {
        _posix(path.relative_to(root))
        for path in test_files
        if path.relative_to(root).parts[:2] == prefix and path.name in names
    }
    if hits:
        return hits
    targets: set[str] = set()
    for extra in (
        Path("plugins") / plugin / "tests",
        Path("plugins") / plugin / "visuals" / "tests",
    ):
        if (root / extra).is_dir():
            targets.add(_posix(extra))
    plugin_app_tests = root / "tests" / "unit" / "test_plugins"
    if plugin_app_tests.is_dir():
        for path in plugin_app_tests.glob(f"test_{plugin}*.py"):
            targets.add(_posix(path.relative_to(root)))
    return targets


def map_changed_file(rel: str, root: Path, test_files: list[Path]) -> set[str]:
    if not rel or rel == WORKFLOW_PATH:
        return set()
    full = root / rel
    if is_pytest_file(rel):
        return {_posix(rel)} if full.is_file() else set()

    names = _name_candidates(rel)
    hits = {
        _posix(path.relative_to(root))
        for path in test_files
        if path.name in names
    }
    hits.update(_plugin_targets(rel, root, test_files))
    if rel.startswith("scripts/"):
        layout = root / "tests" / "unit" / "test_scripts_layout.py"
        if layout.is_file():
            hits.add("tests/unit/test_scripts_layout.py")
    return hits


def plan_pytest_run(changed_paths: list[str], root: Path | None = None) -> PytestPlan:
    """Decide skip / selected / fast from repo-relative changed paths."""
    root = root or BACKOFFICE_ROOT
    rels: list[str] = []
    for raw in changed_paths:
        mapped = to_backoffice_rel(raw)
        if mapped:
            rels.append(mapped)

    if not rels:
        return PytestPlan("skip", (), "No Backoffice files in the diff", False)

    blast = [rel for rel in rels if is_blast_radius(rel)]
    if blast:
        return PytestPlan(
            "fast",
            (),
            "Shared test/app infra changed: " + ", ".join(blast[:8]),
            True,
        )

    actionable = [rel for rel in rels if not is_ignorable(rel)]
    if not actionable:
        return PytestPlan("skip", (), "Diff is non-Python (templates/static/docs)", False)

    test_files = _iter_existing_tests(root)
    targets: set[str] = set()
    for rel in actionable:
        targets.update(map_changed_file(rel, root, test_files))

    existing = tuple(
        sorted(t for t in targets if (root / t).exists())
    )
    if not existing:
        return PytestPlan(
            "skip",
            (),
            "Changed Python files have no matching tests",
            False,
        )

    needs_render = any(t.startswith(RENDER_PREFIXES) for t in existing)
    return PytestPlan("selected", existing, "Mapped changed files to tests", needs_render)


def list_changed_files(base_ref: str | None, repo_root: Path | None = None) -> list[str]:
    repo_root = repo_root or REPO_ROOT
    if base_ref:
        cmd = [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            f"{base_ref}...HEAD",
        ]
    else:
        staged = subprocess.check_output(
            ["git", "-C", str(repo_root), "diff", "--name-only", "--cached", "--diff-filter=ACMR"],
            text=True,
        )
        unstaged = subprocess.check_output(
            ["git", "-C", str(repo_root), "diff", "--name-only", "--diff-filter=ACMR"],
            text=True,
        )
        files = []
        seen: set[str] = set()
        for line in (staged + "\n" + unstaged).splitlines():
            path = line.strip()
            if path and path not in seen:
                seen.add(path)
                files.append(path)
        return files
    output = subprocess.check_output(cmd, text=True)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _write_github_output(plan: PytestPlan) -> None:
    dest = os.environ.get("GITHUB_OUTPUT")
    if not dest:
        print("GITHUB_OUTPUT is not set", file=sys.stderr)
        sys.exit(2)
    with open(dest, "a", encoding="utf-8") as handle:
        handle.write(f"skip={'true' if plan.skip else 'false'}\n")
        handle.write(f"mode={plan.mode}\n")
        handle.write(f"needs_render_libs={'true' if plan.needs_render_libs else 'false'}\n")
        handle.write(f"reason={plan.reason}\n")
        handle.write(f"targets={' '.join(plan.targets)}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select pytest targets from a git diff.")
    parser.add_argument(
        "--base-ref",
        default=None,
        metavar="SHA",
        help="Base commit to diff against (PR base or push before SHA).",
    )
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="Append skip/mode/targets to $GITHUB_OUTPUT.",
    )
    args = parser.parse_args(argv)

    empty_base = (
        not args.base_ref
        or args.base_ref == "0000000000000000000000000000000000000000"
    )
    if args.base_ref and empty_base:
        plan = PytestPlan(
            "fast",
            (),
            "No base SHA available — running fast suite",
            True,
        )
    else:
        try:
            changed = list_changed_files(args.base_ref)
        except subprocess.CalledProcessError as exc:
            print(f"git diff failed: {exc}", file=sys.stderr)
            return 2
        plan = plan_pytest_run(changed)

    print(f"mode={plan.mode}")
    print(f"reason={plan.reason}")
    print(f"needs_render_libs={plan.needs_render_libs}")
    if plan.targets:
        print("targets:")
        for target in plan.targets:
            print(f"  {target}")
    if args.github_output:
        _write_github_output(plan)
    return 0


if __name__ == "__main__":
    sys.exit(main())
