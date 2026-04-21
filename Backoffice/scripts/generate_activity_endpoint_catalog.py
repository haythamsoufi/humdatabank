#!/usr/bin/env python3
"""
Regenerate per-blueprint partials under app/utils/activity_endpoint_catalog/generated/partials/
and merged app/utils/activity_endpoint_catalog/generated/__init__.py from Flask url_map.

Run from Backoffice directory:
  python scripts/generate_activity_endpoint_catalog.py

Requires FLASK_APP / app factory (uses create_app).
"""

from __future__ import annotations

import keyword
import os
import re
import shutil
import sys

_BACKOFFICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKOFFICE_ROOT not in sys.path:
    sys.path.insert(0, _BACKOFFICE_ROOT)

os.chdir(_BACKOFFICE_ROOT)
if not os.environ.get("FLASK_APP"):
    os.environ["FLASK_APP"] = "run.py"

_GENERATED_PKG = os.path.join(
    _BACKOFFICE_ROOT, "app", "utils", "activity_endpoint_catalog", "generated"
)
_PARTIALS_DIR = os.path.join(_GENERATED_PKG, "partials")


def _safe_partial_module(blueprint: str) -> str:
    """Python module filename under partials/ (must be importable)."""
    if not blueprint or not str(blueprint).strip():
        return "unknown_blueprint"
    bp = str(blueprint).strip()
    if not bp.isidentifier() or keyword.iskeyword(bp):
        bp = re.sub(r"[^a-zA-Z0-9_]", "_", bp) + "_bp"
    # Avoid shadowing stdlib modules in common edge cases
    if bp in ("json", "types", "sys", "io", "os", "re"):
        return f"{bp}_bp"
    return bp


def main() -> None:
    from app import create_app
    from app.utils.activity_logging_skip import (
        should_exclude_from_activity_catalog,
        should_skip_activity_path,
    )
    from app.utils.activity_endpoint_overrides import (
        resolve_delete_activity_type,
        resolve_post_activity_type,
    )
    from app.utils.activity_endpoint_catalog.defaults import (
        activity_category_for_endpoint,
        default_generated_description,
    )

    app = create_app()

    by_bp: dict[str, list[tuple[str, str, str, str]]] = {}
    seen: set[tuple[str, str]] = set()
    with app.app_context():
        for rule in app.url_map.iter_rules():
            ep = rule.endpoint
            if not ep:
                continue
            if should_skip_activity_path(str(rule.rule or "")):
                continue
            if ep == "forms.enter_data":
                continue
            if ep in ("favicon", "test_static_file"):
                continue
            methods = set(rule.methods or ()) - {"HEAD", "OPTIONS", "TRACE"}
            for method in sorted(methods):
                if should_exclude_from_activity_catalog(method, ep):
                    continue
                if ep == "main.dashboard" and method == "POST":
                    continue
                if method == "POST" and resolve_post_activity_type(ep):
                    continue
                if method == "DELETE" and resolve_delete_activity_type(ep):
                    continue
                key = (method, ep)
                if key in seen:
                    continue
                seen.add(key)
                desc = default_generated_description(method, ep)
                cat = activity_category_for_endpoint(ep)
                desc_esc = desc.replace("\\", "\\\\").replace('"', '\\"')
                bp = ep.split(".", 1)[0] if "." in ep else ep
                by_bp.setdefault(bp, []).append((method, ep, desc_esc, cat))

    # Clean and recreate partials
    if os.path.isdir(_PARTIALS_DIR):
        shutil.rmtree(_PARTIALS_DIR)
    os.makedirs(_PARTIALS_DIR, exist_ok=True)

    partial_modules: list[tuple[str, str]] = []  # (import_name, safe_bp)

    for bp in sorted(by_bp.keys()):
        safe_mod = _safe_partial_module(bp)
        partial_modules.append((safe_mod, bp))
        lines = [
            '"""',
            f"AUTO-GENERATED — blueprint {bp!r}. Do not edit by hand.",
            "Regenerate: python scripts/generate_activity_endpoint_catalog.py",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec",
            "",
            "",
            "SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {",
        ]
        for method, ep, desc_esc, cat in sorted(by_bp[bp], key=lambda x: (x[0], x[1])):
            lines.append(
                f'    ("{method}", "{ep}"): ActivityEndpointSpec(description="{desc_esc}", activity_type="{cat}"),'
            )
        lines.append("}")
        lines.append("")
        out_path = os.path.join(_PARTIALS_DIR, f"{safe_mod}.py")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    with open(os.path.join(_PARTIALS_DIR, "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""Per-blueprint generated activity catalog partials."""\n')

    init_lines = [
        '"""',
        "AUTO-GENERATED — merged activity catalog from per-blueprint partials.",
        "Regenerate: python scripts/generate_activity_endpoint_catalog.py",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec, merge_activity_specs",
        "",
    ]
    for safe_mod, _bp in sorted(partial_modules, key=lambda x: x[0]):
        init_lines.append(
            f"from app.utils.activity_endpoint_catalog.generated.partials.{safe_mod} import SPECS as _S_{safe_mod}"
        )
    init_lines.append("")
    init_lines.append(
        "GENERATED_ACTIVITY_SPECS: dict[tuple[str, str], ActivityEndpointSpec] = merge_activity_specs("
    )
    specs_sorted = sorted(partial_modules, key=lambda x: x[0])
    for i, (safe_mod, _) in enumerate(specs_sorted):
        init_lines.append(f"    _S_{safe_mod},")
    init_lines.append("    allow_override=False,")
    init_lines.append(")")
    init_lines.append("")

    with open(os.path.join(_GENERATED_PKG, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("\n".join(init_lines) + "\n")

    print(f"Wrote {len(seen)} entries in {len(by_bp)} blueprint partials under {_PARTIALS_DIR}")


if __name__ == "__main__":
    main()
