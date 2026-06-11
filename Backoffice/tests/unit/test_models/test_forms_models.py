"""
Comprehensive tests for app/models/forms.py targeting 100% code coverage.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.factories import (
    create_test_user,
    create_test_country,
    create_test_template,
    create_test_section,
    create_test_item,
    create_test_draft_version,
    create_test_assignment_entity_status,
    create_test_public_submission,
)
from app.models.forms import (
    FormTemplate,
    FormTemplateVersion,
    FormPage,
    TemplateShare,
    FormSection,
    DataEntryMixin,
    FormData,
    DynamicIndicatorData,
    RepeatGroupInstance,
    RepeatGroupData,
)
from app.extensions import db


# ---------------------------------------------------------------------------
# FormTemplate
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormTemplate:
    def test_repr(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="My Template")
            result = repr(template)
            assert "My Template" in result

    def test_name_from_published_version(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Published Name")
            assert template.name == "Published Name"

    def test_name_fallback_to_first_version(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="First Version Name")
            # Remove the published_version link
            template.published_version_id = None
            db_session.commit()
            db_session.refresh(template)
            assert template.name == "First Version Name"

    def test_name_unnamed_when_no_versions(self, db_session, app):
        with app.app_context():
            template = FormTemplate()
            db_session.add(template)
            db_session.flush()
            assert template.name == "Unnamed Template"

    def test_name_translations_from_published_version(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Template")
            template.published_version.name_translations = {"fr": "Modèle"}
            db_session.commit()
            db_session.refresh(template)
            assert template.name_translations == {"fr": "Modèle"}

    def test_name_translations_fallback_to_first_version(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Template")
            template.published_version.name_translations = {"es": "Plantilla"}
            template.published_version_id = None
            db_session.commit()
            db_session.refresh(template)
            result = template.name_translations
            assert result is not None

    def test_name_translations_none_when_no_version(self, db_session, app):
        with app.app_context():
            template = FormTemplate()
            db_session.add(template)
            db_session.flush()
            assert template.name_translations is None

    def test_get_name_translation_from_published(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Template")
            template.published_version.name_translations = {"fr": "Modèle"}
            db_session.commit()
            db_session.refresh(template)
            result = template.get_name_translation("fr")
            assert result == "Modèle"

    def test_get_name_translation_fallback_to_first_version(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Template")
            template.published_version.name_translations = {"fr": "Modèle"}
            template.published_version_id = None
            db_session.commit()
            db_session.refresh(template)
            result = template.get_name_translation("fr")
            assert result is not None  # Falls back

    def test_get_name_translation_no_versions(self, db_session, app):
        with app.app_context():
            template = FormTemplate()
            db_session.add(template)
            db_session.flush()
            result = template.get_name_translation("fr")
            assert result == "Unnamed Template"

    def _test_boolean_property(self, db_session, app, prop_name, setter_name=None):
        """Helper to test boolean properties on FormTemplate."""
        with app.app_context():
            template = create_test_template(db_session)
            result_published = getattr(template, prop_name)
            assert isinstance(result_published, bool)

            # Remove published version
            template.published_version_id = None
            db_session.commit()
            db_session.refresh(template)
            result_fallback = getattr(template, prop_name)
            assert isinstance(result_fallback, bool)

    def test_is_paginated(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            assert isinstance(template.is_paginated, bool)

    def test_is_paginated_no_version(self, db_session, app):
        with app.app_context():
            template = FormTemplate()
            db_session.add(template)
            db_session.flush()
            assert template.is_paginated is False

    def test_is_paginated_fallback(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            template.published_version_id = None
            db_session.commit()
            db_session.refresh(template)
            assert isinstance(template.is_paginated, bool)

    def test_display_order_visible(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            assert isinstance(template.display_order_visible, bool)

    def test_display_order_visible_no_version(self, db_session, app):
        with app.app_context():
            template = FormTemplate()
            db_session.add(template)
            db_session.flush()
            assert template.display_order_visible is False

    def test_display_order_visible_fallback(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            template.published_version_id = None
            db_session.commit()
            db_session.refresh(template)
            assert isinstance(template.display_order_visible, bool)

    def test_enable_export_pdf(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            assert isinstance(template.enable_export_pdf, bool)

    def test_enable_export_pdf_no_version(self, db_session, app):
        with app.app_context():
            template = FormTemplate()
            db_session.add(template)
            db_session.flush()
            assert template.enable_export_pdf is False

    def test_enable_export_pdf_fallback(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            template.published_version_id = None
            db_session.commit()
            db_session.refresh(template)
            assert isinstance(template.enable_export_pdf, bool)

    def test_enable_export_excel(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            assert isinstance(template.enable_export_excel, bool)

    def test_enable_export_excel_no_version(self, db_session, app):
        with app.app_context():
            template = FormTemplate()
            db_session.add(template)
            db_session.flush()
            assert template.enable_export_excel is False

    def test_enable_export_excel_fallback(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            template.published_version_id = None
            db_session.commit()
            db_session.refresh(template)
            assert isinstance(template.enable_export_excel, bool)

    def test_enable_import_excel(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            assert isinstance(template.enable_import_excel, bool)

    def test_enable_import_excel_no_version(self, db_session, app):
        with app.app_context():
            template = FormTemplate()
            db_session.add(template)
            db_session.flush()
            assert template.enable_import_excel is False

    def test_enable_import_excel_fallback(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            template.published_version_id = None
            db_session.commit()
            db_session.refresh(template)
            assert isinstance(template.enable_import_excel, bool)

    def test_enable_ai_validation(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            assert isinstance(template.enable_ai_validation, bool)

    def test_enable_ai_validation_no_version(self, db_session, app):
        with app.app_context():
            template = FormTemplate()
            db_session.add(template)
            db_session.flush()
            assert template.enable_ai_validation is False

    def test_enable_ai_validation_fallback(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            template.published_version_id = None
            db_session.commit()
            db_session.refresh(template)
            assert isinstance(template.enable_ai_validation, bool)

    def test_enable_data_quality(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            assert isinstance(template.enable_data_quality, bool)

    def test_enable_data_quality_no_version(self, db_session, app):
        with app.app_context():
            template = FormTemplate()
            db_session.add(template)
            db_session.flush()
            assert template.enable_data_quality is False

    def test_enable_data_quality_fallback(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            template.published_version_id = None
            db_session.commit()
            db_session.refresh(template)
            assert isinstance(template.enable_data_quality, bool)

    def test_data_quality_methodology(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            result = template.data_quality_methodology
            assert result is None or isinstance(result, str)

    def test_data_quality_methodology_no_version(self, db_session, app):
        with app.app_context():
            template = FormTemplate()
            db_session.add(template)
            db_session.flush()
            assert template.data_quality_methodology is None

    def test_data_quality_methodology_fallback(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            template.published_version_id = None
            db_session.commit()
            db_session.refresh(template)
            result = template.data_quality_methodology
            assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# FormTemplateVersion
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormTemplateVersion:
    def test_repr(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            version = template.published_version
            result = repr(version)
            assert "FormTemplateVersion" in result

    def test_get_effective_name_with_name(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Test")
            version = template.published_version
            assert version.get_effective_name() == "Test"

    def test_get_effective_name_none(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            version = template.published_version
            version.name = None
            assert version.get_effective_name() is None

    def test_get_effective_description(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, description="Some description")
            version = template.published_version
            assert version.get_effective_description() == "Some description"

    def test_get_effective_add_to_self_report(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            version = template.published_version
            assert isinstance(version.get_effective_add_to_self_report(), bool)

    def test_get_effective_display_order_visible(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            version = template.published_version
            assert isinstance(version.get_effective_display_order_visible(), bool)

    def test_get_effective_is_paginated(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            version = template.published_version
            assert isinstance(version.get_effective_is_paginated(), bool)

    def test_get_effective_enable_export_pdf(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            version = template.published_version
            assert isinstance(version.get_effective_enable_export_pdf(), bool)

    def test_get_effective_enable_export_excel(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            version = template.published_version
            assert isinstance(version.get_effective_enable_export_excel(), bool)

    def test_get_effective_enable_import_excel(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            version = template.published_version
            assert isinstance(version.get_effective_enable_import_excel(), bool)

    def test_get_effective_enable_ai_validation(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            version = template.published_version
            assert isinstance(version.get_effective_enable_ai_validation(), bool)

    def test_get_effective_enable_data_quality(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            version = template.published_version
            assert isinstance(version.get_effective_enable_data_quality(), bool)

    def test_get_name_translation_found(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Template")
            version = template.published_version
            version.name_translations = {"fr": "Modèle"}
            db_session.commit()
            result = version.get_name_translation("fr")
            assert result == "Modèle"

    def test_get_name_translation_not_found_falls_back(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Template")
            version = template.published_version
            version.name_translations = None
            db_session.commit()
            result = version.get_name_translation("fr")
            assert result == "Template"


# ---------------------------------------------------------------------------
# FormPage
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormPage:
    def _make_page(self, db_session, app, **kwargs):
        with app.app_context():
            template = create_test_template(db_session)
            version = template.published_version
            page = FormPage(
                version_id=version.id,
                template_id=template.id,
                name=kwargs.get("name", "Test Page"),
                order=kwargs.get("order", 1),
                name_translations=kwargs.get("name_translations"),
            )
            db_session.add(page)
            db_session.commit()
            db_session.refresh(page)
            return page

    def test_repr(self, db_session, app):
        with app.app_context():
            page = self._make_page(db_session, app, name="My Page")
            result = repr(page)
            assert "My Page" in result

    def test_get_name_translation_found(self, db_session, app):
        with app.app_context():
            page = self._make_page(db_session, app, name_translations={"fr": "Ma Page"})
            result = page.get_name_translation("fr")
            assert result == "Ma Page"

    def test_get_name_translation_not_found(self, db_session, app):
        with app.app_context():
            page = self._make_page(db_session, app, name="My Page", name_translations={"fr": "Ma Page"})
            result = page.get_name_translation("es")
            assert result == "My Page"

    def test_get_name_translation_no_translations(self, db_session, app):
        with app.app_context():
            page = self._make_page(db_session, app, name="My Page")
            result = page.get_name_translation("fr")
            assert result == "My Page"

    def test_set_name_translation_new(self, db_session, app):
        with app.app_context():
            page = self._make_page(db_session, app, name="My Page")
            page.set_name_translation("fr", "Ma Page")
            assert page.name_translations["fr"] == "Ma Page"

    def test_set_name_translation_overwrite(self, db_session, app):
        with app.app_context():
            page = self._make_page(db_session, app, name_translations={"fr": "Old"})
            page.set_name_translation("fr", "New")
            assert page.name_translations["fr"] == "New"

    def test_set_name_translation_empty_removes_key(self, db_session, app):
        with app.app_context():
            page = self._make_page(db_session, app, name_translations={"fr": "Ma Page"})
            page.set_name_translation("fr", "")
            assert "fr" not in page.name_translations

    def test_set_name_translation_key_not_present_with_empty(self, db_session, app):
        with app.app_context():
            page = self._make_page(db_session, app, name_translations={"en": "My Page"})
            page.set_name_translation("fr", "")
            assert "fr" not in page.name_translations


# ---------------------------------------------------------------------------
# TemplateShare
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTemplateShare:
    def test_repr(self, db_session, app):
        with app.app_context():
            user1 = create_test_user(db_session)
            user2 = create_test_user(db_session)
            template = create_test_template(db_session)
            share = TemplateShare(
                template_id=template.id,
                shared_with_user_id=user2.id,
                shared_by_user_id=user1.id,
            )
            db_session.add(share)
            db_session.commit()
            result = repr(share)
            assert "TemplateShare" in result
            assert str(template.id) in result


# ---------------------------------------------------------------------------
# FormSection
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormSection:
    def test_is_sub_section_false(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            assert section.is_sub_section is False

    def test_is_sub_section_true(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            parent = create_test_section(db_session, template)
            child = create_test_section(
                db_session, template,
                parent_section_id=parent.id
            )
            assert child.is_sub_section is True

    def test_section_type_enum_standard(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template, section_type="standard")
            from app.models.enums import SectionType
            assert section.section_type_enum == SectionType.standard

    def test_section_type_enum_dynamic_indicators(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template, section_type="dynamic_indicators")
            from app.models.enums import SectionType
            assert section.section_type_enum == SectionType.dynamic_indicators

    def test_section_type_enum_repeat(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template, section_type="repeat")
            from app.models.enums import SectionType
            assert section.section_type_enum == SectionType.repeat

    def test_allowed_sectors_list_empty(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            assert section.allowed_sectors_list == []

    def test_allowed_sectors_list_with_data(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.allowed_sectors = ["Health", "Education"]
            assert section.allowed_sectors_list == ["Health", "Education"]

    def test_allowed_sectors_list_not_a_list(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.allowed_sectors = "not a list"
            assert section.allowed_sectors_list == []

    def test_set_allowed_sectors(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.set_allowed_sectors(["Health"])
            assert section.allowed_sectors == ["Health"]

    def test_set_allowed_sectors_none(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.set_allowed_sectors(None)
            assert section.allowed_sectors is None

    def test_indicator_filters_list_empty(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            assert section.indicator_filters_list == []

    def test_indicator_filters_list_with_data(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.indicator_filters = [{"field": "type", "values": ["number"]}]
            assert len(section.indicator_filters_list) == 1

    def test_indicator_filters_list_not_a_list(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.indicator_filters = "not a list"
            assert section.indicator_filters_list == []

    def test_set_indicator_filters(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            filters = [{"field": "type", "op": "eq", "value": "number"}]
            section.set_indicator_filters(filters)
            assert section.indicator_filters == filters

    def test_set_indicator_filters_none(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.set_indicator_filters(None)
            assert section.indicator_filters is None

    def test_allowed_disaggregation_options_list_empty(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            assert section.allowed_disaggregation_options_list == []

    def test_allowed_disaggregation_options_list_with_data(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.allowed_disaggregation_options = ["total", "sex"]
            assert "total" in section.allowed_disaggregation_options_list

    def test_allowed_disaggregation_options_list_not_a_list(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.allowed_disaggregation_options = "not a list"
            assert section.allowed_disaggregation_options_list == []

    def test_set_allowed_disaggregation_options(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.set_allowed_disaggregation_options(["total", "sex"])
            assert "total" in section.allowed_disaggregation_options

    def test_set_allowed_disaggregation_options_none(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.set_allowed_disaggregation_options(None)
            assert section.allowed_disaggregation_options == []

    def test_data_entry_display_filters_list_default(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.data_entry_display_filters = None
            result = section.data_entry_display_filters_list
            assert result == ["sector"]

    def test_data_entry_display_filters_list_with_data(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.data_entry_display_filters = ["sector", "emergency"]
            assert "sector" in section.data_entry_display_filters_list

    def test_data_entry_display_filters_list_not_a_list(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.data_entry_display_filters = "not a list"
            assert section.data_entry_display_filters_list == ["sector"]

    def test_set_data_entry_display_filters(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.set_data_entry_display_filters(["sector"])
            assert section.data_entry_display_filters == ["sector"]

    def test_set_data_entry_display_filters_none(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.set_data_entry_display_filters(None)
            assert section.data_entry_display_filters == []

    def test_depth_level_main(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            assert section.depth_level == 0

    def test_depth_level_sub(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            parent = create_test_section(db_session, template)
            child = create_test_section(db_session, template, parent_section_id=parent.id)
            assert child.depth_level == 1

    def test_display_order(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template, order=3)
            assert section.display_order == "3"

    def test_display_order_invalid(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.order = None
            assert section.display_order == "0"

    def test_get_name_translation(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.name_translations = {"fr": "Section Fr"}
            result = section.get_name_translation("fr")
            assert result == "Section Fr"

    def test_get_name_translation_missing_key(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.name_translations = {"en": "Section En"}
            result = section.get_name_translation("fr")
            assert result is None

    def test_get_name_translation_no_translations(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.name_translations = None
            result = section.get_name_translation("fr")
            assert result is None

    def test_set_name_translation(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.name_translations = None
            section.set_name_translation("fr", "Section Fr")
            assert section.name_translations["fr"] == "Section Fr"

    def test_max_entries_from_config(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.config = {"max_entries": 5}
            assert section.max_entries == 5

    def test_max_entries_none_when_no_config(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.config = None
            assert section.max_entries is None

    def test_set_max_entries(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.config = {}
            section.set_max_entries(10)
            assert section.config["max_entries"] == 10

    def test_set_max_entries_none_removes_key(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.config = {"max_entries": 5}
            section.set_max_entries(None)
            assert "max_entries" not in section.config

    def test_set_max_entries_invalid_value(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.config = {}
            section.set_max_entries("not_a_number")
            assert section.config.get("max_entries") is None

    def test_set_max_entries_none_config(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.config = None
            section.set_max_entries(5)
            assert section.config["max_entries"] == 5

    def test_set_max_entries_non_dict_config(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            section.config = "invalid"
            section.set_max_entries(5)
            assert section.config["max_entries"] == 5

    def test_repr(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template, name="My Section")
            result = repr(section)
            assert "My Section" in result

    def test_repr_with_sub_section(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            parent = create_test_section(db_session, template, name="Parent")
            child = create_test_section(db_session, template, name="Child", parent_section_id=parent.id)
            result = repr(child)
            assert "Child" in result
            assert "Sub" in result


# ---------------------------------------------------------------------------
# DataEntryMixin (via FormData static/class methods - no DB required)
# ---------------------------------------------------------------------------

class TestDataEntryMixinStaticMethods:
    def test_coerce_scalar_text_value_none(self):
        assert DataEntryMixin._coerce_scalar_text_value(None) is None

    def test_coerce_scalar_text_value_empty_string(self):
        assert DataEntryMixin._coerce_scalar_text_value("") is None

    def test_coerce_scalar_text_value_whitespace(self):
        assert DataEntryMixin._coerce_scalar_text_value("   ") is None

    def test_coerce_scalar_text_value_none_string(self):
        assert DataEntryMixin._coerce_scalar_text_value("none") is None

    def test_coerce_scalar_text_value_null_string(self):
        assert DataEntryMixin._coerce_scalar_text_value("null") is None

    def test_coerce_scalar_text_value_undefined_string(self):
        assert DataEntryMixin._coerce_scalar_text_value("undefined") is None

    def test_coerce_scalar_text_value_normal_string(self):
        assert DataEntryMixin._coerce_scalar_text_value("hello") == "hello"

    def test_coerce_scalar_text_value_strips_whitespace(self):
        assert DataEntryMixin._coerce_scalar_text_value("  hello  ") == "hello"

    def test_coerce_scalar_text_value_too_long_raises(self):
        with pytest.raises(ValueError, match="exceeds 255 characters"):
            DataEntryMixin._coerce_scalar_text_value("x" * 256)

    def test_coerce_scalar_text_value_bool_true(self):
        assert DataEntryMixin._coerce_scalar_text_value(True) == "true"

    def test_coerce_scalar_text_value_bool_false(self):
        assert DataEntryMixin._coerce_scalar_text_value(False) == "false"

    def test_coerce_scalar_text_value_integer(self):
        assert DataEntryMixin._coerce_scalar_text_value(42) == "42"

    def test_coerce_scalar_text_value_float(self):
        assert DataEntryMixin._coerce_scalar_text_value(3.14) == "3.14"

    def test_coerce_scalar_text_value_list(self):
        result = DataEntryMixin._coerce_scalar_text_value(["a", "b"])
        import json
        assert json.loads(result) == ["a", "b"]

    def test_coerce_scalar_text_value_list_too_long_raises(self):
        with pytest.raises(ValueError, match="exceeds 255 characters"):
            DataEntryMixin._coerce_scalar_text_value(["x" * 200, "y" * 200])

    def test_coerce_scalar_text_value_dict_raises(self):
        with pytest.raises(ValueError, match="Structured form payloads"):
            DataEntryMixin._coerce_scalar_text_value({"key": "value"})

    def test_coerce_scalar_text_value_other_type(self):
        result = DataEntryMixin._coerce_scalar_text_value(object.__new__(object))
        assert isinstance(result, str)

    def test_parse_numeric_string_none(self):
        assert DataEntryMixin._parse_numeric_string(None) is None

    def test_parse_numeric_string_empty(self):
        assert DataEntryMixin._parse_numeric_string("") is None

    def test_parse_numeric_string_valid(self):
        assert DataEntryMixin._parse_numeric_string("42.5") == 42.5

    def test_parse_numeric_string_integer(self):
        assert DataEntryMixin._parse_numeric_string(100) == 100.0

    def test_parse_numeric_string_invalid(self):
        assert DataEntryMixin._parse_numeric_string("abc") is None

    def test_calculate_disagg_total_direct_dict(self):
        values = {"direct": {"male": 10, "female": 20}, "indirect": 5}
        total = DataEntryMixin._calculate_disagg_total(values)
        assert total == 35

    def test_calculate_disagg_total_direct_scalar(self):
        values = {"direct": 100, "indirect": 50}
        total = DataEntryMixin._calculate_disagg_total(values)
        assert total == 150

    def test_calculate_disagg_total_direct_only(self):
        values = {"direct": 75}
        total = DataEntryMixin._calculate_disagg_total(values)
        assert total == 75

    def test_calculate_disagg_total_no_direct(self):
        values = {"total": 50, "male": 25, "female": 25}
        total = DataEntryMixin._calculate_disagg_total(values)
        assert total == 100

    def test_calculate_disagg_total_excludes_indirect_in_no_direct(self):
        values = {"male": 25, "female": 25, "indirect": 5, "disability": 2}
        total = DataEntryMixin._calculate_disagg_total(values)
        # indirect and disability are excluded from non-direct sums
        assert total == 50

    def test_calculate_disagg_total_non_numeric_values_skipped(self):
        values = {"male": "not_a_number", "female": 25}
        total = DataEntryMixin._calculate_disagg_total(values)
        assert total == 25

    def test_sync_imputed_numeric_value_with_number(self):
        entry = SimpleNamespace(imputed_value=None, imputed_numeric_value=None)
        DataEntryMixin.sync_imputed_numeric_value(entry, 500)
        assert entry.imputed_value == "500"
        assert entry.imputed_numeric_value == 500.0

    def test_sync_imputed_numeric_value_with_none(self):
        entry = SimpleNamespace(imputed_value=None, imputed_numeric_value=None)
        DataEntryMixin.sync_imputed_numeric_value(entry, None)
        assert entry.imputed_value is None
        assert entry.imputed_numeric_value is None


# ---------------------------------------------------------------------------
# DataEntryMixin instance methods (via FormData with DB)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDataEntryMixinInstanceMethods:
    def _create_form_data(self, db_session, app):
        """Create a FormData instance for testing."""
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            template = aes.assigned_form.template
            section = create_test_section(db_session, template)
            item = create_test_item(db_session, section, template, item_type="indicator")

            fd = FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=item.id,
            )
            db_session.add(fd)
            db_session.commit()
            db_session.refresh(fd)
            return fd

    def test_has_disaggregation_false(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.disagg_data = None
            assert fd.has_disaggregation is False

    def test_has_disaggregation_true(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.disagg_data = {"mode": "total", "values": {"total": 10}}
            assert fd.has_disaggregation is True

    def test_disaggregation_mode_none(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.disagg_data = None
            assert fd.disaggregation_mode is None

    def test_disaggregation_mode(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.disagg_data = {"mode": "sex", "values": {}}
            assert fd.disaggregation_mode == "sex"

    def test_total_value_from_value(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = "100"
            fd.data_not_available = False
            fd.not_applicable = False
            fd.disagg_data = None
            assert fd.total_value == "100"

    def test_total_value_from_disagg_data(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = None
            fd.data_not_available = False
            fd.not_applicable = False
            fd.disagg_data = {"mode": "sex", "values": {"male": 30, "female": 20}}
            total = fd.total_value
            assert total == 50

    def test_total_value_none_when_no_data(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = None
            fd.disagg_data = None
            fd.data_not_available = False
            fd.not_applicable = False
            assert fd.total_value is None

    def test_total_value_data_not_available(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = "100"
            fd.data_not_available = True
            fd.disagg_data = None
            assert fd.total_value is None

    def test_get_disaggregated_value(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.disagg_data = {"mode": "sex", "values": {"male": 30}}
            assert fd.get_disaggregated_value("male") == 30

    def test_get_disaggregated_value_none_when_no_disagg(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.disagg_data = None
            assert fd.get_disaggregated_value("male") is None

    def test_get_effective_value(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = "100"
            fd.data_not_available = False
            fd.not_applicable = False
            assert fd.get_effective_value() == "100"

    def test_get_effective_value_data_not_available(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = "100"
            fd.data_not_available = True
            assert fd.get_effective_value() is None

    def test_get_effective_value_not_applicable(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = "100"
            fd.not_applicable = True
            assert fd.get_effective_value() is None

    def test_is_matrix(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.disagg_type = "matrix"
            assert fd.is_matrix is True
            fd.disagg_type = "simple"
            assert fd.is_matrix is False

    def test_set_simple_value(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.set_simple_value("50")
            assert fd.value == "50"
            assert fd.numeric_value == 50.0
            assert fd.disagg_type == "simple"
            assert fd.data_not_available is False
            assert fd.not_applicable is False

    def test_set_simple_value_none(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.set_simple_value(None)
            assert fd.value is None
            assert fd.numeric_value is None
            assert fd.disagg_type is None

    def test_set_disaggregated_data(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.set_disaggregated_data("sex", {"direct": {"male": 30, "female": 20}})
            assert fd.disagg_type == "standard_disagg"
            assert fd.disagg_data is not None
            assert fd.data_not_available is False

    def test_set_disaggregated_data_zero_total(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.set_disaggregated_data("sex", {})
            assert fd.value is None
            assert fd.numeric_value is None

    def test_set_data_availability_not_available(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = "100"
            fd.set_data_availability(data_not_available=True)
            assert fd.data_not_available is True
            assert fd.value is None
            assert fd.not_applicable is False

    def test_set_data_availability_not_applicable(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = "100"
            fd.set_data_availability(not_applicable=True)
            assert fd.not_applicable is True
            assert fd.value is None

    def test_set_data_availability_clear_flags(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.data_not_available = True
            fd.not_applicable = True
            fd.set_data_availability(False, False)
            assert fd.data_not_available is False
            assert fd.not_applicable is False

    def test_has_data_availability_flags(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.data_not_available = True
            fd.not_applicable = False
            assert fd.has_data_availability_flags is True

            fd.data_not_available = False
            fd.not_applicable = False
            assert fd.has_data_availability_flags is False

    def test_is_data_not_available(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.data_not_available = True
            assert fd.is_data_not_available is True

    def test_is_not_applicable(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.not_applicable = True
            assert fd.is_not_applicable is True

    def test_sync_numeric_value_from_string(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = "99.5"
            fd._sync_numeric_value_from_string()
            assert fd.numeric_value == 99.5


# ---------------------------------------------------------------------------
# FormData specific methods
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormDataMethods:
    def _create_form_data(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            template = aes.assigned_form.template
            section = create_test_section(db_session, template)
            item = create_test_item(db_session, section, template, item_type="indicator")
            fd = FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=item.id,
            )
            db_session.add(fd)
            db_session.commit()
            db_session.refresh(fd)
            return fd

    def test_sync_imputed_numeric_value(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            entry = SimpleNamespace(imputed_value=None, imputed_numeric_value=None)
            FormData.sync_imputed_numeric_value(entry, 250.5)
            assert entry.imputed_value == "250.5"
            assert entry.imputed_numeric_value == 250.5

    def test_get_display_value_from_value(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = "42"
            fd.data_not_available = False
            fd.not_applicable = False
            assert fd.get_display_value() == "42"

    def test_get_display_value_from_prefilled(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = None
            fd.prefilled_value = "prefilled_val"
            fd.imputed_value = None
            fd.data_not_available = False
            fd.not_applicable = False
            assert fd.get_display_value() == "prefilled_val"

    def test_get_display_value_from_imputed(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = None
            fd.prefilled_value = None
            fd.imputed_value = "imputed_val"
            fd.data_not_available = False
            fd.not_applicable = False
            assert fd.get_display_value() == "imputed_val"

    def test_get_display_value_none_all(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = None
            fd.prefilled_value = None
            fd.imputed_value = None
            fd.data_not_available = False
            fd.not_applicable = False
            assert fd.get_display_value() is None

    def test_get_display_value_data_not_available(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = "42"
            fd.data_not_available = True
            assert fd.get_display_value() is None

    def test_get_display_disagg_data_from_disagg(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.data_not_available = False
            fd.not_applicable = False
            fd.disagg_data = {"mode": "sex", "values": {}}
            result = fd.get_display_disagg_data()
            assert result == {"mode": "sex", "values": {}}

    def test_get_display_disagg_data_from_prefilled(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.data_not_available = False
            fd.not_applicable = False
            fd.disagg_data = None
            fd.prefilled_disagg_data = {"mode": "age", "values": {}}
            result = fd.get_display_disagg_data()
            assert result == {"mode": "age", "values": {}}

    def test_get_display_disagg_data_from_imputed(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.data_not_available = False
            fd.not_applicable = False
            fd.disagg_data = None
            fd.prefilled_disagg_data = None
            fd.imputed_disagg_data = {"mode": "total", "values": {}}
            result = fd.get_display_disagg_data()
            assert result == {"mode": "total", "values": {}}

    def test_get_display_disagg_data_none(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.data_not_available = False
            fd.not_applicable = False
            fd.disagg_data = None
            fd.prefilled_disagg_data = None
            fd.imputed_disagg_data = None
            assert fd.get_display_disagg_data() is None

    def test_get_display_disagg_data_not_available(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.data_not_available = True
            fd.disagg_data = {"mode": "sex", "values": {}}
            assert fd.get_display_disagg_data() is None

    def test_is_prefilled_true(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = None
            fd.disagg_data = None
            fd.prefilled_value = "some_value"
            assert fd.is_prefilled() is True

    def test_is_prefilled_false_has_value(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = "reported"
            fd.prefilled_value = "prefilled"
            assert fd.is_prefilled() is False

    def test_is_prefilled_false_no_prefilled(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = None
            fd.disagg_data = None
            fd.prefilled_value = None
            fd.prefilled_disagg_data = None
            assert fd.is_prefilled() is False

    def test_repr_with_data(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.value = "100"
            fd.data_not_available = False
            fd.not_applicable = False
            fd.disagg_data = None
            result = repr(fd)
            assert "FormData" in result

    def test_repr_data_not_available(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.data_not_available = True
            result = repr(fd)
            assert "Data Not Available" in result

    def test_repr_not_applicable(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.not_applicable = True
            fd.data_not_available = False
            result = repr(fd)
            assert "Not Applicable" in result

    def test_repr_disagg_data(self, db_session, app):
        with app.app_context():
            fd = self._create_form_data(db_session, app)
            fd.data_not_available = False
            fd.not_applicable = False
            fd.value = None
            fd.disagg_data = {"mode": "sex", "values": {}}
            result = repr(fd)
            assert "Disaggregated" in result

    def test_repr_no_form_item(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            template = aes.assigned_form.template
            section = create_test_section(db_session, template)
            item = create_test_item(db_session, section, template, item_type="indicator")
            fd = FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=item.id,
            )
            db_session.add(fd)
            db_session.commit()
            db_session.refresh(fd)
            fd.form_item = None
            result = repr(fd)
            assert "Item:N/A" in result


# ---------------------------------------------------------------------------
# RepeatGroupInstance / RepeatGroupData repr
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRepeatGroupReprs:
    def test_repeat_group_instance_repr(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            aes = create_test_assignment_entity_status(db_session)
            template = aes.assigned_form.template
            section = create_test_section(db_session, template, section_type="repeat")

            rgi = RepeatGroupInstance(
                assignment_entity_status_id=aes.id,
                section_id=section.id,
                instance_number=1,
                created_by_user_id=user.id,
            )
            db_session.add(rgi)
            db_session.commit()
            result = repr(rgi)
            assert "RepeatGroupInstance" in result
            assert "1" in result

    def test_repeat_group_data_repr_with_item(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            aes = create_test_assignment_entity_status(db_session)
            template = aes.assigned_form.template
            section = create_test_section(db_session, template, section_type="repeat")
            item = create_test_item(db_session, section, template, item_type="indicator")

            rgi = RepeatGroupInstance(
                assignment_entity_status_id=aes.id,
                section_id=section.id,
                instance_number=1,
                created_by_user_id=user.id,
            )
            db_session.add(rgi)
            db_session.flush()

            rgd = RepeatGroupData(
                repeat_instance_id=rgi.id,
                form_item_id=item.id,
            )
            db_session.add(rgd)
            db_session.commit()
            db_session.refresh(rgd)

            result = repr(rgd)
            assert "RepeatGroupData" in result

    def test_repeat_group_data_repr_data_not_available(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            aes = create_test_assignment_entity_status(db_session)
            template = aes.assigned_form.template
            section = create_test_section(db_session, template, section_type="repeat")
            item = create_test_item(db_session, section, template, item_type="indicator")

            rgi = RepeatGroupInstance(
                assignment_entity_status_id=aes.id,
                section_id=section.id,
                instance_number=2,
                created_by_user_id=user.id,
            )
            db_session.add(rgi)
            db_session.flush()

            rgd = RepeatGroupData(
                repeat_instance_id=rgi.id,
                form_item_id=item.id,
                data_not_available=True,
            )
            db_session.add(rgd)
            db_session.commit()

            result = repr(rgd)
            assert "Data Not Available" in result

    def test_repeat_group_data_repr_not_applicable(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            aes = create_test_assignment_entity_status(db_session)
            template = aes.assigned_form.template
            section = create_test_section(db_session, template, section_type="repeat")
            item = create_test_item(db_session, section, template, item_type="indicator")

            rgi = RepeatGroupInstance(
                assignment_entity_status_id=aes.id,
                section_id=section.id,
                instance_number=3,
                created_by_user_id=user.id,
            )
            db_session.add(rgi)
            db_session.flush()

            rgd = RepeatGroupData(
                repeat_instance_id=rgi.id,
                form_item_id=item.id,
                not_applicable=True,
            )
            db_session.add(rgd)
            db_session.commit()

            result = repr(rgd)
            assert "Not Applicable" in result

    def test_repeat_group_data_repr_no_form_item(self, db_session, app):
        with app.app_context():
            user = create_test_user(db_session)
            aes = create_test_assignment_entity_status(db_session)
            template = aes.assigned_form.template
            section = create_test_section(db_session, template, section_type="repeat")
            item = create_test_item(db_session, section, template, item_type="indicator")

            rgi = RepeatGroupInstance(
                assignment_entity_status_id=aes.id,
                section_id=section.id,
                instance_number=4,
                created_by_user_id=user.id,
            )
            db_session.add(rgi)
            db_session.flush()

            rgd = RepeatGroupData(
                repeat_instance_id=rgi.id,
                form_item_id=item.id,
            )
            db_session.add(rgd)
            db_session.commit()
            db_session.refresh(rgd)
            rgd.form_item = None

            result = repr(rgd)
            assert "Item:N/A" in result
