"""
User-facing labels for audit-trail activity / action types.

Used by the filter dropdown so it matches the grid badges instead of
``admin_ai`` → “Admin Ai”.
"""

from __future__ import annotations

from flask_babel import gettext as _


def activity_type_display_label(value: str) -> str:
    """Return a reviewer-facing label for a stored activity or action type."""
    if not value:
        return ""
    labels = {
        "page_view": _("Page view"),
        "request": _("Back-office action"),
        "backoffice_action": _("Back-office action"),
        "admin_ai": _("AI"),
        "admin_content": _("Content"),
        "admin_embed": _("Embed"),
        "admin_assignments": _("Assignments"),
        "admin_organization": _("Organization"),
        "admin_system": _("Indicators & lists"),
        "admin_users": _("Users"),
        "admin_forms": _("Forms"),
        "admin_analytics": _("Analytics"),
        "admin_utilities": _("Utilities"),
        "admin_settings": _("Settings"),
        "admin_security": _("Settings"),
        "admin_plugin": _("Plugins"),
        "admin_notifications": _("Notifications"),
        "admin_monitoring": _("Monitoring"),
        "admin_portal": _("Account"),
        "admin_other": _("Other"),
        "login": _("Logged in"),
        "logout": _("Logged out"),
        "profile_update": _("Profile updated"),
        "form_saved": _("Draft save"),
        "form_save": _("Draft save"),
        "form_submitted": _("Form submitted"),
        "form_approved": _("Form approved"),
        "form_reopened": _("Form reopened"),
        "form_validated": _("Form validated"),
        "form_submit": _("Form submitted"),
        "data_modified": _("Data modified"),
        "data_deleted": _("Data deleted"),
        "data_update": _("Data modified"),
        "data_delete": _("Data deleted"),
        "data_export": _("Data exported"),
        "file_uploaded": _("File uploaded"),
        "file_upload": _("File uploaded"),
        "account_created": _("Account created"),
        "user_create": _("User added"),
        "user_update": _("User modified"),
        "user_delete": _("User deleted"),
        "access_request_approve": _("Access approved"),
        "access_request_reject": _("Access rejected"),
        "access_request_auto_resolve": _("Access auto-resolved"),
        "country_access_requested": _("Access requested"),
        "device_registered": _("Device registered"),
        "device_unregistered": _("Device unregistered"),
        "settings_updated": _("Settings updated"),
        "email_templates_updated": _("Email templates updated"),
        "api_key_create": _("API key created"),
        "api_key_revoke": _("API key revoked"),
        "template_create": _("Template created"),
        "template_update": _("Template modified"),
        "template_delete": _("Template deleted"),
        "template_import": _("Template imported"),
        "template_import_excel": _("Excel imported"),
        "template_variables_update": _("Variables updated"),
        "template_sharing_update": _("Sharing updated"),
        "template_version_deploy": _("Version deployed"),
        "template_version_create": _("Version created"),
        "template_version_delete": _("Version deleted"),
        "form_section_create": _("Section added"),
        "form_section_update": _("Section modified"),
        "form_section_delete": _("Section deleted"),
        "form_item_create": _("Item added"),
        "form_item_update": _("Item modified"),
        "form_item_delete": _("Item deleted"),
        "form_item_unarchive": _("Item restored"),
        "end_user_session": _("Session ended"),
        "cleanup_sessions": _("Sessions cleaned"),
        "resolve_security_event": _("Security event resolved"),
    }
    if value in labels:
        return labels[value]
    readable = value.replace("_", " ").strip()
    if readable.startswith("admin "):
        readable = readable[6:]
    return readable[:1].upper() + readable[1:] if readable else value
