"""Durable per-import change logs, linked from the audit trail Details panel.

Bulk UPR/FDRS upserts and assignment Excel imports stream a summary JSON plus a
JSONL of row-level changes. Writes go to a local cache under
``instance/import_logs/`` and, on finalize, to ``storage_service`` (filesystem
locally, Azure Blob in prod) so they survive redeploys. The audit row stores
``change_log_url``; View Details opens that page.

Do not store the JSONL in the database — a single UPR import can be thousands
of change rows.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional

from flask import current_app, has_app_context, url_for
from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.utils.audit_context import set_audit_details

logger = logging.getLogger(__name__)

LOG_ID_RE = re.compile(r"^[a-fA-F0-9]{32}$")
_VALUE_PREVIEW_LIMIT = 240
_MAX_WARNING_LINES = 200
VIEWER_CHANGE_LIMIT = 500
STORAGE_CATEGORY = "import_logs"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_valid_import_log_id(log_id: str) -> bool:
    return bool(log_id and LOG_ID_RE.fullmatch(str(log_id)))


def import_logs_dir(log_dir: Optional[str] = None) -> str:
    if log_dir:
        path = log_dir
    elif has_app_context():
        path = os.path.join(current_app.instance_path, "import_logs")
    else:
        path = os.path.join(os.getcwd(), "instance", "import_logs")
    os.makedirs(path, exist_ok=True)
    return path


def summary_path(log_id: str, *, log_dir: Optional[str] = None) -> str:
    return os.path.join(import_logs_dir(log_dir), f"{log_id}.json")


def changes_path(log_id: str, *, log_dir: Optional[str] = None) -> str:
    return os.path.join(import_logs_dir(log_dir), f"{log_id}.jsonl")


def _storage_rel(log_id: str, ext: str) -> str:
    return f"{log_id}.{ext}"


def _use_durable_storage(log_dir: Optional[str] = None) -> bool:
    return log_dir is None and has_app_context()


def persist_import_log_to_storage(log_id: str, *, log_dir: Optional[str] = None) -> None:
    """Copy local summary + JSONL into durable storage. No-op for test *log_dir*."""
    if not is_valid_import_log_id(log_id) or not _use_durable_storage(log_dir):
        return
    from app.services.platform import storage_service

    try:
        for ext, path in (("json", summary_path(log_id, log_dir=log_dir)), ("jsonl", changes_path(log_id, log_dir=log_dir))):
            if not os.path.isfile(path):
                continue
            with open(path, "rb") as handle:
                storage_service.upload(STORAGE_CATEGORY, _storage_rel(log_id, ext), handle.read())
    except Exception:
        logger.exception("Failed to persist import change log %s to durable storage", log_id)


def hydrate_import_log_from_storage(log_id: str, ext: str, *, log_dir: Optional[str] = None) -> bool:
    """Ensure the local cache file exists, downloading from blob if needed."""
    path = summary_path(log_id, log_dir=log_dir) if ext == "json" else changes_path(log_id, log_dir=log_dir)
    if os.path.isfile(path):
        return True
    if not is_valid_import_log_id(log_id) or not _use_durable_storage(log_dir):
        return False
    from app.services.platform import storage_service

    rel = _storage_rel(log_id, ext)
    if not storage_service.exists(STORAGE_CATEGORY, rel):
        return False
    try:
        data = storage_service.download(STORAGE_CATEGORY, rel)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
        return True
    except Exception:
        logger.exception("Failed to hydrate import change log %s.%s from storage", log_id, ext)
        return False


def import_log_file_exists(log_id: str, ext: str, *, log_dir: Optional[str] = None) -> bool:
    path = summary_path(log_id, log_dir=log_dir) if ext == "json" else changes_path(log_id, log_dir=log_dir)
    if os.path.isfile(path):
        return True
    if not is_valid_import_log_id(log_id) or not _use_durable_storage(log_dir):
        return False
    from app.services.platform import storage_service

    return storage_service.exists(STORAGE_CATEGORY, _storage_rel(log_id, ext))


def stream_import_log_file(log_id: str, ext: str, *, filename: str, mimetype: str):
    """Flask response for a summary/JSONL download (storage first, then local cache)."""
    if not is_valid_import_log_id(log_id):
        from werkzeug.exceptions import NotFound

        raise NotFound()
    from flask import send_file
    from app.services.platform import storage_service

    if _use_durable_storage() and storage_service.exists(STORAGE_CATEGORY, _storage_rel(log_id, ext)):
        return storage_service.stream_response(
            STORAGE_CATEGORY,
            _storage_rel(log_id, ext),
            filename,
            mimetype=mimetype,
            as_attachment=True,
        )
    path = summary_path(log_id) if ext == "json" else changes_path(log_id)
    if hydrate_import_log_from_storage(log_id, ext) and os.path.isfile(path):
        return send_file(path, mimetype=mimetype, as_attachment=True, download_name=filename)
    from werkzeug.exceptions import NotFound

    raise NotFound()


_JSON_SCALAR_PAIR_RE = re.compile(
    r'"((?:\\.|[^"\\])*)"\s*:\s*(-?\d+(?:\.\d+)?|null|true|false)'
)


def _dump_json(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=True, sort_keys=True)


def compact_import_value(value: Any, *, limit: int = _VALUE_PREVIEW_LIMIT) -> Any:
    """Shrink scalars/JSON for the change log without dropping the fact of a write."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, dict):
        try:
            text = _dump_json(value)
        except TypeError:
            text = str(value)
        if len(text) <= limit:
            return value
        return {"keys": len(value), "preview": text[:limit] + "…"}
    if isinstance(value, list):
        try:
            text = _dump_json(value)
        except TypeError:
            text = str(value)
        if len(text) <= limit:
            return value
        return {"n": len(value), "preview": text[:limit] + "…"}
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _preview_scalar_pairs(value: Any) -> Optional[frozenset]:
    """Order-independent fingerprint of scalar JSON pairs in a value or compact preview."""
    if value is None or value == "":
        return frozenset()
    if isinstance(value, dict) and "preview" in value and set(value.keys()) <= {"keys", "n", "preview"}:
        text = str(value.get("preview") or "")
        if text.endswith("…"):
            text = text[:-1]
    else:
        try:
            text = _dump_json(value)
        except TypeError:
            return None
    return frozenset(_JSON_SCALAR_PAIR_RE.findall(text))


