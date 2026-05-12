# File: Backoffice/app/services/governance_metrics_service.py
"""
Governance metrics for the Admin Governance dashboard (federation / NS–secretariat style deployments).

Aggregates: focal point / data owner coverage, access control (RBAC),
reporting timeliness and quality, FDRS document compliance, metadata (Indicator Bank /
form) completeness, security & audit events, and translation coverage.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, List

from sqlalchemy import distinct, func, and_, or_, text

from app import db
from app.models import (
    User,
    Country,
    FormTemplate,
    AssignedForm,
    FormItem,
    AssignmentEntityStatus,
    SubmittedDocument,
)
from app.models.forms import FormTemplateVersion
from app.models.core import UserEntityPermission
from app.models.rbac import (
    RbacPermission,
    RbacRole,
    RbacRolePermission,
    RbacUserRole,
    RbacAccessGrant,
)
from app.utils.datetime_helpers import ensure_utc, utcnow

logger = logging.getLogger(__name__)

# FDRS template and compliance doc types (aligned with data_exploration)
FDRS_TEMPLATE_ID = 21
COMPLIANCE_DOC_TYPES = ["Annual Report", "Audited Financial Statement"]

# Max countries per user to flag for "many countries" review
MAX_COUNTRIES_PER_USER_FLAG = 10

# Hardcoded fallback; prefer system-enabled languages via get_supported_languages()
_FALLBACK_TRANSLATABLE_LANGS = ["fr", "es", "ar", "ru", "zh", "hi"]

# Overdue severity thresholds (days)
OVERDUE_CRITICAL_DAYS = 30
OVERDUE_HIGH_DAYS = 8
OVERDUE_MEDIUM_DAYS = 1

# Stale suggestion age (days)
STALE_SUGGESTION_DAYS = 30


def get_governance_metrics() -> Dict[str, Any]:
    """
    Compute all governance metrics for the dashboard.

    Each section runs in its own try/except with a rollback so that a failure
    in one pillar does not abort the PostgreSQL transaction and cascade to the
    remaining sections.

    Returns a dict containing health_score, ownership, access_control, quality,
    compliance, and metadata sections. Security & Audit and Translation Coverage
    are handled separately by the Admin Dashboard.
    """
    empty = _empty_metrics()

    def _safe(name, fn, fallback):
        try:
            result = fn()
            db.session.rollback()  # release any implicit transaction cleanly
            return result
        except Exception as exc:
            logger.error("Governance metric section '%s' failed: %s", name, exc)
            try:
                db.session.rollback()
            except Exception as rb_err:
                logger.debug("_safe rollback failed: %s", rb_err)
            return fallback

    ownership = _safe("ownership", _get_ownership_metrics, empty["ownership"])
    access_control = _safe("access_control", _get_access_control_metrics, empty["access_control"])
    quality = _safe("quality", _get_quality_metrics, empty["quality"])
    compliance = _safe("compliance", _get_compliance_metrics, empty["compliance"])
    metadata = _safe("metadata", _get_metadata_metrics, empty["metadata"])

    sections = {
        "ownership": ownership,
        "access_control": access_control,
        "quality": quality,
        "compliance": compliance,
        "metadata": metadata,
    }

    try:
        health_score = _calculate_health_score(sections)
    except Exception as exc:
        logger.error("Health score calculation failed: %s", exc)
        try:
            db.session.rollback()
        except Exception as rb_err:
            logger.debug("Health score rollback failed: %s", rb_err)
        health_score = empty["health_score"]

    return {"health_score": health_score, **sections}


# ---------------------------------------------------------------------------
# Health Score
# ---------------------------------------------------------------------------

def _calculate_health_score(sections: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute a 0–100 governance health score from weighted pillar scores.

    Security & Audit and Translation Coverage have been moved to the Admin Dashboard.
    Weights (5 governance pillars, total 100%):
      Ownership 18% | Access Control 23% | Quality 23% | Compliance 23% | Metadata 13%
    """
    weights = {
        "ownership": 18,
        "access_control": 23,
        "quality": 23,
        "compliance": 23,
        "metadata": 13,
    }

    def _ownership_score(o):
        total = o.get("total_countries", 0)
        if not total:
            return 50
        fp_pct = o.get("countries_with_focal_point", 0) / total * 100
        active_no_owner = o.get("active_assignments_without_data_owner", 0)
        penalty = min(20, active_no_owner * 2)
        return max(0, fp_pct - penalty)

    def _access_score(ac):
        total = User.query.count() or 1
        users_with_role = ac.get("users_with_role", 0)
        inactive_ghosts = ac.get("inactive_users_with_role", 0)
        ghost_penalty = min(20, inactive_ghosts * 2)
        return max(0, (users_with_role / total * 100) - ghost_penalty)

    def _quality_score(q):
        return min(100, q.get("submission_rate_pct", 0))

    def _compliance_score(c):
        return min(100, c.get("compliance_rate_pct", 0))

    def _metadata_score(m):
        total = m.get("indicators_total", 0)
        if not total:
            return 50
        with_def = m.get("indicators_with_definition", 0)
        return round(with_def / total * 100, 1)

    try:
        pillar_scores = {
            "ownership": _ownership_score(sections.get("ownership", {})),
            "access_control": _access_score(sections.get("access_control", {})),
            "quality": _quality_score(sections.get("quality", {})),
            "compliance": _compliance_score(sections.get("compliance", {})),
            "metadata": _metadata_score(sections.get("metadata", {})),
        }

        score = sum(
            pillar_scores[k] * weights[k] / 100 for k in weights
        )
        score = round(score, 1)

        grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 45 else "F"
        color = (
            "green" if grade == "A"
            else "blue" if grade == "B"
            else "yellow" if grade == "C"
            else "orange" if grade == "D"
            else "red"
        )

        return {
            "score": score,
            "grade": grade,
            "color": color,
            "pillar_scores": pillar_scores,
        }
    except Exception as e:
        logger.warning("Health score calculation failed: %s", e)
        return {"score": 0, "grade": "F", "color": "red", "pillar_scores": {}}


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------

