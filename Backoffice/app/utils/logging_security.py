"""
Logging security utilities to prevent sensitive data leakage in logs.
"""
import re
from typing import Any, Dict, Optional


def sanitize_for_logging(value: Any, max_length: int = 200) -> str:
    """
    Sanitize a value for safe logging by masking sensitive data.

    Args:
        value: The value to sanitize
        max_length: Maximum length for string values before truncation

    Returns:
        Sanitized string representation
    """
    if value is None:
        return 'None'

    # Convert to string
    str_value = str(value)

    # Mask passwords
    str_value = re.sub(
        r'(password\s*[:=]\s*)([^\s&"<>]+)',
        r'\1***MASKED***',
        str_value,
        flags=re.IGNORECASE
    )

    # Mask API keys
    str_value = re.sub(
        r'(api[_-]?key\s*[:=]\s*)([^\s&"<>]+)',
        r'\1***MASKED***',
        str_value,
        flags=re.IGNORECASE
    )

    # Mask tokens
    str_value = re.sub(
        r'(token\s*[:=]\s*)([^\s&"<>]+)',
        r'\1***MASKED***',
        str_value,
        flags=re.IGNORECASE
    )

    # Mask secrets
    str_value = re.sub(
        r'(secret[_-]?key\s*[:=]\s*)([^\s&"<>]+)',
        r'\1***MASKED***',
        str_value,
        flags=re.IGNORECASE
    )

    # Mask session cookies
    str_value = re.sub(
        r'(session\s*=\s*)([^;,\s]+)',
        r'\1***MASKED***',
        str_value,
        flags=re.IGNORECASE
    )

    # Truncate long strings
    if len(str_value) > max_length:
        str_value = f"{str_value[:max_length]}... [TRUNCATED {len(str_value) - max_length} chars]"

    return str_value


def sanitize_dict_for_logging(data: Dict[str, Any], sensitive_keys: Optional[list] = None) -> Dict[str, Any]:
    """
    Sanitize a dictionary for safe logging by masking sensitive keys.

    Args:
        data: Dictionary to sanitize
        sensitive_keys: List of keys to mask (default: common sensitive keys)

    Returns:
        Sanitized dictionary
    """
    if sensitive_keys is None:
        sensitive_keys = ['password', 'csrf_token', 'api_key', 'secret', 'token', 'secret_key', 'session']

    sanitized = {}
    for key, value in data.items():
        key_lower = key.lower()
        # Check if key contains any sensitive keyword
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            sanitized[key] = '***MASKED***'
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict_for_logging(value, sensitive_keys)
        elif isinstance(value, (list, tuple)):
            sanitized[key] = [
                sanitize_dict_for_logging(item, sensitive_keys) if isinstance(item, dict)
                else sanitize_for_logging(item)
                for item in value
            ]
        else:
            sanitized[key] = sanitize_for_logging(value)

    return sanitized
