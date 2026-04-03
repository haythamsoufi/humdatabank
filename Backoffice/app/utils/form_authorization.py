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
    from app.services.authorization_service import AuthorizationService
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
    from app.services.authorization_service import AuthorizationService
    return AuthorizationService.can_edit_assignment(assignment_entity_status, user)


def check_assignment_access(f):
    """
    Decorator to check if user has access to an assignment.
    Expects the first argument to be aes_id (assignment entity status ID).
    """
    @wraps(f)
    def decorated_function(aes_id, *args, **kwargs):
        try:
            aes = AssignmentEntityStatus.query.get_or_404(aes_id)

            # Deactivated assignment guard: treat inactive assignments as unavailable in focal-point flows
            assigned_form = getattr(aes, "assigned_form", None)
            if assigned_form is not None and getattr(assigned_form, "is_active", True) is False:
                flash("This assignment is currently inactive and cannot be accessed.", "warning")
                return redirect(url_for("main.dashboard"))

            # Check entity access (supports all entity types)
            from app.services.authorization_service import AuthorizationService
            if not AuthorizationService.can_access_assignment(aes, current_user):
                from app.services.entity_service import EntityService
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

            # Deactivated assignment guard: prevent edits/submissions when assignment is inactive
            assigned_form = getattr(aes, "assigned_form", None)
            if assigned_form is not None and getattr(assigned_form, "is_active", True) is False:
                flash("This assignment is currently inactive and cannot be edited.", "warning")
                return redirect(url_for("main.dashboard"))

            # Check entity access (supports all entity types)
            from app.services.authorization_service import AuthorizationService
            if not AuthorizationService.can_access_assignment(aes, current_user):
                from app.services.entity_service import EntityService
                entity_name = EntityService.get_entity_display_name(aes.entity_type, aes.entity_id)
                current_app.logger.warning(
                    f"Access denied for user {current_user.email} to AssignmentEntityStatus {aes_id} "
                    f"(Entity: {aes.entity_type} {aes.entity_id} - {entity_name}) - entity not assigned to user."
                )
                flash(f"You are not authorized to access this assignment for {entity_name}.", "warning")
                return redirect(url_for("main.dashboard"))

            # Check edit permissions
            if not can_edit_assignment(aes, current_user):
                flash(
                    f"This assignment for {aes.country.name} is in '{aes.status}' status and cannot be edited by you at this time.",
                    "warning"
                )
                return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes.id))

            return f(aes_id, *args, **kwargs)
        except Exception as e:
            current_app.logger.error(f"Error in assignment edit access check: {e}")
            flash("An error occurred while checking edit permissions.", "danger")
            return redirect(url_for("main.dashboard"))

    return decorated_function


def admin_required(f):
    """
    Backwards-compatible alias for the admin decorator.

    IMPORTANT: Keep a single source of truth for "admin_required" behavior.
    Use the implementation in `app/routes/admin/shared.py`.
    """
    from app.routes.admin.shared import admin_required as _admin_required
    return _admin_required(f)


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

                # Deactivated assignment guard
                assigned_form = getattr(aes, "assigned_form", None)
                if assigned_form is not None and getattr(assigned_form, "is_active", True) is False:
                    flash("This assignment is currently inactive and documents cannot be accessed.", "warning")
                    return redirect(url_for("main.dashboard"))

                # Get country_id from entity_id when entity_type is 'country'
                country_id = aes.entity_id if aes.entity_type == 'country' else None
                if not country_id or not has_country_access(current_user, country_id):
                    flash("You are not authorized to access this document.", "warning")
                    return redirect(url_for("main.dashboard"))

                if not can_edit_assignment(aes, current_user):
                    flash(
                        f"This assignment for {aes.country.name} is in '{aes.status}' status and documents cannot be modified at this time.",
                        "warning"
                    )
                    return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes.id))
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
    from app.services.authorization_service import AuthorizationService
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
    from app.services.authorization_service import AuthorizationService
    return AuthorizationService.check_self_report_access(assignment_entity_status, user)
