"""Declarative RBAC policy for high-risk admin routes.

The startup guard audit (``app.startup_tasks.audit_admin_route_guards``) and the guard-coverage
tests read these tables so that a regression of a known class of issue (dangerous action behind a
read permission, GET with side effects, plugin code changes without System Manager, ...) is
reported as soon as a route is added or a decorator is dropped.

Canonical guard for ``/admin`` routes: ``@permission_required('admin.<area>.<action>')``. An
``admin.*`` permission can only be obtained through a role or a global grant, which is exactly what
makes ``AuthorizationService.is_admin`` true, so it already implies the admin gate. Use
``system_manager_required`` on top for platform-level capabilities, ``admin_required`` only for
pages that are open to every admin plus an object-level check inside the view.
"""

from __future__ import annotations

ADMIN_PERMISSION_PREFIX = "admin."

# Endpoints that must be System Manager only. Plugin install/upload/uninstall load or remove Python
# code (remote-code-execution equivalent); the error-notification test emails every System Manager.
SYSTEM_MANAGER_ONLY_ENDPOINTS = frozenset(
    {
        "plugin_management.install_plugin",
        "plugin_management.uninstall_plugin",
        "plugin_management.upload_plugin",
        "monitoring.test_error_notification",
    }
)

# Endpoints that must never answer GET/HEAD (they trigger side effects).
POST_ONLY_ENDPOINTS = frozenset(
    {
        "monitoring.test_error_notification",
        "monitoring.clear_monitoring_logs",
        "plugin_management.install_plugin",
        "plugin_management.uninstall_plugin",
        "plugin_management.upload_plugin",
    }
)

# Destructive housekeeping: must be guarded by the dedicated permission, never by a read permission.
REQUIRED_PERMISSION_BY_ENDPOINT = {
    "monitoring.clear_monitoring_logs": "admin.system.maintain",
    "utilities.cleanup_sessions": "admin.system.maintain",
    "system_admin.cleanup_sessions": "admin.system.maintain",
    "analytics.cleanup_sessions": "admin.system.maintain",
    "analytics.end_session": "admin.system.maintain",
    "admin_analytics_api.end_session_api": "admin.system.maintain",
    "analytics.resolve_security_event": "admin.security.respond",
    "data_exploration.apply_imputed_value": "admin.data_explore.impute",
    "organization.delete_country": "admin.countries.delete",
    "system_admin.delete_country": "admin.countries.delete",
}

# Routes that are deliberately guarded by a non-``admin.*`` permission (document/assignment
# permissions evaluated with their own scope rules). Everything else must use ``admin.*`` codes.
NON_ADMIN_PERMISSION_ALLOWLIST_PREFIXES = ("assignment.", "documents.", "document.")

# Prefixes outside ``/admin`` that the audit inspects because they serve privileged content.
EXTRA_AUDITED_PATH_PREFIXES = ("/plugins/static",)

# Plugin blueprints mount under these prefixes and guard read-only GET routes with
# ``plugin_route_wrapper`` (login only, no RBAC metadata). Mutating plugin routes must still carry an
# RBAC guard (``plugin_admin_route_wrapper``).
LOGIN_ONLY_READ_PATH_PREFIXES = ("/admin/plugins/",)

# Verb prefixes in view names that indicate a side effect; a GET-only route with such a name is
# reported (side effects must not hang off GET: prefetch, link unfurling and CSRF all bypass POST
# protections).
SIDE_EFFECT_VIEW_PREFIXES = (
    "cleanup",
    "clear_",
    "delete_",
    "remove_",
    "reset_",
    "send_",
    "trigger_",
    "test_",
    "purge",
    "install_",
    "uninstall_",
)

# Views whose names look mutating but are read-only or otherwise reviewed. Keep this list short and
# justify each entry.
GET_SIDE_EFFECT_NAME_ALLOWLIST: frozenset[str] = frozenset()

# POST routes that only read data (search/preview/export bodies too large for a query string) and
# are therefore acceptable behind a ``*.view`` permission. Reviewed one by one.
READ_ONLY_POST_ALLOWLIST = frozenset(
    {
        "system_admin.indicator_bank_neural_map_probe",
        "system_admin.export_indicators",
        "system_admin.get_filtered_indicator_count",
        "data_sync_imputation.preview_data_chunked",
    }
)

# CSRF-exempt mutating routes, each with the reason it is tolerated. New entries need a review: a
# cookie-authenticated mutation without CSRF protection is a request-forgery primitive.
CSRF_EXEMPT_MUTATION_ALLOWLIST = {
    "admin_analytics_api.end_session_api": "CSRF-exempt so the mobile app can POST without a Referer. The view calls enforce_api_or_csrf_protection() (X-Mobile-Auth or CSRF) and requires admin.system.maintain.",
    "admin_communication.api_send_notifications": "Mobile/API client; follow-up: restrict to token auth and drop the exemption for cookie sessions.",
}

# Login-only plugin routes that use POST for a read-only lookup (body too large or sensitive for a
# query string). Anything else that mutates state must use ``plugin_admin_route_wrapper``.
LOGIN_ONLY_POST_ALLOWLIST = frozenset({"interactive_map_plugin.geocode_address"})
