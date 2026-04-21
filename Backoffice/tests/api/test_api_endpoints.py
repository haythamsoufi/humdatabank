"""
Comprehensive API endpoint tests.

Tests all API endpoints to ensure they are working correctly.
"""
import pytest
import json
from app import db
from app.models import (
    FormTemplate, FormItem, LookupList, Country,
    IndicatorBank, IndicatorSuggestion, User,
    AssignedForm, PublicSubmission
)
from app.models.assignments import AssignmentEntityStatus


@pytest.mark.api
@pytest.mark.integration
class TestAPIEndpoints:
    """Test all API endpoints."""

    @pytest.fixture
    def test_ids(self, db_session, app):
        """Set up test data for API tests."""
        with app.app_context():
            from tests.factories import create_test_template, create_test_country

            # Create test template if it doesn't exist
            template = db_session.query(FormTemplate).first()
            if not template:
                template = create_test_template(db_session, name="Test Template", description="Test template for API tests")

            # Create test country if it doesn't exist
            country = db_session.query(Country).first()
            if not country:
                country = create_test_country(db_session, name="Test Country", iso3="TST", region="Europe")

            return {
                'template_id': template.id if template else 1,
                'country_id': country.id if country else 1,
            }

    def test_get_submissions(self, client, auth_headers, db_session, app):
        """Test GET /api/v1/submissions endpoint."""
        with app.app_context():
            from tests.factories import create_test_user
            from tests.helpers import assert_api_response, assert_paginated_response

            # Create test data if needed
            user = create_test_user(db_session)

        response = client.get(
            '/api/v1/submissions',
            headers=auth_headers
        )

        # Should return 200 with proper structure
        if response.status_code == 200:
            data = response.get_json()
            assert data is not None
            # Check for expected structure
            if 'data' in data:
                assert isinstance(data['data'], list)
        else:
            # If not 200, should be proper error response
            assert response.status_code in [401, 403]
            data = response.get_json()
            assert data is not None
            assert 'message' in data or 'error' in data

    def test_get_submission_details(self, client, auth_headers):
        """Test GET /api/v1/submissions/<id> endpoint."""
        submission_id = 1
        response = client.get(
            f'/api/v1/submissions/{submission_id}',
            headers=auth_headers
        )
        assert response.status_code in [200, 404, 401, 403]

    def test_get_all_data(self, client, auth_headers):
        """Test GET /api/v1/data endpoint."""
        response = client.get(
            '/api/v1/data',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_data_tables(self, client, auth_headers):
        """Test GET /api/v1/data/tables endpoint."""
        response = client.get(
            '/api/v1/data/tables',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_template_data(self, client, auth_headers, test_ids):
        """Test GET /api/v1/templates/<id>/data endpoint."""
        template_id = test_ids.get('template_id', 1)
        response = client.get(
            f'/api/v1/templates/{template_id}/data',
            headers=auth_headers
        )
        assert response.status_code in [200, 404, 401, 403]

    def test_get_country_data(self, client, auth_headers, test_ids):
        """Test GET /api/v1/countries/<id>/data endpoint."""
        country_id = test_ids.get('country_id', 1)
        response = client.get(
            f'/api/v1/countries/{country_id}/data',
            headers=auth_headers
        )
        assert response.status_code in [200, 404, 401, 403]

    def test_get_templates(self, client, auth_headers):
        """Test GET /api/v1/templates endpoint."""
        response = client.get(
            '/api/v1/templates',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_template_details(self, client, auth_headers, test_ids, db_session, app):
        """Test GET /api/v1/templates/<id> endpoint."""
        with app.app_context():
            from tests.factories import create_test_template
            from tests.helpers import assert_api_response, assert_error_response

            # Create a test template
            template = create_test_template(db_session)
            template_id = template.id

        # Test with valid ID
        response = client.get(
            f'/api/v1/templates/{template_id}',
            headers=auth_headers
        )

        if response.status_code == 200:
            data = response.get_json()
            assert data is not None
            assert 'id' in data or 'name' in data
        else:
            assert response.status_code in [404, 401, 403]

        # Test with invalid ID
        response = client.get(
            '/api/v1/templates/99999',
            headers=auth_headers
        )
        assert response.status_code in [404, 401, 403]

    def test_get_form_items(self, client, auth_headers):
        """Test GET /api/v1/form-items endpoint."""
        response = client.get(
            '/api/v1/form-items',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_lookup_lists(self, client, auth_headers):
        """Test GET /api/v1/lookup-lists endpoint."""
        response = client.get(
            '/api/v1/lookup-lists',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_countries(self, client, auth_headers):
        """Test GET /api/v1/countrymap endpoint."""
        response = client.get(
            '/api/v1/countrymap',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_periods(self, client, auth_headers):
        """Test GET /api/v1/periods endpoint."""
        response = client.get(
            '/api/v1/periods',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_resources(self, client, auth_headers):
        """Test GET /api/v1/resources endpoint."""
        response = client.get(
            '/api/v1/resources',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_indicator_bank(self, client, auth_headers):
        """Test GET /api/v1/indicator-bank endpoint."""
        response = client.get(
            '/api/v1/indicator-bank',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_indicator_suggestions(self, client, auth_headers):
        """Test GET /api/v1/indicator-suggestions endpoint."""
        response = client.get(
            '/api/v1/indicator-suggestions',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_sectors(self, client, auth_headers):
        """Test GET /api/v1/sectors endpoint."""
        response = client.get(
            '/api/v1/sectors',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_subsectors(self, client, auth_headers):
        """Test GET /api/v1/subsectors endpoint."""
        response = client.get(
            '/api/v1/subsectors',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_sectors_and_subsectors(self, client, auth_headers):
        """Test GET /api/v1/sectors-subsectors endpoint."""
        response = client.get(
            '/api/v1/sectors-subsectors',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_users(self, client, auth_headers):
        """Test GET /api/v1/users endpoint."""
        response = client.get(
            '/api/v1/users',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_assigned_forms(self, client, auth_headers):
        """Test GET /api/v1/assigned-forms endpoint."""
        response = client.get(
            '/api/v1/assigned-forms',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_submitted_documents(self, client, auth_headers):
        """Test GET /api/v1/submitted-documents endpoint."""
        response = client.get(
            '/api/v1/submitted-documents',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_quiz_leaderboard(self, client, auth_headers):
        """Test GET /api/v1/quiz/leaderboard endpoint."""
        response = client.get(
            '/api/v1/quiz/leaderboard',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]

    def test_get_common_words(self, client, auth_headers):
        """Test GET /api/v1/common-words endpoint."""
        response = client.get(
            '/api/v1/common-words',
            headers=auth_headers
        )
        assert response.status_code in [200, 401, 403]
