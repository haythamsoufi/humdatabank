"""
Pytest configuration and fixtures for NGO Databank Backoffice tests.

This module provides shared fixtures and utilities for all tests.
"""
import os
import pytest
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from flask import Flask
from sqlalchemy import text

from app import create_app, db
from app.extensions import login
from app.models import User


def _check_test_database_reachable():
    """Verify the test database is reachable before running the test suite.

    Parses TEST_DATABASE_URL (or DATABASE_URL) from the environment / .env
    and attempts a TCP connection to the host:port. Raises pytest.UsageError
    with actionable instructions when the database is not running.
    """
    from urllib.parse import urlparse
    test_db_url = os.environ.get('TEST_DATABASE_URL') or os.environ.get('DATABASE_URL', '')
    if not test_db_url or test_db_url.startswith('sqlite'):
        return

    parsed = urlparse(test_db_url)
    host = parsed.hostname or 'localhost'
    port = parsed.port or 5432

    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        sock.connect((host, port))
    except OSError:
        raise pytest.UsageError(
            f"\n{'=' * 70}\n"
            f"  TEST DATABASE NOT RUNNING\n"
            f"{'=' * 70}\n"
            f"\n"
            f"  Could not connect to the test database at {host}:{port}.\n"
            f"  URL: {test_db_url}\n"
            f"\n"
            f"  Please start the test database before running tests.\n"
            f"  If you're using Docker, run:\n"
            f"\n"
            f"    docker start ifrc-test-db\n"
            f"\n"
            f"  Or start your local PostgreSQL instance on port {port}.\n"
            f"{'=' * 70}\n"
        )
    finally:
        sock.close()


@pytest.fixture(scope='session')
def app():
    """Create application for testing.

    Uses TEST_DATABASE_URL from .env (PostgreSQL). The test database must be
    running before the suite starts — see _check_test_database_reachable().
    """
    os.environ['FLASK_CONFIG'] = 'testing'

    _check_test_database_reachable()

    app = create_app('testing')

    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['DEBUG'] = False
    app.config['SECRET_KEY'] = 'test-secret-key'
    app.config['API_KEY'] = os.environ.get('API_KEY') or 'test-api-key'
    app.config['SCHEDULER_ENABLED'] = False

    with app.app_context():
        yield app


@pytest.fixture(scope='function')
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture(scope='function')
def runner(app):
    """Create test CLI runner."""
    return app.test_cli_runner()


