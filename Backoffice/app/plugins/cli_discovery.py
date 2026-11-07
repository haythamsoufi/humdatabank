"""Register CLI commands that plugins ship in ``plugins/<id>/cli.py``.

Commands are discovered from the file system rather than from loaded plugin instances so they
exist in every ``flask`` invocation, including debug processes that skip plugin loading.
A plugin module exposes ``register_cli(app)``; a failing module is logged and skipped.
"""
import importlib
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

PLUGINS_ROOT = Path(__file__).resolve().parents[2] / "plugins"


def register_plugin_cli_commands(app, plugins_root: Path = PLUGINS_ROOT) -> List[str]:
    registered: List[str] = []
    if not plugins_root.is_dir():
        return registered
    for cli_file in sorted(plugins_root.glob("*/cli.py")):
        plugin_id = cli_file.parent.name
        if plugin_id.startswith((".", "_")):
            continue
        try:
            module = importlib.import_module(f"plugins.{plugin_id}.cli")
            register = getattr(module, "register_cli", None)
            if callable(register):
                register(app)
                registered.append(plugin_id)
        except Exception as exc:
            logger.warning("CLI commands of plugin %s not registered: %s", plugin_id, exc)
    return registered
