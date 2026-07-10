"""
Unit tests for indicator_bank.py models to achieve 100% code coverage.

Covers: IndicatorBankType, IndicatorBankUnit, IndicatorBank, IndicatorBankHistory,
        IndicatorSuggestion, Sector, SubSector, CommonWord
"""
import pytest
from unittest.mock import patch, MagicMock

from app.models.indicator_bank import (
    IndicatorBankType,
    IndicatorBankUnit,
    IndicatorBank,
    IndicatorBankHistory,
    IndicatorSuggestion,
    Sector,
    SubSector,
    CommonWord,
)
from app.models.enums import IndicatorSuggestionStatusValue, IndicatorSuggestionTypeValue
from tests.factories import create_test_user


@pytest.mark.unit
class TestIndicatorBankType:
    """Tests for IndicatorBankType model."""

    def _create_type(self, db_session, **kwargs):
        import uuid
        defaults = {
            'code': f'NUM_{uuid.uuid4().hex[:6]}',
            'name': 'Number',
        }
        defaults.update(kwargs)
        t = IndicatorBankType(**defaults)
        db_session.add(t)
        db_session.commit()
        db_session.refresh(t)
        return t

    def test_create_type(self, db_session, app):
        """Test creating an indicator bank type."""
        with app.app_context():
            t = self._create_type(db_session, code='NUMBER', name='Number')
            assert t.id is not None
            assert t.name == 'Number'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            t = self._create_type(db_session, code='PCT', name='Percentage')
            assert 'PCT' in repr(t)

    def test_get_name_translation_existing(self, db_session, app):
        """Test get_name_translation returns translated name."""
        with app.app_context():
            t = self._create_type(db_session, name_translations={'fr': 'Nombre'})
            result = t.get_name_translation('fr')
            assert result == 'Nombre'

    def test_get_name_translation_fallback(self, db_session, app):
        """Test get_name_translation falls back to name."""
        with app.app_context():
            t = self._create_type(db_session, name='Number')
            result = t.get_name_translation('de')
            assert result == 'Number'

    def test_get_name_translation_no_translations(self, db_session, app):
        """Test get_name_translation with None name_translations."""
        with app.app_context():
            t = self._create_type(db_session, name='Number', name_translations=None)
            result = t.get_name_translation('fr')
            assert result == 'Number'

    def test_get_name_translation_non_string_val(self, db_session, app):
        """Test get_name_translation ignores non-string translation values."""
        with app.app_context():
            t = self._create_type(db_session, name='Number', name_translations={'fr': 123})
            result = t.get_name_translation('fr')
            assert result == 'Number'

    def test_get_name_translation_locale_normalization(self, db_session, app):
        """Test get_name_translation normalizes locale (fr_FR -> fr)."""
        with app.app_context():
            t = self._create_type(db_session, name_translations={'fr': 'Nombre'})
            result = t.get_name_translation('fr_FR')
            assert result == 'Nombre'

    def test_set_name_translation(self, db_session, app):
        """Test setting a name translation."""
        with app.app_context():
            t = self._create_type(db_session)
            t.set_name_translation('fr', 'Nombre')
            assert t.name_translations['fr'] == 'Nombre'

    def test_set_name_translation_en_ignored(self, db_session, app):
        """Test setting English translation is ignored (uses default name)."""
        with app.app_context():
            t = self._create_type(db_session)
            t.set_name_translation('en', 'English Name')
            assert t.name_translations is None or 'en' not in (t.name_translations or {})

    def test_set_name_translation_empty_lang_ignored(self, db_session, app):
        """Test setting empty language translation is ignored."""
        with app.app_context():
            t = self._create_type(db_session)
            t.set_name_translation('', 'Some Text')
            assert t.name_translations is None

    def test_set_name_translation_empty_text_removes_key(self, db_session, app):
        """Test setting empty text removes existing translation."""
        with app.app_context():
            t = self._create_type(db_session, name_translations={'fr': 'Nombre'})
            t.set_name_translation('fr', '')
            assert 'fr' not in (t.name_translations or {})

    def test_set_name_translation_initializes_dict(self, db_session, app):
        """Test set_name_translation initializes name_translations dict when None."""
        with app.app_context():
            t = self._create_type(db_session, name_translations=None)
            t.set_name_translation('fr', 'Nombre')
            assert isinstance(t.name_translations, dict)


