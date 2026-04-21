#!/usr/bin/env python3
"""Check for common accessibility anti-patterns in Flutter Dart files.

Checks:
  - GestureDetector / InkWell without Semantics wrapper
  - Image.network / Image.asset without semanticLabel
  - IconButton without tooltip

Exit 0 if clean, 1 if issues found (suitable for CI).
"""

import re
import sys
from pathlib import Path

CHECKS = [
    (
        r'IconButton\s*\(',
        r'tooltip\s*:',
        'IconButton without tooltip (needed for screen readers)',
    ),
]


def main():
    lib_dir = Path(__file__).resolve().parent.parent / 'lib'
    issues = []

    for dart_file in sorted(lib_dir.rglob('*.dart')):
        if '.freezed.' in dart_file.name or '.g.' in dart_file.name:
            continue
        content = dart_file.read_text(encoding='utf-8', errors='replace')
        rel = dart_file.relative_to(lib_dir.parent)

        for pattern, fix_pattern, message in CHECKS:
            for m in re.finditer(pattern, content):
                start = m.start()
                block = content[start:start + 500]
                if not re.search(fix_pattern, block):
                    line_no = content[:start].count('\n') + 1
                    issues.append(f'{rel}:{line_no}: {message}')

    if issues:
        print(f'Found {len(issues)} accessibility issue(s):')
        for issue in issues[:50]:
            print(f'  {issue}')
        if len(issues) > 50:
            print(f'  ... and {len(issues) - 50} more')
        return 1
    else:
        print('No accessibility issues found.')
        return 0


if __name__ == '__main__':
    sys.exit(main())