def _is_structured_import_value(value: Any) -> bool:
    if isinstance(value, (dict, list)):
        return True
    if isinstance(value, str) and value[:1] in "{[":
        return True
    return False


def import_values_equivalent(left: Any, right: Any) -> bool:
    """True when two logged values are the same, ignoring JSON key order and compact previews."""
    if left == right:
        return True
    if compact_import_value(left) == compact_import_value(right):
        return True
    if not (_is_structured_import_value(left) or _is_structured_import_value(right)):
        return False
    left_pairs = _preview_scalar_pairs(left)
    right_pairs = _preview_scalar_pairs(right)
    return left_pairs is not None and left_pairs == right_pairs


def _is_truncated_preview(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and "preview" in value
        and set(value.keys()) <= {"keys", "n", "preview"}
        and str(value.get("preview") or "").endswith("…")
    )


def is_noop_import_change(change: Dict[str, Any]) -> bool:
    """True when an update row has the same before/after value and disagg."""
    if not isinstance(change, dict):
        return True
    op = str(change.get("op") or "update").strip().lower()
    if op in ("insert", "stage"):
        return False
    if not import_values_equivalent(change.get("old_value"), change.get("new_value")):
        return False
    if import_values_equivalent(change.get("old_disagg"), change.get("new_disagg")):
        return True
    # Compacted previews are truncated, so key-order differences look like
    # disagg changes even when the stored objects were equal. Same scalar
    # value + same preview key-count is not a user-visible change.
    old_d = change.get("old_disagg")
    new_d = change.get("new_disagg")
    if _is_truncated_preview(old_d) and _is_truncated_preview(new_d):
        return old_d.get("keys") == new_d.get("keys")
    return False


def change_log_url_for(log_id: str) -> Optional[str]:
    if not is_valid_import_log_id(log_id):
        return None
    try:
        return url_for("import_change_log.view_log", log_id=log_id)
    except RuntimeError:
        return f"/admin/import-logs/{log_id}"


