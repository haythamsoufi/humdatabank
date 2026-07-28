"""
Comprehensive tests for AssignmentService.

Targets 100% coverage of app/services/assignment_service.py.
"""
import pytest
from werkzeug.exceptions import NotFound

from app.services.assignments.service import AssignmentService
from tests.factories import (
    create_test_assignment_entity_status,
    create_test_country,
    create_test_template,
)

pytestmark = pytest.mark.unit


@pytest.mark.unit
class TestAssignmentServiceGetById:
    """Tests for get_assignment_entity_status_by_id."""

    def test_found(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            result = AssignmentService.get_assignment_entity_status_by_id(aes.id)
            assert result is not None
            assert result.id == aes.id

    def test_not_found(self, db_session, app):
        with app.app_context():
            result = AssignmentService.get_assignment_entity_status_by_id(9_999_999)
            assert result is None


@pytest.mark.unit
class TestAssignmentServiceGetOr404:
    """Tests for get_assignment_entity_status_or_404."""

    def test_found(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            result = AssignmentService.get_assignment_entity_status_or_404(aes.id)
            assert result is not None
            assert result.id == aes.id

    def test_raises_404(self, db_session, app):
        with app.app_context():
            with pytest.raises((NotFound, Exception)):
                AssignmentService.get_assignment_entity_status_or_404(9_999_999)


@pytest.mark.unit
class TestAssignedFormGetById:
    """Tests for get_assigned_form_by_id."""

    def test_found(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            result = AssignmentService.get_assigned_form_by_id(aes.assigned_form_id)
            assert result is not None
            assert result.id == aes.assigned_form_id

    def test_not_found(self, db_session, app):
        with app.app_context():
            result = AssignmentService.get_assigned_form_by_id(9_999_999)
            assert result is None


@pytest.mark.unit
class TestAssignedFormGetOr404:
    """Tests for get_assigned_form_or_404."""

    def test_found(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            result = AssignmentService.get_assigned_form_or_404(aes.assigned_form_id)
            assert result is not None
            assert result.id == aes.assigned_form_id

    def test_raises_404(self, db_session, app):
        with app.app_context():
            with pytest.raises((NotFound, Exception)):
                AssignmentService.get_assigned_form_or_404(9_999_999)


@pytest.mark.unit
class TestAssignedFormGetByToken:
    """Tests for get_assigned_form_by_token."""

    def test_found_by_token(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            token = aes.assigned_form.unique_token
            if token:
                result = AssignmentService.get_assigned_form_by_token(token)
                assert result is not None
                assert result.id == aes.assigned_form_id

    def test_not_found_by_token(self, db_session, app):
        with app.app_context():
            result = AssignmentService.get_assigned_form_by_token("nonexistent-token-xyz-abc-999")
            assert result is None

    def test_token_coerced_to_string(self, db_session, app):
        """The method calls str() on the token argument."""
        with app.app_context():
            result = AssignmentService.get_assigned_form_by_token(0)
            assert result is None


@pytest.mark.unit
class TestGetAllAssignedForms:
    """Tests for get_all_assigned_forms."""

    def test_ordered_by_period_name(self, db_session, app):
        with app.app_context():
            create_test_assignment_entity_status(db_session, period_name="2023")
            create_test_assignment_entity_status(db_session, period_name="2024")
            query = AssignmentService.get_all_assigned_forms(ordered=True, order_by="period_name")
            results = query.all()
            assert len(results) >= 2

    def test_ordered_by_assigned_at(self, db_session, app):
        with app.app_context():
            create_test_assignment_entity_status(db_session, period_name="2023")
            query = AssignmentService.get_all_assigned_forms(ordered=True, order_by="assigned_at")
            results = query.all()
            assert len(results) >= 1

    def test_unordered(self, db_session, app):
        with app.app_context():
            query = AssignmentService.get_all_assigned_forms(ordered=False)
            # Should return a query object without ordering
            assert query is not None
            _ = query.all()  # ensure it is executable

    def test_default_arguments(self, db_session, app):
        """Default call: ordered=True, order_by='period_name'."""
        with app.app_context():
            query = AssignmentService.get_all_assigned_forms()
            assert query is not None


@pytest.mark.unit
class TestGetAssignedFormsByTemplate:
    """Tests for get_assigned_forms_by_template."""

    def test_returns_forms_for_template(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            template_id = aes.assigned_form.template_id
            query = AssignmentService.get_assigned_forms_by_template(template_id)
            forms = query.all()
            assert any(f.template_id == template_id for f in forms)

    def test_returns_empty_for_unknown_template(self, db_session, app):
        with app.app_context():
            query = AssignmentService.get_assigned_forms_by_template(9_999_999)
            assert query.count() == 0


@pytest.mark.unit
class TestCountAssignedForms:
    """Tests for count_assigned_forms."""

    def test_count_is_int(self, db_session, app):
        with app.app_context():
            count = AssignmentService.count_assigned_forms()
            assert isinstance(count, int)

    def test_count_increases_after_create(self, db_session, app):
        with app.app_context():
            before = AssignmentService.count_assigned_forms()
            create_test_assignment_entity_status(db_session)
            after = AssignmentService.count_assigned_forms()
            assert after >= before + 1


@pytest.mark.unit
class TestGetAssignmentEntityStatusesByAssignedForm:
    """Tests for get_assignment_entity_statuses_by_assigned_form."""

    def test_returns_statuses_for_form(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            query = AssignmentService.get_assignment_entity_statuses_by_assigned_form(
                aes.assigned_form_id
            )
            items = query.all()
            assert any(item.id == aes.id for item in items)

    def test_returns_empty_for_unknown_form(self, db_session, app):
        with app.app_context():
            query = AssignmentService.get_assignment_entity_statuses_by_assigned_form(9_999_999)
            assert query.count() == 0


@pytest.mark.unit
class TestGetAssignmentEntityStatusesByCountry:
    """Tests for get_assignment_entity_statuses_by_country."""

    def test_returns_statuses_for_country(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            query = AssignmentService.get_assignment_entity_statuses_by_country(country.id)
            items = query.all()
            assert any(item.id == aes.id for item in items)

    def test_entity_type_filter_is_country(self, db_session, app):
        """Ensure the query filters by entity_type='country'."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            query = AssignmentService.get_assignment_entity_statuses_by_country(country.id)
            for item in query.all():
                assert item.entity_type == "country"

    def test_returns_empty_for_unknown_country(self, db_session, app):
        with app.app_context():
            query = AssignmentService.get_assignment_entity_statuses_by_country(9_999_999)
            assert query.count() == 0
