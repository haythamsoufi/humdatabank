# Backoffice/app/routes/api/mobile/devices.py
"""Device management routes: push-notification registration, heartbeat."""

from flask import request, current_app
from flask_login import current_user

from app.utils.api_helpers import get_json_safe
from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import mobile_ok, mobile_bad_request
from app.routes.api.mobile import mobile_bp


@mobile_bp.route('/devices/register', methods=['POST'])
@mobile_auth_required
def register_device():
    """Register a device for push notifications."""
    from app.services.notification.push import PushNotificationService
    data = get_json_safe()
    device_token = data.get('device_token')
    platform = data.get('platform')

    if not device_token:
        return mobile_bad_request('device_token is required')
    if not platform or platform not in ('ios', 'android'):
        return mobile_bad_request('platform must be "ios" or "android"')

    ip_address = (
        request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
        if request.headers.getlist("X-Forwarded-For")
        else request.remote_addr
    )

    result = PushNotificationService.register_device(
        user_id=current_user.id,
        device_token=device_token,
        platform=platform,
        app_version=data.get('app_version'),
        device_model=data.get('device_model'),
        device_name=data.get('device_name'),
        os_version=data.get('os_version'),
        ip_address=ip_address,
        timezone=data.get('timezone'),
    )
    if result.get('success'):
        if result.get('message') == 'Device registered':
            from app.services.user_analytics_service import log_user_activity
            log_user_activity(
                activity_type='device_registered',
                description='New device registered for push notifications',
                context_data={
                    'device_id': result.get('device_id'),
                    'platform': platform,
                    'device_model': data.get('device_model'),
                },
            )
        return mobile_ok(data=result)
    return mobile_bad_request(result.get('error', 'Registration failed'))


@mobile_bp.route('/devices/unregister', methods=['POST'])
@mobile_auth_required
def unregister_device():
    """Unregister a device for push notifications."""
    from app.services.notification.push import PushNotificationService
    data = get_json_safe()
    device_token = data.get('device_token')
    if not device_token:
        return mobile_bad_request('device_token is required')

    result = PushNotificationService.unregister_device(
        user_id=current_user.id, device_token=device_token
    )
    if result.get('success'):
        return mobile_ok(data=result)
    return mobile_bad_request(result.get('error', 'Unregistration failed'))


@mobile_bp.route('/devices/heartbeat', methods=['POST'])
@mobile_auth_required
def device_heartbeat():
    """Lightweight heartbeat to update device last_active_at."""
    from app.services.notification.push import PushNotificationService
    from app.services.user_analytics_service import _update_session_activity_explicit
    from flask import session as flask_session, g

    data = get_json_safe()
    device_token = data.get('device_token') or request.headers.get('X-Device-Token')
    if not device_token:
        return mobile_bad_request('device_token is required')

    updated = PushNotificationService.update_device_activity(
        user_id=current_user.id, device_token=device_token
    )

    session_id = flask_session.get('session_id') or getattr(g, '_mobile_jwt_sid', None)
    if session_id:
        _update_session_activity_explicit(session_id, 'heartbeat')

    return mobile_ok(data={'updated': updated})
