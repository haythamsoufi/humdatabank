#!/usr/bin/env python3
"""Quarto pre-render hook: generate chart assets and report body (_body.qmd)."""

from __future__ import annotations

import html
import json
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.config import build_workers, resolve_excel, resolve_figures_output, resolve_report_dir, resolve_report_output  # noqa: E402
from pb_figures.charts import render_dashboard  # noqa: E402
from pb_figures.data import build_model, load_mapping  # noqa: E402
from pb_figures.languages import is_rtl, resolve_build_languages  # noqa: E402
from pb_figures.layouts import section_codes, section_has_indicators  # noqa: E402
from pb_figures.payload import build_payload  # noqa: E402
from pb_figures.render_embed import build_section_embed, render_section_assets  # noqa: E402
from pb_figures.translations import clear_cache  # noqa: E402
from pb_figures.report_meta import (  # noqa: E402
    load_model,
    report_header_meta,
    report_parts,
    report_section_assets_dir,
    report_section_assets_ref,
    section_titles,
    section_uses_part_heading_only,
)

SectionJob = tuple[str, str, str]  # language, section, renderer

# Process pool state — one Excel model per worker process (initializer).
_pool_excel: Path | None = None
_pool_model = None
_pool_mapping = None


def _resolve_languages(excel: Path) -> tuple[str, ...]:
    return resolve_build_languages(excel)


def _clean_build_workspace(languages: tuple[str, ...]) -> None:
    """Drop stale figure/output files from prior builds in the writable workspace."""
    keep = set(languages)
    figures_dir = resolve_figures_output()
    if figures_dir.is_dir():
        for path in figures_dir.iterdir():
            if path.is_dir() and path.name not in keep:
                shutil.rmtree(path, ignore_errors=True)
    output_dir = resolve_report_output()
    if output_dir.is_dir():
        for path in output_dir.iterdir():
            if path.is_file():
                path.unlink(missing_ok=True)


def _section_jobs(
    excel: Path,
    languages: tuple[str, ...],
    mapping,
    renderer: str,
) -> list[SectionJob]:
    jobs: list[SectionJob] = []
    for language in languages:
        for section in section_codes(excel):
            if section_has_indicators(mapping, section):
                jobs.append((language, section, renderer))
    return jobs


def _render_section_job(
    excel: Path,
    language: str,
    section: str,
    renderer: str,
    mapping,
    *,
    model=None,
) -> tuple[str, str, int, int, list[str]]:
    """Render chart + dashboard assets for one language/section pair."""
    if model is None:
        model = build_model(excel)
    assets_dir = report_section_assets_dir(resolve_report_dir(), language, section)
    payload = build_payload(model, section, language, mapping=mapping)
    refs = render_section_assets(payload, assets_dir, language=language)
    label = f"({len(refs)} chart assets)" if refs else "(text-only)"
    log_lines = [f"    {section}/ {label}"]

    dash_path = resolve_figures_output() / language / f"{section}.png"
    render_dashboard(
        model,
        section,
        language=language,
        output_path=dash_path,
        renderer=renderer,
        mapping=mapping,
        render_assets=False,
    )
    return language, section, len(refs), 1, log_lines


def _init_render_pool(excel_path: str) -> None:
    """Load the Excel model once per worker process."""
    global _pool_excel, _pool_model, _pool_mapping
    _pool_excel = Path(excel_path)
    _pool_model = build_model(_pool_excel)
    _pool_mapping = load_mapping(_pool_excel)


def _render_section_job_pooled(job: SectionJob) -> tuple[str, str, int, int, list[str]]:
    language, section, renderer = job
    assert _pool_excel is not None and _pool_model is not None and _pool_mapping is not None
    return _render_section_job(
        _pool_excel,
        language,
        section,
        renderer,
        _pool_mapping,
        model=_pool_model,
    )


def _render_language_assets(
    excel: Path,
    language: str,
    renderer: str,
    mapping,
) -> tuple[str, int, int, list[str]]:
    """Render all chart + dashboard assets for one language (sequential sections)."""
    model = build_model(excel)
    chart_total = 0
    dashboard_total = 0
    log_lines = [f"  [{language}]"]
    for section in section_codes(excel):
        if not section_has_indicators(mapping, section):
            log_lines.append(f"    {section}/ (no indicators)")
            continue
        _, _, charts, dashboards, section_lines = _render_section_job(
            excel, language, section, renderer, mapping, model=model,
        )
        chart_total += charts
        dashboard_total += dashboards
        log_lines.extend(section_lines)
    log_lines.append("")
    return language, chart_total, dashboard_total, log_lines


def _print_section_results(
    languages: tuple[str, ...],
    results: dict[SectionJob, tuple[str, str, int, int, list[str]]],
    jobs: list[SectionJob],
) -> tuple[int, int]:
    chart_total = 0
    dashboard_total = 0
    for language in languages:
        print(f"  [{language}]", flush=True)
        language_jobs = [job for job in jobs if job[0] == language]
        for job in language_jobs:
            _, _, charts, dashboards, log_lines = results[job]
            chart_total += charts
            dashboard_total += dashboards
            for line in log_lines:
                print(line, flush=True)
        print("", flush=True)
    return chart_total, dashboard_total


