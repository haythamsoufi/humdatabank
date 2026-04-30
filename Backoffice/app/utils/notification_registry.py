"""
Canonical NotificationType catalog for the admin Notifications registry page.

Keeps grouped descriptions aligned with NotificationType enum (app.models.enums).
When adding enum members, extend NOTIFICATION_TYPE_REGISTRY_SPECS accordingly.

Each row may include ``recipients``: who receives the in-app notification when the
emitter runs (see ``build_notification_settings_delivery_rows`` for System Settings).

``audiences``: which audience buckets can be toggled in System Configuration for this type
(empty means emitters bypass audience rules—e.g. explicit recipient lists).

``emitter_active``: if ``True``, the application creates in-app notifications for this type when the
corresponding event occurs; if ``False``, the enum row exists for preferences / future use only
(**hypothetical** — see System Configuration grid ordering and Status column).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterator, List

# Buckets that may appear in registry ``audiences`` (subset of app_settings_service.NOTIFICATION_AUDIENCE_BUCKETS).
REGISTRY_AUDIENCE_BUCKETS = frozenset(("focal_points", "admin_users", "system_managers"))

NOTIFICATION_TYPE_REGISTRY_SPECS: List[Dict[str, Any]] = [
    {
        "group": "Assignments",
        "type_key": "assignment_created",
        "emitter_active": True,
        "audiences": ["focal_points", "admin_users", "system_managers"],
        "description": (
            "Created when the user gains a new form assignment requiring action."
        ),
        "recipients": (
            "Focal points: assignment editor/submitter on the entity. "
            "Org admins: ``admin_core`` / ``admin_*`` with entity coverage. "
            "System managers: deployment-wide ``system_manager`` role. Toggle each bucket in settings."
        ),
    },
    {
        "group": "Assignments",
        "type_key": "assignment_submitted",
        "emitter_active": True,
        "audiences": ["focal_points", "admin_users", "system_managers"],
        "description": (
            "Created when someone submits an assignment the user participates in "
            "(e.g., focal point reviewers)."
        ),
        "recipients": (
            "Focal points on the same entity (assignment editor/submitter role), including whoever submitted. "
            "Org admins and system managers are separate buckets below."
        ),
    },
    {
        "group": "Assignments",
        "type_key": "assignment_approved",
        "emitter_active": True,
        "audiences": ["focal_points"],
        "description": (
            "Created when an assignment submission is approved relevant to the user."
        ),
        "recipients": "Focal points on the assignment entity.",
    },
    {
        "group": "Assignments",
        "type_key": "assignment_reopened",
        "emitter_active": True,
        "audiences": ["focal_points"],
        "description": (
            "Created when a previously submitted assignment is reopened for edits."
        ),
        "recipients": "Focal points on the assignment entity.",
    },
    {
        "group": "Assignments",
        "type_key": "self_report_created",
        "emitter_active": True,
        "audiences": ["focal_points"],
        "description": (
            "Created when self-report flows generate a notification tied to assignments."
        ),
        "recipients": "Focal points on the assignment entity.",
    },
    {
        "group": "Assignments",
        "type_key": "deadline_reminder",
        "emitter_active": False,
        "audiences": ["focal_points"],
        "description": (
            "Reminder before or near an assignment deadline for assigned users."
        ),
        "recipients": (
            "No automated notification is emitted by the application today. The type exists "
            "for preference toggles and future scheduled reminders."
        ),
    },
    {
        "group": "Forms & submissions",
        "type_key": "public_submission_received",
        "emitter_active": True,
        "audiences": ["admin_users", "system_managers"],
        "description": (
            "Signals new public-channel submissions reviewers or admins should handle."
        ),
        "recipients": (
            "Org admins covering the submission country, and/or deployment-wide system managers — "
            "toggle independently."
        ),
    },
    {
        "group": "Forms & submissions",
        "type_key": "form_updated",
        "emitter_active": False,
        "audiences": ["focal_points"],
        "description": (
            "Form structure or applicability changed in a way that affects the recipient."
        ),
        "recipients": (
            "No automated notification is emitted by the application today. The type exists "
            "for preference toggles."
        ),
    },
    {
        "group": "Documents & access",
        "type_key": "document_uploaded",
        "emitter_active": True,
        "audiences": ["focal_points", "admin_users", "system_managers"],
        "description": (
            "A document linked to workflows the user participates in was uploaded."
        ),
        "recipients": (
            "Pending standalone uploads: org admins covering the country and/or system managers "
            "(separate toggles). Approved / assignment-linked: focal points on the entity "
            "(uploader excluded where applicable)."
        ),
    },
    {
        "group": "Documents & access",
        "type_key": "user_added_to_country",
        "emitter_active": True,
        "audiences": [],
        "description": (
            "Sent when the user gains access to a country or organisational scope."
        ),
        "recipients": (
            "The user who was granted access (single recipient). "
            "Not controlled by focal/admin audience toggles."
        ),
    },
    {
        "group": "Documents & access",
        "type_key": "access_request_received",
        "emitter_active": True,
        "audiences": ["admin_users", "system_managers"],
        "description": (
            "Notifies approvers/reviewers of a new country or access request submission."
        ),
        "recipients": (
            "Org admins covering the requested country and/or system managers (requester excluded); "
            "not sent when auto-approved."
        ),
    },
    {
        "group": "Templates",
        "type_key": "template_updated",
        "emitter_active": True,
        "audiences": ["focal_points"],
        "description": (
            "Published when template definition changes relevant to downstream users."
        ),
        "recipients": (
            "Focal points on countries that have active assignments using the updated template."
        ),
    },
    {
        "group": "System & admin",
        "type_key": "admin_message",
        "emitter_active": True,
        "audiences": [],
        "description": (
            "Custom notification from the Notifications Center (email/push broadcasts)."
        ),
        "recipients": (
            "Only users explicitly chosen when sending from the Notifications Center; "
            "optional email and mobile push per send. Audience toggles do not apply."
        ),
    },
]


def iter_registry_specs_display_order() -> Iterator[Dict[str, Any]]:
    """Iterate specs with active emitters first (declaration order), hypothetical rows last."""
    indexed = list(enumerate(NOTIFICATION_TYPE_REGISTRY_SPECS))
    indexed.sort(key=lambda item: (not item[1]["emitter_active"], item[0]))
    for _, spec in indexed:
        yield spec


def validate_registry_specs() -> None:
    """Raise AssertionError if registry keys diverge from NotificationType."""
    from app.models.enums import NotificationType

    spec_keys = {s["type_key"] for s in NOTIFICATION_TYPE_REGISTRY_SPECS}
    enum_keys = {nt.value for nt in NotificationType}
    missing = enum_keys - spec_keys
    extra = spec_keys - enum_keys
    assert not missing and not extra, (
        f"notification_registry mismatch: missing={sorted(missing)} extra={sorted(extra)}"
    )

    for spec in NOTIFICATION_TYPE_REGISTRY_SPECS:
        rk = spec.get("type_key") or "?"
        assert isinstance(spec.get("emitter_active"), bool), (
            f"notification_registry missing or invalid emitter_active for {rk}"
        )
        assert spec.get("recipients") and str(spec["recipients"]).strip(), (
            f"notification_registry missing recipients for {rk}"
        )
        aud = spec.get("audiences")
        assert aud is not None and isinstance(aud, list), (
            f"notification_registry missing or invalid audiences for {rk}"
        )
        for a in aud:
            assert a in REGISTRY_AUDIENCE_BUCKETS, f"notification_registry invalid audience {a!r} for {rk}"


validate_registry_specs()


def build_notification_settings_delivery_rows(
    ttl_resolver: Callable[[str], int],
    get_priority_for_type: Callable[[str], str],
    gettext_fn: Callable[[str], str],
    merged_audience_rules: Dict[str, Dict[str, bool]],
) -> List[Dict[str, Any]]:
    """
    Rows for System Configuration → Notifications: recipients, TTL, current priority, label.

    ``gettext_fn`` should be ``flask_babel.gettext`` (or equivalent) for translated UI strings.
    """
    from app.services.notification_service import NotificationService
    from app.services.notification.core import get_default_icon_for_notification_type
    from app.models.enums import NotificationType

    nt_by_value = {nt.value: nt for nt in NotificationType}
    rows: List[Dict[str, Any]] = []
    for spec in iter_registry_specs_display_order():
        tk = spec["type_key"]
        nt = nt_by_value.get(tk)
        icon_cls = (
            get_default_icon_for_notification_type(nt)
            if nt is not None
            else "fas fa-bell"
        )
        aud_list = list(spec.get("audiences") or [])
        rules_row = merged_audience_rules.get(tk) or {}
        emitter_active = bool(spec["emitter_active"])
        emitter_status_display = gettext_fn("Active") if emitter_active else gettext_fn("Hypothetical")
        emitter_status_hint = (
            gettext_fn("An in-app notification is created when this event occurs.")
            if emitter_active
            else gettext_fn(
                "Reserved for preferences or future use — the application does not emit this notification type yet."
            )
        )
        rows.append(
            {
                "group": spec["group"],
                "group_display": gettext_fn(spec["group"]),
                "type_key": tk,
                "label": NotificationService._get_translated_notification_type_label(tk),
                "description_display": gettext_fn(spec["description"]),
                "recipients_display": gettext_fn(spec["recipients"]),
                "ttl_days": ttl_resolver(tk),
                "current_priority": get_priority_for_type(tk),
                "icon_class": icon_cls,
                "audiences": aud_list,
                "audience_focal_points": bool(rules_row.get("focal_points")),
                "audience_admin_users": bool(rules_row.get("admin_users")),
                "audience_system_managers": bool(rules_row.get("system_managers")),
                "emitter_active": emitter_active,
                "emitter_status_display": emitter_status_display,
                "emitter_status_hint": emitter_status_hint,
            }
        )
    return rows


def build_registry_rows(ttl_resolver, priority_resolver) -> List[Dict[str, Any]]:
    """
    Rows for the admin template / CSV.

    ttl_resolver(str) -> int  (effective TTL days from config)
    priority_resolver(str) -> str  (default priority from settings)
    """
    rows: List[Dict[str, Any]] = []
    for spec in iter_registry_specs_display_order():
        tk = spec["type_key"]
        rows.append(
            {
                "group": spec["group"],
                "type_key": tk,
                "description": spec["description"],
                "ttl_days": ttl_resolver(tk),
                "default_priority": priority_resolver(tk),
                "emitter_active": bool(spec["emitter_active"]),
            }
        )
    return rows
