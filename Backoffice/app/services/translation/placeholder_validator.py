"""Server-side validation for gettext format placeholders."""

from __future__ import annotations

import re
from typing import Any, Dict, List

_NAMED_PLACEHOLDER_RE = re.compile(r'%\([^)]+\)[sd]')
_SIMPLE_PLACEHOLDER_RE = re.compile(r'%(?:[sd]|\.\d+[fd])')


def extract_placeholders(text: str | None) -> List[str]:
    """Extract python-format placeholders from *text*."""
    if not text:
        return []
    placeholders: List[str] = []
    placeholders.extend(_NAMED_PLACEHOLDER_RE.findall(text))
    stripped = _NAMED_PLACEHOLDER_RE.sub('', text)
    placeholders.extend(_SIMPLE_PLACEHOLDER_RE.findall(stripped))
    return sorted(set(placeholders))


def validate_placeholders(source_text: str | None, translation_text: str | None) -> Dict[str, Any]:
    """Validate that *translation_text* preserves placeholders from *source_text*."""
    source_placeholders = extract_placeholders(source_text)
    translation_placeholders = extract_placeholders(translation_text)
    missing = [p for p in source_placeholders if p not in translation_placeholders]
    extra = [p for p in translation_placeholders if p not in source_placeholders]
    if missing or extra:
        message_parts = []
        if missing:
            message_parts.append(f'Missing placeholders: {", ".join(missing)}')
        if extra:
            message_parts.append(f'Unexpected placeholders: {", ".join(extra)}')
        return {
            'valid': False,
            'missing': missing,
            'extra': extra,
            'message': '. '.join(message_parts),
        }
    return {'valid': True, 'missing': [], 'extra': []}
