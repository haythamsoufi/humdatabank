import pytest

from app.models import IndicatorBank
from app.models.forms import DynamicIndicatorData, FormData, RepeatGroupData, RepeatGroupInstance
from app.services.indicator_bank_service import (
    IndicatorBankFilters,
    attach_indicator_usage_cache,
    batch_data_value_counts,
    batch_template_counts,
    build_indicator_bank_query,
    serialize_indicator_list,
)
from tests.factories import (
    create_test_assignment_entity_status,
    create_test_item,
    create_test_section,
    create_test_template,
    create_test_user,
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


@pytest.mark.unit
class TestIndicatorUsageCounts:
    def _create_indicator(self, db_session, name="Usage Count Indicator"):
        ind = IndicatorBank(name=name, type="number", archived=False)
        db_session.add(ind)
        db_session.commit()
        db_session.refresh(ind)
        return ind

    def test_batch_template_counts_distinct_templates(self, db_session, app):
        with app.app_context():
            indicator = self._create_indicator(db_session)
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            version = template.published_version
            create_test_item(
                db_session,
                section,
                template,
                version=version,
                indicator_bank_id=indicator.id,
                order=1,
            )
            create_test_item(
                db_session,
                section,
                template,
                version=version,
                indicator_bank_id=indicator.id,
                order=2,
            )

            counts = batch_template_counts([indicator.id])
            assert counts[indicator.id] == 1

    def test_batch_data_value_counts_content_only(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            indicator = self._create_indicator(db_session)
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            version = template.published_version
            item = create_test_item(
                db_session,
                section,
                template,
                version=version,
                indicator_bank_id=indicator.id,
            )
            aes = create_test_assignment_entity_status(db_session, template=template)

            db_session.add(FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=item.id,
                value='42',
            ))
            db_session.add(FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=item.id,
                data_not_available=True,
            ))
            db_session.add(DynamicIndicatorData(
                assignment_entity_status_id=aes.id,
                section_id=section.id,
                indicator_bank_id=indicator.id,
                added_by_user_id=user.id,
                value='99',
            ))
            repeat_instance = RepeatGroupInstance(
                assignment_entity_status_id=aes.id,
                section_id=section.id,
                instance_number=1,
                created_by_user_id=user.id,
            )
            db_session.add(repeat_instance)
            db_session.flush()
            db_session.add(RepeatGroupData(
                repeat_instance_id=repeat_instance.id,
                form_item_id=item.id,
                prefilled_value='7',
            ))
            db_session.commit()

            counts = batch_data_value_counts([indicator.id])
            assert counts[indicator.id] == 3

    def test_attach_indicator_usage_cache_sets_properties(self, db_session, app):
        with app.app_context():
            indicator = self._create_indicator(db_session)
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            version = template.published_version
            item = create_test_item(
                db_session,
                section,
                template,
                version=version,
                indicator_bank_id=indicator.id,
            )
            aes = create_test_assignment_entity_status(db_session, template=template)
            db_session.add(FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=item.id,
                value='15',
            ))
            db_session.commit()

            attach_indicator_usage_cache([indicator])
            assert indicator.template_count == 1
            assert indicator.data_value_count == 1
            assert indicator.usage_count == 1
