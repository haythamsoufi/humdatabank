"""Port of Tableau calculated fields from P&B figures.twb."""

from __future__ import annotations

import math
import re
from functools import lru_cache
from typing import Any

import pandas as pd

from .config import treat_zero_as_missing
from .languages import excel_text
from .translations import section_title_for, t

# ---------------------------------------------------------------------------
# UI label codes (resolved via SG Report.xlsx → Translations sheet)
# ---------------------------------------------------------------------------
INDICATOR_HEADER = "ui.indicator_header"
YEAR_HEADER = "ui.year_header"
TARGET_HEADER = "ui.target_header"
ANNUAL_TARGET_HEADER = "ui.annual_target_header"
NS_REPORTING_HEADER = "ui.ns_reporting_header"
NS_IMPLEMENTING_HEADER = "ui.ns_implementing_header"
TABLE_REPORTING_ROW = "ui.table_reporting_row"
TABLE_IMPLEMENTING_ROW = "ui.table_implementing_row"
NATIONAL_SOCIETIES = "ui.national_societies"
NS_REPORTED_SUFFIX = "ui.ns_reported_suffix"

_NATIONAL_SOCIETIES_FALLBACK = {
    "English": "National Societies",
    "French": "Sociétés nationales",
    "Spanish": "Sociedades Nacionales",
    "Arabic": "الجمعيات الوطنية",
}
EFS_HEADER = "ui.part.ef"
SP_PART_TITLE = "ui.part.sp"
NOT_APPLICABLE = "ui.not_applicable"
NOT_AVAILABLE = "ui.not_available"
TARGET_LABEL_ALL_COVERED = "ui.target_all_covered"
TARGET_LABEL_EF_ALL = "ui.target_ef_all"
TARGET_SUFFIX_SP = "ui.target_suffix_sp"
TARGET_SUFFIX_EF = "ui.target_suffix_ef"

_FOOTNOTES_BY_KEY = {
    "default": "footnote.default",
    "sp1": "footnote.sp1",
    "sp2": "footnote.sp2",
    "ef4": "footnote.ef4",
    "dref": "footnote.dref",
}

# Tableau Indicator field aliases (add ** suffix)
INDICATOR_ALIASES: dict[str, str] = {
    "DREF": "**",
    "649": "**",
}

_MISSING_VALUE_TOKENS = frozenset({"", "n/a", "na", "-", "none", "null"})


def chartable_value(raw: object) -> float | None:
    """Return a numeric indicator Value when it can be plotted, else None.

    NOTE ON value == 0: ported as-is from the original Tableau calculated field,
    which also treated 0 as "no data" rather than a genuine zero — a real
    ambiguity for hand-maintained Excel workbooks (data_source == "excel"), where
    preparers have historically used a bare 0 as a placeholder for "not entered"
    as well as for an actual zero, indistinguishable once the value reaches this
    function. System-generated workbooks (data_source == "system") do NOT have
    this ambiguity: db_source.py's _aggregate_indicator_years_for_template sums
    FormData.numeric_value directly, so a genuine zero comes through as 0.0 and
    "nothing reported" comes through as None — see
    config.treat_zero_as_missing() for how that distinction is preserved here.
    """
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in _MISSING_VALUE_TOKENS:
            return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(value):
        return None
    if value == 0 and treat_zero_as_missing():
        return None
    return value


def label(code: str, language: str) -> str:
    return t(code, language)


def national_societies_label(language: str = "English") -> str:
    text = label(NATIONAL_SOCIETIES, language)
    if text:
        return text
    return _NATIONAL_SOCIETIES_FALLBACK.get(language, _NATIONAL_SOCIETIES_FALLBACK["English"])


def _ns_breakdown_label(role_code: str, language: str) -> str:
    """Prefix reporting/implementing row labels with the National Societies label."""
    role = label(role_code, language)
    prefix = national_societies_label(language)
    if not role:
        return prefix
    role_lower = role.casefold()
    prefix_lower = prefix.casefold()
    if role_lower.startswith(prefix_lower):
        return role
    return f"{prefix} {role}"


def _format_footnote_count(value: int | None) -> str:
    return str(value) if value is not None else "—"


