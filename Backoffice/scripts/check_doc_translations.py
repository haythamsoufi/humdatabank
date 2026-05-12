#!/usr/bin/env python3
"""
Check translation coverage for documentation files.
Reports which files have French, Spanish, and Arabic translations.
"""
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)
from collections import defaultdict

def extract_base_name(filename):
    """Extract base name from filename, handling language variants."""
    # Pattern: name.lang.md or name.md
    match = re.match(r'^(.+?)(?:\.(fr|es|ar))?\.md$', filename)
    if match:
        return match.group(1), match.group(2)
    return filename, None

def check_translations(docs_dir):
    """Check translation coverage for all markdown files."""
    docs_path = Path(docs_dir)

    # Group files by base name
    files_by_base = defaultdict(lambda: {'en': False, 'fr': False, 'es': False, 'ar': False, 'path': None})

    # Find all markdown files (excluding archive, _schema, and meta files)
    for md_file in docs_path.rglob('*.md'):
        # Skip archive, schema files, and meta documentation
        if 'archive' in md_file.parts:
            continue
        if md_file.name.startswith('_'):
            continue
        if md_file.name in ['DOCUMENTATION_IMPROVEMENT_PLAN.md', 'AUTHORING_GUIDE.md']:
            continue

        base_name, lang = extract_base_name(md_file.name)
        rel_path = md_file.relative_to(docs_path)

        # Use the directory path + base name as the key
        key = str(rel_path.parent / base_name) if rel_path.parent != Path('.') else base_name

        if key not in files_by_base or files_by_base[key]['path'] is None:
            files_by_base[key]['path'] = str(rel_path.parent / base_name)

        if lang is None:
            files_by_base[key]['en'] = True
        elif lang in ['fr', 'es', 'ar']:
            files_by_base[key][lang] = True

    # Generate report
    missing_translations = {
        'fr': [],
        'es': [],
        'ar': []
    }

    all_files = []

    for key, info in sorted(files_by_base.items()):
        if not info['en']:
            continue  # Skip if no English version

        all_files.append({
            'path': info['path'],
            'en': info['en'],
            'fr': info['fr'],
            'es': info['es'],
            'ar': info['ar']
        })

        if not info['fr']:
            missing_translations['fr'].append(info['path'])
        if not info['es']:
            missing_translations['es'].append(info['path'])
        if not info['ar']:
            missing_translations['ar'].append(info['path'])

    return all_files, missing_translations

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    docs_dir = Path(__file__).parent / 'docs'

    all_files, missing = check_translations(docs_dir)

    logger.info("=" * 80)
    logger.info("DOCUMENTATION TRANSLATION COVERAGE REPORT")
    logger.info("=" * 80)
    logger.info("")

    # Summary
    total = len(all_files)
    with_fr = sum(1 for f in all_files if f['fr'])
    with_es = sum(1 for f in all_files if f['es'])
    with_ar = sum(1 for f in all_files if f['ar'])
    fully_translated = sum(1 for f in all_files if f['fr'] and f['es'] and f['ar'])

    logger.info("Total documentation files: %d", total)
    logger.info("Files with French translation: %d (%.1f%%)", with_fr, with_fr/total*100)
    logger.info("Files with Spanish translation: %d (%.1f%%)", with_es, with_es/total*100)
    logger.info("Files with Arabic translation: %d (%.1f%%)", with_ar, with_ar/total*100)
    logger.info("Fully translated (FR+ES+AR): %d (%.1f%%)", fully_translated, fully_translated/total*100)
    logger.info("")

    # Files missing translations
    logger.info("=" * 80)
    logger.info("FILES MISSING FRENCH TRANSLATION")
    logger.info("=" * 80)
    if missing['fr']:
        for path in sorted(missing['fr']):
            logger.info("  - %s.md", path)
    else:
        logger.info("  All files have French translations!")
    logger.info("")

    logger.info("=" * 80)
    logger.info("FILES MISSING SPANISH TRANSLATION")
    logger.info("=" * 80)
    if missing['es']:
        for path in sorted(missing['es']):
            logger.info("  - %s.md", path)
    else:
        logger.info("  All files have Spanish translations!")
    logger.info("")

    logger.info("=" * 80)
    logger.info("FILES MISSING ARABIC TRANSLATION")
    logger.info("=" * 80)
    if missing['ar']:
        for path in sorted(missing['ar']):
            logger.info("  - %s.md", path)
    else:
        logger.info("  All files have Arabic translations!")
    logger.info("")

    # Files with all translations
    logger.info("=" * 80)
    logger.info("FILES WITH ALL TRANSLATIONS (FR+ES+AR)")
    logger.info("=" * 80)
    fully_translated_files = [f for f in all_files if f['fr'] and f['es'] and f['ar']]
    if fully_translated_files:
        for f in sorted(fully_translated_files, key=lambda x: x['path']):
            logger.info("  %s.md", f['path'])
    else:
        logger.info("  No files are fully translated.")
    logger.info("")
