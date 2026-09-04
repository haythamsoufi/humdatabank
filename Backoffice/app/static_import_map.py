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

from app.static_version import file_content_token, static_tree_fingerprint

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
    tree_fingerprint: str,
) -> dict:
    static_root = Path(static_root_str)

    def versioned_url_for(rel_path: str) -> str:
        rel_path = rel_path.lstrip("/")
        token = file_content_token(static_root_str, rel_path)
        version = f"{asset_version}.{token}" if token else asset_version
        if cdn_base:
            return f"{cdn_base}/{rel_path}?v={version}"
        return f"{origin.rstrip('/')}/static/{rel_path}?v={version}"

    return build_scoped_import_map(
        static_root=static_root,
        tree_relative=tree_relative,
        cdn_base=cdn_base,
        origin=origin,
        versioned_url_for=versioned_url_for,
    )


def forms_module_import_map(app, origin: str) -> dict:
    """Import map for the entry-form ES module graph under ``js/forms/``.

    When a CDN is configured the map contains *two* sets of scopes:

    1. CDN-origin scopes (primary) — used when modules load from CDN as normal.
    2. App-origin scopes (fallback) — used when the module loader falls back to
       loading entry-form.js from ``/static/`` after CDN CORS failures.  Without
       these scopes the fallback module's relative imports (``./modules/foo.js``)
       would resolve without ``?v=`` cache-busting.  With them every sub-module
       still gets a versioned URL, whether the CDN is reachable or not.
    """
    cdn_base = (app.config.get("STATIC_CDN_URL") or "").strip().rstrip("/")
    asset_version = str(app.config.get("ASSET_VERSION") or "v1")
    static_root = _static_root(app).resolve()
    static_root_str = str(static_root)
    tree_fingerprint = static_tree_fingerprint(static_root, "js/forms")

    cdn_map = _cached_forms_import_map(
        static_root_str,
        "js/forms",
        cdn_base,
        origin,
        asset_version,
        tree_fingerprint,
    )

    if not cdn_base:
        return cdn_map

    # Build app-origin scopes (cdn_base="" → /static/ paths) so the CDN-fallback
    # loader can resolve relative imports to versioned app-origin URLs.
    app_map = _cached_forms_import_map(
        static_root_str,
        "js/forms",
        "",
        origin,
        asset_version,
        tree_fingerprint,
    )
    merged_scopes = {**cdn_map.get("scopes", {}), **app_map.get("scopes", {})}
    return {"scopes": merged_scopes}


def clear_import_map_cache() -> None:
    from app.static_version import clear_static_version_cache
    _cached_forms_import_map.cache_clear()
    clear_static_version_cache()
