"""RBAC scope / separation-of-duties hardening for admin routes.

Covers: guard-audit regressions, seeded permission catalog, country scope, entity-grant delegation,
role-assignment escalation, Data Explorer row scope, import-log ownership, destructive session
housekeeping, and CSRF-token bootstrap safety.
"""
from unittest.mock import patch

import pytest
from flask import Flask

from app import db
from app.models import UserEntityPermission
from app.models.rbac import RbacAccessGrant, RbacPermission, RbacRole, RbacRolePermission, RbacUserRole
from tests.factories import (
    create_test_admin,
    create_test_assignment_entity_status,
    create_test_country,
    create_test_item,
    create_test_section,
    create_test_template,
    create_test_user,
)
from tests.helpers import login_session

pytestmark = [pytest.mark.unit]

JSON = {"Accept": "application/json"}


def _perm_id(db_session, code):
    perm = db_session.query(RbacPermission).filter_by(code=code).first()
    if perm is None:
        perm = RbacPermission(code=code, name=code, description=code)
        db_session.add(perm)
        db_session.flush()
    return perm.id


def make_delegate(db_session, permission_codes, *, entities=(), role_code=None, email=None):
    """User whose only admin capabilities are ``permission_codes``; optionally holding entity grants."""
    user = create_test_user(db_session, role="user", **({"email": email} if email else {}))
    role_code = role_code or f"test_delegate_{user.id}"
    role = RbacRole(code=role_code, name=role_code)
    db_session.add(role)
    db_session.flush()
    for code in permission_codes:
        db_session.add(RbacRolePermission(role_id=role.id, permission_id=_perm_id(db_session, code)))
    db_session.add(RbacUserRole(user_id=user.id, role_id=role.id))
    for entity_type, entity_id in entities:
        db_session.add(UserEntityPermission(user_id=user.id, entity_type=entity_type, entity_id=entity_id))
    db_session.commit()
    return user


def _fresh(model, pk):
    db.session.expire_all()
    return db.session.get(model, pk)


def login(client, user):
    login_session(client, user.id)
    return client


# ---------------------------------------------------------------------------
# Guard audit
# ---------------------------------------------------------------------------

