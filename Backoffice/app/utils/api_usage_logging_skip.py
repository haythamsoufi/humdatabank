"""
Path rules for endpoints excluded from api_usage / APIKeyUsage rows.

These are high-volume or low-signal routes (UI plumbing, heartbeats, static
assets) that would distort aggregate API analytics in Admin → API Management.
Keep aligned with app.utils.activity_logging_skip where the same route is also
excluded from automatic UserActivityLog rows.
"""

from __future__ import annotations


def should_skip_api_usage_path(path: str | None, method: str | None = None) -> bool:
    """Return True if this /api/* request should not be written to api_usage."""
    if not path:
        return False

    path = path.rstrip("/") or path
    method = (method or "GET").strip().upper()

    if "notifications" in path or "refresh-csrf-token" in path:
        return True

    # Live presence heartbeats (not meaningful for aggregate API analytics)
    if path.startswith("/api/forms/presence/"):
        return True

    # WebSocket upgrade endpoints
    if path in ("/api/ai/v2/ws", "/api/ai/documents/ws"):
        return True

    # Streaming / cancel — tracked elsewhere; not comparable to normal REST latency
    if path in ("/api/ai/v2/chat/stream", "/api/ai/v2/chat/cancel"):
        return True

    # Product tour content under document workflows
    if path.startswith("/api/ai/documents/workflows/") and path.endswith("/tour"):
        return True

    # Lookup dropdown option fetches and config UI fragments
    if path.startswith("/api/forms/lookup-lists/") and (
        path.endswith("/options") or path.endswith("/config-ui")
    ):
        return True

    if path == "/api/forms/dynamic-indicators/render-pending":
        return True

    # Per-indicator HTML fragments (same role as render-pending)
    if path.startswith("/api/forms/dynamic-indicators/") and path.endswith("/render"):
        return True

    # Assignment progress widget polled after page load
    if path.startswith("/api/forms/assignment/") and path.endswith("/completion-rate"):
        return True

    if path == "/api/ai/v2/token":
        return True

    if path == "/api/v1/variables/resolve":
        return True

    # Polled conversation list / single conversation (GET only)
    if method == "GET" and path == "/api/ai/v2/conversations":
        return True
    if method == "GET" and path.startswith("/api/ai/v2/conversations/"):
        rest = path[len("/api/ai/v2/conversations/") :]
        if rest and "/" not in rest:
            return True

    # Session / CSRF / client error plumbing
    if path in (
        "/api/v1/csrf-token",
        "/api/v1/platform-error",
        "/api/stream/status",
        "/api/users/profile-summary",
        "/api/preferences",
    ):
        return True

    # Internal form matrix helper (session auth, not external API consumption)
    if path == "/api/v1/matrix/auto-load-entities":
        return True

    # Static sector icons served under /api for convenience
    if path.startswith("/api/v1/uploads/"):
        return True

    # Website embed widgets — not part of the documented external/mobile API surfaces
    if path.startswith("/api/backoffice/"):
        return True

    # Mobile telemetry and device/session plumbing
    if path == "/api/mobile/v1/analytics/screen-view":
        return True
    if path.startswith("/api/mobile/v1/devices/"):
        return True
    if path in ("/api/mobile/v1/auth/session", "/api/mobile/v1/auth/refresh"):
        return True

    return False
