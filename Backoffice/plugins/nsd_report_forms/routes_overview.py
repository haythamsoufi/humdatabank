"""Legacy NSD overview URLs. The registry UI is Admin → Projects."""

from pathlib import Path

from flask import Blueprint, abort, redirect, request, url_for

from app.models.projects import Project
from app.routes.admin.shared import admin_permission_required

from plugins.nsd_report_forms.plugin import NSD_ADMIN_PERMISSION

_PLUGIN_DIR = Path(__file__).resolve().parent

projects_bp = Blueprint(
    "nsd_projects",
    __name__,
    url_prefix="/admin/nsd-projects",
    template_folder=str(_PLUGIN_DIR / "templates"),
)


@projects_bp.route("/", methods=["GET"])
@admin_permission_required(NSD_ADMIN_PERMISSION)
def project_list():
    args = request.args
    params = {}
    for key in ("fund", "country", "status"):
        if args.get(key):
            params[key] = args.get(key)
    if "status" not in args:
        params["status"] = "Open"
    return redirect(url_for("project_management.project_list", **params))


@projects_bp.route("/<path:reference>", methods=["GET"])
@admin_permission_required(NSD_ADMIN_PERMISSION)
def project_detail(reference):
    project = Project.query.filter_by(reference=reference.strip()).first()
    if project is None:
        abort(404)
    return redirect(url_for("project_management.project_detail", project_id=project.id))
