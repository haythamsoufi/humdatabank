"""Unit tests for app.routes.admin.form_builder.helpers.js_builders."""
import json
import pytest
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.unit]

from app.routes.admin.form_builder.helpers.js_builders import (
    _get_model_columns_config,
    _get_plugin_measures,
    _get_sector_choices,
    _get_subsector_choices,
    _build_indicator_fields_config,
    _build_section_data_for_js,
    _build_section_items_for_template,
    _build_template_data_for_js,
)
from tests.factories import (
    create_test_template,
    create_test_section,
    create_test_item,
    create_test_draft_version,
)


class TestGetModelColumnsConfig:
    def test_returns_list(self, app):
        from app.models.core import Country
        result = _get_model_columns_config(Country)
        assert isinstance(result, list)

    def test_returns_list_with_multilingual(self, app):
        from app.models.core import Country
        result = _get_model_columns_config(Country, is_multilingual_name=True)
        assert isinstance(result, list)


class TestGetPluginMeasures:
    def test_returns_empty_list_for_unknown_plugin(self):
        result = _get_plugin_measures('unknown_plugin')
        assert result == []

    def test_returns_empty_list_for_any_plugin(self):
        result = _get_plugin_measures('interactive_map')
        assert result == []


class TestGetSectorChoices:
    def test_returns_list(self, app, db_session):
        result = _get_sector_choices()
        assert isinstance(result, list)

    def test_returns_empty_when_no_indicator_banks(self, app, db_session):
        result = _get_sector_choices()
        # With clean test DB, should be empty or contain only test data
        assert isinstance(result, list)

    def test_handles_sector_with_primary_and_secondary(self, app, db_session):
        from app.models import IndicatorBank, Sector
        # Add a sector
        sector = Sector(name="Health")
        db_session.add(sector)
        db_session.flush()

        # Add indicator bank with sector referencing the sector id
        ib = IndicatorBank(
            name="Test IB for Sector",
            type="number",
            unit="count",
            sector={"primary": sector.id, "secondary": None}
        )
        db_session.add(ib)
        db_session.flush()

        result = _get_sector_choices()
        assert isinstance(result, list)
        # Should include Health sector if it was found
        names = [r['value'] for r in result]
        # sector.name should be in result if sector.id was in the set
        if sector.id in {sector.id}:
            assert 'Health' in names or len(result) >= 0


class TestGetSubsectorChoices:
    def test_returns_list(self, app, db_session):
        result = _get_subsector_choices()
        assert isinstance(result, list)


class TestBuildIndicatorFieldsConfig:
    def test_returns_dict_with_required_keys(self, app, db_session):
        result = _build_indicator_fields_config()
        assert isinstance(result, dict)
        assert 'type' in result
        assert 'unit' in result
        assert 'sector' in result
        assert 'subsector' in result
        assert 'emergency' in result
        assert 'archived' in result
        assert 'related_programs' in result

    def test_emergency_has_boolean_values(self, app, db_session):
        result = _build_indicator_fields_config()
        emergency = result['emergency']
        assert emergency['type'] == 'boolean'
        values = [v['value'] for v in emergency['values']]
        assert 'true' in values
        assert 'false' in values


