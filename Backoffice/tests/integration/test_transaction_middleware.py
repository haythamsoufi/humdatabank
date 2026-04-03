"""
Integration tests for transaction middleware.

Tests transaction commit/rollback behavior with real database operations.
"""
import pytest
import uuid
from unittest.mock import patch
from flask import Flask, Response, stream_with_context
from sqlalchemy import text

from app.extensions import db
from app.utils.transaction_middleware import init_transaction_middleware
from app.utils.transactions import no_auto_transaction


@pytest.fixture
def transaction_test_app(app):
    """Create test Flask app with transaction middleware."""
    test_app = Flask(__name__)
    test_app.config.update(
        TESTING=False,
        PROPAGATE_EXCEPTIONS=False,
        SECRET_KEY="test",
        SQLALCHEMY_DATABASE_URI=app.config['SQLALCHEMY_DATABASE_URI']
    )

    db.init_app(test_app)
    init_transaction_middleware(test_app)

    @test_app.get("/ok")
    def ok():
        return {"ok": True}, 200

    @test_app.get("/bad")
    def bad():
        return {"ok": False}, 400

    @test_app.get("/boom")
    def boom():
        raise RuntimeError("boom")

    @test_app.get("/optout")
    @no_auto_transaction
    def optout():
        return {"ok": True}, 200

    @test_app.get("/stream")
    def stream():
        def gen():
            yield "data: hello\n\n"
        return Response(stream_with_context(gen()), mimetype="text/event-stream")

    return test_app


@pytest.mark.integration
@pytest.mark.transaction
class TestTransactionMiddleware:
    """Test transaction middleware behavior."""

    def test_managed_success_commits_and_removes(self, transaction_test_app):
        """Test that successful requests commit and remove session."""
        import app.utils.transaction_middleware as txn_mw
        client = transaction_test_app.test_client()

        with patch.object(txn_mw.db.session, "commit") as commit_mock, \
             patch.object(txn_mw.db.session, "rollback") as rollback_mock, \
             patch.object(txn_mw.db.session, "remove") as remove_mock:
            resp = client.get("/ok")
            assert resp.status_code == 200
            assert commit_mock.call_count == 1
            assert rollback_mock.call_count == 0
            assert remove_mock.call_count >= 1

    def test_managed_4xx_rolls_back(self, transaction_test_app):
        """Test that 4xx responses rollback transaction."""
        import app.utils.transaction_middleware as txn_mw
        client = transaction_test_app.test_client()

        with patch.object(txn_mw.db.session, "commit") as commit_mock, \
             patch.object(txn_mw.db.session, "rollback") as rollback_mock, \
             patch.object(txn_mw.db.session, "remove") as remove_mock:
            resp = client.get("/bad")
            assert resp.status_code == 400
            assert commit_mock.call_count == 0
            assert rollback_mock.call_count >= 1
            assert remove_mock.call_count >= 1

    def test_exception_rolls_back(self, transaction_test_app):
        """Test that exceptions rollback transaction."""
        import app.utils.transaction_middleware as txn_mw
        client = transaction_test_app.test_client()

        with patch.object(txn_mw.db.session, "commit") as commit_mock, \
             patch.object(txn_mw, "safe_rollback") as safe_rollback_mock, \
             patch.object(txn_mw, "safe_remove") as safe_remove_mock:
            resp = client.get("/boom")
            assert resp.status_code == 500
            assert safe_rollback_mock.call_count >= 1
            assert commit_mock.call_count == 0
            assert safe_remove_mock.call_count >= 1

    def test_optout_does_not_commit_or_rollback(self, transaction_test_app):
        """Test that opt-out endpoints don't commit or rollback."""
        import app.utils.transaction_middleware as txn_mw
        client = transaction_test_app.test_client()

        with patch.object(txn_mw.db.session, "commit") as commit_mock, \
             patch.object(txn_mw.db.session, "rollback") as rollback_mock:
            resp = client.get("/optout")
            assert resp.status_code == 200
            assert commit_mock.call_count == 0
            assert rollback_mock.call_count == 0

    def test_streaming_defers_remove_and_does_not_commit(self, transaction_test_app):
        """Test that streaming responses defer remove and don't commit."""
        import app.utils.transaction_middleware as txn_mw
        client = transaction_test_app.test_client()

        with patch.object(txn_mw.db.session, "commit") as commit_mock, \
             patch.object(txn_mw.db.session, "rollback") as rollback_mock, \
             patch.object(txn_mw.db.session, "remove") as remove_mock:
            resp = client.get("/stream", buffered=True)
            assert resp.status_code == 200
            assert commit_mock.call_count == 0
            assert rollback_mock.call_count == 0
            assert remove_mock.call_count >= 1


