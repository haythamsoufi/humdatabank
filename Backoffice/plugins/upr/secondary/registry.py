"""Secondary source registry surfaced in UPR settings."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plugins.upr.secondary import paths
from plugins.upr.secondary.io import read_json
from plugins.upr.secondary.store import load_secondary_meta, update_source_meta


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rel_plugin_path(path: Path) -> str:
    try:
        return str(path.relative_to(paths.PLUGIN_DIR)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _file_meta(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "row_count": 0, "file_updated_at": None}
    stat = path.stat()
    payload = read_json(path, default={})
    rows = 0
    if isinstance(payload, dict):
        if isinstance(payload.get("rows"), list):
            rows = len(payload["rows"])
        elif isinstance(payload.get("scores"), dict):
            rows = len(payload["scores"])
        elif isinstance(payload.get("values"), dict):
            rows = len(payload["values"])
        elif isinstance(payload.get("by_iso3"), dict):
            rows = len(payload["by_iso3"])
    return {
        "exists": True,
        "row_count": rows,
        "file_updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "path": _rel_plugin_path(path),
    }


def list_round_files(kind: str) -> list[dict[str, Any]]:
    folder = paths.MULTILATERAL_DIR if kind == "multilateral" else paths.EAS_SPRM_OPS_DIR
    paths.ensure_dirs()
    found: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json")):
        payload = read_json(path, default={}) or {}
        found.append(
            {
                "round": path.stem.upper(),
                "year": payload.get("year"),
                "row_count": len(payload.get("rows") or []),
                "updated_at": payload.get("updated_at"),
                "path": _rel_plugin_path(path),
            }
        )
    return found


def source_status(source_id: str) -> dict[str, Any]:
    meta = (load_secondary_meta().get("sources") or {}).get(source_id) or {}
    label = paths.SOURCE_LABELS.get(source_id, source_id)
    base = {
        "id": source_id,
        "label": label,
        "source": meta.get("source"),
        "edition": meta.get("edition"),
        "updated_at": meta.get("updated_at"),
        "row_count": meta.get("row_count") or 0,
        "status": meta.get("status") or "empty",
        "kind": meta.get("kind") or "file",
    }
    if source_id in paths.GLOBAL_FILES:
        file_info = _file_meta(paths.GLOBAL_FILES[source_id])
        if source_id == "inform_risk" and not file_info["exists"]:
            file_info = _file_meta(paths.LEGACY_INFORM_RISK)
        base.update(file_info)
        if not base.get("updated_at"):
            base["updated_at"] = file_info.get("file_updated_at")
        if not base.get("row_count"):
            base["row_count"] = file_info.get("row_count") or 0
        if file_info.get("exists"):
            base["status"] = base.get("status") if base.get("status") != "empty" else "ready"
    elif source_id in {"multilateral", "eas_sprm_ops"}:
        rounds = list_round_files(source_id)
        base["rounds"] = rounds
        base["row_count"] = sum(int(item.get("row_count") or 0) for item in rounds)
        base["kind"] = "round_file"
        if rounds:
            base["status"] = "ready"
            base["updated_at"] = max((item.get("updated_at") or "") for item in rounds) or base.get("updated_at")
    return base


def list_sources() -> list[dict[str, Any]]:
    order = [
        "population",
        "poverty",
        "income_groups",
        "inform_risk",
        "inform_severity",
        "inform_climate",
        "hdi",
        "multilateral",
        "eas_sprm_ops",
    ]
    return [source_status(source_id) for source_id in order]


def touch_source(
    source_id: str,
    *,
    row_count: int | None = None,
    edition: str | None = None,
    source: str | None = None,
    status: str = "ready",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "updated_at": _iso_now(),
        "status": status,
        "kind": "round_file" if source_id in {"multilateral", "eas_sprm_ops"} else "file",
    }
    if row_count is not None:
        fields["row_count"] = int(row_count)
    if edition is not None:
        fields["edition"] = edition
    if source is not None:
        fields["source"] = source
    if extra:
        fields.update(extra)
    if source_id in paths.GLOBAL_FILES:
        fields["path"] = _rel_plugin_path(paths.GLOBAL_FILES[source_id])
    return update_source_meta(source_id, **fields)
