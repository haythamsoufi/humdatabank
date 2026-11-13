# CSP Nonce utilities for Content Security Policy
"""
Utilities for generating and managing CSP nonces to replace 'unsafe-inline' scripts.

CSP nonces provide better XSS protection by allowing only scripts with matching nonces
to execute, eliminating the need for 'unsafe-inline'.
"""

import secrets
from flask import g, request, current_app
from typing import Optional


def generate_csp_nonce() -> str:
    """
    Generate a cryptographically secure nonce for CSP.

    Returns:
        A base64-encoded nonce suitable for CSP nonce attribute
    """
    # Generate 16 random bytes and encode as base64 URL-safe string
    # This gives us ~21 characters, which is sufficient for CSP nonces
    nonce_bytes = secrets.token_bytes(16)
    nonce = secrets.token_urlsafe(16)[:16]  # Use URL-safe encoding, limit length
    return nonce


def get_csp_nonce() -> str:
    """
    Get or generate a CSP nonce for the current request.

    Nonces are stored in Flask's g object to ensure the same nonce
    is used throughout the request lifecycle.

    Returns:
        The nonce string for the current request
    """
    if not hasattr(g, 'csp_nonce'):
        g.csp_nonce = generate_csp_nonce()
    return g.csp_nonce


def get_style_nonce() -> str:
    """
    Get or generate a CSP nonce for inline styles.

    Uses the same nonce as scripts for simplicity, but could be separate
    if needed for different security policies.

    Returns:
        The nonce string for inline styles
    """
    # For now, use the same nonce as scripts
    # This can be changed to a separate nonce if needed
    return get_csp_nonce()


def clear_csp_nonce():
    """
    Clear the CSP nonce from the request context.

    Useful for testing or if you need to regenerate the nonce.
    """
    if hasattr(g, 'csp_nonce'):
        delattr(g, 'csp_nonce')
