import base64
import json
import os
import uuid

import pytest

from app.models.ai_chat import AIConversation, AIMessage
from app.utils.ai.ai_tokens import issue_ai_token
from app.services.ai.chat.retention import archive_conversation
from app.utils.common.datetime_helpers import utcnow
from tests.factories import create_test_user


@pytest.mark.api
def test_ai_health_anonymous_gets_generic_status_only(client, app):
    """Unauthenticated health callers see only the overall status, never per-check detail."""
    resp = client.get("/api/ai/v1/health?probe=embedding")
    assert resp.status_code in (200, 503)
    data = resp.get_json()
    assert set(data) == {"ok"}
    assert isinstance(data["ok"], bool)


@pytest.mark.api
def test_ai_health_manager_gets_checks_and_agent_available(logged_in_sm_client):
    """AI managers get config checks and agent_available."""
    resp = logged_in_sm_client.get("/api/ai/v1/health")
    assert resp.status_code in (200, 503)
    data = resp.get_json()
    assert "checks" in data
    assert "openai_key" in data["checks"]
    assert "embedding_provider" in data["checks"]
    assert isinstance(data["checks"]["agent_available"], bool)


@pytest.mark.api
def test_ai_conversations_require_auth(client, app):
    """Conversations list requires authentication; no auth returns 401."""
    resp = client.get("/api/ai/v1/conversations")
    assert resp.status_code == 401
    data = resp.get_json()
    assert data.get("success") is False
    assert "error" in data or "Authentication" in (data.get("error") or "")


@pytest.mark.api
def test_ai_conversations_invalid_bearer_rejected(client, app):
    """Conversations with invalid Bearer token returns 401."""
    resp = client.get("/api/ai/v1/conversations", headers={"Authorization": "Bearer invalid-token"})
    assert resp.status_code == 401


@pytest.mark.api
def test_ai_chat_validation_message_required(client, app, db_session):
    """POST /api/ai/v1/chat returns 400 when message is missing or empty."""
    user = create_test_user(db_session, email="ai_val@test.local", name="AI Val", role="user")
    with app.app_context():
        token = issue_ai_token(user_id=int(user.id), role="user")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/api/ai/v1/chat",
        json={},
        content_type="application/json",
        headers=headers,
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data.get("success") is False
    assert "message" in (data.get("error") or "").lower() or "required" in (data.get("error") or "").lower()

    resp = client.post(
        "/api/ai/v1/chat",
        json={"message": "   "},
        content_type="application/json",
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.api
def test_ai_chat_validation_message_too_long(client, app, db_session):
    """POST /api/ai/v1/chat returns 413 when message exceeds AI_MAX_MESSAGE_CHARS."""
    user = create_test_user(db_session, email="ai_long@test.local", name="AI Long", role="user")
    with app.app_context():
        token = issue_ai_token(user_id=int(user.id), role="user")
    headers = {"Authorization": f"Bearer {token}"}

    app.config["AI_MAX_MESSAGE_CHARS"] = 50
    long_message = "x" * 51
    resp = client.post(
        "/api/ai/v1/chat",
        json={"message": long_message},
        content_type="application/json",
        headers=headers,
    )
    assert resp.status_code == 413
    data = resp.get_json()
    assert data.get("success") is False


@pytest.mark.api
def test_ai_chat_returns_success_with_fallback(client, app, db_session):
    """POST /api/ai/v1/chat without OPENAI_API_KEY returns 503 (no offline fallback)."""
    user = create_test_user(db_session, email="ai_chat@test.local", name="AI Chat", role="user")
    with app.app_context():
        token = issue_ai_token(user_id=int(user.id), role="user")
    headers = {"Authorization": f"Bearer {token}"}

    # Ensure keys are unset for this assertion
    app.config["OPENAI_API_KEY"] = ""
    resp = client.post(
        "/api/ai/v1/chat",
        json={"message": "Hello, what can you do?"},
        content_type="application/json",
        headers=headers,
    )
    assert resp.status_code == 503
    data = resp.get_json()
    assert data.get("success") is False


@pytest.mark.api
def test_ai_chat_stream_validation(client, app, db_session):
    """POST /api/ai/v1/chat/stream returns 400 when message is empty."""
    user = create_test_user(db_session, email="ai_stream_val@test.local", name="AI Stream Val", role="user")
    with app.app_context():
        token = issue_ai_token(user_id=int(user.id), role="user")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/api/ai/v1/chat/stream",
        json={"message": ""},
        content_type="application/json",
        headers=headers,
    )
    assert resp.status_code == 400


