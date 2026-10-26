"""One-shot import of plugins/*/plugin_config.json into plugin_data."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, List, Mapping, Optional

from flask import has_app_context

from app.extensions import db
from app.models.plugin_data import PluginData
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)

_LEGACY_FILENAME = "plugin_config.json"


def import_missing_plugin_configs(
    plugin_dirs: Iterable[Path],
    *,
    plugin_id_by_dir: Optional[Mapping[Path, str]] = None,
) -> List[str]:
    """Insert ``plugin_config.json`` into ``plugin_data`` when no row exists yet.

    Existing rows are never overwritten. Returns plugin_ids that were imported.
    """
    if not has_app_context():
        return []

    imported: List[str] = []
    for plugin_dir in plugin_dirs:
        directory = Path(plugin_dir)
        config_path = directory / _LEGACY_FILENAME
        if not config_path.is_file():
            continue

        plugin_id = None
        if plugin_id_by_dir:
            plugin_id = plugin_id_by_dir.get(directory) or plugin_id_by_dir.get(directory.resolve())
        if not plugin_id:
            plugin_id = directory.name
        plugin_id = str(plugin_id).strip()
        if not plugin_id:
            continue

        try:
            if PluginData.query.filter_by(plugin_id=plugin_id).first() is not None:
                continue
        except Exception as exc:
            logger.warning("Cannot check plugin_data for %s: %s", plugin_id, exc)
            continue

        try:
            with open(config_path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Skipping corrupt legacy plugin config %s: %s", config_path, exc)
            continue

        if not isinstance(payload, dict):
            logger.warning("Skipping non-object legacy plugin config %s", config_path)
            continue

        try:
            row = PluginData(plugin_id=plugin_id, data=payload, created_at=utcnow(), updated_at=utcnow())
            db.session.add(row)
            db.session.commit()
            imported.append(plugin_id)
            logger.info("Imported legacy plugin config for %s from %s", plugin_id, config_path)
        except Exception as exc:
            db.session.rollback()
            logger.warning("Failed to import legacy plugin config for %s: %s", plugin_id, exc)

    return imported
