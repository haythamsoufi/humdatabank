"""Unit tests for form data processor mixins split from data_service."""
import json
from unittest.mock import MagicMock, patch

import pytest


class TestProcessorMixinDelegation:
    """Verify FormDataService delegates to processor mixins via MRO."""

    def test_mro_includes_all_processor_mixins(self):
        from app.services.forms.data_service import FormDataService
        from app.services.forms.processors import (
            DocumentProcessorMixin,
            IndicatorProcessorMixin,
            PluginProcessorMixin,
            RepeatGroupProcessorMixin,
        )

        mro_names = [c.__name__ for c in FormDataService.__mro__]
        assert PluginProcessorMixin.__name__ in mro_names
        assert IndicatorProcessorMixin.__name__ in mro_names
        assert RepeatGroupProcessorMixin.__name__ in mro_names
        assert DocumentProcessorMixin.__name__ in mro_names

    def test_indicator_methods_on_form_data_service(self):
        from app.services.forms.data_service import FormDataService

        assert FormDataService._calculate_direct_total({"male": 10, "female": 20}) == 30
        assert FormDataService._calculate_total_from_values({"total": 5, "indirect": 2}) == 5

    def test_get_english_field_name_reexport(self):
        from app.services.forms import data_service as ds_module
        from app.services.forms.data_service import FormDataService, get_english_field_name
        from app.services.forms.processors._common import get_english_field_name as common_fn

        item = MagicMock(label="Test Label")
        assert get_english_field_name(item) == "Test Label"
        assert ds_module.get_english_field_name is common_fn
        assert FormDataService._format_repeat_entry_label_text(" hello ") == "hello"


class TestIndicatorProcessorMixin:
    def test_field_supports_disaggregation_sex_option(self):
        from app.services.forms.data_service import FormDataService

        field = MagicMock()
        field.allowed_disaggregation_options = ["sex"]
        field.indirect_reach = False
        assert FormDataService._field_supports_disaggregation(field) is True

    def test_field_supports_disaggregation_total_only(self):
        from app.services.forms.data_service import FormDataService

        field = MagicMock()
        field.allowed_disaggregation_options = ["total"]
        field.indirect_reach = False
        assert FormDataService._field_supports_disaggregation(field) is False

    def test_process_repeat_disaggregation_indicator_total_mode(self):
        from app.services.forms.data_service import FormDataService

        field = MagicMock()
        field.id = 99
        field.type = "Number"
        field.field_type_for_js = "number"
        field.indirect_reach = False
        field_values = {
            "field_0_reporting_mode": "total",
            "field_0_total_value": "42",
        }
        result = FormDataService._process_repeat_disaggregation_indicator(
            field, field_values, 0
        )
        assert result == {"mode": "total", "values": {"total": 42}}


class TestRepeatGroupProcessorMixin:
    def test_format_repeat_entry_label_text(self):
        from app.services.forms.data_service import FormDataService

        assert FormDataService._format_repeat_entry_label_text(None) is None
        assert FormDataService._format_repeat_entry_label_text(["A", "B"]) == "A, B"
        assert FormDataService._format_repeat_entry_label_text("  x  ") == "x"

    def test_find_field_value_skips_availability_flags(self):
        from app.services.forms.data_service import FormDataService

        field_values = {
            "field_1_data_not_available": "1",
            "field_1": "actual",
        }
        assert FormDataService._find_field_value(field_values, 1, ["0"]) == "actual"


class TestPluginProcessorMixin:
    def test_save_plugin_field_data_none_value_is_noop(self):
        from app.services.forms.data_service import FormDataService

        plugin_field = MagicMock()
        aes = MagicMock()
        assert FormDataService._save_plugin_field_data(
            plugin_field, None, aes, []
        ) == []


class TestDocumentProcessorMixin:
    def test_process_document_upload_no_files(self, app):
        from app.services.forms.data_service import FormDataService

        document = MagicMock()
        document.id = 5
        document.label = "Doc"
        document.config = None
        aes = MagicMock()
        aes.__class__.__name__ = "AssignmentEntityStatus"
        aes.id = 1

        with app.test_request_context(method="POST", data={}):
            changes = FormDataService._process_document_upload(document, aes, [])
        assert changes == []
