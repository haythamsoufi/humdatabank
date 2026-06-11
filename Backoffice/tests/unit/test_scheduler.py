"""
Comprehensive tests for app/scheduler.py — targets 100% coverage.

All tests use heavy mocking; no real APScheduler or thread is started.
"""

import os
import threading
import pytest
from unittest.mock import MagicMock, patch, call


# ===========================================================================
# _graceful_shutdown
# ===========================================================================

class TestGracefulShutdown:
    """Tests for the _graceful_shutdown atexit helper."""

    def _import(self):
        from app.scheduler import _graceful_shutdown
        return _graceful_shutdown

    def test_shuts_down_running_scheduler(self):
        fn = self._import()
        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_app = MagicMock()

        fn(mock_scheduler, mock_app)

        mock_scheduler.shutdown.assert_called_once_with(wait=True)
        assert mock_app.scheduler is None

    def test_skips_shutdown_when_not_running(self):
        fn = self._import()
        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_app = MagicMock()

        fn(mock_scheduler, mock_app)

        mock_scheduler.shutdown.assert_not_called()
        assert mock_app.scheduler is None

    def test_exception_in_shutdown_is_suppressed(self):
        fn = self._import()
        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_scheduler.shutdown.side_effect = RuntimeError("cannot shutdown")
        mock_app = MagicMock()

        # Should not raise
        fn(mock_scheduler, mock_app)

    def test_exception_setting_app_scheduler_none_is_suppressed(self):
        fn = self._import()
        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_app = MagicMock()

        # Make setting app.scheduler raise
        type(mock_app).scheduler = property(
            lambda self: None,
            lambda self, v: (_ for _ in ()).throw(AttributeError("read-only")),
        )

        # Should not raise
        fn(mock_scheduler, mock_app)


# ===========================================================================
# init_scheduler
# ===========================================================================