class TestGuardAudit:
    def test_application_routes_have_no_findings(self, app):
        from app.startup_tasks import collect_admin_route_guard_findings

        findings = collect_admin_route_guard_findings(app)
        assert findings == [], "\n".join(f"{f['kind']}: {f['endpoint']} {f['path']} {f['detail']}" for f in findings)

    def test_strict_audit_passes_on_the_real_app(self, app, monkeypatch):
        from app.startup_tasks import audit_admin_route_guards

        admin_rules = [r for r in app.url_map.iter_rules() if r.rule.startswith("/admin")]
        assert len(admin_rules) > 300
        monkeypatch.setenv("RBAC_ADMIN_ROUTE_GUARD_MODE", "strict")
        audit_admin_route_guards(app)

    def test_policy_tables_reference_existing_endpoints(self, app):
        from app.routes.admin import route_policy as policy

        referenced = (
            set(policy.SYSTEM_MANAGER_ONLY_ENDPOINTS)
            | set(policy.POST_ONLY_ENDPOINTS)
            | set(policy.REQUIRED_PERMISSION_BY_ENDPOINT)
            | set(policy.READ_ONLY_POST_ALLOWLIST)
            | set(policy.CSRF_EXEMPT_MUTATION_ALLOWLIST)
            | set(policy.LOGIN_ONLY_POST_ALLOWLIST)
        )
        assert sorted(referenced - set(app.view_functions)) == []

    def test_plugin_static_route_is_audited_and_documented_exempt(self, app):
        view = app.view_functions["plugin_static.serve_plugin_static"]
        assert view._rbac_guard_audit_exempt is True
        assert view._rbac_guard_audit_exempt_reason

    def _mini_app(self):
        from app.routes.admin.shared import (
            admin_required,
            permission_required,
            permission_required_any,
            system_manager_required,
        )

        mini = Flask(__name__)

        @mini.route("/admin/unguarded")
        def unguarded():
            return "x"

        @mini.route("/admin/read-perm-mutation", methods=["POST"])
        @permission_required("admin.things.view")
        def read_perm_mutation():
            return "x"

        @mini.route("/admin/non-admin-perm")
        @permission_required("things.read")
        def non_admin_perm():
            return "x"

        @mini.route("/admin/get-side-effect")
        @permission_required("admin.things.manage")
        def cleanup_things():
            return "x"

        @mini.route("/admin/ok", methods=["POST"])
        @permission_required("admin.things.manage")
        def ok_route():
            return "x"

        @mini.route("/admin/ok-sm", methods=["POST"])
        @admin_required
        @system_manager_required
        def ok_sm():
            return "x"

        @mini.route("/admin/ok-any", methods=["POST"])
        @permission_required_any("admin.a.manage", "admin.b.manage")
        def ok_any():
            return "x"

        return mini

    def test_audit_flags_each_regression_class(self):
        from app.startup_tasks import collect_admin_route_guard_findings

        kinds = {(f["kind"], f["endpoint"]) for f in collect_admin_route_guard_findings(self._mini_app())}
        assert ("missing_guard", "unguarded") in kinds
        assert ("read_permission_on_mutating_route", "read_perm_mutation") in kinds
        assert ("non_admin_permission", "non_admin_perm") in kinds
        assert ("get_side_effect_name", "cleanup_things") in kinds
        assert not {e for _k, e in kinds} & {"ok_route", "ok_sm", "ok_any"}

    def test_audit_flags_policy_violations(self, monkeypatch):
        from app.routes.admin import route_policy as policy
        from app.startup_tasks import collect_admin_route_guard_findings

        monkeypatch.setattr(policy, "SYSTEM_MANAGER_ONLY_ENDPOINTS", frozenset({"ok_route"}))
        monkeypatch.setattr(policy, "POST_ONLY_ENDPOINTS", frozenset({"non_admin_perm"}))
        monkeypatch.setattr(policy, "REQUIRED_PERMISSION_BY_ENDPOINT", {"ok_route": "admin.system.maintain"})
        kinds = {(f["kind"], f["endpoint"]) for f in collect_admin_route_guard_findings(self._mini_app())}
        assert ("policy_system_manager", "ok_route") in kinds
        assert ("policy_post_only", "non_admin_perm") in kinds
        assert ("policy_required_permission", "ok_route") in kinds

    def test_strict_mode_raises(self, monkeypatch):
        from app.startup_tasks import audit_admin_route_guards

        monkeypatch.setenv("RBAC_ADMIN_ROUTE_GUARD_MODE", "error")
        with pytest.raises(RuntimeError):
            audit_admin_route_guards(self._mini_app())
        monkeypatch.setenv("RBAC_ADMIN_ROUTE_GUARD_MODE", "off")
        audit_admin_route_guards(self._mini_app())


# ---------------------------------------------------------------------------
# Seed catalog
# ---------------------------------------------------------------------------

class TestSeedCatalog:
    def _roles(self):
        from app.services.organization.rbac_seed_service import _baseline_roles, _permission_catalog

        catalog = _permission_catalog()
        return {c for c, _n, _d in catalog}, {r["code"]: set(r["permission_codes"]) for r in _baseline_roles(catalog)}

    def test_new_permissions_are_in_catalog(self):
        codes, _ = self._roles()
        assert {"admin.system.maintain", "admin.countries.delete", "admin.data_explore.impute"} <= codes

    def test_admin_full_excludes_platform_level_permissions(self):
        _, roles = self._roles()
        assert not roles["admin_full"] & {"admin.settings.manage", "admin.plugins.manage", "admin.system.maintain"}
        assert "admin.countries.delete" in roles["admin_full"]

    def test_dedicated_roles_carry_new_permissions(self):
        _, roles = self._roles()
        assert "admin.system.maintain" in roles["admin_system_maintainer"]
        assert "admin.data_explore.impute" in roles["admin_data_explorer_data_table"]
        assert "admin.countries.delete" in roles["admin_countries_manager"]

    def test_every_role_permission_exists_in_catalog(self):
        codes, roles = self._roles()
        for role_code, perms in roles.items():
            assert perms <= codes, (role_code, perms - codes)


