# Backoffice/plugins/interactive_map/config.py

"""
Configuration management for the Interactive Map Plugin.
This file handles plugin-level configuration including API keys and global settings.
"""

import os
from typing import Dict, Any, Optional
from flask import current_app
import json
from pathlib import Path

from app.plugins.base_config import BasePluginConfig


# Default plugin configuration
DEFAULT_PLUGIN_CONFIG = {
    "api_keys": {
        "google_maps": "",
        "mapbox": "",
        "openstreetmap": ""  # Usually not needed, but kept for consistency
    },
    "global_settings": {
        "default_map_provider": "mapbox",
        "default_zoom_level": 10,
        "max_markers_per_field": 10,
        "allow_marker_editing": True,
        "geocoding_service": "nominatim",
        "geocoding_api_key": "",
        "enable_caching": True,
        "cache_duration": 3600,  # 1 hour in seconds
        "max_file_size": 10485760,  # 10MB
        "allowed_file_types": [".png", ".jpg", ".jpeg", ".gif", ".svg"],
        "enable_logging": True,
        "log_level": "INFO"
    },
    "map_providers": {
        "openstreetmap": {
            "enabled": True,
            "requires_api_key": False,
            "base_url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            "attribution": "© OpenStreetMap contributors",
            "max_zoom": 19
        },
        "google_maps": {
            "enabled": False,
            "requires_api_key": True,
            "base_url": "https://maps.googleapis.com/maps/api/js",
            "attribution": "© Google Maps",
            "max_zoom": 21
        },
        "mapbox": {
            "enabled": True,
            "requires_api_key": True,
            "base_url": "https://api.mapbox.com/styles/v1/go-ifrc/ckrfe16ru4c8718phmckdfjh0/tiles/{z}/{x}/{y}",
            "attribution": "© Mapbox © OpenStreetMap",
            "max_zoom": 22
        }
    }
}

class InteractiveMapConfig(BasePluginConfig):
    """Manages configuration for the Interactive Map Plugin."""

    def __init__(self):
        super().__init__("interactive_map", DEFAULT_PLUGIN_CONFIG, plugin_root=Path(__file__).parent)

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a specific map provider."""
        return self.config.get("api_keys", {}).get(provider, "")

    def set_api_key(self, provider: str, api_key: str) -> bool:
        """Set API key for a specific map provider."""
        return self.set_setting("api_keys", provider, api_key)

    def get_provider_config(self, provider: str) -> Dict[str, Any]:
        """Get configuration for a specific map provider."""
        return self.config.get("map_providers", {}).get(provider, {})

    def is_provider_enabled(self, provider: str) -> bool:
        """Check if a map provider is enabled."""
        return self.get_provider_config(provider).get("enabled", False)

    def requires_api_key(self, provider: str) -> bool:
        """Check if a map provider requires an API key."""
        return self.get_provider_config(provider).get("requires_api_key", False)

    def get_global_setting(self, key: str) -> Any:
        """Get a global setting value."""
        return self.get_setting("global_settings", key)

    def set_global_setting(self, key: str, value: Any) -> bool:
        """Set a global setting value."""
        return self.set_setting("global_settings", key, value)

# Global instance
plugin_config = InteractiveMapConfig()