@pytest.mark.api
def test_ai_chat_stream_accepts_chunked_waf_payload_envelope(client, app, db_session):
    """POST /chat/stream unwraps {payload, payload__cN} the same way Backoffice JS sends it."""
    user = create_test_user(db_session, email="ai_stream_waf@test.local", name="AI Stream WAF", role="user")
    with app.app_context():
        token = issue_ai_token(user_id=int(user.id), role="user")
    headers = {"Authorization": f"Bearer {token}"}

    inner = {"message": "Say hello in one word.", "client": "backoffice"}
    encoded = base64.b64encode(json.dumps(inner).encode("utf-8")).decode("ascii")
    envelope = {"payload": encoded[:20], "payload__c1": encoded[20:]}

    resp = client.post(
        "/api/ai/v1/chat/stream",
        json=envelope,
        content_type="application/json",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.content_type and "text/event-stream" in resp.content_type
    data_lines = [ln for ln in resp.data.decode("utf-8").split("\n") if ln.startswith("data: ")]
    assert data_lines
    assert json.loads(data_lines[0][6:]).get("type") == "meta"


@pytest.mark.api
def test_ai_chat_stream_rejects_malformed_waf_envelope(client, app, db_session):
    user = create_test_user(db_session, email="ai_stream_waf_bad@test.local", name="AI Stream WAF Bad", role="user")
    with app.app_context():
        token = issue_ai_token(user_id=int(user.id), role="user")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/api/ai/v1/chat/stream",
        json={"payload": "!!!not-valid-base64!!!"},
        content_type="application/json",
        headers=headers,
    )
    assert resp.status_code == 400
    assert "payload" in (resp.get_json() or {}).get("error", "").lower()


