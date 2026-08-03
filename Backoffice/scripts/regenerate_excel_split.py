#!/usr/bin/env python3
"""Regenerate excel split modules from the original monolith (with decorators)."""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "app/services/templates/_excel_service_original.py"
TEMPLATES_DIR = ROOT / "app/services/templates"

EXPORT_METHODS = {
    "export_template",
    "_export_template_sheet",
    "_export_pages_sheet",
    "_export_sections_sheet",
    "_export_items_sheet",
    "_export_metadata_sheet",
    "_export_instructions_sheet",
    "_create_excel_table",
    "_add_dropdown_validation",
    "_add_sheet_reference_dropdown",
    "_get_item_type_options",
    "_get_type_options_from_database",
    "_add_duplicate_highlighting",
    "_style_header_cell",
    "_auto_size_columns",
}

MATRIX_METHODS = {
    "_get_matrix_import_logger",
    "matrix_import_entry_log",
    "_matrix_import_log",
    "_scan_workbook_matrix_items",
    "_summarize_matrix_config_for_log",
    "_summarize_raw_config_cell",
    "_log_matrix_items_in_version",
    "_deep_copy_json",
    "_clean_imported_matrix_config",
    "_find_existing_item_for_import",
    "_normalize_matrix_item_config",
    "_repair_matrix_column_groups",
    "_apply_item_config_from_import",
    "_sync_matrix_item_fields_from_config",
}

IMPORT_METHODS = {
    "_count_nonempty_data_rows",
    "_validate_template_sheet_headers",
    "_validate_import_sheet_headers",
    "validate_import_file",
    "_parse_import_version_mode",
    "_resolve_target_version",
    "resolve_import_target_version_id",
    "_get_or_create_draft_for_import",
    "import_template",
    "_import_template_metadata",
    "_import_pages",
    "_build_published_stable_key_context",
    "_published_item_stable_key_fallback",
    "_resolve_import_stable_key",
    "_validate_stable_key_duplicates_in_sheet",
    "_published_items_by_stable_key",
    "_check_stable_key_identity_mismatch",
    "_import_sections",
    "_import_items",
    "_count_deletion_impact",
    "_clear_version_structure",
    "_clone_template_structure",
    "_get_existing_items_lookup",
}

BASE_ATTRS = {"_MATRIX_CONFIG_KEYS", "_MATRIX_IMPORT_LOG_PREFIX", "_matrix_import_logger"}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def slice_source(source: str, node: ast.AST) -> str:
    lines = source.splitlines(keepends=True)
    start = node.lineno
    end = getattr(node, "end_lineno", node.lineno)
    if isinstance(node, ast.FunctionDef):
        if node.decorator_list:
            start = min(d.lineno for d in node.decorator_list)
    return "".join(lines[start - 1 : end])


def module_header() -> str:
    return textwrap.dedent(
        '''\
        # ========== Template Excel Import/Export Service ==========
        from app.utils.datetime_helpers import utcnow
        """
        Service for exporting and importing form templates to/from Excel.
        """
        '''
    )


def common_imports() -> str:
    return textwrap.dedent(
        '''\
        from flask import current_app
        from flask_login import current_user
        from app import db
        from app.models import (
            FormTemplate, FormPage, FormSection, FormItem, FormTemplateVersion,
            FormData,
            RepeatGroupInstance, RepeatGroupData, DynamicIndicatorData, DynamicSectionContext,
        )
        from app.models.documents import SubmittedDocument
        from app.models.indicator_bank import IndicatorBank
        from contextlib import suppress
        from app.services.monitoring.memory import memory_tracker
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.table import Table, TableStyleInfo
        from openpyxl.worksheet.datavalidation import DataValidation
        from openpyxl.formatting.rule import FormulaRule
        import io
        import json
        import logging
        import re
        import sys
        from datetime import datetime
        from pathlib import Path
        from typing import Dict, List, Any, Optional, Tuple
        from app.utils.stable_key import generate_stable_key, is_valid_stable_key, normalize_stable_key

        '''
    )


def write_module(path: Path, doc: str, base_import: str, class_name: str, parent: str, body_parts: list[str]) -> None:
    content = f'"""{doc}"""\n\n' + module_header() + common_imports() + base_import + f"\n\nclass {class_name}({parent}):\n"
    content += '    """Mixin for TemplateExcelService."""\n\n'
    content += "".join(body_parts)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    source = read_text(ORIGINAL)
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TemplateExcelService")

    base_parts: list[str] = []
    matrix_parts: list[str] = []
    export_parts: list[str] = []
    import_parts: list[str] = []

    for item in cls.body:
        if isinstance(item, ast.FunctionDef):
            name = item.name
            chunk = slice_source(source, item)
            if not chunk.endswith("\n"):
                chunk += "\n"
            chunk += "\n"
            if name in EXPORT_METHODS:
                export_parts.append(chunk)
            elif name in MATRIX_METHODS:
                matrix_parts.append(chunk)
            elif name in IMPORT_METHODS:
                import_parts.append(chunk)
            else:
                base_parts.append(chunk)
        else:
            chunk = slice_source(source, item)
            if not chunk.endswith("\n"):
                chunk += "\n"
            chunk += "\n"
            if isinstance(item, ast.Assign):
                targets = {t.id for t in item.targets if isinstance(t, ast.Name)}
                if targets & BASE_ATTRS:
                    matrix_parts.insert(0, chunk)
                else:
                    base_parts.append(chunk)
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                if item.target.id in BASE_ATTRS:
                    matrix_parts.insert(0, chunk)
                else:
                    base_parts.append(chunk)

    write_module(
        TEMPLATES_DIR / "excel_base.py",
        "Shared constants and helpers for template Excel import/export.",
        "",
        "TemplateExcelBase",
        "object",
        base_parts,
    )
    write_module(
        TEMPLATES_DIR / "matrix_import.py",
        "Matrix-specific template Excel import logic.",
        "from app.services.templates.excel_base import TemplateExcelBase\n",
        "TemplateExcelMatrixMixin",
        "TemplateExcelBase",
        matrix_parts,
    )
    write_module(
        TEMPLATES_DIR / "excel_export.py",
        "Template Excel export paths.",
        "from app.services.templates.excel_base import TemplateExcelBase\n",
        "TemplateExcelExportMixin",
        "TemplateExcelBase",
        export_parts,
    )
    write_module(
        TEMPLATES_DIR / "excel_import.py",
        "Template Excel import paths.",
        "from app.services.templates.matrix_import import TemplateExcelMatrixMixin\n",
        "TemplateExcelImportMixin",
        "TemplateExcelMatrixMixin",
        import_parts,
    )

    orchestrator = textwrap.dedent(
        '''\
        # ========== Template Excel Import/Export Service ==========
        """
        Thin orchestrator for template Excel export/import.

        Implementation is split across excel_base, excel_export, excel_import, and matrix_import.
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
    )
    (TEMPLATES_DIR / "excel_service.py").write_text(orchestrator, encoding="utf-8")
    print("Regenerated excel modules from original monolith.")


if __name__ == "__main__":
    main()
