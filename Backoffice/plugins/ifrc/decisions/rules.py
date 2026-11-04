"""Deterministic rule engine. Pure Python over ``DecisionData``; no database or request access.

A rule either raises a flag with the exact values that triggered it, or is recorded as not
evaluable (for example no comparable baseline). Missing, unavailable and not applicable data
are never read as low or zero values.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from plugins.ifrc.decisions.config import SEVERITIES, render_template, tr
from plugins.ifrc.decisions.facts import Filters, DecisionData, _round_year
from plugins.ifrc.decisions.metrics import (
    DRAFT,
    NOT_APPLICABLE,
    NOT_REPORTED,
    PROVISIONAL,
    REPORTED,
    VALIDATED,
    Observation,
    aggregate,
    meets_quality,
)

_SUBMITTED = frozenset({"submitted", "sent_for_review", "approved"})
_QUALITY_ORDER = (DRAFT, PROVISIONAL, VALIDATED)
MAX_EVIDENCE_PER_FLAG = 30


@dataclass
class RuleOutcome:
    rule_id: str
    rule_version: int
    status: str = "ok"
    entities_evaluated: int = 0
    flags_raised: int = 0
    not_evaluable: list[str] = field(default_factory=list)
    error: str | None = None


BaselineProvider = Callable[[str], "DecisionData | None"]


def flag_key(decision_id: str, rule_id: str, entity_id: str, period_id: str | None) -> str:
    raw = "|".join((decision_id, rule_id, entity_id, period_id or ""))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def previous_comparable_round(round_code: str | None) -> str | None:
    if not round_code or len(round_code) < 3 or not round_code[-2:].isdigit():
        return None
    year = int(round_code[-2:])
    return f"{round_code[:-2]}{(year - 1) % 100:02d}" if year > 0 else None


def latest_plan_round(data: DecisionData, filters: Filters) -> str | None:
    if filters.round:
        return filters.round
    rounds = {s.round for s in data.submissions if s.kind == "plan"}
    rounds |= {o.round for o in data.obs("funding_requirement") if o.round}
    return max(rounds, key=lambda r: (_round_year(r) or 0, r), default=None)


def _worst_quality(states: list[str]) -> str:
    return min(states or [DRAFT], key=_QUALITY_ORDER.index)


def _fmt_money(value: float | None) -> str:
    return "" if value is None else f"{value:,.0f}"


def _fmt_pct(value: float) -> str:
    return f"{value:+.1f}".rstrip("0").rstrip(".") if value else "0"


def _by_country(observations: list[Observation]) -> dict[str, list[Observation]]:
    out: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        out[obs.entity_id].append(obs)
    return out


def _evidence(observations: list[Observation]) -> list[str]:
    ids: list[str] = []
    for obs in observations:
        if obs.evidence_id and obs.evidence_id not in ids:
            ids.append(obs.evidence_id)
    return ids[:MAX_EVIDENCE_PER_FLAG]


def _build_flag(
    decision: dict[str, Any],
    rule: dict[str, Any],
    *,
    entity_type: str,
    entity_id: str,
    entity_name: str,
    period_id: str | None,
    trigger: dict[str, Any],
    message_values: dict[str, Any],
    observations: list[Observation],
    lang: str,
    generated_at: str,
    data_as_of: str | None,
    baseline_period: str | None = None,
    key_period: str | None = None,
) -> dict[str, Any]:
    key = flag_key(decision["id"], rule["id"], entity_id, key_period or period_id)
    values = {"entity_name": entity_name, "current_period": period_id or "", **message_values}
    condition = rule["condition"]
    return {
        "id": f"FLAG-{key}",
        "key": key,
        "decision_id": decision["id"],
        "rule_id": rule["id"],
        "rule_version": rule["version"],
        "rule_name": tr(rule["name"], lang),
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entity_name": entity_name,
        "period_id": period_id,
        "baseline_period": baseline_period,
        "severity": rule["severity"],
        "status": "new",
        "title": tr(rule["name"], lang),
        "message": render_template(tr(rule["message_template"], lang), values),
        "suggested_follow_up": tr(rule.get("recommended_follow_up"), lang),
        "trigger_values": trigger,
        "threshold": {
            "operator": condition["operator"],
            "value": condition["value"],
            "provisional": bool(rule.get("provisional", True)),
        },
        "evidence_ids": _evidence(observations),
        "validation_state": _worst_quality([o.validation_state for o in observations]),
        "visibility": rule.get("visibility", "ifrc_internal"),
        "finding_source": "deterministic_rule",
        "generated_at": generated_at,
        "data_as_of": data_as_of,
        "expires_at": None,
    }


@dataclass
class _Ctx:
    decision: dict[str, Any]
    rule: dict[str, Any]
    data: DecisionData
    filters: Filters
    baseline: BaselineProvider
    lang: str
    generated_at: str
    outcome: RuleOutcome

    def flag(self, **kwargs: Any) -> dict[str, Any]:
        return _build_flag(
            self.decision,
            self.rule,
            lang=self.lang,
            generated_at=self.generated_at,
            data_as_of=self.data.built_at,
            **kwargs,
        )

    def usable(self, observations: list[Observation]) -> list[Observation]:
        minimum = self.rule.get("minimum_data_quality", "any")
        return [o for o in observations if meets_quality(o.validation_state, minimum)]

    def skip(self, reason: str) -> None:
        if reason not in self.outcome.not_evaluable:
            self.outcome.not_evaluable.append(reason)


def _current_funding(ctx: _Ctx) -> tuple[str | None, dict[str, list[Observation]]]:
    current_round = latest_plan_round(ctx.data, ctx.filters)
    if not current_round:
        ctx.skip("No plan round is available in scope.")
        return None, {}
    obs = [o for o in ctx.data.obs("funding_requirement") if o.round == current_round and o.state == REPORTED]
    return current_round, _by_country(ctx.usable(obs))


def _yoy_by_country(ctx: _Ctx, current_round: str) -> tuple[str, int | None, dict[str, tuple]] | None:
    """Round-on-round funding change per country, or ``None`` when there is no comparable baseline round.

    Each value is ``(current, baseline, percent_change, current_obs, baseline_obs)``.
    """
    previous = previous_comparable_round(current_round)
    baseline_data = ctx.baseline(previous) if previous else None
    if baseline_data is None:
        ctx.skip(f"No comparable baseline round ({previous or 'unknown'}) is available.")
        return None
    current_year = _round_year(current_round)
    baseline_year = _round_year(previous)
    current = _by_country(
        ctx.usable([o for o in ctx.data.obs("funding_requirement") if o.round == current_round and o.year == current_year])
    )
    baseline = _by_country(
        ctx.usable([o for o in baseline_data.obs("funding_requirement") if o.round == previous and o.year == baseline_year])
    )
    rows: dict[str, tuple] = {}
    for iso3, cur_obs in sorted(current.items()):
        base_obs = baseline.get(iso3)
        if not base_obs:
            ctx.skip("Some countries have no baseline value in the previous round.")
            continue
        cur = sum(o.value or 0 for o in cur_obs)
        base = sum(o.value or 0 for o in base_obs)
        if base == 0:
            ctx.skip("Some countries have a zero baseline, so a percentage change is undefined.")
            continue
        rows[iso3] = (cur, base, (cur - base) / base * 100, cur_obs, base_obs)
    return previous, baseline_year, rows


def _rule_yoy(ctx: _Ctx) -> list[dict[str, Any]]:
    current_round = latest_plan_round(ctx.data, ctx.filters)
    if not current_round:
        ctx.skip("No plan round is available in scope.")
        return []
    result = _yoy_by_country(ctx, current_round)
    if result is None:
        return []
    previous, baseline_year, rows = result
    current_year = _round_year(current_round)
    threshold = float(ctx.rule["condition"]["value"])
    flags = []
    for iso3, (cur, base, change, cur_obs, base_obs) in rows.items():
        ctx.outcome.entities_evaluated += 1
        if abs(change) < threshold:
            continue
        flags.append(
            ctx.flag(
                entity_type="country",
                entity_id=iso3,
                entity_name=cur_obs[0].entity_name,
                period_id=current_round,
                baseline_period=f"{previous} ({baseline_year})",
                trigger={
                    "current": cur,
                    "baseline": base,
                    "percent_change": round(change, 2),
                    "currency": "CHF",
                    "current_year": current_year,
                    "baseline_year": baseline_year,
                },
                message_values={
                    "percent_change": _fmt_pct(round(change, 1)),
                    "baseline_value": _fmt_money(base),
                    "current_value": _fmt_money(cur),
                    "currency": "CHF",
                    "baseline_period": f"{previous} ({baseline_year})",
                },
                observations=cur_obs + base_obs,
            )
        )
    return flags


def _rule_priority(ctx: _Ctx) -> list[dict[str, Any]]:
    """Countries meeting enough published signals that leadership may want to prioritise them, with reasons.

    No weighted score: a country is listed when it meets ``value`` or more signals and is ordered by how many it
    meets, then by size of requirement.
    """
    condition = ctx.rule["condition"]
    needed = int(condition["value"])
    growth_pct = float(condition.get("growth_pct", 30))
    share_pct = float(condition.get("share_pct", 10))
    min_entities = int(condition.get("min_entities", 5))
    emergency_pct = float(condition.get("emergency_share_pct", 25))
    max_partners = int(condition.get("max_pns_partners", 1))
    current_round, funding = _current_funding(ctx)
    if not current_round:
        return []
    totals = {iso3: sum(o.value or 0 for o in obs) for iso3, obs in funding.items()}
    totals = {iso3: total for iso3, total in totals.items() if total > 0}
    scope_total = sum(totals.values())

    expected = {s.iso3 for s in ctx.data.submissions if s.kind == "plan" and s.round == current_round}
    unassessed = expected - set(totals)
    if unassessed:
        ctx.skip(
            f"{len(unassessed)} of {len(expected)} countries have no usable {current_round} plan and are not assessed; "
            "that does not mean they need less support."
        )
    share_assessed = len(totals) >= min_entities
    if not share_assessed:
        ctx.skip(f"Fewer than {min_entities} countries with a funding requirement, so share of the network is not assessed.")
    yoy = _yoy_by_country(ctx, current_round)
    emergency = _by_country(
        ctx.usable([o for o in ctx.data.obs("emergency_funding_requirement") if o.round == current_round and o.state == REPORTED])
    )
    partners = _by_country([o for o in ctx.data.obs("pns_support_count") if o.round == current_round])
    reasons_t = ctx.rule.get("reasons") or {}

    def reason(key: str, values: dict[str, Any]) -> str:
        return render_template(tr(reasons_t.get(key), ctx.lang), values)

    flags = []
    for iso3, total in sorted(totals.items()):
        ctx.outcome.entities_evaluated += 1
        obs = funding[iso3]
        reasons: list[str] = []
        signals: list[str] = []
        evidence: list[Observation] = []
        assessed = 2 + (1 if share_assessed else 0)
        trigger: dict[str, Any] = {"requirement": total, "currency": "CHF"}
        base_values = {"current_value": _fmt_money(total), "scope_total": _fmt_money(scope_total)}
        baseline_period = None

        if yoy is not None and iso3 in yoy[2]:
            assessed += 1
            previous, baseline_year, rows = yoy
            cur, base, change, cur_obs, base_obs = rows[iso3]
            if change >= growth_pct:
                baseline_period = f"{previous} ({baseline_year})"
                signals.append("growth")
                reasons.append(
                    reason(
                        "growth",
                        {**base_values, "percent_change": f"{change:.0f}", "baseline_value": _fmt_money(base),
                         "current_value": _fmt_money(cur), "baseline_period": baseline_period},
                    )
                )
                trigger.update({"baseline": base, "percent_change": round(change, 1)})
                evidence += cur_obs + base_obs
        if share_assessed and total / scope_total * 100 >= share_pct:
            share = total / scope_total * 100
            signals.append("share")
            reasons.append(reason("share", {**base_values, "share_pct": f"{share:.0f}"}))
            trigger["share_of_network_pct"] = round(share, 1)
            evidence += obs
        emergency_total = sum(o.value or 0 for o in emergency.get(iso3, []))
        if emergency_total > 0 and emergency_total / total * 100 >= emergency_pct:
            share = emergency_total / total * 100
            signals.append("emergency")
            reasons.append(
                reason("emergency", {**base_values, "emergency_share_pct": f"{share:.0f}", "emergency_value": _fmt_money(emergency_total)})
            )
            trigger["emergency_requirement"] = emergency_total
            evidence += emergency[iso3]
        partner_obs = partners.get(iso3, [])
        partner_count = int(sum(o.value or 0 for o in partner_obs))
        if partner_count <= max_partners:
            signals.append("support")
            reasons.append(reason("support", {**base_values, "partners": partner_count}))
            trigger["pns_partners"] = partner_count
            evidence += partner_obs

        if len(signals) < needed:
            continue
        trigger.update({"signals_met": len(signals), "signals_assessed": assessed, "signals": signals})
        flag = ctx.flag(
            entity_type="country",
            entity_id=iso3,
            entity_name=obs[0].entity_name,
            period_id=current_round,
            baseline_period=baseline_period,
            trigger=trigger,
            message_values={"count": len(signals), "assessed": assessed, "reasons": " ".join(reasons)},
            observations=evidence or obs,
        )
        flag["reasons"] = reasons
        if len(signals) > needed:
            flag["severity"] = "important"
        flags.append(flag)
    return flags


def _rule_missing_target(ctx: _Ctx) -> list[dict[str, Any]]:
    """Flag countries with a reported value for the rule's metric but no value for ``other_metric_id``."""
    metric_id = ctx.rule["metric_id"]
    other_id = ctx.rule.get("other_metric_id") or "people_targeted"
    current_round = latest_plan_round(ctx.data, ctx.filters)
    if not current_round:
        ctx.skip("No plan round is available in scope.")
        return []
    primary = _by_country(
        ctx.usable([o for o in ctx.data.obs(metric_id) if o.round == current_round and o.state == REPORTED])
    )
    other = _by_country([o for o in ctx.data.obs(other_id) if o.round == current_round])
    flags = []
    for iso3, p_obs in sorted(primary.items()):
        total = sum(o.value or 0 for o in p_obs)
        if total <= 0:
            continue
        ctx.outcome.entities_evaluated += 1
        o_obs = other.get(iso3, [])
        state = aggregate(o_obs, ())[0]["state"] if o_obs else NOT_REPORTED
        if state in (REPORTED, NOT_APPLICABLE):
            continue
        unit = p_obs[0].unit or ""
        flags.append(
            ctx.flag(
                entity_type="country",
                entity_id=iso3,
                entity_name=p_obs[0].entity_name,
                period_id=current_round,
                trigger={metric_id: total, "currency": unit, f"{other_id}_state": state},
                message_values={"current_value": _fmt_money(total), "currency": unit},
                observations=p_obs + o_obs,
            )
        )
    return flags