def _get_ownership_metrics() -> Dict[str, Any]:
    """Focal point / data owner coverage."""
    from app.models.indicator_bank import IndicatorBank

    total_countries = Country.query.count()
    countries_with_perm = (
        db.session.query(UserEntityPermission.entity_id)
        .filter(UserEntityPermission.entity_type == "country")
        .distinct()
        .all()
    )
    country_ids_with_focal = {r[0] for r in countries_with_perm}
    countries_with_focal_point = len(country_ids_with_focal)
    countries_without_focal_point = total_countries - countries_with_focal_point

    total_users = User.query.count()
    users_with_entities = (
        db.session.query(UserEntityPermission.user_id).distinct().count()
    )
    users_without_entities = max(0, total_users - users_with_entities)

    # Flags: countries without focal point
    all_country_ids = {c.id for c in Country.query.with_entities(Country.id).all()}
    ids_without_focal = all_country_ids - country_ids_with_focal
    countries_without_focal_point_list = [
        {"id": c.id, "name": c.name}
        for c in Country.query.filter(Country.id.in_(ids_without_focal)).order_by(Country.name).all()
    ]

    # Users assigned to many countries (>threshold)
    user_country_counts = (
        db.session.query(
            UserEntityPermission.user_id,
            func.count(UserEntityPermission.id).label("cnt"),
        )
        .filter(UserEntityPermission.entity_type == "country")
        .group_by(UserEntityPermission.user_id)
        .having(func.count(UserEntityPermission.id) > MAX_COUNTRIES_PER_USER_FLAG)
        .all()
    )
    users_with_many_countries = [
        {"user_id": u[0], "country_count": u[1]}
        for u in user_country_counts
    ]

    templates_without_owner = FormTemplate.query.filter(
        FormTemplate.owned_by.is_(None)
    ).count()

    # Assignment data owner gaps
    total_active_assignments = AssignedForm.query.filter(AssignedForm.is_active == True).count()
    assignments_without_data_owner = AssignedForm.query.filter(
        AssignedForm.data_owner_id.is_(None)
    ).count()
    active_assignments_without_data_owner = AssignedForm.query.filter(
        AssignedForm.is_active == True,
        AssignedForm.data_owner_id.is_(None),
    ).count()
    active_assignments_no_owner_list = [
        {
            "id": a.id,
            "period_name": a.period_name,
            "template_name": a.template.name if a.template else "Unknown",
        }
        for a in AssignedForm.query.filter(
            AssignedForm.is_active == True,
            AssignedForm.data_owner_id.is_(None),
        ).limit(30).all()
    ]

    # AES approved without approver recorded (legacy gap)
    approved_aes_without_approver = AssignmentEntityStatus.query.filter(
        AssignmentEntityStatus.status == "Approved",
        AssignmentEntityStatus.approved_by_user_id.is_(None),
    ).count()

    # Countries with no preferred_language set
    try:
        countries_missing_language = Country.query.filter(
            or_(
                Country.preferred_language.is_(None),
                Country.preferred_language == "",
            )
        ).count()
        countries_missing_language_list = [
            {"id": c.id, "name": c.name}
            for c in Country.query.filter(
                or_(Country.preferred_language.is_(None), Country.preferred_language == "")
            ).order_by(Country.name).limit(30).all()
        ]
    except Exception as e:
        logger.debug("countries_missing_language query failed: %s", e)
        try:
            db.session.rollback()
        except Exception as rollback_e:
            logger.debug("rollback failed: %s", rollback_e)
        countries_missing_language = 0
        countries_missing_language_list = []

    # Users with entity permissions but zero RBAC roles (can log in, can't do anything useful)
    user_ids_with_entity = {
        r[0] for r in db.session.query(distinct(UserEntityPermission.user_id)).all()
    }
    user_ids_with_rbac = {
        r[0] for r in db.session.query(distinct(RbacUserRole.user_id)).all()
    }
    user_ids_with_entity_no_role = user_ids_with_entity - user_ids_with_rbac
    users_with_entities_no_role = len(user_ids_with_entity_no_role)
    users_with_entities_no_role_list = [
        {"id": u.id, "email": u.email, "name": u.name}
        for u in User.query.filter(User.id.in_(user_ids_with_entity_no_role)).limit(30).all()
    ] if user_ids_with_entity_no_role else []

    return {
        "total_countries": total_countries,
        "countries_with_focal_point": countries_with_focal_point,
        "countries_without_focal_point": countries_without_focal_point,
        "users_without_entities": users_without_entities,
        "templates_without_owner": templates_without_owner,
        "total_active_assignments": total_active_assignments,
        "assignments_without_data_owner": assignments_without_data_owner,
        "active_assignments_without_data_owner": active_assignments_without_data_owner,
        "approved_aes_without_approver": approved_aes_without_approver,
        "countries_missing_language": countries_missing_language,
        "users_with_entities_no_role": users_with_entities_no_role,
        "flags": {
            "countries_without_focal_point": countries_without_focal_point_list,
            "users_with_many_countries": users_with_many_countries,
            "active_assignments_no_owner": active_assignments_no_owner_list,
            "countries_missing_language": countries_missing_language_list,
            "users_with_entities_no_role": users_with_entities_no_role_list,
        },
    }


