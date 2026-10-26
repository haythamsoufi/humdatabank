#!/usr/bin/env python3
"""Package per-language DOCX and PDF reports into all-languages ZIP archives."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "report" / "output"

# Default copies without a language slug — duplicates of English, not bundled.
_DEFAULT_NAMES = frozenset({"pb-report.docx", "pb-report.pdf", "gb-report.docx", "gb-report.pdf"})


def _collect_language_files(output_dir: Path, suffix: str) -> list[Path]:
    return sorted(
        p
        for p in output_dir.glob(f"pb-report-*{suffix}")
        if p.is_file() and p.name not in _DEFAULT_NAMES
    )


def package_documents(output_dir: Path = OUTPUT_DIR) -> list[Path]:
    """Create all-languages ZIP bundles for DOCX and PDF outputs in output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    for suffix, zip_name in ((".docx", "pb-report-docx-all.zip"), (".pdf", "pb-report-pdf-all.zip")):
        files = _collect_language_files(output_dir, suffix)
        if not files:
            continue
        zip_path = output_dir / zip_name
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in files:
                zf.write(path, arcname=path.name)
        created.append(zip_path)
        print(f"[package_documents] {zip_path.name} ({len(files)} files)", flush=True)

    return created


def main() -> None:
    package_documents()


if __name__ == "__main__":
    main()
