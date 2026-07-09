#!/usr/bin/env python3
"""
Build the GB Report Quarto document.

Generates figures for all Excel languages, then renders HTML with an in-page
language dropdown. Use generate_report_docx.py (or menu option 3) for Word.

Usage:
    gb-report.bat                         (interactive menu — recommended)
    python build_report.py
    python build_report.py --format html
    python build_report.py --format docx-flat   # legacy Quarto flat-image Word
    python build_report.py --figures-only
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gb_figures.config import resolve_excel, cleanup_build_copy  # noqa: E402
from gb_figures.styles import ENV_VAR, STYLE_NAMES  # noqa: E402
REPORT_DIR = ROOT / "report"
QUARTO_ENV_VAR = "GB_QUARTO_EXE"


def _quarto_exe() -> str | None:
    candidates = [
        os.environ.get(QUARTO_ENV_VAR),
        shutil.which("quarto"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)

    win_default = Path(r"C:\Program Files\Quarto\bin\quarto.exe")
    if win_default.exists():
        return str(win_default)
    return None


def _run_quarto(formats: list[str], env: dict[str, str]) -> None:
    quarto = _quarto_exe()
    if not quarto:
        raise SystemExit(
            "Quarto is not installed. Install from https://quarto.org/docs/get-started/ "
            "or run: winget install Posit.Quarto"
        )

    for fmt in formats:
        cmd = [quarto, "render", str(REPORT_DIR / "gb-report.qmd"), "--to", fmt]
        print(f"[build_report] {' '.join(cmd)}", flush=True)
        subprocess.run(cmd, check=True, cwd=REPORT_DIR, env=env)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GB Report Quarto document")
    parser.add_argument("--excel", type=Path, default=None)
    parser.add_argument("--format", dest="formats", action="append",
                        choices=["html", "docx-flat", "pdf"], default=None)
    parser.add_argument("--figures-only", action="store_true")
    parser.add_argument(
        "--style",
        choices=list(STYLE_NAMES),
        default=None,
        help="Figure visual style: classic (default), modern, or professional",
    )
    args = parser.parse_args()

    formats = args.formats or ["html"]
    env = os.environ.copy()
    env["GB_REPORT_LANGUAGE"] = "all"
    env["GB_REPORT_YEAR"] = "2026"
    env["GB_FIGURES_RENDERER"] = "html"
    if args.style:
        env[ENV_VAR] = args.style
    env["PYTHONUNBUFFERED"] = "1"
    excel = resolve_excel(args.excel)
    env["GB_REPORT_EXCEL"] = str(excel.resolve())

    if args.figures_only:
        try:
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "pre_render.py")],
                check=True,
                env=env,
                cwd=ROOT,
            )
        finally:
            cleanup_build_copy(args.excel)
        return

    quarto_formats = [f for f in formats if f in ("html", "pdf", "docx-flat")]
    if "docx-flat" in quarto_formats:
        quarto_formats = [f if f != "docx-flat" else "docx" for f in quarto_formats]

    if quarto_formats:
        # Figures and _body.qmd are generated once via Quarto pre-render hooks
        # configured in report/_quarto.yml.
        print("[build_report] rendering via Quarto (pre-render: figures + body)", flush=True)
        try:
            _run_quarto(quarto_formats, env)
            if "html" in formats:
                from package_figures import package_figures  # noqa: E402

                package_figures()
                # Word and PDF generation are independent of each other (PDF only
                # needs the HTML that Quarto already produced above), so run them
                # as concurrent subprocesses instead of waiting on one before the other.
                print(
                    "[build_report] generating editable Word documents and combined PDFs",
                    flush=True,
                )
                docx_proc = subprocess.Popen(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "generate_report_docx.py"),
                        "--all-languages",
                    ],
                    env=env,
                    cwd=ROOT,
                )
                pdf_proc = subprocess.Popen(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "generate_report_pdf.py"),
                        "--all-languages",
                    ],
                    env=env,
                    cwd=ROOT,
                )
                docx_code = docx_proc.wait()
                pdf_code = pdf_proc.wait()
                if docx_code != 0:
                    raise subprocess.CalledProcessError(docx_code, docx_proc.args)
                if pdf_code != 0:
                    raise subprocess.CalledProcessError(pdf_code, pdf_proc.args)
        finally:
            cleanup_build_copy(args.excel)


if __name__ == "__main__":
    main()
