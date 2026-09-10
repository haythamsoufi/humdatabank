"""
Reviewer-facing audit details for assignment admin mutations.

``assignment_management`` relies on the automatic activity middleware for its
audit rows, so without help a row records only the catalog description ("Updated
an assignment") and request metadata — never which assignment, nor what changed.

These helpers turn the mutations performed by ``edit_assignment`` and
``bulk_update_entity_status`` into labelled ``before → after`` lines that
``details_service.humanize_audit_details_dict`` renders in the Details panel,
plus a one-line description naming the assignment and the affected fields.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.models.assignments import SUBMISSION_REVIEW_RECIPIENT_SPECIFIC
from app.models.enums import status_display_label

# Bulk status updates can span every country in the platform; keep the stored
# JSON and the Details panel bounded.
MAX_AUDIT_CHANGE_LINES = 40

EMPTY_VALUE_TEXT = "—"

# Lowercase plurals for descriptions ("for 3 countries in …"). EntityService
# labels are Title Case singulars, which do not read well mid-sentence.
_ENTITY_TYPE_PLURALS = {
    "country": "countries",
    "national_society": "National Societies",
    "ns_branch": "NS branches",
    "ns_subbranch": "NS sub-branches",
    "ns_localunit": "NS local units",
    "division": "Secretariat divisions",
    "department": "Secretariat departments",
    "regional_office": "regional offices",
    "cluster_office": "cluster offices",
}

_ASSIGNMENT_FIELD_LABELS: Dict[str, str] = {
    "template": "Form template",
    "period_name": "Reporting period",
    "custom_name": "Custom name",
    "expiry_date": "Expiry date",
    "data_owner": "Data owner",
    "requires_delegation_review": "Delegation review required",
    "enable_export_excel": "Excel export",
    "enable_import_excel": "Excel import",
    "enable_export_pdf": "PDF export",
    "submission_review_mode": "Submission review notification",
    "submission_review_recipients": "Submission review recipients",
}


def _date_text(value: Any) -> Optional[str]:
    """ISO date for date/datetime columns; None when unset."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _value_text(value: Any) -> str:
    """Display text for one side of a before/after pair."""
    if value is None or value == "" or value == []:
        return EMPTY_VALUE_TEXT
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value if str(v).strip()) or EMPTY_VALUE_TEXT
    return str(value)


def _change_line(label: str, before: Any, after: Any) -> str:
    return f"{label}: {_value_text(before)} → {_value_text(after)}"


def _cap_lines(lines: Sequence[str]) -> List[str]:
    if len(lines) <= MAX_AUDIT_CHANGE_LINES:
        return list(lines)
    hidden = len(lines) - MAX_AUDIT_CHANGE_LINES
    return [*lines[:MAX_AUDIT_CHANGE_LINES], f"… and {hidden} more"]


def _user_label(user: Any) -> Optional[str]:
    if user is None:
        return None
    name = (getattr(user, "name", "") or "").strip()
    email = (getattr(user, "email", "") or "").strip()
    if name and email:
        return f"{name} ({email})"
    return name or email or f"User #{getattr(user, 'id', '?')}"


def _submission_review_mode_label(mode: Optional[str]) -> str:
    if mode == SUBMISSION_REVIEW_RECIPIENT_SPECIFIC:
        return "Specific IFRC admin(s)"
    return "Designated FDS member for the submitting country"


def assignment_audit_label(assignment: Any) -> Optional[str]:
    """Stable, human-readable assignment name for the audit row.

    Deliberately not ``AssignedForm.display_name``: that is locale-aware, and an
    audit row should read the same for every reviewer.
    """
    if assignment is None:
        return None
    custom = (getattr(assignment, "custom_name", "") or "").strip()
    period = (getattr(assignment, "period_name", "") or "").strip()
    template_name = _template_name(assignment) or ""
    if custom:
        return f"{custom} ({period})" if period else custom
    if template_name and period:
        return f"{template_name} \u2013 {period}"
    return template_name or period or f"Assignment #{getattr(assignment, 'id', '?')}"


