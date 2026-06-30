#!/usr/bin/env python3
"""
Generate missing documentation translations from English sources.

Preserves markdown structure: code fences, inline code, link targets, and paths
are left unchanged; visible text is translated via the app's AutoTranslator.

Usage:
  python scripts/translate_user_guide_docs.py
  python scripts/translate_user_guide_docs.py --lang ru
  python scripts/translate_user_guide_docs.py --section getting-started,data-reporting --lang ru
  python scripts/translate_user_guide_docs.py --dry-run
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

DOCS_LANGS = ("ar", "es", "fr", "ru")

DEFAULT_SECTIONS = ("user-guides", "getting-started", "data-reporting")
LANG_PATTERN = re.compile(r"^(.+?)(?:\.(fr|es|ar|ru))?\.md$")

# Protect segments that must not be sent to the translator.
_PLACEHOLDER_RE = re.compile(r"(\{\{MDPH\d+\}\})")


def _split_base_lang(filename: str) -> tuple[str | None, str | None]:
    match = LANG_PATTERN.match(filename)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def collect_doc_bases(docs_dir: Path, *, include_readme: bool = True) -> dict[str, set[str | None]]:
    """Map base rel path (e.g. admin/add-user) -> set of lang codes (None = en)."""
    by_base: dict[str, set[str | None]] = {}
    for md_file in docs_dir.rglob("*.md"):
        if not include_readme and md_file.name.lower() == "readme.md":
            continue
        base_name, lang = _split_base_lang(md_file.name)
        if base_name is None:
            continue
        rel = md_file.relative_to(docs_dir)
        key = str(rel.parent / base_name).replace("\\", "/")
        by_base.setdefault(key, set()).add(lang)
    return by_base


def missing_translations(
    by_base: dict[str, set[str | None]], langs: tuple[str, ...]
) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {lang: [] for lang in langs}
    for key, have in sorted(by_base.items()):
        if None not in have and "en" not in have:
            # English file has no lang suffix (None marks default en).
            if None not in have:
                continue
        if None not in have:
            continue
        for lang in langs:
            if lang not in have:
                missing[lang].append(key)
    return missing


def _protect_segments(text: str) -> tuple[str, list[str]]:
    """Replace code spans, markdown links, and paths with placeholders."""
    protected: list[str] = []

    def stash(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"{{{{MDPH{len(protected) - 1}}}}}"

    text = re.sub(r"`[^`\n]+`", stash, text)
    text = re.sub(r"\[[^\]]+\]\([^)]+\)", stash, text)
    text = re.sub(r"\b(?:app/|Backoffice/)[\w./_-]+", stash, text)
    text = re.sub(r"/(?:admin|api|help)[\w./_-]*", stash, text)
    return text, protected


def _restore_segments(text: str, protected: list[str]) -> str:
    for idx, original in enumerate(protected):
        text = text.replace(f"{{{{MDPH{idx}}}}}", original)
    return text


def translate_markdown(content: str, target_lang: str, translator) -> str:
    """Translate markdown in paragraph blocks, skipping code fences."""
    lines = content.splitlines(keepends=True)
    blocks: list[tuple[str, bool]] = []  # (text, is_raw)
    current: list[str] = []
    in_fence = False
    fence_marker = ""
    fence_lines: list[str] = []

    def flush_translatable() -> None:
        if current:
            blocks.append(("".join(current), False))
            current.clear()

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```"):
            if not in_fence:
                flush_translatable()
                in_fence = True
                fence_marker = stripped[:3]
                fence_lines = [line]
            else:
                fence_lines.append(line)
                blocks.append(("".join(fence_lines), True))
                fence_lines = []
                in_fence = False
            continue
        if in_fence:
            fence_lines.append(line)
            continue
        if line.strip() == "" and current:
            current.append(line)
            flush_translatable()
        elif line.strip() == "":
            blocks.append((line, True))
        else:
            current.append(line)

    flush_translatable()

    out_parts: list[str] = []
    for text, is_raw in blocks:
        if is_raw or not text.strip():
            out_parts.append(text)
            continue

        chunks: list[str] = []
        chunk_lines: list[str] = []
        chunk_len = 0
        for line in text.splitlines(keepends=True):
            if chunk_len + len(line) > 3500 and chunk_lines:
                chunks.append("".join(chunk_lines))
                chunk_lines = [line]
                chunk_len = len(line)
            else:
                chunk_lines.append(line)
                chunk_len += len(line)
        if chunk_lines:
            chunks.append("".join(chunk_lines))

        translated_chunks: list[str] = []
        for chunk in chunks:
            protected, stash = _protect_segments(chunk)
            translated = translator(protected, target_lang) or chunk
            translated_chunks.append(_restore_segments(translated, stash))
        out_parts.append("".join(translated_chunks))

    return "".join(out_parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate documentation markdown files")
    parser.add_argument("--lang", action="append", dest="langs", help="Target language(s)")
    parser.add_argument(
        "--section",
        action="append",
        dest="sections",
        help="Doc folder under docs/ (default: user-guides, getting-started, data-reporting)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report missing only")
    parser.add_argument("--force", action="store_true", help="Overwrite existing translations")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    backoffice_root = Path(__file__).resolve().parent.parent
    docs_root = backoffice_root / "docs"
    sections = tuple(args.sections) if args.sections else DEFAULT_SECTIONS
    target_langs = tuple(args.langs) if args.langs else DOCS_LANGS

    missing_by_section: dict[str, dict[str, list[str]]] = {}
    total = 0
    for section in sections:
        section_dir = docs_root / section
        if not section_dir.is_dir():
            logger.warning("Skip missing section: %s", section_dir)
            continue
        by_base = collect_doc_bases(section_dir, include_readme=True)
        missing = missing_translations(by_base, target_langs)
        missing_by_section[section] = missing
        section_total = sum(len(v) for v in missing.values())
        total += section_total
        logger.info("Missing translations under docs/%s: %d file(s)", section, section_total)
        for lang in target_langs:
            for key in missing.get(lang, []):
                logger.info("  [%s] %s/%s", lang, section, key)

    if args.dry_run or total == 0:
        return 0

    sys.path.insert(0, str(backoffice_root))
    from app.services.translation.auto_translator import translate_text

    def translator(text: str, lang: str) -> str | None:
        if not text.strip():
            return text
        return translate_text(text, lang, "en")

    written = 0
    for section, missing in missing_by_section.items():
        section_dir = docs_root / section
        for lang in target_langs:
            for key in missing.get(lang, []):
                src_path = section_dir / f"{key}.md"
                dst_path = section_dir / f"{key}.{lang}.md"
                if not src_path.is_file():
                    logger.warning("Skip (no English source): %s", src_path)
                    continue
                if dst_path.exists() and not args.force:
                    logger.info("Skip (exists): %s", dst_path.relative_to(backoffice_root))
                    continue

                logger.info("Translating [%s] %s/%s ...", lang, section, key)
                source = src_path.read_text(encoding="utf-8")
                translated = translate_markdown(source, lang, translator)
                dst_path.write_text(translated, encoding="utf-8")
                written += 1

    logger.info("Wrote %d translation file(s).", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
