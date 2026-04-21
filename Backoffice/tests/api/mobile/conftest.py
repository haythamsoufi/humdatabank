"""Mobile API test fixtures: JWT headers, mobile-specific users."""
import pytest
from tests.factories import create_test_user
from app.utils.mobile_jwt import issue_token_pair


@pytest.fixture
def mobile_user(db_session, app):
    """Standard mobile user (no admin permissions)."""
    with app.app_context():
        return create_test_user(
            db_session, email='mobile@test.com', password='MobilePass123!', role='user',
        )


@pytest.fixture
def admin_mobile_user(db_session, app):
    """Mobile user with admin_core role."""
    with app.app_context():
        return create_test_user(
            db_session, email='admin-mobile@test.com', password='AdminPass123!', role='admin',
        )


@pytest.fixture
def sm_mobile_user(db_session, app):
    """Mobile user with system_manager role."""
    with app.app_context():
        return create_test_user(
            db_session, email='sm-mobile@test.com', password='SmPass123!', role='system_manager',
        )


def _make_jwt_headers(app, user, session_id='test-sid'):
    with app.app_context():
        tokens = issue_token_pair(user.id, session_id=session_id)
        return {
            'Authorization': f'Bearer {tokens["access_token"]}',
            'Content-Type': 'application/json',
            'X-App-Version': '99.0.0',
        }


@pytest.fixture
def jwt_headers(app, mobile_user):
    """Valid JWT headers for a regular user."""
    return _make_jwt_headers(app, mobile_user)


@pytest.fixture
def admin_jwt_headers(app, admin_mobile_user):
    """Valid JWT headers for an admin user."""
    return _make_jwt_headers(app, admin_mobile_user, session_id='admin-sid')


@pytest.fixture
def sm_jwt_headers(app, sm_mobile_user):
    """Valid JWT headers for a system manager."""
    return _make_jwt_headers(app, sm_mobile_user, session_id='sm-sid')


@pytest.fixture
def expired_jwt_headers(app, mobile_user):
    """JWT headers with an expired access token (should 401)."""
    import jwt as pyjwt
    from app.utils.mobile_jwt import (
        _jwt_secret, MOBILE_TOKEN_AUDIENCE, MOBILE_TOKEN_ISSUER, MOBILE_TOKEN_ALGORITHM,
    )
    payload = {
        'sub': str(mobile_user.id), 'type': 'access',
        'iat': 0, 'exp': 1,
        'aud': MOBILE_TOKEN_AUDIENCE, 'iss': MOBILE_TOKEN_ISSUER, 'ver': 1,
    }
    with app.app_context():
        token = pyjwt.encode(payload, _jwt_secret(), algorithm=MOBILE_TOKEN_ALGORITHM)
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
