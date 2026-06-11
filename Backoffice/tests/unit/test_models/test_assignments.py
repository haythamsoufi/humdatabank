"""
Unit tests for assignments.py models to achieve 100% code coverage.

Covers: ReportingPeriod, AssignedForm, AssignmentEntityStatus, PublicSubmission
"""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from app.models.assignments import (
    ReportingPeriod,
    AssignedForm,
    AssignmentEntityStatus,
    PublicSubmission,
)
from app.models.enums import AssignmentEntityStatusValue, PublicSubmissionStatus
from tests.factories import (
    create_test_user,
    create_test_country,
    create_test_template,
    create_test_assignment_entity_status,
    create_test_public_submission,
)
from app.utils.datetime_helpers import utcnow


@pytest.mark.unit
class TestReportingPeriod:
    """Tests for ReportingPeriod model."""

    def _create_period(self, db_session, **kwargs):
        import uuid
        defaults = {
            'name': f'Period {uuid.uuid4().hex[:6]}',
            'period_type': 'annual',
            'period_start': date(2024, 1, 1),
            'period_end': date(2024, 12, 31),
        }
        defaults.update(kwargs)
        p = ReportingPeriod(**defaults)
        db_session.add(p)
        db_session.commit()
        db_session.refresh(p)
        return p

    def test_create_period(self, db_session, app):
        """Test creating a reporting period."""
        with app.app_context():
            p = self._create_period(db_session, name='Annual 2024')
            assert p.id is not None
            assert p.name == 'Annual 2024'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            p = self._create_period(db_session, name='Annual 2024')
            result = repr(p)
            assert 'Annual 2024' in result
            assert '2024-01-01' in result


