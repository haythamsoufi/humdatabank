"""Database-backed plugin configuration (replaces file-based BasePluginConfig)."""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from flask import current_app, has_app_context

from app.extensions import db
from app.models.plugin_data import PluginData

logger = logging.getLogger(__name__)


class DbPluginConfig:
    """Lazy DB-backed config with the same public API as BasePluginConfig."""

    def __init__(
        self,
        plugin_id: str,
        default_config: Dict[str, Any] | None = None,
        *,
        plugin_root: Optional[Path] = None,
        legacy_config_filename: str = "plugin_config.json",
    ):
        self.plugin_id = plugin_id
        self.default_config = default_config or {}
        self.plugin_root = Path(plugin_root) if plugin_root else None
        self.legacy_config_filename = legacy_config_filename
        # In-memory cache only; never populated at import time.
        self.config: Dict[str, Any] = {}

    def _legacy_config_path(self) -> Path | None:
        if self.plugin_root:
            return self.plugin_root / self.legacy_config_filename
        return None

    def _merge_with_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        merged = copy.deepcopy(self.default_config)

        def deep_merge(target: Dict[str, Any], source: Dict[str, Any]) -> None:
            for key, value in source.items():
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    deep_merge(target[key], value)
                else:
                    target[key] = value

        deep_merge(merged, config)
        return merged

    def _load_legacy_file(self) -> Dict[str, Any] | None:
        path = self._legacy_config_path()
        if not path or not path.is_file():
            return None
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else None
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read legacy plugin config %s: %s", path, exc)
            return None

    def _local_config_snapshot(self) -> Dict[str, Any]:
        """Config readable without a Flask app context (import-time safe)."""
        legacy = self._load_legacy_file()
        return self._merge_with_defaults(legacy or {})

    def _get_or_create_row(self, *, for_update: bool = False) -> PluginData:
        query = PluginData.query.filter_by(plugin_id=self.plugin_id)
        if for_update:
            query = query.with_for_update()
        row = query.first()
        if row is not None:
            return row

        legacy = self._load_legacy_file()
        initial = self._merge_with_defaults(legacy or {})
        row = PluginData(plugin_id=self.plugin_id, data=initial)
        db.session.add(row)
        db.session.flush()
        return row

    def _read_config(self) -> Dict[str, Any]:
        if not has_app_context():
            self.config = self._local_config_snapshot()
            return self.config

        row = self._get_or_create_row(for_update=False)
        stored = row.data if isinstance(row.data, dict) else {}
        self.config = self._merge_with_defaults(stored)
        return self.config

    def _save_config(self, config: Dict[str, Any]) -> bool:
        if not has_app_context():
            logger.warning(
                "Cannot persist %s plugin config outside application context",
                self.plugin_id,
            )
            return False

        try:
            row = self._get_or_create_row(for_update=True)
            row.data = copy.deepcopy(config)
            self.config = copy.deepcopy(config)
            db.session.commit()
            return True
        except Exception as exc:
            db.session.rollback()
            if hasattr(current_app, "logger"):
                current_app.logger.error(
                    "Error saving %s plugin data: %s",
                    self.plugin_id,
                    exc,
                    exc_info=True,
                )
            return False

    def get_all_config(self) -> Dict[str, Any]:
        return copy.deepcopy(self._read_config())

    def get_section(self, section_name: str) -> Dict[str, Any]:
        return copy.deepcopy(self._read_config().get(section_name, {}))

    def update_config(self, new_config: Dict[str, Any]) -> bool:
        merged = self._merge_with_defaults(new_config)
        return self._save_config(merged)

    def update_section(self, section_name: str, section_data: Dict[str, Any]) -> bool:
        try:
            config = self._read_config()
            section = config.get(section_name)
            if not isinstance(section, dict):
                section = {}
            section.update(section_data)
            config[section_name] = section
            return self._save_config(config)
        except Exception as exc:
            if hasattr(current_app, "logger"):
                current_app.logger.error(
                    "Error updating %s plugin section %s: %s",
                    self.plugin_id,
                    section_name,
                    exc,
                )
            return False

    def get_setting(self, section: str, key: str, default: Any = None) -> Any:
        return self._read_config().get(section, {}).get(key, default)

    def set_setting(self, section: str, key: str, value: Any) -> bool:
        config = self._read_config()
        if section not in config or not isinstance(config.get(section), dict):
            config[section] = {}
        config[section][key] = value
        return self._save_config(config)

    def reset_to_defaults(self) -> bool:
        return self._save_config(copy.deepcopy(self.default_config))

    def get_nested(self, *keys: str, default: Any = None) -> Any:
        """Read a nested key path from the plugin data document."""
        node: Any = self._read_config()
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return copy.deepcopy(node)

    def set_nested(self, value: Any, *keys: str) -> bool:
        """Write a nested key path into the plugin data document."""
        if not keys:
            return False
        config = self._read_config()
        node: Dict[str, Any] = config
        for key in keys[:-1]:
            child = node.get(key)
            if not isinstance(child, dict):
                child = {}
                node[key] = child
            node = child
        node[keys[-1]] = copy.deepcopy(value)
        return self._save_config(config)