# ---------------------------------------------------------------------------
# Access Control
# ---------------------------------------------------------------------------

def _get_access_control_metrics() -> Dict[str, Any]:
    """RBAC: roles, users with/without role, scoped grants, and flags."""
    roles_count = RbacRole.query.count()
    scoped_grants = RbacAccessGrant.query.count()

    users_with_role = db.session.query(RbacUserRole.user_id).distinct().count()
    total_users = User.query.count()
    users_without_role = max(0, total_users - users_with_role)

    # Orphan permissions (not used by any role or grant)
    perm_ids_in_roles = (
        db.session.query(RbacRolePermission.permission_id).distinct().all()
    )
    perm_ids_in_grants = (
        db.session.query(RbacAccessGrant.permission_id).distinct().all()
    )
    used_perm_ids = {p[0] for p in perm_ids_in_roles} | {p[0] for p in perm_ids_in_grants}
    orphan_permissions = RbacPermission.query.filter(
        ~RbacPermission.id.in_(used_perm_ids)
    ).count() if used_perm_ids else RbacPermission.query.count()

    # Ghost access: inactive users who still have RBAC roles
    inactive_users_with_role = (
        db.session.query(User.id)
        .join(RbacUserRole, User.id == RbacUserRole.user_id)
        .filter(User.active == False)
        .distinct()
        .count()
    )
    inactive_ghost_list = [
        {"id": u.id, "email": u.email, "name": u.name}
        for u in (
            db.session.query(User)
            .join(RbacUserRole, User.id == RbacUserRole.user_id)
            .filter(User.active == False)
            .distinct()
            .limit(30)
            .all()
        )
    ]

    # Users with no role at all
    user_ids_with_role = {r[0] for r in db.session.query(RbacUserRole.user_id).distinct().all()}
    users_with_no_role_list = [
        {"id": u.id, "email": u.email}
        for u in User.query.filter(~User.id.in_(user_ids_with_role)).limit(50).all()
    ]

    # Roles with no users
    role_ids_with_users = {r[0] for r in db.session.query(RbacUserRole.role_id).distinct().all()}
    roles_with_no_users = [
        {"id": r.id, "code": r.code, "name": r.name}
        for r in RbacRole.query.filter(~RbacRole.id.in_(role_ids_with_users)).all()
    ]

    return {
        "roles": roles_count,
        "users_with_role": users_with_role,
        "users_without_role": users_without_role,
        "scoped_grants": scoped_grants,
        "orphan_permissions": orphan_permissions,
        "inactive_users_with_role": inactive_users_with_role,
        "flags": {
            "users_with_no_role": users_with_no_role_list,
            "roles_with_no_users": roles_with_no_users,
            "inactive_ghost_users": inactive_ghost_list,
        },
    }


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------

