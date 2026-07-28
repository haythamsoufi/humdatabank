#!/usr/bin/env python3
"""
Audit script to find unversioned static file references and potential caching issues.

This script scans:
1. Template files for unversioned static references
2. JavaScript files for hardcoded static paths
3. Service worker cache lists
4. Any other potential issues
"""

import logging
import os
import re
import sys
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)

# Patterns to find
PATTERNS = {
    'url_for_static': re.compile(
        r"url_for\s*\(\s*['\"]static['\"]\s*,\s*filename\s*=",
        re.IGNORECASE
    ),
    'absolute_static_path': re.compile(
        r"['\"]/static/([^'\"]+)['\"]",
        re.IGNORECASE
    ),
    'relative_static_path': re.compile(
        r"['\"]\.\.?/static/([^'\"]+)['\"]",
        re.IGNORECASE
    ),
    'static_url_correct': re.compile(
        r"static_url\s*\(",
        re.IGNORECASE
    ),
}

# Files to exclude from scanning
EXCLUDE_PATTERNS = [
    r'.*backup.*',
    r'.*\.pyc$',
    r'.*__pycache__.*',
    r'.*node_modules.*',
    r'.*\.git.*',
]

def should_exclude(file_path):
    """Check if file should be excluded from scanning."""
    path_str = str(file_path)
    for pattern in EXCLUDE_PATTERNS:
        if re.search(pattern, path_str, re.IGNORECASE):
            return True
    return False

def scan_file(file_path, patterns):
    """Scan a file for pattern matches."""
    issues = defaultdict(list)

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            lines = content.split('\n')

        for line_num, line in enumerate(lines, 1):
            # Check for url_for('static', ...)
            if patterns['url_for_static'].search(line):
                # Check if it's in a comment
                if not line.strip().startswith('#'):
                    issues['unversioned_url_for'].append({
                        'line': line_num,
                        'content': line.strip()[:100]
                    })

            # Check for absolute /static/ paths (but allow ES6 imports and getStaticUrl usage)
            if patterns['absolute_static_path'].search(line):
                # Skip ES6 import statements (they need absolute paths)
                if 'import' in line and 'from' in line:
                    continue
                # Skip lines that use window.getStaticUrl() - these are properly versioned
                if 'getStaticUrl' in line:
                    continue
                # Skip service worker cache list - versioning handled by CACHE_VERSION
                if 'CORE_ASSETS' in line or 'EXTERNAL_RESOURCES' in line:
                    continue
                issues['absolute_paths'].append({
                    'line': line_num,
                    'content': line.strip()[:100]
                })

            # Check for relative static paths
            if patterns['relative_static_path'].search(line):
                issues['relative_paths'].append({
                    'line': line_num,
                    'content': line.strip()[:100]
                })

    except Exception as e:
        issues['errors'].append(f"Error reading {file_path}: {e}")

    return issues