def _template_name(assignment: Any) -> Optional[str]:
    """Template name for the assignment's current ``template_id``.

    Assigning ``template_id`` directly leaves the loaded ``template``
    relationship pointing at the previous row, so trust the FK and fall back to
    a lookup (normally an identity-map hit) when the two disagree.
    """
    if assignment is None:
        return None
    template_id = getattr(assignment, "template_id", None)
    template = getattr(assignment, "template", None)
    if template is not None and getattr(template, "id", None) == template_id:
        return (getattr(template, "name", "") or "").strip() or None
    if not template_id:
        return None
    try:
        from app.models import FormTemplate

        row = FormTemplate.query.get(template_id)
    except Exception:
        return None
    return (getattr(row, "name", "") or "").strip() or None


def _data_owner_label(assignment: Any) -> Optional[str]:
    """Data owner display label, resolved from ``data_owner_id`` (see _template_name)."""
    if assignment is None:
        return None
    owner_id = getattr(assignment, "data_owner_id", None)
    owner = getattr(assignment, "data_owner_user", None)
    if owner is not None and getattr(owner, "id", None) == owner_id:
        return _user_label(owner)
    if not owner_id:
        return None
    try:
        from app.models import User

        return _user_label(User.query.get(owner_id))
    except Exception:
        return None


def _entity_noun(entity_types: Iterable[str], count: int) -> str:
    """"countries" / "NS branches" / "entities" for mixed selections."""
    distinct = {t for t in entity_types if t}
    if len(distinct) != 1:
        return "entity" if count == 1 else "entities"
    entity_type = next(iter(distinct))
    if count == 1:
        from app.services.organization.entity_service import EntityService

        try:
            return (EntityService.get_entity_type_label(entity_type) or entity_type).lower()
        except Exception:
            return entity_type.replace("_", " ")
    return _ENTITY_TYPE_PLURALS.get(entity_type, f"{entity_type.replace('_', ' ')}s")


# ---------------------------------------------------------------------------
# edit_assignment
# ---------------------------------------------------------------------------

def assignment_settings_snapshot(assignment: Any) -> Dict[str, Any]:
    """Assignment-level state compared before and after an ``edit_assignment`` POST.

    Only fields the edit form can actually change are captured, so an unrelated
    background update never shows up as an admin edit.
    """
    if assignment is None:
        return {}
    recipients = []
    try:
        recipients = [
            label
            for label in (
                _user_label(u) for u in (assignment.submission_review_recipient_users or [])
            )
            if label
        ]
    except Exception:
        recipients = []
    return {
        "template": _template_name(assignment),
        "period_name": (getattr(assignment, "period_name", "") or "").strip() or None,
        "custom_name": (getattr(assignment, "custom_name", "") or "").strip() or None,
        "custom_name_translations": dict(getattr(assignment, "custom_name_translations", None) or {}),
        "expiry_date": _date_text(getattr(assignment, "expiry_date", None)),
        "data_owner": _data_owner_label(assignment),
        "requires_delegation_review": bool(getattr(assignment, "requires_delegation_review", False)),
        "enable_export_excel": bool(getattr(assignment, "enable_export_excel", False)),
        "enable_import_excel": bool(getattr(assignment, "enable_import_excel", False)),
        "enable_export_pdf": bool(getattr(assignment, "enable_export_pdf", False)),
        "submission_review_mode": _submission_review_mode_label(
            getattr(assignment, "submission_review_recipient_mode", None)
        ),
        "submission_review_recipients": sorted(recipients),
    }


def country_due_dates_snapshot(assignment: Any) -> Optional[str]:
    """Display text for the due date currently shared by the assignment's countries.

    ``edit_assignment`` applies one due date to every country row, so a single
    value is the normal case; pre-existing divergence is reported as "mixed".
    """
    try:
        rows = assignment.country_statuses.all()
        values = sorted({_date_text(row.due_date) or EMPTY_VALUE_TEXT for row in rows})
    except Exception:
        return None
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return f"mixed ({', '.join(values)})"


def _translation_change_lines(
    before: Dict[str, Any],
    after: Dict[str, Any],
) -> List[str]:
    lines: List[str] = []
    for code in sorted(set(before) | set(after)):
        old = (before.get(code) or "").strip()
        new = (after.get(code) or "").strip()
        if old == new:
            continue
        lines.append(_change_line(f"Custom name ({code})", old or None, new or None))
    return lines


