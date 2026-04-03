import os
import logging

# IMPORTANT: gevent monkey-patching must happen BEFORE importing the app (and any
# libraries that import `ssl` / networking modules like `urllib3` / `jwt`).
# Otherwise gevent will warn and can misbehave in edge cases.
#
# In this repo, gevent is kept as an *opt-in* server for debugging WebSockets on
# Windows (the Flask dev server and Waitress are not suitable for HTTP Upgrade).
# Production deployments should use Gunicorn (see entrypoint/Docker/Azure config).
def _should_use_gevent() -> bool:
    """Return True if this process should run using gevent."""
    # Explicit opt-in (env: true/false only)
    if str(os.environ.get("USE_GEVENT_DEV", "false")).strip().lower() == "true":
        return True
    if str(os.environ.get("USE_GEVENT", "false")).strip().lower() == "true":
        return True

    # Default: do NOT auto-enable gevent. Flask dev server should be the normal
    # development experience; gevent is only for explicit WS debugging sessions.
    return False


def _running_from_flask_cli() -> bool:
    """
    True when the process is started via `flask run` / Flask CLI.

    Why this matters:
    - Flask-Sock (via simple-websocket) uses a background *thread* for socket recv().
    - If we gevent-monkeypatch sockets in this process, that thread can crash with:
      `greenlet.error: Cannot switch to a different thread`.
    - Therefore, only apply gevent monkey-patching when we are actually going to run
      the gevent server (e.g., `python run.py`), not when Werkzeug will own the server.
    """
    return str(os.environ.get("FLASK_RUN_FROM_CLI", "")).strip().lower() == "true"


if _should_use_gevent() and not _running_from_flask_cli():
    try:
        from gevent import monkey

        # IMPORTANT:
        # Flask-Sock uses `simple-websocket`, which performs socket recv in a background
        # *thread* on some servers. If we monkey-patch stdlib sockets here, that thread
        # may call into gevent's hub and crash with:
        #   greenlet.error: Cannot switch to a different thread
        #
        # In this project we primarily use gevent as a WS-capable dev server on Windows.
        # The gevent server itself does not require stdlib socket monkey-patching to run.
        # So we intentionally do NOT patch socket/ssl/thread.
        monkey.patch_all(socket=False, ssl=False, thread=False)
    except Exception as e:
        logging.getLogger(__name__).debug("gevent monkey-patch failed: %s", e)
        # If gevent isn't available (or patching fails), continue unpatched.
        # The server-startup logic will fall back to non-gevent servers.
        pass
elif _should_use_gevent() and _running_from_flask_cli():
    # Avoid crashing WebSocket threads under Werkzeug/simple-websocket.
    logging.getLogger(__name__).warning(
        "USE_GEVENT* is enabled but you're running via Flask CLI (Werkzeug). "
        "Skipping gevent monkey-patching to avoid `greenlet.error: Cannot switch to a different thread`. "
        "If you need WebSockets on Windows, start the dev server with `python run.py` "
        "(and ensure `gevent-websocket` is installed)."
    )

from app import create_app, db
import click
from flask.cli import with_appcontext
from app.models import User, Country
from app.utils.transactions import atomic
from app.services.ai_chat_retention import maintain_ai_chat_retention

# Create the Flask app instance
# Use FLASK_CONFIG from environment (loaded via config) to select config;
# falls back to 'default' (DevelopmentConfig) inside create_app when unset
app = create_app(os.getenv('FLASK_CONFIG'))

# Logging configuration is now handled centrally in app/__init__.py
# This ensures consistent logging levels across the entire application

@app.cli.command()
@with_appcontext
def cleanup_sessions():
    """Clean up inactive and expired sessions."""
    from app.utils.user_analytics import cleanup_inactive_sessions

    try:
        count = cleanup_inactive_sessions()
        click.echo(f"Cleaned up {count} inactive sessions.")
        return count
    except Exception as e:
        click.echo(f"Error during session cleanup: {str(e)}")
        return 0

