# Security monitoring and alerting utilities
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from flask import request, current_app, g, has_request_context
from flask_login import current_user
from app.models import SecurityEvent, AdminActionLog
from app import db
from app.utils.datetime_helpers import utcnow

class SecurityMonitor:
    """Security monitoring and alerting system."""

    # Security thresholds
    THRESHOLDS = {
        'failed_logins_per_hour': 10,
        'failed_logins_per_day': 50,
        'api_errors_per_hour': 100,
        'suspicious_requests_per_hour': 20,
        'admin_actions_per_hour': 100
    }

    # Alert severity levels
    SEVERITY_LEVELS = {
        'low': 1,
        'medium': 2,
        'high': 3,
        'critical': 4
    }

    @staticmethod
    def log_security_event(event_type: str, severity: str, description: str,
                          context_data: Optional[Dict] = None, user_id: Optional[int] = None,
                          notify_admins: bool = True):
        """
        Log a security event.

        Args:
            event_type: Type of security event
            severity: Severity level (low, medium, high, critical)
            description: Event description
            context_data: Additional context data
            user_id: Associated user ID
            notify_admins: If True, send email for high/critical (set False to avoid loops when email itself fails)
        """
        try:
            client_info = SecurityMonitor._get_client_info()

            if user_id is not None:
                resolved_user_id = user_id
            elif has_request_context():
                try:
                    resolved_user_id = current_user.id if current_user.is_authenticated else None
                except Exception:
                    resolved_user_id = None
            else:
                resolved_user_id = None

            security_event = SecurityEvent(
                user_id=resolved_user_id,
                event_type=event_type,
                severity=severity,
                description=description,
                ip_address=client_info['ip_address'],
                user_agent=client_info['user_agent'],
                context_data=context_data or {}
            )

            db.session.add(security_event)
            db.session.commit()

            # Send alert if severity is high or critical
            if notify_admins and severity in ['high', 'critical']:
                SecurityMonitor._send_security_alert(security_event)

        except Exception as e:
            current_app.logger.error(f"Failed to log security event: {e}")
            db.session.rollback()

    @staticmethod
    def _get_client_info() -> Dict[str, Any]:
        """Get client information for logging."""
        if has_request_context():
            return {
                'ip_address': request.remote_addr or 'unknown',
                'user_agent': request.user_agent.string if request.user_agent else 'unknown',
                'referrer': request.referrer or 'unknown',
                'method': request.method,
                'endpoint': request.endpoint or 'unknown',
                'url': request.url or 'unknown'
            }
        return {
            'ip_address': 'system',
            'user_agent': 'unknown',
            'referrer': 'unknown',
            'method': 'N/A',
            'endpoint': 'N/A',
            'url': 'N/A',
        }

    @staticmethod
    def _send_security_alert(event: SecurityEvent):
        """Send security alert for high-severity events."""
        try:
            # Log to application log with high priority
            current_app.logger.critical(
                f"SECURITY ALERT: {event.event_type} - {event.severity.upper()} - {event.description} "
                f"(IP: {event.ip_address}, User: {event.user_id})"
            )

            # Send email alert to administrators for high/critical severity events
            from app.services.email.service import send_security_alert

            send_security_alert(
                event_type=event.event_type,
                severity=event.severity,
                description=event.description,
                ip_address=event.ip_address,
                user_id=event.user_id,
                timestamp=event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp)
            )

        except Exception as e:
            current_app.logger.error(f"Failed to send security alert: {e}")

    @staticmethod
    def check_suspicious_activity():
        """Check for suspicious patterns and create alerts."""
        try:
            # Check for multiple failed logins
            SecurityMonitor._check_failed_logins()

            # Check for suspicious request patterns
            SecurityMonitor._check_suspicious_requests()

            # Check for unusual admin activity
            SecurityMonitor._check_admin_activity()

            # Check for potential brute force attacks
            SecurityMonitor._check_brute_force_attempts()

        except Exception as e:
            current_app.logger.error(f"Security monitoring check failed: {e}")

    @staticmethod
    def _check_failed_logins():
        """Check for excessive failed login attempts."""
        try:
            # Check failed logins in the last hour
            one_hour_ago = utcnow() - timedelta(hours=1)

            failed_logins = SecurityEvent.query.filter(
                SecurityEvent.event_type == 'multiple_failed_logins',
                SecurityEvent.timestamp >= one_hour_ago,
                SecurityEvent.is_resolved == False
            ).count()

            if failed_logins >= SecurityMonitor.THRESHOLDS['failed_logins_per_hour']:
                SecurityMonitor.log_security_event(
                    event_type='excessive_failed_logins',
                    severity='high',
                    description=f'Excessive failed login attempts detected: {failed_logins} in the last hour',
                    context_data={'failed_count': failed_logins}
                )

        except Exception as e:
            current_app.logger.error(f"Failed login check error: {e}")

    @staticmethod
    def _check_suspicious_requests():
        """Check for suspicious request patterns."""
        try:
            # Check for requests to non-existent endpoints
            # This would require request logging - implement if needed

            # Check for requests with suspicious user agents
            suspicious_agents = [
                'sqlmap', 'nikto', 'nmap', 'masscan', 'zap', 'burp'
            ]

            # This is a simplified check - in production, you'd analyze actual request logs
            user_agent = request.user_agent.string.lower() if request.user_agent else ''

            for agent in suspicious_agents:
                if agent in user_agent:
                    SecurityMonitor.log_security_event(
                        event_type='suspicious_user_agent',
                        severity='medium',
                        description=f'Suspicious user agent detected: {user_agent}',
                        context_data={'user_agent': user_agent}
                    )
                    break

        except Exception as e:
            current_app.logger.error(f"Suspicious request check error: {e}")

    @staticmethod
    def _check_admin_activity():
        """Check for unusual admin activity patterns."""
        try:
            from app.services.authorization_service import AuthorizationService
            if current_user.is_authenticated and AuthorizationService.is_admin(current_user):
                # Check for high-risk admin actions in the last hour
                one_hour_ago = utcnow() - timedelta(hours=1)

                admin_actions = AdminActionLog.query.filter(
                    AdminActionLog.admin_user_id == current_user.id,
                    AdminActionLog.timestamp >= one_hour_ago,
                    AdminActionLog.risk_level.in_(['high', 'critical'])
                ).count()

                if admin_actions >= 10:  # 10 high-risk actions per hour
                    SecurityMonitor.log_security_event(
                        event_type='excessive_admin_activity',
                        severity='medium',
                        description=f'Excessive high-risk admin actions: {admin_actions} in the last hour',
                        user_id=current_user.id,
                        context_data={'action_count': admin_actions}
                    )

        except Exception as e:
            current_app.logger.error(f"Admin activity check error: {e}")

    @staticmethod
    def _check_brute_force_attempts():
        """Check for potential brute force attacks."""
        try:
            # Check for rapid sequential requests from the same IP
            # This would require request logging - implement based on your needs

            # For now, we'll check based on failed logins
            ip_address = request.remote_addr
            if ip_address:
                one_hour_ago = utcnow() - timedelta(hours=1)

                failed_attempts = SecurityEvent.query.filter(
                    SecurityEvent.event_type == 'multiple_failed_logins',
                    SecurityEvent.ip_address == ip_address,
                    SecurityEvent.timestamp >= one_hour_ago
                ).count()

                if failed_attempts >= 20:  # 20 failed attempts per hour from same IP
                    SecurityMonitor.log_security_event(
                        event_type='potential_brute_force',
                        severity='high',
                        description=f'Potential brute force attack from IP: {ip_address}',
                        context_data={
                            'ip_address': ip_address,
                            'failed_attempts': failed_attempts
                        }
                    )

        except Exception as e:
            current_app.logger.error(f"Brute force check error: {e}")

    @staticmethod
    def get_security_dashboard_data(days: int = 7) -> Dict[str, Any]:
        """Get security dashboard data for the specified period."""
        try:
            start_date = utcnow() - timedelta(days=days)

            # Get security events by severity
            events_by_severity = db.session.query(
                SecurityEvent.severity,
                db.func.count(SecurityEvent.id)
            ).filter(
                SecurityEvent.timestamp >= start_date
            ).group_by(SecurityEvent.severity).all()

            # Get security events by type
            events_by_type = db.session.query(
                SecurityEvent.event_type,
                db.func.count(SecurityEvent.id)
            ).filter(
                SecurityEvent.timestamp >= start_date
            ).group_by(SecurityEvent.event_type).all()

            # Get unresolved events
            unresolved_count = SecurityEvent.query.filter(
                SecurityEvent.is_resolved == False
            ).count()

            return {
                'events_by_severity': dict(events_by_severity),
                'events_by_type': dict(events_by_type),
                'unresolved_count': unresolved_count,
                'period_days': days
            }

        except Exception as e:
            current_app.logger.error(f"Failed to get security dashboard data: {e}")
            return {
                'events_by_severity': {},
                'events_by_type': {},
                'unresolved_count': 0,
                'period_days': days
            }

# Global security monitor instance
security_monitor = SecurityMonitor()

# Convenience functions
def log_security_event(event_type: str, severity: str, description: str,
                      context_data: Optional[Dict] = None, user_id: Optional[int] = None,
                      notify_admins: bool = True):
    """Log a security event."""
    security_monitor.log_security_event(
        event_type, severity, description, context_data, user_id=user_id, notify_admins=notify_admins
    )

def check_security_thresholds():
    """Check security thresholds and create alerts."""
    security_monitor.check_suspicious_activity()

def get_security_metrics(days: int = 7) -> Dict[str, Any]:
    """Get security metrics for dashboard."""
    return security_monitor.get_security_dashboard_data(days)
