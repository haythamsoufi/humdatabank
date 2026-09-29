"""Admin screens for API key permissions: create, edit, list and details."""
import pytest

from app import db
from app.models import APIKey
from app.services.security.api_key_permissions import (
    DATA_READ,
    REFERENCE_READ,
    SUBMISSIONS_READ,
    USERS_READ,
    build_permissions_document,
    parse_key_permissions,
)
from tests.factories import create_test_api_key, create_test_template

pytestmark = [pytest.mark.unit]

CREATE_URL = "/admin/api-management/api-keys/create"


def _form(**overrides):
    data = {"client_name": "UI Client", "rate_limit_per_minute": "60"}
    data.update(overrides)
    return data


def _created(name):
    return APIKey.query.filter_by(client_name=name).first()


class TestCreateScreen:
    def test_page_explains_permissions_in_plain_language(self, logged_in_client):
        html = logged_in_client.get(CREATE_URL).get_data(as_text=True)
        assert "What can this key do?" in html
        assert "Nothing ticked means nothing is allowed" in html
        for label in ("Form data", "Submissions and assignments", "User directory and personal data",
                      "Reference data", "Public content", "Submitted documents"):
            assert label in html
        assert "Personal data" in html and "Sensitive" in html
        assert "Endpoints unlocked" in html
        assert "/api/v1/users" in html and "/api/v1/data" in html
        assert "Public website / embed" in html and "BI / analytics" in html
        assert "Authorization: Bearer" in html
        assert 'src="' in html and "api-key-permissions.js" in html

    def test_empty_permissions_are_rejected(self, logged_in_client, db_session):
        response = logged_in_client.post(CREATE_URL, data=_form(client_name="No Perms"))
        assert response.status_code == 200
        assert "Select at least one permission" in response.get_data(as_text=True)
        assert _created("No Perms") is None

    def test_creates_key_with_explicit_capabilities(self, logged_in_client, db_session):
        response = logged_in_client.post(
            CREATE_URL, data=_form(client_name="Ref Only", capabilities=[REFERENCE_READ])
        )
        assert response.status_code == 200
        assert "What this key can do" in response.get_data(as_text=True)
        key = _created("Ref Only")
        assert key.permissions == build_permissions_document([REFERENCE_READ])
        assert not parse_key_permissions(key.permissions).allow_query_api_key

    def test_sensitive_access_needs_confirmation(self, logged_in_client, db_session):
        response = logged_in_client.post(
            CREATE_URL, data=_form(client_name="Needs Confirm", capabilities=[DATA_READ])
        )
        assert "Please confirm access to sensitive data" in response.get_data(as_text=True)
        assert _created("Needs Confirm") is None

        logged_in_client.post(
            CREATE_URL,
            data=_form(client_name="Confirmed", capabilities=[DATA_READ], confirm_sensitive="y"),
        )
        assert _created("Confirmed") is not None

    def test_scope_is_stored_and_validated(self, logged_in_client, db_session, app):
        template = create_test_template(db_session)
        bad = logged_in_client.post(
            CREATE_URL,
            data=_form(client_name="Empty Scope", capabilities=[DATA_READ], confirm_sensitive="y",
                       restrict_data="y"),
        )
        assert "Choose at least one template or country" in bad.get_data(as_text=True)
        assert _created("Empty Scope") is None

        pointless = logged_in_client.post(
            CREATE_URL,
            data=_form(client_name="Pointless Scope", capabilities=[REFERENCE_READ],
                       restrict_data="y", scope_template_ids=[str(template.id)]),
        )
        assert "only applies to" in pointless.get_data(as_text=True)

        logged_in_client.post(
            CREATE_URL,
            data=_form(client_name="Scoped", capabilities=[DATA_READ, SUBMISSIONS_READ],
                       confirm_sensitive="y", restrict_data="y", scope_template_ids=[str(template.id)]),
        )
        stored = _created("Scoped").permissions
        assert stored["data_scope"] == {"template_ids": [template.id], "country_ids": []}

    def test_query_string_key_not_allowed_with_personal_data(self, logged_in_client, db_session):
        response = logged_in_client.post(
            CREATE_URL,
            data=_form(client_name="URL PII", capabilities=[USERS_READ], confirm_sensitive="y",
                       allow_query_api_key="y"),
        )
        assert "must be sent in a header" in response.get_data(as_text=True)
        assert _created("URL PII") is None

    def test_query_string_key_can_be_enabled_for_non_personal_data(self, logged_in_client, db_session):
        logged_in_client.post(
            CREATE_URL,
            data=_form(client_name="URL Ref", capabilities=[REFERENCE_READ], allow_query_api_key="y"),
        )
        assert _created("URL Ref").permissions["allow_query_api_key"] is True

    def test_unknown_capability_is_rejected(self, logged_in_client, db_session):
        response = logged_in_client.post(
            CREATE_URL, data=_form(client_name="Bogus", capabilities=["root:everything"])
        )
        assert response.status_code == 200
        assert _created("Bogus") is None


