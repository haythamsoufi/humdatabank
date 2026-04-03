#!/usr/bin/env python3
"""
Secret Scanner for IFRC Network Databank

This script scans the codebase for potential hardcoded secrets, API keys,
passwords, and other sensitive information.

Usage:
    python scripts/scan-secrets.py                    # Full scan
    python scripts/scan-secrets.py --pre-commit      # Pre-commit mode (staged files only)
    python scripts/scan-secrets.py --path Backoffice # Scan specific directory
    python scripts/scan-secrets.py --fix             # Show fix suggestions

Author: Security Team
"""

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class SecretPattern:
    """Definition of a secret pattern to detect."""
    name: str
    pattern: str
    severity: str  # 'critical', 'high', 'medium', 'low'
    description: str
    fix_suggestion: str


@dataclass
class Finding:
    """A detected secret finding."""
    file: str
    line_number: int
    line_content: str
    pattern_name: str
    severity: str
    description: str
    fix_suggestion: str


# Secret patterns to detect
SECRET_PATTERNS: List[SecretPattern] = [
    # API Keys
    SecretPattern(
        name="Generic API Key",
        pattern=r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']([a-zA-Z0-9_\-]{20,})["\']',
        severity="high",
        description="Hardcoded API key detected",
        fix_suggestion="Move to environment variable: os.environ.get('API_KEY')"
    ),
    SecretPattern(
        name="OpenAI API Key",
        pattern=r'sk-[a-zA-Z0-9]{48,}',
        severity="critical",
        description="OpenAI API key detected",
        fix_suggestion="Move to environment variable: os.environ.get('OPENAI_API_KEY')"
    ),
    SecretPattern(
        name="Anthropic API Key",
        pattern=r'sk-ant-[a-zA-Z0-9\-]{90,}',
        severity="critical",
        description="Anthropic API key detected",
        fix_suggestion="Move to environment variable: os.environ.get('ANTHROPIC_API_KEY')"
    ),
    SecretPattern(
        name="Azure Key",
        pattern=r'(?i)(azure[_-]?key|subscription[_-]?key)\s*[=:]\s*["\']([a-zA-Z0-9]{32,})["\']',
        severity="critical",
        description="Azure API key detected",
        fix_suggestion="Use Azure Key Vault or environment variables"
    ),

    # Database Credentials
    SecretPattern(
        name="Database URL with Password",
        pattern=r'(?i)(postgres|mysql|mongodb|redis)://[^:]+:([^@\s]+)@[^/\s]+',
        severity="critical",
        description="Database connection string with embedded password",
        fix_suggestion="Use environment variable for DATABASE_URL"
    ),
    SecretPattern(
        name="Hardcoded Password",
        pattern=r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']([^"\']{8,})["\']',
        severity="high",
        description="Hardcoded password detected",
        fix_suggestion="Move to environment variable or secure vault"
    ),

    # Tokens
    SecretPattern(
        name="JWT Token",
        pattern=r'eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}',
        severity="high",
        description="JWT token detected in code",
        fix_suggestion="Tokens should be retrieved at runtime, not hardcoded"
    ),
    SecretPattern(
        name="Bearer Token",
        pattern=r'(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}',
        severity="high",
        description="Bearer token detected",
        fix_suggestion="Tokens should be retrieved at runtime"
    ),
    SecretPattern(
        name="Basic Auth",
        pattern=r'(?i)basic\s+[a-zA-Z0-9+/=]{20,}',
        severity="high",
        description="Basic authentication credentials detected",
        fix_suggestion="Use secure credential management"
    ),

    # Private Keys
    SecretPattern(
        name="Private Key",
        pattern=r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----',
        severity="critical",
        description="Private key detected",
        fix_suggestion="Store in secure key management system, never in code"
    ),
    SecretPattern(
        name="SSH Private Key",
        pattern=r'-----BEGIN\s+OPENSSH\s+PRIVATE\s+KEY-----',
        severity="critical",
        description="SSH private key detected",
        fix_suggestion="Use SSH agent or secure key management"
    ),

    # Flask/Django Secrets
    SecretPattern(
        name="Flask Secret Key",
        pattern=r'(?i)secret[_-]?key\s*[=:]\s*["\']([^"\']{16,})["\']',
        severity="high",
        description="Flask/Django secret key hardcoded",
        fix_suggestion="Use environment variable: os.environ.get('SECRET_KEY')"
    ),

    # UUID-like API Keys (common pattern)
    SecretPattern(
        name="UUID API Key",
        pattern=r'(?i)(api[_-]?key|token|secret)\s*[=:]\s*["\']([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})["\']',
        severity="high",
        description="UUID-format API key/token detected",
        fix_suggestion="Move to environment variable"
    ),

    # AWS Credentials
    SecretPattern(
        name="AWS Access Key",
        pattern=r'(?i)(aws[_-]?access[_-]?key[_-]?id|AKIA)[A-Z0-9]{16,}',
        severity="critical",
        description="AWS access key detected",
        fix_suggestion="Use AWS IAM roles or environment variables"
    ),
    SecretPattern(
        name="AWS Secret Key",
        pattern=r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*["\']([a-zA-Z0-9/+=]{40})["\']',
        severity="critical",
        description="AWS secret access key detected",
        fix_suggestion="Use AWS IAM roles or environment variables"
    ),

    # Generic Secrets
    SecretPattern(
        name="Generic Secret",
        pattern=r'(?i)(secret|credential|auth[_-]?token)\s*[=:]\s*["\']([a-zA-Z0-9_\-]{20,})["\']',
        severity="medium",
        description="Potential secret detected",
        fix_suggestion="Review and move to secure configuration"
    ),
]

# Files and directories to skip
SKIP_PATTERNS = [
    r'[\\/]\.git[\\/]',
    r'[\\/]node_modules[\\/]',  # Skip all node_modules
    r'[\\/]__pycache__[\\/]',
    r'[\\/]\.pytest_cache[\\/]',
    r'[\\/]\.venv[\\/]',
    r'[\\/]venv[\\/]',
    r'[\\/]htmlcov[\\/]',  # Coverage reports
    r'[\\/]\.coverage',
    r'[\\/]dist[\\/]',
    r'[\\/]build[\\/]',
    r'[\\/]\.next[\\/]',
    r'\.env\.example$',
    r'env\.example$',
    r'package-lock\.json$',
    r'\.lock$',
    r'\.min\.js$',
    r'\.min\.css$',
    r'\.pyc$',
    r'\.pyo$',
    r'\.so$',
    r'\.dll$',
    r'\.exe$',
    r'\.png$',
    r'\.jpg$',
    r'\.jpeg$',
    r'\.gif$',
    r'\.ico$',
    r'\.svg$',
    r'\.woff',
    r'\.ttf$',
    r'\.eot$',
    r'\.pdf$',
    r'\.zip$',
    r'\.tar',
    r'\.gz$',
    r'\.map$',  # Source maps
    r'database_dump\.backup$',
    r'scan-secrets\.py$',  # Skip this script itself
    r'\.gitleaks\.toml$',
    r'SECURITY\.md$',
    r'README\.md$',  # Documentation with example configs
    r'[\\/]\.env$',  # Local environment files (gitignored)
    r'[\\/]\.env\.',  # .env.local, .env.development, etc.
    r'firebase.*\.json$',  # Firebase credentials (gitignored)
    r'-firebase-adminsdk.*\.json$',  # Firebase admin SDK files
    r'[\\/]tests[\\/]',  # Test files can have test credentials
    r'_test\.py$',
    r'test_.*\.py$',
]

# False positive patterns to ignore
FALSE_POSITIVE_PATTERNS = [
    r'YOUR_API_KEY',
    r'your-api-key',
    r'<YOUR_.*>',
    r'PLACEHOLDER',
    r'example\.com',
    r'localhost',
    r'127\.0\.0\.1',
    r'test123',
    r'password123',
    r'dummy',
    r'xxxxx',
    r'XXXXXXXX',
    r'\$\{.*\}',  # Environment variable templates
    r'os\.environ\.get',
    r'getenv\(',
    r'config\[',
    r'settings\.',
    r'#.*validation',  # Comments mentioning validation
    r'#.*hardening',   # Comments mentioning hardening
    r'Basic validation',  # Code comments
    r'create_test_user',  # Test fixtures
    r'TestPass',  # Test passwords in test files
    r'export\s+\w+="your_',  # Documentation examples
]


def should_skip_file(filepath: str) -> bool:
    """Check if file should be skipped based on patterns."""
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, filepath):
            return True
    return False