def _rule_pns_unreported(ctx: _Ctx) -> list[dict[str, Any]]:
    """PNS contributions that rest on the host's entry because the PNS has not submitted its own plan."""
    current_round, funding = _current_funding(ctx)
    if not current_round:
        return []
    threshold = float(ctx.rule["condition"]["value"])
    flags = []
    for iso3, obs in sorted(funding.items()):
        pns = [o for o in obs if o.funding_source == "PNS" and (o.value or 0) > 0]
        if not pns:
            continue
        ctx.outcome.entities_evaluated += 1
        pending = [o for o in pns if o.extra.get("pns_reported") != "Yes"]
        names = sorted({o.ns or "" for o in pending if o.ns})
        if len(pending) < max(threshold, 1):
            continue
        amount = sum(o.value or 0 for o in pending)
        flags.append(
            ctx.flag(
                entity_type="country",
                entity_id=iso3,
                entity_name=obs[0].entity_name,
                period_id=current_round,
                trigger={
                    "pns_without_own_plan": len(pending),
                    "pns_total": len({o.ns for o in pns}),
                    "requirement_from_host_entry": amount,
                    "currency": "CHF",
                    "national_societies": names[:25],
                },
                message_values={"count": len(pending), "current_value": _fmt_money(amount), "currency": "CHF"},
                observations=pending,
            )
        )
    return flags


