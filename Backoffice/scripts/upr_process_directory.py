"""
UPR directory processor (first-page visual extraction + optional vision hints).

What it does:
- Scans a directory for PDF files
- Processes ONLY the first N pages (default: 5) into `pages=[{page_number,text,...}]`
- Runs UPR visual extraction (`metadata["upr"]` blocks) on those pages
- Optionally renders the first N pages as images and sends them to an LLM (vision)
  to classify layouts / suggest parsing hints

This is intended for building a "training cases" corpus across years/countries where
UPR visuals vary slightly (e.g., multi-year vs single-year funding panels).
"""

from __future__ import annotations

import argparse
import base64
import logging
import json
import os
from pathlib import Path
import sys
import time
import re
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF

# Ensure `Backoffice/` is on sys.path so `import app` works when running this script directly.
_BACKOFFICE_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKOFFICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKOFFICE_ROOT))

from app import create_app
from app.services.ai_document_processor import AIDocumentProcessor
from app.services.upr.visual_chunking import extract_upr_visual_blocks
from app.utils.constants import DEFAULT_MAX_COMPLETION_TOKENS

logger = logging.getLogger(__name__)

DEFAULT_UPR_TRAINING_DIR = r"C:\IFRC Network Databank\UPR training docs"


def _safe_stem(p: Path) -> str:
    s = p.stem.strip()
    # Keep filenames stable but filesystem-safe
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".", " ") else "_" for ch in s).strip() or "doc"


def _render_pdf_first_pages_png_b64(pdf_path: str, *, max_pages: int = 5, dpi: int = 90) -> List[str]:
    doc = fitz.open(pdf_path)
    out: List[str] = []
    try:
        n = min(int(max_pages), len(doc))
        for i in range(n):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=int(dpi), alpha=False)
            png = pix.tobytes("png")
            out.append(base64.b64encode(png).decode("ascii"))
    finally:
        doc.close()
    return out


def _extract_json_from_text(s: str) -> Optional[Dict[str, Any]]:
    if not s:
        return None
    s = s.strip()
    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    blob = s[start : end + 1]
    try:
        obj = json.loads(blob)
        return obj if isinstance(obj, dict) else None
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("_extract_json_from_text: %s", e)
        return None


