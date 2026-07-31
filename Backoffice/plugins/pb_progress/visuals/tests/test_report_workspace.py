"""Workspace helpers for containerized P&B builds."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.config import (  # noqa: E402
    fontawesome_stylesheet_source,
    prepare_report_workspace,
    resolve_report_dir,
    visuals_build_root,
)


class TestReportWorkspace:
    def test_prepare_report_workspace_copies_static_files(self, tmp_path) -> None:
        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        (source / "pb-report.qmd").write_text("# title", encoding="utf-8")
        (source / "_quarto.yml").write_text("project:\n  type: book\n", encoding="utf-8")
        (source / "styles").mkdir()
        (source / "styles" / "ifrc.scss").write_text("body {}", encoding="utf-8")

        prepare_report_workspace(source, target)

        assert (target / "pb-report.qmd").is_file()
        assert (target / "styles" / "ifrc.scss").is_file()
        assert (target / "figures").is_dir()
        assert (target / "output").is_dir()

    def test_prepare_report_workspace_copies_fontawesome_when_available(self, tmp_path) -> None:
        fa_src = fontawesome_stylesheet_source()
        if fa_src is None:
            return

        source = tmp_path / "source"
        target = tmp_path / "target"
        source.mkdir()
        (source / "pb-report.qmd").write_text("# title", encoding="utf-8")
        (source / "_quarto.yml").write_text("project:\n  type: default\n", encoding="utf-8")

        prepare_report_workspace(source, target)

        copied = target / "static" / "fontawesome-6.5.0.min.css"
        assert copied.is_file()
        assert copied.read_bytes() == fa_src.read_bytes()

    def test_resolve_report_dir_uses_workspace_env(self, tmp_path, monkeypatch) -> None:
        workspace = tmp_path / "build_workspace"
        workspace.mkdir()
        monkeypatch.setenv("PB_VISUALS_BUILD_ROOT", str(workspace))
        assert resolve_report_dir() == workspace / "report"
        monkeypatch.delenv("PB_VISUALS_BUILD_ROOT", raising=False)
        assert visuals_build_root() is None
