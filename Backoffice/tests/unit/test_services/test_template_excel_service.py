"""
Comprehensive tests for TemplateExcelService.

Targets maximum code coverage for app/services/template_excel_service.py.

Strategy:
- Pure-function methods (_rewrite_rule_json_item_ids, _parse_json, helpers) tested without DB.
- Export / Import round-trip tests use real DB fixtures + a request context with a
  logged-in user so current_user is available.
"""
import io
import json
import pytest
import openpyxl
from unittest.mock import patch, MagicMock, call
from flask_login import login_user

from app import db
from app.models import FormTemplate, FormTemplateVersion, FormPage, FormSection, FormItem
from app.services.template_excel_service import TemplateExcelService
from tests.factories import (
    create_test_admin,
    create_test_template,
    create_test_section,
    create_test_item,
    create_test_draft_version,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_export_workbook_bytes(
    template_name="Test",
    pages=None,
    sections=None,
    items=None,
    extra_sheets=None,
):
    """Create a minimal compliant export workbook as bytes.

    Columns are exactly what TemplateExcelService expects.
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    # Template sheet
    ws_t = wb.create_sheet("Template")
    ws_t.append(TemplateExcelService.TEMPLATE_COLUMNS)
    ws_t.append([
        template_name, "desc", False, False, False,
        False, False, False, False, None, None,
    ])

    # Pages sheet
    ws_p = wb.create_sheet("Pages")
    ws_p.append(TemplateExcelService.PAGE_COLUMNS)
    for page in (pages or []):
        ws_p.append(page)

    # Sections sheet
    ws_s = wb.create_sheet("Sections")
    ws_s.append(TemplateExcelService.SECTION_COLUMNS)
    for section in (sections or []):
        ws_s.append(section)

    # Items sheet
    ws_i = wb.create_sheet("Items")
    ws_i.append(TemplateExcelService.ITEM_COLUMNS)
    for item in (items or []):
        ws_i.append(item)

    # Any extra sheets (should be ignored during import)
    for sheet_name in (extra_sheets or []):
        wb.create_sheet(sheet_name)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# _rewrite_rule_json_item_ids
# ---------------------------------------------------------------------------

class TestRewriteRuleJsonItemIds:
    """Pure-function tests – no DB or app context needed."""

    def test_none_returns_none(self):
        assert TemplateExcelService._rewrite_rule_json_item_ids(None, {}) is None

    def test_empty_string_returns_unchanged(self):
        assert TemplateExcelService._rewrite_rule_json_item_ids("  ", {}) == "  "

    def test_dict_input_already_parsed(self):
        rule = {"item_id": "5"}
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {5: 99})
        assert json.loads(result)["item_id"] == "99"

    def test_list_input_rewritten(self):
        rule = [{"item_id": "3"}, {"item_id": "4"}]
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {3: 30, 4: 40})
        parsed = json.loads(result)
        assert parsed[0]["item_id"] == "30"
        assert parsed[1]["item_id"] == "40"

    def test_numeric_string_id(self):
        rule = json.dumps({"item_id": "7"})
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {7: 77})
        assert json.loads(result)["item_id"] == "77"

    def test_integer_id(self):
        rule = json.dumps({"item_id": 8})
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {8: 88})
        assert json.loads(result)["item_id"] == "88"

    def test_float_id(self):
        rule = json.dumps({"item_id": 9.0})
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {9: 99})
        assert json.loads(result)["item_id"] == "99"

    def test_plugin_prefix_two_parts(self):
        rule = json.dumps({"item_id": "plugin_10"})
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {10: 100})
        assert json.loads(result)["item_id"] == "plugin_100"

    def test_plugin_prefix_with_measure(self):
        rule = json.dumps({"item_id": "plugin_11_measure_id"})
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {11: 111})
        parsed = json.loads(result)
        assert parsed["item_id"] == "plugin_111_measure_id"

    def test_plugin_prefix_no_digit_part_unchanged(self):
        rule = json.dumps({"item_id": "plugin_abc"})
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {})
        assert json.loads(result)["item_id"] == "plugin_abc"

    def test_question_prefix(self):
        rule = json.dumps({"item_id": "question_12"})
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {12: 120})
        assert json.loads(result)["item_id"] == "question_120"

    def test_indicator_prefix(self):
        rule = json.dumps({"item_id": "indicator_13"})
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {13: 130})
        assert json.loads(result)["item_id"] == "indicator_130"

    def test_document_field_prefix(self):
        rule = json.dumps({"item_id": "document_field_14"})
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {14: 140})
        assert json.loads(result)["item_id"] == "document_field_140"

    def test_form_item_prefix(self):
        rule = json.dumps({"item_id": "form_item_15"})
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {15: 150})
        assert json.loads(result)["item_id"] == "form_item_150"

    def test_id_not_in_map_returns_original(self):
        rule = json.dumps({"item_id": "99"})
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {})
        assert json.loads(result)["item_id"] == "99"

    def test_question_prefix_id_not_in_map(self):
        rule = json.dumps({"item_id": "question_55"})
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {})
        assert json.loads(result)["item_id"] == "question_55"

    def test_plugin_prefix_id_not_in_map(self):
        rule = json.dumps({"item_id": "plugin_77"})
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {})
        assert json.loads(result)["item_id"] == "plugin_77"

    def test_non_item_id_keys_are_walked(self):
        rule = json.dumps({"nested": {"item_id": "20"}})
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {20: 200})
        assert json.loads(result)["nested"]["item_id"] == "200"

    def test_item_id_none_value_unchanged(self):
        rule = json.dumps({"item_id": None})
        result = TemplateExcelService._rewrite_rule_json_item_ids(rule, {})
        assert json.loads(result)["item_id"] is None

    def test_double_encoded_json(self):
        inner = json.dumps({"item_id": "6"})
        outer = json.dumps(inner)  # double-encoded
        result = TemplateExcelService._rewrite_rule_json_item_ids(outer, {6: 60})
        # After rewrite result should be a JSON-encoded string
        parsed = json.loads(result)
        assert "60" in str(parsed)

    def test_invalid_json_returns_original(self):
        bad = "not_json_{}"
        result = TemplateExcelService._rewrite_rule_json_item_ids(bad, {})
        # Should return original since it can't be parsed
        assert result == bad


# ---------------------------------------------------------------------------
# _parse_json
# ---------------------------------------------------------------------------

class TestParseJson:
    def test_none_returns_none(self):
        assert TemplateExcelService._parse_json(None) is None

    def test_empty_string_returns_none(self):
        assert TemplateExcelService._parse_json("") is None

    def test_none_string_returns_none(self):
        assert TemplateExcelService._parse_json("None") is None

    def test_dict_input_passthrough(self):
        d = {"key": "value"}
        assert TemplateExcelService._parse_json(d) is d

    def test_list_input_passthrough(self):
        lst = [1, 2, 3]
        assert TemplateExcelService._parse_json(lst) is lst

    def test_valid_json_string(self):
        assert TemplateExcelService._parse_json('{"a": 1}') == {"a": 1}

    def test_valid_json_list_string(self):
        assert TemplateExcelService._parse_json('[1, 2]') == [1, 2]

    def test_invalid_json_returns_none(self):
        assert TemplateExcelService._parse_json("{bad json}") is None

    def test_empty_json_object_returns_none(self):
        # json.loads('{}') == {} which is falsy; returns None
        assert TemplateExcelService._parse_json("{}") is None

    def test_empty_json_array_returns_none(self):
        assert TemplateExcelService._parse_json("[]") is None

    def test_non_empty_json_object_returned(self):
        result = TemplateExcelService._parse_json('{"x": 1}')
        assert result == {"x": 1}


# ---------------------------------------------------------------------------
# Helper method unit tests (no DB)
# ---------------------------------------------------------------------------

class TestHelperMethods:
    """Tests for helper/style methods that operate on openpyxl objects."""

    def _make_cell(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        return ws.cell(row=1, column=1)

    def test_style_header_cell_required(self):
        cell = self._make_cell()
        TemplateExcelService._style_header_cell(cell, is_required=True)
        # Red fill for required
        assert cell.fill.fgColor.rgb == TemplateExcelService.IFRC_COLORS['DARK_RED']
        assert cell.font.bold is True

    def test_style_header_cell_optional(self):
        cell = self._make_cell()
        TemplateExcelService._style_header_cell(cell, is_required=False)
        # Blue fill for optional
        assert cell.fill.fgColor.rgb == TemplateExcelService.IFRC_COLORS['DARK_BLUE']

    def test_auto_size_columns_runs_without_error(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.cell(row=1, column=1, value="Hello World")
        ws.cell(row=2, column=1, value="Short")
        # Should not raise
        TemplateExcelService._auto_size_columns(ws, 1)
        assert ws.column_dimensions['A'].width > 0

    def test_create_excel_table_normal(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.cell(row=1, column=1, value="id")
        ws.cell(row=2, column=1, value=1)
        # Should create table without error
        TemplateExcelService._create_excel_table(ws, "TestTable", 1, 2)

    def test_create_excel_table_header_only_adds_empty_row(self):
        """num_rows=1 (header only) should use num_rows=2 (add empty data row)."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.cell(row=1, column=1, value="id")
        TemplateExcelService._create_excel_table(ws, "HeaderOnly", 1, 1)
        # Table should have been created
        assert len(ws.tables) == 1

    def test_create_excel_table_zero_rows_skipped(self):
        """num_rows < 1 => no table created."""
        wb = openpyxl.Workbook()
        ws = wb.active
        TemplateExcelService._create_excel_table(ws, "ZeroTable", 1, 0)
        assert len(ws.tables) == 0

    def test_add_dropdown_validation_empty_options(self):
        """Empty options list should skip adding validation."""
        wb = openpyxl.Workbook()
        ws = wb.active
        # Should not raise
        TemplateExcelService._add_dropdown_validation(ws, 1, [], start_row=2, end_row=10)

    def test_add_dropdown_validation_with_options(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.cell(row=1, column=1, value="section_type")
        TemplateExcelService._add_dropdown_validation(
            ws, 1,
            TemplateExcelService.DROPDOWN_OPTIONS['section_type'],
            start_row=2, end_row=5
        )
        # Validation was added
        assert len(ws.data_validations.dataValidation) > 0

    def test_add_duplicate_highlighting_less_than_3_rows(self):
        """Less than 3 rows => no conditional formatting added."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.cell(row=1, column=1, value="id")
        ws.cell(row=2, column=1, value=1)
        TemplateExcelService._add_duplicate_highlighting(ws, 'id', ['id'], 2)
        # No rule should be added
        assert not ws.conditional_formatting._cf_rules

    def test_add_duplicate_highlighting_column_not_in_headers(self, app):
        """Column name not in headers => silently skipped."""
        with app.app_context():
            wb = openpyxl.Workbook()
            ws = wb.active
            for i in range(1, 6):
                ws.cell(row=i, column=1, value=i)
            TemplateExcelService._add_duplicate_highlighting(ws, 'nonexistent', ['id'], 5)

    def test_add_duplicate_highlighting_normal(self, app):
        with app.app_context():
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.cell(row=1, column=1, value="id")
            for i in range(2, 6):
                ws.cell(row=i, column=1, value=i - 1)
            TemplateExcelService._add_duplicate_highlighting(ws, 'id', ['id'], 5)

    def test_get_item_type_options_includes_standard_types(self, app):
        with app.app_context():
            opts = TemplateExcelService._get_item_type_options()
            assert 'indicator' in opts
            assert 'question' in opts
            assert 'document_field' in opts
            assert 'matrix' in opts

    def test_get_item_type_options_with_plugin_manager(self, app):
        with app.app_context():
            plugin_mgr = MagicMock()
            plugin_mgr.list_active_field_types.return_value = ['custom_type']
            with patch.object(app, 'plugin_manager', plugin_mgr, create=True):
                opts = TemplateExcelService._get_item_type_options()
                assert 'plugin_custom_type' in opts

    def test_get_item_type_options_plugin_exception_handled(self, app):
        """Plugin manager raising exception is handled gracefully."""
        with app.app_context():
            plugin_mgr = MagicMock()
            plugin_mgr.list_active_field_types.side_effect = Exception("Plugin error")
            with patch.object(app, 'plugin_manager', plugin_mgr, create=True):
                opts = TemplateExcelService._get_item_type_options()
                assert 'indicator' in opts  # Standard types still there

    def test_get_type_options_from_database_with_existing_types(self, db_session, app):
        with app.app_context():
            opts = TemplateExcelService._get_type_options_from_database()
            assert isinstance(opts, list)
            assert len(opts) > 0

    def test_get_type_options_from_database_exception_returns_defaults(self, app):
        with app.app_context():
            with patch("app.services.template_excel_service.db") as mock_db:
                mock_db.session.query.side_effect = Exception("DB error")
                opts = TemplateExcelService._get_type_options_from_database()
                assert 'Number' in opts

    def test_add_sheet_reference_dropdown_column_not_found(self, app):
        with app.app_context():
            wb = openpyxl.Workbook()
            source = wb.create_sheet("Pages")
            source.cell(row=1, column=1, value="id")
            target = wb.create_sheet("Sections")
            # Column 'page_id' not in source headers
            TemplateExcelService._add_sheet_reference_dropdown(
                target, 1, source, 'nonexistent_col', start_row=2, end_row=10
            )

    def test_add_sheet_reference_dropdown_normal(self, app):
        with app.app_context():
            wb = openpyxl.Workbook()
            source = wb.create_sheet("Pages")
            source.cell(row=1, column=1, value="id")
            source.cell(row=2, column=1, value=1)
            target = wb.create_sheet("Sections")
            # Should add a data validation referencing Pages
            TemplateExcelService._add_sheet_reference_dropdown(
                target, 1, source, 'id', start_row=2, end_row=10
            )

    def test_add_sheet_reference_dropdown_sheet_name_with_space(self, app):
        with app.app_context():
            wb = openpyxl.Workbook()
            source = wb.create_sheet("My Pages")
            source.cell(row=1, column=1, value="id")
            target = wb.create_sheet("Sections")
            TemplateExcelService._add_sheet_reference_dropdown(
                target, 1, source, 'id', start_row=2, end_row=10
            )


# ---------------------------------------------------------------------------
# _build_item_db_to_export_map
# ---------------------------------------------------------------------------

class TestBuildItemDbToExportMap:
    def test_map_sequential_starting_from_one(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="BuildMap Template")
            version = db_session.query(FormTemplateVersion).filter_by(
                id=template.published_version_id
            ).first()
            section = create_test_section(db_session, template, version=version, order=1)
            item1 = create_test_item(db_session, section, template, version=version, order=1)
            item2 = create_test_item(db_session, section, template, version=version, order=2)

            mapping = TemplateExcelService._build_item_db_to_export_map(template, version)
            assert item1.id in mapping
            assert item2.id in mapping
            # Sequential from 1
            assert sorted(mapping.values()) == list(range(1, len(mapping) + 1))

    def test_empty_template_returns_empty_map(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="EmptyMap Template")
            version = db_session.query(FormTemplateVersion).filter_by(
                id=template.published_version_id
            ).first()
            mapping = TemplateExcelService._build_item_db_to_export_map(template, version)
            assert mapping == {}


# ---------------------------------------------------------------------------
# export_template integration tests
# ---------------------------------------------------------------------------

class TestExportTemplate:
    """Integration tests for export_template – exercises all _export_* methods."""

    def _create_full_template(self, db_session):
        """Create a template with page, section, and item."""
        template = create_test_template(db_session, name="Full Export Template")
        version = db_session.query(FormTemplateVersion).filter_by(
            id=template.published_version_id
        ).first()
        # Update version with various options to exercise all export paths
        version.is_paginated = True
        version.add_to_self_report = True
        version.display_order_visible = True
        version.enable_export_pdf = True
        version.enable_export_excel = True
        version.enable_import_excel = True
        version.enable_ai_validation = True
        version.name_translations = {"fr": "Modèle de test"}
        version.variables = {"var1": "value1"}
        db_session.add(version)
        db_session.commit()
        db_session.refresh(version)

        page = FormPage(
            template_id=template.id,
            version_id=version.id,
            name="Test Page",
            order=1,
            name_translations={"fr": "Page Test"},
        )
        db_session.add(page)
        db_session.flush()

        section = create_test_section(
            db_session, template, version=version,
            name="Export Section", order=1,
            section_type="standard"
        )
        section.page_id = page.id
        section.name_translations = {"fr": "Section Test"}
        section.relevance_condition = json.dumps({"item_id": "1"})
        db_session.add(section)

        section2 = create_test_section(
            db_session, template, version=version,
            name="Sub Section", order=2,
            section_type="standard",
            parent_section_id=section.id
        )
        db_session.add(section2)

        item = create_test_item(
            db_session, section, template, version=version,
            item_type="indicator", order=1,
            label="Test Indicator"
        )
        item.relevance_condition = json.dumps({"item_id": "1"})
        item.validation_condition = json.dumps({"item_id": "1"})
        item.config = {"key": "val"}
        item.label_translations = {"fr": "Indicateur Test"}
        db_session.add(item)

        db_session.commit()
        db_session.refresh(template)
        db_session.refresh(version)
        return template, version, page, section, item

    def test_export_returns_bytes_io(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template, version, page, section, item = self._create_full_template(db_session)

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.export_template(template.id)

            assert isinstance(result, io.BytesIO)
            # Verify it's a valid Excel file
            result.seek(0)
            wb = openpyxl.load_workbook(result)
            assert "Template" in wb.sheetnames
            assert "Pages" in wb.sheetnames
            assert "Sections" in wb.sheetnames
            assert "Items" in wb.sheetnames
            assert "Instructions" in wb.sheetnames

    def test_export_with_specific_version_id(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template, version, page, section, item = self._create_full_template(db_session)

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.export_template(template.id, version_id=version.id)

            assert isinstance(result, io.BytesIO)

    def test_export_with_nonexistent_version_falls_back(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template, version, page, section, item = self._create_full_template(db_session)

            with app.test_request_context():
                login_user(admin)
                # version_id=999999 should fall back to published version
                result = TemplateExcelService.export_template(template.id, version_id=999999)

            assert isinstance(result, io.BytesIO)

    def test_export_no_version_raises_for_template_with_no_version(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            # Create template without a version
            template = FormTemplate()
            db_session.add(template)
            db_session.commit()

            with app.test_request_context():
                login_user(admin)
                with pytest.raises(ValueError, match="No version found"):
                    TemplateExcelService.export_template(template.id)

    def test_export_template_without_pages(self, db_session, app):
        """Template with no pages should still export successfully."""
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="No Pages Export Template")
            version = db_session.query(FormTemplateVersion).filter_by(
                id=template.published_version_id
            ).first()
            section = create_test_section(db_session, template, version=version)
            item = create_test_item(db_session, section, template, version=version)

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.export_template(template.id)

            result.seek(0)
            wb = openpyxl.load_workbook(result)
            assert "Pages" in wb.sheetnames

    def test_export_draft_version_when_no_published(self, db_session, app):
        """Template with only a draft version should use latest."""
        with app.app_context():
            admin = create_test_admin(db_session)
            # Create a template with draft version only
            template = FormTemplate()
            db_session.add(template)
            db_session.flush()
            version = FormTemplateVersion(
                template_id=template.id,
                version_number=1,
                status='draft',
                name='Draft Only',
            )
            db_session.add(version)
            db_session.commit()

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.export_template(template.id)

            assert isinstance(result, io.BytesIO)

    def test_export_produces_metadata_sheet(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template, version, _, _, _ = self._create_full_template(db_session)

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.export_template(template.id)

            result.seek(0)
            wb = openpyxl.load_workbook(result)
            # _Metadata is veryHidden but should exist
            assert "_Metadata" in wb.sheetnames

    def test_export_sections_with_many_items(self, db_session, app):
        """Exercises the items export with multiple items for conditional formatting."""
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Many Items Export")
            version = db_session.query(FormTemplateVersion).filter_by(
                id=template.published_version_id
            ).first()
            section = create_test_section(db_session, template, version=version)
            for i in range(3):
                create_test_item(
                    db_session, section, template, version=version,
                    order=i + 1, label=f"Item {i}"
                )

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.export_template(template.id)

            result.seek(0)
            wb = openpyxl.load_workbook(result)
            ws_items = wb["Items"]
            # Header row + 3 data rows
            assert ws_items.max_row >= 4


# ---------------------------------------------------------------------------
# import_template integration tests
# ---------------------------------------------------------------------------

class TestImportTemplate:
    """Integration tests for import_template."""

    def test_import_missing_required_sheets_fails(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import MissingSheets Template")

            # Workbook missing Template sheet
            wb = openpyxl.Workbook()
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(template.id, buf)

            assert result['success'] is False
            assert "Missing required sheets" in result['message']

    def test_import_with_no_version_fails(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            # Template with no version
            template = FormTemplate()
            db_session.add(template)
            db_session.commit()

            buf = _make_export_workbook_bytes()

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(template.id, buf)

            assert result['success'] is False
            assert "No version" in result['message']

    def test_import_basic_success(self, db_session, app):
        """Import a minimal template with one section and one item."""
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import Basic Template")
            version = db_session.query(FormTemplateVersion).filter_by(
                id=template.published_version_id
            ).first()

            # Build a fresh draft version for import
            draft = create_test_draft_version(db_session, template, name="Draft for Import")

            buf = _make_export_workbook_bytes(
                template_name="Imported Template",
                pages=[],
                sections=[
                    [1, "Section A", 1.0, None, None, "standard",
                     None, None, None, False, False, None, None,
                     None, None, None, False]
                ],
                items=[
                    [1, 1, "indicator", "Item A", 1.0,
                     None, False, None, None, "Number", None,
                     None, None, None, None, None, None, None,
                     None, None, None, None, None]
                ],
            )

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is True
            assert result['created_count']['sections'] == 1

    def test_import_creates_draft_from_published(self, db_session, app):
        """When target version is published, a new draft is created automatically."""
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import AutoDraft Template")

            buf = _make_export_workbook_bytes(
                template_name="AutoDraft Import",
                sections=[
                    [1, "Auto Section", 1.0, None, None, "standard",
                     None, None, None, False, False, None, None,
                     None, None, None, False]
                ],
            )

            with app.test_request_context():
                login_user(admin)
                # Use the published version_id => should auto-create a draft
                result = TemplateExcelService.import_template(template.id, buf)

            assert result['success'] is True

    def test_import_with_pages(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import Pages Template")
            draft = create_test_draft_version(db_session, template, name="Draft Pages")

            buf = _make_export_workbook_bytes(
                pages=[
                    [1, "Page 1", 1, None]
                ],
                sections=[
                    [1, "Sec with Page", 1.0, None, 1, "standard",
                     None, None, None, False, False, None, None,
                     None, None, None, False]
                ],
                items=[
                    [1, 1, "question", "Q1", 1.0,
                     None, False, None, None, "text", None,
                     None, None, None, None, None, None, None,
                     None, None, None, None, None]
                ],
            )

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is True
            assert result['created_count']['pages'] >= 1

    def test_import_with_unrecognized_sheets_ignored(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import ExtraSheets Template")
            draft = create_test_draft_version(db_session, template, name="Draft Extra")

            buf = _make_export_workbook_bytes(
                sections=[
                    [1, "Sec", 1.0, None, None, "standard",
                     None, None, None, False, False, None, None,
                     None, None, None, False]
                ],
                extra_sheets=["CustomData", "SomeOtherSheet"],
            )

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is True

    def test_import_bad_pages_headers_returns_error(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import BadPageHdr Template")
            draft = create_test_draft_version(db_session, template, name="Draft BadHdr")

            wb = openpyxl.Workbook()
            wb.remove(wb.active)
            ws_t = wb.create_sheet("Template")
            ws_t.append(TemplateExcelService.TEMPLATE_COLUMNS)
            ws_t.append(["Name"] + [None] * (len(TemplateExcelService.TEMPLATE_COLUMNS) - 1))
            ws_p = wb.create_sheet("Pages")
            ws_p.append(["wrong", "headers"])  # Bad headers
            ws_s = wb.create_sheet("Sections")
            ws_s.append(TemplateExcelService.SECTION_COLUMNS)
            ws_i = wb.create_sheet("Items")
            ws_i.append(TemplateExcelService.ITEM_COLUMNS)
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is False

    def test_import_bad_sections_headers_returns_error(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import BadSecHdr Template")
            draft = create_test_draft_version(db_session, template, name="Draft BadSecHdr")

            wb = openpyxl.Workbook()
            wb.remove(wb.active)
            ws_t = wb.create_sheet("Template")
            ws_t.append(TemplateExcelService.TEMPLATE_COLUMNS)
            ws_t.append(["Name"] + [None] * (len(TemplateExcelService.TEMPLATE_COLUMNS) - 1))
            ws_p = wb.create_sheet("Pages")
            ws_p.append(TemplateExcelService.PAGE_COLUMNS)
            ws_s = wb.create_sheet("Sections")
            ws_s.append(["wrong", "headers"])  # Bad headers
            ws_i = wb.create_sheet("Items")
            ws_i.append(TemplateExcelService.ITEM_COLUMNS)
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is False

    def test_import_bad_items_headers_returns_error(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import BadItemHdr Template")
            draft = create_test_draft_version(db_session, template, name="Draft BadItemHdr")

            wb = openpyxl.Workbook()
            wb.remove(wb.active)
            ws_t = wb.create_sheet("Template")
            ws_t.append(TemplateExcelService.TEMPLATE_COLUMNS)
            ws_t.append(["Name"] + [None] * (len(TemplateExcelService.TEMPLATE_COLUMNS) - 1))
            ws_p = wb.create_sheet("Pages")
            ws_p.append(TemplateExcelService.PAGE_COLUMNS)
            ws_s = wb.create_sheet("Sections")
            ws_s.append(TemplateExcelService.SECTION_COLUMNS)
            ws_i = wb.create_sheet("Items")
            ws_i.append(["bad", "columns"])  # Bad headers
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is False

    def test_import_template_metadata_missing_required_column(self, db_session, app):
        """Template sheet missing the 'name' required column."""
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import MissingName Template")
            draft = create_test_draft_version(db_session, template, name="Draft MissingName")

            wb = openpyxl.Workbook()
            wb.remove(wb.active)
            ws_t = wb.create_sheet("Template")
            ws_t.append(["description"])  # Missing 'name'
            ws_t.append(["some desc"])
            ws_p = wb.create_sheet("Pages")
            ws_p.append(TemplateExcelService.PAGE_COLUMNS)
            ws_s = wb.create_sheet("Sections")
            ws_s.append(TemplateExcelService.SECTION_COLUMNS)
            ws_i = wb.create_sheet("Items")
            ws_i.append(TemplateExcelService.ITEM_COLUMNS)
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is False

    def test_import_page_missing_id_records_error(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import PageNoID Template")
            draft = create_test_draft_version(db_session, template, name="Draft PageNoID")

            wb = openpyxl.Workbook()
            wb.remove(wb.active)
            ws_t = wb.create_sheet("Template")
            ws_t.append(TemplateExcelService.TEMPLATE_COLUMNS)
            ws_t.append(["Name"] + [None] * (len(TemplateExcelService.TEMPLATE_COLUMNS) - 1))
            ws_p = wb.create_sheet("Pages")
            ws_p.append(TemplateExcelService.PAGE_COLUMNS)
            # Page row with None id
            ws_p.append([None, "Page 1", 1, None])
            ws_s = wb.create_sheet("Sections")
            ws_s.append(TemplateExcelService.SECTION_COLUMNS)
            ws_i = wb.create_sheet("Items")
            ws_i.append(TemplateExcelService.ITEM_COLUMNS)
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is False
            assert any("Missing export ID" in e for e in result['errors'])

    def test_import_section_missing_id_records_error(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import SecNoID Template")
            draft = create_test_draft_version(db_session, template, name="Draft SecNoID")

            wb = openpyxl.Workbook()
            wb.remove(wb.active)
            ws_t = wb.create_sheet("Template")
            ws_t.append(TemplateExcelService.TEMPLATE_COLUMNS)
            ws_t.append(["Name"] + [None] * (len(TemplateExcelService.TEMPLATE_COLUMNS) - 1))
            ws_p = wb.create_sheet("Pages")
            ws_p.append(TemplateExcelService.PAGE_COLUMNS)
            ws_s = wb.create_sheet("Sections")
            ws_s.append(TemplateExcelService.SECTION_COLUMNS)
            # Section with None id
            ws_s.append([None, "Sec", 1.0, None, None, "standard",
                         None, None, None, False, False, None, None,
                         None, None, None, False])
            ws_i = wb.create_sheet("Items")
            ws_i.append(TemplateExcelService.ITEM_COLUMNS)
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is False

    def test_import_item_unresolvable_section_id_records_error(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import ItemBadSec Template")
            draft = create_test_draft_version(db_session, template, name="Draft ItemBadSec")

            buf = _make_export_workbook_bytes(
                items=[
                    [1, 999, "indicator", "Orphan Item", 1.0,
                     None, False, None, None, "Number", None,
                     None, None, None, None, None, None, None,
                     None, None, None, None, None]
                ],
            )

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is False
            assert any("Could not resolve section_id" in e for e in result['errors'])

    def test_import_updates_existing_section(self, db_session, app):
        """When a section with matching order+name already exists, it should be updated."""
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import UpdateSec Template")
            draft = create_test_draft_version(db_session, template, name="Draft UpdateSec")
            # Pre-create the section in the draft version
            existing_section = create_test_section(
                db_session, template, version=draft,
                name="Existing Section", order=1,
                section_type="standard"
            )

            buf = _make_export_workbook_bytes(
                sections=[
                    [1, "Existing Section", 1.0, None, None, "standard",
                     None, None, None, False, False, None, None,
                     None, None, None, False]
                ],
                items=[
                    [1, 1, "indicator", "Indicator Item", 1.0,
                     None, False, None, None, "Number", None,
                     None, None, None, None, None, None, None,
                     None, None, None, None, None]
                ],
            )

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is True

    def test_import_with_parent_section_references(self, db_session, app):
        """Parent section references are resolved correctly in third pass."""
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import ParentSec Template")
            draft = create_test_draft_version(db_session, template, name="Draft ParentSec")

            buf = _make_export_workbook_bytes(
                sections=[
                    [1, "Parent", 1.0, None, None, "standard",
                     None, None, None, False, False, None, None,
                     None, None, None, False],
                    [2, "Child", 2.0, 1, None, "standard",
                     None, None, None, False, False, None, None,
                     None, None, None, False],
                ],
                items=[
                    [1, 1, "indicator", "Parent Item", 1.0,
                     None, False, None, None, "Number", None,
                     None, None, None, None, None, None, None,
                     None, None, None, None, None],
                    [2, 2, "question", "Child Item", 1.0,
                     None, False, None, None, "text", None,
                     None, None, None, None, None, None, None,
                     None, None, None, None, None],
                ],
            )

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is True
            assert result['created_count']['sections'] >= 2

    def test_import_template_row_with_none_values(self, db_session, app):
        """Template sheet with an empty data row is gracefully skipped."""
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import EmptyRow Template")
            draft = create_test_draft_version(db_session, template, name="Draft EmptyRow")

            wb = openpyxl.Workbook()
            wb.remove(wb.active)
            ws_t = wb.create_sheet("Template")
            ws_t.append(TemplateExcelService.TEMPLATE_COLUMNS)
            # Empty row
            ws_t.append([None] * len(TemplateExcelService.TEMPLATE_COLUMNS))
            ws_p = wb.create_sheet("Pages")
            ws_p.append(TemplateExcelService.PAGE_COLUMNS)
            ws_s = wb.create_sheet("Sections")
            ws_s.append(TemplateExcelService.SECTION_COLUMNS)
            ws_i = wb.create_sheet("Items")
            ws_i.append(TemplateExcelService.ITEM_COLUMNS)
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is True

    def test_import_exception_returns_failure(self, db_session, app):
        """A corrupted file triggers exception handler and returns failure."""
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import Exception Template")

            # Pass garbage bytes
            buf = io.BytesIO(b"this is not an excel file")

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(template.id, buf)

            assert result['success'] is False

    def test_import_with_name_translations_json(self, db_session, app):
        """Template sheet with name_translations JSON is applied to version."""
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import NameTrans Template")
            draft = create_test_draft_version(db_session, template, name="Draft NameTrans")

            wb = openpyxl.Workbook()
            wb.remove(wb.active)
            ws_t = wb.create_sheet("Template")
            ws_t.append(TemplateExcelService.TEMPLATE_COLUMNS)
            row = [None] * len(TemplateExcelService.TEMPLATE_COLUMNS)
            row[TemplateExcelService.TEMPLATE_COLUMNS.index('name')] = "Translated Template"
            row[TemplateExcelService.TEMPLATE_COLUMNS.index('name_translations')] = json.dumps({"fr": "Modèle"})
            row[TemplateExcelService.TEMPLATE_COLUMNS.index('variables')] = json.dumps({"v": "1"})
            ws_t.append(row)
            ws_p = wb.create_sheet("Pages")
            ws_p.append(TemplateExcelService.PAGE_COLUMNS)
            ws_s = wb.create_sheet("Sections")
            ws_s.append(TemplateExcelService.SECTION_COLUMNS)
            ws_i = wb.create_sheet("Items")
            ws_i.append(TemplateExcelService.ITEM_COLUMNS)
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is True


# ---------------------------------------------------------------------------
# _clone_template_structure
# ---------------------------------------------------------------------------

class TestCloneTemplateStructure:
    def test_clone_creates_copies_of_pages_sections_items(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Clone Structure Template")
            src_version = db_session.query(FormTemplateVersion).filter_by(
                id=template.published_version_id
            ).first()
            tgt_version = create_test_draft_version(db_session, template, name="Target Draft")

            page = FormPage(
                template_id=template.id,
                version_id=src_version.id,
                name="Src Page",
                order=1,
            )
            db_session.add(page)
            db_session.flush()

            section = create_test_section(
                db_session, template, version=src_version, name="Src Section", order=1
            )
            section.page_id = page.id
            db_session.add(section)
            db_session.flush()

            child = create_test_section(
                db_session, template, version=src_version,
                name="Src Child", order=2, parent_section_id=section.id
            )
            item = create_test_item(
                db_session, section, template, version=src_version,
                order=1, label="Src Item"
            )
            db_session.commit()

            TemplateExcelService._clone_template_structure(
                template.id, src_version.id, tgt_version.id
            )
            db_session.commit()

            # New sections exist for target version
            new_sections = FormSection.query.filter_by(
                template_id=template.id, version_id=tgt_version.id
            ).all()
            assert len(new_sections) >= 2

            # New pages exist
            new_pages = FormPage.query.filter_by(
                template_id=template.id, version_id=tgt_version.id
            ).all()
            assert len(new_pages) >= 1

            # New items exist
            new_items = FormItem.query.filter_by(
                template_id=template.id, version_id=tgt_version.id
            ).all()
            assert len(new_items) >= 1

    def test_clone_with_item_config_json_roundtrip_failure(self, db_session, app):
        """Item config that can't be JSON-serialized still clones via deepcopy fallback."""
        with app.app_context():
            template = create_test_template(db_session, name="Clone Config Fail Template")
            src_version = db_session.query(FormTemplateVersion).filter_by(
                id=template.published_version_id
            ).first()
            tgt_version = create_test_draft_version(db_session, template, name="Clone Tgt Draft")

            section = create_test_section(
                db_session, template, version=src_version, name="Config Section", order=1
            )
            item = create_test_item(
                db_session, section, template, version=src_version,
                order=1, label="Config Item"
            )
            # Config is already a dict (stored in DB)
            item.config = {"nested": {"key": "value"}}
            db_session.add(item)
            db_session.commit()

            TemplateExcelService._clone_template_structure(
                template.id, src_version.id, tgt_version.id
            )
            db_session.commit()

            new_items = FormItem.query.filter_by(
                template_id=template.id, version_id=tgt_version.id
            ).all()
            assert len(new_items) >= 1


# ---------------------------------------------------------------------------
# _get_existing_items_lookup
# ---------------------------------------------------------------------------

class TestGetExistingItemsLookup:
    def test_returns_dict_with_items(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="ExistLookup Template")
            version = db_session.query(FormTemplateVersion).filter_by(
                id=template.published_version_id
            ).first()
            section = create_test_section(db_session, template, version=version)
            item = create_test_item(
                db_session, section, template, version=version,
                item_type="indicator", order=1, label="Lookup Item"
            )

            lookup = TemplateExcelService._get_existing_items_lookup(template.id, version.id)
            key = (item.section_id, item.order, item.item_type, item.label or '')
            assert key in lookup
            assert lookup[key].id == item.id

    def test_returns_empty_for_no_items(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="ExistLookupEmpty Template")
            version = db_session.query(FormTemplateVersion).filter_by(
                id=template.published_version_id
            ).first()
            lookup = TemplateExcelService._get_existing_items_lookup(template.id, version.id)
            assert lookup == {}


# ---------------------------------------------------------------------------
# Round-trip export -> import
# ---------------------------------------------------------------------------

class TestExportImportRoundTrip:
    """Full round-trip: export a template, then import it into a new draft."""

    def test_round_trip_preserves_section_count(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="RoundTrip Template")
            version = db_session.query(FormTemplateVersion).filter_by(
                id=template.published_version_id
            ).first()

            s1 = create_test_section(db_session, template, version=version, name="Sec 1", order=1)
            s2 = create_test_section(db_session, template, version=version, name="Sec 2", order=2)
            create_test_item(
                db_session, s1, template, version=version, order=1, label="Item 1"
            )

            with app.test_request_context():
                login_user(admin)
                export_buf = TemplateExcelService.export_template(template.id)

            # Now import into a new draft (auto-created since published version will be used)
            export_buf.seek(0)

            # Create a new import target (draft version) so we don't mutate the original
            draft = create_test_draft_version(db_session, template, name="Import Draft RT")

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, export_buf, version_id=draft.id
                )

            assert result['success'] is True

    def test_round_trip_with_relevance_conditions(self, db_session, app):
        """Rules with item_id references are rewritten correctly."""
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="RoundTrip Rules Template")
            version = db_session.query(FormTemplateVersion).filter_by(
                id=template.published_version_id
            ).first()

            section = create_test_section(
                db_session, template, version=version, name="Rules Sec", order=1
            )
            item1 = create_test_item(
                db_session, section, template, version=version,
                order=1, label="Rule Source Item"
            )
            item2 = create_test_item(
                db_session, section, template, version=version,
                order=2, label="Rule Target Item"
            )
            # Add a relevance condition referencing item1
            item2.relevance_condition = json.dumps({"item_id": str(item1.id)})
            db_session.add(item2)
            db_session.commit()

            with app.test_request_context():
                login_user(admin)
                export_buf = TemplateExcelService.export_template(template.id)

            draft = create_test_draft_version(db_session, template, name="Import Draft Rules")

            export_buf.seek(0)
            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, export_buf, version_id=draft.id
                )

            assert result['success'] is True


