"""Object-level authorization for child-id form / assignment APIs.

Covers the shared helpers in ``app.utils.form_authorization`` and the routes that use them:
repeat instances, dynamic indicators, lookup-list reads, public submissions, and the
mobile template / access-request / suggestion endpoints.
"""

import uuid

import pytest

from app import db
from app.models import (
    AssignmentEntityStatus,
    FormTemplate,
    CountryAccessRequest,
    DynamicIndicatorData,
    FormSection,
    IndicatorBank,
    IndicatorSuggestion,
    LookupList,
    LookupListRow,
    RepeatGroupInstance,
)
from app.models.rbac import RbacRole, RbacRolePermission, RbacUserRole
from tests.factories import (
    _ensure_permission,
    _grant_entity_permission,
    create_test_assignment_entity_status,
    create_test_country,
    create_test_item,
    create_test_public_submission,
    create_test_section,
    create_test_template,
    create_test_user,
)
from tests.helpers import login_session

_FOCAL_PERMS = ("assignment.view", "assignment.edit", "assignment.submit", "assignment.enter")


def _custom_role_user(db_session, perms, *, name=None):
    """User whose only role is a fresh role holding exactly ``perms``."""
    user = create_test_user(db_session, role="user")
    for link in list(RbacUserRole.query.filter_by(user_id=user.id)):
        db_session.delete(link)
    role = RbacRole(code=f"r_{uuid.uuid4().hex[:10]}", name=name or "Custom")
    db_session.add(role)
    db_session.flush()
    for code in perms:
        pid = _ensure_permission(db_session, code)
        db_session.add(RbacRolePermission(role_id=role.id, permission_id=pid))
    db_session.add(RbacUserRole(user_id=user.id, role_id=role.id))
    db_session.commit()
    return user


def _focal(db_session, aes, *, perms=_FOCAL_PERMS):
    user = _custom_role_user(db_session, perms)
    _grant_entity_permission(db_session, user, aes.entity_type, aes.entity_id)
    db_session.commit()
    return user


@pytest.fixture
def scenario(db_session, app):
    """Two countries on two templates, each with an assignment; child objects on country A."""
    with app.app_context():
        country_a = create_test_country(db_session)
        country_b = create_test_country(db_session)
        template_a = create_test_template(db_session)
        template_b = create_test_template(db_session)
        aes_a = create_test_assignment_entity_status(db_session, country=country_a, template=template_a)
        aes_b = create_test_assignment_entity_status(db_session, country=country_b, template=template_b)

        repeat_section = create_test_section(
            db_session, template_a, section_type="repeat", name="Repeat"
        )
        dynamic_section = create_test_section(
            db_session, template_a, section_type="dynamic_indicators", name="Dynamic"
        )
        foreign_dynamic_section = create_test_section(
            db_session, template_b, section_type="dynamic_indicators", name="Foreign dynamic"
        )
        indicator = IndicatorBank(name=f"Ind {uuid.uuid4().hex[:6]}", type="number", archived=False, emergency=False)
        spare_indicator = IndicatorBank(
            name=f"Spare {uuid.uuid4().hex[:6]}", type="number", archived=False, emergency=False
        )
        db_session.add_all([indicator, spare_indicator])
        db_session.flush()

        focal_a = _focal(db_session, aes_a)
        focal_b = _focal(db_session, aes_b)
        outsider_admin = create_test_user(db_session, role="admin")
        system_manager = create_test_user(db_session, role="system_manager")

        instance = RepeatGroupInstance(
            section_id=repeat_section.id,
            assignment_entity_status_id=aes_a.id,
            instance_number=1,
            created_by_user_id=focal_a.id,
        )
        dynamic = DynamicIndicatorData(
            assignment_entity_status_id=aes_a.id,
            section_id=dynamic_section.id,
            indicator_bank_id=indicator.id,
            added_by_user_id=focal_a.id,
            custom_label="Original",
        )
        db_session.add_all([instance, dynamic])
        db_session.commit()

        yield {
            "aes_a": aes_a.id,
            "aes_b": aes_b.id,
            "template_a": template_a.id,
            "dynamic_section": dynamic_section.id,
            "foreign_dynamic_section": foreign_dynamic_section.id,
            "indicator": indicator.id,
            "spare_indicator": spare_indicator.id,
            "instance": instance.id,
            "dynamic": dynamic.id,
            "focal_a": focal_a.id,
            "focal_b": focal_b.id,
            "outsider_admin": outsider_admin.id,
            "system_manager": system_manager.id,
            "country_a": country_a.id,
            "country_b": country_b.id,
        }