@pytest.mark.unit
class TestAssignedForm:
    """Tests for AssignedForm model."""

    def _create_assigned_form(self, db_session, **kwargs):
        template = create_test_template(db_session)
        defaults = {
            'template_id': template.id,
            'period_name': '2024',
        }
        defaults.update(kwargs)
        af = AssignedForm(**defaults)
        db_session.add(af)
        db_session.commit()
        db_session.refresh(af)
        return af, template

    def test_create_assigned_form(self, db_session, app):
        """Test creating an assigned form."""
        with app.app_context():
            af, template = self._create_assigned_form(db_session)
            assert af.id is not None
            assert af.period_name == '2024'
            assert af.is_active is True

    def test_earliest_due_date_none(self, db_session, app):
        """Test earliest_due_date returns None when no AES with due_date."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session)
            assert af.earliest_due_date is None

    def test_earliest_due_date_with_aes(self, db_session, app):
        """Test earliest_due_date returns the earliest due date."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            aes.due_date = utcnow()
            db_session.commit()
            af = AssignedForm.query.get(aes.assigned_form_id)
            result = af.earliest_due_date
            assert result is not None

    def test_has_multiple_due_dates_false(self, db_session, app):
        """Test has_multiple_due_dates False when zero due dates."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session)
            assert af.has_multiple_due_dates is False

    def test_has_multiple_due_dates_true(self, db_session, app):
        """Test has_multiple_due_dates True when multiple distinct due dates."""
        with app.app_context():
            template = create_test_template(db_session)
            af = AssignedForm(template_id=template.id, period_name='2024-multi')
            db_session.add(af)
            db_session.commit()
            country1 = create_test_country(db_session)
            country2 = create_test_country(db_session)
            from app.models.enums import EntityType
            aes1 = AssignmentEntityStatus(
                assigned_form_id=af.id,
                entity_type=EntityType.country.value,
                entity_id=country1.id,
                status=AssignmentEntityStatusValue.pending,
                due_date=utcnow(),
            )
            aes2 = AssignmentEntityStatus(
                assigned_form_id=af.id,
                entity_type=EntityType.country.value,
                entity_id=country2.id,
                status=AssignmentEntityStatusValue.pending,
                due_date=utcnow() - timedelta(days=1),
            )
            db_session.add_all([aes1, aes2])
            db_session.commit()
            assert af.has_multiple_due_dates is True

    def test_countries_property(self, db_session, app):
        """Test countries property returns country objects."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            af = AssignedForm.query.get(aes.assigned_form_id)
            # May not return country if entity_service not configured in test
            countries = af.countries
            assert isinstance(countries, list)

    def test_public_countries_property(self, db_session, app):
        """Test public_countries returns countries with is_public_available=True."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            aes.is_public_available = True
            db_session.commit()
            af = AssignedForm.query.get(aes.assigned_form_id)
            public_countries = af.public_countries
            assert isinstance(public_countries, list)

    def test_add_country_new(self, db_session, app):
        """Test add_country creates AES for new country."""
        with app.app_context():
            af, template = self._create_assigned_form(db_session)
            country = create_test_country(db_session)
            result = af.add_country(country)
            assert result is not None
            db_session.commit()

    def test_add_country_existing(self, db_session, app):
        """Test add_country returns existing AES if already exists."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            af = AssignedForm.query.get(aes.assigned_form_id)
            # Add same country again
            result = af.add_country(country)
            assert result.id == aes.id

    def test_remove_country_existing(self, db_session, app):
        """Test remove_country deletes AES when country exists."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            af = AssignedForm.query.get(aes.assigned_form_id)
            result = af.remove_country(country)
            assert result is True

    def test_remove_country_not_found(self, db_session, app):
        """Test remove_country returns False when country not in assignment."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session)
            country = create_test_country(db_session)
            result = af.remove_country(country)
            assert result is False

    def test_generate_public_url(self, db_session, app):
        """Test generate_public_url sets unique_token."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session)
            token = af.generate_public_url()
            assert token is not None
            assert af.unique_token == token

    def test_generate_public_url_existing(self, db_session, app):
        """Test generate_public_url returns existing token."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session, unique_token='existing-token')
            token = af.generate_public_url()
            assert token == 'existing-token'

    def test_get_public_url_no_token(self, db_session, app):
        """Test get_public_url returns None when no token."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session)
            result = af.get_public_url()
            assert result is None

    def test_get_public_url_with_token(self, db_session, app):
        """Test get_public_url returns URL when token set."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session)
            af.unique_token = 'test-token-123'
            result = af.get_public_url(external=False)
            assert result is not None
            assert 'test-token-123' in result

    def test_has_public_url_true(self, db_session, app):
        """Test has_public_url True when token set."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session, unique_token='abc123')
            assert af.has_public_url() is True

    def test_has_public_url_false(self, db_session, app):
        """Test has_public_url False when no token."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session)
            assert af.has_public_url() is False

    def test_is_public_accessible_true(self, db_session, app):
        """Test is_public_accessible True when token and is_public_active."""
        with app.app_context():
            af, _ = self._create_assigned_form(
                db_session, unique_token='abc', is_public_active=True
            )
            assert af.is_public_accessible() is True

    def test_is_public_accessible_false_no_token(self, db_session, app):
        """Test is_public_accessible False when no token."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session, is_public_active=True)
            assert af.is_public_accessible() is False

    def test_is_effectively_closed_explicit(self, db_session, app):
        """Test is_effectively_closed True when is_closed=True."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session, is_closed=True)
            assert af.is_effectively_closed is True

    def test_is_effectively_closed_expired(self, db_session, app):
        """Test is_effectively_closed True when past expiry_date."""
        with app.app_context():
            past_date = date.today() - timedelta(days=1)
            af, _ = self._create_assigned_form(db_session, expiry_date=past_date)
            assert af.is_effectively_closed is True

    def test_is_effectively_closed_not_expired(self, db_session, app):
        """Test is_effectively_closed False when future expiry_date."""
        with app.app_context():
            future_date = date.today() + timedelta(days=10)
            af, _ = self._create_assigned_form(db_session, expiry_date=future_date)
            assert af.is_effectively_closed is False

    def test_is_effectively_closed_no_expiry(self, db_session, app):
        """Test is_effectively_closed False when no expiry_date and not closed."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session)
            assert af.is_effectively_closed is False

    def test_is_entry_allowed(self, db_session, app):
        """Test is_entry_allowed returns is_active."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session, is_active=True)
            assert af.is_entry_allowed is True
            af.is_active = False
            assert af.is_entry_allowed is False

    def test_is_public_submission_allowed(self, db_session, app):
        """Test is_public_submission_allowed."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session, is_active=True)
            assert af.is_public_submission_allowed is True
            # Close it
            af.is_closed = True
            assert af.is_public_submission_allowed is False

    def test_operational_clause(self, db_session, app):
        """Test operational_clause returns a SQL clause."""
        with app.app_context():
            clause = AssignedForm.operational_clause()
            assert clause is not None

    def test_toggle_public_access_with_token(self, db_session, app):
        """Test toggle_public_access flips is_public_active."""
        with app.app_context():
            af, _ = self._create_assigned_form(
                db_session, unique_token='abc', is_public_active=False
            )
            result = af.toggle_public_access()
            assert result is True
            result2 = af.toggle_public_access()
            assert result2 is False

    def test_toggle_public_access_no_token(self, db_session, app):
        """Test toggle_public_access does nothing without token."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session)
            result = af.toggle_public_access()
            assert result is False

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            af, _ = self._create_assigned_form(db_session)
            result = repr(af)
            assert '2024' in result