# ---------------------------------------------------------------------------
# Country scope
# ---------------------------------------------------------------------------

class TestCountryScope:
    def _deny_edit_on(self, db_session, user, country):
        for code in ("admin.countries.edit", "admin.organization.manage"):
            db_session.add(
                RbacAccessGrant(
                    principal_type="user",
                    principal_id=user.id,
                    permission_id=_perm_id(db_session, code),
                    scope_kind="entity",
                    entity_type="country",
                    entity_id=country.id,
                    effect="deny",
                )
            )
        db_session.commit()

    def test_edit_page_denied_for_country_with_scoped_deny(self, client, db_session):
        admin = create_test_admin(db_session)
        blocked = create_test_country(db_session, name="Scope Blocked", iso3="SBK", iso2="SK")
        allowed = create_test_country(db_session, name="Scope Allowed", iso3="SAL", iso2="SA")
        self._deny_edit_on(db_session, admin, blocked)
        login(client, admin)

        assert client.get(f"/admin/organization/countries/{blocked.id}/edit").status_code == 302
        assert client.get(f"/admin/organization/countries/{allowed.id}/edit").status_code == 200
        assert client.get(f"/admin/countries/edit/{blocked.id}", headers=JSON).status_code == 403

    def test_delete_requires_dedicated_permission(self, logged_in_client, db_session):
        from app.models import Country

        country = create_test_country(db_session, name="Delete Perm Country", iso3="DPC", iso2="DP")
        resp = logged_in_client.post(f"/admin/organization/countries/{country.id}/delete", headers=JSON)
        assert resp.status_code == 403
        resp = logged_in_client.post(f"/admin/countries/delete/{country.id}", headers=JSON)
        assert resp.status_code == 403
        assert _fresh(Country, country.id) is not None

    def test_delete_allowed_with_permission_and_blocked_by_scoped_deny(self, client, db_session):
        from app.models import Country

        admin = create_test_admin(db_session)
        role = RbacRole.query.filter_by(code="admin_core").first()
        db_session.add(RbacRolePermission(role_id=role.id, permission_id=_perm_id(db_session, "admin.countries.delete")))
        keep = create_test_country(db_session, name="Keep Country", iso3="KPC", iso2="KC")
        gone = create_test_country(db_session, name="Gone Country", iso3="GNC", iso2="GC")
        db_session.add(
            RbacAccessGrant(
                principal_type="user",
                principal_id=admin.id,
                permission_id=_perm_id(db_session, "admin.countries.delete"),
                scope_kind="entity",
                entity_type="country",
                entity_id=keep.id,
                effect="deny",
            )
        )
        db_session.commit()
        keep_id, gone_id = keep.id, gone.id
        login(client, admin)

        client.post(f"/admin/organization/countries/{keep_id}/delete")
        assert _fresh(Country, keep_id) is not None
        client.post(f"/admin/organization/countries/{gone_id}/delete")
        assert _fresh(Country, gone_id) is None

    def test_delete_refused_while_users_hold_access_to_country(self, client, db_session):
        from app.models import Country

        admin = create_test_admin(db_session)
        role = RbacRole.query.filter_by(code="admin_core").first()
        db_session.add(RbacRolePermission(role_id=role.id, permission_id=_perm_id(db_session, "admin.countries.delete")))
        country = create_test_country(db_session, name="In Use Country", iso3="IUC", iso2="IU")
        holder = create_test_user(db_session, role="focal_point")
        db_session.add(UserEntityPermission(user_id=holder.id, entity_type="country", entity_id=country.id))
        db_session.commit()
        country_id = country.id
        login(client, admin)
        client.post(f"/admin/organization/countries/{country_id}/delete")
        client.post(f"/admin/countries/delete/{country_id}")
        assert _fresh(Country, country_id) is not None

    def test_country_import_cannot_modify_out_of_scope_country(self):
        import inspect

        from app.routes.admin.organization import import_export

        assert "user_has_country_permission" in inspect.getsource(import_export.import_countries)