def scan_service_worker():
    """Scan service worker for unversioned static file references."""
    sw_path = Path('app/static/js/sw.js')
    issues = []

    if not sw_path.exists():
        return issues

    try:
        with open(sw_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check CORE_ASSETS array for unversioned paths
        core_assets_match = re.search(
            r'const\s+CORE_ASSETS\s*=\s*\[(.*?)\];',
            content,
            re.DOTALL
        )

        if core_assets_match:
            # Check if CACHE_VERSION is defined (indicates versioning strategy)
            has_cache_version = 'CACHE_VERSION' in content or 'cache_version' in content.lower()

            assets = core_assets_match.group(1)
            # Find all /static/ paths
            static_paths = re.findall(r"'/static/([^']+)'", assets)
            for path in static_paths:
                # If cache versioning is used, this is acceptable (cache name changes invalidate cache)
                if has_cache_version:
                    issues.append({
                        'type': 'service_worker_info',
                        'file': 'app/static/js/sw.js',
                        'path': f'/static/{path}',
                        'note': 'Service worker uses cache versioning (CACHE_VERSION) - paths don\'t need versioning'
                    })
                else:
                    issues.append({
                        'type': 'service_worker_unversioned',
                        'file': 'app/static/js/sw.js',
                        'path': f'/static/{path}',
                        'note': 'Service worker cache list contains unversioned paths - consider using CACHE_VERSION'
                    })

    except Exception as e:
        issues.append({
            'type': 'error',
            'file': 'app/static/js/sw.js',
            'error': str(e)
        })

    return issues

def scan_javascript_files():
    """Scan JavaScript files for hardcoded static paths."""
    js_dir = Path('app/static/js')
    issues = []

    if not js_dir.exists():
        return issues

    for js_file in js_dir.rglob('*.js'):
        if should_exclude(js_file):
            continue

        try:
            with open(js_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')

            # Check if this is a service worker with cache versioning
            is_service_worker = 'sw.js' in str(js_file)
            has_cache_version = 'CACHE_VERSION' in content or 'cache_version' in content.lower()

            for line_num, line in enumerate(lines, 1):
                # Check for /static/ paths in JavaScript (excluding ES6 imports)
                if '/static/' in line and 'import' not in line:
                    # Skip service worker cache lists if cache versioning is used
                    if is_service_worker and has_cache_version:
                        if 'CORE_ASSETS' in line or 'EXTERNAL_RESOURCES' in line or line.strip().startswith("'/"):
                            continue

                    # Check if it's a string literal
                    if re.search(r"['\"]/static/[^'\"]+['\"]", line):
                        # Skip if getStaticUrl is used (even with fallback)
                        if 'getStaticUrl' in line:
                            continue
                        issues.append({
                            'type': 'js_hardcoded_path',
                            'file': str(js_file.relative_to(Path('.'))),
                            'line': line_num,
                            'content': line.strip()[:100]
                        })

        except Exception as e:
            issues.append({
                'type': 'error',
                'file': str(js_file),
                'error': str(e)
            })

    return issues

def main():
    """Main audit function."""
    project_root = Path('.')
    templates_dir = project_root / 'app' / 'templates'

    logger.info("=" * 70)
    logger.info("Static File Versioning Audit")
    logger.info("=" * 70)
    logger.info("")

    all_issues = defaultdict(list)

    # Scan template files
    logger.info("Scanning template files...")
    if templates_dir.exists():
        template_files = list(templates_dir.rglob('*.html'))
        for template_file in template_files:
            if should_exclude(template_file):
                continue

            issues = scan_file(template_file, PATTERNS)
            if issues:
                relative_path = template_file.relative_to(project_root)
                for issue_type, issue_list in issues.items():
                    for issue in issue_list:
                        issue['file'] = str(relative_path)
                        all_issues[issue_type].append(issue)

    # Scan service worker
    logger.info("Scanning service worker...")
    sw_issues = scan_service_worker()
    for issue in sw_issues:
        all_issues[issue['type']].append(issue)

    # Scan JavaScript files
    logger.info("Scanning JavaScript files...")
    js_issues = scan_javascript_files()
    for issue in js_issues:
        all_issues[issue['type']].append(issue)

    # Report results
    logger.info("")
    logger.info("=" * 70)
    logger.info("Audit Results")
    logger.info("=" * 70)
    logger.info("")

    # Count only actual issues (exclude info messages)
    total_issues = sum(
        len(issues) for key, issues in all_issues.items()
        if key != 'service_worker_info'
    )

    if total_issues == 0:
        logger.info("✓ No issues found! All static files appear to be properly versioned.")
        logger.info("")
        return 0

    # Group and report issues
    if all_issues.get('unversioned_url_for'):
        logger.warning("Found %d unversioned url_for('static', ...) calls:", len(all_issues['unversioned_url_for']))
        for issue in all_issues['unversioned_url_for'][:10]:  # Show first 10
            logger.warning("  - %s:%s", issue['file'], issue['line'])
            logger.warning("    %s", issue['content'])
        if len(all_issues['unversioned_url_for']) > 10:
            logger.warning("  ... and %d more", len(all_issues['unversioned_url_for']) - 10)
        logger.info("")

    if all_issues.get('absolute_paths'):
        logger.warning("Found %d absolute /static/ paths:", len(all_issues['absolute_paths']))
        for issue in all_issues['absolute_paths'][:10]:
            logger.warning("  - %s:%s", issue['file'], issue['line'])
            logger.warning("    %s", issue['content'])
        if len(all_issues['absolute_paths']) > 10:
            logger.warning("  ... and %d more", len(all_issues['absolute_paths']) - 10)
        logger.info("")

    if all_issues.get('relative_paths'):
        logger.warning("Found %d relative static paths:", len(all_issues['relative_paths']))
        for issue in all_issues['relative_paths'][:10]:
            logger.warning("  - %s:%s", issue['file'], issue['line'])
            logger.warning("    %s", issue['content'])
        if len(all_issues['relative_paths']) > 10:
            logger.warning("  ... and %d more", len(all_issues['relative_paths']) - 10)
        logger.info("")

    # Separate service worker issues by type
    sw_unversioned = [i for i in all_issues.get('service_worker_unversioned', [])]
    sw_info = [i for i in all_issues.get('service_worker_info', [])]

    if sw_unversioned:
        logger.warning("Service Worker has %d unversioned paths:", len(sw_unversioned))
        for issue in sw_unversioned[:10]:
            logger.warning("  - %s", issue['path'])
        if len(sw_unversioned) > 10:
            logger.warning("  ... and %d more", len(sw_unversioned) - 10)
        logger.info("")
        logger.info("  Note: Consider using CACHE_VERSION to invalidate cache when static files change.")
        logger.info("")

    if sw_info:
        logger.info("Service Worker uses cache versioning (%d paths):", len(sw_info))
        logger.info("  Cache versioning strategy is in place - paths don't need version query parameters.")
        logger.info("  Remember to update CACHE_VERSION when static files change.")
        logger.info("")

    # Filter out JavaScript files that use getStaticUrl
    js_issues_filtered = []
    for issue in all_issues.get('js_hardcoded_path', []):
        # Check if the content shows getStaticUrl usage
        if 'getStaticUrl' not in issue.get('content', ''):
            js_issues_filtered.append(issue)

    if js_issues_filtered:
        logger.warning("Found %d hardcoded static paths in JavaScript (not using getStaticUrl):", len(js_issues_filtered))
        for issue in js_issues_filtered[:10]:
            logger.warning("  - %s:%s", issue['file'], issue['line'])
            logger.warning("    %s", issue['content'])
        if len(js_issues_filtered) > 10:
            logger.warning("  ... and %d more", len(js_issues_filtered) - 10)
        logger.info("")
    elif all_issues.get('js_hardcoded_path'):
        logger.info("✓ JavaScript files are using getStaticUrl() helper for versioning")
        logger.info("")

    if all_issues.get('errors'):
        logger.warning("Errors encountered:")
        for issue in all_issues['errors']:
            logger.warning("  - %s", issue)
        logger.info("")

    logger.info("=" * 70)
    logger.info("Total issues found: %d", total_issues)
    logger.info("=" * 70)
    logger.info("")
    logger.info("Recommendations:")
    logger.info("1. Replace url_for('static', ...) with static_url() in templates")
    logger.info("2. Update hardcoded /static/ paths to use dynamic versioning")
    logger.info("3. Consider updating service worker cache lists to include versions")
    logger.info("4. Review JavaScript files for dynamic static file loading")
    logger.info("")

    return 1 if total_issues > 0 else 0

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main())
