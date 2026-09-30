"""AI security controls: public proxy gate, tool allow-list, form-builder binding, WS limiter, budgets, ACL routes."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from flask import g

from app.extensions import db
from app.models import AIReasoningTrace, AIToolUsage, User
from app.models.embeddings import AIDocument
from app.utils.datetime_helpers import utcnow

pytestmark = [pytest.mark.unit]

SECRET = "proxy-secret-value"


class TestPublicProxyGate:
    def test_missing_secret_fails_closed_outside_local_dev(self, app, monkeypatch):
        from app.routes.ai import _is_allowed_public_proxy_request

        monkeypatch.delenv("AI_PUBLIC_PROXY_SECRET", raising=False)
        with app.test_request_context("/api/ai/v2/chat", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            assert _is_allowed_public_proxy_request() is False

    def test_empty_flask_config_is_not_local_dev(self, app, monkeypatch):
        from app.routes.ai import _is_allowed_public_proxy_request

        monkeypatch.delenv("AI_PUBLIC_PROXY_SECRET", raising=False)
        monkeypatch.setenv("FLASK_CONFIG", "")
        with app.test_request_context("/api/ai/v2/chat", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            assert _is_allowed_public_proxy_request() is False

    def test_explicit_local_dev_loopback_allowed_without_secret(self, app, monkeypatch):
        from app.routes.ai import _is_allowed_public_proxy_request

        monkeypatch.delenv("AI_PUBLIC_PROXY_SECRET", raising=False)
        with patch("app.routes.ai.is_local_dev_environment", return_value=True):
            with app.test_request_context("/api/ai/v2/chat", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
                assert _is_allowed_public_proxy_request() is True
            with app.test_request_context("/api/ai/v2/chat", environ_base={"REMOTE_ADDR": "203.0.113.9"}):
                assert _is_allowed_public_proxy_request() is False

    def test_secret_is_compared_in_constant_time(self, app, monkeypatch):
        from app.routes import ai as ai_module

        monkeypatch.setenv("AI_PUBLIC_PROXY_SECRET", SECRET)
        headers = {ai_module.PUBLIC_AI_PROXY_HEADER: SECRET}
        with app.test_request_context("/api/ai/v2/chat", headers=headers):
            with patch.object(ai_module.hmac, "compare_digest", wraps=ai_module.hmac.compare_digest) as spy:
                assert ai_module._is_allowed_public_proxy_request() is True
            spy.assert_called_once()

    @pytest.mark.parametrize("presented", [None, "", "wrong", SECRET + "x", SECRET[:-1]])
    def test_wrong_or_missing_secret_rejected(self, app, monkeypatch, presented):
        from app.routes import ai as ai_module

        monkeypatch.setenv("AI_PUBLIC_PROXY_SECRET", SECRET)
        headers = {ai_module.PUBLIC_AI_PROXY_HEADER: presented} if presented is not None else {}
        with app.test_request_context("/api/ai/v2/chat", headers=headers):
            assert ai_module._is_allowed_public_proxy_request() is False

    def test_anonymous_chat_endpoint_rejected_without_secret(self, client, monkeypatch):
        monkeypatch.delenv("AI_PUBLIC_PROXY_SECRET", raising=False)
        resp = client.post("/api/ai/v2/chat", json={"message": "hi"})
        assert resp.status_code == 401


@pytest.fixture
def registry(app):
    with app.app_context():
        with patch("app.services.ai.tools.registry.AIVectorStore"):
            from app.services.ai.tools import AIToolsRegistry

            yield AIToolsRegistry()


class TestAnonymousToolSurface:
    def test_tool_catalog_is_allowlisted_for_anonymous(self, app, registry):
        from app.services.ai.policies.access_policy import PUBLIC_TOOL_ALLOWLIST

        with app.test_request_context():
            g.ai_sources_cfg = None
            names = {t["function"]["name"] for t in registry.get_tool_definitions_openai()}
        assert names
        assert names <= PUBLIC_TOOL_ALLOWLIST

    def test_execute_tool_denies_non_allowlisted_tool_for_anonymous(self, app, registry):
        from app.services.ai.tools import ToolExecutionError

        with app.test_request_context():
            g.ai_sources_cfg = None
            with pytest.raises(ToolExecutionError):
                registry.execute_tool("get_assignment_indicator_values", assignment_id=1)

    def test_execute_tool_fails_closed_when_tool_list_unavailable(self, app, registry):
        from app.services.ai.tools import ToolExecutionError

        with app.test_request_context():
            with patch.object(registry, "get_tool_definitions_openai", side_effect=RuntimeError("boom")):
                with pytest.raises(ToolExecutionError):
                    registry.execute_tool("get_indicator_value", country_identifier="Kenya", indicator_name="x")

    def test_execute_tool_rejects_private_and_unknown_names(self, app, registry):
        from app.services.ai.tools import ToolExecutionError

        with app.test_request_context():
            for name in ("_private", "", "vector_store", "does_not_exist"):
                with pytest.raises(ToolExecutionError):
                    registry.execute_tool(name)


class TestFormBuilderBinding:
    def test_client_asserted_context_is_dropped_for_anonymous_and_bearer(self, app, system_manager_user):
        from app.utils.ai_utils import authorize_form_builder_context

        fb = {"enabled": True, "template_id": 1}
        with app.test_request_context():
            assert authorize_form_builder_context(fb, user_id=None) is None
            assert authorize_form_builder_context(fb, user_id=system_manager_user.id, auth_source="bearer") is None
            assert authorize_form_builder_context(fb, user_id=system_manager_user.id, auth_source="anonymous") is None

    def test_user_without_template_permission_is_denied(self, app, test_user):
        from app.utils.ai_utils import authorize_form_builder_context

        with app.test_request_context():
            assert authorize_form_builder_context({"enabled": True}, user_id=test_user.id) is None

    def test_manager_with_cookie_session_is_authorized_and_ids_validated(self, app, system_manager_user):
        from app.utils.ai_utils import authorize_form_builder_context

        with app.test_request_context():
            assert authorize_form_builder_context({"enabled": True}, user_id=system_manager_user.id) == {"enabled": True}
            assert authorize_form_builder_context(
                {"enabled": True, "version_id": 999999}, user_id=system_manager_user.id
            ) is None
            assert authorize_form_builder_context(
                {"enabled": True, "template_id": 999999, "version_id": 999999}, user_id=system_manager_user.id
            ) is None

    def test_explicitly_disabled_context_is_ignored(self, app, system_manager_user):
        from app.utils.ai_utils import authorize_form_builder_context

        with app.test_request_context():
            assert authorize_form_builder_context({"enabled": False}, user_id=system_manager_user.id) is None

    def test_trusted_context_requires_server_side_record(self, app):
        from app.services.ai.policies.access_policy import (
            record_form_builder_authorization,
            trusted_form_builder_context,
        )

        with app.test_request_context():
            assert trusted_form_builder_context() is None
            record_form_builder_authorization({"enabled": True, "template_id": 4})
            assert trusted_form_builder_context() == {"enabled": True, "template_id": 4}
            record_form_builder_authorization(None)
            assert trusted_form_builder_context() is None

    def test_bind_page_context_strips_unvouched_form_builder(self, app):
        from app.services.ai.policies.access_policy import PUBLIC_POLICY

        with app.test_request_context():
            bound = PUBLIC_POLICY.bind_page_context({"currentPage": "/x", "formBuilder": {"enabled": True}})
        assert "formBuilder" not in bound
        assert bound["currentPage"] == "/x"

    def test_executor_ignores_client_asserted_form_builder(self, app):
        from unittest.mock import patch as _patch

        with app.app_context(), app.test_request_context():
            app.config["AI_AGENT_ENABLED"] = True
            app.config["OPENAI_API_KEY"] = "test-key"
            with _patch("openai.OpenAI"):
                from app.services.ai.agent import AIAgentExecutor

                agent = AIAgentExecutor()
                captured = {}

                def _capture(*a, **k):
                    captured["fb"] = getattr(g, "ai_form_builder_ctx", "UNSET")
                    return {"success": True, "answer": "ok", "steps": [], "status": "completed", "tool_calls": 0, "iterations": 1}

                with (
                    _patch.object(agent.trace_service, "create_trace", return_value=None),
                    _patch.object(agent.trace_service, "finalize_trace", return_value=None),
                    _patch.object(agent.query_planner, "plan_simple", return_value=None),
                    _patch.object(agent, "_execute_openai_native", side_effect=_capture),
                ):
                    agent.execute(
                        query="add a field",
                        user_context={"role": "admin", "page_context": {"formBuilder": {"enabled": True, "template_id": 5}}},
                        language="en",
                    )
        assert captured["fb"] is None


class TestWebSocketLimiter:
    def test_redis_failure_falls_back_to_strict_memory_limit(self, app):
        from app.routes import ai_ws

        app.config["REDIS_URL"] = "redis://unreachable.invalid:6379/0"
        ai_ws._GLOBAL_WS_RATE.clear()
        try:
            with app.test_request_context():
                with patch.object(ai_ws, "get_ws_redis_client", side_effect=ConnectionError("down")):
                    results = [
                        ai_ws._global_ws_allow(key="k-fail", window_seconds=60.0, max_events=4) for _ in range(4)
                    ]
        finally:
            app.config.pop("REDIS_URL", None)
        assert results[0] is None and results[1] is None
        assert results[2] is not None and results[3] is not None

    def test_missing_redis_client_also_falls_back(self, app):
        from app.routes import ai_ws

        app.config["REDIS_URL"] = "redis://x"
        ai_ws._GLOBAL_WS_RATE.clear()
        try:
            with app.test_request_context():
                with patch.object(ai_ws, "get_ws_redis_client", return_value=None):
                    results = [ai_ws._global_ws_allow(key="k-none", window_seconds=60.0, max_events=2) for _ in range(3)]
        finally:
            app.config.pop("REDIS_URL", None)
        assert results[0] is None
        assert results[1] is not None

    def test_memory_limiter_enforces_limit(self, app):
        from app.routes import ai_ws

        ai_ws._GLOBAL_WS_RATE.clear()
        with app.test_request_context():
            results = [ai_ws._global_ws_allow(key="k-mem", window_seconds=60.0, max_events=3) for _ in range(4)]
        assert results[:3] == [None, None, None]
        assert results[3] is not None

    def test_reauthorize_rejects_deactivated_user(self, app, test_user):
        from types import SimpleNamespace

        from app.routes.ai_ws import _ws_reauthorize

        with app.test_request_context():
            user = db.session.get(User, test_user.id)
            identity = SimpleNamespace(is_authenticated=True, user=user)
            assert _ws_reauthorize(identity) is None
            user.active = False
            err = _ws_reauthorize(identity)
            db.session.rollback()
        assert err and err["error_type"] == "auth_required"

    def test_reauthorize_enforces_cost_budget(self, app):
        from types import SimpleNamespace

        from app.routes.ai_ws import _ws_reauthorize
        from app.services.ai.policies.usage_budget import BudgetVerdict

        with app.test_request_context():
            with patch("app.routes.ai_ws.check_daily_cost_budget", return_value=BudgetVerdict(False, "anonymous", 30.0, 25.0)):
                err = _ws_reauthorize(SimpleNamespace(is_authenticated=False, user=None))
        assert err and err["error_type"] == "rate_limited"

    def test_docs_ws_rechecks_permission_per_action(self, app, test_user, system_manager_user):
        from app.routes.ai_ws import _docs_ws_still_authorized

        with app.test_request_context():
            assert _docs_ws_still_authorized(system_manager_user.id) is True
            assert _docs_ws_still_authorized(test_user.id) is False
            assert _docs_ws_still_authorized(None) is False
            assert _docs_ws_still_authorized(99999999) is False


class TestUsageBudget:
    def test_defaults_are_finite_and_zero_disables(self, app):
        from app.services.ai.policies.usage_budget import budget_setting, daily_request_limit_string

        assert 0 < budget_setting("AI_CHAT_DAILY_USER_LIMIT") < 1_000_000
        assert daily_request_limit_string("AI_CHAT_DAILY_USER_LIMIT") == "1500 per day"
        app.config["AI_CHAT_DAILY_USER_LIMIT"] = "0"
        try:
            assert daily_request_limit_string("AI_CHAT_DAILY_USER_LIMIT").startswith("100000000")
        finally:
            app.config["AI_CHAT_DAILY_USER_LIMIT"] = None

    def test_invalid_value_falls_back_to_default(self, app):
        from app.services.ai.policies.usage_budget import budget_setting

        app.config["AI_DAILY_COST_BUDGET_USER_USD"] = "not-a-number"
        try:
            assert budget_setting("AI_DAILY_COST_BUDGET_USER_USD") == 10.0
        finally:
            app.config["AI_DAILY_COST_BUDGET_USER_USD"] = None

    def test_user_and_anonymous_cost_budgets(self, app, db_session, test_user):
        from app.services.ai.policies.usage_budget import check_daily_cost_budget, reset_budget_cache

        app.config["AI_DAILY_COST_BUDGET_USER_USD"] = "1.0"
        app.config["AI_DAILY_COST_BUDGET_ANON_USD"] = "0.5"
        app.config["AI_DAILY_COST_BUDGET_SYSTEM_USD"] = "0"
        reset_budget_cache()
        try:
            with app.app_context():
                db_session.add(AIReasoningTrace(user_id=test_user.id, query="q", steps=[], total_cost_usd=1.5))
                db_session.add(AIReasoningTrace(user_id=None, query="q", steps=[], total_cost_usd=0.2))
                db_session.commit()
                verdict = check_daily_cost_budget(test_user.id)
                assert not verdict.allowed and verdict.scope == "user"
                assert check_daily_cost_budget(None).allowed
                db_session.add(AIReasoningTrace(user_id=None, query="q", steps=[], total_cost_usd=0.4))
                db_session.commit()
                reset_budget_cache()
                anon = check_daily_cost_budget(None)
                assert not anon.allowed and anon.scope == "anonymous"
        finally:
            for k in ("USER", "ANON", "SYSTEM"):
                app.config[f"AI_DAILY_COST_BUDGET_{k}_USD"] = None
            reset_budget_cache()

    def test_chat_endpoint_returns_429_when_budget_spent(self, client, app, db_session, monkeypatch):
        from app.services.ai.policies.usage_budget import BudgetVerdict

        monkeypatch.setenv("AI_PUBLIC_PROXY_SECRET", SECRET)
        with patch(
            "app.routes.ai.check_daily_cost_budget", return_value=BudgetVerdict(False, "system", 300.0, 250.0)
        ):
            resp = client.post(
                "/api/ai/v2/chat",
                json={"message": "hi"},
                headers={"X-hum-databank-AI-Proxy": SECRET},
            )
        assert resp.status_code == 429
        assert resp.get_json()["error_type"] == "budget_exceeded"


class TestTracePrivacy:
    def test_text_is_masked_by_default(self, app):
        from app.services.ai.quality.trace_privacy import redact_text

        with app.app_context():
            out = redact_text("mail jane.doe@example.org password: hunter22 done")
        assert "jane.doe@example.org" not in out
        assert "hunter22" not in out

    def test_full_mode_keeps_legacy_behaviour_and_minimal_drops_values(self, app):
        from app.services.ai.quality.trace_privacy import redact_payload, redact_text

        with app.app_context():
            app.config["AI_TRACE_STORE_MODE"] = "full"
            try:
                assert redact_text("a@b.org") == "a@b.org"
                app.config["AI_TRACE_STORE_MODE"] = "minimal"
                out = redact_payload({"result": {"country": "Kenya", "value": 12}, "note": "secret text"})
                assert "Kenya" not in str(out) and "secret text" not in str(out)
            finally:
                app.config["AI_TRACE_STORE_MODE"] = "redacted"

    def test_payload_redaction_masks_sensitive_keys_and_strings(self, app):
        from app.services.ai.quality.trace_privacy import redact_payload

        with app.app_context():
            out = redact_payload({"token": "abc", "rows": [{"contact": "x@y.org"}]})
        assert out["token"] != "abc"
        assert "x@y.org" not in str(out)

    def test_tool_usage_row_is_persisted_redacted(self, app, db_session):
        from app.services.ai.tools._utils import log_tool_usage

        with app.test_request_context():
            trace = AIReasoningTrace(query="q", steps=[])
            db_session.add(trace)
            db_session.commit()
            g.ai_trace_id = trace.id
            log_tool_usage(
                tool_name="t",
                tool_input={"who": "bob@example.org"},
                tool_output={"emails": ["carol@example.org"]},
                success=True,
                error_message=None,
                execution_time_ms=1,
                user_id=None,
            )
            db_session.commit()
            row = db_session.query(AIToolUsage).filter_by(trace_id=trace.id).one()
            assert "bob@example.org" not in str(row.tool_input)
            assert "carol@example.org" not in str(row.tool_output)

    def test_trace_service_redacts_query_and_steps(self, app, db_session):
        from app.services.ai.quality.reasoning_trace import AIReasoningTraceService

        with app.app_context():
            svc = AIReasoningTraceService()
            trace_id = svc.create_trace(
                query="call me on dave@example.org", user_id=None, conversation_id=None, llm_provider="x", llm_model="y"
            )
            svc.finalize_trace(
                trace_id=trace_id,
                query="call me on dave@example.org",
                user_id=None,
                conversation_id=None,
                steps=[{"action": "t", "action_input": {"e": "erin@example.org"}, "observation": {"m": "frank@example.org"}}],
                final_answer="reach gina@example.org",
                status="completed",
                total_cost=0.0,
            )
            row = db.session.get(AIReasoningTrace, trace_id)
            blob = " ".join([row.query, row.final_answer or "", str(row.steps)])
        for leaked in ("dave@", "erin@", "frank@", "gina@"):
            assert leaked not in blob

    def test_purge_scrubs_old_content_but_keeps_cost(self, app, db_session):
        from app.services.ai.quality.trace_privacy import PURGED_TEXT, purge_expired_trace_content

        old = utcnow() - timedelta(days=400)
        with app.app_context():
            trace = AIReasoningTrace(query="secret question", steps=[{"observation": "data"}], final_answer="ans", total_cost_usd=0.7, created_at=old)
            db_session.add(trace)
            db_session.flush()
            usage = AIToolUsage(trace_id=trace.id, tool_name="t", tool_input={"a": 1}, tool_output={"b": 2}, created_at=old)
            db_session.add(usage)
            db_session.commit()
            stats = purge_expired_trace_content()
            assert stats["traces_scrubbed"] >= 1 and stats["tool_usage_scrubbed"] >= 1
            db_session.expire_all()
            row = db_session.get(AIReasoningTrace, trace.id)
            assert row.query == PURGED_TEXT and row.final_answer is None and row.steps == []
            assert row.total_cost_usd == 0.7
            assert db_session.get(AIToolUsage, usage.id).tool_output is None
            assert purge_expired_trace_content()["traces_scrubbed"] == 0

    def test_raw_output_visibility_defaults_to_system_managers(self, app, admin_user, system_manager_user):
        from app.services.ai.quality.trace_privacy import can_view_raw_tool_output, strip_raw_outputs

        with app.test_request_context():
            assert can_view_raw_tool_output(db.session.get(User, system_manager_user.id)) is True
            assert can_view_raw_tool_output(db.session.get(User, admin_user.id)) is False
            assert can_view_raw_tool_output(None) is False
        stripped = strip_raw_outputs({"steps": [{"action": "a", "observation": {"secret": 1}}]})
        assert stripped["steps"][0]["observation"] == {"redacted": True}


class TestDocumentAclRoutes:
    @pytest.fixture
    def docs(self, app, db_session, test_user, admin_user):
        with app.app_context():
            owner = db_session.get(User, admin_user.id)
            created = {
                "public": AIDocument(title="pub", filename="a.pdf", file_type="pdf", is_public=True, user_id=owner.id),
                "admins_only": AIDocument(
                    title="adm", filename="b.pdf", file_type="pdf", is_public=True, allowed_roles=["admin"], user_id=owner.id
                ),
                "private": AIDocument(title="priv", filename="c.pdf", file_type="pdf", is_public=False, user_id=owner.id),
            }
            for d in created.values():
                db_session.add(d)
            db_session.commit()
            yield {k: v.id for k, v in created.items()}
            for d in created.values():
                obj = db_session.get(AIDocument, d.id)
                if obj is not None:
                    db_session.delete(obj)
            db_session.commit()

    def test_get_document_enforces_acl_matrix(self, client, docs, test_user):
        from tests.helpers import login_session

        login_session(client, test_user.id)
        assert client.get(f"/api/ai/documents/{docs['public']}").status_code == 200
        assert client.get(f"/api/ai/documents/{docs['admins_only']}").status_code == 403
        assert client.get(f"/api/ai/documents/{docs['private']}").status_code == 403

    def test_list_documents_only_returns_readable(self, client, docs, test_user):
        from tests.helpers import login_session

        login_session(client, test_user.id)
        resp = client.get("/api/ai/documents/")
        assert resp.status_code == 200
        ids = {d["id"] for d in resp.get_json()["documents"]}
        assert docs["public"] in ids
        assert docs["admins_only"] not in ids
        assert docs["private"] not in ids

    def test_admin_sees_everything(self, logged_in_client, docs):
        resp = logged_in_client.get("/api/ai/documents/")
        ids = {d["id"] for d in resp.get_json()["documents"]}
        assert set(docs.values()) <= ids

    def test_allowed_roles_normalisation(self):
        from app.services.ai.documents.access import normalize_allowed_roles

        assert normalize_allowed_roles(None) == (True, None)
        assert normalize_allowed_roles("") == (True, None)
        assert normalize_allowed_roles("Admin, focal_point") == (True, ["admin", "focal_point"])
        assert normalize_allowed_roles([]) == (True, [])
        assert normalize_allowed_roles("bad role!")[0] is False
        assert normalize_allowed_roles(5)[0] is False
        assert normalize_allowed_roles([f"r{i}" for i in range(50)])[0] is False
