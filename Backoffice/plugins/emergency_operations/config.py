# Backoffice/plugins/emergency_operations/config.py

from pathlib import Path

from app.plugins.db_config import DbPluginConfig


# Default configuration for Emergency Operations Plugin
DEFAULT_CONFIG = {
    "api": {
        "feed": "appeal_group",
        "base_url": "https://go-api.ifrc.org/api/appealgroupchild",
        "timeout": 60
    },
    "query_defaults": {
        "end_date_gt": "2022-12-31",
        "limit": 1000
    },
    "display_defaults": {
        "max_items": 10,
        "show_funded_amount": True,
        "show_requested_amount": True,
        "show_coverage": True,
        "show_closed_operations": True,
        "operation_types": ["Emergency Appeal", "DREF", "All"]
    },
    "caching": {
        "cache_duration": 3600
    },
    # Server-side persistent data cache (file-based).
    # When use_file_cache is True, forms are served from the local file; otherwise from live API.
    "data_cache": {
        "use_file_cache": True,  # False = always call live GO API
        "schedule": "monthly"    # "off" | "daily" | "weekly" | "monthly"
    }
}


class EmergencyOperationsConfig(DbPluginConfig):
    """Configuration manager for Emergency Operations plugin."""

    def __init__(self):
        super().__init__("emergency_operations", DEFAULT_CONFIG, plugin_root=Path(__file__).parent)

    def _normalize_api_section(self, api: dict) -> dict:
        from plugins.emergency_operations.appeal_group import effective_feed_id, url_for_feed

        normalized = dict(api or {})
        feed = effective_feed_id(normalized)
        normalized["feed"] = feed
        normalized["base_url"] = url_for_feed(feed)
        return normalized

    def get_all_config(self):
        config = super().get_all_config()
        api = config.get("api")
        if isinstance(api, dict):
            config["api"] = self._normalize_api_section(api)
        return config

    def update_config(self, new_config):
        if isinstance(new_config, dict) and isinstance(new_config.get("api"), dict):
            new_config = dict(new_config)
            new_config["api"] = self._normalize_api_section(new_config["api"])
        return super().update_config(new_config)

    def update_section(self, section_name, section_data):
        if section_name == "api" and isinstance(section_data, dict):
            current = self.get_section("api")
            if not isinstance(current, dict):
                current = {}
            current.update(section_data)
            section_data = self._normalize_api_section(current)
        return super().update_section(section_name, section_data)

    def get_api_config(self):
        """Get API configuration."""
        return self.get_all_config().get("api", {})

    def get_query_defaults(self):
        """Get query default configuration."""
        return self.get_section('query_defaults')

    def get_display_defaults(self):
        """Get display default configuration."""
        return self.get_section('display_defaults')

    def get_caching_config(self):
        """Get caching configuration."""
        return self.get_section('caching')

    def get_data_cache_config(self):
        """Get server-side persistent file-cache configuration."""
        return self.get_section('data_cache')


# Create a global instance that can be imported
plugin_config = EmergencyOperationsConfig()
