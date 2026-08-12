"""
Pytest configuration and fixtures for Humanitarian Databank Backoffice tests.

This module provides shared fixtures and utilities for all tests.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load Backoffice/.env before app imports (override=False).
load_dotenv(Path(__file__).resolve().parent.parent / '.env', override=False)
os.environ.setdefault('FLASK_CONFIG', 'testing')

import logging
# PostgreSQL NOTICE lines (DROP IF EXISTS, CREATE EXTENSION, etc.) are logged at INFO by
# sqlalchemy.dialects.postgresql; suppress during tests to reduce noise and avoid touching
# RotatingFileHandler when a dev server already holds instance/logs/application.log open.
logging.getLogger('sqlalchemy.dialects.postgresql').setLevel(logging.WARNING)

import pytest
import tempfile
import shutil
from contextlib import suppress
from unittest.mock import patch, MagicMock
from flask import Flask
from sqlalchemy import text

from app import create_app, db
from app.extensions import login
from app.models import User

_PG_NUCLEAR_DROP_SQL = text("""
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN (SELECT table_name FROM information_schema.views WHERE table_schema = current_schema()) LOOP
    EXECUTE 'DROP VIEW IF EXISTS ' || quote_ident(r.table_name) || ' CASCADE';
  END LOOP;
  FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = current_schema()) LOOP
    EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
  END LOOP;
  FOR r IN (SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema = current_schema()) LOOP
    EXECUTE 'DROP SEQUENCE IF EXISTS ' || quote_ident(r.sequence_name) || ' CASCADE';
  END LOOP;
  FOR r IN (
    SELECT t.typname
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE t.typtype = 'e' AND n.nspname = current_schema()
  ) LOOP
    EXECUTE 'DROP TYPE IF EXISTS ' || quote_ident(r.typname) || ' CASCADE';
  END LOOP;