class TestInitScheduler:
    """Tests for init_scheduler."""

    def _import(self):
        from app.scheduler import init_scheduler
        return init_scheduler

    # ------------------------------------------------------------------
    # Early-return conditions
    # ------------------------------------------------------------------

    def test_returns_early_in_testing_mode(self, app):
        init_scheduler = self._import()
        original = app.config.get("TESTING")
        try:
            app.config["TESTING"] = True
            with patch("app.scheduler.threading.Thread") as mock_thread:
                init_scheduler(app, is_reloader=False)
            mock_thread.assert_not_called()
        finally:
            app.config["TESTING"] = original

    def test_returns_early_when_running_migration(self, app):
        init_scheduler = self._import()
        original = app.config.get("TESTING")
        try:
            app.config["TESTING"] = False
            with patch.dict(os.environ, {"RUNNING_MIGRATION": "1"}):
                with patch("app.scheduler.threading.Thread") as mock_thread:
                    init_scheduler(app, is_reloader=False)
            mock_thread.assert_not_called()
        finally:
            app.config["TESTING"] = original
            os.environ.pop("RUNNING_MIGRATION", None)

    def test_returns_early_when_debug_without_reloader(self, app):
        init_scheduler = self._import()
        original_testing = app.config.get("TESTING")
        original_debug = app.config.get("DEBUG")
        try:
            app.config["TESTING"] = False
            app.config["DEBUG"] = True
            os.environ.pop("RUNNING_MIGRATION", None)
            with patch("app.scheduler.threading.Thread") as mock_thread:
                init_scheduler(app, is_reloader=False)
            mock_thread.assert_not_called()
        finally:
            app.config["TESTING"] = original_testing
            app.config["DEBUG"] = original_debug

    def test_returns_early_when_scheduler_already_exists(self, app):
        init_scheduler = self._import()
        original_testing = app.config.get("TESTING")
        original_debug = app.config.get("DEBUG")
        try:
            app.config["TESTING"] = False
            app.config["DEBUG"] = False
            os.environ.pop("RUNNING_MIGRATION", None)
            app.scheduler = MagicMock()  # scheduler already set
            with patch("app.scheduler.threading.Thread") as mock_thread:
                init_scheduler(app, is_reloader=False)
            mock_thread.assert_not_called()
        finally:
            app.config["TESTING"] = original_testing
            app.config["DEBUG"] = original_debug
            if hasattr(app, "scheduler"):
                app.scheduler = None

    def test_creates_scheduler_lock_if_missing(self, app):
        init_scheduler = self._import()
        original_testing = app.config.get("TESTING")
        original_debug = app.config.get("DEBUG")
        try:
            app.config["TESTING"] = False
            app.config["DEBUG"] = False
            os.environ.pop("RUNNING_MIGRATION", None)
            # Remove scheduler and lock to force creation
            if hasattr(app, "scheduler"):
                del app.scheduler
            if hasattr(app, "_scheduler_lock"):
                del app._scheduler_lock

            with patch("app.scheduler.threading.Thread") as mock_thread:
                mock_thread_instance = MagicMock()
                mock_thread.return_value = mock_thread_instance
                init_scheduler(app, is_reloader=False)

            assert hasattr(app, "_scheduler_lock")
            mock_thread_instance.start.assert_called_once()
        finally:
            app.config["TESTING"] = original_testing
            app.config["DEBUG"] = original_debug
            if hasattr(app, "scheduler"):
                app.scheduler = None

    # ------------------------------------------------------------------
    # scheduler_init_task (inner function executed inside the thread)
    # ------------------------------------------------------------------

    def _run_init_task(self, app):
        """
        Helper: call init_scheduler with threading.Thread mocked so we can
        capture and invoke the target function synchronously.
        """
        init_scheduler = self._import()
        original_testing = app.config.get("TESTING")
        original_debug = app.config.get("DEBUG")
        try:
            app.config["TESTING"] = False
            app.config["DEBUG"] = False
            os.environ.pop("RUNNING_MIGRATION", None)
            if hasattr(app, "scheduler"):
                del app.scheduler
            if hasattr(app, "_scheduler_lock"):
                del app._scheduler_lock

            captured_target = {}

            def capture_thread(**kwargs):
                captured_target["fn"] = kwargs.get("target") or kwargs.get("args", [None])[0]
                mock_thread_obj = MagicMock()
                mock_thread_obj.start = MagicMock()
                return mock_thread_obj

            with patch("app.scheduler.threading.Thread", side_effect=capture_thread):
                init_scheduler(app, is_reloader=False)

            return captured_target.get("fn")
        finally:
            app.config["TESTING"] = original_testing
            app.config["DEBUG"] = original_debug

    def test_scheduler_thread_starts(self, app):
        init_scheduler = self._import()
        original_testing = app.config.get("TESTING")
        original_debug = app.config.get("DEBUG")
        try:
            app.config["TESTING"] = False
            app.config["DEBUG"] = False
            os.environ.pop("RUNNING_MIGRATION", None)
            if hasattr(app, "scheduler"):
                del app.scheduler
            if hasattr(app, "_scheduler_lock"):
                del app._scheduler_lock

            mock_thread_instance = MagicMock()
            with patch("app.scheduler.threading.Thread", return_value=mock_thread_instance):
                init_scheduler(app, is_reloader=False)

            mock_thread_instance.start.assert_called_once()
        finally:
            app.config["TESTING"] = original_testing
            app.config["DEBUG"] = original_debug
            if hasattr(app, "scheduler"):
                app.scheduler = None

    def test_scheduler_init_task_success(self, app):
        """Run the inner scheduler_init_task synchronously and verify scheduler starts."""
        original_testing = app.config.get("TESTING")
        original_debug = app.config.get("DEBUG")
        try:
            app.config["TESTING"] = False
            app.config["DEBUG"] = False
            os.environ.pop("RUNNING_MIGRATION", None)
            if hasattr(app, "scheduler"):
                del app.scheduler
            if hasattr(app, "_scheduler_lock"):
                del app._scheduler_lock

            from app.scheduler import init_scheduler

            captured = {}

            class CapturingThread:
                def __init__(self, target=None, daemon=None):
                    captured["target"] = target
                    self.daemon = daemon

                def start(self):
                    pass

            mock_scheduler = MagicMock()
            mock_scheduler.running = False

            with patch("app.scheduler.threading.Thread", CapturingThread):
                init_scheduler(app, is_reloader=False)

            assert "target" in captured

            # Now execute the task synchronously
            with patch("apscheduler.schedulers.background.BackgroundScheduler", return_value=mock_scheduler):
                with patch("app.scheduler.atexit.register"):
                    with patch("app.scheduler.os.getpid", return_value=12345):
                        with patch("time.sleep"):
                            captured["target"]()

            # Scheduler should have been started
            mock_scheduler.start.assert_called_once()
        finally:
            app.config["TESTING"] = original_testing
            app.config["DEBUG"] = original_debug
            if hasattr(app, "scheduler"):
                app.scheduler = None

    def test_scheduler_init_task_scheduler_already_initialized_inside_lock(self, app):
        """If scheduler is set before lock acquisition, skip initialization."""
        original_testing = app.config.get("TESTING")
        original_debug = app.config.get("DEBUG")
        try:
            app.config["TESTING"] = False
            app.config["DEBUG"] = False
            os.environ.pop("RUNNING_MIGRATION", None)
            if hasattr(app, "scheduler"):
                del app.scheduler
            if hasattr(app, "_scheduler_lock"):
                del app._scheduler_lock

            from app.scheduler import init_scheduler

            captured = {}

            class CapturingThread:
                def __init__(self, target=None, daemon=None):
                    captured["target"] = target

                def start(self):
                    pass

            with patch("app.scheduler.threading.Thread", CapturingThread):
                init_scheduler(app, is_reloader=False)

            # Set scheduler before running the task to simulate "already initialized"
            app.scheduler = MagicMock()

            with patch("apscheduler.schedulers.background.BackgroundScheduler") as mock_bg:
                with patch("time.sleep"):
                    captured["target"]()

            # BackgroundScheduler should not have been instantiated
            mock_bg.assert_not_called()
        finally:
            app.config["TESTING"] = original_testing
            app.config["DEBUG"] = original_debug
            if hasattr(app, "scheduler"):
                app.scheduler = None

    def test_scheduler_init_task_exception_resets_scheduler(self, app):
        """If an exception occurs in init task, app.scheduler is reset to None."""
        original_testing = app.config.get("TESTING")
        original_debug = app.config.get("DEBUG")
        try:
            app.config["TESTING"] = False
            app.config["DEBUG"] = False
            os.environ.pop("RUNNING_MIGRATION", None)
            if hasattr(app, "scheduler"):
                del app.scheduler
            if hasattr(app, "_scheduler_lock"):
                del app._scheduler_lock

            from app.scheduler import init_scheduler

            captured = {}

            class CapturingThread:
                def __init__(self, target=None, daemon=None):
                    captured["target"] = target

                def start(self):
                    pass

            with patch("app.scheduler.threading.Thread", CapturingThread):
                init_scheduler(app, is_reloader=False)

            with patch(
                "apscheduler.schedulers.background.BackgroundScheduler",
                side_effect=ImportError("apscheduler not installed"),
            ):
                with patch("time.sleep"):
                    captured["target"]()

            assert getattr(app, "scheduler", None) is None
        finally:
            app.config["TESTING"] = original_testing
            app.config["DEBUG"] = original_debug
            if hasattr(app, "scheduler"):
                app.scheduler = None

    def test_scheduler_already_running_skips_start(self, app):
        """If scheduler.running is True after setup, don't call start()."""
        original_testing = app.config.get("TESTING")
        original_debug = app.config.get("DEBUG")
        try:
            app.config["TESTING"] = False
            app.config["DEBUG"] = False
            os.environ.pop("RUNNING_MIGRATION", None)
            if hasattr(app, "scheduler"):
                del app.scheduler
            if hasattr(app, "_scheduler_lock"):
                del app._scheduler_lock

            from app.scheduler import init_scheduler

            captured = {}

            class CapturingThread:
                def __init__(self, target=None, daemon=None):
                    captured["target"] = target

                def start(self):
                    pass

            mock_scheduler = MagicMock()
            mock_scheduler.running = True  # already running

            with patch("app.scheduler.threading.Thread", CapturingThread):
                init_scheduler(app, is_reloader=False)

            with patch("apscheduler.schedulers.background.BackgroundScheduler", return_value=mock_scheduler):
                with patch("app.scheduler.atexit.register"):
                    with patch("time.sleep"):
                        captured["target"]()

            mock_scheduler.start.assert_not_called()
        finally:
            app.config["TESTING"] = original_testing
            app.config["DEBUG"] = original_debug
            if hasattr(app, "scheduler"):
                app.scheduler = None

    def test_misfire_grace_seconds_invalid_value_uses_default(self, app):
        """Invalid SCHEDULER_MISFIRE_GRACE_SECONDS falls back to 30."""
        original_testing = app.config.get("TESTING")
        original_debug = app.config.get("DEBUG")
        original_grace = app.config.get("SCHEDULER_MISFIRE_GRACE_SECONDS")
        try:
            app.config["TESTING"] = False
            app.config["DEBUG"] = False
            app.config["SCHEDULER_MISFIRE_GRACE_SECONDS"] = "not-a-number"
            os.environ.pop("RUNNING_MIGRATION", None)
            if hasattr(app, "scheduler"):
                del app.scheduler
            if hasattr(app, "_scheduler_lock"):
                del app._scheduler_lock

            from app.scheduler import init_scheduler

            captured = {}

            class CapturingThread:
                def __init__(self, target=None, daemon=None):
                    captured["target"] = target

                def start(self):
                    pass

            mock_scheduler = MagicMock()
            mock_scheduler.running = False

            with patch("app.scheduler.threading.Thread", CapturingThread):
                init_scheduler(app, is_reloader=False)

            with patch("apscheduler.schedulers.background.BackgroundScheduler", return_value=mock_scheduler) as mock_bg:
                with patch("app.scheduler.atexit.register"):
                    with patch("time.sleep"):
                        captured["target"]()

            # BackgroundScheduler was called with job_defaults containing misfire_grace_time=30
            mock_bg.assert_called_once()
            call_kwargs = mock_bg.call_args[1]
            assert call_kwargs["job_defaults"]["misfire_grace_time"] == 30
        finally:
            app.config["TESTING"] = original_testing
            app.config["DEBUG"] = original_debug
            if original_grace is not None:
                app.config["SCHEDULER_MISFIRE_GRACE_SECONDS"] = original_grace
            else:
                app.config.pop("SCHEDULER_MISFIRE_GRACE_SECONDS", None)
            if hasattr(app, "scheduler"):
                app.scheduler = None


