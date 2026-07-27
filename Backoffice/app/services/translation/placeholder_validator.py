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


def localized_validation_message(validation: Dict[str, Any]) -> str:
    """Return a gettext-wrapped user message for a failed validation result."""
    try:
        from flask_babel import _
    except ImportError:
        return validation.get('message') or 'Invalid placeholders'

    parts: list[str] = []
    missing = validation.get('missing') or []
    extra = validation.get('extra') or []
    if missing:
        parts.append(_('Missing placeholders: %(placeholders)s', placeholders=', '.join(missing)))
    if extra:
        parts.append(_('Unexpected placeholders: %(placeholders)s', placeholders=', '.join(extra)))
    return '. '.join(parts) if parts else _('Invalid placeholders')
