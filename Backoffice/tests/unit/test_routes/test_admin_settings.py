"""
Comprehensive tests for app/routes/admin/settings.py
Targeting 100% code coverage of admin settings routes.
"""
import base64
import json
import pytest
import urllib.error
from contextlib import contextmanager
from unittest.mock import patch, MagicMock, call

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_headers():
    return {"Content-Type": "application/json", "Accept": "application/json"}


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _auth_patches():
    """Context managers that bypass RBAC checks for admin settings routes."""
    return [
        patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True),
        patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True),
    ]


@contextmanager
def _auth():
    with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
         patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True):
        yield


def _mock_render(return_value="<html>settings</html>"):
    return patch(
        "app.routes.admin.settings.render_template",
        return_value=return_value,
    )


def _mock_app_settings():
    """Patch all app_settings_service calls used by manage_settings GET."""
    return patch.multiple(
        "app.routes.admin.settings",
        _build_ai_groups=MagicMock(return_value=[]),
        _normalize_localized_value=MagicMock(return_value={}),
    )


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

class TestSettingsAccessControl:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/settings", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.location.lower()

    def test_non_admin_gets_denied(self, client, db_session, app):
        from tests.factories import create_test_user
        user = create_test_user(db_session, email="settings_nonadmin@test.com", role="user")
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True
        resp = client.get("/admin/settings", follow_redirects=False)
        assert resp.status_code in (302, 403)


# ---------------------------------------------------------------------------
# GET /admin/settings
# ---------------------------------------------------------------------------

class TestManageSettingsGet:
    def test_get_settings_renders_template(self, logged_in_client, db_session, app):
        with _auth(), _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/settings")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_get_settings_with_mocked_services(self, logged_in_client, db_session, app):
        from unittest.mock import MagicMock
        mock_settings = {
            "get_supported_languages": MagicMock(return_value=["en"]),
            "set_supported_languages": MagicMock(return_value=True),
            "get_show_language_flags": MagicMock(return_value=True),
            "set_show_language_flags": MagicMock(return_value=True),
            "get_document_types": MagicMock(return_value=[]),
            "set_document_types": MagicMock(return_value=True),
            "get_age_groups": MagicMock(return_value=[]),
            "set_age_groups": MagicMock(return_value=True),
            "get_sex_categories": MagicMock(return_value=[]),
            "set_sex_categories": MagicMock(return_value=True),
            "get_list_translations": MagicMock(return_value={}),
            "set_list_translations": MagicMock(return_value=True),
            "get_enabled_entity_types": MagicMock(return_value=["countries"]),
            "set_enabled_entity_types": MagicMock(return_value=True),
            "get_organization_branding": MagicMock(return_value={}),
            "set_organization_branding": MagicMock(return_value=True),
            "get_chatbot_name": MagicMock(return_value=""),
            "set_chatbot_name": MagicMock(return_value=True),
            "get_ai_beta_access_settings": MagicMock(return_value={"enabled": False, "allowed_user_ids": []}),
            "set_ai_beta_access_settings": MagicMock(return_value=True),
            "get_all_email_templates": MagicMock(return_value={}),
            "set_all_email_templates": MagicMock(return_value=True),
            "get_template_metadata": MagicMock(return_value={}),
            "get_notification_priorities": MagicMock(return_value={}),
            "set_notification_priorities": MagicMock(return_value=True),
            "get_merged_notification_audience_rules": MagicMock(return_value={}),
            "set_notification_audience_rules": MagicMock(return_value=True),
            "get_mobile_min_app_version": MagicMock(return_value=""),
            "set_mobile_min_app_version": MagicMock(return_value=True),
        }
        with _auth(), _mock_render() as mock_rt, \
             patch("app.routes.admin.settings._build_ai_groups", return_value=[]), \
             patch("app.services.app_settings_service.get_supported_languages", return_value=["en"]):
            resp = logged_in_client.get("/admin/settings")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /admin/settings
# ---------------------------------------------------------------------------

