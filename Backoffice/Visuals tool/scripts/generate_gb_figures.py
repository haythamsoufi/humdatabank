#!/usr/bin/env python3
"""
Generate GB Report figures from SG Report.xlsx without Tableau.
Each SP/EF section produces one combined dashboard image.

Usage:
    python generate_gb_figures.py --language English --sections EF1 SP1
    python generate_gb_figures.py --all
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import matplotlib.pyplot as plt

from gb_figures.charts import render_dashboard
from gb_figures.config import DEFAULT_EXCEL, DEFAULT_OUTPUT, LANGUAGES
from gb_figures.data import build_model
from gb_figures.layouts import SECTION_CODES
from gb_figures.styles import ENV_VAR, STYLE_NAMES


def generate_section(
    model,
    section: str,
    language: str,
    output_dir: Path,
    renderer: str = "html",
) -> Path:
    lang_dir = output_dir / language
    lang_dir.mkdir(parents=True, exist_ok=True)
    path = lang_dir / f"{section}.png"
    render_dashboard(model, section, language=language, output_path=path, renderer=renderer)
    if renderer == "matplotlib":
        plt.close("all")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate GB figures from SG Report.xlsx")
    parser.add_argument("--excel", type=Path, default=DEFAULT_EXCEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--language", choices=LANGUAGES, default="English")
    parser.add_argument("--sections", nargs="+", choices=SECTION_CODES)
    parser.add_argument("--all", action="store_true", help="Generate all sections")
    parser.add_argument(
        "--renderer",
        choices=["html", "matplotlib"],
        default="html",
        help="html = publication SVG/CSS (default); matplotlib = legacy",
    )
    parser.add_argument(
        "--style",
        choices=list(STYLE_NAMES),
        default=None,
        help="Figure visual style: classic (default), modern, or professional",
    )
    args = parser.parse_args()

    if args.style:
        os.environ[ENV_VAR] = args.style

    sections = SECTION_CODES if args.all else (args.sections or ["EF1"])
    model = build_model(args.excel)

    print(f"Loaded model: {len(model)} rows from {args.excel}")
    for section in sections:
        path = generate_section(model, section, args.language, args.output, args.renderer)
        print(f"  wrote {path}")


if __name__ == "__main__":
    main()
