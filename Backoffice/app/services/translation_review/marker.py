"""Invisible Unicode markers for in-context translation review."""

from __future__ import annotations

# Private-use tag-region delimiters (zero-width in common fonts).
_MARKER_START = '\U000e0001'
_MARKER_END = '\U000e0002'
_MARKER_BASE = 0xE0100


def encode(msgid: str) -> str:
    """Append an invisible marker encoding *msgid* to a rendered string."""
    if not msgid:
        return ''
    payload = msgid.encode('utf-8')
    encoded = ''.join(chr(_MARKER_BASE + byte) for byte in payload)
    return f'{_MARKER_START}{encoded}{_MARKER_END}'


def decode(text: str) -> list[str]:
    """Return unique msgids found in *text* (order preserved)."""
    if not text:
        return []

    found: list[str] = []
    seen: set[str] = set()
    index = 0
    while True:
        start = text.find(_MARKER_START, index)
        if start == -1:
            break
        end = text.find(_MARKER_END, start + len(_MARKER_START))
        if end == -1:
            break
        encoded = text[start + len(_MARKER_START):end]
        try:
            msgid = bytes(ord(char) - _MARKER_BASE for char in encoded).decode('utf-8')
        except (UnicodeDecodeError, ValueError):
            index = end + len(_MARKER_END)
            continue
        if msgid not in seen:
            seen.add(msgid)
            found.append(msgid)
        index = end + len(_MARKER_END)
    return found


def strip(text: str) -> str:
    """Remove all translation-review markers from *text*."""
    if not text or _MARKER_START not in text:
        return text

    out = text
    while _MARKER_START in out:
        start = out.find(_MARKER_START)
        end = out.find(_MARKER_END, start + len(_MARKER_START))
        if end == -1:
            break
        out = out[:start] + out[end + len(_MARKER_END):]
    return out


def contains_marker(text: str) -> bool:
    return bool(text) and _MARKER_START in text