# ---------------------------------------------------------------------------
# Entity-grant delegation
# ---------------------------------------------------------------------------

class TestEntityGrantDelegation:
    def _setup(self, db_session):
        country_a = create_test_country(db_session, name="Delegate A", iso3="DLA", iso2="DA")
        country_b = create_test_country(db_session, name="Delegate B", iso3="DLB", iso2="DB")
        target = create_test_user(db_session, role="focal_point")
        actor = make_delegate(
            db_session,
            ["admin.users.grants.manage", "admin.users.view"],
            entities=[("country", country_a.id)],
        )
        return actor, target, country_a, country_b

    def _add(self, client, target, country):
        return client.post(
            f"/admin/users/{target.id}/entities/add",
            json={"entity_type": "country", "entity_id": country.id},
        )

    def test_cannot_grant_country_outside_own_scope(self, client, db_session):
        actor, target, _a, country_b = self._setup(db_session)
        resp = self._add(login(client, actor), target, country_b)
        assert resp.status_code == 403
        assert UserEntityPermission.query.filter_by(user_id=target.id, entity_id=country_b.id).count() == 0

    def test_can_grant_country_inside_own_scope(self, client, db_session):
        actor, target, country_a, _b = self._setup(db_session)
        resp = self._add(login(client, actor), target, country_a)
        assert resp.status_code == 200
        assert UserEntityPermission.query.filter_by(user_id=target.id, entity_id=country_a.id).count() == 1

    def test_cannot_revoke_out_of_scope_grant(self, client, db_session):
        actor, target, _a, country_b = self._setup(db_session)
        perm = UserEntityPermission(user_id=target.id, entity_type="country", entity_id=country_b.id)
        db_session.add(perm)
        db_session.commit()
        resp = login(client, actor).delete(f"/admin/users/{target.id}/entities/remove/{perm.id}")
        assert resp.status_code == 403
        assert _fresh(UserEntityPermission, perm.id) is not None

    def test_cannot_change_own_grants(self, client, db_session):
        actor, _t, _a, country_b = self._setup(db_session)
        resp = self._add(login(client, actor), actor, country_b)
        assert resp.status_code == 403

    def test_cannot_change_grants_of_admin_user(self, client, db_session):
        actor, _t, country_a, _b = self._setup(db_session)
        other_admin = create_test_admin(db_session)
        resp = self._add(login(client, actor), other_admin, country_a)
        assert resp.status_code == 403

    def test_global_country_scope_actor_can_grant_any_country(self, client, db_session):
        _actor, target, _a, country_b = self._setup(db_session)
        wide = make_delegate(db_session, ["admin.users.grants.manage", "admin.countries.view"])
        assert self._add(login(client, wide), target, country_b).status_code == 200

    def test_system_manager_can_grant_any_country(self, logged_in_sm_client, db_session):
        _actor, target, _a, country_b = self._setup(db_session)
        assert self._add(logged_in_sm_client, target, country_b).status_code == 200

    def test_scoped_replace_keeps_out_of_scope_rows(self, app, db_session):
        from flask_login import login_user

        from app.routes.admin.user_management.helpers import apply_scoped_entity_replace

        actor, target, country_a, country_b = self._setup(db_session)
        country_c = create_test_country(db_session, name="Delegate C", iso3="DLC", iso2="DC")
        for c in (country_a, country_b):
            db_session.add(UserEntityPermission(user_id=target.id, entity_type="country", entity_id=c.id))
        db_session.commit()

        with app.test_request_context("/"):
            login_user(actor)
            result = apply_scoped_entity_replace(actor, target, "country", [country_c.id])
            db_session.commit()

        remaining = {p.entity_id for p in UserEntityPermission.query.filter_by(user_id=target.id, entity_type="country")}
        assert remaining == {country_b.id}
        assert result["skipped_add"] == [country_c.id]
        assert result["skipped_remove"] == [country_b.id]


