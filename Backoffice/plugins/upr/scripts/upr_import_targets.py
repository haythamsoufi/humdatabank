"""Precise UPR Master import targets: ``(template, round)`` ↔ assigned form.

Every import is an explicit list of targets. A target is one template plus one
UPR round (``24:P26``, ``33:MYR25`` …) and resolves to exactly one assigned form
(``template_id`` + canonical period). There is no "empty = everything" mode.

Legal pairs follow ``UPR_TEMPLATE_PROFILES``::

    P*   -> 24 (Unified Country Plan), 22 (PNS planning)
    AR*  -> 33 (Country reporting),    23 (PNS reporting)
    MYR* -> 33 (Country reporting)

``build_import_plan`` verifies every legal target against the live database and the
uploaded workbook and flags anything that is unmapped or ambiguous; the wizard and
``run_import_targets`` both refuse blocked targets.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import import_upr_excel_data as imp

logger = logging.getLogger(__name__)

ROUND_KIND_LABELS: Dict[str, str] = {
    "P": "Planning",
    "AR": "Annual report",
    "MYR": "Mid-year report",
}
_KIND_ORDER = {"P": 0, "AR": 1, "MYR": 2}

ISSUE_ERROR = "error"
ISSUE_WARNING = "warning"
ISSUE_INFO = "info"

STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_BLOCKED = "blocked"
STATUS_EMPTY = "empty"


class ImportTargetError(ValueError):
    """Raised for illegal, unmapped, or ambiguous import targets."""

    def __init__(self, message: str, *, errors: Optional[Sequence[str]] = None):
        super().__init__(message)
        self.errors: List[str] = list(errors or [message])


# ── Targets ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, order=True)
class ImportTarget:
    template_id: int
    round_code: str

    @property
    def period(self) -> Optional[str]:
        return imp.round_to_period(self.round_code)

    @property
    def key(self) -> str:
        return f"{self.template_id}:{self.round_code}"

    def as_dict(self) -> Dict[str, Any]:
        return {"template_id": self.template_id, "round": self.round_code, "key": self.key}


@dataclass(frozen=True)
class TargetGroup:
    """Targets sharing one template set — executed as a single ``run_upr_import``."""

    template_ids: Tuple[int, ...]
    rounds: Tuple[str, ...]

    @property
    def label(self) -> str:
        return f"templates {','.join(map(str, self.template_ids))} · {', '.join(self.rounds)}"


def round_kind(round_code: str) -> str:
    return imp.round_prefix(round_code)


def round_kind_label(round_code: str) -> str:
    return ROUND_KIND_LABELS.get(round_kind(round_code), "Unknown")


def legal_template_ids_for_round(round_code: str) -> Tuple[int, ...]:
    return tuple(
        tid for tid in sorted(imp.UPR_TEMPLATE_PROFILES) if imp.template_accepts_round(tid, round_code)
    )


def validate_target(template_id: int, round_code: str) -> Optional[str]:
    """Return an error message when the pair is not an importable target."""
    code = str(round_code or "").strip().upper()
    profile = imp.UPR_TEMPLATE_PROFILES.get(int(template_id))
    if profile is None:
        return f"Template {template_id} is not configured for UPR Excel import"
    if not imp.is_upr_master_importable_round(code):
        return (
            f"Round {code or '(empty)'} is outside the closed UPR Master set "
            f"({', '.join(sorted(imp.UPR_MASTER_ALLOWED_ROUNDS))})"
        )
    if not imp.template_accepts_round(template_id, code):
        prefixes = ", ".join(f"{p}*" for p in profile["round_prefixes"])
        return (
            f"Template {template_id} ({profile['name']}) does not import {code}; "
            f"it only accepts {prefixes} rounds"
        )
    if not imp.round_to_period(code):
        return f"Round {code} cannot be mapped to an assignment period"
    return None


def _coerce_target(raw: Any) -> Tuple[int, str]:
    if isinstance(raw, ImportTarget):
        return raw.template_id, raw.round_code
    if isinstance(raw, dict):
        tid = raw.get("template_id", raw.get("template"))
        rnd = raw.get("round", raw.get("round_code"))
        return int(tid), str(rnd or "").strip().upper()
    if isinstance(raw, (tuple, list)) and len(raw) == 2:
        return int(raw[0]), str(raw[1] or "").strip().upper()
    if isinstance(raw, str):
        match = re.fullmatch(r"\s*(\d+)\s*[:/ ]\s*([A-Za-z]+\d+)\s*", raw)
        if match:
            return int(match.group(1)), match.group(2).upper()
    raise ValueError(f"Unrecognised import target: {raw!r}")


def normalize_targets(raw_targets: Iterable[Any]) -> List[ImportTarget]:
    """Parse, validate, and de-duplicate targets; raise ``ImportTargetError`` on any problem."""
    errors: List[str] = []
    seen: Set[ImportTarget] = set()
    for raw in raw_targets or []:
        try:
            tid, rnd = _coerce_target(raw)
        except (TypeError, ValueError) as exc:
            errors.append(str(exc))
            continue
        problem = validate_target(tid, rnd)
        if problem:
            errors.append(problem)
            continue
        seen.add(ImportTarget(tid, rnd))
    if errors:
        raise ImportTargetError("Invalid import targets: " + "; ".join(errors), errors=errors)
    if not seen:
        raise ImportTargetError(
            "No import targets selected. Choose at least one (template, round) target.",
        )
    return sorted(seen, key=_target_sort_key)


def targets_from_templates_and_rounds(
    template_ids: Iterable[int],
    rounds: Iterable[str],
) -> List[ImportTarget]:
    """Legacy ``template_ids`` + ``rounds`` payload → explicit targets (rounds required)."""
    tids = [int(t) for t in template_ids or []]
    rnds = [str(r).strip().upper() for r in rounds or [] if str(r).strip()]
    if not rnds:
        raise ImportTargetError(
            "Rounds are required. An empty rounds list no longer means 'all rounds'; "
            "pick explicit (template, round) targets.",
        )
    if not tids:
        raise ImportTargetError("Templates are required with rounds.")
    errors: List[str] = []
    targets: List[ImportTarget] = []
    for rnd in rnds:
        legal = [t for t in tids if imp.template_accepts_round(t, rnd)]
        if not legal:
            errors.append(f"No selected template imports round {rnd}")
        for tid in legal:
            targets.append(ImportTarget(tid, rnd))
    if errors:
        raise ImportTargetError("Invalid import selection: " + "; ".join(errors), errors=errors)
    return normalize_targets(targets)


def _round_number(round_code: str) -> int:
    match = re.search(r"(\d+)$", str(round_code))
    return int(match.group(1)) if match else 0


def _target_sort_key(target: ImportTarget) -> Tuple[int, int, int]:
    kind = _KIND_ORDER.get(round_kind(target.round_code), 99)
    return (kind, -_round_number(target.round_code), target.template_id)


def group_targets(targets: Sequence[ImportTarget]) -> List[TargetGroup]:
    """Group rounds that share the same template set so each group is one safe import run."""
    templates_by_round: Dict[str, Set[int]] = defaultdict(set)
    for target in targets:
        templates_by_round[target.round_code].add(target.template_id)
    rounds_by_templates: Dict[Tuple[int, ...], List[str]] = defaultdict(list)
    for rnd, tset in templates_by_round.items():
        rounds_by_templates[tuple(sorted(tset))].append(rnd)
    groups = [
        TargetGroup(template_ids=tids, rounds=tuple(sorted(rnds)))
        for tids, rnds in rounds_by_templates.items()
    ]
    groups.sort(key=lambda g: (g.template_ids, g.rounds))
    return groups


# ── Workbook + database inspection ─────────────────────────────────────────


def _country_data_entities(rows: Iterable[Dict[str, Any]]) -> Set[Tuple[str, str]]:
    """``(round, ISO3)`` pairs that have at least one ``Source = Country Data`` row.

    A host country with only PNS Data, Mix Data, or IFRC System rows did not report
    for the country form and is not an import target.
    """
    found: Set[Tuple[str, str]] = set()
    for row in rows:
        rnd = str(row.get("Round") or "").strip().upper()
        iso3 = str(row.get("ISO3") or "").strip().upper()
        if rnd and iso3 and imp.parse_upr_source(row) == "country data":
            found.add((rnd, iso3))
    return found


def workbook_round_stats(
    rows: Iterable[Dict[str, Any]],
    ns_home_iso3: Dict[str, str],
) -> Dict[str, Dict[int, Dict[str, Any]]]:
    """Per round and template: rows the importer would read plus the entities they address.

    Country templates (24, 33) are addressed by host ISO3, and only when that country
    has at least one ``Country Data`` row in the round. PNS templates (22, 23) are
    addressed by the reporting National Society on a ``PNS Data`` row — France qualifies
    only when the NS column says French Red Cross, not because FRA appears as a host.
    """
    rows = list(rows)
    country_scope = _country_data_entities(rows)
    stats: Dict[str, Dict[int, Dict[str, Any]]] = {}
    for row in rows:
        rnd = str(row.get("Round") or "").strip().upper()
        if not rnd or imp.is_aggregate_row(row):
            continue
        sec = str(row.get("Section") or "").strip()
        prefix = imp.round_prefix(rnd)
        entity = str(row.get("Entity") or "").strip().upper()
        ns_name = str(row.get("NS") or "").strip()
        iso3 = str(row.get("ISO3") or "").strip().upper()
        for tid, profile in imp.UPR_TEMPLATE_PROFILES.items():
            if prefix not in tuple(profile.get("round_prefixes") or ()):
                continue
            if sec not in profile.get("sections", frozenset()):
                continue
            bucket = stats.setdefault(rnd, {}).setdefault(
                tid, {"rows": 0, "iso3": set(), "ns_names": set(), "ns_display": {}}
            )
            if tid in (22, 23):
                # Host-reported "Country Data" rows name the partner but are not the
                # partner's own submission. Only PNS Data rows qualify the society.
                if entity != "PNS" or not ns_name or ns_name.lower() == "country":
                    continue
                if not imp.is_pns_data_source(row):
                    continue
                name_key = ns_name.lower()
                bucket["ns_names"].add(name_key)
                bucket["ns_display"].setdefault(name_key, ns_name.strip())
            else:
                if not iso3 or (rnd, iso3) not in country_scope:
                    continue
                bucket["iso3"].add(iso3)
            bucket["rows"] += 1
    return stats


def load_assigned_form_index(template_ids: Sequence[int]) -> List[Dict[str, Any]]:
    """One record per assigned form of the given templates, with entity/status counts."""
    from sqlalchemy import and_

    from app.extensions import db
    from app.models.assignments import AssignedForm, AssignmentEntityStatus
    from app.models.core import Country

    query = (
        db.session.query(
            AssignedForm.id,
            AssignedForm.template_id,
            AssignedForm.period_name,
            AssignedForm.custom_name,
            AssignedForm.is_active,
            AssignedForm.is_closed,
            AssignmentEntityStatus.id,
            AssignmentEntityStatus.status,
            Country.iso3,
        )
        .outerjoin(AssignmentEntityStatus, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .outerjoin(
            Country,
            and_(
                Country.id == AssignmentEntityStatus.entity_id,
                AssignmentEntityStatus.entity_type == "country",
            ),
        )
        .filter(AssignedForm.template_id.in_([int(t) for t in template_ids]))
    )
    index: Dict[int, Dict[str, Any]] = {}
    for af_id, tid, period_name, custom_name, is_active, is_closed, aes_id, status, iso3 in query.all():
        rec = index.get(int(af_id))
        if rec is None:
            rec = {
                "id": int(af_id),
                "template_id": int(tid),
                "period_name": period_name,
                "canonical_period": imp.canonical_upr_period(period_name or ""),
                "custom_name": custom_name,
                "is_active": bool(is_active),
                "is_closed": bool(is_closed),
                "aes_total": 0,
                "status_counts": defaultdict(int),
                "iso3s": set(),
            }
            index[int(af_id)] = rec
        if aes_id is None:
            continue
        rec["aes_total"] += 1
        status_value = getattr(status, "value", status)
        rec["status_counts"][str(status_value)] += 1
        if iso3:
            rec["iso3s"].add(str(iso3).strip().upper())
    for rec in index.values():
        rec["status_counts"] = dict(rec["status_counts"])
    return list(index.values())


def template_readiness(ctx: "imp.UprImportContext", template_id: int) -> Dict[str, Any]:
    """Which published form items the importer needs for ``template_id`` — and which are missing."""
    tid = int(template_id)
    profile = imp.UPR_TEMPLATE_PROFILES.get(tid) or {}
    items: Dict[str, Optional[int]] = {}
    required: List[str] = []
    published = ctx.published_version_ids.get(tid)
    if tid == 22:
        items = {
            "staff_matrix": ctx.staff_matrix_item_id or None,
            "funding_requirements_matrix": ctx.t22_funding_item_id or None,
        }
        required = list(items)
    elif tid == 23:
        items = {"pns_funding_matrix": ctx.pns_funding_item_id or None}
        required = list(items)
    elif tid == 24:
        funding = ctx.t24_funding_by_offset or {}
        items = {
            "funding_matrix_current_year": funding.get(0),
            "longer_term_reach_matrix": ctx.t24_longer_term_item_id or None,
            "emergency_appeals_matrix": ctx.t24_emergency_item_id or None,
            "bilateral_support_matrix": ctx.t24_bilateral_item_id or None,
        }
        required = list(items)
    elif tid == imp.REPORTING_COUNTRY_TEMPLATE_ID:
        special = (getattr(ctx, "reporting_special_items", None) or {}).get(tid, {})
        items = {
            "funding_by_source_matrix": special.get("funding"),
            "expenditure": special.get("expenditure"),
        }
        required = list(items)
    missing = [] if published else ["published_version"]
    missing.extend(name for name in required if not items.get(name))
    return {
        "template_id": tid,
        "name": profile.get("name"),
        "published_version_id": int(published) if published else None,
        "items": {k: (int(v) if v else None) for k, v in items.items()},
        "missing": missing,
        "ready": not missing,
    }


def _country_label(iso: str, country_names: Dict[str, str]) -> str:
    """Display name for an ISO3 code. Falls back to the code when the name is unknown."""
    code = str(iso or "").strip().upper()
    return (country_names.get(code) or "").strip() or code


def _pns_skip_label(
    name: str,
    iso: Optional[str],
    *,
    display: Dict[str, str],
    country_names: Dict[str, str],
) -> str:
    """Label a skipped partner society by its name and home country, never by ISO code."""
    shown = (display.get(name) or name).strip()
    if not iso:
        return f"{shown} (no home country)"
    country = (country_names.get(str(iso).strip().upper()) or "").strip()
    if country:
        return f"{shown} ({country})"
    return shown


def _issue(level: str, code: str, message: str, **extra: Any) -> Dict[str, Any]:
    return {"level": level, "code": code, "message": message, **extra}


def _display_name(af: Dict[str, Any]) -> str:
    return (af.get("custom_name") or "").strip() or f"{af.get('period_name')}"


def build_import_plan(
    *,
    round_stats: Dict[str, Dict[int, Dict[str, Any]]],
    af_index: Sequence[Dict[str, Any]],
    readiness: Dict[int, Dict[str, Any]],
    ns_home_iso3: Dict[str, str],
    workbook_rounds: Iterable[str],
    pns_clear: Optional[Dict[str, Dict[str, int]]] = None,
    country_names: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Verify every legal ``(template, round)`` target. Pure: no database access.

    ``pns_clear`` maps target key → ``{"aes_to_clear", "aes_with_data", "aes_total"}``.
    """
    pns_clear = pns_clear or {}
    country_names = {
        str(iso or "").strip().upper(): str(name or "").strip()
        for iso, name in (country_names or {}).items()
        if str(iso or "").strip() and str(name or "").strip()
    }
    present_rounds = sorted({str(r).strip().upper() for r in workbook_rounds if str(r).strip()})

    allowed_present = [r for r in present_rounds if imp.is_upr_master_importable_round(r)]
    not_importable: List[Dict[str, str]] = []
    unrecognised: List[str] = []
    for rnd in present_rounds:
        if imp.is_upr_master_importable_round(rnd):
            continue
        if imp.round_prefix(rnd) in ROUND_KIND_LABELS:
            not_importable.append(
                {
                    "round": rnd,
                    "kind": round_kind_label(rnd),
                    "reason": "Outside the closed UPR Master set — live or future round, never imported.",
                }
            )
        else:
            unrecognised.append(rnd)

    targets_out: List[Dict[str, Any]] = []
    for rnd in sorted(allowed_present, key=lambda r: (_KIND_ORDER.get(round_kind(r), 99), -_round_number(r))):
        for tid in legal_template_ids_for_round(rnd):
            target = ImportTarget(tid, rnd)
            profile = imp.UPR_TEMPLATE_PROFILES[tid]
            stat = (round_stats.get(rnd) or {}).get(tid) or {"rows": 0, "iso3": set(), "ns_names": set()}
            issues: List[Dict[str, Any]] = []
            period = target.period
            matching = [
                af
                for af in af_index
                if af["template_id"] == tid and period and af["canonical_period"] == period
            ]
            item: Dict[str, Any] = {
                "key": target.key,
                "template_id": tid,
                "template_name": profile["name"],
                "round": rnd,
                "kind": round_kind_label(rnd),
                "period": period,
                "workbook_rows": int(stat["rows"]),
                "assigned_forms": [
                    {
                        "id": af["id"],
                        "period_name": af["period_name"],
                        "name": _display_name(af),
                        "is_active": af["is_active"],
                        "is_closed": af["is_closed"],
                        "entities": af["aes_total"],
                        "status_counts": af["status_counts"],
                    }
                    for af in matching
                ],
                "assigned_form_id": matching[0]["id"] if len(matching) == 1 else None,
                "entities_in_workbook": 0,
                "entities_matched": 0,
                "entities_unmatched": [],
            }

            if stat["rows"] == 0:
                issues.append(
                    _issue(
                        ISSUE_INFO,
                        "no_workbook_rows",
                        f"The workbook has no {profile['name']} rows for {rnd} — nothing to import.",
                    )
                )
            if not matching:
                issues.append(
                    _issue(
                        ISSUE_ERROR,
                        "no_assigned_form",
                        f"No assigned form exists for template {tid} and period '{period}'. "
                        "Nothing can be written until it is assigned.",
                    )
                )
            elif len(matching) > 1:
                ids = ", ".join(f"#{af['id']}" for af in matching)
                issues.append(
                    _issue(
                        ISSUE_ERROR,
                        "multiple_assigned_forms",
                        f"{len(matching)} assigned forms share template {tid} + period '{period}' "
                        f"({ids}). The importer needs exactly one — merge or close the duplicates.",
                    )
                )
            ready = readiness.get(tid) or {}
            if ready and not ready.get("ready", True):
                issues.append(
                    _issue(
                        ISSUE_ERROR,
                        "template_not_ready",
                        f"Template {tid} is missing published form items: "
                        f"{', '.join(ready.get('missing') or [])}.",
                    )
                )

            if len(matching) == 1:
                af = matching[0]
                if af["period_name"] != period:
                    issues.append(
                        _issue(
                            ISSUE_INFO,
                            "period_alias",
                            f"The assigned period is named '{af['period_name']}' and is matched "
                            f"to {rnd} via '{period}'.",
                        )
                    )
                if af["aes_total"] == 0:
                    issues.append(
                        _issue(
                            ISSUE_ERROR,
                            "no_entities",
                            "This form has no assigned entities.",
                        )
                    )
                # A closed assignment is the normal state of historical rounds, so it is not flagged.
                if not af["is_active"]:
                    issues.append(
                        _issue(ISSUE_WARNING, "assigned_form_inactive", "This assigned form is paused.")
                    )

                display = stat.get("ns_display") or {}
                if tid in (22, 23):
                    homes: Dict[str, str] = {}
                    unresolved: List[str] = []
                    for name in stat["ns_names"]:
                        home = ns_home_iso3.get(name)
                        if home:
                            homes[name] = home
                        else:
                            unresolved.append(name)
                    keys = set(homes.values())
                    matched = keys & af["iso3s"]
                    missing_assignment = [
                        _pns_skip_label(name, iso, display=display, country_names=country_names)
                        for name, iso in sorted(homes.items())
                        if iso not in af["iso3s"]
                    ]
                    unmatched = [
                        _pns_skip_label(name, None, display=display, country_names=country_names)
                        for name in sorted(unresolved)
                    ] + missing_assignment
                    item["entities_in_workbook"] = len(keys) + len(unresolved)
                else:
                    keys = set(stat["iso3"])
                    matched = keys & af["iso3s"]
                    unmatched = [
                        _country_label(iso, country_names) for iso in sorted(keys - af["iso3s"])
                    ]
                    item["entities_in_workbook"] = len(keys)
                item["entities_matched"] = len(matched)
                item["entities_unmatched"] = list(unmatched)
                item["entities_unmatched_total"] = len(unmatched)

                if stat["rows"] and item["entities_in_workbook"] and not matched:
                    issues.append(
                        _issue(
                            ISSUE_ERROR,
                            "no_matching_entities",
                            f"None of the {item['entities_in_workbook']} workbook entities have an assignment "
                            "and will be skipped.",
                            items=list(unmatched),
                        )
                    )
                elif unmatched:
                    skipped = len(unmatched)
                    entity_word = "workbook entity" if skipped == 1 else "workbook entities"
                    verb = "has" if skipped == 1 else "have"
                    issues.append(
                        _issue(
                            ISSUE_WARNING,
                            "unmatched_entities",
                            f"{skipped} {entity_word} {verb} no assignment and will be skipped.",
                            items=list(unmatched),
                        )
                    )

                counts = af["status_counts"]
                touched = sum(n for st, n in counts.items() if st != "pending")
                if touched and stat["rows"]:
                    parts = ", ".join(f"{n} {st}" for st, n in sorted(counts.items()) if st != "pending")
                    issues.append(
                        _issue(
                            ISSUE_WARNING,
                            "existing_progress",
                            f"{touched} of {af['aes_total']} assignments already have "
                            f"saved data ({parts}). The import will replace those saved values "
                            "in matching cells.",
                        )
                    )

                clear = pns_clear.get(target.key)
                if clear and clear.get("aes_to_clear"):
                    level = ISSUE_WARNING if clear.get("aes_with_data") else ISSUE_INFO
                    issues.append(
                        _issue(
                            level,
                            "pns_clear",
                            f"{clear['aes_to_clear']} PNS assignments have no "
                            "PNS-reported rows in the workbook; their imported funding/staff data is "
                            f"cleared and status reset to pending ({clear.get('aes_with_data', 0)} currently hold data).",
                        )
                    )
                    item["pns_clear"] = clear
                if clear and clear.get("aes_to_approve"):
                    issues.append(
                        _issue(
                            ISSUE_INFO,
                            "pns_approve",
                            f"{clear['aes_to_approve']} PNS assignments that receive workbook data "
                            "will be marked approved.",
                        )
                    )

            has_error = any(i["level"] == ISSUE_ERROR for i in issues)
            has_warning = any(i["level"] == ISSUE_WARNING for i in issues)
            if stat["rows"] == 0:
                status = STATUS_EMPTY
            elif has_error:
                status = STATUS_BLOCKED
            elif has_warning:
                status = STATUS_WARNING
            else:
                status = STATUS_OK
            item["status"] = status
            item["selectable"] = status in (STATUS_OK, STATUS_WARNING)
            item["issues"] = issues
            targets_out.append(item)

    summary = {STATUS_OK: 0, STATUS_WARNING: 0, STATUS_BLOCKED: 0, STATUS_EMPTY: 0}
    for item in targets_out:
        summary[item["status"]] += 1

    missing_allowlisted = sorted(
        (r for r in imp.UPR_MASTER_ALLOWED_ROUNDS if r not in allowed_present),
        key=lambda r: (_KIND_ORDER.get(round_kind(r), 99), -_round_number(r)),
    )
    return {
        "success": True,
        "targets": targets_out,
        "templates": [readiness[t] for t in sorted(readiness)],
        "not_importable_rounds": not_importable,
        "unrecognised_rounds": unrecognised,
        "allowlisted_rounds_missing": missing_allowlisted,
        "summary": summary,
    }


