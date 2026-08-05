# ========== Data Retrieval: Form Domain ==========
"""
Form data query builders for the Data API and admin (non-AI).

AI chatbot retrieval lives in app.services.ai.data.form_retrieval.
"""

import logging
import re
from datetime import datetime as _dt
from typing import Dict, List, Optional, Any

from sqlalchemy import and_, literal, or_
from sqlalchemy.orm import joinedload

from app.models import FormData, FormItem, FormSection, IndicatorBank, PublicSubmission
from app.models.assignments import AssignmentEntityStatus, AssignedForm
from app.extensions import db
from app.utils.sql_utils import safe_ilike_pattern

from .shared import (
    get_effective_request_user,
    can_view_non_public_form_items,
    form_item_privacy_is_public_expr,
    escape_like_pattern,
)

logger = logging.getLogger(__name__)


def _filter_by_assignment_ids(query, assignment_ids: Optional[List[int]]):
    if not assignment_ids:
        return query
    ids = [int(x) for x in assignment_ids]
    if len(ids) == 1:
        return query.filter(AssignedForm.id == ids[0])
    return query.filter(AssignedForm.id.in_(ids))


def query_form_data(
    *,
    template_id: Optional[int] = None,
    submission_id: Optional[int] = None,
    item_id: Optional[int] = None,
    item_type: Optional[str] = None,
    country_id: Optional[int] = None,
    period_name: Optional[str] = None,
    assignment_ids: Optional[List[int]] = None,
    indicator_bank_id: Optional[int] = None,
    indicator_bank_ids: Optional[List[int]] = None,
    submission_type: Optional[str] = None,
    preload: bool = False,
    full_preload: bool = True,
) -> Dict[str, Any]:
    """
    Centralized FormData query builder for API usage. Does not enforce RBAC (API uses API key),
    but encapsulates join shapes and filters consistently for assigned and public data.

    Returns a dict with two query objects: 'assigned' and 'public'. Callers may further iterate .all().

    ``assignment_ids`` filters by ``AssignedForm.id`` (API-facing assignment scope).
    Accepts one or many ids; comma-separated lists are parsed in the route layer.
    """
    try:
        assigned_q = FormData.query
        public_q = FormData.query.join(AssignmentEntityStatus).join(
            PublicSubmission,
            and_(
                AssignmentEntityStatus.assigned_form_id == PublicSubmission.assigned_form_id,
                AssignmentEntityStatus.entity_id == PublicSubmission.country_id,
                AssignmentEntityStatus.entity_type == 'country',
            ),
        ).join(AssignedForm, PublicSubmission.assigned_form_id == AssignedForm.id)

        # Assigned path joins lazily: add joins only when needed to avoid ambiguous columns
        needs_af_join = bool(template_id or country_id or period_name or assignment_ids)
        if needs_af_join:
            assigned_q = assigned_q.join(AssignmentEntityStatus).join(AssignedForm)

        if assignment_ids:
            # Exact assignment scope wins over template_id / period_name.
            assigned_q = _filter_by_assignment_ids(assigned_q, assignment_ids)
            public_q = _filter_by_assignment_ids(public_q, assignment_ids)
        else:
            if template_id:
                assigned_q = assigned_q.filter(AssignedForm.template_id == template_id)
                public_q = public_q.filter(AssignedForm.template_id == template_id)
            if period_name:
                _pat = f"%{escape_like_pattern(period_name)}%"
                period_filter = AssignedForm.period_name.ilike(_pat, escape="\\")
                years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2}|21\d{2})\b", str(period_name))]
                if years:
                    start_year = min(years)
                    end_year = max(years)
                    period_start = _dt(start_year, 1, 1).date()
                    period_end = _dt(end_year, 12, 31).date()
                    period_filter = or_(
                        period_filter,
                        and_(
                            AssignedForm.period_start.isnot(None),
                            AssignedForm.period_end.isnot(None),
                            AssignedForm.period_start <= period_end,
                            AssignedForm.period_end >= period_start,
                        ),
                    )
                assigned_q = assigned_q.filter(period_filter)
                public_q = public_q.filter(period_filter)
        if country_id:
            assigned_q = assigned_q.filter(
                AssignmentEntityStatus.entity_id == country_id,
                AssignmentEntityStatus.entity_type == 'country'
            )
            public_q = public_q.filter(PublicSubmission.country_id == country_id)

        if submission_id:
            # For assigned path, ensure AES join exists
            if not needs_af_join:
                assigned_q = assigned_q.join(AssignmentEntityStatus)
            assigned_q = assigned_q.filter(AssignmentEntityStatus.id == submission_id)
            public_q = public_q.filter(PublicSubmission.id == submission_id)

        if item_id:
            assigned_q = assigned_q.filter(FormData.form_item_id == item_id)
            public_q = public_q.filter(FormData.form_item_id == item_id)

        if item_type:
            assigned_q = assigned_q.join(FormItem, FormData.form_item).filter(FormItem.item_type == item_type)
            public_q = public_q.join(FormItem, FormData.form_item).filter(FormItem.item_type == item_type)

        if indicator_bank_id:
            assigned_q = assigned_q.join(FormItem, FormData.form_item).join(IndicatorBank, FormItem.indicator_bank).filter(IndicatorBank.id == indicator_bank_id)
            public_q = public_q.join(FormItem, FormData.form_item).join(IndicatorBank, FormItem.indicator_bank).filter(IndicatorBank.id == indicator_bank_id)

        if indicator_bank_ids:
            # Filter to rows whose FormItem.indicator_bank_id is in the given list.
            # Uses a subquery on FormItem to avoid extra joins and join-duplication with
            # existing item_type / indicator_bank_id filters.
            _fi_ids_sq = db.session.query(FormItem.id).filter(
                FormItem.indicator_bank_id.in_(indicator_bank_ids)
            ).subquery()
            assigned_q = assigned_q.filter(FormData.form_item_id.in_(_fi_ids_sq))
            public_q = public_q.filter(FormData.form_item_id.in_(_fi_ids_sq))

        if preload:
            # Core eager-loads needed for every serialization path
            # (AES/assigned_form for assigned rows, public_submission/assigned_form for public rows).
            # Note: AssignedForm.template and PublicSubmission.country are backrefs loaded on access.
            assigned_opts = [
                joinedload(FormData.assignment_entity_status).joinedload(AssignmentEntityStatus.assigned_form),
            ]
            public_opts = [
                joinedload(FormData.public_submission).joinedload(PublicSubmission.assigned_form),
            ]

            if full_preload:
                # Additional joins for form_item_info (only when include_full_info=True).
                # These add 2–3 extra JOINs per query and are skipped on the common path.
                assigned_opts += [
                    joinedload(FormData.form_item).joinedload(FormItem.form_section).joinedload(FormSection.template),
                    joinedload(FormData.form_item).joinedload(FormItem.indicator_bank),
                ]
                public_opts += [
                    joinedload(FormData.form_item).joinedload(FormItem.form_section).joinedload(FormSection.template),
                    joinedload(FormData.form_item).joinedload(FormItem.indicator_bank),
                ]

            assigned_q = assigned_q.options(*assigned_opts)
            public_q = public_q.options(*public_opts)

        # ---------- Privacy gating ----------
        # Public callers (including API key / website / mobile) should see ONLY FormItem privacy='public'.
        # Non-public form items require RBAC.
        viewer = get_effective_request_user()

        if not can_view_non_public_form_items(viewer):
            # Avoid join duplication by using relationship .has() (EXISTS).
            public_only = form_item_privacy_is_public_expr()
            assigned_q = assigned_q.filter(FormData.form_item.has(public_only))
            public_q = public_q.filter(FormData.form_item.has(public_only))

        # Respect submission_type if provided by caller
        return {
            'assigned': None if submission_type == 'public' else assigned_q,
            'public': None if submission_type == 'assigned' else public_q,
        }
    except Exception as e:
        logger.error(f"Error building form data query: {e}", exc_info=True)
        return {'assigned': FormData.query.filter(literal(False)), 'public': FormData.query.filter(literal(False))}


