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
