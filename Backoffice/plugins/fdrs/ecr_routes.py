"""Everyone Counts analysis for Data Explorer."""

from __future__ import annotations

import logging

from flask import request

from app.routes.admin.shared import permission_required
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_ok, json_server_error
from plugins.fdrs import bp
from plugins.fdrs.services.ecr_analysis import load_everyone_counts

logger = logging.getLogger(__name__)


@bp.route("/admin/data-exploration/everyone-counts", methods=["GET"])
@permission_required("admin.data_explore.analysis")
def get_everyone_counts_analysis():
    """Live FDRS headline series used by Everyone Counts.

    ``refresh=1`` downloads a new World Bank snapshot and replaces the saved one.
    """
    refresh = (request.args.get("refresh") or "").strip().lower() in {"1", "true", "yes"}
    try:
        return json_ok(data=load_everyone_counts(refresh_external=refresh))
    except Exception as exc:
        logger.error("Error building Everyone Counts analysis: %s", exc, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)