def _rule_concentration(ctx: _Ctx) -> list[dict[str, Any]]:
    current_round, funding = _current_funding(ctx)
    if not current_round:
        return []
    condition = ctx.rule["condition"]
    min_entities = int(condition.get("min_entities", 5))
    totals = {iso3: sum(o.value or 0 for o in obs) for iso3, obs in funding.items()}
    scope_total = sum(totals.values())
    if len(totals) < min_entities or scope_total <= 0:
        ctx.skip(f"Fewer than {min_entities} countries with a funding requirement in scope.")
        return []
    threshold = float(condition["value"])
    flags = []
    for iso3, total in sorted(totals.items()):
        ctx.outcome.entities_evaluated += 1
        share = total / scope_total * 100
        if share < threshold:
            continue
        flags.append(
            ctx.flag(
                entity_type="country",
                entity_id=iso3,
                entity_name=funding[iso3][0].entity_name,
                period_id=current_round,
                trigger={
                    "current": total,
                    "scope_total": scope_total,
                    "share_pct": round(share, 2),
                    "currency": "CHF",
                    "countries_in_scope": len(totals),
                },
                message_values={
                    "share_pct": f"{share:.1f}",
                    "current_value": _fmt_money(total),
                    "scope_total": _fmt_money(scope_total),
                    "currency": "CHF",
                },
                observations=funding[iso3],
            )
        )
    return flags