def _generate_assets(excel: Path, languages: tuple[str, ...], mapping) -> tuple[int, int]:
    """Render chart assets for HTML embed and full dashboard PNGs under Figures/."""
    renderer = os.environ.get("PB_FIGURES_RENDERER", "html")
    jobs = _section_jobs(excel, languages, mapping, renderer)
    if not jobs:
        return 0, 0

    max_workers = build_workers(len(jobs))

    if max_workers <= 1:
        model = build_model(excel)
        chart_total = 0
        dashboard_total = 0
        for language in languages:
            print(f"  [{language}]", flush=True)
            for section in section_codes(excel):
                if not section_has_indicators(mapping, section):
                    print(f"    {section}/ (no indicators)", flush=True)
                    continue
                _, _, charts, dashboards, log_lines = _render_section_job(
                    excel, language, section, renderer, mapping, model=model,
                )
                chart_total += charts
                dashboard_total += dashboards
                for line in log_lines:
                    print(line, flush=True)
            print("", flush=True)
        return chart_total, dashboard_total

    print(
        f"[pre_render] rendering {len(jobs)} section(s) across "
        f"{max_workers} worker process(es)",
        flush=True,
    )
    results: dict[SectionJob, tuple[str, str, int, int, list[str]]] = {}
    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=_init_render_pool,
        initargs=(str(excel.resolve()),),
    ) as executor:
        futures = {
            executor.submit(_render_section_job_pooled, job): job
            for job in jobs
        }
        for future in as_completed(futures):
            job = futures[future]
            results[job] = future.result()

    return _print_section_results(languages, results, jobs)


def _part_anchor(part_id: str) -> str:
    return f"part-{part_id}"


def _section_anchor(section: str) -> str:
    return f"section-{section.lower()}"


def _render_language_panel(
    language: str,
    model,
    excel: Path,
    mapping,
    *,
    visible: bool = False,
) -> list[str]:
    titles = section_titles(model, language, excel)
    direction = "rtl" if is_rtl(language) else "ltr"
    hidden_attr = "" if visible else " hidden"
    lines = [
        f'<div class="pb-lang-panel" data-lang="{html.escape(language)}" data-dir="{direction}"{hidden_attr}>',
    ]
    for part in report_parts(excel):
        part_title = part["title"].get(language, part["title"]["English"])
        lines.append('<section class="report-part">')
        lines.append(
            f'<h2 class="report-part-title" data-anchor="{_part_anchor(part["id"])}">'
            f"{html.escape(part_title)}</h2>"
        )
        for section in part["sections"]:
            if not section_has_indicators(mapping, section):
                continue
            heading = titles.get(section, section)
            lines.append('<section class="report-section">')
            if not section_uses_part_heading_only(part["id"]):
                lines.append(
                    f'<h3 class="report-section-title" data-anchor="{_section_anchor(section)}">'
                    f"{html.escape(heading)}</h3>"
                )
            assets_dir = report_section_assets_dir(resolve_report_dir(), language, section)
            asset_prefix = report_section_assets_ref(language, section)
            dashboard_html = build_section_embed(
                model,
                section,
                language=language,
                assets_dir=assets_dir,
                asset_url_prefix=asset_prefix,
                render_assets=False,
                mapping=mapping,
            )
            lines.extend(['<div class="report-figure">', dashboard_html, "</div>", "</section>"])
        lines.append("</section>")
    lines.append("</div>")
    return lines


def _generate_body(output: Path, model, languages: tuple[str, ...], excel: Path, mapping) -> None:
    """Write _body.qmd with embedded dashboard HTML for all languages."""
    default_language = languages[0]
    lines: list[str] = [
        "```{=html}",
        f'<div id="pb-language-panels" data-default="{html.escape(default_language)}">',
    ]
    for language in languages:
        lines.extend(
            _render_language_panel(
                language, model, excel, mapping, visible=language == default_language,
            )
        )
    header_json = json.dumps(report_header_meta(languages, excel), ensure_ascii=False)
    lines.extend([
        f'<script type="application/json" id="pb-report-header-i18n">{header_json}</script>',
        "</div>",
        "```",
    ])
    output.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"[pre_render] body: {output.name} ({len(languages)} languages: {', '.join(languages)})",
        flush=True,
    )


def main() -> None:
    clear_cache()
    excel = resolve_excel()
    languages = _resolve_languages(excel)
    _clean_build_workspace(languages)
    model = build_model(excel)
    mapping = load_mapping(excel)

    print(f"[pre_render] {excel.name} -> languages: {', '.join(languages)}", flush=True)

    chart_total, dashboard_total = _generate_assets(excel, languages, mapping)
    print(
        f"[pre_render] assets done: {chart_total} chart assets, "
        f"{dashboard_total} dashboard PNGs -> {resolve_figures_output().name}/",
        flush=True,
    )

    _generate_body(resolve_report_dir() / "_body.qmd", model, languages, excel, mapping)


if __name__ == "__main__":
    main()
    # WeasyPrint/Pango/Cairo can segfault during interpreter teardown on Windows
    # (exit 3221225477 / 0xC0000005) after successful PNG export. Skip cleanup.
    if sys.platform == "win32":
        os._exit(0)