@app.cli.command()
@with_appcontext
def cleanup_sessions_now():
    """Immediately clean up all inactive sessions with detailed output."""
    from app.utils.user_analytics import cleanup_inactive_sessions
    from app.models import UserSessionLog
    from datetime import datetime, timedelta

    try:
        # Show current state
        total_sessions = UserSessionLog.query.count()
        active_sessions = UserSessionLog.query.filter(UserSessionLog.is_active == True).count()

        click.echo(f"Before cleanup:")
        click.echo(f"  Total sessions: {total_sessions}")
        click.echo(f"  Active sessions: {active_sessions}")

        # Show sessions that will be cleaned up
        inactivity_cutoff = datetime.utcnow() - timedelta(hours=2)
        max_duration_cutoff = datetime.utcnow() - timedelta(hours=8)

        inactive_sessions = UserSessionLog.query.filter(
            UserSessionLog.is_active == True,
            UserSessionLog.last_activity < inactivity_cutoff
        ).all()

        long_sessions = UserSessionLog.query.filter(
            UserSessionLog.is_active == True,
            UserSessionLog.session_start < max_duration_cutoff
        ).all()

        sessions_to_close = set(inactive_sessions + long_sessions)

        if sessions_to_close:
            click.echo(f"\nSessions to be cleaned up:")
            for session_log in sessions_to_close:
                user_email = session_log.user.email if session_log.user else "Unknown"
                hours_since_activity = (datetime.utcnow() - session_log.last_activity).total_seconds() / 3600
                click.echo(f"  - User: {user_email}, Last activity: {hours_since_activity:.1f} hours ago")

        # Run cleanup
        count = cleanup_inactive_sessions()

        # Show results
        active_sessions_after = UserSessionLog.query.filter(UserSessionLog.is_active == True).count()

        click.echo(f"\nCleanup completed:")
        click.echo(f"  Sessions cleaned up: {count}")
        click.echo(f"  Active sessions remaining: {active_sessions_after}")

        return count
    except Exception as e:
        click.echo(f"Error during session cleanup: {str(e)}")
        return 0

@app.cli.command()
@with_appcontext
def create_admin():
    """Create the first admin user."""
    email = click.prompt("Admin email")
    password = click.prompt("Admin password", hide_input=True)
    name = click.prompt("Admin name", default="Administrator")

    # Check if user already exists
    if User.query.filter_by(email=email).first():
        click.echo(f"User with email {email} already exists!")
        return

    # Create admin user (RBAC-only)
    admin = User(email=email, name=name)
    admin.set_password(password)

    # Assign all countries to admin
    countries = Country.query.all()
    for country in countries:
        admin.countries.append(country)

    with atomic(remove_session=True):
        db.session.add(admin)
        db.session.flush()

        # Assign RBAC admin role (best-effort)
        try:
            from app.models.rbac import RbacRole, RbacUserRole
            admin_role = RbacRole.query.filter_by(code="admin_core").first()
            if not admin_role:
                admin_role = RbacRole(code="admin_core", name="Admin (Core)", description="Baseline admin role")
                db.session.add(admin_role)
                db.session.flush()
            db.session.add(RbacUserRole(user_id=admin.id, role_id=admin_role.id))
        except Exception as e:
            logging.getLogger(__name__).debug("RBAC admin role assignment failed: %s", e)

    click.echo(f"Admin user {email} created successfully!")

