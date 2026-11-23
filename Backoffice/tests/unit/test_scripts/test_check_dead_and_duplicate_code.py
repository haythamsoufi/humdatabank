"""Guards for unreachable modules, unreferenced assets, and duplicated lines."""

from __future__ import annotations

from pathlib import Path

from scripts.ci.check_dead_code import (
    allowlist_additions,
    find_dead_modules,
    find_orphan_assets,
)
from scripts.ci.check_duplicate_code import (
    Block,
    budget_increase,
    duplicated_line_count,
    find_duplicate_blocks,
    parse_added_ranges,
    touches_added,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_unreachable_module_is_reported_and_package_init_of_a_live_child_is_not(tmp_path: Path):
    root = tmp_path / "backoffice"
    _write(root / "app" / "__init__.py", "from .pkg.child import value\n")
    _write(root / "app" / "unused.py", "value = 1\n")
    _write(root / "app" / "pkg" / "__init__.py", '"""package"""\n')
    _write(root / "app" / "pkg" / "child.py", "value = 1\n")
    _write(root / "app" / "pkg" / "other.py", "value = 2\n")

    dead, errors = find_dead_modules(root)

    assert errors == []
    assert "app/unused.py" in dead
    assert "app/pkg/other.py" in dead
    assert "app/pkg/__init__.py" not in dead
    assert "app/pkg/child.py" not in dead


def test_plugin_entry_and_config_loaded_by_path_are_live(tmp_path: Path):
    root = tmp_path / "backoffice"
    _write(root / "app" / "__init__.py", "")
    _write(
        root / "plugins" / "demo" / "plugin.py",
        "from plugins.demo.routes import build\n",
    )
    _write(
        root / "plugins" / "demo" / "routes.py",
        "def build():\n"
        "    load_plugin_config(__file__)\n"
        "    return None\n",
    )
    _write(root / "plugins" / "demo" / "config.py", "plugin_config = {}\n")
    _write(root / "plugins" / "demo" / "forgotten.py", "value = 1\n")

    dead, errors = find_dead_modules(root)

    assert errors == []
    assert dead == ["plugins/demo/forgotten.py"]


def test_relative_js_import_and_plugin_static_url_keep_assets_live(tmp_path: Path):
    root = tmp_path / "backoffice"
    _write(
        root / "app" / "templates" / "page.html",
        "<script src=\"{{ static_url('js/used.js') }}\"></script>\n",
    )
    _write(root / "app" / "static" / "js" / "used.js", "import { help } from './helper.js';\n")
    _write(root / "app" / "static" / "js" / "helper.js", "export const help = 1;\n")
    _write(root / "app" / "static" / "js" / "orphan.js", "export const orphan = 1;\n")
    _write(
        root / "plugins" / "demo" / "plugin.py",
        "ASSETS = ['/plugins/static/demo/js/field.js']\n",
    )
    _write(root / "plugins" / "demo" / "static" / "js" / "field.js", "export const field = 1;\n")
    _write(root / "plugins" / "demo" / "static" / "js" / "unused.js", "export const unused = 1;\n")

    orphans = find_orphan_assets(root)

    assert orphans == [
        "app/static/js/orphan.js",
        "plugins/demo/static/js/unused.js",
    ]


def test_allowlist_additions_are_new_paths_only():
    previous = "# note\napp/old.py\n"
    current = "app/old.py\napp/new.py\n"
    assert allowlist_additions(previous, current) == ["app/new.py"]
    assert allowlist_additions(current, previous) == []


# Varied line shapes so the repetitive-table filter does not treat it as data.
_LOGIC = """\
def load_{name}(session, user, limit=10):
    rows = session.query({name}Model).filter_by(owner=user.id).all()
    if not rows:
        return {{"items": [], "message": "{text}"}}
    result = []
    for row in rows[:limit]:
        if row.deleted:
            continue
        try:
            payload = row.to_dict()
        except ValueError as exc:
            logger.warning("bad row %s", exc)
            continue
        payload["rank"] = len(result) + 1
        result.append(payload)
    total = sum(item["rank"] for item in result)
    while total > 100:
        total -= 7
    with session.begin():
        session.add(AuditEntry(kind="{name}", count=len(result)))
    return {{"items": result, "total": total}}
"""
_LOGIC_LINES = _LOGIC.count("\n")


def _logic(name: str, text: str) -> str:
    return _LOGIC.format(name=name, text=text)


def test_duplicated_block_counts_lines_in_both_copies(tmp_path: Path):
    root = tmp_path / "backoffice"
    _write(root / "app" / "a.py", _logic("Alpha", "none"))
    _write(root / "app" / "b.py", _logic("Alpha", "none"))
    _write(root / "app" / "c.py", "\n".join(f"only_{index}(value_{index})" for index in range(45)) + "\n")

    assert duplicated_line_count(root) == _LOGIC_LINES * 2
    alone = tmp_path / "single"
    _write(alone / "app" / "a.py", _logic("Alpha", "none"))
    assert duplicated_line_count(alone) == 0


def test_renamed_copy_is_still_a_duplicate(tmp_path: Path):
    root = tmp_path / "backoffice"
    _write(root / "app" / "a.py", _logic("Alpha", "no alpha rows"))
    _write(root / "app" / "b.py", _logic("Beta", "no beta rows"))

    blocks, duplicated = find_duplicate_blocks(root)

    assert duplicated == _LOGIC_LINES * 2
    assert len(blocks) == 1
    assert blocks[0].lines == _LOGIC_LINES
    assert [copy[0] for copy in blocks[0].copies] == ["app/a.py", "app/b.py"]
    assert blocks[0].copies[0][1:] == (1, _LOGIC_LINES)


def test_repetitive_data_table_is_not_a_duplicate(tmp_path: Path):
    root = tmp_path / "backoffice"
    table = "LABELS = {\n" + "".join(f'    "key_{i}": "value {i}",\n' for i in range(40)) + "}\n"
    other = "NAMES = {\n" + "".join(f'    "name_{i}": "text {i}",\n' for i in range(40)) + "}\n"
    _write(root / "app" / "a.py", table)
    _write(root / "app" / "b.py", other)

    assert duplicated_line_count(root) == 0


def test_comments_and_docstrings_do_not_hide_a_copy(tmp_path: Path):
    root = tmp_path / "backoffice"
    documented = '"""Module note."""\n# heading\n' + _logic("Alpha", "none").replace(
        "    rows =", '    """Fetch."""\n    # fetch\n    rows =', 1
    )
    _write(root / "app" / "a.py", documented)
    _write(root / "app" / "b.py", _logic("Alpha", "none"))

    assert duplicated_line_count(root) == _LOGIC_LINES * 2


def test_block_reports_original_line_numbers(tmp_path: Path):
    root = tmp_path / "backoffice"
    _write(root / "app" / "a.py", "# lead\n\n" + _logic("Alpha", "none"))
    _write(root / "app" / "b.py", _logic("Alpha", "none"))

    blocks, _ = find_duplicate_blocks(root)

    assert blocks[0].copies == (("app/a.py", 3, 2 + _LOGIC_LINES), ("app/b.py", 1, _LOGIC_LINES))
    assert f"app/a.py:3-{2 + _LOGIC_LINES}" in blocks[0].describe()


def test_added_ranges_pick_out_blocks_from_a_branch_diff():
    diff = (
        "--- a/Backoffice/app/a.py\n"
        "+++ b/Backoffice/app/a.py\n"
        "@@ -5,0 +6,3 @@ def old():\n"
        "+x\n+y\n+z\n"
        "@@ -20,2 +24 @@\n"
        "+w\n"
        "--- a/Website/x.py\n"
        "+++ b/Website/x.py\n"
        "@@ -1 +1 @@\n"
    )
    added = parse_added_ranges(diff)
    assert added == {"app/a.py": [(6, 8), (24, 24)]}
    assert touches_added(Block(lines=10, copies=(("app/a.py", 1, 7), ("app/b.py", 1, 10))), added)
    assert not touches_added(Block(lines=5, copies=(("app/a.py", 9, 20), ("app/b.py", 1, 5))), added)


def test_budget_increase_ignores_a_shrink():
    previous = "window=40\nduplicated_lines=100\n"
    assert budget_increase(previous, "window=40\nduplicated_lines=100\n") == 0
    assert budget_increase(previous, "window=40\nduplicated_lines=80\n") == 0
    assert budget_increase(previous, "window=40\nduplicated_lines=120\n") == 20


def test_backoffice_tree_passes_both_checks():
    from scripts.ci.check_dead_code import main as dead_main
    from scripts.ci.check_duplicate_code import main as duplicate_main

    assert dead_main([]) == 0
    assert duplicate_main([]) == 0