def get_form_data_queries(queries_dict):
    """
    Extract assigned and public queries from query_form_data result with safe fallbacks.

    Args:
        queries_dict: Dictionary returned by query_form_data() with 'assigned' and 'public' keys

    Returns:
        tuple: (assigned_query, public_query) - Both are always valid query objects (never None)
    """
    assigned_q = queries_dict.get('assigned')
    public_q = queries_dict.get('public')

    # Provide empty query fallback if None
    if assigned_q is None:
        assigned_q = FormData.query.filter(literal(False))
    if public_q is None:
        public_q = FormData.query.filter(literal(False))

    return assigned_q, public_q

def query_dynamic_indicator_data(
    *,
    template_id: Optional[int] = None,
    submission_id: Optional[int] = None,
    country_id: Optional[int] = None,
    period_name: Optional[str] = None,
    assignment_ids: Optional[List[int]] = None,
    section_id: Optional[int] = None,
    indicator_bank_id: Optional[int] = None,
    submission_type: Optional[str] = None,
    preload: bool = False,
) -> Dict[str, Any]:
    """
    Build SQLAlchemy queries for DynamicIndicatorData (user-added indicators in dynamic sections).

    Returns the same ``{'assigned': q, 'public': q}`` pattern as :func:`query_form_data`
    so callers can apply the same RBAC / pagination helpers.

    Unlike regular FormData, DynamicIndicatorData has no ``form_item_id`` — it references
    ``indicator_bank_id`` directly.  Callers identify the template via the AES → AssignedForm
    join, so ``template_id`` filtering works the same way.
    """
    from app.models.forms import DynamicIndicatorData

    needs_aes_join = bool(
        template_id or country_id or period_name or submission_id or assignment_ids
    )

    # --- Assigned path ---
    assigned_q = DynamicIndicatorData.query.filter(
        DynamicIndicatorData.assignment_entity_status_id.isnot(None)
    )
    if needs_aes_join:
        assigned_q = assigned_q.join(
            AssignmentEntityStatus,
            DynamicIndicatorData.assignment_entity_status_id == AssignmentEntityStatus.id,
        ).join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)

    # --- Public path ---
    public_q = DynamicIndicatorData.query.filter(
        DynamicIndicatorData.public_submission_id.isnot(None)
    )
    if needs_aes_join:
        public_q = public_q.join(
            PublicSubmission,
            DynamicIndicatorData.public_submission_id == PublicSubmission.id,
        ).join(AssignedForm, PublicSubmission.assigned_form_id == AssignedForm.id)

    # --- Shared filters ---
    if assignment_ids:
        assigned_q = _filter_by_assignment_ids(assigned_q, assignment_ids)
        public_q = _filter_by_assignment_ids(public_q, assignment_ids)
    else:
        if template_id:
            assigned_q = assigned_q.filter(AssignedForm.template_id == template_id)
            public_q = public_q.filter(AssignedForm.template_id == template_id)
        if period_name:
            _pat = f"%{escape_like_pattern(period_name)}%"
            _period_filter = AssignedForm.period_name.ilike(_pat, escape="\\")
            assigned_q = assigned_q.filter(_period_filter)
            public_q = public_q.filter(_period_filter)

    if country_id:
        assigned_q = assigned_q.filter(
            AssignmentEntityStatus.entity_id == country_id,
            AssignmentEntityStatus.entity_type == 'country',
        )
        public_q = public_q.filter(PublicSubmission.country_id == country_id)

    if submission_id:
        assigned_q = assigned_q.filter(AssignmentEntityStatus.id == submission_id)
        public_q = public_q.filter(PublicSubmission.id == submission_id)

    if section_id:
        assigned_q = assigned_q.filter(DynamicIndicatorData.section_id == section_id)
        public_q = public_q.filter(DynamicIndicatorData.section_id == section_id)

    if indicator_bank_id:
        assigned_q = assigned_q.filter(DynamicIndicatorData.indicator_bank_id == indicator_bank_id)
        public_q = public_q.filter(DynamicIndicatorData.indicator_bank_id == indicator_bank_id)

    if preload:
        from sqlalchemy.orm import joinedload
        assigned_q = assigned_q.options(
            joinedload(DynamicIndicatorData.assignment_entity_status).joinedload(
                AssignmentEntityStatus.assigned_form
            ),
            joinedload(DynamicIndicatorData.indicator_bank),
            joinedload(DynamicIndicatorData.section),
        )
        public_q = public_q.options(
            joinedload(DynamicIndicatorData.public_submission).joinedload(
                PublicSubmission.assigned_form
            ),
            joinedload(DynamicIndicatorData.indicator_bank),
            joinedload(DynamicIndicatorData.section),
        )

    # Privacy: DynamicIndicatorData has no form_item, so no item-level privacy gate applies.
    # Template-level access is the boundary (enforced by callers via template_id scoping).

    return {
        'assigned': None if submission_type == 'public' else assigned_q,
        'public': None if submission_type == 'assigned' else public_q,
    }


