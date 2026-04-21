"""Background task scheduler initialization."""

import atexit
import os
import threading


def _graceful_shutdown(scheduler, app):
    """Shut down APScheduler before the thread-pool executor is torn down.

    Registered via atexit so it runs ahead of concurrent.futures' own
    atexit handler (LIFO order), preventing the
    'cannot schedule new futures after shutdown' RuntimeError that occurs
    when Gunicorn recycles workers (max_requests) or during normal exit.
    """
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception:
        pass
    finally:
        try:
            app.scheduler = None
        except Exception:
            pass


def init_scheduler(app, is_reloader):
    """Initialize the APScheduler background scheduler for periodic tasks."""
    from app.utils.constants import SESSION_INACTIVITY_SECONDS

    should_init = (
        not app.config.get('TESTING', False)
        and not os.environ.get('RUNNING_MIGRATION')
        and (not app.debug or is_reloader)
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
            import time
            time.sleep(0.1)
            with app.app_context():
                with app._scheduler_lock:
                    if hasattr(app, 'scheduler') and app.scheduler is not None:
                        app.logger.debug("Scheduler already initialized, skipping")
                        return

                    from apscheduler.schedulers.background import BackgroundScheduler
                    scheduler = BackgroundScheduler()
                    app.scheduler = scheduler

                    def _cleanup_notifications_with_context():
                        with app.app_context():
                            try:
                                from app.utils.transactions import atomic
                                from app.utils.notifications import cleanup_old_notifications
                                with atomic(remove_session=True):
                                    cleanup_old_notifications()
                            except Exception as _e:
                                app.logger.error(f"Scheduled notifications cleanup failed: {_e}")

                    def _cleanup_sessions_with_context():
                        with app.app_context():
                            try:
                                from app.utils.transactions import atomic
                                from app.services.user_analytics_service import cleanup_inactive_sessions
                                with atomic(remove_session=True):
                                    cleanup_inactive_sessions()
                            except Exception as _e:
                                app.logger.error(f"Scheduled session cleanup failed: {_e}")

                    scheduler.add_job(
                        func=_cleanup_notifications_with_context,
                        trigger="cron", hour=2, minute=0,
                        id='cleanup_notifications', replace_existing=True
                    )

                    scheduler.add_job(
                        func=_cleanup_sessions_with_context,
                        trigger="interval", minutes=60,
                        id='cleanup_inactive_sessions', replace_existing=True
                    )

                    def _retry_failed_emails_with_context():
                        with app.app_context():
                            try:
                                from app.utils.transactions import atomic
                                from app.services.email.delivery import get_pending_retries
                                from app.services.notification.emails import retry_email_delivery_log
                                with atomic(remove_session=True):
                                    pending = get_pending_retries()
                                    for log in pending:
                                        retry_email_delivery_log(log)
                            except Exception as _e:
                                app.logger.error(f"Scheduled email retry job failed: {_e}")

                    scheduler.add_job(
                        func=_retry_failed_emails_with_context,
                        trigger="interval", minutes=15,
                        id='retry_failed_emails', replace_existing=True
                    )

                    def _send_digest_emails_with_context():
                        with app.app_context():
                            try:
                                from app.utils.transactions import atomic
                                from app.services.notification.emails import send_notification_emails
                                with atomic(remove_session=True):
                                    send_notification_emails()
                            except Exception as e:
                                app.logger.error(f"Scheduled digest email job failed: {e}", exc_info=True)

                    scheduler.add_job(
                        func=_send_digest_emails_with_context,
                        trigger="interval", minutes=1,
                        id='check_and_send_digest_emails', replace_existing=True
                    )

                    def _process_scheduled_notifications_with_context():
                        with app.app_context():
                            try:
                                from app.utils.transactions import atomic
                                from app.services.notification.scheduling import process_scheduled_notifications
                                with atomic(remove_session=True):
                                    processed = process_scheduled_notifications()
                                if processed > 0:
                                    app.logger.info(f"Processed {processed} scheduled notification(s)")
                            except Exception as e:
                                app.logger.error(f"Scheduled notification processor failed: {e}", exc_info=True)

                    scheduler.add_job(
                        func=_process_scheduled_notifications_with_context,
                        trigger="interval", minutes=1,
                        id='process_scheduled_notifications', replace_existing=True
                    )

                    def _cleanup_stale_websockets_with_context():
                        with app.app_context():
                            try:
                                from app.utils.ws_manager import ws_manager
                                cleaned = ws_manager.cleanup_stale_connections(max_idle_seconds=float(SESSION_INACTIVITY_SECONDS))
                                if cleaned > 0:
                                    app.logger.info(f"Cleaned up {cleaned} stale WebSocket connections")
                            except Exception as _e:
                                app.logger.error(f"Scheduled WebSocket cleanup failed: {_e}")

                    scheduler.add_job(
                        func=_cleanup_stale_websockets_with_context,
                        trigger="interval", minutes=5,
                        id='cleanup_stale_websockets', replace_existing=True
                    )

                    if not scheduler.running:
                        scheduler.start()
                        atexit.register(_graceful_shutdown, scheduler, app)
                        process_id = os.getpid()
                        app.logger.debug(f"Background scheduler started [PID: {process_id}]")
                    else:
                        app.logger.debug("Scheduler was already running")

        except Exception as e:
            app.logger.warning(f"Could not start notification scheduler: {e}")
            if hasattr(app, 'scheduler'):
                app.scheduler = None

    scheduler_thread = threading.Thread(target=scheduler_init_task, daemon=True)
    scheduler_thread.start()
    app.logger.debug("Notification cleanup scheduler initialization deferred to background thread")
