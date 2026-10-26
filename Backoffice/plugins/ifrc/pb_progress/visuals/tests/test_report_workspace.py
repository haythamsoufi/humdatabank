"""Workspace helpers for containerized P&B builds."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.config import prepare_report_workspace, resolve_report_dir, visuals_build_root  # noqa: E402


def _make_source_report(root: Path, *, styles_body: str = "body {}") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    source = root / "source"
    source.mkdir(parents=True, exist_ok=True)
    (source / "pb-report.qmd").write_text("# title", encoding="utf-8")
    (source / "_quarto.yml").write_text("project:\n  type: book\n", encoding="utf-8")
    (source / "styles").mkdir()
    (source / "styles" / "ifrc.scss").write_text(styles_body, encoding="utf-8")
    (source / "partials").mkdir()
    (source / "partials" / "report-tools.html").write_text("<div></div>", encoding="utf-8")
    return source


class TestReportWorkspace:
    def test_prepare_report_workspace_copies_static_files(self, tmp_path) -> None:
        source = _make_source_report(tmp_path)
        target = tmp_path / "target"

        prepare_report_workspace(source, target)

        assert (target / "pb-report.qmd").is_file()
        assert (target / "styles" / "ifrc.scss").is_file()
        assert (target / "partials" / "report-tools.html").is_file()
        assert (target / "figures").is_dir()
        assert (target / "output").is_dir()

    def test_prepare_report_workspace_rebuilds_without_rmtree(self, tmp_path) -> None:
        """Regression: second build must sync into an existing workspace tree."""
        source = _make_source_report(tmp_path / "round1", styles_body="body { color: red; }")
        target = tmp_path / "target"
        prepare_report_workspace(source, target)

        source_v2 = _make_source_report(tmp_path / "round2", styles_body="body { color: blue; }")
        with patch("pb_figures.config.shutil.rmtree") as rmtree_mock:
            prepare_report_workspace(source_v2, target)
            rmtree_mock.assert_not_called()

        assert "blue" in (target / "styles" / "ifrc.scss").read_text(encoding="utf-8")

    def test_resolve_report_dir_uses_workspace_env(self, tmp_path, monkeypatch) -> None:
        workspace = tmp_path / "build_workspace"
        workspace.mkdir()
        monkeypatch.setenv("PB_VISUALS_BUILD_ROOT", str(workspace))
        assert resolve_report_dir() == workspace / "report"
        monkeypatch.delenv("PB_VISUALS_BUILD_ROOT", raising=False)
        assert visuals_build_root() is None