def _bearer(user_id):
    from app.utils.mobile_jwt import issue_access_token

    return {"Authorization": f"Bearer {issue_access_token(user_id)}"}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.utils import rate_limiting

    rate_limiting._rate_limit_storage.clear()
    yield
    rate_limiting._rate_limit_storage.clear()


def _set_aes_status(db_session, aes_id, status):
    aes = db_session.get(AssignmentEntityStatus, aes_id)
    aes.status = status
    db_session.commit()


@pytest.mark.integration
class TestRepeatInstanceToggleHide:
    def _toggle(self, client, scenario):
        return client.patch(f"/api/forms/repeat-instances/{scenario['instance']}/toggle-hide")

    def test_owner_country_focal_point_can_toggle(self, client, scenario):
        login_session(client, scenario["focal_a"])
        resp = self._toggle(client, scenario)
        assert resp.status_code == 200
        assert resp.get_json()["is_hidden"] is True

    def test_focal_point_of_other_country_gets_404_and_no_change(self, client, db_session, scenario):
        login_session(client, scenario["focal_b"])
        resp = self._toggle(client, scenario)
        assert resp.status_code == 404
        assert db_session.get(RepeatGroupInstance, scenario["instance"]).is_hidden is False

    def test_admin_without_assignment_scope_gets_404(self, client, scenario):
        login_session(client, scenario["outsider_admin"])
        assert self._toggle(client, scenario).status_code == 404

    def test_unknown_instance_is_indistinguishable_from_forbidden(self, client, scenario):
        login_session(client, scenario["focal_b"])
        resp = client.patch("/api/forms/repeat-instances/999999999/toggle-hide")
        assert resp.status_code == 404

    def test_anonymous_is_not_served(self, client, scenario):
        resp = self._toggle(client, scenario)
        assert resp.status_code in (302, 401)

    def test_submitted_assignment_is_read_only_for_focal_point(self, client, db_session, scenario):
        _set_aes_status(db_session, scenario["aes_a"], "submitted")
        login_session(client, scenario["focal_a"])
        assert self._toggle(client, scenario).status_code == 403

    def test_view_only_user_of_owning_country_gets_403(self, client, db_session, scenario):
        aes = db_session.get(AssignmentEntityStatus, scenario["aes_a"])
        viewer = _focal(db_session, aes, perms=("assignment.view",))
        login_session(client, viewer.id)
        assert self._toggle(client, scenario).status_code == 403

    def test_system_manager_can_toggle(self, client, scenario):
        login_session(client, scenario["system_manager"])
        assert self._toggle(client, scenario).status_code == 200


