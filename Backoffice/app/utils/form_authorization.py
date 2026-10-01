# ========== Form Authorization Utilities ==========
"""
Centralized authorization utilities for form access control.
Replaces repeated access control patterns with reusable decorators and helpers.
"""

from functools import wraps
from flask import flash, redirect, url_for, current_app
from flask_login import current_user
from app.models import PublicSubmission
from app.models.assignments import AssignmentEntityStatus
from typing import List, Optional


def redirect_if_assignment_entry_blocked(assigned_form, *, inactive_message: str):
    """Return a dashboard redirect when a deactivated assignment cannot be opened, else None."""
    if assigned_form is None:
        return None
    if not assigned_form.is_entry_allowed:
        flash(inactive_message, "warning")
        return redirect(url_for("main.dashboard"))
    return None


def has_country_access(user, country_id: int) -> bool:
    """
    Centralized access control logic.
    Check if user has access to a specific country.

    Args:
        user: Current user object
        country_id: ID of the country to check access for

    Returns:
        bool: True if user has access, False otherwise
    """
    from app.services.organization.authorization_service import AuthorizationService
    return AuthorizationService.has_country_access(user, country_id)


def can_edit_assignment(assignment_entity_status, user) -> bool:
    """
    Check if user can edit an assignment based on status and role.

    Args:
        assignment_entity_status: AssignmentEntityStatus object
        user: Current user object

    Returns:
        bool: True if user can edit, False otherwise
    """
    from app.services.organization.authorization_service import AuthorizationService
    return AuthorizationService.can_edit_assignment(assignment_entity_status, user)


READONLY_NOTICE_PUBLIC = "public"
READONLY_NOTICE_SENT_FOR_REVIEW = "sent_for_review"
READONLY_NOTICE_APPROVED = "approved"
READONLY_NOTICE_SUBMITTED = "submitted"
READONLY_NOTICE_VIEW_ONLY = "view_only"
READONLY_NOTICE_ROUND_CLOSED = "round_closed"
READONLY_NOTICE_GENERIC = "generic"


def _assignment_status_value(assignment_entity_status) -> str:
    if assignment_entity_status is None:
        return ""
    status = getattr(assignment_entity_status, "status", None)
    if status is None:
        return ""
    return status.value if hasattr(status, "value") else str(status)


def assignment_is_round_closed_for_entity(assignment_entity_status) -> bool:
    """Safely call AssignmentEntityStatus.is_round_closed_for_entity() (a method, not a property)."""
    if assignment_entity_status is None:
        return False
    checker = getattr(assignment_entity_status, "is_round_closed_for_entity", None)
    if not callable(checker):
        return False
    try:
        return bool(checker())
    except Exception:
        return False


def assignment_readonly_notice_reason(
    assignment_entity_status,
    user,
    *,
    is_public_submission: bool = False,
) -> str:
    """Why the entry form is read-only.

    Priority:
      1. Public submission
      2. Workflow lock (sent for review / approved / submitted)
      3. Missing assignment.enter (viewer / documents-only)
      4. Collection round closed for this entity
      5. Generic fallback

    Viewers must not see the closed-round notice: that copy tells data-entry
    users that only an admin can reopen the form, which is misleading when the
    current user could not enter data even on an open assignment.
    """
    if is_public_submission:
        return READONLY_NOTICE_PUBLIC

    status = _assignment_status_value(assignment_entity_status)
    if status == "sent_for_review":
        return READONLY_NOTICE_SENT_FOR_REVIEW
    if status == "approved":
        return READONLY_NOTICE_APPROVED
    if status == "submitted":
        return READONLY_NOTICE_SUBMITTED

    can_enter = False
    if user and getattr(user, "is_authenticated", False) and assignment_entity_status is not None:
        from app.services.organization.authorization_service import AuthorizationService

        scope = {
            "entity_type": getattr(assignment_entity_status, "entity_type", None),
            "entity_id": getattr(assignment_entity_status, "entity_id", None),
            "assigned_form_id": getattr(assignment_entity_status, "assigned_form_id", None),
        }
        assigned_form = getattr(assignment_entity_status, "assigned_form", None)
        if assigned_form is not None:
            scope["template_id"] = getattr(assigned_form, "template_id", None)
        can_enter = AuthorizationService.has_rbac_permission(user, "assignment.enter", scope=scope)

    if not can_enter:
        return READONLY_NOTICE_VIEW_ONLY

    if assignment_is_round_closed_for_entity(assignment_entity_status):
        return READONLY_NOTICE_ROUND_CLOSED

    return READONLY_NOTICE_GENERIC


