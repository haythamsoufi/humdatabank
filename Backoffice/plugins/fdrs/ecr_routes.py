"""Everyone Counts analysis for Data Explorer."""

from __future__ import annotations

import logging

from flask_login import current_user

from app.routes.admin.shared import permission_required
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_accepted, json_error, json_ok, json_server_error
from app.utils.data_quality_constants import FDRS_TEMPLATE_ID
from plugins.fdrs import bp
from plugins.fdrs.services.ecr_snapshot import read_snapshot, request_rebuild

logger = logging.getLogger(__name__)

_SAVED_KEYS = ("status", "busy", "built_at", "started_at", "error")


def _saved(meta: dict) -> dict:
    return {key: meta.get(key) for key in _SAVED_KEYS}


@bp.route("/admin/data-exploration/everyone-counts", methods=["GET"])
@permission_required("admin.data_explore.everyone_counts")
def get_everyone_counts_analysis():
    """Saved Everyone Counts calculation.

    The FDRS panel is not rebuilt here. ``saved`` says when the calculation
    was stored and whether a refresh is still running.
    """
    try:
        payload, saved = read_snapshot(FDRS_TEMPLATE_ID)
    except Exception as exc:
        logger.error("Error reading Everyone Counts snapshot: %s", exc, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)
    if payload:
        return json_ok(data={**payload, "saved": _saved(saved)})
    return json_ok(saved=_saved(saved))


@bp.route("/admin/data-exploration/everyone-counts/refresh", methods=["POST"])
@permission_required("admin.data_explore.everyone_counts")
def refresh_everyone_counts_analysis():
    """Rebuild the saved calculation from current FDRS assignments.

    Returns as soon as the build is queued. External files are the copies
    already saved on the server; refresh those from External sources first.
    """
    try:
        user_id = int(getattr(current_user, "id", 0) or 0)
        result = request_rebuild(FDRS_TEMPLATE_ID, user_id)
    except Exception as exc:
        logger.error("Error queueing Everyone Counts snapshot: %s", exc, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)
    saved = _saved(result)
    if result.get("started"):
        return json_accepted(saved=saved)
    return json_ok(saved=saved)


@bp.route("/admin/data-exploration/everyone-counts/sources/<source_id>", methods=["POST"])
@permission_required("admin.data_explore.everyone_counts")
def refresh_everyone_counts_source(source_id: str):
    """Download one saved external file and return its new status."""
    from plugins.fdrs.services.ecr_external import refresh_source

    try:
        source = refresh_source(source_id)
    except KeyError:
        return json_error("Unknown source.", 404)
    except Exception as exc:
        logger.error("Error refreshing Everyone Counts source %s: %s", source_id, exc, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)
    return json_ok(source=source)