@pytest.mark.integration
class TestDynamicIndicatorObjectAuthorization:
    def _url(self, scenario, suffix):
        return f"/api/forms/dynamic-indicators/{scenario['dynamic']}/{suffix}"

    def test_update_by_owner_succeeds(self, client, db_session, scenario):
        login_session(client, scenario["focal_a"])
        resp = client.put(self._url(scenario, "update"), json={"custom_label": "New"})
        assert resp.status_code == 200
        assert db_session.get(DynamicIndicatorData, scenario["dynamic"]).custom_label == "New"

    def test_update_by_other_country_is_404_and_unchanged(self, client, db_session, scenario):
        login_session(client, scenario["focal_b"])
        resp = client.put(self._url(scenario, "update"), json={"custom_label": "Hijacked"})
        assert resp.status_code == 404
        assert db_session.get(DynamicIndicatorData, scenario["dynamic"]).custom_label == "Original"

    def test_remove_by_other_country_is_404_and_kept(self, client, db_session, scenario):
        login_session(client, scenario["focal_b"])
        assert client.delete(self._url(scenario, "remove")).status_code == 404
        assert db_session.get(DynamicIndicatorData, scenario["dynamic"]) is not None

    def test_remove_by_admin_without_scope_is_404(self, client, db_session, scenario):
        login_session(client, scenario["outsider_admin"])
        assert client.delete(self._url(scenario, "remove")).status_code == 404
        assert db_session.get(DynamicIndicatorData, scenario["dynamic"]) is not None

    def test_render_by_other_country_is_404(self, client, scenario):
        login_session(client, scenario["focal_b"])
        assert client.get(self._url(scenario, "render")).status_code == 404

    def test_remove_on_submitted_assignment_is_403(self, client, db_session, scenario):
        _set_aes_status(db_session, scenario["aes_a"], "submitted")
        login_session(client, scenario["focal_a"])
        assert client.delete(self._url(scenario, "remove")).status_code == 403
        assert db_session.get(DynamicIndicatorData, scenario["dynamic"]) is not None

    def test_remove_by_owner_succeeds(self, client, db_session, scenario):
        login_session(client, scenario["focal_a"])
        assert client.delete(self._url(scenario, "remove")).status_code == 200
        assert db_session.get(DynamicIndicatorData, scenario["dynamic"]) is None

    def _add_payload(self, scenario, **overrides):
        payload = {
            "assignment_entity_status_id": scenario["aes_a"],
            "section_id": scenario["dynamic_section"],
            "indicator_bank_id": scenario["spare_indicator"],
        }
        payload.update(overrides)
        return payload

    def test_add_to_foreign_assignment_is_forbidden(self, client, db_session, scenario):
        login_session(client, scenario["focal_b"])
        before = DynamicIndicatorData.query.count()
        resp = client.post("/api/forms/dynamic-indicators/add", json=self._add_payload(scenario))
        assert resp.status_code == 403
        assert DynamicIndicatorData.query.count() == before

    def test_add_with_section_of_another_template_is_rejected(self, client, scenario):
        login_session(client, scenario["focal_a"])
        resp = client.post(
            "/api/forms/dynamic-indicators/add",
            json=self._add_payload(scenario, section_id=scenario["foreign_dynamic_section"]),
        )
        assert resp.status_code == 400

    def test_add_by_owner_succeeds(self, client, scenario):
        login_session(client, scenario["focal_a"])
        resp = client.post("/api/forms/dynamic-indicators/add", json=self._add_payload(scenario))
        assert resp.status_code == 200

    def test_render_pending_for_foreign_assignment_is_forbidden(self, client, scenario):
        login_session(client, scenario["focal_b"])
        resp = client.post(
            "/api/forms/dynamic-indicators/render-pending",
            json=self._add_payload(scenario, temp_assignment_id="t1"),
        )
        assert resp.status_code == 403