def check_assignment_access(f):
    """
    Decorator to check if user has access to an assignment.
    Expects the first argument to be aes_id (assignment entity status ID).
    """
    @wraps(f)
    def decorated_function(aes_id, *args, **kwargs):
        try:
            aes = AssignmentEntityStatus.query.get_or_404(aes_id)

            assigned_form = getattr(aes, "assigned_form", None)
            blocked = redirect_if_assignment_entry_blocked(
                assigned_form,
                inactive_message="This assignment is currently inactive and cannot be accessed.",
            )
            if blocked is not None:
                return blocked

            # Check entity access (supports all entity types)
            from app.services.organization.authorization_service import AuthorizationService
            if not AuthorizationService.can_access_assignment(aes, current_user):
                from app.services.organization.entity_service import EntityService
                entity_name = EntityService.get_entity_display_name(aes.entity_type, aes.entity_id)
                current_app.logger.warning(
                    f"Access denied for user {current_user.email} to AssignmentEntityStatus {aes_id} "
                    f"(Entity: {aes.entity_type} {aes.entity_id} - {entity_name}) - entity not assigned to user."
                )
                flash(f"You are not authorized to access this assignment for {entity_name}.", "warning")
                return redirect(url_for("main.dashboard"))

            return f(aes_id, *args, **kwargs)
        except Exception as e:
            current_app.logger.error(f"Error in assignment access check: {e}")
            flash("An error occurred while checking access permissions.", "danger")
            return redirect(url_for("main.dashboard"))

    return decorated_function


def check_assignment_edit_access(f):
    """
    Decorator to check if user can edit an assignment.
    Combines access check with edit permission check.
    """
    @wraps(f)
    def decorated_function(aes_id, *args, **kwargs):
        try:
            aes = AssignmentEntityStatus.query.get_or_404(aes_id)

            assigned_form = getattr(aes, "assigned_form", None)
            blocked = redirect_if_assignment_entry_blocked(
                assigned_form,
                inactive_message="This assignment is currently inactive and cannot be edited.",
            )
            if blocked is not None:
                return blocked

            # Check entity access (supports all entity types)
            from app.services.organization.authorization_service import AuthorizationService
            if not AuthorizationService.can_access_assignment(aes, current_user):
                from app.services.organization.entity_service import EntityService
                entity_name = EntityService.get_entity_display_name(aes.entity_type, aes.entity_id)
                current_app.logger.warning(
                    f"Access denied for user {current_user.email} to AssignmentEntityStatus {aes_id} "
                    f"(Entity: {aes.entity_type} {aes.entity_id} - {entity_name}) - entity not assigned to user."
                )
                flash(f"You are not authorized to access this assignment for {entity_name}.", "warning")
                return redirect(url_for("main.dashboard"))

            # Check edit permissions
            if not can_edit_assignment(aes, current_user):
                from app.utils.api_serialization import _country_for_aes
                aes_country = _country_for_aes(aes)
                entity_display = aes_country.name if aes_country else f"entity {aes.entity_id}"
                flash(
                    f"This assignment for {entity_display} is in '{aes.status}' status and cannot be edited by you at this time.",
                    "warning"
                )
                return redirect(url_for("assignments.view_assignment", aes_id=aes.id))

            return f(aes_id, *args, **kwargs)
        except Exception as e:
            current_app.logger.error(f"Error in assignment edit access check: {e}")
            flash("An error occurred while checking edit permissions.", "danger")
            return redirect(url_for("main.dashboard"))

    return decorated_function


