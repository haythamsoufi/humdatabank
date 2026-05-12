# ========== Data Retrieval Service ==========
"""
Centralized service for fetching platform data.

This service consolidates data retrieval logic used across:
- Chatbot (for answering questions)
- API routes (for external access)
- Admin routes (for management interfaces)

Domain modules:
- data_retrieval_shared: helpers (user, RBAC, escape, indicator scoring, country resolution)
- data_retrieval_country: country resolution, country info, assignments, user countries
- data_retrieval_form: form data queries, value breakdown, indicator values, form field value
"""

import json
import logging
import re
from typing import Dict, List, Optional, Union, Any
from datetime import timedelta

from flask_login import current_user
from sqlalchemy import desc, literal, text, func, or_

from app.models import (
    User, Country, FormTemplate, FormTemplateVersion, FormSection, IndicatorBank,
    FormItem, AIDocument, AIDocumentChunk
)
from app.models.assignments import AssignmentEntityStatus
from app.extensions import db
from app.utils.api_helpers import service_error, GENERIC_ERROR_MESSAGE
from app.utils.datetime_helpers import utcnow
from app.utils.sql_utils import safe_ilike_pattern

# Re-export from domain modules so existing "from app.services.data_retrieval_service import ..." still works.
from .data_retrieval_shared import (
    get_indicator_candidates_by_keyword,
    user_allowed_country_ids as _user_allowed_country_ids,
)
from .data_retrieval_country import (
    check_country_access,
    resolve_country,
    get_country_info,
    get_assignments_for_country,
    get_user_countries,
    get_user_country_ids,
)
from .data_retrieval_form import (
    query_form_data,
    get_form_data_queries,
    get_value_breakdown,
    get_indicator_values_for_all_countries,
    get_assignment_indicator_values,
    get_form_field_value,
    get_indicator_timeseries,
)

logger = logging.getLogger(__name__)

def _effective_user_role_and_id() -> Dict[str, Any]:
    """
    Best-effort resolve user context for AI requests.

    - Uses `current_user` when authenticated
    - Falls back to request-scoped `flask.g` values used by AI routes
    """
    user_role = None
    user_id = None
    try:
        from app.services.authorization_service import AuthorizationService
        if getattr(current_user, "is_authenticated", False):
            user_role = AuthorizationService.access_level(current_user)
            user_id = int(getattr(current_user, "id", 0) or 0) or None
    except Exception as e:
        logger.debug("get_effective_request_user: auth resolution failed: %s", e)
    try:
        from flask import g, has_request_context
        if has_request_context():
            if user_id is None:
                try:
                    user_id = int(getattr(g, "ai_user_id", None) or 0) or None
                except Exception as e:
                    logger.debug("get_effective_request_user: g.ai_user_id failed: %s", e)
                    user_id = None
            if user_role is None:
                user_role = getattr(g, "ai_user_access_level", None) or getattr(g, "ai_user_role", None) or user_role
    except Exception as e:
        logger.debug("get_effective_request_user: g context failed: %s", e)
    if not user_role:
        user_role = "public"
    return {"user_role": user_role, "user_id": user_id}

def _dialect_name() -> str:
    try:
        return (getattr(db, "engine", None) and db.engine.dialect.name) or ""
    except Exception as e:
        logger.debug("_dialect_name failed: %s", e)
        return ""


# ==================== User Profile ====================

