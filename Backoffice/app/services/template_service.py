"""
Template Service - Centralized service for template-related database operations.

This service provides a unified interface for FormTemplate queries, replacing
direct database queries in route handlers.
"""

from typing import Optional, List
from app.models import FormTemplate
from app import db
from sqlalchemy import literal


class TemplateService:
    """Service class for template operations."""

    @staticmethod
    def get_by_id(template_id: int) -> Optional[FormTemplate]:
        """Get a template by ID.

        Args:
            template_id: Template ID

        Returns:
            FormTemplate instance or None if not found
        """
        return FormTemplate.query.get(template_id)

    @staticmethod
    def exists(template_id: int) -> bool:
        """Check if a template exists.

        Args:
            template_id: Template ID

        Returns:
            True if template exists, False otherwise
        """
        return FormTemplate.query.filter_by(id=template_id).first() is not None

    @staticmethod
    def get_all():
        """Get all templates.

        Returns:
            Query object for all templates
        """
        return FormTemplate.query

    @staticmethod
    def get_all_published():
        """Get all published templates.

        Returns:
            Query object for published templates (has published_version_id)
        """
        return FormTemplate.query.filter(FormTemplate.published_version_id.isnot(None))

    @staticmethod
    def get_by_ids(template_ids: List[int]):
        """Get templates by a list of IDs.

        Args:
            template_ids: List of template IDs

        Returns:
            Query object filtered by IDs
        """
        if not template_ids:
            return FormTemplate.query.filter(literal(False))  # Empty query
        return FormTemplate.query.filter(FormTemplate.id.in_(template_ids))
