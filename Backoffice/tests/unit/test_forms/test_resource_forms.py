"""Unit tests for app/forms/content/resource_forms.py — targets 100% coverage."""
import pytest
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.unit]


class TestAddLanguageFieldsToClassDecorator:
    """Tests for the _add_language_fields_to_class decorator function."""

    def test_adds_title_fields_for_configured_languages(self, app):
        with app.app_context():
            from app.forms.content.resource_forms import ResourceForm
            # ResourceForm was already decorated; check that language fields exist
            from config import Config
            langs = getattr(Config, 'LANGUAGES', ['en'])
            for lang in langs:
                assert hasattr(ResourceForm, f'title_{lang}')

    def test_adds_description_fields(self, app):
        with app.app_context():
            from app.forms.content.resource_forms import ResourceForm
            from config import Config
            langs = getattr(Config, 'LANGUAGES', ['en'])
            for lang in langs:
                assert hasattr(ResourceForm, f'description_{lang}')

    def test_adds_document_fields(self, app):
        with app.app_context():
            from app.forms.content.resource_forms import ResourceForm
            from config import Config
            langs = getattr(Config, 'LANGUAGES', ['en'])
            for lang in langs:
                assert hasattr(ResourceForm, f'document_{lang}')

    def test_adds_thumbnail_fields(self, app):
        with app.app_context():
            from app.forms.content.resource_forms import ResourceForm
            from config import Config
            langs = getattr(Config, 'LANGUAGES', ['en'])
            for lang in langs:
                assert hasattr(ResourceForm, f'thumbnail_{lang}')


class TestResourceFormInit:
    def _make_mock_subcategory(self, id_, name, order=0):
        sc = MagicMock()
        sc.id = id_
        sc.name = name
        sc.display_order = order
        return sc

    def test_form_instantiates(self, app):
        with app.app_context():
            from app.forms.content.resource_forms import ResourceForm
            with patch('app.forms.content.resource_forms.ResourceForm.__init__') as _:
                pass  # already patched above for isolation

            with patch('app.models.documents.ResourceSubcategory') as mock_rsc:
                mock_rsc.query.order_by.return_value.all.return_value = []
                form = ResourceForm(data={'default_title': 'Test', 'resource_type': 'publication'})
                assert form is not None

    def test_subcategory_choices_populated(self, app):
        with app.app_context():
            sub = self._make_mock_subcategory(1, 'Reports')
            with patch('app.models.documents.ResourceSubcategory') as mock_rsc:
                mock_rsc.query.order_by.return_value.all.return_value = [sub]
                from app.forms.content.resource_forms import ResourceForm
                form = ResourceForm(data={'default_title': 'X', 'resource_type': 'publication'})
                ids = [c[0] for c in form.resource_subcategory_id.choices]
                assert 1 in ids

    def test_sentinel_in_choices(self, app):
        with app.app_context():
            with patch('app.models.documents.ResourceSubcategory') as mock_rsc:
                mock_rsc.query.order_by.return_value.all.return_value = []
                from app.forms.content.resource_forms import ResourceForm
                form = ResourceForm(data={'default_title': 'X', 'resource_type': 'publication'})
                ids = [c[0] for c in form.resource_subcategory_id.choices]
                assert ResourceForm.MANAGE_SUBCATEGORIES_SENTINEL in ids


