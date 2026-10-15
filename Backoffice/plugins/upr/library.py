"""Durable UPR visuals for the Generate table.

Bulk export still builds a one-off ZIP for the run. Each successful dashboard
is also stored under ``library/{assignment}/{format}/{lang}/{aes_id}/`` so the
table can show what is ready and offer a download after the run ZIP expires.
"""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Any

from werkzeug.exceptions import NotFound

from app.services.platform import storage_service
from app.utils.datetime_helpers import utcnow
from plugins.upr.bulk import normalize_export_format
from plugins.upr.catalog import DASHBOARD_BY_ID
from plugins.upr.errors import UprError
from plugins.upr.i18n import parse_export_language
from plugins.upr.service import STORAGE_CATEGORY

logger = logging.getLogger(__name__)

_FORMAT_EXT = {"png": "png", "pdf": "pdf", "idml": "zip"}
_FORMAT_MIME = {"png": "image/png", "pdf": "application/pdf", "idml": "application/zip"}


def library_root(assigned_form_id: int, export_format: str, lang: str) -> str:
    fmt = normalize_export_format(export_format)
    language = parse_export_language(lang)
    return f"library/{int(assigned_form_id)}/{fmt}/{language}"


def _dashboard_id(value: str) -> str:
    did = str(value or "").strip()
    if did not in DASHBOARD_BY_ID:
        raise UprError("Unknown dashboard.")
    return did


def _extension(export_format: str) -> str:
    return _FORMAT_EXT[normalize_export_format(export_format)]


def _download_name(name: str, dashboard_id: str, ext: str) -> str:
    base = Path(str(name or "")).name.replace("\r", "").replace("\n", "").replace('"', "").strip()
    if not base or base in {".", ".."}:
        return f"{dashboard_id}.{ext}"
    return base


def _index_key(root: str) -> str:
    return f"{root}/index.json"


_ENTITY_ID = re.compile(r"^(?:\d+|bundle-[a-z0-9-]+)$")


def _entity_segment(value: str) -> str:
    text = str(value or "").strip()
    if text.isdigit():
        text = str(int(text))
    if not _ENTITY_ID.match(text):
        raise UprError("Unknown stored visual.")
    return text


def _item_key(root: str, entity_id: str, dashboard_id: str, ext: str) -> str:
    return f"{root}/{_entity_segment(entity_id)}/{dashboard_id}.{ext}"


def _package_key(root: str, entity_id: str) -> str:
    return f"{root}/{_entity_segment(entity_id)}/package.zip"


def _is_library_entity(value: str) -> bool:
    text = str(value or "").strip()
    if text.isdigit():
        return True
    return bool(_ENTITY_ID.match(text))


def _empty_index() -> dict[str, Any]:
    return {"version": 1, "countries": {}}


def _read_index(root: str) -> dict[str, Any]:
    key = _index_key(root)
    if not storage_service.exists(STORAGE_CATEGORY, key):
        return _empty_index()
    try:
        raw = storage_service.download(STORAGE_CATEGORY, key)
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        logger.warning("UPR library index unreadable: %s", key, exc_info=True)
        return _empty_index()
    if not isinstance(data, dict):
        return _empty_index()
    countries = data.get("countries")
    if not isinstance(countries, dict):
        countries = {}
    return {"version": 1, "countries": countries}


def _write_index(root: str, index: dict[str, Any]) -> None:
    payload = json.dumps(index, separators=(",", ":")).encode("utf-8")
    storage_service.upload(STORAGE_CATEGORY, _index_key(root), payload)


def _unique_arcname(used: set[str], filename: str, dashboard_id: str) -> str:
    name = filename
    if name not in used:
        used.add(name)
        return name
    prefixed = f"{dashboard_id}_{name}"
    used.add(prefixed)
    return prefixed


