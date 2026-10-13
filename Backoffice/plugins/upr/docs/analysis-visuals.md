# UPR Analysis visuals — architecture and reuse

The **UPR Analysis** Data Explorer tab, the **presentation** and the **A4 report** draw from **one description of the visuals**. Nothing about a chart, KPI, table or footnote is defined twice.

```
live data ──► aggregators ──► payload ──► views ──► outline ──► renderers
              impact.py       (raw        impact_views.py   pages.js    tab           (upr-impact.js)
              narrative.py    series)     narrative_views.py            presentation  (slides.js)
                                          analysis_spec.py              A4 report     (report.js)
                                          analysis_labels.py
```

| Layer | Files | Owns |
|---|---|---|
| Rules shared by every layer | `analysis_common.py` | Round codes and order, "submitted" statuses, the settled-round ratio, year-over-year change, region scoping |
| Aggregation (pure) | `impact.py`, `narrative.py` | Numbers: per-year data series, participation by stage |
| Display text | `analysis_labels.py` | Every title, hint, series name, column heading and note (one msgid catalogue, Flask-Babel) |
| View schema + helpers | `analysis_spec.py` | The JSON structure below, palette, table and KPI helpers |
| Views | `impact_views.py`, `narrative_views.py` | Which visuals exist, how each series is drawn, what each table shows |
| Entry points | `analysis_service.py` | `build_impact_analysis`, `build_narrative_analysis`, `build_analysis_bundle` |
| Browser renderers | `static/js/upr-analysis-{format,charts,dom}.js` | Raw value → text, view chart → ApexCharts options, cards / KPIs / tables, and `dom.renderBlock` for exports |
| Export outline | `static/js/upr-analysis-pages.js` | Which blocks (cover, section, KPIs, visuals, tables, notes) an export contains, in order |
| Presentation | `static/js/upr-analysis-slides.js`, `css/upr-analysis-export.css` | 16:9 slide deck: navigation, scaling, full screen |
| A4 report | `static/js/upr-analysis-report.js`, `css/upr-analysis-{export,print}.css` | A4 pagination and the print flow |
| The tab | `static/js/upr-impact.js`, `templates/upr/impact_panel.html` | Fetching, loading states, region and round-type controls, the export dialog |

## The view

Defined in the docstring of `analysis_spec.py`. In short, a view is

```
{ title, lead, kpis: [KPI], visuals: [Visual], notes: [str], warnings: [str], has_data }
```

- A **visual** has `id`, `title`, `hint`, `kind` (`chart`, `panels` for small multiples, `gaps` for follow-up lists), a declarative **chart**, and a **table** holding the same numbers with country drill-down rows.
- A **visual** may also carry `findings` (empty today): see *Findings* below.
- A **chart** is `categories` + `series` (`kind`: `column` / `line` / `area`, `axis`, `format`, `color`) + `axes`. It names no charting library.
- Values stay **raw**; a `format` name (`int`, `money`, `pct`, `abs_int`) says how to print them. Chart axes, tooltips, KPIs and table cells all share one number.

The data section has one view (`impact_views.build_impact_view`). The participation section has one view per round type (`narrative_views.build_narrative_views` → `ALL`, `P`, `MYR`, `AR`), so switching needs no new request and an export can walk all of them.

`GET /admin/data-exploration/upr-impact/data` returns `{impact, view}`; `/upr-impact/narrative` returns `{narrative, views}`. `impact`/`narrative` are the raw payloads, kept for API consumers.

## Adding or changing a visual

1. Add the text to `analysis_labels.analysis_labels()` (reuse existing msgids where you can).
2. Add a function to `impact_views.py` or `narrative_views.py` returning `visual(...)` and register it in the view builder. The tab renders it with no JavaScript change.
3. If a chart needs a new look, extend the chart spec and `upr-analysis-charts.js` together, with a case in `tests/js/plugins/upr-analysis.test.js`.
4. Regenerate the contract fixture (below) and run both test suites.

## Findings (explaining a visual)

A visual can carry `findings: [Finding]`, short written takeaways such as "Planned funding doubled between 2024 and 2025". They are **part of the view**, so the tab, the slides and the A4 report show the same words and a translation covers all three. No findings are written yet; every visual's list is empty and nothing renders until one is added.

```python
from plugins.upr.analysis_spec import finding, visual

visual(
    "funding", title, hint, chart=chart, table=table,
    findings=[
        finding("ambition", fill(labels["finding_funding_ambition"], ...),
                title=labels["finding_funding_ambition_title"],
                tone="positive",              # "info" (default) | "positive" | "attention"
                categories=["2025 *"]),       # chart categories it is about (optional)
    ],
)
```

