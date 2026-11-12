"""Extract display text from JSONB list fields (strings or legacy ``{text: ...}`` objects)."""

from __future__ import annotations

from typing import Any, Iterable, List, Optional


def text_from_jsonb_item(item: Any) -> Optional[str]:
    """Return stripped text from a JSONB list entry (string or dict with text/question keys)."""
    if item is None:
        return None
    if isinstance(item, dict):
        for key in ("text", "question", "name", "value"):
            val = item.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        return None
    text = str(item).strip()
    return text or None


def text_list_from_jsonb(items: Any) -> List[str]:
    """Return ordered, de-duplicated text values from a JSONB array."""
    if not items or not isinstance(items, list):
        return []
    out: List[str] = []
    seen: set[str] = set()
    for item in items:
        text = text_from_jsonb_item(item)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
