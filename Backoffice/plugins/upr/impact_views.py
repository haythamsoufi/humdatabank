"""View of the Analysis "data" section: KPI cards, charts and tables.

Turns the payload from :func:`plugins.upr.impact.build_upr_impact` into the
renderer-independent structure described in :mod:`plugins.upr.analysis_spec`.
This is the one place that decides which visuals exist, how they are titled, how
each series is drawn and what the matching table shows. The tab, the PDF export
and the presentation all read it.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from plugins.upr.analysis_labels import analysis_labels, fill
from plugins.upr.analysis_spec import (
    COLORS,
    along,
    at_year,
    axis,
    chart,
    column,
    country_rows,
    kpi,
    latest_first,
    midyear_cell,
    series,
    table,
    table_row,
    value_or_none,
    visual,
    year_label,
    years_of,
)

CAPACITY_PANELS = (
    ("volunteers", "volunteers", "green"),
    ("staff", "staff", "red"),
    ("branches", "branches", "navy"),
    ("local_units", "local_units", "blue"),
)


def has_any_data(payload: Mapping[str, Any]) -> bool:
    by_year = (payload.get("coverage") or {}).get("by_year") or []
    return any((p.get("plan_submitted") or 0) > 0 or (p.get("report_submitted") or 0) > 0 for p in by_year)


def build_impact_view(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """KPI cards, visuals and notes for the data section of the Analysis."""
    labels = analysis_labels()
    view: dict[str, Any] = {
        "title": labels["intro_title"],
        "lead": labels["intro_lead"],
        "kpis": [],
        "visuals": [],
        "notes": [],
        "warnings": [],
        "has_data": False,
    }
    if not payload or not has_any_data(payload):
        return view

    context = _Context(payload, labels)
    view["has_data"] = True
    view["kpis"] = _kpis(payload.get("headline") or {}, labels)
    view["visuals"] = [
        _coverage(context),
        _funding(context),
        _reach(context),
        _partners(context),
        _capacity(context),
    ]
    view["notes"] = _notes(payload, labels)
    return view


class _Context:
    """What every visual of the data section needs from the payload."""

    def __init__(self, payload: Mapping[str, Any], labels: Mapping[str, str]) -> None:
        self.payload = payload
        self.labels = labels
        self.in_progress_years = list(payload.get("in_progress_years") or [])
        self.midyear_years = set(payload.get("midyear_fallback_years") or [])
        self.years = list(payload.get("years") or [])

    def year_cats(self, years: Iterable[Any]) -> list[str]:
        return [year_label(y, self.in_progress_years) for y in years]


def _latest(headline: Mapping[str, Any], key: str) -> Any:
    return (headline.get(key) or {}).get("latest")


def _kpis(headline: Mapping[str, Any], labels: Mapping[str, str]) -> list[dict[str, Any]]:
    return [
        kpi("coverage", labels["kpi_coverage"], _latest(headline, "coverage"), "int", headline.get("coverage"), labels),
        kpi(
            "plan_requirement",
            labels["kpi_requirement"],
            _latest(headline, "plan_requirement"),
            "money",
            headline.get("plan_requirement"),
            labels,
        ),
        kpi("reach", labels["kpi_reach"], _latest(headline, "reach"), "int", headline.get("reach"), labels),
        kpi("partners", labels["kpi_partners"], _latest(headline, "partners"), "int", headline.get("partners"), labels),
        kpi(
            "partner_funding",
            labels["kpi_partner_funding"],
            _latest(headline, "partner_funding"),
            "money",
            headline.get("partner_funding"),
            labels,
        ),
    ]


def _notes(payload: Mapping[str, Any], labels: Mapping[str, str]) -> list[str]:
    notes: list[str] = []
    in_progress = payload.get("in_progress_years") or []
    midyear = payload.get("midyear_fallback_years") or []
    if in_progress:
        notes.append(fill(labels["in_progress_note"], years=", ".join(str(y) for y in in_progress)))
    if midyear:
        notes.append(fill(labels["midyear_note"], years=", ".join(str(y) for y in midyear)))
    notes.append(labels["impact_footnote"])
    return notes


def _join_countries(sources: Mapping[str, Iterable[Mapping[str, Any]] | None]) -> list[dict[str, Any]]:
    """Merge per-metric country lists into one row per country."""
    rows: dict[str, dict[str, Any]] = {}
    for field, countries in sources.items():
        for item in countries or []:
            iso = item.get("iso3")
            if not iso:
                continue
            row = rows.setdefault(iso, {"country": item.get("country") or iso})
            if item.get("country"):
                row["country"] = item["country"]
            row[field] = item.get("value")
    return list(rows.values())


def _coverage(ctx: _Context) -> dict[str, Any]:
    labels = ctx.labels
    points = (ctx.payload.get("coverage") or {}).get("by_year") or []
    rows = []
    for p in points:
        countries = country_rows(
            [c.get("country"), c.get("plan_submitted") or None, c.get("report_submitted") or None]
            for c in p.get("countries") or []
        )
        rows.append(
            (
                p.get("year"),
                table_row(
                    [
                        year_label(p.get("year"), ctx.in_progress_years),
                        value_or_none(p, "plan_submitted"),
                        value_or_none(p, "report_submitted"),
                    ],
                    countries,
                ),
            )
        )
    return visual(
        "coverage",
        labels["coverage_title"],
        labels["coverage_hint"],
        wide=True,
        chart=chart(
            ctx.year_cats(years_of(points)),
            [
                series(labels["plan_submitted"], column(points, "plan_submitted"), color=COLORS["navy"]),
                series(labels["report_submitted"], column(points, "report_submitted"), color=COLORS["teal"]),
            ],
        ),
        table=table(
            labels["coverage_title"],
            [labels["year"], labels["plan_submitted"], labels["report_submitted"]],
            latest_first(rows),
        ),
    )


def _funding(ctx: _Context) -> dict[str, Any]:
    labels = ctx.labels
    funding = ctx.payload.get("funding") or {}
    plan_pts = funding.get("plan_requirement")
    reported_pts = funding.get("report_funding")
    spent_pts = funding.get("report_expenditure")

    rows = []
    for year in ctx.years:
        plan = at_year(plan_pts, year)
        reported = at_year(reported_pts, year)
        spent = at_year(spent_pts, year)
        midyear = year in ctx.midyear_years
        countries = country_rows(
            [
                row["country"],
                row.get("plan"),
                midyear_cell(row.get("funding"), midyear),
                midyear_cell(row.get("expenditure"), midyear),
            ]
            for row in _join_countries(
                {
                    "plan": (plan or {}).get("countries"),
                    "funding": (reported or {}).get("countries"),
                    "expenditure": (spent or {}).get("countries"),
                }
            )
        )
        rows.append(
            (
                year,
                table_row(
                    [
                        year_label(year, ctx.in_progress_years),
                        value_or_none(plan, "value"),
                        midyear_cell(value_or_none(reported, "value"), midyear),
                        midyear_cell(value_or_none(spent, "value"), midyear),
                    ],
                    countries,
                ),
            )
        )

    return visual(
        "funding",
        labels["funding_title"],
        labels["funding_hint"],
        chart=chart(
            ctx.year_cats(ctx.years),
            [
                series(labels["plan_requirement"], along(ctx.years, plan_pts, "value"), kind="line", color=COLORS["navy"], fmt="money"),
                series(labels["report_funding"], along(ctx.years, reported_pts, "value"), kind="line", color=COLORS["amber"], fmt="money"),
                series(
                    labels["report_expenditure"],
                    along(ctx.years, spent_pts, "value"),
                    kind="line",
                    color=COLORS["red"],
                    fmt="money",
                    dashed=True,
                ),
            ],
            axes={"primary": axis("money")},
        ),
        table=table(
            labels["funding_title"],
            [labels["year"], labels["plan_requirement"], labels["report_funding"], labels["report_expenditure"]],
            latest_first(rows),
            note=labels["funding_source_note"],
            legend=labels["midyear_legend"],
        ),
    )


def _reach(ctx: _Context) -> dict[str, Any]:
    labels = ctx.labels
    points = (ctx.payload.get("reach") or {}).get("by_year") or []
    rows = [
        (
            p.get("year"),
            table_row(
                [year_label(p.get("year"), ctx.in_progress_years), p.get("round"), value_or_none(p, "value")],
                country_rows([c.get("country"), None, c.get("value") or None] for c in p.get("countries") or []),
            ),
        )
        for p in points
    ]
    return visual(
        "reach",
        labels["reach_title"],
        labels["reach_hint"],
        chart=chart(
            ctx.year_cats(years_of(points)),
            [series(labels["people_reached"], column(points, "value"), kind="area", color=COLORS["teal"], fmt="int")],
            axes={"primary": axis("money")},
            gradient=(0.4, 0.5, 0.05),
        ),
        table=table(
            labels["reach_title"],
            [labels["year"], labels["plan_round"], labels["people_reached"]],
            latest_first(rows),
        ),
    )


def _partners(ctx: _Context) -> dict[str, Any]:
    labels = ctx.labels
    points = (ctx.payload.get("partners") or {}).get("by_year") or []
    rows = [
        (
            p.get("year"),
            table_row(
                [
                    year_label(p.get("year"), ctx.in_progress_years),
                    p.get("round"),
                    value_or_none(p, "partners"),
                    value_or_none(p, "funding"),
                ],
                country_rows(
                    [c.get("country"), None, c.get("partners") or None, c.get("funding") or None]
                    for c in p.get("countries") or []
                ),
            ),
        )
        for p in points
    ]
    return visual(
        "partners",
        labels["partners_title"],
        labels["partners_hint"],
        chart=chart(
            ctx.year_cats(years_of(points)),
            [
                series(labels["partners"], column(points, "partners"), color=COLORS["purple"], fmt="int"),
                series(
                    labels["partner_funding"],
                    column(points, "funding"),
                    kind="line",
                    color=COLORS["amber"],
                    axis_id="secondary",
                    fmt="money",
                ),
            ],
            axes={"primary": axis("int"), "secondary": axis("money", opposite=True)},
            column_width="45%",
        ),
        table=table(
            labels["partners_title"],
            [labels["year"], labels["report_round"], labels["partners"], labels["partner_funding"]],
            latest_first(rows),
            note=labels["partners_source_note"],
        ),
    )


def _capacity(ctx: _Context) -> dict[str, Any]:
    labels = ctx.labels
    capacity = ctx.payload.get("capacity") or {}

    # One shared axis cannot show millions of volunteers next to thousands of
    # branches, so each measure is its own panel scaled to its own counts.
    panels = []
    for key, label_key, color in CAPACITY_PANELS:
        points = capacity.get(key) or []
        years = years_of(points)
        latest = None
        for p in points:
            if p.get("value"):
                latest = p
        data = [v if (v or 0) > 0 else None for v in along(years, points, "value")]
        panels.append(
            {
                "id": key,
                "name": labels[label_key],
                "color": COLORS[color],
                "value": latest.get("value") if latest else None,
                "year": latest.get("year") if latest else None,
                "chart": chart(
                    ctx.year_cats(years),
                    [series(labels[label_key], data, kind="area", color=COLORS[color], fmt="int")],
                    axes={"primary": axis("money", tick_amount=4)},
                    height=240,
                    curve="straight",
                    stroke_width=2,
                    legend=False,
                    gradient=(0.3, 0.35, 0.02),
                ),
            }
        )

    cap_years = years_of(capacity.get("volunteers"))
    rows = []
    for year in cap_years:
        vol = at_year(capacity.get("volunteers"), year)
        staff = at_year(capacity.get("staff"), year)
        branches = at_year(capacity.get("branches"), year)
        units = at_year(capacity.get("local_units"), year)
        countries = country_rows(
            [
                row["country"],
                None,
                row.get("volunteers") or None,
                row.get("staff") or None,
                row.get("branches") or None,
                row.get("units") or None,
            ]
            for row in _join_countries(
                {
                    "volunteers": (vol or {}).get("countries"),
                    "staff": (staff or {}).get("countries"),
                    "branches": (branches or {}).get("countries"),
                    "units": (units or {}).get("countries"),
                }
            )
        )
        rows.append(
            (
                year,
                table_row(
                    [
                        year_label(year, ctx.in_progress_years),
                        (vol or {}).get("round"),
                        value_or_none(vol, "value"),
                        value_or_none(staff, "value"),
                        value_or_none(branches, "value"),
                        value_or_none(units, "value"),
                    ],
                    countries,
                ),
            )
        )
    return visual(
        "capacity",
        labels["capacity_title"],
        labels["capacity_hint"],
        kind="panels",
        wide=True,
        panels=panels,
        table=table(
            labels["capacity_title"],
            [
                labels["year"],
                labels["report_round"],
                labels["volunteers"],
                labels["staff"],
                labels["branches"],
                labels["local_units"],
            ],
            latest_first(rows),
        ),
    )