class TestEditScreen:
    def _legacy_key(self, db_session, name="Legacy Client"):
        document = build_permissions_document(
            parse_key_permissions({"data": "read_all"}).capabilities,
            allow_query_api_key=True,
            legacy={"full_access": True, "original": None},
        )
        key, _ = create_test_api_key(db_session, client_name=name, permissions=document)
        return key

    def test_legacy_key_shows_banner_and_full_access(self, logged_in_client, db_session):
        key = self._legacy_key(db_session)
        html = logged_in_client.get(f"/admin/api-management/api-keys/{key.id}/edit").get_data(as_text=True)
        assert "Legacy full access" in html
        assert "keepLegacyFullAccess" in html

    def test_keeping_legacy_access_requires_confirmation_and_changes_nothing(self, logged_in_client, db_session):
        key = self._legacy_key(db_session, "Keep Legacy")
        before = dict(key.permissions)
        url = f"/admin/api-management/api-keys/{key.id}/edit"
        base = {"client_name": "Keep Legacy", "rate_limit_per_minute": "60", "keep_legacy_full_access": "y"}

        refused = logged_in_client.post(url, data=base)
        assert refused.status_code == 200
        assert "Confirm that you accept keeping full access" in refused.get_data(as_text=True)

        accepted = logged_in_client.post(url, data={**base, "confirm_sensitive": "y"})
        assert accepted.status_code == 302
        db.session.refresh(key)
        assert key.permissions == before

    def test_narrowing_a_legacy_key_replaces_the_document(self, logged_in_client, db_session):
        key = self._legacy_key(db_session, "Narrow Me")
        response = logged_in_client.post(
            f"/admin/api-management/api-keys/{key.id}/edit",
            data={"client_name": "Narrow Me", "rate_limit_per_minute": "60", "capabilities": [REFERENCE_READ]},
        )
        assert response.status_code == 302
        db.session.refresh(key)
        assert key.permissions == build_permissions_document([REFERENCE_READ])
        assert not parse_key_permissions(key.permissions).legacy_full_access

    def test_edit_form_is_prefilled_from_the_stored_document(self, logged_in_client, db_session):
        key, _ = create_test_api_key(
            db_session, client_name="Prefilled",
            permissions=build_permissions_document([REFERENCE_READ, USERS_READ]),
        )
        html = logged_in_client.get(f"/admin/api-management/api-keys/{key.id}/edit").get_data(as_text=True)
        assert 'value="users:read"' in html
        checked = [line for line in html.splitlines() if 'value="users:read"' in line or 'checked' in line]
        assert any("checked" in line for line in html.splitlines())
        assert checked

    def test_edit_audit_records_permission_change(self, logged_in_client, db_session):
        from unittest.mock import patch

        key, _ = create_test_api_key(
            db_session, client_name="Audited", permissions=build_permissions_document([REFERENCE_READ])
        )
        with patch("app.routes.admin.api_key_management.log_admin_action") as audit:
            logged_in_client.post(
                f"/admin/api-management/api-keys/{key.id}/edit",
                data={"client_name": "Audited", "rate_limit_per_minute": "60",
                      "capabilities": [REFERENCE_READ, USERS_READ], "confirm_sensitive": "y"},
            )
        kwargs = audit.call_args.kwargs
        assert kwargs["old_values"]["permissions"]["capabilities"] == [REFERENCE_READ]
        assert USERS_READ in kwargs["new_values"]["permissions"]["capabilities"]
        assert kwargs["risk_level"] == "high"


class TestListAndDetails:
    def test_list_shows_effective_access_for_each_key(self, logged_in_client, db_session):
        create_test_api_key(db_session, client_name="Row Legacy", permissions=build_permissions_document(
            [REFERENCE_READ], legacy={"full_access": True, "original": None}))
        create_test_api_key(db_session, client_name="Row Empty", permissions=None)
        create_test_api_key(db_session, client_name="Row Scoped", permissions=build_permissions_document(
            [DATA_READ], restrict_data=True, template_ids=[1]))
        html = logged_in_client.get("/admin/api-management/api-keys").get_data(as_text=True)
        assert "Legacy: full access" in html
        assert "No access" in html
        assert "Limited scope" in html

    def test_details_lists_permissions_and_recommendations(self, logged_in_client, db_session):
        legacy, _ = create_test_api_key(db_session, client_name="Detail Legacy", permissions=build_permissions_document(
            [REFERENCE_READ, USERS_READ], allow_query_api_key=True,
            legacy={"full_access": True, "original": None}))
        html = logged_in_client.get(f"/admin/api-management/api-keys/{legacy.id}").get_data(as_text=True)
        assert "Legacy: full access" in html
        assert "User directory and personal data" in html
        assert "Recommended: narrow this key" in html
        assert "Recommended: set an expiry date" in html
        assert "sent in the URL" in html

    def test_details_of_key_without_permissions_explains_the_refusal(self, logged_in_client, db_session):
        key, _ = create_test_api_key(db_session, client_name="Detail Empty", permissions=None)
        html = logged_in_client.get(f"/admin/api-management/api-keys/{key.id}").get_data(as_text=True)
        assert "every request with it is refused" in html
