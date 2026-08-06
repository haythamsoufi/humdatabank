"""Smoke tests for the P&B report build pipeline (matches production failure modes)."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import pytest

from plugins.pb_progress.db_source import validate_uploaded_workbook
from plugins.pb_progress.service import PBProgressService
from workbook_fixtures import (
    apply_section_order_env,
    cumulative_docx_item,
    section_order_env_json,
    sp1_mapping_row,
    write_test_workbook,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
VISUALS_ROOT = PLUGIN_ROOT / "visuals"
SCRIPTS = VISUALS_ROOT / "scripts"
SOURCE_REPORT = VISUALS_ROOT / "report"


@pytest.fixture
def build_workspace(tmp_path, monkeypatch):
    """Writable workspace mirroring PB_VISUALS_BUILD_ROOT layout."""
    workspace = tmp_path / "build_workspace"
    workspace.mkdir()
    monkeypatch.setenv("PB_VISUALS_BUILD_ROOT", str(workspace))
    monkeypatch.setenv("PB_BUILD_WORKERS", "1")
    apply_section_order_env(monkeypatch, {"sp": ["SP1"]})
    yield workspace
    monkeypatch.delenv("PB_VISUALS_BUILD_ROOT", raising=False)


@pytest.fixture
def staging_workbook(tmp_path):
    """Minimal workbook with SP1 mapping only."""
    path = tmp_path / "staging_gap.xlsx"
    write_test_workbook(path, mapping_rows=[sp1_mapping_row()])
    return path


@pytest.mark.pb_progress
def test_render_stack_preflight_smoke(build_workspace) -> None:
    """Same checks as PBProgressService before starting a build."""
    PBProgressService._verify_render_stack()


@pytest.mark.pb_progress
def test_prepare_report_workspace_survives_rebuild(build_workspace) -> None:
    from pb_figures.config import prepare_report_workspace, resolve_report_dir

    target = resolve_report_dir()
    prepare_report_workspace(SOURCE_REPORT, target)

    updated_source = build_workspace / "source_v2" / "report"
    updated_source.mkdir(parents=True)
    for name in ("pb-report.qmd", "_quarto.yml"):
        (updated_source / name).write_text(f"# {name}\n", encoding="utf-8")
    (updated_source / "styles").mkdir()
    (updated_source / "styles" / "ifrc.scss").write_text("body { color: blue; }", encoding="utf-8")

    with patch("pb_figures.config.shutil.rmtree") as rmtree_mock:
        prepare_report_workspace(updated_source, target)
        rmtree_mock.assert_not_called()

    assert "blue" in (target / "styles" / "ifrc.scss").read_text(encoding="utf-8")


@pytest.mark.pb_progress
def test_generate_body_skips_unmapped_cc1(
    staging_workbook, build_workspace, tmp_path, monkeypatch
) -> None:
    from pb_figures.data import build_model, load_mapping
    from pb_figures.translations import clear_cache
    from pre_render import _generate_body

    monkeypatch.setenv(
        "PB_REPORT_SECTION_ORDER",
        section_order_env_json({"cc": ["CC1"], "sp": ["SP1"], "ef": ["EF1"]}),
    )
    clear_cache()
    body_path = tmp_path / "_body.qmd"
    monkeypatch.setenv("PB_REPORT_EXCEL", str(staging_workbook))
    model = build_model(staging_workbook)
    mapping = load_mapping(staging_workbook)
    _generate_body(body_path, model, ("English",), staging_workbook, mapping)
    body = body_path.read_text(encoding="utf-8")
    assert "report-figure" in body
    assert "section-cc1" not in body


@pytest.mark.pb_progress
def test_validate_workbook_has_no_section_order_gaps(staging_workbook) -> None:
    summary = validate_uploaded_workbook(staging_workbook)
    assert summary["valid"] is True
    assert summary["sections_without_indicators"] == []


@pytest.mark.pb_progress
def test_line_chart_svg_is_well_formed_and_rasterizes(tmp_path) -> None:
    from pb_figures.line_chart import render_line_chart_svg
    from pb_figures.render_docx import render_line_chart_asset
    from pb_figures.svg_raster import write_svg_png

    item = cumulative_docx_item()
    svg = render_line_chart_svg(
        item,
        481,
        chart_id="asset-line",
        show_value_labels=True,
        show_target_labels=True,
        target_label="Target",
    )
    assert 'font-family=""' not in svg
    ET.fromstring(svg)

    png_path = tmp_path / "line.png"
    write_svg_png(svg, png_path, width=481, height=110)
    assert png_path.stat().st_size > 100

    docx_png = tmp_path / "docx_line.png"
    render_line_chart_asset(item, "Target", docx_png, language="English")
    assert docx_png.stat().st_size > 100


@pytest.mark.pb_progress
def test_dashboard_png_rasterizes_sp1(staging_workbook, build_workspace, monkeypatch) -> None:
    """Dashboard ZIP PNGs use WeasyPrint — layout must not collapse like CSS Grid."""
    from pb_figures.charts import render_dashboard
    from pb_figures.data import build_model, load_mapping

    monkeypatch.setenv("PB_REPORT_EXCEL", str(staging_workbook))
    monkeypatch.setenv("PB_REPORT_YEAR", "2027")
    model = build_model(staging_workbook)
    mapping = load_mapping(staging_workbook)
    output = build_workspace / "Figures" / "English" / "SP1.png"
    render_dashboard(
        model,
        "SP1",
        language="English",
        output_path=output,
        mapping=mapping,
    )
    assert output.is_file()
    assert output.stat().st_size > 5000

    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")
    with Image.open(output) as image:
        width, height = image.size
        assert width >= 1200  # 827 CSS px @ 2x raster scale (~1241px)
        assert height >= 280
        pixels = list(image.convert("RGB").getdata())
        # IFRC red (#c22526) appears in title and chart markers when layout is intact.
        red_pixels = sum(1 for r, g, b in pixels if r > 170 and g < 90 and b < 90)
        assert red_pixels > 20


@pytest.mark.pb_progress
def test_package_figures_module_and_defaults(tmp_path) -> None:
    module = importlib.import_module("package_figures")
    assert not hasattr(module, "FIGURES_DIR")

    figures = tmp_path / "Figures"
    output = tmp_path / "output"
    english = figures / "English"
    english.mkdir(parents=True)
    (english / "SP1.png").write_bytes(b"png")

    created = module.package_figures(figures, output, languages=("English",))
    names = {path.name for path in created}
    assert "pb-report-figures-english.zip" in names
    assert "pb-report-figures-all.zip" in names


@pytest.mark.pb_progress
def test_pre_render_figures_only_subprocess(staging_workbook, build_workspace) -> None:
    """Exercise pre_render.main against a staging-shaped workbook."""
    env = os.environ.copy()
    env["PB_REPORT_EXCEL"] = str(staging_workbook.resolve())
    env["PB_VISUALS_BUILD_ROOT"] = str(build_workspace)
    env["PB_REPORT_LANGUAGE"] = "English"
    env["PB_REPORT_YEAR"] = "2027"
    env["PB_BUILD_WORKERS"] = "1"
    env["PB_FIGURES_RENDERER"] = "html"
    env["PB_REPORT_SECTION_ORDER"] = section_order_env_json({"sp": ["SP1"]})
    env["PYTHONUNBUFFERED"] = "1"

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "pre_render.py")],
        cwd=str(VISUALS_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout

    report_dir = build_workspace / "report"
    body = report_dir / "_body.qmd"
    assert body.is_file()
    assert body.stat().st_size > 0
    assert (build_workspace / "Figures" / "English" / "SP1.png").is_file()


@pytest.mark.pb_progress
@pytest.mark.slow
def test_generate_docx_subprocess(staging_workbook, build_workspace) -> None:
    env = os.environ.copy()
    env["PB_REPORT_EXCEL"] = str(staging_workbook.resolve())
    env["PB_VISUALS_BUILD_ROOT"] = str(build_workspace)
    env["PB_REPORT_LANGUAGE"] = "English"
    env["PB_REPORT_YEAR"] = "2027"
    env["PB_BUILD_WORKERS"] = "1"
    env["PB_REPORT_SECTION_ORDER"] = section_order_env_json({"sp": ["SP1"]})

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "generate_report_docx.py"),
            "--language",
            "English",
            "--sections",
            "SP1",
        ],
        cwd=str(VISUALS_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    output = build_workspace / "report" / "output" / "pb-report-english.docx"
    assert output.is_file()
    assert output.stat().st_size > 1000