def build_assignment_update_audit(
    assignment: Any,
    before: Dict[str, Any],
    after: Dict[str, Any],
    *,
    country_due_date_before: Optional[str] = None,
    country_due_date_after: Optional[str] = None,
) -> Tuple[Dict[str, Any], str]:
    """Return ``(details, description)`` for an ``edit_assignment`` POST."""
    lines: List[str] = []
    changed_labels: List[str] = []

    for key, label in _ASSIGNMENT_FIELD_LABELS.items():
        old = before.get(key)
        new = after.get(key)
        if old == new:
            continue
        lines.append(_change_line(label, old, new))
        changed_labels.append(label)

    translation_lines = _translation_change_lines(
        before.get("custom_name_translations") or {},
        after.get("custom_name_translations") or {},
    )
    if translation_lines:
        lines.extend(translation_lines)
        changed_labels.append("Custom name translations")

    if country_due_date_after is not None and country_due_date_before != country_due_date_after:
        lines.append(
            _change_line("Due date (all countries)", country_due_date_before, country_due_date_after)
        )
        changed_labels.append("Due date")

    assignment_title = assignment_audit_label(assignment)
    details: Dict[str, Any] = {
        "assignment_title": assignment_title,
        "template_name": after.get("template") or before.get("template"),
        "changes": _cap_lines(lines) if lines else ["No assignment fields changed"],
    }

    # Keep the catalog description ("Updated an assignment") as a prefix so the
    # audit trail treats this line as a richer version of the catalog default.
    quoted = f" '{assignment_title}'" if assignment_title else ""
    if changed_labels:
        description = f"Updated an assignment{quoted}: changed {', '.join(changed_labels)}"
    else:
        description = f"Updated an assignment{quoted}: no fields changed"
    return details, description


# ---------------------------------------------------------------------------
# bulk_update_entity_status
# ---------------------------------------------------------------------------

def build_entity_status_update_audit(
    assignment: Any,
    changes: Sequence[Dict[str, Any]],
    *,
    new_status: Any,
    new_due_date: Any = None,
) -> Tuple[Dict[str, Any], str]:
    """Return ``(details, description)`` for a bulk entity-status update.

    ``changes`` entries describe one ``AssignmentEntityStatus`` row each:
    ``name``, ``entity_type``, ``status_before``, ``status_after``,
    ``due_before`` and ``due_after``.
    """
    status_label = status_display_label(new_status)
    due_date_text = _date_text(new_due_date)

    status_lines: List[str] = []
    unchanged_names: List[str] = []
    due_lines: List[str] = []

    for change in changes:
        name = change.get("name") or f"Entity #{change.get('entity_id', '?')}"
        before_label = status_display_label(change.get("status_before"))
        after_label = status_display_label(change.get("status_after"))
        if before_label == after_label:
            unchanged_names.append(name)
        else:
            status_lines.append(_change_line(name, before_label, after_label))
        due_before = _date_text(change.get("due_before"))
        due_after = _date_text(change.get("due_after"))
        if due_date_text is not None and due_before != due_after:
            due_lines.append(_change_line(name, due_before, due_after))

    noun = _entity_noun((c.get("entity_type") for c in changes), len(changes))
    details: Dict[str, Any] = {
        "assignment_title": assignment_audit_label(assignment),
        "template_name": _template_name(assignment),
        "new_status": status_label,
        "entities_updated": len(changes),
        "status_changes": _cap_lines(status_lines),
    }
    if unchanged_names:
        details["already_at_this_status"] = _cap_lines(sorted(unchanged_names))
    if due_date_text is not None:
        details["new_due_date"] = due_date_text
        details["due_date_changes"] = _cap_lines(due_lines)

    assignment_title = assignment_audit_label(assignment)
    if len(changes) == 1:
        target = changes[0].get("name") or noun
    else:
        target = f"{len(changes)} {noun}"
    description = f"Updated assignment status to {status_label} for {target}"
    if assignment_title:
        description += f" in '{assignment_title}'"
    if due_date_text is not None:
        description += f" (due date set to {due_date_text})"
    return details, description