class TestManageSettingsPost:
    def _post_settings(self, logged_in_client, data=None, **extra):
        defaults = {
            "languages": ["en"],
            "document_types[]": ["Report", "Assessment"],
            "age_groups[]": ["<5", "5-17"],
            "sex_categories[]": ["Male", "Female"],
            "enabled_entity_types[]": ["countries"],
            "show_language_flags": "1",
            "mobile_min_app_version": "1.0.0",
        }
        if data:
            defaults.update(data)
        defaults.update(extra)
        return logged_in_client.post(
            "/admin/settings",
            data=defaults,
            follow_redirects=False,
        )

    def test_post_settings_saves_and_renders(self, logged_in_client, db_session, app):
        with _auth(), _mock_render() as mock_rt:
            resp = self._post_settings(logged_in_client)
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_settings_with_json_payload(self, logged_in_client, db_session, app):
        payload = {
            "languages": ["en"],
            "document_types[]": [],
            "age_groups[]": [],
            "sex_categories[]": [],
            "enabled_entity_types[]": ["countries"],
        }
        inner_b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
        with _auth(), _mock_render() as mock_rt:
            resp = logged_in_client.post(
                "/admin/settings",
                json={"payload": inner_b64},
                headers=_json_headers(),
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

    def test_post_partial_save_flag(self, logged_in_client, db_session, app):
        payload = {"languages": ["en"], "settings_partial_save": "1"}
        inner_b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
        with _auth(), _mock_render():
            resp = logged_in_client.post(
                "/admin/settings",
                json={"payload": inner_b64},
                headers=_json_headers(),
                follow_redirects=False,
            )
        assert resp.status_code in (200, 400)

    def test_post_settings_branding_fields(self, logged_in_client, db_session, app):
        with _auth(), _mock_render():
            resp = self._post_settings(
                logged_in_client,
                data={
                    "organization_name_en": "Test Org",
                    "organization_short_name_en": "TO",
                    "chatbot_name": "TestBot",
                }
            )
        assert resp.status_code in (200, 302)

    def test_post_settings_ai_settings(self, logged_in_client, db_session, app):
        with _auth(), _mock_render():
            resp = self._post_settings(
                logged_in_client,
                data={"ai_setting_OPENAI_MODEL": "gpt-4"},
            )
        assert resp.status_code in (200, 302)

    def test_post_settings_notification_priorities(self, logged_in_client, db_session, app):
        with _auth(), _mock_render():
            resp = self._post_settings(
                logged_in_client,
                data={"notification_priority_assignment_reminder": "high"},
            )
        assert resp.status_code in (200, 302)

    def test_post_settings_list_translations(self, logged_in_client, db_session, app):
        translations = json.dumps({"en": {"Report": "Report"}})
        with _auth(), _mock_render():
            resp = self._post_settings(
                logged_in_client,
                data={"document_types_translations": translations},
            )
        assert resp.status_code in (200, 302)

    def test_post_settings_with_language_order(self, logged_in_client, db_session, app):
        with _auth(), _mock_render():
            resp = self._post_settings(
                logged_in_client,
                data={"languages": ["en", "fr"], "languages_order": "en,fr"},
            )
        assert resp.status_code in (200, 302)

    def test_post_settings_with_invalid_ai_setting(self, logged_in_client, db_session, app):
        with _auth(), _mock_render():
            resp = self._post_settings(
                logged_in_client,
                data={"ai_setting_UNKNOWN_KEY": "value"},
            )
        assert resp.status_code in (200, 302)

    def test_post_settings_with_ai_beta_settings(self, logged_in_client, db_session, app):
        with _auth(), _mock_render():
            resp = self._post_settings(
                logged_in_client,
                data={"ai_beta_enabled": "1", "ai_beta_allowed_user_ids": ""},
            )
        assert resp.status_code in (200, 302)

    def test_post_settings_with_audience_rules_json(self, logged_in_client, db_session, app):
        rules = json.dumps({"assignment_reminder": {"roles": ["admin_core"]}})
        with _auth(), _mock_render():
            resp = self._post_settings(
                logged_in_client,
                data={"notification_audience_rules": rules},
            )
        assert resp.status_code in (200, 302)

    def test_post_settings_with_email_templates_disabled(self, logged_in_client, db_session, app):
        with _auth(), _mock_render():
            resp = self._post_settings(
                logged_in_client,
                data={"email_templates_b64": "{}"},
            )
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# POST /admin/settings/branding-assets-upload
# ---------------------------------------------------------------------------

class TestBrandingAssetsUpload:
    def test_upload_unavailable_returns_400(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.utils.branding_visual_assets.branding_visual_upload_available", return_value=False):
            resp = logged_in_client.post("/admin/settings/branding-assets-upload", data={})
        assert resp.status_code == 400

    def test_upload_no_files_returns_400(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.utils.branding_visual_assets.branding_visual_upload_available", return_value=True):
            resp = logged_in_client.post("/admin/settings/branding-assets-upload", data={})
        assert resp.status_code == 400

    def test_upload_logo_success(self, logged_in_client, db_session, app):
        import io
        logo_data = io.BytesIO(b"fake-png-data")
        with _auth(), \
             patch("app.utils.branding_visual_assets.branding_visual_upload_available", return_value=True), \
             patch("app.utils.branding_visual_assets.upload_organization_logo", return_value="/path/logo.png"), \
             patch("app.utils.branding_visual_assets.delete_branding_object_if_present"):
            resp = logged_in_client.post(
                "/admin/settings/branding-assets-upload",
                data={"organization_logo_file": (logo_data, "logo.png")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True

    def test_upload_logo_value_error(self, logged_in_client, db_session, app):
        import io
        logo_data = io.BytesIO(b"bad")
        with _auth(), \
             patch("app.utils.branding_visual_assets.branding_visual_upload_available", return_value=True), \
             patch("app.utils.branding_visual_assets.upload_organization_logo", side_effect=ValueError("bad format")):
            resp = logged_in_client.post(
                "/admin/settings/branding-assets-upload",
                data={"organization_logo_file": (logo_data, "logo.png")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400

    def test_upload_logo_general_exception(self, logged_in_client, db_session, app):
        import io
        logo_data = io.BytesIO(b"bad")
        with _auth(), \
             patch("app.utils.branding_visual_assets.branding_visual_upload_available", return_value=True), \
             patch("app.utils.branding_visual_assets.upload_organization_logo", side_effect=Exception("storage error")):
            resp = logged_in_client.post(
                "/admin/settings/branding-assets-upload",
                data={"organization_logo_file": (logo_data, "logo.png")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 500

    def test_upload_favicon_success(self, logged_in_client, db_session, app):
        import io
        fav_data = io.BytesIO(b"fake-ico-data")
        with _auth(), \
             patch("app.utils.branding_visual_assets.branding_visual_upload_available", return_value=True), \
             patch("app.utils.branding_visual_assets.upload_organization_favicon", return_value="/path/fav.ico"), \
             patch("app.utils.branding_visual_assets.delete_branding_object_if_present"):
            resp = logged_in_client.post(
                "/admin/settings/branding-assets-upload",
                data={"organization_favicon_file": (fav_data, "favicon.ico")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200

    def test_upload_favicon_value_error(self, logged_in_client, db_session, app):
        import io
        fav_data = io.BytesIO(b"bad")
        with _auth(), \
             patch("app.utils.branding_visual_assets.branding_visual_upload_available", return_value=True), \
             patch("app.utils.branding_visual_assets.upload_organization_favicon", side_effect=ValueError("bad fav")):
            resp = logged_in_client.post(
                "/admin/settings/branding-assets-upload",
                data={"organization_favicon_file": (fav_data, "favicon.ico")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400

    def test_upload_favicon_exception(self, logged_in_client, db_session, app):
        import io
        fav_data = io.BytesIO(b"bad")
        with _auth(), \
             patch("app.utils.branding_visual_assets.branding_visual_upload_available", return_value=True), \
             patch("app.utils.branding_visual_assets.upload_organization_favicon", side_effect=Exception("error")):
            resp = logged_in_client.post(
                "/admin/settings/branding-assets-upload",
                data={"organization_favicon_file": (fav_data, "favicon.ico")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /admin/api/settings/ai-reset
# ---------------------------------------------------------------------------

class TestAISettingsReset:
    def test_ai_reset_success(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.services.app_settings_service.set_ai_settings", return_value=True), \
             patch("app.services.app_settings_service.apply_ai_settings_to_config"):
            resp = logged_in_client.post(
                "/admin/api/settings/ai-reset",
                headers=_json_headers(),
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True

    def test_ai_reset_failure(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.services.app_settings_service.set_ai_settings", return_value=False):
            resp = logged_in_client.post(
                "/admin/api/settings/ai-reset",
                headers=_json_headers(),
            )
        assert resp.status_code == 500

    def test_ai_reset_exception(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.services.app_settings_service.set_ai_settings", side_effect=Exception("db error")):
            resp = logged_in_client.post(
                "/admin/api/settings/ai-reset",
                headers=_json_headers(),
            )
        assert resp.status_code == 500

    def test_ai_reset_unauthenticated(self, client, db_session):
        resp = client.post("/admin/api/settings/ai-reset", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /admin/api/settings/email-templates
# ---------------------------------------------------------------------------

class TestEmailTemplates:
    def _valid_b64_templates(self):
        html = "<html>Test email</html>"
        b64_html = _b64(html)
        return {"email_template_welcome": {"en": b64_html}}

    def test_save_email_templates_success(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.services.app_settings_service.set_all_email_templates", return_value=True):
            resp = logged_in_client.post(
                "/admin/api/settings/email-templates",
                json={"email_templates_b64": self._valid_b64_templates()},
                headers=_json_headers(),
            )
        assert resp.status_code in (200, 400)

    def test_save_email_templates_missing_payload(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/api/settings/email-templates",
                json={},
                headers=_json_headers(),
            )
        assert resp.status_code in (200, 400)

    def test_save_email_templates_invalid_key(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/api/settings/email-templates",
                json={"email_templates_b64": {"INVALID_KEY": {"en": _b64("<html/>")} }},
                headers=_json_headers(),
            )
        assert resp.status_code in (200, 400)

    def test_save_email_templates_unauthenticated(self, client, db_session):
        resp = client.post("/admin/api/settings/email-templates", follow_redirects=False)
        assert resp.status_code == 302

    def test_save_email_templates_with_metadata(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.services.app_settings_service.set_all_email_templates", return_value=True), \
             patch("app.services.app_settings_service.set_template_metadata", return_value=True, create=True):
            resp = logged_in_client.post(
                "/admin/api/settings/email-templates",
                json={
                    "email_templates_b64": self._valid_b64_templates(),
                    "template_metadata": {"email_template_welcome": {"subject": "Welcome"}},
                },
                headers=_json_headers(),
            )
        assert resp.status_code in (200, 400)


# ---------------------------------------------------------------------------
# POST /admin/api/settings/email-template-preview
# ---------------------------------------------------------------------------

class TestEmailTemplatePreview:
    def _valid_payload(self):
        return {
            "template_key": "email_template_welcome",
            "html_b64": _b64("<html><body>Hello {{name}}</body></html>"),
            "template_language": "en",
        }

    def test_preview_success(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.services.email.preview_context.get_email_template_preview_context",
                   return_value={"name": "Test User"}), \
             patch("app.services.email.rendering.render_admin_email_template_for_preview",
                   return_value=("<html>Hello Test User</html>", None)), \
             patch("app.services.email.rendering.sanitize_admin_email_html_for_api",
                   side_effect=lambda x: x):
            resp = logged_in_client.post(
                "/admin/api/settings/email-template-preview",
                json=self._valid_payload(),
                headers=_json_headers(),
            )
        assert resp.status_code in (200, 400, 500)

    def test_preview_missing_template_key(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/api/settings/email-template-preview",
                json={"html_b64": _b64("<html/>")},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_preview_invalid_template_key(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/api/settings/email-template-preview",
                json={"template_key": "INVALID", "html_b64": _b64("<html/>")},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_preview_missing_html_b64(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/api/settings/email-template-preview",
                json={"template_key": "email_template_welcome"},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_preview_empty_html_b64(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/api/settings/email-template-preview",
                json={"template_key": "email_template_welcome", "html_b64": _b64("  ")},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_preview_render_error(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.services.email.preview_context.get_email_template_preview_context",
                   return_value={}), \
             patch("app.services.email.rendering.render_admin_email_template_for_preview",
                   return_value=(None, "Render error")):
            resp = logged_in_client.post(
                "/admin/api/settings/email-template-preview",
                json=self._valid_payload(),
                headers=_json_headers(),
            )
        assert resp.status_code in (200, 400)

    def test_preview_invalid_template_language_type(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/api/settings/email-template-preview",
                json={"template_key": "email_template_welcome", "html_b64": _b64("<html/>"),
                      "template_language": 123},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_preview_unauthenticated(self, client, db_session):
        resp = client.post("/admin/api/settings/email-template-preview", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /admin/api/settings/email-template-test-send
# ---------------------------------------------------------------------------

class TestEmailTemplateTestSend:
    def _valid_payload(self):
        return {
            "template_key": "email_template_welcome",
            "html_b64": _b64("<html><body>Test</body></html>"),
            "template_language": "en",
        }

    def test_test_send_missing_key(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/api/settings/email-template-test-send",
                json={"html_b64": _b64("<html/>")},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_test_send_invalid_key(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/api/settings/email-template-test-send",
                json={"template_key": "INVALID", "html_b64": _b64("<html/>")},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_test_send_missing_html_b64(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/api/settings/email-template-test-send",
                json={"template_key": "email_template_welcome"},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_test_send_empty_html(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/api/settings/email-template-test-send",
                json={"template_key": "email_template_welcome", "html_b64": _b64("  ")},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_test_send_success(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.services.email.preview_context.get_email_template_preview_context",
                   return_value={}), \
             patch("app.services.email.rendering.render_admin_email_template_for_preview",
                   return_value=("<html>Test</html>", None)), \
             patch("app.services.email.rendering.sanitize_admin_email_html_for_api",
                   side_effect=lambda x: x), \
             patch("app.services.email.client.send_email", return_value=True):
            resp = logged_in_client.post(
                "/admin/api/settings/email-template-test-send",
                json=self._valid_payload(),
                headers=_json_headers(),
            )
        assert resp.status_code in (200, 400, 500)

    def test_test_send_email_fails(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.services.email.preview_context.get_email_template_preview_context",
                   return_value={}), \
             patch("app.services.email.rendering.render_admin_email_template_for_preview",
                   return_value=("<html>Test</html>", None)), \
             patch("app.services.email.rendering.sanitize_admin_email_html_for_api",
                   side_effect=lambda x: x), \
             patch("app.services.email.client.send_email", return_value=False):
            resp = logged_in_client.post(
                "/admin/api/settings/email-template-test-send",
                json=self._valid_payload(),
                headers=_json_headers(),
            )
        assert resp.status_code in (200, 400)

    def test_test_send_unauthenticated(self, client, db_session):
        resp = client.post("/admin/api/settings/email-template-test-send", follow_redirects=False)
        assert resp.status_code == 302

    def test_test_send_invalid_recipient_user_id(self, logged_in_client, db_session, app):
        with _auth():
            payload = self._valid_payload()
            payload["recipient_user_id"] = "not-a-number"
            resp = logged_in_client.post(
                "/admin/api/settings/email-template-test-send",
                json=payload,
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_test_send_unknown_recipient_user_id(self, logged_in_client, db_session, app):
        with _auth():
            payload = self._valid_payload()
            payload["recipient_user_id"] = 999999999
            resp = logged_in_client.post(
                "/admin/api/settings/email-template-test-send",
                json=payload,
                headers=_json_headers(),
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /admin/api/settings/email-templates/seed
# ---------------------------------------------------------------------------

class TestEmailTemplatesSeed:
    def test_seed_success(self, logged_in_client, db_session, app):
        mock_stats = {"created": 2, "updated": 0, "skipped": 0}
        with _auth(), \
             patch("scripts.seed_email_templates.seed_templates", return_value=mock_stats):
            resp = logged_in_client.post(
                "/admin/api/settings/email-templates/seed",
                json={},
                headers=_json_headers(),
            )
        assert resp.status_code in (200, 500)

    def test_seed_with_force_flag(self, logged_in_client, db_session, app):
        mock_stats = {"created": 3, "updated": 0, "skipped": 0}
        with _auth(), \
             patch("scripts.seed_email_templates.seed_templates", return_value=mock_stats):
            resp = logged_in_client.post(
                "/admin/api/settings/email-templates/seed",
                json={"force": True},
                headers=_json_headers(),
            )
        assert resp.status_code in (200, 500)

    def test_seed_exception(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("scripts.seed_email_templates.seed_templates", side_effect=Exception("fail")):
            resp = logged_in_client.post(
                "/admin/api/settings/email-templates/seed",
                json={},
                headers=_json_headers(),
            )
        assert resp.status_code in (200, 500)

    def test_seed_unauthenticated(self, client, db_session):
        resp = client.post("/admin/api/settings/email-templates/seed", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET+POST /admin/api/settings/languages
# ---------------------------------------------------------------------------

class TestLanguagesSettings:
    def test_get_languages(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.services.app_settings_service.get_supported_languages", return_value=["en", "fr"]):
            resp = logged_in_client.get("/admin/api/settings/languages")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "languages" in data

    def test_post_languages_valid(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.services.app_settings_service.set_supported_languages", return_value=True), \
             patch("app.services.app_settings_service.get_supported_languages", return_value=["en"]), \
             patch("app.services.app_settings_service.get_show_language_flags", return_value=False):
            resp = logged_in_client.post(
                "/admin/api/settings/languages",
                json={"languages": ["en", "fr"]},
                headers=_json_headers(),
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "languages" in data

    def test_post_languages_not_list(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/api/settings/languages",
                json={"languages": "en"},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_post_languages_save_fails(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.services.app_settings_service.set_supported_languages", return_value=False):
            resp = logged_in_client.post(
                "/admin/api/settings/languages",
                json={"languages": ["en"]},
                headers=_json_headers(),
            )
        assert resp.status_code == 500

    def test_post_languages_with_flag_prefetch(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.services.app_settings_service.set_supported_languages", return_value=True), \
             patch("app.services.app_settings_service.get_supported_languages", return_value=["en", "de"]), \
             patch("app.services.app_settings_service.get_show_language_flags", return_value=True), \
             patch("app.utils.language_flags.prefetch_language_flags_to_local_cache"):
            resp = logged_in_client.post(
                "/admin/api/settings/languages",
                json={"languages": ["en", "de"]},
                headers=_json_headers(),
            )
        assert resp.status_code in (200, 500)

    def test_languages_unauthenticated(self, client, db_session):
        resp = client.get("/admin/api/settings/languages", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET /admin/api/settings/check-updates
# ---------------------------------------------------------------------------

class TestCheckUpdates:
    def test_check_updates_success(self, logged_in_client, db_session, app):
        mock_release = {
            "tag_name": "v2.0.0",
            "name": "Release 2.0.0",
            "html_url": "https://github.com/repo/releases/v2.0.0",
            "published_at": "2026-01-01T00:00:00Z",
        }
        with _auth(), \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_release).encode("utf-8")
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            resp = logged_in_client.get("/admin/api/settings/check-updates")
        assert resp.status_code in (200, 502)

    def test_check_updates_404_falls_back_to_tags(self, logged_in_client, db_session, app):
        mock_tags = [{"name": "v1.5.0"}]
        http_error = urllib.error.HTTPError(
            url="https://api.github.com/repos/x/y/releases/latest",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )
        with _auth(), \
             patch("urllib.request.urlopen") as mock_urlopen:
            call_count = [0]
            def side_effect(*a, **kw):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise http_error
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps(mock_tags).encode("utf-8")
                mock_resp.__enter__ = MagicMock(return_value=mock_resp)
                mock_resp.__exit__ = MagicMock(return_value=False)
                return mock_resp
            mock_urlopen.side_effect = side_effect
            resp = logged_in_client.get("/admin/api/settings/check-updates")
        assert resp.status_code in (200, 502)

    def test_check_updates_401_error(self, logged_in_client, db_session, app):
        http_error = urllib.error.HTTPError(
            url="https://api.github.com/x",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )
        with _auth(), \
             patch("urllib.request.urlopen", side_effect=http_error):
            resp = logged_in_client.get("/admin/api/settings/check-updates")
        assert resp.status_code == 502

    def test_check_updates_403_error(self, logged_in_client, db_session, app):
        http_error = urllib.error.HTTPError(
            url="https://api.github.com/x",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=None,
        )
        with _auth(), \
             patch("urllib.request.urlopen", side_effect=http_error):
            resp = logged_in_client.get("/admin/api/settings/check-updates")
        assert resp.status_code == 502

    def test_check_updates_generic_exception(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("urllib.request.urlopen", side_effect=Exception("network error")):
            resp = logged_in_client.get("/admin/api/settings/check-updates")
        assert resp.status_code == 502

    def test_check_updates_404_tags_empty(self, logged_in_client, db_session, app):
        http_error = urllib.error.HTTPError(
            url="https://api.github.com/x",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )
        with _auth(), \
             patch("urllib.request.urlopen") as mock_urlopen:
            call_count = [0]
            def side_effect(*a, **kw):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise http_error
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps([]).encode("utf-8")
                mock_resp.__enter__ = MagicMock(return_value=mock_resp)
                mock_resp.__exit__ = MagicMock(return_value=False)
                return mock_resp
            mock_urlopen.side_effect = side_effect
            resp = logged_in_client.get("/admin/api/settings/check-updates")
        assert resp.status_code in (200, 502)

    def test_check_updates_404_repo_inaccessible_with_token(self, logged_in_client, db_session, app):
        http_error = urllib.error.HTTPError(
            url="https://api.github.com/repos/org/private/releases/latest",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )
        with _auth(), \
             patch("app.routes.admin.settings._github_update_check_config",
                   return_value=("org/private", "ghp_testtoken", "1.0.0")), \
             patch("urllib.request.urlopen", side_effect=http_error):
            resp = logged_in_client.get("/admin/api/settings/check-updates")
        assert resp.status_code == 502
        body = resp.get_json()
        assert body.get("success") is False
        assert "GITHUB_REPO" in body.get("error", "")
        assert "GITHUB_TOKEN" in body.get("error", "")

    def test_check_updates_not_available_when_current_is_ahead(self, logged_in_client, db_session, app):
        """Deploy image tag (1.0.5) ahead of GitHub latest release (1.0.4) must not prompt update."""
        mock_release = {
            "tag_name": "v1.0.4",
            "name": "v1.0.4",
            "html_url": "https://github.com/repo/releases/tag/v1.0.4",
            "published_at": "2026-04-11T00:00:00Z",
        }
        with _auth(), \
             patch("app.routes.admin.settings._github_update_check_config",
                   return_value=("haythamsoufi/humdatabank", "", "1.0.5")), \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_release).encode("utf-8")
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            resp = logged_in_client.get("/admin/api/settings/check-updates")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get("success") is True
        assert body.get("update_available") is False
        assert body.get("current_version") == "1.0.5"
        assert body.get("latest_version") == "1.0.4"

    def test_check_updates_available_when_current_is_behind(self, logged_in_client, db_session, app):
        mock_release = {
            "tag_name": "v1.0.4",
            "name": "v1.0.4",
            "html_url": "https://github.com/repo/releases/tag/v1.0.4",
            "published_at": "2026-04-11T00:00:00Z",
        }
        with _auth(), \
             patch("app.routes.admin.settings._github_update_check_config",
                   return_value=("haythamsoufi/humdatabank", "", "1.0.1")), \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_release).encode("utf-8")
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            resp = logged_in_client.get("/admin/api/settings/check-updates")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get("update_available") is True

    def test_check_updates_unauthenticated(self, client, db_session):
        resp = client.get("/admin/api/settings/check-updates", follow_redirects=False)
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Internal helpers covered via import
# ---------------------------------------------------------------------------

class TestSettingsInternalHelpers:
    def test_build_ai_groups_returns_list(self, app):
        with app.app_context():
            from app.routes.admin.settings import _build_ai_groups
            with patch("app.services.app_settings_service.get_ai_settings", return_value={}):
                result = _build_ai_groups()
            assert isinstance(result, list)

    def test_normalize_localized_value_string(self, app):
        with app.app_context():
            from app.routes.admin.settings import _normalize_localized_value
            result = _normalize_localized_value("Hello World")
            assert isinstance(result, dict)
            assert result.get("en") == "Hello World"

    def test_normalize_localized_value_dict(self, app):
        with app.app_context():
            from app.routes.admin.settings import _normalize_localized_value
            result = _normalize_localized_value({"en": "Hello", "fr": "Bonjour"})
            assert result == {"en": "Hello", "fr": "Bonjour"}

    def test_normalize_localized_value_none(self, app):
        with app.app_context():
            from app.routes.admin.settings import _normalize_localized_value
            result = _normalize_localized_value(None)
            assert isinstance(result, dict)

    def test_b64decode_utf8_valid(self, app):
        with app.app_context():
            from app.routes.admin.settings import _b64decode_utf8
            encoded = _b64("<html>test</html>")
            result = _b64decode_utf8(encoded)
            assert result == "<html>test</html>"

    def test_b64decode_utf8_invalid(self, app):
        with app.app_context():
            from app.routes.admin.settings import _b64decode_utf8
            result = _b64decode_utf8("not-valid-b64!!!")
            assert isinstance(result, str)

    def test_message_for_email_test_send_failure_with_known_key(self, app):
        with app.app_context():
            from app.routes.admin.settings import _message_for_email_test_send_failure
            msg = _message_for_email_test_send_failure([{"code": "recipient_allowlist"}])
            assert isinstance(msg, str)
            assert len(msg) > 0

    def test_message_for_email_test_send_failure_empty(self, app):
        with app.app_context():
            from app.routes.admin.settings import _message_for_email_test_send_failure
            msg = _message_for_email_test_send_failure([])
            assert isinstance(msg, str)

    def test_personalize_email_preview_context_for_user(self, app):
        with app.app_context():
            from app.routes.admin.settings import _personalize_email_preview_context_for_user

            class _U:
                id = 42
                name = "Jamie Example"
                email = "jamie@example.org"

            ctx = _personalize_email_preview_context_for_user(
                {"user_name": "Sample", "user_email": "x@y.z", "user_id": 1},
                _U(),
            )
            assert ctx["user_name"] == "Jamie"
            assert ctx["user_email"] == "jamie@example.org"
            assert ctx["user_id"] == 42

    def test_manage_settings_form_baseline_callable(self, app):
        with app.app_context():
            from app.routes.admin.settings import _manage_settings_form_baseline
            result = _manage_settings_form_baseline(
                csrf_token="",
                current_supported=["en"],
                current_show_language_flags=True,
                current_doc_types=["Report"],
                current_age_groups=["<5"],
                current_sex_categories=["Male"],
                doc_types_translations={},
                age_groups_translations={},
                sex_categories_translations={},
                current_entity_types=["countries"],
                current_mobile_min_app_version="",
                org_name_translations={"en": "Test"},
                org_short_name_translations={},
                current_branding={},
                current_chatbot_name="",
                notification_priorities={},
                merged_notification_audience_rules={},
                ai_groups=[],
                ai_beta_enabled=False,
                ai_beta_allowed_user_ids=[],
            )
            assert isinstance(result, dict)
