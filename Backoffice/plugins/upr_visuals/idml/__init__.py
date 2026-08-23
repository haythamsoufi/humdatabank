"""UPR visuals → InDesign IDML and Word-narrative PDF."""

from __future__ import annotations

import zipfile
from io import BytesIO

from plugins.upr_visuals.errors import UprVisualsError
from plugins.upr_visuals.idml.builder import (
    build_indesign_package,
    zip_indesign_package,
)
from plugins.upr_visuals.idml.narrative_pdf import merge_report_pdfs, render_narrative_pdf_bytes
from plugins.upr_visuals.idml.narrative_style import folio_label, folio_text, style_narrative_blocks
from plugins.upr_visuals.idml.word_reader import load_word_paragraphs

DOCX_MAX_BYTES = 20 * 1024 * 1024
# Compressed uploads can still explode; cap the XML members we actually parse.
DOCX_MAX_UNCOMPRESSED_BYTES = 80 * 1024 * 1024
DOCX_XML_MEMBERS = ("word/document.xml", "word/_rels/document.xml.rels")

__all__ = [
    "DOCX_MAX_BYTES",
    "DOCX_MAX_UNCOMPRESSED_BYTES",
    "DOCX_XML_MEMBERS",
    "build_indesign_package",
    "folio_label",
    "folio_text",
    "load_word_paragraphs",
    "merge_report_pdfs",
    "read_docx_upload",
    "read_docx_xml_member",
    "render_narrative_pdf_bytes",
    "style_narrative_blocks",
    "validate_docx_bytes",
    "zip_indesign_package",
]


def _reject_oversized_zip_member(info: zipfile.ZipInfo) -> None:
    if int(getattr(info, "file_size", 0) or 0) > DOCX_MAX_UNCOMPRESSED_BYTES:
        raise UprVisualsError("The Word document is too large to process.")


def read_docx_xml_member(zf: zipfile.ZipFile, name: str) -> bytes:
    """Read one named OOXML member after checking uncompressed size."""
    info = zf.getinfo(name)
    _reject_oversized_zip_member(info)
    data = zf.read(name)
    if len(data) > DOCX_MAX_UNCOMPRESSED_BYTES:
        raise UprVisualsError("The Word document is too large to process.")
    return data


def validate_docx_bytes(data: bytes) -> None:
    if not data:
        raise UprVisualsError("Upload a Word document (.docx).")
    if len(data) > DOCX_MAX_BYTES:
        raise UprVisualsError("Upload a Word document (.docx) of 20 MB or less.")
    if not data.startswith(b"PK"):
        raise UprVisualsError("Upload a Word document (.docx).")
    try:
        with zipfile.ZipFile(BytesIO(data)) as zf:
            names = zf.namelist()
            if "word/document.xml" not in names:
                raise UprVisualsError("Upload a Word document (.docx).")
            for name in DOCX_XML_MEMBERS:
                if name in names:
                    _reject_oversized_zip_member(zf.getinfo(name))
    except zipfile.BadZipFile as exc:
        raise UprVisualsError("Upload a Word document (.docx).") from exc


def read_docx_upload(storage, *, filename: str = "") -> bytes:
    name = (filename or getattr(storage, "filename", "") or "").strip().lower()
    if name and not name.endswith(".docx"):
        raise UprVisualsError("Upload a Word document (.docx).")
    data = storage.read()
    validate_docx_bytes(data)
    return data
