"""Post a validated Draft 0 to the authenticated IFRC GO write API.

Operational updates go to ``dref-op-update``. Final reports go to
``dref-final-report``. The record is created as a GO draft so GO can process it.
Contact names and addresses are not sent.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from urllib import error as urlerror
from urllib import request as urlrequest

from flask import current_app

from app.extensions import db
from app.utils.common.datetime_helpers import ensure_utc, utcnow
from plugins.dref_monitoring.constants import GO_API_ROOT
from plugins.dref_monitoring.models import DrefDraft
from plugins.dref_monitoring.services.drafts import narrative_map
from plugins.dref_monitoring.services.narrative_format import to_plain

logger = logging.getLogger(__name__)

_TOKEN_MISSING = "GO API token is not configured."
_REJECTED = "GO did not accept the report."


def go_payload(operation, draft) -> dict:
    # GO takes plain text. Lists keep their "- " and "1. " markers, paragraphs are split by a blank line.
    chapters = {key: to_plain(text) for key, text in narrative_map(draft).items()}
    payload = {
        "title": (operation.disaster_name or operation.appeal_code or "")[:255],
        "appeal_code": operation.appeal_code,
        "status": 1,
        "starting_language": draft.language or "en",
        "event_description": chapters.get("what_happened") or "",
        "event_scope": chapters.get("scope_and_scale") or "",
        "ifrc": chapters.get("ifrc_actions") or "",
        "icrc": chapters.get("icrc_actions") or "",
        "un_or_other_actor": chapters.get("other_actors") or "",
        "identified_gaps": chapters.get("needs") or "",
        "operation_objective": chapters.get("overall_objective") or "",
        "response_strategy": chapters.get("strategy_rationale") or "",
        "people_assisted": chapters.get("who_targeted") or "",
        "selection_criteria": chapters.get("selection_criteria") or "",
    }
    if operation.go_appeal_id:
        payload["dref"] = operation.go_appeal_id
    if operation.people_targeted is not None:
        payload["number_of_people_targeted"] = operation.people_targeted
    if operation.people_affected is not None:
        payload["number_of_people_affected"] = operation.people_affected
    if draft.report_kind == "final_report":
        payload["mitigation_efforts_and_achievements"] = chapters.get("achievements") or ""
        payload["lessons_learned_and_challenges"] = chapters.get("challenges") or ""
        if operation.end_date is not None:
            payload["operation_end_date"] = operation.end_date.isoformat()
    else:
        payload["summary_of_change"] = chapters.get("summary_of_changes") or ""
        if operation.end_date is not None:
            payload["new_operational_end_date"] = operation.end_date.isoformat()
        if operation.total_approved is not None:
            payload["total_dref_allocation"] = int(operation.total_approved)
    return {key: value for key, value in payload.items() if value not in ("", None)}


def _default_post(url: str, payload: dict, token: str) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=60) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urlerror.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body


_SENDING = "sending"
_SEND_TIMEOUT = timedelta(minutes=5)
_BUSY = "This report is already being sent to GO."


def _claim(draft) -> dict | None:
    """Reserve the draft for one send, so a double click cannot post it twice.

    Returns a result when there is nothing to send, or None once this call owns
    the send. The row is locked while the claim is written. A claim older than
    the timeout is treated as a worker that died and can be retaken.
    """
    row = (
        db.session.query(DrefDraft)
        .filter_by(id=draft.id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if row is None:
        return {"ok": False, "error": "Draft not found."}
    if (row.status or "") == "submitted" and row.go_status == "sent":
        db.session.rollback()
        return {"ok": True, "reference": row.go_reference}
    if (row.status or "draft") == "draft":
        db.session.rollback()
        return {"ok": False, "error": "Validate the draft before sending it to GO."}
    started = ensure_utc(row.go_submitted_at)
    if row.go_status == _SENDING and started is not None and utcnow() - started < _SEND_TIMEOUT:
        db.session.rollback()
        return {"ok": False, "error": _BUSY}
    row.go_status = _SENDING
    row.go_submitted_at = utcnow()
    row.go_error = ""
    db.session.commit()
    return None


def submit_draft(operation, draft, post=None) -> dict:
    if draft.operation_id != operation.id:
        return {"ok": False, "error": "Draft not found."}
    claimed = _claim(draft)
    if claimed is not None:
        return claimed
    token = str(current_app.config.get("GO_API_TOKEN") or "").strip()
    if not token:
        draft.go_status = "failed"
        draft.go_error = _TOKEN_MISSING
        draft.go_submitted_at = None
        db.session.commit()
        return {"ok": False, "error": _TOKEN_MISSING}
    root = str(current_app.config.get("GO_API_BASE") or GO_API_ROOT).rstrip("/") + "/"
    path = "dref-final-report/" if draft.report_kind == "final_report" else "dref-op-update/"
    url = root + path
    sender = post or _default_post
    try:
        payload = go_payload(operation, draft)
        status, body = sender(url, payload, token)
    except Exception:
        logger.warning("DREF GO submission failed for %s", operation.appeal_code, exc_info=True)
        draft.go_status = "failed"
        draft.go_error = _REJECTED
        draft.go_submitted_at = None
        db.session.commit()
        return {"ok": False, "error": _REJECTED}
    if status < 200 or status >= 300:
        logger.warning("DREF GO submission for %s returned %s", operation.appeal_code, status)
        draft.go_status = "failed"
        draft.go_error = _REJECTED
        draft.go_submitted_at = None
        db.session.commit()
        return {"ok": False, "error": _REJECTED}
    reference = ""
    try:
        parsed = json.loads(body or "{}")
        if isinstance(parsed, dict) and parsed.get("id") is not None:
            reference = str(parsed.get("id"))
    except json.JSONDecodeError:
        reference = ""
    draft.status = "submitted"
    draft.go_status = "sent"
    draft.go_reference = reference[:64]
    draft.go_error = ""
    draft.go_submitted_at = utcnow()
    db.session.commit()
    return {"ok": True, "reference": draft.go_reference}