def _get_quality_metrics() -> Dict[str, Any]:
    """Assignment and submission health: status counts, overdue, submission rate, never-started."""
    base = AssignmentEntityStatus.query.filter(
        AssignmentEntityStatus.entity_type == "country"
    )
    total_country_assignments = base.count()

    by_status = (
        db.session.query(AssignmentEntityStatus.status, func.count(AssignmentEntityStatus.id))
        .filter(AssignmentEntityStatus.entity_type == "country")
        .group_by(AssignmentEntityStatus.status)
        .all()
    )
    by_status_dict = {s: c for s, c in by_status}

    now = utcnow()
    overdue_q = AssignmentEntityStatus.query.filter(
        and_(
            AssignmentEntityStatus.entity_type == "country",
            AssignmentEntityStatus.due_date.isnot(None),
            AssignmentEntityStatus.due_date < now,
            AssignmentEntityStatus.status.in_(["Assigned", "In Progress"]),
        )
    )
    overdue_count = overdue_q.count()

    submitted_or_approved = by_status_dict.get("Submitted", 0) + by_status_dict.get("Approved", 0)
    submission_rate_pct = (
        (submitted_or_approved / total_country_assignments * 100.0)
        if total_country_assignments else 0.0
    )

    # Overdue list with severity buckets
    # FormTemplate.name is a @property; use FormTemplateVersion.name (the real column) via join
    from sqlalchemy import func as _func
    overdue_rows = (
        overdue_q
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .join(FormTemplate, AssignedForm.template_id == FormTemplate.id)
        .outerjoin(
            FormTemplateVersion,
            FormTemplate.published_version_id == FormTemplateVersion.id,
        )
        .join(Country, AssignmentEntityStatus.entity_id == Country.id)
        .with_entities(
            _func.coalesce(FormTemplateVersion.name, AssignedForm.period_name).label("template_name"),
            Country.name.label("country_name"),
            AssignmentEntityStatus.due_date,
            AssignmentEntityStatus.id,
        )
        .order_by(AssignmentEntityStatus.due_date.asc())
        .limit(50)
        .all()
    )
    overdue_list = []
    severity_counts = {"critical": 0, "high": 0, "medium": 0}
    for r in overdue_rows:
        due = ensure_utc(r.due_date) if r.due_date else None
        days_overdue = (now - due).days if due else 0
        if days_overdue > OVERDUE_CRITICAL_DAYS:
            sev = "critical"
        elif days_overdue > OVERDUE_HIGH_DAYS:
            sev = "high"
        else:
            sev = "medium"
        severity_counts[sev] += 1
        overdue_list.append({
            "template_name": r.template_name,
            "country_name": r.country_name,
            "due_date": r.due_date.isoformat() if r.due_date else None,
            "days_overdue": days_overdue,
            "severity": sev,
            "assignment_entity_status_id": r.id,
        })

    # Assignments with no entity statuses
    af_ids_with_entities = {
        a[0] for a in db.session.query(distinct(AssignmentEntityStatus.assigned_form_id)).all()
    }
    all_af_ids = {a[0] for a in db.session.query(AssignedForm.id).all()}
    af_ids_without_entities = all_af_ids - af_ids_with_entities
    assignments_with_no_entities = [
        {"id": a.id, "period_name": a.period_name, "template_id": a.template_id}
        for a in AssignedForm.query.filter(AssignedForm.id.in_(af_ids_without_entities)).limit(30).all()
    ]

    # Never-started assignments: all entities still in Pending
    # Subquery: assignments where every entity status is Pending
    try:
        non_pending_af_ids = {
            r[0] for r in db.session.query(distinct(AssignmentEntityStatus.assigned_form_id))
            .filter(AssignmentEntityStatus.status != "Pending")
            .all()
        }
        all_af_ids_with_entities = {
            r[0] for r in db.session.query(distinct(AssignmentEntityStatus.assigned_form_id)).all()
        }
        never_started_af_ids = all_af_ids_with_entities - non_pending_af_ids
        never_started_count = len(never_started_af_ids)
        never_started_list = [
            {
                "id": a.id,
                "period_name": a.period_name,
                "template_name": a.template.name if a.template else "Unknown",
                "entity_count": a.entity_statuses.count(),
            }
            for a in AssignedForm.query.filter(
                AssignedForm.id.in_(never_started_af_ids),
                AssignedForm.is_active == True,
            ).limit(20).all()
        ]
    except Exception as e:
        logger.debug("never_started_count query failed: %s", e)
        try:
            db.session.rollback()
        except Exception as rollback_e:
            logger.debug("rollback failed: %s", rollback_e)
        never_started_count = 0
        never_started_list = []

    # Templates with no AssignedForm
    template_ids_with_af = {a[0] for a in db.session.query(distinct(AssignedForm.template_id)).all()}
    all_template_ids = {t[0] for t in db.session.query(FormTemplate.id).all()}
    template_ids_without_af = all_template_ids - template_ids_with_af
    templates_with_no_assigned_form = [
        {"id": t.id, "name": t.name}
        for t in FormTemplate.query.filter(FormTemplate.id.in_(template_ids_without_af)).limit(30).all()
    ]

    return {
        "total_country_assignments": total_country_assignments,
        "by_status": by_status_dict,
        "overdue_count": overdue_count,
        "overdue_by_severity": severity_counts,
        "submission_rate_pct": round(submission_rate_pct, 1),
        "never_started_count": never_started_count,
        "flags": {
            "overdue": overdue_list,
            "never_started": never_started_list,
            "assignments_with_no_entities": assignments_with_no_entities,
            "templates_with_no_assigned_form": templates_with_no_assigned_form,
        },
    }


# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------

def _get_compliance_metrics() -> Dict[str, Any]:
    """FDRS document compliance: Annual Report + Audited Financial Statement in last 3 periods."""
    all_periods_query = (
        db.session.query(distinct(AssignedForm.period_name))
        .filter(
            AssignedForm.template_id == FDRS_TEMPLATE_ID,
            AssignedForm.period_name.isnot(None),
        )
        .order_by(AssignedForm.period_name.desc())
        .all()
    )
    all_periods = [p[0] for p in all_periods_query if p[0]]
    periods = all_periods[:3]

    if not periods:
        total_countries = Country.query.count()
        return {
            "compliant_count": 0,
            "non_compliant_count": total_countries,
            "compliance_rate_pct": 0.0,
            "flags": {"non_compliant_countries": []},
        }

    countries = Country.query.order_by(Country.name).all()
    doc_items = (
        FormItem.query.filter(
            FormItem.template_id == FDRS_TEMPLATE_ID,
            FormItem.item_type == "document_field",
            FormItem.archived == False,
        ).all()
    )

    doc_item_map = {}
    all_doc_item_ids = []
    for item in doc_items:
        label = (item.label or "").strip()
        for doc_type in COMPLIANCE_DOC_TYPES:
            if doc_type.lower() in label.lower():
                if doc_type not in doc_item_map:
                    doc_item_map[doc_type] = []
                doc_item_map[doc_type].append(item.id)
                all_doc_item_ids.append(item.id)
                break
    item_id_to_doc_type = {}
    for doc_type, item_ids in doc_item_map.items():
        for item_id in item_ids:
            item_id_to_doc_type[item_id] = doc_type

    assignments = (
        AssignedForm.query.filter(
            AssignedForm.template_id == FDRS_TEMPLATE_ID,
            AssignedForm.period_name.in_(periods),
        ).all()
    )
    assignment_map = {a.period_name: a for a in assignments}
    assignment_ids = [a.id for a in assignments]

    all_aes = []
    if assignment_ids:
        all_aes = (
            AssignmentEntityStatus.query.filter(
                AssignmentEntityStatus.assigned_form_id.in_(assignment_ids),
                AssignmentEntityStatus.entity_type == "country",
            ).all()
        )
    aes_lookup = {}
    aes_ids = []
    for aes in all_aes:
        aes_lookup[(aes.assigned_form_id, aes.entity_id)] = aes
        aes_ids.append(aes.id)

    submitted_docs = []
    if aes_ids and all_doc_item_ids:
        submitted_docs = (
            SubmittedDocument.query.filter(
                SubmittedDocument.assignment_entity_status_id.in_(aes_ids),
                SubmittedDocument.form_item_id.in_(all_doc_item_ids),
            ).all()
        )
    doc_lookup = {}
    for doc in submitted_docs:
        doc_type = item_id_to_doc_type.get(doc.form_item_id)
        if doc_type:
            doc_lookup[(doc.assignment_entity_status_id, doc_type)] = True

    compliant_count = 0
    non_compliant_list = []

    for country in countries:
        has_annual_report = False
        has_audited_financial = False
        for period in periods:
            assignment = assignment_map.get(period)
            if assignment:
                aes = aes_lookup.get((assignment.id, country.id))
                if aes:
                    for doc_type in COMPLIANCE_DOC_TYPES:
                        if doc_lookup.get((aes.id, doc_type)):
                            if doc_type == "Annual Report":
                                has_annual_report = True
                            elif doc_type == "Audited Financial Statement":
                                has_audited_financial = True
        is_compliant = has_annual_report and has_audited_financial
        if is_compliant:
            compliant_count += 1
        else:
            non_compliant_list.append(
                {"id": country.id, "name": country.name, "iso3": country.iso3}
            )

    non_compliant_count = len(non_compliant_list)
    total = len(countries)
    compliance_rate_pct = round((compliant_count / total * 100.0) if total else 0.0, 1)

    return {
        "compliant_count": compliant_count,
        "non_compliant_count": non_compliant_count,
        "compliance_rate_pct": compliance_rate_pct,
        "flags": {"non_compliant_countries": non_compliant_list[:100]},
    }


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def _get_metadata_metrics() -> Dict[str, Any]:
    """Indicator Bank and form item completeness, published templates never assigned, stale suggestions."""
    from app.models.indicator_bank import IndicatorBank, IndicatorSuggestion

    indicators_total = IndicatorBank.query.count()
    indicators_with_definition = IndicatorBank.query.filter(
        and_(
            IndicatorBank.archived == False,
            IndicatorBank.definition.isnot(None),
            IndicatorBank.definition != "",
        )
    ).count()
    indicators_without_definition = IndicatorBank.query.filter(
        and_(
            IndicatorBank.archived == False,
            or_(
                IndicatorBank.definition.is_(None),
                IndicatorBank.definition == "",
            ),
        )
    ).count()
    archived_indicators = IndicatorBank.query.filter(IndicatorBank.archived == True).count()

    form_items_total = FormItem.query.filter(FormItem.archived == False).count()
    form_items_with_description = (
        db.session.query(FormItem)
        .outerjoin(IndicatorBank, FormItem.indicator_bank_id == IndicatorBank.id)
        .filter(
            FormItem.archived == False,
            or_(
                and_(FormItem.definition.isnot(None), FormItem.definition != ""),
                and_(FormItem.description.isnot(None), FormItem.description != ""),
                and_(
                    FormItem.indicator_bank_id.isnot(None),
                    IndicatorBank.definition.isnot(None),
                    IndicatorBank.definition != "",
                ),
            ),
        )
        .count()
    )
    form_items_without_description = form_items_total - form_items_with_description

    # Published templates that have never been assigned
    template_ids_with_af = {
        r[0] for r in db.session.query(distinct(AssignedForm.template_id)).all()
    }
    published_templates = FormTemplate.query.filter(
        FormTemplate.published_version_id.isnot(None)
    ).all()
    published_never_assigned_list = [
        {"id": t.id, "name": t.name}
        for t in published_templates
        if t.id not in template_ids_with_af
    ]
    published_never_assigned = len(published_never_assigned_list)

    # Stale indicator suggestions (>30 days in Pending)
    stale_cutoff = utcnow() - timedelta(days=STALE_SUGGESTION_DAYS)
    try:
        stale_suggestions_q = IndicatorSuggestion.query.filter(
            IndicatorSuggestion.status == "Pending",
            IndicatorSuggestion.submitted_at < stale_cutoff,
        )
        indicator_suggestions_stale = stale_suggestions_q.count()
        stale_suggestions_list = [
            {
                "id": s.id,
                "indicator_name": s.indicator_name,
                "submitter": s.submitter_name,
                "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None,
            }
            for s in stale_suggestions_q.order_by(IndicatorSuggestion.submitted_at.asc()).limit(20).all()
        ]
    except Exception as e:
        logger.debug("indicator_suggestions_stale query failed: %s", e)
        try:
            db.session.rollback()
        except Exception as rollback_e:
            logger.debug("rollback failed: %s", rollback_e)
        indicator_suggestions_stale = 0
        stale_suggestions_list = []

    return {
        "indicators_total": indicators_total,
        "indicators_with_definition": indicators_with_definition,
        "indicators_without_definition": indicators_without_definition,
        "form_items_total": form_items_total,
        "form_items_with_description": form_items_with_description,
        "form_items_without_description": form_items_without_description,
        "archived_indicators": archived_indicators,
        "published_never_assigned": published_never_assigned,
        "indicator_suggestions_stale": indicator_suggestions_stale,
        "flags": {
            "indicators_without_definition": indicators_without_definition,
            "form_items_without_description": form_items_without_description,
            "published_never_assigned": published_never_assigned_list[:20],
            "stale_suggestions": stale_suggestions_list,
        },
    }