def _rule_unvalidated(ctx: _Ctx) -> list[dict[str, Any]]:
    current_round, funding = _current_funding(ctx)
    if not current_round:
        return []
    flags = []
    for iso3, obs in sorted(funding.items()):
        ctx.outcome.entities_evaluated += 1
        pending = [o for o in obs if o.validation_state != VALIDATED]
        if not pending:
            continue
        total = sum(o.value or 0 for o in pending)
        statuses = sorted({o.status or "unknown" for o in pending})
        state = _worst_quality([o.validation_state for o in pending])
        flags.append(
            ctx.flag(
                entity_type="country",
                entity_id=iso3,
                entity_name=obs[0].entity_name,
                period_id=current_round,
                trigger={
                    "provisional_requirement": total,
                    "currency": "CHF",
                    "validation_state": state,
                    "statuses": statuses,
                },
                message_values={
                    "current_value": _fmt_money(total),
                    "currency": "CHF",
                    "validation_state": state,
                    "status": ", ".join(statuses),
                },
                observations=pending,
            )
        )
    return flags


def _in_lookback(ctx: _Ctx, obs: Observation) -> bool:
    if ctx.filters.round:
        return True
    years = int(ctx.rule["condition"].get("lookback_years", 1))
    return obs.year is None or obs.year >= ctx.data.today.year - years


