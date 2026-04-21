"""
Assignment Service - Centralized service for assignment-related database operations.

This service provides a unified interface for AssignmentEntityStatus and AssignedForm queries,
replacing direct database queries in route handlers.
"""

from typing import Optional, List
from app.models import AssignmentEntityStatus, AssignedForm
from app import db


class AssignmentService:
    """Service class for assignment operations."""

    @staticmethod
    def get_assignment_entity_status_by_id(aes_id: int) -> Optional[AssignmentEntityStatus]:
        """Get an AssignmentEntityStatus by ID.

        Args:
            aes_id: AssignmentEntityStatus ID

        Returns:
            AssignmentEntityStatus instance or None if not found
        """
        return AssignmentEntityStatus.query.get(aes_id)

    @staticmethod
    def get_assignment_entity_status_or_404(aes_id: int) -> AssignmentEntityStatus:
        """Get an AssignmentEntityStatus by ID or raise 404.

        Args:
            aes_id: AssignmentEntityStatus ID

        Returns:
            AssignmentEntityStatus instance

        Raises:
            404 if not found
        """
        from flask import abort
        aes = AssignmentEntityStatus.query.get(aes_id)
        if not aes:
            abort(404)
        return aes

    @staticmethod
    def get_assigned_form_by_id(assignment_id: int) -> Optional[AssignedForm]:
        """Get an AssignedForm by ID.

        Args:
            assignment_id: AssignedForm ID

        Returns:
            AssignedForm instance or None if not found
        """
        return AssignedForm.query.get(assignment_id)

    @staticmethod
    def get_assigned_form_or_404(assignment_id: int) -> AssignedForm:
        """Get an AssignedForm by ID or raise 404.

        Args:
            assignment_id: AssignedForm ID

        Returns:
            AssignedForm instance

        Raises:
            404 if not found
        """
        from flask import abort
        assignment = AssignedForm.query.get(assignment_id)
        if not assignment:
            abort(404)
        return assignment

    @staticmethod
    def get_assigned_form_by_token(token: str) -> Optional[AssignedForm]:
        """Get an AssignedForm by unique token.

        Args:
            token: Unique token string

        Returns:
            AssignedForm instance or None if not found
        """
        return AssignedForm.query.filter_by(unique_token=str(token)).first()

    @staticmethod
    def get_all_assigned_forms(ordered: bool = True, order_by: str = 'period_name'):
        """Get all assigned forms.

        Args:
            ordered: If True, order results
            order_by: Field to order by ('period_name' or 'assigned_at')

        Returns:
            Query object for assigned forms
        """
        query = AssignedForm.query
        if ordered:
            if order_by == 'assigned_at':
                query = query.order_by(AssignedForm.assigned_at.desc())
            else:
                query = query.order_by(AssignedForm.period_name.desc())
        return query

    @staticmethod
    def get_assigned_forms_by_template(template_id: int):
        """Get all assigned forms for a template.

        Args:
            template_id: Template ID

        Returns:
            Query object filtered by template_id
        """
        return AssignedForm.query.filter_by(template_id=template_id)

    @staticmethod
    def count_assigned_forms() -> int:
        """Get total count of assigned forms.

        Returns:
            Total count of assigned forms
        """
        return AssignedForm.query.count()

    @staticmethod
    def get_assignment_entity_statuses_by_assigned_form(assigned_form_id: int):
        """Get all AssignmentEntityStatus entries for an assigned form.

        Args:
            assigned_form_id: AssignedForm ID

        Returns:
            Query object filtered by assigned_form_id
        """
        return AssignmentEntityStatus.query.filter_by(assigned_form_id=assigned_form_id)

    @staticmethod
    def get_assignment_entity_statuses_by_country(country_id: int):
        """Get all AssignmentEntityStatus entries for a country.

        Args:
            country_id: Country ID

        Returns:
            Query object filtered by country_id and entity_type='country'
        """
        return AssignmentEntityStatus.query.filter_by(
            entity_id=country_id,
            entity_type='country'
        )
