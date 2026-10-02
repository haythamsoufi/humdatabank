"""Data governance operating register.

The dashboard used to average five unrelated percentages into a grade. This
module replaces that with a control catalog:

- each control states a rule, who is accountable, and how it is tested
- a failing test opens one issue on the register
- the issue stays open until the test passes, or until a manager records a
  risk acceptance with a reason and a review date
- an acceptance expires on that date and the issue reopens

Checks are limited to facts this platform can actually prove. Submission
timeliness is not called data quality. FDRS document compliance is monitored
in Explore Data, not here. "Every account has a role" is not a control.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from flask import url_for
from flask_babel import _
from sqlalchemy import and_, case, func

from app import db
from app.models import (
    AssignedForm,
    AssignmentEntityStatus,
    Country,
    FormTemplate,
    GovernanceIssue,
)
from app.models.enums import AssignmentEntityStatusValue
from app.services.platform.governance_metrics_service import get_governance_metrics
from app.utils.datetime_helpers import ensure_utc, utcnow

logger = logging.getLogger(__name__)

EVIDENCE_LIMIT = 12
ACCEPTANCE_MIN_REASON = 10
ACCEPTANCE_MAX_REASON = 1000
ACCEPTANCE_MAX_DAYS = 365
RECENT_APPROVAL_DAYS = 90
CRITICAL_OVERDUE_DAYS = 30

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2}

DOMAIN_KEYS = (
    "ownership",
    "access",
    "reporting",
    "glossary",
    "lifecycle",
)


def build_governance_report() -> Dict[str, Any]:
    """Evaluate every control, sync the issue register, and return a view model."""
    ctx = _collect_context()
    controls = evaluate_controls(ctx)
    issues_by_code = sync_issues(controls)
    return _present(controls, issues_by_code, ctx.get("ownership") or {})


def accept_governance_issue(issue: GovernanceIssue, *, user_id: int, reason: str, until: date) -> None:
    """Record a time-bounded risk acceptance. Caller validates reason and date."""
    now = utcnow()
    issue.status = "accepted"
    issue.accepted_by_user_id = user_id
    issue.accepted_at = now
    issue.acceptance_reason = reason.strip()
    issue.accepted_until = until
    issue.last_seen_at = now
    db.session.flush()


def reopen_governance_issue(issue: GovernanceIssue) -> None:
    """Put an accepted risk back on the open queue. Clears the acceptance."""
    now = utcnow()
    issue.status = "open"
    issue.reopened_at = now
    issue.last_seen_at = now
    issue.accepted_by_user_id = None
    issue.accepted_at = None
    issue.acceptance_reason = None
    issue.accepted_until = None
    issue.resolved_at = None
    issue.resolution = None
    db.session.flush()


def validate_acceptance(reason: str, until_raw: str, *, today: Optional[date] = None) -> tuple[Optional[date], Optional[str]]:
    """Return ``(until, error)``. ``until`` is set only when the input is valid."""
    today = today or utcnow().date()
    text = (reason or "").strip()
    if len(text) < ACCEPTANCE_MIN_REASON:
        return None, _("Give a reason of at least %(n)s characters.", n=ACCEPTANCE_MIN_REASON)
    if len(text) > ACCEPTANCE_MAX_REASON:
        return None, _("The reason must be %(n)s characters or fewer.", n=ACCEPTANCE_MAX_REASON)
    try:
        until = date.fromisoformat((until_raw or "").strip())
    except ValueError:
        return None, _("Choose a review date.")
    if until <= today:
        return None, _("The review date must be in the future.")
    if until > today + timedelta(days=ACCEPTANCE_MAX_DAYS):
        return None, _("A risk acceptance can run for at most one year. Choose an earlier review date.")
    return until, None


# ---------------------------------------------------------------------------
# Evaluation (pure — no database)
# ---------------------------------------------------------------------------

def evaluate_controls(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Turn a context dict into control results. Safe to call without a database."""
    errors = set(ctx.get("errors") or [])
    return [
        _own_01(ctx, errors),
        _own_02(ctx, errors),
        _own_03(ctx, errors),
        _acc_01(ctx, errors),
        _acc_02(ctx, errors),
        _acc_03(ctx, errors),
        _rpt_01(ctx, errors),
        _rpt_02(ctx, errors),
        _met_01(ctx, errors),
        _met_02(ctx, errors),
        _lif_01(ctx, errors),
    ]


