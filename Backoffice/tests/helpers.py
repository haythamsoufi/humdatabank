"""
Test helper utilities for common test assertions and operations.
"""
from typing import Dict, List, Optional, Any


def assert_api_response(response, expected_status: int = 200, expected_keys: Optional[List[str]] = None):
    """
    Helper to assert API response structure.

    Args:
        response: Flask test client response
        expected_status: Expected HTTP status code
        expected_keys: List of keys that should be in response JSON
    """
    assert response.status_code == expected_status, \
        f"Expected status {expected_status}, got {response.status_code}. Response: {response.get_data(as_text=True)[:500]}"

    if expected_keys:
        data = response.get_json()
        assert data is not None, "Response is not valid JSON"
        for key in expected_keys:
            assert key in data, f"Expected key '{key}' not found in response. Keys: {list(data.keys())}"


def assert_paginated_response(response, min_items: int = 0, expected_status: int = 200):
    """
    Helper to assert paginated API response structure.

    Args:
        response: Flask test client response
        min_items: Minimum number of items expected in 'data' array
        expected_status: Expected HTTP status code
    """
    assert_api_response(response, expected_status=expected_status)
    data = response.get_json()

    assert 'data' in data, "Paginated response missing 'data' key"
    assert isinstance(data['data'], list), "Response 'data' is not a list"
    assert len(data['data']) >= min_items, \
        f"Expected at least {min_items} items, got {len(data['data'])}"

    # Check for pagination metadata (if present)
    if 'pagination' in data:
        pagination = data['pagination']
        assert 'page' in pagination or 'total' in pagination, \
            "Pagination metadata missing expected keys"


def assert_error_response(response, expected_status: int, expected_message: Optional[str] = None):
    """
    Helper to assert error response structure.

    Args:
        response: Flask test client response
        expected_status: Expected HTTP status code
        expected_message: Optional expected error message
    """
    assert response.status_code == expected_status, \
        f"Expected status {expected_status}, got {response.status_code}"

    data = response.get_json()
    assert data is not None, "Error response is not valid JSON"
    assert 'message' in data or 'error' in data, \
        "Error response missing 'message' or 'error' key"

    if expected_message:
        message = data.get('message') or data.get('error', '')
        assert expected_message.lower() in message.lower(), \
            f"Expected message containing '{expected_message}', got '{message}'"


def assert_validation_error(response, field_name: Optional[str] = None):
    """
    Helper to assert validation error response.

    Args:
        response: Flask test client response
        field_name: Optional specific field that should have validation error
    """
    assert response.status_code in [400, 422], \
        f"Expected validation error (400/422), got {response.status_code}"

    data = response.get_json()
    assert data is not None, "Validation error response is not valid JSON"

    if field_name:
        # Check if errors dict contains the field
        if 'errors' in data:
            assert field_name in data['errors'], \
                f"Expected validation error for field '{field_name}'"


def create_test_data_dict(**kwargs) -> Dict[str, Any]:
    """
    Create a test data dictionary with defaults.

    Args:
        **kwargs: Override default values

    Returns:
        Dict with test data
    """
    defaults = {
        'name': 'Test Name',
        'description': 'Test Description',
        'email': 'test@example.com',
        'value': 'test_value'
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# HTTP / session helpers (integration route tests)
# ---------------------------------------------------------------------------

def login_session(client: Any, user_id: int) -> None:
    """Log a user into the Flask test client via session_transaction."""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def assert_redirect(resp: Any, contains: Optional[str] = None) -> None:
    """Assert a response is an HTTP redirect and optionally check Location.

    ``contains="dashboard"`` matches ``main.dashboard``, which is mounted at ``/``.
    """
    assert resp.status_code in (301, 302, 303, 307, 308)
    if contains is None:
        return
    location = resp.headers.get("Location") or ""
    if contains == "dashboard":
        from urllib.parse import urlparse
        path = urlparse(location).path or "/"
        assert path in ("/", "/dashboard") or "dashboard" in location, (
            f"Expected dashboard redirect, got Location={location!r}"
        )
        return
    assert contains in location


def assert_json_has_keys(resp: Any, *keys: str) -> dict:
    """Parse JSON and assert top-level keys exist."""
    data = resp.get_json()
    assert isinstance(data, dict)
    for k in keys:
        assert k in data
    return data


def set_selected_entity_session(
    client: Any,
    *,
    entity_type: str,
    entity_id: int,
    country_id: Optional[int] = None,
) -> None:
    """Set dashboard entity selection keys on the test client session."""
    from app.utils.constants import SELECTED_COUNTRY_ID_SESSION_KEY

    with client.session_transaction() as sess:
        sess["selected_entity_type"] = entity_type
        sess["selected_entity_id"] = entity_id
        if country_id is not None:
            sess[SELECTED_COUNTRY_ID_SESSION_KEY] = country_id


def get_csrf_headers(client: Any) -> dict:
    """Fetch CSRF token from /api/v1/csrf-token for unsafe requests."""
    resp = client.get("/api/v1/csrf-token")
    assert resp.status_code == 200
    token = (resp.get_json() or {}).get("csrf_token")
    assert token
    return {"X-CSRFToken": token}
