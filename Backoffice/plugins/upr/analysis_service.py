"""Entry points that produce the Analysis for any consumer.

The Analysis tab, a PDF export and a presentation all call these, so they get
the same payloads and the same views. Views are text, so build them inside
``flask_babel.force_locale(...)`` to export in another language.
"""

from __future__ import annotations

from typing import Any

from plugins.upr.impact import build_upr_impact
from plugins.upr.impact_views import build_impact_view
from plugins.upr.narrative import build_narrative_participation
from plugins.upr.narrative_views import build_narrative_views


def build_impact_analysis(*, region: str | None = None) -> dict[str, Any]:
    """Data section: raw series and the renderer-independent view."""
    payload = build_upr_impact(region=region)
    return {"payload": payload, "view": build_impact_view(payload)}


def build_narrative_analysis(*, region: str | None = None) -> dict[str, Any]:
    """Participation section: raw series and one view per round type."""
    payload = build_narrative_participation(region=region)
    return {"payload": payload, "views": build_narrative_views(payload)}


def build_analysis_bundle(*, region: str | None = None) -> dict[str, Any]:
    """Everything an export needs for one region (or the whole network)."""
    return {
        "region": region,
        "impact": build_impact_analysis(region=region),
        "narrative": build_narrative_analysis(region=region),
    }
