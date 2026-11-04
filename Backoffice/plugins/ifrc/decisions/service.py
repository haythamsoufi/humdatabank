"""Decision Maker service: one implementation behind the UI, the API, exports and the chatbot tools."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from plugins.ifrc.decisions import config, facts, rules, store
from plugins.ifrc.decisions.access import AccessContext
from plugins.ifrc.decisions.config import tr
from plugins.ifrc.decisions.facts import DecisionData, Filters, _round_year, build_decision_data
from plugins.ifrc.decisions.metrics import (
    DRAFT,
    METRIC_REGISTRY,
    PROVISIONAL,
    REPORTED,
    VALIDATED,
    Observation,
    aggregate,
)

logger = logging.getLogger(__name__)

_SUBMITTED = frozenset({"submitted", "sent_for_review", "approved"})
# Provisional readiness bands, shown to users as such.
_READY_PCT = 80.0
_PARTIAL_PCT = 50.0
_RUN_DEDUPE_SECONDS = 60
_RESTRICTED_NOTE = "Totals include only the countries you are permitted to see."
_PLAN_METRICS = frozenset(
    {
        "funding_requirement",
        "funding_requirement_by_priority",
        "people_targeted",
        "indicators_data_unavailable",
        "emergency_funding_requirement",
        "emergency_people_targeted",
        "pns_support_count",
        "core_indicators_reported",
    }
)


class NotFound(LookupError):
    """Raised for unknown records and for records the user may not see (indistinguishable on purpose)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


class _Loaded:
    """Extract plus helpers for one request."""

    def __init__(self, access: AccessContext, today: date | None = None, extract: dict[str, Any] | None = None):
        self.access = access
        self.today = today
        if extract is None:
            extract, _hit = facts.load_extract()
        self.extract = extract

    def build(self, filters: Filters) -> DecisionData:
        return build_decision_data(self.extract, self.access, filters, today=self.today)

    def baseline_provider(self, filters: Filters) -> rules.BaselineProvider:
        def provide(round_code: str) -> DecisionData | None:
            data = self.build(replace(filters, round=round_code, year=None))
            return data if data.obs("funding_requirement") else None

        return provide


def _decision_or_404(decision_id: str, access: AccessContext, *, by_slug: bool = False) -> dict[str, Any]:
    decisions = store.load_decisions()
    decision = None
    if by_slug:
        decision = next((d for d in decisions.values() if d.get("slug") == decision_id), None)
    else:
        decision = decisions.get(decision_id)
    if decision is None or not access.can_see_decision(decision):
        raise NotFound("decision")
    return decision


def resolve_decision_id(slug_or_id: str, access: AccessContext) -> str:
    decisions = store.load_decisions()
    for decision in decisions.values():
        if slug_or_id in (decision["id"], decision.get("slug")) and access.can_see_decision(decision):
            return decision["id"]
    raise NotFound("decision")


