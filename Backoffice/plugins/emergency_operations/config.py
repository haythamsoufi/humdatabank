# Backoffice/plugins/emergency_operations/config.py

from pathlib import Path

from app.plugins.base_config import BasePluginConfig


# Default configuration for Emergency Operations Plugin
DEFAULT_CONFIG = {
    "api": {
        "base_url": "https://goadmin.ifrc.org/api/v2/appeal/",
        "timeout": 10
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


class EmergencyOperationsConfig(BasePluginConfig):
    """Configuration manager for Emergency Operations plugin."""

    def __init__(self):
        super().__init__("emergency_operations", DEFAULT_CONFIG, plugin_root=Path(__file__).parent)

    def get_api_config(self):
        """Get API configuration."""
        return self.get_section('api')

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
