"""Build scoped import maps so ES module relative imports use cache-busted URLs.

When the entry script is loaded via static_url() (e.g. entry-form.js?v=561aa…),
relative imports like ``import './main.js'`` resolve without the query string.
That splits the browser cache and causes duplicate network fetches on CDN origins.

An import map scoped to each directory under ``js/forms/`` maps the absolute,
unversioned URL of every relatively-imported module to the same versioned URL
that static_url() emits. Keys must be absolute: relative keys ("./x.js") are
resolved against the HTML document URL by the browser, so they never match.
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

# Absolute ``/static/...js`` import specifiers. They resolve to the app origin with
# no ?v=, regardless of where the importer was loaded from, and are not covered by
# directory scopes (the referrer may be an inline module in the HTML document).
_ABSOLUTE_STATIC_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[\w\s{},*.$]+from\s+|)|"""
    r"""export\s+(?:\{[^}]*\}|\*|\w+)\s+from\s+|"""
    r"""import\s*\(\s*)['"]/static/([^'"]+\.js)['"]""",
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
    unversioned_url_for=None,
    extra_absolute_modules=(),
) -> dict:
    """Return ``{"scopes": {...}}`` for all relative imports under *tree_relative*.

    When *cdn_base* is empty (app-origin URLs) the result also carries a top-level
    ``"imports"`` map for absolute ``/static/...js`` specifiers found under the tree
    and for *extra_absolute_modules* (static-relative paths imported by inline
    module scripts in templates).
    """
    tree_path = static_root / tree_relative.replace("/", posixpath.sep)
    if not tree_path.is_dir():
        return {"scopes": {}}

    scopes: dict[str, dict[str, str]] = {}
    imports: dict[str, str] = {}

    def add_absolute(target_rel: str) -> None:
        if cdn_base or not unversioned_url_for:
            return
        if not (static_root / target_rel.replace("/", posixpath.sep)).is_file():
            return
        imports[unversioned_url_for(target_rel)] = versioned_url_for(target_rel)

    for target_rel in extra_absolute_modules:
        add_absolute(target_rel)

    for js_file in sorted(tree_path.rglob("*.js")):
        rel_to_static = js_file.relative_to(static_root).as_posix()
        dir_rel = posixpath.dirname(rel_to_static)
        scope_key = _scope_prefix(cdn_base, dir_rel, origin)

        try:
            content = js_file.read_text(encoding="utf-8")
        except OSError:
            continue

        for target_rel in _ABSOLUTE_STATIC_IMPORT_RE.findall(content):
            add_absolute(target_rel)

        for specifier in _RELATIVE_IMPORT_RE.findall(content):
            if not specifier.startswith("."):
                continue
            target_rel = posixpath.normpath(posixpath.join(dir_rel, specifier))
            if not target_rel.endswith(".js"):
                continue
            target_path = static_root / target_rel.replace("/", posixpath.sep)
            if not target_path.is_file():
                continue
            # The key MUST be the absolute, unversioned URL the browser resolves the
            # specifier to. Import-map keys such as "./main.js" are resolved against the
            # *document* URL (e.g. /forms/assignment/5), not the importing module, so a
            # relative key never matches and every nested import silently loads an
            # unversioned (immutable-cached) URL -> stale module / missing-export errors.
            key = unversioned_url_for(target_rel) if unversioned_url_for else specifier
            scopes.setdefault(scope_key, {})[key] = versioned_url_for(target_rel)

    result: dict = {"scopes": scopes}
    if imports:
        result["imports"] = imports
    return result


@lru_cache(maxsize=32)
def _cached_forms_import_map(
    static_root_str: str,
    tree_relative: str,
    cdn_base: str,
    origin: str,
    asset_version: str,
    tree_fingerprint: str,
    extra_absolute_modules: tuple = (),
) -> dict:
    static_root = Path(static_root_str)

    def versioned_url_for(rel_path: str) -> str:
        rel_path = rel_path.lstrip("/")
        token = file_content_token(static_root_str, rel_path)
        version = f"{asset_version}.{token}" if token else asset_version
        if cdn_base:
            return f"{cdn_base}/{rel_path}?v={version}"
        return f"{origin.rstrip('/')}/static/{rel_path}?v={version}"

    def unversioned_url_for(rel_path: str) -> str:
        rel_path = rel_path.lstrip("/")
        if cdn_base:
            return f"{cdn_base}/{rel_path}"
        return f"{origin.rstrip('/')}/static/{rel_path}"

    return build_scoped_import_map(
        static_root=static_root,
        tree_relative=tree_relative,
        cdn_base=cdn_base,
        origin=origin,
        versioned_url_for=versioned_url_for,
        unversioned_url_for=unversioned_url_for,
        extra_absolute_modules=extra_absolute_modules,
    )


