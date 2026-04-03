#!/usr/bin/env python3
"""
Test script for static file caching headers.

This script verifies that:
1. Versioned static files get long cache headers (1 year, immutable)
2. Unversioned static files get short cache headers (1 hour, must-revalidate)
3. ETags are present for static files
4. Cache headers are correctly set for different file types

Usage:
    python scripts/test_static_cache.py [--base-url BASE_URL] [--verbose]
"""

import argparse
import logging
import os
import sys
import requests

logger = logging.getLogger(__name__)
from urllib.parse import urljoin

# Add parent directory to path to import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Test files to check
TEST_FILES = [
    'css/output.css',
    'css/forms.css',
    'css/layout.css',
    'js/layout.js',
    'js/csrf.js',
    'js/chatbot.js',
]

# Expected cache headers
VERSIONED_CACHE_HEADERS = {
    'max-age': '31536000',  # 1 year in seconds
    'public': True,
    'immutable': True,
}

UNVERSIONED_CACHE_HEADERS = {
    'max-age': '3600',  # 1 hour in seconds
    'public': True,
    'must-revalidate': True,
}


def parse_cache_control(header_value):
    """Parse Cache-Control header into a dictionary."""
    if not header_value:
        return {}

    directives = {}
    for part in header_value.split(','):
        part = part.strip()
        if '=' in part:
            key, value = part.split('=', 1)
            directives[key.strip().lower()] = value.strip()
        else:
            directives[part.strip().lower()] = True

    return directives


def check_cache_headers(response, expected_headers, file_path, versioned=True):
    """Check if response has expected cache headers."""
    cache_control = response.headers.get('Cache-Control', '')
    parsed = parse_cache_control(cache_control)

    issues = []
    warnings = []

    # Check each expected header
    for key, expected_value in expected_headers.items():
        actual_value = parsed.get(key)

        if actual_value is None:
            issues.append(f"Missing '{key}' directive")
        elif isinstance(expected_value, bool) and actual_value is not True:
            issues.append(f"'{key}' should be present but got: {actual_value}")
        elif isinstance(expected_value, str) and str(actual_value) != expected_value:
            issues.append(f"'{key}' should be '{expected_value}' but got '{actual_value}'")

    # Check ETag presence
    etag = response.headers.get('ETag')
    if not etag:
        warnings.append("ETag header missing (Flask should add this automatically)")

    # Check Last-Modified presence
    last_modified = response.headers.get('Last-Modified')
    if not last_modified:
        warnings.append("Last-Modified header missing")

    return issues, warnings, parsed


def test_static_file(base_url, file_path, versioned=True, verbose=False):
    """Test a single static file."""
    if versioned:
        url = urljoin(base_url, f'/static/{file_path}?v=1.0')
        expected_headers = VERSIONED_CACHE_HEADERS
        test_type = "versioned"
    else:
        url = urljoin(base_url, f'/static/{file_path}')
        expected_headers = UNVERSIONED_CACHE_HEADERS
        test_type = "unversioned"

    try:
        response = requests.head(url, timeout=10, allow_redirects=True)

        if response.status_code != 200:
            return {
                'file': file_path,
                'type': test_type,
                'status': 'ERROR',
                'message': f"HTTP {response.status_code}: {response.reason}",
                'url': url
            }

        issues, warnings, parsed_headers = check_cache_headers(
            response, expected_headers, file_path, versioned
        )

        if issues:
            return {
                'file': file_path,
                'type': test_type,
                'status': 'FAIL',
                'issues': issues,
                'warnings': warnings,
                'cache_control': response.headers.get('Cache-Control', ''),
                'parsed_headers': parsed_headers,
                'etag': response.headers.get('ETag', 'N/A'),
                'url': url
            }
        else:
            return {
                'file': file_path,
                'type': test_type,
                'status': 'PASS',
                'warnings': warnings,
                'cache_control': response.headers.get('Cache-Control', ''),
                'etag': response.headers.get('ETag', 'N/A'),
                'url': url
            }

    except requests.exceptions.RequestException as e:
        return {
            'file': file_path,
            'type': test_type,
            'status': 'ERROR',
            'message': f"Request failed: {str(e)}",
            'url': url
        }


