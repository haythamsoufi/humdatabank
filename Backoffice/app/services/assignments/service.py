"""
Assignment Service - Centralized service for assignment-related database operations.

This service provides a unified interface for AssignmentEntityStatus and AssignedForm queries,
replacing direct database queries in route handlers.
"""

from datetime import timedelta
from typing import Optional

from app.models import AssignmentEntityStatus, AssignedForm
from app.models.enums import AssignmentEntityStatusValue
from app.utils.datetime_helpers import utcnow
from sqlalchemy.orm import joinedload

# Dashboard overdue logic matches the user dashboard: only pending / in_progress
# past the due date count as overdue (review/submitted/approved are not).
_OVERDUE_STATUSES = frozenset({
    AssignmentEntityStatusValue.pending.value,
    AssignmentEntityStatusValue.in_progress.value,
})
_DONE_STATUSES = frozenset({
    AssignmentEntityStatusValue.submitted.value,
    AssignmentEntityStatusValue.approved.value,
})
_CANCELLED = AssignmentEntityStatusValue.cancelled.value
_DUE_SOON_DAYS = 7


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
        return (
            AssignmentEntityStatus.query
            .options(
                joinedload(AssignmentEntityStatus.assigned_form)
                .joinedload(AssignedForm.template)
            )
            .get(aes_id)
        )

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

    @staticmethod
    def _aes_status_key(aes) -> str:
        status = getattr(aes, 'status', None)
        if status is None:
            return AssignmentEntityStatusValue.pending.value
        return status.value if hasattr(status, 'value') else str(status)

    @staticmethod
    def _aes_due_date(aes):
        due = getattr(aes, 'due_date', None)
        if due is None:
            return None
        return due.date() if hasattr(due, 'date') else due

    @staticmethod
    def build_status_overview(assignment, entities=None) -> Optional[dict]:
        """Aggregate lifecycle, workflow, and deadline stats for an existing assignment.

        Args:
            assignment: AssignedForm instance (None returns None).
            entities: Optional preloaded AssignmentEntityStatus list. When omitted,
                ``assignment.entity_statuses`` is loaded.

        Returns:
            Dict for the edit-assignment status dashboard, or None.
        """
        if assignment is None:
            return None

        if entities is None:
            entities = list(assignment.entity_statuses.all())
        else:
            entities = list(entities)

        today = utcnow().date()
        due_soon_until = today + timedelta(days=_DUE_SOON_DAYS)

        status_counts = {value: 0 for value, _label in AssignmentEntityStatusValue.choices()}
        country_count = 0
        public_country_count = 0
        overdue_count = 0
        due_soon_count = 0
        completion_sum = 0.0
        completion_n = 0
        distinct_due_dates = set()

        for aes in entities:
            key = AssignmentService._aes_status_key(aes)
            if key not in status_counts:
                status_counts[key] = 0
            status_counts[key] += 1

            if getattr(aes, 'entity_type', None) == 'country':
                country_count += 1
                if getattr(aes, 'is_public_available', False):
                    public_country_count += 1

            due_date = AssignmentService._aes_due_date(aes)
            if due_date is not None:
                distinct_due_dates.add(due_date)
                if key in _OVERDUE_STATUSES:
                    if due_date < today:
                        overdue_count += 1
                    elif today <= due_date <= due_soon_until:
                        due_soon_count += 1

            rate = getattr(aes, 'completion_rate', None)
            if rate is not None:
                completion_sum += float(rate)
                completion_n += 1

        entity_count = len(entities)
        cancelled_count = status_counts.get(_CANCELLED, 0)
        done_count = sum(status_counts.get(s, 0) for s in _DONE_STATUSES)
        expected_count = max(entity_count - cancelled_count, 0)
        open_count = max(expected_count - done_count, 0)
        submission_rate_pct = (
            round((done_count / expected_count) * 100.0, 1) if expected_count else 0.0
        )
        avg_completion_pct = (
            round(completion_sum / completion_n, 1) if completion_n else None
        )

        status_breakdown = []
        for value, _label in AssignmentEntityStatusValue.choices():
            count = status_counts.get(value, 0)
            status_breakdown.append({
                'value': value,
                'count': count,
                'pct': round((count / entity_count) * 100.0, 1) if entity_count else 0.0,
            })
        for value, count in status_counts.items():
            if value not in {row['value'] for row in status_breakdown}:
                status_breakdown.append({
                    'value': value,
                    'count': count,
                    'pct': round((count / entity_count) * 100.0, 1) if entity_count else 0.0,
                })

        if assignment.is_effectively_closed:
            lifecycle = 'closed_expired' if (not assignment.is_closed and assignment.expiry_date) else 'closed'
        elif not assignment.is_active:
            lifecycle = 'inactive'
        else:
            lifecycle = 'active'

        data_owner = getattr(assignment, 'data_owner_user', None)
        template = getattr(assignment, 'template', None)

        return {
            'lifecycle': lifecycle,
            'is_active': bool(assignment.is_active),
            'is_closed': bool(assignment.is_closed),
            'is_effectively_closed': bool(assignment.is_effectively_closed),
            'entity_count': entity_count,
            'country_count': country_count,
            'open_count': open_count,
            'done_count': done_count,
            'cancelled_count': cancelled_count,
            'status_counts': status_counts,
            'status_breakdown': status_breakdown,
            'submission_rate_pct': submission_rate_pct,
            'avg_completion_pct': avg_completion_pct,
            'overdue_count': overdue_count,
            'due_soon_count': due_soon_count,
            'earliest_due_date': min(distinct_due_dates) if distinct_due_dates else None,
            'has_multiple_due_dates': len(distinct_due_dates) > 1,
            'expiry_date': assignment.expiry_date,
            'public_url_generated': bool(assignment.has_public_url()),
            'public_url_active': bool(assignment.is_public_active),
            'public_country_count': public_country_count,
            'has_data_owner': data_owner is not None,
            'data_owner_name': (data_owner.name if data_owner else None),
            'template_name': template.name if template else None,
            'period_name': assignment.period_name,
            'assigned_at': assignment.assigned_at,
        }