@lru_cache(maxsize=8)
def _cached_reporting_totals(excel_path_str: str, year: str | None) -> tuple[str, int | None, int | None]:
    from .data import reporting_source_totals

    totals = reporting_source_totals(excel_path_str, year=year or None)
    return (
        str(totals["year"]),
        totals.get("upr_ns"),
        totals.get("fdrs_ns"),
    )


def _resolve_footnote_totals(
    *,
    year: str | int | None = None,
    upr_ns: int | None = None,
    fdrs_ns: int | None = None,
) -> dict[str, Any]:
    if year is not None and upr_ns is not None and fdrs_ns is not None:
        return {"year": str(year), "upr_ns": upr_ns, "fdrs_ns": fdrs_ns}

    from .config import resolve_excel

    excel_path = resolve_excel()
    cached_year, cached_upr, cached_fdrs = _cached_reporting_totals(
        str(excel_path),
        str(year).strip() if year is not None else None,
    )
    return {
        "year": str(year) if year is not None else cached_year,
        "upr_ns": upr_ns if upr_ns is not None else cached_upr,
        "fdrs_ns": fdrs_ns if fdrs_ns is not None else cached_fdrs,
    }


_LEGACY_DATA_SOURCE_PATTERNS: dict[str, re.Pattern[str]] = {
    "English": re.compile(
        r"(\*)\d{4}( data is based on reports received from )\d+( NSs through the unified "
        r"reporting process and )\d+( NSs through FDRS)"
    ),
    "French": re.compile(
        r"(\* Les données de )\d{4}( reposent sur les rapports de )\d+( SN via le processus "
        r"de rapport unifié et de )\d+( SN via le FDRS)"
    ),
    "Spanish": re.compile(
        r"(\* Los datos de )\d{4}( se basan en los informes de )\d+( Sociedades Nacionales "
        r"a través del proceso unificado de presentación de informes y de )\d+( Sociedades "
        r"Nacionales a través del (?:banco de datos y sistema de información general interno "
        r"\(FDRS\)|FDRS))"
    ),
    "Arabic": re.compile(
        r"(\*تستند بيانات عام )\d{4}( إلى تقارير )\d+( جمعيات وطنية من خلال عملية التقارير "
        r"الموحدة و)\d+( جمعية وطنية من خلال نظام (?:قاعدة البيانات ونظام الإفادة في الاتحاد "
        r"الدولي|FDRS))"
    ),
}


def _strip_sp2_dref_paragraph(text: str) -> str:
    """Remove legacy SP2 DREF allocation footnote (dropped from report)."""
    markers = (
        "IFRC-DREF",
        "IFRC DREF",
        "Fondo de Emergencia para la Intervención",
        "77 millions CHF",
        "77 millones de francos",
        "77 مليون فرنك",
    )
    lines = text.split("\n")
    kept = [
        line
        for line in lines
        if not (line.strip().startswith("**") and any(marker in line for marker in markers))
    ]
    return "\n".join(kept).strip()


def _apply_footnote_placeholders(
    template: str,
    *,
    year: str,
    upr_ns: int | None,
    fdrs_ns: int | None,
    language: str = "English",
) -> str:
    upr = _format_footnote_count(upr_ns)
    fdrs = _format_footnote_count(fdrs_ns)

    if "{year}" in template or "{upr_ns}" in template or "{fdrs_ns}" in template:
        return template.format(year=year, upr_ns=upr, fdrs_ns=fdrs)

    pattern = _LEGACY_DATA_SOURCE_PATTERNS.get(language)
    if pattern and pattern.search(template):
        return pattern.sub(
            lambda match: (
                f"{match.group(1)}{year}{match.group(2)}{upr}"
                f"{match.group(3)}{fdrs}{match.group(4)}"
            ),
            template,
        )

    return template


def footnote_for_key(
    key: str,
    language: str,
    *,
    year: str | int | None = None,
    upr_ns: int | None = None,
    fdrs_ns: int | None = None,
) -> str:
    code = _FOOTNOTES_BY_KEY.get(key, _FOOTNOTES_BY_KEY["default"])
    template = t(code, language)
    totals = _resolve_footnote_totals(year=year, upr_ns=upr_ns, fdrs_ns=fdrs_ns)
    rendered = _apply_footnote_placeholders(
        template,
        year=str(totals["year"]),
        upr_ns=totals["upr_ns"],
        fdrs_ns=totals["fdrs_ns"],
        language=language,
    )
    if key == "sp2":
        return _strip_sp2_dref_paragraph(rendered)
    return rendered


