from flask import request, current_app
from flask_login import login_required, current_user
from app.models import db, User, UserSessionLog
from app.models.core import Country, UserEntityPermission
from app.models.rbac import RbacUserRole, RbacRole
from sqlalchemy import or_, func
from contextlib import suppress

from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_ok, json_server_error
from app.utils.error_handling import handle_json_view_exception
from app.utils.profile_summary_payload import (
    role_badge_key_from_rbac_codes,
    collect_arg_strings,
    parse_uuid_list,
    parse_int_user_ids,
    profile_summary_scope_fields,
)

from app.routes.main import bp


@bp.route("/api/users/profile-summary", methods=["GET"])
@login_required
def api_users_profile_summary():
    """Return lightweight user profile summaries for hover tooltips (dashboard/non-admin pages)."""
    try:
        user_ids_raw = collect_arg_strings(request.args, "user_ids")
        external_raw = collect_arg_strings(request.args, "external_ids")
        emails_raw = collect_arg_strings(request.args, "emails")

        external_uuids = parse_uuid_list(external_raw)
        emails = [str(e).strip().lower() for e in emails_raw if str(e).strip()]
        parsed_user_ids = parse_int_user_ids(user_ids_raw)

        from app.services.authorization_service import AuthorizationService
        is_privileged = bool(
            AuthorizationService.is_system_manager(current_user) or
            AuthorizationService.has_rbac_permission(current_user, "admin.users.view")
        )

        # Non-privileged callers must not use arbitrary sequential ids (enumeration).
        # Allow integer id only for the current user (self).
        if is_privileged:
            effective_user_ids = parsed_user_ids
        else:
            effective_user_ids = [i for i in parsed_user_ids if i == int(current_user.id)]

        if not effective_user_ids and not external_uuids and not emails:
            return json_ok(status='success', profiles=[])

        query = User.query
        filters = []
        if effective_user_ids:
            filters.append(User.id.in_(list(set(effective_user_ids))))
        if external_uuids:
            filters.append(User.external_id.in_(list(set(external_uuids))))
        if emails:
            filters.append(func.lower(User.email).in_(list(set(emails))))
        query = query.filter(or_(*filters))

        users = query.all()
        if not users:
            return json_ok(status='success', profiles=[])

        # Non-admin users can only fetch profile summaries for users sharing at least one entity scope,
        # plus themselves. Admin/system-manager users are unrestricted.
        if not is_privileged:
            visible_user_ids = {int(current_user.id)}
            requester_scopes = {
                (str(p.entity_type), int(p.entity_id))
                for p in UserEntityPermission.query.filter_by(user_id=current_user.id).all()
                if getattr(p, "entity_type", None) and getattr(p, "entity_id", None) is not None
            }
            if requester_scopes:
                all_candidate_perms = UserEntityPermission.query.filter(
                    UserEntityPermission.user_id.in_([u.id for u in users])
                ).all()
                for perm in all_candidate_perms:
                    scope_key = (str(perm.entity_type), int(perm.entity_id))
                    if scope_key in requester_scopes:
                        visible_user_ids.add(int(perm.user_id))
            users = [u for u in users if int(u.id) in visible_user_ids]
            if not users:
                return json_ok(status='success', profiles=[])

        found_user_ids = [u.id for u in users]

        # Fetch last presence (most recent session activity) per user
        last_presence_by_user_id = {}
        with suppress(Exception):
            last_presence_rows = (
                db.session.query(
                    UserSessionLog.user_id,
                    func.max(UserSessionLog.last_activity).label('last_presence')
                )
                .filter(UserSessionLog.user_id.in_(found_user_ids))
                .group_by(UserSessionLog.user_id)
                .all()
            )
            for row in last_presence_rows:
                last_presence_by_user_id[row.user_id] = row.last_presence

        role_codes_by_user_id = {}
        with suppress(Exception):
            user_roles = RbacUserRole.query.filter(RbacUserRole.user_id.in_(found_user_ids)).all()
            role_ids = list({ur.role_id for ur in user_roles})
            roles = RbacRole.query.filter(RbacRole.id.in_(role_ids)).all() if role_ids else []
            roles_by_id = {r.id: r for r in roles}
            for ur in user_roles:
                role = roles_by_id.get(ur.role_id)
                if not role:
                    continue
                role_code = (role.code or '').strip()
                if role_code:
                    role_codes_by_user_id.setdefault(ur.user_id, []).append(role_code)

        all_permissions = UserEntityPermission.query.filter(
            UserEntityPermission.user_id.in_(found_user_ids)
        ).all()

        country_ids_by_user_id: dict[int, set[int]] = {}
        entity_counts_by_user_id: dict[int, dict[str, int]] = {}
        for perm in all_permissions:
            uid = int(perm.user_id)
            etype = str(perm.entity_type or '')
            if etype == 'country':
                country_ids_by_user_id.setdefault(uid, set()).add(int(perm.entity_id))
            elif etype:
                bucket = entity_counts_by_user_id.setdefault(uid, {})
                bucket[etype] = int(bucket.get(etype, 0)) + 1

        all_countries = Country.query.all()
        country_id_to_name_region = {
            int(c.id): (str(c.name or ''), str(c.region or '')) for c in all_countries
        }
        region_to_all_country_ids: dict[str, set[int]] = {}
        for c in all_countries:
            r = str(c.region or '')
            region_to_all_country_ids.setdefault(r, set()).add(int(c.id))

        profiles = []
        for user in users:
            profile_color = user.profile_color
            if not profile_color:
                with suppress(Exception):
                    profile_color = user.generate_profile_color()

            last_presence_dt = last_presence_by_user_id.get(user.id)
            last_presence_iso = last_presence_dt.isoformat() + 'Z' if last_presence_dt else None

            rb_key = role_badge_key_from_rbac_codes(
                role_codes_by_user_id.get(user.id, [])
            )
            row = {
                'external_id': str(user.external_id) if user.external_id else None,
                'name': user.name or '',
                'email': user.email or '',
                'title': user.title or '',
                'profile_color': profile_color or '#3B82F6',
                'active': bool(user.active),
                'last_presence': last_presence_iso,
                'role_badge_key': rb_key,
            }
            row.update(
                profile_summary_scope_fields(
                    rb_key,
                    country_ids_by_user_id.get(user.id, set()),
                    dict(entity_counts_by_user_id.get(user.id, {})),
                    country_id_to_name_region=country_id_to_name_region,
                    region_to_all_country_ids=region_to_all_country_ids,
                )
            )
            if is_privileged:
                row['id'] = user.id
            profiles.append(row)

        return json_ok(status='success', profiles=profiles)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/notifications", methods=["GET"])
