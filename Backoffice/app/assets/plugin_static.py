"""Versioning, URLs and cache headers for static files that plugins serve themselves.

Core assets get their ``?v=`` token from ``static_url()`` and their headers from
``static_serving``. A plugin that mounts its own ``/<name>/static/<path>`` route
must give the same guarantees, otherwise a changed script can sit in a browser
for a year behind an unchanged URL. Plugins call these helpers instead of
re-implementing the rules:

    from app.assets.plugin_static import plugin_static_url, send_plugin_static

    PLUGIN_STATIC = _PLUGIN_DIR / "static"

    def my_static_url(filename):
        return plugin_static_url("my_plugin.static_file", PLUGIN_STATIC, filename)

    @bp.route("/my-plugin/static/<path:filename>")
    def static_file(filename):
        return send_plugin_static(PLUGIN_STATIC, filename)

Keep the ``/<segment>/static/`` shape in the route: the service worker treats
any same-origin ``…/static/….js|css`` request as a code asset that must always
track the server's bytes (see ``respondStaticAsset`` in ``js/sw.js``).

The token is ``<deploy ASSET_VERSION>.<content hash>``, identical to core
``static_url()``. A byte change is therefore always a new URL, regardless of
file timestamps (zip deploys, timestamp-preserving copies).
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from flask import Response, current_app, request, send_from_directory, url_for

from app.assets.static_version import (
    deploy_asset_version,
    file_content_token,
    normalize_static_relative,
)

PathLike = Union[str, Path]

_IMMUTABLE = "max-age=31536000, {scope}, immutable"
_REVALIDATE = "max-age=0, {scope}, must-revalidate"
_ONE_HOUR = "max-age=3600, {scope}, must-revalidate"
_NO_STORE = "no-cache, no-store, must-revalidate"

_CODE_SUFFIXES = (".js", ".mjs", ".css")


def plugin_asset_version(static_dir: PathLike, filename: str) -> str:
    """``?v=`` token for *filename* under *static_dir* (deploy version + content hash)."""
    rel = normalize_static_relative(filename)
    try:
        deploy = deploy_asset_version(current_app)
    except RuntimeError:  # no application context (scripts)
        deploy = "v1"
    token = file_content_token(str(Path(static_dir)), rel) if rel else ""
    return f"{deploy}.{token}" if token else deploy


def plugin_static_url(endpoint: str, static_dir: PathLike, filename: str) -> str:
    """URL for a plugin static file, versioned by content.

    *endpoint* is the plugin's static route (it must take a ``filename`` argument).
    """
    return url_for(endpoint, filename=filename, v=plugin_asset_version(static_dir, filename))


def apply_plugin_static_cache(response: Response, *, private: bool = False) -> Response:
    """Same cache policy as core ``/static/``.

    * versioned (``?v=``)      -> one year, immutable
    * unversioned JS/CSS       -> revalidate on every load
    * other unversioned files  -> one hour
    * DEBUG and unversioned    -> no-store, so direct hits show edits

    ``private`` marks login-gated files so shared caches never keep them.
    Non-200 responses (304, errors) are left as the file server produced them.
    """
    response._skip_cache_override = True
    if response.status_code != 200:
        return response

    scope = "private" if private else "public"
    versioned = bool(request.args.get("v"))
    path = (request.path or "").lower()

    for header in ("Cache-Control", "Pragma", "Expires"):
        response.headers.remove(header)

    if current_app.config.get("DEBUG", False) and not versioned:
        response.headers["Cache-Control"] = _NO_STORE
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    elif versioned:
        response.headers["Cache-Control"] = _IMMUTABLE.format(scope=scope)
    elif path.endswith(_CODE_SUFFIXES):
        response.headers["Cache-Control"] = _REVALIDATE.format(scope=scope)
    else:
        response.headers["Cache-Control"] = _ONE_HOUR.format(scope=scope)
    response.headers["Vary"] = "Accept-Encoding"
    return response


def send_plugin_static(static_dir: PathLike, filename: str, *, private: bool = False) -> Response:
    """Serve *filename* from *static_dir* with the shared cache policy.

    ``send_from_directory`` rejects paths that escape *static_dir* (404).
    Authorisation stays with the caller's route decorators.
    """
    response = send_from_directory(str(Path(static_dir)), filename)
    return apply_plugin_static_cache(response, private=private)