@pytest.mark.unit
class TestIndicatorBankUnit:
    """Tests for IndicatorBankUnit model."""

    def _create_unit(self, db_session, **kwargs):
        import uuid
        defaults = {
            'code': f'PPL_{uuid.uuid4().hex[:6]}',
            'name': 'People',
        }
        defaults.update(kwargs)
        u = IndicatorBankUnit(**defaults)
        db_session.add(u)
        db_session.commit()
        db_session.refresh(u)
        return u

    def test_create_unit(self, db_session, app):
        """Test creating an indicator bank unit."""
        with app.app_context():
            u = self._create_unit(db_session, code='PEOPLE', name='People')
            assert u.id is not None
            assert u.name == 'People'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            u = self._create_unit(db_session, code='HH')
            assert 'HH' in repr(u)

    def test_get_name_translation_existing(self, db_session, app):
        """Test get_name_translation returns translated name."""
        with app.app_context():
            u = self._create_unit(db_session, name_translations={'fr': 'Personnes'})
            result = u.get_name_translation('fr')
            assert result == 'Personnes'

    def test_get_name_translation_fallback(self, db_session, app):
        """Test fallback to name when translation missing."""
        with app.app_context():
            u = self._create_unit(db_session, name='People')
            result = u.get_name_translation('es')
            assert result == 'People'

    def test_set_name_translation(self, db_session, app):
        """Test setting translation."""
        with app.app_context():
            u = self._create_unit(db_session)
            u.set_name_translation('es', 'Personas')
            assert u.name_translations['es'] == 'Personas'

    def test_set_name_translation_en_ignored(self, db_session, app):
        """Test English translation is ignored."""
        with app.app_context():
            u = self._create_unit(db_session)
            u.set_name_translation('en', 'English')
            # Should not be stored
            assert u.name_translations is None or 'en' not in (u.name_translations or {})

    def test_set_name_translation_initializes(self, db_session, app):
        """Test initializes dict when None."""
        with app.app_context():
            u = self._create_unit(db_session, name_translations=None)
            u.set_name_translation('fr', 'Personnes')
            assert isinstance(u.name_translations, dict)

    def test_set_name_translation_empty_removes(self, db_session, app):
        """Test empty text removes key."""
        with app.app_context():
            u = self._create_unit(db_session, name_translations={'fr': 'Personnes'})
            u.set_name_translation('fr', '')
            assert 'fr' not in (u.name_translations or {})