def _compute_pns_clear(
    rows: List[Dict[str, Any]],
    ctx: "imp.UprImportContext",
    plan_targets: List[Dict[str, Any]],
) -> Dict[str, Dict[str, int]]:
    """Per PNS target: assignments the import will clear (not reported in the workbook)."""
    from sqlalchemy import distinct, func

    from app.extensions import db
    from app.models.forms import FormData

    out: Dict[str, Dict[str, int]] = {}
    for item in plan_targets:
        tid = item["template_id"]
        if tid not in (22, 23) or not item.get("assigned_form_id") or not item["workbook_rows"]:
            continue
        rnd = item["round"]
        t22_yes, t23_yes = imp._build_pns_reported_yes_sets(rows, ctx, [tid], rounds={rnd})
        reported_aes = {int(a) for a, _ in (t22_yes if tid == 22 else t23_yes)}
        aes_ids = imp.target_aes_ids(ctx, [tid], {rnd})
        to_clear = aes_ids - reported_aes
        item_ids = imp.upr_pns_import_item_ids(ctx, tid)
        with_data = 0
        if to_clear and item_ids:
            with_data = int(
                db.session.query(func.count(distinct(FormData.assignment_entity_status_id)))
                .filter(
                    FormData.assignment_entity_status_id.in_(sorted(to_clear)),
                    FormData.form_item_id.in_(sorted(item_ids)),
                )
                .scalar()
                or 0
            )
        out[item["key"]] = {
            "aes_total": len(aes_ids),
            "aes_to_clear": len(to_clear),
            "aes_with_data": with_data,
            "aes_to_approve": len(reported_aes & aes_ids),
        }
    return out


