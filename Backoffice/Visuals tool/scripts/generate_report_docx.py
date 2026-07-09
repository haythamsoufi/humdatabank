#!/usr/bin/env python3
"""Generate editable Word report with chart images and text in lightly bordered tables."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gb_figures.config import build_workers, resolve_excel, cleanup_build_copy
from gb_figures.data import build_model, load_sg_report
from gb_figures.languages import discover_languages, docx_filename
from gb_figures.layouts import SECTION_CODES
from gb_figures.render_docx import render_report_docx

OUTPUT_DIR = ROOT / "report" / "output"


def _render_one(
    excel: Path,
    language: str,
    output_path: Path,
    sections: list[str] | None,
) -> tuple[str, Path]:
    """Worker: build the model and render one language's DOCX standalone."""
    model = build_model(excel)
    render_report_docx(model, language=language, output_path=output_path, sections=sections)
    return language, output_path


def _resolve_languages(excel: Path, args: argparse.Namespace) -> list[str]:
    if args.language:
        return [args.language]
    if args.all_languages:
        return list(discover_languages(load_sg_report(excel)["mapping"]))
    env_lang = os.environ.get("GB_REPORT_LANGUAGE")
    if env_lang and env_lang.lower() not in ("all", "*"):
        return [env_lang]
    return list(discover_languages(load_sg_report(excel)["mapping"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate editable GB Report DOCX")
    parser.add_argument("--language", choices=["English", "French", "Spanish", "Arabic"])
    parser.add_argument("--all-languages", action="store_true",
                        help="Generate one editable DOCX per Excel language")
    parser.add_argument("--excel", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--sections", nargs="+", choices=SECTION_CODES)
    args = parser.parse_args()

    excel = resolve_excel(args.excel)
    languages = _resolve_languages(excel, args)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, Path] = {}
    for language in languages:
        output = OUTPUT_DIR / docx_filename(language)
        if args.output and len(languages) == 1:
            output = args.output
        outputs[language] = output

    try:
        max_workers = build_workers(len(languages))
        if max_workers <= 1:
            for language in languages:
                _render_one(excel, language, outputs[language], args.sections)
                print(f"[generate_report_docx] wrote {outputs[language]}")
        else:
            print(
                f"[generate_report_docx] rendering {len(languages)} languages across "
                f"{max_workers} worker process(es)"
            )
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        _render_one, excel, language, outputs[language], args.sections
                    ): language
                    for language in languages
                }
                for future in as_completed(futures):
                    language = futures[future]
                    _, output = future.result()
                    print(f"[generate_report_docx] wrote {output}")

        default_copy = OUTPUT_DIR / "gb-report.docx"
        shutil.copy2(outputs[languages[0]], default_copy)
        print(f"[generate_report_docx] wrote {default_copy} (default)")
    finally:
        cleanup_build_copy(args.excel)


if __name__ == "__main__":
    main()
