#!/usr/bin/env python3
"""
Script to update all template files to use static_url() instead of url_for('static', ...).

This ensures all static files get version query parameters for proper caching.
"""

import logging
import os
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Pattern to match url_for('static', filename='...')
PATTERN = re.compile(
    r"url_for\s*\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"]+)['\"]\s*\)",
    re.IGNORECASE
)

# Pattern to match absolute static paths /static/...
ABSOLUTE_PATTERN = re.compile(
    r"['\"]/static/([^'\"]+)['\"]",
    re.IGNORECASE
)

def replace_url_for_static(content):
    """Replace url_for('static', filename='...') with static_url('...')."""
    def replacer(match):
        filename = match.group(1)
        return f"static_url('{filename}')"

    return PATTERN.sub(replacer, content)

def replace_absolute_static_paths(content):
    """Replace absolute /static/... paths with static_url('...')."""
    def replacer(match):
        filename = match.group(1)
        return f"static_url('{filename}')"

    return ABSOLUTE_PATTERN.sub(replacer, content)

def process_file(file_path):
    """Process a single template file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content

        # Replace url_for('static', filename='...')
        content = replace_url_for_static(content)

        # Replace absolute /static/... paths (but be careful with ES6 imports)
        # Only replace in href, src, and similar attributes, not in import statements
        lines = content.split('\n')
        new_lines = []
        for line in lines:
            # Skip ES6 import statements - they need absolute paths
            if 'import' in line and 'from' in line and '/static/' in line:
                new_lines.append(line)
            else:
                # Replace absolute paths in other contexts
                new_line = replace_absolute_static_paths(line)
                new_lines.append(new_line)

        content = '\n'.join(new_lines)

        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        logger.error("Error processing %s: %s", file_path, e)
        return False

def main():
    """Main function to process all template files."""
    # Get the project root directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    templates_dir = project_root / 'app' / 'templates'

    if not templates_dir.exists():
        logger.error("Templates directory not found: %s", templates_dir)
        sys.exit(1)

    logger.info("Scanning templates directory: %s", templates_dir)
    logger.info("-" * 70)

    # Find all HTML template files
    template_files = list(templates_dir.rglob('*.html'))

    if not template_files:
        logger.info("No template files found.")
        sys.exit(0)

    logger.info("Found %d template files", len(template_files))
    logger.info("-" * 70)

    updated_files = []
    skipped_files = []

    for template_file in template_files:
        # Skip backup files
        if 'backup' in str(template_file).lower():
            skipped_files.append(template_file)
            continue

        relative_path = template_file.relative_to(project_root)
        if process_file(template_file):
            updated_files.append(relative_path)
            logger.info("Updated: %s", relative_path)
        else:
            # File didn't need updating
            pass

    logger.info("-" * 70)
    logger.info("Summary:")
    logger.info("  Updated: %d files", len(updated_files))
    logger.info("  Skipped (backup files): %d files", len(skipped_files))
    logger.info("  Total processed: %d files", len(template_files))

    if updated_files:
        logger.info("Updated files:")
        for file in updated_files:
            logger.info("  - %s", file)

    logger.info("Done! All static file references now use static_url() for versioning.")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
