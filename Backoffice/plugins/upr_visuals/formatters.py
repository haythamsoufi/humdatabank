"""Tableau-faithful number formatting used by UPR Visuals.twb."""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

_LATIN_AMOUNT_RE = re.compile(r"(?P<num>\d[\d,]*(?:\.\d+)?)")


def to_number(value: Any) -> float | None:
    """Coerce stored form values to float. Empty / non-numeric → None."""
    if value is None or value is False:
        return None
    if isinstance(value, bool):
        return 1.0 if value else None
    if isinstance(value, (int, float)):
        if value != value:  # NaN
            return None
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"none", "null", "n/a", "not reported", "undefined"}:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def format_count(value: Any) -> str:
    """Integer with thousands separators, Tableau ``n#,##0``."""
    from plugins.upr_visuals.i18n import t

    number = to_number(value)
    if number is None:
        return t("Not reported")
    return f"{int(round(number)):,}"


def format_percent(value: Any) -> str:
    """Whole-percent label for form-stored 0–100 values (``60`` → ``60%``)."""
    from plugins.upr_visuals.i18n import t

    number = to_number(value)
    if number is None:
        return t("Not reported")
    if number == int(number):
        return f"{int(number)}%"
    text = f"{number:.1f}".rstrip("0").rstrip(".")
    return f"{text}%"


def _arabic_million_suffix(millions: float) -> str:
    """Arabic unit after a numeric million count (digits, not spelled words).

    Dual مليونان and accusative مليونا are for fully written-out numbers,
    not digit labels. Any fractional count uses singular مليون.

    | Value              | Form    | Example      |
    |--------------------|---------|--------------|
    | 1                  | مليون   | 1 مليون      |
    | 2                  | مليون   | 2 مليون      |
    | integer 3–10       | ملايين  | 5 ملايين     |
    | integer 11+        | مليون   | 25 مليون     |
    | any fractional     | مليون   | 2.6 مليون    |
    """
    count = int(math.floor(millions + 1e-9))
    has_fraction = abs(millions - count) > 1e-9
    if has_fraction:
        return "مليون"
    if 3 <= count <= 10:
        return "ملايين"
    return "مليون"


def _format_million_digits(rounded: float) -> str:
    if rounded == int(rounded):
        return f"{int(rounded):,}"
    return f"{rounded:.1f}".rstrip("0").rstrip(".")


def _format_millions_compact(number: float) -> str:
    """Compact millions. Gate 3: only ``ar`` uses مليون / ملايين (not other RTL)."""
    millions = number / 1_000_000.0
    rounded = round(millions, 1)
    from plugins.upr_visuals.i18n import current_export_language

    if current_export_language() == "ar":
        return f"{_format_million_digits(rounded)} {_arabic_million_suffix(rounded)}"
    if rounded == int(rounded):
        return f"{int(rounded)}M"
    text = f"{rounded:.1f}".rstrip("0").rstrip(".")
    return f"{text}M"


def chf_label() -> str:
    """ISO code in Latin locales; Arabic uses the IFRC phrase فرنك سويسري."""
    from plugins.upr_visuals.i18n import t

    return t("CHF")


def split_display_amount(amount: str, *, require_arabic: bool = True) -> tuple[str, str] | None:
    """Split a mixed amount into ``(unit, number)`` for LTR flex layout.

    Gate 4 (script): default requires an Arabic letter (``\\u0600–\\u06ff``), not
    ``is_rtl()`` or ``lang == "ar"``. Hebrew amounts do not split.

    WeasyPrint's bidi still paints ``مليون 1`` as digits-then-unit. Callers wrap
    the parts in separate spans. Pass ``require_arabic=False`` to attach a CHF
    label to a Latin-only amount (``163,000`` → unit ``فرنك سويسري``).
    """
    text = " ".join((amount or "").split())
    if not text:
        return None
    if require_arabic and not any("\u0600" <= char <= "\u06ff" for char in text):
        return None
    matches = list(_LATIN_AMOUNT_RE.finditer(text))
    if not matches:
        return None
    num_match = matches[-1]
    unit = " ".join(
        part
        for part in (text[: num_match.start()].strip(), text[num_match.end() :].strip())
        if part
    )
    if not unit:
        return None
    return unit, num_match.group("num")


