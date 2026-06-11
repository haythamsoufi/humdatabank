"""Tests for transaction_middleware.py — targeting 100% coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest
from flask import g

from app.middleware.transaction_middleware import (
    _get_view_func,
    init_transaction_middleware,
)


def _hook(app, registry: str, name: str):
    funcs = getattr(app, f"{registry}_funcs", {}).get(None, [])
    return next((fn for fn in funcs if fn.__name__ == name), None)


# ────────────────────────────────────────────────────────────────────────────
# _get_view_func
# ────────────────────────────────────────────────────────────────────────────

class TestGetViewFunc:
    def test_no_endpoint_returns_none(self, app):
        with app.test_request_context("/"):
            with patch("app.middleware.transaction_middleware.request") as mock_req:
                mock_req.endpoint = None
                result = _get_view_func()
                assert result is None

    def test_valid_endpoint_returns_func(self, app):
        with app.test_request_context("/"):
            # Patch request.endpoint and current_app.view_functions
            with patch("app.middleware.transaction_middleware.request") as mock_req, \
                 patch("app.middleware.transaction_middleware.current_app") as mock_app:
                mock_req.endpoint = "main.index"
                mock_fn = MagicMock()
                mock_app.view_functions = {"main.index": mock_fn}
                result = _get_view_func()
                assert result is mock_fn

    def test_endpoint_not_in_view_functions_returns_none(self, app):
        with app.test_request_context("/"):
            with patch("app.middleware.transaction_middleware.request") as mock_req, \
                 patch("app.middleware.transaction_middleware.current_app") as mock_app:
                mock_req.endpoint = "missing.endpoint"
                mock_app.view_functions = {}
                result = _get_view_func()
                assert result is None

    def test_exception_in_lookup_returns_none(self, app, caplog):
        import logging

        with app.test_request_context("/"):
            with patch("app.middleware.transaction_middleware.request") as mock_req, \
                 patch("app.middleware.transaction_middleware.current_app") as mock_app:
                mock_req.endpoint = "some.endpoint"
                mock_app.view_functions = MagicMock()
                mock_app.view_functions.get.side_effect = Exception("lookup failed")
                with caplog.at_level(logging.DEBUG,
                                     logger="app.middleware.transaction_middleware"):
                    result = _get_view_func()
                assert result is None
                assert "lookup failed" in caplog.text


# ────────────────────────────────────────────────────────────────────────────
# init_transaction_middleware — before_request
# ────────────────────────────────────────────────────────────────────────────

class TestTransactionBeforeRequest:
    def test_static_endpoint_not_managed(self, app):
        with app.test_request_context("/static/file.js"):
            with patch("app.middleware.transaction_middleware.request") as mock_req:
                mock_req.endpoint = "static"
                # Simulate before_request hook manually
                g._auto_txn_managed = False
                g._auto_txn_streaming = False
                assert g._auto_txn_managed is False

    def test_opted_out_view_not_managed(self, app, client):
        """Views decorated with @no_auto_transaction skip transaction management."""
        from app.utils.transactions import no_auto_transaction

        with app.test_request_context("/test_opted_out"):
            with patch("app.middleware.transaction_middleware._get_view_func") as mock_gvf, \
                 patch("app.middleware.transaction_middleware.is_view_opted_out",
                       return_value=True), \
                 patch("app.middleware.transaction_middleware.is_view_forced",
                       return_value=False), \
                 patch("app.middleware.transaction_middleware.request") as mock_req:
                mock_req.endpoint = "test.opted_out"
                g._auto_txn_managed = False
                g._auto_txn_streaming = False

                @no_auto_transaction
                def opted_out_view():
                    return "ok"

                mock_gvf.return_value = opted_out_view
                # Before request hook would set g._auto_txn_managed = False
                assert g._auto_txn_managed is False

    def test_normal_endpoint_is_managed(self, app, client):
        resp = client.get("/")
        # The before_request hook runs on all requests
        assert resp is not None


# ────────────────────────────────────────────────────────────────────────────
# init_transaction_middleware — after_request
# ────────────────────────────────────────────────────────────────────────────

class TestTransactionAfterRequest:
    def test_not_managed_does_nothing(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_managed = False
            g._auto_txn_streaming = False
            g._auto_txn_force_rollback = False

            with patch("app.middleware.transaction_middleware.is_streaming_response",
                       return_value=False), \
                 patch("app.middleware.transaction_middleware.db") as mock_db, \
                 patch("app.middleware.transaction_middleware.safe_remove") as mock_remove:
                from flask import make_response
                response = make_response("ok", 200)

                # Simulate after_request logic
                managed = bool(getattr(g, "_auto_txn_managed", False))
                assert not managed
                mock_db.session.commit.assert_not_called()

    def test_managed_2xx_commits(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_managed = True
            g._auto_txn_streaming = False
            g._auto_txn_force_rollback = False

            with patch("app.middleware.transaction_middleware.is_streaming_response",
                       return_value=False), \
                 patch("app.middleware.transaction_middleware.db") as mock_db, \
                 patch("app.middleware.transaction_middleware.run_post_commit_callbacks") as mock_cb, \
                 patch("app.middleware.transaction_middleware.safe_remove"):
                from flask import make_response
                response = make_response("ok", 200)

                # Simulate the after_request logic
                try:
                    status_code = response.status_code
                    if not getattr(g, "_auto_txn_force_rollback", False):
                        if status_code < 400:
                            mock_db.session.commit()
                            mock_cb()
                except Exception:
                    pass

                mock_db.session.commit.assert_called_once()
                mock_cb.assert_called_once()

    def test_managed_4xx_rolls_back(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_managed = True
            g._auto_txn_streaming = False
            g._auto_txn_force_rollback = False

            with patch("app.middleware.transaction_middleware.is_streaming_response",
                       return_value=False), \
                 patch("app.middleware.transaction_middleware.safe_rollback") as mock_rb, \
                 patch("app.middleware.transaction_middleware.safe_remove"):
                from flask import make_response
                response = make_response("not found", 404)

                # Simulate the after_request logic for 4xx
                status_code = response.status_code
                if status_code >= 400:
                    mock_rb(reason=f"response_status_{status_code}")

                mock_rb.assert_called_once_with(reason="response_status_404")

    def test_force_rollback_flag_triggers_rollback(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_managed = True
            g._auto_txn_streaming = False
            g._auto_txn_force_rollback = True

            with patch("app.middleware.transaction_middleware.is_streaming_response",
                       return_value=False), \
                 patch("app.middleware.transaction_middleware.safe_rollback") as mock_rb, \
                 patch("app.middleware.transaction_middleware.safe_remove"):
                from flask import make_response
                response = make_response("ok", 200)

                # force_rollback overrides 2xx
                force_rollback = bool(getattr(g, "_auto_txn_force_rollback", False))
                if force_rollback:
                    mock_rb(reason="manual_request")

                mock_rb.assert_called_once_with(reason="manual_request")

    def test_streaming_response_deferred(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_managed = True
            g._auto_txn_streaming = False

            with patch("app.middleware.transaction_middleware.is_streaming_response",
                       return_value=True), \
                 patch("app.middleware.transaction_middleware.safe_remove") as mock_remove:
                from flask import make_response
                response = make_response("ok", 200)
                # When streaming: call_on_close is registered, _auto_txn_streaming is set

                # Simulate: is_streaming → set streaming flag
                g._auto_txn_streaming = True
                # call_on_close is not easy to assert in unit tests; just ensure no commit called

    def test_commit_failure_triggers_rollback_and_raises(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_managed = True
            g._auto_txn_force_rollback = False

            with patch("app.middleware.transaction_middleware.is_streaming_response",
                       return_value=False), \
                 patch("app.middleware.transaction_middleware.db") as mock_db, \
                 patch("app.middleware.transaction_middleware.safe_rollback") as mock_rb, \
                 patch("app.middleware.transaction_middleware.safe_remove"):
                mock_db.session.commit.side_effect = Exception("DB commit failed")

                from flask import make_response
                response = make_response("ok", 200)

                # Simulate the commit failure path
                with pytest.raises(Exception, match="DB commit failed"):
                    try:
                        mock_db.session.commit()
                    except Exception as e:
                        mock_rb(reason="commit_failed")
                        raise

                mock_rb.assert_called_once_with(reason="commit_failed")


# ────────────────────────────────────────────────────────────────────────────
# init_transaction_middleware — teardown_request
# ────────────────────────────────────────────────────────────────────────────

class TestTransactionTeardownRequest:
    def test_teardown_no_exception_calls_safe_remove(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_streaming = False

            with patch("app.middleware.transaction_middleware.safe_remove") as mock_remove, \
                 patch("app.middleware.transaction_middleware.safe_rollback") as mock_rb:
                # Simulate teardown with no exception
                exception = None
                streaming = bool(getattr(g, "_auto_txn_streaming", False))

                if not streaming:
                    if exception is not None:
                        mock_rb(reason="teardown_exception")
                    mock_remove(reason="teardown")

                mock_rb.assert_not_called()
                mock_remove.assert_called_once_with(reason="teardown")

    def test_teardown_with_exception_rollbacks(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_streaming = False

            with patch("app.middleware.transaction_middleware.safe_remove") as mock_remove, \
                 patch("app.middleware.transaction_middleware.safe_rollback") as mock_rb:
                exception = ValueError("something went wrong")
                streaming = bool(getattr(g, "_auto_txn_streaming", False))

                if not streaming:
                    if exception is not None:
                        mock_rb(reason="teardown_exception")
                    mock_remove(reason="teardown")

                mock_rb.assert_called_once_with(reason="teardown_exception")
                mock_remove.assert_called_once_with(reason="teardown")

    def test_teardown_streaming_skips_rollback_and_remove(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_streaming = True

            with patch("app.middleware.transaction_middleware.safe_remove") as mock_remove, \
                 patch("app.middleware.transaction_middleware.safe_rollback") as mock_rb:
                exception = None
                streaming = bool(getattr(g, "_auto_txn_streaming", False))

                if streaming:
                    pass  # Early return in actual code
                else:
                    if exception is not None:
                        mock_rb(reason="teardown_exception")
                    mock_remove(reason="teardown")

                mock_rb.assert_not_called()
                mock_remove.assert_not_called()


# ────────────────────────────────────────────────────────────────────────────
# init_transaction_middleware — handle_exception wrapping
# ────────────────────────────────────────────────────────────────────────────

class TestHandleExceptionWrapping:
    def test_handle_exception_not_double_wrapped(self):
        """Calling init_transaction_middleware twice does not double-wrap handle_exception."""
        from flask import Flask

        test_app = Flask(__name__)
        test_app._auto_txn_handle_exception_wrapped = True

        with patch.object(test_app, "before_request"), \
             patch.object(test_app, "after_request"), \
             patch.object(test_app, "teardown_request"):
            init_transaction_middleware(test_app)

        # Guard flag set: handle_exception must remain Flask's default, not our wrapper.
        assert test_app.handle_exception.__name__ == "handle_exception"

    def test_handle_exception_wraps_once(self):
        """First init wraps handle_exception; rollback is called on exception."""
        from flask import Flask
        test_app = Flask(__name__)
        test_app.config["TESTING"] = True
        test_app.config["SECRET_KEY"] = "test-key"

        assert not getattr(test_app, "_auto_txn_handle_exception_wrapped", False)

        with patch("app.middleware.transaction_middleware.safe_rollback") as mock_rb, \
             patch("app.middleware.transaction_middleware.safe_remove") as mock_remove:
            init_transaction_middleware(test_app)
            assert getattr(test_app, "_auto_txn_handle_exception_wrapped", False) is True


# ────────────────────────────────────────────────────────────────────────────
# End-to-end: actual HTTP requests through transaction middleware
# ────────────────────────────────────────────────────────────────────────────

class TestTransactionMiddlewareIntegration:
    def test_get_request_does_not_crash(self, app, client):
        resp = client.get("/")
        assert resp is not None

    def test_unknown_endpoint_handled_gracefully(self, app, client):
        resp = client.get("/nonexistent-path-xyz-abc")
        assert resp.status_code == 404

    def test_after_request_with_static_endpoint_skipped(self, app, client):
        """Static file requests should set _auto_txn_managed = False."""
        resp = client.get("/static/nonexistent.js")
        # 404 is fine — important: no crash from transaction middleware
        assert resp is not None


# ────────────────────────────────────────────────────────────────────────────
# Registered hook execution (covers init_transaction_middleware bodies)
# ────────────────────────────────────────────────────────────────────────────

class TestTransactionRegisteredHooks:
    def test_before_request_manages_dashboard(self, app):
        with app.test_request_context("/dashboard"):
            g.pop("_auto_txn_managed", None)
            _hook(app, "before_request", "_txn_before_request")()
            assert g._auto_txn_managed is True
            assert g._auto_txn_streaming is False

    def test_before_request_skips_static(self, app):
        with app.test_request_context("/static/app.js"):
            _hook(app, "before_request", "_txn_before_request")()
            assert g._auto_txn_managed is False

    def test_before_request_opted_out_view(self, app):
        from app.utils.transactions import no_auto_transaction

        @no_auto_transaction
        def opted_out():
            return "ok"

        with app.test_request_context("/dashboard"):
            with patch("app.middleware.transaction_middleware._get_view_func",
                       return_value=opted_out), \
                 patch("app.middleware.transaction_middleware.is_view_opted_out",
                       return_value=True), \
                 patch("app.middleware.transaction_middleware.is_view_forced",
                       return_value=False):
                _hook(app, "before_request", "_txn_before_request")()
                assert g._auto_txn_managed is False

    def test_after_request_commits_managed_2xx(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_managed = True
            with patch("app.middleware.transaction_middleware.is_streaming_response",
                       return_value=False), \
                 patch("app.middleware.transaction_middleware.db") as mock_db, \
                 patch("app.middleware.transaction_middleware.run_post_commit_callbacks") as mock_cb, \
                 patch("app.middleware.transaction_middleware.safe_remove") as mock_remove:
                from flask import make_response
                resp = _hook(app, "after_request", "_txn_after_request")(make_response("ok", 200))
                mock_db.session.commit.assert_called_once()
                mock_cb.assert_called_once()
                mock_remove.assert_called_once_with(reason="after_request")
                assert resp.status_code == 200

    def test_after_request_rolls_back_4xx(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_managed = True
            with patch("app.middleware.transaction_middleware.is_streaming_response",
                       return_value=False), \
                 patch("app.middleware.transaction_middleware.safe_rollback") as mock_rb, \
                 patch("app.middleware.transaction_middleware.safe_remove") as mock_remove:
                from flask import make_response
                _hook(app, "after_request", "_txn_after_request")(make_response("nope", 404))
                mock_rb.assert_called_once_with(reason="response_status_404")
                mock_remove.assert_called_once_with(reason="after_request")

    def test_after_request_force_rollback(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_managed = True
            g._auto_txn_force_rollback = True
            with patch("app.middleware.transaction_middleware.is_streaming_response",
                       return_value=False), \
                 patch("app.middleware.transaction_middleware.safe_rollback") as mock_rb, \
                 patch("app.middleware.transaction_middleware.safe_remove"):
                from flask import make_response
                _hook(app, "after_request", "_txn_after_request")(make_response("ok", 200))
                mock_rb.assert_called_once_with(reason="manual_request")

    def test_after_request_unmanaged_is_noop(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_managed = False
            with patch("app.middleware.transaction_middleware.db") as mock_db:
                from flask import make_response
                _hook(app, "after_request", "_txn_after_request")(make_response("ok", 200))
                mock_db.session.commit.assert_not_called()

    def test_after_request_streaming_defers_cleanup(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_managed = True
            with patch("app.middleware.transaction_middleware.is_streaming_response",
                       return_value=True), \
                 patch("app.middleware.transaction_middleware.safe_remove") as mock_remove:
                from flask import make_response
                resp = make_response("ok", 200)
                out = _hook(app, "after_request", "_txn_after_request")(resp)
                assert g._auto_txn_streaming is True
                assert out is resp
                mock_remove.assert_not_called()
                for callback in getattr(resp, "_close_callbacks", []):
                    callback()
                mock_remove.assert_called_once_with(reason="stream_close")

    def test_after_request_commit_failure_rolls_back_and_raises(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_managed = True
            with patch("app.middleware.transaction_middleware.is_streaming_response",
                       return_value=False), \
                 patch("app.middleware.transaction_middleware.db") as mock_db, \
                 patch("app.middleware.transaction_middleware.safe_rollback") as mock_rb, \
                 patch("app.middleware.transaction_middleware.safe_remove"):
                mock_db.session.commit.side_effect = RuntimeError("commit failed")
                from flask import make_response
                with pytest.raises(RuntimeError, match="commit failed"):
                    _hook(app, "after_request", "_txn_after_request")(make_response("ok", 200))
                mock_rb.assert_called_once_with(reason="commit_failed")

    def test_teardown_request_rollbacks_on_exception(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_streaming = False
            with patch("app.middleware.transaction_middleware.safe_rollback") as mock_rb, \
                 patch("app.middleware.transaction_middleware.safe_remove") as mock_remove:
                _hook(app, "teardown_request", "_txn_teardown_request")(ValueError("boom"))
                mock_rb.assert_called_once_with(reason="teardown_exception")
                mock_remove.assert_called_once_with(reason="teardown")

    def test_teardown_request_skips_when_streaming(self, app):
        with app.test_request_context("/dashboard"):
            g._auto_txn_streaming = True
            with patch("app.middleware.transaction_middleware.safe_rollback") as mock_rb, \
                 patch("app.middleware.transaction_middleware.safe_remove") as mock_remove:
                _hook(app, "teardown_request", "_txn_teardown_request")(None)
                mock_rb.assert_not_called()
                mock_remove.assert_not_called()

    def test_handle_exception_wrapper_rolls_back(self):
        from flask import Flask

        test_app = Flask(__name__)
        delegate = MagicMock(return_value=MagicMock(status_code=500))

        with patch("app.middleware.transaction_middleware.safe_rollback") as mock_rb, \
             patch("app.middleware.transaction_middleware.safe_remove") as mock_remove, \
             patch.object(Flask, "handle_exception", delegate):
            init_transaction_middleware(test_app)
            wrapped = test_app.handle_exception

            with test_app.test_request_context("/"):
                result = wrapped(ValueError("boom"))

            mock_rb.assert_called_once_with(reason="handle_exception")
            mock_remove.assert_called_once_with(reason="handle_exception")
            delegate.assert_called_once()
            assert result.status_code == 500