def check_document_access(f):
    """
    Decorator to check access for document operations.
    Handles both assignment documents and public submission documents.
    """
    @wraps(f)
    def decorated_function(document_id, *args, **kwargs):
        try:
            # Import here to avoid circular imports
            from app.models import SubmittedDocument

            # Try to find the document in either table
            document = SubmittedDocument.query.get(document_id)
            if document:
                # Assignment document
                aes = document.assignment_entity_status
                if not aes:
                    flash("Error accessing document.", "danger")
                    return redirect(url_for("main.dashboard"))

                assigned_form = getattr(aes, "assigned_form", None)
                blocked = redirect_if_assignment_entry_blocked(
                    assigned_form,
                    inactive_message="This assignment is currently inactive and documents cannot be accessed.",
                )
                if blocked is not None:
                    return blocked

                # Check assignment access for all entity types (not just countries).
                from app.services.organization.authorization_service import AuthorizationService
                if not AuthorizationService.can_access_assignment(aes, current_user):
                    flash("You are not authorized to access this document.", "warning")
                    return redirect(url_for("main.dashboard"))

                if not can_edit_assignment(aes, current_user):
                    from app.utils.api_serialization import _country_for_aes
                    doc_country = _country_for_aes(aes)
                    entity_label = doc_country.name if doc_country else f"entity {aes.entity_id}"
                    flash(
                        f"This assignment for {entity_label} is in '{aes.status}' status and documents cannot be modified at this time.",
                        "warning"
                    )
                    return redirect(url_for("assignments.view_assignment", aes_id=aes.id))
            else:
                # Document not found - all documents are now in SubmittedDocument table
                flash("Document not found.", "danger")
                return redirect(url_for("main.dashboard"))

            return f(document_id, *args, **kwargs)
        except Exception as e:
            current_app.logger.error(f"Error in document access check: {e}")
            flash("An error occurred while checking document access.", "danger")
            return redirect(url_for("main.dashboard"))

    return decorated_function


# ========== Object-level authorization for child objects ==========
#
# Every object that hangs off an AssignmentEntityStatus (repeat instances, dynamic
# indicators, discussion comments, form data, ...) or a PublicSubmission inherits the
# access rules of its owner. Routes that receive the *child* id must resolve the owner
# and authorize with the right verb instead of relying on @login_required or a coarse
# country check. All of that lives here so routes stay one-liners:
#
#   ctx, err = authorize_child_json(RepeatGroupInstance, instance_id, AES_ACTION_EDIT,
#                                   label="Repeat instance")
#   if err is not None:
#       return err
#
# Verbs map onto AuthorizationService (same rules as the entry form itself):
#   view   -> can_access_assignment
#   edit   -> can_edit_assignment   (status / round / delegation aware)
#   submit -> can_submit_assignment
#
# Error policy:
#   * Child addressed by its own id: missing and out-of-scope are indistinguishable (404);
#     a caller who may view but not perform the verb gets 403.
#   * Assignment addressed by id in the request (AES-scoped endpoints): 403 with the
#     generic "Assignment not found or access denied" message, as ensure_aes_access did.

AES_ACTION_VIEW = "view"
AES_ACTION_EDIT = "edit"
AES_ACTION_SUBMIT = "submit"
PUBLIC_SUBMISSION_ACTION_VIEW = "view"
PUBLIC_SUBMISSION_ACTION_EDIT = "edit"
PUBLIC_SUBMISSION_ACTION_MANAGE = "manage"

AUTH_OK = "ok"
AUTH_HIDDEN = "hidden"
AUTH_FORBIDDEN = "forbidden"

ASSIGNMENT_NOT_FOUND_MESSAGE = "Assignment not found or access denied"

_PUBLIC_SUBMISSION_MANAGE_PERMISSION = "admin.assignments.public_submissions.manage"


def aes_action_allowed(aes, user, action: str = AES_ACTION_VIEW) -> bool:
    """True when ``user`` may perform ``action`` (view/edit/submit) on ``aes``."""
    from app.services.organization.authorization_service import AuthorizationService

    if aes is None or user is None:
        return False
    if action == AES_ACTION_VIEW:
        return AuthorizationService.can_access_assignment(aes, user)
    if action == AES_ACTION_EDIT:
        return AuthorizationService.can_edit_assignment(aes, user)
    if action == AES_ACTION_SUBMIT:
        return AuthorizationService.can_submit_assignment(aes, user)
    raise ValueError(f"Unknown assignment action: {action!r}")