@pytest.mark.integration
class TestLookupListReadAccess:
    @pytest.fixture
    def lists(self, db_session, app, scenario):
        with app.app_context():
            referenced = LookupList(name=f"Ref {uuid.uuid4().hex[:6]}", columns_config=[{"name": "name", "type": "string"}])
            unreferenced = LookupList(name=f"Unref {uuid.uuid4().hex[:6]}", columns_config=[{"name": "name", "type": "string"}])
            db_session.add_all([referenced, unreferenced])
            db_session.flush()
            for lst in (referenced, unreferenced):
                for i in range(3):
                    db_session.add(LookupListRow(lookup_list_id=lst.id, order=i, data={"name": f"row{i}"}))
            tpl = db_session.get(FormTemplate, scenario["template_a"])
            section = FormSection.query.filter_by(template_id=tpl.id).first()
            create_test_item(
                db_session,
                section,
                tpl,
                item_type="question",
                type="single_choice",
                lookup_list_id=str(referenced.id),
            )
            db_session.commit()
            yield {"referenced": referenced.id, "unreferenced": unreferenced.id}

    def _options(self, client, list_id):
        return client.get(f"/api/forms/lookup-lists/{list_id}/options")

    def test_assigned_user_reads_list_used_by_their_template(self, client, scenario, lists):
        login_session(client, scenario["focal_a"])
        resp = self._options(client, lists["referenced"])
        assert resp.status_code == 200
        assert len(resp.get_json()["rows"]) == 3

    def test_user_of_other_template_cannot_read_list(self, client, scenario, lists):
        login_session(client, scenario["focal_b"])
        assert self._options(client, lists["referenced"]).status_code == 404

    def test_list_not_used_by_any_reachable_template_is_hidden(self, client, scenario, lists):
        login_session(client, scenario["focal_a"])
        assert self._options(client, lists["unreferenced"]).status_code == 404

    def test_admin_without_template_permission_cannot_read(self, client, scenario, lists):
        login_session(client, scenario["outsider_admin"])
        assert self._options(client, lists["referenced"]).status_code == 404

    def test_template_editor_can_read_any_list(self, client, db_session, scenario, lists):
        editor = _custom_role_user(db_session, ("admin.templates.edit",))
        login_session(client, editor.id)
        assert self._options(client, lists["unreferenced"]).status_code == 200

    def test_system_manager_can_read_any_list(self, client, scenario, lists):
        login_session(client, scenario["system_manager"])
        assert self._options(client, lists["unreferenced"]).status_code == 200

    def test_response_is_capped_and_flags_truncation(self, client, monkeypatch, scenario, lists):
        monkeypatch.setattr("app.routes.forms_api.MAX_LOOKUP_OPTIONS_ROWS", 2)
        login_session(client, scenario["focal_a"])
        data = self._options(client, lists["referenced"]).get_json()
        assert len(data["rows"]) == 2
        assert data["truncated"] is True

    def test_search_rows_requires_same_access(self, client, scenario, lists):
        body = {"lookup_list_id": lists["referenced"], "display_column": "name"}
        login_session(client, scenario["focal_b"])
        assert client.post("/forms/matrix/search-rows", json=body).status_code == 404
        login_session(client, scenario["focal_a"])
        resp = client.post("/forms/matrix/search-rows", json=body)
        assert resp.status_code == 200
        assert len(resp.get_json()["options"]) == 3

    def test_search_rows_hides_unreferenced_list(self, client, scenario, lists):
        body = {"lookup_list_id": lists["unreferenced"], "display_column": "name"}
        login_session(client, scenario["focal_a"])
        assert client.post("/forms/matrix/search-rows", json=body).status_code == 404