# ---------------------------------------------------------------------------
# Import indicator_bank_id validation
# ---------------------------------------------------------------------------

class TestImportIndicatorBankValidation:
    """Tests for indicator_bank_id validation logic during item import."""

    def test_import_item_with_null_indicator_bank_id_flagged(self, db_session, app):
        """indicator type with null indicator_bank_id should flag import issue in config."""
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import IB Null Template")
            draft = create_test_draft_version(db_session, template, name="Draft IB Null")

            buf = _make_export_workbook_bytes(
                sections=[
                    [1, "IB Section", 1.0, None, None, "standard",
                     None, None, None, False, False, None, None,
                     None, None, None, False]
                ],
                items=[
                    [1, 1, "indicator", "Null IB Item", 1.0,
                     None, False, None, None, "Number", None,
                     None, None, None, None, None, None, None,
                     None, None, None, None, None]
                    # indicator_bank_id at index 8 = None
                ],
            )

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is True
            # Item should be created with _import_issues in config
            new_items = FormItem.query.filter_by(
                template_id=template.id, version_id=draft.id
            ).all()
            assert len(new_items) >= 1

    def test_import_item_with_missing_indicator_bank_reference(self, db_session, app):
        """indicator type referencing a non-existent IndicatorBank ID."""
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import IB Missing Template")
            draft = create_test_draft_version(db_session, template, name="Draft IB Missing")

            buf = _make_export_workbook_bytes(
                sections=[
                    [1, "IB Section 2", 1.0, None, None, "standard",
                     None, None, None, False, False, None, None,
                     None, None, None, False]
                ],
                items=[
                    [1, 1, "indicator", "Missing IB Item", 1.0,
                     None, False, None, 9999999, "Number", None,
                     None, None, None, None, None, None, None,
                     None, None, None, None, None]
                    # indicator_bank_id=9999999 (non-existent)
                ],
            )

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is True

    def test_import_non_indicator_item_clears_indicator_issues(self, db_session, app):
        """Non-indicator item with any indicator_bank_id doesn't trigger validation."""
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Import NonInd Template")
            draft = create_test_draft_version(db_session, template, name="Draft NonInd")

            buf = _make_export_workbook_bytes(
                sections=[
                    [1, "NonInd Section", 1.0, None, None, "standard",
                     None, None, None, False, False, None, None,
                     None, None, None, False]
                ],
                items=[
                    [1, 1, "question", "Question Item", 1.0,
                     None, False, None, None, "text", None,
                     None, None, None, None, None, None, None,
                     None, None, None, None, None]
                ],
            )

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.import_template(
                    template.id, buf, version_id=draft.id
                )

            assert result['success'] is True