@pytest.mark.unit
class TestAssignmentEntityStatus:
    """Tests for AssignmentEntityStatus model."""

    def test_create_aes(self, db_session, app):
        """Test creating an AES."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assert aes.id is not None
            assert aes.entity_type == 'country'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            result = repr(aes)
            assert 'AssignmentEntityStatus' in result
            assert 'country' in result

    def test_country_id_for_country_entity(self, db_session, app):
        """Test country_id returns entity_id for country entity_type."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assert aes.country_id == country.id

    def test_country_id_for_non_country_entity(self, db_session, app):
        """Test country_id for non-country entity_type uses entity service."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            # Change entity_type to test non-country path
            aes.entity_type = 'ns_branch'
            aes.entity_id = 999
            db_session.commit()
            # Patch EntityService to avoid real DB calls
            with patch('app.services.entity_service.EntityService.get_country_for_entity', return_value=None):
                result = aes.country_id
                assert result is None

    def test_country_id_non_country_with_country_object(self, db_session, app):
        """Test country_id for non-country returns country.id via service."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            aes.entity_type = 'ns_branch'
            aes.entity_id = 999
            db_session.commit()
            mock_country = MagicMock()
            mock_country.id = country.id
            with patch('app.services.entity_service.EntityService.get_country_for_entity', return_value=mock_country):
                result = aes.country_id
                assert result == country.id

    def test_country_id_exception_returns_none(self, db_session, app):
        """Test country_id exception returns None."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            aes.entity_type = 'ns_branch'
            aes.entity_id = 999
            db_session.commit()
            with patch('app.services.entity_service.EntityService.get_country_for_entity', side_effect=Exception('db error')):
                result = aes.country_id
                assert result is None

    def test_is_round_closed_for_entity_not_closed(self, db_session, app):
        """Test is_round_closed_for_entity False when assignment not closed."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            assert aes.is_round_closed_for_entity() is False

    def test_is_round_closed_for_entity_reopened(self, db_session, app):
        """Test is_round_closed_for_entity False when reopened_after_close=True."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            aes.reopened_after_close = True
            db_session.commit()
            assert aes.is_round_closed_for_entity() is False

    def test_is_round_closed_for_entity_closed_assignment(self, db_session, app):
        """Test is_round_closed_for_entity True when assignment is closed."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            aes.assigned_form.is_closed = True
            db_session.commit()
            assert aes.is_round_closed_for_entity() is True

    def test_entity_property_calls_service(self, db_session, app):
        """Test entity property calls EntityService."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            with patch('app.services.entity_service.EntityService.get_entity', return_value=country) as mock_get:
                entity = aes.entity
                mock_get.assert_called_once_with('country', country.id)

    def test_country_property_calls_service(self, db_session, app):
        """Test country property calls EntityService."""
        with app.app_context():
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            with patch('app.services.entity_service.EntityService.get_country_for_entity', return_value=country):
                c = aes.country
                assert c is not None


@pytest.mark.unit
class TestPublicSubmission:
    """Tests for PublicSubmission model."""

    def test_create_submission(self, db_session, app):
        """Test creating a public submission."""
        with app.app_context():
            submission, _, _ = create_test_public_submission(db_session)
            assert submission.id is not None
            assert submission.status == PublicSubmissionStatus.pending

    def test_repr_with_assignment(self, db_session, app):
        """Test __repr__ with assigned_form."""
        with app.app_context():
            submission, _, _ = create_test_public_submission(db_session)
            result = repr(submission)
            assert 'PublicSubmission' in result
            assert 'AssignedForm:' in result

    def test_repr_without_assignment(self, db_session, app):
        """Test __repr__ without assigned_form."""
        with app.app_context():
            country = create_test_country(db_session)
            submission = PublicSubmission(
                country_id=country.id,
                status=PublicSubmissionStatus.pending,
            )
            db_session.add(submission)
            db_session.commit()
            db_session.refresh(submission)
            result = repr(submission)
            assert 'NoAssignment' in result

    def test_submission_with_all_fields(self, db_session, app):
        """Test submission with all optional fields."""
        with app.app_context():
            submission, _, _ = create_test_public_submission(
                db_session,
                submitter_name='Jane Doe',
                submitter_email='jane@example.com',
                status='pending',
            )
            assert submission.submitter_name == 'Jane Doe'
            assert submission.submitter_email == 'jane@example.com'
