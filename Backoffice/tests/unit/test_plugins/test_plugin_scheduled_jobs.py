"""Plugins contribute scheduler jobs through BasePlugin.get_scheduled_jobs."""
from unittest.mock import MagicMock

import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from app.plugins.base import ScheduledJob
from app.scheduler import _register_plugin_jobs, _run_scheduled_job


def _app_with_plugins(plugins, active=()):
    app = MagicMock()
    app.plugin_manager.plugins = plugins
    app.plugin_manager.is_plugin_active.side_effect = lambda pid: pid in active
    return app


@pytest.mark.unit
def test_fdrs_public_export_job_is_declared_by_the_plugin(app):
    jobs = app.plugin_manager.plugins["fdrs"].get_scheduled_jobs()
    assert [j.job_id for j in jobs] == ["fdrs_public_export_snapshot"]
    assert jobs[0].trigger == "cron"
    assert jobs[0].trigger_args == {"hour": 4, "minute": 15, "timezone": "UTC"}


@pytest.mark.unit
def test_plugin_jobs_are_added_with_their_trigger():
    plugin = MagicMock()
    plugin.get_scheduled_jobs.return_value = [
        ScheduledJob(
            job_id="demo_job",
            name="Demo",
            func=lambda: None,
            trigger="cron",
            trigger_args={"hour": 4, "minute": 15, "timezone": "UTC"},
        )
    ]
    scheduler = BackgroundScheduler()
    _register_plugin_jobs(_app_with_plugins({"demo": plugin}), scheduler)

    job = scheduler.get_job("demo_job")
    assert job is not None
    assert job.name == "Demo"
    assert "hour='4'" in str(job.trigger) and "minute='15'" in str(job.trigger)


@pytest.mark.unit
def test_broken_plugin_does_not_stop_other_plugin_jobs():
    broken = MagicMock()
    broken.get_scheduled_jobs.side_effect = RuntimeError("boom")
    good = MagicMock()
    good.get_scheduled_jobs.return_value = [
        ScheduledJob("good_job", "Good", lambda: None, "interval", {"minutes": 5})
    ]
    scheduler = BackgroundScheduler()
    _register_plugin_jobs(_app_with_plugins({"a_broken": broken, "b_good": good}), scheduler)
    assert scheduler.get_job("good_job") is not None


@pytest.mark.unit
def test_inactive_plugin_job_run_is_skipped():
    ran = []
    app = _app_with_plugins({}, active=())
    app.app_context.return_value.__enter__ = lambda self: None
    app.app_context.return_value.__exit__ = lambda self, *a: False
    _run_scheduled_job(app, "demo_job", lambda: ran.append(1), plugin_id="demo")
    assert ran == []
