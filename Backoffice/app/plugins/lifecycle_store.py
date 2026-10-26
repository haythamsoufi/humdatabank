"""DB-backed plugin activation state (replaces instance/plugin_states.json)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Sequence

from flask import has_app_context

from app.extensions import db
from app.models.plugin_data import PluginData
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)

LIFECYCLE_PLUGIN_ID = "__plugin_lifecycle__"
_ACTIVE_IDS_KEY = "active_plugin_ids"
_LEGACY_ACTIVE_KEY = "active_plugins"


def _row_query(*, for_update: bool = False):
    query = PluginData.query.filter_by(plugin_id=LIFECYCLE_PLUGIN_ID)
    if for_update:
        query = query.with_for_update()
    return query


def _tokens_from_payload(payload: Any) -> List[str]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get(_ACTIVE_IDS_KEY)
    if raw is None:
        raw = payload.get(_LEGACY_ACTIVE_KEY)
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(token).strip() for token in raw if str(token).strip()]


def load_active_plugin_ids() -> List[str]:
    """Return persisted active plugin tokens, or [] when missing / unavailable."""
    if not has_app_context():
        return []
    try:
        row = _row_query().first()
        if row is None:
            return []
        return _tokens_from_payload(row.data)
    except Exception as exc:
        logger.warning("Failed to load plugin lifecycle state from DB: %s", exc)
        return []


def get_updated_at() -> Optional[datetime]:
    """Lifecycle row ``updated_at``, or None when missing / unavailable."""
    if not has_app_context():
        return None
    try:
        row = _row_query().first()
        if row is None:
            return None
        return row.updated_at
    except Exception as exc:
        logger.warning("Failed to read plugin lifecycle updated_at: %s", exc)
        return None


def save_active_plugin_ids(plugin_ids: Sequence[str]) -> bool:
    """Persist the active plugin id set. Returns False on failure."""
    if not has_app_context():
        logger.warning("Cannot persist plugin lifecycle state outside application context")
        return False

    cleaned = sorted({str(pid).strip() for pid in plugin_ids if str(pid).strip()})
    try:
        row = _row_query(for_update=True).first()
        payload = {
            _ACTIVE_IDS_KEY: cleaned,
            "last_updated": utcnow().isoformat(),
        }
        if row is None:
            row = PluginData(plugin_id=LIFECYCLE_PLUGIN_ID, data=payload)
            db.session.add(row)
        else:
            data = dict(row.data) if isinstance(row.data, dict) else {}
            data[_ACTIVE_IDS_KEY] = cleaned
            data["last_updated"] = payload["last_updated"]
            data.pop(_LEGACY_ACTIVE_KEY, None)
            row.data = data
            row.updated_at = utcnow()
        db.session.commit()
        return True
    except Exception as exc:
        db.session.rollback()
        logger.error("Failed to save plugin lifecycle state: %s", exc, exc_info=True)
        return False


def migrate_from_legacy_state_file(path: Path) -> Optional[List[str]]:
    """Import ``plugin_states.json`` into DB when the lifecycle row is absent.

    Returns the imported token list when a migration ran, otherwise None.
    Does nothing when the lifecycle row already exists.
    """
    if not has_app_context():
        return None

    try:
        if _row_query().first() is not None:
            return None
    except Exception as exc:
        logger.warning("Cannot check lifecycle row for legacy migrate: %s", exc)
        return None

    state_path = Path(path)
    if not state_path.is_file():
        return None

    try:
        with open(state_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read legacy plugin_states.json %s: %s", state_path, exc)
        return None

    tokens = _tokens_from_payload(payload)
    if not save_active_plugin_ids(tokens):
        return None
    logger.info(
        "Migrated %s active plugin token(s) from %s into plugin_data",
        len(tokens),
        state_path,
    )
    return tokens