def get_user_profile(user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Return safe user profile info including RBAC roles and country access.
    """
    try:
        current_user_authenticated = getattr(current_user, 'is_authenticated', False)
        if user_id is None:
            if not current_user_authenticated:
                return {'error': 'Not authenticated'}
            user = current_user
        else:
            user = db.session.get(User, int(user_id))
        if not user:
            return {'error': 'User not found'}

        current_user_id = int(getattr(current_user, 'id', 0) or 0) if current_user_authenticated else None
        if user_id and current_user_id and user_id != current_user_id:
            from app.services.authorization_service import AuthorizationService
            if not (AuthorizationService.is_system_manager(current_user) or AuthorizationService.has_rbac_permission(current_user, "admin.users.view")):
                return {'error': 'Access denied'}

        user_countries = []
        if hasattr(user, 'countries') and hasattr(user.countries, 'all'):
            user_countries = [
                {'id': c.id, 'name': c.name, 'iso3': getattr(c, 'iso3', '')}
                for c in user.countries.all()
            ]

        profile = {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'assigned_countries': user_countries,
            'chatbot_enabled': getattr(user, 'chatbot_enabled', True),
        }

        try:
            from app.models.rbac import RbacUserRole, RbacRole
            urs = RbacUserRole.query.filter_by(user_id=user.id).all()
            role_ids = [ur.role_id for ur in urs]
            roles = RbacRole.query.filter(RbacRole.id.in_(role_ids)).all() if role_ids else []
            profile['rbac_roles'] = [{'code': r.code, 'name': r.name} for r in roles]
        except Exception as e:
            logger.debug("get_user_profile: RBAC roles fetch failed for user %s: %s", user.id, e)
            profile['rbac_roles'] = []

        return profile
    except Exception as e:
        logger.exception("get_user_profile error: %s", e)
        return {'error': 'Could not retrieve user profile'}


# ==================== Indicator Details ====================

def get_indicator_details(identifier: Union[int, str]) -> Optional[Dict[str, Any]]:
    """Fetch comprehensive indicator details by ID or name.

    Resolution order: ID lookup, then semantic/vector resolution when configured,
    then keyword fallback (name and optional name variants, e.g. 'volunteers' -> 'volunteering').
    """
    try:
        ind = None
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            ind = db.session.get(IndicatorBank, int(identifier))
        if not ind and isinstance(identifier, str):
            ident = (identifier or "").strip()
            # Use same resolution as get_value_breakdown: vector/LLM when configured
            try:
                from app.services.indicator_resolution_service import resolve_indicator_identifier
                ind = resolve_indicator_identifier(identifier, user_query=None)
            except Exception as e:
                logger.debug("Indicator resolution (vector/LLM) in get_indicator_details failed: %s", e)
            # Keyword fallback: name and name variants (e.g. "volunteers" -> "volunteering")
            if not ind and ident:
                candidates = get_indicator_candidates_by_keyword(ident)
                ind = candidates[0] if candidates else None
            if not ind and ident and getattr(IndicatorBank, "fdrs_kpi_code", None) is not None:
                fdrs_pattern = safe_ilike_pattern(ident)
                ind = IndicatorBank.query.filter(
                    IndicatorBank.fdrs_kpi_code.isnot(None),
                    IndicatorBank.fdrs_kpi_code.ilike(fdrs_pattern),
                ).first()
            # Last resort: match when all words in the query appear in the indicator name (any order)
            if not ind and ident and len(ident) > 2:
                words = [w.strip() for w in re.split(r"\s+", ident) if len(w.strip()) > 1]
                if words:
                    patterns = [safe_ilike_pattern(w) for w in words]
                    ind = (
                        IndicatorBank.query.filter(
                            *[IndicatorBank.name.ilike(p) for p in patterns]
                        ).first()
                    )
        if not ind:
            return None

        return {
            'id': ind.id,
            'name': ind.name,
            'type': ind.type,
            'unit': ind.unit,
            'definition': ind.definition,
            'sectors': ind.get_all_sector_names(),
            'sub_sectors': ind.get_all_subsector_names(),
            'emergency': ind.emergency,
            'archived': ind.archived,
            'related_programs': ind.related_programs_list,
            'usage_count': ind.usage_count,
            'created_at': ind.created_at.isoformat() if ind.created_at else None,
            'updated_at': ind.updated_at.isoformat() if ind.updated_at else None,
        }
    except Exception as e:
        logger.exception("Error fetching indicator details: %s", e)
        return None


# ==================== Template Structure ====================

def get_template_structure(template_identifier: Union[int, str]) -> Dict[str, Any]:
    """Get template structure: sections, fields, validations."""
    try:
        template = None
        if isinstance(template_identifier, int):
            template = db.session.get(FormTemplate, template_identifier)
        elif isinstance(template_identifier, str):
            if template_identifier.isdigit():
                template = db.session.get(FormTemplate, int(template_identifier))
            if not template:
                template = (
                    FormTemplate.query
                    .join(FormTemplateVersion, FormTemplateVersion.template_id == FormTemplate.id)
                    .filter(FormTemplateVersion.name.ilike(safe_ilike_pattern(template_identifier)))
                    .first()
                )

        if not template:
            return {'error': 'Template not found'}

        sections = []
        # Use column attribute rather than string ordering for safety.
        section_rows = template.sections.order_by(FormSection.order.asc()).all()
        section_ids = [s.id for s in section_rows]

        # Avoid N+1: compute item counts and sample items in bulk.
        item_counts_by_section: Dict[int, int] = {}
        sample_items_by_section: Dict[int, List[Dict[str, Any]]] = {sid: [] for sid in section_ids}
        if section_ids:
            try:
                counts = (
                    db.session.query(FormItem.section_id, func.count(FormItem.id))
                    .filter(FormItem.section_id.in_(section_ids))
                    .group_by(FormItem.section_id)
                    .all()
                )
                item_counts_by_section = {int(sid): int(cnt or 0) for sid, cnt in counts}
            except Exception as e:
                logger.debug("get_template_structure: item_counts_by_section failed: %s", e)
                item_counts_by_section = {}

            try:
                # Use a window function where available (Postgres/SQLite 3.25+) to fetch the first N items per section
                # without loading all items.
                rn = func.row_number().over(
                    partition_by=FormItem.section_id,
                    order_by=FormItem.order.asc(),
                ).label("rn")
                subq = (
                    db.session.query(
                        FormItem.section_id.label("section_id"),
                        FormItem.label.label("label"),
                        FormItem.item_type.label("item_type"),
                        FormItem.is_required.label("is_required"),
                        FormItem.validation_condition.label("validation_condition"),
                        rn,
                    )
                    .filter(FormItem.section_id.in_(section_ids))
                    .subquery()
                )
                rows = (
                    db.session.query(subq)
                    .filter(subq.c.rn <= 10)
                    .order_by(subq.c.section_id.asc(), subq.c.rn.asc())
                    .all()
                )
                for r in rows:
                    arr = sample_items_by_section.setdefault(int(r.section_id), [])
                    arr.append({
                        'label': r.label,
                        'type': r.item_type,
                        'required': bool(r.is_required),
                        'has_validation': bool(r.validation_condition),
                    })
            except Exception as e:
                logger.debug("sample_items extraction failed: %s", e)

        for section in section_rows:
            sections.append({
                'name': section.name,
                'order': section.order,
                'is_sub_section': section.is_sub_section,
                'items_count': item_counts_by_section.get(int(section.id), 0),
                'sample_items': sample_items_by_section.get(int(section.id), []),
            })

        effective_version = template.published_version
        if not effective_version:
            effective_version = template.versions.order_by(FormTemplateVersion.created_at.desc()).first()
        effective_description = effective_version.description if effective_version else None
        effective_is_paginated = effective_version.is_paginated if effective_version else False

        indicator_names = []
        try:
            seen_ids = set()
            for item in template.form_items.filter(FormItem.indicator_bank_id.isnot(None)).all():
                if item.indicator_bank_id and item.indicator_bank_id not in seen_ids:
                    seen_ids.add(item.indicator_bank_id)
                    if item.indicator_bank:
                        indicator_names.append(item.indicator_bank.name)
            indicator_names = sorted(set(indicator_names))
        except Exception as e:
            logger.debug("get_template_structure: indicator_names extraction failed: %s", e)
            indicator_names = []

        return {
            'template': {
                'id': template.id,
                'name': template.name,
                'description': effective_description,
                'is_paginated': effective_is_paginated,
                'created_at': template.created_at.isoformat() if hasattr(template, 'created_at') and template.created_at else None,
            },
            'sections': sections,
            'total_sections': len(sections),
            'total_items': template.form_items.count(),
            'indicator_names': indicator_names,
        }
    except Exception as e:
        logger.exception("get_template_structure error: %s", e)
        return {'error': 'Could not retrieve template info'}


# ==================== Platform Statistics ====================

def get_platform_stats(user_scoped: bool = True) -> Dict[str, int]:
    """Get platform-wide statistics with optional user scoping."""
    try:
        if user_scoped is False:
            try:
                from app.services.authorization_service import AuthorizationService
                if not (
                    getattr(current_user, "is_authenticated", False)
                    and (AuthorizationService.is_admin(current_user) or AuthorizationService.is_system_manager(current_user))
                ):
                    user_scoped = True
            except Exception as e:
                logger.debug("admin scope check failed: %s", e)
                user_scoped = True

        stats = {
            'total_users': User.query.count(),
            'total_countries': Country.query.count(),
            'total_templates': FormTemplate.query.count(),
            'total_indicators': IndicatorBank.query.filter_by(archived=False).count(),
            'total_assignments': 0,
            'total_submissions': 0,
        }

        allowed_ids = _user_allowed_country_ids() if user_scoped else None
        if user_scoped and allowed_ids is not None:
            if allowed_ids:
                stats['total_assignments'] = AssignmentEntityStatus.query.filter(
                    AssignmentEntityStatus.entity_id.in_(allowed_ids),
                    AssignmentEntityStatus.entity_type == 'country'
                ).count()
                stats['total_submissions'] = AssignmentEntityStatus.query.filter(
                    AssignmentEntityStatus.entity_id.in_(allowed_ids),
                    AssignmentEntityStatus.entity_type == 'country',
                    AssignmentEntityStatus.status.in_(['Submitted', 'Approved'])
                ).count()
        else:
            stats['total_assignments'] = AssignmentEntityStatus.query.filter(
                AssignmentEntityStatus.entity_type == 'country'
            ).count()
            stats['total_submissions'] = AssignmentEntityStatus.query.filter(
                AssignmentEntityStatus.entity_type == 'country',
                AssignmentEntityStatus.status.in_(['Submitted', 'Approved'])
            ).count()

        return stats
    except Exception as e:
        logger.exception("Error getting platform stats: %s", e)
        return {
            'total_users': 0,
            'total_countries': 0,
            'total_templates': 0,
            'total_indicators': 0,
            'total_assignments': 0,
            'total_submissions': 0,
        }


# ==================== User-Specific Data ====================

def get_user_data_context(user_id: Optional[int] = None) -> Dict[str, Any]:
    """Get user-specific data context for focal points or admins."""
    try:
        user = current_user if user_id is None else db.session.get(User, int(user_id))
        if not user:
            return {}

        user_data = {}
        from app.services.authorization_service import AuthorizationService
        from sqlalchemy.orm import joinedload
        from app.models import AssignedForm

        # Prevent cross-user data access unless explicitly authorized.
        if user_id is not None and int(user_id) != int(getattr(current_user, "id", 0) or 0):
            if not (
                AuthorizationService.is_system_manager(current_user)
                or AuthorizationService.has_rbac_permission(current_user, "admin.users.view")
            ):
                return {}

        if AuthorizationService.has_role(user, "assignment_editor_submitter") and not AuthorizationService.is_admin(user):
            user_countries = []
            if hasattr(user, 'countries') and hasattr(user.countries, 'all'):
                user_countries = user.countries.all()
            country_ids = [c.id for c in user_countries]
            user_data['countries'] = [c.name for c in user_countries]

            if country_ids:
                total = AssignmentEntityStatus.query.filter(
                    AssignmentEntityStatus.entity_id.in_(country_ids),
                    AssignmentEntityStatus.entity_type == 'country'
                ).count()
                completed = AssignmentEntityStatus.query.filter(
                    AssignmentEntityStatus.entity_id.in_(country_ids),
                    AssignmentEntityStatus.entity_type == 'country',
                    AssignmentEntityStatus.status.in_(['Submitted', 'Approved'])
                ).count()
                user_data['total_assignments'] = total
                user_data['completed_assignments'] = completed
                user_data['pending_assignments'] = max(total - completed, 0)

                pending_statuses = (
                    AssignmentEntityStatus.query
                    .options(
                        joinedload(AssignmentEntityStatus.assigned_form).joinedload(AssignedForm.template),
                        joinedload(AssignmentEntityStatus.country)
                    )
                    .filter(
                        AssignmentEntityStatus.entity_id.in_(country_ids),
                        AssignmentEntityStatus.entity_type == 'country',
                        ~AssignmentEntityStatus.status.in_(['Submitted', 'Approved'])
                    )
                    .order_by(AssignmentEntityStatus.due_date.asc().nullslast())
                    .limit(10)
                    .all()
                )
                user_data['pending_assignment_details'] = [
                    {
                        'template_name': s.assigned_form.template.name if s.assigned_form and s.assigned_form.template else 'Unknown',
                        'deadline': s.due_date.isoformat() if s.due_date else None,
                        'country': s.country.name if s.country else 'Unknown',
                    }
                    for s in pending_statuses
                ]

        elif AuthorizationService.is_admin(user):
            user_data['recent_submissions_count'] = AssignmentEntityStatus.query.filter(
                AssignmentEntityStatus.entity_type == 'country',
                AssignmentEntityStatus.status.in_(['Submitted', 'Approved']),
                AssignmentEntityStatus.status_timestamp >= utcnow() - timedelta(days=30)
            ).count()
            user_data['pending_assignments'] = AssignmentEntityStatus.query.filter(
                AssignmentEntityStatus.entity_type == 'country',
                ~AssignmentEntityStatus.status.in_(['Submitted', 'Approved'])
            ).count()

        return user_data
    except Exception as e:
        logger.exception("Error getting user data context: %s", e)
        return {}


# ==================== FormData Map & ACS Access ====================

def get_formdata_map(aes_id: int, item_ids: Optional[List[int]] = None) -> Dict[int, str]:
    """Get FormData entries for an assignment as a map of form_item_id -> value."""
    try:
        from app.models import FormData
        aes = db.session.get(AssignmentEntityStatus, aes_id)
        if not aes:
            logger.warning(f"Access denied for ACS {aes_id} (not found)")
            return {}

        from app.services.entity_service import EntityService
        if not EntityService.check_user_entity_access(current_user, aes.entity_type, aes.entity_id):
            logger.warning(f"Access denied for ACS {aes_id} (entity_type={aes.entity_type}, entity_id={aes.entity_id})")
            return {}

        query = FormData.query.filter_by(assignment_entity_status_id=aes_id)
        if item_ids:
            query = query.filter(FormData.form_item_id.in_(item_ids))
        entries = query.all()
        return {entry.form_item_id: entry.value for entry in entries}
    except Exception as e:
        logger.exception("Error getting FormData map for ACS %s: %s", aes_id, e)
        return {}


def get_aes_with_joins(aes_id: int):
    """Get AssignmentEntityStatus with common joins and RBAC enforcement."""
    try:
        from app.models import AssignedForm
        from sqlalchemy.orm import joinedload
        from app.services.entity_service import EntityService

        aes = AssignmentEntityStatus.query.options(
            joinedload(AssignmentEntityStatus.assigned_form).joinedload(AssignedForm.template),
        ).get(aes_id)

        if not aes:
            logger.warning(f"AES {aes_id} not found")
            return None
        if not EntityService.check_user_entity_access(current_user, aes.entity_type, aes.entity_id):
            logger.warning(f"Access denied for AES {aes_id} (entity_type={aes.entity_type}, entity_id={aes.entity_id})")
            return None
        return aes
    except Exception as e:
        logger.exception("Error getting AES %s with joins: %s", aes_id, e)
        return None


# ==================== UPR Visual KPI Lookup ====================
# Moved to app.services.upr.data_retrieval – re-exported for backward compat.
from app.services.upr.data_retrieval import (  # noqa: E402,F401
    get_upr_kpi_value,
    get_upr_kpi_timeseries,
    get_upr_kpi_values_for_all_countries,
)


def ensure_aes_access(aes_id: int) -> Dict[str, Any]:
    """Ensure user has access to an AssignmentEntityStatus."""
    try:
        aes = get_aes_with_joins(aes_id)
        if not aes:
            return {'error': 'Assignment not found or access denied'}
        return {'aes': aes}
    except Exception as e:
        logger.exception("Error ensuring AES access for %s: %s", aes_id, e)
        return {'error': 'Could not verify assignment access'}


# ==================== Export ====================

__all__ = [
    'get_user_profile',
    'get_country_info',
    'resolve_country',
    'get_indicator_details',
    'get_template_structure',
    'get_value_breakdown',
    'get_indicator_values_for_all_countries',
    'get_assignments_for_country',
    'get_assignment_indicator_values',
    'get_platform_stats',
    'get_user_data_context',
    'check_country_access',
    '_user_allowed_country_ids',
    'get_formdata_map',
    'get_aes_with_joins',
    'ensure_aes_access',
    'get_user_countries',
    'get_user_country_ids',
    'get_upr_kpi_value',
    'get_upr_kpi_values_for_all_countries',
    'query_form_data',
    'get_form_data_queries',
    'get_form_field_value',
]