def check_aes_action(aes, user, action: str = AES_ACTION_VIEW) -> str:
    """Tri-state decision: ``AUTH_OK``, ``AUTH_HIDDEN`` (cannot even view) or ``AUTH_FORBIDDEN``."""
    if aes is None or not aes_action_allowed(aes, user, AES_ACTION_VIEW):
        return AUTH_HIDDEN
    if action != AES_ACTION_VIEW and not aes_action_allowed(aes, user, action):
        return AUTH_FORBIDDEN
    return AUTH_OK


def load_aes_for_user(aes_id, user, action: str = AES_ACTION_VIEW):
    """Return the AES when ``user`` may perform ``action`` on it, else ``None``.

    For non-response contexts (HTML redirects, optional request hints such as an
    ``aes_id`` query parameter) where the caller only needs allowed-or-not.
    """
    try:
        aes_pk = int(aes_id)
    except (TypeError, ValueError):
        return None
    from app.extensions import db

    aes = db.session.get(AssignmentEntityStatus, aes_pk)
    if check_aes_action(aes, user, action) != AUTH_OK:
        return None
    return aes


def authorize_aes_json(aes_id, action: str = AES_ACTION_EDIT, *, forbidden_message: Optional[str] = None):
    """JSON guard for endpoints that receive an assignment id in the request.

    Returns ``(aes, None)`` on success or ``(None, response)``.
    """
    from app.extensions import db
    from app.utils.api_responses import json_forbidden, json_not_found

    try:
        aes_pk = int(aes_id)
    except (TypeError, ValueError):
        return None, json_not_found(ASSIGNMENT_NOT_FOUND_MESSAGE)

    aes = db.session.get(AssignmentEntityStatus, aes_pk)
    decision = check_aes_action(aes, current_user, action)
    # Hidden and missing assignments share 404 so callers cannot tell them apart.
    if decision == AUTH_HIDDEN:
        return None, json_not_found(ASSIGNMENT_NOT_FOUND_MESSAGE)
    if decision == AUTH_FORBIDDEN:
        return None, json_forbidden(forbidden_message or "You cannot modify this assignment")
    return aes, None


def public_submission_access(submission, user, action: str = PUBLIC_SUBMISSION_ACTION_VIEW) -> str:
    """Tri-state decision for a PublicSubmission.

    view   -> System Manager, ``admin.assignments.public_submissions.manage`` or access to the
              submission's country.
    edit   -> manage permission, or country access plus ``assignment.enter``.
    manage -> System Manager or the manage permission (approve / reject / delete / status).
    """
    from app.services.organization.authorization_service import AuthorizationService

    if submission is None or user is None or not getattr(user, "is_authenticated", False):
        return AUTH_HIDDEN

    can_manage = AuthorizationService.is_system_manager(user) or AuthorizationService.has_rbac_permission(
        user, _PUBLIC_SUBMISSION_MANAGE_PERMISSION
    )
    country_ok = can_manage or AuthorizationService.has_country_access(user, submission.country_id)
    if not country_ok:
        return AUTH_HIDDEN
    if action == PUBLIC_SUBMISSION_ACTION_VIEW or can_manage:
        return AUTH_OK
    if action == PUBLIC_SUBMISSION_ACTION_EDIT and AuthorizationService.has_rbac_permission(user, "assignment.enter"):
        return AUTH_OK
    return AUTH_FORBIDDEN


class ChildAccess:
    """Resolved owner of a child object after a successful authorization."""

    __slots__ = ("obj", "aes", "public_submission")

    def __init__(self, obj, aes=None, public_submission=None):
        self.obj = obj
        self.aes = aes
        self.public_submission = public_submission


