"""Assertion helpers for the mobile API test suite."""


def assert_mobile_ok(response, status=200, has_data=False, has_message=False):
    """Assert the standard mobile success envelope."""
    assert response.status_code == status, (
        f"Expected {status}, got {response.status_code}: {response.get_data(as_text=True)[:500]}"
    )
    body = response.get_json()
    assert body is not None, "Response is not valid JSON"
    assert body['success'] is True
    if has_data:
        assert 'data' in body, f"Expected 'data' key, got keys: {list(body.keys())}"
    if has_message:
        assert 'message' in body, f"Expected 'message' key, got keys: {list(body.keys())}"


def assert_mobile_paginated(response, min_items=0):
    """Assert the mobile paginated envelope."""
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.get_data(as_text=True)[:500]}"
    )
    body = response.get_json()
    assert body is not None
    assert body['success'] is True
    assert isinstance(body['data'], list), f"Expected list 'data', got {type(body['data'])}"
    assert len(body['data']) >= min_items, (
        f"Expected >= {min_items} items, got {len(body['data'])}"
    )
    assert 'meta' in body, f"Missing 'meta' key, got keys: {list(body.keys())}"
    for key in ('total', 'page', 'per_page', 'total_pages'):
        assert key in body['meta'], f"Missing meta.{key}"


def assert_mobile_error(response, status, error_code=None):
    """Assert the mobile error envelope."""
    assert response.status_code == status, (
        f"Expected {status}, got {response.status_code}: {response.get_data(as_text=True)[:500]}"
    )
    body = response.get_json()
    assert body is not None, "Response is not valid JSON"
    assert body['success'] is False
    assert 'error' in body
    if error_code:
        assert body.get('error_code') == error_code, (
            f"Expected error_code '{error_code}', got '{body.get('error_code')}'"
        )