def store_rendered_country(
    *,
    assigned_form_id: int,
    export_format: str,
    lang: str,
    aes_id: int,
    files: list[tuple[str, Path, str]],
    package_filename: str,
    library_id: str | None = None,
) -> None:
    """Save rendered dashboards and rebuild that country's package zip.

    Dashboards that failed this run stay as they were. An empty *files* list
    does not change the library.
    """
    if not files:
        return
    fmt = normalize_export_format(export_format)
    ext = _extension(fmt)
    root = library_root(assigned_form_id, fmt, lang)
    prepared: list[tuple[str, Path, str]] = []
    for dashboard_id, path, download_name in files:
        did = _dashboard_id(dashboard_id)
        prepared.append((did, Path(path), _download_name(download_name, did, ext)))

    entity = _entity_segment(library_id or str(int(aes_id)))
    when = utcnow().replace(microsecond=0).isoformat()
    fresh: dict[str, bytes] = {}
    index = _read_index(root)
    countries = index["countries"]
    entry = countries.get(entity)
    if not isinstance(entry, dict):
        entry = {}
    dashboards = entry.get("dashboards")
    if not isinstance(dashboards, dict):
        dashboards = {}

    for did, path, filename in prepared:
        data = path.read_bytes()
        storage_service.upload(STORAGE_CATEGORY, _item_key(root, entity, did, ext), data)
        dashboards[did] = {"filename": filename, "generated_at": when}
        fresh[did] = data

    used: set[str] = set()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for did, meta in dashboards.items():
            if did not in DASHBOARD_BY_ID or not isinstance(meta, dict):
                continue
            filename = _download_name(str(meta.get("filename") or ""), did, ext)
            arcname = _unique_arcname(used, filename, did)
            if did in fresh:
                archive.writestr(arcname, fresh[did])
                continue
            key = _item_key(root, entity, did, ext)
            if storage_service.exists(STORAGE_CATEGORY, key):
                archive.writestr(arcname, storage_service.download(STORAGE_CATEGORY, key))

    package_name = _download_name(package_filename, "package", "zip")
    if not package_name.lower().endswith(".zip"):
        package_name = f"{package_name}.zip"
    storage_service.upload(STORAGE_CATEGORY, _package_key(root, entity), buffer.getvalue())
    countries[entity] = {
        "generated_at": when,
        "dashboards": dashboards,
        "zip": {"filename": package_name, "generated_at": when},
    }
    _write_index(root, index)


def library_status(assigned_form_id: int, export_format: str, lang: str) -> dict[str, Any]:
    """Per-country generated dashboards and package, without storage keys."""
    index = _read_index(library_root(assigned_form_id, export_format, lang))
    out: dict[str, Any] = {}
    for aes_key, entry in index["countries"].items():
        if not _is_library_entity(str(aes_key)) or not isinstance(entry, dict):
            continue
        dashboards: dict[str, Any] = {}
        raw = entry.get("dashboards")
        if isinstance(raw, dict):
            for did, meta in raw.items():
                if did not in DASHBOARD_BY_ID or not isinstance(meta, dict):
                    continue
                dashboards[did] = {
                    "filename": str(meta.get("filename") or ""),
                    "generated_at": meta.get("generated_at"),
                }
        zip_meta = entry.get("zip") if isinstance(entry.get("zip"), dict) else None
        out[_entity_segment(str(aes_key))] = {
            "generated_at": entry.get("generated_at"),
            "dashboards": dashboards,
            "zip": (
                {
                    "filename": str(zip_meta.get("filename") or ""),
                    "generated_at": zip_meta.get("generated_at"),
                }
                if zip_meta
                else None
            ),
        }
    return out


