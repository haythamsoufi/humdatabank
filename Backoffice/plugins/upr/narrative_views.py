"""View of the Analysis "participation" section: data vs narrative, per round type.

Turns the payload from :func:`plugins.upr.narrative.build_narrative_participation`
into the renderer-independent structure described in
:mod:`plugins.upr.analysis_spec`. One view is built for every round type
(``ALL`` overview, ``P`` plans, ``MYR`` mid-year, ``AR`` annual), so the tab can
switch without another request and an export can walk all of them.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from plugins.upr.analysis_common import TRACKS
from plugins.upr.analysis_labels import analysis_labels, fill
from plugins.upr.analysis_spec import (
    COLORS,
    axis,
    chart,
    country_rows,
    format_int_text,
    kpi,
    latest_first,
    pct_text,
    plain_rows,
    series,
    table,
    table_row,
    visual,
    with_abs_change,
)

OVERVIEW = "ALL"
VIEW_TRACKS = (OVERVIEW, *TRACKS)

# Gap lists, as (payload key, label key). Per round type they refer to its
# latest settled round; the overview spans every settled round.
_TRACK_GAP_LISTS = (
    ("narrative_only", "narr_narrative_only"),
    ("data_only", "narr_data_only"),
    ("unpublished", "narr_not_public"),
    ("lapsed", "narr_lapsed_title"),
)
_OVERVIEW_GAP_LISTS = (
    ("always", "narr_gap_always"),
    ("intermittent", "narr_gap_intermittent"),
    ("planned_not_reported", "narr_gap_planned_not_reported"),
    ("never", "narr_gap_never"),
)


def build_narrative_views(payload: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    """``{track: view}`` for the overview and each round type."""
    labels = analysis_labels()
    return {track: build_narrative_view(payload, track, labels) for track in VIEW_TRACKS}


def build_narrative_view(
    payload: Mapping[str, Any] | None,
    track: str = OVERVIEW,
    labels: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    labels = labels or analysis_labels()
    view: dict[str, Any] = {
        "track": track,
        "title": labels["narr_title"],
        "lead": labels["narr_lead"],
        "kpis": [],
        "visuals": [],
        "notes": [],
        "warnings": [],
        "has_data": False,
    }
    if not payload:
        return view

    ctx = _Context(payload, track, labels)
    view["has_data"] = bool(payload.get("rounds"))
    view["kpis"] = _overview_kpis(ctx) if ctx.overview else _track_kpis(ctx)
    view["visuals"] = [_stage(ctx), _mix(ctx), _publication(ctx), _retention(ctx), _gaps(ctx)]
    view["notes"] = _notes(ctx)
    view["warnings"] = _warnings(ctx)
    return view


class _Context:
    def __init__(self, payload: Mapping[str, Any], track: str, labels: Mapping[str, str]) -> None:
        self.payload = payload
        self.track = track
        self.labels = labels
        self.overview = track == OVERVIEW
        tracks = payload.get("tracks") or {}
        if self.overview:
            # Every round, oldest first, so plans / mid-year / annual interleave by date.
            merged = [*(tracks.get("P") or []), *(tracks.get("MYR") or []), *(tracks.get("AR") or [])]
            self.points = sorted(merged, key=lambda p: p.get("order") or 0)
        else:
            self.points = list(tracks.get(track) or [])

    def categories(self) -> list[str]:
        return [
            (str(p.get("round")) if self.overview else str(p.get("year"))) + (" *" if p.get("in_progress") else "")
            for p in self.points
        ]

    def values(self, key: str, *, only_with_data: bool = False) -> list[Any]:
        return [
            None if (only_with_data and not p.get("data_available")) else p.get(key)
            for p in self.points
        ]


def _headline(ctx: _Context, track: str, metric: str) -> Mapping[str, Any]:
    return ((ctx.payload.get("headline") or {}).get(track) or {}).get(metric) or {}


# -- KPI cards ----------------------------------------------------------------


def _overview_kpis(ctx: _Context) -> list[dict[str, Any]]:
    labels = ctx.labels
    overview = ctx.payload.get("overview") or {}
    cycle = overview.get("cycle")
    settled = len(overview.get("settled_rounds") or [])
    always = len((overview.get("gaps") or {}).get("always") or [])

    def by_track(kpi_id: str, label_key: str, track: str) -> dict[str, Any]:
        delta = _headline(ctx, track, "any")
        return kpi(kpi_id, labels[label_key], delta.get("latest"), "int", delta, labels)

    cycle_delta = None
    if cycle:
        cycle_delta = {
            "latest": cycle.get("completion_pct"),
            "latest_year": cycle.get("year"),
            "note": fill(
                labels["narr_kpi_cycle_note"],
                both=format_int_text(cycle.get("both")),
                plan=format_int_text(cycle.get("plan")),
            ),
        }
    always_delta = None
    if settled:
        always_delta = {
            "latest": always,
            "note": fill(labels["narr_kpi_always_note"], n=format_int_text(settled)),
        }
    return [
        by_track("plans", "narr_kpi_plans", "P"),
        by_track("midyear", "narr_kpi_midyear", "MYR"),
        by_track("annual", "narr_kpi_annual", "AR"),
        kpi("cycle", labels["narr_kpi_cycle"], cycle.get("completion_pct") if cycle else None, "pct", cycle_delta, labels),
        kpi("always", labels["narr_kpi_always"], always if settled else None, "int", always_delta, labels),
    ]


def _track_kpis(ctx: _Context) -> list[dict[str, Any]]:
    labels = ctx.labels
    track = ctx.track
    any_delta = _headline(ctx, track, "any")
    internal = _headline(ctx, track, "internal")
    public = _headline(ctx, track, "public")
    hidden = with_abs_change(_headline(ctx, track, "narrative_only"), "")
    publication = with_abs_change(_headline(ctx, track, "publication_pct"), " pts")
    return [
        kpi("any", labels["narr_kpi_any"], any_delta.get("latest"), "int", any_delta, labels),
        kpi("internal", labels["narr_kpi_internal"], internal.get("latest"), "int", internal, labels),
        kpi("public", labels["narr_kpi_public"], public.get("latest"), "int", public, labels),
        kpi("hidden", labels["narr_kpi_hidden"], hidden.get("latest"), "int", hidden, labels),
        kpi("publication", labels["narr_kpi_publication"], publication.get("latest"), "pct", publication, labels),
    ]


# -- tables --------------------------------------------------------------------


def _year_cell(point: Mapping[str, Any]) -> str:
    return str(point.get("year")) + (" *" if point.get("in_progress") else "")


def _point_table(
    ctx: _Context,
    title: str,
    columns: Sequence[str],
    cells_of: Any,
    country_keys: Sequence[str | None],
    *,
    note: str = "",
) -> dict[str, Any]:
    rows = []
    for point in ctx.points:
        details = []
        for c in point.get("countries") or []:
            cells: list[Any] = [c.get("country"), ""]
            for key in country_keys:
                cells.append((c.get(key) or None) if key else None)
            details.append(cells)
        # ``order`` keeps plan / mid-year / annual rounds of one year in date order.
        sort_key = point.get("order") if point.get("order") is not None else point.get("year")
        rows.append((sort_key, table_row(cells_of(point), country_rows(details))))
    return table(title, columns, latest_first(rows), note=note)


# -- visuals -------------------------------------------------------------------


def _stage(ctx: _Context) -> dict[str, Any]:
    labels = ctx.labels
    return visual(
        "narr_stage",
        labels["stage_title"],
        labels["stage_hint"],
        wide=True,
        chart=chart(
            ctx.categories(),
            [
                series(labels["narr_data_submitted"], ctx.values("data_submitted", only_with_data=True), color=COLORS["navy"]),
                series(labels["narr_internal"], ctx.values("internal"), color=COLORS["amber"]),
                series(labels["narr_public"], ctx.values("public"), color=COLORS["teal"]),
                series(labels["narr_either"], ctx.values("any"), kind="line", color=COLORS["red"]),
            ],
            height=320,
            column_width="65%",
        ),
        table=_point_table(
            ctx,
            labels["stage_title"],
            [
                labels["year"],
                labels["narr_round"],
                labels["narr_data_submitted"],
                labels["narr_internal"],
                labels["narr_public"],
                labels["narr_either"],
                labels["narr_participation_pct"],
            ],
            lambda p: [
                _year_cell(p),
                p.get("round"),
                p.get("data_submitted") if p.get("data_available") else None,
                p.get("internal"),
                p.get("public"),
                p.get("any"),
                pct_text(p.get("participation_pct")),
            ],
            ["data_submitted", "internal", "public", "any", None],
        ),
    )


def _mix(ctx: _Context) -> dict[str, Any]:
    labels = ctx.labels
    return visual(
        "narr_mix",
        labels["mix_title"],
        labels["mix_hint"],
        chart=chart(
            ctx.categories(),
            [
                series(labels["narr_both"], ctx.values("both"), color=COLORS["green"]),
                series(labels["narr_narrative_only"], ctx.values("narrative_only"), color=COLORS["amber"]),
                series(labels["narr_data_only"], ctx.values("data_only"), color=COLORS["navy"]),
            ],
            stacked=True,
            column_width="55%",
            border_radius=2,
        ),
        table=_point_table(
            ctx,
            labels["mix_title"],
            [labels["year"], labels["narr_round"], labels["narr_both"], labels["narr_narrative_only"], labels["narr_data_only"]],
            lambda p: [_year_cell(p), p.get("round"), p.get("both"), p.get("narrative_only"), p.get("data_only")],
            ["both", "narrative_only", "data_only"],
        ),
    )


def _publication(ctx: _Context) -> dict[str, Any]:
    labels = ctx.labels
    return visual(
        "narr_pub",
        labels["pub_title"],
        labels["pub_hint"],
        chart=chart(
            ctx.categories(),
            [
                series(labels["narr_internal"], ctx.values("internal"), color=COLORS["amber"]),
                series(labels["narr_published"], ctx.values("published"), color=COLORS["teal"]),
                series(
                    labels["narr_publication_rate"],
                    ctx.values("publication_pct"),
                    kind="line",
                    color=COLORS["purple"],
                    axis_id="secondary",
                    fmt="pct",
                ),
            ],
            axes={
                "primary": axis("int"),
                "secondary": axis("pct", opposite=True, minimum=0, maximum=100),
            },
        ),
        table=_point_table(
            ctx,
            labels["pub_title"],
            [
                labels["year"],
                labels["narr_round"],
                labels["narr_internal"],
                labels["narr_published"],
                labels["narr_not_public"],
                labels["narr_public_only"],
                labels["narr_publication_rate"],
            ],
            lambda p: [
                _year_cell(p),
                p.get("round"),
                p.get("internal"),
                p.get("published"),
                p.get("unpublished"),
                p.get("public_only"),
                pct_text(p.get("publication_pct")),
            ],
            ["internal", "published", "unpublished", "public_only", None],
        ),
    )


def _retention(ctx: _Context) -> dict[str, Any]:
    """Retention for one round type; across all rounds, an engagement-depth histogram."""
    labels = ctx.labels
    if ctx.overview:
        engagement = (ctx.payload.get("overview") or {}).get("engagement") or []
        title = labels["narr_eng_title"]
        return visual(
            "narr_ret",
            title,
            labels["narr_eng_hint"],
            chart=chart(
                [str(e.get("rounds")) for e in engagement],
                [series(labels["narr_eng_series"], [e.get("countries") for e in engagement], color=COLORS["teal"])],
                legend=False,
                data_labels=True,
                x_title=labels["narr_eng_rounds"],
            ),
            table=table(
                title,
                [labels["narr_eng_rounds"], labels["narr_eng_series"]],
                plain_rows([str(e.get("rounds")), e.get("countries")] for e in engagement),
                note=labels["narr_eng_hint"],
            ),
        )

    title = labels["narr_ret_title"]
    lapsed = [None if p.get("lapsed") is None else -p["lapsed"] for p in ctx.points]
    return visual(
        "narr_ret",
        title,
        labels["narr_ret_hint"],
        chart=chart(
            ctx.categories(),
            [
                series(labels["narr_baseline"], ctx.values("baseline"), color=COLORS["grey"], fmt="abs_int"),
                series(labels["narr_retained"], ctx.values("retained"), color=COLORS["green"], fmt="abs_int"),
                series(labels["narr_new"], ctx.values("new"), color=COLORS["teal"], fmt="abs_int"),
                series(labels["narr_lapsed"], lapsed, color=COLORS["red"], fmt="abs_int"),
            ],
            axes={"primary": axis("abs_int")},
            stacked=True,
            column_width="55%",
            border_radius=2,
        ),
        table=_point_table(
            ctx,
            title,
            [labels["year"], labels["narr_round"], labels["narr_baseline"], labels["narr_retained"], labels["narr_new"], labels["narr_lapsed"]],
            lambda p: [_year_cell(p), p.get("round"), p.get("baseline"), p.get("retained"), p.get("new"), p.get("lapsed")],
            ["baseline", "retained", "new", "lapsed"],
        ),
    )


def _gap_source(ctx: _Context) -> tuple[Sequence[tuple[str, str]], Mapping[str, Any], str, str]:
    """``(definitions, lists, hint, title suffix)`` for the "Gaps to follow up" card."""
    labels = ctx.labels
    if ctx.overview:
        overview = ctx.payload.get("overview") or {}
        lists = dict(overview.get("gaps") or {})
        cycle = overview.get("cycle")
        if cycle:
            lists["planned_not_reported"] = cycle.get("planned_not_reported") or []
        hint = fill(
            labels["narr_gaps_hint_all"],
            n=format_int_text(len(overview.get("settled_rounds") or [])),
            year=cycle.get("year") if cycle else "",
        )
        return _OVERVIEW_GAP_LISTS, lists, hint, ""
    gap = (ctx.payload.get("gaps") or {}).get(ctx.track)
    if not gap:
        return _TRACK_GAP_LISTS, {}, "", ""
    return (
        _TRACK_GAP_LISTS,
        gap,
        fill(labels["narr_gaps_hint"], round=gap.get("round")),
        " — " + str(gap.get("round")),
    )


def _gaps(ctx: _Context) -> dict[str, Any]:
    labels = ctx.labels
    definitions, lists, hint, suffix = _gap_source(ctx)
    gaps = []
    if lists:
        for key, label_key in definitions:
            entries = lists.get(key) or []
            gaps.append(
                {
                    "id": key,
                    "label": labels[label_key],
                    "count": len(entries),
                    "table": table(
                        labels[label_key] + suffix,
                        [labels["narr_country"], labels["narr_region"]],
                        plain_rows([c.get("name"), c.get("region")] for c in entries),
                        note="" if entries else labels["narr_none"],
                    ),
                }
            )

    rounds = ctx.payload.get("rounds") or []
    matrix = table(
        labels["narr_matrix_title"],
        [labels["narr_country"], labels["narr_region"], *rounds],
        plain_rows(
            [m.get("name"), m.get("region"), *[(m.get("rounds") or {}).get(r, "") for r in rounds]]
            for m in ctx.payload.get("matrix") or []
        ),
        note=labels["narr_matrix_note"],
    )
    return visual(
        "narr_gaps",
        labels["gaps_title"],
        hint,
        kind="gaps",
        gaps=gaps,
        table=matrix,
        table_label=labels["matrix_button_aria"],
    )


# -- notes ---------------------------------------------------------------------


def _notes(ctx: _Context) -> list[str]:
    labels = ctx.labels
    payload = ctx.payload
    notes: list[str] = []
    open_rounds = [
        r for r in payload.get("in_progress") or [] if ctx.overview or str(r).startswith(ctx.track)
    ]
    if open_rounds:
        notes.append(fill(labels["narr_note_in_progress"], years=", ".join(open_rounds)))
    no_data = [str(p.get("round")) for p in ctx.points if not p.get("data_available")]
    if no_data:
        notes.append(fill(labels["narr_note_no_data"], rounds=", ".join(no_data)))
    sources = payload.get("sources") or {}
    notes.append(
        fill(
            labels["narr_note_sources"],
            internal=format_int_text((sources.get("internal") or {}).get("documents")),
            public=format_int_text((sources.get("public") or {}).get("documents")),
        )
    )
    if payload.get("universe"):
        notes.append(fill(labels["narr_note_universe"], n=format_int_text(payload["universe"])))
    return notes


def _warnings(ctx: _Context) -> list[str]:
    labels = ctx.labels
    sources = ctx.payload.get("sources") or {}
    out = []
    for key, label_key in (("internal", "narr_internal"), ("public", "narr_public")):
        source = sources.get(key)
        if source and source.get("available") is False:
            out.append(f"{labels[label_key]}: {source.get('message') or ''}")
    return out
