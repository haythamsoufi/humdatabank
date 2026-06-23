"""Build scoped import maps so ES module relative imports use cache-busted URLs.

When the entry script is loaded via static_url() (e.g. entry-form.js?v=561aa…),
relative imports like ``import './main.js'`` resolve without the query string.
That splits the browser cache and causes duplicate network fetches on CDN origins.

An import map scoped to each directory under ``js/forms/`` maps every relative
specifier found in source to the same versioned URL that static_url() emits.
"""

from __future__ import annotations

import posixpath
import re
from functools import lru_cache
from pathlib import Path

# Static and dynamic relative imports / re-exports (./ and ../ specifiers).
_RELATIVE_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[\w\s{},*.$]+from\s+|)|"""
    r"""export\s+(?:\{[^}]*\}|\*|\w+)\s+from\s+|"""
    r"""import\s*\(\s*)['"]((?:\./|\.\./)[^'"]+)['"]""",
    re.MULTILINE,
)


def _static_root(app) -> Path:
    if app.static_folder:
        return Path(app.static_folder)
    return Path(app.root_path) / "static"


def _scope_prefix(cdn_base: str, dir_relative: str, origin: str) -> str:
    """Absolute URL prefix (trailing slash) used as an import-map scope key."""
    dir_relative = dir_relative.strip("/")
    if cdn_base:
        return f"{cdn_base}/{dir_relative}/" if dir_relative else f"{cdn_base}/"
    path = f"/static/{dir_relative}/" if dir_relative else "/static/"
    return f"{origin.rstrip('/')}{path}"


def build_scoped_import_map(
    *,
    static_root: Path,
    tree_relative: str,
    cdn_base: str,
    origin: str,
    versioned_url_for,
) -> dict:
    """Return ``{"scopes": {...}}`` for all relative imports under *tree_relative*."""
    tree_path = static_root / tree_relative.replace("/", posixpath.sep)
    if not tree_path.is_dir():
        return {"scopes": {}}

    scopes: dict[str, dict[str, str]] = {}

    for js_file in sorted(tree_path.rglob("*.js")):
        rel_to_static = js_file.relative_to(static_root).as_posix()
        dir_rel = posixpath.dirname(rel_to_static)
        scope_key = _scope_prefix(cdn_base, dir_rel, origin)

        try:
            content = js_file.read_text(encoding="utf-8")
        except OSError:
            continue

        for specifier in _RELATIVE_IMPORT_RE.findall(content):
            if not specifier.startswith("."):
                continue
            target_rel = posixpath.normpath(posixpath.join(dir_rel, specifier))
            if not target_rel.endswith(".js"):
                continue
            target_path = static_root / target_rel.replace("/", posixpath.sep)
            if not target_path.is_file():
                continue
            scopes.setdefault(scope_key, {})[specifier] = versioned_url_for(target_rel)

    return {"scopes": scopes}


@lru_cache(maxsize=8)
def _cached_forms_import_map(
    static_root_str: str,
    tree_relative: str,
    cdn_base: str,
    origin: str,
    asset_version: str,
) -> dict:
    static_root = Path(static_root_str)

    def versioned_url_for(rel_path: str) -> str:
        rel_path = rel_path.lstrip("/")
        if cdn_base:
            return f"{cdn_base}/{rel_path}?v={asset_version}"
        return f"{origin.rstrip('/')}/static/{rel_path}?v={asset_version}"

    return build_scoped_import_map(
        static_root=static_root,
        tree_relative=tree_relative,
        cdn_base=cdn_base,
        origin=origin,
        versioned_url_for=versioned_url_for,
    )


def forms_module_import_map(app, origin: str) -> dict:
    """Import map for the entry-form ES module graph under ``js/forms/``."""
    cdn_base = (app.config.get("STATIC_CDN_URL") or "").strip().rstrip("/")
    asset_version = str(app.config.get("ASSET_VERSION") or "v1")
    static_root = _static_root(app)
    return _cached_forms_import_map(
        str(static_root.resolve()),
        "js/forms",
        cdn_base,
        origin,
        asset_version,
    )


def clear_import_map_cache() -> None:
    _cached_forms_import_map.cache_clear()
