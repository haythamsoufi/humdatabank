"""Assignment export job reuse and matching."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.utils.datetime_helpers import utcnow
from plugins.upr_visuals.assignment_job import (
    ASSIGNMENT_EXPORT_JOB_TYPE,
    REUSE_COMPLETED_SECONDS,
    _reusable_job_id,
    _visual_job_matches,
    take_matching_pdf_bytes,
)
from plugins.upr_visuals.typography import export_style_token


def _job(**meta):
    defaults = {
        "aes_id": 1641,
        "export_format": "pdf",
        "dashboard_id": "combined",
        "lang": "ar",
        "has_word": False,
        "style_rev": export_style_token(),
    }
    defaults.update(meta)
    return SimpleNamespace(job_type=ASSIGNMENT_EXPORT_JOB_TYPE, meta=defaults)


@pytest.mark.unit
def test_visual_job_matches_same_assignment_format_lang():
    job = _job()
    assert _visual_job_matches(
        job, aes_id=1641, export_format="pdf", dashboard_id="combined", lang="ar"
    )
    assert not _visual_job_matches(
        job, aes_id=1641, export_format="pdf", dashboard_id="combined", lang="en"
    )
    assert not _visual_job_matches(
        job, aes_id=9, export_format="pdf", dashboard_id="combined", lang="ar"
    )
    assert not _visual_job_matches(
        job, aes_id=1641, export_format="png", dashboard_id="combined", lang="ar"
    )
    job.meta["style_rev"] = "0"
    assert not _visual_job_matches(
        job, aes_id=1641, export_format="pdf", dashboard_id="combined", lang="ar"
    )
    job.meta["style_rev"] = 2
    assert not _visual_job_matches(
        job, aes_id=1641, export_format="pdf", dashboard_id="combined", lang="ar"
    )


@pytest.mark.unit
def test_visual_job_matches_skips_narrative_jobs():
    job = _job(has_word=True)
    assert not _visual_job_matches(
        job, aes_id=1641, export_format="pdf", dashboard_id="combined", lang="ar"
    )


def _pick(**kwargs):
    return _reusable_job_id(
        kwargs.pop("jobs"),
        aes_id=1641,
        export_format="pdf",
        dashboard_id="combined",
        lang="ar",
        **kwargs,
    )


@pytest.mark.unit
def test_find_reusable_returns_in_flight_job():
    running = _job()
    running.id = "in-flight"
    running.status = "running"
    running.created_at = utcnow()
    running.finished_at = None
    assert _pick(jobs=[running]) == "in-flight"


@pytest.mark.unit
def test_find_reusable_returns_fresh_completed_file(tmp_path):
    output = tmp_path / "out.pdf"
    output.write_bytes(b"%PDF-1.4")
    done = _job(output_path=str(output))
    done.id = "ready"
    done.status = "completed"
    done.created_at = utcnow()
    done.finished_at = utcnow()
    assert _pick(jobs=[done]) == "ready"


@pytest.mark.unit
def test_find_reusable_accepts_naive_finished_at(tmp_path):
    output = tmp_path / "out.pdf"
    output.write_bytes(b"%PDF-1.4")
    done = _job(output_path=str(output))
    done.id = "naive"
    done.status = "completed"
    done.finished_at = utcnow().replace(tzinfo=None)
    done.created_at = done.finished_at
    assert _pick(jobs=[done]) == "naive"


@pytest.mark.unit
def test_find_reusable_skips_stale_completed(tmp_path):
    output = tmp_path / "out.pdf"
    output.write_bytes(b"%PDF-1.4")
    stale = _job(output_path=str(output))
    stale.id = "old"
    stale.status = "completed"
    stale.finished_at = utcnow() - timedelta(seconds=REUSE_COMPLETED_SECONDS + 30)
    stale.created_at = stale.finished_at
    assert _pick(jobs=[stale]) is None


def _patch_pdf_lookup(monkeypatch, job_id, job):
    monkeypatch.setattr(
        "plugins.upr_visuals.assignment_job.find_reusable_assignment_export_job",
        lambda **_k: job_id,
    )
    monkeypatch.setattr(
        "plugins.upr_visuals.assignment_job.AIJob",
        SimpleNamespace(query=SimpleNamespace(get=lambda _id: job)),
    )


@pytest.mark.unit
def test_take_matching_pdf_bytes_returns_completed_file(tmp_path, monkeypatch):
    output = tmp_path / "out.pdf"
    output.write_bytes(b"%PDF-1.4 hello")
    _patch_pdf_lookup(
        monkeypatch,
        "pdf-job",
        SimpleNamespace(
            status="completed",
            meta={"output_path": str(output), "filename": "AFG.pdf"},
        ),
    )
    data, name = take_matching_pdf_bytes(aes_id=3129)
    assert data == b"%PDF-1.4 hello"
    assert name == "AFG.pdf"


@pytest.mark.unit
def test_take_matching_pdf_bytes_waits_for_inflight(tmp_path, monkeypatch):
    output = tmp_path / "out.pdf"
    output.write_bytes(b"%PDF-1.4")
    running = SimpleNamespace(status="running", meta={})
    done = SimpleNamespace(
        status="completed",
        meta={"output_path": str(output), "filename": "x.pdf"},
    )
    states = iter([running, done])
    monkeypatch.setattr(
        "plugins.upr_visuals.assignment_job.find_reusable_assignment_export_job",
        lambda **_k: "pdf-job",
    )
    monkeypatch.setattr(
        "plugins.upr_visuals.assignment_job.AIJob",
        SimpleNamespace(query=SimpleNamespace(get=lambda _id: next(states))),
    )
    monkeypatch.setattr("plugins.upr_visuals.assignment_job.db.session.expire_all", lambda: None)
    monkeypatch.setattr("plugins.upr_visuals.assignment_job.time.sleep", lambda _s: None)
    data, name = take_matching_pdf_bytes(aes_id=3129, timeout=2)
    assert data.startswith(b"%PDF")
    assert name == "x.pdf"


@pytest.mark.unit
def test_take_matching_pdf_bytes_none_when_no_job(monkeypatch):
    monkeypatch.setattr(
        "plugins.upr_visuals.assignment_job.find_reusable_assignment_export_job",
        lambda **_k: None,
    )
    assert take_matching_pdf_bytes(aes_id=3129) is None