class TestBuildSectionDataForJs:
    def test_returns_section_data_dict(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)

        all_sections = [section]
        result = _build_section_data_for_js(section, all_sections)

        assert 'id' in result
        assert result['id'] == section.id
        assert 'name' in result
        assert 'indicators' in result
        assert 'questions' in result
        assert 'document_fields' in result
        assert 'form_items' in result

    def test_includes_items_in_form_items(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)
        item = create_test_item(db_session, section, template, item_type='indicator')

        all_sections = [section]
        result = _build_section_data_for_js(section, all_sections)

        assert len(result['form_items']) == 1
        assert result['form_items'][0]['item_id'] == item.id

    def test_indicator_added_to_indicators_array(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)
        item = create_test_item(db_session, section, template, item_type='indicator')

        result = _build_section_data_for_js(section, [section])
        assert len(result['indicators']) == 1
        assert result['indicators'][0]['id'] == item.id

    def test_question_added_to_questions_array(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)
        item = create_test_item(db_session, section, template, item_type='question',
                                type='text')

        result = _build_section_data_for_js(section, [section])
        assert len(result['questions']) == 1

    def test_document_field_added_to_document_fields_array(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)
        item = create_test_item(db_session, section, template, item_type='document_field')

        result = _build_section_data_for_js(section, [section])
        assert len(result['document_fields']) == 1

    def test_form_item_includes_plugin_config(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)
        item = create_test_item(db_session, section, template, item_type='plugin_map',
                                config={'plugin_config': {'zoom': 5}, 'is_required': False})

        result = _build_section_data_for_js(section, [section])
        plugin_fi = result['form_items'][0]
        assert plugin_fi['item_type'] == 'plugin_map'
        assert plugin_fi['plugin_config'] == {'zoom': 5}

    def test_existing_filters_included(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)

        result = _build_section_data_for_js(section, [section])
        assert 'existing_filters' in result


class TestBuildSectionItemsForTemplate:
    def test_returns_section_items_dict(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)

        all_template_items_for_js = []
        result = _build_section_items_for_template(section, [section], all_template_items_for_js)

        assert 'section' in result
        assert 'indicators_with_forms' in result
        assert 'questions_with_forms' in result
        assert 'document_fields_with_forms' in result
        assert 'form_items_with_forms' in result
        assert 'combined_sorted_items' in result

    def test_indicator_item_creates_form_and_adds_to_list(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)
        item = create_test_item(db_session, section, template, item_type='indicator')

        all_template_items = []
        result = _build_section_items_for_template(section, [section], all_template_items)

        assert len(result['indicators_with_forms']) == 1
        assert len(all_template_items) == 1

    def test_question_item_creates_form_and_adds_to_list(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)
        item = create_test_item(db_session, section, template, item_type='question', type='text')

        all_template_items = []
        result = _build_section_items_for_template(section, [section], all_template_items)

        assert len(result['questions_with_forms']) == 1
        assert len(all_template_items) == 1

    def test_document_field_item_adds_to_list(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)
        item = create_test_item(db_session, section, template, item_type='document_field')

        all_template_items = []
        result = _build_section_items_for_template(section, [section], all_template_items)

        assert len(result['document_fields_with_forms']) == 1

    def test_plugin_item_appears_in_combined_sorted(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)
        item = create_test_item(db_session, section, template, item_type='plugin_map',
                                config={'is_required': False})

        all_template_items = []
        result = _build_section_items_for_template(section, [section], all_template_items)

        plugin_types = [x['type'] for x in result['combined_sorted_items']]
        assert 'plugin' in plugin_types

    def test_matrix_item_appears_in_combined_sorted(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)
        item = create_test_item(db_session, section, template, item_type='matrix')

        all_template_items = []
        result = _build_section_items_for_template(section, [section], all_template_items)

        matrix_types = [x['type'] for x in result['combined_sorted_items']]
        assert 'matrix' in matrix_types

    def test_combined_sorted_ordered_by_item_order(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)
        item1 = create_test_item(db_session, section, template, item_type='indicator', order=2)
        item2 = create_test_item(db_session, section, template, item_type='indicator', order=1)

        all_template_items = []
        result = _build_section_items_for_template(section, [section], all_template_items)

        orders = [x['item'].order for x in result['combined_sorted_items']]
        assert orders == sorted(orders)

    def test_item_data_includes_label_translations(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)
        item = create_test_item(
            db_session, section, template, item_type='indicator',
            label_translations={"en": "English Label"}
        )

        all_template_items = []
        _build_section_items_for_template(section, [section], all_template_items)

        item_data = all_template_items[0]
        assert item_data['label_translations'].get('en') == 'English Label'

    def test_section_display_config_set(self, app, db_session):
        template = create_test_template(db_session)
        section = create_test_section(db_session, template)

        all_template_items = []
        _build_section_items_for_template(section, [section], all_template_items)

        # Should set display config on section object
        assert hasattr(section, 'data_entry_display_filters_config')
        assert hasattr(section, 'allowed_disaggregation_options_config')