def _flag_states(keys: list[str]) -> dict[str, dict[str, Any]]:
    if not keys:
        return {}
    try:
        from plugins.ifrc.decisions.models import DecisionFlagState

        rows = DecisionFlagState.query.filter(DecisionFlagState.flag_key.in_(keys)).all()
    except Exception:
        from app.extensions import db

        db.session.rollback()
        logger.warning("Decision flag state unavailable", exc_info=True)
        return {}
    return {
        row.flag_key: {
            "status": row.status,
            "note": row.note,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    }


def _evaluate(
    decision: dict[str, Any],
    loaded: _Loaded,
    filters: Filters,
    *,
    record: bool = True,
) -> tuple[DecisionData, list[dict[str, Any]], list[rules.RuleOutcome]]:
    data = loaded.build(filters)
    rule_map = store.load_rules()
    flags, outcomes = rules.evaluate_decision(
        decision, rule_map, data, filters, loaded.baseline_provider(filters)
    )
    states = _flag_states([f["key"] for f in flags])
    for flag in flags:
        state = states.get(flag["key"])
        if state:
            flag["status"] = state["status"]
            flag["review_note"] = state.get("note")
            flag["reviewed_at"] = state.get("updated_at")
    if record:
        _record_runs(decision, outcomes, loaded.access.user_id)
    return data, flags, outcomes


def _record_runs(decision: dict[str, Any], outcomes: list[rules.RuleOutcome], user_id: int | None) -> None:
    if not outcomes:
        return
    try:
        from app.extensions import db
        from plugins.ifrc.decisions.models import DecisionRuleRun

        cutoff = _now().replace(tzinfo=None) - timedelta(seconds=_RUN_DEDUPE_SECONDS)
        for outcome in outcomes:
            recent = (
                DecisionRuleRun.query.filter_by(
                    decision_id=decision["id"], rule_id=outcome.rule_id, rule_version=outcome.rule_version
                )
                .filter(DecisionRuleRun.ran_at >= cutoff)
                .first()
            )
            if recent:
                continue
            db.session.add(
                DecisionRuleRun(
                    decision_id=decision["id"],
                    rule_id=outcome.rule_id,
                    rule_version=outcome.rule_version,
                    status=outcome.status,
                    entities_evaluated=outcome.entities_evaluated,
                    flags_raised=outcome.flags_raised,
                    error=outcome.error,
                    ran_by_user_id=user_id,
                )
            )
        db.session.commit()
    except Exception:
        from app.extensions import db

        db.session.rollback()
        logger.warning("Could not record rule runs", exc_info=True)


def _apply_flag_filters(flags: list[dict[str, Any]], filters: Filters) -> list[dict[str, Any]]:
    out = flags
    if filters.flag_status:
        out = [f for f in out if f["status"] == filters.flag_status]
    if filters.severity:
        out = [f for f in out if f["severity"] == filters.severity]
    return out


# ---------------------------------------------------------------------------
# Envelope, coverage and quality
# ---------------------------------------------------------------------------


def coverage_for(data: DecisionData, round_code: str | None) -> dict[str, Any]:
    subs = [s for s in data.submissions if s.kind == "plan" and (round_code is None or s.round == round_code)]
    expected = len(subs)
    submitted = sum(1 for s in subs if s.status in _SUBMITTED)
    validated = sum(1 for s in subs if s.validation_state == VALIDATED)
    pct = round(submitted / expected * 100, 1) if expected else None
    return {
        "round": round_code,
        "expected": expected,
        "submitted": submitted,
        "validated": validated,
        "coverage_pct": pct,
    }


def readiness_for(coverage: dict[str, Any]) -> str:
    pct = coverage.get("coverage_pct")
    if pct is None or not coverage.get("expected"):
        return "Unavailable"
    if pct >= _READY_PCT:
        return "Ready"
    if pct >= _PARTIAL_PCT:
        return "Partial"
    return "Limited"


def _validation_mix(observations: list[Observation]) -> dict[str, int]:
    mix = {VALIDATED: 0, PROVISIONAL: 0, DRAFT: 0}
    for obs in observations:
        mix[obs.validation_state] = mix.get(obs.validation_state, 0) + 1
    return mix


def _sources(data: DecisionData) -> list[dict[str, Any]]:
    return [
        {
            "source_system": "ifrc_databank",
            "dataset": "Unified Plan and Report assignments",
            "owner": "FDS",
            "synchronized_at": data.built_at,
            "note": "Read from the Databank's own submissions; GO and ERP are not yet integrated.",
        }
    ]


def _envelope(
    payload: Any,
    *,
    decision: dict[str, Any] | None,
    filters: Filters,
    data: DecisionData,
    access: AccessContext,
    round_code: str | None,
    caveats: list[str] | None = None,
    observations: list[Observation] | None = None,
) -> dict[str, Any]:
    cov = coverage_for(data, round_code)
    notes = list(caveats or []) + list(data.notes)
    if access.scope_limited:
        notes.append(_RESTRICTED_NOTE)
    if cov["expected"] and cov["coverage_pct"] is not None and cov["coverage_pct"] < _READY_PCT:
        notes.append(
            f"Only {cov['submitted']} of {cov['expected']} expected submissions are in; aggregates are incomplete."
        )
    return {
        "data": payload,
        "scope": {**filters.as_scope(), "round": round_code, "decision_id": decision["id"] if decision else None},
        "coverage": cov,
        "data_quality": {
            "readiness": readiness_for(cov),
            "readiness_basis": "Provisional bands: 80% Ready, 50% Partial, otherwise Limited.",
            "validation_mix": _validation_mix(observations or data.obs("funding_requirement")),
            "caveats": notes,
        },
        "refreshed_at": data.built_at,
        "sources": _sources(data),
        "permission_context": access.public_view(),
    }


# ---------------------------------------------------------------------------
# Public operations
# ---------------------------------------------------------------------------


def _decision_view(decision: dict[str, Any], lang: str) -> dict[str, Any]:
    return {
        "id": decision["id"],
        "slug": decision["slug"],
        "title": tr(decision["title"], lang),
        "question": tr(decision["question"], lang),
        "description": tr(decision.get("description"), lang),
        "owner_team": decision.get("owner_team"),
        "status": decision.get("status"),
        "visibility": decision.get("visibility"),
        "audience": decision.get("audience", []),
        "dimensions": decision.get("dimensions", []),
        "metric_ids": decision.get("metric_ids", []),
        "rule_ids": decision.get("rule_ids", []),
        "version": decision.get("version", 1),
        "effective_from": decision.get("effective_from"),
        "languages": [code for code in config.LANGUAGES if isinstance(decision["title"], dict) and decision["title"].get(code)],
    }


def list_decisions(access: AccessContext, filters: Filters, *, loaded: _Loaded | None = None) -> dict[str, Any]:
    visible = [d for d in store.load_decisions().values() if access.can_see_decision(d)]
    if not visible:
        return {
            "data": {"decisions": []},
            "scope": filters.as_scope(),
            "coverage": {},
            "data_quality": {"caveats": []},
            "refreshed_at": None,
            "sources": [],
            "permission_context": access.public_view(),
        }
    loaded = loaded or _Loaded(access)
    cards = []
    refreshed = None
    scope_data = loaded.build(filters)
    for decision in visible:
        data, flags, _outcomes = _evaluate(decision, loaded, filters, record=False)
        round_code = rules.latest_plan_round(data, filters)
        cov = coverage_for(data, round_code)
        refreshed = refreshed or data.built_at
        counts = _flag_counts(flags)
        cards.append(
            {
                **_decision_view(decision, filters.lang),
                "coverage": cov,
                "readiness": readiness_for(cov),
                "flag_counts": counts,
                "last_refresh": data.built_at,
            }
        )
    return {
        "data": {"decisions": cards},
        "scope": filters.as_scope(),
        "coverage": coverage_for(scope_data, None),
        "data_quality": {"caveats": [_RESTRICTED_NOTE] if access.scope_limited else []},
        "refreshed_at": refreshed,
        "sources": _sources(scope_data),
        "permission_context": access.public_view(),
    }


def _flag_counts(flags: list[dict[str, Any]]) -> dict[str, Any]:
    by_severity = {s: 0 for s in config.SEVERITIES}
    by_status: dict[str, int] = {}
    for flag in flags:
        by_severity[flag["severity"]] += 1
        by_status[flag["status"]] = by_status.get(flag["status"], 0) + 1
    open_count = sum(n for status, n in by_status.items() if status in ("new", "acknowledged", "under_review"))
    return {"total": len(flags), "open": open_count, "by_severity": by_severity, "by_status": by_status}


def get_definition(decision_id: str, access: AccessContext, lang: str = "en") -> dict[str, Any]:
    decision = _decision_or_404(decision_id, access)
    rule_map = store.load_rules()
    view = _decision_view(decision, lang)
    view["metrics"] = [METRIC_REGISTRY[m].to_dict(lang) for m in decision.get("metric_ids", []) if m in METRIC_REGISTRY]
    view["rules"] = [_rule_view(rule_map[r], lang) for r in decision.get("rule_ids", []) if r in rule_map]
    return view


def _rule_view(rule: dict[str, Any], lang: str) -> dict[str, Any]:
    return {
        "id": rule["id"],
        "name": tr(rule["name"], lang),
        "version": rule["version"],
        "type": rule.get("type", "deterministic"),
        "enabled": rule.get("enabled", True),
        "metric_id": rule["metric_id"],
        "condition": rule["condition"],
        "severity": rule["severity"],
        "minimum_data_quality": rule.get("minimum_data_quality", "any"),
        "message_template": tr(rule["message_template"], lang),
        "recommended_follow_up": tr(rule.get("recommended_follow_up"), lang),
        "provisional": bool(rule.get("provisional", True)),
        "provisional_note": config.PROVISIONAL_NOTE if rule.get("provisional", True) else None,
    }


def methodology(decision_id: str, access: AccessContext, lang: str = "en") -> dict[str, Any]:
    decision = _decision_or_404(decision_id, access)
    view = get_definition(decision_id, access, lang)
    return {
        "data": {
            "decision_id": decision["id"],
            "version": decision.get("version", 1),
            "methodology_markdown": decision.get("methodology_markdown", ""),
            "metrics": view["metrics"],
            "rules": view["rules"],
        },
        "permission_context": access.public_view(),
    }


def metric_definitions(lang: str = "en") -> dict[str, Any]:
    return {"data": [m.to_dict(lang) for m in METRIC_REGISTRY.values()]}


def _observation_view(obs: Observation) -> dict[str, Any]:
    return {
        "evidence_id": obs.evidence_id,
        "country": obs.entity_id,
        "name": obs.entity_name,
        "region": obs.region,
        "round": obs.round,
        "year": obs.year,
        "value": obs.value,
        "state": obs.state,
        "unit": obs.unit,
        "validation_state": obs.validation_state,
        "label": obs.label,
    }


def decision_metrics(
    decision_id: str,
    filters: Filters,
    access: AccessContext,
    *,
    group_by: tuple[str, ...] = (),
    metric_id: str | None = None,
    loaded: _Loaded | None = None,
) -> dict[str, Any]:
    decision = _decision_or_404(decision_id, access)
    loaded = loaded or _Loaded(access)
    data = loaded.build(filters)
    round_code = rules.latest_plan_round(data, filters)
    wanted = [metric_id] if metric_id else list(decision.get("metric_ids", []))
    unknown = [m for m in wanted if m not in decision.get("metric_ids", [])]
    if unknown:
        raise ValueError("metric is not part of this decision")
    out = []
    for mid in wanted:
        definition = METRIC_REGISTRY[mid]
        bad = [g for g in group_by if g not in definition.valid_dimensions]
        if bad:
            raise ValueError(f"{mid} cannot be grouped by {', '.join(bad)}")
        out.append(_metric_result(definition.id, data, group_by, round_code, filters, lang=filters.lang))
    observations = data.obs("funding_requirement")
    return _envelope(out, decision=decision, filters=filters, data=data, access=access, round_code=round_code, observations=observations)


def _metric_result(
    metric_id: str,
    data: DecisionData,
    group_by: tuple[str, ...],
    round_code: str | None,
    filters: Filters,
    *,
    lang: str,
) -> dict[str, Any]:
    definition = METRIC_REGISTRY[metric_id]
    result: dict[str, Any] = {"metric": definition.to_dict(lang), "group_by": list(group_by)}
    if metric_id == "submission_coverage":
        result["groups"] = _coverage_groups(data, group_by, round_code)
        return result
    observations = list(data.obs(metric_id))
    plan_metric = metric_id in _PLAN_METRICS
    if plan_metric and round_code:
        observations = [o for o in observations if o.round == round_code]
        result["round"] = round_code
        round_year = _round_year(round_code)
        if metric_id != "indicators_data_unavailable" and "year" not in group_by and not filters.year and round_year:
            observations = [o for o in observations if o.year == round_year]
            result["year"] = round_year
    method = definition.aggregation if definition.aggregation in ("sum", "max", "min", "count") else "sum"
    result["groups"] = aggregate(observations, group_by, method=method)
    return result


def _coverage_groups(data: DecisionData, group_by: tuple[str, ...], round_code: str | None) -> list[dict[str, Any]]:
    groups: dict[tuple, dict[str, Any]] = {}
    for sub in data.submissions:
        if sub.kind != "plan" or (round_code and sub.round != round_code):
            continue
        key_values = {
            name: {"region": sub.region, "round": sub.round, "validation_state": sub.validation_state}[name]
            for name in group_by
        }
        group = groups.setdefault(tuple(key_values.values()), {"key": key_values, "expected": 0, "submitted": 0, "validated": 0})
        group["expected"] += 1
        group["submitted"] += 1 if sub.status in _SUBMITTED else 0
        group["validated"] += 1 if sub.validation_state == VALIDATED else 0
    out = []
    for group in groups.values():
        group["value"] = round(group["submitted"] / group["expected"] * 100, 1) if group["expected"] else None
        group["state"] = REPORTED if group["expected"] else "not_reported"
        out.append(group)
    out.sort(key=lambda g: tuple(str(v) for v in g["key"].values()))
    return out


def decision_flags(
    decision_id: str,
    filters: Filters,
    access: AccessContext,
    *,
    loaded: _Loaded | None = None,
) -> dict[str, Any]:
    decision = _decision_or_404(decision_id, access)
    loaded = loaded or _Loaded(access)
    data, flags, outcomes = _evaluate(decision, loaded, filters)
    round_code = rules.latest_plan_round(data, filters)
    visible = _apply_flag_filters(flags, filters)
    return _envelope(
        {
            "flags": visible,
            "counts": _flag_counts(flags),
            "rules": [
                {
                    "rule_id": o.rule_id,
                    "rule_version": o.rule_version,
                    "status": o.status,
                    "entities_evaluated": o.entities_evaluated,
                    "flags_raised": o.flags_raised,
                    "not_evaluated": o.not_evaluable,
                }
                for o in outcomes
            ],
        },
        decision=decision,
        filters=filters,
        data=data,
        access=access,
        round_code=round_code,
        caveats=[reason for o in outcomes for reason in o.not_evaluable],
    )


def decision_summary(
    decision_id: str,
    filters: Filters,
    access: AccessContext,
    *,
    loaded: _Loaded | None = None,
) -> dict[str, Any]:
    decision = _decision_or_404(decision_id, access)
    loaded = loaded or _Loaded(access)
    data, flags, outcomes = _evaluate(decision, loaded, filters)
    round_code = rules.latest_plan_round(data, filters)
    current_year = _round_year(round_code)
    funding = [
        o for o in data.obs("funding_requirement") if o.round == round_code and (filters.year or current_year) == o.year
    ]

    key_metrics = []
    for mid in decision.get("metric_ids", []):
        if mid in ("funding_requirement_by_priority",):
            continue
        result = _metric_result(mid, data, (), round_code, filters, lang=filters.lang)
        group = (result["groups"] or [{}])[0]
        key_metrics.append(
            {
                "metric_id": mid,
                "name": result["metric"]["name"],
                "unit": result["metric"]["unit"],
                "value": group.get("value"),
                "state": group.get("state", "not_reported"),
                "coverage_pct": group.get("value") if mid == "submission_coverage" else None,
                "extra": {k: group[k] for k in ("expected", "submitted", "validated") if k in group},
            }
        )

    by_source = aggregate(funding, ("funding_source",))
    trend = _trend(loaded, filters)
    entities = _country_rows(decision, data, flags, round_code, loaded, filters)
    caveats = [r for o in outcomes for r in o.not_evaluable]
    if "people_targeted" in decision.get("metric_ids", []):
        caveats.append("People to be reached uses the headline total and is a provisional mapping, pending FDS confirmation.")
    caveats.append(config.PROVISIONAL_NOTE)
    return _envelope(
        {
            "decision": _decision_view(decision, filters.lang),
            "key_metrics": key_metrics,
            "funding_by_source": by_source,
            "trend": trend,
            "entities": entities,
            "flag_counts": _flag_counts(flags),
            "top_flags": _apply_flag_filters(flags, filters)[:10],
            "assistant_prompts": _assistant_prompts(decision["id"], round_code),
        },
        decision=decision,
        filters=filters,
        data=data,
        access=access,
        round_code=round_code,
        caveats=caveats,
        observations=funding,
    )


def _assistant_prompts(decision_id: str, round_code: str | None) -> list[str]:
    period = round_code or "the latest plan round"
    shared = "What data is missing before this regional summary can be used?"
    prompts = {
        "DEC-001": [
            f"Which countries should be prioritised for greater Federation-wide support in {period}, and why?",
            f"Which countries meet three or more priority signals in {period}?",
        ],
        "DEC-002": [
            f"Which countries have funding requirements that changed by more than 30% compared with the previous planning round ({period})?",
            f"Which Strategic Priorities account for the largest share of {period} requirements?",
        ],
        "DEC-003": [
            f"How many countries, and how much funding requirement and people to be reached, does {period} cover?",
            f"Which regions have the weakest coverage in {period}?",
        ],
        "DEC-005": [
            f"Which countries plan emergency operations in {period}, and what funding requirement do they state?",
            f"Which {period} plans have emergency targets without emergency funding, or the reverse?",
        ],
        "DEC-006": [
            f"How is the {period} funding requirement split between host National Societies, PNS and the Secretariat?",
            f"Which {period} PNS figures come from the host's plan rather than the PNS's own plan?",
        ],
        "DEC-007": [
            f"Which {period} figures are not yet validated and should be caveated before use?",
            "Which submissions have been waiting for review the longest?",
        ],
        "DEC-008": [
            f"Compare {period} funding requirement by region and funding source.",
            f"What is the funding requirement by Strategic Priority for each region in {period}?",
        ],
    }
    default = [
        f"Show countries with an incomplete or unvalidated {period} plan.",
        "Which submissions have been waiting for review the longest?",
    ]
    return [*prompts.get(decision_id, default), shared]


def _trend(loaded: _Loaded, filters: Filters) -> list[dict[str, Any]]:
    data = loaded.build(replace(filters, round=None, year=None))
    rows = []
    by_round: dict[str, list[Observation]] = {}
    for obs in data.obs("funding_requirement"):
        if obs.round and obs.year == _round_year(obs.round):
            by_round.setdefault(obs.round, []).append(obs)
    for round_code, obs in sorted(by_round.items(), key=lambda kv: _round_year(kv[0]) or 0):
        group = aggregate(obs, ())[0]
        rows.append(
            {
                "round": round_code,
                "year": _round_year(round_code),
                "value": group["value"],
                "countries": len({o.entity_id for o in obs}),
                "validation_states": group["validation_states"],
                "currency": "CHF",
            }
        )
    return rows


def _country_rows(
    decision: dict[str, Any],
    data: DecisionData,
    flags: list[dict[str, Any]],
    round_code: str | None,
    loaded: _Loaded,
    filters: Filters,
) -> list[dict[str, Any]]:
    year = _round_year(round_code)
    previous = rules.previous_comparable_round(round_code)
    baseline = loaded.baseline_provider(filters)(previous) if previous else None
    base_year = _round_year(previous)
    flag_by_country: dict[str, list[dict[str, Any]]] = {}
    for flag in flags:
        flag_by_country.setdefault(flag["entity_id"], []).append(flag)

    subs = [s for s in data.submissions if s.kind == "plan" and (round_code is None or s.round == round_code)]
    funding = {}
    for obs in data.obs("funding_requirement"):
        if obs.round == round_code and obs.year == year:
            funding.setdefault(obs.entity_id, []).append(obs)
    base_funding: dict[str, list[Observation]] = {}
    if baseline:
        for obs in baseline.obs("funding_requirement"):
            if obs.round == previous and obs.year == base_year:
                base_funding.setdefault(obs.entity_id, []).append(obs)
    people = {o.entity_id: o for o in data.obs("people_targeted") if o.round == round_code}

    rows = []
    for sub in sorted(subs, key=lambda s: s.country):
        f_obs = funding.get(sub.iso3, [])
        cur = sum(o.value or 0 for o in f_obs) if f_obs else None
        base = sum(o.value or 0 for o in base_funding.get(sub.iso3, [])) if base_funding.get(sub.iso3) else None
        change = round((cur - base) / base * 100, 1) if cur is not None and base else None
        p = people.get(sub.iso3)
        rows.append(
            {
                "country": sub.iso3,
                "name": sub.country,
                "region": sub.region,
                "status": sub.status,
                "validation_state": sub.validation_state,
                "funding_requirement": cur,
                "baseline_funding_requirement": base,
                "percent_change": change,
                "people_targeted": p.value if p else None,
                "people_targeted_state": p.state if p else "not_reported",
                "flag_count": len(flag_by_country.get(sub.iso3, [])),
                "max_severity": max(
                    (f["severity"] for f in flag_by_country.get(sub.iso3, [])),
                    key=config.SEVERITIES.index,
                    default=None,
                ),
                "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None,
                "due_date": sub.due_date.isoformat() if sub.due_date else None,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Flags: detail, review state, feedback
# ---------------------------------------------------------------------------


def _find_flag(flag_id: str, access: AccessContext, decision_id: str | None, loaded: _Loaded, lang: str = "en"):
    key = flag_id[5:] if flag_id.startswith("FLAG-") else flag_id
    if not (len(key) == 32 and all(c in "0123456789abcdef" for c in key)):
        raise NotFound("flag")
    for decision in store.load_decisions().values():
        if decision_id and decision["id"] != decision_id:
            continue
        if not access.can_see_decision(decision):
            continue
        _data, flags, _outcomes = _evaluate(decision, loaded, Filters(lang=lang), record=False)
        for flag in flags:
            if flag["key"] == key:
                return decision, flag
    raise NotFound("flag")


def flag_detail(flag_id: str, access: AccessContext, *, lang: str = "en", loaded: _Loaded | None = None) -> dict[str, Any]:
    loaded = loaded or _Loaded(access)
    decision, flag = _find_flag(flag_id, access, None, loaded, lang)
    evidence = [e for e in (_evidence_by_id(eid, access, loaded) for eid in flag["evidence_ids"]) if e]
    return {
        "data": {"flag": flag, "evidence": evidence, "rule": _rule_view(store.load_rules()[flag["rule_id"]], lang)},
        "refreshed_at": flag.get("data_as_of"),
        "permission_context": access.public_view(),
    }


def set_flag_status(
    flag_id: str,
    status: str,
    access: AccessContext,
    *,
    note: str | None = None,
    loaded: _Loaded | None = None,
) -> dict[str, Any]:
    if status not in config.FLAG_STATUSES or status == "new":
        raise ValueError("status is not recognised")
    loaded = loaded or _Loaded(access)
    decision, flag = _find_flag(flag_id, access, None, loaded)
    from app.extensions import db
    from plugins.ifrc.decisions.models import DecisionFlagState

    row = DecisionFlagState.query.filter_by(flag_key=flag["key"]).first()
    if row is None:
        row = DecisionFlagState(
            flag_key=flag["key"],
            decision_id=decision["id"],
            rule_id=flag["rule_id"],
            rule_version=flag["rule_version"],
            entity_id=flag["entity_id"],
        )
        db.session.add(row)
    row.status = status
    row.rule_version = flag["rule_version"]
    row.note = (note or "").strip()[:2000] or None
    row.updated_by_user_id = access.user_id
    db.session.commit()
    _audit_event("flag_status", flag["id"], {"status": status})
    return {"data": {"flag_id": flag["id"], "status": status}}


def add_flag_feedback(
    flag_id: str,
    verdict: str,
    access: AccessContext,
    *,
    note: str | None = None,
    loaded: _Loaded | None = None,
) -> dict[str, Any]:
    if verdict not in config.FEEDBACK_VERDICTS:
        raise ValueError("verdict is not recognised")
    loaded = loaded or _Loaded(access)
    decision, flag = _find_flag(flag_id, access, None, loaded)
    from app.extensions import db
    from plugins.ifrc.decisions.models import DecisionFlagFeedback

    db.session.add(
        DecisionFlagFeedback(
            flag_key=flag["key"],
            decision_id=decision["id"],
            rule_id=flag["rule_id"],
            rule_version=flag["rule_version"],
            verdict=verdict,
            note=(note or "").strip()[:2000] or None,
            user_id=access.user_id,
        )
    )
    db.session.commit()
    _audit_event("flag_feedback", flag["id"], {"verdict": verdict})
    return {"data": {"flag_id": flag["id"], "verdict": verdict}}


def _audit_event(event: str, target: str, details: dict[str, Any]) -> None:
    logger.info("decision_support event=%s target=%s details=%s", event, target, details)


# ---------------------------------------------------------------------------
# Evidence and source records
# ---------------------------------------------------------------------------


def _all_visible_observations(access: AccessContext, loaded: _Loaded) -> dict[str, tuple[dict[str, Any], Observation]]:
    index: dict[str, tuple[dict[str, Any], Observation]] = {}
    filters = Filters()
    data = loaded.build(filters)
    base_rounds = {o.round for o in data.obs("funding_requirement") if o.round}
    provide = loaded.baseline_provider(filters)
    previous_rounds = {rules.previous_comparable_round(r) for r in base_rounds} - {None}
    baselines = [b for b in (provide(r) for r in sorted(previous_rounds)) if b]
    for decision in store.load_decisions().values():
        if not access.can_see_decision(decision):
            continue
        for mid in decision.get("metric_ids", []):
            for obs in data.obs(mid):
                index.setdefault(obs.evidence_id, (decision, obs))
        for baseline in baselines:
            for obs in baseline.obs("funding_requirement"):
                index.setdefault(obs.evidence_id, (decision, obs))
    return index


def _evidence_record(obs: Observation, decision: dict[str, Any]) -> dict[str, Any]:
    definition = METRIC_REGISTRY[obs.metric_id]
    return {
        "id": obs.evidence_id,
        "source_system": obs.extra.get("source_system", "ifrc_databank"),
        "dataset": obs.extra.get("dataset"),
        "submission_id": obs.submission_id,
        "indicator": obs.extra.get("indicator") or definition.id,
        "section": obs.extra.get("section"),
        "attribute": obs.extra.get("attribute"),
        "round": obs.round,
        "year": obs.year,
        "entity": {"type": "country", "id": obs.entity_id, "name": obs.entity_name, "region": obs.region},
        "label": obs.label,
        "value": obs.value,
        "state": obs.state,
        "unit": obs.unit,
        "currency": obs.currency,
        "validation_state": obs.validation_state,
        "assignment_status": obs.status,
        "visibility": obs.extra.get("visibility", "ifrc_internal"),
        "last_synchronized_at": obs.extra.get("synchronized_at"),
        "accessed_at": _now().isoformat(),
        "definition": {"metric_id": definition.id, "version": definition.version, "name": definition.name.get("en")},
        "decision_id": decision["id"],
        "extra": {k: v for k, v in obs.extra.items() if k in ("indicators", "partners", "operations", "anchor_date", "pns_reported", "source", "kind")},
    }


def _evidence_by_id(evidence_id: str, access: AccessContext, loaded: _Loaded) -> dict[str, Any] | None:
    found = _all_visible_observations(access, loaded).get(evidence_id)
    return _evidence_record(found[1], found[0]) if found else None


def get_evidence(evidence_id: str, access: AccessContext, *, loaded: _Loaded | None = None) -> dict[str, Any]:
    if not evidence_id.startswith("EVID-") or len(evidence_id) > 40:
        raise NotFound("evidence")
    if not access.authenticated or not access.can_view:
        raise NotFound("evidence")
    loaded = loaded or _Loaded(access)
    record = _evidence_by_id(evidence_id, access, loaded)
    if record is None:
        raise NotFound("evidence")
    return {"data": record, "refreshed_at": record["last_synchronized_at"], "permission_context": access.public_view()}


def get_source_record(reference: str, access: AccessContext, *, loaded: _Loaded | None = None) -> dict[str, Any]:
    """``submission:<id>`` or ``EVID-...``. Out-of-scope records look identical to missing ones."""
    ref = (reference or "").strip()
    if ref.startswith("EVID-"):
        return get_evidence(ref, access, loaded=loaded)
    if ref.startswith("submission:") and ref[11:].isdigit():
        if not access.authenticated or not access.can_view:
            raise NotFound("record")
        loaded = loaded or _Loaded(access)
        sid = int(ref[11:])
        data = loaded.build(Filters())
        sub = next((s for s in data.submissions if s.submission_id == sid), None)
        if sub is None:
            raise NotFound("record")
        return {
            "data": {
                "reference": ref,
                "source_system": "ifrc_databank",
                "submission_id": sid,
                "country": {"iso3": sub.iso3, "name": sub.country, "region": sub.region},
                "round": sub.round,
                "kind": sub.kind,
                "status": sub.status,
                "validation_state": sub.validation_state,
                "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None,
                "due_date": sub.due_date.isoformat() if sub.due_date else None,
            },
            "refreshed_at": data.built_at,
            "permission_context": access.public_view(),
        }
    raise NotFound("record")


def flag_evidence(flag_id: str, access: AccessContext, *, loaded: _Loaded | None = None) -> dict[str, Any]:
    return flag_detail(flag_id, access, loaded=loaded)


__all__ = [
    "NotFound",
    "list_decisions",
    "get_definition",
    "methodology",
    "metric_definitions",
    "decision_metrics",
    "decision_flags",
    "decision_summary",
    "flag_detail",
    "set_flag_status",
    "add_flag_feedback",
    "get_evidence",
    "get_source_record",
]