# ---------------------------------------------------------------------------
# Security & Audit
# ---------------------------------------------------------------------------

def _get_security_audit_metrics() -> Dict[str, Any]:
    """Security events, admin actions, and login audit metrics."""
    from app.models.system import AdminActionLog, SecurityEvent
    from app.models.core import UserLoginLog

    cutoff_30d = utcnow() - timedelta(days=30)

    # High-risk admin actions in last 30 days
    try:
        high_risk_actions_30d = AdminActionLog.query.filter(
            AdminActionLog.timestamp >= cutoff_30d,
            AdminActionLog.risk_level.in_(["high", "critical"]),
        ).count()

        actions_requiring_review = [
            {
                "id": a.id,
                "action_type": a.action_type,
                "admin_email": a.admin_user.email if a.admin_user else "Unknown",
                "timestamp": a.timestamp.isoformat() if a.timestamp else None,
                "risk_level": a.risk_level,
            }
            for a in AdminActionLog.query.filter(
                AdminActionLog.requires_review == True
            ).order_by(AdminActionLog.timestamp.desc()).limit(20).all()
        ]
    except Exception as e:
        logger.debug("high_risk_actions_30d query failed: %s", e)
        try:
            db.session.rollback()
        except Exception as rollback_e:
            logger.debug("rollback failed: %s", rollback_e)
        high_risk_actions_30d = 0
        actions_requiring_review = []

    # Security events
    try:
        unresolved_security_events = SecurityEvent.query.filter(
            SecurityEvent.is_resolved == False
        ).count()

        severity_breakdown = {}
        for sev in ["low", "medium", "high", "critical"]:
            severity_breakdown[sev] = SecurityEvent.query.filter(
                SecurityEvent.severity == sev,
                SecurityEvent.is_resolved == False,
            ).count()
    except Exception as e:
        logger.debug("unresolved_security_events query failed: %s", e)
        try:
            db.session.rollback()
        except Exception as rollback_e:
            logger.debug("rollback failed: %s", rollback_e)
        unresolved_security_events = 0
        severity_breakdown = {"low": 0, "medium": 0, "high": 0, "critical": 0}

    # Login audit
    try:
        suspicious_logins_30d = UserLoginLog.query.filter(
            UserLoginLog.timestamp >= cutoff_30d,
            UserLoginLog.is_suspicious == True,
        ).count()

        total_logins_30d = UserLoginLog.query.filter(
            UserLoginLog.timestamp >= cutoff_30d,
        ).count()
        failed_logins_30d = UserLoginLog.query.filter(
            UserLoginLog.timestamp >= cutoff_30d,
            UserLoginLog.event_type == "login_failed",
        ).count()
        failed_login_rate_30d = round(
            (failed_logins_30d / total_logins_30d * 100.0) if total_logins_30d else 0.0, 1
        )
    except Exception as e:
        logger.debug("suspicious_logins_30d query failed: %s", e)
        try:
            db.session.rollback()
        except Exception as rollback_e:
            logger.debug("rollback failed: %s", rollback_e)
        suspicious_logins_30d = 0
        failed_login_rate_30d = 0.0
        failed_logins_30d = 0
        total_logins_30d = 0

    return {
        "high_risk_actions_30d": high_risk_actions_30d,
        "actions_requiring_review_count": len(actions_requiring_review),
        "unresolved_security_events": unresolved_security_events,
        "severity_breakdown": severity_breakdown,
        "suspicious_logins_30d": suspicious_logins_30d,
        "failed_login_rate_30d": failed_login_rate_30d,
        "total_logins_30d": total_logins_30d,
        "flags": {
            "actions_requiring_review": actions_requiring_review,
        },
    }


