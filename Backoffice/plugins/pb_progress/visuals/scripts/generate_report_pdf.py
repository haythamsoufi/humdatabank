#!/usr/bin/env python3
"""Generate combined PDF reports from the built HTML output."""

from __future__ import annotations

import argparse
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.config import build_workers, cleanup_build_copy, resolve_excel, resolve_report_output
from pb_figures.languages import LANGUAGES, pdf_filename, resolve_build_languages
from pb_figures.render_pdf import render_report_pdf

OUTPUT_DIR = ROOT / "report" / "output"
HTML_REPORT = OUTPUT_DIR / "pb-report.html"


def _output_dir() -> Path:
    return resolve_report_output()


def _html_report() -> Path:
    return _output_dir() / "pb-report.html"


def _render_one(html_path: Path, output_path: Path, language: str) -> tuple[str, Path]:
    """Worker: render one language's PDF via WeasyPrint."""
    render_report_pdf(html_path, output_path, language=language)
    return language, output_path


def _resolve_languages(excel: Path, args: argparse.Namespace) -> list[str]:
    if args.language:
        return [args.language]
    if args.all_languages:
        return list(LANGUAGES)
    return list(resolve_build_languages(excel))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate combined P&B Report PDF")
    parser.add_argument("--language", choices=["English", "French", "Spanish", "Arabic"])
    parser.add_argument(
        "--all-languages",
        action="store_true",
        help="Generate one combined PDF per Excel language",
    )
    parser.add_argument("--excel", type=Path, default=None)
    parser.add_argument("--html", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    excel = resolve_excel(args.excel)
    languages = _resolve_languages(excel, args)
    output_dir = _output_dir()
    html_path = args.html or _html_report()

    if not html_path.is_file():
        raise SystemExit(
            f"HTML report not found: {html_path}\n"
            "Run build_report.py --format html first."
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, Path] = {}
    for language in languages:
        output = output_dir / pdf_filename(language)
        if args.output and len(languages) == 1:
            output = args.output
        outputs[language] = output

    try:
        max_workers = build_workers(len(languages))
        if max_workers <= 1:
            for language in languages:
                _render_one(html_path, outputs[language], language)
                print(f"[generate_report_pdf] wrote {outputs[language]}")
        else:
            print(
                f"[generate_report_pdf] rendering {len(languages)} languages across "
                f"{max_workers} worker process(es)"
            )
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(_render_one, html_path, outputs[language], language): language
                    for language in languages
                }
                for future in as_completed(futures):
                    language = futures[future]
                    _, output = future.result()
                    print(f"[generate_report_pdf] wrote {output}")

        default_copy = output_dir / "pb-report.pdf"
        shutil.copy2(outputs[languages[0]], default_copy)
        print(f"[generate_report_pdf] wrote {default_copy} (default)")
    finally:
        cleanup_build_copy(args.excel)


if __name__ == "__main__":
    main()