# ---------------------------------------------------------------------------
# Role assignment escalation
# ---------------------------------------------------------------------------

class TestRoleAssignmentEscalation:
    def _roles(self, db_session):
        harmless = RbacRole(code="assignment_extra_viewer", name="Extra viewer")
        powerful = RbacRole(code="custom_ops_lead", name="Custom ops lead")
        db_session.add_all([harmless, powerful])
        db_session.flush()
        db_session.add(RbacRolePermission(role_id=harmless.id, permission_id=_perm_id(db_session, "assignment.view")))
        db_session.add(RbacRolePermission(role_id=powerful.id, permission_id=_perm_id(db_session, "admin.settings.manage")))
        db_session.commit()
        return harmless, powerful

    def test_catalog_hides_roles_the_actor_cannot_hand_out(self, client, db_session):
        harmless, powerful = self._roles(db_session)
        actor = make_delegate(db_session, ["admin.users.roles.assign", "admin.users.view"])
        codes = {r["code"] for r in login(client, actor).get("/admin/api/rbac/roles").get_json()["data"]}
        assert harmless.code in codes
        assert powerful.code not in codes
        assert not codes & {"system_manager", "admin_full", "admin_plugins_manager"}

    def test_catalog_lists_everything_for_system_manager(self, logged_in_sm_client, db_session):
        _h, powerful = self._roles(db_session)
        codes = {r["code"] for r in logged_in_sm_client.get("/admin/api/rbac/roles").get_json()["data"]}
        assert powerful.code in codes

    def test_requested_role_with_unheld_admin_permission_is_dropped(self, app, db_session):
        from app.routes.admin.user_management.helpers import _filter_requested_admin_roles_for_actor

        harmless, powerful = self._roles(db_session)
        actor = make_delegate(db_session, ["admin.users.roles.assign", "admin.users.view"])
        with app.test_request_context("/"):
            kept, dropped = _filter_requested_admin_roles_for_actor([harmless.id, powerful.id], actor)
        assert kept == [harmless.id]
        assert dropped == [powerful.id]

    def test_actor_may_hand_out_role_whose_admin_permissions_it_holds(self, app, db_session):
        from app.routes.admin.user_management.helpers import _filter_requested_admin_roles_for_actor

        _h, powerful = self._roles(db_session)
        actor = make_delegate(db_session, ["admin.users.roles.assign", "admin.settings.manage"])
        with app.test_request_context("/"):
            kept, dropped = _filter_requested_admin_roles_for_actor([powerful.id], actor)
        assert kept == [powerful.id] and dropped == []

    def test_api_patch_cannot_grant_escalating_role(self, client, db_session):
        _h, powerful = self._roles(db_session)
        actor = make_delegate(db_session, ["admin.users.roles.assign", "admin.users.edit", "admin.users.view"])
        target = create_test_user(db_session, role="user")
        resp = login(client, actor).patch(
            f"/admin/api/users/{target.id}", json={"rbac_role_ids": [powerful.id]}, headers=JSON
        )
        assert resp.status_code == 400
        assert RbacUserRole.query.filter_by(user_id=target.id, role_id=powerful.id).count() == 0


# ---------------------------------------------------------------------------
# Data Explorer row scope
# ---------------------------------------------------------------------------

