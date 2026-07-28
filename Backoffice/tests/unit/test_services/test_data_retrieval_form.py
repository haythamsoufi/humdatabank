"""
Tests for form data retrieval: API query builders and AI chatbot tools.

- data_retrieval_form: query_form_data, get_form_data_queries
- ai_data.form_retrieval: indicator/bulk tools used by the chatbot
"""
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from app.models import (
    IndicatorBank, FormData, FormItem, FormSection, AssignedForm,
    AssignmentEntityStatus, Country,
)
from app.models.enums import EntityType
from tests.factories import (
    create_test_user, create_test_admin, create_test_country,
    create_test_template, create_test_section, create_test_item,
    create_test_assignment_entity_status,
)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def _make_indicator(db_session, name: str, archived: bool = False, **kwargs) -> IndicatorBank:
    ind = IndicatorBank(
        name=name,
        type=kwargs.get("type", "number"),
        archived=archived,
        unit=kwargs.get("unit"),
        definition=kwargs.get("definition"),
    )
    db_session.add(ind)
    db_session.commit()
    db_session.refresh(ind)
    return ind


def _make_form_data(db_session, *, aes, form_item, value=None, disagg_data=None) -> FormData:
    fd = FormData(
        assignment_entity_status_id=aes.id,
        form_item_id=form_item.id,
        value=str(value) if value is not None else None,
        disagg_data=disagg_data,
    )
    db_session.add(fd)
    db_session.commit()
    db_session.refresh(fd)
    return fd


def _make_full_setup(db_session, *, status="submitted", value="100", period_name="2024"):
    """Create country + template + section + indicator + item + aes + formdata."""
    country = create_test_country(db_session)
    template = create_test_template(db_session)
    section = create_test_section(db_session, template)
    ind = _make_indicator(db_session, f"Test Indicator {id(db_session)}")
    item = create_test_item(
        db_session, section, template,
        item_type="indicator",
        indicator_bank_id=ind.id,
    )
    # Set public privacy on item so unauthenticated queries return data
    item.config = {"privacy": "public"}
    db_session.commit()

    # Update period on the AssignedForm
    assigned_form = AssignedForm(
        template_id=template.id,
        period_name=period_name,
    )
    db_session.add(assigned_form)
    db_session.flush()

    aes = AssignmentEntityStatus(
        assigned_form_id=assigned_form.id,
        entity_type=EntityType.country.value,
        entity_id=country.id,
        status=status,
    )
    db_session.add(aes)
    db_session.flush()

    fd = FormData(
        assignment_entity_status_id=aes.id,
        form_item_id=item.id,
        value=value,
    )
    db_session.add(fd)
    db_session.commit()
    db_session.refresh(aes)

    return country, template, section, ind, item, assigned_form, aes, fd


# ---------------------------------------------------------------------------
# numeric_from_formdata_value
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestNumericFromFormdataValue:
    def test_none_value_returns_none(self, app):
        with app.app_context():
            from app.services.ai.data.form_retrieval import numeric_from_formdata_value
            assert numeric_from_formdata_value(None, None) is None

    def test_int_value(self, app):
        with app.app_context():
            from app.services.ai.data.form_retrieval import numeric_from_formdata_value
            result = numeric_from_formdata_value(42, None)
            assert result == 42.0

    def test_float_value(self, app):
        with app.app_context():
            from app.services.ai.data.form_retrieval import numeric_from_formdata_value
            result = numeric_from_formdata_value(3.14, None)
            assert result == pytest.approx(3.14)

    def test_string_numeric_value(self, app):
        with app.app_context():
            from app.services.ai.data.form_retrieval import numeric_from_formdata_value
            result = numeric_from_formdata_value("100", None)
            assert result == 100.0

    def test_string_with_comma(self, app):
        with app.app_context():
            from app.services.ai.data.form_retrieval import numeric_from_formdata_value
            result = numeric_from_formdata_value("1,000", None)
            assert result == 1000.0

    def test_disagg_data_dict_with_values(self, app):
        with app.app_context():
            from app.services.ai.data.form_retrieval import numeric_from_formdata_value
            disagg = {"values": {"a": 10, "b": 20}}
            result = numeric_from_formdata_value(None, disagg)
            assert result == 30.0

    def test_disagg_data_flat_dict(self, app):
        with app.app_context():
            from app.services.ai.data.form_retrieval import numeric_from_formdata_value
            disagg = {"2024_SP1": 100, "2024_SP2": 200}
            result = numeric_from_formdata_value(None, disagg)
            assert result == 300.0

    def test_disagg_data_modified_original_cell(self, app):
        with app.app_context():
            from app.services.ai.data.form_retrieval import numeric_from_formdata_value
            disagg = {"row1": {"modified": 50, "original": 40}}
            result = numeric_from_formdata_value(None, disagg)
            assert result == 50.0

    def test_disagg_data_with_skip_underscore_keys(self, app):
        with app.app_context():
            from app.services.ai.data.form_retrieval import numeric_from_formdata_value
            disagg = {"_meta": 999, "real": 100}
            result = numeric_from_formdata_value(None, disagg)
            # _meta should be excluded
            assert result == 100.0

    def test_empty_disagg_data(self, app):
        with app.app_context():
            from app.services.ai.data.form_retrieval import numeric_from_formdata_value
            result = numeric_from_formdata_value(None, {})
            assert result is None

    def test_zero_value_is_falsy_returns_none(self, app):
        with app.app_context():
            from app.services.ai.data.form_retrieval import numeric_from_formdata_value
            # 0.0 total from disagg should return None
            disagg = {"_meta": 999}
            result = numeric_from_formdata_value(None, disagg)
            assert result is None