# ---------------------------------------------------------------------------
# Translation Coverage
# ---------------------------------------------------------------------------

def _get_translation_metrics() -> Dict[str, Any]:
    """
    Per-language translation coverage (name + definition) for active IndicatorBank indicators.

    Loads all indicators once in Python and counts non-empty translation entries per language.
    Only reports on languages currently enabled in system settings (excluding English as the
    base language). Falls back to a hardcoded list if settings are unavailable.
    """
    from app.models.indicator_bank import IndicatorBank
    from app.services.app_settings_service import get_supported_languages

    enabled = get_supported_languages(default=_FALLBACK_TRANSLATABLE_LANGS)
    translatable = [l for l in enabled if l != "en"]
    if not translatable:
        translatable = list(_FALLBACK_TRANSLATABLE_LANGS)

    indicators = IndicatorBank.query.filter(IndicatorBank.archived == False).all()
    total = len(indicators)

    if not total:
        return {
            lang: {"name_pct": 0.0, "def_pct": 0.0, "name_count": 0, "def_count": 0, "total": 0}
            for lang in translatable
        }

    result = {}
    for lang in translatable:
        name_count = sum(
            1 for ind in indicators
            if isinstance(ind.name_translations, dict) and ind.name_translations.get(lang)
        )
        def_count = sum(
            1 for ind in indicators
            if isinstance(ind.definition_translations, dict) and ind.definition_translations.get(lang)
        )
        result[lang] = {
            "name_pct": round(name_count / total * 100, 1),
            "def_pct": round(def_count / total * 100, 1),
            "name_count": name_count,
            "def_count": def_count,
            "total": total,
        }

    return result


