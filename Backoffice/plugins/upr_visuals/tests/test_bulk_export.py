"""Bulk export format helpers and isolated job dispatch."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from plugins.upr_visuals.bulk import (
    collect_narrative_uploads,
    match_narrative_path,
    normalize_export_format,
)
from plugins.upr_visuals.errors import UprVisualsError
from plugins.upr_visuals.export_job import run_export_job_file


def _docx_bytes(text: str = "Hello") -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("word/document.xml", document)
    return out.getvalue()


class _Upload:
    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self._data = data

    def read(self):
        return self._data


@pytest.mark.unit
def test_normalize_export_format():
    assert normalize_export_format("PDF") == "pdf"
    assert normalize_export_format(None) == "png"
    with pytest.raises(UprVisualsError):
        normalize_export_format("docx")


@pytest.mark.unit
def test_match_narrative_path_prefers_iso3(tmp_path):
    afg = tmp_path / "AFG.docx"
    afg.write_bytes(b"afg")
    named = tmp_path / "afghanistan.docx"
    named.write_bytes(b"name")
    paths = {"afg": str(afg), "afghanistan": str(named)}
    assert match_narrative_path(paths, iso3="AFG").read_bytes() == b"afg"
    assert match_narrative_path(paths, country_name="Afghanistan").read_bytes() == b"name"
    assert match_narrative_path(paths, iso3="BGD") is None
    paths["11"] = str(afg)
    assert match_narrative_path(paths, aes_id=11).read_bytes() == b"afg"


@pytest.mark.unit
def test_collect_narrative_uploads_from_zip_and_docx():
    docx = _docx_bytes("AFG")
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as zf:
        zf.writestr("AFG.docx", docx)
        zf.writestr("notes.txt", "skip")
    found = collect_narrative_uploads([_Upload("narratives.zip", zbuf.getvalue())])
    assert set(found) == {"afg"}
    found.update(collect_narrative_uploads([_Upload("Bangladesh.docx", _docx_bytes("BD"))]))
    assert "bangladesh" in found


@pytest.mark.unit
def test_run_export_job_file_pdf(tmp_path, monkeypatch):
    html = tmp_path / "in.html"
    html.write_text("<html/>", encoding="utf-8")
    out = tmp_path / "out.pdf"
    job = tmp_path / "job.json"
    job.write_text(
        json.dumps({"kind": "pdf", "html_path": str(html), "output_path": str(out), "dashboard_id": "combined"}),
        encoding="utf-8",
    )

    def fake_pdf(_html, dashboard_id="combined", zoom=1.0, title=""):
        return b"%PDF-fake"

    monkeypatch.setattr("plugins.upr_visuals.export_job.render_pdf_bytes", fake_pdf)
    run_export_job_file(job)
    assert out.read_bytes() == b"%PDF-fake"


@pytest.mark.unit
def test_run_export_job_file_idml(tmp_path, monkeypatch):
    html = tmp_path / "in.html"
    html.write_text("<html/>", encoding="utf-8")
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"meta": {"document_title": "Afghanistan"}}), encoding="utf-8")
    out = tmp_path / "out.zip"
    job = tmp_path / "job.json"
    work = tmp_path / "work"
    job.write_text(
        json.dumps(
            {
                "kind": "idml",
                "html_path": str(html),
                "payload_path": str(payload),
                "output_path": str(out),
                "work_dir": str(work),
                "dashboard_id": "combined",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("plugins.upr_visuals.export_job.render_pdf_bytes", lambda *_a, **_k: b"%PDF")

    def fake_package(**_kw):
        return {"zip_bytes": b"PK-idml"}

    monkeypatch.setattr("plugins.upr_visuals.idml.build_indesign_package", fake_package)
    run_export_job_file(job)
    assert out.read_bytes() == b"PK-idml"


@pytest.mark.unit
def test_run_export_job_file_narrative_uses_pretranslated_blocks(tmp_path, monkeypatch):
    html = tmp_path / "in.html"
    html.write_text("<html/>", encoding="utf-8")
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"meta": {"country_name": "Uganda"}}), encoding="utf-8")
    styled = tmp_path / "styled.json"
    styled.write_text(json.dumps([{"style": "Body", "text": "مرحبا"}]), encoding="utf-8")
    out = tmp_path / "out.pdf"
    job = tmp_path / "job.json"
    job.write_text(
        json.dumps(
            {
                "kind": "narrative_pdf",
                "html_path": str(html),
                "payload_path": str(payload),
                "styled_path": str(styled),
                "output_path": str(out),
                "dashboard_id": "combined",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("plugins.upr_visuals.export_job.render_pdf_bytes", lambda *_a, **_k: b"%PDF-vis")

    def fake_narrative(blocks, folio=""):
        assert blocks[0]["text"] == "مرحبا"
        return b"%PDF-nar"

    monkeypatch.setattr("plugins.upr_visuals.idml.render_narrative_pdf_bytes", fake_narrative)
    monkeypatch.setattr(
        "plugins.upr_visuals.idml.merge_report_pdfs",
        lambda visuals, narrative, folio="": visuals + narrative,
    )
    run_export_job_file(job)
    assert out.read_bytes() == b"%PDF-vis%PDF-nar"


@pytest.mark.unit
def test_run_export_job_file_narrative_pages(tmp_path, monkeypatch):
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"meta": {"country_name": "Uganda"}}), encoding="utf-8")
    styled = tmp_path / "styled.json"
    styled.write_text(json.dumps([{"style": "Body", "text": "Hello"}]), encoding="utf-8")
    out = tmp_path / "out.pdf"
    job = tmp_path / "job.json"
    job.write_text(
        json.dumps(
            {
                "kind": "narrative_pages",
                "payload_path": str(payload),
                "styled_path": str(styled),
                "output_path": str(out),
            }
        ),
        encoding="utf-8",
    )

    def fake_narrative(blocks, folio=""):
        assert blocks[0]["text"] == "Hello"
        return b"%PDF-pages"

    monkeypatch.setattr("plugins.upr_visuals.idml.render_narrative_pdf_bytes", fake_narrative)
    run_export_job_file(job)
    assert out.read_bytes() == b"%PDF-pages"