def _vision_suggest_upr_layouts(
    *,
    page_png_b64: List[str],
    title: Optional[str],
    filename: Optional[str],
    model: str,
    api_key: str,
) -> Optional[Dict[str, Any]]:
    """
    Ask a vision-capable model to identify which UPR visuals/layout variants appear on pages 1..N.
    Returns JSON (dict) or None.
    """
    if not page_png_b64:
        return None

    from openai import OpenAI  # type: ignore

    client = OpenAI(api_key=api_key)

    prompt = (
        "You are helping build a robust extractor for IFRC UPR (Unified Planning and Reporting) PDFs.\n"
        "UPR documents (Plan / Midyear report / Annual report) contain infographic visuals mostly on pages 1–5.\n"
        "Layouts vary slightly by year, doc type, and country (e.g., some show multi-year funding, others single-year).\n\n"
        "Given the first pages as images, return ONLY valid JSON with:\n"
        "{\n"
        '  "doc_type_guess": "plan"|"midyear_report"|"annual_report"|"unknown",\n'
        '  "year_guess": number|null,\n'
        '  "pages": [\n'
        "    {\n"
        '      "page_number": number,\n'
        '      "visuals": [\n'
        "        {\n"
        '          "visual_type": "in_support_kpis"|"people_reached"|"people_to_be_reached"|"financial_overview"|"funding_requirements"|"hazards"|"pns_bilateral_support"|"other"|"none",\n'
        '          "layout_variant": string|null,\n'
        '          "notes": string|null\n'
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ],\n"
        '  "global_notes": string|null,\n'
        '  "parsing_hints": {\n'
        '     "funding_requirements": {"years_shown": number|null, "multi_column": boolean|null},\n'
        '     "country_specific_weirdness": string|null\n'
        "  }\n"
        "}\n\n"
        "Rules:\n"
        "- Be conservative; if unsure use visual_type='other' and explain in notes.\n"
        "- Return ONLY JSON. No markdown.\n"
    )
    if title or filename:
        prompt += f"\nDocument hint: title={title!r}, filename={filename!r}\n"

    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    for i, b64 in enumerate(page_png_b64, start=1):
        content.append({"type": "text", "text": f"Page {i} image:"})
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

    # Rate limits for image prompts can be hit easily. Retry with backoff on 429.
    for attempt in range(8):
        try:
            resp = client.chat.completions.create(
                model=str(model),
                messages=[
                    {"role": "system", "content": "Return ONLY valid JSON."},
                    {"role": "user", "content": content},
                ],
                max_completion_tokens=DEFAULT_MAX_COMPLETION_TOKENS,
            )
            msg = resp.choices[0].message if (resp and resp.choices) else None
            raw = (getattr(msg, "content", None) or "").strip() if msg else ""
            return _extract_json_from_text(raw)
        except Exception as e:
            s = str(e)
            is_rate = ("rate limit" in s.lower()) or ("rate_limit_exceeded" in s.lower()) or ("Error code: 429" in s)
            if not is_rate:
                raise
            # Try to parse suggested retry delay from message: "Please try again in Xs."
            wait_s = None
            m = re.search(r"try again in\s+([0-9.]+)s", s, flags=re.IGNORECASE)
            if m:
                try:
                    wait_s = float(m.group(1))
                except Exception as e2:
                    import logging
                    logging.getLogger(__name__).debug("parse retry delay: %s", e2)
                    wait_s = None
            if wait_s is None:
                wait_s = min(20.0, 1.0 + (attempt * 2.0))
            time.sleep(float(wait_s) + 0.25)
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Process a directory of UPR PDFs (first pages only).")
    parser.add_argument(
        "input_dir",
        nargs="?",
        default=DEFAULT_UPR_TRAINING_DIR,
        help=f"Directory containing PDFs (recursively scanned). Default: {DEFAULT_UPR_TRAINING_DIR}",
    )
    parser.add_argument("--output-dir", default="upr_out", help="Where to write JSON outputs")
    parser.add_argument("--max-pages", type=int, default=5, help="How many pages to process from each PDF")
    parser.add_argument("--dpi", type=int, default=90, help="DPI for rendered page PNGs (vision only)")
    parser.add_argument("--recursive", action="store_true", help="Recurse into subdirectories")
    parser.add_argument("--vision-compare", action="store_true", help="Send rendered pages to LLM to get layout hints")
    parser.add_argument(
        "--vision-skip-existing",
        action="store_true",
        help="Skip vision call if vision_hints.json already exists for a PDF",
    )
    parser.add_argument("--vision-model", default=None, help="Vision model name (default from config or 'gpt-4o-mini')")
    parser.add_argument("--enable-layout-words", action="store_true", help="Enable word-level layout extraction (improves some parsers)")
    parser.add_argument("--enable-upr-kpi-clip", action="store_true", help="Attach UPR KPI header crop b64 (for KPI-specific vision)")
    args = parser.parse_args()

    in_dir = Path(args.input_dir)
    if not in_dir.exists():
        raise SystemExit(f"Input directory not found: {in_dir}")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    app = create_app(os.getenv("FLASK_CONFIG"))
    with app.app_context():
        # Toggle processor-side enrichment features for the first N pages.
        if args.enable_layout_words:
            app.config["AI_PDF_LAYOUT_WORDS_ENABLED"] = True
            app.config["AI_PDF_LAYOUT_WORDS_MAX_PAGES"] = int(args.max_pages)
            # Enable deterministic UPR KPI parsing using word bboxes.
            # This is especially important for plan PDFs where OCR text can be near-empty.
            app.config["AI_UPR_LAYOUT_KPI_ENABLED"] = True
        if args.enable_upr_kpi_clip:
            # This only attaches the crop b64 to pages. The actual KPI-vision extraction is gated
            # by the same flag in `upr_visual_chunking.extract_in_support_kpis`, so keep it OFF here
            # unless you also want the extractor to call OpenAI.
            app.config["AI_UPR_VISION_KPI_ENABLED"] = True
            app.config["AI_UPR_VISION_MAX_PAGES"] = int(args.max_pages)

        processor = AIDocumentProcessor()

        pdf_paths = list(in_dir.rglob("*.pdf")) if args.recursive else list(in_dir.glob("*.pdf"))
        pdf_paths = [p for p in pdf_paths if p.is_file()]
        pdf_paths.sort(key=lambda p: str(p).lower())

        logger.info("Found %d PDFs", len(pdf_paths))

        # Vision compare config
        vision_enabled = bool(args.vision_compare)
        openai_key = str(app.config.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "")
        vision_model = (
            str(args.vision_model)
            if args.vision_model
            else str(app.config.get("AI_UPR_VISION_MODEL", "gpt-4o-mini"))
        )

        for pdf in pdf_paths:
            try:
                stem = _safe_stem(pdf)
                doc_out_dir = out_dir / stem
                doc_out_dir.mkdir(parents=True, exist_ok=True)

                processed = processor.process_document(
                    file_path=str(pdf),
                    filename=pdf.name,
                    extract_images=False,
                    ocr_enabled=False,
                    max_pages=int(args.max_pages),
                )
                pages = processed.get("pages") or []
                meta = processed.get("metadata") or {}
                title = meta.get("title") if isinstance(meta, dict) else None

                blocks = extract_upr_visual_blocks(
                    pages=pages,
                    document_title=title if isinstance(title, str) else None,
                    document_filename=pdf.name,
                )

                (doc_out_dir / "extracted_blocks.json").write_text(
                    json.dumps(
                        {
                            "source_pdf": str(pdf),
                            "processed_pages": (meta.get("processed_pages") if isinstance(meta, dict) else None),
                            "blocks": blocks,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                if vision_enabled:
                    if bool(args.vision_skip_existing) and (doc_out_dir / "vision_hints.json").exists():
                        continue
                    if not openai_key:
                        print(f"[SKIP vision] OPENAI_API_KEY not set for {pdf.name}")
                    else:
                        page_imgs = _render_pdf_first_pages_png_b64(str(pdf), max_pages=int(args.max_pages), dpi=int(args.dpi))
                        hints = _vision_suggest_upr_layouts(
                            page_png_b64=page_imgs,
                            title=title if isinstance(title, str) else None,
                            filename=pdf.name,
                            model=vision_model,
                            api_key=openai_key,
                        )
                        if hints:
                            (doc_out_dir / "vision_hints.json").write_text(
                                json.dumps(hints, ensure_ascii=False, indent=2),
                                encoding="utf-8",
                            )
                logger.info("Processed: %s -> blocks=%d", pdf.name, len(blocks))
            except Exception as e:
                logger.error("[ERROR] %s: %s", pdf.name, e)
                continue

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())