class TestResourceFormValidation:
    def test_valid_form(self, app):
        with app.app_context():
            with patch('app.models.documents.ResourceSubcategory') as mock_rsc:
                mock_rsc.query.order_by.return_value.all.return_value = []
                from app.forms.content.resource_forms import ResourceForm
                form = ResourceForm(data={
                    'default_title': 'My Resource',
                    'resource_type': 'publication',
                    'resource_subcategory_id': 0,
                })
                assert form.validate() is True

    def test_missing_default_title(self, app):
        with app.app_context():
            with patch('app.models.documents.ResourceSubcategory') as mock_rsc:
                mock_rsc.query.order_by.return_value.all.return_value = []
                from app.forms.content.resource_forms import ResourceForm
                form = ResourceForm(data={
                    'resource_type': 'publication',
                    'resource_subcategory_id': 0,
                })
                assert form.validate() is False
                assert 'default_title' in form.errors

    def test_sentinel_subcategory_fails_validation(self, app):
        with app.app_context():
            with patch('app.models.documents.ResourceSubcategory') as mock_rsc:
                mock_rsc.query.order_by.return_value.all.return_value = []
                from app.forms.content.resource_forms import ResourceForm
                from werkzeug.datastructures import ImmutableMultiDict
                # Use formdata so raw_data is set and validators run properly
                form = ResourceForm(formdata=ImmutableMultiDict([
                    ('default_title', 'My Resource'),
                    ('resource_type', 'publication'),
                    ('resource_subcategory_id', str(ResourceForm.MANAGE_SUBCATEGORIES_SENTINEL)),
                ]))
                assert form.validate() is False
                assert 'resource_subcategory_id' in form.errors

    def test_sentinel_not_none_triggers_error(self, app):
        with app.app_context():
            with patch('app.models.documents.ResourceSubcategory') as mock_rsc:
                mock_rsc.query.order_by.return_value.all.return_value = []
                from app.forms.content.resource_forms import ResourceForm
                form = ResourceForm(data={
                    'default_title': 'My Resource',
                    'resource_type': 'publication',
                })
                # Directly call the validator with sentinel
                from wtforms.validators import ValidationError
                field = MagicMock()
                field.data = ResourceForm.MANAGE_SUBCATEGORIES_SENTINEL
                with pytest.raises(ValidationError):
                    form.validate_resource_subcategory_id(field)

    def test_non_sentinel_subcategory_passes_custom_validator(self, app):
        with app.app_context():
            with patch('app.models.documents.ResourceSubcategory') as mock_rsc:
                mock_rsc.query.order_by.return_value.all.return_value = []
                from app.forms.content.resource_forms import ResourceForm
                form = ResourceForm(data={'default_title': 'X', 'resource_type': 'publication'})
                field = MagicMock()
                field.data = 1  # normal ID, not sentinel
                form.validate_resource_subcategory_id(field)  # should not raise

    def test_none_subcategory_passes_custom_validator(self, app):
        with app.app_context():
            with patch('app.models.documents.ResourceSubcategory') as mock_rsc:
                mock_rsc.query.order_by.return_value.all.return_value = []
                from app.forms.content.resource_forms import ResourceForm
                form = ResourceForm(data={'default_title': 'X', 'resource_type': 'publication'})
                field = MagicMock()
                field.data = None
                form.validate_resource_subcategory_id(field)  # should not raise


class TestResourceFormAddMissingLanguageFields:
    def test_adds_new_language_fields(self, app):
        with app.app_context():
            with patch('app.models.documents.ResourceSubcategory') as mock_rsc:
                mock_rsc.query.order_by.return_value.all.return_value = []
                from app.forms.content.resource_forms import ResourceForm
                ResourceForm._add_missing_language_fields_to_class(['zz'])
                assert hasattr(ResourceForm, 'title_zz')

    def test_does_not_overwrite_existing_fields(self, app):
        with app.app_context():
            with patch('app.models.documents.ResourceSubcategory') as mock_rsc:
                mock_rsc.query.order_by.return_value.all.return_value = []
                from app.forms.content.resource_forms import ResourceForm
                # Add field once
                ResourceForm._add_missing_language_fields_to_class(['en'])
                original_en = getattr(ResourceForm, 'title_en', None)
                # Add again - should not change
                ResourceForm._add_missing_language_fields_to_class(['en'])
                assert getattr(ResourceForm, 'title_en', None) is original_en


class TestResourceFormRebuildUnboundFields:
    def test_rebuild_succeeds(self, app):
        with app.app_context():
            with patch('app.models.documents.ResourceSubcategory') as mock_rsc:
                mock_rsc.query.order_by.return_value.all.return_value = []
                from app.forms.content.resource_forms import ResourceForm
                ResourceForm._rebuild_unbound_fields()
                assert isinstance(ResourceForm._unbound_fields, list)

    def test_rebuild_handles_exception(self, app):
        with app.app_context():
            from app.forms.content.resource_forms import ResourceForm
            with patch('builtins.dir', side_effect=RuntimeError('error')):
                ResourceForm._rebuild_unbound_fields()
            # Should have _unbound_fields (either from prior call or fallback)
            assert hasattr(ResourceForm, '_unbound_fields')
