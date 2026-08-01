"""URL and action-button validation for notifications."""
from typing import Optional, Dict, Any, List

from flask import current_app
from urllib.parse import urlparse

def validate_notification_url(url: str) -> bool:
    """
    Validate notification URLs to prevent open redirects and XSS attacks.

    By default, only relative paths are allowed. External URLs require
    explicit whitelist configuration via NOTIFICATION_ALLOWED_DOMAINS.

    Args:
        url: URL to validate

    Returns:
        True if URL is safe, False otherwise
    """
    if not url:
        return True  # Empty URL is OK

    url = url.strip()

    # Reject dangerous schemes
    dangerous_schemes = ['javascript:', 'data:', 'vbscript:', 'file:', 'about:']
    url_lower = url.lower()
    for scheme in dangerous_schemes:
        if url_lower.startswith(scheme):
            return False

    # Allow relative paths (must start with /)
    if url.startswith('/'):
        # Reject protocol-relative URLs (//evil.com)
        if url.startswith('//'):
            return False
        # Reject characters that break out of HTML attributes or enable injection if ever
        # rendered without escaping (defence in depth alongside Jinja escaping).
        if any(ch in url for ch in ('"', "'", '<', '>', '\n', '\r', '\0')):
            return False
        # Allow relative paths by default (safest option)
        return True

    # For absolute URLs, require explicit whitelist configuration
    retry_context = None
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ['http', 'https']:
            return False

        # SECURITY: By default, only allow relative paths
        # External URLs require explicit whitelist configuration
        allowed_domains = current_app.config.get('NOTIFICATION_ALLOWED_DOMAINS', [])
        if not allowed_domains:
            current_app.logger.warning(
                f"External URL rejected (no whitelist configured): {url[:100]}. "
                f"Only relative paths are allowed by default. "
                f"Configure NOTIFICATION_ALLOWED_DOMAINS to allow external URLs."
            )
            return False

        if parsed.netloc not in allowed_domains:
            current_app.logger.warning(
                f"External URL rejected (domain not in whitelist): {parsed.netloc}. "
                f"Allowed domains: {allowed_domains}"
            )
            return False

        return True
    except Exception as e:
        # Invalid URL format
        current_app.logger.debug(f"URL validation failed for '{url[:100]}': {e}")
        return False


def validate_action_button_endpoint(endpoint: Optional[str]) -> bool:
    """
    Validate action button endpoint to ensure it's safe.

    Args:
        endpoint: Endpoint URL to validate

    Returns:
        True if endpoint is safe, False otherwise
    """
    if not endpoint:
        return True  # Empty endpoint is OK

    endpoint = endpoint.strip()

    # Must be a relative path
    if not endpoint.startswith('/'):
        return False

    # Reject dangerous patterns
    dangerous_patterns = ['//', 'javascript:', 'data:', '../', '..\\']
    endpoint_lower = endpoint.lower()
    for pattern in dangerous_patterns:
        if pattern in endpoint_lower:
            return False

    # Optionally: Check against whitelist of allowed endpoint patterns
    allowed_patterns = current_app.config.get('NOTIFICATION_ALLOWED_ENDPOINTS', [])
    if allowed_patterns:
        # Check if endpoint matches any allowed pattern
        for pattern in allowed_patterns:
            # Simple pattern matching (could use regex for more complex)
            if pattern.replace('{id}', '').replace('{*}', '') in endpoint:
                return True
        return False

    # If no whitelist configured, allow any relative path (but still check for dangerous patterns above)
    return True


def validate_and_sanitize_action_buttons(action_buttons: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    """
    Validate and sanitize action buttons when deserializing from database.
    This provides defense-in-depth validation when action buttons are retrieved.

    Args:
        action_buttons: List of action button dictionaries from database

    Returns:
        Validated and sanitized list of action buttons, or None if invalid/empty
    """
    if not action_buttons:
        return None

    if not isinstance(action_buttons, list):
        current_app.logger.warning(f"Invalid action_buttons type: {type(action_buttons)}, expected list")
        return None

    validated_buttons = []
    for i, btn in enumerate(action_buttons):
        if not isinstance(btn, dict):
            current_app.logger.warning(f"Action button at index {i} is not a dictionary, skipping")
            continue

        # Validate required fields
        if 'action' not in btn or 'label' not in btn:
            current_app.logger.warning(f"Action button at index {i} missing required fields (action, label), skipping")
            continue

        # Validate and sanitize label
        label = btn.get('label', '')
        if not isinstance(label, str):
            current_app.logger.warning(f"Action button at index {i} label is not a string, skipping")
            continue

        max_label_length = current_app.config.get('MAX_ACTION_BUTTON_LABEL_LENGTH', 100)
        if len(label) > max_label_length:
            current_app.logger.warning(f"Action button at index {i} label too long ({len(label)} chars), truncating")
            label = label[:max_label_length]

        # Validate action identifier
        action = btn.get('action', '')
        if not isinstance(action, str):
            current_app.logger.warning(f"Action button at index {i} action is not a string, skipping")
            continue

        max_action_length = current_app.config.get('MAX_ACTION_BUTTON_ACTION_LENGTH', 50)
        if len(action) > max_action_length:
            current_app.logger.warning(f"Action button at index {i} action too long ({len(action)} chars), skipping")
            continue

        # Validate endpoint if provided
        endpoint = btn.get('endpoint')
        if endpoint:
            if not isinstance(endpoint, str):
                current_app.logger.warning(f"Action button at index {i} endpoint is not a string, removing endpoint")
                endpoint = None
            elif not validate_action_button_endpoint(endpoint):
                current_app.logger.warning(
                    f"Action button at index {i} has unsafe endpoint '{endpoint}', removing endpoint"
                )
                endpoint = None

        # Validate style if provided
        style = btn.get('style')
        valid_styles = ['primary', 'danger', 'secondary', 'success', 'warning', 'info']
        if style and style not in valid_styles:
            current_app.logger.warning(f"Action button at index {i} has invalid style '{style}', using default")
            style = 'primary'

        # Create validated button
        validated_btn = {
            'action': action,
            'label': label,
        }

        if endpoint:
            validated_btn['endpoint'] = endpoint

        if style:
            validated_btn['style'] = style

        validated_buttons.append(validated_btn)

    return validated_buttons if validated_buttons else None
