"""Entry-form context for FDRS reporting-currency and Swiss-franc amounts."""

from __future__ import annotations

from pathlib import Path

from flask import jsonify, send_from_directory, url_for
from flask_login import current_user, login_required

from plugins.fdrs import _PLUGIN_DIR, bp
from plugins.fdrs.services.fdrs_currency import (
    CHF_MATRIX_PREFIX,
    end_date_from_items,
    is_chf_companion_item,
    normalize_rate_date,
    period_year,
    rate_for_date,
    reporting_end_item,
)


def _asset_version(filename: str) -> str:
    path = Path(_PLUGIN_DIR) / "static" / filename
    try:
        return str(int(path.stat().st_mtime))
    except OSError:
        return "0"


def fdrs_static_url(filename: str) -> str:
    return url_for("fdrs.static_file", filename=filename, v=_asset_version(filename))


@bp.route("/fdrs/static/<path:filename>", methods=["GET"])
@login_required
def static_file(filename: str):
    response = send_from_directory(str(Path(_PLUGIN_DIR) / "static"), filename)
    response.headers["Cache-Control"] = "no-cache"
    return response


@bp.route("/fdrs/entry-currency", methods=["GET"])
@login_required
def entry_currency():
    """Companion item ids, stored Swiss-franc amounts, and the year's exchange rates."""
    from app.models import AssignmentEntityStatus, FormData, FormItem
    from app.services.organization.authorization_service import AuthorizationService

    raw_id = (request_aes_id() or "").strip()
    if not raw_id.isdigit():
        return jsonify({"error": "assignment_required"}), 400
    status = AssignmentEntityStatus.query.get(int(raw_id))
    if status is None:
        return jsonify({"error": "not_found"}), 404
    if not AuthorizationService.can_access_assignment(status, current_user):
        return jsonify({"error": "forbidden"}), 403

    assignment = status.assigned_form
    template = assignment.template if assignment is not None else None
    version_id = getattr(template, "published_version_id", None) if template is not None else None
    if version_id is None or getattr(template, "id", None) != 21:
        return jsonify(_empty_context())

    items = FormItem.query.filter_by(version_id=version_id, archived=False).all()
    companions = [item for item in items if is_chf_companion_item(item)]
    by_id = {item.id: item for item in items}
    source_ids = []
    pairs = []
    for companion in companions:
        source_id = (companion.config or {}).get("fdrs_chf_source_item_id")
        try:
            source_id = int(source_id)
        except (TypeError, ValueError):
            continue
        if source_id not in by_id:
            continue
        source_ids.append(source_id)
        pairs.append((source_id, companion.id))

    currency_item_id = None
    for item in items:
        if item.item_type == "question" and "reporting currency" in (item.label or "").lower():
            currency_item_id = item.id
            break
    end_item = reporting_end_item(items)
    end_date_item_id = end_item.id if end_item is not None else None

    matrix = next((item for item in items if (item.config or {}).get("fdrs_income_sources")), None)
    wanted = {item_id for pair in pairs for item_id in pair}
    if currency_item_id:
        wanted.add(currency_item_id)
    if end_date_item_id:
        wanted.add(end_date_item_id)
    if matrix is not None:
        wanted.add(matrix.id)

    stored = {}
    if wanted:
        rows = FormData.query.filter(
            FormData.assignment_entity_status_id == status.id,
            FormData.form_item_id.in_(wanted),
        ).all()
        stored = {row.form_item_id: row for row in rows}

    year = period_year(getattr(assignment, "period_name", "") or "")
    saved_currency = ""
    if currency_item_id:
        currency_row = stored.get(currency_item_id)
        if currency_row is not None and currency_row.value:
            saved_currency = str(currency_row.value).strip()
    from flask import request

    asked = (request.args.get("currency") or saved_currency).strip()
    saved_end = ""
    if end_date_item_id:
        end_row = stored.get(end_date_item_id)
        if end_row is not None and end_row.value:
            saved_end = str(end_row.value).strip()
    rate_date = normalize_rate_date(request.args.get("date") or saved_end) or ""
    rates = _rate_map(rate_date, asked)
    pair_payload = []
    for source_id, companion_id in pairs:
        companion_row = stored.get(companion_id)
        pair_payload.append(
            {
                "local_item_id": source_id,
                "chf_item_id": companion_id,
                "chf_value": getattr(companion_row, "value", None) if companion_row is not None else None,
            }
        )

    matrix_payload = None
    if matrix is not None:
        matrix_row = stored.get(matrix.id)
        disagg = matrix_row.disagg_data if matrix_row is not None else None
        chf_cells = {}
        if isinstance(disagg, dict):
            for key, value in disagg.items():
                if isinstance(key, str) and key.startswith(CHF_MATRIX_PREFIX):
                    chf_cells[key[len(CHF_MATRIX_PREFIX) :]] = value
        matrix_payload = {"item_id": matrix.id, "column": "Funding", "chf": chf_cells}

    return jsonify(
        {
            "year": year,
            "currency_item_id": currency_item_id,
            "end_date_item_id": end_date_item_id,
            "rate_date": rate_date,
            "rates": rates,
            "pairs": pair_payload,
            "matrix": matrix_payload,
        }
    )


@bp.route("/fdrs/exchange-rate", methods=["GET"])
@login_required
def exchange_rate():
    """Swiss francs per 1 unit of a currency on the financial reporting end date."""
    from flask import request

    rate_date = normalize_rate_date(request.args.get("date")) or ""
    currency = (request.args.get("currency") or "").strip().upper()
    if not rate_date or not currency:
        return jsonify({"error": "date_and_currency_required"}), 400
    rate = rate_for_date(rate_date, currency)
    return jsonify({"date": rate_date, "currency": currency, "rate": rate})


def _rate_map(rate_date: str, currency: str) -> dict:
    rate = rate_for_date(rate_date, currency)
    if rate is None or not str(currency or "").strip():
        return {}
    return {str(currency).strip().upper(): rate}


def request_aes_id() -> str:
    from flask import request

    return str(request.args.get("aes_id") or "")


def _empty_context() -> dict:
    return {
        "year": "",
        "currency_item_id": None,
        "end_date_item_id": None,
        "rate_date": "",
        "rates": {},
        "pairs": [],
        "matrix": None,
    }