@pytest.fixture(scope='function')
def db_session(app):
    """Create database session and clean up after test."""
    with app.app_context():
        # Import all models from the main models package
        # This ensures all models are registered with SQLAlchemy metadata
        from app import models

        # Explicitly import key models to ensure they're registered
        from app.models import (
            User, Country, FormTemplate, FormTemplateVersion, FormSection,
            FormItem, FormData, DynamicIndicatorData, AssignedForm,
            AssignmentEntityStatus, PublicSubmission, IndicatorBank,
            SubmittedDocument, APIKey
        )

        # Force metadata to be populated
        metadata = db.metadata
        _ = list(metadata.tables.keys())

        metadata_tables = list(db.metadata.tables.keys())
        if not metadata_tables:
            raise RuntimeError("No tables found in metadata! Models may not be imported correctly.")

        try:
            # Drop all tables first to ensure clean state
            # Wrap in try-except to ignore errors about missing constraints/indexes
            try:
                db.metadata.drop_all(bind=db.engine, checkfirst=True)
            except Exception:
                pass  # Ignore errors about missing constraints/indexes
            try:
                db.drop_all()
            except Exception:
                pass  # Ignore errors if tables don't exist

            # On some environments, DROP/CREATE via SQLAlchemy can leave behind objects
            # (e.g., when drop_all fails due to dependency/permission quirks and we ignore
            # the exception). This can cause schema drift where existing tables miss
            # newly-added columns. Force-drop all objects in the current schema.
            try:
                with db.engine.begin() as conn:
                    conn.execute(text("""
DO $$
DECLARE r RECORD;
BEGIN
  -- Drop views first
  FOR r IN (SELECT table_name FROM information_schema.views WHERE table_schema = current_schema()) LOOP
    EXECUTE 'DROP VIEW IF EXISTS ' || quote_ident(r.table_name) || ' CASCADE';
  END LOOP;

  -- Drop tables
  FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = current_schema()) LOOP
    EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
  END LOOP;

  -- Drop sequences
  FOR r IN (SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema = current_schema()) LOOP
    EXECUTE 'DROP SEQUENCE IF EXISTS ' || quote_ident(r.sequence_name) || ' CASCADE';
  END LOOP;
END $$;
                    """))
            except Exception:
                # If the database is not PostgreSQL or permissions are restricted,
                # fall back to best-effort drop_all behavior above.
                pass

            # Drop problematic index that persists between test runs
            # Do this multiple times to ensure it's gone
            for _ in range(3):
                try:
                    with db.engine.begin() as conn:
                        # Drop in correct order: index first, then table.
                        # In some DBs, a leftover *table* may exist with the same name
                        # as the index, which also breaks CREATE INDEX.
                        conn.execute(text("DROP INDEX IF EXISTS ix_api_key_usage_timestamp CASCADE"))
                        conn.execute(text("DROP TABLE IF EXISTS ix_api_key_usage_timestamp CASCADE"))
                        conn.execute(text("DROP SEQUENCE IF EXISTS ix_api_key_usage_timestamp CASCADE"))
                        conn.execute(text("DROP TABLE IF EXISTS api_key_usage CASCADE"))
                        # Some environments reuse a long-lived database where this table
                        # might exist with an older schema. Ensure it's dropped so
                        # create_all can recreate it with current model columns.
                        conn.execute(text("DROP TABLE IF EXISTS indicator_bank CASCADE"))
                        conn.execute(text("DROP TABLE IF EXISTS indicator_bank_history CASCADE"))
                except Exception:
                    pass  # Ignore if doesn't exist

            # Create all tables - handle duplicate index errors gracefully
            # Use a custom approach that continues even if index creation fails
            try:
                # First attempt: try creating all tables at once
                # Use checkfirst=True to avoid Postgres ENUM/type duplicate errors
                # if any named types survive best-effort schema cleanup.
                db.metadata.create_all(bind=db.engine, checkfirst=True)
            except Exception as create_error:
                error_str = str(create_error).lower()
                if 'duplicate' in error_str or 'already exists' in error_str:
                    # Duplicate index error occurred - drop it and retry, or create tables individually
                    # Try dropping the index one more time
                    try:
                        with db.engine.begin() as conn:
                            conn.execute(text("DROP INDEX IF EXISTS ix_api_key_usage_timestamp CASCADE"))
                    except Exception:
                        pass
                    # Retry create_all after cleanup (keeps FK dependency ordering correct)
                    db.metadata.create_all(bind=db.engine, checkfirst=True)
                else:
                    # Non-duplicate error - this is serious, re-raise
                    raise

            # Verify critical tables exist
            with db.engine.connect() as conn:
                def _table_exists(name: str) -> bool:
                    result = conn.execute(text(
                        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_schema=current_schema() AND table_name = :t)"
                    ), {"t": name})
                    return bool(result.scalar())

                missing = [t for t in ("form_template", "api_keys", "form_data") if not _table_exists(t)]
                if missing:
                    raise RuntimeError(
                        "CRITICAL: expected tables were not created: "
                        + ", ".join(missing)
                    )

        except RuntimeError:
            raise
        except Exception as e:
            import traceback
            app.logger.error(f"Error creating tables: {e}\n{traceback.format_exc()}")
            raise

        yield db.session

        # Clean up
        db.session.remove()
        try:
            db.drop_all()
        except Exception:
            pass


@pytest.fixture(scope='function')
def api_key(db_session, app):
    """Create a real API key for testing."""
    with app.app_context():
        # Ensure all models are imported (db_session should have done this, but be safe)
        import app.models

        from app.models import APIKey

        # Verify tables exist before trying to create API key
        # db_session fixture should have created them, but double-check
        try:
            # Try to query to verify table exists
            APIKey.query.first()
        except Exception:
            # If query fails, try to create tables again
            db.create_all()

        # Generate new API key
        full_key, key_hash, key_prefix = APIKey.generate_key()
        key_id = full_key[:32]

        # Create API key record
        api_key_obj = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            client_name='Test Client',
            client_description='API key for testing',
            rate_limit_per_minute=1000,
            is_active=True,
            is_revoked=False
        )
        db.session.add(api_key_obj)
        db.session.commit()

        yield (api_key_obj, full_key)


@pytest.fixture(scope='function')
def auth_headers(api_key, db_session, app):
    """Return auth headers with a real API key (database-backed APIKey model).

    NOTE: This is for `authenticate_api_request`-based endpoints (not `require_api_key`,
    which uses `current_app.config['API_KEY']`).
    """
    api_key_obj, full_key = api_key

    # Return headers with real API key
    yield {
        'Authorization': f'Bearer {full_key}',
        'X-API-Key': full_key
    }


