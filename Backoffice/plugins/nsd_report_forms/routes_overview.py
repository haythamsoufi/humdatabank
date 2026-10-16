"""NSD admin project overview: project list and project detail (read-only).

Own blueprint (``nsd_projects``, /admin/nsd-projects). Register it from ``NsdReportFormsPlugin`` with
``get_additional_blueprints()`` (see overview_delivery/README.txt).
"""
from pathlib import Path

from flask import Blueprint, abort, redirect, render_template, request, url_for

from app.routes.admin.shared import admin_permission_required

from plugins.nsd_report_forms.overview import data
from plugins.nsd_report_forms.plugin import NSD_ADMIN_PERMISSION

_PLUGIN_DIR = Path(__file__).resolve().parent

projects_bp = Blueprint(
    "nsd_projects",
    __name__,
    url_prefix="/admin/nsd-projects",
    template_folder=str(_PLUGIN_DIR / "templates"),
)

TEMPLATE_DIR = "plugins/nsd_report_forms/nsd_projects"


@projects_bp.route("/", methods=["GET"])
@admin_permission_required(NSD_ADMIN_PERMISSION)
def project_list():
    args = request.args
    # MOMO opens on the "Open" projects on the first visit (no status parameter at all)
    if "status" not in args:
        params = {k: args.get(k) for k in ("fund", "region", "country") if args.get(k)}
        params["status"] = "Open"
        return redirect(url_for("nsd_projects.project_list", **params))
    result = data.project_list(args.get("fund", "").strip(), args.get("region", "").strip(),
                               args.get("country", "").strip(), args.get("status", "").strip())
    return render_template(f"{TEMPLATE_DIR}/list.html", **result)


@projects_bp.route("/<path:reference>", methods=["GET"])
@admin_permission_required(NSD_ADMIN_PERMISSION)
def project_detail(reference):
    project = data.project_detail(reference.strip())
    if project is None:
        abort(404)
    return render_template(f"{TEMPLATE_DIR}/detail.html", p=project)