def query_repeat_group_data(
    *,
    template_id: Optional[int] = None,
    submission_id: Optional[int] = None,
    item_id: Optional[int] = None,
    country_id: Optional[int] = None,
    period_name: Optional[str] = None,
    assignment_ids: Optional[List[int]] = None,
    section_id: Optional[int] = None,
    submission_type: Optional[str] = None,
    preload: bool = False,
) -> Dict[str, Any]:
    """
    Build SQLAlchemy queries for RepeatGroupData (field answers inside repeat-section instances).

    Returns the same ``{'assigned': q, 'public': q}`` pattern as :func:`query_form_data`.

    Each row has a ``form_item_id`` (same semantics as regular FormData) plus
    ``repeat_instance_id``, ``instance_number``, and ``instance_label`` for grouping.
    """
    from app.models.forms import RepeatGroupData, RepeatGroupInstance

    needs_instance_join = bool(
        template_id or country_id or period_name or submission_id or section_id or assignment_ids
    )

    # --- Assigned path ---
    assigned_q = RepeatGroupData.query.join(
        RepeatGroupInstance,
        RepeatGroupData.repeat_instance_id == RepeatGroupInstance.id,
    ).filter(RepeatGroupInstance.assignment_entity_status_id.isnot(None))

    if needs_instance_join:
        assigned_q = assigned_q.join(
            AssignmentEntityStatus,
            RepeatGroupInstance.assignment_entity_status_id == AssignmentEntityStatus.id,
        ).join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)

    # --- Public path ---
    public_q = RepeatGroupData.query.join(
        RepeatGroupInstance,
        RepeatGroupData.repeat_instance_id == RepeatGroupInstance.id,
    ).filter(RepeatGroupInstance.public_submission_id.isnot(None))

    if needs_instance_join:
        public_q = public_q.join(
            PublicSubmission,
            RepeatGroupInstance.public_submission_id == PublicSubmission.id,
        ).join(AssignedForm, PublicSubmission.assigned_form_id == AssignedForm.id)

    # --- Shared filters ---
    if assignment_ids:
        assigned_q = _filter_by_assignment_ids(assigned_q, assignment_ids)
        public_q = _filter_by_assignment_ids(public_q, assignment_ids)
    else:
        if template_id:
            assigned_q = assigned_q.filter(AssignedForm.template_id == template_id)
            public_q = public_q.filter(AssignedForm.template_id == template_id)
        if period_name:
            _pat = f"%{escape_like_pattern(period_name)}%"
            _period_filter = AssignedForm.period_name.ilike(_pat, escape="\\")
            assigned_q = assigned_q.filter(_period_filter)
            public_q = public_q.filter(_period_filter)

    if country_id:
        assigned_q = assigned_q.filter(
            AssignmentEntityStatus.entity_id == country_id,
            AssignmentEntityStatus.entity_type == 'country',
        )
        public_q = public_q.filter(PublicSubmission.country_id == country_id)

    if submission_id:
        assigned_q = assigned_q.filter(AssignmentEntityStatus.id == submission_id)
        public_q = public_q.filter(PublicSubmission.id == submission_id)

    if section_id:
        assigned_q = assigned_q.filter(RepeatGroupInstance.section_id == section_id)
        public_q = public_q.filter(RepeatGroupInstance.section_id == section_id)

    if item_id:
        assigned_q = assigned_q.filter(RepeatGroupData.form_item_id == item_id)
        public_q = public_q.filter(RepeatGroupData.form_item_id == item_id)

    if preload:
        from sqlalchemy.orm import joinedload
        assigned_q = assigned_q.options(
            joinedload(RepeatGroupData.repeat_instance).joinedload(
                RepeatGroupInstance.assignment_entity_status
            ).joinedload(AssignmentEntityStatus.assigned_form),
            joinedload(RepeatGroupData.repeat_instance).joinedload(
                RepeatGroupInstance.section
            ),
            joinedload(RepeatGroupData.form_item),
        )
        public_q = public_q.options(
            joinedload(RepeatGroupData.repeat_instance).joinedload(
                RepeatGroupInstance.public_submission
            ).joinedload(PublicSubmission.assigned_form),
            joinedload(RepeatGroupData.repeat_instance).joinedload(
                RepeatGroupInstance.section
            ),
            joinedload(RepeatGroupData.form_item),
        )

    # Privacy: apply the same public-only gate that query_form_data uses on FormData.form_item.
    viewer = get_effective_request_user()
    if not can_view_non_public_form_items(viewer):
        public_only = form_item_privacy_is_public_expr()
        assigned_q = assigned_q.filter(RepeatGroupData.form_item.has(public_only))
        public_q = public_q.filter(RepeatGroupData.form_item.has(public_only))

    return {
        'assigned': None if submission_type == 'public' else assigned_q,
        'public': None if submission_type == 'assigned' else public_q,
    }
