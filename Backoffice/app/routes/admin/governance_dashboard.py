# File: Backoffice/app/routes/admin/governance_dashboard.py
"""
Governance Dashboard – Admin page for IFRC data governance.

Surfaces: focal point (country) coverage, access control (RBAC), reporting timeliness
and quality, FDRS document compliance, and metadata completeness. Actionable metrics
and flags with links to the right admin screens.
"""

from flask import Blueprint, render_template, request
from app.routes.admin.shared import permission_required
from app.services.governance_metrics_service import get_governance_metrics
from app.utils.api_responses import json_ok

bp = Blueprint("governance_dashboard", __name__, url_prefix="/admin")


@bp.route("/governance", methods=["GET"])
@permission_required("admin.governance.view")
def governance_dashboard():
    """Governance dashboard: stats, flags, and links for data ownership, access, quality, compliance, metadata."""
    metrics = get_governance_metrics()
    return render_template(
        "admin/governance/dashboard.html",
        metrics=metrics,
        title="Governance Dashboard",
    )


@bp.route("/governance/api/metrics", methods=["GET"])
@permission_required("admin.governance.view")
def api_governance_metrics():
    """JSON endpoint for governance metrics (e.g. for future widgets or refresh)."""
    metrics = get_governance_metrics()
    return json_ok(**metrics) if isinstance(metrics, dict) else json_ok(data=metrics)