def _arabic_unit_left(amount: str, extra_unit: str = "") -> str:
    """Keep Arabic unit words to the left of the Latin number.

    ``1 مليون`` in an RTL document paints the unit on the right of the digits
    and collides with neighbouring labels (e.g. Total). Emit ``مليون 1`` and
    isolate that run as LTR at the call site.
    """
    text = " ".join((amount or "").split())
    extra = (extra_unit or "").strip()
    if not text:
        return extra
    parts = split_display_amount(text) or split_display_amount(text, require_arabic=False)
    if parts:
        unit, number = parts
        return " ".join(part for part in (unit, extra, number) if part)
    return " ".join(part for part in (extra, text) if part)


def with_chf(display: str, *, prefix: bool = False) -> str:
    """Attach the localized CHF label. Arabic units stay to the left of digits."""
    from plugins.upr_visuals.i18n import current_export_language

    text = (display or "").strip()
    label = chf_label()
    if not text:
        return label
    if current_export_language() == "ar":
        return _arabic_unit_left(text, label)
    if prefix:
        return f"{label} {text}"
    return f"{text} {label}"


def format_compact_chf(value: Any) -> str:
    """Compact CHF-style labels from Tableau ``Value units`` / PNS funding calc.

    < 1,000 → raw integer
    < 1,000,000 → thousands as ``N,000``
    ≥ 1,000,000 → ``N.nM`` (drop trailing ``.0``); Arabic uses digit + مليون / ملايين
    """
    number = to_number(value)
    if number is None or number == 0:
        return ""
    if abs(number) < 1000:
        return str(int(round(number)))
    if abs(number) < 1_000_000:
        thousands = int(round(number / 1000.0))
        if thousands < 1000:
            return f"{thousands},000"
    return _format_millions_compact(number)


def format_chf(value: Any) -> str:
    """Full CHF amount with thousands separators, or ``Not reported``."""
    from plugins.upr_visuals.i18n import t

    number = to_number(value)
    if number is None:
        return t("Not reported")
    return f"{int(round(number)):,}"


def period_to_round(period_name: str | None, kind: str) -> str:
    """Map assignment period_name back to the Tableau RoundParam codes."""
    raw = (period_name or "").strip()
    if not raw:
        return ""
    lower = raw.lower()
    if lower.startswith("jan-jun"):
        year = _year_token(raw)
        return f"MYR{year % 100:02d}" if year else raw
    year = _year_token(raw)
    if year is None:
        return raw
    if kind == "plan":
        return f"P{year % 100:02d}"
    return f"AR{year % 100:02d}"


def _year_token(period_name: str) -> int | None:
    digits = []
    for token in period_name.replace("-", " ").split():
        if token.isdigit() and len(token) == 4:
            digits.append(int(token))
    return digits[-1] if digits else None


def planning_years(period_name: str | None) -> list[int]:
    """Three-year planning horizon for Unified Country Plan visuals."""
    year = _year_token(period_name or "")
    if year is None:
        return []
    return [year, year + 1, year + 2]


def format_header_date(value: date | None = None) -> str:
    """INP/annual-report cover date, e.g. ``2 July 2026``."""
    day = value or date.today()
    try:
        from flask import has_app_context
        from flask_babel import format_date

        if has_app_context():
            return format_date(day, format="d MMMM y")
    except Exception:
        pass
    return f"{day.day} {day.strftime('%B %Y')}"


def document_subtitle(
    kind: str,
    period_name: str | None,
    *,
    plan_years: list[int] | None = None,
) -> str:
    """Cover line under the country name on All visuals."""
    from plugins.upr_visuals.i18n import t

    years = [int(year) for year in (plan_years or []) if year]
    if kind == "plan":
        if len(years) >= 2:
            return t(f"{years[0]}-{years[-1]} IFRC network country plan")
        if years:
            return t(f"{years[0]} IFRC network country plan")
        horizon = planning_years(period_name)
        if len(horizon) >= 2:
            return t(f"{horizon[0]}-{horizon[-1]} IFRC network country plan")
        if horizon:
            return t(f"{horizon[0]} IFRC network country plan")
        return t("IFRC network country plan")
    year = years[0] if years else _year_token(period_name or "")
    raw = (period_name or "").strip().lower()
    if raw.startswith("jan-jun"):
        return t(
            f"{year} IFRC network mid-year report, Jan-Jun"
            if year
            else "IFRC network mid-year report, Jan-Jun"
        )
    return t(
        f"{year} IFRC network annual report, Jan-Dec"
        if year
        else "IFRC network annual report, Jan-Dec"
    )


def appeal_number(iso2: str | None) -> str:
    """Country appeal code ``MAA`` + ISO2 + ``001`` (e.g. Uganda → ``MAAUG001``)."""
    code = (iso2 or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return f"MAA{code}001"
