"""Unified file-storage abstraction for uploads.

Supports two providers selected via ``UPLOAD_STORAGE_PROVIDER``:

* **filesystem** (default) -- reads/writes under ``UPLOAD_FOLDER`` on the local disk.
* **azure_blob** -- reads/writes to an Azure Blob Storage container (``AZURE_STORAGE_CONTAINER``).

Every public method accepts a *category* (e.g. ``ADMIN_DOCUMENTS``) and a
*rel_path* (the relative path stored in the database).  The provider resolves
these to either a local filesystem path or a blob name transparently.
"""

from __future__ import annotations

import io
import logging
import mimetypes
import os
import re
import tempfile
from typing import Optional, Tuple, Union

from flask import current_app, send_file

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category constants -- map to subdirectories / blob prefixes
# ---------------------------------------------------------------------------
ADMIN_DOCUMENTS = "admin_documents"
RESOURCES = "resources"
SUBMISSIONS = "submissions"
# Entity-scoped submission/library files live directly under UPLOAD_FOLDER (no "submissions/" prefix).
# Use empty string so _local_abs / _blob_name omit the category segment.
ENTITY_REPO_ROOT = ""
SYSTEM = "system"
AI_DOCUMENTS = "ai_documents"
TEMP = "temp"

# Files larger than this (5 MB) are streamed in chunks from Azure Blob
# rather than buffered entirely in memory.
_AZURE_STREAM_THRESHOLD = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _provider() -> str:
    return current_app.config.get("UPLOAD_STORAGE_PROVIDER") or "filesystem"


def _upload_base() -> str:
    return os.path.abspath(current_app.config.get("UPLOAD_FOLDER", "uploads"))


def _normalize_rel(rel_path: str) -> str:
    """Normalize a relative path to forward-slash form, stripping leading slashes."""
    rel = (rel_path or "").replace("\\", "/").strip("/")
    return rel


def _local_abs(category: str, rel_path: str) -> str:
    """Build absolute local path: UPLOAD_FOLDER / category / rel_path.

    When *category* is empty (``ENTITY_REPO_ROOT``), files resolve under ``UPLOAD_FOLDER`` only.
    """
    base = _upload_base()
    if category:
        base = os.path.join(base, category)
    safe_rel = _normalize_rel(rel_path)
    candidate = os.path.abspath(os.path.join(base, *[p for p in safe_rel.split("/") if p]))
    base_real = os.path.realpath(base)
    cand_real = os.path.realpath(candidate)
    if not cand_real.startswith(base_real + os.sep) and cand_real != base_real:
        raise PermissionError("Resolved path escapes base directory")
    return cand_real


def _blob_name(category: str, rel_path: str) -> str:
    """Build the blob name: category/rel_path (forward-slash), or *rel_path* when category is empty."""
    safe_rel = _normalize_rel(rel_path)
    if category:
        return f"{category}/{safe_rel}"
    return safe_rel


def _get_container_client():
    """Return an Azure ``ContainerClient`` for the uploads container."""
    conn = current_app.config.get("AZURE_STORAGE_CONNECTION_STRING")
    container_name = current_app.config.get("AZURE_STORAGE_CONTAINER") or "uploads"
    if not conn:
        raise RuntimeError(
            "AZURE_STORAGE_CONNECTION_STRING must be set when UPLOAD_STORAGE_PROVIDER=azure_blob"
        )
    try:
        from azure.storage.blob import BlobServiceClient  # type: ignore
        svc = BlobServiceClient.from_connection_string(conn)
        return svc.get_container_client(container_name)
    except Exception as e:
        raise RuntimeError(f"Failed to initialise Azure Blob client: {e}") from e


def _guess_mimetype(filename: str) -> str:
    mt, _ = mimetypes.guess_type(filename or "")
    return mt or "application/octet-stream"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upload(category: str, rel_path: str, data: Union[bytes, "FileStorage"]) -> str:  # noqa: F821
    """Save *data* (bytes or Werkzeug ``FileStorage``) and return the normalised rel_path.

    * **filesystem** -- writes to ``UPLOAD_FOLDER/category/rel_path``
    * **azure_blob** -- uploads blob ``category/rel_path`` into the container
    """
    safe_rel = _normalize_rel(rel_path)
    if not safe_rel:
        raise ValueError("rel_path must not be empty")

    if _provider() == "azure_blob":
        name = _blob_name(category, safe_rel)
        container = _get_container_client()
        if isinstance(data, bytes):
            blob_data = data
        else:
            pos = data.stream.tell()
            blob_data = data.stream.read()
            data.stream.seek(pos)
        container.upload_blob(name=name, data=blob_data, overwrite=True)
        logger.debug("Uploaded blob %s (%d bytes)", name, len(blob_data))
    else:
        abs_path = _local_abs(category, safe_rel)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        if isinstance(data, bytes):
            with open(abs_path, "wb") as f:
                f.write(data)
        else:
            data.save(abs_path)
        logger.debug("Saved local file %s", abs_path)

    return safe_rel


