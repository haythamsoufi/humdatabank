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