# ===========================================================================
# Scheduled job inner functions (coverage of closures)
# ===========================================================================

class TestScheduledJobInnerFunctions:
    """
    Execute the closures added as scheduler jobs to cover their code paths.
    The closures are created inside scheduler_init_task; we capture them via
    the BackgroundScheduler.add_job mock.
    """

    def _run_init_and_capture_jobs(self, app):
        """Returns a dict {job_id: func} of all registered job functions."""
        from app.scheduler import init_scheduler

        original_testing = app.config.get("TESTING")
        original_debug = app.config.get("DEBUG")
        try:
            app.config["TESTING"] = False
            app.config["DEBUG"] = False
            os.environ.pop("RUNNING_MIGRATION", None)
            if hasattr(app, "scheduler"):
                del app.scheduler
            if hasattr(app, "_scheduler_lock"):
                del app._scheduler_lock

            jobs = {}
            captured = {}

            class CapturingThread:
                def __init__(self, target=None, daemon=None):
                    captured["target"] = target

                def start(self):
                    pass

            mock_scheduler = MagicMock()
            mock_scheduler.running = False

            def capture_add_job(func, trigger, id, **kwargs):
                jobs[id] = func

            mock_scheduler.add_job.side_effect = capture_add_job

            with patch("app.scheduler.threading.Thread", CapturingThread):
                init_scheduler(app, is_reloader=False)

            with patch(
                "apscheduler.schedulers.background.BackgroundScheduler",
                return_value=mock_scheduler,
            ):
                with patch("app.scheduler.atexit.register"):
                    with patch("time.sleep"):
                        captured["target"]()

            return jobs
        finally:
            app.config["TESTING"] = original_testing
            app.config["DEBUG"] = original_debug
            if hasattr(app, "scheduler"):
                app.scheduler = None

    def test_cleanup_notifications_success(self, app):
        jobs = self._run_init_and_capture_jobs(app)
        fn = jobs.get("cleanup_notifications")
        assert fn is not None

        with patch("app.utils.transactions.atomic") as mock_atomic:
            mock_atomic.return_value.__enter__ = MagicMock(return_value=None)
            mock_atomic.return_value.__exit__ = MagicMock(return_value=False)
            with patch("app.utils.notifications.cleanup_old_notifications"):
                fn()  # should not raise

    def test_cleanup_notifications_exception(self, app):
        jobs = self._run_init_and_capture_jobs(app)
        fn = jobs.get("cleanup_notifications")
        assert fn is not None

        with patch("app.utils.notifications.cleanup_old_notifications", side_effect=Exception("db error")):
            fn()  # exception is caught and logged

    def test_cleanup_sessions_success(self, app):
        jobs = self._run_init_and_capture_jobs(app)
        fn = jobs.get("cleanup_inactive_sessions")
        assert fn is not None

        with patch("app.services.user_analytics_service.cleanup_inactive_sessions", return_value=3):
            fn()

    def test_cleanup_sessions_exception(self, app):
        jobs = self._run_init_and_capture_jobs(app)
        fn = jobs.get("cleanup_inactive_sessions")

        with patch(
            "app.services.user_analytics_service.cleanup_inactive_sessions",
            side_effect=Exception("session table missing"),
        ):
            fn()  # should be caught

    def test_retry_failed_emails_success(self, app):
        jobs = self._run_init_and_capture_jobs(app)
        fn = jobs.get("retry_failed_emails")
        assert fn is not None

        mock_log = MagicMock()
        with patch("app.services.email.delivery.get_pending_retries", return_value=[mock_log]):
            with patch("app.services.notification.emails.retry_email_delivery_log"):
                fn()

    def test_retry_failed_emails_exception(self, app):
        jobs = self._run_init_and_capture_jobs(app)
        fn = jobs.get("retry_failed_emails")

        with patch(
            "app.services.email.delivery.get_pending_retries",
            side_effect=Exception("conn reset"),
        ):
            fn()  # should be caught

    def test_send_digest_emails_success(self, app):
        jobs = self._run_init_and_capture_jobs(app)
        fn = jobs.get("check_and_send_digest_emails")
        assert fn is not None

        with patch("app.services.notification.emails.send_notification_emails"):
            fn()

    def test_send_digest_emails_exception(self, app):
        jobs = self._run_init_and_capture_jobs(app)
        fn = jobs.get("check_and_send_digest_emails")

        with patch(
            "app.services.notification.emails.send_notification_emails",
            side_effect=Exception("smtp down"),
        ):
            fn()  # should be caught

    def test_process_scheduled_notifications_success_with_processed(self, app):
        jobs = self._run_init_and_capture_jobs(app)
        fn = jobs.get("process_scheduled_notifications")
        assert fn is not None

        with patch(
            "app.services.notification.scheduling.process_scheduled_notifications",
            return_value=5,
        ):
            fn()

    def test_process_scheduled_notifications_success_zero(self, app):
        jobs = self._run_init_and_capture_jobs(app)
        fn = jobs.get("process_scheduled_notifications")

        with patch(
            "app.services.notification.scheduling.process_scheduled_notifications",
            return_value=0,
        ):
            fn()

    def test_process_scheduled_notifications_exception(self, app):
        jobs = self._run_init_and_capture_jobs(app)
        fn = jobs.get("process_scheduled_notifications")

        with patch(
            "app.services.notification.scheduling.process_scheduled_notifications",
            side_effect=Exception("queue error"),
        ):
            fn()  # should be caught

    def test_cleanup_stale_websockets_success_with_cleaned(self, app):
        jobs = self._run_init_and_capture_jobs(app)
        fn = jobs.get("cleanup_stale_websockets")
        assert fn is not None

        mock_ws_manager = MagicMock()
        mock_ws_manager.cleanup_stale_connections.return_value = 3
        with patch("app.utils.ws_manager.ws_manager", mock_ws_manager):
            fn()

    def test_cleanup_stale_websockets_success_zero_cleaned(self, app):
        jobs = self._run_init_and_capture_jobs(app)
        fn = jobs.get("cleanup_stale_websockets")

        mock_ws_manager = MagicMock()
        mock_ws_manager.cleanup_stale_connections.return_value = 0
        with patch("app.utils.ws_manager.ws_manager", mock_ws_manager):
            fn()

    def test_cleanup_stale_websockets_exception(self, app):
        jobs = self._run_init_and_capture_jobs(app)
        fn = jobs.get("cleanup_stale_websockets")

        with patch(
            "app.utils.ws_manager.ws_manager",
            side_effect=Exception("ws module not loaded"),
        ):
            fn()  # should be caught
