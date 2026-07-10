"""Unit tests for app/forms/system/indicator_bank_forms.py — targets 100% coverage."""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Module-level utilities
# ---------------------------------------------------------------------------

class TestSplitCsvTags:
    def test_empty_string(self):
        from app.forms.system.indicator_bank_forms import _split_csv_tags
        assert _split_csv_tags('') == []

    def test_none(self):
        from app.forms.system.indicator_bank_forms import _split_csv_tags
        assert _split_csv_tags(None) == []

    def test_single_tag(self):
        from app.forms.system.indicator_bank_forms import _split_csv_tags
        assert _split_csv_tags('health') == ['health']

    def test_multiple_tags(self):
        from app.forms.system.indicator_bank_forms import _split_csv_tags
        assert _split_csv_tags('health, education, water') == ['health', 'education', 'water']

    def test_strips_whitespace(self):
        from app.forms.system.indicator_bank_forms import _split_csv_tags
        assert _split_csv_tags('  a , b , c  ') == ['a', 'b', 'c']

    def test_filters_empty_parts(self):
        from app.forms.system.indicator_bank_forms import _split_csv_tags
        result = _split_csv_tags('a,,b')
        assert '' not in result


class TestJoinCsvTags:
    def test_none(self):
        from app.forms.system.indicator_bank_forms import _join_csv_tags
        assert _join_csv_tags(None) == ''

    def test_empty_list(self):
        from app.forms.system.indicator_bank_forms import _join_csv_tags
        assert _join_csv_tags([]) == ''

    def test_list_of_strings(self):
        from app.forms.system.indicator_bank_forms import _join_csv_tags
        result = _join_csv_tags(['health', 'education'])
        assert result == 'health, education'

    def test_string_passthrough(self):
        from app.forms.system.indicator_bank_forms import _join_csv_tags
        result = _join_csv_tags('existing string')
        assert result == 'existing string'

    def test_strips_whitespace_in_list(self):
        from app.forms.system.indicator_bank_forms import _join_csv_tags
        result = _join_csv_tags(['  health  ', '  water  '])
        assert result == 'health, water'


# ---------------------------------------------------------------------------
# Helpers for mocking the DB dependencies
# ---------------------------------------------------------------------------

def _mock_indicator_bank_form_deps():
    """Return a context manager that patches all DB calls in IndicatorBankForm."""
    mtype = MagicMock()
    mtype.id = 1
    mtype.name = 'Number'
    munit = MagicMock()
    munit.id = 2
    munit.name = 'People'
    sector = MagicMock()
    sector.id = 10
    sector.name = 'Health'
    subsector = MagicMock()
    subsector.id = 20
    subsector.name = 'Primary Health'

    patches = [
        patch('app.forms.system.indicator_bank_forms.IndicatorBankType.query') ,
        patch('app.forms.system.indicator_bank_forms.IndicatorBankUnit.query'),
        patch('app.forms.system.indicator_bank_forms.Sector.query'),
        patch('app.forms.system.indicator_bank_forms.SubSector.query'),
        patch('app.routes.admin.shared.get_localized_sector_name', return_value='Health'),
        patch('app.routes.admin.shared.get_localized_subsector_name', return_value='Primary Health'),
    ]
    return patches, mtype, munit, sector, subsector