def _own_01(ctx, errors):
    spec = _spec(
        "OWN-01", "ownership", "high",
        _("Active assignments have a data owner"),
        _("Every open assignment names the person accountable for the data collected in that cycle."),
        _("Assignment administrator"),
        _href("assignment_management.manage_assignments", no_data_owner=1),
    )
    if "ownership" in errors:
        return _unknown(spec)
    samples = ctx.get("assignments_without_owner") or []
    count = int(ctx.get("assignments_without_owner_count") or len(samples))
    if count == 0:
        return _pass(spec, _("Every open assignment has a data owner."))
    return _fail(
        spec, count,
        _("%(n)s open assignment(s) have no data owner.", n=count),
        samples,
    )


def _own_02(ctx, errors):
    spec = _spec(
        "OWN-02", "ownership", "high",
        _("Published templates have an owner"),
        _("Every published template names the person accountable for the standard it defines."),
        _("Template administrator"),
        _href("form_builder.manage_templates"),
    )
    if "templates" in errors:
        return _unknown(spec)
    samples = ctx.get("templates_without_owner") or []
    count = int(ctx.get("templates_without_owner_count") or len(samples))
    if count == 0:
        return _pass(spec, _("Every published template has an owner."))
    return _fail(
        spec, count,
        _("%(n)s published template(s) have no owner.", n=count),
        samples,
    )


def _own_03(ctx, errors):
    spec = _spec(
        "OWN-03", "ownership", "high",
        _("Open assignments have a focal point"),
        _("Every country on an open assignment has at least one focal point who can submit for it. Countries that are not in a current cycle are listed in the register below and are not a failure of this control."),
        _("User administrator"),
        _href("user_management.manage_users"),
    )
    if "focal" in errors:
        return _unknown(spec)
    samples = ctx.get("countries_on_open_assignment_without_focal") or []
    if not samples:
        return _pass(spec, _("Every country on an open assignment has a focal point."))
    return _fail(
        spec, len(samples),
        _("%(n)s country assignment(s) are open with no focal point.", n=len(samples)),
        samples,
    )


def _acc_01(ctx, errors):
    spec = _spec(
        "ACC-01", "access", "high",
        _("Deactivated accounts do not keep roles"),
        _("A deactivated person cannot sign in, but a role left on the account returns the moment the account is switched back on. Remove the role when the person leaves."),
        _("User administrator"),
        _href("user_management.manage_users"),
    )
    if "access" in errors:
        return _unknown(spec)
    samples = ctx.get("ghost_users") or []
    count = max(int(ctx.get("ghost_users_count") or 0), len(samples))
    if count == 0:
        return _pass(spec, _("No deactivated account still holds a role."))
    return _fail(
        spec, count,
        _("%(n)s deactivated account(s) still hold a role.", n=count),
        samples,
    )


def _acc_02(ctx, errors):
    spec = _spec(
        "ACC-02", "access", "high",
        _("Country access comes with a role"),
        _("A person scoped to a country and given no role can sign in and still cannot do the work. Either assign the role or remove the country access."),
        _("User administrator"),
        _href("user_management.manage_users"),
    )
    if "access" in errors:
        return _unknown(spec)
    samples = ctx.get("entity_without_role") or []
    count = max(int(ctx.get("entity_without_role_count") or 0), len(samples))
    if count == 0:
        return _pass(spec, _("Nobody has country access without a role."))
    return _fail(
        spec, count,
        _("%(n)s account(s) have country access and no role.", n=count),
        samples,
    )


def _acc_03(ctx, errors):
    spec = _spec(
        "ACC-03", "access", "medium",
        _("Recent approvals name the approver"),
        _("An approval in the last 90 days records the person who approved it. Older rows from before this field existed are not part of this control."),
        _("Assignment administrator"),
        None,
    )
    if "approvals" in errors:
        return _unknown(spec)
    count = int(ctx.get("recent_approvals_without_approver") or 0)
    if count == 0:
        return _pass(spec, _("Every approval in the last 90 days records an approver."))
    return _fail(
        spec, count,
        _("%(n)s approval(s) in the last 90 days have no approver recorded.", n=count),
        [],
    )


