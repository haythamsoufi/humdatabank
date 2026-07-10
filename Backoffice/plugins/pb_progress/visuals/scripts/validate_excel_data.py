#!/usr/bin/env python3
"""Check that Final, Mapping, and TotalReported join correctly."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.config import resolve_excel
from pb_figures.data import DataModelError, build_model, load_sg_report


def main() -> None:
    excel = resolve_excel()
    print(f"Workbook: {excel}")

    sheets = load_sg_report(excel)
    final = sheets["final"]
    mapping = sheets["mapping"]
    print(f"  Final: {len(final)} rows, {len(final.columns)} columns")
    print(f"  Mapping: {len(mapping)} rows, {len(mapping.columns)} columns")

    try:
        model = build_model(excel)
    except DataModelError as exc:
        raise SystemExit(f"\nData model error:\n  {exc}") from exc

    sections = sorted(model["section"].dropna().astype(str).unique())
    ids = model["ID"].nunique()
    print(f"\nJoin OK: {len(model)} rows, {ids} indicators")
    print(f"Sections: {', '.join(sections)}")


if __name__ == "__main__":
    main()
