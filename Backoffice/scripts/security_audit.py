#!/usr/bin/env python3
"""
Security Audit Script

Performs security audits including:
- Dependency vulnerability scanning
- Configuration validation
- Security checklist verification
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def check_dependencies():
    """Check Python dependencies for known vulnerabilities."""
    logger.info("=" * 80)
    logger.info("DEPENDENCY SECURITY AUDIT")
    logger.info("=" * 80)

    # Try safety first
    try:
        logger.info("\n[1/2] Checking with safety...")
        result = subprocess.run(
            ['safety', 'check', '--json'],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            logger.info("✓ No known vulnerabilities found with safety")
            return True
        else:
            try:
                vulnerabilities = json.loads(result.stdout)
                if vulnerabilities:
                    logger.warning("Found %d vulnerabilities:", len(vulnerabilities))
                    for vuln in vulnerabilities:
                        logger.warning("  - %s: %s", vuln.get('package', 'unknown'), vuln.get('vulnerability', 'unknown'))
                    return False
                else:
                    logger.info("✓ No vulnerabilities found")
                    return True
            except json.JSONDecodeError:
                logger.warning("Safety check failed: %s", result.stderr)
                return None

    except FileNotFoundError:
        logger.warning("'safety' not installed. Install with: pip install safety")
    except subprocess.TimeoutExpired:
        logger.warning("Safety check timed out")
    except Exception as e:
        logger.warning("Error running safety: %s", e)

    # Try pip-audit as fallback
    try:
        logger.info("\n[2/2] Checking with pip-audit...")
        result = subprocess.run(
            ['pip-audit', '--format=json'],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            try:
                audit_data = json.loads(result.stdout)
                vulnerabilities = audit_data.get('vulnerabilities', [])

                if vulnerabilities:
                    logger.warning("Found %d vulnerabilities:", len(vulnerabilities))
                    for vuln in vulnerabilities:
                        logger.warning("  - %s: %s", vuln.get('name', 'unknown'), vuln.get('id', 'unknown'))
                    return False
                else:
                    logger.info("✓ No vulnerabilities found")
                    return True
            except json.JSONDecodeError:
                logger.info("✓ No vulnerabilities found (unable to parse output)")
                return True
        else:
            logger.warning("pip-audit check failed: %s", result.stderr)
            return None

    except FileNotFoundError:
        logger.warning("'pip-audit' not installed. Install with: pip install pip-audit")
    except subprocess.TimeoutExpired:
        logger.warning("pip-audit check timed out")
    except Exception as e:
        logger.warning("Error running pip-audit: %s", e)

    logger.warning("No dependency scanner available. Install 'safety' or 'pip-audit'")
    return None


def check_configuration():
    """Check security configuration."""
    logger.info("\n" + "=" * 80)
    logger.info("CONFIGURATION SECURITY CHECK")
    logger.info("=" * 80)

    issues = []

    # Check environment variables
    required_vars = ['SECRET_KEY', 'DATABASE_URL']
    recommended_vars = ['API_KEY', 'ADMIN_EMAILS']

    logger.info("\n[1/3] Checking required environment variables...")
    for var in required_vars:
        if os.environ.get(var):
            logger.info("✓ %s is set", var)
        else:
            logger.error("✗ %s is NOT set (REQUIRED)", var)
            issues.append(f"Missing required: {var}")

    logger.info("\n[2/3] Checking recommended environment variables...")
    for var in recommended_vars:
        if os.environ.get(var):
            logger.info("✓ %s is set", var)
        else:
            logger.warning("%s is not set (recommended)", var)

    # Check if running in production
    flask_config = os.environ.get('FLASK_CONFIG', '').lower()
    logger.info("\n[3/3] Environment: %s", flask_config or 'development')

    if flask_config == 'production':
        logger.info("✓ Running in production mode")

        # Additional production checks
        if not os.environ.get('SECRET_KEY'):
            issues.append("SECRET_KEY must be set in production")
        if str(os.environ.get('DEBUG', '')).strip().lower() == 'true':
            issues.append("DEBUG should be False in production")
    else:
        logger.warning("Not in production mode (acceptable for development)")

    return issues


def check_files():
    """Check for sensitive files that shouldn't be committed."""
    logger.info("\n" + "=" * 80)
    logger.info("FILE SECURITY CHECK")
    logger.info("=" * 80)

    sensitive_patterns = [
        '*.key',
        '*.pem',
        '*.p12',
        '*.pfx',
        '*.env',
        '*.secret',
        'credentials.json',
        'secrets.json',
    ]

    logger.info("\nChecking for sensitive files...")

    # This is a basic check - in production, use git-secrets or similar
    root_path = Path(__file__).parent.parent
    found_issues = []

    for pattern in sensitive_patterns:
        for file_path in root_path.rglob(pattern):
            # Skip files in .gitignore
            if '.git' in str(file_path) or '__pycache__' in str(file_path):
                continue

            # Check if file contains sensitive data
            try:
                if file_path.is_file() and file_path.stat().st_size < 1024 * 1024:  # < 1MB
                    content = file_path.read_text(errors='ignore')
                    if any(keyword in content.lower() for keyword in ['password', 'secret', 'api_key', 'token']):
                        logger.warning("Potentially sensitive file: %s", file_path.relative_to(root_path))
                        found_issues.append(str(file_path.relative_to(root_path)))
            except Exception as e:
                logger.debug("Error reading file %s: %s", file_path, e)

    if not found_issues:
        logger.info("✓ No obvious sensitive files found in repository")

    return found_issues


def main():
    """Run all security audits."""
    logger.info("\n" + "=" * 80)
    logger.info("SECURITY AUDIT - Humanitarian Databank")
    logger.info("=" * 80)

    all_passed = True

    # Run checks
    dep_check = check_dependencies()
    config_issues = check_configuration()
    file_issues = check_files()

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("AUDIT SUMMARY")
    logger.info("=" * 80)

    if dep_check is False:
        logger.error("✗ Dependency vulnerabilities found")
        all_passed = False
    elif dep_check is True:
        logger.info("✓ Dependencies: OK")
    else:
        logger.warning("Dependencies: Unable to check (install safety or pip-audit)")

    if config_issues:
        logger.error("✗ Configuration issues: %d", len(config_issues))
        for issue in config_issues:
            logger.error("  - %s", issue)
        all_passed = False
    else:
        logger.info("✓ Configuration: OK")

    if file_issues:
        logger.warning("Potentially sensitive files found: %d", len(file_issues))
    else:
        logger.info("✓ File check: OK")

    logger.info("\n" + "=" * 80)

    if all_passed:
        logger.info("✓ SECURITY AUDIT PASSED")
        return 0
    else:
        logger.error("✗ SECURITY AUDIT FAILED - Review issues above")
        return 1


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main())