@pytest.fixture(scope='function')
def session_auth_headers(db_session, app):
    """Create session-based authentication headers (for non-API endpoints)."""
    with app.app_context():
        # Check if user already exists and delete it first
        existing_user = User.query.filter_by(email='test_user@example.com').first()
        if existing_user:
            db.session.delete(existing_user)
            db.session.commit()

        # Create test user
        user = User(
            email='test_user@example.com',
            name='Test User',
            active=True
        )
        user.set_password('test_password')
        db.session.add(user)
        db.session.commit()

        # Return empty headers - session will be set via session_transaction
        yield {}


def _cleanup_user_dependencies(user_id):
    """Delete rows that reference a user via NOT NULL FKs to allow safe deletion."""
    from app.models.documents import SubmittedDocument
    from app.models.forms import DynamicIndicatorData, RepeatGroupInstance
    from app.models.core import UserActivityLog, UserSessionLog
    SubmittedDocument.query.filter_by(uploaded_by_user_id=user_id).delete()
    DynamicIndicatorData.query.filter_by(added_by_user_id=user_id).delete()
    RepeatGroupInstance.query.filter_by(created_by_user_id=user_id).delete()
    # Activity/session logs can be created during auth tests; delete before user delete
    UserActivityLog.query.filter_by(user_id=user_id).delete()
    UserSessionLog.query.filter_by(user_id=user_id).delete()


@pytest.fixture(scope='function')
def admin_user(db_session, app):
    """Create and return an admin user."""
    from tests.factories import create_test_admin
    with app.app_context():
        # Check if user already exists and delete it first
        existing_user = User.query.filter_by(email='test_admin@example.com').first()
        if existing_user:
            _cleanup_user_dependencies(existing_user.id)
            db.session.delete(existing_user)
            db.session.commit()

        user = create_test_admin(
            db_session,
            email='test_admin@example.com',
            name='Test Admin',
            password='admin_password',
        )
        yield user


@pytest.fixture(scope='function')
def test_user(db_session, app):
    """Create and return a regular test user."""
    from tests.factories import create_test_user as _create_test_user
    with app.app_context():
        # Check if user already exists and delete it first
        existing_user = User.query.filter_by(email='test_user@example.com').first()
        if existing_user:
            _cleanup_user_dependencies(existing_user.id)
            db.session.delete(existing_user)
            db.session.commit()

        user = _create_test_user(
            db_session,
            email='test_user@example.com',
            name='Test User',
            password='user_password',
            role='user',
        )
        yield user


@pytest.fixture(scope='function')
def logged_in_client(client, admin_user):
    """Return a test client with logged-in admin user."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_user.id)
        sess['_fresh'] = True
    return client


@pytest.fixture(scope='function')
def mock_email():
    """Mock email sending."""
    with patch('app.utils.email_client.send_email') as mock:
        mock.return_value = True
        yield mock


@pytest.fixture(scope='function')
def mock_requests():
    """Mock requests library."""
    with patch('requests.post') as mock_post, \
         patch('requests.get') as mock_get:
        yield {
            'post': mock_post,
            'get': mock_get
        }


@pytest.fixture(scope='function')
def temp_upload_dir():
    """Create temporary upload directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope='function')
def transaction_test_table(db_session, app):
    """Create test table for transaction middleware tests."""
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(
                text("""
                    CREATE TABLE IF NOT EXISTS txn_mw_test (
                        id SERIAL PRIMARY KEY,
                        marker TEXT NOT NULL UNIQUE
                    )
                """)
            )
        yield
        # Cleanup
        try:
            with db.engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS txn_mw_test"))
        except Exception:
            pass