def indicator_label(row: pd.Series, language: str = "English") -> str:
    """Tableau [Indicator] — English/French/Spanish/Arabic columns from Mapping."""
    text = excel_text(row, language, "indicator")
    indicator_id = str(row.get("ID", "") or "")
    suffix = INDICATOR_ALIASES.get(indicator_id, "")
    return f"{text}{suffix}" if text else ""


def section_title(row: pd.Series, language: str = "English") -> str:
    """Section title from Translations sheet (section.SP1, …), else Mapping SP columns."""
    section = str(row.get("section", "") or "").strip()
    if section:
        title = section_title_for(section, language)
        if title:
            return title
    return excel_text(row, language, "section")


def annual_target_value(row: pd.Series) -> float | None:
    """Numeric annual target for chart positioning (Target value or Annual Target)."""
    raw = row.get("Target value")
    if raw is not None and not (isinstance(raw, float) and math.isnan(raw)):
        return float(raw)
    raw = row.get("Annual Target")
    if isinstance(raw, (int, float)) and not (isinstance(raw, float) and math.isnan(raw)):
        return float(raw)
    return None


def _parse_target_number(text: str) -> float | None:
    cleaned = text.strip().replace(",", "").replace(" ", "")
    if not cleaned:
        return None
    if cleaned.endswith("%"):
        try:
            return float(cleaned[:-1]) / 100
        except ValueError:
            return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def indicator_format_unit(row: pd.Series | dict[str, Any]) -> str | None:
    """typeOfMeasurement from Indicator bank — used for value/target formatting."""
    if isinstance(row, dict):
        raw = row.get("typeOfMeasurement")
        fallback = row.get("Unit")
    else:
        raw = row.get("typeOfMeasurement")
        fallback = row.get("Unit")
    if raw is not None and not (isinstance(raw, float) and math.isnan(raw)):
        text = str(raw).strip()
        if text:
            if text.lower() in {"percentage", "percent", "%"}:
                return "Percentage"
            return text
    if fallback is None or (isinstance(fallback, float) and math.isnan(fallback)):
        return None
    text = str(fallback).strip()
    return text or None


def annual_target_label(row: pd.Series, language: str = "English") -> str | None:
    """Display label on annual target line — Excel Annual Target / Annual Target AR."""
    unit = indicator_format_unit(row)
    text = excel_text(row, language, "annual_target")
    if text:
        num = _parse_target_number(text)
        if num is not None:
            formatted = format_value(num, unit, language)
            if formatted:
                return formatted
        return text
    value = annual_target_value(row)
    return format_value(value, unit, language) if value is not None else None


def _format_under_million(value: float) -> str:
    if value < 1000:
        return str(int(value))
    return f"{round(value / 1000):.0f},000"


def _format_millions_english(value: float) -> str:
    millions = round(value / 1_000_000, 1)
    return f"{millions:g}M"


def is_percentage_unit(unit: str | None) -> bool:
    return str(unit or "").strip().lower() in {"percentage", "percent", "%"}


def _format_percentage(value: float) -> str:
    """Format percentage values stored as fractions (0.23) or whole percents (23)."""
    if 0 < abs(value) <= 1:
        pct = value * 100
    else:
        pct = value
    return f"{round(pct):.0f}%"