def build_library_archive(assigned_form_id: int, export_format: str, lang: str) -> tuple[bytes, str]:
    """One ZIP of every stored dashboard for this assignment, format, and language."""
    fmt = normalize_export_format(export_format)
    if fmt not in {"png", "pdf"}:
        raise UprError("Choose PNG or PDF for this download.")
    root = library_root(assigned_form_id, fmt, lang)
    index = _read_index(root)
    ext = _extension(fmt)
    buffer = io.BytesIO()
    count = 0
    used_folders: set[str] = set()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        countries = index["countries"]
        for aes_key in sorted(countries, key=lambda key: (0, int(key)) if str(key).isdigit() else (1, str(key))):
            entry = countries[aes_key]
            if not _is_library_entity(str(aes_key)) or not isinstance(entry, dict):
                continue
            dashboards = entry.get("dashboards") if isinstance(entry.get("dashboards"), dict) else {}
            zip_meta = entry.get("zip") if isinstance(entry.get("zip"), dict) else {}
            stem = Path(str(zip_meta.get("filename") or "")).stem
            folder = stem or (f"country-{int(aes_key)}" if str(aes_key).isdigit() else str(aes_key))
            base = folder
            suffix = 2
            while folder in used_folders:
                folder = f"{base}-{suffix}"
                suffix += 1
            used_folders.add(folder)
            used_names: set[str] = set()
            for did, meta in dashboards.items():
                if did not in DASHBOARD_BY_ID or not isinstance(meta, dict):
                    continue
                key = _item_key(root, str(aes_key), did, ext)
                if not storage_service.exists(STORAGE_CATEGORY, key):
                    continue
                filename = _download_name(str(meta.get("filename") or ""), did, ext)
                arcname = _unique_arcname(used_names, filename, did)
                archive.writestr(f"{folder}/{arcname}", storage_service.download(STORAGE_CATEGORY, key))
                count += 1
    if count == 0:
        raise NotFound("No generated files yet.")
    return buffer.getvalue(), f"upr-{fmt}-all-countries.zip"


def _require_country(assigned_form_id: int, aes_id: int) -> int:
    from app.models.assignments import AssignmentEntityStatus

    row = AssignmentEntityStatus.query.get(int(aes_id))
    if (
        row is None
        or row.entity_type != "country"
        or int(row.assigned_form_id or 0) != int(assigned_form_id)
    ):
        raise UprError("Select a country on this assignment.")
    return int(row.id)


def open_library_dashboard(
    *,
    assigned_form_id: int,
    export_format: str,
    lang: str,
    aes_id: int | None = None,
    dashboard_id: str,
    library_id: str | None = None,
):
    fmt = normalize_export_format(export_format)
    did = _dashboard_id(dashboard_id)
    ext = _extension(fmt)
    entity = _entity_segment(library_id) if library_id else str(_require_country(assigned_form_id, int(aes_id or 0)))
    root = library_root(assigned_form_id, fmt, lang)
    key = _item_key(root, entity, did, ext)
    if not storage_service.exists(STORAGE_CATEGORY, key):
        raise NotFound("Visual is not ready.")
    entry = (_read_index(root)["countries"].get(entity) or {})
    meta = {}
    if isinstance(entry, dict):
        raw = entry.get("dashboards")
        if isinstance(raw, dict) and isinstance(raw.get(did), dict):
            meta = raw[did]
    filename = _download_name(str(meta.get("filename") or ""), did, ext)
    return storage_service.stream_response(
        STORAGE_CATEGORY,
        key,
        filename=filename,
        mimetype=_FORMAT_MIME[fmt],
        as_attachment=True,
    )


def open_library_package(
    *,
    assigned_form_id: int,
    export_format: str,
    lang: str,
    aes_id: int | None = None,
    library_id: str | None = None,
):
    fmt = normalize_export_format(export_format)
    entity = _entity_segment(library_id) if library_id else str(_require_country(assigned_form_id, int(aes_id or 0)))
    root = library_root(assigned_form_id, fmt, lang)
    key = _package_key(root, entity)
    if not storage_service.exists(STORAGE_CATEGORY, key):
        raise NotFound("Package is not ready.")
    entry = (_read_index(root)["countries"].get(entity) or {})
    zip_meta = entry.get("zip") if isinstance(entry, dict) and isinstance(entry.get("zip"), dict) else {}
    filename = _download_name(str(zip_meta.get("filename") or ""), "package", "zip")
    if not filename.lower().endswith(".zip"):
        filename = f"{filename}.zip"
    return storage_service.stream_response(
        STORAGE_CATEGORY,
        key,
        filename=filename,
        mimetype="application/zip",
        as_attachment=True,
    )
