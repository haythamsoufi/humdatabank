#!/usr/bin/env python3
"""
Comprehensive API endpoint testing script.

This script tests all API endpoints to ensure they are working correctly.
It can be run at any time to verify the API is functioning properly.

Usage:
    python scripts/test_api_endpoints.py
    python scripts/test_api_endpoints.py --base-url http://localhost:5000
    python scripts/test_api_endpoints.py --api-key YOUR_API_KEY
"""

import argparse
import logging
import os
import sys

logger = logging.getLogger(__name__)
import json
from typing import Dict, List, Tuple, Optional
from datetime import datetime

# Add the parent directory to the path so we can import from app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app import create_app
    from flask import url_for
    USE_FLASK_CLIENT = True
except ImportError:
    USE_FLASK_CLIENT = False
    try:
        import requests
    except ImportError:
        logger.error("Neither Flask app nor requests library available.")
        logger.error("Please install requests: pip install requests")
        sys.exit(1)


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class APITester:
    """Test all API endpoints"""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, use_flask_client: bool = True):
        self.base_url = base_url or 'http://localhost:5000'
        self.api_key = api_key or os.getenv('API_KEY', 'test_api_key')
        self.use_flask_client = use_flask_client and USE_FLASK_CLIENT
        self.app = None
        self.client = None
        self.results: List[Dict] = []
        self.test_ids = {}  # Cache for real IDs from database

        if self.use_flask_client:
            self.app = create_app(os.getenv('FLASK_CONFIG'))
            self.client = self.app.test_client()
            # Fetch real IDs from database for testing
            self._fetch_test_ids()

    def _fetch_test_ids(self):
        """Fetch real IDs from database for testing detail endpoints"""
        if not self.use_flask_client or not self.app:
            return

        try:
            with self.app.app_context():
                from app import db
                from app.models import (
                    FormTemplate, FormItem, LookupList, Country,
                    IndicatorBank, IndicatorSuggestion, User,
                    AssignedForm, PublicSubmission
                )
                from app.models.assignments import AssignmentEntityStatus

                # Get first available ID for each model
                template = FormTemplate.query.first()
                if template:
                    self.test_ids['template_id'] = template.id

                form_item = FormItem.query.first()
                if form_item:
                    self.test_ids['form_item_id'] = form_item.id

                lookup_list = LookupList.query.first()
                if lookup_list:
                    self.test_ids['lookup_list_id'] = lookup_list.id

                country = Country.query.first()
                if country:
                    self.test_ids['country_id'] = country.id

                indicator = IndicatorBank.query.first()
                if indicator:
                    self.test_ids['indicator_id'] = indicator.id

                suggestion = IndicatorSuggestion.query.first()
                if suggestion:
                    self.test_ids['suggestion_id'] = suggestion.id

                user = User.query.first()
                if user:
                    self.test_ids['user_id'] = user.id

                # Get submission IDs
                assigned_status = AssignmentEntityStatus.query.first()
                if assigned_status:
                    self.test_ids['submission_id'] = assigned_status.id

                public_submission = PublicSubmission.query.first()
                if public_submission:
                    self.test_ids['public_submission_id'] = public_submission.id

        except Exception as e:
            logger.warning("Could not fetch test IDs from database: %s", e)
            # Continue with hardcoded IDs if database fetch fails

    def _make_request(self, method: str, endpoint: str, requires_login: bool = False, **kwargs) -> Tuple[int, dict]:
        """Make HTTP request to endpoint

        Args:
            method: HTTP method
            endpoint: API endpoint path
            requires_login: If True, log in a user before making the request (Flask test client only)
            **kwargs: Additional arguments for request
        """
        try:
            # Use Authorization header (Bearer token) instead of query parameter
            headers = kwargs.get('headers', {})
            headers['Authorization'] = f'Bearer {self.api_key}'
            kwargs['headers'] = headers

            if self.use_flask_client:
                # Use Flask test client - construct path without query params
                path = f"/api/v1{endpoint}"

                # Extract json data if present
                json_data = kwargs.pop('json', None)
                if json_data:
                    kwargs['data'] = json.dumps(json_data)
                    kwargs['content_type'] = 'application/json'

                # Flask test client requires headers via environ_base in WSGI format
                environ_base = kwargs.pop('environ_base', {})
                for key, value in headers.items():
                    # Convert header name to HTTP_ format for WSGI (e.g., Authorization -> HTTP_AUTHORIZATION)
                    header_name = 'HTTP_' + key.upper().replace('-', '_')
                    environ_base[header_name] = value
                kwargs['environ_base'] = environ_base

                # If login is required, set up the session first
                if requires_login:
                    with self.app.app_context():
                        from app.models import User
                        from app import db

                        # Get or create a test user
                        user = User.query.filter_by(email='test_admin@example.com').first()
                        if not user:
                            # Create a test user if it doesn't exist
                            user = User(
                                email='test_admin@example.com',
                                name='Test Admin',
                                role='admin'
                            )
                            user.set_password('test123')
                            db.session.add(user)
                            db.session.commit()

                    # Use session_transaction to manually set session variables
                    # This is the proper way to test login_required endpoints with test client
                    with self.client.session_transaction() as sess:
                        # Flask-Login stores user_id in session
                        sess['_user_id'] = str(user.id)
                        sess['_fresh'] = True

                # Make the actual API request
                with self.app.app_context():
                    response = self.client.open(
                        path,
                        method=method,
                        **kwargs
                    )
                status_code = response.status_code
                try:
                    data = json.loads(response.data) if response.data else {}
                except (json.JSONDecodeError, ValueError, TypeError):
                    data = {'raw': str(response.data[:200]) if response.data else ''}
            else:
                # Use requests library
                url = f"{self.base_url}/api/v1{endpoint}"

                if method == 'GET':
                    response = requests.get(url, headers=headers, **{k: v for k, v in kwargs.items() if k != 'headers'}, timeout=10)
                elif method == 'POST':
                    response = requests.post(url, headers=headers, json=kwargs.get('json'), **{k: v for k, v in kwargs.items() if k not in ('json', 'headers')}, timeout=10)
                elif method == 'PUT':
                    response = requests.put(url, headers=headers, json=kwargs.get('json'), **{k: v for k, v in kwargs.items() if k not in ('json', 'headers')}, timeout=10)
                else:
                    response = requests.request(method, url, headers=headers, **{k: v for k, v in kwargs.items() if k != 'headers'}, timeout=10)

                status_code = response.status_code
                try:
                    data = response.json()
                except (json.JSONDecodeError, ValueError, TypeError):
                    data = {'raw': str(response.text[:200]) if response.text else ''}

            return status_code, data
        except Exception as e:
            return 0, {'error': str(e)}

    def test_endpoint(self, name: str, method: str, endpoint: str, expected_status = 200, requires_login: bool = False, **kwargs) -> Dict:
        """Test a single endpoint

        Args:
            name: Test name
            method: HTTP method
            endpoint: API endpoint path
            expected_status: Expected status code(s) - can be int or list
            requires_login: If True, log in a user before making the request (Flask test client only)
            **kwargs: Additional arguments for request
        """
        logger.info("  Testing %s %s...", method, endpoint)

        status_code, data = self._make_request(method, endpoint, requires_login=requires_login, **kwargs)

        # Handle expected_status as int or list
        if isinstance(expected_status, list):
            success = status_code in expected_status
            expected_str = str(expected_status)
        else:
            success = status_code == expected_status or (expected_status == 200 and 200 <= status_code < 300)
            expected_str = str(expected_status)

        if success:
            logger.info("    ✓ (%s)", status_code)
        else:
            logger.warning("    ✗ (%s, expected %s)", status_code, expected_str)
            if 'error' in data:
                error_msg = data.get('error', 'Unknown error')
                logger.warning("    Error: %s", (error_msg if isinstance(error_msg, str) else str(error_msg))[:100])

        result = {
            'name': name,
            'method': method,
            'endpoint': endpoint,
            'status_code': status_code,
            'expected_status': expected_str,
            'success': success,
            'error': data.get('error') if not success else None
        }
        self.results.append(result)
        return result

    def run_all_tests(self):
        """Run all API endpoint tests"""
        api_key_display = '*' * (len(self.api_key) - 4) + self.api_key[-4:] if len(self.api_key) > 4 else '****'
        logger.info("=" * 80)
        logger.info("API Endpoint Test Suite")
        logger.info("=" * 80)
        logger.info("Base URL: %s", self.base_url)
        logger.info("API Key: %s", api_key_display)
        logger.info("Test Client: %s", 'Flask Test Client' if self.use_flask_client else 'Requests')
        logger.info("")

        # Submissions
        logger.info("Submissions Endpoints")
        self.test_endpoint("Get Submissions", "GET", "/submissions")
        submission_id = self.test_ids.get('submission_id', 1)
        self.test_endpoint("Get Submission Details", "GET", f"/submissions/{submission_id}", expected_status=[200, 404])
        logger.info("")

        # Data
        logger.info("Data Endpoints")
        self.test_endpoint("Get All Data", "GET", "/data")
        self.test_endpoint("Get Data Tables", "GET", "/data/tables")
        template_id = self.test_ids.get('template_id', 1)
        self.test_endpoint("Get Template Data", "GET", f"/templates/{template_id}/data", expected_status=[200, 404])
        country_id = self.test_ids.get('country_id', 1)
        self.test_endpoint("Get Country Data", "GET", f"/countries/{country_id}/data", expected_status=[200, 404])
        logger.info("")

        # Templates
        logger.info("Template Endpoints")
        self.test_endpoint("Get Templates", "GET", "/templates")
        template_id = self.test_ids.get('template_id', 1)
        self.test_endpoint("Get Template Details", "GET", f"/templates/{template_id}", expected_status=[200, 404])
        self.test_endpoint("Get Form Items", "GET", "/form-items")
        form_item_id = self.test_ids.get('form_item_id', 1)
        self.test_endpoint("Get Form Item Details", "GET", f"/form-items/{form_item_id}", expected_status=[200, 404])
        self.test_endpoint("Get Lookup Lists", "GET", "/lookup-lists")
        lookup_list_id = self.test_ids.get('lookup_list_id', 1)
        self.test_endpoint("Get Lookup List Details", "GET", f"/lookup-lists/{lookup_list_id}", expected_status=[200, 404])
        logger.info("")

        # Countries
        logger.info("Country Endpoints")
        self.test_endpoint("Get Countries", "GET", "/countrymap")
        self.test_endpoint("Get Periods", "GET", "/periods")
        logger.info("")

        # Resources
        logger.info("Resource Endpoints")
        self.test_endpoint("Get Resources", "GET", "/resources")
        logger.info("")

        # Indicators
        logger.info("Indicator Endpoints")
        self.test_endpoint("Get Indicator Bank", "GET", "/indicator-bank")
        indicator_id = self.test_ids.get('indicator_id', 1)
        self.test_endpoint("Get Indicator Details", "GET", f"/indicator-bank/{indicator_id}", expected_status=[200, 404])
        self.test_endpoint("Get Indicator Suggestions", "GET", "/indicator-suggestions")
        suggestion_id = self.test_ids.get('suggestion_id', 1)
        self.test_endpoint("Get Indicator Suggestion", "GET", f"/indicator-suggestions/{suggestion_id}", expected_status=[200, 404])
        self.test_endpoint("Get Sectors", "GET", "/sectors")
        self.test_endpoint("Get Subsectors", "GET", "/subsectors")
        self.test_endpoint("Get Sectors and Subsectors", "GET", "/sectors-subsectors")
        logger.info("")

        # Users
        logger.info("User Endpoints")
        self.test_endpoint("Get Users", "GET", "/users")
        user_id = self.test_ids.get('user_id', 1)
        self.test_endpoint("Get User Details", "GET", f"/users/{user_id}", expected_status=[200, 404])
        # Note: /user/profile and /dashboard require login, so they may fail without session
        logger.info("")

        # Assignments
        logger.info("Assignment Endpoints")
        self.test_endpoint("Get Assigned Forms", "GET", "/assigned-forms")
        # Note: /matrix/auto-load-entities requires POST with data and login
        logger.info("")

        # Documents
        logger.info("Document Endpoints")
        self.test_endpoint("Get Submitted Documents", "GET", "/submitted-documents")
        # Note: Upload endpoints require actual files
        logger.info("")

        # Quiz
        logger.info("Quiz Endpoints")
        self.test_endpoint("Get Quiz Leaderboard", "GET", "/quiz/leaderboard")
        # Note: /quiz/submit-score requires POST with data and login
        logger.info("")

        # Common
        logger.info("Common Endpoints")
        self.test_endpoint("Get Common Words", "GET", "/common-words")
        logger.info("")

        # Variables (requires login)
        logger.info("Variable Endpoints")
        if self.use_flask_client:
            # Test with logged-in user session
            assignment_status_id = self.test_ids.get('submission_id', 1)
            template_id = self.test_ids.get('template_id', 1)
            self.test_endpoint(
                "Resolve Variables (with login)",
                "POST",
                "/variables/resolve",
                json={
                    "assignment_entity_status_id": assignment_status_id,
                    "template_id": template_id,
                    "row_entity_id": self.test_ids.get('country_id')
                },
                requires_login=True,
                expected_status=[200, 400, 401, 403, 404]
            )
        else:
            logger.info("  Note: /variables/resolve requires login session (skipped when using requests)")
        logger.info("")

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print test summary"""
        total = len(self.results)
        passed = sum(1 for r in self.results if r['success'])
        failed = total - passed

        logger.info("")
        logger.info("=" * 80)
        logger.info("Test Summary")
        logger.info("=" * 80)
        logger.info("Total Tests: %d", total)
        logger.info("Passed: %d", passed)
        logger.info("Failed: %d", failed)
        logger.info("")

        if failed > 0:
            logger.warning("Failed Tests:")
            for result in self.results:
                if not result['success']:
                    logger.warning("  ✗ %s %s - Status: %s", result['method'], result['endpoint'], result['status_code'])
                    if result['error']:
                        logger.warning("    Error: %s", (result['error'] or '')[:100])
            logger.info("")

        # Save results to file
        results_file = f"api_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'base_url': self.base_url,
                'total_tests': total,
                'passed': passed,
                'failed': failed,
                'results': self.results
            }, f, indent=2)

        logger.info("Results saved to: %s", results_file)
        logger.info("")

        return failed == 0


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Test all API endpoints')
    parser.add_argument('--base-url', default=None, help='Base URL for API (default: http://localhost:5000 or Flask test client)')
    parser.add_argument('--api-key', default=None, help='API key for authentication (default: from API_KEY env var or test_api_key)')
    parser.add_argument('--use-requests', action='store_true', help='Use requests library instead of Flask test client')

    args = parser.parse_args()

    tester = APITester(
        base_url=args.base_url,
        api_key=args.api_key,
        use_flask_client=not args.use_requests
    )

    success = tester.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
