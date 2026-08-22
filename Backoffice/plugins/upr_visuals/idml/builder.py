"""Public facade for UPR visuals InDesign packages."""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from plugins.upr_visuals.idml.constants import *  # noqa: F403
from plugins.upr_visuals.idml.narrative_style import folio_label, style_narrative_blocks
from plugins.upr_visuals.idml.pages import add_narrative_pages, build_cover_chrome, build_native_pages
from plugins.upr_visuals.idml.pdf_extract import export_visual_svgs
from plugins.upr_visuals.idml.word_reader import load_word_paragraphs
from plugins.upr_visuals.idml.xml_idml import Idml, _xml_text

__all__ = [
    "Idml",
    "_xml_text",
    "add_narrative_pages",
    "build_cover_chrome",
    "build_indesign_package",
    "build_native_pages",
    "export_visual_svgs",
    "folio_label",
    "load_word_paragraphs",
    "style_narrative_blocks",
    "zip_indesign_package",
]


def zip_indesign_package(idml_bytes: bytes, idml_name: str, links_dir: Path) -> bytes:
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(idml_name, idml_bytes)
        if links_dir.is_dir():
            for path in sorted(links_dir.iterdir()):
                if path.is_file() and path.suffix.lower() in {".svg", ".png"}:
                    zf.write(path, arcname=f"Links/{path.name}")
    return out.getvalue()


def build_indesign_package(
    *,
    payload: dict,
    pdf_bytes: bytes,
    work_dir: Path,
    word_bytes: bytes | None = None,
) -> dict:
    import fitz
    from plugins.upr_visuals.data import filename_from_visual_title

    work_dir = Path(work_dir)
    links = work_dir / "Links"
    links.mkdir(parents=True, exist_ok=True)
    meta = payload.get("meta") or {}
    title = meta.get("document_title") or "UPR visuals"
    idml_name = filename_from_visual_title(title, "idml")

    pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    doc = Idml()
    try:
        visual_bands = build_native_pages(doc, pdf_doc, payload, links)
    finally:
        pdf_doc.close()

    styled: list[dict] = []
    if word_bytes:
        styled = style_narrative_blocks(
            load_word_paragraphs(word_bytes),
            country_name=str(meta.get("country_name") or ""),
        )
        add_narrative_pages(doc, styled, folio=folio_label(meta))

    idml_bytes = doc.package_bytes()
    (work_dir / idml_name).write_bytes(idml_bytes)
    return {
        "idml_bytes": idml_bytes,
        "idml_name": idml_name,
        "zip_bytes": zip_indesign_package(idml_bytes, idml_name, links),
        "pages": doc.page_count,
        "visual_bands": visual_bands,
        "narrative_paragraphs": len(styled),
        "title": title,
        "styled": styled,
    }