def _workflow_rule(ctx: _Ctx, metric_id: str, extra: Callable[[Observation], dict[str, Any]]) -> list[dict[str, Any]]:
    threshold = float(ctx.rule["condition"]["value"])
    flags = []
    for obs in ctx.data.obs(metric_id):
        if obs.state != REPORTED or obs.value is None or not _in_lookback(ctx, obs):
            continue
        ctx.outcome.entities_evaluated += 1
        if obs.value < threshold:
            continue
        flags.append(
            ctx.flag(
                entity_type="country",
                entity_id=obs.entity_id,
                entity_name=obs.entity_name,
                period_id=obs.round,
                key_period=f"{obs.round}#{obs.submission_id}",
                trigger={"days": int(obs.value), "status": obs.status, "round": obs.round, **extra(obs)},
                message_values={"days": int(obs.value), "status": (obs.status or "").replace("_", " ")},
                observations=[obs],
            )
        )
    return flags


def _rule_stalled(ctx: _Ctx) -> list[dict[str, Any]]:
    return _workflow_rule(ctx, "submissions_stalled_days", lambda o: {"submitted_on": o.extra.get("anchor_date")})


def _rule_overdue(ctx: _Ctx) -> list[dict[str, Any]]:
    return _workflow_rule(ctx, "submissions_overdue_days", lambda o: {"due_on": o.extra.get("anchor_date")})


