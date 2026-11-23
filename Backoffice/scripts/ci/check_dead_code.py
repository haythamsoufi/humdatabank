#!/usr/bin/env python3
"""Fail on high-confidence dead code in Backoffice.

Two signals, both stdlib and both biased toward missing a real problem rather
than failing a live file:

1. Python modules under ``app/`` and ``plugins/`` that nothing reachable from
   an entry point imports. Importing a submodule counts as running that
   package's ``__init__.py``. Literal ``importlib.import_module`` calls,
   ``plugins/<id>/plugin.py`` and ``plugins/<id>/cli.py``, and sibling
   ``config.py`` loaded by ``load_plugin_config()`` are entry edges.
2. First-party ``.js`` / ``.css`` files whose path is never mentioned from
   templates, Python, JSON, or another live asset, including relative
   ``import`` specifiers resolved from the importing file.

``scripts/ci/dead_code_allowlist.txt`` holds modules that are unreachable today.
The list may only shrink: a path that is no longer dead must be removed, and
``--base-ref`` rejects any path added since that revision.

Usage (from Backoffice/ or the repo root):

    python scripts/ci/check_dead_code.py
    python Backoffice/scripts/ci/check_dead_code.py --base-ref origin/main
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

BACKOFFICE = Path(__file__).resolve().parents[2]
REPO = BACKOFFICE.parent
ALLOWLIST_PATH = Path(__file__).resolve().with_name("dead_code_allowlist.txt")
GIT_ALLOWLIST = "Backoffice/scripts/ci/dead_code_allowlist.txt"

SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".venv",
    "coverage",
    "htmlcov",
    "libs",
    "migrations",
    "node_modules",
    "tinymce",
    "venv",
}
CANDIDATE_EXCLUDE = {"migrations", "sample_plugin_package", "scripts", "tests"}
ASSET_SKIP_RELS = {
    "app/static/css/input.css",
    "app/static/css/output.css",
}
_ASSET_TOKEN = re.compile(r"[\w./\\-]*\.(?:js|css)\b")
MODULE_CONST = re.compile(r"^[A-Za-z_][\w]*(\.[A-Za-z_][\w]*)*$")
ZERO_SHA = "0000000000000000000000000000000000000000"


def module_name(root: Path, path: Path) -> str:
    parts = list(path.relative_to(root).parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def package_parts(root: Path, path: Path) -> list[str]:
    name = module_name(root, path)
    if path.name == "__init__.py":
        return name.split(".") if name else []
    return name.split(".")[:-1]


def _skipped(path: Path, root: Path) -> bool:
    return any(part in SKIP_DIR_NAMES or part.startswith(".") for part in path.relative_to(root).parts)


def _is_candidate(rel: Path) -> bool:
    parts = rel.parts
    if not parts or parts[0] not in {"app", "plugins"}:
        return False
    return not any(part in CANDIDATE_EXCLUDE for part in parts)


def _is_entry(rel: Path) -> bool:
    if rel.name in {"conftest.py", "run.py"}:
        return True
    if rel.as_posix() == "app/__init__.py":
        return True
    if rel.parts and rel.parts[0] in {"scripts", "tests"}:
        return True
    if "tests" in rel.parts or "scripts" in rel.parts:
        return True
    # Plugin manager loads plugins/<id>/plugin.py. CLI discovery loads plugins/<id>/cli.py.
    if rel.parts and rel.parts[0] == "plugins" and len(rel.parts) == 3 and rel.name in {"plugin.py", "cli.py"}:
        return True
    return False


def _remember(edges: dict[str, set[str]], src: str, target: str, known: set[str]) -> None:
    parts = target.split(".")
    for length in range(len(parts), 0, -1):
        candidate = ".".join(parts[:length])
        if candidate in known and candidate != src:
            edges[src].add(candidate)
            return


def _string_constants(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and MODULE_CONST.match(node.value):
            found.add(node.value)
    return found


def _dynamic_imports(tree: ast.AST, pkg: list[str], known: set[str]) -> set[str]:
    """Resolve import_module() calls, including the lazy maps in package __init__ files."""
    targets: set[str] = set()
    dynamic = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        is_import = (isinstance(func, ast.Attribute) and func.attr == "import_module") or (
            isinstance(func, ast.Name) and func.id == "import_module"
        )
        if not is_import:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            targets.add(arg.value)
            continue
        dynamic = True
        if not isinstance(arg, ast.JoinedStr):
            continue
        literals: list[str] = []
        for part in arg.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                literals.append(part.value)
            else:
                literals.append("*")
        pattern = "".join(literals)
        if pattern.startswith("plugins.") and pattern.endswith(".cli"):
            targets.update(name for name in known if name.startswith("plugins.") and name.endswith(".cli"))
        elif pattern.startswith("plugins.") and pattern.endswith(".plugin"):
            targets.update(name for name in known if name.startswith("plugins.") and name.endswith(".plugin"))
    if dynamic:
        for const in _string_constants(tree):
            if const.startswith("app.") or const.startswith("plugins."):
                targets.add(const)
                continue
            relative = ".".join([*pkg, *const.split(".")])
            if relative in known:
                targets.add(relative)
    return targets


def _python_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [path for path in root.rglob("*.py") if path.is_file() and not _skipped(path, root)]


def find_dead_modules(root: Path) -> tuple[list[str], list[str]]:
    """Return ``(dead posix paths, parse errors)``."""
    files = _python_files(root)
    known = {module_name(root, path): path for path in files}
    edges: dict[str, set[str]] = defaultdict(set)
    errors: list[str] = []
    for path in files:
        src = module_name(root, path)
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (SyntaxError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(root).as_posix()}: {exc}")
            continue
        pkg = package_parts(root, path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    _remember(edges, src, alias.name, known)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0:
                    if node.module:
                        _remember(edges, src, node.module, known)
                        for alias in node.names:
                            _remember(edges, src, f"{node.module}.{alias.name}", known)
                    continue
                if node.level - 1 > len(pkg):
                    continue
                base = pkg[: len(pkg) - (node.level - 1)]
                if node.module:
                    absolute = ".".join([*base, *node.module.split(".")])
                    _remember(edges, src, absolute, known)
                    for alias in node.names:
                        _remember(edges, src, f"{absolute}.{alias.name}", known)
                else:
                    for alias in node.names:
                        _remember(edges, src, ".".join([*base, alias.name]), known)
        for target in _dynamic_imports(tree, pkg, set(known)):
            _remember(edges, src, target, known)
        if "load_plugin_config(" in source:
            _remember(edges, src, ".".join([*pkg, "config"]), known)

    entries = [name for name, path in known.items() if _is_entry(path.relative_to(root))]
    workflow_blob = _workflow_blob(root)
    for name, path in known.items():
        rel = path.relative_to(root).as_posix()
        if rel in workflow_blob or f"Backoffice/{rel}" in workflow_blob:
            entries.append(name)

    live: set[str] = set()
    stack = [name for name in entries if name in known]
    while stack:
        current = stack.pop()
        if current in live or current not in known:
            continue
        live.add(current)
        stack.extend(edges.get(current, ()))
        # Importing pkg.mod executes pkg/__init__.py, whose imports are live too.
        if "." in current:
            stack.append(current.rsplit(".", 1)[0])

    dead: list[str] = []
    for name, path in known.items():
        rel = path.relative_to(root)
        if _is_candidate(rel) and name not in live:
            dead.append(rel.as_posix())
    return sorted(dead), errors


def _workflow_blob(root: Path) -> str:
    repo = root.parent
    chunks: list[str] = []
    workflows = repo / ".github" / "workflows"
    if workflows.is_dir():
        for path in workflows.glob("*.yml"):
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    for name in ("Dockerfile", "entrypoint.sh"):
        path = root / name
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def _static_key(path: Path) -> str | None:
    parts = path.parts
    if "static" not in parts:
        return None
    index = len(parts) - 1 - parts[::-1].index("static")
    return "/".join(parts[index + 1 :])


def _asset_candidates(root: Path) -> list[Path]:
    found: list[Path] = []
    for folder in (root / "app" / "static", root / "plugins"):
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.suffix not in {".js", ".css"}:
                continue
            if _skipped(path, root) or path.name.endswith(".min.js"):
                continue
            rel = path.relative_to(root).as_posix()
            if rel in ASSET_SKIP_RELS:
                continue
            if "static" not in path.parts:
                continue
            found.append(path)
    return found


def _resolve_relative(from_file: Path, spec: str) -> Path | None:
    if not spec.startswith("."):
        return None
    target = (from_file.parent / spec).resolve()
    if target.is_file():
        return target
    for suffix in (".js", ".css"):
        with_suffix = Path(str(target) + suffix)
        if with_suffix.is_file():
            return with_suffix
    for candidate in (target / "index.js", target / "index.css"):
        if candidate.is_file():
            return candidate
    return None


def _asset_needles(by_rel: dict[str, Path]) -> dict[str, list[str]]:
    """Map a path fragment to the assets it names.

    Plugin field modules are often referenced as ``/plugins/static/<id>/js/file.js``
    rather than the repo path ``plugins/<id>/static/js/file.js``. A fragment that
    matches more than one asset marks every match, so a shared name cannot hide
    a live file.
    """
    grouped: dict[str, list[str]] = defaultdict(list)

    def add(needle: str | None, rel: str) -> None:
        if needle:
            grouped[needle].append(rel)

    for rel, path in by_rel.items():
        add(rel, rel)
        add(_static_key(path), rel)
        parts = rel.split("/")
        if "static" in parts and parts[0] == "plugins":
            index = parts.index("static")
            if index >= 1:
                plugin_id = parts[index - 1]
                rest = "/".join(parts[index + 1 :])
                add(f"plugins/static/{plugin_id}/{rest}", rel)
    return {needle: sorted(set(rels)) for needle, rels in grouped.items()}


def _mark_asset_tokens(
    text: str,
    base: Path | None,
    root: Path,
    by_rel: dict[str, Path],
    needles: dict[str, list[str]],
    live: set[str],
) -> None:
    for match in _ASSET_TOKEN.finditer(text):
        token = match.group(0).replace("\\", "/")
        if token.startswith("."):
            if base is None:
                continue
            resolved = _resolve_relative(base, token)
            if resolved is None:
                continue
            try:
                rel = resolved.relative_to(root).as_posix()
            except ValueError:
                continue
            if rel in by_rel:
                live.add(rel)
            continue
        token = token.lstrip("/")
        if token.startswith("Backoffice/"):
            token = token[len("Backoffice/") :]
        rels = needles.get(token)
        if rels is None and token.startswith("static/"):
            rels = needles.get(token[len("static/") :])
        if rels:
            live.update(rels)


def _seed_texts(root: Path) -> list[tuple[Path | None, str]]:
    """Non-asset files that may name a static path. ``None`` means no relative base."""
    texts: list[tuple[Path | None, str]] = []
    roots = [root / "app", root / "plugins", root / "scripts", root / "tests", root / "assets"]
    package_json = root / "package.json"
    if package_json.is_file():
        texts.append((None, package_json.read_text(encoding="utf-8", errors="ignore")))
    for folder in roots:
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".html", ".json", ".js", ".css", ".yml", ".yaml", ".md"}:
                continue
            if path.suffix.lower() == ".md":
                continue
            if _skipped(path, root):
                continue
            rel = path.relative_to(root).as_posix()
            if rel in ASSET_SKIP_RELS or path.stat().st_size > 2_000_000:
                continue
            # Candidate assets are followed only after something else references them.
            if path.suffix in {".js", ".css"} and "static" in path.parts and rel not in ASSET_SKIP_RELS:
                continue
            try:
                texts.append((path, path.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                continue
    return texts


def find_orphan_assets(root: Path) -> list[str]:
    assets = _asset_candidates(root)
    by_rel = {path.relative_to(root).as_posix(): path for path in assets}
    needles = _asset_needles(by_rel)
    live: set[str] = set()

    def absorb(text: str, base: Path | None) -> None:
        _mark_asset_tokens(text, base, root, by_rel, needles, live)

    for base, text in _seed_texts(root):
        absorb(text, base)

    queue = list(live)
    scanned: set[str] = set()
    while queue:
        rel = queue.pop()
        if rel in scanned:
            continue
        scanned.add(rel)
        path = by_rel.get(rel)
        if path is None:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        before = len(live)
        absorb(text, path)
        if len(live) != before:
            queue.extend(live - scanned)

    return sorted(rel for rel in by_rel if rel not in live)


def parse_allowlist(text: str) -> list[str]:
    paths: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            paths.append(line.replace("\\", "/"))
    return paths


def allowlist_additions(previous: str, current: str) -> list[str]:
    return sorted(set(parse_allowlist(current)) - set(parse_allowlist(previous)))


def _git_show(rev: str, git_path: str) -> str | None:
    if not rev or rev == ZERO_SHA:
        return None
    result = subprocess.run(
        ["git", "show", f"{rev}:{git_path}"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", default="", help="Fail if the allowlist gained paths since this git revision")
    parser.add_argument("--root", type=Path, default=BACKOFFICE, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    root = args.root.resolve()
    dead, errors = find_dead_modules(root)
    orphans = find_orphan_assets(root)
    allow_text = ALLOWLIST_PATH.read_text(encoding="utf-8") if ALLOWLIST_PATH.is_file() else ""
    allowed = parse_allowlist(allow_text)
    allowed_set = set(allowed)
    dead_set = set(dead)

    problems: list[str] = list(errors)
    unexpected = sorted(dead_set - allowed_set)
    stale = sorted(path for path in allowed_set if path not in dead_set)
    if unexpected:
        problems.append("Unreferenced Python modules (import them, delete them, or remove them from the tree):")
        problems.extend(f"  {path}" for path in unexpected)
    if orphans:
        problems.append("Unreferenced JS/CSS (no template, Python, or live asset names this file):")
        problems.extend(f"  {path}" for path in orphans)
    if stale:
        problems.append("Allowlist entries that are no longer dead — delete these lines:")
        problems.extend(f"  {path}" for path in stale)
    if len(allowed) != len(allowed_set):
        problems.append("Allowlist contains a duplicate path.")

    if args.base_ref and root == BACKOFFICE:
        previous = _git_show(args.base_ref, GIT_ALLOWLIST)
        if previous is not None:
            added = allowlist_additions(previous, allow_text)
            if added:
                problems.append("Dead-code allowlist may only shrink. Added paths:")
                problems.extend(f"  {path}" for path in added)

    if problems:
        print("ERROR: dead-code check failed.", file=sys.stderr)
        print("\n".join(problems), file=sys.stderr)
        return 1

    print(f"OK: dead-code check passed ({len(dead)} allowlisted module(s), 0 orphan assets).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