class TestApplyImputedValueScope:
    URL = "/admin/data-exploration/apply-imputed-value"

    def _row(self, db_session, owner_id):
        from app.models import FormData

        template = create_test_template(db_session, owner_id=owner_id)
        country = create_test_country(db_session)
        aes = create_test_assignment_entity_status(db_session, country=country, template=template)
        version_id = template.published_version_id
        section = create_test_section(db_session, template)
        item = create_test_item(db_session, section, template, type="number")
        fd = FormData(assignment_entity_status_id=aes.id, form_item_id=item.id, value="1")
        db_session.add(fd)
        db_session.commit()
        return template, country, aes, item, fd, version_id

    def _explorer(self, db_session, *, impute=True, entities=()):
        perms = ["admin.data_explore.data_table"] + (["admin.data_explore.impute"] if impute else [])
        return make_delegate(db_session, perms, entities=entities)

    def test_user_without_template_access_cannot_impute(self, client, db_session):
        from app.models import FormData

        owner = create_test_user(db_session, role="user")
        _t, _c, aes, item, fd, _v = self._row(db_session, owner.id)
        actor = self._explorer(db_session)
        resp = login(client, actor).post(self.URL, json={"form_data_id": fd.id, "imputed_value": "9"})
        assert resp.status_code == 404
        resp = client.post(
            self.URL, json={"submission_id": aes.id, "form_item_id": item.id, "imputed_value": "9"}
        )
        assert resp.status_code == 404
        assert _fresh(FormData, fd.id).imputed_value is None

    def test_impute_permission_is_required_in_addition_to_data_table(self, client, db_session):
        owner = create_test_user(db_session, role="user")
        _t, _c, _aes, _i, fd, _v = self._row(db_session, owner.id)
        actor = self._explorer(db_session, impute=False)
        resp = login(client, actor).post(
            self.URL, json={"form_data_id": fd.id, "imputed_value": "9"}, headers=JSON
        )
        assert resp.status_code == 403

    def test_template_owner_with_country_access_can_impute(self, client, db_session):
        from app.models import FormData

        actor = self._explorer(db_session)
        template, country, _aes, _item, fd, _v = self._row(db_session, actor.id)
        db_session.add(UserEntityPermission(user_id=actor.id, entity_type="country", entity_id=country.id))
        db_session.commit()
        resp = login(client, actor).post(self.URL, json={"form_data_id": fd.id, "imputed_value": "9"})
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert _fresh(FormData, fd.id).imputed_value == "9"

    def test_template_owner_without_country_access_cannot_impute(self, client, db_session):
        from app.models import FormData

        actor = self._explorer(db_session)
        _t, _c, _aes, _item, fd, _v = self._row(db_session, actor.id)
        resp = login(client, actor).post(self.URL, json={"form_data_id": fd.id, "imputed_value": "9"})
        assert resp.status_code == 404
        assert _fresh(FormData, fd.id).imputed_value is None

    def test_form_item_from_another_template_is_rejected(self, client, db_session):
        actor = self._explorer(db_session)
        template, country, aes, _item, _fd, _v = self._row(db_session, actor.id)
        db_session.add(UserEntityPermission(user_id=actor.id, entity_type="country", entity_id=country.id))
        other_template = create_test_template(db_session, owner_id=actor.id)
        other_item = create_test_item(
            db_session, create_test_section(db_session, other_template), other_template, type="number"
        )
        db_session.commit()
        resp = login(client, actor).post(
            self.URL, json={"submission_id": aes.id, "form_item_id": other_item.id, "imputed_value": "9"}
        )
        assert resp.status_code == 400

    def test_ai_opinions_are_filtered_by_scope(self, client, db_session):
        owner = create_test_user(db_session, role="user")
        _t, _c, _aes, _i, fd, _v = self._row(db_session, owner.id)
        actor = self._explorer(db_session)
        with patch("app.routes.admin.data_exploration._ai_beta_denied_response", return_value=None):
            data = login(client, actor).get(f"/admin/data-exploration/ai-opinions?ids={fd.id}").get_json()
        assert str(fd.id) not in (data.get("opinionsByFormDataId") or {})