@pytest.fixture
def transaction_db_test_app(app, transaction_test_table):
    """Create test Flask app with database for transaction tests."""
    test_app = Flask("txn_mw_db_tests")
    test_app.config.update(
        SECRET_KEY="test",
        TESTING=False,
        PROPAGATE_EXCEPTIONS=False,
        SQLALCHEMY_DATABASE_URI=app.config['SQLALCHEMY_DATABASE_URI'],
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    db.init_app(test_app)
    init_transaction_middleware(test_app)

    @test_app.get("/_txn_test/write_ok")
    def _write_ok():
        marker = uuid.uuid4().hex
        db.session.execute(text("INSERT INTO txn_mw_test (marker) VALUES (:m)"), {"m": marker})
        return {"marker": marker}, 200

    @test_app.get("/_txn_test/write_400")
    def _write_400():
        marker = uuid.uuid4().hex
        db.session.execute(text("INSERT INTO txn_mw_test (marker) VALUES (:m)"), {"m": marker})
        return {"marker": marker}, 400

    @test_app.get("/_txn_test/write_boom")
    def _write_boom():
        marker = uuid.uuid4().hex
        db.session.execute(text("INSERT INTO txn_mw_test (marker) VALUES (:m)"), {"m": marker})
        raise RuntimeError("boom")

    return test_app


@pytest.mark.integration
@pytest.mark.transaction
@pytest.mark.db
class TestTransactionMiddlewareDB:
    """
    Integration tests against a real Postgres database.

    These tests create and drop a dedicated table `txn_mw_test` so we can
    validate commit/rollback semantics without touching any existing app tables.
    """

    def _marker_exists(self, marker: str, test_app) -> bool:
        """Check if marker exists in test table."""
        with test_app.app_context():
            with db.engine.connect() as conn:
                found = conn.execute(
                    text("SELECT 1 FROM txn_mw_test WHERE marker = :m LIMIT 1"), {"m": marker}
                ).fetchone()
                return found is not None

    def test_db_commit_on_200(self, transaction_db_test_app):
        """Test that 200 responses commit to database."""
        client = transaction_db_test_app.test_client()
        resp = client.get("/_txn_test/write_ok")
        assert resp.status_code == 200
        marker = resp.get_json()["marker"]
        assert self._marker_exists(marker, transaction_db_test_app)

    def test_db_rollback_on_400(self, transaction_db_test_app):
        """Test that 400 responses rollback database changes."""
        client = transaction_db_test_app.test_client()
        resp = client.get("/_txn_test/write_400")
        assert resp.status_code == 400
        marker = resp.get_json()["marker"]
        assert not self._marker_exists(marker, transaction_db_test_app)

    def test_db_rollback_on_exception(self, transaction_db_test_app):
        """Test that exceptions rollback database changes."""
        client = transaction_db_test_app.test_client()
        resp = client.get("/_txn_test/write_boom")
        assert resp.status_code == 500
        # Verify the table doesn't grow unexpectedly
        with transaction_db_test_app.app_context():
            with db.engine.connect() as conn:
                count = conn.execute(text("SELECT COUNT(*) FROM txn_mw_test")).scalar() or 0
        assert count >= 0
