"""
Organization branding helper functions.

Provides convenient access to organization branding information throughout the application.
All functions read from the database settings (via app_settings) with fallback to environment variables.
Supports localized organization names based on current locale.
"""
from typing import Dict, Optional
from flask import has_request_context, request
from flask_babel import get_locale
from app.utils.app_settings import (
    get_organization_branding,
    get_organization_domain,
    get_organization_email_domain,
    get_organization_name,
    get_organization_short_name,
    is_organization_email,
    get_organization_logo_path,
    get_organization_copyright_year,
)


def get_org_name(default: str = "NGO Databank", locale: Optional[str] = None) -> str:
    """Get organization name. Alias for get_organization_name."""
    return get_organization_name(default=default, locale=locale)


def get_org_short_name(default: str = "NGO Databank", locale: Optional[str] = None) -> str:
    """Get organization short name. Alias for get_organization_short_name."""
    return get_organization_short_name(default=default, locale=locale)


def get_org_domain(default: str = "ngodatabank.org") -> str:
    """Get organization domain. Alias for get_organization_domain."""
    return get_organization_domain(default=default)


def get_org_email_domain(default: str = "ngodatabank.org") -> str:
    """Get organization email domain. Alias for get_organization_email_domain."""
    return get_organization_email_domain(default=default)


def is_org_email(email: str) -> bool:
    """Check if email belongs to organization domain. Alias for is_organization_email."""
    return is_organization_email(email)


def get_org_logo_path(default: str = "logo.svg") -> str:
    """Get organization logo path. Alias for get_organization_logo_path."""
    return get_organization_logo_path(default=default)


def get_org_copyright_year(default: Optional[str] = None) -> str:
    """Get organization copyright year. Alias for get_organization_copyright_year."""
    return get_organization_copyright_year(default=default)


def get_org_branding() -> Dict:
    """Get all organization branding information as a dictionary.

    Returns a dictionary with keys:
    - organization_name
    - organization_short_name
    - organization_domain
    - organization_email_domain
    - organization_logo_path (optional)
    - organization_copyright_year
    """
    return get_organization_branding()


# Convenience function for templates and views
def get_branding_context(locale: Optional[str] = None) -> Dict:
    """Get organization branding as a context dictionary for templates.

    This is a convenience function that returns all branding info
    in a format suitable for passing to Jinja templates.
    Uses current locale for localized fields.

    Args:
        locale: Optional locale code. If None, uses current request locale.

    Returns:
        Dictionary with localized branding values
    """
    branding = get_organization_branding()
    return {
        "org_name": get_org_name(locale=locale),
        "org_short_name": get_org_short_name(locale=locale),
        "org_domain": branding.get("organization_domain", "ngodatabank.org"),
        "org_email_domain": branding.get("organization_email_domain", branding.get("organization_domain", "ngodatabank.org")),
        "org_logo": branding.get("organization_logo_path", "logo.svg"),
        "org_copyright_year": branding.get("organization_copyright_year", ""),
    }