@pytest.mark.integration
class TestPublicSubmissionAuthorization:
    @pytest.fixture
    def submission(self, db_session, app, scenario):
        with app.app_context():
            sub, _, _ = create_test_public_submission(db_session, country=create_test_country(db_session))
            yield sub.id, sub.country_id

    def _admin_user(self, db_session, perms, country_id=None):
        user = _custom_role_user(db_session, perms)
        if country_id:
            _grant_entity_permission(db_session, user, "country", country_id)
            db_session.commit()
        return user

    def test_admin_without_manage_permission_cannot_delete(self, client, db_session, submission):
        sub_id, country_id = submission
        user = self._admin_user(db_session, ("admin.assignments.view",), country_id)
        login_session(client, user.id)
        resp = client.post(f"/forms/public-submission/{sub_id}/delete")
        assert resp.status_code == 403
        from app.models import PublicSubmission

        assert db_session.get(PublicSubmission, sub_id) is not None

    def test_admin_without_country_scope_gets_404(self, client, db_session, submission):
        sub_id, _ = submission
        user = self._admin_user(db_session, ("admin.assignments.view",))
        login_session(client, user.id)
        assert client.post(f"/forms/public-submission/{sub_id}/approve").status_code == 404
        assert client.get(f"/forms/public-submission/{sub_id}/view").status_code == 404

    def test_manage_permission_holder_can_approve(self, client, db_session, submission):
        sub_id, _ = submission
        user = self._admin_user(db_session, ("admin.assignments.public_submissions.manage",))
        login_session(client, user.id)
        resp = client.post(f"/forms/public-submission/{sub_id}/approve")
        assert resp.status_code in (302, 303)
        from app.models import PublicSubmission

        db_session.expire_all()
        assert str(db_session.get(PublicSubmission, sub_id).status.value) == "approved"

    def test_edit_query_flag_does_not_grant_write_access(self, client, db_session, submission):
        sub_id, country_id = submission
        user = self._admin_user(db_session, ("admin.assignments.view",), country_id)
        login_session(client, user.id)
        resp = client.post(
            f"/forms/public-submission/{sub_id}/view?edit=true",
            data={"submitter_name": "Changed"},
        )
        assert resp.status_code in (403, 404, 405)
        from app.models import PublicSubmission

        db_session.expire_all()
        assert db_session.get(PublicSubmission, sub_id).submitter_name != "Changed"

    def test_status_endpoint_is_json_forbidden_without_manage(self, client, db_session, submission):
        sub_id, country_id = submission
        user = self._admin_user(db_session, ("admin.assignments.view",), country_id)
        login_session(client, user.id)
        resp = client.post(f"/forms/public-submission/{sub_id}/status", data={"status": "approved"})
        assert resp.status_code == 403
        assert resp.get_json()["success"] is False


@pytest.mark.unit
class TestAuthorizationHelpers:
    def test_check_aes_action_tri_state(self, db_session, app, scenario):
        from app.utils.form_authorization import (
            AES_ACTION_EDIT,
            AES_ACTION_VIEW,
            AUTH_FORBIDDEN,
            AUTH_HIDDEN,
            AUTH_OK,
            check_aes_action,
        )

        with app.app_context():
            aes = db_session.get(AssignmentEntityStatus, scenario["aes_a"])
            from app.models import User

            owner = db_session.get(User, scenario["focal_a"])
            outsider = db_session.get(User, scenario["focal_b"])
            viewer = _focal(db_session, aes, perms=("assignment.view",))

            assert check_aes_action(aes, owner, AES_ACTION_EDIT) == AUTH_OK
            assert check_aes_action(aes, outsider, AES_ACTION_VIEW) == AUTH_HIDDEN
            assert check_aes_action(aes, viewer, AES_ACTION_VIEW) == AUTH_OK
            assert check_aes_action(aes, viewer, AES_ACTION_EDIT) == AUTH_FORBIDDEN

    def test_orphan_child_is_only_reachable_by_system_manager(self, db_session, app, scenario):
        from app.models import User
        from app.utils.form_authorization import AES_ACTION_VIEW, AUTH_HIDDEN, AUTH_OK, authorize_child

        with app.app_context():
            orphan = RepeatGroupInstance(
                section_id=db_session.get(DynamicIndicatorData, scenario["dynamic"]).section_id,
                assignment_entity_status_id=None,
                public_submission_id=None,
                instance_number=9,
            )
            assert authorize_child(orphan, db_session.get(User, scenario["focal_a"]), AES_ACTION_VIEW) == AUTH_HIDDEN
            assert authorize_child(orphan, db_session.get(User, scenario["system_manager"]), AES_ACTION_VIEW) == AUTH_OK

    def test_lock_aes_for_update_reports_concurrent_status_change(self, db_session, app, scenario):
        from app.utils.form_authorization import lock_aes_for_update

        with app.app_context():
            aes = db_session.get(AssignmentEntityStatus, scenario["aes_a"])
            assert lock_aes_for_update(aes) is False
            db_session.execute(
                db.text("UPDATE assignment_entity_status SET status = 'submitted' WHERE id = :i"),
                {"i": aes.id},
            )
            assert lock_aes_for_update(aes) is True
            assert str(getattr(aes.status, "value", aes.status)) == "submitted"

    def test_user_can_access_template(self, db_session, app, scenario):
        from app.models import User
        from app.utils.form_authorization import user_can_access_template

        with app.app_context():
            owner = db_session.get(User, scenario["focal_a"])
            outsider = db_session.get(User, scenario["focal_b"])
            sm = db_session.get(User, scenario["system_manager"])
            assert user_can_access_template(owner, scenario["template_a"]) is True
            assert user_can_access_template(outsider, scenario["template_a"]) is False
            assert user_can_access_template(sm, scenario["template_a"]) is True