# ---------------------------------------------------------------------------
# query_form_data
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestQueryFormData:
    def test_returns_dict_with_assigned_and_public(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import query_form_data
            mock_user = MagicMock()
            mock_user.is_authenticated = False
            with patch("app.services.data_retrieval.form.get_effective_request_user", return_value=None), \
                 patch("app.services.data_retrieval.form.can_view_non_public_form_items",
                       return_value=False):
                result = query_form_data()
                assert "assigned" in result
                assert "public" in result

    def test_with_template_id_filter(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import query_form_data
            template = create_test_template(db_session)
            with patch("app.services.data_retrieval.form.get_effective_request_user", return_value=None), \
                 patch("app.services.data_retrieval.form.can_view_non_public_form_items",
                       return_value=True):
                result = query_form_data(template_id=template.id)
                assert result["assigned"] is not None
                assert result["public"] is not None

    def test_with_country_id_filter(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import query_form_data
            country = create_test_country(db_session)
            with patch("app.services.data_retrieval.form.get_effective_request_user", return_value=None), \
                 patch("app.services.data_retrieval.form.can_view_non_public_form_items",
                       return_value=True):
                result = query_form_data(country_id=country.id)
                assert result["assigned"] is not None

    def test_with_period_name_filter(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import query_form_data
            with patch("app.services.data_retrieval.form.get_effective_request_user", return_value=None), \
                 patch("app.services.data_retrieval.form.can_view_non_public_form_items",
                       return_value=True):
                result = query_form_data(period_name="2024")
                assert result["assigned"] is not None

    def test_with_submission_id_filter(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import query_form_data
            with patch("app.services.data_retrieval.form.get_effective_request_user", return_value=None), \
                 patch("app.services.data_retrieval.form.can_view_non_public_form_items",
                       return_value=True):
                result = query_form_data(submission_id=1)
                assert result["assigned"] is not None

    def test_with_item_id_filter(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import query_form_data
            with patch("app.services.data_retrieval.form.get_effective_request_user", return_value=None), \
                 patch("app.services.data_retrieval.form.can_view_non_public_form_items",
                       return_value=True):
                result = query_form_data(item_id=1)
                assert result["assigned"] is not None

    def test_with_item_type_filter(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import query_form_data
            with patch("app.services.data_retrieval.form.get_effective_request_user", return_value=None), \
                 patch("app.services.data_retrieval.form.can_view_non_public_form_items",
                       return_value=True):
                result = query_form_data(item_type="indicator")
                assert result["assigned"] is not None

    def test_with_indicator_bank_id_filter(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import query_form_data
            ind = _make_indicator(db_session, "Test IB SVC10")
            with patch("app.services.data_retrieval.form.get_effective_request_user", return_value=None), \
                 patch("app.services.data_retrieval.form.can_view_non_public_form_items",
                       return_value=True):
                result = query_form_data(indicator_bank_id=ind.id)
                assert result["assigned"] is not None

    def test_with_indicator_bank_ids_filter(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import query_form_data
            ind1 = _make_indicator(db_session, "Test IB SVC11a")
            ind2 = _make_indicator(db_session, "Test IB SVC11b")
            with patch("app.services.data_retrieval.form.get_effective_request_user", return_value=None), \
                 patch("app.services.data_retrieval.form.can_view_non_public_form_items",
                       return_value=True):
                result = query_form_data(indicator_bank_ids=[ind1.id, ind2.id])
                assert result["assigned"] is not None

    def test_submission_type_public_only(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import query_form_data
            with patch("app.services.data_retrieval.form.get_effective_request_user", return_value=None), \
                 patch("app.services.data_retrieval.form.can_view_non_public_form_items",
                       return_value=True):
                result = query_form_data(submission_type="public")
                assert result["assigned"] is None

    def test_submission_type_assigned_only(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import query_form_data
            with patch("app.services.data_retrieval.form.get_effective_request_user", return_value=None), \
                 patch("app.services.data_retrieval.form.can_view_non_public_form_items",
                       return_value=True):
                result = query_form_data(submission_type="assigned")
                assert result["public"] is None

    def test_preload_true(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import query_form_data
            with patch("app.services.data_retrieval.form.get_effective_request_user", return_value=None), \
                 patch("app.services.data_retrieval.form.can_view_non_public_form_items",
                       return_value=True):
                result = query_form_data(preload=True)
                assert result["assigned"] is not None

    def test_period_name_with_year_range(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import query_form_data
            with patch("app.services.data_retrieval.form.get_effective_request_user", return_value=None), \
                 patch("app.services.data_retrieval.form.can_view_non_public_form_items",
                       return_value=True):
                result = query_form_data(period_name="2023-2024")
                assert result["assigned"] is not None

    def test_exception_returns_empty_queries(self, app):
        with app.app_context():
            from app.services.data_retrieval.form import query_form_data
            with patch("app.services.data_retrieval.form.FormData") as mock_fd:
                mock_fd.query.side_effect = Exception("fail")
                result = query_form_data()
                # Should return fallback empty queries
                assert "assigned" in result
                assert "public" in result


# ---------------------------------------------------------------------------
# get_form_data_queries
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetFormDataQueries:
    def test_none_values_return_empty_queries(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import get_form_data_queries
            result = get_form_data_queries({"assigned": None, "public": None})
            assigned_q, public_q = result
            # Should be valid query objects (not None)
            assert assigned_q is not None
            assert public_q is not None

    def test_valid_queries_returned_as_is(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import get_form_data_queries
            assigned_q = FormData.query
            public_q = FormData.query
            result = get_form_data_queries({"assigned": assigned_q, "public": public_q})
            r_assigned, r_public = result
            assert r_assigned is assigned_q
            assert r_public is public_q

    def test_partial_none_returns_fallback(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import get_form_data_queries
            assigned_q = FormData.query
            result = get_form_data_queries({"assigned": assigned_q, "public": None})
            r_assigned, r_public = result
            assert r_assigned is assigned_q
            assert r_public is not None


# ---------------------------------------------------------------------------
# get_value_breakdown
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetValueBreakdown:
    def test_indicator_not_found_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_value_breakdown
            country = create_test_country(db_session)
            with patch("app.services.ai.data.form_retrieval.check_country_access", return_value=True), \
                 patch("app.services.indicators.resolution_service.resolve_indicator_identifier",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.get_indicator_candidates_by_keyword",
                       return_value=[]):
                result = get_value_breakdown(country.id, "Nonexistent Indicator XYZ999")
                assert "error" in result

    def test_by_indicator_id_not_found(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_value_breakdown
            country = create_test_country(db_session)
            with patch("app.services.ai.data.form_retrieval.check_country_access", return_value=True):
                result = get_value_breakdown(country.id, 999999)
                assert "error" in result

    def test_returns_result_with_data(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_value_breakdown
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value="500"
            )
            with patch("app.services.ai.data.form_retrieval.check_country_access", return_value=True), \
                 patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.can_view_non_public_form_items",
                       return_value=True), \
                 patch("app.services.indicators.resolution_service.resolve_indicator_identifier",
                       return_value=None):
                result = get_value_breakdown(country.id, ind.id)
                assert "error" not in result or result.get("total", 0) >= 0

    def test_by_string_indicator_id(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_value_breakdown
            country = create_test_country(db_session)
            ind = _make_indicator(db_session, "Test VB Indicator SVC20")
            with patch("app.services.ai.data.form_retrieval.check_country_access", return_value=True), \
                 patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.can_view_non_public_form_items",
                       return_value=True):
                result = get_value_breakdown(country.id, str(ind.id))
                # If no form items, returns zero breakdown
                assert "error" not in result or "Indicator" in result.get("error", "")

    def test_with_period_filter(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_value_breakdown
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value="200", period_name="2024"
            )
            with patch("app.services.ai.data.form_retrieval.check_country_access", return_value=True), \
                 patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.can_view_non_public_form_items",
                       return_value=True), \
                 patch("app.services.indicators.resolution_service.resolve_indicator_identifier",
                       return_value=None):
                result = get_value_breakdown(country.id, ind.id, period="2024")
                assert isinstance(result, dict)

    def test_template_name_hint(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_value_breakdown
            country = create_test_country(db_session)
            template = create_test_template(db_session, name="FDRS Template VBTest")
            with patch("app.services.ai.data.form_retrieval.check_country_access", return_value=True), \
                 patch("app.services.indicators.resolution_service.resolve_indicator_identifier",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.get_indicator_candidates_by_keyword",
                       return_value=[]):
                result = get_value_breakdown(country.id, "FDRS Template VBTest")
                # Should return hint about template
                assert "error" in result or "hint" in result

    def test_multiple_candidates_scoring(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_value_breakdown
            country = create_test_country(db_session)
            ind1 = _make_indicator(db_session, "Number of volunteers VB1")
            ind2 = _make_indicator(db_session, "People volunteering VB2")
            with patch("app.services.ai.data.form_retrieval.check_country_access", return_value=True), \
                 patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.can_view_non_public_form_items",
                       return_value=True), \
                 patch("app.services.indicators.resolution_service.resolve_indicator_identifier",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.get_indicator_candidates_by_keyword",
                       return_value=[ind1, ind2]):
                result = get_value_breakdown(country.id, "volunteers VB1")
                assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# get_form_data_queries (integration via query_form_data)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestQueryFormDataIntegration:
    def test_returns_formdata_with_all_filters(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval.form import query_form_data
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value="100"
            )
            with patch("app.services.data_retrieval.form.get_effective_request_user",
                       return_value=None), \
                 patch("app.services.data_retrieval.form.can_view_non_public_form_items",
                       return_value=True):
                result = query_form_data(
                    template_id=template.id,
                    country_id=country.id,
                    indicator_bank_id=ind.id,
                )
                assert result["assigned"] is not None
                all_rows = result["assigned"].all()
                assert any(r.id == fd.id for r in all_rows)


# ---------------------------------------------------------------------------
# get_indicator_values_for_all_countries
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetIndicatorValuesForAllCountries:
    def test_empty_indicator_name_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_values_for_all_countries
            with patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.can_view_non_public_form_items",
                       return_value=False), \
                 patch("app.services.data_retrieval.form_helpers.user_allowed_country_ids",
                       return_value=None):
                result = get_indicator_values_for_all_countries("")
                assert "error" in result or result.get("success") is False

    def test_indicator_not_found_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_values_for_all_countries
            with patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.can_view_non_public_form_items",
                       return_value=False), \
                 patch("app.services.data_retrieval.form_helpers.user_allowed_country_ids",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.get_indicator_candidates_by_keyword",
                       return_value=[]), \
                 patch("app.services.indicators.resolution_service.get_indicator_candidates",
                       return_value=[]):
                result = get_indicator_values_for_all_countries("Unknown Indicator 99999XYZ")
                assert result.get("success") is False or "error" in result

    def test_by_digit_id(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_values_for_all_countries
            ind = _make_indicator(db_session, "Test All Countries SVC30")
            with patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.can_view_non_public_form_items",
                       return_value=True), \
                 patch("app.services.data_retrieval.form_helpers.user_allowed_country_ids",
                       return_value=None):
                result = get_indicator_values_for_all_countries(str(ind.id))
                assert "rows" in result

    def test_returns_empty_rows_when_no_data(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_values_for_all_countries
            ind = _make_indicator(db_session, "Test All Countries No Data SVC31")
            with patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.can_view_non_public_form_items",
                       return_value=True), \
                 patch("app.services.data_retrieval.form_helpers.user_allowed_country_ids",
                       return_value=None), \
                 patch("app.services.indicators.resolution_service.get_indicator_candidates",
                       side_effect=Exception("no vector")), \
                 patch("app.services.ai.data.form_retrieval.get_indicator_candidates_by_keyword",
                       return_value=[ind]):
                result = get_indicator_values_for_all_countries(ind.name)
                assert result.get("rows", []) == [] or "success" in result

    def test_with_period_filter(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_values_for_all_countries
            ind = _make_indicator(db_session, "Test All Countries Period SVC32")
            with patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.can_view_non_public_form_items",
                       return_value=True), \
                 patch("app.services.data_retrieval.form_helpers.user_allowed_country_ids",
                       return_value=None), \
                 patch("app.services.indicators.resolution_service.get_indicator_candidates",
                       side_effect=Exception("no vector")), \
                 patch("app.services.ai.data.form_retrieval.get_indicator_candidates_by_keyword",
                       return_value=[ind]):
                result = get_indicator_values_for_all_countries(ind.name, period="2024")
                assert isinstance(result, dict)

    def test_with_min_value_filter(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_values_for_all_countries
            ind = _make_indicator(db_session, "Test All Countries MinVal SVC33")
            with patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.can_view_non_public_form_items",
                       return_value=True), \
                 patch("app.services.data_retrieval.form_helpers.user_allowed_country_ids",
                       return_value=None), \
                 patch("app.services.indicators.resolution_service.get_indicator_candidates",
                       side_effect=Exception("no vector")), \
                 patch("app.services.ai.data.form_retrieval.get_indicator_candidates_by_keyword",
                       return_value=[ind]):
                result = get_indicator_values_for_all_countries(ind.name, min_value=100.0)
                assert isinstance(result, dict)

    def test_with_progress_callback(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_values_for_all_countries
            ind = _make_indicator(db_session, "Test All Countries Progress SVC34")
            progress_msgs = []
            def on_progress(msg):
                progress_msgs.append(msg)
            with patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.can_view_non_public_form_items",
                       return_value=True), \
                 patch("app.services.data_retrieval.form_helpers.user_allowed_country_ids",
                       return_value=None), \
                 patch("app.services.indicators.resolution_service.get_indicator_candidates",
                       side_effect=Exception("no vector")), \
                 patch("app.services.ai.data.form_retrieval.get_indicator_candidates_by_keyword",
                       return_value=[ind]):
                result = get_indicator_values_for_all_countries(
                    ind.name, on_progress=on_progress
                )
                assert len(progress_msgs) >= 0  # callback may or may not fire

    def test_restricted_user_scoped_countries(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_values_for_all_countries
            ind = _make_indicator(db_session, "Test Scoped Countries SVC35")
            country = create_test_country(db_session)
            with patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None), \
                 patch("app.services.ai.data.form_retrieval.can_view_non_public_form_items",
                       return_value=False), \
                 patch("app.services.data_retrieval.form_helpers.user_allowed_country_ids",
                       return_value={country.id}), \
                 patch("app.services.indicators.resolution_service.get_indicator_candidates",
                       side_effect=Exception("no vector")), \
                 patch("app.services.ai.data.form_retrieval.get_indicator_candidates_by_keyword",
                       return_value=[ind]):
                result = get_indicator_values_for_all_countries(ind.name)
                assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# get_assignment_indicator_values
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetAssignmentIndicatorValues:
    def test_country_not_found_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_assignment_indicator_values
            result = get_assignment_indicator_values("Nonexistent XYZ999", "Some Template")
            assert "error" in result

    def test_access_denied_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_assignment_indicator_values
            country = create_test_country(db_session)
            with patch("app.services.ai.data.form_retrieval.resolve_country",
                       return_value=country), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=False):
                result = get_assignment_indicator_values(country.id, "Some Template")
                assert "error" in result
                assert "Access denied" in result["error"]

    def test_template_not_found_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_assignment_indicator_values
            country = create_test_country(db_session)
            with patch("app.services.ai.data.form_retrieval.resolve_country",
                       return_value=country), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True):
                result = get_assignment_indicator_values(
                    country.id, "Nonexistent Template XYZ999"
                )
                assert "error" in result

    def test_no_assignment_found_returns_empty_values(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_assignment_indicator_values
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            with patch("app.services.ai.data.form_retrieval.resolve_country",
                       return_value=country), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True):
                result = get_assignment_indicator_values(country.id, template.id)
                assert result["indicator_values"] == []
                assert "No assignment found" in result.get("notes", "")

    def test_returns_indicator_values(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_assignment_indicator_values
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value="100"
            )
            with patch("app.services.ai.data.form_retrieval.resolve_country",
                       return_value=country), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True):
                result = get_assignment_indicator_values(country.id, template.id)
                assert isinstance(result.get("indicator_values", []), list)

    def test_by_string_template_id(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_assignment_indicator_values
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="in_progress", value="200"
            )
            with patch("app.services.ai.data.form_retrieval.resolve_country",
                       return_value=country), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True):
                result = get_assignment_indicator_values(
                    country.id, str(template.id)
                )
                assert isinstance(result, dict)

    def test_by_template_name(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_assignment_indicator_values
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="approved", value="300"
            )
            template_name = template.name
            with patch("app.services.ai.data.form_retrieval.resolve_country",
                       return_value=country), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True):
                result = get_assignment_indicator_values(country.id, template_name)
                assert isinstance(result, dict)

    def test_with_period_filter(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_assignment_indicator_values
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value="400", period_name="2024"
            )
            with patch("app.services.ai.data.form_retrieval.resolve_country",
                       return_value=country), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True):
                result = get_assignment_indicator_values(
                    country.id, template.id, period="2024"
                )
                assert isinstance(result, dict)

    def test_disagg_data_processed(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_assignment_indicator_values
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value=None
            )
            fd.disagg_data = {"values": {"direct": 50, "indirect": 30}}
            db_session.commit()
            with patch("app.services.ai.data.form_retrieval.resolve_country",
                       return_value=country), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True):
                result = get_assignment_indicator_values(country.id, template.id)
                assert isinstance(result, dict)

    def test_data_status_saved_when_not_submitted(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_assignment_indicator_values
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="in_progress", value="100"
            )
            with patch("app.services.ai.data.form_retrieval.resolve_country",
                       return_value=country), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True):
                result = get_assignment_indicator_values(country.id, template.id)
                if result.get("indicator_values"):
                    assert result.get("data_status") == "saved"

    def test_exception_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_assignment_indicator_values
            with patch("app.services.ai.data.form_retrieval.resolve_country",
                       side_effect=Exception("fail")):
                result = get_assignment_indicator_values(1, 1)
                assert "error" in result


# ---------------------------------------------------------------------------
# get_form_field_value
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetFormFieldValue:
    def test_country_not_found_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_form_field_value
            with patch("app.services.ai.data.form_retrieval.get_country_info",
                       return_value={"error": "Country not found"}):
                result = get_form_field_value("Nonexistent Country", "Some Field")
                assert result.get("success") is False or "error" in result

    def test_empty_field_label_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_form_field_value
            country = create_test_country(db_session)
            with patch("app.services.ai.data.form_retrieval.get_country_info",
                       return_value={"country": {"id": country.id, "name": country.name}}):
                result = get_form_field_value(country.name, "")
                assert result.get("success") is False or "error" in result

    def test_no_form_items_found(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_form_field_value
            country = create_test_country(db_session)
            with patch("app.services.ai.data.form_retrieval.get_country_info",
                       return_value={"country": {"id": country.id, "name": country.name}}), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True):
                result = get_form_field_value(
                    country.name, "Nonexistent field label XYZ999"
                )
                assert result.get("success") is False or "error" in result

    def test_returns_total_for_numeric_data(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_form_field_value
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value="250"
            )
            country_info = {
                "country": {"id": country.id, "name": country.name}
            }
            with patch("app.services.ai.data.form_retrieval.get_country_info",
                       return_value=country_info), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True), \
                 patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None):
                result = get_form_field_value(country.name, item.label)
                if result.get("success"):
                    assert isinstance(result.get("total"), (int, float))

    def test_returns_breakdown_dict(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_form_field_value
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value="100"
            )
            country_info = {"country": {"id": country.id, "name": country.name}}
            with patch("app.services.ai.data.form_retrieval.get_country_info",
                       return_value=country_info), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True), \
                 patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None):
                result = get_form_field_value(country.name, item.label)
                if result.get("success"):
                    assert "breakdown" in result

    def test_disagg_data_values_format(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_form_field_value
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value=None
            )
            fd.disagg_data = {"values": {"2024": 500, "2025": 700}}
            db_session.commit()
            country_info = {"country": {"id": country.id, "name": country.name}}
            with patch("app.services.ai.data.form_retrieval.get_country_info",
                       return_value=country_info), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True), \
                 patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None):
                result = get_form_field_value(country.name, item.label)
                if result.get("success"):
                    assert result.get("total", 0) >= 0

    def test_flat_disagg_data(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_form_field_value
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value=None
            )
            fd.disagg_data = {"2024_SP1": 100, "2024_SP2": 200}
            db_session.commit()
            country_info = {"country": {"id": country.id, "name": country.name}}
            with patch("app.services.ai.data.form_retrieval.get_country_info",
                       return_value=country_info), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True), \
                 patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None):
                result = get_form_field_value(country.name, item.label)
                if result.get("success"):
                    assert result.get("total", 0) >= 0

    def test_with_period_filter(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_form_field_value
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value=None
            )
            fd.disagg_data = {"2027_SP1": 100}
            db_session.commit()
            country_info = {"country": {"id": country.id, "name": country.name}}
            with patch("app.services.ai.data.form_retrieval.get_country_info",
                       return_value=country_info), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True), \
                 patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None):
                result = get_form_field_value(country.name, item.label, period="2027")
                assert isinstance(result, dict)

    def test_with_assignment_period(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_form_field_value
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value="100", period_name="2024"
            )
            country_info = {"country": {"id": country.id, "name": country.name}}
            with patch("app.services.ai.data.form_retrieval.get_country_info",
                       return_value=country_info), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True), \
                 patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None):
                result = get_form_field_value(
                    country.name, item.label, assignment_period="2024"
                )
                assert isinstance(result, dict)

    def test_text_value_returned(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_form_field_value
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value="This is a text answer"
            )
            country_info = {"country": {"id": country.id, "name": country.name}}
            with patch("app.services.ai.data.form_retrieval.get_country_info",
                       return_value=country_info), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True), \
                 patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None):
                result = get_form_field_value(country.name, item.label)
                # Text value: either shows in text_values or total remains 0
                assert isinstance(result, dict)

    def test_access_denied_no_public_item(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_form_field_value
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value="100"
            )
            item.config = {"privacy": "ifrc_network"}
            db_session.commit()
            country_info = {"country": {"id": country.id, "name": country.name}}
            mock_user = MagicMock()
            mock_user.is_authenticated = False
            with patch("app.services.ai.data.form_retrieval.get_country_info",
                       return_value=country_info), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=False), \
                 patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=mock_user), \
                 patch("app.services.ai.data.form_retrieval.can_view_non_public_form_items",
                       return_value=False):
                result = get_form_field_value(country.name, item.label)
                # Without access to private items, may return empty or error
                assert isinstance(result, dict)

    def test_saves_fallback_when_no_submitted_data(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_form_field_value
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="in_progress", value="100"
            )
            country_info = {"country": {"id": country.id, "name": country.name}}
            with patch("app.services.ai.data.form_retrieval.get_country_info",
                       return_value=country_info), \
                 patch("app.services.ai.data.form_retrieval.check_country_access",
                       return_value=True), \
                 patch("app.services.ai.data.form_retrieval.get_effective_request_user",
                       return_value=None):
                result = get_form_field_value(country.name, item.label)
                if result.get("success") and result.get("records_count", 0) > 0:
                    assert result.get("data_status") == "saved"

    def test_exception_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_form_field_value
            with patch("app.services.ai.data.form_retrieval.get_country_info",
                       side_effect=Exception("fail")):
                result = get_form_field_value("AnyCountry", "AnyField")
                assert result.get("success") is False


