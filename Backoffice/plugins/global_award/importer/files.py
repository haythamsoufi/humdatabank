"""Workbooks the importer can read: uploads kept on disk and logframes in the repository root."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import current_app

from plugins.global_award.constants import REPO_ROOT

FILE_ID = re.compile(r"^[0-9a-f]{32}$")
UPLOAD_FOLDER = "global_award_uploads"
# Workbooks saved before the plugin id was singular.
_PREVIOUS_UPLOAD_FOLDER = "global_awards_uploads"
STORED_LIMIT = 12
# The two workbooks the importer takes, each with its own upload slot.
SLOT_LOGFRAME = "logframe"
SLOT_SECTORAL = "sectoral"
SLOTS = (SLOT_LOGFRAME, SLOT_SECTORAL)
# A repository workbook is offered for a slot when its name looks like that workbook.
_REPO_NAME_HINTS = {
    SLOT_LOGFRAME: ("global award", "marc", "log frame", "logframe"),
    SLOT_SECTORAL: ("sectoral",),
}

REF_REPO = "repo"
REF_STORED = "stored"


def upload_dir() -> Path:
    folder = Path(current_app.instance_path) / UPLOAD_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    previous = Path(current_app.instance_path) / _PREVIOUS_UPLOAD_FOLDER
    if previous.is_dir():
        for item in list(previous.iterdir()):
            dest = folder / item.name
            if not dest.exists():
                item.replace(dest)
        try:
            previous.rmdir()
        except OSError:
            pass
    return folder


def _meta_path(path: Path) -> Path:
    return path.with_name(path.stem + ".meta.json")


def _read_meta(path: Path) -> Dict[str, Any]:
    meta = _meta_path(path)
    if not meta.is_file():
        return {}
    try:
        payload = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _slot_of(meta: Dict[str, Any]) -> str:
    """Uploads kept before there were two slots have no slot and are logframes."""
    slot = str(meta.get("slot") or SLOT_LOGFRAME)
    return slot if slot in SLOTS else SLOT_LOGFRAME


def store_upload(data: bytes, filename: str, slot: str = SLOT_LOGFRAME) -> str:
    """Keep an uploaded workbook and return its file id.

    The same bytes are stored once per slot; uploading them again only refreshes the name
    and time, so the list does not fill with copies of one file.
    """
    digest = hashlib.sha256(data).hexdigest()
    folder = upload_dir()
    file_id = None
    for path in folder.glob("*.xlsx"):
        if not FILE_ID.match(path.stem):
            continue
        meta = _read_meta(path)
        if meta.get("sha256") == digest and _slot_of(meta) == slot:
            file_id = path.stem
            break
    if file_id is None:
        file_id = uuid.uuid4().hex
        (folder / f"{file_id}.xlsx").write_bytes(data)
    meta = {
        "filename": filename,
        "size": len(data),
        "sha256": digest,
        "slot": slot,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    _meta_path(folder / f"{file_id}.xlsx").write_text(json.dumps(meta), encoding="utf-8")
    return file_id


def stored_path(file_id: str) -> Optional[Path]:
    if not file_id or not FILE_ID.match(file_id):
        return None
    path = upload_dir() / f"{file_id}.xlsx"
    return path if path.is_file() else None


def stored_name(file_id: str) -> str:
    path = stored_path(file_id)
    return str(_read_meta(path).get("filename") or "Uploaded workbook") if path else "Uploaded workbook"


def repo_workbooks(slot: str = SLOT_LOGFRAME) -> List[Path]:
    """Workbooks for ``slot`` in the repository root, newest first."""
    hints = _REPO_NAME_HINTS.get(slot, ())
    try:
        candidates = [
            path
            for path in REPO_ROOT.glob("*.xlsx")
            if path.is_file()
            and not path.name.startswith("~$")
            and any(hint in path.name.casefold() for hint in hints)
        ]
    except OSError:
        return []
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)


def repo_workbook(name: str, slot: str = SLOT_LOGFRAME) -> Optional[Path]:
    """The repository workbook called ``name``, only when it is one that is offered for ``slot``."""
    for path in repo_workbooks(slot):
        if path.name == name:
            return path
    return None


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _when(value: Any) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = str(value or "")
    if len(text) >= 16 and text[10] == "T":
        return text[:10] + " " + text[11:16] + " UTC"
    return text or "—"


def list_disk_files(slot: str = SLOT_LOGFRAME) -> List[Dict[str, Any]]:
    """Uploads kept for ``slot``, then its repository workbooks. Each row carries a ``ref``."""
    rows: List[Dict[str, Any]] = []
    stored = []
    try:
        for path in upload_dir().glob("*.xlsx"):
            if path.is_file() and FILE_ID.match(path.stem):
                meta = _read_meta(path)
                if _slot_of(meta) != slot:
                    continue
                stored.append((str(meta.get("uploaded_at") or ""), path, meta))
    except OSError:
        stored = []
    for uploaded, path, meta in sorted(stored, key=lambda row: row[0], reverse=True)[:STORED_LIMIT]:
        size = meta.get("size") if isinstance(meta.get("size"), int) else path.stat().st_size
        rows.append({
            "name": str(meta.get("filename") or "Uploaded workbook"),
            "found": True,
            "size_label": _format_bytes(int(size or 0)),
            "modified_label": _when(uploaded or path.stat().st_mtime),
            "note": "Uploaded to this server.",
            "kind": REF_STORED,
            "ref": f"{REF_STORED}:{path.stem}",
        })
    for path in repo_workbooks(slot):
        stat = path.stat()
        rows.append({
            "name": path.name,
            "found": True,
            "size_label": _format_bytes(stat.st_size),
            "modified_label": _when(stat.st_mtime),
            "note": "Stored with the repository.",
            "kind": REF_REPO,
            "ref": f"{REF_REPO}:{path.name}",
        })
    return rows


def resolve_ref(ref: str, slot: str = SLOT_LOGFRAME) -> Optional[tuple[Path, str]]:
    """``(path, display name)`` for a ref from :func:`list_disk_files` of ``slot``, or ``None``.

    A file kept for the other slot does not resolve, so a logframe cannot be imported as the
    sectoral workbook or the other way round.
    """
    kind, _sep, value = (ref or "").partition(":")
    if kind == REF_STORED:
        path = stored_path(value)
        if path is None or _slot_of(_read_meta(path)) != slot:
            return None
        return path, stored_name(value)
    if kind == REF_REPO:
        path = repo_workbook(value, slot)
        return (path, path.name) if path else None
    return None
