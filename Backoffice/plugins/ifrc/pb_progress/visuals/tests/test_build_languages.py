"""Tests for build language selection and workspace cleanup."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_TESTS = ROOT.parent / "tests"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(PLUGIN_TESTS))

from build_report import _language_subprocess_args  # noqa: E402
from pb_figures.languages import resolve_build_languages  # noqa: E402
from pre_render import _clean_build_workspace  # noqa: E402
from workbook_fixtures import sp1_mapping_row, write_test_workbook  # noqa: E402


@pytest.fixture
def minimal_workbook(tmp_path):
    path = tmp_path / "workbook.xlsx"
    write_test_workbook(path, mapping_rows=[sp1_mapping_row()])
    return path


@pytest.mark.unit
def test_resolve_build_languages_honours_env(monkeypatch, minimal_workbook) -> None:
    monkeypatch.setenv("PB_REPORT_EXCEL", str(minimal_workbook))
    monkeypatch.setenv("PB_REPORT_LANGUAGE", "English")
    assert resolve_build_languages(minimal_workbook) == ("English",)


@pytest.mark.unit
def test_resolve_build_languages_all_returns_every_language(monkeypatch, minimal_workbook) -> None:
    monkeypatch.setenv("PB_REPORT_EXCEL", str(minimal_workbook))
    monkeypatch.setenv("PB_REPORT_LANGUAGE", "all")
    assert resolve_build_languages(minimal_workbook) == (
        "English",
        "French",
        "Spanish",
        "Arabic",
    )


@pytest.mark.unit
def test_language_subprocess_args_single_language() -> None:
    assert _language_subprocess_args({"PB_REPORT_LANGUAGE": "French"}) == ["--language", "French"]


@pytest.mark.unit
def test_language_subprocess_args_all_languages() -> None:
    assert _language_subprocess_args({"PB_REPORT_LANGUAGE": "all"}) == ["--all-languages"]


@pytest.mark.unit
def test_clean_build_workspace_removes_stale_language_dirs(tmp_path, monkeypatch) -> None:
    figures = tmp_path / "Figures"
    output = tmp_path / "output"
    (figures / "English").mkdir(parents=True)
    (figures / "French").mkdir(parents=True)
    (figures / "English" / "SP1.png").write_bytes(b"png")
    (figures / "French" / "SP1.png").write_bytes(b"png")
    output.mkdir(parents=True)
    (output / "pb-report-french.pdf").write_bytes(b"pdf")

    monkeypatch.setattr("pre_render.resolve_figures_output", lambda: figures)
    monkeypatch.setattr("pre_render.resolve_report_output", lambda: output)

    _clean_build_workspace(("English",))

    assert (figures / "English").is_dir()
    assert not (figures / "French").exists()
    assert list(output.iterdir()) == []