def _rpt_01(ctx, errors):
    spec = _spec(
        "RPT-01", "reporting", "critical",
        _("Open work is not more than 30 days overdue"),
        _("On an open assignment, a country submission still in progress is not more than 30 days past its due date. This is timeliness, not a check of the values submitted."),
        _("Data owner"),
        None,
    )
    if "overdue" in errors:
        return _unknown(spec)
    samples = ctx.get("critical_overdue") or []
    count = int(ctx.get("critical_overdue_count") or len(samples))
    if count == 0:
        return _pass(spec, _("No open country submission is more than 30 days overdue."))
    return _fail(
        spec, count,
        _("%(n)s open country submission(s) are more than 30 days overdue.", n=count),
        samples,
    )


def _rpt_02(ctx, errors):
    spec = _spec(
        "RPT-02", "reporting", "high",
        _("Open assignments are not untouched after the due date"),
        _("An open assignment whose earliest due date has passed is not still entirely unstarted."),
        _("Data owner"),
        None,
    )
    if "overdue" in errors:
        return _unknown(spec)
    samples = ctx.get("unstarted_past_due") or []
    if not samples:
        return _pass(spec, _("No open assignment is still unstarted after its due date."))
    return _fail(
        spec, len(samples),
        _("%(n)s open assignment(s) are still unstarted after the due date.", n=len(samples)),
        samples,
    )


def _met_01(ctx, errors):
    spec = _spec(
        "MET-01", "glossary", "medium",
        _("Active indicators have a definition"),
        _("Every indicator that is not archived has a definition. Archived indicators are out of scope. This is the business glossary, not a score of form-field labels."),
        _("Indicator Bank manager"),
        _href("system_admin.manage_indicator_bank"),
    )
    if "glossary" in errors:
        return _unknown(spec)
    missing = int(ctx.get("indicators_missing_definition") or 0)
    defined = int(ctx.get("indicators_active") or 0)
    if missing == 0:
        return _pass(spec, _("Every active indicator has a definition."))
    return _fail(
        spec, missing,
        _("%(missing)s of %(active)s active indicators have no definition.", missing=missing, active=defined + missing),
        [],
    )


def _met_02(ctx, errors):
    spec = _spec(
        "MET-02", "glossary", "medium",
        _("Indicator suggestions are reviewed within 30 days"),
        _("A suggestion still pending after 30 days has a reviewer. The glossary does not grow a queue nobody owns."),
        _("Indicator Bank manager"),
        _href("utilities.manage_indicator_suggestions"),
    )
    if "glossary" in errors:
        return _unknown(spec)
    samples = ctx.get("stale_suggestions") or []
    count = int(ctx.get("stale_suggestions_count") or len(samples))
    if count == 0:
        return _pass(spec, _("No indicator suggestion has been pending for more than 30 days."))
    return _fail(
        spec, count,
        _("%(n)s indicator suggestion(s) have been pending for more than 30 days.", n=count),
        samples,
    )


def _lif_01(ctx, errors):
    spec = _spec(
        "LIF-01", "lifecycle", "high",
        _("Public submission links expire"),
        _("An active public link, which accepts data without a login, has an expiry date. A link with no end date stays open until someone remembers to switch it off."),
        _("Assignment administrator"),
        None,
    )
    if "public_links" in errors:
        return _unknown(spec)
    samples = ctx.get("public_links_without_expiry") or []
    count = max(int(ctx.get("public_links_without_expiry_count") or 0), len(samples))
    if count == 0:
        return _pass(spec, _("Every active public submission link has an expiry date."))
    return _fail(
        spec, count,
        _("%(n)s active public link(s) have no expiry date.", n=count),
        samples,
    )


def _spec(code, domain, severity, title, statement, accountable, href):
    return {
        "code": code,
        "domain": domain,
        "severity": severity,
        "title": title,
        "statement": statement,
        "accountable": accountable,
        "href": href,
    }


def _base(spec, status, summary, failing_count, evidence):
    return {
        **spec,
        "status": status,
        "summary": summary,
        "failing_count": failing_count,
        "evidence": list(evidence or [])[:EVIDENCE_LIMIT],
    }


def _pass(spec, summary):
    return _base(spec, "effective", summary, 0, [])


