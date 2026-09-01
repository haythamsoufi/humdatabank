"""Unit tests for form data processor mixins split from data_service."""
import base64
import json
from unittest.mock import MagicMock, patch

import pytest


class TestDecodeB64MatrixJson:
    """WAF workaround: field_value[id] may arrive as ``b64:<base64 utf-8 json>``.

    See Backoffice/docs/runbooks/incidents/waf-403-form-payload-refactor-guide.md
    (field-level b64: convention) for why this exists and its safe-failure contract.
    """

    def _b64(self, s: str) -> str:
        return 'b64:' + base64.b64encode(s.encode('utf-8')).decode('ascii')

    def test_passthrough_for_empty_value(self):
        from app.services.forms.processors._common import decode_b64_matrix_json
        assert decode_b64_matrix_json('') == ''
        assert decode_b64_matrix_json(None) is None

    def test_passthrough_for_raw_json_without_prefix(self):
        """Backwards compatibility with older cached JS / offline draft resubmits."""
        from app.services.forms.processors._common import decode_b64_matrix_json
        raw = '{"1_Total Funding": 123.12}'
        assert decode_b64_matrix_json(raw) == raw

    def test_decodes_valid_b64_prefixed_json(self):
        from app.services.forms.processors._common import decode_b64_matrix_json
        original = '{"4_EFs": 0, "4_Total Funding": 123.12}'
        assert decode_b64_matrix_json(self._b64(original)) == original

    def test_decodes_non_ascii_row_names(self):
        """Matches the encoder's unescape(encodeURIComponent(...)) + btoa() round-trip."""
        from app.services.forms.processors._common import decode_b64_matrix_json
        original = json.dumps({"Société Nationale_Funding": 5})
        assert decode_b64_matrix_json(self._b64(original)) == original

    def test_raises_matrix_json_decode_error_on_corrupted_payload(self):
        """Must raise (not silently return ''), or callers could mistake corruption
        for an intentionally-cleared field and wipe previously-saved data."""
        from app.services.forms.processors._common import decode_b64_matrix_json, MatrixJsonDecodeError
        with pytest.raises(MatrixJsonDecodeError):
            decode_b64_matrix_json('b64:not-valid-base64!!!')


class TestGetPossiblyChunkedFormValue:
    """WAF workaround: matrix-field-chunking.js may split a large field_value[id]
    across field_value[id]/__c1/__c2/... to dodge a WAF argument-length rule
    (e.g. OWASP CRS 920370 "Argument value too long") — base64 (above) helps
    against signature rules but *inflates* size, making a length rule more
    likely for large tables, not less. See "Azure App Gateway WAF Rules the
    App Should Respect" in waf-403-form-payload-refactor-guide.md.
    """

    def test_missing_field_returns_default(self):
        from app.services.forms.processors._common import get_possibly_chunked_form_value
        assert get_possibly_chunked_form_value({}, 'field_value[1]') == ''
        assert get_possibly_chunked_form_value({}, 'field_value[1]', default='fallback') == 'fallback'

    def test_unchunked_value_returned_unchanged(self):
        """No __c1 present: behaves exactly like form.get(field_name) always did."""
        from app.services.forms.processors._common import get_possibly_chunked_form_value
        form = {'field_value[1]': 'b64:aGVsbG8='}
        assert get_possibly_chunked_form_value(form, 'field_value[1]') == 'b64:aGVsbG8='

    def test_chunks_are_reassembled_in_order(self):
        from app.services.forms.processors._common import get_possibly_chunked_form_value
        form = {
            'field_value[1]': 'b64:AAAA',
            'field_value[1]__c1': 'BBBB',
            'field_value[1]__c2': 'CCCC',
        }
        assert get_possibly_chunked_form_value(form, 'field_value[1]') == 'b64:AAAABBBBCCCC'

    def test_stops_at_first_missing_chunk_index(self):
        """A gap (e.g. __c1 present, __c2 absent, __c3 present) must not be
        bridged — reassembly stops at the first missing index, matching how
        the client only ever emits a contiguous 1..N sequence."""
        from app.services.forms.processors._common import get_possibly_chunked_form_value
        form = {
            'field_value[1]': 'b64:AAAA',
            'field_value[1]__c1': 'BBBB',
            'field_value[1]__c3': 'DDDD',  # __c2 missing — must be ignored
        }
        assert get_possibly_chunked_form_value(form, 'field_value[1]') == 'b64:AAAABBBB'

    def test_does_not_touch_a_different_fields_chunks(self):
        from app.services.forms.processors._common import get_possibly_chunked_form_value
        form = {
            'field_value[1]': 'b64:AAAA',
            'field_value[2]__c1': 'unrelated',
        }
        assert get_possibly_chunked_form_value(form, 'field_value[1]') == 'b64:AAAA'

    def test_integrates_with_decode_b64_matrix_json(self):
        """End-to-end: chunk, reassemble, decode — matches what
        FormDataService._process_matrix_data does."""
        import base64
        from app.services.forms.processors._common import (
            get_possibly_chunked_form_value,
            decode_b64_matrix_json,
        )
        original = '{"1_col": 5, "2_col": 9}'
        full_b64 = 'b64:' + base64.b64encode(original.encode('utf-8')).decode('ascii')
        midpoint = len(full_b64) // 2
        form = {
            'field_value[1]': full_b64[:midpoint],
            'field_value[1]__c1': full_b64[midpoint:],
        }
        reassembled = get_possibly_chunked_form_value(form, 'field_value[1]')
        assert decode_b64_matrix_json(reassembled) == original


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
