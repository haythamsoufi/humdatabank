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
from plugins.upr_visuals.catalog import UPR_VISUAL_TEMPLATE_IDS, kind_for_template
from plugins.upr_visuals.errors import UprVisualsError

EXPORT_FORMATS = frozenset({"png", "pdf", "idml"})
MAX_NARRATIVE_FILES = 250


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
        raise UprVisualsError("Select a Unified Plan or Report assignment.")
    return assigned


def normalize_export_format(value: str | None) -> str:
    kind = str(value or "png").strip().lower()
    if kind not in EXPORT_FORMATS:
        raise UprVisualsError("Choose PNG, PDF, or InDesign.")
    return kind


def _stem_key(name: str) -> str:
    return Path(name).stem.strip().lower()


def _alnum(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _docx_from_zip(data: bytes) -> dict[str, bytes]:
    from plugins.upr_visuals.idml import DOCX_MAX_UNCOMPRESSED_BYTES, validate_docx_bytes

    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UprVisualsError("Upload a zip of Word documents (.docx).") from exc
    found: dict[str, bytes] = {}
    with archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if info.is_dir() or name.startswith("__MACOSX") or "/__MACOSX/" in f"/{name}/":
                continue
            if not name.lower().endswith(".docx"):
                continue
            if int(getattr(info, "file_size", 0) or 0) > DOCX_MAX_UNCOMPRESSED_BYTES:
                raise UprVisualsError("The Word document is too large to process.")
            raw = archive.read(info)
            validate_docx_bytes(raw)
            found[_stem_key(name)] = raw
            if len(found) > MAX_NARRATIVE_FILES:
                raise UprVisualsError(f"Upload at most {MAX_NARRATIVE_FILES} Word documents.")
    if not found:
        raise UprVisualsError("The zip did not contain any Word documents (.docx).")
    return found


def collect_narrative_uploads(storages) -> dict[str, bytes]:
    """Map filename stem → docx bytes from .docx files and/or a zip of them."""
    from plugins.upr_visuals.idml import read_docx_upload

    found: dict[str, bytes] = {}
    for storage in storages or []:
        filename = (getattr(storage, "filename", "") or "").strip()
        if not filename:
            continue
        lower = filename.lower()
        if lower.endswith(".zip"):
            found.update(_docx_from_zip(storage.read()))
        elif lower.endswith(".docx"):
            found[_stem_key(filename)] = read_docx_upload(storage, filename=filename)
        else:
            raise UprVisualsError("Upload Word documents (.docx) or a zip of them.")
        if len(found) > MAX_NARRATIVE_FILES:
            raise UprVisualsError(f"Upload at most {MAX_NARRATIVE_FILES} Word documents.")
    return found


def match_narrative_path(
    paths: dict[str, str],
    *,
    iso3: str = "",
    country_name: str = "",
    aes_id: int | None = None,
) -> Path | None:
    """Pick a saved .docx for a country. Prefer ISO3, then country name, then aes id."""
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