@app.cli.command()
@with_appcontext
def force_cleanup_old_sessions():
    """Force cleanup of all sessions older than 1 hour, regardless of activity."""
    from app.utils.user_analytics import cleanup_inactive_sessions
    from app.models import UserSessionLog
    from datetime import datetime, timedelta

    try:
        # Show current state
        total_sessions = UserSessionLog.query.count()
        active_sessions = UserSessionLog.query.filter(UserSessionLog.is_active == True).count()

        click.echo(f"Before force cleanup:")
        click.echo(f"  Total sessions: {total_sessions}")
        click.echo(f"  Active sessions: {active_sessions}")

        # Show all active sessions with details
        active_session_details = UserSessionLog.query.filter(UserSessionLog.is_active == True).all()
        click.echo(f"\nActive session details:")
        for session_log in active_session_details:
            user_email = session_log.user.email if session_log.user else "Unknown"
            hours_since_start = (datetime.utcnow() - session_log.session_start).total_seconds() / 3600
            hours_since_activity = (datetime.utcnow() - session_log.last_activity).total_seconds() / 3600
            click.echo(f"  - User: {user_email}")
            click.echo(f"    Session start: {session_log.session_start}")
            click.echo(f"    Last activity: {session_log.last_activity}")
            click.echo(f"    Hours since start: {hours_since_start:.1f}")
            click.echo(f"    Hours since activity: {hours_since_activity:.1f}")
            click.echo()

        # Force cleanup with very aggressive timeouts (1 hour inactivity, 2 hours max)
        count = cleanup_inactive_sessions(inactivity_hours=1, max_session_hours=2)

        # Show results
        active_sessions_after = UserSessionLog.query.filter(UserSessionLog.is_active == True).count()

        click.echo(f"Force cleanup completed:")
        click.echo(f"  Sessions cleaned up: {count}")
        click.echo(f"  Active sessions remaining: {active_sessions_after}")

        return count
    except Exception as e:
        click.echo(f"Error during force cleanup: {str(e)}")
        return 0

@app.cli.command()
@with_appcontext
def show_all_sessions():
    """Show all sessions (active and inactive) with detailed information."""
    from app.models import UserSessionLog
    from datetime import datetime, timedelta

    try:
        click.echo("=== ALL SESSIONS IN DATABASE ===")

        all_sessions = UserSessionLog.query.order_by(UserSessionLog.session_start.desc()).all()

        click.echo(f"Total sessions in database: {len(all_sessions)}")

        active_count = 0
        inactive_count = 0

        for session_log in all_sessions:
            user_email = session_log.user.email if session_log.user else "Unknown"
            hours_since_start = (datetime.utcnow() - session_log.session_start).total_seconds() / 3600
            hours_since_activity = (datetime.utcnow() - session_log.last_activity).total_seconds() / 3600

            status = "ACTIVE" if session_log.is_active else "INACTIVE"
            if session_log.is_active:
                active_count += 1
            else:
                inactive_count += 1

            click.echo(f"\n{status} - User: {user_email}")
            click.echo(f"  Session ID: {session_log.session_id}")
            click.echo(f"  Session start: {session_log.session_start}")
            click.echo(f"  Last activity: {session_log.last_activity}")
            click.echo(f"  Hours since start: {hours_since_start:.1f}")
            click.echo(f"  Hours since activity: {hours_since_activity:.1f}")
            if not session_log.is_active:
                click.echo(f"  Ended by: {session_log.ended_by}")
                click.echo(f"  Duration: {session_log.duration_minutes} minutes")

        click.echo(f"\nSummary:")
        click.echo(f"  Active sessions: {active_count}")
        click.echo(f"  Inactive sessions: {inactive_count}")

        # Ask if user wants to force cleanup
        if active_count > 0:
            click.echo(f"\nWould you like to force cleanup of all {active_count} active sessions? (y/N)")

    except Exception as e:
        click.echo(f"Error showing sessions: {str(e)}")

@app.cli.command()
@click.option('--enable/--disable', default=True, help='Enable or disable debug logging')
@with_appcontext
def toggle_debug_logging(enable):
    """Toggle debug logging for application components at runtime."""
    from app.utils.debug_utils import debug_manager

    debug_manager.set_debug_mode(enable)
    status = "enabled" if enable else "disabled"
    click.echo(f"Debug logging {status} for all application components")

    if enable:
        click.echo("Debug logging features now available:")
        click.echo("  - Performance monitoring")
        click.echo("  - Detailed form data logging")
        click.echo("  - Database query tracking")
        click.echo("  - Enhanced error context")

