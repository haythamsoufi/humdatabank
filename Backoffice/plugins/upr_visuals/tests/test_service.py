"""Unit tests for remaining UprVisualsService render helpers."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from plugins.upr_visuals.service import UprVisualsService, visual_export_filename


@pytest.mark.unit
def test_visual_export_filename_prefers_document_title_for_combined():
    name = visual_export_filename(
        {"document_title": "Afghanistan INP AR 2026", "iso3": "AFG", "round_code": "P26"},
        "combined",
        "pdf",
    )
    assert name.endswith(".pdf")
    assert "Afghanistan" in name


@pytest.mark.unit
def test_visual_export_filename_uses_iso_round_dashboard():
    name = visual_export_filename(
        {"iso3": "BGD", "round_code": "P26"},
        "in_support",
        "png",
    )
    assert name == "BGD_P26_in_support.png"


@pytest.mark.unit
def test_render_with_timeout_invokes_callable():
    assert UprVisualsService._render_with_timeout(lambda: 42, timeout=1) == 42


@pytest.mark.unit
def test_render_isolated_parallel_runs_jobs_together(monkeypatch):
    barrier = threading.Barrier(2, timeout=2)
    kinds = []

    def fake_isolated(job, timeout=120, on_progress=None):
        kinds.append(job["kind"])
        barrier.wait()
        return Path(job["output_path"])

    ticks = []
    monkeypatch.setattr("plugins.upr_visuals.service.run_isolated", fake_isolated)
    paths = UprVisualsService._render_isolated_parallel(
        [{"kind": "pdf", "output_path": "a.pdf"}, {"kind": "narrative_pages", "output_path": "b.pdf"}],
        on_tick=ticks.append,
    )
    assert set(kinds) == {"pdf", "narrative_pages"}
    assert [str(path) for path in paths] == ["a.pdf", "b.pdf"]
    assert ticks


@pytest.mark.unit
def test_render_isolated_parallel_single_job(monkeypatch):
    seen = []

    def fake_isolated(job, timeout=120, on_progress=None):
        seen.append(job["kind"])
        return Path("only.pdf")

    monkeypatch.setattr("plugins.upr_visuals.service.run_isolated", fake_isolated)
    paths = UprVisualsService._render_isolated_parallel([{"kind": "pdf"}])
    assert seen == ["pdf"]
    assert paths == [Path("only.pdf")]


@pytest.mark.unit
def test_render_bulk_item_png_writes_file(tmp_path, monkeypatch):
    def fake_png(_html, tmp, dashboard_id="combined", **_kwargs):
        Path(tmp).write_bytes(b"png-bytes")

    monkeypatch.setattr("plugins.upr_visuals.service.render_png_isolated", fake_png)
    tmp, arcname = UprVisualsService._render_bulk_item(
        tmp_path,
        payload={"meta": {"iso3": "AFG", "round_code": "P26"}},
        html="<html/>",
        dashboard_id="combined",
        folder="AFG_P26",
        export_format="png",
        word_path=None,
    )
    assert tmp.read_bytes() == b"png-bytes"
    assert arcname == "AFG_P26/combined.png"


@pytest.mark.unit
def test_narrative_pdf_bytes_runs_isolated(tmp_path, monkeypatch):
    from contextlib import contextmanager

    class _App:
        instance_path = str(tmp_path)

    @contextmanager
    def fake_locale(lang):
        yield lang

    monkeypatch.setattr("plugins.upr_visuals.service.current_app", _App())
    monkeypatch.setattr("plugins.upr_visuals.service.export_locale", fake_locale)
    monkeypatch.setattr(
        UprVisualsService,
        "_dashboard_html",
        classmethod(lambda cls, aes_id, dashboard_id, **_kw: ({"meta": {"document_title": "Uganda", "iso3": "UGA"}}, "<html/>")),
    )
    monkeypatch.setattr("plugins.upr_visuals.idml.load_word_paragraphs", lambda _word: [{"text": "Hello"}])
    monkeypatch.setattr(
        "plugins.upr_visuals.idml.style_narrative_blocks",
        lambda blocks, country_name="": blocks,
    )
    monkeypatch.setattr(
        "plugins.upr_visuals.service.translate_styled_blocks",
        lambda blocks, on_progress=None: blocks,
    )

    kinds = []
    barrier = threading.Barrier(2, timeout=2)

    def fake_isolated(job, timeout=120, on_progress=None):
        kinds.append(job["kind"])
        barrier.wait()
        Path(job["output_path"]).write_bytes(b"%PDF-" + job["kind"].encode())
        return Path(job["output_path"])

    monkeypatch.setattr("plugins.upr_visuals.service.run_isolated", fake_isolated)
    monkeypatch.setattr(
        "plugins.upr_visuals.idml.merge_report_pdfs",
        lambda visuals, narrative, folio="": visuals + narrative,
    )
    monkeypatch.setattr("plugins.upr_visuals.idml.folio_label", lambda _meta: "folio")
    seen = []
    data, filename = UprVisualsService.narrative_pdf_bytes(
        9,
        b"PK",
        lang="ar",
        on_progress=lambda **kw: seen.append(kw["message"]),
    )
    assert set(kinds) == {"pdf", "narrative_pages"}
    assert data == b"%PDF-pdf%PDF-narrative_pages"
    assert filename.endswith(".pdf")
    assert any("Translating" in msg for msg in seen)
    assert any("visuals and narrative" in msg for msg in seen)
