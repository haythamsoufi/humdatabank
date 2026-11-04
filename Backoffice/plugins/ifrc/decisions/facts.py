"""Turn the Unified Plan/Report extract into permission-filtered observations.

The extract comes from ``plugins.upr.upr_data`` (the same fact tables the Power BI endpoints serve), cached
against the database revision. That cache holds source facts only and is never keyed to a user. Each
request filters the rows to the user's countries here, before any metric or rule is calculated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable

from plugins.ifrc.decisions.access import AccessContext
from plugins.ifrc.decisions.config import FLAG_STATUSES, LANGUAGES, SEVERITIES
from plugins.ifrc.decisions.metrics import (
    DRAFT,
    NOT_APPLICABLE,
    PROVISIONAL,
    REPORTED,
    UNAVAILABLE,
    VALIDATED,
    METRIC_REGISTRY,
    Observation,
    evidence_id_for,
    validation_state_for,
)

_ROUND_RE = re.compile(r"^[A-Z]{1,3}\d{2}$")
_ISO3_RE = re.compile(r"^[A-Za-z]{3}$")
_FUNDING_ENTITIES = frozenset({"HNS", "IFRC Secretariat", "PNS"})
_STALLED_STATUSES = frozenset({"submitted", "sent_for_review"})
_OPEN_STATUSES = frozenset({"pending", "in_progress", "requires_revision"})
_SUBMITTED_STATUSES = frozenset({"submitted", "sent_for_review", "approved"})
_HEADLINE_ATTRIBUTES = frozenset({"total", "row_total"})
VALIDATION_FILTERS = (VALIDATED, PROVISIONAL, DRAFT)


@dataclass(frozen=True)
class Filters:
    region: str | None = None
    country: str | None = None
    round: str | None = None
    year: int | None = None
    strategic_priority: str | None = None
    funding_source: str | None = None
    validation_state: str | None = None
    flag_status: str | None = None
    severity: str | None = None
    lang: str = "en"

    @classmethod
    def from_args(cls, args: Any) -> "Filters":
        """Parse request arguments. Raises ``ValueError`` with a fixed message for bad input."""

        def one(name: str) -> str | None:
            raw = (args.get(name) or "").strip()
            return raw or None

        country = one("country")
        if country and not _ISO3_RE.match(country):
            raise ValueError("country must be a 3-letter ISO code")
        round_code = one("round")
        if round_code:
            round_code = round_code.upper()
            if not _ROUND_RE.match(round_code):
                raise ValueError("round must look like P27, AR26 or MYR26")
        year = one("year")
        if year and not (year.isdigit() and len(year) == 4):
            raise ValueError("year must be a 4-digit year")
        validation_state = one("validation_state")
        if validation_state and validation_state not in VALIDATION_FILTERS:
            raise ValueError("validation_state must be validated, provisional or draft")
        flag_status = one("flag_status")
        if flag_status and flag_status not in FLAG_STATUSES:
            raise ValueError("flag_status is not recognised")
        severity = one("severity")
        if severity and severity not in SEVERITIES:
            raise ValueError("severity is not recognised")
        lang = (one("lang") or "en").lower()
        if lang not in LANGUAGES:
            lang = "en"
        free = {name: (one(name) or "")[:80] or None for name in ("region", "strategic_priority", "funding_source")}
        return cls(
            region=free["region"],
            country=country.upper() if country else None,
            round=round_code,
            year=int(year) if year else None,
            strategic_priority=free["strategic_priority"],
            funding_source=free["funding_source"],
            validation_state=validation_state,
            flag_status=flag_status,
            severity=severity,
            lang=lang,
        )

    def as_scope(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None and k != "lang"}


@dataclass(frozen=True)
class Submission:
    submission_id: int | None
    round: str
    kind: str  # plan | report
    iso3: str
    country: str
    region: str | None
    ns: str | None
    status: str
    validation_state: str
    submitted_at: date | None
    due_date: date | None
    year: int | None


@dataclass
class DecisionData:
    submissions: list[Submission] = field(default_factory=list)
    observations: dict[str, list[Observation]] = field(default_factory=dict)
    built_at: str | None = None
    today: date = field(default_factory=lambda: datetime.now(timezone.utc).date())
    notes: list[str] = field(default_factory=list)

    def obs(self, metric_id: str) -> list[Observation]:
        return self.observations.get(metric_id, [])


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _round_kind(round_code: str | None) -> str:
    return "plan" if (round_code or "").upper().startswith("P") else "report"


def _round_year(round_code: str | None) -> int | None:
    match = re.search(r"(\d{2})$", round_code or "")
    return 2000 + int(match.group(1)) if match else None


def _to_submission(row: dict[str, Any], kind: str | None = None) -> Submission | None:
    round_code = (row.get("Round") or "").strip().upper()
    iso3 = (row.get("ISO3") or "").strip().upper()
    if not round_code or not iso3:
        return None
    status = (row.get("status") or "").strip().lower()
    if status == "cancelled":
        return None
    return Submission(
        submission_id=row.get("submission_id"),
        round=round_code,
        kind=kind or _round_kind(round_code),
        iso3=iso3,
        country=row.get("Country") or iso3,
        region=row.get("Region"),
        ns=row.get("NS"),
        status=status,
        validation_state=validation_state_for(status),
        submitted_at=_parse_date(row.get("submitted_at")),
        due_date=_parse_date(row.get("due_date")),
        year=_round_year(round_code),
    )


def _matches(filters: Filters, *, iso3: str | None, region: str | None, round_code: str | None) -> bool:
    if filters.country and (iso3 or "").upper() != filters.country:
        return False
    if filters.region and (region or "").strip().lower() != filters.region.strip().lower():
        return False
    if filters.round and (round_code or "").upper() != filters.round:
        return False
    return True


def _unavailable_label(label: Any) -> bool:
    return "data not available" in str(label or "").lower()


def _not_applicable_label(label: Any) -> bool:
    return str(label or "").strip().lower() == "not applicable"


def _evidence_extra(row: dict[str, Any], sub: Submission | None, built_at: str | None) -> dict[str, Any]:
    return {
        "source_system": "ifrc_databank",
        "dataset": "unified_plan",
        "submission_id": row.get("submission_id"),
        "indicator": row.get("Indicator"),
        "section": row.get("Section"),
        "attribute": row.get("Attribute"),
        "pns_reported": row.get("PNS reported"),
        "source": row.get("Source"),
        "status": sub.status if sub else None,
        "visibility": "ifrc_internal",
        "synchronized_at": built_at,
    }


def _funding_observations(
    facts: Iterable[dict[str, Any]], subs: dict[Any, Submission], built_at: str | None
) -> tuple[list[Observation], list[Observation], list[Observation]]:
    """Totals per (submission, year, source, PNS), a breakdown by Strategic Priority and the emergency share.

    Mirrors the Backoffice's own rule: the sum of the Strategic Priority columns is used when present,
    otherwise the Total column. Zero cells are not emitted by the extract, so an absent row is
    "not reported", never zero.
    """
    totals: dict[tuple, dict[str, Any]] = {}
    breakdown: list[Observation] = []
    emergency: list[Observation] = []
    for row in facts:
        if row.get("Section") != "Funding" or row.get("Indicator") != "Funding":
            continue
        entity = row.get("Entity")
        if entity not in _FUNDING_ENTITIES:
            continue
        number = row.get("ValueNum")
        if not isinstance(number, (int, float)) or isinstance(number, bool):
            continue
        sub = subs.get(row.get("submission_id"))
        round_code = row.get("Round")
        year = row.get("Year")
        key = (row.get("submission_id"), row.get("ISO3"), round_code, year, entity, row.get("NS"))
        slot = totals.setdefault(key, {"parts": 0.0, "has_parts": False, "total": 0.0, "row": row, "sub": sub})
        attribute = str(row.get("Attribute") or "")
        if attribute == "Total":
            slot["total"] += float(number)
            continue
        slot["parts"] += float(number)
        slot["has_parts"] = True
        priority = row.get("SP/EF") or ("Emergency operations" if attribute == "Emergency Operations" else attribute)
        targets = [("funding_requirement_by_priority", breakdown)]
        if attribute == "Emergency Operations":
            targets.append(("emergency_funding_requirement", emergency))
        for metric_id, bucket in targets:
            bucket.append(
                _funding_obs(
                    metric_id, row, sub, float(number), built_at,
                    priority=str(priority), evidence_key=(attribute, priority),
                )
            )
    out = []
    for slot in totals.values():
        value = slot["parts"] if slot["has_parts"] else slot["total"]
        out.append(_funding_obs("funding_requirement", slot["row"], slot["sub"], value, built_at))
    return out, breakdown, emergency


def _funding_obs(
    metric_id: str,
    row: dict[str, Any],
    sub: Submission | None,
    value: float,
    built_at: str | None,
    *,
    priority: str | None = None,
    evidence_key: tuple = (),
) -> Observation:
    if sub is not None:
        validation = sub.validation_state
    else:
        validation = PROVISIONAL if row.get("PNS reported") == "Yes" else DRAFT
    entity = row.get("Entity")
    ns = row.get("NS")
    label = f"{entity}: {ns}" if entity == "PNS" and ns else entity
    return Observation(
        metric_id=metric_id,
        entity_id=str(row.get("ISO3") or ""),
        entity_name=str(row.get("Country") or row.get("ISO3") or ""),
        region=row.get("Region"),
        round=row.get("Round"),
        year=row.get("Year"),
        state=REPORTED,
        value=value,
        validation_state=validation,
        submission_id=row.get("submission_id"),
        status=sub.status if sub else None,
        unit="CHF",
        currency="CHF",
        funding_source=entity,
        strategic_priority=priority,
        ns=ns,
        label=label,
        evidence_id=evidence_id_for(metric_id, row.get("submission_id"), row.get("Year"), entity, ns, *evidence_key),
        extra=_evidence_extra(row, sub, built_at),
    )


def _people_observations(
    facts: Iterable[dict[str, Any]], plan_subs: list[Submission], built_at: str | None
) -> list[Observation]:
    """Headline people to be reached per submission and year. Not additive across Strategic Priorities."""
    best: dict[tuple, dict[str, Any]] = {}
    states: dict[int | None, str] = {}
    for row in facts:
        if row.get("Section") != "Reach" or row.get("Indicator") != "People to be reached":
            continue
        sid = row.get("submission_id")
        label = row.get("Applicable/Data not available")
        number = row.get("ValueNum")
        if isinstance(number, (int, float)) and not isinstance(number, bool):
            if str(row.get("Attribute") or "").lower() in _HEADLINE_ATTRIBUTES:
                key = (sid, row.get("Year"))
                if key not in best or number > best[key]["ValueNum"]:
                    best[key] = row
        elif _not_applicable_label(label):
            states.setdefault(sid, NOT_APPLICABLE)
        elif _unavailable_label(label):
            states[sid] = UNAVAILABLE
    out: list[Observation] = []
    with_value = set()
    for (sid, year), row in best.items():
        with_value.add(sid)
        sub = next((s for s in plan_subs if s.submission_id == sid), None)
        out.append(_people_obs(row, sub, float(row["ValueNum"]), REPORTED, year, built_at))
    for sub in plan_subs:
        if sub.submission_id in with_value:
            continue
        state = states.get(sub.submission_id)
        if state is None:
            continue
        out.append(
            _people_obs(
                {"ISO3": sub.iso3, "Country": sub.country, "Region": sub.region, "Round": sub.round,
                 "submission_id": sub.submission_id, "Year": sub.year, "Indicator": "People to be reached",
                 "Section": "Reach"},
                sub, None, state, sub.year, built_at,
            )
        )
    return out


def _people_obs(
    row: dict[str, Any], sub: Submission | None, value: float | None, state: str, year: Any, built_at: str | None
) -> Observation:
    return Observation(
        metric_id="people_targeted",
        entity_id=str(row.get("ISO3") or ""),
        entity_name=str(row.get("Country") or row.get("ISO3") or ""),
        region=row.get("Region"),
        round=row.get("Round"),
        year=year,
        state=state,
        value=value,
        validation_state=sub.validation_state if sub else DRAFT,
        submission_id=row.get("submission_id"),
        status=sub.status if sub else None,
        unit="people",
        evidence_id=evidence_id_for("people_targeted", row.get("submission_id"), year),
        extra=_evidence_extra(row, sub, built_at),
    )


def _emergency_people_observations(
    facts: Iterable[dict[str, Any]], subs: dict[Any, Submission], built_at: str | None
) -> list[Observation]:
    """People to be reached per emergency operation (largest cell), added across operations."""
    per_operation: dict[tuple, float] = {}
    for row in facts:
        if row.get("Section") != "Emergencies" or row.get("Indicator") != "People to be reached":
            continue
        number = row.get("ValueNum")
        if not isinstance(number, (int, float)) or isinstance(number, bool):
            continue
        key = (row.get("submission_id"), row.get("Year"), row.get("Attribute"))
        per_operation[key] = max(per_operation.get(key, 0.0), float(number))
    grouped: dict[tuple, list[float]] = {}
    for (sid, year, _operation), number in per_operation.items():
        grouped.setdefault((sid, year), []).append(number)
    out = []
    for (sid, year), numbers in grouped.items():
        sub = subs.get(sid)
        if sub is None:
            continue
        out.append(
            Observation(
                metric_id="emergency_people_targeted",
                entity_id=sub.iso3,
                entity_name=sub.country,
                region=sub.region,
                round=sub.round,
                year=year,
                state=REPORTED,
                value=sum(numbers),
                validation_state=sub.validation_state,
                submission_id=sid,
                status=sub.status,
                unit="people",
                evidence_id=evidence_id_for("emergency_people_targeted", sid, year),
                extra={
                    "source_system": "ifrc_databank",
                    "dataset": "unified_plan",
                    "submission_id": sid,
                    "operations": len(numbers),
                    "visibility": "ifrc_internal",
                    "synchronized_at": built_at,
                },
            )
        )
    return out


def _pns_support_observations(
    facts: Iterable[dict[str, Any]],
    funding: Iterable[Observation],
    subs: dict[Any, Submission],
    built_at: str | None,
) -> list[Observation]:
    """Distinct PNS per country and round with a planned contribution or bilateral support. Absent means not reported."""
    partners: dict[tuple, dict[str, Any]] = {}

    def add(sid: Any, iso3: Any, round_code: Any, country: Any, region: Any, name: str) -> None:
        entry = partners.setdefault((sid, iso3, round_code), {"names": set(), "country": country, "region": region})
        entry["names"].add(name)

    for obs in funding:
        if obs.funding_source == "PNS" and obs.ns and (obs.value or 0) > 0:
            add(obs.submission_id, obs.entity_id, obs.round, obs.entity_name, obs.region, obs.ns)
    for row in facts:
        number = row.get("ValueNum")
        if (
            row.get("Section") == "Support"
            and row.get("Entity") == "PNS"
            and row.get("NS")
            and isinstance(number, (int, float))
            and not isinstance(number, bool)
            and number > 0
        ):
            add(row.get("submission_id"), row.get("ISO3"), row.get("Round"), row.get("Country"), row.get("Region"), str(row["NS"]))
    out = []
    for (sid, iso3, round_code), entry in partners.items():
        sub = subs.get(sid)
        if sub is None or not iso3:
            continue
        out.append(
            Observation(
                metric_id="pns_support_count",
                entity_id=str(iso3),
                entity_name=str(entry["country"] or iso3),
                region=entry["region"],
                round=round_code,
                year=_round_year(round_code),
                state=REPORTED,
                value=float(len(entry["names"])),
                validation_state=sub.validation_state,
                submission_id=sid,
                status=sub.status,
                unit="count",
                evidence_id=evidence_id_for("pns_support_count", sid),
                extra={
                    "source_system": "ifrc_databank",
                    "dataset": "unified_plan",
                    "submission_id": sid,
                    "partners": sorted(entry["names"])[:25],
                    "visibility": "ifrc_internal",
                    "synchronized_at": built_at,
                },
            )
        )
    return out


_CORE_SECTIONS = frozenset({"Core indicators", "NS Data"})


def _core_indicator_observations(
    facts: Iterable[dict[str, Any]], subs: dict[Any, Submission], built_at: str | None
) -> list[Observation]:
    per_sub: dict[Any, set[str]] = {}
    for row in facts:
        number = row.get("ValueNum")
        if row.get("Section") not in _CORE_SECTIONS or not isinstance(number, (int, float)) or isinstance(number, bool):
            continue
        per_sub.setdefault(row.get("submission_id"), set()).add(str(row.get("Indicator") or row.get("SectionB") or ""))
    out = []
    for sid, names in per_sub.items():
        sub = subs.get(sid)
        if sub is None:
            continue
        out.append(
            Observation(
                metric_id="core_indicators_reported",
                entity_id=sub.iso3,
                entity_name=sub.country,
                region=sub.region,
                round=sub.round,
                year=sub.year,
                state=REPORTED,
                value=float(len(names)),
                validation_state=sub.validation_state,
                submission_id=sid,
                status=sub.status,
                unit="count",
                evidence_id=evidence_id_for("core_indicators_reported", sid),
                extra={
                    "source_system": "ifrc_databank",
                    "dataset": "unified_plan",
                    "submission_id": sid,
                    "indicators": sorted(n for n in names if n)[:25],
                    "visibility": "ifrc_internal",
                    "synchronized_at": built_at,
                },
            )
        )
    return out


def _unavailable_observations(
    facts: Iterable[dict[str, Any]], subs: dict[Any, Submission], built_at: str | None
) -> list[Observation]:
    per_sub: dict[Any, list[dict[str, Any]]] = {}
    for row in facts:
        if _unavailable_label(row.get("Applicable/Data not available")):
            per_sub.setdefault(row.get("submission_id"), []).append(row)
    out = []
    for sid, rows in per_sub.items():
        sub = subs.get(sid)
        if sub is None:
            continue
        names = sorted({str(r.get("Indicator") or r.get("Section") or "") for r in rows if r.get("Indicator") or r.get("Section")})
        out.append(
            Observation(
                metric_id="indicators_data_unavailable",
                entity_id=sub.iso3,
                entity_name=sub.country,
                region=sub.region,
                round=sub.round,
                year=sub.year,
                state=REPORTED,
                value=float(len(rows)),
                validation_state=sub.validation_state,
                submission_id=sid,
                status=sub.status,
                unit="count",
                evidence_id=evidence_id_for("indicators_data_unavailable", sid),
                extra={
                    "source_system": "ifrc_databank",
                    "dataset": "unified_plan",
                    "submission_id": sid,
                    "indicators": names[:25],
                    "visibility": "ifrc_internal",
                    "synchronized_at": built_at,
                },
            )
        )
    return out


def _workflow_observations(subs: list[Submission], today: date, built_at: str | None) -> list[Observation]:
    out = []
    for sub in subs:
        if sub.status in _STALLED_STATUSES and sub.submitted_at:
            days = (today - sub.submitted_at).days
            metric_id, anchor = "submissions_stalled_days", sub.submitted_at
        elif sub.status in _OPEN_STATUSES and sub.due_date:
            days = (today - sub.due_date).days
            metric_id, anchor = "submissions_overdue_days", sub.due_date
        else:
            continue
        out.append(
            Observation(
                metric_id=metric_id,
                entity_id=sub.iso3,
                entity_name=sub.country,
                region=sub.region,
                round=sub.round,
                year=sub.year,
                state=REPORTED,
                value=float(max(days, 0)),
                validation_state=sub.validation_state,
                submission_id=sub.submission_id,
                status=sub.status,
                unit="days",
                evidence_id=evidence_id_for(metric_id, sub.submission_id),
                extra={
                    "source_system": "ifrc_databank",
                    "dataset": f"unified_{sub.kind}_assignment",
                    "submission_id": sub.submission_id,
                    "anchor_date": anchor.isoformat(),
                    "status": sub.status,
                    "kind": sub.kind,
                    "visibility": "ifrc_internal",
                    "synchronized_at": built_at,
                },
            )
        )
    return out


def build_decision_data(
    extract: dict[str, Any],
    access: AccessContext,
    filters: Filters,
    *,
    today: date | None = None,
) -> DecisionData:
    """Filter to what ``access`` may read, then derive observations. Nothing is computed from other rows."""
    today = today or datetime.now(timezone.utc).date()
    built_at = extract.get("built_at")

    plan_rows = access.filter_rows(extract.get("plan_submissions") or [])
    report_rows = access.filter_rows(extract.get("report_submissions") or [])
    subs: list[Submission] = []
    for kind, rows in (("plan", plan_rows), ("report", report_rows)):
        for row in rows:
            sub = _to_submission(row, kind)
            if sub and _matches(filters, iso3=sub.iso3, region=sub.region, round_code=sub.round):
                subs.append(sub)
    if filters.validation_state:
        subs = [s for s in subs if s.validation_state == filters.validation_state]

    plan_subs = [s for s in subs if s.kind == "plan"]
    subs_by_id = {s.submission_id: s for s in plan_subs}

    allowed_rows = access.filter_rows(extract.get("plan_facts") or [])
    facts = [
        row
        for row in allowed_rows
        if _matches(filters, iso3=row.get("ISO3"), region=row.get("Region"), round_code=row.get("Round"))
    ]
    if filters.year:
        facts = [row for row in facts if row.get("Year") == filters.year]

    totals, breakdown, emergency_funding = _funding_observations(facts, subs_by_id, built_at)
    people = _people_observations(facts, plan_subs, built_at)
    emergency_people = _emergency_people_observations(facts, subs_by_id, built_at)
    pns_support = _pns_support_observations(facts, totals, subs_by_id, built_at)
    core_indicators = _core_indicator_observations(facts, subs_by_id, built_at)
    unavailable = _unavailable_observations(facts, subs_by_id, built_at)
    workflow = _workflow_observations(subs, today, built_at)

    def keep(observations: list[Observation]) -> list[Observation]:
        out = []
        for obs in observations:
            definition = METRIC_REGISTRY[obs.metric_id]
            if obs.validation_state not in definition.allowed_validation_states:
                continue
            if filters.validation_state and obs.validation_state != filters.validation_state:
                continue
            if filters.funding_source and obs.funding_source != filters.funding_source:
                continue
            if filters.strategic_priority and obs.strategic_priority != filters.strategic_priority:
                continue
            out.append(obs)
        return out

    data = DecisionData(
        submissions=subs,
        observations={
            "funding_requirement": keep(totals),
            "funding_requirement_by_priority": keep(breakdown),
            "people_targeted": keep(people),
            "emergency_funding_requirement": keep(emergency_funding),
            "emergency_people_targeted": keep(emergency_people),
            "pns_support_count": keep(pns_support),
            "core_indicators_reported": keep(core_indicators),
            "indicators_data_unavailable": keep(unavailable),
            "submissions_stalled_days": keep([o for o in workflow if o.metric_id == "submissions_stalled_days"]),
            "submissions_overdue_days": keep([o for o in workflow if o.metric_id == "submissions_overdue_days"]),
        },
        built_at=built_at,
        today=today,
    )
    if not plan_rows and not report_rows:
        data.notes.append("No submissions are available in your scope.")
    return data


def load_extract() -> tuple[dict[str, Any], bool]:
    """Source facts for all rounds and countries, cached against the database revision (no user data in the key)."""
    from plugins.upr.api_cache import get_or_build_upr_payload
    from plugins.upr.upr_data import build_upr_data, build_upr_submissions

    def build() -> dict[str, Any]:
        plan = build_upr_data(template="plan")
        report = build_upr_submissions(template="report")
        return {
            "plan_facts": plan["data"],
            "plan_submissions": plan["submissions"],
            "report_submissions": report["data"],
            "built_at": datetime.now(timezone.utc).isoformat(),
        }

    return get_or_build_upr_payload("decisions-extract", {"generation": 1}, build)