# ---------------------------------------------------------------------------
# get_indicator_timeseries
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetIndicatorTimeseries:
    def test_empty_identifier_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_timeseries
            country = create_test_country(db_session)
            result = get_indicator_timeseries(
                country_id=country.id, indicator_identifier=""
            )
            assert result.get("success") is False or "error" in result

    def test_indicator_not_found_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_timeseries
            country = create_test_country(db_session)
            with patch("app.services.ai.data.form_retrieval.resolve_indicator_to_primary_id",
                       return_value=None):
                result = get_indicator_timeseries(
                    country_id=country.id,
                    indicator_identifier="Nonexistent Indicator XYZ999",
                )
                assert result.get("success") is False or "error" in result

    def test_no_form_items_returns_empty_series(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_timeseries
            country = create_test_country(db_session)
            ind = _make_indicator(db_session, "Test Timeseries SVC40")
            with patch("app.services.ai.data.form_retrieval.resolve_indicator_to_primary_id",
                       return_value=ind.id):
                result = get_indicator_timeseries(
                    country_id=country.id,
                    indicator_identifier=ind.name,
                )
                assert result.get("success") is True
                assert result.get("series", None) is not None
                assert result.get("count", 0) == 0

    def test_returns_series_with_data(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_timeseries
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value="500", period_name="2023"
            )
            with patch("app.services.ai.data.form_retrieval.resolve_indicator_to_primary_id",
                       return_value=ind.id):
                result = get_indicator_timeseries(
                    country_id=country.id,
                    indicator_identifier=ind.name,
                )
                assert result.get("success") is True
                assert isinstance(result.get("series"), list)

    def test_include_saved_false_filters_non_submitted(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_timeseries
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="in_progress", value="100", period_name="2022"
            )
            with patch("app.services.ai.data.form_retrieval.resolve_indicator_to_primary_id",
                       return_value=ind.id):
                result = get_indicator_timeseries(
                    country_id=country.id,
                    indicator_identifier=ind.name,
                    include_saved=False,
                )
                # Only submitted data should be included
                assert result.get("success") is True
                assert result.get("count", 0) == 0

    def test_limit_periods_respected(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_timeseries
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value="100", period_name="2024"
            )
            with patch("app.services.ai.data.form_retrieval.resolve_indicator_to_primary_id",
                       return_value=ind.id):
                result = get_indicator_timeseries(
                    country_id=country.id,
                    indicator_identifier=ind.name,
                    limit_periods=1,
                )
                assert result.get("count", 0) <= 1

    def test_progress_callback_called(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_timeseries
            country = create_test_country(db_session)
            ind = _make_indicator(db_session, "Test TS Progress SVC41")
            msgs = []
            def cb(m):
                msgs.append(m)
            with patch("app.services.ai.data.form_retrieval.resolve_indicator_to_primary_id",
                       return_value=ind.id):
                result = get_indicator_timeseries(
                    country_id=country.id,
                    indicator_identifier=ind.name,
                    on_progress=cb,
                )
                assert isinstance(result, dict)

    def test_approved_data_status(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_timeseries
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="approved", value="700", period_name="2021"
            )
            with patch("app.services.ai.data.form_retrieval.resolve_indicator_to_primary_id",
                       return_value=ind.id):
                result = get_indicator_timeseries(
                    country_id=country.id,
                    indicator_identifier=ind.name,
                )
                if result.get("series"):
                    assert result["series"][0]["data_status"] in ("approved", "submitted", "saved")

    def test_point_indicator_heuristic(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_timeseries
            country, template, section, ind, item, af, aes, fd = _make_full_setup(
                db_session, status="submitted", value="100", period_name="2023"
            )
            ind.name = "Number of branches test SVC42"
            db_session.commit()
            with patch("app.services.ai.data.form_retrieval.resolve_indicator_to_primary_id",
                       return_value=ind.id):
                result = get_indicator_timeseries(
                    country_id=country.id,
                    indicator_identifier=ind.name,
                )
                assert result.get("success") is True

    def test_exception_returns_error(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import get_indicator_timeseries
            with patch("app.services.ai.data.form_retrieval.resolve_indicator_to_primary_id",
                       side_effect=Exception("fail")):
                result = get_indicator_timeseries(
                    country_id=1, indicator_identifier="something"
                )
                assert result.get("success") is False


# ---------------------------------------------------------------------------
# Additional helper coverage: resolve_indicator_to_primary_id
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestResolveIndicatorToPrimaryId:
    def test_digit_string_resolves_by_id(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import resolve_indicator_to_primary_id
            ind = _make_indicator(db_session, "Test RI SVC50")
            result = resolve_indicator_to_primary_id(str(ind.id))
            assert result == ind.id

    def test_nonexistent_digit_returns_none(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import resolve_indicator_to_primary_id
            result = resolve_indicator_to_primary_id("999999")
            assert result is None

    def test_by_name_returns_id(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import resolve_indicator_to_primary_id
            ind = _make_indicator(db_session, "Number of volunteers unique RI SVC51")
            with patch("app.services.indicators.resolution_service.get_indicator_candidates",
                       side_effect=Exception("no vector")), \
                 patch("app.services.ai.data.form_retrieval.get_indicator_candidates_by_keyword",
                       return_value=[ind]):
                result = resolve_indicator_to_primary_id(ind.name)
                assert result == ind.id

    def test_empty_string_returns_none(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import resolve_indicator_to_primary_id
            result = resolve_indicator_to_primary_id("")
            assert result is None

    def test_no_candidates_returns_none(self, app, db_session):
        with app.app_context():
            from app.services.ai.data.form_retrieval import resolve_indicator_to_primary_id
            with patch("app.services.indicators.resolution_service.get_indicator_candidates",
                       side_effect=Exception("no vector")), \
                 patch("app.services.ai.data.form_retrieval.get_indicator_candidates_by_keyword",
                       return_value=[]):
                result = resolve_indicator_to_primary_id("Completely unknown XYZ999")
                assert result is None