def print_result(result, verbose=False):
    """Print test result in a readable format."""
    status_symbols = {
        'PASS': '✓',
        'FAIL': '✗',
        'ERROR': '⚠'
    }

    symbol = status_symbols.get(result['status'], '?')
    logger.info("%s %s (%s)", symbol, result['file'], result['type'])

    if result['status'] == 'PASS':
        if verbose:
            logger.info("   Cache-Control: %s", result.get('cache_control', 'N/A'))
            logger.info("   ETag: %s", result.get('etag', 'N/A'))
            if result.get('warnings'):
                for warning in result['warnings']:
                    logger.warning("   Warning: %s", warning)

    elif result['status'] == 'FAIL':
        logger.info("   URL: %s", result.get('url', 'N/A'))
        logger.info("   Cache-Control: %s", result.get('cache_control', 'N/A'))
        if result.get('issues'):
            logger.info("   Issues:")
            for issue in result['issues']:
                logger.info("     - %s", issue)
        if result.get('warnings'):
            for warning in result['warnings']:
                logger.warning("   Warning: %s", warning)

    elif result['status'] == 'ERROR':
        logger.error("   %s", result.get('message', 'Unknown error'))
        if verbose and result.get('url'):
            logger.info("   URL: %s", result.get('url', 'N/A'))


def main():
    parser = argparse.ArgumentParser(
        description='Test static file caching headers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test against local development server
  python scripts/test_static_cache.py

  # Test against production
  python scripts/test_static_cache.py --base-url https://example.com

  # Verbose output
  python scripts/test_static_cache.py --verbose
        """
    )
    parser.add_argument(
        '--base-url',
        default='http://localhost:5000',
        help='Base URL of the application (default: http://localhost:5000)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed output including cache headers'
    )
    parser.add_argument(
        '--files',
        nargs='+',
        help='Specific files to test (default: all test files)'
    )
    parser.add_argument(
        '--versioned-only',
        action='store_true',
        help='Only test versioned files'
    )
    parser.add_argument(
        '--unversioned-only',
        action='store_true',
        help='Only test unversioned files'
    )

    args = parser.parse_args()

    # Determine which files to test
    files_to_test = args.files if args.files else TEST_FILES

    # Determine test types
    # Default to versioned-only since all templates now use static_url()
    test_versioned = not args.unversioned_only
    test_unversioned = args.unversioned_only  # Only test unversioned if explicitly requested

    logger.info("Testing static file caching for: %s", args.base_url)
    logger.info("Files: %s", ', '.join(files_to_test))
    if not args.unversioned_only and not args.versioned_only:
        logger.info("Note: Testing versioned files only (default). Use --unversioned-only to test fallback behavior.")
    logger.info("-" * 70)

    results = []

    # Test each file
    for file_path in files_to_test:
        if test_versioned:
            result = test_static_file(args.base_url, file_path, versioned=True, verbose=args.verbose)
            results.append(result)
            print_result(result, verbose=args.verbose)

        if test_unversioned:
            result = test_static_file(args.base_url, file_path, versioned=False, verbose=args.verbose)
            results.append(result)
            print_result(result, verbose=args.verbose)

    logger.info("-" * 70)

    # Summary
    passed = sum(1 for r in results if r['status'] == 'PASS')
    failed = sum(1 for r in results if r['status'] == 'FAIL')
    errors = sum(1 for r in results if r['status'] == 'ERROR')
    total = len(results)

    logger.info("Summary: %d/%d passed, %d failed, %d errors", passed, total, failed, errors)

    if failed > 0 or errors > 0:
        logger.warning("Failed/Error details:")
        for result in results:
            if result['status'] in ('FAIL', 'ERROR'):
                logger.warning("%s (%s):", result['file'], result['type'])
                if result['status'] == 'FAIL':
                    for issue in result.get('issues', []):
                        logger.warning("  - %s", issue)
                else:
                    logger.warning("  - %s", result.get('message', 'Unknown error'))

        sys.exit(1)
    else:
        logger.info("All tests passed!")
        sys.exit(0)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
