import json
import os
import uuid

import pytest

from app.models.ai_chat import AIConversation, AIMessage
from app.utils.ai_tokens import issue_ai_token
from app.services.ai_chat_retention import archive_conversation
from app.utils.datetime_helpers import utcnow
from tests.factories import create_test_user


@pytest.mark.api
def test_ai_health_returns_checks_and_agent_available(client, app):
    """Health endpoint returns 200 and includes config checks and agent_available."""
    resp = client.get("/api/ai/v2/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "checks" in data
    assert "openai_key" in data["checks"]
    assert "embedding_provider" in data["checks"]
    assert "agent_available" in data["checks"]
    assert isinstance(data["checks"]["agent_available"], bool)


@pytest.mark.api
def test_ai_conversations_require_auth(client, app):
    """Conversations list requires authentication; no auth returns 401."""
    resp = client.get("/api/ai/v2/conversations")
    assert resp.status_code == 401
    data = resp.get_json()
    assert data.get("success") is False
    assert "error" in data or "Authentication" in (data.get("error") or "")


@pytest.mark.api
def test_ai_conversations_invalid_bearer_rejected(client, app):
    """Conversations with invalid Bearer token returns 401."""
    resp = client.get("/api/ai/v2/conversations", headers={"Authorization": "Bearer invalid-token"})
    assert resp.status_code == 401


@pytest.mark.api
def test_ai_chat_validation_message_required(client, app):
    """POST /api/ai/v2/chat returns 400 when message is missing or empty."""
    resp = client.post(
        "/api/ai/v2/chat",
        json={},
        content_type="application/json",
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data.get("success") is False
    assert "message" in (data.get("error") or "").lower() or "required" in (data.get("error") or "").lower()

    resp = client.post(
        "/api/ai/v2/chat",
        json={"message": "   "},
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.api
def test_ai_chat_validation_message_too_long(client, app):
    """POST /api/ai/v2/chat returns 413 when message exceeds AI_MAX_MESSAGE_CHARS."""
    app.config["AI_MAX_MESSAGE_CHARS"] = 50
    long_message = "x" * 51
    resp = client.post(
        "/api/ai/v2/chat",
        json={"message": long_message},
        content_type="application/json",
    )
    assert resp.status_code == 413
    data = resp.get_json()
    assert data.get("success") is False


@pytest.mark.api
def test_ai_chat_returns_success_with_fallback(client, app):
    """POST /api/ai/v2/chat returns 200 and a reply (fallback when no API keys)."""
    resp = client.post(
        "/api/ai/v2/chat",
        json={"message": "Hello, what can you do?"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("success") is True
    assert "reply" in data
    assert data.get("meta", {}).get("provider") in ("fallback", "openai", "gemini", "azure", "agent")


@pytest.mark.api
def test_ai_chat_stream_validation(client, app):
    """POST /api/ai/v2/chat/stream returns 400 when message is empty."""
    resp = client.post(
        "/api/ai/v2/chat/stream",
        json={"message": ""},
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.api
def test_ai_chat_stream_returns_sse_meta_and_done(client, app):
    """POST /api/ai/v2/chat/stream returns SSE with meta and done events."""
    resp = client.post(
        "/api/ai/v2/chat/stream",
        json={"message": "Say hello in one word."},
        content_type="application/json",
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
def test_ai_chat_request_parse_helpers(app):
    """Shared parse_chat_request and resolve helpers behave correctly."""
    from app.services.ai_chat_request import (
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
    resp = client.get("/api/ai/v2/conversations?limit=50", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert any(c["id"] == convo_id for c in data["conversations"])

    # Export conversation
    resp = client.get(f"/api/ai/v2/conversations/{convo_id}/export", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type", "").startswith("application/json")
    payload = json.loads(resp.data.decode("utf-8"))
    assert payload["conversation"]["id"] == convo_id
    assert len(payload["messages"]) == 2

    # Delete all requires confirmation
    resp = client.delete("/api/ai/v2/conversations", headers=headers)
    assert resp.status_code == 400

    resp = client.delete("/api/ai/v2/conversations?confirm=true", headers=headers)
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

    with app.app_context():
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
    with app.app_context():
        archived = archive_conversation(conversation_id=convo_id, user_id=int(user.id), dry_run=False)
        assert archived is not None
        assert archived.is_archived is True
        assert archived.archive_provider == "filesystem"
        assert archived.archive_path

        # Archive file exists on disk
        full_path = os.path.join(app.config["UPLOAD_FOLDER"], archived.archive_path)
        assert os.path.exists(full_path)

    # GET conversation should read from archive
    resp = client.get(f"/api/ai/v2/conversations/{convo_id}?limit=200", headers=headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["meta"]["source"] == "archive"
    assert len(data["messages"]) == 1


@pytest.mark.api
def test_ai_token_requires_login(client):
    resp = client.get("/api/ai/v2/token", follow_redirects=False)
    # Flask-Login typically redirects to login for browser unauthenticated requests
    assert resp.status_code in (302, 401, 403)


@pytest.mark.api
def test_ai_token_issues_jwt_for_logged_in_user(logged_in_client):
    resp = logged_in_client.get("/api/ai/v2/token")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "token" in data


@pytest.mark.api
@pytest.mark.db
def test_ai_table_export_requires_auth(client):
    resp = client.post("/api/ai/v2/table/export", json={"rows": [["A"]]})
    assert resp.status_code == 401


@pytest.mark.api
@pytest.mark.db
def test_ai_table_export_validation_and_headers(client, app, db_session):
    user = create_test_user(db_session, email="table@test.local", name="Table Tester", role="user")
    with app.app_context():
        token = issue_ai_token(user_id=int(user.id), role="user")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/ai/v2/table/export", headers=headers, json={})
    assert resp.status_code == 400

    resp = client.post("/api/ai/v2/table/export", headers=headers, json={"rows": [["H1", "H2"], ["a", "b"]]})
    resp.close()
    assert resp.status_code == 200
    assert resp.headers.get("X-NGO-Databank-Export-Completed") == "1"
    assert resp.headers.get("X-NGO-Databank-Export-Filename") == "table-data.xlsx"
