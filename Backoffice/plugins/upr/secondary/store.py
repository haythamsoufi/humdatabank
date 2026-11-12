"""plugin_data helpers for UPR secondary registry metadata."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.extensions import db
from app.models.plugin_data import PluginData
from app.utils.common.datetime_helpers import utcnow

PLUGIN_ID = "upr"
SECONDARY_KEY = "secondary"


def _empty_secondary() -> dict[str, Any]:
    return {"sources": {}}


def load_plugin_payload() -> dict[str, Any]:
    row = PluginData.query.filter_by(plugin_id=PLUGIN_ID).first()
    if row is None or not isinstance(row.data, dict):
        return {}
    return dict(row.data)


def save_plugin_payload(payload: dict[str, Any]) -> dict[str, Any]:
    row = PluginData.query.filter_by(plugin_id=PLUGIN_ID).first()
    now = utcnow()
    if row is None:
        row = PluginData(plugin_id=PLUGIN_ID, data=payload, created_at=now, updated_at=now)
        db.session.add(row)
    else:
        row.data = payload
        row.updated_at = now
    db.session.commit()
    return payload


def load_secondary_meta() -> dict[str, Any]:
    payload = load_plugin_payload()
    secondary = payload.get(SECONDARY_KEY)
    if not isinstance(secondary, dict):
        return _empty_secondary()
    sources = secondary.get("sources")
    if not isinstance(sources, dict):
        secondary = {**secondary, "sources": {}}
    return secondary


def save_secondary_meta(secondary: dict[str, Any]) -> dict[str, Any]:
    payload = load_plugin_payload()
    payload = deepcopy(payload) if payload else {}
    payload[SECONDARY_KEY] = secondary
    save_plugin_payload(payload)
    return secondary


def update_source_meta(source_id: str, **fields: Any) -> dict[str, Any]:
    secondary = load_secondary_meta()
    sources = dict(secondary.get("sources") or {})
    current = dict(sources.get(source_id) or {})
    current.update(fields)
    current.setdefault("id", source_id)
    sources[source_id] = current
    secondary["sources"] = sources
    save_secondary_meta(secondary)
    return current
