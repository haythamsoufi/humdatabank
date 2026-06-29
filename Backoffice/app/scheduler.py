"""Background task scheduler initialization."""

import atexit
import os
import tempfile
import threading
import time as _time


def _graceful_shutdown(scheduler, app):
    """Shut down APScheduler before the thread-pool executor is torn down.

    Registered via atexit so it runs ahead of concurrent.futures' own
    atexit handler (LIFO order), preventing the
    'cannot schedule new futures after shutdown' RuntimeError that occurs
    when Gunicorn recycles workers (max_requests) or during normal exit.

    wait=True: shutdown must not return until the scheduler thread and its
    executor are fully stopped. wait=False was racing: the default pool can be
    closed while the scheduler loop is still calling submit() for the next job.
    """
    try:
        if scheduler.running:
            scheduler.shutdown(wait=True)
    except Exception:
        pass
    finally:
        try:
            app.scheduler = None
        except Exception:
            pass


def _is_scheduler_worker() -> bool:
    """Return True if this worker process should run the background scheduler.

    In a multi-worker gunicorn deployment every forked worker process calls
    init_scheduler independently (preload_app=False).  Running APScheduler in
    *every* worker means the same maintenance jobs (email retry, session
    cleanup, notification dispatch) fire N times per interval — once per
    worker — causing redundant DB writes, duplicate emails, and unnecessary
    connection-pool pressure that contributes to 502/504 errors.

    Strategy (lowest-ops-overhead):
      1. If SCHEDULER_WORKER_ONLY_PID is set (injected by a pre_exec/post_fork
         hook or the startup script), only the matching PID runs the scheduler.
      2. Otherwise, only the lowest-numbered gunicorn worker runs it, detected
         by writing a lock file keyed on the gunicorn master PID.  The first
         worker to create the file wins; all subsequent workers skip init.
      3. SCHEDULER_DISABLE_ALL_WORKERS=true disables in every worker (use when
         jobs are handled by an external Azure Function / Container Job).
    """
    if os.environ.get('SCHEDULER_DISABLE_ALL_WORKERS', '').strip().lower() in ('1', 'true', 'yes'):
        return False

    only_pid_env = os.environ.get('SCHEDULER_WORKER_ONLY_PID', '').strip()
    if only_pid_env:
        try:
            return os.getpid() == int(only_pid_env)
        except ValueError:
            pass

    # Lock-file strategy: first worker to create the file wins.
    master_pid = os.getppid()  # gunicorn worker's parent = master process
    lock_path = os.path.join(tempfile.gettempdir(), f'hdb_scheduler_{master_pid}.lock')
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True  # this worker created the lock — it owns the scheduler
    except FileExistsError:
        return False  # another worker already owns the scheduler
    except OSError:
        # Filesystem issue — fall back to allowing this worker (conservative)
        return True


def _run_scheduled_job(app, label: str, fn) -> None:
    """Execute fn inside an app context with standardised error handling and duration logging.

    All scheduler jobs should be invoked through this helper so that:
    - Each run gets a fresh app context (and therefore a fresh scoped DB session).
      Flask-SQLAlchemy tears down the scoped session — returning the connection
      to the pool — automatically when the app context exits, so DB connections
      are never held longer than the job body.
    - Unhandled exceptions are caught, logged with exc_info, and never propagate
      into APScheduler's thread pool (where a bare raise would silence future runs).
    - Jobs taking ≥2 s are surfaced as INFO; ≥30 s as WARNING for alerting.

    Note: job bodies (fn) must manage their own transactions. They should NOT
    be wrapped in atomic() externally — that would commit an already-committed
    session and, for email jobs, hold the connection open during HTTP sends.
    """
    t0 = _time.monotonic()
    try:
        with app.app_context():
            fn()
    except Exception as exc:
        app.logger.error("Scheduled job '%s' failed: %s", label, exc, exc_info=True)
    finally:
        elapsed = _time.monotonic() - t0
        if elapsed >= 30.0:
            app.logger.warning("Scheduled job '%s' took %.2fs", label, elapsed)
        elif elapsed >= 2.0:
            app.logger.info("Scheduled job '%s' took %.2fs", label, elapsed)
        else:
            app.logger.debug("Scheduled job '%s' took %.2fs", label, elapsed)


