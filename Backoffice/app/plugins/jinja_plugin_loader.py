"""
Deterministic Jinja2 template loader for plugins.

Contract:
- Plugins register `templates/` folders at load time (via PluginManager discovery).
- Templates are referenced as: "plugins/<plugin_id>/<template_name>".
- No "search these N paths" logic; template lookup is deterministic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Tuple

from jinja2 import BaseLoader, TemplateNotFound


class PluginTemplateLoader(BaseLoader):
    """
    Load templates for plugins via canonical names:
        plugins/<plugin_id>/<relpath>
    """

    def __init__(self, get_template_dir: Callable[[str], Optional[Path]]):
        super().__init__()
        self._get_template_dir = get_template_dir

    def get_source(self, environment, template: str) -> Tuple[str, str, Callable[[], bool]]:
        # Only handle our deterministic plugin namespace
        if not template.startswith("plugins/"):
            raise TemplateNotFound(template)

        parts = template.split("/", 2)
        if len(parts) < 3:
            raise TemplateNotFound(template)

        _, plugin_id, rel = parts
        if not plugin_id or not rel:
            raise TemplateNotFound(template)

        base_dir = self._get_template_dir(plugin_id)
        if not base_dir:
            raise TemplateNotFound(template)

        base_dir = Path(base_dir)
        filename = (base_dir / rel).resolve()

        # Prevent directory traversal: resolved template must remain within template root
        try:
            filename.relative_to(base_dir.resolve())
        except Exception as e:
            raise TemplateNotFound(template) from e

        if not filename.exists() or not filename.is_file():
            raise TemplateNotFound(template)

        mtime = filename.stat().st_mtime
        source = filename.read_text(encoding="utf-8")

        def uptodate() -> bool:
            try:
                return filename.exists() and filename.stat().st_mtime == mtime
            except OSError:
                return False

        return source, str(filename), uptodate
