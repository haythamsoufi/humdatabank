"""Decision Support pages and JSON API."""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable

from flask import g, jsonify, render_template, request, send_from_directory, url_for
from flask_login import current_user

from app.utils.api_responses import (
    GENERIC_ERROR_MESSAGE,
    json_auth_required,
    json_bad_request,
    json_forbidden,
    json_not_found,
)
from app.utils.client_ip import get_client_ip
from app.routes.admin.shared import permission_required
from app.utils.error_handling import handle_json_view_exception
from app.utils.rate_limiting import rate_limit
from plugins.ifrc.decisions import _PLUGIN_DIR, bp
from plugins.ifrc.decisions import service
from plugins.ifrc.decisions.access import AccessContext, resolve_access_context
from plugins.ifrc.decisions.config import ConfigError
from plugins.ifrc.decisions.facts import Filters
from plugins.ifrc.decisions.metrics import METRIC_REGISTRY

logger = logging.getLogger(__name__)

_MAX_NOTE = 2000


def _rate_key() -> str:
    who = getattr(current_user, "id", None) or get_client_ip()
    return f"decisions:{who}:{request.endpoint}"


def _access() -> AccessContext:
    cached = getattr(g, "_decision_access", None)
    if cached is None:
        cached = resolve_access_context()
        g._decision_access = cached
    return cached


def api_view(*, manage: bool = False, per_minute: int = 120) -> Callable:
    """Session-authenticated JSON endpoint. Unreadable and missing records both answer 404."""

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        @rate_limit(requests_per_minute=per_minute, key_func=_rate_key)
        def wrapper(*args: Any, **kwargs: Any):
            if not getattr(current_user, "is_authenticated", False):
                return json_auth_required()
            access = _access()
            if not access.can_view:
                logger.info("decision_support access_denied user=%s path=%s", access.user_id, request.path)
                return json_forbidden("You do not have access to Decision Support.")
            if manage and not access.can_manage:
                logger.info("decision_support access_denied user=%s path=%s", access.user_id, request.path)
                return json_forbidden("You do not have permission to administer Decision Support.")
            try:
                return fn(access, *args, **kwargs)
            except service.NotFound:
                return json_not_found("Not found.")
            except service.Denied:
                return json_forbidden("You do not have permission to administer Decision Support.")
            except ConfigError as exc:
                return json_bad_request("Invalid configuration.", errors=exc.errors)
            except ValueError as exc:
                return json_bad_request(str(exc))
            except Exception as exc:  # noqa: BLE001 - surfaced as a generic JSON error
                return handle_json_view_exception(exc, GENERIC_ERROR_MESSAGE)

        return wrapper

    return decorator


def _json(payload: dict[str, Any]):
    response = jsonify(payload)
    # Per-user, permission-filtered output must never be stored by shared caches.
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _filters() -> Filters:
    return Filters.from_args(request.args)


def _group_by() -> tuple[str, ...]:
    raw = (request.args.get("group_by") or "").strip()
    if not raw:
        return ()
    parts = tuple(p.strip() for p in raw.split(",") if p.strip())
    allowed = {dim for m in METRIC_REGISTRY.values() for dim in m.valid_dimensions}
    if len(parts) > 3 or any(p not in allowed for p in parts):
        raise ValueError("group_by is not recognised")
    return parts


def _body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("A JSON object is required.")
    return data


def _note(body: dict[str, Any]) -> str | None:
    note = body.get("note")
    if note is None:
        return None
    if not isinstance(note, str) or len(note) > _MAX_NOTE:
        raise ValueError("note must be text of at most 2000 characters")
    return note


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@bp.route("/api/decisions", methods=["GET"])
@api_view()
def api_list(access: AccessContext):
    return _json(service.list_decisions(access, _filters()))


@bp.route("/api/decisions/<decision_id>", methods=["GET"])
@api_view()
def api_definition(access: AccessContext, decision_id: str):
    lang = _filters().lang
    resolved = service.resolve_decision_id(decision_id, access)
    return _json({"data": service.get_definition(resolved, access, lang), "permission_context": access.public_view()})


