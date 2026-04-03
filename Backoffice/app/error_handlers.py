"""HTTP error handlers for the Flask application."""

from contextlib import suppress
from flask import render_template, request, session, current_app
from flask_login import current_user

from app.utils.api_responses import json_bad_request, json_error, json_forbidden, json_not_found, json_server_error
from app.utils.csp_nonce import get_style_nonce
from app.utils.datetime_helpers import utcnow
from app.utils.request_utils import is_json_request


def register_error_handlers(app):
    """Register all HTTP error handlers on the Flask app."""

    @app.errorhandler(400)
    def bad_request(error):
        if is_json_request():
            return json_bad_request(
                'The request was invalid or malformed.',
                success=False, error='Bad Request', error_code=400,
            )
        return render_template('errors/error.html',
                               error_code=400, error_title='Bad Request',
                               error_message='The request was invalid or malformed. Please check your input and try again.',
                               error_details=str(error) if app.config.get('DEBUG') else None,
                               current_user=current_user, style_nonce=get_style_nonce()), 400

    @app.errorhandler(401)
    def unauthorized(error):
        if is_json_request():
            return json_error(
                'Authentication required to access this resource.',
                401, success=False, error='Unauthorized', error_code=401,
            )
        return render_template('errors/error.html',
                               error_code=401, error_title='Unauthorized',
                               error_message='You need to be logged in to access this page. Please log in and try again.',
                               error_details=str(error) if app.config.get('DEBUG') else None,
                               current_user=current_user, style_nonce=get_style_nonce()), 401

    @app.errorhandler(403)
    def forbidden(error):
        if not app.config.get('DEBUG'):
            try:
                from app.utils.security_monitoring import SecurityMonitor

                user_id = None
                if getattr(current_user, 'is_authenticated', False):
                    raw_user_id = session.get('_user_id')
                    if raw_user_id is None:
                        with suppress(Exception):
                            raw_user_id = current_user.get_id()
                    with suppress(Exception):
                        user_id = int(raw_user_id) if raw_user_id is not None else None
                    if user_id is None:
                        with suppress(Exception):
                            user_id = getattr(current_user, 'id', None)

                SecurityMonitor.log_security_event(
                    event_type='http_403_forbidden',
                    severity='medium',
                    description=f'Access forbidden: {request.method} {request.path}'[:500],
                    context_data={
                        'url': request.url[:2000] if request else None,
                        'endpoint': request.endpoint if request else None,
                        'method': request.method if request else None,
                    },
                    user_id=user_id,
                )
            except Exception:
                app.logger.debug('Failed to log 403 security event', exc_info=True)

        if is_json_request():
            return json_forbidden(
                'You do not have permission to access this resource. If you have been on this page a long time, refresh the page and try again.',
                success=False, error='Forbidden', error_code=403,
            )
        return render_template('errors/error.html',
                               error_code=403, error_title='Access Forbidden',
                               error_message='You do not have permission to access this resource. Please contact an administrator if you believe this is an error.',
                               error_details=str(error) if app.config.get('DEBUG') else None,
                               current_user=current_user, style_nonce=get_style_nonce()), 403

    @app.errorhandler(404)
    def not_found(error):
        if is_json_request():
            return json_not_found(
                'The requested resource could not be found.',
                success=False, error='Not Found', error_code=404,
            )
        return render_template('errors/error.html',
                               error_code=404, error_title='Page Not Found',
                               error_message='The page you are looking for does not exist. It may have been moved or deleted.',
                               error_details=str(error) if app.config.get('DEBUG') else None,
                               current_user=current_user, style_nonce=get_style_nonce()), 404

    @app.errorhandler(500)
    def internal_error(error):
        import traceback

        error_traceback = traceback.format_exc()
        app.logger.error(f'Server Error: {error}', exc_info=True)

        if not app.config.get('DEBUG'):
            try:
                from app.utils.security_monitoring import SecurityMonitor
                from app.utils.email_service import send_security_alert

                error_message = str(error)
                error_url = request.url if request else 'Unknown URL'
                user_id = None
                if getattr(current_user, 'is_authenticated', False):
                    raw_user_id = session.get('_user_id')
                    if raw_user_id is None:
                        with suppress(Exception):
                            raw_user_id = current_user.get_id()
                    with suppress(Exception):
                        user_id = int(raw_user_id) if raw_user_id is not None else None
                    if user_id is None:
                        with suppress(Exception):
                            user_id = getattr(current_user, 'id', None)
                ip_address = request.remote_addr if request else 'Unknown'

                SecurityMonitor.log_security_event(
                    event_type='internal_server_error',
                    severity='critical',
                    description=f'Internal Server Error: {error_message[:200]}',
                    context_data={
                        'url': error_url,
                        'endpoint': request.endpoint if request else None,
                        'method': request.method if request else None,
                        'traceback': error_traceback[:1000]
                    },
                    user_id=user_id
                )

                try:
                    from app.models import User
                    try:
                        from app.models.rbac import RbacUserRole, RbacRole
                        managers = (
                            User.query.join(RbacUserRole, User.id == RbacUserRole.user_id)
                            .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                            .filter(RbacRole.code == "system_manager")
                            .filter(User.active.is_(True))
                            .all()
                        )
                    except Exception as e:
                        app.logger.debug("RBAC join for system managers failed, using empty list: %s", e)
                        managers = User.query.filter(User.active.is_(True)).limit(0).all()

                    if managers:
                        manager_emails = [m.email for m in managers if m.email]
                        if manager_emails:
                            success = send_security_alert(
                                event_type='internal_server_error',
                                severity='critical',
                                description=f'Internal Server Error occurred: {error_message[:200]}',
                                ip_address=ip_address,
                                user_id=user_id,
                                timestamp=utcnow().isoformat(),
                                recipients=manager_emails
                            )
                            if success:
                                app.logger.info(f"Security alert sent to {len(manager_emails)} system managers: {', '.join(manager_emails)}")
                            else:
                                app.logger.error(f"Failed to send security alert to system managers: {manager_emails}")
                        else:
                            app.logger.warning("System managers found but none have email addresses configured")
                    else:
                        app.logger.warning("No active system managers found in database for error notification")
                except Exception as email_error:
                    app.logger.error(f"Failed to send error notification email: {email_error}")

            except Exception as notify_error:
                app.logger.error(f"Failed to notify system managers of error: {notify_error}")

        if is_json_request():
            return json_server_error(
                'An unexpected error occurred. Please try again later.',
                success=False, error='Internal Server Error', error_code=500,
            )
        return render_template('errors/error.html',
                               error_code=500, error_title='Internal Server Error',
                               error_message='An unexpected error occurred on our end. We have been notified and are working to fix it. Please try again later.',
                               error_details=str(error) if app.config.get('DEBUG') else None,
                               current_user=current_user, style_nonce=get_style_nonce()), 500

    @app.errorhandler(502)
    def bad_gateway(error):
        if is_json_request():
            return json_error(
                'The server received an invalid response from an upstream server.',
                502, success=False, error='Bad Gateway', error_code=502,
            )
        return render_template('errors/error.html',
                               error_code=502, error_title='Bad Gateway',
                               error_message='The server received an invalid response. Please try again in a few moments.',
                               error_details=str(error) if app.config.get('DEBUG') else None,
                               current_user=current_user, style_nonce=get_style_nonce()), 502

    @app.errorhandler(503)
    def service_unavailable(error):
        if is_json_request():
            return json_error(
                'The service is temporarily unavailable. Please try again later.',
                503, success=False, error='Service Unavailable', error_code=503,
            )
        return render_template('errors/error.html',
                               error_code=503, error_title='Service Unavailable',
                               error_message='The service is temporarily unavailable due to maintenance or high load. Please try again later.',
                               error_details=str(error) if app.config.get('DEBUG') else None,
                               current_user=current_user, style_nonce=get_style_nonce()), 503