# ---------------------------------------------------------------------------
# Import change logs
# ---------------------------------------------------------------------------

class TestImportChangeLogAuthorization:
    LOG_ID = "a" * 32

    def _url(self, suffix="summary.json"):
        return f"/admin/import-logs/{self.LOG_ID}/{suffix}"

    def _stream(self):
        return patch(
            "app.routes.admin.import_change_log.stream_import_log_file",
            return_value=("ok", 200),
        )

    def test_templates_view_alone_cannot_read_someone_elses_log(self, client, db_session):
        actor = make_delegate(db_session, ["admin.templates.view"])
        with self._stream() as stream:
            assert login(client, actor).get(self._url()).status_code == 404
        stream.assert_not_called()

    def test_audit_viewer_can_read_any_log(self, client, db_session):
        actor = make_delegate(db_session, ["admin.audit.view"])
        with self._stream() as stream:
            assert login(client, actor).get(self._url()).status_code == 200
        stream.assert_called_once()

    def test_initiator_can_read_own_log(self, client, db_session):
        from app.models import UserActivityLog

        actor = make_delegate(db_session, ["admin.templates.view"])
        db_session.add(
            UserActivityLog(
                user_id=actor.id,
                activity_type="admin_import",
                ip_address="127.0.0.1",
                context_data={"job_id": self.LOG_ID},
            )
        )
        db_session.commit()
        with self._stream():
            assert login(client, actor).get(self._url()).status_code == 200

    def test_other_users_activity_does_not_grant_access(self, client, db_session):
        from app.models import UserActivityLog

        owner = create_test_user(db_session, role="user")
        db_session.add(
            UserActivityLog(
                user_id=owner.id,
                activity_type="admin_import",
                ip_address="127.0.0.1",
                context_data={"job_id": self.LOG_ID},
            )
        )
        db_session.commit()
        actor = make_delegate(db_session, ["admin.templates.view"])
        with self._stream():
            assert login(client, actor).get(self._url("changes.jsonl")).status_code == 404

    def test_system_manager_can_read(self, logged_in_sm_client):
        with self._stream():
            assert logged_in_sm_client.get(self._url()).status_code == 200

    def test_invalid_id_is_404(self, logged_in_sm_client):
        assert logged_in_sm_client.get("/admin/import-logs/not-a-log-id/summary.json").status_code == 404


# ---------------------------------------------------------------------------
# Destructive housekeeping is not a read permission
# ---------------------------------------------------------------------------

class TestSessionHousekeepingPermissions:
    @pytest.mark.parametrize(
        "url",
        [
            "/admin/utilities/sessions/cleanup",
            "/admin/analytics/cleanup-sessions",
            "/admin/analytics/end-session/abc",
            "/admin/api/analytics/end-session/abc",
        ],
    )
    def test_analytics_viewer_is_denied(self, client, db_session, url):
        viewer = make_delegate(db_session, ["admin.analytics.view"])
        assert login(client, viewer).post(url, headers=JSON).status_code == 403

    def test_security_event_resolution_needs_respond_permission(self, client, db_session):
        viewer = make_delegate(db_session, ["admin.analytics.view", "admin.security.view"])
        assert login(client, viewer).post("/admin/analytics/security-events/1/resolve", headers=JSON).status_code == 403
        responder = make_delegate(db_session, ["admin.security.respond"])
        assert login(client, responder).post(
            "/admin/analytics/security-events/999999/resolve", headers=JSON
        ).status_code != 403

    def test_maintainer_passes_the_guard(self, client, db_session):
        maintainer = make_delegate(db_session, ["admin.system.maintain"])
        resp = login(client, maintainer).post("/admin/api/analytics/end-session/does-not-exist", headers=JSON)
        assert resp.status_code in (400, 404)


