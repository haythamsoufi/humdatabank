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
from plugins.upr_visuals.idml.word_reader import load_narrative_paragraphs, load_word_paragraphs

DOCX_MAX_BYTES = 20 * 1024 * 1024
PDF_MAX_BYTES = DOCX_MAX_BYTES
PDF_MAX_PAGES = 200
# Compressed uploads can still explode; cap the XML members we actually parse.
DOCX_MAX_UNCOMPRESSED_BYTES = 80 * 1024 * 1024
DOCX_XML_MEMBERS = ("word/document.xml", "word/_rels/document.xml.rels")

__all__ = [
    "DOCX_MAX_BYTES",
    "DOCX_MAX_UNCOMPRESSED_BYTES",
    "DOCX_XML_MEMBERS",
    "PDF_MAX_BYTES",
    "PDF_MAX_PAGES",
    "build_indesign_package",
    "folio_label",
    "folio_text",
    "is_pdf_bytes",
    "load_narrative_paragraphs",
    "load_word_paragraphs",
    "merge_report_pdfs",
    "read_docx_upload",
    "read_docx_xml_member",
    "read_narrative_upload",
    "render_narrative_pdf_bytes",
    "style_narrative_blocks",
    "validate_docx_bytes",
    "validate_pdf_bytes",
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


def is_pdf_bytes(data: bytes | None) -> bool:
    return bool(data) and data.startswith(b"%PDF")


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


def validate_pdf_bytes(data: bytes) -> None:
    if not is_pdf_bytes(data):
        raise UprVisualsError("Upload a Word document (.docx) or PDF.")
    if len(data) > PDF_MAX_BYTES:
        raise UprVisualsError("Upload a Word document (.docx) or PDF of 20 MB or less.")
    import fitz

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise UprVisualsError("Upload a valid PDF.") from exc
    try:
        if doc.needs_pass:
            raise UprVisualsError("This PDF is password-protected.")
        if doc.page_count < 1:
            raise UprVisualsError("This PDF has no pages.")
        if doc.page_count > PDF_MAX_PAGES:
            raise UprVisualsError(f"Upload a PDF of {PDF_MAX_PAGES} pages or fewer.")
    finally:
        doc.close()


def read_docx_upload(storage, *, filename: str = "") -> bytes:
    name = (filename or getattr(storage, "filename", "") or "").strip().lower()
    if name and not name.endswith(".docx"):
        raise UprVisualsError("Upload a Word document (.docx).")
    data = storage.read()
    validate_docx_bytes(data)
    return data


def read_narrative_upload(storage, *, filename: str = "") -> bytes:
    name = (filename or getattr(storage, "filename", "") or "").strip().lower()
    if name and not name.endswith((".docx", ".pdf")):
        raise UprVisualsError("Upload a Word document (.docx) or PDF.")
    data = storage.read()
    if is_pdf_bytes(data) or name.endswith(".pdf"):
        validate_pdf_bytes(data)
        return data
    validate_docx_bytes(data)
    return data
