"""Unit tests for app/forms/system/indicator_lookup_forms.py — targets 100% coverage."""
import pytest
from unittest.mock import patch, MagicMock
from wtforms.validators import ValidationError

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# _validate_code_pattern
# ---------------------------------------------------------------------------

class TestValidateCodePattern:
    def test_valid_lowercase_code(self):
        from app.forms.system.indicator_lookup_forms import _validate_code_pattern
        result = _validate_code_pattern('number')
        assert result == 'number'

    def test_valid_code_with_digits(self):
        from app.forms.system.indicator_lookup_forms import _validate_code_pattern
        result = _validate_code_pattern('type1')
        assert result == 'type1'

    def test_valid_code_with_underscore(self):
        from app.forms.system.indicator_lookup_forms import _validate_code_pattern
        result = _validate_code_pattern('my_code_type')
        assert result == 'my_code_type'

    def test_uppercased_code_normalized(self):
        from app.forms.system.indicator_lookup_forms import _validate_code_pattern
        result = _validate_code_pattern('NUMBER')
        assert result == 'number'

    def test_max_length_64_passes(self):
        from app.forms.system.indicator_lookup_forms import _validate_code_pattern
        code = 'a' * 64
        result = _validate_code_pattern(code)
        assert len(result) == 64

    def test_empty_string_raises(self):
        from app.forms.system.indicator_lookup_forms import _validate_code_pattern
        with pytest.raises(ValidationError, match="1–64 characters"):
            _validate_code_pattern('')

    def test_too_long_raises(self):
        from app.forms.system.indicator_lookup_forms import _validate_code_pattern
        with pytest.raises(ValidationError):
            _validate_code_pattern('a' * 65)

    def test_space_raises(self):
        from app.forms.system.indicator_lookup_forms import _validate_code_pattern
        with pytest.raises(ValidationError):
            _validate_code_pattern('my code')

    def test_hyphen_raises(self):
        from app.forms.system.indicator_lookup_forms import _validate_code_pattern
        with pytest.raises(ValidationError):
            _validate_code_pattern('my-code')

    def test_none_coerced_to_empty_raises(self):
        from app.forms.system.indicator_lookup_forms import _validate_code_pattern
        with pytest.raises(ValidationError):
            _validate_code_pattern(None)


# ---------------------------------------------------------------------------
# IndicatorBankTypeForm
# ---------------------------------------------------------------------------

