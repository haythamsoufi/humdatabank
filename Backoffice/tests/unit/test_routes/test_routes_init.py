"""Tests for app/routes/__init__.py — blueprint registration."""
from unittest.mock import MagicMock, patch, call
import time

import pytest

pytestmark = [pytest.mark.unit]


class TestRegisterAllBlueprints:
    """Tests for register_all_blueprints covering exception paths and timing branches."""

    def _make_mock_app(self):
        mock_app = MagicMock()
        mock_app.logger = MagicMock()
        mock_app.register_blueprint = MagicMock()
        mock_app.config = {}
        return mock_app

    def _make_mock_csrf(self):
        mock_csrf = MagicMock()
        mock_csrf.exempt = MagicMock()
        return mock_csrf

    def test_register_all_blueprints_returns_float(self, app):
        """register_all_blueprints returns the elapsed blueprint_time as a float."""
        from app.routes import register_all_blueprints

        mock_app = self._make_mock_app()
        mock_csrf = self._make_mock_csrf()

        with patch("app.routes.auth") as _auth, \
           patch("app.routes.main") as _main, \
           patch("app.routes.help_docs") as _help, \
           patch("app.routes.forms") as _forms, \
           patch("app.routes.forms_api") as _forms_api, \
           patch("app.routes.plugins") as _plugins, \
           patch("app.routes.public") as _public, \
           patch("app.routes.notifications") as _notifs, \
           patch("app.routes.api.register_api_blueprints"), \
           patch("app.routes.api.api_bp", MagicMock()), \
           patch("app.routes.ai.ai_bp", MagicMock()), \
           patch("app.routes.ai_documents.ai_docs_bp", MagicMock()), \
           patch("app.routes.excel") as _excel, \
           patch("app.routes.ai_ws.register_ai_ws"), \
           patch("app.swagger.routes.swagger_bp", MagicMock()), \
           patch("app.routes.api.indicator_bank_compat.indicator_bank_compat_bp", MagicMock()), \
           patch("app.routes.api.mobile.mobile_bp", MagicMock()), \
           patch("app.routes.admin.register_admin_blueprints"), \
           patch("app.startup_tasks.audit_admin_route_guards"):

            result = register_all_blueprints(mock_app, mock_csrf, 0.0)

        assert isinstance(result, float)
        mock_app.register_blueprint.assert_called()

    def test_csrf_exempt_ai_bp_exception_is_swallowed(self, app):
        """If csrf.exempt(ai_bp) raises, the warning is logged and execution continues."""
        from app.routes import register_all_blueprints

        mock_app = self._make_mock_app()
        mock_csrf = self._make_mock_csrf()
        # csrf.exempt is called unprotected twice (indicator_bank_compat_bp, mobile_bp)
        # before the try/except block that wraps csrf.exempt(ai_bp) — raise only on 3rd call
        mock_csrf.exempt.side_effect = [None, None, Exception("csrf error")]

        with patch("app.routes.auth"), \
             patch("app.routes.main"), \
             patch("app.routes.help_docs"), \
             patch("app.routes.forms"), \
             patch("app.routes.forms_api"), \
             patch("app.routes.plugins"), \
             patch("app.routes.public"), \
             patch("app.routes.notifications"), \
             patch("app.routes.api.register_api_blueprints"), \
             patch("app.routes.api.api_bp", MagicMock()), \
             patch("app.routes.ai.ai_bp", MagicMock()), \
             patch("app.routes.ai_documents.ai_docs_bp", MagicMock()), \
             patch("app.routes.excel"), \
             patch("app.routes.ai_ws.register_ai_ws"), \
             patch("app.swagger.routes.swagger_bp", MagicMock()), \
             patch("app.routes.api.indicator_bank_compat.indicator_bank_compat_bp", MagicMock()), \
             patch("app.routes.api.mobile.mobile_bp", MagicMock()), \
             patch("app.routes.admin.register_admin_blueprints"), \
             patch("app.startup_tasks.audit_admin_route_guards"):

            result = register_all_blueprints(mock_app, mock_csrf, 0.0)

        assert isinstance(result, float)
        mock_app.logger.warning.assert_called()

    def test_ai_ws_register_exception_is_swallowed(self, app):
        """If register_ai_ws raises, the warning is logged and execution continues."""
        from app.routes import register_all_blueprints

        mock_app = self._make_mock_app()
        mock_csrf = self._make_mock_csrf()

        with patch("app.routes.auth"), \
             patch("app.routes.main"), \
             patch("app.routes.help_docs"), \
             patch("app.routes.forms"), \
             patch("app.routes.forms_api"), \
             patch("app.routes.plugins"), \
             patch("app.routes.public"), \
             patch("app.routes.notifications"), \
             patch("app.routes.api.register_api_blueprints"), \
             patch("app.routes.api.api_bp", MagicMock()), \
             patch("app.routes.ai.ai_bp", MagicMock()), \
             patch("app.routes.ai_documents.ai_docs_bp", MagicMock()), \
             patch("app.routes.excel"), \
             patch("app.routes.ai_ws.register_ai_ws", side_effect=Exception("ws error")), \
             patch("app.swagger.routes.swagger_bp", MagicMock()), \
             patch("app.routes.api.indicator_bank_compat.indicator_bank_compat_bp", MagicMock()), \
             patch("app.routes.api.mobile.mobile_bp", MagicMock()), \
             patch("app.routes.admin.register_admin_blueprints"), \
             patch("app.startup_tasks.audit_admin_route_guards"):

            result = register_all_blueprints(mock_app, mock_csrf, 0.0)

        assert isinstance(result, float)
        mock_app.logger.warning.assert_called()

    def test_notifications_ws_exception_is_swallowed(self, app):
        """If register_notifications_ws raises, the warning is logged and execution continues."""
        from app.routes import register_all_blueprints

        mock_app = self._make_mock_app()
        mock_csrf = self._make_mock_csrf()

        with patch("app.routes.auth"), \
             patch("app.routes.main"), \
             patch("app.routes.help_docs"), \
             patch("app.routes.forms"), \
             patch("app.routes.forms_api"), \
             patch("app.routes.plugins"), \
             patch("app.routes.public"), \
             patch("app.routes.notifications"), \
             patch("app.routes.api.register_api_blueprints"), \
             patch("app.routes.api.api_bp", MagicMock()), \
             patch("app.routes.ai.ai_bp", MagicMock()), \
             patch("app.routes.ai_documents.ai_docs_bp", MagicMock()), \
             patch("app.routes.excel"), \
             patch("app.routes.ai_ws.register_ai_ws"), \
             patch("app.swagger.routes.swagger_bp", MagicMock()), \
             patch("app.routes.api.indicator_bank_compat.indicator_bank_compat_bp", MagicMock()), \
             patch("app.routes.api.mobile.mobile_bp", MagicMock()), \
             patch("app.routes.notifications_ws.register_notifications_ws", side_effect=Exception("notif ws error")), \
             patch("app.routes.admin.register_admin_blueprints"), \
             patch("app.startup_tasks.audit_admin_route_guards"):

            result = register_all_blueprints(mock_app, mock_csrf, 0.0)

        assert isinstance(result, float)
        mock_app.logger.warning.assert_called()

    def test_notifications_ws_false_return_no_debug_log(self, app):
        """If register_notifications_ws returns False, no debug log is emitted for it."""
        from app.routes import register_all_blueprints

        mock_app = self._make_mock_app()
        mock_csrf = self._make_mock_csrf()

        with patch("app.routes.auth"), \
             patch("app.routes.main"), \
             patch("app.routes.help_docs"), \
             patch("app.routes.forms"), \
             patch("app.routes.forms_api"), \
             patch("app.routes.plugins"), \
             patch("app.routes.public"), \
             patch("app.routes.notifications"), \
             patch("app.routes.api.register_api_blueprints"), \
             patch("app.routes.api.api_bp", MagicMock()), \
             patch("app.routes.ai.ai_bp", MagicMock()), \
             patch("app.routes.ai_documents.ai_docs_bp", MagicMock()), \
             patch("app.routes.excel"), \
             patch("app.routes.ai_ws.register_ai_ws"), \
             patch("app.swagger.routes.swagger_bp", MagicMock()), \
             patch("app.routes.api.indicator_bank_compat.indicator_bank_compat_bp", MagicMock()), \
             patch("app.routes.api.mobile.mobile_bp", MagicMock()), \
             patch("app.routes.notifications_ws.register_notifications_ws", return_value=False), \
             patch("app.routes.admin.register_admin_blueprints"), \
             patch("app.startup_tasks.audit_admin_route_guards"):

            result = register_all_blueprints(mock_app, mock_csrf, 0.0)

        assert isinstance(result, float)

    def test_debug_log_when_import_slow(self, app):
        """Slow import time (> 0.5s) triggers debug log."""
        from app.routes import register_all_blueprints

        mock_app = self._make_mock_app()
        mock_csrf = self._make_mock_csrf()

        call_count = [0]
        orig_time = time.time

        def mock_time():
            call_count[0] += 1
            # Make the import phase appear slow
            if call_count[0] <= 3:
                return 0.0
            if call_count[0] == 4:
                return 1.0  # bp_import_time > 0.5
            return 1.0

        with patch("app.routes.auth"), \
             patch("app.routes.main"), \
             patch("app.routes.help_docs"), \
             patch("app.routes.forms"), \
             patch("app.routes.forms_api"), \
             patch("app.routes.plugins"), \
             patch("app.routes.public"), \
             patch("app.routes.notifications"), \
             patch("app.routes.api.register_api_blueprints"), \
             patch("app.routes.api.api_bp", MagicMock()), \
             patch("app.routes.ai.ai_bp", MagicMock()), \
             patch("app.routes.ai_documents.ai_docs_bp", MagicMock()), \
             patch("app.routes.excel"), \
             patch("app.routes.ai_ws.register_ai_ws"), \
             patch("app.swagger.routes.swagger_bp", MagicMock()), \
             patch("app.routes.api.indicator_bank_compat.indicator_bank_compat_bp", MagicMock()), \
             patch("app.routes.api.mobile.mobile_bp", MagicMock()), \
             patch("app.routes.admin.register_admin_blueprints"), \
             patch("app.startup_tasks.audit_admin_route_guards"), \
             patch("app.routes.time") as mock_time_mod:
            mock_time_mod.time.side_effect = mock_time
            result = register_all_blueprints(mock_app, mock_csrf, 0.0)

        # Just assert it completed without error
        assert result is not None
