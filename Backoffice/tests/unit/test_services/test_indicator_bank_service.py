import pytest

from app.services.indicator_bank_service import (
    IndicatorBankFilters,
    build_indicator_bank_query,
    serialize_indicator_list,
)
from app.utils.api_serialization import (
    format_bridge_disagg_rows,
    format_fact_form_value_row,
)
from app.models.api_key_management import (
    API_KEY_DATA_NONE,
    API_KEY_DATA_READ_ALL,
    API_KEY_DATA_READ_SCOPED,
    resolve_api_key_data_access,
)


@pytest.mark.unit
class TestApiKeyDataAccess:
    def test_null_permissions_default_read_all(self):
        mode, scope = resolve_api_key_data_access(None)
        assert mode == API_KEY_DATA_READ_ALL
        assert scope is None

    def test_read_scoped_permissions(self):
        mode, scope = resolve_api_key_data_access({
            "data": API_KEY_DATA_READ_SCOPED,
            "template_ids": [1, 2],
            "country_ids": [5],
        })
        assert mode == API_KEY_DATA_READ_SCOPED
        assert scope == {"template_ids": [1, 2], "country_ids": [5]}

    def test_none_permissions(self):
        mode, scope = resolve_api_key_data_access({"data": API_KEY_DATA_NONE})
        assert mode == API_KEY_DATA_NONE
        assert scope is None


@pytest.mark.unit
class TestStarSchemaSerialization:
    def test_format_fact_row_strips_disagg(self):
        row = format_fact_form_value_row({
            "id": 1,
            "form_item_id": 10,
            "country_id": 3,
            "template_id": 2,
            "period_name": "FY2024",
            "submission_id": 99,
            "submission_type": "assigned",
            "value": "42",
            "num_value": 42,
            "data_status": "available",
            "submitted_at": "2024-01-01T00:00:00",
            "disaggregation_data": {"mode": "total", "values": {"total": 1}},
        })
        assert "disaggregation_data" not in row
        assert row["form_item_id"] == 10

    def test_format_bridge_disagg_rows(self):
        rows = format_bridge_disagg_rows(
            1,
            {"mode": "matrix", "values": {"10_SP2": 100, "_meta": "x"}},
            source="reported",
        )
        assert len(rows) == 1
        assert rows[0]["form_data_id"] == 1
        assert rows[0]["key"] == "10_SP2"
        assert rows[0]["value"] == 100


@pytest.mark.unit
class TestIndicatorBankService:
    def test_build_indicator_bank_query_no_crash(self, app):
        with app.app_context():
            query = build_indicator_bank_query(IndicatorBankFilters(search="test"))
            assert query is not None

    def test_serialize_indicator_list_empty(self, app):
        with app.app_context():
            assert serialize_indicator_list([]) == []