END $$;
""")

_CRITICAL_TEST_TABLES = (
    "user",
    "country",
    "user_entity_permissions",
    "form_template",
    "api_keys",
    "form_data",
    "dynamic_indicator_data",
    "indicator_bank",
    "rbac_role",
)


def _disengage_db_connections():
    """Roll back, remove the scoped session, and dispose pooled connections."""
    for action in (
        lambda: db.session.rollback(),
        lambda: db.session.remove(),
        lambda: db.engine.dispose(),
    ):
        with suppress(Exception):
            action()


def _drop_legacy_test_artifacts():
    """Drop objects that sometimes survive generic schema cleanup."""
    for _ in range(3):
        try:
            with db.engine.begin() as conn:
                conn.execute(text("DROP INDEX IF EXISTS ix_api_key_usage_timestamp CASCADE"))
                conn.execute(text("DROP TABLE IF EXISTS ix_api_key_usage_timestamp CASCADE"))
                conn.execute(text("DROP SEQUENCE IF EXISTS ix_api_key_usage_timestamp CASCADE"))
                conn.execute(text("DROP TABLE IF EXISTS api_key_usage CASCADE"))
                conn.execute(text("DROP TABLE IF EXISTS indicator_bank CASCADE"))
                conn.execute(text("DROP TABLE IF EXISTS indicator_bank_history CASCADE"))
        except Exception:
            pass


def _nuclear_drop_postgres_schema():
    """Drop all objects in the current PostgreSQL schema."""
    if db.engine.dialect.name != "postgresql":
        return
    last_error = None
    for _ in range(2):
        _disengage_db_connections()
        try:
            with db.engine.begin() as conn:
                conn.execute(_PG_NUCLEAR_DROP_SQL)
            return
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Failed to reset PostgreSQL test schema: {last_error}") from last_error


def _missing_critical_tables():
    with db.engine.connect() as conn:
        missing = []
        for table_name in _CRITICAL_TEST_TABLES:
            exists = conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.tables "
                "WHERE table_schema=current_schema() AND table_name = :t)"
            ), {"t": table_name}).scalar()
            if not exists:
                missing.append(table_name)
        return missing


def _create_all_test_tables():
    """Create all ORM tables, retrying once on duplicate-object errors."""
    try:
        db.metadata.create_all(bind=db.engine, checkfirst=True)
    except Exception as create_error:
        error_str = str(create_error).lower()
        if 'duplicate' in error_str or 'already exists' in error_str:
            try:
                with db.engine.begin() as conn:
                    conn.execute(text("DROP INDEX IF EXISTS ix_api_key_usage_timestamp CASCADE"))
            except Exception:
                pass
            db.metadata.create_all(bind=db.engine, checkfirst=True)
        else:
            raise


def _reset_test_schema(app):
    """Drop and recreate the full test schema from current model metadata."""
    _disengage_db_connections()

    if db.engine.dialect.name == "postgresql":
        with db.engine.connect() as conn:
            conn.execute(text("SELECT pg_advisory_lock(7474242)"))
            # pg_advisory_lock is session-scoped, not transaction-scoped: committing
            # here does NOT release it, but it stops this connection from sitting
            # idle-in-transaction for the whole (multi-second) reset below. The test
            # DB's idle_in_transaction_session_timeout would otherwise kill this
            # connection while _run_test_schema_reset() does its real work on other
            # connections, turning an otherwise-successful reset into a spurious
            # "server closed the connection unexpectedly" failure on unlock.
            conn.commit()
            try:
                _run_test_schema_reset()
            finally:
                with suppress(Exception):
                    conn.execute(text("SELECT pg_advisory_unlock(7474242)"))
                    conn.commit()
        return

    _run_test_schema_reset()


def _run_test_schema_reset():
    """Schema drop/create body (caller holds pg advisory lock when on PostgreSQL)."""
    with suppress(Exception):
        db.metadata.drop_all(bind=db.engine, checkfirst=True)
    with suppress(Exception):
        db.drop_all()

    _nuclear_drop_postgres_schema()
    _drop_legacy_test_artifacts()

    if db.engine.dialect.name == "postgresql":
        with db.engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    _create_all_test_tables()

    missing = _missing_critical_tables()
    if missing:
        _disengage_db_connections()
        _nuclear_drop_postgres_schema()
        if db.engine.dialect.name == "postgresql":
            with db.engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        _create_all_test_tables()
        missing = _missing_critical_tables()

    if missing:
        raise RuntimeError(
            "CRITICAL: expected tables were not created: "
            + ", ".join(missing)
        )


def _register_error_trigger_routes(app):
    """Register /test-error/<code> routes for error handler unit tests."""
    from flask import Blueprint, abort
    from flask_wtf.csrf import CSRFError

    bp = Blueprint("_error_triggers", __name__, url_prefix="/test-error")

    @bp.route("/400")
    def trigger_400():
        abort(400)

    @bp.route("/401")
    def trigger_401():
        abort(401)

    @bp.route("/403")
    def trigger_403():
        abort(403)

    @bp.route("/404")
    def trigger_404():
        abort(404)

    @bp.route("/500")
    def trigger_500():
        abort(500)

    @bp.route("/502")
    def trigger_502():
        abort(502)

    @bp.route("/503")
    def trigger_503():
        abort(503)

    @bp.route("/csrf", methods=["GET", "POST"])
    def trigger_csrf():
        raise CSRFError("The CSRF session token is missing.")

    app.register_blueprint(bp)


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
    app.config['SECRET_KEY'] = 'test-secret-key-for-pytest-suite-32b!'
    app.config['MOBILE_JWT_SECRET'] = 'test-mobile-jwt-secret-for-pytest-32b!'
    app.config['API_KEY'] = os.environ.get('API_KEY') or 'test-api-key'
    app.config['SCHEDULER_ENABLED'] = False
    _features = dict(app.config.get('FEATURES') or {})
    _features['notifications_push_enabled'] = True
    app.config['FEATURES'] = _features
    # Allow oversized multipart payloads to reach route handlers that enforce their own limits.
    app.config['MAX_CONTENT_LENGTH'] = 60 * 1024 * 1024
    # Keep logout redirects on the local login route during tests (avoid B2C end_session URLs).
    app.config['AZURE_B2C_POST_LOGOUT_REDIRECT_URI'] = 'http://127.0.0.1/login'
    # Ensure patch.object(app, "form_integration", ...) works in plugin route tests.
    app.form_integration = getattr(app, 'form_integration', None)

    # Plugin manager is initialized during create_app(); ensure field types are
    # registered even if DEBUG was True at config import time (before FLASK_CONFIG=testing).
    plugin_manager = getattr(app, 'plugin_manager', None)
    if plugin_manager is not None:
        if not plugin_manager.field_types:
            plugin_manager.load_plugins()
            plugin_manager.register_template_loader()
            plugin_manager.register_blueprints()
        if not getattr(app, 'form_integration', None):
            from app.plugins.form_integration import FormIntegration
            app.form_integration = FormIntegration(plugin_manager)
        elif not getattr(app.form_integration, 'plugin_manager', None):
            app.form_integration.plugin_manager = plugin_manager

    _register_error_trigger_routes(app)

    with app.app_context():
        yield app


@pytest.fixture(scope='function')
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture(autouse=True)
def reset_flask_request_globals(app):
    """Clear leaked Flask ``g`` transaction/mobile state between tests."""
    def _clear():
        try:
            from flask import g, has_request_context
            if has_request_context():
                for key in (
                    '_auto_txn_managed',
                    '_auto_txn_force_rollback',
                    '_mobile_jwt_sid',
                    '_post_commit_callbacks',
                ):
                    with suppress(Exception):
                        if hasattr(g, key):
                            delattr(g, key)
        except Exception:
            pass

    _clear()
    yield
    _clear()


@pytest.fixture(autouse=True)
def reset_site_lock_flags(app):
    """Reset coming-soon / maintenance locks so later tests are not blocked."""
    app.config["COMING_SOON_LOCK"] = False
    app.config["MAINTENANCE_LOCK"] = False
    app.config.pop("COMING_SOON_BYPASS_SECRET", None)
    app.config.pop("MAINTENANCE_BYPASS_SECRET", None)
    yield
    app.config["COMING_SOON_LOCK"] = False
    app.config["MAINTENANCE_LOCK"] = False
    app.config.pop("COMING_SOON_BYPASS_SECRET", None)
    app.config.pop("MAINTENANCE_BYPASS_SECRET", None)


@pytest.fixture(autouse=True)
def reset_in_memory_rate_limits():
    """Clear in-memory rate limit counters between tests.

    The custom deque-based limiter in rate_limiting.py uses a module-level
    defaultdict that accumulates across tests.  Without this reset the
    limiter can trip on routes that are exercised many times during the suite
    (e.g. /auth/change-password with requests_per_minute=5).
    """
    yield
    try:
        from app.utils.rate_limiting import _rate_limit_storage
        _rate_limit_storage.clear()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def reset_aes_access_light_cache():
    """Clear the (user, aes) access cache in data_retrieval_service.

    check_aes_access_light caches positive results in a module-level dict;
    without this reset a hit from one test could mask changed fixtures or
    permissions in a later test reusing the same ids.
    """
    yield
    try:
        from app.services.data_retrieval.service import clear_aes_access_light_cache
        clear_aes_access_light_cache()
    except Exception:
        pass


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
            SubmittedDocument, APIKey, AIReasoningTrace, AITermConcept,
        )
        from app.models.api_usage import APIUsage  # noqa: F401 — ensures api_usage table is created

        # Force metadata to be populated
        metadata = db.metadata
        _ = list(metadata.tables.keys())

        metadata_tables = list(db.metadata.tables.keys())
        if not metadata_tables:
            raise RuntimeError("No tables found in metadata! Models may not be imported correctly.")

        try:
            _reset_test_schema(app)
        except RuntimeError:
            raise
        except Exception as e:
            import traceback
            app.logger.error(f"Error creating tables: {e}\n{traceback.format_exc()}")
            raise

        session_factory = db.session.session_factory
        prev_expire_on_commit = session_factory.kw.get("expire_on_commit", True)
        session_factory.configure(expire_on_commit=False)
        try:
            yield db.session
        finally:
            session_factory.configure(expire_on_commit=prev_expire_on_commit)
            _disengage_db_connections()


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
        full_key, key_id, key_hash, key_prefix = APIKey.generate_key()

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
        user_id = user.id
        db.session.expunge(user)
        user.id = user_id
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
        user_id = user.id
        db.session.expunge(user)
        user.id = user_id
        yield user


@pytest.fixture(scope='function')
def logged_in_client(client, admin_user, app):
    """Return a test client with logged-in admin user."""
    with app.app_context():
        user_id = admin_user.id
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True
    return client


@pytest.fixture(scope='function')
def logged_in_admin_client(logged_in_client):
    """Alias for logged-in admin test client."""
    return logged_in_client


@pytest.fixture(scope='function')
def focal_point_user(db_session, app):
    """Focal-point user with country entity permission and one assignment."""
    from sqlalchemy.orm import joinedload
    from app.models.assignments import AssignmentEntityStatus
    from tests.factories import create_focal_point_with_country
    with app.app_context():
        user, country, aes = create_focal_point_with_country(db_session)
        aes = (
            db_session.query(AssignmentEntityStatus)
            .options(joinedload(AssignmentEntityStatus.assigned_form))
            .filter_by(id=aes.id)
            .one()
        )
        yield {
            "user_id": user.id,
            "country_id": country.id,
            "aes_id": aes.id,
            "period_name": aes.assigned_form.period_name,
        }


@pytest.fixture(scope='function')
def system_manager_user(db_session, app):
    """System manager user for admin dashboard routes."""
    from tests.factories import create_test_user
    with app.app_context():
        user = create_test_user(
            db_session,
            email='test_sm@example.com',
            role='system_manager',
        )
        user_id = user.id
        db.session.expunge(user)
        user.id = user_id
        yield user


@pytest.fixture(scope='function')
def logged_in_sm_client(client, system_manager_user, app):
    """Test client logged in as system manager."""
    from tests.helpers import login_session
    with app.app_context():
        login_session(client, system_manager_user.id)
    return client


@pytest.fixture(scope='function')
def logged_in_focal_client(client, focal_point_user, app):
    """Test client logged in as focal_point_user."""
    from tests.helpers import login_session, set_selected_entity_session
    user_id = focal_point_user["user_id"]
    country_id = focal_point_user["country_id"]
    login_session(client, user_id)
    set_selected_entity_session(
        client,
        entity_type="country",
        entity_id=country_id,
        country_id=country_id,
    )
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


# ---------------------------------------------------------------------------
# Per-worker database isolation for pytest-xdist
# ---------------------------------------------------------------------------

def _ensure_worker_database(base_url: str, db_name: str) -> None:
    """Create the per-worker database if it does not already exist.

    Connects to the PostgreSQL 'postgres' maintenance database using the same
    host/port/user/password as the test URL, then issues CREATE DATABASE if the
    target DB is absent.  Silently no-ops for non-PostgreSQL URLs or when the
    DB already exists.
    """
    import re
    try:
        from urllib.parse import urlparse
        import psycopg2

        # Strip SQLAlchemy driver suffix (e.g. +psycopg2) for psycopg2 connection
        clean_url = re.sub(r'\+\w+', '', base_url, count=1)
        parsed = urlparse(clean_url)
        if not parsed.scheme.startswith('postgresql') and not parsed.scheme.startswith('postgres'):
            return

        conn = psycopg2.connect(
            host=parsed.hostname or 'localhost',
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password or '',
            dbname='postgres',
            connect_timeout=5,
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute('SELECT 1 FROM pg_database WHERE datname = %s', (db_name,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{db_name}"')
        cur.close()
        conn.close()
    except Exception:
        pass  # If creation fails, let the test fixture surface the real error


def pytest_configure(config):
    """Configure pytest markers and (for xdist workers) isolate test databases."""

    # ── per-worker DB isolation ──────────────────────────────────────────────
    # Each xdist worker gets its own database so parallel workers do not fight
    # over DDL locks when db_session drops/recreates the full schema.
    # PYTEST_XDIST_WORKER is set to e.g. "gw0", "gw1", … by pytest-xdist.
    worker_id = os.environ.get('PYTEST_XDIST_WORKER', '')
    if worker_id:
        from urllib.parse import urlparse, urlunparse
        import re

        base_url = os.environ.get('TEST_DATABASE_URL') or os.environ.get('DATABASE_URL', '')
        if base_url and not base_url.startswith('sqlite'):
            parsed = urlparse(base_url)
            # Append worker suffix to the DB name path: /ngo_databank_test -> /ngo_databank_test_gw0
            original_db = parsed.path.lstrip('/')
            worker_db = f'{original_db}_{worker_id}'
            new_url = urlunparse(parsed._replace(path=f'/{worker_db}'))

            _ensure_worker_database(base_url, worker_db)

            os.environ['TEST_DATABASE_URL'] = new_url
            os.environ['DATABASE_URL'] = new_url

    # ── markers ─────────────────────────────────────────────────────────────
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
    config.addinivalue_line(
        "markers", "critical: Critical production route smoke tests"
    )


def _patch_terminal_progress_count_and_percent(config):
    """Pytest 9 shows count OR percent; show both in terminal progress lines."""
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    if reporter._show_progress_info not in ("count", "progress"):
        return

    original_get_msg = reporter._get_progress_information_message

    def _format_progress_message() -> str:
        session = reporter._session
        if session is None:
            return ""
        collected = session.testscollected
        progress = reporter.reported_progress
        if not collected:
            return " [100%]"
        pct = progress * 100 // collected
        width = len(str(collected))
        return f" [{progress:{width}d}/{collected} {pct:3d}%]"

    def _get_progress_information_message_both():
        if reporter._show_progress_info == "times":
            return original_get_msg()
        return _format_progress_message()

    def _write_progress_information_if_past_edge_both():
        w = reporter._width_of_current_line
        if reporter._show_progress_info in ("count", "progress"):
            session = reporter._session
            num_tests = session.testscollected if session else 0
            progress_length = len(f" [{num_tests}/{num_tests} 100%]")
        elif reporter._show_progress_info == "times":
            progress_length = len(" 99h 59m")
        else:
            progress_length = len(" [100%]")
        past_edge = w + progress_length + 1 >= reporter._screen_width
        if past_edge:
            main_color, _ = reporter._get_main_color()
            msg = _format_progress_message()
            reporter._tw.write(msg + "\n", **{main_color: True})

    reporter._get_progress_information_message = _get_progress_information_message_both
    reporter._write_progress_information_if_past_edge = _write_progress_information_if_past_edge_both


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location."""
    for item in items:
        norm = str(item.fspath).replace('\\', '/')
        if '/tests/unit/' in norm:
            item.add_marker(pytest.mark.unit)
        elif '/tests/integration/' in norm:
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.slow)
        elif '/tests/api/' in norm:
            item.add_marker(pytest.mark.api)
            item.add_marker(pytest.mark.slow)


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


