"""Warning grouping helpers for UPR Excel import preview and run summaries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple


# Legacy phrasing (bulk importer / older workbooks) plus the entry-form wording.
_EMERGENCY_CODE_IMPORTED_RE = re.compile(
    r"^Emergency code '([^']+)' not found in GO API for ([A-Z]{3}) — imported using Excel name/code; review in form$"
)
_EMERGENCY_APPEAL_NOT_LISTED_RE = re.compile(
    r"^Emergency appeal ([A-Z0-9]+) is not listed for this country in GO\. "
    r"The Excel name and code were imported — please review it on the form\.$"
)
_MATRIX_ROW_FRIENDLY_RE = re.compile(
    r'^The imported row [“"\'](.+?)[”"\'] does not match a row on [“"\'](.+?)[”"\']\.'
)
_MATRIX_COL_FRIENDLY_RE = re.compile(
    r'^The imported column [“"\'](.+?)[”"\'] does not match a column on [“"\'](.+?)[”"\']\.'
)
_MATRIX_ROW_LEGACY_RE = re.compile(
    r"^Matrix row '([^']+)' not found in current form configuration(?: for item (\d+))?"
)


def warning_text(warning: Any) -> str:
    """Return the display string from a warning (plain text or structured item)."""
    if isinstance(warning, dict):
        return str(warning.get("message") or warning.get("text") or "").strip()
    return str(warning or "").strip()


def warning_item_id(warning: Any) -> Optional[int]:
    """Return a form-item id to scroll to, if the warning carries one."""
    if not isinstance(warning, dict) or warning.get("item_id") is None:
        return None
    try:
        return int(warning["item_id"])
    except (TypeError, ValueError):
        return None


def make_import_warning(
    message: str,
    *,
    item_id: Optional[int] = None,
    code: Optional[str] = None,
    iso3: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a structured import warning the entry form can turn into a jump-link."""
    out: Dict[str, Any] = {"message": str(message or "").strip()}
    if item_id:
        out["item_id"] = int(item_id)
    if code:
        out["code"] = str(code).strip().upper()
    if iso3:
        out["iso3"] = str(iso3).strip().upper()
    return out


