"""Inventory guard for the Jinja ``|safe`` filter.

``|tojson|safe`` (JS/JSON embedding) is fine. Every other ``|safe`` is a trust decision:
this test pins the reviewed set per template so adding a new one requires a conscious
edit here (and a justification in review). Prefer ``|rich_text``, ``Markup`` from an
escaping helper, or removing ``|safe`` altogether.

Justifications for the reviewed entries:
- macros/excel_io_modal.html, macros/excel_import_dropzone.html, macros/modal_shell.html,
  components/_page_header.html: caller-supplied fragments authored in other templates
  (developer-controlled macro arguments, never request data).
- core/dashboard/_admin_panel.html, core/activity_items_partial.html:
  ``format_activity_value`` / ``render_matrix_change`` return ``escape``-d output.
- forms/entry_form/*: ``form_integration.render_custom_field_entry_form`` returns ``Markup``
  built from an autoescaped plugin template (or the escaped fallback).
- admin/reports/export_pdf.html: ``payload.content`` is sanitised by
  ``services/reports/sanitize_service`` on save (follow-up: re-sanitise at export).
- Remaining multi-line/JS entries wrap ``_()``/``url_for`` values already passed through ``tojson``.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_SAFE = re.compile(r"\|\s*safe\b")

_REVIEWED = {
    "app/templates/admin/reports/export_pdf.html": 1,
    "app/templates/components/_page_header.html": 2,
    "app/templates/core/activity_items_partial.html": 10,
    "app/templates/core/dashboard/_admin_panel.html": 10,
    "app/templates/forms/entry_form/entry_form.html": 2,
    "app/templates/macros/excel_import_dropzone.html": 2,
    "app/templates/macros/excel_io_modal.html": 31,
    "app/templates/macros/modal_shell.html": 1,
}


def _scan():
    counts = {}
    for base in (ROOT / "app" / "templates", ROOT / "plugins"):
        for path in base.rglob("*.html"):
            rel = path.relative_to(ROOT).as_posix()
            for line in path.read_text(encoding="utf-8").splitlines():
                if not _SAFE.search(line):
                    continue
                if "tojson" in line or "escapejs" in line or "|js" in line or "safe_json_attr" in line:
                    continue
                counts[rel] = counts.get(rel, 0) + 1
    return counts


def test_safe_filter_usage_matches_reviewed_inventory():
    counts = _scan()
    new = {k: v for k, v in counts.items() if v > _REVIEWED.get(k, 0)}
    assert not new, (
        "New |safe usage (not |tojson|safe). Use |rich_text / Markup from an escaping helper, "
        f"or review and add to _REVIEWED with a justification: {new}"
    )