@app.cli.command()
@with_appcontext
def show_performance_stats():
    """Show performance statistics for monitored operations."""
    from app.utils.debug_utils import get_performance_stats

    stats = get_performance_stats()

    if not stats:
        click.echo("No performance data available. Enable debug logging to collect performance metrics.")
        return

    click.echo("=== PERFORMANCE STATISTICS ===")
    click.echo()

    for operation, data in stats.items():
        click.echo(f"Operation: {operation}")
        click.echo(f"  Total calls: {data['count']}")
        click.echo(f"  Average time: {data['avg_time']:.3f}s")
        click.echo(f"  Max time: {data['max_time']:.3f}s")
        click.echo(f"  Min time: {data['min_time']:.3f}s")
        click.echo(f"  Total time: {data['total_time']:.3f}s")
        click.echo()


@app.cli.command("migrate-uploads-to-azure")
@click.option('--dry-run', is_flag=True, default=False, help='Show what would be uploaded without actually uploading.')
@click.option('--category', default=None, help='Only migrate a specific category (e.g. admin_documents, resources, submissions, system, ai_documents).')
@with_appcontext
def migrate_uploads_to_azure(dry_run, category):
    """Migrate files from the local UPLOAD_FOLDER to Azure Blob Storage.

    Walks UPLOAD_FOLDER, infers the storage category from the top-level subfolder name,
    and uploads each file via storage_service. Skips files that already exist in Blob.
    Requires UPLOAD_STORAGE_PROVIDER=azure_blob and AZURE_STORAGE_CONNECTION_STRING to be set.
    """
    from app.services import storage_service as _ss

    if not _ss.is_azure():
        click.echo("ERROR: UPLOAD_STORAGE_PROVIDER is not 'azure_blob'. Set AZURE_STORAGE_CONNECTION_STRING and ensure UPLOAD_STORAGE_PROVIDER=azure_blob.")
        return

    upload_folder = app.config.get('UPLOAD_FOLDER', '').strip()
    if not upload_folder or not os.path.isdir(upload_folder):
        click.echo(f"ERROR: UPLOAD_FOLDER '{upload_folder}' does not exist or is not a directory.")
        return

    known_categories = {_ss.ADMIN_DOCUMENTS, _ss.RESOURCES, _ss.SUBMISSIONS, _ss.SYSTEM, _ss.AI_DOCUMENTS}

    uploaded = skipped = errors = 0

    for root, _dirs, files in os.walk(upload_folder):
        for fname in files:
            abs_path = os.path.join(root, fname)
            # Build the path relative to UPLOAD_FOLDER using forward slashes
            rel_from_base = os.path.relpath(abs_path, upload_folder).replace('\\', '/')
            parts = rel_from_base.split('/', 1)
            if len(parts) < 2:
                click.echo(f"  SKIP (no category subfolder): {rel_from_base}")
                skipped += 1
                continue

            cat = parts[0]
            rel_path = parts[1]

            if category and cat != category:
                continue

            if cat not in known_categories:
                click.echo(f"  SKIP (unknown category '{cat}'): {rel_from_base}")
                skipped += 1
                continue

            # Skip files that already exist in Blob
            if _ss.exists(cat, rel_path):
                click.echo(f"  EXISTS: {cat}/{rel_path}")
                skipped += 1
                continue

            if dry_run:
                click.echo(f"  WOULD UPLOAD: {cat}/{rel_path}")
                uploaded += 1
                continue

            try:
                with open(abs_path, 'rb') as fh:
                    _ss.upload(cat, rel_path, fh.read())
                click.echo(f"  UPLOADED: {cat}/{rel_path}")
                uploaded += 1
            except Exception as e:
                click.echo(f"  ERROR ({cat}/{rel_path}): {e}")
                errors += 1

    action = "Would upload" if dry_run else "Uploaded"
    click.echo(f"\nDone. {action}: {uploaded}  |  Skipped/exists: {skipped}  |  Errors: {errors}")


