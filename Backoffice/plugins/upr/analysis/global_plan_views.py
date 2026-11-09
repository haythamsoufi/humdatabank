"""Renderer-independent views for the Global Plan Analysis subtab."""

from __future__ import annotations

from typing import Any, Mapping

from plugins.upr.analysis.analysis_labels import analysis_labels, fill
from plugins.upr.analysis.analysis_spec import (
    COLORS,
    axis,
    chart,
    country_rows,
    kpi,
    plain_rows,
    series,
    table,
    table_row,
    visual,
)
from plugins.upr.analysis.global_plan import SECTION_IDS, THEME_CODES

ENTITY_COLORS = {
    "HNS": COLORS["purple"],
    "PNS": COLORS["teal"],
    "IFRC Secretariat": COLORS["navy"],
}
THEME_COLORS = {
    "SP1": "#9B6AAE",
    "SP2": "#5CB8B2",
    "SP3": "#4B9CD3",
    "SP4": "#F2C94C",
    "SP5": "#F58220",
    "EFs": COLORS["grey"],
    "EAs": COLORS["red"],
    "Total": "#6B7280",
}


def build_global_plan_views(payload: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    labels = analysis_labels()
    return {section: build_global_plan_view(payload, section, labels) for section in SECTION_IDS}


def build_global_plan_view(
    payload: Mapping[str, Any] | None,
    section: str = "overview",
    labels: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    labels = labels or analysis_labels()
    view: dict[str, Any] = {
        "section": section,
        "title": labels.get(f"gp_section_{section}", labels["gp_title"]),
        "lead": labels.get(f"gp_lead_{section}", labels["gp_lead"]),
        "kpis": [],
        "visuals": [],
        "notes": [],
        "warnings": [],
        "has_data": False,
    }
    if not payload or not payload.get("has_data"):
        return view

    year = payload.get("year")
    area_labels = dict(payload.get("area_labels") or {})
    if labels.get("gp_theme_total"):
        area_labels["Total"] = labels["gp_theme_total"]
    view["has_data"] = True
    builders = {
        "overview": _overview,
        "secretariat": _secretariat,
        "pns": _pns,
        "yearly": _yearly,
        "regional": _regional,
        "divisional": _divisional,
        "geo": _geo,
        "people_reached": _people_reached,
        "emergencies": _emergencies,
        "countries": _countries,
        "prioritisation": _prioritisation,
    }
    builder = builders.get(section, _overview)
    kpis, visuals, notes = builder(payload, labels, year, area_labels)
    view["kpis"] = kpis
    view["visuals"] = visuals
    view["notes"] = notes
    return view


def _area_name(code: str, area_labels: Mapping[str, str]) -> str:
    return str(area_labels.get(code) or code)


def _kpi(kpi_id: str, label: str, value: Any, fmt: str, labels: Mapping[str, str], year: Any = None) -> dict[str, Any]:
    delta = {"latest": value, "latest_year": year} if year is not None else None
    return kpi(kpi_id, label, value, fmt, delta, labels)


def _compact_short(value: Any) -> str:
    """Bar/list labels like ``2.1 B`` / ``906.5 M``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number == 0:
        return "0"
    abs_n = abs(number)
    if abs_n >= 1_000_000_000:
        text = f"{number / 1_000_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{text} B"
    if abs_n >= 1_000_000:
        text = f"{number / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{text} M"
    if abs_n >= 1_000:
        return f"{int(round(number / 1_000))} K"
    return str(int(round(number)))


def _words_amount(value: Any) -> str:
    """Total / people callouts like ``3.4 billion`` / ``238 million``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    abs_n = abs(number)
    if abs_n >= 1_000_000_000:
        text = f"{number / 1_000_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{text} billion"
    if abs_n >= 1_000_000:
        text = f"{number / 1_000_000:.1f}".rstrip("0").rstrip(".")
        return f"{text} million"
    if abs_n >= 1_000:
        text = f"{number / 1_000:.1f}".rstrip("0").rstrip(".")
        return f"{text} thousand"
    return str(int(round(number)))


def _overview_hero(payload, labels, year) -> dict[str, Any]:
    funding = payload.get("funding") or {}
    reach = payload.get("reach") or {}
    selected = funding.get("selected_entity") or {}
    total = funding.get("selected_total")
    people = reach.get("selected_total")
    pns_providers = (payload.get("pns") or {}).get("providers") or (payload.get("pns") or {}).get("top_providers") or []
    rows = [
        {
            "id": "ifrc",
            "label": labels["gp_overview_ifrc"],
            "value": selected.get("IFRC Secretariat"),
            "display": _compact_short(selected.get("IFRC Secretariat")),
            "color": "#E30613",
        },
        {
            "id": "hns",
            "label": labels["gp_overview_hns"],
            "value": selected.get("HNS"),
            "display": _compact_short(selected.get("HNS")),
            "color": "#6B4C9A",
        },
        {
            "id": "pns",
            "label": labels["gp_overview_pns"],
            "value": selected.get("PNS"),
            "display": _compact_short(selected.get("PNS")),
            "color": "#C4A35A",
        },
    ]
    table_rows = [
        table_row([labels["gp_overview_ifrc"], selected.get("IFRC Secretariat")]),
        table_row([labels["gp_overview_hns"], selected.get("HNS")]),
        table_row(
            [labels["gp_overview_pns"], selected.get("PNS")],
            country_rows([[r.get("name"), r.get("value")] for r in pns_providers]),
        ),
        table_row([labels["gp_col_total"], total]),
    ]
    return visual(
        "gp_overview_hero",
        fill(labels["gp_overview_title"], year=year or ""),
        fill(labels["gp_overview_hint"], year=year or ""),
        kind="overview",
        wide=True,
        overview={
            "year": year,
            "total": total,
            "total_display": _words_amount(total),
            "total_caption": fill(labels["gp_overview_total_caption"], year=year or ""),
            "people": people,
            "people_display": _words_amount(people),
            "people_caption": labels["gp_overview_people_caption"],
            "rows": rows,
        },
        table=table(
            fill(labels["gp_overview_title"], year=year or ""),
            [labels["gp_col_group"], labels["gp_col_fr"]],
            table_rows,
            note=labels.get("gp_overview_table_note") or "",
        ),
    )


def _overview(payload, labels, year, area_labels):
    funding = payload.get("funding") or {}
    reach = payload.get("reach") or {}
    overlay_year = ((payload.get("overlay") or {}).get("year") or {})
    kpis = [
        _kpi("gp_countries", labels["gp_kpi_countries"], payload.get("countries_submitting"), "int", labels, year),
    ]
    if overlay_year.get("special_purpose_funds") is not None:
        kpis.append(
            _kpi("gp_spf", labels["gp_kpi_spf"], overlay_year.get("special_purpose_funds"), "money", labels, year)
        )
    if overlay_year.get("new_emergency_appeals_estimate") is not None:
        kpis.append(
            _kpi(
                "gp_ea_est",
                labels["gp_kpi_ea_estimate"],
                overlay_year.get("new_emergency_appeals_estimate"),
                "money",
                labels,
                year,
            )
        )

    hero = _overview_hero(payload, labels, year)

    themes = [c for c in THEME_CODES if (funding.get("selected_theme") or {}).get(c)]
    if not themes:
        themes = list(THEME_CODES)
    by_te = {
        (row.get("key"), area): row.get(area)
        for row in funding.get("by_theme_entity") or []
        if row.get("year") == year
        for area in THEME_CODES
    }
    entity_series = [
        series(
            ent,
            [by_te.get((ent, area)) for area in themes],
            kind="column",
            color=ENTITY_COLORS.get(ent, COLORS["grey"]),
            fmt="money",
        )
        for ent in payload.get("entity_order") or []
    ]

    fr_visual = visual(
        "gp_fr_entity_theme",
        fill(labels["gp_fr_entity_theme_title"], year=year or ""),
        labels["gp_fr_entity_theme_hint"],
        chart=chart(
            [_area_name(a, area_labels) for a in themes],
            entity_series,
            axes={"primary": axis("money")},
            stacked=True,
            height=340,
        ),
        table=table(
            fill(labels["gp_fr_entity_theme_title"], year=year or ""),
            [labels["gp_col_theme"], *list(payload.get("entity_order") or [])],
            plain_rows(
                [
                    [
                        _area_name(area, area_labels),
                        *[by_te.get((ent, area)) for ent in (payload.get("entity_order") or [])],
                    ]
                    for area in themes
                ]
            ),
        ),
    )

    reach_theme = reach.get("selected_theme") or {}
    reach_codes = [c for c in THEME_CODES if reach_theme.get(c)] or list(THEME_CODES)
    reach_visual = visual(
        "gp_reach_theme",
        fill(labels["gp_reach_theme_title"], year=year or ""),
        labels["gp_reach_theme_hint"],
        chart=chart(
            [_area_name(a, area_labels) for a in reach_codes],
            [
                series(
                    labels["gp_kpi_reach"],
                    [reach_theme.get(a) for a in reach_codes],
                    kind="column",
                    color=COLORS["teal"],
                    fmt="int",
                )
            ],
            axes={"primary": axis("int")},
        ),
        table=table(
            fill(labels["gp_reach_theme_title"], year=year or ""),
            [labels["gp_col_theme"], labels["gp_kpi_reach"]],
            plain_rows([[_area_name(a, area_labels), reach_theme.get(a)] for a in reach_codes]),
        ),
    )

    nsif_share = (payload.get("secretariat") or {}).get("nsif_share") or {}
    submit_visual = visual(
        "gp_submit_priority",
        labels["gp_submit_title"],
        labels["gp_submit_hint"],
        chart=chart(
            [labels["gp_nsif"], labels["gp_other"]],
            [
                series(
                    labels["gp_kpi_countries"],
                    [
                        sum(1 for c in payload.get("countries") or [] if c.get("nsif") and c.get("plan_submitted")),
                        sum(1 for c in payload.get("countries") or [] if not c.get("nsif") and c.get("plan_submitted")),
                    ],
                    kind="column",
                    color=COLORS["navy"],
                    fmt="int",
                )
            ],
            axes={"primary": axis("int")},
            legend=False,
            height=260,
        ),
        table=table(
            labels["gp_submit_title"],
            [labels["gp_col_group"], labels["gp_kpi_countries"], labels["gp_col_fr"]],
            plain_rows(
                [
                    [labels["gp_nsif"], None, nsif_share.get("nsif")],
                    [labels["gp_other"], None, nsif_share.get("other")],
                ]
            ),
        ),
    )

    notes = [labels["gp_note_live"], labels["gp_note_round_year"]]
    if overlay_year.get("use_manual_ea_rollover"):
        notes.append(labels["gp_note_emergencies"])
    if overlay_year.get("note"):
        notes.append(str(overlay_year["note"]))
    return kpis, [hero, fr_visual, reach_visual, submit_visual], notes


def _secretariat(payload, labels, year, area_labels):
    sec = payload.get("secretariat") or {}
    by_theme = sec.get("by_theme") or {}
    themes = [c for c in THEME_CODES if by_theme.get(c)] or list(THEME_CODES)
    share = sec.get("nsif_share") or {}
    kpis = [
        _kpi("sec_total", labels["gp_kpi_secretariat"], sec.get("total"), "money", labels, year),
        _kpi("sec_nsif", labels["gp_kpi_nsif_fr"], share.get("nsif"), "money", labels, year),
        _kpi("sec_other", labels["gp_kpi_other_fr"], share.get("other"), "money", labels, year),
    ]
    theme_visual = visual(
        "gp_sec_theme",
        fill(labels["gp_sec_theme_title"], year=year or ""),
        labels["gp_sec_theme_hint"],
        chart=chart(
            [_area_name(a, area_labels) for a in themes],
            [
                series(
                    labels["gp_kpi_secretariat"],
                    [by_theme.get(a) for a in themes],
                    kind="column",
                    color=COLORS["navy"],
                    fmt="money",
                )
            ],
            axes={"primary": axis("money")},
        ),
        table=table(
            fill(labels["gp_sec_theme_title"], year=year or ""),
            [labels["gp_col_theme"], labels["gp_col_fr"]],
            plain_rows([[_area_name(a, area_labels), by_theme.get(a)] for a in themes]),
        ),
    )
    top = sec.get("top_recipients") or []
    top_visual = visual(
        "gp_sec_top",
        labels["gp_sec_top_title"],
        labels["gp_sec_top_hint"],
        chart=chart(
            [r.get("country") for r in top[:12]],
            [
                series(
                    labels["gp_col_fr"],
                    [r.get("value") for r in top[:12]],
                    kind="column",
                    color=COLORS["red"],
                    fmt="money",
                )
            ],
            axes={"primary": axis("money")},
            legend=False,
            horizontal=True,
            height=320,
        ),
        table=table(
            labels["gp_sec_top_title"],
            [labels["gp_col_country"], labels["gp_col_fr"], labels["gp_nsif"]],
            plain_rows([[r.get("country"), r.get("value"), labels["gp_yes"] if r.get("nsif") else labels["gp_no"]] for r in top]),
        ),
    )
    share_visual = visual(
        "gp_sec_share",
        labels["gp_sec_share_title"],
        labels["gp_sec_share_hint"],
        chart=chart(
            [labels["gp_nsif"], labels["gp_other"]],
            [
                series(
                    labels["gp_col_fr"],
                    [share.get("nsif"), share.get("other")],
                    kind="column",
                    color=COLORS["amber"],
                    fmt="money",
                )
            ],
            axes={"primary": axis("money")},
            legend=False,
            height=260,
        ),
    )
    return kpis, [theme_visual, top_visual, share_visual], [labels["gp_note_live"]]


def _pns(payload, labels, year, area_labels):
    pns = payload.get("pns") or {}
    kpis = [
        _kpi("pns_providers", labels["gp_kpi_pns_providers"], pns.get("provider_count"), "int", labels, year),
        _kpi("pns_recipients", labels["gp_kpi_pns_recipients"], pns.get("recipient_count"), "int", labels, year),
    ]
    providers = pns.get("providers") or pns.get("top_providers") or []
    chart_providers = pns.get("top_providers") or providers[:15]
    recipients = pns.get("top_recipients") or []
    provider_visual = visual(
        "gp_pns_providers",
        labels["gp_pns_providers_title"],
        labels["gp_pns_providers_hint"],
        chart=chart(
            [r.get("name") for r in chart_providers[:12]],
            [
                series(
                    labels["gp_col_fr"],
                    [r.get("value") for r in chart_providers[:12]],
                    kind="column",
                    color=COLORS["teal"],
                    fmt="money",
                )
            ],
            axes={"primary": axis("money")},
            legend=False,
            horizontal=True,
            height=320,
        ),
        table=table(
            labels["gp_pns_providers_title"],
            [labels["gp_col_pns"], labels["gp_col_fr"]],
            plain_rows([[r.get("name"), r.get("value")] for r in providers]),
            note=labels.get("gp_pns_providers_table_note") or "",
        ),
    )
    recipient_visual = visual(
        "gp_pns_recipients",
        labels["gp_pns_recipients_title"],
        labels["gp_pns_recipients_hint"],
        chart=chart(
            [r.get("country") for r in recipients[:12]],
            [
                series(
                    labels["gp_col_fr"],
                    [r.get("value") for r in recipients[:12]],
                    kind="column",
                    color=COLORS["purple"],
                    fmt="money",
                )
            ],
            axes={"primary": axis("money")},
            legend=False,
            horizontal=True,
            height=320,
        ),
        table=table(
            labels["gp_pns_recipients_title"],
            [labels["gp_col_country"], labels["gp_col_fr"], labels["gp_nsif"]],
            plain_rows(
                [[r.get("country"), r.get("value"), labels["gp_yes"] if r.get("nsif") else labels["gp_no"]] for r in recipients]
            ),
        ),
    )
    return kpis, [provider_visual, recipient_visual], [labels["gp_note_live"]]


def _yearly(payload, labels, year, area_labels):
    funding = payload.get("funding") or {}
    by_year = funding.get("by_theme_year") or []
    years = [r.get("year") for r in by_year]
    theme_series = []
    for area in THEME_CODES:
        theme_series.append(
            series(
                _area_name(area, area_labels),
                [r.get(area) for r in by_year],
                kind="column",
                color=THEME_COLORS.get(area, COLORS["grey"]),
                fmt="money",
            )
        )
    entity_year = funding.get("by_entity_year") or []
    entity_series = [
        series(
            ent,
            [r.get(ent) for r in entity_year],
            kind="line",
            color=ENTITY_COLORS.get(ent, COLORS["grey"]),
            fmt="money",
        )
        for ent in payload.get("entity_order") or []
    ]
    kpis = [
        _kpi("yr_total", labels["gp_kpi_total_fr"], funding.get("selected_total"), "money", labels, year),
    ]
    theme_visual = visual(
        "gp_yearly_theme",
        labels["gp_yearly_theme_title"],
        labels["gp_yearly_theme_hint"],
        chart=chart(years, theme_series, axes={"primary": axis("money")}, stacked=True, height=340),
        table=table(
            labels["gp_yearly_theme_title"],
            [labels["year"], *[_area_name(a, area_labels) for a in THEME_CODES]],
            plain_rows([[r.get("year"), *[r.get(a) for a in THEME_CODES]] for r in by_year]),
        ),
    )
    entity_visual = visual(
        "gp_yearly_entity",
        labels["gp_yearly_entity_title"],
        labels["gp_yearly_entity_hint"],
        chart=chart(
            [r.get("year") for r in entity_year],
            entity_series,
            axes={"primary": axis("money")},
            height=300,
        ),
        table=table(
            labels["gp_yearly_entity_title"],
            [labels["year"], *(payload.get("entity_order") or []), labels["gp_col_total"]],
            plain_rows(
                [[r.get("year"), *[r.get(e) for e in (payload.get("entity_order") or [])], r.get("total")] for r in entity_year]
            ),
        ),
    )
    return kpis, [theme_visual, entity_visual], [labels["gp_note_live"]]


def _regional(payload, labels, year, area_labels):
    rows = [
        r
        for r in ((payload.get("funding") or {}).get("by_theme_region") or [])
        if r.get("year") == year
    ]
    regions = [r.get("key") for r in rows]
    kpis = [_kpi("reg_count", labels["gp_kpi_regions"], len(regions), "int", labels, year)]
    series_list = []
    for area in THEME_CODES:
        if any(r.get(area) for r in rows):
            series_list.append(
                series(
                    _area_name(area, area_labels),
                    [r.get(area) for r in rows],
                    kind="column",
                    color=THEME_COLORS.get(area, COLORS["grey"]),
                    fmt="money",
                )
            )
    visual_chart = visual(
        "gp_regional_theme",
        fill(labels["gp_regional_title"], year=year or ""),
        labels["gp_regional_hint"],
        chart=chart(regions, series_list, axes={"primary": axis("money")}, stacked=True, height=340)
        if regions
        else chart([], [], axes={"primary": axis("money")}),
        table=table(
            fill(labels["gp_regional_title"], year=year or ""),
            [labels["gp_col_region"], *[_area_name(a, area_labels) for a in THEME_CODES], labels["gp_col_total"]],
            plain_rows(
                [
                    [
                        r.get("key"),
                        *[r.get(a) for a in THEME_CODES],
                        sum(float(r.get(a) or 0) for a in THEME_CODES),
                    ]
                    for r in rows
                ]
            ),
        ),
    )
    return kpis, [visual_chart], [labels["gp_note_live"]]


def _divisional(payload, labels, year, area_labels):
    divisions = (payload.get("overlay") or {}).get("divisions") or []
    by_div: dict[str, float] = {}
    for row in divisions:
        name = str(row.get("division") or "").strip()
        if not name:
            continue
        by_div[name] = by_div.get(name, 0.0) + float(row.get("value") or 0)
    names = sorted(by_div, key=lambda n: (-by_div[n], n.lower()))
    kpis = [
        _kpi("div_total", labels["gp_kpi_divisional"], sum(by_div.values()) or None, "money", labels, year),
        _kpi("div_count", labels["gp_kpi_divisions"], len(names) or None, "int", labels, year),
    ]
    visual_chart = visual(
        "gp_divisional",
        fill(labels["gp_divisional_title"], year=year or ""),
        labels["gp_divisional_hint"],
        chart=chart(
            names,
            [
                series(
                    labels["gp_col_fr"],
                    [by_div[n] for n in names],
                    kind="column",
                    color=COLORS["navy"],
                    fmt="money",
                )
            ],
            axes={"primary": axis("money")},
            legend=False,
            horizontal=True,
            height=320,
        )
        if names
        else chart([], [], axes={"primary": axis("money")}),
        table=table(
            fill(labels["gp_divisional_title"], year=year or ""),
            [labels["gp_col_division"], labels["gp_col_department"], labels["gp_col_theme"], labels["gp_col_fr"]],
            plain_rows(
                [
                    [
                        d.get("division"),
                        d.get("department"),
                        _area_name(str(d.get("area") or ""), area_labels),
                        d.get("value"),
                    ]
                    for d in divisions
                ]
            ),
        ),
    )
    notes = [labels["gp_note_divisional"]]
    if not divisions:
        notes.append(labels["gp_note_divisional_empty"])
    return kpis, [visual_chart], notes


def _geo(payload, labels, year, area_labels):
    rows = [
        r
        for r in ((payload.get("funding") or {}).get("by_theme_region") or [])
        if r.get("year") == year
    ]
    nsif_countries = sorted(
        (c for c in payload.get("countries") or [] if c.get("nsif") and c.get("total")),
        key=lambda c: (-float(c.get("total") or 0), str(c.get("country")).lower()),
    )[:10]
    kpis = [
        _kpi("geo_nsif", labels["gp_kpi_nsif_countries"], len([c for c in payload.get("countries") or [] if c.get("nsif")]), "int", labels, year),
    ]
    regional = visual(
        "gp_geo_region",
        fill(labels["gp_geo_title"], year=year or ""),
        labels["gp_geo_hint"],
        chart=chart(
            [r.get("key") for r in rows],
            [
                series(
                    _area_name(area, area_labels),
                    [r.get(area) for r in rows],
                    kind="column",
                    color=THEME_COLORS.get(area, COLORS["grey"]),
                    fmt="money",
                )
                for area in THEME_CODES
                if any(r.get(area) for r in rows)
            ],
            axes={"primary": axis("money")},
            stacked=True,
            height=340,
        )
        if rows
        else chart([], [], axes={"primary": axis("money")}),
        table=table(
            fill(labels["gp_geo_title"], year=year or ""),
            [labels["gp_col_region"], *[_area_name(a, area_labels) for a in THEME_CODES]],
            plain_rows([[r.get("key"), *[r.get(a) for a in THEME_CODES]] for r in rows]),
        ),
    )
    nsif_visual = visual(
        "gp_geo_nsif",
        labels["gp_geo_nsif_title"],
        labels["gp_geo_nsif_hint"],
        chart=chart(
            [c.get("country") for c in nsif_countries],
            [
                series(
                    labels["gp_col_fr"],
                    [c.get("total") for c in nsif_countries],
                    kind="column",
                    color=COLORS["red"],
                    fmt="money",
                )
            ],
            axes={"primary": axis("money")},
            legend=False,
            horizontal=True,
            height=300,
        ),
        table=table(
            labels["gp_geo_nsif_title"],
            [labels["gp_col_country"], labels["gp_col_region"], labels["gp_col_fr"]],
            plain_rows([[c.get("country"), c.get("region"), c.get("total")] for c in nsif_countries]),
        ),
    )
    return kpis, [regional, nsif_visual], [labels["gp_note_live"]]


def _people_reached(payload, labels, year, area_labels):
    reach = payload.get("reach") or {}
    selected = reach.get("selected_theme") or {}
    codes = [c for c in THEME_CODES if selected.get(c)] or list(THEME_CODES)
    rows = [r for r in reach.get("by_theme_region") or [] if r.get("year") == year]
    kpis = [_kpi("reach_total", labels["gp_kpi_reach"], reach.get("selected_total"), "int", labels, year)]
    theme_visual = visual(
        "gp_people_theme",
        fill(labels["gp_people_theme_title"], year=year or ""),
        labels["gp_people_theme_hint"],
        chart=chart(
            [_area_name(a, area_labels) for a in codes],
            [
                series(
                    labels["gp_kpi_reach"],
                    [selected.get(a) for a in codes],
                    kind="column",
                    color=COLORS["teal"],
                    fmt="int",
                )
            ],
            axes={"primary": axis("int")},
            legend=False,
        ),
        table=table(
            fill(labels["gp_people_theme_title"], year=year or ""),
            [labels["gp_col_theme"], labels["gp_kpi_reach"]],
            plain_rows([[_area_name(a, area_labels), selected.get(a)] for a in codes]),
        ),
    )
    region_visual = visual(
        "gp_people_region",
        fill(labels["gp_people_region_title"], year=year or ""),
        labels["gp_people_region_hint"],
        chart=chart(
            [r.get("key") for r in rows],
            [
                series(
                    _area_name(area, area_labels),
                    [r.get(area) for r in rows],
                    kind="column",
                    color=THEME_COLORS.get(area, COLORS["grey"]),
                    fmt="int",
                )
                for area in THEME_CODES
                if any(r.get(area) for r in rows)
            ],
            axes={"primary": axis("int")},
            stacked=True,
            height=320,
        )
        if rows
        else chart([], [], axes={"primary": axis("int")}),
        table=table(
            fill(labels["gp_people_region_title"], year=year or ""),
            [labels["gp_col_region"], *[_area_name(a, area_labels) for a in THEME_CODES]],
            plain_rows([[r.get("key"), *[r.get(a) for a in THEME_CODES]] for r in rows]),
        ),
    )
    return kpis, [theme_visual, region_visual], [labels["gp_note_live"]]


def _emergencies(payload, labels, year, area_labels):
    overlay = payload.get("overlay") or {}
    appeals = overlay.get("appeals") or []
    year_block = overlay.get("year") or {}
    ea_theme = ((payload.get("funding") or {}).get("selected_theme") or {}).get("EAs")
    kpis = [
        _kpi("ea_plan", labels["gp_kpi_ea_plan"], ea_theme, "money", labels, year),
        _kpi("ea_sprm", labels["gp_kpi_ea_sprm"], payload.get("eas_sprm_total"), "money", labels, year),
        _kpi(
            "ea_est",
            labels["gp_kpi_ea_estimate"],
            year_block.get("new_emergency_appeals_estimate"),
            "money",
            labels,
            year,
        ),
        _kpi("ea_appeals", labels["gp_kpi_appeals"], len(appeals) or None, "int", labels, year),
    ]
    if year_block.get("use_manual_ea_rollover"):
        kpis.insert(
            1,
            _kpi(
                "ea_rollover",
                labels["gp_kpi_ea_rollover"],
                year_block.get("emergency_appeals_rollover"),
                "money",
                labels,
                year,
            ),
        )
    appeal_visual = visual(
        "gp_appeals",
        labels["gp_appeals_title"],
        labels["gp_appeals_hint"],
        chart=chart(
            [a.get("name") or a.get("country") or a.get("iso3") for a in appeals[:15]],
            [
                series(
                    labels["gp_col_requested"],
                    [a.get("amount_requested") for a in appeals[:15]],
                    kind="column",
                    color=COLORS["navy"],
                    fmt="money",
                ),
                series(
                    labels["gp_col_funded"],
                    [a.get("amount_funded") for a in appeals[:15]],
                    kind="column",
                    color=COLORS["green"],
                    fmt="money",
                ),
            ],
            axes={"primary": axis("money")},
            height=320,
        )
        if appeals
        else chart([], [], axes={"primary": axis("money")}),
        table=table(
            labels["gp_appeals_title"],
            [
                labels["gp_col_appeal"],
                labels["gp_col_country"],
                labels["gp_col_region"],
                labels["gp_col_requested"],
                labels["gp_col_funded"],
            ],
            plain_rows(
                [
                    [
                        a.get("name"),
                        a.get("country") or a.get("iso3"),
                        a.get("region"),
                        a.get("amount_requested"),
                        a.get("amount_funded"),
                    ]
                    for a in appeals
                ]
            ),
        ),
    )
    notes = [labels["gp_note_emergencies"]]
    return kpis, [appeal_visual], notes


def _countries(payload, labels, year, area_labels):
    rows = payload.get("countries") or []
    kpis = [
        _kpi("c_submit", labels["gp_kpi_countries"], payload.get("countries_submitting"), "int", labels, year),
        _kpi("c_fr", labels["gp_kpi_countries_fr"], payload.get("countries_with_fr"), "int", labels, year),
        _kpi("c_nsif", labels["gp_kpi_nsif_countries"], sum(1 for r in rows if r.get("nsif")), "int", labels, year),
    ]
    visual_table = visual(
        "gp_countries",
        labels["gp_countries_title"],
        labels["gp_countries_hint"],
        wide=True,
        kind="chart",
        chart=chart(
            [r.get("country") for r in rows[:20]],
            [
                series(
                    labels["gp_col_fr"],
                    [r.get("total") for r in rows[:20]],
                    kind="column",
                    color=COLORS["navy"],
                    fmt="money",
                )
            ],
            axes={"primary": axis("money")},
            legend=False,
            horizontal=True,
            height=300,
        ),
        table=table(
            labels["gp_countries_title"],
            [
                labels["gp_col_country"],
                labels["gp_col_region"],
                labels["gp_nsif"],
                labels["gp_oda"],
                labels["gp_col_inform"],
                labels["gp_col_submitted"],
                labels["gp_col_fr"],
            ],
            plain_rows(
                [
                    [
                        r.get("country"),
                        r.get("region"),
                        labels["gp_yes"] if r.get("nsif") else labels["gp_no"],
                        labels["gp_yes"] if r.get("oda") else labels["gp_no"],
                        r.get("inform"),
                        labels["gp_yes"] if r.get("plan_submitted") else labels["gp_no"],
                        r.get("total"),
                    ]
                    for r in rows
                ]
            ),
        ),
    )
    return kpis, [visual_table], [labels["gp_note_categories"]]


def _prioritisation(payload, labels, year, area_labels):
    prio = payload.get("prioritisation") or {}
    rows = prio.get("rows") or []
    groups = prio.get("group_counts") or []
    flags = prio.get("flag_counts") or {}
    kpis = [
        _kpi("pr_eligible", labels["gp_kpi_eligible"], prio.get("eligible"), "int", labels, year),
        _kpi("pr_part", labels["gp_kpi_participation"], prio.get("participation_up"), "int", labels, year),
        _kpi(
            "pr_pns",
            labels["gp_kpi_pns_among"],
            prio.get("pns_among_participants"),
            "int",
            labels,
            year,
        ),
        _kpi(
            "pr_pns_pct",
            labels["gp_kpi_pns_among_pct"],
            prio.get("pns_among_participants_pct"),
            "pct",
            labels,
            year,
        ),
    ]
    group_visual = visual(
        "gp_prio_groups",
        labels["gp_prio_groups_title"],
        labels["gp_prio_groups_hint"],
        chart=chart(
            [g.get("group") for g in groups],
            [
                series(
                    labels["gp_kpi_countries"],
                    [g.get("count") for g in groups],
                    kind="column",
                    color=COLORS["teal"],
                    fmt="int",
                )
            ],
            axes={"primary": axis("int")},
            legend=False,
            height=280,
        ),
        table=table(
            labels["gp_prio_groups_title"],
            [labels["gp_col_group"], labels["gp_kpi_countries"]],
            plain_rows([[g.get("group"), g.get("count")] for g in groups]),
        ),
    )
    flag_visual = visual(
        "gp_prio_flags",
        labels["gp_prio_flags_title"],
        labels["gp_prio_flags_hint"],
        chart=chart(
            [
                labels["gp_flag_inform"],
                labels["gp_oda"],
                labels["gp_nsif"],
                labels["gp_flag_large"],
                labels["gp_flag_pns"],
            ],
            [
                series(
                    labels["gp_kpi_countries"],
                    [
                        flags.get("inform"),
                        flags.get("oda"),
                        flags.get("nsif"),
                        flags.get("large_emergency"),
                        flags.get("pns"),
                    ],
                    kind="column",
                    color=COLORS["amber"],
                    fmt="int",
                )
            ],
            axes={"primary": axis("int")},
            legend=False,
            height=280,
        ),
    )
    table_visual = visual(
        "gp_prio_table",
        labels["gp_prio_table_title"],
        labels["gp_prio_table_hint"],
        wide=True,
        chart=chart(
            [r.get("country") for r in rows[:20]],
            [
                series(
                    labels["gp_col_score"],
                    [r.get("prioritisation_score") for r in rows[:20]],
                    kind="column",
                    color=COLORS["navy"],
                    fmt="int",
                )
            ],
            axes={"primary": axis("int")},
            legend=False,
            horizontal=True,
            height=300,
        ),
        table=table(
            labels["gp_prio_table_title"],
            [
                labels["gp_col_country"],
                labels["gp_col_region"],
                labels["gp_col_score"],
                labels["gp_col_group"],
                labels["gp_col_inform"],
                labels["gp_oda"],
                labels["gp_nsif"],
                labels["gp_flag_large"],
                labels["gp_flag_pns"],
                labels["gp_col_submitted"],
            ],
            plain_rows(
                [
                    [
                        r.get("country"),
                        r.get("region"),
                        r.get("prioritisation_score"),
                        r.get("prioritisation_group"),
                        r.get("inform"),
                        labels["gp_yes"] if r.get("oda") else labels["gp_no"],
                        labels["gp_yes"] if r.get("nsif") else labels["gp_no"],
                        labels["gp_yes"] if r.get("large_emergency") else labels["gp_no"],
                        labels["gp_yes"] if r.get("pns") else labels["gp_no"],
                        labels["gp_yes"] if r.get("participation_up") else labels["gp_no"],
                    ]
                    for r in rows
                ]
            ),
        ),
    )
    return kpis, [group_visual, flag_visual, table_visual], [labels["gp_note_prioritisation"]]
