"""JSON API endpoints for user management (mobile / AJAX clients)."""

import re
from contextlib import suppress

from flask import request, current_app
from flask_login import current_user

from app import db
from app.models import User, Country, UserEntityPermission, CountryAccessRequest, UserSessionLog
from app.routes.admin.shared import permission_required
from app.services.user_analytics_service import log_admin_action
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_bad_request, json_forbidden, json_not_found, json_ok
from app.utils.error_handling import handle_json_view_exception
from app.utils.transactions import request_transaction_rollback

from . import bp
from .helpers import (
    build_admin_user_detail_dict,
    build_admin_user_list_rows,
    _set_user_rbac_roles,
    _filter_requested_admin_roles_for_actor,
    _country_access_request_to_dict,
    _get_user_deletion_preview,
)


@bp.route("/api/users", methods=["GET"])
@permission_required('admin.users.view')
def api_users_list():
    """API endpoint to get users list in JSON format for Flutter app"""
    try:
        users = User.query.order_by(User.id.asc()).all()
        users_data = build_admin_user_list_rows(users)
        return json_ok(status='success', data=users_data)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/users/<int:user_id>", methods=["GET"])
@permission_required('admin.users.view')
def api_user_detail(user_id):
    """JSON user profile for mobile/admin clients: roles, RBAC permissions, entity grants."""
    try:
        payload = build_admin_user_detail_dict(user_id)
        if not payload:
            return json_not_found("User not found")
        # json_ok merges dict `data` into the root; nest explicitly so clients get { success, data: payload }
        return json_ok({"data": payload}, status="success")
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/rbac/roles", methods=["GET"])
@permission_required('admin.users.roles.assign')
def api_rbac_roles_catalog():
    """JSON list of RBAC roles (id, code, name) for mobile admin role editors."""
    try:
        from app.models.rbac import RbacRole

        roles = RbacRole.query.order_by(RbacRole.code.asc()).all()
        rows = [{"id": r.id, "code": r.code, "name": r.name} for r in roles]
        return json_ok({"data": rows}, status="success")
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/users/<int:user_id>", methods=["PUT", "PATCH"])
@permission_required('admin.users.edit')
def api_user_update(user_id):
    """JSON API: profile fields and/or rbac_role_ids for admin clients."""
    try:
        from app.models.rbac import RbacRole, RbacUserRole
        from app.services.authorization_service import AuthorizationService

        user = User.query.get(user_id)
        if not user:
            return json_not_found("User not found")

        data = request.get_json(silent=True, force=True)
        try:
            raw_len = len(request.get_data(cache=True) or b"")
        except Exception:
            raw_len = None
        ct = (request.content_type or "")[:160]

        def _bad(msg):
            current_app.logger.warning(
                "api_user_update 400: %s | user_id=%s target_user_id=%s actor_id=%s "
                "method=%s content_type=%r content_length=%s raw_body_len=%s json_keys=%s",
                msg,
                user_id,
                user.id,
                getattr(current_user, "id", None),
                request.method,
                ct,
                request.content_length,
                raw_len,
                sorted(data.keys()) if isinstance(data, dict) else None,
            )
            return json_bad_request(msg)

        if not isinstance(data, dict):
            current_app.logger.warning(
                "api_user_update 400: Expected JSON body | user_id=%s target_user_id=%s actor_id=%s "
                "method=%s content_type=%r content_length=%s raw_body_len=%s parsed_type=%s",
                user_id,
                user.id,
                getattr(current_user, "id", None),
                request.method,
                ct,
                request.content_length,
                raw_len,
                type(data).__name__,
            )
            return json_bad_request("Expected JSON body")

        current_app.logger.info(
            "api_user_update: request user_id=%s target_user_id=%s actor_id=%s method=%s "
            "content_type=%r raw_body_len=%s json_keys=%s",
            user_id,
            user.id,
            getattr(current_user, "id", None),
            request.method,
            ct,
            raw_len,
            sorted(data.keys()),
        )

        allowed = {"name", "title", "active", "chatbot_enabled", "profile_color", "rbac_role_ids"}
        if not allowed.intersection(data.keys()):
            return _bad("No updatable fields in request")

        current_is_sys_mgr = AuthorizationService.is_system_manager(current_user)
        editing_self = bool(current_user.id == user.id)
        target_is_admin = bool(AuthorizationService.is_admin(user))
        user_is_sys_mgr = bool(AuthorizationService.is_system_manager(user))

        if (not current_is_sys_mgr) and (not editing_self) and target_is_admin:
            current_app.logger.warning(
                "api_user_update 403: Only a System Manager can modify an admin user | "
                "user_id=%s target_user_id=%s actor_id=%s json_keys=%s",
                user_id,
                user.id,
                getattr(current_user, "id", None),
                sorted(data.keys()),
            )
            return json_forbidden("Only a System Manager can modify an admin user.", success=False)

        if user_is_sys_mgr and not current_is_sys_mgr:
            current_app.logger.warning(
                "api_user_update 403: Only a System Manager can modify a System Manager user | "
                "user_id=%s target_user_id=%s actor_id=%s json_keys=%s",
                user_id,
                user.id,
                getattr(current_user, "id", None),
                sorted(data.keys()),
            )
            return json_forbidden("Only a System Manager can modify a System Manager user.", success=False)

        try:
            old_rbac_role_ids = [ur.role_id for ur in RbacUserRole.query.filter_by(user_id=user.id).all()]
        except Exception as e:
            current_app.logger.debug("old_rbac_role_ids query failed: %s", e)
            old_rbac_role_ids = []

        old_values = {
            "name": user.name,
            "title": user.title,
            "active": user.active,
            "chatbot_enabled": user.chatbot_enabled,
            "profile_color": user.profile_color,
            "rbac_role_ids": old_rbac_role_ids,
        }

        if "name" in data:
            raw = data.get("name")
            if raw is None:
                user.name = None
            else:
                name = str(raw).strip()
                if len(name) > 100:
                    return _bad("Name must be 100 characters or less")
                user.name = name if name else None

        if "title" in data:
            raw = data.get("title")
            if raw is None or (isinstance(raw, str) and not str(raw).strip()):
                user.title = None
            else:
                t = str(raw).strip()
                if len(t) > 100:
                    return _bad("Title must be 100 characters or less")
                user.title = t

        if "chatbot_enabled" in data:
            user.chatbot_enabled = bool(data.get("chatbot_enabled"))

        if "profile_color" in data:
            raw_pc = data.get("profile_color")
            # Explicit JSON null means "do not change" (PATCH-style), not "clear to empty".
            if raw_pc is None:
                pass
            else:
                pc = str(raw_pc).strip()
                if not pc:
                    return _bad("profile_color cannot be empty")
                if not re.match(r"^#[0-9A-Fa-f]{6}$", pc):
                    return _bad("profile_color must be a #RRGGBB hex value")
                user.profile_color = pc

        if "active" in data:
            new_active = bool(data.get("active"))
            if not new_active and user.id == current_user.id:
                return _bad("You cannot deactivate your own account")
            user.active = new_active
            if new_active:
                user.deactivated_at = None
            else:
                user.deactivated_at = db.func.now()

        if "rbac_role_ids" in data:
            if not AuthorizationService.has_rbac_permission(current_user, "admin.users.roles.assign"):
                current_app.logger.warning(
                    "api_user_update 403: role assign denied | user_id=%s target_user_id=%s actor_id=%s",
                    user_id,
                    user.id,
                    getattr(current_user, "id", None),
                )
                return json_forbidden("You do not have permission to assign roles.", success=False)
            roles_read_only = bool(editing_self and not current_is_sys_mgr)
            if roles_read_only:
                return _bad("You cannot change your own roles.")

            raw_ids = data.get("rbac_role_ids")
            if not isinstance(raw_ids, list):
                return _bad("rbac_role_ids must be a list")
            requested_role_ids = []
            for x in raw_ids:
                try:
                    requested_role_ids.append(int(x))
                except Exception:
                    return _bad("Invalid role id in rbac_role_ids")

            sys_role = RbacRole.query.filter_by(code="system_manager").first()
            plugins_role = RbacRole.query.filter_by(code="admin_plugins_manager").first()

            restricted_role_ids = set()
            try:
                restricted_codes = ["system_manager", "admin_full", "admin_plugins_manager"]
                rows = RbacRole.query.filter(RbacRole.code.in_(restricted_codes)).with_entities(RbacRole.id).all()
                restricted_role_ids = {int(r[0]) for r in rows if r and r[0] is not None}
            except Exception as e:
                current_app.logger.debug("restricted_role_ids query failed: %s", e)

            if not current_is_sys_mgr and restricted_role_ids:
                requested_role_ids = [rid for rid in requested_role_ids if int(rid) not in restricted_role_ids]

            if sys_role and (sys_role.id in requested_role_ids) and not current_is_sys_mgr:
                return _bad("Only a System Manager can assign the System Manager role.")

            if plugins_role and (plugins_role.id in requested_role_ids) and not current_is_sys_mgr:
                return _bad("Only a System Manager can assign the Plugins role.")

            if not current_is_sys_mgr:
                requested_role_ids, _dropped = _filter_requested_admin_roles_for_actor(requested_role_ids, current_user)

            if not requested_role_ids:
                return _bad("rbac_role_ids must include at least one role")

            _set_user_rbac_roles(user, requested_role_ids)

        db.session.flush()

        try:
            new_rbac_role_ids = [ur.role_id for ur in RbacUserRole.query.filter_by(user_id=user.id).all()]
        except Exception as e:
            current_app.logger.debug("new_rbac_role_ids query failed: %s", e)
            new_rbac_role_ids = old_rbac_role_ids

        new_values = {
            "name": user.name,
            "title": user.title,
            "active": user.active,
            "chatbot_enabled": user.chatbot_enabled,
            "profile_color": user.profile_color,
            "rbac_role_ids": new_rbac_role_ids,
        }

        risk_level = "low"
        if old_values.get("active") != new_values.get("active"):
            risk_level = "medium"
        if set(old_values.get("rbac_role_ids") or []) != set(new_values.get("rbac_role_ids") or []):
            risk_level = "medium"

        log_admin_action(
            action_type="user_update",
            description=f"Updated user (API): {user.email}",
            target_type="user",
            target_id=user.id,
            target_description=f"{user.name or user.email}",
            old_values=old_values,
            new_values=new_values,
            risk_level=risk_level,
        )
        db.session.flush()
        current_app.logger.info(
            "api_user_update: success user_id=%s target_user_id=%s actor_id=%s",
            user_id,
            user.id,
            getattr(current_user, "id", None),
        )
        return json_ok(status="success", message="User updated successfully")
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/users/profile-summary", methods=["GET"])
@permission_required('admin.users.view')
def api_users_profile_summary():
    """Return lightweight user profile summaries for AG Grid hover popups."""
    try:
        user_ids_raw = request.args.getlist('user_ids')
        if not user_ids_raw:
            user_ids_csv = (request.args.get('user_ids') or '').strip()
            if user_ids_csv:
                user_ids_raw = [part.strip() for part in user_ids_csv.split(',') if part.strip()]

        emails_raw = request.args.getlist('emails')
        if not emails_raw:
            emails_csv = (request.args.get('emails') or '').strip()
            if emails_csv:
                emails_raw = [part.strip() for part in emails_csv.split(',') if part.strip()]

        user_ids = []
        for value in user_ids_raw:
            with suppress(Exception):
                user_ids.append(int(value))

        emails = [str(email).strip().lower() for email in (emails_raw or []) if str(email).strip()]

        if not user_ids and not emails:
            return json_ok(status='success', profiles=[])

        query = User.query
        filters = []
        if user_ids:
            filters.append(User.id.in_(list(set(user_ids))))
        if emails:
            filters.append(db.func.lower(User.email).in_(list(set(emails))))
        if filters:
            from sqlalchemy import or_
            query = query.filter(or_(*filters))

        users = query.all()
        if not users:
            return json_ok(status='success', profiles=[])

        found_user_ids = [u.id for u in users]

        # Fetch last presence (most recent session activity) per user
        last_presence_by_user_id = {}
        with suppress(Exception):
            from sqlalchemy import func as sa_func
            last_presence_rows = (
                db.session.query(
                    UserSessionLog.user_id,
                    sa_func.max(UserSessionLog.last_activity).label('last_presence')
                )
                .filter(UserSessionLog.user_id.in_(found_user_ids))
                .group_by(UserSessionLog.user_id)
                .all()
            )
            for row in last_presence_rows:
                last_presence_by_user_id[row.user_id] = row.last_presence

        roles_by_user_id = {}
        with suppress(Exception):
            from app.models.rbac import RbacRole, RbacUserRole

            user_roles = RbacUserRole.query.filter(RbacUserRole.user_id.in_(found_user_ids)).all()
            role_ids = list({ur.role_id for ur in user_roles})
            roles = RbacRole.query.filter(RbacRole.id.in_(role_ids)).all() if role_ids else []
            roles_by_id = {r.id: r for r in roles}
            for ur in user_roles:
                role = roles_by_id.get(ur.role_id)
                if not role:
                    continue
                roles_by_user_id.setdefault(ur.user_id, []).append(role.name or role.code)

        all_permissions = UserEntityPermission.query.filter(
            UserEntityPermission.user_id.in_(found_user_ids)
        ).all()

        country_count_by_user_id = {}
        entity_counts_by_user_id = {}
        for perm in all_permissions:
            uid = int(perm.user_id)
            etype = str(perm.entity_type or '')
            if etype == 'country':
                country_count_by_user_id[uid] = country_count_by_user_id.get(uid, 0) + 1
            elif etype:
                bucket = entity_counts_by_user_id.setdefault(uid, {})
                bucket[etype] = int(bucket.get(etype, 0)) + 1

        profiles = []
        for user in users:
            profile_color = user.profile_color
            if not profile_color:
                with suppress(Exception):
                    profile_color = user.generate_profile_color()

            entity_counts = entity_counts_by_user_id.get(user.id, {})
            entity_summary_parts = []
            for key, value in sorted(entity_counts.items()):
                if int(value) > 0:
                    entity_summary_parts.append(f"{key.replace('_', ' ')}: {value}")

            last_presence_dt = last_presence_by_user_id.get(user.id)
            last_presence_iso = last_presence_dt.isoformat() + 'Z' if last_presence_dt else None

            profiles.append({
                'id': user.id,
                'name': user.name or '',
                'email': user.email or '',
                'title': user.title or '',
                'profile_color': profile_color or '#3B82F6',
                'active': bool(user.active),
                'last_presence': last_presence_iso,
                'rbac_roles': roles_by_user_id.get(user.id, []),
                'countries_count': int(country_count_by_user_id.get(user.id, 0)),
                'entity_counts': entity_counts,
                'entity_summary': ', '.join(entity_summary_parts),
            })

        return json_ok(status='success', profiles=profiles)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/api/users/access-requests/count", methods=["GET"])