def build_import_plan_from_db(path: str, *, use_row_cache: bool = True) -> Dict[str, Any]:
    """Read the workbook and the live database, then verify every legal target.

    Needs an active Flask app context.
    """
    _headers, rows = imp.load_upr_data_sheet_cached(path, use_cache=use_row_cache)
    template_ids = sorted(imp.UPR_TEMPLATE_PROFILES)
    ctx = imp.build_import_context(template_ids)
    af_index = load_assigned_form_index(template_ids)
    readiness = {tid: template_readiness(ctx, tid) for tid in template_ids}
    round_stats = workbook_round_stats(rows, ctx.ns_home_country_iso3)
    workbook_rounds = {str(r.get("Round") or "").strip().upper() for r in rows}

    plan_kwargs = dict(
        round_stats=round_stats,
        af_index=af_index,
        readiness=readiness,
        ns_home_iso3=ctx.ns_home_country_iso3,
        workbook_rounds=workbook_rounds,
        country_names=ctx.country_name_by_iso3,
    )
    plan = build_import_plan(**plan_kwargs)
    # Second pass adds the PNS "will be cleared" counts (needs DB + full context).
    pns_clear = _compute_pns_clear(rows, ctx, plan["targets"])
    if pns_clear:
        plan = build_import_plan(**plan_kwargs, pns_clear=pns_clear)
    plan["total_rows"] = len(rows)
    return plan


