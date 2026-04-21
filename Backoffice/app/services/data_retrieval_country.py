# ========== Data Retrieval: Country Domain ==========
"""
Country resolution, country info, assignments, and user-accessible country lists.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Union, Any

from flask_login import current_user
from sqlalchemy.orm import joinedload

from app.models import Country, AssignedForm, FormTemplateVersion
from app.models.assignments import AssignmentEntityStatus
from app.extensions import db
from app.utils.datetime_helpers import utcnow

from .data_retrieval_shared import (
    user_allowed_country_ids,
    resolve_country_from_identifier,
)

logger = logging.getLogger(__name__)


def check_country_access(country_id: int) -> bool:
    """
    Check if current user has access to a specific country.
    """
    allowed = user_allowed_country_ids()
    if allowed is None:
        return True
    if country_id in allowed:
        return True
    try:
        if getattr(current_user, "is_authenticated", False):
            from app.services.entity_service import EntityService
            return bool(EntityService.check_user_entity_access(current_user, "country", int(country_id)))
    except Exception as e:
        logger.debug("check_country_access failed for country_id=%s: %s", country_id, e)
        return False
    return False


def resolve_country(country_identifier: Union[int, str]) -> Optional[Country]:
    """
    Resolve a country without enforcing RBAC.
    Use when you need a stable country id/name and will enforce access at the data layer.
    """
    try:
        if isinstance(country_identifier, int):
            return db.session.get(Country, int(country_identifier))
        if isinstance(country_identifier, str):
            if country_identifier.strip().isdigit():
                return db.session.get(Country, int(country_identifier.strip()))
            return resolve_country_from_identifier(country_identifier)
    except Exception as e:
        logger.debug("resolve_country failed for %r: %s", country_identifier, e)
        return None
    return None


def get_country_info(country_identifier: Union[int, str]) -> Dict[str, Any]:
    """
    Get comprehensive country information with RBAC enforcement.
    """
    try:
        country = None
        if isinstance(country_identifier, int):
            country = db.session.get(Country, country_identifier)
        elif isinstance(country_identifier, str):
            country = resolve_country_from_identifier(country_identifier)

        if not country:
            return {'error': 'Country not found'}

        if not check_country_access(country.id):
            return {'error': 'Access denied for this country'}

        statuses = (
            AssignmentEntityStatus.query
            .filter_by(entity_id=country.id, entity_type='country')
            .options(
                joinedload(AssignmentEntityStatus.assigned_form).joinedload(AssignedForm.template),
            )
            .all()
        )

        total = len(statuses)
        completed = sum(1 for s in statuses if s.status in ['Submitted', 'Approved'])
        pending = total - completed

        now = utcnow()
        upcoming = []
        for s in statuses:
            if s.status not in ['Submitted', 'Approved'] and s.due_date and s.due_date > now:
                upcoming.append({
                    'template_name': s.assigned_form.template.name if s.assigned_form and s.assigned_form.template else 'Unknown',
                    'due_date': s.due_date.isoformat(),
                    'days_left': (s.due_date - now).days,
                })
        upcoming = sorted(upcoming, key=lambda x: x['days_left'])[:5]

        recent_submissions = []
        for s in sorted(statuses, key=lambda x: x.status_timestamp or datetime.min, reverse=True)[:5]:
            if s.status in ['Submitted', 'Approved']:
                recent_submissions.append({
                    'template_name': s.assigned_form.template.name if s.assigned_form and s.assigned_form.template else 'Unknown',
                    'status': s.status,
                    'timestamp': s.status_timestamp.isoformat() if s.status_timestamp else None,
                })

        return {
            'country': {
                'id': country.id,
                'name': country.name,
                'iso3': getattr(country, 'iso3', ''),
                'national_society': (country.primary_national_society.name if getattr(country, 'primary_national_society', None) and country.primary_national_society else ''),
                'region': getattr(country, 'region', ''),
                'status': getattr(country, 'status', ''),
            },
            'assignments': {'total': total, 'completed': completed, 'pending': pending},
            'upcoming_deadlines': upcoming,
            'recent_submissions': recent_submissions,
        }
    except Exception as e:
        logger.error(f"get_country_info error: {e}")
        return {'error': 'Could not retrieve country overview'}


def get_assignments_for_country(
    country_id: int,
    status_filter: Optional[str] = None,
    include_details: bool = True
) -> List[Dict[str, Any]]:
    """Query assignments for a specific country with RBAC enforcement."""
    try:
        if not check_country_access(country_id):
            logger.warning(f"User {current_user.id} attempted to access country {country_id} without permission")
            return []

        query = (
            db.session.query(AssignedForm, AssignmentEntityStatus)
            .join(AssignmentEntityStatus, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
            .filter(
                AssignmentEntityStatus.entity_id == int(country_id),
                AssignmentEntityStatus.entity_type == 'country',
            )
            .options(joinedload(AssignedForm.template))
        )
        if status_filter:
            query = query.filter(AssignmentEntityStatus.status == status_filter)
        rows = query.all()

        assignment_data = []
        for assignment, status_info in rows:
            assignment_info = {
                'id': assignment.id,
                'template_name': assignment.template.name if assignment.template else 'Unknown Template',
                'period_name': assignment.period_name,
                'deadline': status_info.due_date.isoformat() if status_info and status_info.due_date else None,
                'is_completed': status_info.status in ['Submitted', 'Approved'] if status_info else False,
                'created_at': assignment.assigned_at.isoformat() if assignment.assigned_at else None,
                'status': status_info.status if status_info else 'Unknown'
            }
            if include_details:
                template_description = ''
                if assignment.template:
                    eff_v = assignment.template.published_version
                    if not eff_v:
                        eff_v = assignment.template.versions.order_by(FormTemplateVersion.created_at.desc()).first()
                    template_description = eff_v.description if (eff_v and eff_v.description) else ''
                assignment_info['template_description'] = template_description
                assignment_info['submitted_at'] = None
            assignment_data.append(assignment_info)

        return assignment_data
    except Exception as e:
        logger.error(f"Error querying assignments for country {country_id}: {e}", exc_info=True)
        return []


def get_user_countries() -> List[Dict[str, Any]]:
    """Get countries accessible to the current user (assigned countries list)."""
    try:
        allowed_ids = user_allowed_country_ids()
        if allowed_ids is None:
            countries = Country.query.order_by(Country.name).all()
        else:
            countries = current_user.countries.order_by(Country.name).all() if hasattr(current_user, 'countries') else []

        return [
            {
                'id': c.id,
                'name': c.name,
                'iso3': getattr(c, 'iso3', ''),
                'national_society': (c.primary_national_society.name if getattr(c, 'primary_national_society', None) and c.primary_national_society else '')
            }
            for c in countries
        ]
    except Exception as e:
        logger.error(f"Error getting user countries: {e}")
        return []


def get_user_country_ids() -> List[int]:
    """Get list of country IDs accessible to the current user."""
    try:
        allowed_ids = user_allowed_country_ids()
        if allowed_ids is None:
            return [c.id for c in Country.query.all()]
        return [c.id for c in current_user.countries.all()] if hasattr(current_user, 'countries') else []
    except Exception as e:
        logger.error(f"Error getting user country IDs: {e}")
        return []