@bp.route("/api/decisions/<decision_id>/summary", methods=["GET"])
@api_view(per_minute=60)
def api_summary(access: AccessContext, decision_id: str):
    resolved = service.resolve_decision_id(decision_id, access)
    return _json(service.decision_summary(resolved, _filters(), access))


@bp.route("/api/decisions/<decision_id>/metrics", methods=["GET"])
@api_view(per_minute=60)
def api_metrics(access: AccessContext, decision_id: str):
    resolved = service.resolve_decision_id(decision_id, access)
    metric = (request.args.get("metric") or "").strip() or None
    return _json(
        service.decision_metrics(resolved, _filters(), access, group_by=_group_by(), metric_id=metric)
    )


@bp.route("/api/decisions/<decision_id>/flags", methods=["GET"])
@api_view(per_minute=60)
def api_flags(access: AccessContext, decision_id: str):
    resolved = service.resolve_decision_id(decision_id, access)
    return _json(service.decision_flags(resolved, _filters(), access))


@bp.route("/api/decision-flags/<flag_id>", methods=["GET"])
@api_view(per_minute=60)
def api_flag(access: AccessContext, flag_id: str):
    return _json(service.flag_detail(flag_id, access, lang=_filters().lang))


@bp.route("/api/decision-flags/<flag_id>/acknowledge", methods=["POST"])
@api_view(per_minute=30)
def api_flag_acknowledge(access: AccessContext, flag_id: str):
    body = _body()
    return _json(service.set_flag_status(flag_id, "acknowledged", access, note=_note(body)))


@bp.route("/api/decision-flags/<flag_id>/review", methods=["POST"])
@api_view(per_minute=30)
def api_flag_review(access: AccessContext, flag_id: str):
    body = _body()
    return _json(service.set_flag_status(flag_id, "under_review", access, note=_note(body)))


@bp.route("/api/decision-flags/<flag_id>/resolve", methods=["POST"])
@api_view(per_minute=30)
def api_flag_resolve(access: AccessContext, flag_id: str):
    body = _body()
    status = "dismissed" if body.get("dismiss") is True else "resolved"
    return _json(service.set_flag_status(flag_id, status, access, note=_note(body)))


@bp.route("/api/decision-flags/<flag_id>/feedback", methods=["POST"])
@api_view(per_minute=30)
def api_flag_feedback(access: AccessContext, flag_id: str):
    body = _body()
    verdict = body.get("verdict")
    if not isinstance(verdict, str):
        raise ValueError("verdict is required")
    return _json(service.add_flag_feedback(flag_id, verdict, access, note=_note(body)))


@bp.route("/api/decision-evidence/<evidence_id>", methods=["GET"])
@api_view()
def api_evidence(access: AccessContext, evidence_id: str):
    return _json(service.get_evidence(evidence_id, access))


@bp.route("/api/decision-sources/<path:reference>", methods=["GET"])
@api_view()
def api_source(access: AccessContext, reference: str):
    return _json(service.get_source_record(reference, access))


@bp.route("/api/metric-definitions", methods=["GET"])
@api_view()
def api_metric_definitions(access: AccessContext):
    return _json(service.metric_definitions(_filters().lang))


@bp.route("/api/decision-methodologies/<decision_id>", methods=["GET"])
@api_view()
def api_methodology(access: AccessContext, decision_id: str):
    resolved = service.resolve_decision_id(decision_id, access)
    return _json(service.methodology(resolved, access, _filters().lang))


# Administration ------------------------------------------------------------


@bp.route("/api/admin/decisions", methods=["GET"])
@api_view(manage=True)
def api_admin_overview(access: AccessContext):
    return _json(service.admin_overview(access))


@bp.route("/api/admin/decision-rules/<rule_id>", methods=["PUT"])
@api_view(manage=True, per_minute=30)
def api_admin_rule_update(access: AccessContext, rule_id: str):
    body = _body()
    changes = body.get("changes")
    if not isinstance(changes, dict):
        raise ValueError("changes is required")
    return _json(service.update_rule(rule_id, changes, access, _note(body)))