# ---------------------------------------------------------------------------
# CSRF bootstrap
# ---------------------------------------------------------------------------

class TestCsrfRefreshHardening:
    def test_cross_site_fetch_is_refused(self, logged_in_client):
        resp = logged_in_client.get("/admin/api/refresh-csrf-token", headers={"Sec-Fetch-Site": "cross-site"})
        assert resp.status_code == 403

    def test_same_origin_gets_uncacheable_token(self, logged_in_client):
        resp = logged_in_client.get("/admin/api/refresh-csrf-token", headers={"Sec-Fetch-Site": "same-origin"})
        assert resp.status_code == 200
        assert resp.headers["Cache-Control"] == "no-store"
        assert resp.get_json()["csrf_token"]

    def test_anonymous_gets_no_token(self, client):
        resp = client.get("/admin/api/refresh-csrf-token", headers=JSON)
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# DEBUG_SKIP_LOGIN
# ---------------------------------------------------------------------------

class TestDebugSkipLogin:
    URL = "/admin/api/refresh-csrf-token"
    HEADERS = {"Accept": "application/json", "Sec-Fetch-Site": "same-origin"}

    @pytest.fixture
    def skip_login(self, app, monkeypatch, db_session):
        create_test_user(db_session, role="system_manager")
        monkeypatch.setitem(app.config, "DEBUG_SKIP_LOGIN", True)
        monkeypatch.setitem(app.config, "FLASK_CONFIG", "development")
        monkeypatch.setitem(app.config, "DEBUG", True)

    def _get(self, client, *, remote_addr="127.0.0.1", headers=None):
        return client.get(
            self.URL,
            headers={**self.HEADERS, **(headers or {})},
            environ_overrides={"REMOTE_ADDR": remote_addr},
        )

    def test_direct_loopback_logs_in_with_a_fresh_session(self, client, skip_login):
        with client.session_transaction() as sess:
            sess["pre_auth_marker"] = "fixation"
            sess["session_id"] = "attacker-chosen"
        resp = self._get(client)
        assert resp.status_code == 200
        with client.session_transaction() as sess:
            assert "pre_auth_marker" not in sess
            assert sess["session_id"] != "attacker-chosen"
            assert sess["debug_skip_login"] is True
            assert sess["session_start"] and sess["last_activity"]
            assert sess.permanent is True

    def test_ipv6_loopback_is_accepted(self, client, skip_login):
        assert self._get(client, remote_addr="::1").status_code == 200

    @pytest.mark.parametrize("remote_addr", ["203.0.113.9", "10.0.0.5"])
    def test_non_loopback_is_not_logged_in(self, client, skip_login, remote_addr):
        assert self._get(client, remote_addr=remote_addr).status_code in (302, 401)
        with client.session_transaction() as sess:
            assert "debug_skip_login" not in sess

    @pytest.mark.parametrize("header", ["X-Forwarded-For", "X-Real-IP", "Forwarded"])
    def test_proxied_loopback_is_not_logged_in(self, client, skip_login, header):
        resp = self._get(client, headers={header: "203.0.113.9"})
        assert resp.status_code in (302, 401)

    @pytest.mark.parametrize(
        "overrides",
        [{"FLASK_CONFIG": "testing"}, {"FLASK_CONFIG": "production"}, {"DEBUG": False}],
    )
    def test_ignored_outside_development_with_debug(self, app, client, skip_login, monkeypatch, overrides):
        for key, value in overrides.items():
            monkeypatch.setitem(app.config, key, value)
        assert self._get(client).status_code in (302, 401)

    def test_disabled_by_default(self, app, client, db_session):
        create_test_user(db_session, role="system_manager")
        assert app.config.get("DEBUG_SKIP_LOGIN") in (False, None)
        assert self._get(client).status_code in (302, 401)
