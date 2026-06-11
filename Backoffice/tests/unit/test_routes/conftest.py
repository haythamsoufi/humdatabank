"""Local fixtures for test_routes unit tests.

Provides admin/regular user fixtures that call factories DIRECTLY without
extra `with app.app_context():` nesting — exactly like the working
`admin_mobile_user` fixture in tests/api/mobile/conftest.py.
"""
import pytest
from tests.factories import create_test_admin, create_test_user


@pytest.fixture
def route_admin(db_session, app):
    """Admin user for direct route unit tests."""
    return create_test_admin(
        db_session,
        email='route-admin@example.com',
        password='AdminPass123!',
    )


@pytest.fixture
def route_user(db_session, app):
    """Regular user for direct route unit tests."""
    return create_test_user(
        db_session,
        email='route-user@example.com',
        password='UserPass123!',
        role='user',
    )