@app.cli.command("ai-chat-maintenance")
@click.option("--archive-days", type=int, default=None, help="Archive conversations older than N days (overrides env/config)")
@click.option("--purge-days", type=int, default=None, help="Purge conversations older than N days (overrides env/config)")
@click.option("--batch-size", type=int, default=None, help="Max conversations per run for archive and purge steps")
@click.option("--user-id", type=int, default=None, help="Restrict maintenance to a single user_id (optional)")
@click.option("--dry-run", is_flag=True, default=False, help="Show what would happen without writing/deleting anything")
@with_appcontext
def ai_chat_maintenance(archive_days, purge_days, batch_size, user_id, dry_run):
    """Archive/purge AI chat conversations based on configured retention policy."""
    stats = maintain_ai_chat_retention(
        archive_after_days=archive_days,
        purge_after_days=purge_days,
        batch_size=batch_size,
        dry_run=bool(dry_run),
        user_id=user_id,
    )
    click.echo("AI chat maintenance completed")
    click.echo(f"  archived_conversations: {stats.archived_conversations}")
    click.echo(f"  purged_conversations:   {stats.purged_conversations}")
    click.echo(f"  deleted_archives:       {stats.deleted_archive_objects}")
    click.echo(f"  errors:                 {stats.errors}")


@app.cli.command()
@with_appcontext
def force_cleanup_all_active():
    """Force cleanup of ALL active sessions immediately."""
    from app.models import UserSessionLog
    from datetime import datetime
    from app import db

    try:
        with atomic(remove_session=True):
            active_sessions = UserSessionLog.query.filter(UserSessionLog.is_active == True).all()
            click.echo(f"Force closing {len(active_sessions)} active sessions...")

            for session_log in active_sessions:
                user_email = session_log.user.email if session_log.user else "Unknown"

                session_log.session_end = datetime.utcnow()
                session_log.is_active = False
                session_log.ended_by = 'force_cleanup'

                # Calculate duration
                duration = session_log.session_end - session_log.session_start
                session_log.duration_minutes = int(duration.total_seconds() / 60)

                click.echo(f"  Closed session for {user_email}")

        count = len(active_sessions)
        if count > 0:
            click.echo(f"\nSuccessfully force-closed {count} sessions.")
        else:
            click.echo("No active sessions to close.")

        return count

    except Exception as e:
        click.echo(f"Error during force cleanup: {str(e)}")
        return 0