def _format_progress_label(idx: int, total: int) -> str:
    """Human-readable progress for test_results.log (matches terminal: n/total + %)."""
    total = total or 1
    pct = int(100 * idx / total)
    width = len(str(total))
    return f"[{idx:{width}d}/{total} {pct:3d}%]"


def pytest_sessionstart(session):
    global _session_start_time
    _session_start_time = _time.time()
    _patch_terminal_progress_count_and_percent(session.config)
    # Live progress file (updated per test on the controller process).
    with open(_results_log_path, 'w', encoding='utf-8') as f:
        f.write("=" * 120 + " test session starts " + "=" * 10 + "\n")
        f.write(f"platform {_sys.platform} -- Python {_platform.python_version()}, "
                f"pytest-{pytest.__version__}\n")
        f.write("collected ... (waiting for collection to finish)\n\n")


def pytest_report_collectionfinish(config, start_path, items):
    """Record number of collected items for progress percentages."""
    global _total_collected
    _total_collected = len(items)
    with open(_results_log_path, 'a', encoding='utf-8') as f:
        f.write(f"collected {_total_collected} items\n\n")


def _append_live_progress(outcome, nodeid, duration):
    """Append one completed test line so tail -f shows real progress."""
    total = _total_collected or 1
    idx = len(_test_outcomes)
    with open(_results_log_path, 'a', encoding='utf-8') as f:
        f.write(f"{nodeid} {outcome} {_format_progress_label(idx, total)} ({duration:.2f}s)\n")


def pytest_runtest_logreport(report):
    """Capture every test phase result (call for pass/fail, setup/teardown for errors)."""
    if report.when == 'call':
        outcome = report.outcome.upper()          # PASSED / FAILED / SKIPPED
        longrepr = report.longreprtext if report.failed else None
        _test_outcomes.append((outcome, report.nodeid, longrepr, report.duration))
        _append_live_progress(outcome, report.nodeid, report.duration)
    elif report.when in ('setup', 'teardown') and report.failed:
        longrepr = report.longreprtext or None
        entry = (f"ERROR ({report.when})", report.nodeid, longrepr, report.duration)
        _test_outcomes.append(entry)
        _append_live_progress(entry[0], report.nodeid, report.duration)


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
            f.write(f"{nodeid} {outcome} {_format_progress_label(idx, total)}\n")

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