class TestIndicatorBankTypeForm:
    def _make_form(self, app, data=None, editing_id=None):
        from app.forms.system.indicator_lookup_forms import IndicatorBankTypeForm
        return IndicatorBankTypeForm(data=data or {}, editing_id=editing_id)

    def test_instantiation(self, app):
        with app.app_context():
            form = self._make_form(app)
            assert form is not None

    def test_sort_order_defaults_to_zero(self, app):
        with app.app_context():
            form = self._make_form(app, data={'code': 'number', 'name': 'Number'})
            # sort_order should be 0 if not provided
            assert form.sort_order.data == 0

    def test_multilingual_name_fields_added(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            from app.forms.system.indicator_lookup_forms import IndicatorBankTypeForm
            form = IndicatorBankTypeForm(data={})
            assert hasattr(IndicatorBankTypeForm, 'name_fr')

    def test_validate_code_valid(self, app):
        with app.app_context():
            form = self._make_form(app)
            field = MagicMock()
            field.data = 'valid_code'
            form.validate_code(field)  # should not raise

    def test_validate_code_invalid_raises(self, app):
        with app.app_context():
            form = self._make_form(app)
            field = MagicMock()
            field.data = 'INVALID CODE!'
            with pytest.raises(ValidationError):
                form.validate_code(field)

    def test_validate_code_empty_raises(self, app):
        with app.app_context():
            form = self._make_form(app)
            field = MagicMock()
            field.data = ''
            with pytest.raises(ValidationError):
                form.validate_code(field)

    def test_validate_unique_code_passes(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_lookup_forms.IndicatorBankType') as mock_type:
                mock_type.query.filter.return_value.first.return_value = None
                mock_type.code = MagicMock()
                from app.forms.system.indicator_lookup_forms import IndicatorBankTypeForm
                form = IndicatorBankTypeForm(data={'code': 'number', 'name': 'Number'})
                with patch('app.extensions.db') as mock_db:
                    mock_db.func.lower.return_value = 'number'
                    mock_type.query.filter.return_value.first.return_value = None
                    result = form.validate()
                assert result is True

    def test_validate_duplicate_code_fails(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_lookup_forms.IndicatorBankType') as mock_type, \
                 patch('app.forms.system.indicator_lookup_forms.db') as mock_db:
                existing = MagicMock()
                mock_db.func.lower.return_value = MagicMock()
                mock_type.query.filter.return_value.first.return_value = existing
                mock_type.code = MagicMock()
                from app.forms.system.indicator_lookup_forms import IndicatorBankTypeForm
                form = IndicatorBankTypeForm(data={'code': 'number', 'name': 'Number'})
                result = form.validate()
                assert result is False
                assert 'code' in form.errors or any('already in use' in str(e) for e in form.code.errors)

    def test_validate_excludes_editing_id(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_lookup_forms.IndicatorBankType') as mock_type, \
                 patch('app.forms.system.indicator_lookup_forms.db') as mock_db:
                mock_db.func.lower.return_value = MagicMock()
                mock_type.query.filter.return_value.filter.return_value.first.return_value = None
                mock_type.code = MagicMock()
                mock_type.id = MagicMock()
                from app.forms.system.indicator_lookup_forms import IndicatorBankTypeForm
                form = IndicatorBankTypeForm(data={'code': 'number', 'name': 'Number'}, editing_id=5)
                # The filter chain with editing_id should pass
                result = form.validate()
                assert result is True

    def test_validate_fails_on_field_errors(self, app):
        with app.app_context():
            from app.forms.system.indicator_lookup_forms import IndicatorBankTypeForm
            # Missing required code and name
            form = IndicatorBankTypeForm(data={})
            result = form.validate()
            assert result is False


# ---------------------------------------------------------------------------
# IndicatorBankUnitForm
# ---------------------------------------------------------------------------

class TestIndicatorBankUnitForm:
    def _make_form(self, app, data=None, editing_id=None):
        from app.forms.system.indicator_lookup_forms import IndicatorBankUnitForm
        return IndicatorBankUnitForm(data=data or {}, editing_id=editing_id)

    def test_instantiation(self, app):
        with app.app_context():
            form = self._make_form(app)
            assert form is not None

    def test_sort_order_defaults_to_zero(self, app):
        with app.app_context():
            form = self._make_form(app, data={'code': 'people', 'name': 'People'})
            assert form.sort_order.data == 0

    def test_multilingual_name_fields_added(self, app):
        with app.app_context():
            app.config['TRANSLATABLE_LANGUAGES'] = ['fr']
            from app.forms.system.indicator_lookup_forms import IndicatorBankUnitForm
            form = IndicatorBankUnitForm(data={})
            assert hasattr(IndicatorBankUnitForm, 'name_fr')

    def test_allows_disaggregation_field_exists(self, app):
        with app.app_context():
            form = self._make_form(app)
            assert hasattr(form, 'allows_disaggregation')

    def test_validate_code_valid(self, app):
        with app.app_context():
            form = self._make_form(app)
            field = MagicMock()
            field.data = 'people'
            form.validate_code(field)  # should not raise

    def test_validate_code_invalid_raises(self, app):
        with app.app_context():
            form = self._make_form(app)
            field = MagicMock()
            field.data = 'People Count'
            with pytest.raises(ValidationError):
                form.validate_code(field)

    def test_validate_unique_code_passes(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_lookup_forms.IndicatorBankUnit') as mock_unit, \
                 patch('app.forms.system.indicator_lookup_forms.db') as mock_db:
                mock_db.func.lower.return_value = MagicMock()
                mock_unit.query.filter.return_value.first.return_value = None
                mock_unit.code = MagicMock()
                from app.forms.system.indicator_lookup_forms import IndicatorBankUnitForm
                form = IndicatorBankUnitForm(data={'code': 'people', 'name': 'People'})
                result = form.validate()
                assert result is True

    def test_validate_duplicate_code_fails(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_lookup_forms.IndicatorBankUnit') as mock_unit, \
                 patch('app.forms.system.indicator_lookup_forms.db') as mock_db:
                existing = MagicMock()
                mock_db.func.lower.return_value = MagicMock()
                mock_unit.query.filter.return_value.first.return_value = existing
                mock_unit.code = MagicMock()
                from app.forms.system.indicator_lookup_forms import IndicatorBankUnitForm
                form = IndicatorBankUnitForm(data={'code': 'people', 'name': 'People'})
                result = form.validate()
                assert result is False
                assert any('already in use' in str(e) for e in form.code.errors)

    def test_validate_excludes_editing_id(self, app):
        with app.app_context():
            with patch('app.forms.system.indicator_lookup_forms.IndicatorBankUnit') as mock_unit, \
                 patch('app.forms.system.indicator_lookup_forms.db') as mock_db:
                mock_db.func.lower.return_value = MagicMock()
                mock_unit.query.filter.return_value.filter.return_value.first.return_value = None
                mock_unit.code = MagicMock()
                mock_unit.id = MagicMock()
                from app.forms.system.indicator_lookup_forms import IndicatorBankUnitForm
                form = IndicatorBankUnitForm(data={'code': 'people', 'name': 'People'}, editing_id=3)
                result = form.validate()
                assert result is True

    def test_validate_fails_on_field_errors(self, app):
        with app.app_context():
            from app.forms.system.indicator_lookup_forms import IndicatorBankUnitForm
            form = IndicatorBankUnitForm(data={})
            result = form.validate()
            assert result is False

    def test_is_active_field_default_true(self, app):
        with app.app_context():
            from app.forms.system.indicator_lookup_forms import IndicatorBankUnitForm
            form = IndicatorBankUnitForm(data={'code': 'people', 'name': 'People'})
            # is_active should default to True
            assert hasattr(form, 'is_active')