# Loaded on every page by core/layout.html (js/chatbot/main.js and its imports,
# including ../lib/waf-json-body.js from chatbot/transport.js).
LAYOUT_IMPORT_TREES = ("js/chatbot", "js/lib")

# Pages that inject their own map (entry form, form builder) replace the layout map,
# so their maps must also include LAYOUT_IMPORT_TREES.
FORMS_IMPORT_TREES = ("js/forms",) + LAYOUT_IMPORT_TREES

# Modules imported by absolute /static/ path from inline <script type="module"> blocks
# in templates/forms/form_builder/form_builder.html (not discoverable by scanning JS).
# tests/unit/test_static_import_map.py keeps this list in sync with the template.
FORM_BUILDER_TEMPLATE_MODULES = (
    "js/components/translation-modal.js",
    "js/components/translation-matrix.js",
    "js/form_builder/modules/form-builder-init.js",
    "js/form_builder/modules/variables/template-variables.js",
    "js/form_builder/modules/variables/variable-formatting.js",
    "js/core/tooltip.js",
)

# The form builder entry (js/form_builder/main.js) imports relatively from these
# trees too (components/translation-*.js, lib/waf-json-body.js, ...), so each
# needs a scope or its modules load unversioned and stay cached as immutable.
FORM_BUILDER_IMPORT_TREES = (
    "js/form_builder",
    "js/components",
    "js/forms",
) + LAYOUT_IMPORT_TREES


def scoped_import_map(app, origin: str, trees, extra_absolute_modules=()) -> dict:
    """Import map covering every relative import found under each tree in *trees*.

    When a CDN is configured the map contains *two* sets of scopes:

    1. CDN-origin scopes (primary) — used when modules load from CDN as normal.
    2. App-origin scopes (fallback) — used when the module loader falls back to
       loading the entry script from ``/static/`` after CDN CORS failures.  Without
       these scopes the fallback module's relative imports (``./modules/foo.js``)
       would resolve without ``?v=`` cache-busting.  With them every sub-module
       still gets a versioned URL, whether the CDN is reachable or not.
    """
    cdn_base = (app.config.get("STATIC_CDN_URL") or "").strip().rstrip("/")
    asset_version = str(app.config.get("ASSET_VERSION") or "v1")
    static_root = _static_root(app).resolve()
    static_root_str = str(static_root)

    bases = [cdn_base]
    if cdn_base:
        # App-origin fallback scopes (cdn_base="" → /static/ paths).
        bases.append("")

    merged_scopes: dict[str, dict[str, str]] = {}
    merged_imports: dict[str, str] = {}
    extra = tuple(extra_absolute_modules)
    for tree in trees:
        tree_fingerprint = static_tree_fingerprint(static_root, tree)
        for base in bases:
            tree_map = _cached_forms_import_map(
                static_root_str,
                tree,
                base,
                origin,
                asset_version,
                tree_fingerprint,
                extra,
            )
            for scope_key, imports in tree_map.get("scopes", {}).items():
                merged_scopes.setdefault(scope_key, {}).update(imports)
            merged_imports.update(tree_map.get("imports", {}))
    result: dict = {"scopes": merged_scopes}
    if merged_imports:
        result["imports"] = merged_imports
    return result


def layout_import_map(app, origin: str) -> dict:
    """Import map for modules loaded by the base layout (chatbot) on every page."""
    return scoped_import_map(app, origin, LAYOUT_IMPORT_TREES)


def forms_module_import_map(app, origin: str) -> dict:
    """Import map for the entry-form ES module graph under ``js/forms/``."""
    return scoped_import_map(app, origin, FORMS_IMPORT_TREES)


def form_builder_import_map(app, origin: str) -> dict:
    """Import map for the form builder module graph (see FORM_BUILDER_IMPORT_TREES)."""
    return scoped_import_map(
        app,
        origin,
        FORM_BUILDER_IMPORT_TREES,
        FORM_BUILDER_TEMPLATE_MODULES,
    )


def clear_import_map_cache() -> None:
    from app.static_version import clear_static_version_cache
    _cached_forms_import_map.cache_clear()
    clear_static_version_cache()