def _rule_unavailable(ctx: _Ctx) -> list[dict[str, Any]]:
    current_round = latest_plan_round(ctx.data, ctx.filters)
    if not current_round:
        ctx.skip("No plan round is available in scope.")
        return []
    threshold = float(ctx.rule["condition"]["value"])
    flags = []
    for obs in ctx.usable([o for o in ctx.data.obs("indicators_data_unavailable") if o.round == current_round]):
        ctx.outcome.entities_evaluated += 1
        if (obs.value or 0) < threshold:
            continue
        flags.append(
            ctx.flag(
                entity_type="country",
                entity_id=obs.entity_id,
                entity_name=obs.entity_name,
                period_id=current_round,
                trigger={"count": int(obs.value or 0), "indicators": obs.extra.get("indicators", [])},
                message_values={"count": int(obs.value or 0)},
                observations=[obs],
            )
        )
    return flags


def _rule_coverage(ctx: _Ctx) -> list[dict[str, Any]]:
    current_round = latest_plan_round(ctx.data, ctx.filters)
    if not current_round:
        ctx.skip("No plan round is available in scope.")
        return []
    subs = [s for s in ctx.data.submissions if s.kind == "plan" and s.round == current_round]
    if not subs:
        ctx.skip("No expected submissions in scope for the selected round.")
        return []
    ctx.outcome.entities_evaluated += 1
    submitted = sum(1 for s in subs if s.status in _SUBMITTED)
    coverage = submitted / len(subs) * 100
    threshold = float(ctx.rule["condition"]["value"])
    if coverage >= threshold:
        return []
    scope_id = f"scope:{(ctx.filters.region or 'all').lower()}:{current_round}"
    return [
        ctx.flag(
            entity_type="scope",
            entity_id=scope_id,
            entity_name=ctx.filters.region or "All regions",
            period_id=current_round,
            trigger={"submitted": submitted, "expected": len(subs), "coverage_pct": round(coverage, 1)},
            message_values={
                "submitted": submitted,
                "expected": len(subs),
                "coverage_pct": f"{coverage:.0f}",
                "threshold": f"{threshold:g}",
            },
            observations=[],
        )
    ]


_OPERATORS: dict[str, Callable[[_Ctx], list[dict[str, Any]]]] = {
    "absolute_percent_change_gte": _rule_yoy,
    "metric_present_other_missing": _rule_missing_target,
    "share_of_total_gte": _rule_concentration,
    "validation_pending_with_data": _rule_unvalidated,
    "stalled_days_gte": _rule_stalled,
    "overdue_days_gte": _rule_overdue,
    "unavailable_count_gte": _rule_unavailable,
    "coverage_below_pct": _rule_coverage,
    "pns_unreported_gte": _rule_pns_unreported,
    "priority_signals_gte": _rule_priority,
}


def evaluate_decision(
    decision: dict[str, Any],
    rules: dict[str, dict[str, Any]],
    data: DecisionData,
    filters: Filters,
    baseline: BaselineProvider,
    *,
    states: dict[str, dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[RuleOutcome]]:
    """Run every enabled rule of ``decision``. A failing rule is isolated and reported, not raised."""
    generated_at = (now or datetime.now(timezone.utc)).isoformat()
    flags: list[dict[str, Any]] = []
    outcomes: list[RuleOutcome] = []
    for rule_id in decision.get("rule_ids") or []:
        rule = rules.get(rule_id)
        if rule is None or not rule.get("enabled", True):
            continue
        outcome = RuleOutcome(rule_id=rule_id, rule_version=int(rule["version"]))
        ctx = _Ctx(decision, rule, data, filters, baseline, filters.lang, generated_at, outcome)
        handler = _OPERATORS.get(rule["condition"]["operator"])
        try:
            if handler is None:
                raise ValueError("unsupported operator")
            raised = handler(ctx)
        except Exception as exc:  # noqa: BLE001 - one bad rule must not hide the others
            outcome.status = "error"
            outcome.error = f"{type(exc).__name__}"
            raised = []
        outcome.flags_raised = len(raised)
        flags.extend(raised)
        outcomes.append(outcome)

    states = states or {}
    for flag in flags:
        state = states.get(flag["key"])
        if state:
            flag["status"] = state["status"]
            flag["review_note"] = state.get("note")
            flag["reviewed_at"] = state.get("updated_at")
    flags.sort(
        key=lambda f: (
            -SEVERITIES.index(f["severity"]),
            -f["trigger_values"].get("signals_met", 0),
            -f["trigger_values"].get("requirement", 0),
            f["entity_name"],
            f["rule_id"],
            f["period_id"] or "",
        )
    )
    return flags, outcomes
