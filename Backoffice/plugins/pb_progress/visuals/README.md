# P&B Report — July 2026

Python + Quarto pipeline that generates the IFRC Plan & Budget report from `SG Report.xlsx`.

## Quick start

Double-click **`pb-report.bat`** or run from a terminal:

```bat
pb-report.bat
```

Choose **1** to build the full report (HTML + editable Word, all languages).

## Requirements

- Python 3.11+
- [Quarto](https://quarto.org/) (`winget install Posit.Quarto`)
- Dependencies: `pip install -r requirements.txt`
- Playwright browser: `python -m playwright install chromium`

Use menu options **5** and **6** in `pb-report.bat` to install Python dependencies and Playwright Chromium.

## Project layout

```
├── SG Report.xlsx          Data source (keep closed while building)
├── pb-report.bat           Interactive build menu
├── requirements.txt        Python dependencies (includes scripts/pb_figures/)
├── scripts/                Python pipeline
│   ├── build_report.py     Main build entry point
│   ├── pre_render.py       Generates figures + report/_body.qmd (run by build_report.py)
│   ├── generate_pb_figures.py
│   ├── generate_report_docx.py
│   ├── package_figures.py
│   ├── validate_excel_data.py
│   └── pb_figures/         Rendering package
├── report/                 Quarto project
│   ├── pb-report.qmd
│   ├── fonts/              Bundled Tajawal (Arabic typography, offline)
│   └── output/             Built HTML and Word files
├── Figures/                Generated dashboard PNGs (per language)
├── tests/                  Automated checks
└── Archive/                Legacy Tableau workbooks and old scripts
```

## Outputs

| File | Description |
|------|-------------|
| `report/output/pb-report.html` | Interactive HTML report with language dropdown |
| `report/output/pb-report.docx` | Editable Word (English default) |
| `report/output/pb-report-{language}.docx` | Editable Word per language |
| `report/output/pb-report-figures-*.zip` | Dashboard PNG bundles for download |

## Manual commands

```powershell
cd scripts
python build_report.py                  # Full build
python build_report.py --figures-only   # Regenerate figures only
python generate_report_docx.py --all-languages
python generate_pb_figures.py --all --language English
python generate_pb_figures.py --all --language English --style modern
python build_report.py --style professional
python validate_excel_data.py           # Check Excel joins
python -m unittest discover -s ../tests # Run automated tests
```

Close `SG Report.xlsx` in Excel before building. If it is open, the batch tool will try a temporary copy.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PB_REPORT_EXCEL` | `SG Report.xlsx` | Override Excel data path |
| `PB_REPORT_LANGUAGE` | `all` | Target language(s) |
| `PB_REPORT_YEAR` | `2026` | Report year |
| `PB_FIGURES_RENDERER` | `html` | `html` (Playwright, default) or `matplotlib` (legacy fallback) |
| `PB_FIGURES_STYLE` | `classic` | Figure visual style: `classic`, `modern`, or `professional` |
| `PB_QUARTO_EXE` | *(auto)* | Override Quarto executable path |

### Figure styles

Three build-time themes keep IFRC red/orange brand colours and vary line effects, neutrals, and typography:

| Style | Look |
|-------|------|
| `classic` | Current Tableau-faithful default (clean lines, no effects) |
| `modern` | Area fill, soft shadow, marker rings, lighter dividers |
| `professional` | Marker rings, thinner stroke, hairline dividers |

Set via `--style` on `build_report.py` / `generate_pb_figures.py`, or `PB_FIGURES_STYLE` in the environment.

## Maintenance

### Temporarily hidden indicators

Some indicators can be hidden without changing Excel. Edit `TEMPORARILY_HIDDEN` in `scripts/pb_figures/layouts.py`:

```python
TEMPORARILY_HIDDEN = {
    "SP2": frozenset({"Katya01"}),  # Funds mobilized — remove this entry to restore
}
```

### Reference data not used by the pipeline

Optional reference workbooks (for example `FDRS.xlsx`) belong in `Archive/reference/` and are not read by the build. The pipeline uses the `FDRS KPI` column in `SG Report.xlsx` → `Mapping` sheet only.

### Legacy renderer

The Matplotlib renderer (`PB_FIGURES_RENDERER=matplotlib`) remains for debugging only. Production builds always use Playwright HTML/SVG.
