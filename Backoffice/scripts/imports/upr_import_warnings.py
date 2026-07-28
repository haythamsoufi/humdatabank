"""Warning grouping helpers for UPR Excel import preview and run summaries."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


@dataclass
class _WarningClassification:
    group_key: str
    display_base: str
    iso3: Optional[str] = None
    rnd: Optional[str] = None
    bank_id: Optional[str] = None


def _classify_warning_for_grouping(message: str) -> _WarningClassification:
    """Map a warning to a group key and display base, stripping country/round when useful."""
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
            re.compile(r"^Emergency appeal code (.+) not found in GO API for ([A-Z]{3})$"),
            lambda m: _WarningClassification(
                group_key=f"ea_code_not_found|{m.group(1)}",
                display_base=f"Emergency appeal code {m.group(1)} not found in GO API",
                iso3=m.group(2),
            ),
        ),
        (
            re.compile(
                r"^No EA Code for (EA\d) and only (\d+) appeal\(s\) in GO API for ([A-Z]{3}) — skipped$"
            ),
            lambda m: _WarningClassification(
                group_key=f"no_ea_code|{m.group(1)}|{m.group(2)}",
                display_base=f"No EA Code for {m.group(1)} and only {m.group(2)} appeal(s) in GO API — skipped",
                iso3=m.group(3),
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
        parts = _classify_warning_for_grouping(message)
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
