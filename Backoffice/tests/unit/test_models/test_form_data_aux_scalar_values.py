from types import SimpleNamespace

import pytest

from app.models.forms import FormData


def test_imputed_value_is_stored_as_scalar_text_with_numeric_cache():
    entry = SimpleNamespace(imputed_value=None, imputed_numeric_value=None)

    FormData.sync_imputed_numeric_value(entry, 1200)

    assert entry.imputed_value == "1200"
    assert entry.imputed_numeric_value == 1200.0


def test_imputed_multi_choice_list_is_stored_like_value_json_string():
    entry = SimpleNamespace(imputed_value=None, imputed_numeric_value=None)

    FormData.sync_imputed_numeric_value(entry, ["A", "B"])

    assert entry.imputed_value == '["A", "B"]'
    assert entry.imputed_numeric_value is None


def test_structured_imputed_scalar_payload_is_rejected():
    entry = SimpleNamespace(imputed_value=None, imputed_numeric_value=None)

    with pytest.raises(ValueError, match="Structured form payloads"):
        FormData.sync_imputed_numeric_value(entry, {"mode": "total", "values": {"direct": 1}})
