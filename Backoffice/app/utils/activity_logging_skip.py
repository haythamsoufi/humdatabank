"""
Rules for endpoints that should not produce automatic UserActivityLog rows.

Shared by activity middleware and catalog gap tooling so skip logic stays aligned.
"""

from __future__ import annotations

# Exact endpoint names to skip (mirror app.middleware.activity_middleware)
SKIP_ACTIVITY_ENDPOINTS: frozenset[str] = frozenset(
    {
        "auth.login",
        "auth.logout",
        "api.heartbeat",
        "api.status",
        "public.health_check",
        "forms_api.api_presence_heartbeat",
        "forms_api.api_presence_active_users",
        "main.api_get_notifications_count",
        "main.api_get_notifications",
        "notifications.api_get_notification_count",
        "notifications.api_get_notifications",
        "notifications.api_get_notification_preferences",
        "notifications.api_notification_stream_status",
        "notifications.mark_notifications_read",
        "main.mark_notifications_read",
        "main.service_worker",
        "form_builder.edit_item",
        "form_builder.new_section_item",
        "form_builder.delete_item",
        "utilities.api_auto_translate",
        "utilities.api_auto_translate_summary",
        "organization.api_auto_translate_organizations",
        "system_admin.get_filtered_indicator_count",
        "forms.search_matrix_rows",
        "main.load_more_activities",
        "forms_api.api_render_pending_dynamic_indicator",
        "ai_v2.chat",
        "ai_v2.chat_stream",
        "ai_v2.list_conversations",
        "ai_v2.issue_token",
        "notifications.device_heartbeat",
        "mobile_api.device_heartbeat",
        "mobile_api.screen_view",
        "admin_analytics_api.session_logs_list_api",
        "admin_analytics_api.login_logs_list_api",
        "user_management.api_users_profile_summary",
        "main.api_users_profile_summary",
        "utilities.refresh_csrf_token",
        "utilities.refresh_csrf_token_get",
        "forms_api.api_search_indicator_bank",
        "forms_api.get_lookup_list_options",
        "forms_api.get_lookup_list_config_ui",
        "forms_api.api_render_dynamic_indicator",
        "user_management.get_user_entities",
        "user_management.get_ns_hierarchy",
        "user_management.get_secretariat_hierarchy",
        "user_management.get_secretariat_regions_hierarchy",
        "ai_documents.list_ifrc_api_documents",
        "ai_documents.list_ifrc_api_types",
        "ai_ws",
        "ai_management.list_system_documents",
        "settings.api_check_updates",
        "utilities.api_translation_services",
        # AdminActionLog already records end_user_session (forced logout); skip duplicate UserActivityLog.
        "admin_analytics_api.end_session_api",
        # Legacy redirect shim only — not a user-facing action worth an activity row.
        "admin.legacy_api_key_admin_redirect",
    }
)

SKIP_ACTIVITY_ENDPOINT_PREFIXES: tuple[str, ...] = ("static", "plugin_static")

SKIP_ACTIVITY_ENDPOINT_SUFFIXES: frozenset[str] = frozenset(
    {
        "get_workflow_tour",
        "api_presence_heartbeat",
        "api_notification_stream_status",
        "api_get_notification_count",
        "api_get_notification_preferences",
        "service_worker",
        "device_heartbeat",
    }
)


def should_skip_activity_endpoint(endpoint: str | None) -> bool:
    """Return True if automatic activity logging should not record this endpoint."""
    if not endpoint:
        return False
    if endpoint in SKIP_ACTIVITY_ENDPOINTS:
        return True
    for prefix in SKIP_ACTIVITY_ENDPOINT_PREFIXES:
        if endpoint.startswith(prefix):
            return True
    suffix = endpoint.rsplit(".", 1)[-1]
    if suffix in SKIP_ACTIVITY_ENDPOINT_SUFFIXES:
        return True
    return False


def should_exclude_from_activity_catalog(method: str | None, endpoint: str | None) -> bool:
    """
    True for routes that should not appear in ENDPOINT_ACTIVITY_SPECS (generator + gap checks).

    Automatic middleware only bumps session ``page_views`` for GET navigations — it never
    writes ``UserActivityLog`` rows for ``activity_type == page_view`` (see
    ``after_request``). Catalog rows for GET would be misleading or would have
    incorrectly forced ``activity_type`` overrides before the guard was added.
    """
    if not endpoint:
        return True
    if should_skip_activity_endpoint(endpoint):
        return True
    m = (method or "GET").strip().upper()
    if m == "GET":
        return True
    return False


def should_skip_activity_path(path: str | None) -> bool:
    """Skip JSON APIs that middleware does not log."""
    if not path:
        return False
    if path.startswith("/api/v1/") or path.startswith("/api/mobile/"):
        return True
    return False
