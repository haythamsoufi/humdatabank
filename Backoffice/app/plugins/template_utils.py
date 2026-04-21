"""
Deterministic template utilities for plugins.
"""

from pathlib import Path
from flask import current_app, render_template


def render_plugin_template(plugin_id: str, template_name: str, **context) -> str:
    """
    Render a plugin template deterministically via the registered plugin template loader.

    Template naming contract:
        render_plugin_template("interactive_map", "field.html")
    resolves to:
        "plugins/interactive_map/field.html"
    """
    try:
        return render_template(f"plugins/{plugin_id}/{template_name}", **context)
    except Exception as e:
        current_app.logger.error(f"Error rendering plugin template plugins/{plugin_id}/{template_name}: {e}", exc_info=True)
        raise


def get_plugin_template_path(plugin_name: str, template_name: str) -> Path:
    """
    Get the full path to a plugin's template file.

    Args:
        plugin_name: Name of the plugin
        template_name: Name of the template file

    Returns:
        Path object pointing to the template file
    """
    # Deprecated: template resolution should be done via Jinja loader, not filesystem paths.
    plugin_dir_name = plugin_name
    plugins_base = Path(current_app.root_path).parent / 'plugins'
    return plugins_base / plugin_dir_name / 'templates' / template_name


def plugin_template_exists(plugin_name: str, template_name: str) -> bool:
    """
    Check if a template exists in a plugin's template directory.

    Args:
        plugin_name: Name of the plugin
        template_name: Name of the template file

    Returns:
        True if template exists, False otherwise
    """
    try:
        template_path = get_plugin_template_path(plugin_name, template_name)
        return template_path.exists()
    except Exception as e:
        current_app.logger.debug("get_plugin_template_path failed: %s", e)
        return False


def list_plugin_templates(plugin_name: str) -> list:
    """
    List all templates available in a plugin's template directory.

    Args:
        plugin_name: Name of the plugin

    Returns:
        List of template file names
    """
    try:
        plugins_base = Path(current_app.root_path).parent / 'plugins'
        template_dir = plugins_base / plugin_name / 'templates'

        if not template_dir.exists():
            return []

        return [f.name for f in template_dir.iterdir() if f.is_file() and f.suffix == '.html']
    except Exception as e:
        current_app.logger.error(f"Error listing plugin templates for {plugin_name}: {e}")
        return []
