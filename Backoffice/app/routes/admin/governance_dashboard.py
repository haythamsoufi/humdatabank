# File: Backoffice/app/routes/admin/governance_dashboard.py
"""
Data governance register.

The page is the operating record for governance controls: what the rule is,
whether the live check passes, and the decision taken when it does not.
"""

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_babel import _
from flask_login import current_user

from app import db
from app.models import GovernanceIssue
from app.routes.admin.shared import permission_required
from app.services.organization.authorization_service import AuthorizationService
from app.services.platform.governance_program import (
    accept_governance_issue,
    build_governance_report,
    reopen_governance_issue,
    validate_acceptance,
)
from app.services.platform.user_analytics_service import log_admin_action
from app.utils.api_responses import json_ok_result
from app.utils.country_utils import get_countries_by_region_with_part_of
from app.utils.request_utils import get_request_data

bp = Blueprint("governance_dashboard", __name__, url_prefix="/admin")


@bp.route("/governance", methods=["GET"])
@permission_required("admin.governance.view")
def governance_dashboard():
    """Control register, open issues, and the focal-point stewardship list."""
    report = build_governance_report()
    can_manage = AuthorizationService.has_rbac_permission(current_user, "admin.governance.manage")
    _countries, part_of_programs, part_of_category_to_countries, part_of_text_groups = (
        get_countries_by_region_with_part_of()
    )
    return render_template(
        "admin/governance/dashboard.html",
        report=report,
        can_manage=can_manage,
        part_of_programs=part_of_programs,
        part_of_category_to_countries=part_of_category_to_countries,
        part_of_text_groups=part_of_text_groups,
        title=_("Data governance"),
    )


@bp.route("/governance/api/metrics", methods=["GET"])
@permission_required("admin.governance.view")
def api_governance_metrics():
    """JSON snapshot of the control register (same evaluation as the page)."""
    return json_ok_result(build_governance_report())


@bp.route("/governance/issues/<int:issue_id>/accept", methods=["POST"])
@permission_required("admin.governance.manage")
def accept_issue(issue_id):
    """Record a time-bounded risk acceptance against an open control gap."""
    issue = GovernanceIssue.query.get_or_404(issue_id)
    if issue.status != "open":
        flash(_("Only an open issue can be accepted."), "warning")
        return redirect(_register_url())

    data = get_request_data()
    until, error = validate_acceptance(data.get("reason"), data.get("accepted_until"))
    if error:
        flash(error, "warning")
        return redirect(_register_url())

    accept_governance_issue(issue, user_id=current_user.id, reason=data.get("reason"), until=until)
    log_admin_action(
        "governance_risk_accepted",
        _("Accepted %(code)s until %(until)s.", code=issue.control_code, until=until.isoformat()),
        target_type="governance_issue",
        target_id=issue.id,
        target_description=issue.control_code,
        new_values={
            "control_code": issue.control_code,
            "accepted_until": until.isoformat(),
            "reason": issue.acceptance_reason,
        },
        risk_level="medium",
    )
    db.session.flush()
    flash(
        _("Risk accepted for %(code)s until %(until)s. It reopens on that date if the gap is still there.",
          code=issue.control_code, until=until.isoformat()),
        "success",
    )
    return redirect(_register_url())


@bp.route("/governance/issues/<int:issue_id>/reopen", methods=["POST"])
@permission_required("admin.governance.manage")
def reopen_issue(issue_id):
    """Withdraw a risk acceptance and put the gap back on the open queue."""
    issue = GovernanceIssue.query.get_or_404(issue_id)
    if issue.status != "accepted":
        flash(_("Only an accepted risk can be reopened."), "warning")
        return redirect(_register_url())

    code = issue.control_code
    reopen_governance_issue(issue)
    log_admin_action(
        "governance_risk_reopened",
        _("Reopened %(code)s.", code=code),
        target_type="governance_issue",
        target_id=issue.id,
        target_description=code,
        new_values={"control_code": code, "status": "open"},
        risk_level="medium",
    )
    db.session.flush()
    flash(_("%(code)s is back on the open queue.", code=code), "success")
    return redirect(_register_url())


def _register_url() -> str:
    return url_for("governance_dashboard.governance_dashboard") + "#issues"
