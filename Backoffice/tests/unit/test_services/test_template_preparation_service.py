"""
Tests for TemplatePreparationService.

Targets maximum code coverage for app/services/template_preparation_service.py.
"""
import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from app import db
from app.models import FormSection, FormPage
from app.services.template_preparation_service import TemplatePreparationService
from tests.factories import (
    create_test_template,
    create_test_section,
    create_test_item,
)


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

def _make_mock_field(
    id=1,
    order=1,
    is_question=False,
    is_indicator=True,
    is_document_field=False,
    is_required_for_js=False,
    field_type_for_js="NUMBER",
    dynamic_assignment_id=None,
):
    """Build a lightweight mock form field for section status tests."""
    f = MagicMock()
    f.id = id
    f.order = order
    f.is_question = is_question
    f.is_indicator = is_indicator
    f.is_document_field = is_document_field
    f.is_required_for_js = is_required_for_js
    f.field_type_for_js = field_type_for_js
    f.dynamic_assignment_id = dynamic_assignment_id
    return f


def _make_mock_section(
    id=1,
    name="Section 1",
    section_type="standard",
    parent_section_id=None,
    fields_ordered=None,
    indicator_filters_list=None,
):
    """Build a lightweight mock section."""
    s = MagicMock(spec=FormSection)
    s.id = id
    s.name = name
    s.section_type = section_type
    s.parent_section_id = parent_section_id
    s.fields_ordered = fields_ordered if fields_ordered is not None else []
    s.indicator_filters_list = indicator_filters_list or []
    s.page = None
    s.page_id = None
    return s


