"""Personal PM pages of the NSD funds monitoring: only the projects that name the signed-in user as IFRC project manager.

Own blueprint (``nsd_pm``, /nsd-funds), separate from the admin overview (``nsd_projects``, /admin/nsd-projects) and
the import. A project manager only needs the permission ``nsd_funds.pm_overview``; they never get the admin pages.

* GET /nsd-funds/pm-overview        the PM page (MOMO "pm_personal")
* GET /nsd-funds/projects/<ref>     the project page, 404 unless the project's IFRC project manager email is the user's
* GET /nsd-funds/links              {"pm_overview": url} for holders of the permission, {} for everybody else

NSD admins (and System Managers) may add ``?as=<email>`` to preview another PM's pages; it is ignored for everyone else.
"""
from pathlib import Path

from flask import Blueprint, abort, jsonify, render_template, request, url_for
from flask_login import current_user

from app.routes.admin.shared import permission_required
from app.services.organization.authorization_service import AuthorizationService

from plugins.nsd_report_forms.overview import data
from plugins.nsd_report_forms.plugin import NSD_ADMIN_PERMISSION, NSD_PM_PERMISSION

_PLUGIN_DIR = Path(__file__).resolve().parent

pm_bp = Blueprint(
    "nsd_pm",
    __name__,
    url_prefix="/nsd-funds",
    template_folder=str(_PLUGIN_DIR / "templates"),
)

TEMPLATE_DIR = "plugins/nsd_report_forms"


def _can_preview() -> bool:
    return AuthorizationService.has_rbac_permission(current_user, NSD_ADMIN_PERMISSION)


def _viewing():
    """(email whose projects are shown, True when an NSD admin previews another PM)."""
    own = data.norm_email(getattr(current_user, "email", ""))
    asked = data.norm_email(request.args.get("as"))
    if asked and _can_preview():
        return asked, asked != own
    return own, False


def _as_args(email: str, previewing: bool) -> dict:
    return {"as": email} if previewing else {}


@pm_bp.route("/pm-overview", methods=["GET"])
@permission_required(NSD_PM_PERMISSION)
def pm_overview():
    email, previewing = _viewing()
    result = data.pm_projects(email)
    extra = _as_args(email, previewing)
    for p in result["projects"]:
        p["url"] = url_for("nsd_pm.project_detail", reference=p["reference"], **extra)
    return render_template(
        f"{TEMPLATE_DIR}/nsd_pm/pm_overview.html", **result, previewing=previewing, can_preview=_can_preview(),
        explore_url=url_for("data_exploration.explore_data", tab="nsd_funds"),
    )


@pm_bp.route("/projects/<path:reference>", methods=["GET"])
@permission_required(NSD_PM_PERMISSION)
def project_detail(reference):
    email, previewing = _viewing()
    # a project the PM is not named on is indistinguishable from one that does not exist
    project = data.project_detail(reference.strip(), pm_email=email)
    if project is None:
        abort(404)
    back = url_for("nsd_pm.pm_overview", **_as_args(email, previewing))
    return render_template(
        f"{TEMPLATE_DIR}/nsd_projects/detail.html", p=project,
        brand_url=back, back_url=back, back_label="Back to my projects",
        exit_url=url_for("data_exploration.explore_data", tab="nsd_funds"),
    )


@pm_bp.route("/links", methods=["GET"])
def links():
    out = {}
    if current_user.is_authenticated and AuthorizationService.has_rbac_permission(current_user, NSD_PM_PERMISSION):
        out["pm_overview"] = url_for("nsd_pm.pm_overview")
    resp = jsonify(out)
    resp.headers["Cache-Control"] = "no-store"
    return resp
