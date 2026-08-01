"""Shared validation scope API endpoints (periods / countries)."""

from __future__ import annotations

from flask import Blueprint, request
from flask_login import login_required

from app.routes.admin.shared import permission_required
from app.services.validation.dashboard_service import (
    global_periods_for_template,
    list_countries_for_period,
)
from app.utils.api_responses import json_bad_request, json_ok


def periods_api():
    template_id = request.args.get("template_id", type=int)
    if not template_id:
        return json_bad_request("template_id is required")
    return json_ok(periods=global_periods_for_template(template_id))


def countries_api():
    template_id = request.args.get("template_id", type=int)
    period = request.args.get("period", type=str)
    if not template_id or not period:
        return json_bad_request("template_id and period are required")
    return json_ok(countries=list_countries_for_period(template_id, period))


def register_validation_scope_routes(
    bp: Blueprint,
    url_prefix: str,
    permission: str,
    *,
    endpoint_prefix: str,
) -> None:
    """Register periods/countries GET APIs on *bp* under *url_prefix*."""

    @bp.route(f"{url_prefix}/api/periods", methods=["GET"], endpoint=f"{endpoint_prefix}_periods_api")
    @login_required
    @permission_required(permission)
    def _periods_api_view():
        return periods_api()

    @bp.route(f"{url_prefix}/api/countries", methods=["GET"], endpoint=f"{endpoint_prefix}_countries_api")
    @login_required
    @permission_required(permission)
    def _countries_api_view():
        return countries_api()
