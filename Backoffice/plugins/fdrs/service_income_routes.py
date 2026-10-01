"""FDRS service-income estimate for Data Explorer."""

from __future__ import annotations

import logging

from flask import request

from app.routes.admin.shared import permission_required
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_ok, json_server_error
from plugins.fdrs import bp
from plugins.fdrs.services.service_income_analysis import load_service_income_analysis

logger = logging.getLogger(__name__)


@bp.route("/admin/data-exploration/service-income", methods=["GET"])
@permission_required("admin.data_explore.analysis")
def get_service_income_analysis():
    """Yearly FDRS income and service income, with the closed-round reference."""
    published_only = (request.args.get("published_only") or "").strip().lower() in {"1", "true", "yes"}
    try:
        return json_ok(data=load_service_income_analysis(published_only=published_only))
    except Exception as exc:
        logger.error("Error building service income analysis: %s", exc, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)
