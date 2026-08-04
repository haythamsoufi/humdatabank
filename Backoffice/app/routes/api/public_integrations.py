"""Public integration endpoints optimized for Custom GPT Actions."""

from __future__ import annotations

import uuid

from flask import current_app, request

from app.routes.api import api_bp
from app.services.public_analytics_service import aggregate_global_trend, resolve_indicator_query
from app.utils.api_helpers import api_error, json_response
from app.utils.rate_limiting import api_rate_limit


@api_bp.route("/public/global-trend", methods=["GET"])
@api_rate_limit()
def public_global_trend():
    """
    Compact global totals by reporting period for public indicators.

    Preferred for AI assistants (Custom GPT) — returns ~1–2 KB instead of multi-MB /data payloads.
    """
    try:
        indicator_bank_id = request.args.get("indicator_bank_id", type=int)
        query = request.args.get("query", default="", type=str).strip()
        period_name = request.args.get("period_name", default="", type=str).strip()
        max_pages = request.args.get("max_pages", default=20, type=int)

        payload = aggregate_global_trend(
            indicator_bank_id=indicator_bank_id,
            query=query,
            period_name=period_name,
            max_pages=max_pages,
        )
        response = json_response(payload)
        response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
        response.headers["X-Public-Data-Access"] = "true"
        return response
    except ValueError as exc:
        return api_error(str(exc), 400)
    except Exception as exc:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            "public/global-trend failed [ID: %s]: %s",
            error_id,
            exc,
            exc_info=True,
        )
        return api_error("Could not compute global trend", 500, error_id, None)


@api_bp.route("/public/indicators/resolve", methods=["GET"])
@api_rate_limit()
def public_resolve_indicator():
    """Map a natural-language metric name to an indicator bank id (compact response)."""
    try:
        query = request.args.get("query", default="", type=str).strip()
        limit = request.args.get("limit", default=5, type=int)
        if not query:
            return api_error("query is required", 400)
        payload = resolve_indicator_query(query, limit=max(1, min(limit, 20)))
        response = json_response(payload)
        response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
        return response
    except Exception as exc:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            "public/indicators/resolve failed [ID: %s]: %s",
            error_id,
            exc,
            exc_info=True,
        )
        return api_error("Could not resolve indicator", 500, error_id, None)
