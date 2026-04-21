# Backoffice/app/plugins/base_config.py

import json
from pathlib import Path
from typing import Dict, Any, Optional

from flask import current_app


class BasePluginConfig:
    """Base class for plugin configuration management."""

    def __init__(
        self,
        plugin_id: str,
        default_config: Dict[str, Any] = None,
        plugin_root: Optional[Path] = None,
    ):
        # Canonical identity (must match folder name)
        self.plugin_id = plugin_id
        self.plugin_root = Path(plugin_root) if plugin_root else None
        self.default_config = default_config or {}
        self.config_file = self._get_config_file_path()
        self.config = self._load_config()

    def _get_config_file_path(self) -> Path:
        """Get the path to the plugin configuration file."""
        # Preferred: plugin passes its root folder explicitly (no guessing)
        if self.plugin_root:
            return self.plugin_root / "plugin_config.json"

        # Fallback: look for plugin folder by canonical plugin_id in standard locations
        possible_paths = [
            # Backoffice/plugins/<plugin_id>
            Path(__file__).parent.parent.parent.parent / "plugins" / self.plugin_id,
            # Backoffice/app/plugins/..../plugins/<plugin_id> (rare)
            Path(__file__).parent.parent.parent / "plugins" / self.plugin_id,
        ]
        for path in possible_paths:
            if path.exists():
                return path / "plugin_config.json"

        # Last resort: keep config next to this module (better than guessing display names)
        return Path(__file__).parent / "plugin_config.json"

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default if not exists."""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    # Merge with defaults to ensure all required keys exist
                    return self._merge_with_defaults(config)
            else:
                # Create default configuration file
                self._save_config(self.default_config)
                return self.default_config.copy()
        except Exception as e:
            if hasattr(current_app, 'logger'):
                current_app.logger.error(f"Error loading {self.plugin_id} config: {e}")
            return self.default_config.copy()

    def _merge_with_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge loaded config with defaults to ensure all keys exist."""
        merged = self.default_config.copy()

        def deep_merge(target: Dict[str, Any], source: Dict[str, Any]):
            for key, value in source.items():
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    deep_merge(target[key], value)
                else:
                    target[key] = value

        deep_merge(merged, config)
        return merged

    def _save_config(self, config: Dict[str, Any]) -> bool:
        """Save configuration to file."""
        try:
            # Ensure directory exists
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            # Update in-memory config
            self.config = config.copy()

            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)

            if hasattr(current_app, 'logger'):
                current_app.logger.info(f"Successfully saved {self.plugin_id} config to {self.config_file}")
            return True
        except Exception as e:
            if hasattr(current_app, 'logger'):
                current_app.logger.error(f"Error saving {self.plugin_id} config to {self.config_file}: {e}", exc_info=True)
            return False

    def get_all_config(self) -> Dict[str, Any]:
        """Get the complete configuration."""
        return self.config.copy()

    def get_section(self, section_name: str) -> Dict[str, Any]:
        """Get a specific configuration section."""
        return self.config.get(section_name, {})

    def update_config(self, new_config: Dict[str, Any]) -> bool:
        """Update the configuration with new values."""
        self.config = self._merge_with_defaults(new_config)
        return self._save_config(self.config)

    def update_section(self, section_name: str, section_data: Dict[str, Any]) -> bool:
        """Update a specific configuration section."""
        try:
            if section_name not in self.config:
                self.config[section_name] = {}

            self.config[section_name].update(section_data)
            return self._save_config(self.config)
        except Exception as e:
            if hasattr(current_app, 'logger'):
                current_app.logger.error(f"Error updating {self.plugin_id} config section {section_name}: {e}")
            return False

    def get_setting(self, section: str, key: str, default: Any = None) -> Any:
        """Get a specific setting value."""
        return self.config.get(section, {}).get(key, default)

    def set_setting(self, section: str, key: str, value: Any) -> bool:
        """Set a specific setting value."""
        if section not in self.config:
            self.config[section] = {}

        self.config[section][key] = value
        return self._save_config(self.config)

    def reset_to_defaults(self) -> bool:
        """Reset configuration to default values."""
        self.config = self.default_config.copy()
        return self._save_config(self.config)