@bp.route("/api/admin/decision-rules/<rule_id>/history", methods=["GET"])
@api_view(manage=True)
def api_admin_rule_history(access: AccessContext, rule_id: str):
    return _json(service.rule_history(rule_id, access))


@bp.route("/api/admin/decisions/<decision_id>", methods=["PUT"])
@api_view(manage=True, per_minute=30)
def api_admin_decision_update(access: AccessContext, decision_id: str):
    body = _body()
    changes = body.get("changes")
    if not isinstance(changes, dict):
        raise ValueError("changes is required")
    return _json(service.update_decision(decision_id, changes, access, _note(body)))


@bp.route("/api/admin/decision-runs", methods=["GET"])
@api_view(manage=True)
def api_admin_runs(access: AccessContext):
    return _json(service.rule_runs(access))


@bp.route("/api/admin/decision-feedback", methods=["GET"])
@api_view(manage=True)
def api_admin_feedback(access: AccessContext):
    return _json(service.feedback_summary(access))


@bp.route("/api/admin/decision-integrations", methods=["GET"])
@api_view(manage=True)
def api_admin_integrations(access: AccessContext):
    return _json(service.integration_health(access))


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def _page_guard():
    """Return a redirect/response when the user may not open the page, else ``None``."""
    from flask import flash, redirect

    if not getattr(current_user, "is_authenticated", False):
        flash("Access denied. Please log in.", "warning")
        return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
    if not _access().can_view:
        flash("Access denied. Decision Support permission required.", "warning")
        return redirect(url_for("main.dashboard"))
    return None


@bp.route("/decisions/static/<path:filename>", methods=["GET"])
def static_file(filename: str):
    if not getattr(current_user, "is_authenticated", False):
        return json_auth_required()
    return send_from_directory(str(_PLUGIN_DIR / "static"), filename)


def _page(template: str, **context: Any):
    return render_template(f"plugins/ifrc/decisions/{template}", **context)


@bp.route("/decisions", methods=["GET"])
def page_catalogue():
    denied = _page_guard()
    if denied is not None:
        return denied
    return _page("catalogue.html", can_manage=_access().can_manage)


@bp.route("/decisions/<slug>", methods=["GET"])
def page_workspace(slug: str):
    denied = _page_guard()
    if denied is not None:
        return denied
    try:
        decision_id = service.resolve_decision_id(slug, _access())
    except service.NotFound:
        return json_not_found("Not found.")
    return _page("workspace.html", decision_id=decision_id, slug=slug, country="", region="")


@bp.route("/decisions/<slug>/country/<country_code>", methods=["GET"])
def page_country(slug: str, country_code: str):
    denied = _page_guard()
    if denied is not None:
        return denied
    code = country_code.strip().upper()
    if len(code) != 3 or not code.isalpha():
        return json_not_found("Not found.")
    try:
        decision_id = service.resolve_decision_id(slug, _access())
    except service.NotFound:
        return json_not_found("Not found.")
    if not _access().can_read_iso3(code):
        return json_not_found("Not found.")
    return _page("workspace.html", decision_id=decision_id, slug=slug, country=code, region="")


@bp.route("/decisions/<slug>/region/<region_code>", methods=["GET"])
def page_region(slug: str, region_code: str):
    denied = _page_guard()
    if denied is not None:
        return denied
    try:
        decision_id = service.resolve_decision_id(slug, _access())
    except service.NotFound:
        return json_not_found("Not found.")
    return _page("workspace.html", decision_id=decision_id, slug=slug, country="", region=region_code[:80])


@bp.route("/decisions/<slug>/evidence", methods=["GET"])
def page_evidence(slug: str):
    denied = _page_guard()
    if denied is not None:
        return denied
    try:
        decision_id = service.resolve_decision_id(slug, _access())
    except service.NotFound:
        return json_not_found("Not found.")
    return _page("workspace.html", decision_id=decision_id, slug=slug, country="", region="", focus="evidence")


@bp.route("/admin/decisions", methods=["GET"])
@permission_required("admin.decisions.manage")
def page_admin():
    return _page("admin.html")
