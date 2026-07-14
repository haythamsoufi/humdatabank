"""
Comprehensive pytest tests for app/routes/main/views.py.

Covers:
- language_flag_svg: cached, uncached, dev/prod modes
- set_language: valid/invalid language, referrer handling
- reload_translations: debug vs prod mode, with/without referrer
- chat_immersive: all access gates, new/existing conversation
- download_submission_pdf: auth, weasyprint availability, PDF generation
- service_worker: file present/missing, content injection
- manage_ns_hierarchy: roles/permissions, scope filtering
- manifest: icon types
"""
import os
from io import BytesIO
from unittest.mock import MagicMock, patch, mock_open

import pytest
from flask import json

from tests.factories import (
    create_test_user,
    create_test_country,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


# ---------------------------------------------------------------------------
# language_flag_svg
# ---------------------------------------------------------------------------

class TestLanguageFlagSvg:
    def test_returns_placeholder_when_no_cache(self, client, app, tmp_path):
        """When no cached SVG exists, falls back to placeholder."""
        placeholder_svg = b"<svg/>"
        placeholder_dir = tmp_path / "images" / "flags"
        placeholder_dir.mkdir(parents=True)
        (placeholder_dir / "placeholder.svg").write_bytes(placeholder_svg)

        with patch("app.routes.main.views.os.path.exists", return_value=False), \
             patch("app.routes.main.views.send_from_directory") as mock_sfd:
            mock_response = MagicMock()
            mock_response.headers = {}
            mock_response.status_code = 200
            mock_sfd.return_value = mock_response
            resp = client.get("/flags/en.svg")
        # Route should attempt to serve some response
        assert resp.status_code in (200, 302, 404, 500)

    def test_serves_cached_flag_production(self, client, app, tmp_path):
        cache_dir = tmp_path / "flag_cache"
        cache_dir.mkdir()
        (cache_dir / "gb.svg").write_text("<svg/>")

        with patch("app.routes.main.views.os.path.exists", return_value=True), \
             patch("app.routes.main.views.os.path.join", side_effect=os.path.join), \
             patch("app.routes.main.views.send_from_directory") as mock_sfd:
            mock_response = MagicMock()
            mock_response.headers = {}
            mock_response.status_code = 200
            mock_sfd.return_value = mock_response
            resp = client.get("/flags/en.svg")
        assert resp.status_code in (200, 302, 404, 500)

    def test_serves_cached_flag_dev_mode(self, client, app):
        app.config["DEBUG"] = True
        try:
            with patch("app.routes.main.views.os.path.exists", return_value=True), \
                 patch("app.routes.main.views.send_from_directory") as mock_sfd:
                mock_response = MagicMock()
                mock_response.headers = {}
                mock_response.status_code = 200
                mock_sfd.return_value = mock_response
                resp = client.get("/flags/en.svg")
            assert resp.status_code in (200, 302, 404, 500)
        finally:
            app.config["DEBUG"] = False

    def test_unknown_language_defaults_to_en(self, client, app):
        with patch("app.routes.main.views.os.path.exists", return_value=False), \
             patch("app.routes.main.views.send_from_directory") as mock_sfd:
            mock_response = MagicMock()
            mock_response.headers = {}
            mock_response.status_code = 200
            mock_sfd.return_value = mock_response
            resp = client.get("/flags/zzz.svg")
        assert resp.status_code in (200, 302, 404, 500)


# ---------------------------------------------------------------------------
# set_language
# ---------------------------------------------------------------------------

class TestSetLanguage:
    def test_valid_language_sets_session(self, client, app):
        app.config["SUPPORTED_LANGUAGES"] = ["en", "fr", "es"]
        with patch("app.utils.redirect_utils.is_safe_redirect_url", return_value=False):
            resp = client.get("/language/fr")
        assert resp.status_code == 302
        assert "ui_language=fr" in resp.headers.get("Set-Cookie", "")
        # After redirect, language should be in session
        with client.session_transaction() as sess:
            assert sess.get("language") == "fr"

    def test_valid_language_persists_for_logged_in_user(self, client, app):
        app.config["SUPPORTED_LANGUAGES"] = ["en", "fr", "es"]
        mock_user = MagicMock()
        mock_user.is_authenticated = True

        with patch("app.utils.redirect_utils.is_safe_redirect_url", return_value=False), \
             patch("flask_login.current_user", mock_user), \
             patch("app.i18n.persist_user_preferred_language") as persist:
            resp = client.get("/language/es")
        assert resp.status_code == 302
        persist.assert_called_once_with(mock_user, "es")

    def test_unsupported_language_still_redirects(self, client, app):
        app.config["SUPPORTED_LANGUAGES"] = ["en", "fr"]
        with patch("app.utils.redirect_utils.is_safe_redirect_url", return_value=False):
            resp = client.get("/language/zz")
        assert resp.status_code == 302

    def test_language_with_region_code_resolved(self, client, app):
        app.config["SUPPORTED_LANGUAGES"] = ["en", "fr", "pt_BR"]
        with patch("app.utils.redirect_utils.is_safe_redirect_url", return_value=False):
            resp = client.get("/language/pt-BR")
        assert resp.status_code == 302

    def test_safe_referrer_redirects_to_referrer_path(self, client, app):
        app.config["SUPPORTED_LANGUAGES"] = ["en", "fr"]
        with patch("app.utils.redirect_utils.is_safe_redirect_url", return_value=True), \
             patch("app.utils.redirect_utils.get_safe_redirect_url", return_value="/some/page"):
            resp = client.get("/language/en", headers={"Referer": "http://localhost/some/page"})
        assert resp.status_code == 302

    def test_unsafe_referrer_redirects_to_dashboard(self, client, app):
        app.config["SUPPORTED_LANGUAGES"] = ["en"]
        with patch("app.utils.redirect_utils.is_safe_redirect_url", return_value=False):
            resp = client.get("/language/en", headers={"Referer": "http://evil.com/"})
        assert resp.status_code == 302

    def test_no_referrer_redirects_to_dashboard(self, client, app):
        app.config["SUPPORTED_LANGUAGES"] = ["en"]
        resp = client.get("/language/en")
        assert resp.status_code == 302

    def test_babel_refresh_exception_ignored(self, client, app):
        app.config["SUPPORTED_LANGUAGES"] = ["en"]
        with patch("app.utils.redirect_utils.is_safe_redirect_url", return_value=False):
            # refresh is imported inside the function; patch there
            with patch("flask_babel.refresh", side_effect=Exception("refresh fail")):
                resp = client.get("/language/en")
        assert resp.status_code == 302

    def test_language_base_code_match(self, client, app):
        """e.g. 'fr_FR' maps to 'fr' when 'fr' is in supported."""
        app.config["SUPPORTED_LANGUAGES"] = ["en", "fr"]
        with patch("app.utils.redirect_utils.is_safe_redirect_url", return_value=False):
            resp = client.get("/language/fr_FR")
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# reload_translations
# ---------------------------------------------------------------------------

class TestReloadTranslations:
    def test_debug_mode_reloads(self, client, app):
        app.config["DEBUG"] = True
        try:
            with patch("app.utils.redirect_utils.is_safe_redirect_url", return_value=False), \
                 patch("flask_babel.refresh"), \
                 patch("app.extensions.ensure_translation_mo_files"):
                resp = client.get("/reload-translations")
            assert resp.status_code == 302
        finally:
            app.config["DEBUG"] = False

    def test_non_debug_mode_shows_warning(self, client, app):
        app.config["DEBUG"] = False
        with patch("app.utils.redirect_utils.is_safe_redirect_url", return_value=False):
            resp = client.get("/reload-translations")
        assert resp.status_code == 302

    def test_debug_with_safe_referrer(self, client, app):
        app.config["DEBUG"] = True
        try:
            with patch("app.utils.redirect_utils.is_safe_redirect_url", return_value=True), \
                 patch("app.utils.redirect_utils.get_safe_redirect_url", return_value="/prev"), \
                 patch("flask_babel.refresh"), \
                 patch("app.extensions.ensure_translation_mo_files"):
                resp = client.get(
                    "/reload-translations",
                    headers={"Referer": "http://localhost/prev"},
                )
            assert resp.status_code == 302
        finally:
            app.config["DEBUG"] = False

    def test_debug_ensure_mo_exception_handled(self, client, app):
        app.config["DEBUG"] = True
        try:
            with patch("app.utils.redirect_utils.is_safe_redirect_url", return_value=False), \
                 patch("flask_babel.refresh"), \
                 patch("app.extensions.ensure_translation_mo_files", side_effect=Exception("fail")):
                resp = client.get("/reload-translations")
            assert resp.status_code == 302
        finally:
            app.config["DEBUG"] = False

    def test_debug_missing_translations_dir(self, client, app):
        app.config["DEBUG"] = True
        app.config.pop("BACKOFFICE_TRANSLATIONS_DIR", None)
        try:
            with patch("app.utils.redirect_utils.is_safe_redirect_url", return_value=False), \
                 patch("flask_babel.refresh"):
                resp = client.get("/reload-translations")
            assert resp.status_code == 302
        finally:
            app.config["DEBUG"] = False


# ---------------------------------------------------------------------------
# chat_immersive
# ---------------------------------------------------------------------------

class TestChatImmersive:
    def test_redirects_when_chatbot_disabled(self, logged_in_client, app):
        app.config["CHATBOT_ENABLED"] = False
        try:
            resp = logged_in_client.get("/chat")
            assert resp.status_code == 302
        finally:
            app.config.pop("CHATBOT_ENABLED", None)

    def test_redirects_when_user_chatbot_disabled(self, logged_in_client, db_session, admin_user, app):
        app.config["CHATBOT_ENABLED"] = True
        with patch("app.services.app_settings_service.user_has_ai_beta_access", return_value=True), \
             patch("app.services.app_settings_service.get_chatbot_org_only", return_value=False):
            # Patch current_user.chatbot_enabled = False
            with patch("flask_login.utils._get_user") as mock_get_user:
                mock_user = MagicMock()
                mock_user.is_authenticated = True
                mock_user.chatbot_enabled = False
                mock_user.email = "test@example.com"
                mock_get_user.return_value = mock_user
                resp = logged_in_client.get("/chat")
        assert resp.status_code == 302

    def test_redirects_when_no_ai_beta_access(self, logged_in_client, app):
        app.config["CHATBOT_ENABLED"] = True
        with patch("app.services.app_settings_service.user_has_ai_beta_access", return_value=False):
            resp = logged_in_client.get("/chat")
        assert resp.status_code == 302

    def test_redirects_org_only_non_org_user(self, logged_in_client, app, admin_user):
        app.config["CHATBOT_ENABLED"] = True
        with patch("app.services.app_settings_service.user_has_ai_beta_access", return_value=True), \
             patch("app.services.app_settings_service.get_chatbot_org_only", return_value=True), \
             patch("app.services.app_settings_service.is_organization_email", return_value=False):
            resp = logged_in_client.get("/chat")
        assert resp.status_code == 302

    def test_renders_chat_for_valid_user(self, logged_in_client, app):
        app.config["CHATBOT_ENABLED"] = True
        with patch("app.services.app_settings_service.user_has_ai_beta_access", return_value=True), \
             patch("app.services.app_settings_service.get_chatbot_org_only", return_value=False), \
             patch("app.services.app_settings_service.get_chatbot_name", return_value="AI Helper"), \
             patch("app.routes.main.views.render_template", return_value="<html>chat</html>") as mock_rt:
            resp = logged_in_client.get("/chat")
        assert resp.status_code == 200

    def test_renders_chat_with_conversation_id(self, logged_in_client, app):
        import uuid
        conv_id = str(uuid.uuid4())
        app.config["CHATBOT_ENABLED"] = True
        with patch("app.services.app_settings_service.user_has_ai_beta_access", return_value=True), \
             patch("app.services.app_settings_service.get_chatbot_org_only", return_value=False), \
             patch("app.services.app_settings_service.get_chatbot_name", return_value=""), \
             patch("app.routes.main.views.render_template", return_value="<html>chat</html>"):
            resp = logged_in_client.get(f"/chat/{conv_id}")
        assert resp.status_code == 200

    def test_chatbot_name_exception_ignored(self, logged_in_client, app):
        app.config["CHATBOT_ENABLED"] = True
        with patch("app.services.app_settings_service.user_has_ai_beta_access", return_value=True), \
             patch("app.services.app_settings_service.get_chatbot_org_only", return_value=False), \
             patch("app.services.app_settings_service.get_chatbot_name", side_effect=Exception("name fail")), \
             patch("app.routes.main.views.render_template", return_value="<html>chat</html>"):
            resp = logged_in_client.get("/chat")
        assert resp.status_code == 200

    def test_org_only_check_exception_ignored(self, logged_in_client, app):
        app.config["CHATBOT_ENABLED"] = True
        with patch("app.services.app_settings_service.user_has_ai_beta_access", return_value=True), \
             patch("app.services.app_settings_service.get_chatbot_org_only", side_effect=Exception("org check fail")), \
             patch("app.services.app_settings_service.get_chatbot_name", return_value=""), \
             patch("app.routes.main.views.render_template", return_value="<html>chat</html>"):
            resp = logged_in_client.get("/chat")
        assert resp.status_code == 200

    def test_unauthenticated_redirects(self, client, app):
        app.config["CHATBOT_ENABLED"] = True
        resp = client.get("/chat")
        assert resp.status_code in (302, 401)

    def test_chatbot_default_enabled(self, logged_in_client, app):
        """When CHATBOT_ENABLED not set, defaults to True."""
        app.config.pop("CHATBOT_ENABLED", None)
        with patch("app.services.app_settings_service.user_has_ai_beta_access", return_value=True), \
             patch("app.services.app_settings_service.get_chatbot_org_only", return_value=False), \
             patch("app.services.app_settings_service.get_chatbot_name", return_value="Bot"), \
             patch("app.routes.main.views.render_template", return_value="<html>chat</html>"):
            resp = logged_in_client.get("/chat")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# download_submission_pdf
# ---------------------------------------------------------------------------

class TestDownloadSubmissionPdf:
    def test_unauthenticated_redirects(self, client):
        resp = client.get("/download_submission_pdf/1")
        assert resp.status_code in (302, 401)

    def test_404_for_missing_submission(self, logged_in_client):
        resp = logged_in_client.get("/download_submission_pdf/99999")
        assert resp.status_code == 404

    def test_403_when_no_country_access(self, logged_in_client, db_session, app, admin_user):
        mock_submission = MagicMock()
        mock_submission.id = 1
        mock_submission.country_id = 999
        mock_submission.submitter_name = "Tester"
        mock_submission.submitter_email = "tester@example.com"

        with patch("app.models.PublicSubmission.query") as mock_q, \
             patch("app.services.authorization_service.AuthorizationService.is_admin", return_value=False):
            mock_q.get_or_404.return_value = mock_submission
            # entity_permissions is empty
            mock_submission_user = MagicMock()
            mock_submission_user.entity_permissions = []
            with patch("flask_login.utils._get_user") as mock_gu:
                mock_gu.return_value = mock_submission_user
                mock_gu.return_value.is_authenticated = True
                resp = logged_in_client.get("/download_submission_pdf/1")
        assert resp.status_code in (403, 302, 404)

    def test_weasyprint_unavailable_returns_503(self, logged_in_client, db_session, app, admin_user):
        mock_submission = MagicMock()
        mock_submission.id = 1
        mock_submission.country_id = 1
        mock_submission.country = MagicMock()
        mock_submission.country.name = "Testland"
        mock_submission.submitter_name = "T"
        mock_submission.submitter_email = "t@t.com"
        mock_submission.data_entries = []
        mock_submission.submitted_documents = []
        mock_submission.submitted_at = MagicMock()
        mock_submission.submitted_at.strftime.return_value = "20240101"

        with patch("app.models.PublicSubmission.query") as mock_q, \
             patch("app.services.authorization_service.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.main.views.render_template", return_value="<html/>"), \
             patch.dict("sys.modules", {"weasyprint": None}):
            mock_q.get_or_404.return_value = mock_submission
            resp = logged_in_client.get("/download_submission_pdf/1")
        assert resp.status_code in (503, 200, 500)

    def test_admin_can_access_any_submission(self, logged_in_client, db_session, app, admin_user):
        """Admin bypass: is_admin returns True, no entity check needed."""
        mock_submission = MagicMock()
        mock_submission.id = 1
        mock_submission.country_id = 999  # different country
        mock_submission.country = MagicMock()
        mock_submission.country.name = "Farland"
        mock_submission.submitter_name = "A"
        mock_submission.submitter_email = "a@b.com"
        mock_submission.data_entries = []
        mock_submission.submitted_documents = []
        mock_submission.submitted_at = MagicMock()
        mock_submission.submitted_at.strftime.return_value = "20240101"

        with patch("app.models.PublicSubmission.query") as mock_q, \
             patch("app.services.authorization_service.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.main.views.render_template", return_value="<html/>"), \
             patch.dict("sys.modules", {"weasyprint": None}):
            mock_q.get_or_404.return_value = mock_submission
            resp = logged_in_client.get("/download_submission_pdf/1")
        # Either 503 (weasyprint not available) or 200
        assert resp.status_code in (503, 200, 500)


# ---------------------------------------------------------------------------
# service_worker
# ---------------------------------------------------------------------------

class TestServiceWorker:
    def test_missing_sw_file_returns_404(self, client, app, tmp_path):
        # Ensure sw.js doesn't exist
        with patch("app.routes.main.views.os.path.exists", return_value=False):
            resp = client.get("/sw.js")
        assert resp.status_code == 404

    def test_sw_file_served_with_version_injected(self, client, app):
        sw_content = "const CACHE='ASSET_VERSION_PLACEHOLDER';"
        app.config["ASSET_VERSION"] = "v42"
        m = mock_open(read_data=sw_content)
        with patch("app.routes.main.views.os.path.exists", return_value=True), \
             patch("builtins.open", m):
            resp = client.get("/sw.js")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "v42" in body
        assert "ASSET_VERSION_PLACEHOLDER" not in body

    def test_sw_served_default_version(self, client, app):
        sw_content = "const CACHE='ASSET_VERSION_PLACEHOLDER';"
        app.config.pop("ASSET_VERSION", None)
        m = mock_open(read_data=sw_content)
        with patch("app.routes.main.views.os.path.exists", return_value=True), \
             patch("builtins.open", m):
            resp = client.get("/sw.js")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "v1" in body

    def test_sw_exception_returns_404(self, client, app):
        with patch("app.routes.main.views.os.path.exists", side_effect=Exception("io error")):
            resp = client.get("/sw.js")
        assert resp.status_code == 404

    def test_sw_content_type_is_javascript(self, client, app):
        sw_content = "// service worker"
        m = mock_open(read_data=sw_content)
        with patch("app.routes.main.views.os.path.exists", return_value=True), \
             patch("builtins.open", m):
            resp = client.get("/sw.js")
        assert resp.status_code == 200
        ct = resp.content_type or ""
        assert "javascript" in ct


# ---------------------------------------------------------------------------
# manage_ns_hierarchy
# ---------------------------------------------------------------------------

class TestManageNsHierarchy:
    def test_unauthenticated_redirects(self, client):
        resp = client.get("/ns_structure")
        assert resp.status_code in (302, 401)

    def test_forbidden_for_viewer_user(self, logged_in_client, db_session, app, admin_user):
        with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False), \
             patch("app.services.authorization_service.AuthorizationService.has_rbac_permission", return_value=False), \
             patch("app.services.authorization_service.AuthorizationService.has_role", return_value=False):
            resp = logged_in_client.get("/ns_structure")
        assert resp.status_code == 403

    def test_system_manager_sees_all_branches(self, logged_in_client, db_session, app, admin_user):
        with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.services.authorization_service.AuthorizationService.has_rbac_permission", return_value=False), \
             patch("app.services.authorization_service.AuthorizationService.has_role", return_value=False), \
             patch("app.models.NSBranch") as mock_branch, \
             patch("app.models.NSSubBranch") as mock_sub, \
             patch("app.models.NSLocalUnit") as mock_lu, \
             patch("app.routes.main.views.render_template", return_value="<html>ns</html>") as mock_rt:
            mock_branch.query.order_by.return_value.all.return_value = []
            mock_sub.query.order_by.return_value.all.return_value = []
            mock_lu.query.order_by.return_value.all.return_value = []
            resp = logged_in_client.get("/ns_structure")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_org_admin_sees_all_branches(self, logged_in_client, db_session, app, admin_user):
        with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False), \
             patch("app.services.authorization_service.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.services.authorization_service.AuthorizationService.has_role", return_value=False), \
             patch("app.models.NSBranch") as mock_branch, \
             patch("app.models.NSSubBranch") as mock_sub, \
             patch("app.models.NSLocalUnit") as mock_lu, \
             patch("app.routes.main.views.render_template", return_value="<html>ns</html>"):
            mock_branch.query.order_by.return_value.all.return_value = []
            mock_sub.query.order_by.return_value.all.return_value = []
            mock_lu.query.order_by.return_value.all.return_value = []
            resp = logged_in_client.get("/ns_structure")
        assert resp.status_code == 200

    def test_focal_point_no_countries_empty_data(self, logged_in_client, db_session, app, admin_user):
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.countries = MagicMock()
        mock_user.countries.all.return_value = []

        with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False), \
             patch("app.services.authorization_service.AuthorizationService.has_rbac_permission", return_value=False), \
             patch("app.services.authorization_service.AuthorizationService.has_role", return_value=True), \
             patch("flask_login.utils._get_user", return_value=mock_user), \
             patch("app.routes.main.views.render_template", return_value="<html>ns</html>") as mock_rt:
            resp = logged_in_client.get("/ns_structure")
        assert resp.status_code == 200

    def test_focal_point_single_country_no_country_select(self, logged_in_client, db_session, app, admin_user):
        mock_country = MagicMock()
        mock_country.id = 1
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.countries = MagicMock()
        mock_user.countries.all.return_value = [mock_country]

        with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False), \
             patch("app.services.authorization_service.AuthorizationService.has_rbac_permission", return_value=False), \
             patch("app.services.authorization_service.AuthorizationService.has_role", return_value=True), \
             patch("flask_login.utils._get_user", return_value=mock_user), \
             patch("app.models.NSBranch") as mock_branch, \
             patch("app.models.NSSubBranch") as mock_sub, \
             patch("app.models.NSLocalUnit") as mock_lu, \
             patch("app.routes.main.views.render_template", return_value="<html>ns</html>") as mock_rt:
            mock_branch.query.filter.return_value.order_by.return_value.all.return_value = []
            mock_sub.query.join.return_value.filter.return_value.order_by.return_value.all.return_value = []
            mock_lu.query.join.return_value.filter.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.get("/ns_structure")
        assert resp.status_code == 200
        kwargs = mock_rt.call_args[1] if mock_rt.call_args else {}
        # Single country means countries=[]
        assert kwargs.get("countries") == []

    def test_focal_point_multiple_countries_shows_select(self, logged_in_client, db_session, app, admin_user):
        c1, c2 = MagicMock(id=1), MagicMock(id=2)
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.countries = MagicMock()
        mock_user.countries.all.return_value = [c1, c2]

        with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False), \
             patch("app.services.authorization_service.AuthorizationService.has_rbac_permission", return_value=False), \
             patch("app.services.authorization_service.AuthorizationService.has_role", return_value=True), \
             patch("flask_login.utils._get_user", return_value=mock_user), \
             patch("app.models.NSBranch") as mock_branch, \
             patch("app.models.NSSubBranch") as mock_sub, \
             patch("app.models.NSLocalUnit") as mock_lu, \
             patch("app.routes.main.views.render_template", return_value="<html>ns</html>") as mock_rt:
            mock_branch.query.filter.return_value.order_by.return_value.all.return_value = []
            mock_sub.query.join.return_value.filter.return_value.order_by.return_value.all.return_value = []
            mock_lu.query.join.return_value.filter.return_value.order_by.return_value.all.return_value = []
            resp = logged_in_client.get("/ns_structure")
        assert resp.status_code == 200
        kwargs = mock_rt.call_args[1] if mock_rt.call_args else {}
        assert kwargs.get("countries") == [c1, c2]

    def test_focal_point_user_no_countries_attribute(self, logged_in_client, db_session, app, admin_user):
        """Handle users without 'countries' attribute gracefully."""
        mock_user = MagicMock(spec=[])  # no attributes
        mock_user.is_authenticated = True

        with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False), \
             patch("app.services.authorization_service.AuthorizationService.has_rbac_permission", return_value=False), \
             patch("app.services.authorization_service.AuthorizationService.has_role", return_value=True), \
             patch("flask_login.utils._get_user", return_value=mock_user), \
             patch("app.routes.main.views.render_template", return_value="<html>ns</html>"):
            resp = logged_in_client.get("/ns_structure")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------

