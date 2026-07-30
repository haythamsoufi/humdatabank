#!/usr/bin/env python3
"""Package dashboard PNGs into ZIP archives for HTML report download links."""

from __future__ import annotations

import zipfile
from pathlib import Path

from pb_figures.config import resolve_figures_output, resolve_report_output

ROOT = Path(__file__).resolve().parents[1]


def _language_slug(language: str) -> str:
    return language.lower().replace(" ", "-")


def package_figures(
    figures_dir: Path = FIGURES_DIR,
    output_dir: Path = OUTPUT_DIR,
    *,
    languages: tuple[str, ...] | None = None,
) -> list[Path]:
    """Create per-language and all-languages ZIP files in output_dir."""
    if not figures_dir.is_dir():
        raise FileNotFoundError(f"Figures directory not found: {figures_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    discovered = sorted(
        p.name for p in figures_dir.iterdir() if p.is_dir() and any(p.glob("*.png"))
    )
    if languages:
        lang_dirs = [lang for lang in languages if (figures_dir / lang).is_dir()]
    else:
        lang_dirs = discovered

    created: list[Path] = []
    all_members: list[tuple[Path, str]] = []

    for language in lang_dirs:
        lang_path = figures_dir / language
        png_files = sorted(lang_path.glob("*.png"))
        if not png_files:
            continue

        zip_path = output_dir / f"pb-report-figures-{_language_slug(language)}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for png in png_files:
                arcname = f"{language}/{png.name}"
                zf.write(png, arcname=arcname)
                all_members.append((png, arcname))
        created.append(zip_path)
        print(f"[package_figures] {zip_path.name} ({len(png_files)} PNGs)", flush=True)

    if all_members:
        all_zip = output_dir / "pb-report-figures-all.zip"
        with zipfile.ZipFile(all_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for png, arcname in all_members:
                zf.write(png, arcname=arcname)
        created.append(all_zip)
        print(f"[package_figures] {all_zip.name} ({len(all_members)} PNGs)", flush=True)

    return created


def main() -> None:
    package_figures(resolve_figures_output(), resolve_report_output())


if __name__ == "__main__":
    main()