def _fail(spec, count, summary, evidence):
    return _base(spec, "gap", summary, count, evidence)


def _unknown(spec):
    return _base(spec, "unknown", _("This control could not be evaluated. The previous result was left unchanged."), 0, [])


def _href(endpoint, **values):
    try:
        return url_for(endpoint, **values)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Context collection
# ---------------------------------------------------------------------------

def _collect_context() -> Dict[str, Any]:
    errors = set()
    try:
        metrics = get_governance_metrics()
    except Exception as exc:
        logger.error("Governance metrics failed: %s", exc)
        metrics = {}
        errors.update({"ownership", "access", "glossary"})

    ownership = metrics.get("ownership") or {}
    access = metrics.get("access_control") or {}
    glossary = metrics.get("metadata") or {}

    ctx: Dict[str, Any] = {
        "errors": errors,
        "ownership": ownership,
        "assignments_without_owner": _assignment_samples(ownership),
        "assignments_without_owner_count": int(ownership.get("active_assignments_without_data_owner") or 0),
        "ghost_users": _user_samples((access.get("flags") or {}).get("inactive_ghost_users")),
        "ghost_users_count": int(access.get("inactive_users_with_role") or 0),
        "entity_without_role": _user_samples((ownership.get("flags") or {}).get("users_with_entities_no_role")),
        "entity_without_role_count": int(ownership.get("users_with_entities_no_role") or 0),
        "indicators_missing_definition": int(glossary.get("indicators_without_definition") or 0),
        "indicators_active": int(glossary.get("indicators_with_definition") or 0),
        "stale_suggestions_count": int(glossary.get("indicator_suggestions_stale") or 0),
        "stale_suggestions": _suggestion_samples((glossary.get("flags") or {}).get("stale_suggestions")),
    }
    if metrics.get("ownership") is None:
        errors.add("ownership")
    if metrics.get("access_control") is None:
        errors.add("access")
    if metrics.get("metadata") is None:
        errors.add("glossary")

    ctx["templates_without_owner"], ctx["templates_without_owner_count"], tmpl_err = _published_templates_without_owner()
    if tmpl_err:
        errors.add("templates")
    ctx["countries_on_open_assignment_without_focal"], focal_err = _countries_missing_focal(ownership)
    if focal_err:
        errors.add("focal")
    ctx["recent_approvals_without_approver"], appr_err = _recent_approvals_without_approver()
    if appr_err:
        errors.add("approvals")
    overdue, overdue_count, unstarted, overdue_err = _reporting_gaps()
    ctx["critical_overdue"] = overdue
    ctx["critical_overdue_count"] = overdue_count
    ctx["unstarted_past_due"] = unstarted
    if overdue_err:
        errors.add("overdue")
    public_samples, public_count, pub_err = _public_links_without_expiry()
    ctx["public_links_without_expiry"] = public_samples
    ctx["public_links_without_expiry_count"] = public_count
    if pub_err:
        errors.add("public_links")

    ctx["errors"] = errors
    return ctx


def _assignment_samples(ownership: Dict[str, Any]) -> List[Dict[str, Any]]:
    samples = []
    for row in (ownership.get("flags") or {}).get("active_assignments_no_owner") or []:
        label = " — ".join(
            part for part in (row.get("template_name"), row.get("period_name")) if part
        ) or _("Assignment %(id)s", id=row.get("id"))
        href = _href("assignment_management.edit_assignment", assignment_id=row.get("id")) if row.get("id") else None
        samples.append({"label": label, "href": href})
    return samples


def _user_samples(rows) -> List[Dict[str, Any]]:
    samples = []
    for row in rows or []:
        name = (row.get("name") or "").strip()
        email = (row.get("email") or "").strip()
        label = f"{name} ({email})" if name and email else (email or name or _("User %(id)s", id=row.get("id")))
        href = _href("user_management.edit_user", user_id=row.get("id")) if row.get("id") else None
        samples.append({"label": label, "href": href})
    return samples


def _suggestion_samples(rows) -> List[Dict[str, Any]]:
    href = _href("utilities.manage_indicator_suggestions")
    samples = []
    for row in rows or []:
        label = row.get("indicator_name") or _("Suggestion %(id)s", id=row.get("id"))
        samples.append({"label": label, "href": href})
    return samples