1. Add the text to `analysis_labels.py` (never hard-code English in a builder) and compute any numbers from the payload, so a finding cannot disagree with the chart beside it.
2. Pass `findings=[...]` to `visual(...)`. Nothing else changes: no JavaScript, no template.
3. Regenerate the fixture and run both suites. `test_every_visual_lists_findings_that_the_renderers_can_place` checks that ids are unique, tones are valid and `categories` really are categories of that visual's chart (focus is only supported on single-chart visuals).

How each output shows them:

| Output | Behaviour |
|---|---|
| Tab, A4 report | A "Key findings" list under the chart, all visible (`dom.renderFindings(..., 'visible')`) |
| Presentation | Each finding starts hidden behind a numbered button; the space is reserved so nothing jumps. **Next / Space / Enter / →** reveals the next finding, then moves on; **← ** hides the last one first. Click a number to show or hide that finding, **I** (or the lightbulb) toggles all. The chart highlights the `categories` of every finding currently shown (`charts.focus`). The counter shows `slide / total · shown/findings`. |

Slides with findings draw the chart shorter (`slides.FINDINGS_SIZE`) to leave room. Revealed state is kept while navigating back and forth and resets when the presentation is reopened.

Not built yet, and where it would go: findings on KPIs or on a whole section (add a `findings` list to the KPI / view and a block type in `dom.renderBlock`), highlighting a series rather than a category (extend `focus` in the spec and `charts.focus`), and findings on multi-chart visuals (`panels`).

## Contract fixture

`plugins/upr/tests/fixtures/analysis_views.json` is generated by the Python view builders and rendered by the vitest suite, so server and browser are tested against the same data.

```
UPR_UPDATE_FIXTURES=1 pytest plugins/upr/tests/test_analysis_views.py   # regenerate after changing a view
npm run test:js -- tests/js/plugins/upr-analysis.test.js                # from Backoffice/
```

## Presentation and A4 report

Both are built **in the browser from the views the tab already loaded** (same region, no extra request), because the visuals are ApexCharts drawn by JavaScript. They do not recompute numbers or re-type text.

```
Export dialog (upr-impact.js)  ─ selected sections ─►  pages.buildOutline()  ─ blocks ─►  slides.open()
                                                                                   └────►  report.open()
```

- **Outline** (`upr-analysis-pages.js`, pure): `cover`, then per section a `section` heading, `kpis`, one `visual` per visual, optional `table`s and `notes`. A block points at the view's own objects. Sections are `data` and `track:ALL|P|MYR|AR`.
- **`dom.renderBlock`** turns any block into DOM with the tab's own classes (`upri-kpi`, `upri-card`, …) and reports the charts still to draw, which are mounted with `charts.mountAll(plots, {animate: false})`. Static output has no clicks, so cards drop the table button and spell out the gap lists.
- **Presentation**: a fixed 1280×720 stage scaled by CSS transform, one slide per block (tables are report-only), arrow keys / Space / Home / End, `F` for full screen, `Esc` to close. ApexCharts cannot measure a scaled container, so every slide chart gets an explicit `width` and `height` (`slides.CHART_SIZE`).
- **A4 report**: fixed-size 210×297 mm pages, blocks flow onto a page until it is full (the host reserves its chart height up front, so pages are measured before charts exist). The footer is created with the page so its height is always part of the measurement. **Print** uses the browser's print dialog (*Save as PDF*): the live SVG charts stay vector and the text stays selectable, and it looks exactly like the tab. The `@page` / hide-the-app rules live in `upr-analysis-print.css`, linked with `media="not all"` and switched to `print` only while a report is open so printing elsewhere in the Backoffice is untouched.
- **Chart sizes** for the two outputs are the only layout numbers: `slides.CHART_SIZE` and `report.CHART_SIZE`. If you change the page padding in `upr-analysis-export.css`, adjust the latter.

Adding a visual to the view makes it appear in the tab, the slides and the report with no export code. A new block *type* needs a case in `dom.renderBlock`, a style in `upr-analysis-export.css`, and a test in `tests/js/plugins/upr-analysis-export.test.js`.

**Not built**: a one-click PDF download. That needs either a headless browser on the server (the Backoffice has none) or rasterising the page with html2canvas / jsPDF (neither is vendored; the result would be blurrier and not searchable). A server-drawn PDF would mean re-implementing the charts a second time, which is what this design avoids. A `.pptx` could be written server-side from the same `series` / `categories` (for example with `python-pptx`, not a dependency yet).

## Conventions kept on purpose

- **Participating** means data *or* narrative (`narr_kpi_any`). The data-only headline is labelled "National Societies that reported" (`kpi_coverage`) so one report never shows two different numbers under the same name.
- **Region** is resolved once (`analysis_common.iso3s_in_region`) from the country catalogue, for both sections.
- Server-side text numbers (notes) use thousands separators in English style; table cells and KPI values are formatted in the browser with the user's locale.
- Chart colours live in `analysis_spec.COLORS` (brand navy/red from `catalog.py`); the `--upri-*` CSS variables only style the page around the charts.