def resolve_child_owner(obj):
    """Return ``(aes, public_submission)`` that own ``obj`` (either may be ``None``)."""
    aes = getattr(obj, "assignment_entity_status", None)
    if aes is None and getattr(obj, "assignment_entity_status_id", None):
        from app.extensions import db

        aes = db.session.get(AssignmentEntityStatus, obj.assignment_entity_status_id)
    submission = None
    if aes is None and getattr(obj, "public_submission_id", None):
        submission = getattr(obj, "public_submission", None)
        if submission is None:
            from app.extensions import db

            submission = db.session.get(PublicSubmission, obj.public_submission_id)
    return aes, submission


def authorize_child(obj, user, action: str = AES_ACTION_EDIT) -> str:
    """Tri-state decision for ``action`` on a child object via its owning AES / public submission."""
    from app.services.organization.authorization_service import AuthorizationService

    aes, submission = resolve_child_owner(obj)
    if aes is not None:
        return check_aes_action(aes, user, action)
    if submission is not None:
        ps_action = PUBLIC_SUBMISSION_ACTION_VIEW if action == AES_ACTION_VIEW else PUBLIC_SUBMISSION_ACTION_EDIT
        return public_submission_access(submission, user, ps_action)
    # Orphans have no owner to inherit rules from: only the RBAC superuser may touch them.
    return AUTH_OK if AuthorizationService.is_system_manager(user) else AUTH_HIDDEN


def authorize_child_json(model, object_id, action: str = AES_ACTION_EDIT, *, label: str = "Item"):
    """Load ``model`` by primary key and authorize ``action`` against its owning assignment.

    Returns ``(ChildAccess, None)`` on success or ``(None, response)`` where the response is
    404 (missing or outside the caller's scope) / 403 (visible but verb not permitted).
    """
    from app.extensions import db
    from app.utils.api_responses import json_forbidden, json_not_found

    obj = db.session.get(model, object_id)
    if obj is None:
        return None, json_not_found(f"{label} not found")

    decision = authorize_child(obj, current_user, action)
    if decision == AUTH_HIDDEN:
        return None, json_not_found(f"{label} not found")
    if decision == AUTH_FORBIDDEN:
        return None, json_forbidden(f"You cannot modify this {label.lower()}")

    aes, submission = resolve_child_owner(obj)
    return ChildAccess(obj, aes=aes, public_submission=submission), None


AES_LOCK_UNCHANGED = "unchanged"
AES_LOCK_CHANGED = "changed"
AES_LOCK_GONE = "gone"

TRANSITION_OK = "ok"
TRANSITION_GONE = "gone"
TRANSITION_STALE = "stale_status"
TRANSITION_FORBIDDEN = "forbidden"


def _naive_timestamp(value):
    if value is None or getattr(value, "tzinfo", None) is None:
        return value
    return value.replace(tzinfo=None)


def _lock_aes_row(aes) -> str:
    """Take ``SELECT ... FOR UPDATE`` on the row behind ``aes`` and reload ``aes`` if it moved.

    Under READ COMMITTED a lock that had to wait returns the latest committed row version,
    so comparing status and status timestamp with the in-memory instance reveals whether
    another transaction transitioned it after this request loaded it.
    """
    from app.extensions import db
    from sqlalchemy import select

    before = (_assignment_status_value(aes), _naive_timestamp(getattr(aes, "status_timestamp", None)))
    row = db.session.execute(
        select(AssignmentEntityStatus.status, AssignmentEntityStatus.status_timestamp)
        .where(AssignmentEntityStatus.id == aes.id)
        .with_for_update()
    ).one_or_none()
    if row is None:
        return AES_LOCK_GONE
    current_status = row[0].value if hasattr(row[0], "value") else str(row[0])
    if (current_status, _naive_timestamp(row[1])) == before:
        return AES_LOCK_UNCHANGED
    db.session.refresh(aes)
    return AES_LOCK_CHANGED


