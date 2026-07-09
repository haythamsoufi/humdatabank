#!/usr/bin/env python3
"""Quarto pre-render hook: generate chart assets and report body (_body.qmd)."""

from __future__ import annotations

import html
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from gb_figures.config import DEFAULT_OUTPUT, build_workers, resolve_excel  # noqa: E402
from gb_figures.charts import render_dashboard  # noqa: E402
from gb_figures.data import build_model, load_sg_report  # noqa: E402
from gb_figures.languages import discover_languages, is_rtl  # noqa: E402
from gb_figures.layouts import SECTION_CODES  # noqa: E402
from gb_figures.payload import build_payload  # noqa: E402
from gb_figures.render_embed import build_section_embed, render_section_assets  # noqa: E402
from gb_figures.render_html import PlaywrightScreenshotSession  # noqa: E402
from gb_figures.report_meta import (  # noqa: E402
    load_model,
    report_parts,
    report_section_assets_dir,
    report_section_assets_ref,
    section_titles,
)


def _resolve_languages(excel: Path) -> tuple[str, ...]:
    requested = os.environ.get("GB_REPORT_LANGUAGE")
    if requested and requested.lower() not in ("all", "*"):
        return (requested,)
    return discover_languages(load_sg_report(excel)["mapping"])


def _render_language_assets(
    excel: Path,
    language: str,
    renderer: str,
) -> tuple[str, int, int, list[str]]:
    """Render all chart + dashboard assets for one language.

    Runs standalone (rebuilds its own model and opens its own Chromium instance)
    so it can be executed in a worker process alongside other languages.
    """
    model = build_model(excel)
    chart_total = 0
    dashboard_total = 0
    log_lines = [f"  [{language}]"]
    with PlaywrightScreenshotSession() as session:
        for section in SECTION_CODES:
            assets_dir = report_section_assets_dir(ROOT, language, section)
            payload = build_payload(model, section, language)
            refs = render_section_assets(
                payload, assets_dir, language=language, session=session,
            )
            label = f"({len(refs)} chart assets)" if refs else "(text-only)"
            log_lines.append(f"    {section}/ {label}")
            chart_total += len(refs)

            dash_path = DEFAULT_OUTPUT / language / f"{section}.png"
            render_dashboard(
                model,
                section,
                language=language,
                output_path=dash_path,
                renderer=renderer,
                session=session,
            )
            dashboard_total += 1
    log_lines.append("")
    return language, chart_total, dashboard_total, log_lines


def _generate_assets(excel: Path, languages: tuple[str, ...]) -> tuple[int, int]:
    """Render chart assets for HTML embed and full dashboard PNGs under Figures/.

    Languages are independent of one another, so they are farmed out to a pool
    of worker processes (each with its own Chromium instance) when there is
    more than one language to render.
    """
    chart_total = 0
    dashboard_total = 0
    renderer = os.environ.get("GB_FIGURES_RENDERER", "html")
    max_workers = build_workers(len(languages))

    if max_workers <= 1:
        for language in languages:
            _, charts, dashboards, log_lines = _render_language_assets(excel, language, renderer)
            chart_total += charts
            dashboard_total += dashboards
            for line in log_lines:
                print(line, flush=True)
        return chart_total, dashboard_total

    print(
        f"[pre_render] rendering {len(languages)} languages across "
        f"{max_workers} worker process(es)",
        flush=True,
    )
    results: dict[str, tuple[str, int, int, list[str]]] = {}
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_render_language_assets, excel, language, renderer): language
            for language in languages
        }
        for future in as_completed(futures):
            language = futures[future]
            results[language] = future.result()

    for language in languages:
        _, charts, dashboards, log_lines = results[language]
        chart_total += charts
        dashboard_total += dashboards
        for line in log_lines:
            print(line, flush=True)
    return chart_total, dashboard_total


def _part_anchor(part_id: str) -> str:
    return f"part-{part_id}"


def _section_anchor(section: str) -> str:
    return f"section-{section.lower()}"


def _render_language_panel(
    language: str,
    model,
    excel: Path,
    *,
    visible: bool = False,
) -> list[str]:
    titles = section_titles(model, language)
    direction = "rtl" if is_rtl(language) else "ltr"
    hidden_attr = "" if visible else " hidden"
    lines = [
        f'<div class="gb-lang-panel" data-lang="{html.escape(language)}" data-dir="{direction}"{hidden_attr}>',
    ]
    for part in report_parts(excel):
        part_title = part["title"].get(language, part["title"]["English"])
        lines.append('<section class="report-part">')
        lines.append(
            f'<h2 class="report-part-title" data-anchor="{_part_anchor(part["id"])}">'
            f"{html.escape(part_title)}</h2>"
        )
        for section in part["sections"]:
            heading = titles.get(section, section)
            lines.append('<section class="report-section">')
            lines.append(
                f'<h3 class="report-section-title" data-anchor="{_section_anchor(section)}">'
                f"{html.escape(heading)}</h3>"
            )
            assets_dir = report_section_assets_dir(ROOT, language, section)
            asset_prefix = report_section_assets_ref(language, section)
            dashboard_html = build_section_embed(
                model,
                section,
                language=language,
                assets_dir=assets_dir,
                asset_url_prefix=asset_prefix,
                render_assets=False,
            )
            lines.extend(['<div class="report-figure">', dashboard_html, "</div>", "</section>"])
        lines.append("</section>")
    lines.append("</div>")
    return lines


def _generate_body(output: Path, model, languages: tuple[str, ...], excel: Path) -> None:
    """Write _body.qmd with embedded dashboard HTML for all languages."""
    default_language = languages[0]
    lines: list[str] = [
        "```{=html}",
        f'<div id="gb-language-panels" data-default="{html.escape(default_language)}">',
    ]
    for language in languages:
        lines.extend(
            _render_language_panel(
                language, model, excel, visible=language == default_language,
            )
        )
    lines.extend([
        "</div>",
        "```",
    ])
    output.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"[pre_render] body: {output.name} ({len(languages)} languages: {', '.join(languages)})",
        flush=True,
    )


def main() -> None:
    excel = resolve_excel()
    languages = _resolve_languages(excel)
    model = build_model(excel)

    print(f"[pre_render] {excel.name} -> languages: {', '.join(languages)}", flush=True)

    chart_total, dashboard_total = _generate_assets(excel, languages)
    print(
        f"[pre_render] assets done: {chart_total} chart assets, "
        f"{dashboard_total} dashboard PNGs -> {DEFAULT_OUTPUT.name}/",
        flush=True,
    )

    _generate_body(ROOT / "report" / "_body.qmd", model, languages, excel)


if __name__ == "__main__":
    main()
