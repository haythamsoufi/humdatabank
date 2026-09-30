"""api_tracker must persist the same redacted, size-capped payload for APIUsage and APIKeyUsage."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

from flask import g, make_response

from app.middleware.api_tracker import track_api_response

_PAYLOAD = {
    "username": "user1",
    "newPassword": "hunter2-new",
    "nested": {"clientSecret": "cs-value", "list": [{"refreshToken": "rt-value", "ok": 1}]},
    "X-Api-Key": "k-value",
}


def _track(app, payload, api_key_id):
    with app.test_request_context("/api/v1/thing", method="POST", json={"ignored": True}):
        g.api_start_time = time.time() - 0.01
        g.api_key_usage_id = api_key_id
        g.api_key_usage_client_name = "client"
        g.api_key_record = None
        with patch("app.middleware.api_tracker._should_skip_api_usage_tracking", return_value=False), \
             patch("app.middleware.api_tracker.get_json_safe", return_value=payload), \
             patch("sqlalchemy.orm.sessionmaker") as mock_sm:
            session = MagicMock()
            mock_sm.return_value.return_value = session
            track_api_response(make_response("ok", 200))
    return [call.args[0] for call in session.add.call_args_list]


def test_api_usage_redacts_nested_and_camel_case_keys(app):
    (usage,) = _track(app, _PAYLOAD, api_key_id=None)
    blob = json.dumps(usage.request_data)
    for secret in ("hunter2-new", "cs-value", "rt-value", "k-value"):
        assert secret not in blob
    assert usage.request_data["username"] == "user1"


def test_api_key_usage_row_gets_identical_redacted_payload(app):
    usage, key_usage = _track(app, _PAYLOAD, api_key_id=7)
    assert key_usage.request_data == usage.request_data
    blob = json.dumps(key_usage.request_data)
    for secret in ("hunter2-new", "cs-value", "rt-value", "k-value"):
        assert secret not in blob


def test_oversized_payload_is_capped_for_both_rows(app):
    big = {f"f{i}": "z" * 400 for i in range(200)}
    usage, key_usage = _track(app, big, api_key_id=7)
    for row in (usage, key_usage):
        assert row.request_data["_truncated"] is True
        assert len(json.dumps(row.request_data)) < 8 * 1024


def test_empty_body_stores_no_payload(app):
    (usage,) = _track(app, {}, api_key_id=None)
    assert usage.request_data is None
