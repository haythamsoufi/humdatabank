"""UPR visuals → InDesign IDML and Word-narrative PDF."""

from __future__ import annotations

import zipfile
from io import BytesIO

from plugins.upr_visuals.data import UprVisualsError
from plugins.upr_visuals.idml.builder import (
    build_indesign_package,
    folio_label,
    load_word_paragraphs,
    style_narrative_blocks,
    zip_indesign_package,
)
from plugins.upr_visuals.idml.narrative_pdf import merge_report_pdfs, render_narrative_pdf_bytes

DOCX_MAX_BYTES = 20 * 1024 * 1024

__all__ = [
    "DOCX_MAX_BYTES",
    "build_indesign_package",
    "folio_label",
    "load_word_paragraphs",
    "merge_report_pdfs",
    "read_docx_upload",
    "render_narrative_pdf_bytes",
    "style_narrative_blocks",
    "validate_docx_bytes",
    "zip_indesign_package",
]


def validate_docx_bytes(data: bytes) -> None:
    if not data:
        raise UprVisualsError("Upload a Word document (.docx).")
    if len(data) > DOCX_MAX_BYTES:
        raise UprVisualsError("Upload a Word document (.docx) of 20 MB or less.")
    if not data.startswith(b"PK"):
        raise UprVisualsError("Upload a Word document (.docx).")
    try:
        names = zipfile.ZipFile(BytesIO(data)).namelist()
    except zipfile.BadZipFile as exc:
        raise UprVisualsError("Upload a Word document (.docx).") from exc
    if "word/document.xml" not in names:
        raise UprVisualsError("Upload a Word document (.docx).")


def read_docx_upload(storage, *, filename: str = "") -> bytes:
    name = (filename or getattr(storage, "filename", "") or "").strip().lower()
    if name and not name.endswith(".docx"):
        raise UprVisualsError("Upload a Word document (.docx).")
    data = storage.read()
    validate_docx_bytes(data)
    return data
