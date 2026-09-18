"""Bulk export assignment/country listings and narrative-file matching."""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.assignments import AssignedForm, AssignmentEntityStatus
from plugins.upr.catalog import UPR_VISUAL_TEMPLATE_IDS, kind_for_template
from plugins.upr.errors import UprError

EXPORT_FORMATS = frozenset({"png", "pdf", "idml"})
MAX_NARRATIVE_FILES = 250
MAX_BULK_NARRATIVE_BYTES = 80 * 1024 * 1024


def list_assigned_forms_for_bulk() -> list[dict[str, Any]]:
    """Unified Plan and Report assignments available for bulk export."""
    rows = (
        AssignedForm.query.options(joinedload(AssignedForm.template))
        .filter(AssignedForm.template_id.in_(UPR_VISUAL_TEMPLATE_IDS))
        .order_by(
            AssignedForm.assigned_at.desc().nullslast(),
            AssignedForm.id.desc(),
        )
        .all()
    )
    return [
        {
            "id": assigned.id,
            "display_name": assigned.display_name,
            "template_id": assigned.template_id,
            "template_name": assigned.template.name if assigned.template else "",
            "period_name": assigned.period_name,
            "kind": kind_for_template(int(assigned.template_id or 0)),
        }
        for assigned in rows
    ]


def list_countries_for_bulk(assigned_form_id: int) -> list[dict[str, Any]]:
    """Country rows on one assignment, for bulk export."""
    from app.models.core import Country

    rows = (
        db.session.query(AssignmentEntityStatus, Country)
        .outerjoin(
            Country,
            db.and_(
                AssignmentEntityStatus.entity_type == "country",
                AssignmentEntityStatus.entity_id == Country.id,
            ),
        )
        .filter(AssignmentEntityStatus.assigned_form_id == int(assigned_form_id))
        .filter(AssignmentEntityStatus.entity_type == "country")
        .order_by(Country.name.asc().nullslast())
        .all()
    )
    return [
        {
            "aes_id": aes.id,
            "country_name": country.name if country else "",
            "iso3": country.iso3 if country else "",
        }
        for aes, country in rows
    ]


def get_assigned_form_for_bulk(assigned_form_id: int) -> AssignedForm:
    assigned = AssignedForm.query.get(int(assigned_form_id))
    if assigned is None or int(assigned.template_id or 0) not in UPR_VISUAL_TEMPLATE_IDS:
        raise UprError("Select a Unified Plan or Report assignment.")
    return assigned


def normalize_export_format(value: str | None) -> str:
    kind = str(value or "png").strip().lower()
    if kind not in EXPORT_FORMATS:
        raise UprError("Choose PNG, PDF, or InDesign.")
    return kind


def _stem_key(name: str) -> str:
    return Path(name).stem.strip().lower()


def _alnum(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _narratives_from_zip(data: bytes) -> dict[str, bytes]:
    from plugins.upr.idml import (
        DOCX_MAX_BYTES,
        PDF_MAX_BYTES,
        is_pdf_bytes,
        validate_docx_bytes,
        validate_pdf_bytes,
    )

    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UprError("Upload a zip of Word documents (.docx) or PDFs.") from exc
    found: dict[str, bytes] = {}
    total_bytes = 0
    with archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if info.is_dir() or name.startswith("__MACOSX") or "/__MACOSX/" in f"/{name}/":
                continue
            lower = name.lower()
            if not lower.endswith((".docx", ".pdf")):
                continue
            declared = int(getattr(info, "file_size", 0) or 0)
            limit = PDF_MAX_BYTES if lower.endswith(".pdf") else DOCX_MAX_BYTES
            if declared > limit:
                raise UprError("The narrative file is too large to process.")
            raw = archive.read(info)
            total_bytes += len(raw)
            if total_bytes > MAX_BULK_NARRATIVE_BYTES:
                raise UprError("The zip of narrative files is too large to process.")
            if is_pdf_bytes(raw) or lower.endswith(".pdf"):
                validate_pdf_bytes(raw)
            else:
                validate_docx_bytes(raw)
            found[_stem_key(name)] = raw
            if len(found) > MAX_NARRATIVE_FILES:
                raise UprError(f"Upload at most {MAX_NARRATIVE_FILES} narrative files.")
    if not found:
        raise UprError("The zip did not contain any Word documents (.docx) or PDFs.")
    return found


def collect_narrative_uploads(storages) -> dict[str, bytes]:
    """Map filename stem → docx/pdf bytes from those files and/or a zip of them."""
    from plugins.upr.idml import read_narrative_upload

    found: dict[str, bytes] = {}
    for storage in storages or []:
        filename = (getattr(storage, "filename", "") or "").strip()
        if not filename:
            continue
        lower = filename.lower()
        if lower.endswith(".zip"):
            found.update(_narratives_from_zip(storage.read()))
        elif lower.endswith((".docx", ".pdf")):
            found[_stem_key(filename)] = read_narrative_upload(storage, filename=filename)
        else:
            raise UprError("Upload Word documents (.docx), PDFs, or a zip of them.")
        if len(found) > MAX_NARRATIVE_FILES:
            raise UprError(f"Upload at most {MAX_NARRATIVE_FILES} narrative files.")
    return found


def match_narrative_path(
    paths: dict[str, str],
    *,
    iso3: str = "",
    country_name: str = "",
    aes_id: int | None = None,
) -> Path | None:
    """Pick a saved narrative file for a country. Prefer ISO3, then country name, then aes id."""
    if not paths:
        return None
    iso = (iso3 or "").strip().lower()
    if iso and iso in paths:
        return Path(paths[iso])
    if iso:
        for stem, raw_path in paths.items():
            parts = re.split(r"[\s_\-.]+", stem)
            if iso in parts or stem.startswith(iso):
                return Path(raw_path)
    name = _alnum(country_name)
    if name:
        for stem, raw_path in paths.items():
            if _alnum(stem) == name:
                return Path(raw_path)
    if aes_id is not None and str(aes_id) in paths:
        return Path(paths[str(aes_id)])
    return None