def set_import_audit_details(
    *,
    log_id: str,
    import_kind: str,
    filename: Optional[str] = None,
    rounds: Optional[Iterable[str]] = None,
    templates: Optional[Iterable[Any]] = None,
    dry_run: Optional[bool] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Attach the change-log link to this request's audit-trail row."""
    fields: Dict[str, Any] = {
        "job_id": log_id,
        "import_kind": import_kind,
        "change_log_url": change_log_url_for(log_id),
    }
    if filename:
        fields["filename"] = filename
    if rounds:
        fields["rounds"] = [str(r) for r in rounds if str(r).strip()]
    if templates:
        fields["templates"] = [str(t) for t in templates if str(t).strip()]
    if dry_run is not None:
        fields["dry_run"] = bool(dry_run)
    if extra:
        fields.update(extra)
    set_audit_details(**fields)


def attach_import_change_log_to_activity(
    *,
    log_id: str,
    user_id: Optional[int],
    extra: Optional[Dict[str, Any]] = None,
) -> bool:
    """Merge completion counts onto the queued audit row (async imports)."""
    if not user_id or not is_valid_import_log_id(log_id):
        return False
    from app.models.core import UserActivityLog

    rows = (
        UserActivityLog.query.filter_by(user_id=int(user_id))
        .order_by(UserActivityLog.id.desc())
        .limit(80)
        .all()
    )
    for row in rows:
        ctx = dict(row.context_data or {})
        if str(ctx.get("job_id") or "") != str(log_id):
            continue
        ctx["change_log_url"] = change_log_url_for(log_id)
        if extra:
            for key, value in extra.items():
                if value is None or value == "" or value == []:
                    continue
                ctx[key] = value
        row.context_data = ctx
        flag_modified(row, "context_data")
        db.session.add(row)
        db.session.commit()
        return True
    return False


class ImportChangeLogWriter:
    """Stream row-level changes to JSONL and write a summary JSON on finalize."""

    def __init__(
        self,
        log_id: str,
        *,
        kind: str,
        meta: Optional[Dict[str, Any]] = None,
        log_dir: Optional[str] = None,
    ):
        if not is_valid_import_log_id(log_id):
            raise ValueError("Invalid import log id")
        self.log_id = log_id
        self.kind = kind
        self.meta = dict(meta or {})
        self.log_dir = log_dir
        self.started_at = utc_iso()
        self.change_count = 0
        self._finalized = False
        self._fh = open(changes_path(log_id, log_dir=log_dir), "w", encoding="utf-8")

    def __enter__(self) -> "ImportChangeLogWriter":
        return self

    def __exit__(self, exc_type, exc, _tb) -> None:
        if not self._finalized:
            self.finalize({"success": False, "errors": 1} if exc_type else {})

    def record(self, change: Dict[str, Any]) -> None:
        if not isinstance(change, dict) or not change:
            return
        if is_noop_import_change(change):
            return
        row = {
            "op": change.get("op") or "update",
            "aes_id": change.get("aes_id"),
            "item_id": change.get("item_id"),
            "iso3": change.get("iso3") or None,
            "year": change.get("year") or None,
            "kpi": change.get("kpi") or None,
            "label": change.get("label") or None,
            "old_value": compact_import_value(change.get("old_value")),
            "new_value": compact_import_value(change.get("new_value")),
            "old_disagg": compact_import_value(change.get("old_disagg")),
            "new_disagg": compact_import_value(change.get("new_disagg")),
        }
        self._fh.write(json.dumps(row, default=str, ensure_ascii=True) + "\n")
        self.change_count += 1

    def finalize(self, stats: Optional[Dict[str, Any]] = None) -> str:
        if self._finalized:
            return summary_path(self.log_id, log_dir=self.log_dir)
        try:
            self._fh.flush()
        finally:
            self._fh.close()
            self._finalized = True
        stats = dict(stats or {})
        warnings = stats.get("warnings") or []
        if isinstance(warnings, list) and len(warnings) > _MAX_WARNING_LINES:
            warnings = warnings[:_MAX_WARNING_LINES] + [
                f"… {len(stats.get('warnings') or []) - _MAX_WARNING_LINES} more warnings omitted"
            ]
        payload = {
            "log_id": self.log_id,
            "kind": self.kind,
            "started_at": self.started_at,
            "finished_at": utc_iso(),
            "change_count": self.change_count,
            "meta": self.meta,
            "stats": {
                key: stats.get(key)
                for key in (
                    "loaded",
                    "skipped",
                    "inserted",
                    "updated",
                    "unchanged",
                    "errors",
                    "updated_count",
                    "transformed",
                    "warning_count",
                    "warning_unique_count",
                    "documents_inserted",
                    "documents_updated",
                    "success",
                    "dry_run",
                )
                if key in stats
            },
            "warnings": warnings,
        }
        path = summary_path(self.log_id, log_dir=self.log_dir)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str, ensure_ascii=True)
        persist_import_log_to_storage(self.log_id, log_dir=self.log_dir)
        return path