def verify_targets(
    plan: Dict[str, Any],
    targets: Sequence[ImportTarget],
) -> Dict[str, Dict[str, Any]]:
    """Return ``key → plan item`` for the selected targets or raise ``ImportTargetError``."""
    by_key = {item["key"]: item for item in plan.get("targets", [])}
    errors: List[str] = []
    for target in targets:
        item = by_key.get(target.key)
        if item is None:
            errors.append(f"{target.key}: round {target.round_code} is not present in the uploaded workbook")
            continue
        if item["selectable"]:
            continue
        reasons = [
            i["message"] for i in item["issues"] if i["level"] in (ISSUE_ERROR, ISSUE_INFO)
        ] or ["not importable"]
        errors.append(f"{target.key} ({item['template_name']} · {item['round']}): " + " ".join(reasons))
    if errors:
        raise ImportTargetError(
            "Import blocked — some selected targets are not mapped correctly: " + " | ".join(errors),
            errors=errors,
        )
    return {t.key: by_key[t.key] for t in targets}


# ── Execution ──────────────────────────────────────────────────────────────


def _app_context():
    try:
        from flask import current_app as _cur

        _cur._get_current_object()
        return nullcontext()
    except RuntimeError:
        from app import create_app

        return create_app().app_context()


def _merge_stats(acc: Dict[str, Any], stats: Dict[str, Any]) -> None:
    for key, value in (stats or {}).items():
        if key in ("preview_path", "success"):
            continue
        if key == "warnings":
            bucket = acc.setdefault("warnings", [])
            bucket.extend(w for w in (value or []) if w not in bucket)
        elif isinstance(value, bool):
            acc[key] = bool(acc.get(key)) or value
        elif isinstance(value, (int, float)):
            acc[key] = acc.get(key, 0) + value
        else:
            acc[key] = value