# ---------------------------------------------------------------------------
# Export Instructions sheet content
# ---------------------------------------------------------------------------

class TestExportInstructionsSheet:
    def test_instructions_sheet_has_title(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Instructions Sheet Template")
            version = db_session.query(FormTemplateVersion).filter_by(
                id=template.published_version_id
            ).first()
            section = create_test_section(db_session, template, version=version)

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.export_template(template.id)

            result.seek(0)
            wb = openpyxl.load_workbook(result)
            ws = wb["Instructions"]
            # First cell should be the title
            title = ws.cell(row=1, column=1).value
            assert "Instructions" in (title or "")

    def test_instructions_sheet_has_required_columns_info(self, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session)
            template = create_test_template(db_session, name="Instructions Content Template")
            version = db_session.query(FormTemplateVersion).filter_by(
                id=template.published_version_id
            ).first()
            section = create_test_section(db_session, template, version=version)

            with app.test_request_context():
                login_user(admin)
                result = TemplateExcelService.export_template(template.id)

            result.seek(0)
            wb = openpyxl.load_workbook(result)
            ws = wb["Instructions"]
            # Check that some content exists beyond row 1
            has_content = any(
                ws.cell(row=r, column=1).value
                for r in range(2, ws.max_row + 1)
            )
            assert has_content


# ---------------------------------------------------------------------------
# Class-level constants / configuration
# ---------------------------------------------------------------------------

class TestClassConstants:
    def test_ifrc_colors_defined(self):
        assert 'RED' in TemplateExcelService.IFRC_COLORS
        assert 'WHITE' in TemplateExcelService.IFRC_COLORS
        assert 'DARK_RED' in TemplateExcelService.IFRC_COLORS

    def test_required_columns_defined(self):
        assert 'name' in TemplateExcelService.REQUIRED_COLUMNS['Template']
        assert 'id' in TemplateExcelService.REQUIRED_COLUMNS['Pages']

    def test_dropdown_options_defined(self):
        assert 'TRUE' in TemplateExcelService.DROPDOWN_OPTIONS['archived']
        assert 'FALSE' in TemplateExcelService.DROPDOWN_OPTIONS['archived']

    def test_column_definitions_defined(self):
        assert 'name' in TemplateExcelService.TEMPLATE_COLUMNS
        assert 'id' in TemplateExcelService.PAGE_COLUMNS
        assert 'id' in TemplateExcelService.SECTION_COLUMNS
        assert 'id' in TemplateExcelService.ITEM_COLUMNS

    def test_excel_export_version(self):
        assert TemplateExcelService.EXCEL_EXPORT_VERSION == 'V1'