@pytest.mark.unit
class TestIndicatorBank:
    """Tests for IndicatorBank model."""

    def _create_indicator(self, db_session, **kwargs):
        import uuid
        defaults = {
            'name': f'Test Indicator {uuid.uuid4().hex[:6]}',
            'type': 'number',
        }
        defaults.update(kwargs)
        ind = IndicatorBank(**defaults)
        db_session.add(ind)
        db_session.commit()
        db_session.refresh(ind)
        return ind

    def test_create_indicator(self, db_session, app):
        """Test creating an indicator."""
        with app.app_context():
            ind = self._create_indicator(db_session, name='Volunteers', type='number')
            assert ind.id is not None
            assert ind.name == 'Volunteers'
            assert ind.type == 'number'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            ind = self._create_indicator(db_session, name='Staff Count', type='number')
            result = repr(ind)
            assert 'Staff Count' in result

    def test_timestamps_set_on_init(self, db_session, app):
        """Test created_at and updated_at are set on creation."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            assert ind.created_at is not None
            assert ind.updated_at is not None

    def test_sector_display_empty(self, db_session, app):
        """Test sector_display returns empty string when no sector."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            assert ind.sector_display == ''

    def test_sector_display_with_sector(self, db_session, app):
        """Test sector_display formats sector names."""
        with app.app_context():
            sector = Sector(name='Health')
            db_session.add(sector)
            db_session.commit()
            ind = self._create_indicator(db_session, sector={'primary': sector.id})
            result = ind.sector_display
            assert 'Health' in result

    def test_sector_display_with_missing_sector_id(self, db_session, app):
        """Test sector_display handles missing sector gracefully."""
        with app.app_context():
            ind = self._create_indicator(db_session, sector={'primary': 99999})
            result = ind.sector_display
            assert result == ''

    def test_sub_sector_display_empty(self, db_session, app):
        """Test sub_sector_display returns empty string when no sub_sector."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            assert ind.sub_sector_display == ''

    def test_sub_sector_display_with_subsector(self, db_session, app):
        """Test sub_sector_display formats subsector names."""
        with app.app_context():
            subsector = SubSector(name='Nutrition')
            db_session.add(subsector)
            db_session.commit()
            ind = self._create_indicator(db_session, sub_sector={'primary': subsector.id})
            result = ind.sub_sector_display
            assert 'Nutrition' in result

    def test_related_programs_list_from_jsonb(self, db_session, app):
        """Test related_programs_list from JSONB column."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            ind._related_programs_list = ['WASH', 'Health']
            result = ind.related_programs_list
            assert result == ['WASH', 'Health']

    def test_related_programs_list_from_text(self, db_session, app):
        """Test related_programs_list parsed from CSV string via setter."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            ind.related_programs_list = 'WASH, Health, Shelter'
            result = ind.related_programs_list
            assert 'WASH' in result
            assert 'Health' in result
            assert 'Shelter' in result

    def test_related_programs_list_pipe_separator(self, db_session, app):
        """Test related_programs_list with pipe separator via setter."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            ind.related_programs_list = 'WASH|Health'
            result = ind.related_programs_list
            assert 'WASH' in result
            assert 'Health' in result

    def test_related_programs_list_empty(self, db_session, app):
        """Test related_programs_list returns empty list when None."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            assert ind.related_programs_list == []

    def test_related_programs_list_non_list_jsonb(self, db_session, app):
        """Test related_programs_list returns empty list if JSONB is not a list."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            ind._related_programs_list = {'not': 'a list'}
            assert ind.related_programs_list == []

    def test_related_programs_list_setter_list(self, db_session, app):
        """Test setter with a list."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            ind.related_programs_list = ['WASH', 'Health', '']
            assert ind._related_programs_list == ['WASH', 'Health']

    def test_related_programs_list_setter_none(self, db_session, app):
        """Test setter with None."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            ind.related_programs_list = None
            assert ind._related_programs_list is None

    def test_related_programs_list_setter_string(self, db_session, app):
        """Test setter with a string."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            ind.related_programs_list = 'WASH, Health'
            assert 'WASH' in ind._related_programs_list
            assert 'Health' in ind._related_programs_list

    def test_related_programs_list_setter_overwrites_existing(self, db_session, app):
        """Test setter replaces existing related programs."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            ind.related_programs_list = ['Old Program']
            ind.related_programs_list = ['New Program']
            assert ind.related_programs_list == ['New Program']

    def test_related_programs_list_resolved(self, db_session, app):
        """Test related_programs_list_resolved returns list."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            ind.related_programs_list = ['WASH']
            result = ind.related_programs_list_resolved
            assert 'WASH' in result

    def test_get_sector_by_level_no_sector(self, db_session, app):
        """Test get_sector_by_level returns None when no sector."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            result = ind.get_sector_by_level('primary')
            assert result is None

    def test_get_sector_by_level_missing_level(self, db_session, app):
        """Test get_sector_by_level returns None for missing level."""
        with app.app_context():
            ind = self._create_indicator(db_session, sector={'primary': 1})
            result = ind.get_sector_by_level('secondary')
            assert result is None

    def test_get_sector_by_level_cached(self, db_session, app):
        """Test get_sector_by_level uses cached sectors."""
        with app.app_context():
            mock_sector = MagicMock()
            mock_sector.name = 'Health'
            ind = self._create_indicator(db_session, sector={'primary': 1})
            ind._cached_sectors = {'primary': mock_sector}
            result = ind.get_sector_by_level('primary')
            assert result == mock_sector

    def test_get_sector_name_by_level(self, db_session, app):
        """Test get_sector_name_by_level returns name."""
        with app.app_context():
            sector = Sector(name='Education')
            db_session.add(sector)
            db_session.commit()
            ind = self._create_indicator(db_session, sector={'primary': sector.id})
            result = ind.get_sector_name_by_level('primary')
            assert result == 'Education'

    def test_get_sector_name_by_level_none(self, db_session, app):
        """Test get_sector_name_by_level returns None when no sector."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            result = ind.get_sector_name_by_level('primary')
            assert result is None

    def test_get_subsector_by_level_no_subsector(self, db_session, app):
        """Test get_subsector_by_level returns None when no sub_sector."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            result = ind.get_subsector_by_level('primary')
            assert result is None

    def test_get_subsector_by_level_cached(self, db_session, app):
        """Test get_subsector_by_level uses cached subsectors."""
        with app.app_context():
            mock_subsector = MagicMock()
            mock_subsector.name = 'Nutrition'
            ind = self._create_indicator(db_session, sub_sector={'primary': 1})
            ind._cached_subsectors = {'primary': mock_subsector}
            result = ind.get_subsector_by_level('primary')
            assert result == mock_subsector

    def test_get_subsector_name_by_level(self, db_session, app):
        """Test get_subsector_name_by_level returns name."""
        with app.app_context():
            subsector = SubSector(name='Community Health')
            db_session.add(subsector)
            db_session.commit()
            ind = self._create_indicator(db_session, sub_sector={'primary': subsector.id})
            result = ind.get_subsector_name_by_level('primary')
            assert result == 'Community Health'

    def test_get_subsector_name_by_level_none(self, db_session, app):
        """Test get_subsector_name_by_level returns None."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            result = ind.get_subsector_name_by_level('primary')
            assert result is None

    def test_get_all_sector_names(self, db_session, app):
        """Test get_all_sector_names returns list."""
        with app.app_context():
            sector1 = Sector(name='Health 2')
            sector2 = Sector(name='Education 2')
            db_session.add_all([sector1, sector2])
            db_session.commit()
            ind = self._create_indicator(
                db_session,
                sector={'primary': sector1.id, 'secondary': sector2.id}
            )
            names = ind.get_all_sector_names()
            assert 'Health 2' in names
            assert 'Education 2' in names

    def test_get_all_subsector_names(self, db_session, app):
        """Test get_all_subsector_names returns list."""
        with app.app_context():
            sub = SubSector(name='Water Quality')
            db_session.add(sub)
            db_session.commit()
            ind = self._create_indicator(db_session, sub_sector={'primary': sub.id})
            names = ind.get_all_subsector_names()
            assert 'Water Quality' in names

    def test_clear_cache(self, db_session, app):
        """Test clear_cache removes cached attributes."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            ind._cached_sectors = {'primary': MagicMock()}
            ind._cached_subsectors = {'primary': MagicMock()}
            ind._cached_programs_list = ['WASH']
            ind.clear_cache()
            assert not hasattr(ind, '_cached_sectors')
            assert not hasattr(ind, '_cached_subsectors')
            assert not hasattr(ind, '_cached_programs_list')

    def test_sync_type_unit_string_columns(self, db_session, app):
        """Test sync_type_unit_string_columns updates type from measurement_type."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            mock_type = MagicMock()
            mock_type.code = 'percentage'
            ind.measurement_type = mock_type
            mock_unit = MagicMock()
            mock_unit.code = 'percent'
            ind.measurement_unit = mock_unit
            ind.indicator_unit_id = 1
            ind.sync_type_unit_string_columns()
            assert ind.type == 'percentage'
            assert ind.unit == 'percent'

    def test_sync_type_unit_no_type(self, db_session, app):
        """Test sync_type_unit_string_columns with no measurement_type."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            ind.measurement_type = None
            ind.measurement_unit = None
            ind.sync_type_unit_string_columns()
            # Should not raise

    def test_template_instances_property(self, db_session, app):
        """Test template_instances returns a query."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            q = ind.template_instances
            assert q is not None

    def test_usage_count_no_cache(self, db_session, app):
        """Test usage_count returns integer count."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            count = ind.usage_count
            assert isinstance(count, int)

    def test_usage_count_with_cache(self, db_session, app):
        """Test usage_count returns cached value."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            ind._cached_usage_count = 42
            assert ind.usage_count == 42

    def test_get_name_translation(self, db_session, app):
        """Test get_name_translation."""
        with app.app_context():
            ind = self._create_indicator(db_session, name='Volunteers', name_translations={'fr': 'Bénévoles'})
            assert ind.get_name_translation('fr') == 'Bénévoles'
            assert ind.get_name_translation('de') == 'Volunteers'

    def test_set_name_translation(self, db_session, app):
        """Test set_name_translation."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            ind.set_name_translation('fr', 'Bénévoles')
            assert ind.name_translations['fr'] == 'Bénévoles'
            ind.set_name_translation('fr', '')
            assert 'fr' not in ind.name_translations

    def test_set_name_translation_init(self, db_session, app):
        """Test set_name_translation initializes dict."""
        with app.app_context():
            ind = self._create_indicator(db_session, name_translations=None)
            ind.set_name_translation('fr', 'Bénévoles')
            assert isinstance(ind.name_translations, dict)

    def test_get_definition_translation(self, db_session, app):
        """Test get_definition_translation."""
        with app.app_context():
            ind = self._create_indicator(
                db_session,
                definition='Number of volunteers',
                definition_translations={'fr': 'Nombre de bénévoles'},
            )
            assert ind.get_definition_translation('fr') == 'Nombre de bénévoles'
            assert ind.get_definition_translation('de') == 'Number of volunteers'

    def test_set_definition_translation(self, db_session, app):
        """Test set_definition_translation."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            ind.set_definition_translation('es', 'Definición')
            assert ind.definition_translations['es'] == 'Definición'

    def test_set_definition_translation_init(self, db_session, app):
        """Test set_definition_translation initializes dict."""
        with app.app_context():
            ind = self._create_indicator(db_session, definition_translations=None)
            ind.set_definition_translation('es', 'Definición')
            assert isinstance(ind.definition_translations, dict)

    def test_set_definition_translation_empty_removes(self, db_session, app):
        """Test set_definition_translation empty removes key."""
        with app.app_context():
            ind = self._create_indicator(db_session, definition_translations={'es': 'Definición'})
            ind.set_definition_translation('es', '')
            assert 'es' not in ind.definition_translations

    def test_get_aggregated_label_translation(self, db_session, app):
        """Test get_aggregated_label_translation."""
        with app.app_context():
            ind = self._create_indicator(
                db_session,
                aggregated_label='Total Volunteers',
                aggregated_label_translations={'fr': 'Bénévoles Total'},
            )
            assert ind.get_aggregated_label_translation('fr') == 'Bénévoles Total'
            assert ind.get_aggregated_label_translation('de') == 'Total Volunteers'

    def test_set_aggregated_label_translation(self, db_session, app):
        """Test set_aggregated_label_translation."""
        with app.app_context():
            ind = self._create_indicator(db_session)
            ind.set_aggregated_label_translation('fr', 'Bénévoles Total')
            assert ind.aggregated_label_translations['fr'] == 'Bénévoles Total'

    def test_set_aggregated_label_translation_init(self, db_session, app):
        """Test initializes dict."""
        with app.app_context():
            ind = self._create_indicator(db_session, aggregated_label_translations=None)
            ind.set_aggregated_label_translation('fr', 'Bénévoles Total')
            assert isinstance(ind.aggregated_label_translations, dict)

    def test_set_aggregated_label_translation_empty_removes(self, db_session, app):
        """Test empty removes key."""
        with app.app_context():
            ind = self._create_indicator(
                db_session, aggregated_label_translations={'fr': 'Bénévoles Total'}
            )
            ind.set_aggregated_label_translation('fr', '')
            assert 'fr' not in ind.aggregated_label_translations

    def test_tags_list(self, db_session, app):
        """Test tags_list returns list from JSONB."""
        with app.app_context():
            ind = self._create_indicator(db_session, tags=['health', 'volunteers'])
            result = ind.tags_list
            assert 'health' in result

    def test_monitoring_questions_list(self, db_session, app):
        """Test monitoring_questions_list returns list."""
        with app.app_context():
            ind = self._create_indicator(
                db_session,
                monitoring_questions=['How many volunteers?', 'Are they trained?']
            )
            result = ind.monitoring_questions_list
            assert 'How many volunteers?' in result


@pytest.mark.unit
class TestIndicatorBankHistory:
    """Tests for IndicatorBankHistory model."""

    def _create_history(self, db_session, indicator, user, **kwargs):
        defaults = {
            'indicator_bank_id': indicator.id,
            'user_id': user.id,
            'name': indicator.name,
            'type': indicator.type,
            'change_type': 'update',
            'change_description': 'Updated name',
        }
        defaults.update(kwargs)
        h = IndicatorBankHistory(**defaults)
        db_session.add(h)
        db_session.commit()
        db_session.refresh(h)
        return h

    def _create_indicator(self, db_session):
        import uuid
        ind = IndicatorBank(name=f'Hist Indicator {uuid.uuid4().hex[:6]}', type='number')
        db_session.add(ind)
        db_session.commit()
        return ind

    def test_create_history(self, db_session, app):
        """Test creating indicator history record."""
        with app.app_context():
            user = create_test_user(db_session)
            ind = self._create_indicator(db_session)
            h = self._create_history(db_session, ind, user)
            assert h.id is not None

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            user = create_test_user(db_session)
            ind = self._create_indicator(db_session)
            h = self._create_history(db_session, ind, user, change_type='create')
            result = repr(h)
            assert 'create' in result

    def test_timestamps_set_on_init(self, db_session, app):
        """Test created_at is set."""
        with app.app_context():
            user = create_test_user(db_session)
            ind = self._create_indicator(db_session)
            h = self._create_history(db_session, ind, user)
            assert h.created_at is not None

    def test_get_name_translation(self, db_session, app):
        """Test get_name_translation."""
        with app.app_context():
            user = create_test_user(db_session)
            ind = self._create_indicator(db_session)
            h = self._create_history(
                db_session, ind, user,
                name_translations={'fr': 'Bénévoles'}
            )
            assert h.get_name_translation('fr') == 'Bénévoles'
            assert h.get_name_translation('de') == h.name

    def test_set_name_translation(self, db_session, app):
        """Test set_name_translation."""
        with app.app_context():
            user = create_test_user(db_session)
            ind = self._create_indicator(db_session)
            h = self._create_history(db_session, ind, user)
            h.set_name_translation('es', 'Voluntarios')
            assert h.name_translations['es'] == 'Voluntarios'

    def test_set_name_translation_init(self, db_session, app):
        """Test initializes dict."""
        with app.app_context():
            user = create_test_user(db_session)
            ind = self._create_indicator(db_session)
            h = self._create_history(db_session, ind, user)
            h.name_translations = None
            h.set_name_translation('es', 'Voluntarios')
            assert isinstance(h.name_translations, dict)

    def test_set_name_translation_empty_removes(self, db_session, app):
        """Test empty text removes key."""
        with app.app_context():
            user = create_test_user(db_session)
            ind = self._create_indicator(db_session)
            h = self._create_history(db_session, ind, user, name_translations={'es': 'Voluntarios'})
            h.set_name_translation('es', '')
            assert 'es' not in h.name_translations

    def test_get_definition_translation(self, db_session, app):
        """Test get_definition_translation."""
        with app.app_context():
            user = create_test_user(db_session)
            ind = self._create_indicator(db_session)
            h = self._create_history(
                db_session, ind, user,
                definition='Description',
                definition_translations={'fr': 'Définition'}
            )
            assert h.get_definition_translation('fr') == 'Définition'
            assert h.get_definition_translation('de') == 'Description'

    def test_set_definition_translation(self, db_session, app):
        """Test set_definition_translation."""
        with app.app_context():
            user = create_test_user(db_session)
            ind = self._create_indicator(db_session)
            h = self._create_history(db_session, ind, user)
            h.set_definition_translation('fr', 'Définition')
            assert h.definition_translations['fr'] == 'Définition'

    def test_set_definition_translation_init(self, db_session, app):
        """Test initializes dict."""
        with app.app_context():
            user = create_test_user(db_session)
            ind = self._create_indicator(db_session)
            h = self._create_history(db_session, ind, user)
            h.definition_translations = None
            h.set_definition_translation('fr', 'Définition')
            assert isinstance(h.definition_translations, dict)

    def test_set_definition_translation_empty_removes(self, db_session, app):
        """Test empty text removes key."""
        with app.app_context():
            user = create_test_user(db_session)
            ind = self._create_indicator(db_session)
            h = self._create_history(db_session, ind, user, definition_translations={'fr': 'Définition'})
            h.set_definition_translation('fr', '')
            assert 'fr' not in h.definition_translations


@pytest.mark.unit
class TestIndicatorSuggestion:
    """Tests for IndicatorSuggestion model."""

    def _create_suggestion(self, db_session, **kwargs):
        defaults = {
            'submitter_name': 'John Doe',
            'submitter_email': 'john@example.com',
            'indicator_name': 'New Indicator',
            'reason': 'This is needed',
        }
        defaults.update(kwargs)
        s = IndicatorSuggestion(**defaults)
        db_session.add(s)
        db_session.commit()
        db_session.refresh(s)
        return s

    def test_create_suggestion(self, db_session, app):
        """Test creating an indicator suggestion."""
        with app.app_context():
            s = self._create_suggestion(db_session)
            assert s.id is not None
            assert s.submitter_name == 'John Doe'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            s = self._create_suggestion(db_session)
            result = repr(s)
            assert 'IndicatorSuggestion' in result

    def test_is_new_indicator_true(self, db_session, app):
        """Test is_new_indicator is True for new_indicator type."""
        with app.app_context():
            s = self._create_suggestion(
                db_session,
                suggestion_type=IndicatorSuggestionTypeValue.new_indicator.value
            )
            assert s.is_new_indicator is True

    def test_is_new_indicator_false(self, db_session, app):
        """Test is_new_indicator is False for non-new_indicator type."""
        with app.app_context():
            s = self._create_suggestion(
                db_session,
                suggestion_type=IndicatorSuggestionTypeValue.correction.value
            )
            assert s.is_new_indicator is False

    def test_status_display(self, db_session, app):
        """Test status_display returns readable labels."""
        with app.app_context():
            for status, expected in [
                ('pending', 'Pending Review'),
                ('reviewed', 'Under Review'),
                ('approved', 'Approved'),
                ('rejected', 'Rejected'),
                ('implemented', 'Implemented'),
            ]:
                s = self._create_suggestion(db_session, status=status)
                assert s.status_display == expected

    def test_status_display_unknown(self, db_session, app):
        """Test status_display uses title case for unknown status."""
        with app.app_context():
            # Create with 'pending' but check unknown status via mock
            s = self._create_suggestion(db_session)
            # status is stored as enum, simulate unknown by patching
            from unittest.mock import patch
            with patch.object(type(s), 'status', new_callable=lambda: property(lambda self: 'custom_status')):
                result = s.status_display
                assert result == 'Custom Status'

    def test_suggestion_type_display(self, db_session, app):
        """Test suggestion_type_display returns mapped labels."""
        with app.app_context():
            type_map = {
                'correction': 'Correction to existing indicator',
                'improvement': 'Improvement to existing indicator',
                'new_indicator': 'Propose new indicator',
                'other': 'Other',
            }
            for stype, expected in type_map.items():
                s = self._create_suggestion(db_session, suggestion_type=stype)
                assert s.suggestion_type_display == expected


@pytest.mark.unit
class TestSector:
    """Tests for Sector model."""

    def _create_sector(self, db_session, **kwargs):
        import uuid
        defaults = {'name': f'Sector {uuid.uuid4().hex[:6]}'}
        defaults.update(kwargs)
        s = Sector(**defaults)
        db_session.add(s)
        db_session.commit()
        db_session.refresh(s)
        return s

    def test_create_sector(self, db_session, app):
        """Test creating a sector."""
        with app.app_context():
            s = self._create_sector(db_session, name='Health Services')
            assert s.id is not None
            assert s.name == 'Health Services'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            s = self._create_sector(db_session, name='My Sector')
            assert 'My Sector' in repr(s)

    def test_logo_url_with_path(self, db_session, app):
        """Test logo_url returns correct URL."""
        with app.app_context():
            s = self._create_sector(db_session, logo_path='health/logo.png')
            assert '/uploads/sectors/health/logo.png' == s.logo_url

    def test_logo_url_none(self, db_session, app):
        """Test logo_url returns None when no logo_path."""
        with app.app_context():
            s = self._create_sector(db_session)
            assert s.logo_url is None

    def test_get_name_translation(self, db_session, app):
        """Test get_name_translation."""
        with app.app_context():
            s = self._create_sector(db_session, name='Health', name_translations={'fr': 'Santé'})
            assert s.get_name_translation('fr') == 'Santé'
            assert s.get_name_translation('de') == 'Health'

    def test_get_name_translation_none_translations(self, db_session, app):
        """Test get_name_translation with no translations."""
        with app.app_context():
            s = self._create_sector(db_session, name='Health', name_translations=None)
            assert s.get_name_translation('fr') == 'Health'

    def test_get_name_translation_locale_normalization(self, db_session, app):
        """Test locale normalization (fr-FR -> fr)."""
        with app.app_context():
            s = self._create_sector(db_session, name_translations={'fr': 'Santé'})
            assert s.get_name_translation('fr-FR') == 'Santé'

    def test_set_name_translation(self, db_session, app):
        """Test set_name_translation."""
        with app.app_context():
            s = self._create_sector(db_session)
            s.set_name_translation('fr', 'Santé')
            assert s.name_translations['fr'] == 'Santé'

    def test_set_name_translation_en_ignored(self, db_session, app):
        """Test English translation is ignored."""
        with app.app_context():
            s = self._create_sector(db_session)
            s.set_name_translation('en', 'English')
            assert s.name_translations is None or 'en' not in (s.name_translations or {})

    def test_set_name_translation_empty_lang_ignored(self, db_session, app):
        """Test empty language is ignored."""
        with app.app_context():
            s = self._create_sector(db_session)
            s.set_name_translation('', 'Something')
            assert s.name_translations is None

    def test_set_name_translation_empty_text_removes(self, db_session, app):
        """Test empty text removes key."""
        with app.app_context():
            s = self._create_sector(db_session, name_translations={'fr': 'Santé'})
            s.set_name_translation('fr', '')
            assert 'fr' not in (s.name_translations or {})

    def test_set_name_translation_init(self, db_session, app):
        """Test initializes dict."""
        with app.app_context():
            s = self._create_sector(db_session, name_translations=None)
            s.set_name_translation('fr', 'Santé')
            assert isinstance(s.name_translations, dict)

    def test_timestamps_set(self, db_session, app):
        """Test created_at and updated_at set on init."""
        with app.app_context():
            s = self._create_sector(db_session)
            assert s.created_at is not None
            assert s.updated_at is not None


@pytest.mark.unit
class TestSubSector:
    """Tests for SubSector model."""

    def _create_subsector(self, db_session, **kwargs):
        import uuid
        defaults = {'name': f'SubSector {uuid.uuid4().hex[:6]}'}
        defaults.update(kwargs)
        s = SubSector(**defaults)
        db_session.add(s)
        db_session.commit()
        db_session.refresh(s)
        return s

    def test_create_subsector(self, db_session, app):
        """Test creating a sub-sector."""
        with app.app_context():
            s = self._create_subsector(db_session, name='Nutrition Programs')
            assert s.id is not None
            assert s.name == 'Nutrition Programs'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            s = self._create_subsector(db_session, name='My SubSector')
            assert 'My SubSector' in repr(s)

    def test_get_name_translation(self, db_session, app):
        """Test get_name_translation."""
        with app.app_context():
            s = self._create_subsector(db_session, name='Nutrition', name_translations={'fr': 'Nutrition FR'})
            assert s.get_name_translation('fr') == 'Nutrition FR'
            assert s.get_name_translation('de') == 'Nutrition'

    def test_set_name_translation(self, db_session, app):
        """Test set_name_translation."""
        with app.app_context():
            s = self._create_subsector(db_session)
            s.set_name_translation('fr', 'Nutrition FR')
            assert s.name_translations['fr'] == 'Nutrition FR'

    def test_set_name_translation_en_ignored(self, db_session, app):
        """Test English is ignored."""
        with app.app_context():
            s = self._create_subsector(db_session)
            s.set_name_translation('en', 'English')
            assert s.name_translations is None or 'en' not in (s.name_translations or {})

    def test_set_name_translation_empty_lang_ignored(self, db_session, app):
        """Test empty language is ignored."""
        with app.app_context():
            s = self._create_subsector(db_session)
            s.set_name_translation('', 'text')
            assert s.name_translations is None

    def test_set_name_translation_empty_removes(self, db_session, app):
        """Test empty text removes key."""
        with app.app_context():
            s = self._create_subsector(db_session, name_translations={'fr': 'FR'})
            s.set_name_translation('fr', '')
            assert 'fr' not in (s.name_translations or {})

    def test_set_name_translation_init(self, db_session, app):
        """Test initializes dict when None."""
        with app.app_context():
            s = self._create_subsector(db_session, name_translations=None)
            s.set_name_translation('fr', 'FR')
            assert isinstance(s.name_translations, dict)

    def test_timestamps_set(self, db_session, app):
        """Test timestamps are set."""
        with app.app_context():
            s = self._create_subsector(db_session)
            assert s.created_at is not None
            assert s.updated_at is not None


@pytest.mark.unit
class TestCommonWord:
    """Tests for CommonWord model."""

    def _create_word(self, db_session, **kwargs):
        import uuid
        defaults = {
            'term': f'volunteer_{uuid.uuid4().hex[:6]}',
            'meaning': 'A person who works voluntarily.',
        }
        defaults.update(kwargs)
        w = CommonWord(**defaults)
        db_session.add(w)
        db_session.commit()
        db_session.refresh(w)
        return w

    def test_create_word(self, db_session, app):
        """Test creating a common word."""
        with app.app_context():
            w = self._create_word(db_session, term='volunteer', meaning='A volunteer definition')
            assert w.id is not None
            assert w.term == 'volunteer'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            w = self._create_word(db_session, term='testterm')
            assert 'testterm' in repr(w)

    def test_get_meaning_translation(self, db_session, app):
        """Test get_meaning_translation returns translated meaning."""
        with app.app_context():
            w = self._create_word(db_session, meaning_translations={'fr': 'Définition FR'})
            assert w.get_meaning_translation('fr') == 'Définition FR'
            assert w.get_meaning_translation('de') == w.meaning

    def test_set_meaning_translation(self, db_session, app):
        """Test set_meaning_translation sets value."""
        with app.app_context():
            w = self._create_word(db_session)
            w.set_meaning_translation('fr', 'Définition FR')
            assert w.meaning_translations['fr'] == 'Définition FR'

    def test_set_meaning_translation_init(self, db_session, app):
        """Test initializes dict when None."""
        with app.app_context():
            w = self._create_word(db_session, meaning_translations=None)
            w.set_meaning_translation('fr', 'Définition FR')
            assert isinstance(w.meaning_translations, dict)

    def test_set_meaning_translation_empty_removes(self, db_session, app):
        """Test empty text removes key."""
        with app.app_context():
            w = self._create_word(db_session, meaning_translations={'fr': 'Définition FR'})
            w.set_meaning_translation('fr', '')
            assert 'fr' not in w.meaning_translations

    def test_timestamps_set(self, db_session, app):
        """Test created_at/updated_at set on init."""
        with app.app_context():
            w = self._create_word(db_session)
            assert w.created_at is not None
            assert w.updated_at is not None

    def test_with_user(self, db_session, app):
        """Test common word with created_by_user_id."""
        with app.app_context():
            user = create_test_user(db_session)
            w = self._create_word(db_session, created_by_user_id=user.id)
            assert w.created_by_user_id == user.id