def _make_ib_form(app, data=None):
    """Create an IndicatorBankForm with mocked DB queries."""
    mtype = MagicMock(); mtype.id = 1; mtype.name = 'Number'
    munit = MagicMock(); munit.id = 2; munit.name = 'People'
    sector = MagicMock(); sector.id = 10; sector.name = 'Health'
    subsector = MagicMock(); subsector.id = 20; subsector.name = 'Sub'

    with patch('app.forms.system.indicator_bank_forms.IndicatorBankType') as mt, \
         patch('app.forms.system.indicator_bank_forms.IndicatorBankUnit') as mu, \
         patch('app.forms.system.indicator_bank_forms.Sector') as ms, \
         patch('app.forms.system.indicator_bank_forms.SubSector') as mss, \
         patch('app.routes.admin.shared.get_localized_sector_name', return_value='Health'), \
         patch('app.routes.admin.shared.get_localized_subsector_name', return_value='Sub'):

        mt.query.filter_by.return_value.order_by.return_value.all.return_value = [mtype]
        mu.query.filter_by.return_value.order_by.return_value.all.return_value = [munit]
        ms.query.filter_by.return_value.order_by.return_value.all.return_value = [sector]
        mss.query.filter_by.return_value.order_by.return_value.all.return_value = [subsector]

        from app.forms.system.indicator_bank_forms import IndicatorBankForm
        form = IndicatorBankForm(data=data or {'name': 'Test Indicator', 'type': 1})
        form.type.choices = [(1, 'Number')]
        form.unit.choices = [(None, '-- No unit --'), (2, 'People')]
        form.sector_primary.choices = [(None, '-- Select --'), (10, 'Health')]
        form.sector_secondary.choices = [(None, '-- Select --'), (10, 'Health')]
        form.sector_tertiary.choices = [(None, '-- Select --'), (10, 'Health')]
        form.sub_sector_primary.choices = [(None, '-- Select --'), (20, 'Sub')]
        form.sub_sector_secondary.choices = [(None, '-- Select --'), (20, 'Sub')]
        form.sub_sector_tertiary.choices = [(None, '-- Select --'), (20, 'Sub')]
        return form