def is_false_positive(line: str) -> bool:
    """Check if the line is a known false positive."""
    for pattern in FALSE_POSITIVE_PATTERNS:
        if re.search(pattern, line, re.IGNORECASE):
            return True
    return False


def is_binary_file(filepath: str) -> bool:
    """Quick check if file is binary."""
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(1024)
            # Check for null bytes (common in binary files)
            if b'\x00' in chunk:
                return True
            # Check if mostly non-text bytes
            text_chars = bytearray({7,8,9,10,12,13,27} | set(range(0x20, 0x100)) - {0x7f})
            non_text = sum(1 for byte in chunk if byte not in text_chars)
            return non_text > len(chunk) * 0.3
    except Exception:
        return True


def scan_file(filepath: str) -> List[Finding]:
    """Scan a single file for secrets."""
    findings = []

    # Skip large files (>1MB) and binary files
    try:
        file_size = os.path.getsize(filepath)
        if file_size > 1024 * 1024:  # 1MB
            return findings
        if is_binary_file(filepath):
            return findings
    except Exception:
        return findings

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception:
        return findings

    for line_num, line in enumerate(lines, 1):
        # Skip false positives
        if is_false_positive(line):
            continue

        for pattern in SECRET_PATTERNS:
            if re.search(pattern.pattern, line):
                findings.append(Finding(
                    file=filepath,
                    line_number=line_num,
                    line_content=line.strip()[:100] + ('...' if len(line.strip()) > 100 else ''),
                    pattern_name=pattern.name,
                    severity=pattern.severity,
                    description=pattern.description,
                    fix_suggestion=pattern.fix_suggestion
                ))

    return findings


