"""Entry points that produce the Analysis for any consumer.

The Analysis tab, a PDF export and a presentation all call these, so they get
the same payloads and the same views. Views are text, so build them inside
``flask_babel.force_locale(...)`` to export in another language.
"""

from __future__ import annotations

from typing import Any

from plugins.upr.analysis.global_plan import build_upr_global_plan
from plugins.upr.analysis.global_plan_views import build_global_plan_views
from plugins.upr.analysis.analysis_data import build_upr_analysis
from plugins.upr.analysis.analysis_views import build_analysis_view
from plugins.upr.analysis.narrative import build_narrative_participation
from plugins.upr.analysis.narrative_views import build_narrative_views


def build_data_analysis(*, region: str | None = None) -> dict[str, Any]:
    """Data section: raw series and the renderer-independent view."""
    payload = build_upr_analysis(region=region)
    return {"payload": payload, "view": build_analysis_view(payload)}


def build_narrative_analysis(*, region: str | None = None) -> dict[str, Any]:
    """Participation section: raw series and one view per round type."""
    payload = build_narrative_participation(region=region)
    return {"payload": payload, "views": build_narrative_views(payload)}


def build_global_plan_analysis(
    *, region: str | None = None, year: int | None = None
) -> dict[str, Any]:
    """Global Plan section: raw series and one view per dashboard section."""
    payload = build_upr_global_plan(region=region, year=year)
    return {"payload": payload, "views": build_global_plan_views(payload)}


def build_analysis_bundle(
    *, region: str | None = None, year: int | None = None
) -> dict[str, Any]:
    """Everything an export needs for one region (or the whole network)."""
    return {
        "region": region,
        "year": year,
        "data": build_data_analysis(region=region),
        "narrative": build_narrative_analysis(region=region),
        "global_plan": build_global_plan_analysis(region=region, year=year),
    }