@permission_required('admin.access_requests.view')
def api_access_requests_count():
    """API endpoint to get pending access requests count"""
    try:
        count = CountryAccessRequest.query.filter_by(status='pending').count()
        return json_ok(status='success', data={'count': count})
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/users/access-requests", methods=["GET"])
@permission_required('admin.access_requests.view')
def api_access_requests_list():
    """JSON list of pending and recently processed country access requests (mobile app)."""
    try:
        from sqlalchemy.orm import joinedload
        from app.services.app_settings_service import get_auto_approve_access_requests

        base = CountryAccessRequest.query.options(
            joinedload(CountryAccessRequest.user),
            joinedload(CountryAccessRequest.country),
            joinedload(CountryAccessRequest.processed_by),
        )
        pending_requests = (
            base.filter_by(status="pending")
            .order_by(CountryAccessRequest.created_at.asc())
            .all()
        )
        processed_requests = (
            base.filter(CountryAccessRequest.status.in_(["approved", "rejected"]))
            .order_by(
                CountryAccessRequest.processed_at.desc().nullslast(),
                CountryAccessRequest.created_at.desc(),
            )
            .limit(100)
            .all()
        )
        return json_ok(
            pending=[_country_access_request_to_dict(r) for r in pending_requests],
            processed=[_country_access_request_to_dict(r) for r in processed_requests],
            auto_approve_enabled=get_auto_approve_access_requests(),
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/users/access-requests/<int:request_id>/approve", methods=["POST"])
@permission_required('admin.access_requests.approve')
def api_approve_access_request(request_id):
    """Approve a country access request (JSON; same behaviour as the HTML POST)."""
    req = CountryAccessRequest.query.get_or_404(request_id)
    if req.status != "pending":
        return json_bad_request("This request has already been processed.")
    try:
        user = User.query.get_or_404(req.user_id)
        country = Country.query.get_or_404(req.country_id)
        user.add_entity_permission(entity_type="country", entity_id=country.id)
        req.status = "approved"
        req.processed_by_user_id = current_user.id
        req.processed_at = db.func.now()

        db.session.flush()

        log_admin_action(
            action_type="access_request_approve",
            description=f"Approved country access request for {user.email} to {country.name}",
            target_type="country_access_request",
            target_id=request_id,
            target_description=f"User: {user.email}, Country: {country.name}",
            new_values={
                "user_id": user.id,
                "user_email": user.email,
                "country_id": country.id,
                "country_name": country.name,
                "status": "approved",
            },
            risk_level="low",
        )

        db.session.flush()

        try:
            from app.services.notification.core import notify_user_added_to_country

            notify_user_added_to_country(user.id, country.id)
        except Exception as e:
            current_app.logger.error(
                f"Error sending user added to country notification: {e}", exc_info=True
            )

        return json_ok(request=_country_access_request_to_dict(req))
    except Exception as e:
        request_transaction_rollback()
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/users/access-requests/<int:request_id>/reject", methods=["POST"])
@permission_required('admin.access_requests.reject')
def api_reject_access_request(request_id):
    """Reject a country access request (JSON)."""
    req = CountryAccessRequest.query.get_or_404(request_id)
    if req.status != "pending":
        return json_bad_request("This request has already been processed.")
    try:
        user = User.query.get(req.user_id)
        country = Country.query.get(req.country_id)

        req.status = "rejected"
        req.processed_by_user_id = current_user.id
        req.processed_at = db.func.now()

        db.session.flush()

        log_admin_action(
            action_type="access_request_reject",
            description=(
                f"Rejected country access request for {user.email if user else 'unknown'} "
                f"to {country.name if country else 'unknown'}"
            ),
            target_type="country_access_request",
            target_id=request_id,
            target_description=(
                f"User: {user.email if user else 'unknown'}, "
                f"Country: {country.name if country else 'unknown'}"
            ),
            new_values={
                "user_id": req.user_id,
                "user_email": user.email if user else None,
                "country_id": req.country_id,
                "country_name": country.name if country else None,
                "status": "rejected",
            },
            risk_level="low",
        )

        db.session.flush()
        return json_ok(request=_country_access_request_to_dict(req))
    except Exception as e:
        request_transaction_rollback()
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/users/access-requests/approve-all", methods=["POST"])
@permission_required('admin.access_requests.approve')
def api_approve_all_access_requests():
    """Approve all pending country access requests (JSON)."""
    pending = CountryAccessRequest.query.filter_by(status="pending").all()
    if not pending:
        return json_ok(approved_count=0, message="No pending requests to approve.")

    approved_count = 0
    errors = 0
    for req in pending:
        try:
            user = User.query.get(req.user_id)
            country = Country.query.get(req.country_id)
            if not user or not country:
                errors += 1
                continue
            user.add_entity_permission(entity_type="country", entity_id=country.id)
            req.status = "approved"
            req.processed_by_user_id = current_user.id
            req.processed_at = db.func.now()
            db.session.flush()

            log_admin_action(
                action_type="access_request_approve",
                description=f"Bulk-approved country access request for {user.email} to {country.name}",
                target_type="country_access_request",
                target_id=req.id,
                target_description=f"User: {user.email}, Country: {country.name}",
                new_values={
                    "user_id": user.id,
                    "user_email": user.email,
                    "country_id": country.id,
                    "country_name": country.name,
                    "status": "approved",
                },
                risk_level="low",
            )
            db.session.flush()

            try:
                from app.services.notification.core import notify_user_added_to_country

                notify_user_added_to_country(user.id, country.id)
            except Exception as e:
                current_app.logger.debug("notify_user_added_to_country failed: %s", e)

            approved_count += 1
        except Exception:
            errors += 1

    return json_ok(approved_count=approved_count, errors=errors)


@bp.route("/api/users/<int:user_id>/deletion-preview", methods=["GET"])
@permission_required('admin.users.delete')
def api_user_deletion_preview(user_id):
    """API endpoint to get user deletion preview in JSON format"""
    from app.services.authorization_service import AuthorizationService
    if not current_user.is_authenticated or not AuthorizationService.is_system_manager(current_user):
        return json_forbidden('Only system managers can delete users.')
    user = User.query.get_or_404(user_id)
    try:
        preview = _get_user_deletion_preview(user)
        return json_ok(status='success', data=preview)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/users/<int:user_id>/activate", methods=["POST"])
@permission_required('admin.users.deactivate')
def api_activate_user(user_id):
    """API endpoint to activate a user"""
    try:
        from app.services.authorization_service import AuthorizationService
        user = User.query.get_or_404(user_id)
        if user.id == current_user.id:
            return json_bad_request('You cannot activate your own account')
        if (not AuthorizationService.is_system_manager(current_user)) and AuthorizationService.is_admin(user):
            return json_forbidden('Only a System Manager can modify an admin user')
        old_active = bool(getattr(user, 'active', True))
        user.active = True
        user.deactivated_at = None

        db.session.flush()
        log_admin_action(
            action_type='user_update',
            description=f'Activated user: {user.email}',
            target_type='user',
            target_id=user.id,
            target_description=f'{user.name or user.email}',
            old_values={'active': old_active},
            new_values={'active': True},
            risk_level='medium'
        )
        db.session.flush()
        return json_ok(status='success', message='User activated successfully')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/api/users/<int:user_id>/deactivate", methods=["POST"])
@permission_required('admin.users.deactivate')
def api_deactivate_user(user_id):
    """API endpoint to deactivate a user"""
    try:
        from app.services.authorization_service import AuthorizationService
        user = User.query.get_or_404(user_id)
        if user.id == current_user.id:
            return json_bad_request('You cannot deactivate your own account')
        if (not AuthorizationService.is_system_manager(current_user)) and AuthorizationService.is_admin(user):
            return json_forbidden('Only a System Manager can modify an admin user')
        old_active = bool(getattr(user, 'active', True))
        user.active = False
        user.deactivated_at = db.func.now()

        db.session.flush()
        log_admin_action(
            action_type='user_update',
            description=f'Deactivated user: {user.email}',
            target_type='user',
            target_id=user.id,
            target_description=f'{user.name or user.email}',
            old_values={'active': old_active},
            new_values={'active': False},
            risk_level='medium'
        )
        db.session.flush()
        return json_ok(status='success', message='User deactivated successfully')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)