def staged_payload_changes(payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Turn a stage-only Excel payload (fields/matrices) into change-log rows."""
    if not isinstance(payload, dict):
        return []
    changes: List[Dict[str, Any]] = []
    for item_id, value in (payload.get("fields") or {}).items():
        if isinstance(value, dict):
            changes.append({
                "op": "stage",
                "item_id": item_id,
                "new_value": value.get("value"),
                "new_disagg": value.get("disagg_data") or value.get("disagg"),
            })
        else:
            changes.append({"op": "stage", "item_id": item_id, "new_value": value})
    for item_id, value in (payload.get("matrices") or {}).items():
        changes.append({"op": "stage", "item_id": item_id, "new_disagg": value})
    for entry in payload.get("dynamic_indicators") or []:
        if not isinstance(entry, dict):
            continue
        changes.append({
            "op": "stage",
            "label": entry.get("name") or entry.get("kpi") or "dynamic_indicator",
            "new_value": entry.get("value"),
            "new_disagg": entry.get("disagg_data") or entry.get("matrix"),
        })
    for entry in payload.get("repeat_slots") or []:
        if not isinstance(entry, dict):
            continue
        changes.append({
            "op": "stage",
            "label": entry.get("label") or entry.get("name") or "repeat_slot",
            "new_value": entry.get("value") or entry,
        })
    return changes


def persist_import_change_log(
    *,
    log_id: str,
    kind: str,
    meta: Optional[Dict[str, Any]] = None,
    changes: Optional[Iterable[Dict[str, Any]]] = None,
    stats: Optional[Dict[str, Any]] = None,
    log_dir: Optional[str] = None,
) -> str:
    writer = ImportChangeLogWriter(log_id, kind=kind, meta=meta, log_dir=log_dir)
    for change in changes or []:
        writer.record(change)
    return writer.finalize(stats)


def record_assignment_import_audit(
    *,
    kind: str,
    result: Dict[str, Any],
    filename: Optional[str] = None,
    assignment_label: Optional[str] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> str:
    """Write a change log for a synchronous assignment Excel import and attach audit details."""
    log_id = uuid.uuid4().hex
    meta = {
        "filename": filename,
        "assignment": assignment_label,
        **(extra_meta or {}),
    }
    changes = result.get("changes") or []
    if not changes:
        changes = staged_payload_changes(result.get("payload"))
    persist_import_change_log(
        log_id=log_id,
        kind=kind,
        meta=meta,
        changes=changes,
        stats={
            "updated": result.get("updated_count"),
            "updated_count": result.get("updated_count"),
            "errors": len(result.get("errors") or []),
            "success": result.get("success"),
            "warnings": result.get("warnings") or [],
        },
    )
    set_import_audit_details(
        log_id=log_id,
        import_kind=kind,
        filename=filename,
        extra={
            "rows_updated": result.get("updated_count"),
            "assignment": assignment_label,
        },
    )
    return log_id


def load_import_log_summary(log_id: str, *, log_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    path = summary_path(log_id, log_dir=log_dir)
    if not os.path.isfile(path):
        hydrate_import_log_from_storage(log_id, "json", log_dir=log_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read import change log %s", log_id)
        return None
    return payload if isinstance(payload, dict) else None


def iter_import_log_changes(
    log_id: str,
    *,
    limit: int = VIEWER_CHANGE_LIMIT,
    log_dir: Optional[str] = None,
) -> Iterator[Dict[str, Any]]:
    path = changes_path(log_id, log_dir=log_dir)
    if not os.path.isfile(path):
        hydrate_import_log_from_storage(log_id, "jsonl", log_dir=log_dir)
    if not os.path.isfile(path):
        return
        yield  # pragma: no cover  # makes this a generator
    n = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if n >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and not is_noop_import_change(row):
                yield row
                n += 1


def count_import_log_changes(
    log_id: str,
    *,
    log_dir: Optional[str] = None,
    include_noops: bool = False,
) -> int:
    path = changes_path(log_id, log_dir=log_dir)
    if not os.path.isfile(path):
        hydrate_import_log_from_storage(log_id, "jsonl", log_dir=log_dir)
    if not os.path.isfile(path):
        return 0
    n = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            if include_noops:
                n += 1
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and not is_noop_import_change(row):
                n += 1
    return n


def count_import_log_noops(log_id: str, *, log_dir: Optional[str] = None) -> int:
    path = changes_path(log_id, log_dir=log_dir)
    if not os.path.isfile(path):
        hydrate_import_log_from_storage(log_id, "jsonl", log_dir=log_dir)
    if not os.path.isfile(path):
        return 0
    n = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and is_noop_import_change(row):
                n += 1
    return n