def init_scheduler(app, is_reloader):
    """Initialize the APScheduler background scheduler for periodic tasks."""
    from app.utils.constants import SESSION_INACTIVITY_SECONDS

    should_init = (
        not app.config.get('TESTING', False)
        and not os.environ.get('RUNNING_MIGRATION')
        and (not app.debug or is_reloader)
        and _is_scheduler_worker()
    )

    if not should_init:
        return

    if hasattr(app, 'scheduler') and app.scheduler is not None:
        app.logger.debug("Scheduler already exists, skipping initialization")
        return

    if not hasattr(app, '_scheduler_lock'):
        app._scheduler_lock = threading.Lock()

    def scheduler_init_task():
        try:
            _time.sleep(0.1)
            with app.app_context():
                with app._scheduler_lock:
                    if hasattr(app, 'scheduler') and app.scheduler is not None:
                        app.logger.debug("Scheduler already initialized, skipping")
                        return

                    from apscheduler.schedulers.background import BackgroundScheduler
                    try:
                        misfire_grace_seconds = int(app.config.get('SCHEDULER_MISFIRE_GRACE_SECONDS', 30))
                    except (TypeError, ValueError):
                        misfire_grace_seconds = 30

                    scheduler = BackgroundScheduler(job_defaults={
                        'coalesce': True,
                        'max_instances': 1,
                        'misfire_grace_time': max(1, misfire_grace_seconds),
                    })
                    app.scheduler = scheduler

                    # ── job bodies ────────────────────────────────────────────────────
                    # Each function is a plain callable with no app-context boilerplate —
                    # _run_scheduled_job provides the context, error handling, and timing.

                    def _cleanup_notifications():
                        from app.utils.notifications import cleanup_old_notifications
                        cleanup_old_notifications()

                    def _cleanup_sessions():
                        from app.services.user_analytics_service import cleanup_inactive_sessions
                        cleanup_inactive_sessions()

                    # Automatic email retries removed — admins retry from Communication Center.

                    def _send_digest_emails():
                        from app.services.notification.emails import send_notification_emails
                        send_notification_emails()

                    def _send_fds_access_request_digests():
                        from app.utils.datetime_helpers import now_in_org_timezone
                        from app.services.app_settings_service import (
                            get_fds_access_request_digest_enabled,
                            get_fds_access_request_digest_local_hour,
                        )
                        if not get_fds_access_request_digest_enabled():
                            return
                        if now_in_org_timezone().hour != get_fds_access_request_digest_local_hour():
                            return
                        from app.services.email.fds_access_request_digest import send_fds_access_request_digests
                        sent = send_fds_access_request_digests()
                        if sent > 0:
                            app.logger.info(
                                "Sent %d FDS access request digest email(s)", sent
                            )

                    def _process_scheduled_notifications():
                        from app.services.notification.scheduling import process_scheduled_notifications
                        processed = process_scheduled_notifications()
                        if processed > 0:
                            app.logger.info("Processed %d scheduled notification(s)", processed)

                    def _cleanup_stale_websockets():
                        # Purely in-memory — no DB connection needed.
                        # Own try/except so APScheduler never loses the job on error.
                        try:
                            from app.utils.ws_manager import ws_manager
                            cleaned = ws_manager.cleanup_stale_connections(
                                max_idle_seconds=float(SESSION_INACTIVITY_SECONDS)
                            )
                            if cleaned > 0:
                                app.logger.info("Cleaned up %d stale WebSocket connections", cleaned)
                        except Exception as exc:
                            app.logger.error("Scheduled WebSocket cleanup failed: %s", exc)

                    # ── job registration ──────────────────────────────────────────────

                    scheduler.add_job(
                        func=lambda: _run_scheduled_job(app, 'cleanup_notifications', _cleanup_notifications),
                        trigger="cron", hour=2, minute=0,
                        id='cleanup_notifications', name='Cleanup old notifications',
                        replace_existing=True
                    )

                    scheduler.add_job(
                        func=lambda: _run_scheduled_job(app, 'cleanup_sessions', _cleanup_sessions),
                        trigger="interval", minutes=60,
                        id='cleanup_inactive_sessions', name='Cleanup inactive user sessions',
                        replace_existing=True
                    )

                    try:
                        digest_interval = max(1, int(
                            app.config.get('SCHEDULER_DIGEST_EMAIL_INTERVAL_MINUTES', 5)
                        ))
                    except (TypeError, ValueError):
                        digest_interval = 5

                    scheduler.add_job(
                        func=lambda: _run_scheduled_job(app, 'send_digest_emails', _send_digest_emails),
                        trigger="interval", minutes=digest_interval,
                        id='check_and_send_digest_emails', name='Send notification digest emails',
                        replace_existing=True
                    )

                    scheduler.add_job(
                        func=lambda: _run_scheduled_job(
                            app, 'send_fds_access_request_digests', _send_fds_access_request_digests
                        ),
                        trigger="cron", minute=0,
                        id='send_fds_access_request_digests',
                        name='Send FDS access request digest emails',
                        replace_existing=True
                    )

                    scheduler.add_job(
                        func=lambda: _run_scheduled_job(
                            app, 'process_scheduled_notifications', _process_scheduled_notifications
                        ),
                        trigger="interval", minutes=1,
                        id='process_scheduled_notifications', name='Process scheduled notifications',
                        replace_existing=True
                    )

                    # WebSocket cleanup is purely in-memory — registered directly so it
                    # runs without opening a DB connection at all.
                    scheduler.add_job(
                        func=_cleanup_stale_websockets,
                        trigger="interval", minutes=5,
                        id='cleanup_stale_websockets', name='Cleanup stale WebSocket connections',
                        replace_existing=True
                    )

                    if not scheduler.running:
                        scheduler.start()
                        atexit.register(_graceful_shutdown, scheduler, app)
                        process_id = os.getpid()
                        app.logger.debug("Background scheduler started [PID: %d]", process_id)
                    else:
                        app.logger.debug("Scheduler was already running")

        except Exception as e:
            app.logger.warning("Could not start notification scheduler: %s", e)
            if hasattr(app, 'scheduler'):
                app.scheduler = None

    scheduler_thread = threading.Thread(target=scheduler_init_task, daemon=True)
    scheduler_thread.start()
    app.logger.debug("Notification cleanup scheduler initialization deferred to background thread")