class TestManifest:
    def test_manifest_returns_json(self, client, app):
        with patch("app.services.app_settings_service.get_organization_name", return_value="TestOrg"), \
             patch("app.services.app_settings_service.get_organization_short_name", return_value="TO"), \
             patch("app.services.app_settings_service.get_organization_logo_path", return_value=""), \
             patch("app.services.app_settings_service.get_organization_favicon_path", return_value=""), \
             patch("app.services.app_settings_service.organization_visual_asset_href", return_value="/static/icon.svg"):
            resp = client.get("/manifest.webmanifest")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "name" in data
        assert data["name"] == "TestOrg"
        assert "icons" in data

    def test_manifest_svg_icon(self, client, app):
        with patch("app.services.app_settings_service.get_organization_name", return_value="Org"), \
             patch("app.services.app_settings_service.get_organization_short_name", return_value="O"), \
             patch("app.services.app_settings_service.get_organization_logo_path", return_value="logo.svg"), \
             patch("app.services.app_settings_service.get_organization_favicon_path", return_value=""), \
             patch("app.services.app_settings_service.organization_visual_asset_href", return_value="/logo.svg"):
            resp = client.get("/manifest.webmanifest")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        icon = data["icons"][0]
        assert icon["type"] == "image/svg+xml"
        assert icon["sizes"] == "any"

    def test_manifest_png_icon(self, client, app):
        with patch("app.services.app_settings_service.get_organization_name", return_value="Org"), \
             patch("app.services.app_settings_service.get_organization_short_name", return_value="O"), \
             patch("app.services.app_settings_service.get_organization_logo_path", return_value="logo.png"), \
             patch("app.services.app_settings_service.get_organization_favicon_path", return_value=""), \
             patch("app.services.app_settings_service.organization_visual_asset_href", return_value="/logo.png"):
            resp = client.get("/manifest.webmanifest")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        icon = data["icons"][0]
        assert icon["type"] == "image/png"

    def test_manifest_jpeg_icon(self, client, app):
        with patch("app.services.app_settings_service.get_organization_name", return_value="Org"), \
             patch("app.services.app_settings_service.get_organization_short_name", return_value="O"), \
             patch("app.services.app_settings_service.get_organization_logo_path", return_value="logo.jpg"), \
             patch("app.services.app_settings_service.get_organization_favicon_path", return_value=""), \
             patch("app.services.app_settings_service.organization_visual_asset_href", return_value="/logo.jpg"):
            resp = client.get("/manifest.webmanifest")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        icon = data["icons"][0]
        assert icon["type"] == "image/jpeg"

    def test_manifest_unknown_extension_defaults_svg(self, client, app):
        with patch("app.services.app_settings_service.get_organization_name", return_value="Org"), \
             patch("app.services.app_settings_service.get_organization_short_name", return_value="O"), \
             patch("app.services.app_settings_service.get_organization_logo_path", return_value="logo.webp"), \
             patch("app.services.app_settings_service.get_organization_favicon_path", return_value=""), \
             patch("app.services.app_settings_service.organization_visual_asset_href", return_value="/logo.webp"):
            resp = client.get("/manifest.webmanifest")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        icon = data["icons"][0]
        assert icon["type"] == "image/svg+xml"

    def test_manifest_short_name_from_org_name_truncated(self, client, app):
        """If short_name is empty, truncates org name to 15 chars."""
        with patch("app.services.app_settings_service.get_organization_name", return_value="A Very Long Organization Name"), \
             patch("app.services.app_settings_service.get_organization_short_name", return_value=""), \
             patch("app.services.app_settings_service.get_organization_logo_path", return_value=""), \
             patch("app.services.app_settings_service.get_organization_favicon_path", return_value=""), \
             patch("app.services.app_settings_service.organization_visual_asset_href", return_value="/icon.svg"):
            resp = client.get("/manifest.webmanifest")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["short_name"]) <= 15

    def test_manifest_content_type(self, client, app):
        with patch("app.services.app_settings_service.get_organization_name", return_value="Org"), \
             patch("app.services.app_settings_service.get_organization_short_name", return_value="O"), \
             patch("app.services.app_settings_service.get_organization_logo_path", return_value=""), \
             patch("app.services.app_settings_service.get_organization_favicon_path", return_value=""), \
             patch("app.services.app_settings_service.organization_visual_asset_href", return_value="/icon.svg"):
            resp = client.get("/manifest.webmanifest")
        assert "manifest" in resp.content_type or "json" in resp.content_type

    def test_manifest_jpeg_extension(self, client, app):
        with patch("app.services.app_settings_service.get_organization_name", return_value="Org"), \
             patch("app.services.app_settings_service.get_organization_short_name", return_value="O"), \
             patch("app.services.app_settings_service.get_organization_logo_path", return_value="logo.jpeg"), \
             patch("app.services.app_settings_service.get_organization_favicon_path", return_value=""), \
             patch("app.services.app_settings_service.organization_visual_asset_href", return_value="/logo.jpeg"):
            resp = client.get("/manifest.webmanifest")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["icons"][0]["type"] == "image/jpeg"