def require_aes_write_lock(aes, action: str = AES_ACTION_EDIT):
    """Lock ``aes`` before a data write. Returns a JSON error response, or ``None`` when the lock is held.

    A vanished row is 404. A row whose status moved out of the caller's edit rights is 409.
    A status change that is still editable is refreshed and the caller may continue.
    """
    from flask_login import current_user
    from app.utils.api_responses import json_error, json_not_found

    if aes is None:
        return json_not_found(ASSIGNMENT_NOT_FOUND_MESSAGE)
    outcome = _lock_aes_row(aes)
    if outcome == AES_LOCK_GONE:
        return json_not_found(ASSIGNMENT_NOT_FOUND_MESSAGE)
    if outcome == AES_LOCK_CHANGED and check_aes_action(aes, current_user, action) != AUTH_OK:
        return json_error("This assignment changed and can no longer be edited.", 409)
    return None


def lock_public_submission(submission_id):
    """Return the public submission row locked for update, or ``None`` when it does not exist."""
    from sqlalchemy import select
    from app.extensions import db

    try:
        pk = int(submission_id)
    except (TypeError, ValueError):
        return None
    return db.session.execute(
        select(PublicSubmission).where(PublicSubmission.id == pk).with_for_update()
    ).scalar_one_or_none()


def lock_aes_for_update(aes) -> bool:
    """Take a row lock on ``aes`` and reload it. Returns True if it changed (or vanished) meanwhile.

    Workflow transitions must serialize on the assignment row, otherwise two concurrent
    requests both pass the "allowed from this status" check and transition twice (double
    notifications, double audit rows, approve over a just-reopened form). The lock lasts
    until the request transaction ends (transaction middleware commit / rollback), so call
    it immediately before the transition and never commit between the lock and the write.
    Callers that must also re-validate use ``begin_aes_transition``.
    """
    return _lock_aes_row(aes) != AES_LOCK_UNCHANGED


def lock_aes_rows_for_update(ids, *, assigned_form_id: Optional[int] = None) -> list:
    """Lock several AES rows in ascending id order and return them freshly loaded.

    Every bulk path must go through here: two bulk requests over overlapping sets would
    otherwise lock in different orders and deadlock. Lock order across tables is always
    AssignmentEntityStatus first, then AssignmentPageStatus / child rows.
    """
    from app.extensions import db
    from sqlalchemy import select

    unique_ids = sorted({int(i) for i in ids})
    if not unique_ids:
        return []
    stmt = select(AssignmentEntityStatus).where(AssignmentEntityStatus.id.in_(unique_ids))
    if assigned_form_id is not None:
        stmt = stmt.where(AssignmentEntityStatus.assigned_form_id == assigned_form_id)
    stmt = (
        stmt.order_by(AssignmentEntityStatus.id)
        .with_for_update(of=AssignmentEntityStatus)
        .execution_options(populate_existing=True)
    )
    return list(db.session.execute(stmt).scalars().all())


class AesTransition:
    """Outcome of ``begin_aes_transition``; ``ok`` means the caller holds the lock and may write."""

    __slots__ = ("reason", "status", "changed")

    def __init__(self, reason: str, status: str, changed: bool = False):
        self.reason = reason
        self.status = status
        self.changed = changed

    @property
    def ok(self) -> bool:
        return self.reason == TRANSITION_OK

    def __bool__(self) -> bool:
        return self.ok


def begin_aes_transition(aes, user, *, permission=None, allowed_from=None) -> AesTransition:
    """Lock ``aes`` and re-validate the transition against the locked, current row.

    ``permission`` is an ``AuthorizationService.can_*`` style callable ``(aes, user) -> bool``
    evaluated after the lock so that status-dependent predicates see the fresh status.
    ``allowed_from`` is an optional iterable of source statuses (enum members or strings).
    """
    state = _lock_aes_row(aes)
    changed = state == AES_LOCK_CHANGED
    if state == AES_LOCK_GONE:
        return AesTransition(TRANSITION_GONE, "", True)
    current = _assignment_status_value(aes)
    if allowed_from is not None:
        allowed = {s.value if hasattr(s, "value") else str(s) for s in allowed_from}
        if current not in allowed:
            return AesTransition(TRANSITION_STALE, current, changed)
    if permission is not None and not permission(aes, user):
        return AesTransition(TRANSITION_FORBIDDEN, current, changed)
    return AesTransition(TRANSITION_OK, current, changed)