def serialize_upr_import_warnings(warnings: Iterable[Any]) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Split warnings into display strings plus structured items for the UI."""
    texts: List[str] = []
    items: List[Dict[str, Any]] = []
    for raw in warnings:
        text = warning_text(raw)
        if not text:
            continue
        texts.append(text)
        item: Dict[str, Any] = {"message": text}
        item_id = warning_item_id(raw)
        if item_id:
            item["item_id"] = item_id
        items.append(item)
    return texts, items


def canonicalize_upr_import_warning(message: str) -> str:
    """Normalize warning text so case variants dedupe to one message."""
    text = str(message or "").strip()
    match = _EMERGENCY_CODE_IMPORTED_RE.match(text)
    if not match:
        listed = _EMERGENCY_APPEAL_NOT_LISTED_RE.match(text)
        if listed:
            return (
                f"Emergency appeal {listed.group(1).upper()} is not listed for this country "
                "in GO. The Excel name and code were imported — please review it on the form."
            )
        return text
    code, iso3 = match.group(1).upper(), match.group(2)
    return (
        f"Emergency code '{code}' not found in GO API for {iso3} — "
        "imported using Excel name/code; review in form"
    )


def _canonicalize_warning_item(raw: Any) -> Any:
    if isinstance(raw, dict):
        out = dict(raw)
        out["message"] = canonicalize_upr_import_warning(warning_text(raw))
        if out.get("code"):
            out["code"] = str(out["code"]).upper()
        return out
    return canonicalize_upr_import_warning(str(raw or "").strip())


def _matrix_row_group_key(text: str) -> Optional[Tuple[str, str]]:
    """Return (field_label, row_name) when *text* is a matrix-row mismatch warning."""
    match = _MATRIX_ROW_FRIENDLY_RE.match(text)
    if match:
        return match.group(2), match.group(1)
    legacy = _MATRIX_ROW_LEGACY_RE.match(text)
    if legacy:
        return legacy.group(2) or "", legacy.group(1)
    return None


def _format_quoted_list(names: List[str]) -> str:
    quoted = [f"“{name}”" for name in names]
    if len(quoted) == 1:
        return quoted[0]
    if len(quoted) == 2:
        return f"{quoted[0]} and {quoted[1]}"
    return f"{', '.join(quoted[:-1])}, and {quoted[-1]}"


def _merge_matrix_row_warnings(items: List[Any]) -> List[Any]:
    """Collapse per-cell row mismatches into one warning per field (and list the rows)."""
    groups: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    passthrough: List[Any] = []
    for raw in items:
        text = warning_text(raw)
        parsed = _matrix_row_group_key(text)
        if not parsed:
            passthrough.append(raw)
            continue
        field_label, row_name = parsed
        group_key = field_label or warning_text(raw)
        if group_key not in groups:
            groups[group_key] = {
                "field": field_label,
                "rows": [],
                "item_id": warning_item_id(raw),
                "first": raw,
            }
            order.append(group_key)
        group = groups[group_key]
        if row_name not in group["rows"]:
            group["rows"].append(row_name)
        if group["item_id"] is None:
            group["item_id"] = warning_item_id(raw)

    merged: List[Any] = []
    for key in order:
        group = groups[key]
        rows: List[str] = group["rows"]
        field = group["field"]
        if len(rows) == 1 and field:
            message = (
                f"The imported row “{rows[0]}” does not match a row on “{field}”. "
                "The value was imported but may not appear in the table."
            )
        elif len(rows) == 1:
            message = warning_text(group["first"])
        elif field:
            message = (
                f"These imported rows do not match the current “{field}” table: "
                f"{_format_quoted_list(rows)}. The values were imported but may not appear "
                "in the table."
            )
        else:
            message = (
                f"These imported rows do not match the current form table: "
                f"{_format_quoted_list(rows)}. The values were imported but may not appear "
                "in the table."
            )
        merged.append(make_import_warning(message, item_id=group["item_id"]))
    return passthrough + merged


def dedupe_upr_import_warnings(warnings: Iterable[Any]) -> List[Any]:
    """Return unique import warnings, collapsing redundant variants."""
    seen: Set[str] = set()
    out: List[Any] = []
    period_noted = False
    for raw in warnings:
        item = _canonicalize_warning_item(raw)
        text = warning_text(item)
        if not text or text in seen:
            continue
        lower = text.lower()
        if "period" in lower and ("does not match" in lower or "differs from" in lower):
            if period_noted:
                continue
            period_noted = True
        seen.add(text)
        out.append(item)
    return _merge_matrix_row_warnings(out)


@dataclass
class _WarningClassification:
    group_key: str
    display_base: str
    iso3: Optional[str] = None
    rnd: Optional[str] = None
    bank_id: Optional[str] = None


def _classify_warning_for_grouping(message: str, *, raw: Any = None) -> _WarningClassification:
    """Map a warning to a group key and display base, stripping country/round when useful."""
    if isinstance(raw, dict) and raw.get("code"):
        code = str(raw["code"]).upper()
        return _WarningClassification(
            group_key=f"ea_code_not_found|{code}",
            display_base=(
                f"Emergency appeal {code} is not listed in GO — "
                "imported using the Excel name and code; please review it on the form"
            ),
            iso3=raw.get("iso3"),
        )
    patterns: Tuple[
        Tuple[re.Pattern[str], Callable[[re.Match[str]], _WarningClassification]],
        ...,
    ] = (
        (
            re.compile(
                r"^No reporting-country form item for bank (\d+) area '([^']+)' "
                r"\(([A-Z]{3}) ([A-Z0-9]+)\)$"
            ),
            lambda m: _WarningClassification(
                group_key=f"missing_reporting_item|{m.group(2)}",
                display_base=f"No reporting-country form item for area '{m.group(2)}'",
                iso3=m.group(3),
                rnd=m.group(4),
                bank_id=m.group(1),
            ),
        ),
        (
            re.compile(r"^Unknown SP/EF area for reporting SP breakdown: '([^']+)' \(([A-Z]{3}) ([A-Z0-9]+)\)$"),
            lambda m: _WarningClassification(
                group_key=f"unknown_sp_breakdown|{m.group(1)}",
                display_base=f"Unknown SP/EF area for reporting SP breakdown: '{m.group(1)}'",
                iso3=m.group(2),
                rnd=m.group(3),
            ),
        ),
        (
            re.compile(
                r"^Emergency code '([^']+)' not found in GO API for ([A-Z]{3}) — imported using Excel name/code; review in form$"
            ),
            lambda m: _WarningClassification(
                group_key=f"ea_code_not_found|{m.group(1).upper()}",
                display_base=(
                    f"Emergency code '{m.group(1).upper()}' not found in GO API — "
                    "imported using Excel labels; review in form"
                ),
                iso3=m.group(2),
            ),
        ),
        (
            _EMERGENCY_APPEAL_NOT_LISTED_RE,
            lambda m: _WarningClassification(
                group_key=f"ea_code_not_found|{m.group(1).upper()}",
                display_base=(
                    f"Emergency appeal {m.group(1).upper()} is not listed in GO — "
                    "imported using the Excel name and code; please review it on the form"
                ),
            ),
        ),
        (
            re.compile(r"^Emergency appeal code (.+) not found in GO API for ([A-Z]{3})$"),
            lambda m: _WarningClassification(
                group_key=f"ea_code_not_found|{m.group(1)}",
                display_base=f"Emergency appeal code {m.group(1)} not found in GO API",
                iso3=m.group(2),
            ),
        ),
        (
            re.compile(r"^Reach (EA\d) for ([A-Z]{3}) missing EA Code — using GO slot (\d+): (.+)$"),
            lambda m: _WarningClassification(
                group_key=f"reach_ea_fallback|{m.group(1)}|slot={m.group(3)}",
                display_base=f"Reach {m.group(1)} missing EA Code — using GO slot {m.group(3)}: {m.group(4)}",
                iso3=m.group(2),
            ),
        ),
        (
            re.compile(r"^Funding row missing Year for ([A-Z]{3}) ([A-Z0-9]+)$"),
            lambda m: _WarningClassification(
                group_key="funding_missing_year",
                display_base="Funding row missing Year",
                iso3=m.group(1),
                rnd=m.group(2),
            ),
        ),
        (
            re.compile(r"^Reach row missing Year for ([A-Z]{3}) ([A-Z0-9]+) (\S+)$"),
            lambda m: _WarningClassification(
                group_key=f"reach_missing_year|{m.group(3)}",
                display_base=f"Reach row missing Year ({m.group(3)})",
                iso3=m.group(1),
                rnd=m.group(2),
            ),
        ),
        (
            re.compile(r"^No active NS found for host country: (.+)$"),
            lambda m: _WarningClassification(
                group_key="no_host_ns",
                display_base="No active NS found for host country",
                iso3=m.group(1).strip("'\""),
            ),
        ),
        (
            re.compile(r"^Cannot resolve Country\.id for ISO3: (.+)$"),
            lambda m: _WarningClassification(
                group_key="no_country_id",
                display_base="Cannot resolve Country.id for ISO3",
                iso3=m.group(1).strip("'\""),
            ),
        ),
        (
            re.compile(r"^No template 22 assignment for ([A-Z]{3}) (\S+) \(NS: (.+)\)$"),
            lambda m: _WarningClassification(
                group_key=f"no_t22_assignment|{m.group(3)}|{m.group(2)}",
                display_base=f"No template 22 assignment for {m.group(2)} (NS: {m.group(3)})",
                iso3=m.group(1),
            ),
        ),
        (
            re.compile(r"^Indicator bank id (\d+) not found; skipping dynamic import$"),
            lambda m: _WarningClassification(
                group_key=f"missing_indicator_bank|{m.group(1)}",
                display_base=f"Indicator bank id {m.group(1)} not found; skipping dynamic import",
                bank_id=m.group(1),
            ),
        ),
        (
            re.compile(
                r"^Percentage indicator '(.+)' = ([\-0-9.]+) is outside the valid 0-100% range "
                r"\(([A-Z]{3}) (\S+)\) — please check for a data-entry mistake "
                r"\(e\.g\. 500 instead of 50\)\.$"
            ),
            lambda m: _WarningClassification(
                group_key=f"percentage_out_of_range|{m.group(1)}",
                display_base=f"Percentage indicator {m.group(1)!r} has values outside the valid 0-100% range",
                iso3=m.group(3),
                rnd=m.group(4),
            ),
        ),
    )

    for pattern, builder in patterns:
        match = pattern.match(message)
        if match:
            return builder(match)
    return _WarningClassification(group_key=message, display_base=message)


def _format_warning_group_suffix(
    count: int,
    countries: Set[str],
    rounds: Set[str],
    *,
    bank_ids: Optional[Set[str]] = None,
) -> str:
    parts: List[str] = []
    if count > 1:
        parts.append(f"×{count}")
    if len(countries) > 1:
        parts.append(f"{len(countries)} countries")
    if bank_ids and len(bank_ids) > 1:
        parts.append(f"{len(bank_ids)} indicators")
    if rounds:
        ordered = sorted(rounds)
        if len(ordered) <= 4:
            parts.append(", ".join(ordered))
        else:
            parts.append(f"{len(ordered)} rounds")
    if not parts:
        return ""
    return f" ({', '.join(parts)})"


def summarize_warnings(warnings: List[str]) -> Dict[str, Any]:
    """Deduplicate warnings for display, grouping country/round variants of the same issue."""
    @dataclass
    class _Group:
        label: str
        count: int = 0
        countries: Set[str] = field(default_factory=set)
        rounds: Set[str] = field(default_factory=set)
        bank_ids: Set[str] = field(default_factory=set)

    groups: Dict[str, _Group] = {}
    order: List[str] = []

    for message in warnings:
        text = warning_text(message)
        parts = _classify_warning_for_grouping(text, raw=message)
        if parts.group_key not in groups:
            groups[parts.group_key] = _Group(label=parts.display_base)
            order.append(parts.group_key)
        group = groups[parts.group_key]
        group.count += 1
        if parts.iso3:
            group.countries.add(parts.iso3)
        if parts.rnd:
            group.rounds.add(parts.rnd)
        if parts.bank_id:
            group.bank_ids.add(parts.bank_id)

    summarized = [
        groups[key].label + _format_warning_group_suffix(
            groups[key].count,
            groups[key].countries,
            groups[key].rounds,
            bank_ids=groups[key].bank_ids or None,
        )
        for key in order
    ]
    return {
        "warnings": summarized,
        "warning_count": len(warnings),
        "warning_unique_count": len(order),
    }