# Pytest hooks
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests (fast, no database)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (require database)"
    )
    config.addinivalue_line(
        "markers", "api: API endpoint tests"
    )
    config.addinivalue_line(
        "markers", "slow: Slow running tests"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location."""
    for item in items:
        # Mark tests in unit/ directory as unit tests
        if 'unit' in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        # Mark tests in integration/ directory as integration tests
        elif 'integration' in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        # Mark tests with 'api' in name as api tests
        elif 'api' in str(item.fspath) or 'api' in item.name:
            item.add_marker(pytest.mark.api)


# ---------------------------------------------------------------------------
# Write full test results (mirrors terminal output) to test_results.log
# so the file can be shared for debugging.
# ---------------------------------------------------------------------------
import sys as _sys
import time as _time
import platform as _platform

_results_log_path = os.path.join(os.path.dirname(__file__), '..', 'test_results.log')
_test_outcomes = []          # list of (outcome, nodeid, longreprtext_or_None, duration_seconds)
_total_collected = 0         # set in pytest_report_collectionfinish
_session_start_time = None   # set in pytest_sessionstart


def pytest_sessionstart(session):
    global _session_start_time
    _session_start_time = _time.time()


def pytest_report_collectionfinish(config, start_path, startdir, items):
    """Record number of collected items for progress percentages."""
    global _total_collected
    _total_collected = len(items)


def pytest_runtest_logreport(report):
    """Capture every test phase result (call for pass/fail, setup/teardown for errors)."""
    if report.when == 'call':
        outcome = report.outcome.upper()          # PASSED / FAILED / SKIPPED
        longrepr = report.longreprtext if report.failed else None
        _test_outcomes.append((outcome, report.nodeid, longrepr, report.duration))
    elif report.when in ('setup', 'teardown') and report.failed:
        longrepr = report.longreprtext or None
        _test_outcomes.append(
            (f"ERROR ({report.when})", report.nodeid, longrepr, report.duration)
        )


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Write comprehensive results (like terminal output) to test_results.log."""
    from datetime import datetime as _dt

    stats = terminalreporter.stats
    passed  = len(stats.get('passed', []))
    failed  = len(stats.get('failed', []))
    errors  = len(stats.get('error', []))
    skipped = len(stats.get('skipped', []))
    warnings_list = stats.get('warnings', [])
    warnings_count = len(warnings_list)

    elapsed = _time.time() - (_session_start_time or _time.time())
    total = _total_collected or 1

    with open(_results_log_path, 'w', encoding='utf-8') as f:
        # ── session header ──────────────────────────────────────────────
        f.write("=" * 120 + " test session starts " + "=" * 10 + "\n")
        f.write(f"platform {_sys.platform} -- Python {_platform.python_version()}, "
                f"pytest-{pytest.__version__}\n")
        f.write(f"rootdir: {config.rootdir}\n")
        if config.inipath:
            f.write(f"configfile: {config.inipath.name}\n")
        f.write(f"collected {_total_collected} items\n\n")

        # ── per-test lines (mirrors -v output) ─────────────────────────
        for idx, (outcome, nodeid, _longrepr, _dur) in enumerate(_test_outcomes, 1):
            pct = int(100 * idx / total)
            f.write(f"{nodeid} {outcome} [{pct:3d}%]\n")

        f.write("\n")

        # ── failures / errors section with full tracebacks ─────────────
        failure_entries = [
            (o, n, r) for o, n, r, _d in _test_outcomes
            if 'FAIL' in o or 'ERROR' in o
        ]
        if failure_entries:
            f.write("=" * 120 + " FAILURES / ERRORS " + "=" * 10 + "\n\n")
            for outcome, nodeid, longrepr in failure_entries:
                f.write("_" * 120 + "\n")
                f.write(f"{outcome}: {nodeid}\n\n")
                if longrepr:
                    f.write(longrepr + "\n")
                f.write("\n")

        # ── warnings summary ───────────────────────────────────────────
        if warnings_count:
            f.write("=" * 120 + " warnings summary " + "=" * 10 + "\n\n")
            for wreport in warnings_list[:50]:      # cap to keep log readable
                f.write(f"  {wreport.nodeid}\n")
                f.write(f"    {wreport.message}\n\n")
            if warnings_count > 50:
                f.write(f"  ... and {warnings_count - 50} more warnings\n\n")

        # ── coverage summary (if pytest-cov produced one) ──────────────
        try:
            cov_plugin = config.pluginmanager.getplugin('_cov')
            if cov_plugin and hasattr(cov_plugin, 'cov_report'):
                # cov_report is a dict of {report_type: path}
                cov_report = getattr(cov_plugin, 'cov_report', {})
                if cov_report:
                    f.write("=" * 120 + " coverage " + "=" * 10 + "\n")
                    for rtype, rpath in cov_report.items():
                        f.write(f"  {rtype}: {rpath}\n")
                    f.write("\n")
        except Exception:
            pass    # coverage details not critical

        # ── final summary line ─────────────────────────────────────────
        f.write("=" * 130 + "\n")
        parts = []
        if passed:   parts.append(f"\033[32m{passed} passed\033[0m")
        if failed:   parts.append(f"\033[31m{failed} failed\033[0m")
        if errors:   parts.append(f"\033[31m{errors} errors\033[0m")
        if skipped:  parts.append(f"\033[33m{skipped} skipped\033[0m")
        if warnings_count: parts.append(f"\033[33m{warnings_count} warnings\033[0m")
        f.write(f"{', '.join(parts)} in {elapsed:.2f}s ({elapsed/60:.0f}m {elapsed%60:.0f}s)\n")
        f.write(f"exit code: {exitstatus}\n")
        f.write(f"generated: {_dt.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