_LOOKUP_LIST_ADMIN_PERMISSIONS = (
    "admin.templates.view",
    "admin.templates.edit",
    "admin.templates.create",
    "admin.assignments.view",
    "admin.assignments.edit",
)


def _has_template_admin_permission(user) -> bool:
    from app.services.organization.authorization_service import AuthorizationService

    if AuthorizationService.is_system_manager(user):
        return True
    return any(AuthorizationService.has_rbac_permission(user, code) for code in _LOOKUP_LIST_ADMIN_PERMISSIONS)


def _reachable_template_filters(user, template_column) -> list:
    """SQL filters restricting ``template_column`` to templates the non-admin ``user`` can reach.

    Reachable means: assigned for one of the user's entities (needs ``assignment.view``), or
    owned by / shared with the user (``get_user_allowed_template_ids``).
    """
    from app.models.assignments import AssignedForm
    from app.models.core import UserEntityPermission
    from app.services.organization.authorization_service import AuthorizationService
    from app.services.security.api_authentication import get_user_allowed_template_ids
    from sqlalchemy import and_, select

    filters = []
    if AuthorizationService.has_rbac_permission(user, "assignment.view"):
        entity_templates = (
            select(AssignedForm.template_id)
            .join(AssignmentEntityStatus, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
            .join(
                UserEntityPermission,
                and_(
                    UserEntityPermission.entity_type == AssignmentEntityStatus.entity_type,
                    UserEntityPermission.entity_id == AssignmentEntityStatus.entity_id,
                    UserEntityPermission.user_id == user.id,
                ),
            )
        )
        filters.append(template_column.in_(entity_templates))

    owned_or_shared = get_user_allowed_template_ids(user.id)
    if owned_or_shared:
        filters.append(template_column.in_(owned_or_shared))
    return filters


def user_can_access_template(user, template_id) -> bool:
    """Whether ``user`` may read the structure of template ``template_id``.

    System Managers and template/assignment admins may read any template; everyone else
    needs an assignment for one of their entities or template ownership/share.
    """
    from app.extensions import db
    from app.models import FormTemplate
    from sqlalchemy import or_

    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if _has_template_admin_permission(user):
        return True
    filters = _reachable_template_filters(user, FormTemplate.id)
    if not filters:
        return False
    return db.session.query(
        db.session.query(FormTemplate.id)
        .filter(FormTemplate.id == template_id, or_(*filters))
        .exists()
    ).scalar() is True


def user_can_read_lookup_list(user, list_id) -> bool:
    """Whether ``user`` may read the rows of an admin-managed (numeric-id) lookup list.

    Lookup lists are global reference data with no owner column, so access is derived from
    use: the list must be referenced by a (non-archived) form item of a template the user
    can reach - via an assignment for one of their entities, or template ownership/share -
    unless the user is a System Manager or holds a template/assignment admin permission
    (form builder, assignment admins).
    """
    from app.extensions import db
    from app.models import FormItem
    from sqlalchemy import or_

    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if _has_template_admin_permission(user):
        return True

    list_key = str(list_id).strip()
    if not list_key:
        return False

    template_filters = _reachable_template_filters(user, FormItem.template_id)
    if not template_filters:
        return False

    referenced = db.session.query(FormItem.id).filter(
        FormItem.lookup_list_id == list_key,
        FormItem.archived.is_(False),
        or_(*template_filters),
    )
    return db.session.query(referenced.exists()).scalar() is True


def validate_country_list_access(user, country_ids: List[int]) -> List[int]:
    """
    Validate and filter a list of country IDs based on user access.

    Args:
        user: Current user object
        country_ids: List of country IDs to validate

    Returns:
        List of country IDs the user has access to
    """
    from app.services.organization.authorization_service import AuthorizationService
    return AuthorizationService.validate_country_list_access(user, country_ids)


def check_self_report_access(assignment_entity_status, user) -> bool:
    """
    Check if user can access/modify a self-report assignment.

    Args:
        assignment_entity_status: AssignmentEntityStatus object
        user: Current user object

    Returns:
        bool: True if user has access, False otherwise
    """
    from app.services.organization.authorization_service import AuthorizationService
    return AuthorizationService.check_self_report_access(assignment_entity_status, user)