def _published_templates_without_owner():
    try:
        rows = (
            FormTemplate.query.filter(
                FormTemplate.published_version_id.isnot(None),
                FormTemplate.owned_by.is_(None),
            )
            .order_by(FormTemplate.id.asc())
            .limit(EVIDENCE_LIMIT)
            .all()
        )
        count = FormTemplate.query.filter(
            FormTemplate.published_version_id.isnot(None),
            FormTemplate.owned_by.is_(None),
        ).count()
        href = _href("form_builder.manage_templates")
        samples = [{"label": (t.name or _("Template %(id)s", id=t.id)), "href": href} for t in rows]
        return samples, count, False
    except Exception as exc:
        logger.error("OWN-02 evaluation failed: %s", exc)
        db.session.rollback()
        return [], 0, True


def _countries_missing_focal(ownership: Dict[str, Any]):
    try:
        covered = {
            row["id"]
            for row in (ownership.get("country_focal_point_coverage") or [])
            if row.get("total_focal_points", 0) > 0
        }
        rows = (
            db.session.query(Country.id, Country.name)
            .join(
                AssignmentEntityStatus,
                and_(
                    AssignmentEntityStatus.entity_id == Country.id,
                    AssignmentEntityStatus.entity_type == "country",
                ),
            )
            .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
            .filter(AssignedForm.operational_clause())
            .distinct()
            .order_by(Country.name.asc())
            .all()
        )
        # A failed ownership section returns no countries. Do not treat every
        # country on an open assignment as missing a focal point.
        if rows and not ownership.get("total_countries"):
            return [], True
        missing = [{"label": name, "href": None} for cid, name in rows if cid not in covered]
        return missing, False
    except Exception as exc:
        logger.error("OWN-03 evaluation failed: %s", exc)
        db.session.rollback()
        return [], True


def _recent_approvals_without_approver():
    try:
        cutoff = utcnow() - timedelta(days=RECENT_APPROVAL_DAYS)
        count = AssignmentEntityStatus.query.filter(
            AssignmentEntityStatus.status == AssignmentEntityStatusValue.approved,
            AssignmentEntityStatus.approved_by_user_id.is_(None),
            AssignmentEntityStatus.status_timestamp >= cutoff,
        ).count()
        return count, False
    except Exception as exc:
        logger.error("ACC-03 evaluation failed: %s", exc)
        db.session.rollback()
        return 0, True


def _overdue_days(now, due) -> int:
    """Days past due. Stored due dates are often naive UTC."""
    if due is None:
        return CRITICAL_OVERDUE_DAYS
    return max(0, (now - ensure_utc(due)).days)