@pytest.mark.api
def test_ai_chat_stream_returns_sse_meta_and_done(client, app, db_session):
    """POST /api/ai/v1/chat/stream returns SSE with meta and done events."""
    user = create_test_user(db_session, email="ai_stream@test.local", name="AI Stream", role="user")
    with app.app_context():
        token = issue_ai_token(user_id=int(user.id), role="user")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(
        "/api/ai/v1/chat/stream",
        json={"message": "Say hello in one word."},
        content_type="application/json",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.content_type and "text/event-stream" in resp.content_type
    lines = resp.data.decode("utf-8").strip().split("\n")
    data_lines = [ln for ln in lines if ln.startswith("data: ")]
    assert len(data_lines) >= 1
    first = json.loads(data_lines[0][6:])
    assert first.get("type") == "meta"
    # Last non-empty data line should be done (or error)
    for line in reversed(data_lines):
        payload = json.loads(line[6:])
        if payload.get("type") in ("done", "error"):
            if payload.get("type") == "done":
                assert "response" in payload
            break
    else:
        pytest.fail("Expected at least one 'done' or 'error' event in stream")


@pytest.mark.api
@pytest.mark.db
def test_ai_chat_await_returns_stored_reply_without_running_agent(client, app, db_session):
    """POST /chat/await delivers a reply that was already stored for this client message."""
    user = create_test_user(db_session, email="ai_await@test.local", name="AI Await", role="user")
    with app.app_context():
        token = issue_ai_token(user_id=int(user.id), role="user")
    headers = {"Authorization": f"Bearer {token}"}
    convo_id = str(uuid.uuid4())
    client_message_id = "msg-await-1"
    convo = AIConversation(id=convo_id, user_id=user.id, title="Await", created_at=utcnow(), updated_at=utcnow())
    db_session.add(convo)
    db_session.add(
        AIMessage(
            conversation_id=convo_id,
            user_id=user.id,
            role="user",
            content="test3",
            client_message_id=client_message_id,
            created_at=utcnow(),
        )
    )
    db_session.add(
        AIMessage(
            conversation_id=convo_id,
            user_id=user.id,
            role="assistant",
            content="Ready when you are.",
            created_at=utcnow(),
        )
    )
    db_session.commit()

    resp = client.post(
        "/api/ai/v1/chat/await",
        json={
            "conversation_id": convo_id,
            "client_message_id": client_message_id,
            "wait_seconds": 1,
        },
        content_type="application/json",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("ready") is True
    assert data.get("reply") == "Ready when you are."
    assert data.get("conversation_id") == convo_id


@pytest.mark.api
def test_ai_chat_duplicate_post_does_not_start_a_second_run(client, app, db_session):
    """POST /chat while that client_message_id is already running returns 409."""
    from app.services.ai.chat.inflight_turns import begin_turn, finish_turn

    user = create_test_user(db_session, email="ai_dup@test.local", name="AI Dup", role="user")
    with app.app_context():
        token = issue_ai_token(user_id=int(user.id), role="user")
    headers = {"Authorization": f"Bearer {token}"}
    convo_id = str(uuid.uuid4())
    client_message_id = "msg-dup-1"
    _turn, created = begin_turn(
        user_id=int(user.id),
        client_message_id=client_message_id,
        conversation_id=convo_id,
        request_id="owner-request",
    )
    assert created is True
    try:
        resp = client.post(
            "/api/ai/v1/chat",
            json={
                "message": "test3",
                "conversation_id": convo_id,
                "client_message_id": client_message_id,
            },
            content_type="application/json",
            headers=headers,
        )
        assert resp.status_code == 409
        data = resp.get_json()
        assert data.get("error_type") == "turn_in_progress"
    finally:
        finish_turn(user_id=int(user.id), client_message_id=client_message_id, status="cancelled")


@pytest.mark.api
def test_ai_chat_request_parse_helpers(app):
    """Shared parse_chat_request and resolve helpers behave correctly."""
    from app.services.ai.chat.request import (
        parse_chat_request,
        apply_anonymous_rules,
        ChatRequestParsed,
    )

    with app.app_context():
        parsed, err, code = parse_chat_request({})
        assert err is not None
        assert code == 400

        parsed, err, code = parse_chat_request({"message": "Hi"})
        assert err is None
        assert parsed is not None
        assert isinstance(parsed, ChatRequestParsed)
        assert parsed.message == "Hi"
        assert parsed.preferred_language == "en"

        applied = apply_anonymous_rules(parsed)
        assert applied.conversation_id is None
        assert applied.conversation_history == []
        assert applied.client_message_id is None
        assert applied.branch_from_edit is False


@pytest.mark.api
@pytest.mark.db
def test_ai_chat_list_export_and_delete_all(client, app, db_session, tmp_path):
    # Create user
    user = create_test_user(db_session, email="ai@test.local", name="AI Tester", role="user")

    # Issue bearer token for AI endpoints
    with app.app_context():
        token = issue_ai_token(user_id=int(user.id), role="user")

    headers = {"Authorization": f"Bearer {token}"}

    # Create a conversation + messages in DB
    convo_id = str(uuid.uuid4())
    convo = AIConversation(id=convo_id, user_id=user.id, title="Test convo", created_at=utcnow(), updated_at=utcnow())
    db_session.add(convo)
    db_session.add(
        AIMessage(conversation_id=convo_id, user_id=user.id, role="user", content="Hello", created_at=utcnow())
    )
    db_session.add(
        AIMessage(conversation_id=convo_id, user_id=user.id, role="assistant", content="Hi!", created_at=utcnow())
    )
    db_session.commit()

    # List conversations
    resp = client.get("/api/ai/v1/conversations?limit=50", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert any(c["id"] == convo_id for c in data["conversations"])

    # Export conversation
    resp = client.get(f"/api/ai/v1/conversations/{convo_id}/export", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type", "").startswith("application/json")
    payload = json.loads(resp.data.decode("utf-8"))
    assert payload["conversation"]["id"] == convo_id
    assert len(payload["messages"]) == 2

    # Delete all requires confirmation
    resp = client.delete("/api/ai/v1/conversations", headers=headers)
    assert resp.status_code == 400

    resp = client.delete("/api/ai/v1/conversations?confirm=true", headers=headers)
    assert resp.status_code == 200
    out = resp.get_json()
    assert out["success"] is True
    assert out["deleted_conversations"] >= 1


@pytest.mark.api
@pytest.mark.db
def test_ai_chat_archived_conversation_loads_from_archive(client, app, db_session, tmp_path):
    # Ensure filesystem archiving writes to a temp directory
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    app.config["AI_CHAT_ARCHIVE_PROVIDER"] = "filesystem"
    app.config["AI_CHAT_ARCHIVE_DIR"] = "ai_chat_archives"

    user = create_test_user(db_session, email="archive@test.local", name="Archive Tester", role="user")

    # app fixture already pushes an app context; avoid nested contexts (they use a
    # separate scoped session and leave stale AIConversation rows in the outer one).
    token = issue_ai_token(user_id=int(user.id), role="user")
    headers = {"Authorization": f"Bearer {token}"}

    convo_id = str(uuid.uuid4())
    convo = AIConversation(id=convo_id, user_id=user.id, title="Archived convo", created_at=utcnow(), updated_at=utcnow())
    db_session.add(convo)
    db_session.add(
        AIMessage(conversation_id=convo_id, user_id=user.id, role="user", content="Archive me", created_at=utcnow())
    )
    db_session.commit()

    # Archive it (should delete DB messages and write archive file)
    archived = archive_conversation(conversation_id=convo_id, user_id=int(user.id), dry_run=False)
    assert archived is not None
    assert archived.is_archived is True
    assert archived.archive_provider == "filesystem"
    assert archived.archive_path

    # Archive file exists on disk
    full_path = os.path.join(app.config["UPLOAD_FOLDER"], archived.archive_path)
    assert os.path.exists(full_path)

    # GET conversation should read from archive
    resp = client.get(f"/api/ai/v1/conversations/{convo_id}?limit=200", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["meta"]["source"] == "archive"
    assert len(data["messages"]) == 1


@pytest.mark.api
def test_ai_token_requires_login(client):
    resp = client.get("/api/ai/v1/token", follow_redirects=False)
    # Flask-Login typically redirects to login for browser unauthenticated requests
    assert resp.status_code in (302, 401, 403)


@pytest.mark.api
def test_ai_token_issues_jwt_for_logged_in_user(logged_in_client):
    resp = logged_in_client.get("/api/ai/v1/token")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "token" in data


@pytest.mark.api
@pytest.mark.db
def test_ai_table_export_requires_auth(client):
    resp = client.post("/api/ai/v1/table/export", json={"rows": [["A"]]})
    assert resp.status_code == 401


@pytest.mark.api
@pytest.mark.db
def test_ai_table_export_validation_and_headers(client, app, db_session):
    user = create_test_user(db_session, email="table@test.local", name="Table Tester", role="user")
    with app.app_context():
        token = issue_ai_token(user_id=int(user.id), role="user")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/ai/v1/table/export", headers=headers, json={})
    assert resp.status_code == 400

    resp = client.post("/api/ai/v1/table/export", headers=headers, json={"rows": [["H1", "H2"], ["a", "b"]]})
    resp.close()
    assert resp.status_code == 200
    assert resp.headers.get("X-hum-databank-Export-Completed") == "1"
    assert resp.headers.get("X-hum-databank-Export-Filename") == "table-data.xlsx"


def _csrf_rejected(resp) -> bool:
    body = resp.get_json(silent=True) or {}
    return resp.status_code == 400 and body.get("csrf_refresh_required") is True


@pytest.mark.api
@pytest.mark.db
def test_ai_identity_prefers_bearer_over_cookie(app, client, db_session):
    """Mobile sends its stored session cookie *and* the AI token; the token must win."""
    from app.utils.ai.ai_request_user import resolve_ai_identity

    cookie_user = create_test_user(db_session, email="cookie-id@test.local", name="Cookie", role="user")
    bearer_user = create_test_user(db_session, email="bearer-id@test.local", name="Bearer", role="user")
    with app.app_context():
        cookie_id, bearer_id = int(cookie_user.id), int(bearer_user.id)
        token = issue_ai_token(user_id=bearer_id, role="user")
    with client.session_transaction() as sess:
        sess["_user_id"] = str(cookie_id)
        sess["_fresh"] = True

    with client.application.test_request_context(
        "/api/ai/v1/chat", method="POST", headers={"Authorization": f"Bearer {token}"}
    ):
        from flask import session as flask_session

        flask_session["_user_id"] = str(cookie_id)
        identity = resolve_ai_identity()
        assert identity.auth_source == "bearer"
        assert int(identity.user.id) == bearer_id

    with client.application.test_request_context("/api/ai/v1/chat", method="POST"):
        from flask import session as flask_session

        flask_session["_user_id"] = str(cookie_id)
        identity = resolve_ai_identity()
        assert identity.auth_source == "cookie"
        assert int(identity.user.id) == cookie_id

    # The SSE worker opens a context with no session. The stored user must stay
    # the caller, not follow current_user back to AnonymousUserMixin.
    with client.application.test_request_context("/api/ai/v1/chat/stream", method="POST"):
        assert int(identity.user.id) == cookie_id


@pytest.mark.api
@pytest.mark.db
def test_ai_post_with_cookie_and_bearer_skips_csrf_but_cookie_only_does_not(app, client, db_session, monkeypatch):
    user = create_test_user(db_session, email="csrf-mobile@test.local", name="Mobile", role="user")
    with app.app_context():
        uid = int(user.id)
        token = issue_ai_token(user_id=uid, role="user")
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)
    with client.session_transaction() as sess:
        sess["_user_id"] = str(uid)
        sess["_fresh"] = True

    cookie_only = client.post("/api/ai/v1/feedback", json={"trace_id": 1, "rating": "like"})
    assert _csrf_rejected(cookie_only)

    both = client.post(
        "/api/ai/v1/feedback",
        json={"trace_id": 1, "rating": "like"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert not _csrf_rejected(both), both.get_data(as_text=True)


def _dlp_confirm_mode(app, monkeypatch):
    monkeypatch.setitem(app.config, "AI_DLP_ENABLED", True)
    monkeypatch.setitem(app.config, "AI_DLP_MODE", "confirm")
    monkeypatch.setitem(app.config, "AI_DLP_AUTO_MASK_KINDS", ("email", "phone"))
    monkeypatch.setitem(app.config, "AI_MAX_MESSAGE_CHARS", 4000)
    monkeypatch.setitem(app.config, "OPENAI_API_KEY", "")


@pytest.mark.api
@pytest.mark.db
def test_ai_chat_dlp_asks_before_sending_a_credential(client, app, db_session, monkeypatch):
    """Confirm mode stops a credential before any provider call, naming only the finding kind."""
    _dlp_confirm_mode(app, monkeypatch)
    user = create_test_user(db_session, email="ai_dlp@test.local", name="AI DLP", role="user")
    with app.app_context():
        token = issue_ai_token(user_id=int(user.id), role="user")

    resp = client.post(
        "/api/ai/v1/chat",
        json={"message": "password: SuperSecret123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error_type"] == "dlp_requires_confirmation"
    assert data["dlp"]["findings"] == [{"kind": "password", "count": 1}]
    assert "SuperSecret123" not in resp.get_data(as_text=True)


@pytest.mark.api
@pytest.mark.db
def test_ai_chat_edit_branch_persists_masked_history(client, app, db_session, monkeypatch):
    """Regression: an edit/retry ("branch_from_edit") persisted the client's transcript
    verbatim, so text that DLP had masked, or that the user cancelled at the DLP dialog,
    still reached the database and the LLM."""
    _dlp_confirm_mode(app, monkeypatch)
    user = create_test_user(db_session, email="ai_dlp_edit@test.local", name="AI DLP Edit", role="user")
    with app.app_context():
        token = issue_ai_token(user_id=int(user.id), role="user")
    convo_id = str(uuid.uuid4())

    resp = client.post(
        "/api/ai/v1/chat",
        json={
            "message": "and my api_key=Zq8vR2xL9mN4pT7w",
            "conversation_id": convo_id,
            "branch_from_edit": True,
            "allow_sensitive": True,
            "conversationHistory": [
                {"isUser": True, "message": "mail me at jane@example.org"},
                {"isUser": False, "message": "Noted."},
                {"isUser": True, "message": "and my api_key=Zq8vR2xL9mN4pT7w"},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    # No provider is configured: the branch is persisted, then the LLM call fails.
    assert resp.status_code == 503
    rows = AIMessage.query.filter_by(conversation_id=convo_id).order_by(AIMessage.id).all()
    assert [(r.role, r.content) for r in rows] == [
        ("user", "mail me at [REDACTED_EMAIL]"),
        ("assistant", "Noted."),
        ("user", "and my api_key=[REDACTED_API_KEY]"),
    ]
    assert db_session.get(AIConversation, convo_id).title == "mail me at [REDACTED_EMAIL]"


@pytest.mark.api
def test_ai_chat_edit_branch_appends_the_screened_message_after_an_assistant_turn(app, monkeypatch):
    from app.services.ai.chat.request import ChatRequestParsed, _edit_branch_history

    _dlp_confirm_mode(app, monkeypatch)
    parsed = ChatRequestParsed(
        message="try again for [REDACTED_EMAIL]",
        page_context={},
        conversation_id=None,
        preferred_language="en",
        conversation_history=[
            {"isUser": True, "message": "mail a@b.com"},
            {"isUser": False, "message": "Done."},
        ],
        client_message_id=None,
        branch_from_edit=True,
    )
    with app.app_context():
        history = _edit_branch_history(parsed)
    assert history == [
        {"isUser": True, "message": "mail [REDACTED_EMAIL]"},
        {"isUser": False, "message": "Done."},
        {"isUser": True, "message": "try again for [REDACTED_EMAIL]"},
    ]


@pytest.mark.api
def test_ai_chat_anonymous_history_is_masked(app, monkeypatch):
    """Anonymous history comes from the client and goes to the LLM, so its user turns are masked."""
    from app.services.ai.chat.request import apply_anonymous_rules, parse_chat_request

    _dlp_confirm_mode(app, monkeypatch)
    with app.app_context():
        parsed, _err, _code = parse_chat_request(
            {
                "message": "Hi",
                "conversationHistory": [
                    {"isUser": True, "message": "password: SuperSecret123"},
                    {"isUser": False, "message": "I can't use that."},
                ],
            }
        )
        applied = apply_anonymous_rules(parsed)
    assert applied.conversation_history == [
        {"isUser": True, "message": "password: [REDACTED_PASSWORD]"},
        {"isUser": False, "message": "I can't use that."},
    ]