@pytest.mark.integration
class TestMobileObjectAuthorization:
    def test_template_structure_is_scoped_to_reachable_templates(self, client, scenario):
        url = f"/api/mobile/v1/templates/{scenario['template_a']}/structure"
        headers = _bearer(scenario["focal_b"])
        assert client.get(url, headers=headers).status_code == 404
        headers = _bearer(scenario["focal_a"])
        assert client.get(url, headers=headers).status_code == 200

    def test_resolve_fields_and_stable_key_follow_template_scope(self, client, scenario):
        base = f"/api/mobile/v1/templates/{scenario['template_a']}"
        headers = _bearer(scenario["focal_b"])
        assert client.post(f"{base}/resolve-fields", json={"fields": []}, headers=headers).status_code == 404
        assert client.get(f"{base}/items/by-stable-key/anything", headers=headers).status_code == 404

    @pytest.fixture
    def access_request(self, db_session, app, scenario):
        with app.app_context():
            requester = create_test_user(db_session, role="user")
            req = CountryAccessRequest(user_id=requester.id, country_id=scenario["country_b"], status="pending")
            db_session.add(req)
            db_session.commit()
            yield req.id, requester.id

    def test_approve_requires_exact_permission_not_users_edit(self, client, db_session, scenario, access_request):
        req_id, _ = access_request
        user = _custom_role_user(db_session, ("admin.users.edit", "admin.access_requests.view"))
        headers = _bearer(user.id)
        resp = client.post(f"/api/mobile/v1/admin/access-requests/{req_id}/approve", headers=headers)
        assert resp.status_code == 403
        assert db_session.get(CountryAccessRequest, req_id).status == "pending"

    def test_reject_requires_reject_permission(self, client, db_session, scenario, access_request):
        req_id, _ = access_request
        user = _custom_role_user(db_session, ("admin.access_requests.approve",))
        headers = _bearer(user.id)
        assert client.post(f"/api/mobile/v1/admin/access-requests/{req_id}/reject", headers=headers).status_code == 403

    def test_approve_with_permission_grants_access_and_is_audited(self, client, db_session, scenario, access_request):
        from app.models import AdminActionLog

        req_id, requester_id = access_request
        user = _custom_role_user(db_session, ("admin.access_requests.approve",))
        headers = _bearer(user.id)
        resp = client.post(f"/api/mobile/v1/admin/access-requests/{req_id}/approve", headers=headers)
        assert resp.status_code == 200
        db_session.expire_all()
        assert db_session.get(CountryAccessRequest, req_id).status == "approved"
        from app.models.core import UserEntityPermission

        assert UserEntityPermission.query.filter_by(
            user_id=requester_id, entity_type="country", entity_id=scenario["country_b"]
        ).count() == 1
        audited = AdminActionLog.query.filter_by(admin_user_id=user.id, action_type="access_request_approve").count()
        assert audited == 1

    def test_approve_all_requires_approve_permission(self, client, db_session, scenario, access_request):
        user = _custom_role_user(db_session, ("admin.users.edit",))
        headers = _bearer(user.id)
        assert client.post("/api/mobile/v1/admin/access-requests/approve-all", headers=headers).status_code == 403