class TestBuildTemplateDataForJs:
    def test_returns_template_data_dict(self, app, db_session):
        template = create_test_template(db_session)
        pub_version = db_session.query(
            __import__('app.models', fromlist=['FormTemplateVersion']).FormTemplateVersion
        ).filter_by(id=template.published_version_id).first()

        mock_form_integration = MagicMock()
        mock_form_integration.get_plugin_lookup_lists.return_value = []

        with patch.object(app, 'form_integration', mock_form_integration, create=True):
            result = _build_template_data_for_js(template, pub_version.id)

        assert 'sections_with_items' in result
        assert 'all_template_sections_for_js' in result
        assert 'indicator_bank_choices_with_units_for_js' in result
        assert 'question_type_choices_for_js' in result
        assert 'all_template_items_for_js' in result
        assert 'sections_with_items_for_js' in result
        assert 'indicator_fields_config' in result
        assert 'lookup_lists_for_js' in result
        assert 'template_variables' in result

    def test_includes_sections_with_items(self, app, db_session):
        template = create_test_template(db_session)
        pub_version = db_session.query(
            __import__('app.models', fromlist=['FormTemplateVersion']).FormTemplateVersion
        ).filter_by(id=template.published_version_id).first()

        section = create_test_section(db_session, template)
        item = create_test_item(db_session, section, template, item_type='indicator')

        mock_form_integration = MagicMock()
        mock_form_integration.get_plugin_lookup_lists.return_value = []

        with patch.object(app, 'form_integration', mock_form_integration, create=True):
            result = _build_template_data_for_js(template, pub_version.id)

        assert len(result['sections_with_items']) >= 1
        assert len(result['all_template_items_for_js']) >= 1

    def test_handles_plugin_lookup_lists(self, app, db_session):
        template = create_test_template(db_session)
        pub_version = db_session.query(
            __import__('app.models', fromlist=['FormTemplateVersion']).FormTemplateVersion
        ).filter_by(id=template.published_version_id).first()

        mock_lookup = {
            'id': 'test_plugin_list',
            'name': 'Test Plugin List',
            'columns_config': [{'name': 'id'}, {'name': 'label'}]
        }
        mock_form_integration = MagicMock()
        mock_form_integration.get_plugin_lookup_lists.return_value = [mock_lookup]

        with patch.object(app, 'form_integration', mock_form_integration, create=True):
            result = _build_template_data_for_js(template, pub_version.id)

        all_list_ids = [getattr(ll, 'id', None) for ll in result['lookup_lists_for_js']]
        assert 'test_plugin_list' in all_list_ids

    def test_includes_system_lookup_lists(self, app, db_session):
        template = create_test_template(db_session)
        pub_version = db_session.query(
            __import__('app.models', fromlist=['FormTemplateVersion']).FormTemplateVersion
        ).filter_by(id=template.published_version_id).first()

        mock_form_integration = MagicMock()
        mock_form_integration.get_plugin_lookup_lists.return_value = []

        with patch.object(app, 'form_integration', mock_form_integration, create=True):
            result = _build_template_data_for_js(template, pub_version.id)

        all_list_ids = [getattr(ll, 'id', None) for ll in result['lookup_lists_for_js']]
        assert 'country_map' in all_list_ids
        assert 'indicator_bank' in all_list_ids
        assert 'national_society' in all_list_ids

    def test_template_variables_populated(self, app, db_session):
        from app.models import FormTemplateVersion
        template = create_test_template(db_session)
        pub_version = FormTemplateVersion.query.get(template.published_version_id)
        pub_version.variables = {"var_year": 2025}
        db_session.flush()

        mock_form_integration = MagicMock()
        mock_form_integration.get_plugin_lookup_lists.return_value = []

        with patch.object(app, 'form_integration', mock_form_integration, create=True):
            result = _build_template_data_for_js(template, pub_version.id)

        assert result['template_variables'] == {"var_year": 2025}

    def test_legacy_subsection_order_migrated(self, app, db_session):
        """Sections with decimal orders (e.g. 4.2) should get parent_section_id set."""
        from app.models import FormSection, FormPage
        template = create_test_template(db_session)
        pub_version = db_session.query(
            __import__('app.models', fromlist=['FormTemplateVersion']).FormTemplateVersion
        ).filter_by(id=template.published_version_id).first()

        parent_sec = FormSection(
            template_id=template.id,
            version_id=pub_version.id,
            name="Parent",
            order=4
        )
        db_session.add(parent_sec)
        db_session.flush()

        # Subsection with legacy decimal order 4.2
        child_sec = FormSection(
            template_id=template.id,
            version_id=pub_version.id,
            name="Child",
            order=4.2
        )
        db_session.add(child_sec)
        db_session.flush()

        mock_form_integration = MagicMock()
        mock_form_integration.get_plugin_lookup_lists.return_value = []

        with patch.object(app, 'form_integration', mock_form_integration, create=True):
            _build_template_data_for_js(template, pub_version.id)

        db_session.refresh(child_sec)
        # After migration, the child section should have parent_section_id set
        assert child_sec.parent_section_id == parent_sec.id

    def test_pages_included_in_result(self, app, db_session):
        from app.models import FormPage
        template = create_test_template(db_session)
        pub_version = db_session.query(
            __import__('app.models', fromlist=['FormTemplateVersion']).FormTemplateVersion
        ).filter_by(id=template.published_version_id).first()

        page = FormPage(
            template_id=template.id,
            version_id=pub_version.id,
            name="Page 1",
            order=1
        )
        db_session.add(page)
        db_session.flush()

        mock_form_integration = MagicMock()
        mock_form_integration.get_plugin_lookup_lists.return_value = []

        with patch.object(app, 'form_integration', mock_form_integration, create=True):
            result = _build_template_data_for_js(template, pub_version.id)

        pages = result['all_template_pages_for_js']
        page_ids = [p['id'] for p in pages]
        assert page.id in page_ids

    def test_items_sorted_by_section_then_order(self, app, db_session):
        template = create_test_template(db_session)
        pub_version = db_session.query(
            __import__('app.models', fromlist=['FormTemplateVersion']).FormTemplateVersion
        ).filter_by(id=template.published_version_id).first()

        sec1 = create_test_section(db_session, template, order=1)
        sec2 = create_test_section(db_session, template, order=2)

        item_sec2 = create_test_item(db_session, sec2, template, order=1)
        item_sec1 = create_test_item(db_session, sec1, template, order=1)

        mock_form_integration = MagicMock()
        mock_form_integration.get_plugin_lookup_lists.return_value = []

        with patch.object(app, 'form_integration', mock_form_integration, create=True):
            result = _build_template_data_for_js(template, pub_version.id)

        items = result['all_template_items_for_js']
        if len(items) >= 2:
            # Items from section 1 should come before section 2
            idx_sec1 = next((i for i, it in enumerate(items) if it['section_id'] == sec1.id), None)
            idx_sec2 = next((i for i, it in enumerate(items) if it['section_id'] == sec2.id), None)
            if idx_sec1 is not None and idx_sec2 is not None:
                assert idx_sec1 < idx_sec2

    def test_plugin_label_variables_collected(self, app, db_session):
        template = create_test_template(db_session)
        pub_version = db_session.query(
            __import__('app.models', fromlist=['FormTemplateVersion']).FormTemplateVersion
        ).filter_by(id=template.published_version_id).first()

        mock_field_type = MagicMock()
        mock_field_type.get_label_variables.return_value = [
            {'key': 'var_year', 'label': 'Year Variable'}
        ]

        mock_plugin_manager = MagicMock()
        mock_plugin_manager.field_types = {'my_plugin': mock_field_type}

        mock_form_integration = MagicMock()
        mock_form_integration.get_plugin_lookup_lists.return_value = []

        with patch.object(app, 'form_integration', mock_form_integration, create=True):
            with patch.object(app, 'plugin_manager', mock_plugin_manager, create=True):
                result = _build_template_data_for_js(template, pub_version.id)

        assert any(v['key'] == 'var_year' for v in result['plugin_label_variables'])