# ---------------------------------------------------------------------------
# Empty fallback
# ---------------------------------------------------------------------------

def _empty_metrics() -> Dict[str, Any]:
    """Return empty structure when metrics fail."""
    return {
        "health_score": {"score": 0, "grade": "F", "color": "red", "pillar_scores": {}},
        "ownership": {
            "total_countries": 0,
            "countries_with_focal_point": 0,
            "countries_without_focal_point": 0,
            "users_without_entities": 0,
            "templates_without_owner": 0,
            "total_active_assignments": 0,
            "assignments_without_data_owner": 0,
            "active_assignments_without_data_owner": 0,
            "approved_aes_without_approver": 0,
            "countries_missing_language": 0,
            "users_with_entities_no_role": 0,
            "flags": {
                "countries_without_focal_point": [],
                "users_with_many_countries": [],
                "active_assignments_no_owner": [],
                "countries_missing_language": [],
                "users_with_entities_no_role": [],
            },
        },
        "access_control": {
            "roles": 0,
            "users_with_role": 0,
            "users_without_role": 0,
            "scoped_grants": 0,
            "orphan_permissions": 0,
            "inactive_users_with_role": 0,
            "flags": {"users_with_no_role": [], "roles_with_no_users": [], "inactive_ghost_users": []},
        },
        "quality": {
            "total_country_assignments": 0,
            "by_status": {},
            "overdue_count": 0,
            "overdue_by_severity": {"critical": 0, "high": 0, "medium": 0},
            "submission_rate_pct": 0.0,
            "never_started_count": 0,
            "flags": {
                "overdue": [],
                "never_started": [],
                "assignments_with_no_entities": [],
                "templates_with_no_assigned_form": [],
            },
        },
        "compliance": {
            "compliant_count": 0,
            "non_compliant_count": 0,
            "compliance_rate_pct": 0.0,
            "flags": {"non_compliant_countries": []},
        },
        "metadata": {
            "indicators_total": 0,
            "indicators_with_definition": 0,
            "indicators_without_definition": 0,
            "form_items_with_description": 0,
            "form_items_without_description": 0,
            "archived_indicators": 0,
            "published_never_assigned": 0,
            "indicator_suggestions_stale": 0,
            "flags": {
                "indicators_without_definition": 0,
                "form_items_without_description": 0,
                "published_never_assigned": [],
                "stale_suggestions": [],
            },
        },
    }
