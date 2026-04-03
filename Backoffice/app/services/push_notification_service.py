# ========== Push Notification Service ==========
from app.utils.datetime_helpers import utcnow
"""
Push notification service for sending notifications via FCM V1 API (Firebase Cloud Messaging).

This service handles:
- Sending push notifications to Android and iOS devices using FCM V1 API
- Managing device tokens
- Handling push notification failures
- OAuth2 authentication with service account
"""

import os
import json
import requests
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from flask import current_app
from app import db
from app.models import UserDevice, User

logger = logging.getLogger(__name__)

try:
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False
    logger.warning(
        "google-auth not installed. Install with: pip install google-auth "
        "google-auth-oauthlib google-auth-httplib2"
    )


class PushNotificationService:
    """Service for sending push notifications via FCM V1 API."""

    _credentials = None
    _access_token = None
    _token_expiry = None

    @staticmethod
    def _get_access_token() -> Optional[str]:
        """
        Get OAuth2 access token for FCM V1 API.
        Uses service account JSON file for authentication.

        Returns:
            Access token string or None if authentication fails
        """
        if not GOOGLE_AUTH_AVAILABLE:
            current_app.logger.error("google-auth library not available")
            return None

        try:
            # Get service account JSON path from environment
            service_account_path = os.environ.get('FCM_SERVICE_ACCOUNT_PATH')
            if not service_account_path:
                current_app.logger.error("FCM_SERVICE_ACCOUNT_PATH not configured")
                return None

            # Check if token is still valid
            if (PushNotificationService._access_token and
                PushNotificationService._token_expiry and
                utcnow() < PushNotificationService._token_expiry):
                return PushNotificationService._access_token

            # Load credentials from service account JSON
            if not PushNotificationService._credentials:
                if not os.path.exists(service_account_path):
                    current_app.logger.error(f"Service account file not found: {service_account_path}")
                    return None

                with open(service_account_path, 'r') as f:
                    service_account_info = json.load(f)

                # Create credentials
                credentials = service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=['https://www.googleapis.com/auth/firebase.messaging']
                )
                PushNotificationService._credentials = credentials

            # Refresh token if needed
            if not PushNotificationService._credentials.valid:
                PushNotificationService._credentials.refresh(Request())

            # Get access token
            PushNotificationService._access_token = PushNotificationService._credentials.token
            # Token expires in 1 hour, refresh 5 minutes before expiry
            from datetime import timedelta
            PushNotificationService._token_expiry = utcnow() + timedelta(hours=1, minutes=-5)

            return PushNotificationService._access_token

        except Exception as e:
            current_app.logger.error(f"Error getting access token: {str(e)}")
            return None

    @staticmethod
    def send_push_notification(
        user_id: int,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        priority: str = 'normal'
    ) -> Dict[str, Any]:
        """
        Send push notification to all devices registered for a user.

        Args:
            user_id: ID of the user to send notification to
            title: Notification title
            body: Notification body/message
            data: Optional data payload (dict)
            priority: Priority level ('normal' or 'high')

        Returns:
            Dict with success status and results
        """
        try:
            # Get all active devices for the user (exclude logged-out devices)
            devices = UserDevice.query.filter_by(
                user_id=user_id
            ).filter(
                UserDevice.logged_out_at.is_(None)
            ).all()

            if not devices:
                current_app.logger.debug(f"No active devices found for user {user_id}")
                return {
                    'success': False,
                    'error': 'No active devices registered. Notification was created in the database but push notification cannot be sent.',
                    'devices_count': 0,
                    'notification_created': True  # Indicate that notification record was created
                }

            # Get project ID from service account or environment
            project_id = os.environ.get('FCM_PROJECT_ID')
            if not project_id:
                # Try to get from service account file
                service_account_path = os.environ.get('FCM_SERVICE_ACCOUNT_PATH')
                if service_account_path and os.path.exists(service_account_path):
                    with open(service_account_path, 'r') as f:
                        service_account_info = json.load(f)
                        project_id = service_account_info.get('project_id')

            if not project_id:
                current_app.logger.warning("FCM_PROJECT_ID not configured, skipping push notification")
                return {
                    'success': False,
                    'error': 'FCM not configured',
                    'devices_count': len(devices)
                }

            results = []
            success_count = 0
            failure_count = 0

            # Send to each device
            for device in devices:
                result = PushNotificationService._send_to_device(
                    device.device_token,
                    device.platform,
                    title,
                    body,
                    data,
                    priority,
                    project_id
                )
                results.append(result)

                if result['success']:
                    success_count += 1
                    # Update last_active_at and reset failure count on success
                    device.last_active_at = utcnow()
                    device.consecutive_failures = 0
                else:
                    failure_count += 1
                    # Track consecutive failures
                    device.consecutive_failures = getattr(device, 'consecutive_failures', 0) + 1

                    error_code = result.get('error_code', '')
                    # Only remove device after 3+ consecutive failures (prevents removal on transient errors)
                    if device.consecutive_failures >= 3 and ('NOT_FOUND' in error_code or 'INVALID_ARGUMENT' in error_code):
                        current_app.logger.warning(
                            f"Removing invalid device token after {device.consecutive_failures} consecutive failures: "
                            f"{device.device_token[:20]}..."
                        )
                        db.session.delete(device)
                    else:
                        # Save failure count for tracking
                        current_app.logger.debug(
                            f"Push notification failed for device {device.id} "
                            f"(consecutive failures: {device.consecutive_failures}/3)"
                        )

            db.session.commit()

            return {
                'success': success_count > 0,
                'devices_count': len(devices),
                'success_count': success_count,
                'failure_count': failure_count,
                'results': results
            }

        except Exception as e:
            current_app.logger.error(f"Error sending push notification: {str(e)}")
            db.session.rollback()
            return {
                'success': False,
                'error': 'An error occurred while sending the notification.'
            }

    @staticmethod
    def _send_to_device(
        device_token: str,
        platform: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        priority: str = 'normal',
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send push notification to a single device via FCM V1 API.

        Args:
            device_token: FCM device token
            platform: Platform ('ios' or 'android')
            title: Notification title
            body: Notification body
            data: Optional data payload
            priority: Priority level
            project_id: Firebase project ID

        Returns:
            Dict with success status and error info if failed
        """
        try:
            if not project_id:
                project_id = os.environ.get('FCM_PROJECT_ID')
                if not project_id:
                    return {
                        'success': False,
                        'error': 'FCM_PROJECT_ID not configured'
                    }

            # Get access token
            access_token = PushNotificationService._get_access_token()
            if not access_token:
                return {
                    'success': False,
                    'error': 'Failed to get access token'
                }

            # FCM V1 API endpoint
            fcm_url = f'https://fcm.googleapis.com/v1/projects/{project_id}/messages:send'

            # Build message for FCM V1 API
            message = {
                'message': {
                    'token': device_token,
                    'notification': {
                        'title': title,
                        'body': body
                    },
                    'android': {
                        'priority': 'HIGH' if priority in ['high', 'urgent'] else 'NORMAL',
                        'notification': {
                            'sound': 'default',
                            'channel_id': 'ifrc_databank_channel',
                            'notification_priority': 'PRIORITY_HIGH' if priority in ['high', 'urgent'] else 'PRIORITY_DEFAULT'
                        }
                    },
                    'apns': {
                        'headers': {
                            'apns-priority': '10' if priority in ['high', 'urgent'] else '5'
                        },
                        'payload': {
                            'aps': {
                                'alert': {
                                    'title': title,
                                    'body': body
                                },
                                'sound': 'default',
                                'badge': 1
                            }
                        }
                    }
                }
            }

            # Add data payload if provided
            if data:
                # Convert all data values to strings (FCM requirement)
                message['message']['data'] = {k: str(v) for k, v in data.items()}

            # Send request to FCM V1 API
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            response = requests.post(
                fcm_url,
                headers=headers,
                json=message,
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                message_name = result.get('name', '')
                current_app.logger.debug(f"Push notification sent successfully: {message_name}")
                return {
                    'success': True,
                    'message_id': message_name
                }
            else:
                error_data = response.json() if response.content else {}
                error = error_data.get('error', {})
                error_message = error.get('message', f'HTTP {response.status_code}')
                error_code = error.get('code', '')

                current_app.logger.warning(
                    f"FCM V1 API error for {device_token[:20]}...: {error_message} (code: {error_code})"
                )
                return {
                    'success': False,
                    'error': error_message,
                    'error_code': error_code
                }

        except requests.exceptions.Timeout as e:
            current_app.logger.error(f"Timeout sending push notification to {device_token[:20]}...: {str(e)}")
            return {
                'success': False,
                'error': 'Request timeout',
                'error_code': 'TIMEOUT',
                'retryable': True
            }
        except requests.exceptions.ConnectionError as e:
            current_app.logger.error(f"Connection error sending push notification to {device_token[:20]}...: {str(e)}")
            return {
                'success': False,
                'error': 'Connection error',
                'error_code': 'CONNECTION_ERROR',
                'retryable': True
            }
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Network error sending push notification to {device_token[:20]}...: {str(e)}")
            return {
                'success': False,
                'error': 'Network error.',
                'error_code': 'NETWORK_ERROR',
                'retryable': True
            }
        except Exception as e:
            current_app.logger.error(f"Unexpected error sending push notification to {device_token[:20]}...: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': 'An error occurred while sending the notification.',
                'error_code': 'UNKNOWN_ERROR',
                'retryable': False
            }

    @staticmethod
    def register_device(
        user_id: int,
        device_token: str,
        platform: str,
        app_version: Optional[str] = None,
        device_model: Optional[str] = None,
        device_name: Optional[str] = None,
        os_version: Optional[str] = None,
        ip_address: Optional[str] = None,
        timezone: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Register a device for push notifications.

        Args:
            user_id: ID of the user
            device_token: FCM device token
            platform: Platform ('ios' or 'android')
            app_version: Optional app version string
            device_model: Optional device model (e.g., "iPhone 14 Pro")
            device_name: Optional user-assigned device name
            os_version: Optional OS version (e.g., "iOS 17.2")
            ip_address: Optional IP address at registration time
            timezone: Optional timezone (e.g., "America/New_York")

        Returns:
            Dict with success status
        """
        try:
            # Check if device already exists
            existing_device = UserDevice.query.filter_by(device_token=device_token).first()

            if existing_device:
                # Update existing device and clear logged_out_at if it was logged out
                existing_device.user_id = user_id
                existing_device.platform = platform
                if app_version:
                    existing_device.app_version = app_version
                if device_model:
                    existing_device.device_model = device_model
                if device_name:
                    existing_device.device_name = device_name
                if os_version:
                    existing_device.os_version = os_version
                if ip_address:
                    existing_device.ip_address = ip_address
                if timezone:
                    existing_device.timezone = timezone
                existing_device.last_active_at = utcnow()
                # Clear logged_out_at to reactivate the device
                existing_device.logged_out_at = None
                db.session.commit()

                return {
                    'success': True,
                    'message': 'Device updated and reactivated' if existing_device.logged_out_at is None else 'Device updated',
                    'device_id': existing_device.id
                }
            else:
                # Create new device
                device = UserDevice(
                    user_id=user_id,
                    device_token=device_token,
                    platform=platform,
                    app_version=app_version,
                    device_model=device_model,
                    device_name=device_name,
                    os_version=os_version,
                    ip_address=ip_address,
                    timezone=timezone
                )
                db.session.add(device)
                db.session.commit()

                return {
                    'success': True,
                    'message': 'Device registered',
                    'device_id': device.id
                }

        except Exception as e:
            current_app.logger.error(f"Error registering device: {str(e)}")
            db.session.rollback()
            return {
                'success': False,
                'error': 'An error occurred while registering the device.'
            }

    @staticmethod
    def unregister_device(
        user_id: int,
        device_token: str
    ) -> Dict[str, Any]:
        """
        Mark a device as logged out (instead of deleting it).
        This preserves device history while preventing push notifications.

        Args:
            user_id: ID of the user
            device_token: FCM device token

        Returns:
            Dict with success status
        """
        try:
            device = UserDevice.query.filter_by(
                user_id=user_id,
                device_token=device_token
            ).first()

            if device:
                # Mark as logged out instead of deleting
                device.logged_out_at = utcnow()
                db.session.commit()
                current_app.logger.info(f"Device {device.id} marked as logged out for user {user_id}")
                return {
                    'success': True,
                    'message': 'Device logged out'
                }
            else:
                return {
                    'success': False,
                    'error': 'Device not found'
                }

        except Exception as e:
            current_app.logger.error(f"Error unregistering device: {str(e)}")
            db.session.rollback()
            return {
                'success': False,
                'error': 'An error occurred while unregistering the device.'
            }

    @staticmethod
    def send_bulk_push_notifications(
        user_ids: List[int],
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        priority: str = 'normal'
    ) -> Dict[str, Any]:
        """
        Send push notifications to multiple users.

        Args:
            user_ids: List of user IDs
            title: Notification title
            body: Notification body
            data: Optional data payload
            priority: Priority level

        Returns:
            Dict with summary of results
        """
        total_devices = 0
        total_success = 0
        total_failure = 0
        user_results = []

        for user_id in user_ids:
            result = PushNotificationService.send_push_notification(
                user_id=user_id,
                title=title,
                body=body,
                data=data,
                priority=priority
            )

            user_results.append({
                'user_id': user_id,
                'result': result
            })

            if result.get('success'):
                total_success += result.get('success_count', 0)
                total_devices += result.get('devices_count', 0)
            else:
                total_failure += result.get('devices_count', 0)
                total_devices += result.get('devices_count', 0)

        return {
            'success': total_success > 0,
            'total_users': len(user_ids),
            'total_devices': total_devices,
            'total_success': total_success,
            'total_failure': total_failure,
            'user_results': user_results
        }

    @staticmethod
    def update_device_activity(
        user_id: int,
        device_token: Optional[str] = None,
        throttle_minutes: int = 5
    ) -> bool:
        """
        Lightweight method to update device last_active_at timestamp.
        Includes throttling to prevent excessive database writes.

        Args:
            user_id: ID of the user
            device_token: Optional device token. If provided, updates that specific device.
                         If None, updates all devices for the user.
            throttle_minutes: Minimum minutes between updates for the same device (default: 5)

        Returns:
            True if update was performed, False if throttled or device not found
        """
        try:
            from datetime import timedelta

            now = utcnow()
            throttle_threshold = now - timedelta(minutes=throttle_minutes)

            if device_token:
                # Update specific device if token provided (only active devices)
                device = UserDevice.query.filter_by(
                    user_id=user_id,
                    device_token=device_token
                ).filter(
                    UserDevice.logged_out_at.is_(None)
                ).first()

                if device and (device.last_active_at is None or device.last_active_at < throttle_threshold):
                    device.last_active_at = now
                    db.session.commit()
                    return True
                return False
            else:
                # Update all active devices for user (used when device_token not available)
                # Only update devices that haven't been updated recently and are not logged out
                devices = UserDevice.query.filter_by(user_id=user_id).filter(
                    UserDevice.logged_out_at.is_(None)
                ).filter(
                    db.or_(
                        UserDevice.last_active_at.is_(None),
                        UserDevice.last_active_at < throttle_threshold
                    )
                ).all()

                if devices:
                    for device in devices:
                        device.last_active_at = now
                    db.session.commit()
                    return True
                return False

        except Exception as e:
            current_app.logger.debug(f"Error updating device activity (non-critical): {str(e)}")
            # Don't rollback - this is non-critical, just log and continue
            return False
