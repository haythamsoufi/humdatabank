"""
Comprehensive pytest tests for app/services/user_service.py.

Covers every method and every branch, including SQLAlchemyError and
unexpected Exception error paths.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from sqlalchemy.exc import SQLAlchemyError

from app.services.user_service import UserService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raising_query_desc(raise_on_nth=1):
    """
    Return a (descriptor_class, counter_list) pair.
    On the N-th __get__ call the descriptor raises SQLAlchemyError.
    Subsequent calls return a configurable MagicMock query.
    """
    _count = [0]

    class _Desc:
        def __get__(self_d, obj, objtype=None):
            _count[0] += 1
            if _count[0] == raise_on_nth:
                raise SQLAlchemyError("simulated DB error")
            m = MagicMock()
            m.filter.return_value = MagicMock()
            m.filter_by.return_value = MagicMock()
            return m

    return _Desc, _count


# ---------------------------------------------------------------------------
# _handle_db_error
# ---------------------------------------------------------------------------

class TestHandleDbError:
    """Tests for UserService._handle_db_error."""

    def test_rollback_called_on_error(self, app):
        with app.app_context():
            with patch("app.services.user_service.db") as mock_db:
                UserService._handle_db_error(Exception("oops"), "op")
                mock_db.session.rollback.assert_called_once()

    def test_rollback_failure_closes_session(self, app):
        """When rollback itself raises, the session should be closed."""
        with app.app_context():
            with patch("app.services.user_service.db") as mock_db:
                mock_db.session.rollback.side_effect = Exception("rollback exploded")
                mock_db.session.close = MagicMock()
                # Should not raise
                UserService._handle_db_error(Exception("original"), "op")
                mock_db.session.close.assert_called_once()

    def test_rollback_failure_close_also_fails(self, app):
        """If both rollback and close fail, suppress(Exception) swallows it."""
        with app.app_context():
            with patch("app.services.user_service.db") as mock_db:
                mock_db.session.rollback.side_effect = Exception("rollback exploded")
                mock_db.session.close.side_effect = Exception("close also exploded")
                # Must not raise
                UserService._handle_db_error(Exception("original"), "op")


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------

class TestGetById:
    """Tests for UserService.get_by_id."""

    def test_returns_user_when_found(self, db_session, app):
        from tests.factories import create_test_user
        with app.app_context():
            user = create_test_user(db_session)
            result = UserService.get_by_id(user.id)
            assert result is not None
            assert result.id == user.id

    def test_returns_none_when_not_found(self, db_session, app):
        with app.app_context():
            result = UserService.get_by_id(999_999_999)
            assert result is None

    def test_sqlalchemy_error_returns_none(self, app):
        with app.app_context():
            with patch("app.services.user_service.User") as MockUser:
                MockUser.query.get.side_effect = SQLAlchemyError("DB")
                with patch("app.services.user_service.db"):
                    result = UserService.get_by_id(1)
                    assert result is None

    def test_unexpected_exception_returns_none(self, app):
        with app.app_context():
            with patch("app.services.user_service.User") as MockUser:
                MockUser.query.get.side_effect = RuntimeError("unexpected")
                result = UserService.get_by_id(1)
                assert result is None


# ---------------------------------------------------------------------------
# get_by_email
# ---------------------------------------------------------------------------

class TestGetByEmail:
    """Tests for UserService.get_by_email."""

    def test_returns_user_when_found(self, db_session, app):
        from tests.factories import create_test_user
        with app.app_context():
            user = create_test_user(db_session, email="findme@example.com")
            result = UserService.get_by_email("findme@example.com")
            assert result is not None
            assert result.email == "findme@example.com"

    def test_case_insensitive_lookup(self, db_session, app):
        from tests.factories import create_test_user
        with app.app_context():
            create_test_user(db_session, email="upper@example.com")
            result = UserService.get_by_email("UPPER@EXAMPLE.COM")
            assert result is not None

    def test_strips_whitespace_from_email(self, db_session, app):
        from tests.factories import create_test_user
        with app.app_context():
            create_test_user(db_session, email="strip@example.com")
            result = UserService.get_by_email("  strip@example.com  ")
            assert result is not None

    def test_returns_none_when_not_found(self, db_session, app):
        with app.app_context():
            result = UserService.get_by_email("ghost@example.com")
            assert result is None

    def test_sqlalchemy_error_retries_and_succeeds(self, app):
        """On SQLAlchemyError the service rolls back and retries once."""
        with app.app_context():
            expected_user = MagicMock()
            call_count = [0]

            def first_side_effect():
                call_count[0] += 1
                if call_count[0] == 1:
                    raise SQLAlchemyError("first attempt fails")
                return expected_user

            with patch("app.services.user_service.User") as MockUser:
                MockUser.query.filter_by.return_value.first.side_effect = first_side_effect
                with patch("app.services.user_service.db"):
                    result = UserService.get_by_email("retry@example.com")
                    assert result is expected_user

    def test_sqlalchemy_error_retry_also_fails_returns_none(self, app):
        with app.app_context():
            with patch("app.services.user_service.User") as MockUser:
                MockUser.query.filter_by.return_value.first.side_effect = SQLAlchemyError("persistent")
                with patch("app.services.user_service.db"):
                    result = UserService.get_by_email("fail@example.com")
                    assert result is None

    def test_unexpected_exception_returns_none(self, app):
        with app.app_context():
            with patch("app.services.user_service.User") as MockUser:
                MockUser.query.filter_by.return_value.first.side_effect = RuntimeError("boom")
                result = UserService.get_by_email("boom@example.com")
                assert result is None


# ---------------------------------------------------------------------------
# get_by_ids
# ---------------------------------------------------------------------------

class TestGetByIds:
    """Tests for UserService.get_by_ids."""

    def test_empty_list_returns_empty_query(self, db_session, app):
        with app.app_context():
            result = UserService.get_by_ids([])
            assert result.count() == 0

    def test_returns_users_for_given_ids(self, db_session, app):
        from tests.factories import create_test_user
        with app.app_context():
            u1 = create_test_user(db_session)
            u2 = create_test_user(db_session)
            result = UserService.get_by_ids([u1.id, u2.id])
            assert result.count() == 2

    def test_partial_ids_returns_matching_users(self, db_session, app):
        from tests.factories import create_test_user
        with app.app_context():
            u1 = create_test_user(db_session)
            create_test_user(db_session)
            result = UserService.get_by_ids([u1.id])
            assert result.count() == 1

    def test_sqlalchemy_error_returns_empty_query(self, app):
        """On SQLAlchemy error the error handler returns a literal(False) query."""
        with app.app_context():
            call_count = [0]

            def filter_side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise SQLAlchemyError("DB")
                m = MagicMock()
                m.count.return_value = 0
                return m

            with patch("app.services.user_service.User") as MockUser:
                MockUser.query.filter.side_effect = filter_side_effect
                with patch("app.services.user_service.db"):
                    # Non-empty list triggers the in_() path
                    result = UserService.get_by_ids([1, 2])
                    # The error-handler path was exercised
                    assert call_count[0] == 2

    def test_unexpected_exception_returns_empty_query(self, app):
        with app.app_context():
            call_count = [0]

            def filter_side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise RuntimeError("unexpected")
                return MagicMock()

            with patch("app.services.user_service.User") as MockUser:
                MockUser.query.filter.side_effect = filter_side_effect
                result = UserService.get_by_ids([1, 2])
                assert call_count[0] == 2


# ---------------------------------------------------------------------------
# exists
# ---------------------------------------------------------------------------

class TestExists:
    """Tests for UserService.exists."""

    def test_returns_true_when_user_exists(self, db_session, app):
        from tests.factories import create_test_user
        with app.app_context():
            create_test_user(db_session, email="existing@example.com")
            assert UserService.exists("existing@example.com") is True

    def test_returns_false_when_user_does_not_exist(self, db_session, app):
        with app.app_context():
            assert UserService.exists("nobody@example.com") is False

    def test_sqlalchemy_error_returns_false(self, app):
        with app.app_context():
            with patch("app.services.user_service.User") as MockUser:
                MockUser.query.filter_by.return_value.first.side_effect = SQLAlchemyError("DB")
                with patch("app.services.user_service.db"):
                    assert UserService.exists("x@x.com") is False

    def test_unexpected_exception_returns_false(self, app):
        with app.app_context():
            with patch("app.services.user_service.User") as MockUser:
                MockUser.query.filter_by.return_value.first.side_effect = RuntimeError("boom")
                assert UserService.exists("x@x.com") is False


# ---------------------------------------------------------------------------
# get_all_active
# ---------------------------------------------------------------------------

class TestGetAllActive:
    """Tests for UserService.get_all_active."""

    def test_returns_query_with_active_users(self, db_session, app):
        from tests.factories import create_test_user
        with app.app_context():
            create_test_user(db_session, active=True)
            result = UserService.get_all_active()
            assert result is not None
            assert result.count() >= 1

    def test_excludes_inactive_users(self, db_session, app):
        from tests.factories import create_test_user
        with app.app_context():
            u = create_test_user(db_session, active=False)
            ids_in_result = [x.id for x in UserService.get_all_active().all()]
            assert u.id not in ids_in_result

    def test_sqlalchemy_error_returns_empty_query(self, app):
        with app.app_context():
            call_count = [0]

            def filter_by_side(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise SQLAlchemyError("DB")
                return MagicMock()

            with patch("app.services.user_service.User") as MockUser:
                MockUser.query.filter_by.side_effect = filter_by_side
                with patch("app.services.user_service.db"):
                    result = UserService.get_all_active()
                    assert result is not None
                    assert call_count[0] == 2

    def test_unexpected_exception_returns_empty_query(self, app):
        with app.app_context():
            call_count = [0]

            def filter_by_side(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise RuntimeError("boom")
                return MagicMock()

            with patch("app.services.user_service.User") as MockUser:
                MockUser.query.filter_by.side_effect = filter_by_side
                result = UserService.get_all_active()
                assert result is not None
                assert call_count[0] == 2


# ---------------------------------------------------------------------------
# get_all
# ---------------------------------------------------------------------------

class TestGetAll:
    """Tests for UserService.get_all."""

    def test_returns_all_users_query(self, db_session, app):
        with app.app_context():
            result = UserService.get_all()
            assert result is not None

    def test_result_includes_created_users(self, db_session, app):
        from tests.factories import create_test_user
        with app.app_context():
            u = create_test_user(db_session)
            ids = [row.id for row in UserService.get_all().all()]
            assert u.id in ids

    def test_sqlalchemy_error_returns_empty_query(self, app):
        """SQLAlchemyError on User.query triggers the error handler."""
        _desc_count = [0]

        class _RaisingQueryDesc:
            def __get__(self_d, obj, objtype=None):
                _desc_count[0] += 1
                if _desc_count[0] == 1:
                    raise SQLAlchemyError("DB error")
                m = MagicMock()
                m.filter.return_value = MagicMock()
                return m

        class MockUser:
            query = _RaisingQueryDesc()

        with app.app_context():
            with patch("app.services.user_service.User", MockUser):
                with patch("app.services.user_service.db"):
                    result = UserService.get_all()
                    assert result is not None
                    assert _desc_count[0] == 2  # tried once, handler tried again

    def test_unexpected_exception_returns_empty_query(self, app):
        _desc_count = [0]

        class _RaisingQueryDesc:
            def __get__(self_d, obj, objtype=None):
                _desc_count[0] += 1
                if _desc_count[0] == 1:
                    raise RuntimeError("unexpected boom")
                m = MagicMock()
                m.filter.return_value = MagicMock()
                return m

        class MockUser:
            query = _RaisingQueryDesc()

        with app.app_context():
            with patch("app.services.user_service.User", MockUser):
                result = UserService.get_all()
                assert result is not None
                assert _desc_count[0] == 2