def download(category: str, rel_path: str) -> bytes:
    """Return file contents as bytes."""
    safe_rel = _normalize_rel(rel_path)
    if _provider() == "azure_blob":
        name = _blob_name(category, safe_rel)
        container = _get_container_client()
        blob = container.get_blob_client(name)
        return blob.download_blob().readall()
    else:
        abs_path = _local_abs(category, safe_rel)
        with open(abs_path, "rb") as f:
            return f.read()


def stream_response(
    category: str,
    rel_path: str,
    filename: str,
    mimetype: Optional[str] = None,
    as_attachment: bool = True,
):
    """Return a Flask response that streams the file to the client.

    This replaces direct ``send_file`` / ``send_from_directory`` calls.
    For Azure Blob, files larger than ``_AZURE_STREAM_THRESHOLD`` are
    streamed in chunks to avoid buffering the entire blob in memory.
    """
    safe_rel = _normalize_rel(rel_path)
    effective_mime = mimetype or _guess_mimetype(filename)

    if _provider() == "azure_blob":
        name = _blob_name(category, safe_rel)
        container = _get_container_client()
        blob = container.get_blob_client(name)
        props = blob.get_blob_properties()
        blob_size = props.size or 0

        if blob_size > _AZURE_STREAM_THRESHOLD:
            from flask import Response as FlaskResponse
            from werkzeug.http import dump_header

            def _generate():
                stream = blob.download_blob()
                for chunk in stream.chunks():
                    yield chunk

            headers = {
                "Content-Type": effective_mime,
                "Content-Length": str(blob_size),
            }
            if as_attachment:
                headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{dump_header(filename)}"
            else:
                headers["Content-Disposition"] = f"inline; filename*=UTF-8''{dump_header(filename)}"
            return FlaskResponse(_generate(), headers=headers)

        content = blob.download_blob().readall()
        buf = io.BytesIO(content)
        return send_file(
            buf,
            mimetype=effective_mime,
            as_attachment=as_attachment,
            download_name=filename,
        )
    else:
        abs_path = _local_abs(category, safe_rel)
        return send_file(
            abs_path,
            mimetype=effective_mime,
            as_attachment=as_attachment,
            download_name=filename,
        )


def delete(category: str, rel_path: str) -> bool:
    """Delete a file.  Returns ``True`` if the file was removed."""
    safe_rel = _normalize_rel(rel_path)
    if not safe_rel:
        return False

    if _provider() == "azure_blob":
        try:
            name = _blob_name(category, safe_rel)
            container = _get_container_client()
            blob = container.get_blob_client(name)
            blob.delete_blob()
            logger.debug("Deleted blob %s", name)
            return True
        except Exception as e:
            logger.debug("Azure blob delete failed for %s: %s", safe_rel, e)
            return False
    else:
        try:
            abs_path = _local_abs(category, safe_rel)
            if os.path.exists(abs_path):
                os.remove(abs_path)
                logger.debug("Deleted local file %s", abs_path)
                return True
            return False
        except Exception as e:
            logger.debug("Local file delete failed for %s: %s", safe_rel, e)
            return False


def exists(category: str, rel_path: str) -> bool:
    """Check whether a file exists."""
    safe_rel = _normalize_rel(rel_path)
    if not safe_rel:
        return False

    if _provider() == "azure_blob":
        try:
            name = _blob_name(category, safe_rel)
            container = _get_container_client()
            blob = container.get_blob_client(name)
            blob.get_blob_properties()
            return True
        except Exception:
            return False
    else:
        try:
            abs_path = _local_abs(category, safe_rel)
            return os.path.exists(abs_path)
        except (PermissionError, ValueError):
            return False


