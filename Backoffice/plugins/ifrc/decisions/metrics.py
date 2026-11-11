"""Metric registry and aggregation. Pure Python: no database or request access.

Every chart, endpoint, export and chatbot tool takes its numbers from here so a
calculation is defined once. Zero, not applicable, data unavailable and not
reported are kept distinct and never coerced into one another.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable

from plugins.ifrc.decisions.config import tr

# Observation states. A reported 0 is a real zero; the others carry no number.
REPORTED = "reported"
NOT_APPLICABLE = "not_applicable"
UNAVAILABLE = "unavailable"
NOT_REPORTED = "not_reported"

VALIDATED = "validated"
PROVISIONAL = "provisional"
DRAFT = "draft"
_QUALITY_RANK = {DRAFT: 0, PROVISIONAL: 1, VALIDATED: 2}
_MIN_QUALITY_RANK = {"any": 0, "reviewable": 1, "validated": 2}

_STATUS_TO_VALIDATION = {
    "approved": VALIDATED,
    "submitted": PROVISIONAL,
    "sent_for_review": PROVISIONAL,
    "pending": DRAFT,
    "in_progress": DRAFT,
    "requires_revision": DRAFT,
}


def validation_state_for(status: str | None) -> str:
    return _STATUS_TO_VALIDATION.get((status or "").strip().lower(), DRAFT)


def meets_quality(validation_state: str, minimum: str) -> bool:
    return _QUALITY_RANK.get(validation_state, 0) >= _MIN_QUALITY_RANK.get(minimum, 0)


@dataclass(frozen=True)
class MetricDefinition:
    id: str
    name: dict[str, str]
    description: str
    definition: str
    unit: str
    currency: str | None = None
    valid_dimensions: tuple[str, ...] = ()
    aggregation: str = "sum"
    source_precedence: str = ""
    allowed_validation_states: tuple[str, ...] = (VALIDATED, PROVISIONAL)
    state_semantics: str = (
        "Zero is a reported value. Not applicable, data unavailable and not reported are separate states "
        "and are never summed as zero."
    )
    time_logic: str = ""
    disclosure: str = "Aggregated only over records the requesting user may read."
    quality_tests: tuple[str, ...] = ()
    version: int = 1
    effective_from: str = "2026-11-04"
    provisional_mapping: bool = False

    def to_dict(self, lang: str | None = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": tr(self.name, lang),
            "description": self.description,
            "definition": self.definition,
            "unit": self.unit,
            "currency": self.currency,
            "valid_dimensions": list(self.valid_dimensions),
            "aggregation": self.aggregation,
            "source_precedence": self.source_precedence,
            "allowed_validation_states": list(self.allowed_validation_states),
            "state_semantics": self.state_semantics,
            "time_logic": self.time_logic,
            "disclosure": self.disclosure,
            "quality_tests": list(self.quality_tests),
            "version": self.version,
            "effective_from": self.effective_from,
            "provisional_mapping": self.provisional_mapping,
        }


_FUNDING_DIMS = ("country", "region", "round", "year", "funding_source", "validation_state")

METRIC_REGISTRY: dict[str, MetricDefinition] = {
    m.id: m
    for m in (
        MetricDefinition(
            id="funding_requirement",
            name={"en": "Funding requirement", "fr": "Besoin de financement"},
            description="Funding requirement stated in the Unified Plan, by funding source.",
            definition=(
                "Sum of the total column of the Unified Plan funding matrices (host National Society, IFRC "
                "Secretariat and each Participating National Society). A PNS's own submitted plan replaces the "
                "host's entry for that PNS. This is a requirement, not confirmed funding, income or expenditure."
            ),
            unit="CHF",
            currency="CHF",
            valid_dimensions=_FUNDING_DIMS,
            source_precedence="PNS plan (T22) over host plan (T24) entry for the same PNS.",
            time_logic="Year is the planning year of the matrix; the round is the assignment period.",
            quality_tests=("non_negative", "currency_is_chf", "no_double_count_of_pns_rows"),
        ),
        MetricDefinition(
            id="funding_requirement_by_priority",
            name={"en": "Funding requirement by Strategic Priority", "fr": "Besoin de financement par priorité stratégique"},
            description="Funding requirement split by Strategic Priority, Enabling Function and emergency operations.",
            definition="Sum of the Strategic Priority and Enabling Function columns of the Unified Plan funding matrices.",
            unit="CHF",
            currency="CHF",
            valid_dimensions=_FUNDING_DIMS + ("strategic_priority",),
            source_precedence="Same as funding_requirement.",
            time_logic="Same as funding_requirement.",
            quality_tests=("breakdown_reconciles_to_total",),
        ),
        MetricDefinition(
            id="people_targeted",
            name={"en": "People to be reached", "fr": "Personnes à atteindre"},
            description="Headline number of people the plan aims to reach.",
            definition="Total of the Unified Plan 'people to be reached' matrix. Strategic Priority rows are not additive.",
            unit="people",
            valid_dimensions=("country", "region", "round", "year", "validation_state"),
            source_precedence="Host plan (T24).",
            time_logic="Planning year of the matrix.",
            provisional_mapping=True,
            quality_tests=("non_negative",),
        ),
        MetricDefinition(
            id="emergency_funding_requirement",
            name={"en": "Emergency operations funding requirement", "fr": "Besoin de financement des opérations d'urgence"},
            description="Part of the funding requirement planned for emergency operations.",
            definition="Sum of the 'Emergency Operations' column of the Unified Plan funding matrices, across funding sources.",
            unit="CHF",
            currency="CHF",
            valid_dimensions=_FUNDING_DIMS,
            source_precedence="Same as funding_requirement.",
            time_logic="Same as funding_requirement.",
            quality_tests=("non_negative", "not_above_funding_requirement"),
        ),
        MetricDefinition(
            id="emergency_people_targeted",
            name={"en": "People to be reached in emergencies", "fr": "Personnes à atteindre en situation d'urgence"},
            description="People the plan aims to reach through listed emergency operations.",
            definition=(
                "For each emergency operation in the Unified Plan emergency matrix, the largest figure entered; "
                "operations are then added together. Figures across Strategic Priorities are not added."
            ),
            unit="people",
            valid_dimensions=("country", "region", "round", "year", "validation_state"),
            source_precedence="Host plan (T24).",
            time_logic="Planning year of the matrix.",
            provisional_mapping=True,
            quality_tests=("non_negative",),
        ),
        MetricDefinition(
            id="pns_support_count",
            name={"en": "Participating National Societies supporting", "fr": "Sociétés nationales participantes en appui"},
            description="Number of Participating National Societies with a planned contribution or bilateral support.",
            definition=(
                "Distinct PNS with a funding requirement above zero or a planned bilateral support entry in the host "
                "Unified Plan. Summed across countries it counts country-PNS relationships, not distinct PNS."
            ),
            unit="count",
            valid_dimensions=("country", "region", "round", "year", "validation_state"),
            source_precedence="Host plan (T24) and the PNS's own plan (T22) where submitted.",
            time_logic="Round year. Absence means no support is recorded, not that none exists.",
            quality_tests=("pns_names_resolved",),
        ),
        MetricDefinition(
            id="core_indicators_reported",
            name={"en": "Core and capacity indicators reported", "fr": "Indicateurs de base et de capacité renseignés"},
            description="Number of core and National Society capacity indicators with a reported value.",
            definition="Distinct indicators in the Core indicators and NS Data sections of a Unified Plan that carry a number.",
            unit="count",
            valid_dimensions=("country", "region", "round", "year", "validation_state"),
            source_precedence="Host plan (T24).",
            time_logic="Per assignment round.",
            quality_tests=("non_negative",),
        ),
        MetricDefinition(
            id="income",
            name={"en": "Income", "fr": "Revenu"},
            description="Income reported to FDRS, or in the Unified Report when FDRS has no figure.",
            definition=(
                "National Society total income in CHF. When FDRS and Unified Reporting both have the figure, "
                "FDRS is used. Otherwise the Unified Report funding total is used. This is income, not the "
                "plan's funding requirement."
            ),
            unit="CHF",
            currency="CHF",
            valid_dimensions=_FUNDING_DIMS,
            source_precedence="FDRS (template 21) over Unified Reporting (template 33); annual report over mid-year.",
            time_logic="Latest calendar year reported by each country. Years are not added together.",
            quality_tests=("non_negative", "currency_is_chf"),
        ),
        MetricDefinition(
            id="expenditure",
            name={"en": "Expenditure", "fr": "Dépenses"},
            description="Expenditure reported to FDRS, or in the Unified Report when FDRS has no figure.",
            definition=(
                "National Society expenditure in CHF, with the same source rule as income. "
                "Not added to the funding requirement."
            ),
            unit="CHF",
            currency="CHF",
            valid_dimensions=_FUNDING_DIMS,
            source_precedence="FDRS (template 21) over Unified Reporting (template 33); annual report over mid-year.",
            time_logic="Latest calendar year reported by each country. Years are not added together.",
            quality_tests=("non_negative", "currency_is_chf"),
        ),
        MetricDefinition(
            id="volunteers",
            name={"en": "Volunteers", "fr": "Volontaires"},
            description="People volunteering, from the preferred approved source for that country and year.",
            definition="Volunteer count on the winning approved assignment for the country and year.",
            unit="count",
            valid_dimensions=("country", "region", "year", "validation_state"),
            source_precedence="FDRS, then annual reporting, then mid-year reporting, then planning. One source supplies all four key figures.",
            time_logic="Latest year per country. A blank on the winning source stays blank.",
            quality_tests=("non_negative",),
        ),
        MetricDefinition(
            id="paid_staff",
            name={"en": "Paid staff", "fr": "Personnel rémunéré"},
            description="Paid staff, from the same approved source as volunteers.",
            definition="Paid staff count on the winning approved assignment for the country and year.",
            unit="count",
            valid_dimensions=("country", "region", "year", "validation_state"),
            source_precedence="Same assignment as volunteers.",
            time_logic="Latest year per country.",
            quality_tests=("non_negative",),
        ),
        MetricDefinition(
            id="branches",
            name={"en": "Branches", "fr": "Branches"},
            description="National Society branches, from the same approved source as volunteers.",
            definition="Branch count on the winning approved assignment for the country and year.",
            unit="count",
            valid_dimensions=("country", "region", "year", "validation_state"),
            source_precedence="Same assignment as volunteers.",
            time_logic="Latest year per country.",
            quality_tests=("non_negative",),
        ),
        MetricDefinition(
            id="local_units",
            name={"en": "Local units", "fr": "Unités locales"},
            description="National Society local units, from the same approved source as volunteers.",
            definition="Local unit count on the winning approved assignment for the country and year.",
            unit="count",
            valid_dimensions=("country", "region", "year", "validation_state"),
            source_precedence="Same assignment as volunteers.",
            time_logic="Latest year per country.",
            quality_tests=("non_negative",),
        ),
        MetricDefinition(
            id="submission_coverage",
            name={"en": "Submission coverage", "fr": "Couverture des soumissions"},
            description="Share of expected submissions that have been submitted or approved.",
            definition="(submitted + sent for review + approved) / expected assignments, cancelled excluded.",
            unit="percent",
            aggregation="ratio",
            valid_dimensions=("region", "round", "validation_state"),
            allowed_validation_states=(VALIDATED, PROVISIONAL, DRAFT),
            time_logic="Per assignment round.",
        ),
        MetricDefinition(
            id="submissions_stalled_days",
            name={"en": "Days a submission has awaited review", "fr": "Jours d'attente d'examen"},
            description="Days since submission for assignments that are submitted or sent for review.",
            definition="today - submitted_at for status submitted or sent_for_review.",
            unit="days",
            aggregation="max",
            valid_dimensions=("country", "region", "round"),
            allowed_validation_states=(PROVISIONAL,),
            time_logic="Evaluated on the day of the request.",
        ),
        MetricDefinition(
            id="submissions_overdue_days",
            name={"en": "Days past due date", "fr": "Jours de retard"},
            description="Days past the due date for assignments still open.",
            definition="today - due_date for status pending, in progress or requires revision.",
            unit="days",
            aggregation="max",
            valid_dimensions=("country", "region", "round"),
            allowed_validation_states=(DRAFT,),
            time_logic="Evaluated on the day of the request.",
        ),
        MetricDefinition(
            id="indicators_data_unavailable",
            name={"en": "Applicable indicators with data unavailable", "fr": "Indicateurs applicables sans données"},
            description="Count of indicator values marked 'data not available' in a submission.",
            definition="Count of Unified Plan fact rows whose availability is 'Data not available'.",
            unit="count",
            aggregation="count",
            valid_dimensions=("country", "region", "round", "validation_state"),
            time_logic="Per assignment round.",
        ),
    )
}


@dataclass(frozen=True)
class Observation:
    metric_id: str
    entity_id: str  # ISO3
    entity_name: str
    region: str | None
    round: str | None
    year: int | None
    state: str
    value: float | None
    validation_state: str
    submission_id: int | None
    status: str | None
    unit: str = ""
    currency: str | None = None
    funding_source: str | None = None
    strategic_priority: str | None = None
    ns: str | None = None
    label: str | None = None
    evidence_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def dim(self, name: str) -> Any:
        return {
            "country": self.entity_id,
            "region": self.region,
            "round": self.round,
            "year": self.year,
            "funding_source": self.funding_source,
            "strategic_priority": self.strategic_priority,
            "validation_state": self.validation_state,
        }[name]


def evidence_id_for(*parts: Any) -> str:
    digest = hashlib.sha256("|".join("" if p is None else str(p) for p in parts).encode("utf-8")).hexdigest()
    return f"EVID-{digest[:16]}"


def aggregate(
    observations: Iterable[Observation],
    group_by: tuple[str, ...] = (),
    *,
    method: str = "sum",
) -> list[dict[str, Any]]:
    """Group observations. A group has a number only when something was reported.

    ``state`` tells why there is no number: all not applicable, any unavailable, or nothing reported.
    """
    groups: dict[tuple, dict[str, Any]] = {}
    for obs in observations:
        key = tuple(obs.dim(name) for name in group_by)
        group = groups.setdefault(
            key,
            {
                "key": {name: value for name, value in zip(group_by, key)},
                "values": [],
                "n_reported": 0,
                "n_not_applicable": 0,
                "n_unavailable": 0,
                "evidence_ids": [],
                "validation_states": set(),
                "unit": obs.unit,
                "currency": obs.currency,
            },
        )
        group["validation_states"].add(obs.validation_state)
        if obs.evidence_id and obs.evidence_id not in group["evidence_ids"]:
            group["evidence_ids"].append(obs.evidence_id)
        if obs.state == REPORTED and obs.value is not None:
            group["n_reported"] += 1
            group["values"].append(obs.value)
        elif obs.state == NOT_APPLICABLE:
            group["n_not_applicable"] += 1
        else:
            group["n_unavailable"] += 1

    out = []
    for group in groups.values():
        values = group.pop("values")
        if values:
            number = {"sum": sum, "max": max, "min": min, "count": len}[method](values)
            state = REPORTED
        else:
            number = None
            if group["n_unavailable"]:
                state = UNAVAILABLE
            elif group["n_not_applicable"]:
                state = NOT_APPLICABLE
            else:
                state = NOT_REPORTED
        group["value"] = number
        group["state"] = state
        group["validation_states"] = sorted(group["validation_states"])
        out.append(group)
    out.sort(key=lambda g: tuple(str(v) for v in g["key"].values()))
    return out