@pytest.mark.integration
class TestMobileIndicatorSuggestion:
    URL = "/api/mobile/v1/data/indicator-suggestions"

    @staticmethod
    def _payload(**overrides):
        payload = {
            "submitter_name": "Jane Doe",
            "submitter_email": f"jane{uuid.uuid4().hex[:6]}@example.org",
            "suggestion_type": "new_indicator",
            "indicator_name": "People reached",
            "reason": "Needed for reporting",
        }
        payload.update(overrides)
        return payload

    @pytest.fixture(autouse=True)
    def _clean_suggestions(self, db_session, app):
        with app.app_context():
            IndicatorSuggestion.query.delete()
            db_session.commit()
        yield
        with app.app_context():
            IndicatorSuggestion.query.delete()
            db_session.commit()

    @pytest.fixture(autouse=True)
    def _no_email(self, monkeypatch):
        monkeypatch.setattr("app.services.email.service.send_suggestion_confirmation_email", lambda s: True)
        monkeypatch.setattr("app.services.email.service.send_admin_notification_email", lambda s: True)

    def test_valid_submission_is_created(self, client):
        resp = client.post(self.URL, json=self._payload())
        assert resp.status_code == 201
        assert IndicatorSuggestion.query.count() == 1

    @pytest.mark.parametrize(
        "overrides",
        [
            {"suggestion_type": "drop table"},
            {"submitter_email": "not-an-email"},
            {"indicator_name": "x" * 300},
            {"reason": "y" * 6000},
            {"type": "z" * 60},
            {"indicator_id": "abc"},
            {"indicator_id": 987654321},
            {"emergency": "maybe"},
            {"sector": ["a"]},
            {"sector": {"primary": "  "}},
            {"sub_sector": {"bogus": "x", "primary": "p"}},
            {"submitter_name": 123},
        ],
    )
    def test_invalid_payloads_are_rejected_without_writing(self, client, overrides):
        before = IndicatorSuggestion.query.count()
        resp = client.post(self.URL, json=self._payload(**overrides))
        assert resp.status_code == 400
        assert IndicatorSuggestion.query.count() == before

    def test_non_object_body_is_rejected(self, client):
        assert client.post(self.URL, data="[]", content_type="application/json").status_code == 400

    def test_per_email_daily_cap(self, client, app, monkeypatch):
        monkeypatch.setitem(app.config, "SUGGESTION_PER_EMAIL_DAILY_LIMIT", 2)
        email = "repeat@example.org"
        for _ in range(2):
            assert client.post(self.URL, json=self._payload(submitter_email=email)).status_code == 201
        resp = client.post(self.URL, json=self._payload(submitter_email=email.upper()))
        assert resp.status_code == 429
        assert IndicatorSuggestion.query.count() == 2

    def test_global_hourly_cap(self, client, app, monkeypatch):
        monkeypatch.setitem(app.config, "SUGGESTION_GLOBAL_HOURLY_LIMIT", 1)
        assert client.post(self.URL, json=self._payload()).status_code == 201
        assert client.post(self.URL, json=self._payload()).status_code == 429

    def test_captcha_required_when_enabled(self, client, app, monkeypatch):
        monkeypatch.setitem(app.config, "MOBILE_SUGGESTION_REQUIRE_CAPTCHA", True)
        monkeypatch.setattr("app.routes.api.indicator_bank_compat._verify_recaptcha", lambda token: token == "good")
        assert client.post(self.URL, json=self._payload()).status_code == 400
        assert client.post(self.URL, json=self._payload(token="bad")).status_code == 400
        assert client.post(self.URL, json=self._payload(token="good")).status_code == 201
        assert IndicatorSuggestion.query.count() == 1
