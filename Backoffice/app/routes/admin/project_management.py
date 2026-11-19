"""Compatibility redirects.

The project record, its reports and its settings live under Assignments
(``project_assignments``). These endpoint names stay so older links, including
plugin pages that still call ``url_for('project_management....')``, keep working.
POST requests are forwarded with 307 so the body is resubmitted to the new route.
"""

from flask import Blueprint, redirect, request, url_for

from app.routes.admin.shared import permission_required, permission_required_any

bp = Blueprint("project_management", __name__, url_prefix="/admin/projects")

_VIEW = permission_required_any("admin.assignments.view", "nsd_funds.pm_overview")
_EDIT = permission_required("admin.assignments.edit")
_DELETE = permission_required("admin.assignments.delete")


def _forward(endpoint, **params):
    code = 307 if request.method == "POST" else 302
    query = request.args.to_dict(flat=True)
    for key, value in list(query.items()):
        if key in params:
            query.pop(key)
        elif value == "":
            query.pop(key)
    return redirect(url_for(endpoint, **params, **query), code=code)


@bp.route("/", methods=["GET"])
@_VIEW
def project_list():
    args = {key: value for key, value in request.args.to_dict(flat=True).items() if value != ""}
    args["type"] = "project"
    return redirect(url_for("assignment_management.manage_assignments", **args))


@bp.route("/monitoring/data", methods=["GET"])
@_VIEW
def monitoring_data():
    return _forward("project_assignments.monitoring_data")


@bp.route("/monitoring/export.csv", methods=["GET"])
@_VIEW
def monitoring_export():
    return _forward("project_assignments.monitoring_export")


@bp.route("/new", methods=["GET", "POST"])
@_EDIT
def project_new():
    return _forward("project_assignments.project_new")


@bp.route("/<int:project_id>", methods=["GET"])
@_VIEW
def project_detail(project_id):
    return redirect(url_for("project_assignments.project_page", project_id=project_id))


@bp.route("/<int:project_id>/edit", methods=["GET", "POST"])
@_VIEW
def project_edit(project_id):
    return _forward("project_assignments.project_edit", project_id=project_id)


@bp.route("/<int:project_id>/inline", methods=["POST"])
@_EDIT
def project_inline_save(project_id):
    return _forward("project_assignments.project_inline_save", project_id=project_id)


@bp.route("/<int:project_id>/delete", methods=["POST"])
@_DELETE
def project_delete(project_id):
    return _forward("project_assignments.project_delete", project_id=project_id)


@bp.route("/<int:project_id>/cycles", methods=["POST"])
@_EDIT
def project_add_cycle(project_id):
    return _forward("project_assignments.project_add_report", project_id=project_id)


@bp.route("/<int:project_id>/cycles/<int:assignment_id>/close", methods=["POST"])
@_EDIT
def project_cycle_close(project_id, assignment_id):
    return _forward(
        "project_assignments.project_report_close",
        project_id=project_id,
        assignment_id=assignment_id,
    )


@bp.route("/<int:project_id>/cycles/<int:assignment_id>/reopen", methods=["POST"])
@_EDIT
def project_cycle_reopen(project_id, assignment_id):
    return _forward(
        "project_assignments.project_report_reopen",
        project_id=project_id,
        assignment_id=assignment_id,
    )