def run_import_targets(
    input_path: str,
    targets: Iterable[Any],
    *,
    dry_run: bool = False,
    batch_size: int = 1000,
    preview_excel_path: Optional[str] = None,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    use_row_cache: bool = True,
    use_transform_cache: bool = True,
    change_recorder: Optional[Callable[[Dict[str, Any]], None]] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Verify the selected targets against live data, then import them group by group.

    ``user_id`` is the acting user passed to each group's ``run_upr_import``
    call for PNS status changes. Imports do not write entity activity rows.
    """
    selected = normalize_targets(targets)
    groups = group_targets(selected)

    with _app_context():
        if progress_cb:
            progress_cb({"stage": "verify", "message": "Verifying target mapping...", "percent": 1.0})
        plan = build_import_plan_from_db(input_path, use_row_cache=use_row_cache)
        resolved = verify_targets(plan, selected)

        total = len(groups)
        merged: Dict[str, Any] = {}
        preview_rows: Optional[List[Dict[str, str]]] = [] if (preview_excel_path and dry_run) else None
        for index, group in enumerate(groups):

            def _scaled(payload: Dict[str, Any], _i: int = index, _g: TargetGroup = group) -> None:
                if not progress_cb:
                    return
                out = dict(payload)
                pct = out.get("percent")
                if pct is not None:
                    out["percent"] = min(99.0, 2.0 + (_i + float(pct) / 100.0) * 97.0 / total)
                if out.get("stage") == "complete":
                    out["stage"] = "group_complete"
                    out.pop("stats", None)
                if out.get("message"):
                    out["message"] = f"[{_g.label}] {out['message']}"
                progress_cb(out)

            stats = imp.run_upr_import(
                input_path,
                template_ids=list(group.template_ids),
                rounds=list(group.rounds),
                dry_run=dry_run,
                batch_size=batch_size,
                progress_cb=_scaled,
                cancel_check=cancel_check,
                use_row_cache=use_row_cache,
                use_transform_cache=use_transform_cache,
                change_recorder=change_recorder,
                collect_preview_rows=preview_rows,
                user_id=user_id,
            )
            _merge_stats(merged, stats)

        if preview_rows is not None and preview_rows:
            imp.write_rows_to_excel(preview_rows, preview_excel_path)
            merged["preview_path"] = preview_excel_path

        merged["targets"] = [t.key for t in selected]
        merged["assigned_forms"] = {key: item.get("assigned_form_id") for key, item in resolved.items()}
        merged["target_groups"] = [
            {"template_ids": list(g.template_ids), "rounds": list(g.rounds)} for g in groups
        ]
        if progress_cb:
            progress_cb(
                {"stage": "complete", "message": "UPR import completed.", "percent": 100.0, "stats": merged}
            )
        return merged


def preview_targets(
    input_path: str,
    targets: Iterable[Any],
    *,
    use_row_cache: bool = True,
) -> Dict[str, Any]:
    """Dry transform of the selected targets: row counts, warnings, PNS clear counts."""
    selected = normalize_targets(targets)
    groups = group_targets(selected)

    with _app_context():
        plan = build_import_plan_from_db(input_path, use_row_cache=use_row_cache)
        resolved = verify_targets(plan, selected)

        by_item: Dict[str, int] = {}
        by_iso3: Dict[str, int] = {}
        transformed = 0
        dynamic_rows = 0
        all_warnings: List[str] = []
        from_cache_all = True
        for group in groups:
            imp.assert_import_scope(list(group.template_ids), set(group.rounds))
            import_rows, ctx, from_cache = imp.prepare_upr_transform(
                input_path,
                list(group.template_ids),
                rounds=list(group.rounds),
                use_row_cache=use_row_cache,
                use_transform_cache=True,
                save_transform_cache=True,
            )
            from_cache_all = from_cache_all and from_cache
            transformed += len(import_rows)
            dynamic_rows += len(ctx.dynamic_indicator_entries)
            all_warnings.extend(ctx.warnings)
            for row in import_rows:
                item_id = row.get("item_id") or row.get("form_item_id")
                iso3 = row.get("_debug_iso3") or ""
                if item_id:
                    by_item[str(item_id)] = by_item.get(str(item_id), 0) + 1
                if iso3:
                    by_iso3[iso3] = by_iso3.get(iso3, 0) + 1
        summary = imp.summarize_warnings(all_warnings)
        return {
            "success": True,
            "transformed_rows": transformed,
            "dynamic_rows": dynamic_rows,
            "by_item": by_item,
            "countries": len(by_iso3),
            "from_transform_cache": from_cache_all,
            "targets": [
                {
                    "key": key,
                    "template_id": item["template_id"],
                    "template_name": item["template_name"],
                    "round": item["round"],
                    "period": item["period"],
                    "assigned_form_id": item["assigned_form_id"],
                    "status": item["status"],
                    "pns_clear": item.get("pns_clear"),
                }
                for key, item in resolved.items()
            ],
            **summary,
        }