def get_absolute_path(category: str, rel_path: str) -> str:
    """Return a local filesystem path to the file.

    * **filesystem** -- returns the real path directly.
    * **azure_blob** -- downloads the blob to a temp file and returns that path.
      The caller is responsible for cleaning up the temp file when done.
    """
    safe_rel = _normalize_rel(rel_path)
    if _provider() == "azure_blob":
        content = download(category, safe_rel)
        _, ext = os.path.splitext(safe_rel)
        fd, tmp_path = tempfile.mkstemp(suffix=ext)
        try:
            os.write(fd, content)
        finally:
            os.close(fd)
        return tmp_path
    else:
        return _local_abs(category, safe_rel)


def get_size(category: str, rel_path: str) -> int:
    """Return the file size in bytes, or -1 if the file cannot be found."""
    safe_rel = _normalize_rel(rel_path)
    if _provider() == "azure_blob":
        try:
            name = _blob_name(category, safe_rel)
            container = _get_container_client()
            blob = container.get_blob_client(name)
            props = blob.get_blob_properties()
            return props.size
        except Exception:
            return -1
    else:
        try:
            abs_path = _local_abs(category, safe_rel)
            return os.path.getsize(abs_path)
        except (OSError, PermissionError):
            return -1


def archive(category: str, rel_path: str, archive_rel_path: str) -> str:
    """Copy a file to an archive path within the same category.

    Downloads the existing file and re-uploads it under *archive_rel_path*.
    Returns the normalised archive relative path.  The original file is **not**
    deleted -- the caller decides whether to keep or remove it.
    """
    data = download(category, rel_path)
    return upload(category, archive_rel_path, data)


_ENTITY_TYPE_PATH_SEGMENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def normalize_standalone_entity_type_slug(entity_type: str | None) -> str:
    """Normalise entity type for use in storage paths (``{slug}/{id}/…``)."""
    t = (entity_type or "").strip().lower().replace("-", "_")
    if not _ENTITY_TYPE_PATH_SEGMENT_RE.fullmatch(t):
        raise ValueError("Invalid linked entity type")
    return t


def _is_entity_repo_scoped_relative_path(rel: str) -> bool:
    """True for ``{entity_type}/{numeric_id}/…`` (entity repo / submission document layout).

    *entity_type* must be a value of :class:`app.models.enums.EntityType`.
    """
    from app.models.enums import EntityType

    rel = (rel or "").replace("\\", "/").strip()
    if not rel:
        return False
    parts = rel.split("/")
    if len(parts) < 2 or not parts[1].isdigit():
        return False
    seg0 = parts[0]
    if not _ENTITY_TYPE_PATH_SEGMENT_RE.fullmatch(seg0):
        return False
    valid = {e.value for e in EntityType}
    return seg0 in valid


def standalone_entity_file_rel_path(
    entity_type_slug: str, entity_id: int, folder_uuid: str, filename: str
) -> str:
    """Relative path at upload root for a standalone library file (``ENTITY_REPO_ROOT``)."""
    et = normalize_standalone_entity_type_slug(entity_type_slug)
    return f"{et}/{int(entity_id)}/{folder_uuid}/{filename}"


def submitted_document_rel_storage_category(rel_path: str | None) -> str:
    """Resolve storage category from a ``SubmittedDocument`` relative path.

    * New layout: ``{entity_type}/{entity_id}/…`` at ``UPLOAD_FOLDER`` root (``ENTITY_REPO_ROOT``).
    * Legacy: same DB path but file was stored under ``UPLOAD_FOLDER/submissions/…`` (``SUBMISSIONS``),
      or assignment paths containing ``…/assignments/{aes}/…`` (always ``SUBMISSIONS``).
    * Anything else defaults to ``ADMIN_DOCUMENTS``.
    """
    rel = (rel_path or "").replace("\\", "/").strip()
    if not rel:
        return ADMIN_DOCUMENTS
    parts = rel.split("/")
    # Legacy assignment-relative prefix in the stored path
    if len(parts) >= 3 and parts[2] == "assignments":
        return SUBMISSIONS
    if _is_entity_repo_scoped_relative_path(rel):
        # Prefer legacy tree when the object still lives under submissions/
        if exists(SUBMISSIONS, rel):
            return SUBMISSIONS
        return ENTITY_REPO_ROOT
    return ADMIN_DOCUMENTS