class TestIndicatorBankForm:
    def test_instantiation(self, app):
        with app.app_context():
            form = _make_ib_form(app)
            assert form is not None

    def test_has_multilingual_name_fields(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            form = _make_ib_form(app)
            from app.forms.system.indicator_bank_forms import IndicatorBankForm
            assert hasattr(IndicatorBankForm, 'name_fr')

    def test_populate_choices_error_fallback(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_bank_forms.IndicatorBankType') as mt, \
                 patch('app.forms.system.indicator_bank_forms.IndicatorBankUnit') as mu, \
                 patch('app.forms.system.indicator_bank_forms.Sector') as ms, \
                 patch('app.forms.system.indicator_bank_forms.SubSector') as mss:
                mt.query.filter_by.return_value.order_by.side_effect = RuntimeError('db fail')
                mu.query.filter_by.return_value.order_by.return_value.all.return_value = []
                ms.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mss.query.filter_by.return_value.order_by.return_value.all.return_value = []
                from app.forms.system.indicator_bank_forms import IndicatorBankForm
                form = IndicatorBankForm(data={'name': 'Test', 'type': 1})
                # Should have fallback empty choices
                assert form.sector_primary.choices is not None

    def test_translatable_languages_fallback(self, app):
        with app.app_context():
            form = _make_ib_form(app)
            # Simulate no TRANSLATABLE_LANGUAGES in config
            original = app.config.get('TRANSLATABLE_LANGUAGES')
            app.config['TRANSLATABLE_LANGUAGES'] = None
            try:
                langs = form._translatable_languages()
                assert langs == [] or isinstance(langs, list)
            finally:
                if original is not None:
                    app.config['TRANSLATABLE_LANGUAGES'] = original

    def test_translatable_languages_from_config(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr', 'ar']
            form = _make_ib_form(app)
            langs = form._translatable_languages()
            assert 'fr' in langs

    def test_populate_multilingual_field(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            form = _make_ib_form(app)
            from app.forms.system.indicator_bank_forms import IndicatorBankForm
            if hasattr(IndicatorBankForm, 'name_fr'):
                form._populate_multilingual_field({'fr': 'Nom du test'}, 'name')
                assert form.name_fr.data == 'Nom du test'

    def test_populate_multilingual_field_non_string_value(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            form = _make_ib_form(app)
            from app.forms.system.indicator_bank_forms import IndicatorBankForm
            if hasattr(IndicatorBankForm, 'name_fr'):
                form._populate_multilingual_field({'fr': 123}, 'name')
                assert form.name_fr.data == ''

    def test_populate_multilingual_field_missing_lang(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            form = _make_ib_form(app)
            from app.forms.system.indicator_bank_forms import IndicatorBankForm
            if hasattr(IndicatorBankForm, 'name_fr'):
                form._populate_multilingual_field({}, 'name')
                assert form.name_fr.data == ''

    def test_apply_multilingual_field(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            form = _make_ib_form(app)
            from app.forms.system.indicator_bank_forms import IndicatorBankForm
            if hasattr(IndicatorBankForm, 'name_fr'):
                form.name_fr.data = 'Test French'
                mock_ib = MagicMock()
                mock_ib.set_name_translation = MagicMock()
                form._apply_multilingual_field(mock_ib, 'name', 'set_name_translation')
                mock_ib.set_name_translation.assert_called_with('fr', 'Test French')

    def test_non_empty_values_from_request(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_bank_forms.get_request_data') as mock_req:
                mock_data = MagicMock()
                mock_data.getlist.return_value = ['Q1', '', 'Q2', '  ']
                mock_req.return_value = mock_data
                from app.forms.system.indicator_bank_forms import IndicatorBankForm
                result = IndicatorBankForm._non_empty_values_from_request('monitoring_questions')
                assert result == ['Q1', 'Q2']

    def test_monitoring_questions_from_request_empty(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_bank_forms.get_request_data') as mock_req:
                mock_data = MagicMock()
                mock_data.getlist.return_value = []
                mock_req.return_value = mock_data
                from app.forms.system.indicator_bank_forms import IndicatorBankForm
                result = IndicatorBankForm.monitoring_questions_from_request()
                assert result is None

    def test_monitoring_questions_from_request_with_values(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_bank_forms.get_request_data') as mock_req:
                mock_data = MagicMock()
                mock_data.getlist.return_value = ['Q1', 'Q2']
                mock_req.return_value = mock_data
                from app.forms.system.indicator_bank_forms import IndicatorBankForm
                result = IndicatorBankForm.monitoring_questions_from_request()
                assert result == ['Q1', 'Q2']

    def test_related_programs_from_request_empty(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_bank_forms.get_request_data') as mock_req:
                mock_data = MagicMock()
                mock_data.getlist.return_value = []
                mock_req.return_value = mock_data
                from app.forms.system.indicator_bank_forms import IndicatorBankForm
                result = IndicatorBankForm.related_programs_from_request()
                assert result is None

    def test_related_programs_from_request_with_values(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_bank_forms.get_request_data') as mock_req:
                mock_data = MagicMock()
                mock_data.getlist.return_value = ['Prog A', 'Prog B']
                mock_req.return_value = mock_data
                from app.forms.system.indicator_bank_forms import IndicatorBankForm
                result = IndicatorBankForm.related_programs_from_request()
                assert result == ['Prog A', 'Prog B']


class TestIndicatorBankFormPopulateFrom:
    def _make_mock_indicator_bank(self):
        ib = MagicMock()
        ib.name = 'Test IB'
        ib.indicator_type_id = 1
        ib.type = 'Number'
        ib.indicator_unit_id = 2
        ib.unit = 'people'
        ib.fdrs_kpi_code = 'FD001'
        ib.definition = 'A test indicator'
        ib.aggregated_label = 'Total count'
        ib.area = 'EF2'
        ib.data_source = 'IFRC'
        ib.disaggregation_guidance = 'By sex'
        ib.tags_list = ['health', 'emergency']
        ib.name_translations = {'fr': 'Indicateur Test'}
        ib.aggregated_label_translations = {'fr': 'Compte total'}
        ib.archived = False
        ib.emergency = True
        ib.comments = 'Test comments'
        ib.sector = {'primary': 10}
        ib.sub_sector = {'primary': 20}
        return ib

    def test_populate_from_indicator_bank(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            form = _make_ib_form(app)
            mock_ib = self._make_mock_indicator_bank()
            with patch('app.services.indicator_measurement_sync.resolve_type_id_for_legacy_string', return_value=1), \
                 patch('app.services.indicator_measurement_sync.resolve_unit_id_for_legacy_string', return_value=2):
                form.populate_from_indicator_bank(mock_ib)
            assert form.name.data == 'Test IB'

    def test_populate_from_no_type_id_uses_legacy_resolver(self, app):
        with app.app_context():
            form = _make_ib_form(app)
            mock_ib = self._make_mock_indicator_bank()
            mock_ib.indicator_type_id = None
            with patch('app.services.indicator_measurement_sync.resolve_type_id_for_legacy_string', return_value=1) as mock_resolver, \
                 patch('app.services.indicator_measurement_sync.resolve_unit_id_for_legacy_string', return_value=2):
                form.populate_from_indicator_bank(mock_ib)
                mock_resolver.assert_called_once_with(mock_ib.type)

    def test_populate_from_no_unit_id_uses_legacy_resolver(self, app):
        with app.app_context():
            form = _make_ib_form(app)
            mock_ib = self._make_mock_indicator_bank()
            mock_ib.indicator_unit_id = None
            with patch('app.services.indicator_measurement_sync.resolve_type_id_for_legacy_string', return_value=1), \
                 patch('app.services.indicator_measurement_sync.resolve_unit_id_for_legacy_string', return_value=2) as mock_unit_resolver:
                form.populate_from_indicator_bank(mock_ib)
                mock_unit_resolver.assert_called_once_with(mock_ib.unit)

    def test_populate_from_with_non_dict_translations(self, app):
        with app.app_context():
            form = _make_ib_form(app)
            mock_ib = self._make_mock_indicator_bank()
            mock_ib.name_translations = None
            mock_ib.aggregated_label_translations = 'invalid'
            with patch('app.services.indicator_measurement_sync.resolve_type_id_for_legacy_string', return_value=1), \
                 patch('app.services.indicator_measurement_sync.resolve_unit_id_for_legacy_string', return_value=2):
                form.populate_from_indicator_bank(mock_ib)
            # Should not raise, just use empty dict fallback

    def test_populate_from_no_sector(self, app):
        with app.app_context():
            form = _make_ib_form(app)
            mock_ib = self._make_mock_indicator_bank()
            mock_ib.sector = None
            mock_ib.sub_sector = None
            with patch('app.services.indicator_measurement_sync.resolve_type_id_for_legacy_string', return_value=1), \
                 patch('app.services.indicator_measurement_sync.resolve_unit_id_for_legacy_string', return_value=2):
                form.populate_from_indicator_bank(mock_ib)
            # Should not set sector fields


class TestIndicatorBankFormPopulateIndicatorBank:
    def test_populate_indicator_bank(self, app):
        with app.app_context():
            form = _make_ib_form(app, data={'name': 'My IB', 'type': 1})
            form.name.data = 'My Indicator'
            form.type.data = 1
            form.unit.data = None
            form.fdrs_kpi_code.data = 'FD001'
            form.definition.data = 'Definition'
            form.aggregated_label.data = 'Agg Label'
            form.area.data = 'EF2'
            form.data_source.data = 'IFRC'
            form.disaggregation_guidance.data = 'By sex'
            form.tags.data = 'health, water'
            form.archived.data = False
            form.emergency.data = True
            form.comments.data = 'Some comments'
            form.sector_primary.data = None
            form.sector_secondary.data = None
            form.sector_tertiary.data = None
            form.sub_sector_primary.data = None
            form.sub_sector_secondary.data = None
            form.sub_sector_tertiary.data = None

            mock_ib = MagicMock()
            mock_ib.set_name_translation = MagicMock()
            mock_ib.set_aggregated_label_translation = MagicMock()
            mock_ib.sync_type_unit_string_columns = MagicMock()

            with patch('app.forms.system.indicator_bank_forms.get_request_data') as mock_req:
                mock_data = MagicMock()
                mock_data.getlist.return_value = []
                mock_req.return_value = mock_data
                form.populate_indicator_bank(mock_ib)

            assert mock_ib.name == 'My Indicator'

    def test_populate_indicator_bank_with_sectors(self, app):
        with app.app_context():
            form = _make_ib_form(app, data={'name': 'My IB', 'type': 1})
            form.name.data = 'Sector Test'
            form.type.data = 1
            form.unit.data = None
            form.fdrs_kpi_code.data = ''
            form.definition.data = ''
            form.aggregated_label.data = ''
            form.area.data = ''
            form.data_source.data = ''
            form.disaggregation_guidance.data = ''
            form.tags.data = ''
            form.archived.data = False
            form.emergency.data = False
            form.comments.data = ''
            form.sector_primary.data = 10
            form.sector_secondary.data = None
            form.sector_tertiary.data = None
            form.sub_sector_primary.data = 20
            form.sub_sector_secondary.data = None
            form.sub_sector_tertiary.data = None

            mock_ib = MagicMock()
            mock_ib.set_name_translation = MagicMock()
            mock_ib.set_aggregated_label_translation = MagicMock()
            mock_ib.sync_type_unit_string_columns = MagicMock()

            with patch('app.forms.system.indicator_bank_forms.get_request_data') as mock_req:
                mock_data = MagicMock()
                mock_data.getlist.return_value = []
                mock_req.return_value = mock_data
                form.populate_indicator_bank(mock_ib)

            assert mock_ib.sector == {'primary': 10}
            assert mock_ib.sub_sector == {'primary': 20}

    def test_populate_indicator_bank_syncs_related_programs_list(self, app):
        with app.app_context():
            form = _make_ib_form(app, data={'name': 'My IB', 'type': 1})
            form.name.data = 'Programs Test'
            form.type.data = 1
            form.unit.data = None
            form.fdrs_kpi_code.data = ''
            form.definition.data = ''
            form.aggregated_label.data = ''
            form.area.data = ''
            form.data_source.data = ''
            form.disaggregation_guidance.data = ''
            form.tags.data = ''
            form.archived.data = False
            form.emergency.data = False
            form.comments.data = ''
            form.sector_primary.data = None
            form.sector_secondary.data = None
            form.sector_tertiary.data = None
            form.sub_sector_primary.data = None
            form.sub_sector_secondary.data = None
            form.sub_sector_tertiary.data = None

            mock_ib = MagicMock()
            mock_ib.set_name_translation = MagicMock()
            mock_ib.set_aggregated_label_translation = MagicMock()
            mock_ib.sync_type_unit_string_columns = MagicMock()

            with patch('app.forms.system.indicator_bank_forms.get_request_data') as mock_req:
                mock_data = MagicMock()
                mock_data.getlist.return_value = ['Health', 'WASH']
                mock_req.return_value = mock_data
                form.populate_indicator_bank(mock_ib)

            assert mock_ib.related_programs_list == ['Health', 'WASH']

class TestSectorForm:
    def test_instantiation(self, app):
        with app.app_context():
            from app.forms.system.indicator_bank_forms import SectorForm
            form = SectorForm(data={'name': 'Health'})
            assert form is not None

    def test_valid_data(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_bank_forms.Sector') as mock_sector:
                mock_sector.query.filter_by.return_value.first.return_value = None
                from app.forms.system.indicator_bank_forms import SectorForm
                form = SectorForm(data={'name': 'Health'})
                assert form.validate() is True

    def test_missing_name_fails(self, app):
        with app.app_context():
            from app.forms.system.indicator_bank_forms import SectorForm
            form = SectorForm(data={})
            assert form.validate() is False
            assert 'name' in form.errors

    def test_duplicate_name_raises(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_bank_forms.Sector') as mock_sector:
                mock_sector.query.filter_by.return_value.first.return_value = MagicMock()
                mock_sector.__name__ = 'Sector'
                from app.forms.system.indicator_bank_forms import SectorForm
                form = SectorForm(data={'name': 'Duplicate'})
                assert form.validate() is False

    def test_validate_name_with_original_id(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_bank_forms.Sector') as mock_sector:
                mock_q = MagicMock()
                mock_q.filter.return_value.first.return_value = None
                mock_sector.query.filter_by.return_value = mock_q
                mock_sector.id = MagicMock()
                from app.forms.system.indicator_bank_forms import SectorForm
                form = SectorForm(data={'name': 'Existing'}, original_sector_id=5)
                assert form.validate() is True

    def test_multilingual_name_fields_added(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            from app.forms.system.indicator_bank_forms import SectorForm
            form = SectorForm(data={'name': 'Health'})
            assert hasattr(SectorForm, 'name_fr')


# ---------------------------------------------------------------------------
# SubSectorForm
# ---------------------------------------------------------------------------

class TestSubSectorForm:
    def _make_sector(self):
        s = MagicMock()
        s.id = 10
        s.name = 'Health'
        s.display_order = 0
        return s

    def test_instantiation(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_bank_forms.Sector') as mock_sector, \
                 patch('app.routes.admin.shared.get_localized_sector_name', return_value='Health'):
                mock_sector.query.filter_by.return_value.order_by.return_value.all.return_value = []
                from app.forms.system.indicator_bank_forms import SubSectorForm
                form = SubSectorForm(data={'name': 'Primary Health'})
                assert form is not None

    def test_valid_data(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_bank_forms.Sector') as mock_sector, \
                 patch('app.routes.admin.shared.get_localized_sector_name', return_value='Health'), \
                 patch('app.forms.system.indicator_bank_forms.SubSector') as mock_ss:
                mock_sector.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_ss.query.filter_by.return_value.first.return_value = None
                from app.forms.system.indicator_bank_forms import SubSectorForm
                form = SubSectorForm(data={'name': 'Primary Health'})
                assert form.validate() is True

    def test_duplicate_name_fails(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_bank_forms.Sector') as mock_sector, \
                 patch('app.routes.admin.shared.get_localized_sector_name', return_value='Health'), \
                 patch('app.forms.system.indicator_bank_forms.SubSector') as mock_ss:
                mock_sector.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_ss.query.filter_by.return_value.first.return_value = MagicMock()
                mock_ss.__name__ = 'SubSector'
                from app.forms.system.indicator_bank_forms import SubSectorForm
                form = SubSectorForm(data={'name': 'Duplicate Sub'})
                assert form.validate() is False

    def test_sector_choices_populated(self, app):
        with app.app_context():
            sector = self._make_sector()
            with patch('app.forms.system.indicator_bank_forms.Sector') as mock_sector, \
                 patch('app.routes.admin.shared.get_localized_sector_name', return_value='Health'):
                mock_sector.query.filter_by.return_value.order_by.return_value.all.return_value = [sector]
                from app.forms.system.indicator_bank_forms import SubSectorForm
                form = SubSectorForm(data={'name': 'Sub'})
                sector_ids = [c[0] for c in form.sector_id.choices]
                assert 10 in sector_ids

    def test_multilingual_name_fields_added(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            with patch('app.forms.system.indicator_bank_forms.Sector') as mock_sector, \
                 patch('app.routes.admin.shared.get_localized_sector_name', return_value='Health'):
                mock_sector.query.filter_by.return_value.order_by.return_value.all.return_value = []
                from app.forms.system.indicator_bank_forms import SubSectorForm
                form = SubSectorForm(data={'name': 'Sub'})
                assert hasattr(SubSectorForm, 'name_fr')


# ---------------------------------------------------------------------------
# CommonWordForm
# ---------------------------------------------------------------------------

class TestCommonWordForm:
    def test_instantiation(self, app):
        with app.app_context():
            from app.forms.system.indicator_bank_forms import CommonWordForm
            form = CommonWordForm(data={'term': 'Emergency', 'meaning': 'A crisis situation'})
            assert form is not None

    def test_valid_data(self, app):
        with app.app_context():
            from app.forms.system.indicator_bank_forms import CommonWordForm
            form = CommonWordForm(data={'term': 'Emergency', 'meaning': 'A crisis situation'})
            assert form.validate() is True

    def test_missing_term_fails(self, app):
        with app.app_context():
            from app.forms.system.indicator_bank_forms import CommonWordForm
            form = CommonWordForm(data={'meaning': 'A crisis situation'})
            assert form.validate() is False
            assert 'term' in form.errors

    def test_missing_meaning_fails(self, app):
        with app.app_context():
            from app.forms.system.indicator_bank_forms import CommonWordForm
            form = CommonWordForm(data={'term': 'Emergency'})
            assert form.validate() is False
            assert 'meaning' in form.errors

    def test_multilingual_fields_added(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            from app.forms.system.indicator_bank_forms import CommonWordForm
            form = CommonWordForm(data={'term': 'Test', 'meaning': 'Test meaning'})
            assert hasattr(CommonWordForm, 'meaning_fr')

    def test_populate_common_word(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            from app.forms.system.indicator_bank_forms import CommonWordForm
            form = CommonWordForm(data={'term': 'Emergency', 'meaning': 'A crisis'})
            mock_cw = MagicMock()
            mock_cw.set_meaning_translation = MagicMock()
            from app.forms.system.indicator_bank_forms import CommonWordForm as CWF
            if hasattr(CWF, 'meaning_fr'):
                form.meaning_fr.data = 'Une crise'
            form.populate_common_word(mock_cw)
            assert mock_cw.term == 'Emergency'
            assert mock_cw.meaning == 'A crisis'

    def test_populate_common_word_translatable_fallback(self, app):
        with app.app_context():
            from app.forms.system.indicator_bank_forms import CommonWordForm
            form = CommonWordForm(data={'term': 'Emergency', 'meaning': 'A crisis'})
            mock_cw = MagicMock()
            mock_cw.set_meaning_translation = MagicMock()
            # Remove TRANSLATABLE_LANGUAGES to trigger the empty-list fallback
            original = app.config.get('TRANSLATABLE_LANGUAGES')
            app.config['TRANSLATABLE_LANGUAGES'] = None
            try:
                form.populate_common_word(mock_cw)
            finally:
                if original is not None:
                    app.config['TRANSLATABLE_LANGUAGES'] = original
            # Should not raise

    def test_populate_from_common_word(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            from app.forms.system.indicator_bank_forms import CommonWordForm
            form = CommonWordForm(data={})
            mock_cw = MagicMock()
            mock_cw.term = 'Emergency'
            mock_cw.meaning = 'A crisis'
            mock_cw.is_active = True
            mock_cw.meaning_translations = {'fr': 'Une crise'}
            form.populate_from_common_word(mock_cw)
            assert form.term.data == 'Emergency'
            assert form.meaning.data == 'A crisis'

    def test_populate_from_common_word_non_dict_translations(self, app):
        with app.app_context():
            from app.forms.system.indicator_bank_forms import CommonWordForm
            form = CommonWordForm(data={})
            mock_cw = MagicMock()
            mock_cw.term = 'Test'
            mock_cw.meaning = 'Test meaning'
            mock_cw.is_active = True
            mock_cw.meaning_translations = None  # Not a dict
            form.populate_from_common_word(mock_cw)
            # Should not raise

    def test_populate_from_common_word_translatable_fallback(self, app):
        with app.app_context():
            from app.forms.system.indicator_bank_forms import CommonWordForm
            form = CommonWordForm(data={})
            mock_cw = MagicMock()
            mock_cw.term = 'Test'
            mock_cw.meaning = 'Test meaning'
            mock_cw.is_active = True
            mock_cw.meaning_translations = {}
            original = app.config.get('TRANSLATABLE_LANGUAGES')
            app.config['TRANSLATABLE_LANGUAGES'] = None
            try:
                form.populate_from_common_word(mock_cw)
            finally:
                if original is not None:
                    app.config['TRANSLATABLE_LANGUAGES'] = original
            # Should not raise
