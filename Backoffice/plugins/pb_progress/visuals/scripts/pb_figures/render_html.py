"""Render publication-quality dashboards via Python HTML/SVG + WeasyPrint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import resolve_report_dir
from .html_raster import render_dashboard_png
from .payload import build_payload
from .report_meta import report_section_assets_dir, report_section_assets_ref
from .render_embed import build_section_embed


def _embed_dashboard_height(payload: dict[str, Any]) -> int:
    """Estimate pixel height for dashboard PNG rasterization."""
    base = 130
    for item in payload["cumulative"]:
        if item.get("unavailable"):
            base += 96
        elif item.get("ns_table_mode") in {"implementing_count", "ns_unit"}:
            base += 130
        elif item.get("show_ns_breakdown") is False:
            base += 119
        else:
            base += 155
    for _pair in payload.get("donut_pairs", []):
        base += 90
    for _item in payload.get("donuts", []):
        base += 90
    return max(base, 400)


# Backward-compatible alias used by tests and legacy callers.
_dashboard_height = _embed_dashboard_height


def render_dashboard_html(
    model,
    section: str,
    *,
    language: str = "English",
    output_path: Path | None = None,
    scale: float = 2.0,
    session=None,
    mapping=None,
    render_assets: bool = True,
) -> Path:
    """Render dashboard to PNG using the same HTML embed path as the Quarto report."""
    del session  # kept for caller compatibility during migration

    if output_path is None:
        raise ValueError("output_path is required for HTML renderer")

    report_root = resolve_report_dir()
    assets_dir = report_section_assets_dir(report_root, language, section)
    asset_prefix = report_section_assets_ref(language, section)
    payload = build_payload(model, section, language, mapping=mapping)

    dashboard_html = build_section_embed(
        model,
        section,
        language=language,
        assets_dir=assets_dir,
        asset_url_prefix=asset_prefix,
        render_assets=render_assets,
        mapping=mapping,
    )

    return render_dashboard_png(
        dashboard_html,
        Path(output_path),
        width=827,
        height=_embed_dashboard_height(payload),
        scale=scale,
        base_url=report_root,
        language=language,
    )


def render_dashboard_svg(
    model,
    section: str,
    *,
    language: str = "English",
    output_path: Path | None = None,
    mapping=None,
) -> Path:
    """Save standalone HTML preview alongside PNG."""
    del mapping
    report_root = resolve_report_dir()
    assets_dir = report_section_assets_dir(report_root, language, section)
    asset_prefix = report_section_assets_ref(language, section)

    dashboard_html = build_section_embed(
        model,
        section,
        language=language,
        assets_dir=assets_dir,
        asset_url_prefix=asset_prefix,
        render_assets=True,
    )
    if output_path is None:
        raise ValueError("output_path is required")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dashboard_html, encoding="utf-8")
    return output_path