def _is_effectively_absolute_stored_path(sp: str) -> bool:
    """True for normal OS absolute paths and for POSIX /foo/... (Linux deploy paths
    on Windows return False for :func:`os.path.isabs`, so we need this for Azure-style paths)."""
    if not sp or not (sp.strip()):
        return False
    if os.path.isabs(sp):
        return True
    s = (sp or "").replace("\\", "/")
    if s.startswith("/") and not s.startswith("//"):
        return True
    return False


def category_rel_for_submitted_storage_path(
    storage_path: str,
) -> Optional[Tuple[str, str]]:
    """Map a ``SubmittedDocument.storage_path`` (relative or legacy absolute) to
    ``(category, rel)`` for :func:`exists`, :func:`get_absolute_path`, and
    :func:`stream_response`. Returns ``None`` when *storage_path* is a non-empty
    absolute local path that exists on disk (callers may ``send_file`` it directly).
    """
    from app.utils.file_paths import get_upload_base_path, normalize_stored_relative_path

    sp = (storage_path or "").strip()
    if not sp:
        return None
    rel_effective: Optional[str] = None
    if _is_effectively_absolute_stored_path(sp):
        if os.path.exists(sp):
            return None
        # Prefer stripping the configured upload base (works when DB path matches this host).
        try:
            base = os.path.normpath(get_upload_base_path())
            b_s = base.replace("\\", "/")
            a_s = sp.replace("\\", "/")
            if a_s.lower().startswith(b_s.lower() + "/") or a_s.lower() == b_s.lower():
                prefix = b_s if b_s.endswith("/") else b_s + "/"
                rel_effective = a_s[len(prefix) :].lstrip("/") if a_s.lower() != b_s.lower() else ""
        except (ValueError, OSError) as e:
            logger.debug("submitted path strip from upload base: %s", e)
        if not rel_effective:
            # Linux deploy path on another machine, or /home/site/.../uploads/... in DB: take after /uploads/
            spu = sp.replace("\\", "/")
            u = "/uploads/"
            ix = spu.lower().rfind(u)
            if ix != -1:
                rel_effective = spu[ix + len(u) :].lstrip("/")
        if not rel_effective:
            return None
    else:
        rel_effective = _normalize_rel(sp)

    cat = submitted_document_rel_storage_category(rel_effective)
    if cat not in (SUBMISSIONS, ENTITY_REPO_ROOT):
        rel_key = normalize_stored_relative_path(rel_effective, root_folder="admin_documents")
        out_cat = ADMIN_DOCUMENTS
    else:
        rel_key = _normalize_rel(rel_effective)
        out_cat = cat
    return (out_cat, rel_key)


def submitted_source_exists(storage_path: str) -> bool:
    """Return whether the file exists in the active storage provider (filesystem or Azure)."""
    sp = (storage_path or "").strip()
    if not sp:
        return False
    if _is_effectively_absolute_stored_path(sp) and os.path.exists(sp):
        return True
    pair = category_rel_for_submitted_storage_path(sp)
    if not pair:
        return False
    cat, rel_key = pair
    return exists(cat, rel_key)


def local_path_for_submitted_document_processing(
    storage_path: str,
) -> Tuple[Optional[str], bool]:
    """Resolve a submitted-document path to a local path for the AI pipeline.

    For Azure Blob, returns a **temporary file**; the second return value is
    ``True`` when the caller should delete *local_path* after processing.
    For filesystem, returns the real path and ``False``.
    """
    sp = (storage_path or "").strip()
    if not sp:
        return None, False
    if _is_effectively_absolute_stored_path(sp) and os.path.exists(sp):
        return sp, False
    pair = category_rel_for_submitted_storage_path(sp)
    if not pair:
        return None, False
    cat, rel_key = pair
    if not exists(cat, rel_key):
        return None, False
    return get_absolute_path(cat, rel_key), is_azure()


def ai_aidoc_storage_path_for_submitted(
    original_storage_path: str,
) -> str:
    """Return the ``AIDocument.storage_path`` value: canonical forward-slash
    relative key when the DB had a legacy absolute path under *uploads*."""
    sp = (original_storage_path or "").strip()
    if not sp:
        return sp
    if not _is_effectively_absolute_stored_path(sp):
        return sp.replace("\\", "/")
    if os.path.exists(sp):
        return sp.replace("\\", "/")
    pair = category_rel_for_submitted_storage_path(sp)
    if not pair:
        return sp.replace("\\", "/")
    return pair[1]


def is_azure() -> bool:
    """Return ``True`` when the active provider is Azure Blob Storage."""
    return _provider() == "azure_blob"
