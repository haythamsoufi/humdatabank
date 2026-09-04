"""Cache-bust tokens for static_url() and the forms import map.

A deploy SHA alone is not enough: if ASSET_VERSION is pinned (Azure App
Setting) or a static-only upload keeps the same ?v=, browsers that already
stored ajax-save.js as immutable will keep the old module. Each URL therefore
embeds both the deploy token and a content hash of that file so a byte change
is always a new cache key.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path


def static_root_from_app(app) -> Path:
    if getattr(app, "static_folder", None):
        return Path(app.static_folder)
    return Path(getattr(app, "root_path", ".")) / "static"


def normalize_static_relative(filename: str) -> str:
    rel = (filename or "").replace("\\", "/").lstrip("/")
    if rel.startswith("static/"):
        rel = rel[len("static/") :]
    return rel


@lru_cache(maxsize=8192)
def file_content_token(static_root: str, relative: str) -> str:
    path = Path(static_root, *relative.split("/")) if relative else Path(static_root)
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(data).hexdigest()[:12]


def deploy_asset_version(app) -> str:
    return str((getattr(app, "config", {}) or {}).get("ASSET_VERSION") or "v1").strip() or "v1"


def asset_query_version(app, filename: str) -> str:
    """Return the ?v= token for *filename* (deploy version + content hash)."""
    deploy = deploy_asset_version(app)
    rel = normalize_static_relative(filename)
    token = file_content_token(str(static_root_from_app(app).resolve()), rel)
    return f"{deploy}.{token}" if token else deploy


def versioned_static_url(*, base_url: str, filename: str, version: str) -> str:
    filename = normalize_static_relative(filename)
    return f"{base_url.rstrip('/')}/{filename}?v={version}"


def static_tree_fingerprint(static_root: Path, tree_relative: str) -> str:
    """Invalidate import-map caches when any file under *tree_relative* changes."""
    tree = Path(static_root, *tree_relative.split("/")) if tree_relative else static_root
    if not tree.is_dir():
        return ""
    digest = hashlib.sha256()
    for path in sorted(tree.rglob("*.js")):
        try:
            stat = path.stat()
        except OSError:
            continue
        rel = path.relative_to(static_root).as_posix()
        digest.update(f"{rel}:{stat.st_size}:{stat.st_mtime_ns}\n".encode())
    return digest.hexdigest()[:16]


def clear_static_version_cache() -> None:
    file_content_token.cache_clear()
