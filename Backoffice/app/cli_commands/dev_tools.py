"""Development and maintenance CLI commands (registered via create_app)."""

import logging
import os

import click
from flask import current_app
from flask.cli import with_appcontext

from app.extensions import db
from app.utils.transactions import atomic

logger = logging.getLogger(__name__)


def register_dev_tools_commands(app):
    """Register dev/admin CLI commands that previously lived only in run.py."""

    @app.cli.command()
    @with_appcontext
    def cleanup_sessions():
        """Clean up inactive and expired sessions."""
        from app.services.platform.user_analytics_service import cleanup_inactive_sessions

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
        from datetime import datetime, timedelta

        from app.models import UserSessionLog
        from app.services.platform.user_analytics_service import cleanup_inactive_sessions

        try:
            total_sessions = UserSessionLog.query.count()
            active_sessions = UserSessionLog.query.filter(UserSessionLog.is_active == True).count()

            click.echo("Before cleanup:")
            click.echo(f"  Total sessions: {total_sessions}")
            click.echo(f"  Active sessions: {active_sessions}")

            inactivity_cutoff = datetime.utcnow() - timedelta(hours=2)
            max_duration_cutoff = datetime.utcnow() - timedelta(hours=8)

            inactive_sessions = UserSessionLog.query.filter(
                UserSessionLog.is_active == True,
                UserSessionLog.last_activity < inactivity_cutoff,
            ).all()

            long_sessions = UserSessionLog.query.filter(
                UserSessionLog.is_active == True,
                UserSessionLog.session_start < max_duration_cutoff,
            ).all()

            sessions_to_close = set(inactive_sessions + long_sessions)

            if sessions_to_close:
                click.echo("\nSessions to be cleaned up:")
                for session_log in sessions_to_close:
                    user_email = session_log.user.email if session_log.user else "Unknown"
                    hours_since_activity = (
                        datetime.utcnow() - session_log.last_activity
                    ).total_seconds() / 3600
                    click.echo(
                        f"  - User: {user_email}, Last activity: {hours_since_activity:.1f} hours ago"
                    )

            count = cleanup_inactive_sessions()

            active_sessions_after = UserSessionLog.query.filter(
                UserSessionLog.is_active == True
            ).count()

            click.echo("\nCleanup completed:")
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
        from app.models import Country, User

        email = click.prompt("Admin email")
        password = click.prompt("Admin password", hide_input=True)
        name = click.prompt("Admin name", default="Administrator")

        if User.query.filter_by(email=email).first():
            click.echo(f"User with email {email} already exists!")
            return

        admin = User(email=email, name=name)
        admin.set_password(password)

        for country in Country.query.all():
            admin.countries.append(country)

        with atomic(remove_session=True):
            db.session.add(admin)
            db.session.flush()

            try:
                from app.models.rbac import RbacRole, RbacUserRole

                admin_role = RbacRole.query.filter_by(code="admin_core").first()
                if not admin_role:
                    admin_role = RbacRole(
                        code="admin_core",
                        name="Admin (Core)",
                        description="Baseline admin role",
                    )
                    db.session.add(admin_role)
                    db.session.flush()
                db.session.add(RbacUserRole(user_id=admin.id, role_id=admin_role.id))
            except Exception as e:
                logger.debug("RBAC admin role assignment failed: %s", e)

        click.echo(f"Admin user {email} created successfully!")

    @app.cli.command("seed-test-data")
    @with_appcontext
    def seed_test_data():
        """Create default test users and data for local development.

        Creates Testland country, RBAC roles, and three test users:
          - test_sys@<domain>   (System Manager)
          - test_admin@<domain> (Admin)
          - test_focal@<domain> (Focal Point)

        Passwords come from TEST_SYS_MANAGER_PASSWORD, TEST_ADMIN_PASSWORD,
        TEST_FOCAL_PASSWORD env vars (or are generated randomly).
        Set these in your .env so the quick-login buttons work on the login page.

        Refuses to run in production or staging environments.
        """
        flask_cfg = os.environ.get("FLASK_CONFIG", "").lower()
        if flask_cfg in ("production", "staging"):
            click.echo(f"ERROR: Cannot seed test data in {flask_cfg} environment.")
            raise SystemExit(1)

        from app.seeding import create_default_data

        click.echo("Seeding test data ...")
        try:
            create_default_data(current_app._get_current_object())
            click.echo("Done. Test users are ready.")
            if not os.environ.get("TEST_ADMIN_PASSWORD") or not os.environ.get(
                "TEST_FOCAL_PASSWORD"
            ):
                click.echo(
                    "\nTip: Set TEST_ADMIN_PASSWORD, TEST_FOCAL_PASSWORD, and "
                    "TEST_SYS_MANAGER_PASSWORD in your .env to enable quick-login "
                    "buttons on the login page."
                )
        except Exception as e:
            click.echo(f"Error seeding test data: {e}")

    @app.cli.command()
    @with_appcontext
    def force_cleanup_old_sessions():
        """Force cleanup of all sessions older than 1 hour, regardless of activity."""
        from datetime import datetime, timedelta

        from app.models import UserSessionLog
        from app.services.platform.user_analytics_service import cleanup_inactive_sessions

        try:
            total_sessions = UserSessionLog.query.count()
            active_sessions = UserSessionLog.query.filter(
                UserSessionLog.is_active == True
            ).count()

            click.echo("Before force cleanup:")
            click.echo(f"  Total sessions: {total_sessions}")
            click.echo(f"  Active sessions: {active_sessions}")

            active_session_details = UserSessionLog.query.filter(
                UserSessionLog.is_active == True
            ).all()
            click.echo("\nActive session details:")
            for session_log in active_session_details:
                user_email = session_log.user.email if session_log.user else "Unknown"
                hours_since_start = (
                    datetime.utcnow() - session_log.session_start
                ).total_seconds() / 3600
                hours_since_activity = (
                    datetime.utcnow() - session_log.last_activity
                ).total_seconds() / 3600
                click.echo(f"  - User: {user_email}")
                click.echo(f"    Session start: {session_log.session_start}")
                click.echo(f"    Last activity: {session_log.last_activity}")
                click.echo(f"    Hours since start: {hours_since_start:.1f}")
                click.echo(f"    Hours since activity: {hours_since_activity:.1f}")
                click.echo()

            count = cleanup_inactive_sessions(inactivity_hours=1, max_session_hours=2)

            active_sessions_after = UserSessionLog.query.filter(
                UserSessionLog.is_active == True
            ).count()

            click.echo("Force cleanup completed:")
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
        from datetime import datetime

        from app.models import UserSessionLog

        try:
            click.echo("=== ALL SESSIONS IN DATABASE ===")

            all_sessions = UserSessionLog.query.order_by(
                UserSessionLog.session_start.desc()
            ).all()

            click.echo(f"Total sessions in database: {len(all_sessions)}")

            active_count = 0
            inactive_count = 0

            for session_log in all_sessions:
                user_email = session_log.user.email if session_log.user else "Unknown"
                hours_since_start = (
                    datetime.utcnow() - session_log.session_start
                ).total_seconds() / 3600
                hours_since_activity = (
                    datetime.utcnow() - session_log.last_activity
                ).total_seconds() / 3600

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

            click.echo("\nSummary:")
            click.echo(f"  Active sessions: {active_count}")
            click.echo(f"  Inactive sessions: {inactive_count}")

            if active_count > 0:
                click.echo(
                    f"\nWould you like to force cleanup of all {active_count} active sessions? (y/N)"
                )

        except Exception as e:
            click.echo(f"Error showing sessions: {str(e)}")

    @app.cli.command()
    @click.option("--enable/--disable", default=True, help="Enable or disable debug logging")
    @with_appcontext
    def toggle_debug_logging(enable):
        """Toggle debug logging for application components at runtime."""
        from app.services.monitoring.debug import debug_manager

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
        from app.services.monitoring.debug import get_performance_stats

        stats = get_performance_stats()

        if not stats:
            click.echo(
                "No performance data available. Enable debug logging to collect performance metrics."
            )
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
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Show what would be uploaded without actually uploading.",
    )
    @click.option(
        "--category",
        default=None,
        help="Only migrate a specific category (e.g. admin_documents, resources, submissions, system, ai_documents).",
    )
    @with_appcontext
    def migrate_uploads_to_azure(dry_run, category):
        """Migrate files from the local UPLOAD_FOLDER to Azure Blob Storage."""
        from app.services.platform import storage_service as _ss

        if not _ss.is_azure():
            click.echo(
                "ERROR: UPLOAD_STORAGE_PROVIDER is not 'azure_blob'. Set AZURE_STORAGE_CONNECTION_STRING and ensure UPLOAD_STORAGE_PROVIDER=azure_blob."
            )
            return

        upload_folder = current_app.config.get("UPLOAD_FOLDER", "").strip()
        if not upload_folder or not os.path.isdir(upload_folder):
            click.echo(
                f"ERROR: UPLOAD_FOLDER '{upload_folder}' does not exist or is not a directory."
            )
            return

        known_categories = {
            _ss.ADMIN_DOCUMENTS,
            _ss.RESOURCES,
            _ss.SUBMISSIONS,
            _ss.SYSTEM,
            _ss.AI_DOCUMENTS,
        }

        uploaded = skipped = errors = 0

        for root, _dirs, files in os.walk(upload_folder):
            for fname in files:
                abs_path = os.path.join(root, fname)
                rel_from_base = os.path.relpath(abs_path, upload_folder).replace("\\", "/")
                parts = rel_from_base.split("/", 1)
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

                if _ss.exists(cat, rel_path):
                    click.echo(f"  EXISTS: {cat}/{rel_path}")
                    skipped += 1
                    continue

                if dry_run:
                    click.echo(f"  WOULD UPLOAD: {cat}/{rel_path}")
                    uploaded += 1
                    continue

                try:
                    with open(abs_path, "rb") as fh:
                        _ss.upload(cat, rel_path, fh.read())
                    click.echo(f"  UPLOADED: {cat}/{rel_path}")
                    uploaded += 1
                except Exception as e:
                    click.echo(f"  ERROR ({cat}/{rel_path}): {e}")
                    errors += 1

        action = "Would upload" if dry_run else "Uploaded"
        click.echo(
            f"\nDone. {action}: {uploaded}  |  Skipped/exists: {skipped}  |  Errors: {errors}"
        )

    @app.cli.command("ai-chat-maintenance")
    @click.option(
        "--archive-days",
        type=int,
        default=None,
        help="Archive conversations older than N days (overrides env/config)",
    )
    @click.option(
        "--purge-days",
        type=int,
        default=None,
        help="Purge conversations older than N days (overrides env/config)",
    )
    @click.option(
        "--batch-size",
        type=int,
        default=None,
        help="Max conversations per run for archive and purge steps",
    )
    @click.option(
        "--user-id",
        type=int,
        default=None,
        help="Restrict maintenance to a single user_id (optional)",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Show what would happen without writing/deleting anything",
    )
    @with_appcontext
    def ai_chat_maintenance(archive_days, purge_days, batch_size, user_id, dry_run):
        """Archive/purge AI chat conversations based on configured retention policy."""
        from app.services.ai.chat.retention import maintain_ai_chat_retention

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
        from datetime import datetime

        from app.models import UserSessionLog

        try:
            with atomic(remove_session=True):
                active_sessions = UserSessionLog.query.filter(
                    UserSessionLog.is_active == True
                ).all()
                click.echo(f"Force closing {len(active_sessions)} active sessions...")

                for session_log in active_sessions:
                    user_email = session_log.user.email if session_log.user else "Unknown"

                    session_log.session_end = datetime.utcnow()
                    session_log.is_active = False
                    session_log.ended_by = "force_cleanup"

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
