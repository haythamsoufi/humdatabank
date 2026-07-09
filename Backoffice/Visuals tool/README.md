# GB Report — July 2026

Python + Quarto pipeline that generates the IFRC Governing Board report from `SG Report.xlsx`.

## Quick start

Double-click **`gb-report.bat`** or run from a terminal:

```bat
gb-report.bat
```

Choose **1** to build the full report (HTML + editable Word, all languages).

## Requirements

- Python 3.11+
- [Quarto](https://quarto.org/) (`winget install Posit.Quarto`)
- Dependencies: `pip install -r requirements.txt`
- Playwright browser: `python -m playwright install chromium`

Use menu options **5** and **6** in `gb-report.bat` to install Python dependencies and Playwright Chromium.

## Project layout

```
├── SG Report.xlsx          Data source (keep closed while building)
├── gb-report.bat           Interactive build menu
├── requirements.txt        Python dependencies (includes scripts/gb_figures/)
├── scripts/                Python pipeline
│   ├── build_report.py     Main build entry point
│   ├── pre_render.py       Quarto pre-render hook (figures + _body.qmd)
│   ├── generate_gb_figures.py
│   ├── generate_report_docx.py
│   ├── package_figures.py
│   ├── validate_excel_data.py
│   └── gb_figures/         Rendering package
├── report/                 Quarto project
│   ├── gb-report.qmd
│   ├── fonts/              Bundled Tajawal (Arabic typography, offline)
│   └── output/             Built HTML and Word files
├── Figures/                Generated dashboard PNGs (per language)
├── tests/                  Automated checks
└── Archive/                Legacy Tableau workbooks and old scripts
```

## Outputs

| File | Description |
|------|-------------|
| `report/output/gb-report.html` | Interactive HTML report with language dropdown |
| `report/output/gb-report.docx` | Editable Word (English default) |
| `report/output/gb-report-{language}.docx` | Editable Word per language |
| `report/output/gb-report-figures-*.zip` | Dashboard PNG bundles for download |

## Manual commands

```powershell
cd scripts
python build_report.py                  # Full build
python build_report.py --figures-only   # Regenerate figures only
python generate_report_docx.py --all-languages
python generate_gb_figures.py --all --language English
python generate_gb_figures.py --all --language English --style modern
python build_report.py --style professional
python validate_excel_data.py           # Check Excel joins
python -m unittest discover -s ../tests # Run automated tests
```

Close `SG Report.xlsx` in Excel before building. If it is open, the batch tool will try a temporary copy.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `GB_REPORT_EXCEL` | `SG Report.xlsx` | Override Excel data path |
| `GB_REPORT_LANGUAGE` | `all` | Target language(s) |
| `GB_REPORT_YEAR` | `2026` | Report year |
| `GB_FIGURES_RENDERER` | `html` | `html` (Playwright, default) or `matplotlib` (legacy fallback) |
| `GB_FIGURES_STYLE` | `classic` | Figure visual style: `classic`, `modern`, or `professional` |
| `GB_QUARTO_EXE` | *(auto)* | Override Quarto executable path |

### Figure styles

Three build-time themes keep IFRC red/orange brand colours and vary line effects, neutrals, and typography:

| Style | Look |
|-------|------|
| `classic` | Current Tableau-faithful default (clean lines, no effects) |
| `modern` | Area fill, soft shadow, marker rings, lighter dividers |
| `professional` | Marker rings, thinner stroke, hairline dividers |

Set via `--style` on `build_report.py` / `generate_gb_figures.py`, or `GB_FIGURES_STYLE` in the environment.

## Maintenance

### Temporarily hidden indicators

Some indicators can be hidden without changing Excel. Edit `TEMPORARILY_HIDDEN` in `scripts/gb_figures/layouts.py`:

```python
TEMPORARILY_HIDDEN = {
    "SP2": frozenset({"Katya01"}),  # Funds mobilized — remove this entry to restore
}
```

### Reference data not used by the pipeline

Optional reference workbooks (for example `FDRS.xlsx`) belong in `Archive/reference/` and are not read by the build. The pipeline uses the `FDRS KPI` column in `SG Report.xlsx` → `Mapping` sheet only.

### Legacy renderer

The Matplotlib renderer (`GB_FIGURES_RENDERER=matplotlib`) remains for debugging only. Production builds always use Playwright HTML/SVG.