def get_staged_files() -> List[str]:
    """Get list of staged files for pre-commit mode."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACM'],
            capture_output=True,
            text=True,
            check=True
        )
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except subprocess.CalledProcessError:
        return []


def scan_directory(path: str, staged_only: bool = False, file_list: Optional[List[str]] = None) -> List[Finding]:
    """Scan a directory recursively for secrets."""
    findings = []

    if file_list:
        # Use provided file list (from pre-commit hook)
        files = [f for f in file_list if os.path.exists(f)]
    elif staged_only:
        files = get_staged_files()
        files = [f for f in files if os.path.exists(f)]
    else:
        files = []
        for root, dirs, filenames in os.walk(path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]

            for filename in filenames:
                filepath = os.path.join(root, filename)
                files.append(filepath)

    for filepath in files:
        if should_skip_file(filepath):
            continue

        file_findings = scan_file(filepath)
        findings.extend(file_findings)

    return findings


def print_findings(findings: List[Finding], show_fix: bool = False) -> None:
    """Print findings in a readable format."""
    if not findings:
        safe_print("\n[OK] No secrets detected!")
        return

    # Group by severity
    critical = [f for f in findings if f.severity == 'critical']
    high = [f for f in findings if f.severity == 'high']
    medium = [f for f in findings if f.severity == 'medium']
    low = [f for f in findings if f.severity == 'low']

    safe_print(f"\n[SCAN] Secret Scan Results")
    safe_print(f"{'=' * 60}")
    safe_print(f"Total findings: {len(findings)}")
    safe_print(f"  [CRITICAL] : {len(critical)}")
    safe_print(f"  [HIGH]     : {len(high)}")
    safe_print(f"  [MEDIUM]   : {len(medium)}")
    safe_print(f"  [LOW]      : {len(low)}")
    safe_print("")

    for finding in sorted(findings, key=lambda f: ['critical', 'high', 'medium', 'low'].index(f.severity)):
        severity_label = f"[{finding.severity.upper()}]"

        safe_print(f"{severity_label} {finding.pattern_name}")
        safe_print(f"   File: {finding.file}:{finding.line_number}")
        safe_print(f"   Content: {finding.line_content}")

        if show_fix:
            safe_print(f"   Fix: {finding.fix_suggestion}")

        safe_print("")


def safe_print(text: str) -> None:
    """Print with fallback for Windows console encoding issues."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Remove emojis and special characters for Windows console
        import unicodedata
        clean_text = ''.join(
            c if unicodedata.category(c) != 'So' else '[*]'
            for c in text
        )
        print(clean_text.encode('ascii', 'replace').decode('ascii'))


def main():
    parser = argparse.ArgumentParser(
        description='Scan codebase for hardcoded secrets'
    )
    parser.add_argument(
        'files',
        nargs='*',
        help='Files to scan (used by pre-commit hook)'
    )
    parser.add_argument(
        '--path',
        default='.',
        help='Path to scan (default: current directory)'
    )
    parser.add_argument(
        '--pre-commit',
        action='store_true',
        help='Pre-commit mode: only scan staged files'
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Show fix suggestions for each finding'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON'
    )
    parser.add_argument(
        '--fail-on',
        choices=['critical', 'high', 'medium', 'low', 'none'],
        default='high',
        help='Fail (exit 1) if findings at this severity or above (default: high)'
    )

    args = parser.parse_args()

    safe_print("[SECURITY] IFRC Databank Secret Scanner")

    # If files are provided (from pre-commit), use them
    file_list = args.files if args.files else None

    if file_list:
        safe_print(f"Scanning {len(file_list)} file(s) from pre-commit")
    else:
        safe_print(f"Scanning: {os.path.abspath(args.path)}")

    if args.pre_commit and not file_list:
        print("Mode: Pre-commit (staged files only)")

    findings = scan_directory(args.path, staged_only=args.pre_commit and not file_list, file_list=file_list)

    if args.json:
        import json
        output = [{
            'file': f.file,
            'line': f.line_number,
            'content': f.line_content,
            'pattern': f.pattern_name,
            'severity': f.severity,
            'description': f.description,
            'fix': f.fix_suggestion
        } for f in findings]
        print(json.dumps(output, indent=2))
    else:
        print_findings(findings, show_fix=args.fix)

    # Determine exit code based on severity threshold
    if args.fail_on == 'none':
        sys.exit(0)

    severity_levels = ['low', 'medium', 'high', 'critical']
    threshold_index = severity_levels.index(args.fail_on)

    for finding in findings:
        finding_index = severity_levels.index(finding.severity)
        if finding_index >= threshold_index:
            safe_print(f"\n[FAIL] Failing due to {finding.severity} severity finding(s)")
            sys.exit(1)

    sys.exit(0)


if __name__ == '__main__':
    main()
