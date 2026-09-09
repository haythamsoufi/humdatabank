"""
Request-scoped audit enrichment for the automatic activity middleware.

Most admin mutations are recorded by ``activity_middleware`` without any code in
the view, which keeps coverage complete but leaves the audit row with only the
catalog description and request metadata. A view that knows *what* changed can
call :func:`set_audit_details` (and optionally :func:`set_audit_description`) so
the same single ``UserActivityLog`` row carries reviewer-facing before/after
fields — no second row, unlike calling ``log_admin_action`` from a blueprint the
middleware does not skip.

Keys land in ``UserActivityLog.context_data`` and are rendered by
``app.services.audit.details_service.humanize_audit_details_dict``, so prefer
already-humanized labels and values over raw IDs and enum members.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from flask import g

# ``flask.g`` attribute holding the pending detail fields for this request.
AUDIT_DETAILS_ATTR = "audit_context_extra"

# Marks a row whose description was written by the view rather than the catalog,
# so the audit trail does not replace it with the generic catalog line.
CURATED_DESCRIPTION_KEY = "audit_description_curated"


def set_audit_details(**fields: Any) -> None:
    """Merge reviewer-facing fields into this request's audit row details.

    Safe to call more than once; later calls win for repeated keys. Values that
    are ``None`` or empty are dropped so the Details panel stays hidden when a
    request changed nothing.
    """
    try:
        pending: Dict[str, Any] = dict(getattr(g, AUDIT_DETAILS_ATTR, None) or {})
        for key, value in fields.items():
            if value is None or value == "" or value == [] or value == {}:
                continue
            pending[key] = value
        setattr(g, AUDIT_DETAILS_ATTR, pending)
    except RuntimeError:
        # No request context (background job, shell) — nothing to enrich.
        pass


def set_audit_description(description: Optional[str]) -> None:
    """Replace the catalog description for this request's audit row."""
    if not description or not str(description).strip():
        return
    try:
        g.audit_activity_description = str(description).strip()
    except RuntimeError:
        pass


def apply_audit_details_to_context(
    context_data: Dict[str, Any],
    *,
    description_curated: bool = False,
) -> Dict[str, Any]:
    """Fold view-supplied details into the middleware's ``context_data``.

    View-supplied keys intentionally override middleware-derived ones: the view
    knows the real target of a bulk action, while the middleware can only guess
    from form fields and URL args.
    """
    if not isinstance(context_data, dict):
        return context_data
    try:
        extra = getattr(g, AUDIT_DETAILS_ATTR, None)
    except RuntimeError:
        extra = None
    if isinstance(extra, dict) and extra:
        context_data.update(extra)
    if description_curated:
        context_data[CURATED_DESCRIPTION_KEY] = True
    return context_data


def has_curated_description(context_data: Optional[Dict[str, Any]]) -> bool:
    """True when the stored description was written by the view."""
    if not isinstance(context_data, dict):
        return False
    return bool(context_data.get(CURATED_DESCRIPTION_KEY))