# ---------------------------------------------------------------------------
# calculate_section_statuses
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCalculateSectionStatuses:
    """Tests for TemplatePreparationService.calculate_section_statuses."""

    def test_section_with_no_items_returns_na(self):
        section = _make_mock_section(name="Empty", fields_ordered=[])
        result = TemplatePreparationService.calculate_section_statuses(
            [section], {}, {}
        )
        assert result["Empty"] == "N/A"

    def test_section_with_no_filled_items_returns_not_started(self):
        field = _make_mock_field(id=10)
        section = _make_mock_section(name="NotStarted", fields_ordered=[field])
        result = TemplatePreparationService.calculate_section_statuses(
            [section], {}, {}
        )
        assert result["NotStarted"] == "Not Started"

    def test_section_fully_filled_returns_completed(self):
        field = _make_mock_field(id=10, is_document_field=False, is_indicator=True)
        section = _make_mock_section(name="Done", fields_ordered=[field])
        # Provide data with a non-empty value
        existing_data = {"field_value[10]": "42"}
        result = TemplatePreparationService.calculate_section_statuses(
            [section], existing_data, {}
        )
        assert result["Done"] == "Completed"

    def test_section_partially_filled_returns_in_progress(self):
        f1 = _make_mock_field(id=11)
        f2 = _make_mock_field(id=12)
        section = _make_mock_section(name="Partial", fields_ordered=[f1, f2])
        existing_data = {"field_value[11]": "5"}
        result = TemplatePreparationService.calculate_section_statuses(
            [section], existing_data, {}
        )
        assert result["Partial"] == "in_progress"

    def test_section_without_fields_ordered_returns_error(self):
        """When fields_ordered is not set at all."""
        section = MagicMock(spec=FormSection)
        section.name = "NoFieldsOrdered"
        # Don't set fields_ordered attribute
        del section.fields_ordered
        result = TemplatePreparationService.calculate_section_statuses(
            [section], {}, {}
        )
        assert result["NoFieldsOrdered"] == "Error: Fields not processed"

    def test_document_field_filled_counts(self):
        """Document fields count as filled when in submitted_documents_dict."""
        field = _make_mock_field(id=20, is_document_field=True, is_required_for_js=False)
        section = _make_mock_section(name="DocFilled", fields_ordered=[field])
        submitted_docs = {"field_value[20]": "doc123"}
        result = TemplatePreparationService.calculate_section_statuses(
            [section], {}, submitted_docs
        )
        assert result["DocFilled"] == "Completed"

    def test_document_field_required_fills_when_in_docs(self):
        """Required document field counts as filled when submitted."""
        field = _make_mock_field(id=21, is_document_field=True, is_required_for_js=True)
        section = _make_mock_section(name="DocReq", fields_ordered=[field])
        submitted_docs = {"field_value[21]": "doc456"}
        result = TemplatePreparationService.calculate_section_statuses(
            [section], {}, submitted_docs
        )
        assert result["DocReq"] == "Completed"

    def test_checkbox_true_value_counts(self):
        """CHECKBOX field with 'true' string counts as filled."""
        field = _make_mock_field(id=30, is_document_field=False, field_type_for_js="CHECKBOX")
        section = _make_mock_section(name="Checkbox", fields_ordered=[field])
        existing_data = {"field_value[30]": "true"}
        result = TemplatePreparationService.calculate_section_statuses(
            [section], existing_data, {}
        )
        assert result["Checkbox"] == "Completed"

    def test_checkbox_true_bool_counts(self):
        """CHECKBOX field with True bool counts as filled."""
        field = _make_mock_field(id=31, is_document_field=False, field_type_for_js="CHECKBOX")
        section = _make_mock_section(name="CheckboxBool", fields_ordered=[field])
        existing_data = {"field_value[31]": True}
        result = TemplatePreparationService.calculate_section_statuses(
            [section], existing_data, {}
        )
        assert result["CheckboxBool"] == "Completed"

    def test_checkbox_false_does_not_count(self):
        """CHECKBOX field with 'false' does not count as filled."""
        field = _make_mock_field(id=32, is_document_field=False, field_type_for_js="CHECKBOX")
        section = _make_mock_section(name="CheckboxFalse", fields_ordered=[field])
        existing_data = {"field_value[32]": "false"}
        result = TemplatePreparationService.calculate_section_statuses(
            [section], existing_data, {}
        )
        assert result["CheckboxFalse"] == "Not Started"

    def test_dict_with_values_key_counts_when_non_empty(self):
        """Disaggregated dict entries with 'values' key count when any value is non-empty."""
        field = _make_mock_field(id=40)
        section = _make_mock_section(name="DictVals", fields_ordered=[field])
        existing_data = {"field_value[40]": {"values": {"r1": "10", "r2": None}}}
        result = TemplatePreparationService.calculate_section_statuses(
            [section], existing_data, {}
        )
        assert result["DictVals"] == "Completed"

    def test_dict_with_values_key_empty_does_not_count(self):
        """Disaggregated dict entries with all None values don't count."""
        field = _make_mock_field(id=41)
        section = _make_mock_section(name="DictValsEmpty", fields_ordered=[field])
        existing_data = {"field_value[41]": {"values": {"r1": None, "r2": None}}}
        result = TemplatePreparationService.calculate_section_statuses(
            [section], existing_data, {}
        )
        assert result["DictValsEmpty"] == "Not Started"

    def test_dynamic_field_uses_dynamic_key(self):
        """Dynamic indicator fields use dynamic_<id> key format."""
        field = _make_mock_field(id=50, dynamic_assignment_id=99)
        section = _make_mock_section(name="Dynamic", fields_ordered=[field])
        existing_data = {"field_value[dynamic_99]": "15"}
        result = TemplatePreparationService.calculate_section_statuses(
            [section], existing_data, {}
        )
        assert result["Dynamic"] == "Completed"

    def test_empty_string_data_does_not_count(self):
        """Empty string data does not count as filled."""
        field = _make_mock_field(id=60)
        section = _make_mock_section(name="EmptyStr", fields_ordered=[field])
        existing_data = {"field_value[60]": "  "}
        result = TemplatePreparationService.calculate_section_statuses(
            [section], existing_data, {}
        )
        assert result["EmptyStr"] == "Not Started"

    def test_multiple_sections(self):
        """Multiple sections are all processed."""
        f1 = _make_mock_field(id=70)
        s1 = _make_mock_section(id=1, name="Sec1", fields_ordered=[f1])
        s2 = _make_mock_section(id=2, name="Sec2", fields_ordered=[])
        existing_data = {"field_value[70]": "5"}
        result = TemplatePreparationService.calculate_section_statuses(
            [s1, s2], existing_data, {}
        )
        assert result["Sec1"] == "Completed"
        assert result["Sec2"] == "N/A"