if __name__ == '__main__':
    def _find_available_port(host: str, start_port: int, max_tries: int = 20) -> int:
        """
        Find an available TCP port by attempting to bind.

        This avoids WinError 10013/10048 cases on Windows where some ports (notably 5000)
        may be excluded/reserved by the OS or another process.
        """
        try:
            import socket
        except Exception as e:
            logging.getLogger(__name__).debug("socket import failed: %s", e)
            return start_port

        for p in range(int(start_port), int(start_port) + int(max_tries)):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                except Exception as e:
                    logging.getLogger(__name__).debug("setsockopt SO_REUSEADDR failed: %s", e)
                s.bind((host, p))
                return p
            except OSError:
                continue
            finally:
                try:
                    s.close()
                except Exception as e:
                    logging.getLogger(__name__).debug("socket close failed: %s", e)
        return start_port

    def _parse_bool_env(value: str | None, default: bool = False) -> bool:
        """Parse env as boolean. Only 'true' and 'false' accepted (case-insensitive)."""
        if value is None or str(value).strip() == "":
            return default
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        return default

    # Prefer Flask CLI for development:
    #   python -m flask --app run --debug run
    # This __main__ block remains as a convenient fallback (`python run.py`).
    host = os.environ.get("FLASK_RUN_HOST") or "127.0.0.1"
    port_env = os.environ.get("PORT") or os.environ.get("FLASK_RUN_PORT")
    default_port = 5000
    port = int(port_env) if port_env else int(default_port)

    if not port_env:
        port = _find_available_port(host, port)

    debug_env = os.environ.get("FLASK_DEBUG")
    if debug_env is not None:
        debug = _parse_bool_env(debug_env, default=False)
    else:
        debug = os.environ.get("FLASK_CONFIG", "").lower() != "production"

    threaded = _parse_bool_env(os.environ.get("FLASK_THREADED"), default=True)

    if os.environ.get("FLASK_CONFIG", "").lower() == "production":
        app.logger.warning("FLASK_CONFIG=production but running via `python run.py`.")
        app.logger.warning("For production/Azure, prefer Gunicorn (see `config/gunicorn.conf.py` and `entrypoint.sh`).")

    # Explicit opt-in for gevent (useful for WebSocket debugging on Windows).
    if _should_use_gevent():
        try:
            from gevent import pywsgi
            try:
                # Provides WebSocket upgrade support for Flask-Sock under gevent.
                # Without this handler, Flask-Sock may fall back to simple-websocket threads.
                from geventwebsocket.handler import WebSocketHandler  # type: ignore
            except Exception as e:
                logging.getLogger(__name__).debug("gevent-websocket WebSocketHandler import failed: %s", e)
                WebSocketHandler = None  # type: ignore

            app.logger.info(f"Starting gevent WSGI server on {host}:{port}")
            app.logger.info("Note: gevent mode does not enable Flask auto-reload.")
            if WebSocketHandler is None:
                app.logger.warning(
                    "gevent-websocket is not installed; WebSocket upgrades may not work correctly under gevent. "
                    "Install with: pip install gevent-websocket"
                )
                server = pywsgi.WSGIServer((host, port), app, log=app.logger)
            else:
                server = pywsgi.WSGIServer(
                    (host, port),
                    app,
                    handler_class=WebSocketHandler,
                    log=app.logger,
                )
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                app.logger.info("Received Ctrl+C, shutting down gevent server...")
                try:
                    server.stop(timeout=1)
                except Exception as stop_e:
                    logging.getLogger(__name__).debug("gevent server stop failed: %s", stop_e)
        except Exception as e:
            app.logger.error(f"Failed to start gevent server: {e}")
            app.logger.warning("Falling back to Flask development server.")

    # Default: Flask development server (development ergonomics + reloader).
    #
    # On Windows the stat reloader can trigger false-positive reloads because:
    #   1. Python writes __pycache__/*.pyc files on first import after a reload.
    #      On some Windows FS configurations this can bump the mtime of the
    #      parent directory, which in turn looks like a watched .py file changed.
    #   2. The instance/logs/ directory lives inside the project tree; any log
    #      write during startup can appear as a file-system change.
    #
    # We pass exclude_patterns to the reloader to skip these noisy paths.
    use_stat_reloader = os.name == "nt"
    app.logger.debug(f"Starting Flask dev server on {host}:{port} (debug={debug}, threaded={threaded})")

    # Paths to exclude from the stat/watchdog reloader so they don't trigger
    # spurious restarts (relative glob patterns understood by Werkzeug reloader).
    _exclude_patterns = [
        "**/__pycache__/**",
        "**/*.pyc",
        "**/instance/**",
        "**/.pytest_cache/**",
        "**/.coverage",
        "**/*.log",
    ]

    if use_stat_reloader:
        app.run(
            debug=debug,
            host=host,
            port=port,
            use_reloader=debug,
            reloader_type="stat",
            threaded=threaded,
            exclude_patterns=_exclude_patterns,
        )
    else:
        app.run(
            debug=debug,
            host=host,
            port=port,
            use_reloader=debug,
            threaded=threaded,
            exclude_patterns=_exclude_patterns,
        )