def _arabic_million_suffix(millions: float) -> str:
    """Arabic plural form for the million count (see IFRC Arabic style guide).

    Range rules apply to the whole-number part of the count so values like
    10.8M use the 3–10 form (ملايين), not the 100+ fallback. Values of 100+
    use مليون only when the count is a whole number (e.g. 100 مليون); fractional
    counts keep مليونا (e.g. 219.3 مليونا).

    | Range  | Form     | Example    |
    |--------|----------|------------|
    | 1      | مليون    | 1 مليون    |
    | 2      | مليونان  | 2 مليونان  |
    | 3–10   | ملايين   | 5 ملايين   |
    | 11–99  | مليونا  | 25 مليونا  |
    | 100+   | مليون    | 100 مليون  |
    """
    count = int(math.floor(millions + 1e-9))
    has_fraction = abs(millions - count) > 1e-9
    if count == 1:
        return "مليون"
    if count == 2:
        return "مليونان"
    if 3 <= count <= 10:
        return "ملايين"
    if 11 <= count <= 99:
        return "مليونا"
    if count >= 100 and not has_fraction:
        return "مليون"
    if count >= 11:
        return "مليونا"
    return "مليون"


def _format_millions_arabic(value: float) -> str:
    """Tableau [Formatted] Arabic plural rules for values >= 1,000,000."""
    millions = round(value / 1_000_000, 1)
    num = f"{millions:g}"
    return f"{num} {_arabic_million_suffix(millions)}"


def format_value(value: float | int | None, unit: str | None, language: str = "English") -> str | None:
    """Tableau [Formatted] calculation.

    See the value == 0 note on chartable_value() above — same "0 means no data
    for Excel, real zero for system-generated" rule, kept in sync with it
    intentionally via treat_zero_as_missing().
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if value == 0 and treat_zero_as_missing():
        return None
    if is_percentage_unit(unit):
        return _format_percentage(float(value))
    if value < 1_000_000:
        return _format_under_million(float(value))
    if language == "Arabic":
        return _format_millions_arabic(float(value))
    return _format_millions_english(float(value))


def format_donut_value(value: float | int | None, unit: str | None, language: str = "English") -> str | None:
    """Tableau [Formatted2] — used for Katya01 donut centre labels.

    See the value == 0 note on chartable_value() above — same "0 means no data
    for Excel, real zero for system-generated" rule, kept in sync with it
    intentionally via treat_zero_as_missing().
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if value == 0 and treat_zero_as_missing():
        return None
    if is_percentage_unit(unit):
        return _format_percentage(float(value))
    if value < 1_000_000:
        return _format_under_million(float(value))
    if language == "Arabic":
        millions = round(float(value) / 1_000_000)
        num = f"{millions:g}"
        return f"{num}\n{_arabic_million_suffix(millions)}"
    return _format_millions_english(float(value))


def format_target(value: float | int | None) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return format_value(value, None)


def gap_value(target: float | None, value: float | None) -> float:
    if target is None or value is None:
        return 0.0
    return max(target - value, 0.0)