# ---------------------------------------------------------------------------
# create_mock_assignment_for_preview
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCreateMockAssignmentForPreview:
    def test_returns_mock_acs_with_correct_id(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Preview Mock Template")
            mock_acs = TemplatePreparationService.create_mock_assignment_for_preview(template)
            assert mock_acs.id == 0
            assert mock_acs.status == "Preview Mode"
            assert mock_acs.due_date is None

    def test_mock_acs_has_assigned_form(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Preview Mock AF Template")
            mock_acs = TemplatePreparationService.create_mock_assignment_for_preview(template)
            assert mock_acs.assigned_form is not None
            assert mock_acs.assigned_form.template is template
            assert mock_acs.assigned_form.period_name == "Preview Period"

    def test_mock_acs_country_has_translations(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Preview Country Trans Template")
            mock_acs = TemplatePreparationService.create_mock_assignment_for_preview(template)
            assert mock_acs.country.name == "Preview Country"
            assert "fr" in mock_acs.country.name_translations
            assert "es" in mock_acs.country.name_translations
            assert "ar" in mock_acs.country.name_translations


# ---------------------------------------------------------------------------
# _process_related_programs
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestProcessRelatedPrograms:
    def test_none_input_returns_none(self):
        result = TemplatePreparationService._process_related_programs(None)
        assert result is None

    def test_empty_string_returns_none(self):
        result = TemplatePreparationService._process_related_programs("")
        assert result is None

    def test_single_program_returns_it(self):
        result = TemplatePreparationService._process_related_programs("Health")
        assert result == "Health"

    def test_multiple_programs_returns_first(self):
        result = TemplatePreparationService._process_related_programs("Health, Education, WASH")
        assert result == "Health"

    def test_whitespace_is_stripped(self):
        result = TemplatePreparationService._process_related_programs("  Health  ,  WASH  ")
        assert result == "Health"

    def test_only_commas_returns_none(self):
        result = TemplatePreparationService._process_related_programs(",,,")
        assert result is None


# ---------------------------------------------------------------------------
# _get_indicator_sector_name
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetIndicatorSectorName:
    def test_no_sector_returns_none(self):
        indicator = MagicMock()
        indicator.sector = None
        result = TemplatePreparationService._get_indicator_sector_name(indicator)
        assert result is None

    def test_sector_without_primary_returns_none(self):
        indicator = MagicMock()
        indicator.sector = {"secondary": 99}
        result = TemplatePreparationService._get_indicator_sector_name(indicator)
        assert result is None

    def test_sector_with_primary_but_no_db_record_returns_none(self, db_session, app):
        with app.app_context():
            indicator = MagicMock()
            indicator.sector = {"primary": 999999}
            with patch("app.services.template_preparation_service.Sector") as MockSector:
                MockSector.query.get.return_value = None
                result = TemplatePreparationService._get_indicator_sector_name(indicator)
                assert result is None

    def test_sector_with_primary_and_db_record_returns_name(self, db_session, app):
        with app.app_context():
            indicator = MagicMock()
            indicator.sector = {"primary": 1}
            mock_sector = MagicMock()
            with patch("app.services.template_preparation_service.Sector") as MockSector:
                MockSector.query.get.return_value = mock_sector
                with patch(
                    "app.services.template_preparation_service.get_localized_sector_name",
                    return_value="Health Sector"
                ):
                    result = TemplatePreparationService._get_indicator_sector_name(indicator)
                    assert result == "Health Sector"


# ---------------------------------------------------------------------------
# _get_indicator_subsector_name
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetIndicatorSubsectorName:
    def test_no_sub_sector_returns_none(self):
        indicator = MagicMock()
        indicator.sub_sector = None
        result = TemplatePreparationService._get_indicator_subsector_name(indicator)
        assert result is None

    def test_sub_sector_without_primary_returns_none(self):
        indicator = MagicMock()
        indicator.sub_sector = {}
        result = TemplatePreparationService._get_indicator_subsector_name(indicator)
        assert result is None

    def test_sub_sector_with_primary_but_no_record_returns_none(self, db_session, app):
        with app.app_context():
            indicator = MagicMock()
            indicator.sub_sector = {"primary": 999999}
            with patch("app.services.template_preparation_service.SubSector") as MockSS:
                MockSS.query.get.return_value = None
                result = TemplatePreparationService._get_indicator_subsector_name(indicator)
                assert result is None

    def test_sub_sector_with_primary_and_record_returns_name(self, db_session, app):
        with app.app_context():
            indicator = MagicMock()
            indicator.sub_sector = {"primary": 5}
            mock_ss = MagicMock()
            with patch("app.services.template_preparation_service.SubSector") as MockSS:
                MockSS.query.get.return_value = mock_ss
                with patch(
                    "app.services.template_preparation_service.get_localized_subsector_name",
                    return_value="Prevention"
                ):
                    result = TemplatePreparationService._get_indicator_subsector_name(indicator)
                    assert result == "Prevention"


# ---------------------------------------------------------------------------
# _apply_template_translations
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestApplyTemplateTranslations:
    def test_applies_page_display_name(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="ApplyTrans Template")
            page_mock = MagicMock(spec=FormPage)
            page_mock.id = 1

            section_mock = _make_mock_section()
            section_mock.page = page_mock
            section_mock.page.id = 1

            with patch("app.services.template_preparation_service.FormPage") as MockFP:
                MockFP.query.filter_by.return_value.order_by.return_value.all.return_value = []
                with patch(
                    "app.services.template_preparation_service.get_localized_page_name",
                    return_value="Page EN"
                ) as mock_page_name:
                    with patch(
                        "app.services.template_preparation_service.get_localized_section_name",
                        return_value="Section EN"
                    ):
                        TemplatePreparationService._apply_template_translations(
                            template, [section_mock]
                        )
                        assert section_mock.display_name == "Section EN"

    def test_applies_section_display_name(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="SectionTrans Template")
            section = _make_mock_section()
            section.page = None

            with patch("app.services.template_preparation_service.FormPage") as MockFP:
                MockFP.query.filter_by.return_value.order_by.return_value.all.return_value = []
                with patch(
                    "app.services.template_preparation_service.get_localized_section_name",
                    return_value="My Section"
                ):
                    TemplatePreparationService._apply_template_translations(
                        template, [section]
                    )
                    assert section.display_name == "My Section"

    def test_page_processed_only_once(self, db_session, app):
        """A page referenced by multiple sections should only get display_name set once."""
        with app.app_context():
            template = create_test_template(db_session, name="PageOnce Template")
            shared_page = MagicMock(spec=FormPage)
            shared_page.id = 42

            s1 = _make_mock_section(id=1)
            s1.page = shared_page
            s2 = _make_mock_section(id=2)
            s2.page = shared_page

            with patch("app.services.template_preparation_service.FormPage") as MockFP:
                MockFP.query.filter_by.return_value.order_by.return_value.all.return_value = []
                call_count = {"n": 0}

                def mock_page_name(p):
                    call_count["n"] += 1
                    return "Shared Page"

                with patch(
                    "app.services.template_preparation_service.get_localized_page_name",
                    side_effect=mock_page_name
                ):
                    with patch(
                        "app.services.template_preparation_service.get_localized_section_name",
                        return_value="Sec"
                    ):
                        TemplatePreparationService._apply_template_translations(
                            template, [s1, s2]
                        )
                # Page display_name called once per page ID
                assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# _prepare_available_indicators
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPrepareAvailableIndicators:
    def test_standard_section_gets_empty_list(self, db_session, app):
        with app.app_context():
            section = _make_mock_section(section_type="standard")
            result = TemplatePreparationService._prepare_available_indicators([section])
            assert result[section.id] == []

    def test_dynamic_section_queries_indicators(self, db_session, app):
        with app.app_context():
            section = _make_mock_section(id=5, section_type="dynamic_indicators")
            section.indicator_filters_list = []

            mock_indicator = MagicMock()
            mock_indicator.id = 1
            mock_indicator.type = "Number"
            mock_indicator.unit = "unit"
            mock_indicator.emergency = False
            mock_indicator.related_programs = None
            mock_indicator.sector = None
            mock_indicator.sub_sector = None

            with patch("app.services.template_preparation_service.IndicatorBank") as MockIB:
                query_mock = MagicMock()
                MockIB.query.filter.return_value = query_mock
                query_mock.order_by.return_value.all.return_value = [mock_indicator]

                with patch(
                    "app.services.template_preparation_service.get_localized_indicator_name",
                    return_value="Indicator Name"
                ):
                    with patch(
                        "app.services.template_preparation_service.get_indicator_bank_unit_display",
                        return_value=None
                    ):
                        result = TemplatePreparationService._prepare_available_indicators([section])
                        assert len(result[5]) == 1
                        assert result[5][0]["id"] == 1
                        assert result[5][0]["name"] == "Indicator Name"

    def test_dynamic_section_applies_type_filter(self, db_session, app):
        with app.app_context():
            section = _make_mock_section(id=6, section_type="dynamic_indicators")
            section.indicator_filters_list = [
                {"field": "type", "values": ["Number"]}
            ]

            with patch("app.services.template_preparation_service.IndicatorBank") as MockIB:
                base_q = MagicMock()
                MockIB.query.filter.return_value = base_q
                type_filtered_q = MagicMock()
                base_q.filter.return_value = type_filtered_q
                type_filtered_q.order_by.return_value.all.return_value = []

                result = TemplatePreparationService._prepare_available_indicators([section])
                assert result[6] == []

    def test_dynamic_section_applies_unit_filter(self, db_session, app):
        with app.app_context():
            section = _make_mock_section(id=7, section_type="dynamic_indicators")
            section.indicator_filters_list = [
                {"field": "unit", "values": ["percent"]}
            ]

            with patch("app.services.template_preparation_service.IndicatorBank") as MockIB:
                base_q = MagicMock()
                MockIB.query.filter.return_value = base_q
                filtered_q = MagicMock()
                base_q.filter.return_value = filtered_q
                filtered_q.order_by.return_value.all.return_value = []

                result = TemplatePreparationService._prepare_available_indicators([section])
                assert result[7] == []

    def test_dynamic_section_applies_emergency_filter(self, db_session, app):
        with app.app_context():
            section = _make_mock_section(id=8, section_type="dynamic_indicators")
            section.indicator_filters_list = [
                {"field": "emergency", "values": ["true"]}
            ]

            with patch("app.services.template_preparation_service.IndicatorBank") as MockIB:
                base_q = MagicMock()
                MockIB.query.filter.return_value = base_q
                filtered_q = MagicMock()
                base_q.filter.return_value = filtered_q
                filtered_q.order_by.return_value.all.return_value = []

                result = TemplatePreparationService._prepare_available_indicators([section])
                assert result[8] == []

    def test_dynamic_section_applies_archived_filter(self, db_session, app):
        with app.app_context():
            section = _make_mock_section(id=9, section_type="dynamic_indicators")
            section.indicator_filters_list = [
                {"field": "archived", "values": ["false"]}
            ]

            with patch("app.services.template_preparation_service.IndicatorBank") as MockIB:
                base_q = MagicMock()
                MockIB.query.filter.return_value = base_q
                filtered_q = MagicMock()
                base_q.filter.return_value = filtered_q
                filtered_q.order_by.return_value.all.return_value = []

                result = TemplatePreparationService._prepare_available_indicators([section])
                assert result[9] == []

    def test_filter_with_empty_field_skipped(self, db_session, app):
        with app.app_context():
            section = _make_mock_section(id=10, section_type="dynamic_indicators")
            # Filter with no field/values should be skipped
            section.indicator_filters_list = [
                {"field": "", "values": []}
            ]

            with patch("app.services.template_preparation_service.IndicatorBank") as MockIB:
                base_q = MagicMock()
                MockIB.query.filter.return_value = base_q
                base_q.order_by.return_value.all.return_value = []

                result = TemplatePreparationService._prepare_available_indicators([section])
                assert result[10] == []

    def test_indicator_with_related_programs(self, db_session, app):
        with app.app_context():
            section = _make_mock_section(id=11, section_type="dynamic_indicators")
            section.indicator_filters_list = []

            mock_ind = MagicMock()
            mock_ind.id = 99
            mock_ind.type = "Number"
            mock_ind.unit = "count"
            mock_ind.emergency = True
            mock_ind.related_programs = "Health, Education"
            mock_ind.sector = None
            mock_ind.sub_sector = None

            with patch("app.services.template_preparation_service.IndicatorBank") as MockIB:
                q = MagicMock()
                MockIB.query.filter.return_value = q
                q.order_by.return_value.all.return_value = [mock_ind]

                with patch(
                    "app.services.template_preparation_service.get_localized_indicator_name",
                    return_value="Health Indicator"
                ):
                    with patch(
                        "app.services.template_preparation_service.get_indicator_bank_unit_display",
                        return_value="Count"
                    ):
                        result = TemplatePreparationService._prepare_available_indicators([section])
                        assert result[11][0]["related_programs"] == "Health"

    def test_indicator_emergency_none_returns_none_string(self, db_session, app):
        with app.app_context():
            section = _make_mock_section(id=12, section_type="dynamic_indicators")
            section.indicator_filters_list = []

            mock_ind = MagicMock()
            mock_ind.id = 100
            mock_ind.type = "Text"
            mock_ind.unit = "text"
            mock_ind.emergency = None
            mock_ind.related_programs = None
            mock_ind.sector = None
            mock_ind.sub_sector = None

            with patch("app.services.template_preparation_service.IndicatorBank") as MockIB:
                q = MagicMock()
                MockIB.query.filter.return_value = q
                q.order_by.return_value.all.return_value = [mock_ind]

                with patch(
                    "app.services.template_preparation_service.get_localized_indicator_name",
                    return_value="Text Ind"
                ):
                    with patch(
                        "app.services.template_preparation_service.get_indicator_bank_unit_display",
                        return_value=None
                    ):
                        result = TemplatePreparationService._prepare_available_indicators([section])
                        assert result[12][0]["emergency"] is None


# ---------------------------------------------------------------------------
# _process_section
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestProcessSection:
    def test_process_section_sets_fields_ordered(self, db_session, app):
        with app.app_context():
            section = _make_mock_section()

            mock_fields = [_make_mock_field(id=1), _make_mock_field(id=2)]

            with patch(
                "app.services.template_preparation_service.get_form_items_for_section",
                return_value=mock_fields
            ):
                TemplatePreparationService._process_section(section, None, False)
                assert section.fields_ordered == mock_fields

    def test_process_section_logs_sub_section(self, db_session, app):
        with app.app_context():
            section = _make_mock_section()
            section.parent_section_id = 1
            section.name = "Sub Section"

            with patch(
                "app.services.template_preparation_service.get_form_items_for_section",
                return_value=[_make_mock_field(id=1, is_question=True, is_indicator=False)]
            ):
                # Should not raise
                TemplatePreparationService._process_section(section, None, False)
                assert len(section.fields_ordered) == 1

    def test_process_section_logs_empty_fields(self, db_session, app):
        with app.app_context():
            section = _make_mock_section()
            section.name = "Empty Section"

            with patch(
                "app.services.template_preparation_service.get_form_items_for_section",
                return_value=[]
            ):
                TemplatePreparationService._process_section(section, None, False)
                assert section.fields_ordered == []


# ---------------------------------------------------------------------------
# prepare_template_for_rendering (integration-level, uses real DB)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPrepareTemplateForRendering:
    def test_returns_tuple_of_template_sections_indicators(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="PrepRender Template")

            # Mock all external calls so test is self-contained
            with patch(
                "app.services.template_preparation_service.FormSection"
            ) as MockFS:
                MockFS.query.filter.return_value.order_by.return_value.all.return_value = []
                with patch(
                    "app.services.template_preparation_service.FormItem"
                ) as MockFI:
                    MockFI.query.filter.return_value.order_by.return_value.all.return_value = []
                    with patch(
                        "app.services.template_preparation_service.FormItemProcessor"
                    ):
                        with patch(
                            "app.services.template_preparation_service.FormPage"
                        ) as MockFP:
                            MockFP.query.filter_by.return_value.order_by.return_value.all.return_value = []
                            with patch(
                                "app.services.template_preparation_service.get_localized_section_name",
                                return_value="S"
                            ):
                                result = TemplatePreparationService.prepare_template_for_rendering(
                                    template, None, False
                                )
                                tmpl, sections, avail = result
                                assert tmpl is template
                                assert isinstance(sections, list)
                                assert isinstance(avail, dict)

    def test_prepare_with_real_db_sections(self, db_session, app):
        """Test with real DB sections but mocked item loading."""
        with app.app_context():
            template = create_test_template(db_session, name="PrepRender Real Sections")
            section = create_test_section(db_session, template, name="Real Section", order=1)

            with patch(
                "app.services.template_preparation_service.FormItemProcessor"
            ) as MockFIP:
                MockFIP.setup_form_item_for_template.return_value = MagicMock()
                with patch(
                    "app.services.template_preparation_service.get_form_items_for_section",
                    return_value=[]
                ):
                    with patch(
                        "app.services.template_preparation_service.FormPage"
                    ) as MockFP:
                        MockFP.query.filter_by.return_value.order_by.return_value.all.return_value = []
                        with patch(
                            "app.services.template_preparation_service.get_localized_section_name",
                            return_value="Real Section Display"
                        ):
                            tmpl, sections, avail = TemplatePreparationService.prepare_template_for_rendering(
                                template, None, False
                            )
                            assert tmpl is template
                            assert isinstance(sections, list)

    def test_prepare_with_subsection(self, db_session, app):
        """Sections with parent_section_id are separated into sub_sections_by_parent."""
        with app.app_context():
            template = create_test_template(db_session, name="PrepRender SubSection Template")
            parent = create_test_section(db_session, template, name="Parent Sec", order=1)
            child = create_test_section(
                db_session, template, name="Child Sec", order=2,
                parent_section_id=parent.id
            )

            with patch(
                "app.services.template_preparation_service.FormItemProcessor"
            ) as MockFIP:
                MockFIP.setup_form_item_for_template.return_value = MagicMock()
                with patch(
                    "app.services.template_preparation_service.get_form_items_for_section",
                    return_value=[]
                ):
                    with patch(
                        "app.services.template_preparation_service.FormPage"
                    ) as MockFP:
                        MockFP.query.filter_by.return_value.order_by.return_value.all.return_value = []
                        with patch(
                            "app.services.template_preparation_service.get_localized_section_name",
                            return_value="Section"
                        ):
                            tmpl, sections, avail = TemplatePreparationService.prepare_template_for_rendering(
                                template, None, False
                            )
                            section_ids = [s.id for s in sections]
                            assert parent.id in section_ids
                            assert child.id in section_ids

    def test_prepare_handles_bulk_item_prefetch_failure(self, db_session, app):
        """When bulk FormItem prefetch fails, falls back to per-section loading."""
        with app.app_context():
            template = create_test_template(db_session, name="PrepRender Fallback Template")
            section = create_test_section(db_session, template, name="Fallback Section", order=1)

            with patch(
                "app.services.template_preparation_service.FormItem"
            ) as MockFI:
                # Simulate exception in bulk fetch
                MockFI.query.filter.side_effect = Exception("DB error")
                with patch(
                    "app.services.template_preparation_service.get_form_items_for_section",
                    return_value=[]
                ):
                    with patch(
                        "app.services.template_preparation_service.FormPage"
                    ) as MockFP:
                        MockFP.query.filter_by.return_value.order_by.return_value.all.return_value = []
                        with patch(
                            "app.services.template_preparation_service.get_localized_section_name",
                            return_value="S"
                        ):
                            tmpl, sections, avail = TemplatePreparationService.prepare_template_for_rendering(
                                template, None, False
                            )
                            assert tmpl is template

    def test_prepare_with_verbose_logging(self, db_session, app):
        """Exercises verbose logging branch."""
        with app.app_context():
            app.config["VERBOSE_FORM_DATA_LOGGING"] = True
            template = create_test_template(db_session, name="PrepRender Verbose Template")
            section = create_test_section(db_session, template, name="Verbose Sec", order=1)

            mock_field = _make_mock_field(id=1, is_question=True, is_indicator=False, is_document_field=False)

            with patch(
                "app.services.template_preparation_service.FormItemProcessor"
            ) as MockFIP:
                MockFIP.setup_form_item_for_template.return_value = mock_field
                with patch(
                    "app.services.template_preparation_service.get_form_items_for_section",
                    return_value=[]
                ):
                    with patch(
                        "app.services.template_preparation_service.FormPage"
                    ) as MockFP:
                        MockFP.query.filter_by.return_value.order_by.return_value.all.return_value = []
                        with patch(
                            "app.services.template_preparation_service.get_localized_section_name",
                            return_value="S"
                        ):
                            # Should not raise
                            TemplatePreparationService.prepare_template_for_rendering(
                                template, None, False
                            )
            # Clean up config
            app.config.pop("VERBOSE_FORM_DATA_LOGGING", None)

    def test_prepare_dynamic_section_loads_dynamic_indicators(self, db_session, app):
        """Dynamic indicator sections trigger _process_dynamic_indicators_for_section."""
        with app.app_context():
            template = create_test_template(db_session, name="PrepRender Dynamic Template")
            section = create_test_section(
                db_session, template,
                name="Dynamic Section", order=1,
                section_type="dynamic_indicators"
            )

            mock_acs = MagicMock()
            mock_dyn_field = _make_mock_field(id=200)

            with patch(
                "app.services.template_preparation_service.FormItemProcessor"
            ) as MockFIP:
                MockFIP.setup_form_item_for_template.return_value = MagicMock()
                with patch(
                    "app.services.template_preparation_service._process_dynamic_indicators_for_section",
                    return_value=[mock_dyn_field]
                ):
                    with patch(
                        "app.services.template_preparation_service.FormPage"
                    ) as MockFP:
                        MockFP.query.filter_by.return_value.order_by.return_value.all.return_value = []
                        with patch(
                            "app.services.template_preparation_service.get_localized_section_name",
                            return_value="Dynamic"
                        ):
                            with patch(
                                "app.services.template_preparation_service.IndicatorBank"
                            ) as MockIB:
                                q = MagicMock()
                                MockIB.query.filter.return_value = q
                                q.order_by.return_value.all.return_value = []
                                tmpl, sections, avail = TemplatePreparationService.prepare_template_for_rendering(
                                    template, mock_acs, False
                                )
                                assert tmpl is template

    def test_prepare_dynamic_section_handles_dyn_error(self, db_session, app):
        """When dynamic indicator loading fails, it is logged and not raised."""
        with app.app_context():
            template = create_test_template(db_session, name="PrepRender DynErr Template")
            section = create_test_section(
                db_session, template,
                name="Dyn Error Section", order=1,
                section_type="dynamic_indicators"
            )

            mock_acs = MagicMock()

            with patch(
                "app.services.template_preparation_service.FormItemProcessor"
            ) as MockFIP:
                MockFIP.setup_form_item_for_template.return_value = MagicMock()
                with patch(
                    "app.services.template_preparation_service._process_dynamic_indicators_for_section",
                    side_effect=Exception("Dynamic error")
                ):
                    with patch(
                        "app.services.template_preparation_service.FormPage"
                    ) as MockFP:
                        MockFP.query.filter_by.return_value.order_by.return_value.all.return_value = []
                        with patch(
                            "app.services.template_preparation_service.get_localized_section_name",
                            return_value="S"
                        ):
                            with patch(
                                "app.services.template_preparation_service.IndicatorBank"
                            ) as MockIB:
                                q = MagicMock()
                                MockIB.query.filter.return_value = q
                                q.order_by.return_value.all.return_value = []
                                # Should not raise
                                result = TemplatePreparationService.prepare_template_for_rendering(
                                    template, mock_acs, False
                                )
                                assert result[0] is template