def _reporting_gaps():
    try:
        now = utcnow()
        critical_before = now - timedelta(days=CRITICAL_OVERDUE_DAYS)
        overdue_q = (
            AssignmentEntityStatus.query.join(
                AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id
            )
            .join(Country, AssignmentEntityStatus.entity_id == Country.id)
            .filter(
                AssignmentEntityStatus.entity_type == "country",
                AssignmentEntityStatus.due_date.isnot(None),
                AssignmentEntityStatus.due_date < critical_before,
                AssignmentEntityStatus.status.in_([
                    AssignmentEntityStatusValue.pending,
                    AssignmentEntityStatusValue.in_progress,
                    AssignmentEntityStatusValue.requires_revision,
                    AssignmentEntityStatusValue.sent_for_review,
                ]),
                AssignedForm.operational_clause(),
            )
        )
        overdue_count = overdue_q.count()
        overdue_rows = (
            overdue_q.with_entities(
                AssignedForm.id,
                AssignedForm.period_name,
                Country.name,
                AssignmentEntityStatus.due_date,
            )
            .order_by(AssignmentEntityStatus.due_date.asc())
            .limit(EVIDENCE_LIMIT)
            .all()
        )
        overdue = []
        for assignment_id, period_name, country_name, due in overdue_rows:
            days = _overdue_days(now, due)
            label = _("%(country)s — %(period)s (%(days)s days overdue)", country=country_name, period=period_name or "—", days=days)
            overdue.append({
                "label": label,
                "href": _href("assignment_management.edit_assignment", assignment_id=assignment_id),
            })

        non_pending = func.sum(
            case((AssignmentEntityStatus.status != AssignmentEntityStatusValue.pending, 1), else_=0)
        )
        unstarted_rows = (
            db.session.query(
                AssignedForm.id,
                AssignedForm.period_name,
                func.min(AssignmentEntityStatus.due_date).label("first_due"),
            )
            .join(AssignmentEntityStatus, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
            .filter(
                AssignmentEntityStatus.entity_type == "country",
                AssignedForm.operational_clause(),
            )
            .group_by(AssignedForm.id, AssignedForm.period_name)
            .having(and_(non_pending == 0, func.min(AssignmentEntityStatus.due_date) < now))
            .order_by(func.min(AssignmentEntityStatus.due_date).asc())
            .limit(EVIDENCE_LIMIT)
            .all()
        )
        unstarted = [
            {
                "label": period or _("Assignment %(id)s", id=assignment_id),
                "href": _href("assignment_management.edit_assignment", assignment_id=assignment_id),
            }
            for assignment_id, period, _due in unstarted_rows
        ]
        return overdue, overdue_count, unstarted, False
    except Exception as exc:
        logger.error("Reporting-discipline evaluation failed: %s", exc)
        db.session.rollback()
        return [], 0, [], True


def _public_links_without_expiry():
    try:
        rows = (
            AssignedForm.query.filter(
                AssignedForm.is_public_active.is_(True),
                AssignedForm.unique_token.isnot(None),
                AssignedForm.expiry_date.is_(None),
            )
            .order_by(AssignedForm.id.asc())
            .limit(EVIDENCE_LIMIT)
            .all()
        )
        samples = []
        for row in rows:
            template_name = row.template.name if row.template else _("Assignment %(id)s", id=row.id)
            label = " — ".join(part for part in (template_name, row.period_name) if part)
            samples.append({
                "label": label,
                "href": _href("assignment_management.edit_assignment", assignment_id=row.id),
            })
        # Count may exceed the sample. A second query keeps the issue total honest.
        count = AssignedForm.query.filter(
            AssignedForm.is_public_active.is_(True),
            AssignedForm.unique_token.isnot(None),
            AssignedForm.expiry_date.is_(None),
        ).count()
        return samples, count, False
    except Exception as exc:
        logger.error("LIF-01 evaluation failed: %s", exc)
        db.session.rollback()
        return [], 0, True


# ---------------------------------------------------------------------------
# Issue register
# ---------------------------------------------------------------------------

def sync_issues(controls: List[Dict[str, Any]]) -> Dict[str, GovernanceIssue]:
    """Upsert one issue per control. Unknown results are left untouched.

    Flushes so new rows have ids for the page, and leaves the commit to the
    request transaction.
    """
    now = utcnow()
    today = now.date()
    existing = {
        row.fingerprint: row
        for row in GovernanceIssue.query.all()
    }
    known_codes = set()
    for control in controls:
        code = control["code"]
        known_codes.add(code)
        if control["status"] == "unknown":
            continue
        issue = existing.get(code)
        if control["status"] in ("effective", "not_applicable"):
            if issue is not None and issue.status in ("open", "accepted"):
                _resolve(issue, "control_passed" if control["status"] == "effective" else "control_not_applicable", now)
            continue
        if control["status"] != "gap":
            continue
        if issue is None:
            issue = GovernanceIssue(
                control_code=code,
                fingerprint=code,
                title=control["title"],
                severity=control["severity"],
                status="open",
                opened_at=now,
            )
            db.session.add(issue)
            existing[code] = issue
        elif issue.status == "resolved":
            issue.status = "open"
            issue.reopened_at = now
            issue.resolved_at = None
            issue.resolution = None
            _clear_acceptance(issue)
        elif issue.status == "accepted" and issue.accepted_until and issue.accepted_until < today:
            issue.status = "open"
            issue.reopened_at = now
        issue.title = str(control["title"])
        issue.severity = control["severity"]
        issue.summary = str(control["summary"] or "")
        issue.failing_count = int(control["failing_count"] or 0)
        issue.evidence = _plain_evidence(control.get("evidence"))
        issue.last_seen_at = now

    for fingerprint, issue in existing.items():
        if fingerprint not in known_codes and issue.status in ("open", "accepted"):
            _resolve(issue, "control_retired", now)

    db.session.flush()
    return existing


def _plain_evidence(items) -> List[Dict[str, Any]]:
    cleaned = []
    for item in items or []:
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        href = item.get("href")
        cleaned.append({"label": label, "href": str(href) if href else None})
    return cleaned


def _resolve(issue: GovernanceIssue, resolution: str, now) -> None:
    issue.status = "resolved"
    issue.resolution = resolution
    issue.resolved_at = now
    issue.last_seen_at = now
    issue.failing_count = 0
    issue.evidence = []


def _clear_acceptance(issue: GovernanceIssue) -> None:
    issue.accepted_by_user_id = None
    issue.accepted_at = None
    issue.acceptance_reason = None
    issue.accepted_until = None


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------

def _present(controls: List[Dict[str, Any]], issues_by_code: Dict[str, GovernanceIssue], ownership: Dict[str, Any]) -> Dict[str, Any]:
    issue_views = []
    resolved = []
    display_controls = []
    for control in controls:
        issue = issues_by_code.get(control["code"])
        status = control["status"]
        if issue is not None and issue.status == "accepted" and status == "gap":
            status = "accepted"
        view = {
            **control,
            "title": str(control.get("title") or ""),
            "statement": str(control.get("statement") or ""),
            "accountable": str(control.get("accountable") or ""),
            "summary": str(control.get("summary") or ""),
            "status": status,
            "evidence": _plain_evidence(control.get("evidence")),
            "issue_id": issue.id if issue is not None and status in ("gap", "accepted") else None,
        }
        display_controls.append(view)
        if issue is None:
            continue
        if issue.status in ("open", "accepted"):
            issue_views.append(_issue_view(issue, control))
        elif issue.status == "resolved" and issue.resolved_at is not None:
            resolved.append(_issue_view(issue, control))

    issue_views.sort(key=lambda row: (SEVERITY_ORDER.get(row["severity"], 9), row["code"]))
    resolved.sort(key=lambda row: row.get("resolved_at") or "", reverse=True)

    domains = []
    for key in DOMAIN_KEYS:
        rows = [row for row in display_controls if row["domain"] == key]
        if rows:
            domains.append({"key": key, "label": str(_domain_label(key)), "controls": rows})

    summary = {
        "open": sum(1 for row in issue_views if row["status"] == "open"),
        "accepted": sum(1 for row in issue_views if row["status"] == "accepted"),
        "effective": sum(1 for row in display_controls if row["status"] == "effective"),
        "not_applicable": sum(1 for row in display_controls if row["status"] == "not_applicable"),
        "unknown": sum(1 for row in display_controls if row["status"] == "unknown"),
        "controls": len(display_controls),
    }
    return {
        "summary": summary,
        "issues": issue_views,
        "recently_resolved": resolved[:8],
        "domains": domains,
        "ownership": ownership,
    }


def _domain_label(key: str) -> str:
    if key == "ownership":
        return _("Ownership")
    if key == "access":
        return _("Access")
    if key == "reporting":
        return _("Reporting discipline")
    if key == "glossary":
        return _("Glossary")
    if key == "lifecycle":
        return _("Lifecycle")
    return key


def _issue_view(issue: GovernanceIssue, control: Dict[str, Any]) -> Dict[str, Any]:
    accepter = None
    user = getattr(issue, "accepted_by", None)
    if user is not None:
        accepter = (getattr(user, "name", None) or "").strip() or getattr(user, "email", None)
    return {
        "id": issue.id,
        "code": issue.control_code,
        "title": str(control.get("title") or issue.title),
        "statement": str(control.get("statement") or ""),
        "accountable": str(control.get("accountable") or ""),
        "severity": issue.severity,
        "status": issue.status,
        "summary": str(issue.summary or control.get("summary") or ""),
        "failing_count": issue.failing_count or 0,
        "evidence": issue.evidence or [],
        "acceptance_reason": issue.acceptance_reason,
        "accepted_until": issue.accepted_until.isoformat() if issue.accepted_until else None,
        "accepted_by": accepter,
        "expired": bool(
            issue.status == "open"
            and issue.accepted_until
            and issue.reopened_at
            and issue.acceptance_reason
        ),
        "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
        "href": control.get("href"),
    }

