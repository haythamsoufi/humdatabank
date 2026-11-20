"""Small parsers shared by GO sync, Excel import, and form posts."""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(Decimal(str(value).replace(",", "").strip()))
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


def as_money(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def date_text(value: date | None) -> str:
    return value.isoformat() if value else ""


_BLOCK_TAGS = re.compile(r"</?(?:p|div|br|li|ul|ol|h[1-6]|tr|table)\b[^>]*>", re.IGNORECASE)
_ANY_TAG = re.compile(r"<[^>]+>")
_BLANK_RUN = re.compile(r"[ \t\u00a0\u200b]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def plain_text(value: Any, limit: int | None = None) -> str:
    """GO stores some narrative as HTML. Return readable text with paragraph breaks kept."""
    if value is None:
        return ""
    text = _BLOCK_TAGS.sub("\n", str(value))
    text = html.unescape(_ANY_TAG.sub("", text))
    lines = [_BLANK_RUN.sub(" ", line).strip() for line in text.splitlines()]
    text = _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
    if limit is not None and len(text) > limit:
        cut = text[: limit - 1]
        # Prefer ending on a sentence, so a clipped paragraph does not stop mid-word.
        stop = max(cut.rfind(". "), cut.rfind(".\n"))
        text = (cut[: stop + 1] if stop > limit * 0.6 else cut.rstrip()) + ("" if stop > limit * 0.6 else "…")
    return text
