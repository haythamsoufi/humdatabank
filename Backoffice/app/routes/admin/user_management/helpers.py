"""Shared helper functions for the user-management blueprint."""

from contextlib import suppress
from collections import defaultdict

from flask import current_app, request

from app import db
from app.models import (
    User, Country, CountryAccessRequest, UserEntityPermission,
    Notification, NotificationPreferences, NotificationCampaign,
    EmailDeliveryLog, EntityActivityLog, UserLoginLog, UserActivityLog,
    UserSessionLog, AdminActionLog, SecurityEvent, TemplateShare,
    DynamicIndicatorData, RepeatGroupInstance, RepeatGroupData, SubmittedDocument,
    IndicatorBankHistory, IndicatorSuggestion, CommonWord,
    FormTemplate, FormTemplateVersion, SystemSettings, APIKey,
    PasswordResetToken, AIConversation, AIMessage,
)
from app.models.system import UserDevice
from app.utils.entity_groups import get_enabled_entity_groups, get_allowed_entity_type_codes
from app.utils.azure_b2c_config import is_azure_b2c_configured


def _apply_role_type_and_implications(
    requested_role_ids: list[int] | list,
    *,
    role_type: str | None,
    drop_role_codes: set[str] | None = None,
) -> list[int]:
    """
    Backend enforcement for role-type defaults and role implications.

    - If role_type == 'focal_point': ensure at least one assignment role is present
      (default to Assignment Viewer when none are selected).
    - Always drop deprecated "documents upload only" role(s) from the request (we treat upload as part of Editor & Submitter).

    Best-effort: if RBAC tables aren't available, returns cleaned ints only.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    cleaned: list[int] = []
    for rid in (requested_role_ids or []):
        with suppress(Exception):
            if rid is None:
                continue
            cleaned.append(int(rid))

    # de-dupe while preserving order
    seen = set()
    cleaned = [r for r in cleaned if not (r in seen or seen.add(r))]

    _log.debug("[_apply_role_type] ENTER role_type=%r, cleaned_ids=%s", role_type, cleaned)

    try:
        from app.models.rbac import RbacRole
    except Exception as e:
        current_app.logger.debug("RbacRole import failed: %s", e)
        return cleaned

    drop_role_codes = drop_role_codes or set()
    normalized_role_type = (role_type or "").strip().lower()

    # Unknown/tampered role_type values (anything other than the two valid options)
    # must not silently bypass both the admin-auto-downgrade and the focal-point
    # admin-stripping safety nets below. Default to the more restrictive option.
    if normalized_role_type not in ("admin", "focal_point"):
        normalized_role_type = "focal_point"

    # Auto-downgrade: "admin" without any admin_* roles and without assignment_approver
    # is effectively a focal point.  The UI does this client-side too, but we enforce here
    # as a safety net.
    if normalized_role_type == "admin" and cleaned:
        try:
            _rows = (
                RbacRole.query.with_entities(RbacRole.id, RbacRole.code)
                .filter(RbacRole.id.in_(cleaned))
                .all()
            )
            _codes = {str(code) for _, code in _rows if code}
            has_admin = any(c.startswith("admin_") or c == "system_manager" for c in _codes)
            has_approver = "assignment_approver" in _codes
            _log.debug("[_apply_role_type] auto-downgrade check: codes=%s, has_admin=%s, has_approver=%s", _codes, has_admin, has_approver)
            if not has_admin and not has_approver:
                normalized_role_type = "focal_point"
                _log.debug("[_apply_role_type] DOWNGRADED to focal_point")
        except Exception as e:
            current_app.logger.debug("_apply_role_type auto-downgrade check failed: %s", e)

    _log.debug("[_apply_role_type] normalized_role_type=%s", normalized_role_type)

    _FOCAL_POINT_ASSIGNMENT_CODES = frozenset(
        {"assignment_viewer", "assignment_editor_submitter"}
    )

    required_codes: list[str] = []
    if normalized_role_type == "focal_point":
        # IMPORTANT: Role Type is mutually exclusive between "Admin" and "Focal Point".
        # If the user is saved as a focal point, strip all admin roles regardless of what the form submitted
        # (UI may hide admin sections but not uncheck them). Approver is admin-only in the
        # UI, so it is stripped here too — otherwise a stale Approver tick would survive
        # the demotion and grant approval rights to a "focal point".
        def _dropped_for_focal(code: str) -> bool:
            return (
                code.startswith("admin_")
                or code == "system_manager"
                or code == "assignment_approver"
            )

        code_by_id: dict[int, str] = {}
        try:
            cleaned_rows = (
                RbacRole.query.with_entities(RbacRole.id, RbacRole.code)
                .filter(RbacRole.id.in_(cleaned))
                .all()
            )
            code_by_id = {int(rid): str(code) for rid, code in cleaned_rows if rid and code}
            cleaned = [rid for rid in cleaned if not _dropped_for_focal(code_by_id.get(int(rid), ""))]
            has_assignment_role = any(
                code_by_id.get(int(rid), "") in _FOCAL_POINT_ASSIGNMENT_CODES for rid in cleaned
            )
            if not has_assignment_role:
                required_codes = ["assignment_viewer"]
        except Exception as e:
            current_app.logger.debug("RBAC code_by_id query failed: %s", e)
            required_codes = ["assignment_viewer"]

    # Assignment roles are now independent of admin_core — they must be explicitly assigned.
    # Do not auto-inject assignment roles based on admin role presence.

    # Resolve role IDs in bulk
    target_codes = set(drop_role_codes) | set(required_codes)
    if not target_codes:
        return cleaned

    rows = (
        RbacRole.query.with_entities(RbacRole.id, RbacRole.code)
        .filter(RbacRole.code.in_(list(target_codes)))
        .all()
    )
    id_by_code = {str(code): int(rid) for rid, code in rows if rid and code}

    # Drop deprecated codes (if present)
    drop_ids = {id_by_code[c] for c in drop_role_codes if c in id_by_code}
    if drop_ids:
        cleaned = [rid for rid in cleaned if rid not in drop_ids]

    # Add required codes (if present)
    for c in required_codes:
        rid = id_by_code.get(c)
        if rid and rid not in cleaned:
            cleaned.append(rid)

    return cleaned


def _selected_role_type_for_rerender(form) -> str | None:
    """
    Role type to re-select when re-rendering the user form after a failed POST.

    Returns the submitted role_type ('admin' / 'focal_point') so the template does
    not snap back to the DB-computed type while checkboxes still reflect the POST.
    As a side effect, when 'focal_point' was submitted, scrubs admin roles from
    form.rbac_roles.data so stale (hidden) admin ticks are not re-rendered checked.

    Returns None for GET requests or when no valid role_type was submitted
    (e.g. the selector was disabled/read-only).
    """
    if request.method != "POST":
        return None
    raw = (request.form.get("role_type") or "").strip().lower()
    if raw not in ("admin", "focal_point"):
        return None
    if raw == "focal_point" and getattr(form, "rbac_roles", None) is not None:
        form.rbac_roles.data = _apply_role_type_and_implications(
            list(form.rbac_roles.data or []),
            role_type="focal_point",
            drop_role_codes={"assignment_documents_uploader"},
        )
    return raw


def _get_allowed_non_country_entity_types():
    """Entity type codes for enabled groups excluding 'countries'."""
    groups = [g for g in get_enabled_entity_groups() if g != 'countries']
    return list(get_allowed_entity_type_codes(groups))


def _warn_if_critical_rbac_roles_missing(restricted_codes: list, restricted_role_ids: set) -> None:
    """
    Defensive integrity check for the privilege-escalation guards in new_user/edit_user.

    Those guards look up System Manager / Admin: Full / Plugins-manager by RBAC role
    `code` and simply no-op (fail OPEN, not closed) if the lookup comes back empty —
    e.g. `if sys_role and not current_is_sys_mgr: <filter choices>` silently skips the
    filter when `sys_role` is None. That's expected/harmless on a fresh install before
    `flask rbac seed` has ever run. But if RBAC *has* been seeded and one of these
    specific codes is still missing (renamed via direct DB edit, corrupted migration,
    accidental deletion, ...), it's a silent, security-relevant misconfiguration that
    should be surfaced in logs rather than swallowed.
    """
    try:
        from app.models.rbac import RbacRole

        if RbacRole.query.first() is None:
            # RBAC hasn't been seeded at all yet; nothing to warn about.
            return
        if len(restricted_role_ids) < len(restricted_codes):
            current_app.logger.warning(
                "RBAC integrity: expected critical role code(s) %s in rbac_role but "
                "only found %d matching row(s). Privilege-escalation guards for the "
                "missing role(s) will not be enforced until the seed data is corrected "
                "(re-run `flask rbac seed`).",
                restricted_codes,
                len(restricted_role_ids),
            )
    except Exception as e:
        current_app.logger.debug("critical RBAC role integrity check failed: %s", e)


def _get_missing_rbac_role_codes_for_display(current_is_sys_mgr: bool) -> list:
    """
    Best-effort list of baseline/extension RBAC role codes missing from the database,
    for the user_form.html "RBAC seed data looks incomplete" banner.

    Only computed for System Managers: they're the only ones who can act on it (by
    running `flask rbac seed`), and it costs an extra query, so non-system-managers
    loading the same form don't pay for it.
    """
    if not current_is_sys_mgr:
        return []
    try:
        from app.services.rbac_seed_service import get_missing_baseline_role_codes
        return get_missing_baseline_role_codes()
    except Exception as e:
        current_app.logger.debug("_get_missing_rbac_role_codes_for_display failed: %s", e)
        return []


def _is_azure_sso_enabled() -> bool:
    """
    Return True when Azure AD B2C (OIDC) login is configured.

    When enabled, users may not have a local password (passwords are managed externally).
    """
    return is_azure_b2c_configured(current_app)


def _normalize_user_email_for_comparison(value) -> str:
    """Lowercase/strip for comparing submitted vs stored login emails."""
    if value is None:
        return ""
    return str(value).strip().lower()


def _compute_role_type_for_user_id(user_id: int, *, check_admin_grants: bool = False) -> str:
    """
    Align with user_form.html role type selector: users with any admin_* role,
    system_manager, or assignment_approver are treated as Admin; otherwise Focal Point.

    Approver counts as Admin because the UI only exposes (and preserves) the Approver
    checkbox in Admin mode; rendering an approver-only user as Focal Point would hide
    the role and strip it on the next save.

    When `check_admin_grants` is True, also treats the user as Admin if
    `AuthorizationService.is_admin()` is true (e.g. via a global scoped admin.*
    access grant with no admin_* role attached). This keeps the Role Type default
    and "target is admin" gating in user_form.html aligned with the actual
    authorization check (`AuthorizationService.is_admin`) used elsewhere (e.g. in
    `edit_user`/`archive_user`) to block non-System-Managers from modifying admins.
    Opt-in only: it costs an extra RBAC query, so bulk list/detail builders that
    call this per-user (see `build_admin_user_list_rows`) should leave it off.
    """
    try:
        from app.models.rbac import RbacUserRole, RbacRole

        user_role_codes = {
            str(code)
            for code, in (
                RbacUserRole.query.join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                .with_entities(RbacRole.code)
                .filter(RbacUserRole.user_id == user_id)
                .all()
            )
        }
        has_admin_roles = any(
            c.startswith("admin_") or c in ("system_manager", "assignment_approver")
            for c in user_role_codes
        )
        if has_admin_roles:
            return "admin"

        if check_admin_grants:
            from app.services.authorization_service import AuthorizationService

            target_user = User.query.get(user_id)
            if target_user and AuthorizationService.is_admin(target_user):
                return "admin"

        return "focal_point"
    except Exception as e:
        current_app.logger.debug("computed_role_type check failed: %s", e)
        return "admin"


def _get_role_ids_by_code_for_user(user: User) -> dict:
    """Return a mapping of role_code -> role_id for roles assigned to a user (best-effort)."""
    try:
        from app.models.rbac import RbacUserRole, RbacRole
    except Exception as e:
        current_app.logger.debug("RbacUserRole/RbacRole import failed: %s", e)
        return {}
    try:
        rows = (
            RbacUserRole.query.join(RbacRole, RbacUserRole.role_id == RbacRole.id)
            .with_entities(RbacRole.code, RbacRole.id)
            .filter(RbacUserRole.user_id == int(getattr(user, "id", 0) or 0))
            .all()
        )
        return {str(code): int(rid) for code, rid in rows if code and rid}
    except Exception as e:
        current_app.logger.debug("_role_code_to_id_map query failed: %s", e)
        return {}


def _filter_requested_admin_roles_for_actor(requested_role_ids, actor: User):
    """
    Enforce: non-system-managers may only assign admin_* roles that they already have.
    Returns (filtered_role_ids, dropped_admin_role_ids).
    """
    try:
        from app.models.rbac import RbacRole
    except Exception as e:
        current_app.logger.debug("RbacRole import failed (_clean_requested_role_ids): %s", e)
        return list(requested_role_ids or []), []

    cleaned = []
    for rid in (requested_role_ids or []):
        try:
            cleaned.append(int(rid))
        except Exception as e:
            current_app.logger.debug("rid int parse failed: %s", e)
            continue
    if not cleaned:
        return [], []

    actor_role_ids_by_code = _get_role_ids_by_code_for_user(actor)
    actor_admin_role_ids = {rid for code, rid in actor_role_ids_by_code.items() if str(code).startswith("admin_")}

    # Resolve requested role codes
    role_rows = RbacRole.query.with_entities(RbacRole.id, RbacRole.code).filter(RbacRole.id.in_(cleaned)).all()
    code_by_id = {int(rid): str(code) for rid, code in role_rows if rid and code}

    dropped = []
    kept = []
    for rid in cleaned:
        code = code_by_id.get(int(rid), "")
        if code.startswith("admin_") and int(rid) not in actor_admin_role_ids:
            dropped.append(int(rid))
            continue
        kept.append(int(rid))
    return kept, dropped


def _filter_role_choices_for_actor(choices, actor: User):
    """
    Filter WTForms rbac_roles choices so non-system-managers only see admin_* roles they already have.
    Choices are [(id, label), ...].
    """
    try:
        from app.models.rbac import RbacRole
    except Exception as e:
        current_app.logger.debug("RbacRole import failed (_role_choices): %s", e)
        return list(choices or [])

    actor_role_ids_by_code = _get_role_ids_by_code_for_user(actor)
    actor_admin_role_ids = {rid for code, rid in actor_role_ids_by_code.items() if str(code).startswith("admin_")}

    ids = []
    for rid, _label in (choices or []):
        try:
            ids.append(int(rid))
        except Exception as e:
            current_app.logger.debug("rid int parse (_role_choices): %s", e)
            continue
    if not ids:
        return list(choices or [])

    rows = RbacRole.query.with_entities(RbacRole.id, RbacRole.code).filter(RbacRole.id.in_(ids)).all()
    code_by_id = {int(rid): str(code) for rid, code in rows if rid and code}

    filtered = []
    for rid, label in (choices or []):
        try:
            rid_int = int(rid)
        except Exception as e:
            current_app.logger.debug("rid_int parse failed: %s", e)
            continue
        code = code_by_id.get(rid_int, "")
        if code.startswith("admin_") and rid_int not in actor_admin_role_ids:
            continue
        filtered.append((rid_int, label))
    return filtered


def _country_access_request_to_dict(req: CountryAccessRequest) -> dict:
    """Serialize a CountryAccessRequest for JSON APIs (mobile / AJAX)."""
    user = req.user
    country = req.country
    processor = req.processed_by

    def _iso(dt):
        if not dt:
            return None
        try:
            s = dt.isoformat()
            return s + "Z" if not s.endswith("Z") and "+" not in s else s
        except Exception:
            return None

    return {
        "id": req.id,
        "status": req.status,
        "request_message": req.request_message,
        "created_at": _iso(req.created_at),
        "processed_at": _iso(req.processed_at),
        "admin_notes": req.admin_notes,
        "user": {
            "id": user.id if user else None,
            "email": user.email if user else None,
            "name": user.name if user else None,
        },
        "country": {
            "id": country.id if country else None,
            "name": country.name if country else None,
            "iso2": getattr(country, "iso2", None) if country else None,
        },
        "processed_by": (
            {
                "id": processor.id,
                "name": processor.name,
                "email": processor.email,
            }
            if processor
            else None
        ),
    }


def _get_role_codes_by_id() -> dict:
    """
    Return {role_id: role_code} for all RBAC roles (best-effort).

    Used by user_form.html / user-form.js to identify special roles (System
    Manager, Admin: Full, Admin: Core, Translator, Assignment Viewer/Editor &
    Submitter/Approver) by their stable `code` rather than by parsing the
    human-editable `name` label. Falls back to {} if RBAC isn't available yet.
    """
    try:
        from app.models.rbac import RbacRole
        return {int(r.id): str(r.code) for r in RbacRole.query.with_entities(RbacRole.id, RbacRole.code).all()}
    except Exception as e:
        current_app.logger.debug("_get_role_codes_by_id query failed: %s", e)
        return {}


def _get_countries_by_region():
    """Get countries grouped by region for form display"""
    countries_by_region = defaultdict(list)
    all_countries = Country.query.order_by(Country.region, Country.name).all()
    for country in all_countries:
        region_name = country.region if country.region else "Unassigned Region"
        countries_by_region[region_name].append(country)
    return countries_by_region

def _set_user_rbac_roles(user: User, role_ids):
    """Replace RBAC roles for a user (idempotent).

    Safe no-op if RBAC tables are not available (pre-migration).
    """
    try:
        from app.models.rbac import RbacUserRole
    except Exception as e:
        current_app.logger.debug("RbacUserRole import failed: %s", e)
        return

    user_id = getattr(user, "id", None)
    if not user_id:
        return

    cleaned = []
    for rid in (role_ids or []):
        with suppress(Exception):
            if rid is None:
                continue
            cleaned.append(int(rid))
    # de-dupe while preserving order
    seen = set()
    cleaned = [r for r in cleaned if not (r in seen or seen.add(r))]

    # Replace all user roles
    RbacUserRole.query.filter_by(user_id=user_id).delete()
    for rid in cleaned:
        db.session.add(RbacUserRole(user_id=user_id, role_id=rid))


def _ensure_user_has_default_rbac_role(user: User, *, default_role_code: str = "assignment_viewer") -> None:
    """
    Ensure the user has at least one RBAC role (safe default) when the current
    actor is not allowed to assign roles via the UI.

    Best-effort: no-op if RBAC tables are not available yet.
    """
    try:
        from app.models.rbac import RbacRole, RbacUserRole
    except Exception as e:
        current_app.logger.debug("RbacRole/RbacUserRole import failed: %s", e)
        return

    user_id = getattr(user, "id", None)
    if not user_id:
        return

    try:
        existing = RbacUserRole.query.filter_by(user_id=user_id).first()
        if existing:
            return
    except Exception as e:
        current_app.logger.debug("RBAC grant check failed: %s", e)
        return

    role = RbacRole.query.filter_by(code=default_role_code).first()
    if not role:
        # Create a minimal role record if seeding hasn't been run yet.
        role = RbacRole(code=default_role_code, name="Assignment Viewer", description="Read-only access to assignments.")
        db.session.add(role)
        db.session.flush()

    # Assign the role
    db.session.add(RbacUserRole(user_id=user_id, role_id=int(role.id)))

def _get_user_deletion_preview(user: User) -> dict:
    """Build a summary of data that will be deleted or unassigned when deleting the given user."""
    uid = user.id
    # Some tables reference user-owned rows indirectly (e.g., EmailDeliveryLog -> Notification).
    # Use subqueries so the preview matches what the delete cascade will actually remove.
    notif_ids_select = db.select(Notification.id).where(Notification.user_id == uid)
    will_delete = {
        'notifications': Notification.query.filter_by(user_id=uid).count(),
        'notification_preferences': 1 if NotificationPreferences.query.filter_by(user_id=uid).first() else 0,
        'entity_activity_logs': EntityActivityLog.query.filter_by(user_id=uid).count(),
        'country_access_requests': CountryAccessRequest.query.filter_by(user_id=uid).count(),
        'admin_action_logs': AdminActionLog.query.filter_by(admin_user_id=uid).count(),
        'user_session_logs': UserSessionLog.query.filter_by(user_id=uid).count(),
        'template_shares_given': TemplateShare.query.filter_by(shared_by_user_id=uid).count(),
        'template_shares_received': TemplateShare.query.filter_by(shared_with_user_id=uid).count(),
        'dynamic_indicator_data': DynamicIndicatorData.query.filter_by(added_by_user_id=uid).count(),
        'repeat_group_instances': RepeatGroupInstance.query.filter_by(created_by_user_id=uid).count(),
        'submitted_documents': SubmittedDocument.query.filter_by(uploaded_by_user_id=uid).count(),
        'indicator_bank_history': IndicatorBankHistory.query.filter_by(user_id=uid).count(),
        'entity_permissions': UserEntityPermission.query.filter_by(user_id=uid).count(),
        'user_devices': UserDevice.query.filter_by(user_id=uid).count(),
        # Delete logs either owned by this user, OR linked to notifications owned by this user
        'email_delivery_logs': EmailDeliveryLog.query.filter(
            db.or_(
                EmailDeliveryLog.user_id == uid,
                EmailDeliveryLog.notification_id.in_(notif_ids_select),
            )
        ).count(),
        'password_reset_tokens': PasswordResetToken.query.filter_by(user_id=uid).count(),
        'api_keys': APIKey.query.filter_by(user_id=uid).count(),
        'notification_campaigns': NotificationCampaign.query.filter_by(created_by=uid).count(),
        'ai_conversations': AIConversation.query.filter_by(user_id=uid).count(),
        'ai_messages': AIMessage.query.filter_by(user_id=uid).count(),
        'user_activity_logs': UserActivityLog.query.filter_by(user_id=uid).count(),
    }
    will_unassign = {
        'user_login_logs': UserLoginLog.query.filter_by(user_id=uid).count(),
        'security_events_reported': SecurityEvent.query.filter_by(user_id=uid).count(),
        'security_events_resolved_by': SecurityEvent.query.filter_by(resolved_by_user_id=uid).count(),
        'country_access_requests_processed': CountryAccessRequest.query.filter_by(processed_by_user_id=uid).count(),
        'api_keys_created_by': APIKey.query.filter_by(created_by_user_id=uid).count(),
        'system_settings_updated': SystemSettings.query.filter_by(updated_by_user_id=uid).count(),
        'indicator_suggestions_reviewed': IndicatorSuggestion.query.filter_by(reviewed_by_user_id=uid).count(),
        'common_words_created': CommonWord.query.filter_by(created_by_user_id=uid).count(),
    }
    return {
        'will_delete': will_delete,
        'will_unassign': will_unassign,
    }

def _cascade_delete_user_related(user: User) -> None:
    """Delete or unassign records that reference the given user, then delete the user itself."""
    uid = user.id

    # 1) Clear entity permissions (legacy countries derived from permissions)
    UserEntityPermission.query.filter_by(user_id=uid).delete(synchronize_session=False)

    # 2) Delete direct ownership rows that must not remain
    # IMPORTANT: delete dependent rows first to satisfy FK constraints (e.g. email_delivery_log -> notification)
    notif_ids_select = db.select(Notification.id).where(Notification.user_id == uid)
    EmailDeliveryLog.query.filter(
        db.or_(
            EmailDeliveryLog.user_id == uid,
            EmailDeliveryLog.notification_id.in_(notif_ids_select),
        )
    ).delete(synchronize_session=False)
    Notification.query.filter_by(user_id=uid).delete(synchronize_session=False)
    prefs = NotificationPreferences.query.filter_by(user_id=uid).first()
    if prefs:
        db.session.delete(prefs)
    EntityActivityLog.query.filter_by(user_id=uid).delete(synchronize_session=False)
    CountryAccessRequest.query.filter_by(user_id=uid).delete(synchronize_session=False)
    AdminActionLog.query.filter_by(admin_user_id=uid).delete(synchronize_session=False)
    UserSessionLog.query.filter_by(user_id=uid).delete(synchronize_session=False)
    TemplateShare.query.filter(
        db.or_(TemplateShare.shared_by_user_id == uid, TemplateShare.shared_with_user_id == uid)
    ).delete(synchronize_session=False)
    DynamicIndicatorData.query.filter_by(added_by_user_id=uid).delete(synchronize_session=False)
    # repeat_group_data.repeat_instance_id → repeat_group_instance.id has no DB CASCADE;
    # delete child rows before the instances to avoid FK violations.
    user_instance_ids_sq = db.session.query(RepeatGroupInstance.id).filter_by(
        created_by_user_id=uid
    ).subquery()
    RepeatGroupData.query.filter(
        RepeatGroupData.repeat_instance_id.in_(user_instance_ids_sq)
    ).delete(synchronize_session=False)
    RepeatGroupInstance.query.filter_by(created_by_user_id=uid).delete(synchronize_session=False)
    SubmittedDocument.query.filter_by(uploaded_by_user_id=uid).delete(synchronize_session=False)
    IndicatorBankHistory.query.filter_by(user_id=uid).delete(synchronize_session=False)
    UserDevice.query.filter_by(user_id=uid).delete(synchronize_session=False)
    PasswordResetToken.query.filter_by(user_id=uid).delete(synchronize_session=False)
    APIKey.query.filter_by(user_id=uid).delete(synchronize_session=False)
    NotificationCampaign.query.filter_by(created_by=uid).delete(synchronize_session=False)
    # AI chat tables do not define DB-level cascade; delete children first
    AIMessage.query.filter_by(user_id=uid).delete(synchronize_session=False)
    AIConversation.query.filter_by(user_id=uid).delete(synchronize_session=False)

    # 3) Unassign nullable references to preserve history
    # user_activity_log.user_id is NOT NULL in the current schema; delete these logs instead
    UserActivityLog.query.filter_by(user_id=uid).delete(synchronize_session=False)
    UserLoginLog.query.filter_by(user_id=uid).update({'user_id': None}, synchronize_session=False)
    SecurityEvent.query.filter_by(user_id=uid).update({'user_id': None}, synchronize_session=False)
    SecurityEvent.query.filter_by(resolved_by_user_id=uid).update({'resolved_by_user_id': None}, synchronize_session=False)
    CountryAccessRequest.query.filter_by(processed_by_user_id=uid).update({'processed_by_user_id': None}, synchronize_session=False)
    APIKey.query.filter_by(created_by_user_id=uid).update({'created_by_user_id': None}, synchronize_session=False)
    SystemSettings.query.filter_by(updated_by_user_id=uid).update({'updated_by_user_id': None}, synchronize_session=False)
    IndicatorSuggestion.query.filter_by(reviewed_by_user_id=uid).update({'reviewed_by_user_id': None}, synchronize_session=False)
    CommonWord.query.filter_by(created_by_user_id=uid).update({'created_by_user_id': None}, synchronize_session=False)

    # 4) Nullify optional creator/owner pointers on forms
    FormTemplate.query.filter_by(created_by=uid).update({'created_by': None}, synchronize_session=False)
    FormTemplate.query.filter_by(owned_by=uid).update({'owned_by': None}, synchronize_session=False)
    FormTemplateVersion.query.filter_by(created_by=uid).update({'created_by': None}, synchronize_session=False)
    FormTemplateVersion.query.filter_by(updated_by=uid).update({'updated_by': None}, synchronize_session=False)

    # 5) Commit intermediate cleanup before deleting the user
    db.session.flush()

    # 6) Finally delete the user
    db.session.delete(user)
    db.session.flush()


def build_admin_user_list_rows(users: list) -> list[dict]:
    """
    Directory rows aligned with GET /admin/api/users (Flutter / mobile admin list).

    Bulk-loads RBAC + entity permissions for the given User ORM objects only.
    """
    if not users:
        return []

    user_ids = [u.id for u in users]

    roles_by_user_id: dict = {}
    try:
        from app.models.rbac import RbacUserRole, RbacRole

        user_roles = RbacUserRole.query.filter(RbacUserRole.user_id.in_(user_ids)).all()
        role_ids = list({ur.role_id for ur in user_roles})
        roles = RbacRole.query.filter(RbacRole.id.in_(role_ids)).all() if role_ids else []
        roles_by_id = {r.id: r for r in roles}
        for ur in user_roles:
            roles_by_user_id.setdefault(ur.user_id, []).append(roles_by_id.get(ur.role_id))
    except Exception as e:
        current_app.logger.debug("build_admin_user_list_rows roles: %s", e)
        roles_by_user_id = {}

    all_permissions = UserEntityPermission.query.filter(
        UserEntityPermission.user_id.in_(user_ids)
    ).all()

    permissions_by_user: dict = {}
    for perm in all_permissions:
        if perm.user_id not in permissions_by_user:
            permissions_by_user[perm.user_id] = {}
        if perm.entity_type not in permissions_by_user[perm.user_id]:
            permissions_by_user[perm.user_id][perm.entity_type] = 0
        permissions_by_user[perm.user_id][perm.entity_type] += 1

    country_ids: set = set()
    for perm in all_permissions:
        if perm.entity_type == "country":
            country_ids.add(perm.entity_id)

    countries_by_id: dict = {}
    if country_ids:
        for c in Country.query.filter(Country.id.in_(country_ids)).all():
            countries_by_id[c.id] = c

    user_countries_map: dict = {}
    for perm in all_permissions:
        if perm.entity_type == "country" and perm.entity_id in countries_by_id:
            user_countries_map.setdefault(perm.user_id, []).append(countries_by_id[perm.entity_id])

    users_data: list[dict] = []
    for user in users:
        user_countries = []
        for country in user_countries_map.get(user.id, []):
            user_countries.append(
                {
                    "id": country.id,
                    "name": country.name,
                    "code": country.iso3,
                }
            )

        entity_counts: dict = {}
        user_perms = permissions_by_user.get(user.id, {})

        if user_perms.get("ns_branch", 0) > 0:
            entity_counts["branches"] = user_perms["ns_branch"]
        if user_perms.get("ns_subbranch", 0) > 0:
            entity_counts["sub_branches"] = user_perms["ns_subbranch"]
        if user_perms.get("ns_localunit", 0) > 0:
            entity_counts["local_units"] = user_perms["ns_localunit"]
        if user_perms.get("division", 0) > 0:
            entity_counts["divisions"] = user_perms["division"]
        if user_perms.get("department", 0) > 0:
            entity_counts["departments"] = user_perms["department"]
        if user_perms.get("regional_office", 0) > 0:
            entity_counts["regional_offices"] = user_perms["regional_office"]

        cluster_perms = user_perms.get("cluster_office", 0)
        if cluster_perms > 0:
            entity_counts["cluster_offices"] = cluster_perms

        rbac_roles = []
        for r in roles_by_user_id.get(user.id) or []:
            if not r:
                continue
            rbac_roles.append({"id": r.id, "code": r.code, "name": r.name})

        users_data.append(
            {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "title": user.title,
                "rbac_roles": rbac_roles,
                "active": user.active,
                "chatbot_enabled": user.chatbot_enabled,
                "profile_color": user.profile_color,
                "country_ids": [c.id for c in user_countries_map.get(user.id, [])],
                "countries": user_countries,
                "entity_counts": entity_counts if entity_counts else None,
                "computed_role_type": _compute_role_type_for_user_id(user.id),
            }
        )

    return users_data


def build_admin_user_detail_dict(user_id: int) -> dict | None:
    """
    User detail payload aligned with GET /admin/api/users/<id> (mobile admin detail).
    """
    from sqlalchemy.orm import selectinload

    from app.models.enums import EntityType
    from app.models.rbac import RbacRole, RbacUserRole
    from app.services.entity_service import EntityService

    user = User.query.get(user_id)
    if not user:
        return None

    user_roles = RbacUserRole.query.filter_by(user_id=user_id).all()
    role_ids = list({ur.role_id for ur in user_roles})
    roles = (
        RbacRole.query.options(selectinload(RbacRole.permissions))
        .filter(RbacRole.id.in_(role_ids))
        .all()
        if role_ids
        else []
    )
    roles_by_id = {r.id: r for r in roles}

    rbac_roles = []
    perm_agg: dict = {}
    for ur in user_roles:
        r = roles_by_id.get(ur.role_id)
        if not r:
            continue
        perms = [{"code": p.code, "name": p.name} for p in sorted(r.permissions, key=lambda x: x.code)]
        for p in r.permissions:
            perm_agg.setdefault(p.code, p.name)
        rbac_roles.append(
            {
                "id": r.id,
                "code": r.code,
                "name": r.name,
                "description": r.description,
                "permissions": perms,
            }
        )

    effective_permissions = [{"code": c, "name": perm_agg[c]} for c in sorted(perm_agg.keys())]

    entity_permissions = UserEntityPermission.query.filter_by(user_id=user_id).all()
    _country_type = EntityType.country.value

    def _perm_is_country(p) -> bool:
        return (p.entity_type or "").strip().lower() == _country_type

    country_ids = list({p.entity_id for p in entity_permissions if _perm_is_country(p)})
    countries_by_id: dict = {}
    if country_ids:
        for c in Country.query.filter(Country.id.in_(country_ids)).all():
            countries_by_id[c.id] = c

    entities_data = []
    perm_pairs = [(perm.entity_type, perm.entity_id) for perm in entity_permissions]
    hierarchy_names = EntityService.batch_entity_names(perm_pairs, include_hierarchy=True)
    for perm in entity_permissions:
        name = hierarchy_names.get((perm.entity_type, perm.entity_id))
        if not isinstance(name, str) or not name.strip():
            et = (perm.entity_type or "entity").replace("_", " ")
            name = f"Unavailable ({et})"
        else:
            name = name.replace("_", " ")
        row = {
            "permission_id": perm.id,
            "entity_type": perm.entity_type,
            "entity_id": perm.entity_id,
            "entity_name": name,
        }
        if _perm_is_country(perm):
            co = countries_by_id.get(perm.entity_id)
            if co:
                reg = (co.region or "").strip()
                row["entity_region"] = reg if reg else "Unassigned Region"
        entities_data.append(row)
    entities_data.sort(
        key=lambda x: (
            x["entity_type"] or "",
            (x.get("entity_region") or "\uffff").lower(),
            (x["entity_name"] or "").lower(),
            x["entity_id"],
        )
    )

    computed_role_type = _compute_role_type_for_user_id(user_id)
    is_system_manager = any((r.get("code") == "system_manager") for r in rbac_roles)

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "title": user.title,
        "active": user.active,
        "chatbot_enabled": user.chatbot_enabled,
        "profile_color": user.profile_color,
        "rbac_roles": rbac_roles,
        "effective_permissions": effective_permissions,
        "entity_permissions": entities_data,
        "computed_role_type": computed_role_type,
        "is_system_manager": is_system_manager,
    }


def _get_translator_form_context(user=None):
    """Template context for per-language translator grants on the user form."""
    from flask_login import current_user
    from app.models.rbac import RbacRole
    from app.services.authorization_service import AuthorizationService
    from app.services.translation_review.assignment_service import get_assigned_language_codes

    translatable = list(current_app.config.get('TRANSLATABLE_LANGUAGES') or [])
    translator_role = RbacRole.query.filter_by(code='translator').first()
    assigned = get_assigned_language_codes(user) if user else []

    actor = current_user
    can_manage = False
    if getattr(actor, 'is_authenticated', False):
        can_manage = (
            AuthorizationService.is_system_manager(actor)
            or AuthorizationService.has_rbac_permission(actor, 'admin.users.roles.assign')
            or AuthorizationService.has_rbac_permission(actor, 'admin.translations.manage')
        )

    return {
        'translatable_languages': translatable,
        'translator_language_codes': assigned,
        'translator_role_id': int(translator_role.id) if translator_role else None,
        'can_manage_translator_languages': can_manage,
    }


def _apply_user_translator_languages(user_id: int, *, can_manage: bool) -> None:
    """Persist translator language grants from the user form POST."""
    if not can_manage:
        return

    from flask_login import current_user
    from app.services.translation_review.assignment_service import set_user_translator_languages

    assigned_by = None
    if getattr(current_user, 'is_authenticated', False):
        assigned_by = int(current_user.id)

    languages = request.form.getlist('translator_languages')
    set_user_translator_languages(
        int(user_id),
        languages,
        assigned_by_user_id=assigned_by,
    )
