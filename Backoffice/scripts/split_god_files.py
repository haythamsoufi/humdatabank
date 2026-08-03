#!/usr/bin/env python3
"""One-off helper to split notification notifiers and excel_service modules."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTIF_CORE = ROOT / "app/services/notification/core.py"
NOTIFIERS_DIR = ROOT / "app/services/notification/notifiers"
EXCEL_SERVICE = ROOT / "app/services/templates/excel_service.py"
TEMPLATES_DIR = ROOT / "app/services/templates"


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def slice_lines(lines: list[str], start: int, end: int) -> list[str]:
    """1-based inclusive line range."""
    return lines[start - 1 : end]


def split_notification_notifiers() -> None:
    lines = read_lines(NOTIF_CORE)

    ranges = {
        "assignment": [
            (922, 1029),   # notify_assignment_created
            (1032, 1160),  # notify_assignment_submitted + _focal_point_ids_by_org_domain
            (1163, 1341),  # sent_for_review, returned_for_revision
            (1377, 1477),  # approved, reopened
            (1516, 1564),  # self_report_created
            (1941, 1991),  # form_data_updated
        ],
        "documents": [
            (1344, 1374),  # notify_document_uploaded
            (1620, 1938),  # notify_standalone_document_uploaded
        ],
        "digest": [
            (1480, 1617),  # user_added_to_country, public_submission_received
        ],
    }

    common_header = '''"""Typed notification helpers for {domain} events."""

from flask import url_for, current_app
from flask_login import current_user
from flask_babel import gettext as _
from sqlalchemy import or_, select

from app.models import NotificationType, User, Country
from app.services.platform.app_settings_service import audience_bucket_enabled
from app.services.notification.audience import (
    collect_entity_admin_audience_recipient_ids,
    get_assignment_editor_submitter_user_ids_for_entity,
)
from app.services.notification.creation import create_notification

'''

    assignment_extra = '''from app.services.notification.core import (
    log_entity_activity,
    notify_entity_focal_points,
)

'''

    documents_extra = '''from app.services.notification.core import log_entity_activity, notify_entity_focal_points

'''

    digest_extra = '''from app.services.notification.core import log_entity_activity, notify_entity_focal_points

'''

    extras = {
        "assignment": assignment_extra,
        "documents": documents_extra,
        "digest": digest_extra,
    }

    domains = {
        "assignment": "assignment workflow",
        "documents": "document upload",
        "digest": "admin and user onboarding",
    }

    extracted_line_nums: set[int] = set()
    for domain, segs in ranges.items():
        body: list[str] = []
        for start, end in segs:
            for ln in range(start, end + 1):
                extracted_line_nums.add(ln)
            body.extend(slice_lines(lines, start, end))
            if body and not body[-1].endswith("\n"):
                body[-1] += "\n"
            body.append("\n")

        content = common_header.format(domain=domains[domain])
        content += extras[domain]
        content += "".join(body)
        write_lines(NOTIFIERS_DIR / f"{domain}.py", [content])

    write_lines(
        NOTIFIERS_DIR / "__init__.py",
        [
            '"""Domain-specific notification helpers."""\n',
            "from app.services.notification.notifiers.assignment import (\n",
            "    notify_assignment_created,\n",
            "    notify_assignment_submitted,\n",
            "    notify_assignment_sent_for_review,\n",
            "    notify_assignment_returned_for_revision,\n",
            "    notify_assignment_approved,\n",
            "    notify_assignment_reopened,\n",
            "    notify_self_report_created,\n",
            "    notify_form_data_updated,\n",
            ")\n",
            "from app.services.notification.notifiers.documents import (\n",
            "    notify_document_uploaded,\n",
            "    notify_standalone_document_uploaded,\n",
            ")\n",
            "from app.services.notification.notifiers.digest import (\n",
            "    notify_user_added_to_country,\n",
            "    notify_public_submission_received,\n",
            ")\n",
            "\n",
            "__all__ = [\n",
            "    'notify_assignment_created',\n",
            "    'notify_assignment_submitted',\n",
            "    'notify_assignment_sent_for_review',\n",
            "    'notify_assignment_returned_for_revision',\n",
            "    'notify_assignment_approved',\n",
            "    'notify_assignment_reopened',\n",
            "    'notify_self_report_created',\n",
            "    'notify_form_data_updated',\n",
            "    'notify_document_uploaded',\n",
            "    'notify_standalone_document_uploaded',\n",
            "    'notify_user_added_to_country',\n",
            "    'notify_public_submission_received',\n",
            "]\n",
        ],
    )

    # Remove extracted blocks from core.py (keep notify_entity_focal_points)
    new_core: list[str] = []
    skip_until = 0
    for idx, line in enumerate(lines, start=1):
        if idx <= skip_until:
            continue
        if idx == 920 and line.strip() == "# Convenience functions for common notification scenarios":
            # Skip through notify_form_data_updated (1991), keep capture_field_changes
            skip_until = 1991
            continue
        new_core.append(line)

    reexports = '''
# ---------------------------------------------------------------------------
# Re-exports from notifier modules (preserve import paths)
# ---------------------------------------------------------------------------
from app.services.notification.notifiers.assignment import (
    notify_assignment_created,
    notify_assignment_submitted,
    notify_assignment_sent_for_review,
    notify_assignment_returned_for_revision,
    notify_assignment_approved,
    notify_assignment_reopened,
    notify_self_report_created,
    notify_form_data_updated,
)
from app.services.notification.notifiers.documents import (
    notify_document_uploaded,
    notify_standalone_document_uploaded,
)
from app.services.notification.notifiers.digest import (
    notify_user_added_to_country,
    notify_public_submission_received,
)

'''
    # Insert re-exports before validators re-exports block
    out: list[str] = []
    inserted = False
    for line in new_core:
        if not inserted and line.startswith("from app.services.notification.validators import"):
            out.append(reexports)
            inserted = True
        out.append(line)
    if not inserted:
        out.append(reexports)

    write_lines(NOTIF_CORE, out)
    print(f"Notification split: extracted {len(extracted_line_nums)} lines into notifiers/")


def split_excel_service() -> None:
    lines = read_lines(EXCEL_SERVICE)

    # Locate class body boundaries (1-based line numbers from AST)
    class_start = 41
    first_method = 196

    header = slice_lines(lines, 1, 40)  # imports through blank line before class

    # Constants: lines 44-549 (inside class, before first matrix-specific attr at 601)
    constants = slice_lines(lines, 44, 549)

    shared_methods = [
        (196, 533),
        (554, 599),
        (1051, 1163),
        (3723, 3738),
    ]
    matrix_methods = [
        (601, 611),  # _MATRIX_CONFIG_KEYS + logger attr
        (614, 1048),
    ]
    export_methods = [(1167, 2005)]
    import_methods = [(2008, 3720)]

    def build_class(name: str, bases: str, parts: list[tuple[int, int]]) -> str:
        body: list[str] = []
        for start, end in parts:
            body.extend(slice_lines(lines, start, end))
            body.append("\n")
        return (
            f'"""Template Excel service — {name.split("TemplateExcel")[-1].lower()} mixin."""\n\n'
            + "".join(header)
            + f"\nclass {name}({bases}):\n"
            + '    """Mixin for TemplateExcelService."""\n\n'
            + "".join(constants if name == "TemplateExcelBase" else [])
            + "".join(body)
        )

    base_content = build_class("TemplateExcelBase", "object", shared_methods)
    write_lines(TEMPLATES_DIR / "excel_base.py", [base_content])

    matrix_content = build_class(
        "TemplateExcelMatrixMixin", "TemplateExcelBase", matrix_methods
    )
    write_lines(TEMPLATES_DIR / "matrix_import.py", [matrix_content])

    export_content = build_class(
        "TemplateExcelExportMixin", "TemplateExcelBase", export_methods
    )
    write_lines(TEMPLATES_DIR / "excel_export.py", [export_content])

    import_content = build_class(
        "TemplateExcelImportMixin", "TemplateExcelMatrixMixin", import_methods
    )
    write_lines(TEMPLATES_DIR / "excel_import.py", [import_content])

    orchestrator = '''# ========== Template Excel Import/Export Service ==========
"""
Thin orchestrator for template Excel export/import.

Implementation is split across:
- excel_base.py — shared constants and helpers
- excel_export.py — export paths
- excel_import.py — import paths
- matrix_import.py — matrix-specific import logic
"""

from app.services.templates.excel_base import TemplateExcelBase
from app.services.templates.excel_export import TemplateExcelExportMixin
from app.services.templates.excel_import import TemplateExcelImportMixin
from app.services.templates.matrix_import import TemplateExcelMatrixMixin


class TemplateExcelService(TemplateExcelImportMixin, TemplateExcelExportMixin):
    """Service for template Excel export/import operations."""

    pass


__all__ = ["TemplateExcelService"]
'''
    write_lines(EXCEL_SERVICE, [orchestrator])
    print("Excel split: created excel_base, excel_export, excel_import, matrix_import")


if __name__ == "__main__":
    split_notification_notifiers()
    split_excel_service()
    print("Done.")