@login_required
def api_get_notifications():
    """Get notifications for the current user via API"""
    from app.services.notification.service import NotificationService

    try:
        # Get notifications
        notifications_data, total_count = NotificationService.get_user_notifications(
            user_id=current_user.id,
            unread_only=False,
            notification_type=None,
            date_from=None,
            date_to=None,
            include_archived=False,
            archived_only=False,
            limit=20,
            offset=0
        )

        unread_count = NotificationService.get_unread_count(current_user.id)

        return json_ok(
            success=True,
            notifications=notifications_data,
            unread_count=unread_count,
            total_count=total_count
        )

    except Exception as e:
        current_app.logger.error(f"Error getting notifications: {e}")
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route("/api/notifications/count", methods=["GET"])
@login_required
def api_get_notifications_count():
    """Get unread notifications count for the current user"""
    from app.services.notification.service import NotificationService

    try:
        unread_count = NotificationService.get_unread_count(current_user.id)

        return json_ok(success=True, unread_count=unread_count)

    except Exception as e:
        current_app.logger.error(f"Error getting notifications count: {e}")
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route("/api/notifications/websocket-status", methods=["GET"])
def api_websocket_status_public():
    """
    Public endpoint to check if WebSocket is enabled on the server.
    No authentication required - useful for quick verification after deployment.

    Returns basic WebSocket status without sensitive diagnostics.
    """
    import os

    websocket_enabled = bool(current_app.config.get('WEBSOCKET_ENABLED', True))

    # Check if flask-sock is available
    try:
        import flask_sock  # type: ignore
        flask_sock_available = True
    except Exception as e:
        current_app.logger.debug("flask_sock import failed: %s", e)
        flask_sock_available = False

    return json_ok(
        success=True,
        enabled=websocket_enabled,
        websocket_enabled=websocket_enabled,
        websocket_endpoint='/api/notifications/ws',
        flask_sock_available=flask_sock_available,
        message='WebSocket status check - use /notifications/api/stream/status for full diagnostics (login required)'
    )