def out_of_suffix(
    value: float | None,
    unit: str | None,
    count: float | None,
    total_reported: str | None,
    language: str = "English",
) -> str | None:
    """Tableau [Out of] / [NSs Reported] calculations."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if unit in {"Platforms", "Metrics"} and count is not None and not math.isnan(count):
        return f"/{int(count)}{label(NS_REPORTED_SUFFIX, language)}"
    if total_reported:
        return f"/ {total_reported}"
    return None


def _ef_target_display(row: pd.Series, language: str = "English") -> str:
    """Format EF target text before appending the year suffix."""
    unit = indicator_format_unit(row)
    excel_target = excel_text(row, language, "target")
    if excel_target:
        return _format_ef_target_token(excel_target, unit, language)

    # Some percentage targets live only in Target AR (e.g. 644 → %50).
    target_ar = row.get("Target AR")
    if target_ar is not None and not (isinstance(target_ar, float) and math.isnan(target_ar)):
        ar_text = str(target_ar).strip()
        if ar_text.startswith("%"):
            return _format_ef_target_token(ar_text, unit, language)

    raw = row.get("Target")
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return ""
    if is_percentage_unit(unit):
        return format_value(float(raw), unit, language) or ""
    formatted = format_value(float(raw), unit, language) if isinstance(raw, (int, float)) else None
    return formatted or _target_scalar(row)


def _format_ef_target_token(text: str, unit: str | None, language: str) -> str:
    if text.startswith("%"):
        return f"{text.lstrip('%').strip()}%"
    try:
        num = float(text.replace(",", ""))
        if is_percentage_unit(unit) and 0 <= num <= 1:
            return format_value(num, unit, language) or text
        if num == int(num):
            return str(int(num))
    except ValueError:
        pass
    return text


def target_label_ef(row: pd.Series, language: str = "English") -> str:
    """Tableau [TargetLabel2] for Enabling Functions."""
    fdrs_kpi = str(row.get("FDRS KPI", "") or "")
    if fdrs_kpi == "645":
        return label(TARGET_LABEL_EF_ALL, language)

    target = _ef_target_display(row, language)
    if not target:
        return ""

    suffix = label(TARGET_SUFFIX_EF, language)
    if suffix and suffix in target:
        return target
    return f"{target} {suffix}"


def target_label_sp(row: pd.Series, language: str = "English") -> str:
    """Tableau [TargetLabel] for Strategic Priorities."""
    fdrs_kpi = str(row.get("FDRS KPI", "") or "")
    indicator_id = str(row.get("ID", "") or "")

    if fdrs_kpi == "All_Covered":
        return label(TARGET_LABEL_ALL_COVERED, language)

    annual = excel_text(row, language, "annual_target")
    if indicator_id == "Katya01" and annual:
        if language == "Arabic":
            return f"{label(ANNUAL_TARGET_HEADER, language)} \n{annual}"
        return f"{label(ANNUAL_TARGET_HEADER, language)}\n{annual}"

    excel_target = excel_text(row, language, "target")
    if excel_target:
        if language == "Arabic" or excel_target.startswith("%") or len(excel_target.split()) > 2:
            return excel_target
        return f"{label(TARGET_HEADER, language)}\n{excel_target}"

    target = _ef_target_display(row, language)
    if not target:
        return ""
    return f"{label(TARGET_HEADER, language)}\n{target}{label(TARGET_SUFFIX_SP, language)}"


def _target_scalar(row: pd.Series) -> str:
    target = row.get("Target")
    if target is None or (isinstance(target, float) and math.isnan(target)):
        return ""
    return str(target)


def year_display(year: str) -> str:
    return f" {year}*" if year == "2025" else year


def headers(language: str = "English") -> dict[str, str]:
    """Tableau column headers (IndicatorHeader, YearHeader, etc.)."""
    return {
        "indicator": label(INDICATOR_HEADER, language),
        "year": label(YEAR_HEADER, language),
        "target": label(TARGET_HEADER, language),
        "annual_target": label(ANNUAL_TARGET_HEADER, language),
        "ns_reporting": _ns_breakdown_label(NS_REPORTING_HEADER, language),
        "ns_implementing": _ns_breakdown_label(NS_IMPLEMENTING_HEADER, language),
    }


def table_row_labels(language: str = "English") -> dict[str, str]:
    return {
        "year": label(YEAR_HEADER, language),
        "reporting": _ns_breakdown_label(TABLE_REPORTING_ROW, language),
        "implementing": _ns_breakdown_label(TABLE_IMPLEMENTING_ROW, language),
    }


def part_title(
    part_id: str,
    language: str = "English",
    excel_path: Path | str | None = None,
) -> str:
    normalized = str(part_id or "").strip().lower()
    title = t(f"ui.part.{normalized}", language, excel_path)
    if title:
        return title
    if normalized == "ef":
        legacy = label(EFS_HEADER, language)
        if legacy:
            return legacy
    if normalized == "sp":
        legacy = label(SP_PART_TITLE, language)
        if legacy:
            return legacy
    return normalized.replace("-", " ").replace("_", " ").title()


def footnote_2025(language: str = "English") -> str:
    return footnote_for_key("default", language)


def section_footnote(
    section: str,
    language: str = "English",
    *,
    year: str | int | None = None,
    upr_ns: int | None = None,
    fdrs_ns: int | None = None,
) -> str:
    from .layouts import SECTION_FOOTNOTE_KEYS

    key = SECTION_FOOTNOTE_KEYS.get(section, "default")
    return footnote_for_key(
        key,
        language,
        year=year,
        upr_ns=upr_ns,
        fdrs_ns=fdrs_ns,
    )


def not_applicable(language: str = "English") -> str:
    return label(NOT_APPLICABLE, language)


def not_available(language: str = "English") -> str:
    return label(NOT_AVAILABLE, language)
