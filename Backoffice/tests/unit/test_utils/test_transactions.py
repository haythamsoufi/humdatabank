"""
Unit tests for transactions utilities.

Covers: register_post_commit, run_post_commit_callbacks, safe_rollback,
safe_remove, request_transaction_rollback, atomic, no_auto_transaction,
force_transaction, is_view_opted_out, is_view_forced, is_streaming_response.
"""
import pytest
from unittest.mock import MagicMock, patch, call

from app.utils.transactions import (
    register_post_commit,
    run_post_commit_callbacks,
    safe_rollback,
    safe_remove,
    request_transaction_rollback,
    atomic,
    no_auto_transaction,
    force_transaction,
    is_view_opted_out,
    is_view_forced,
    is_streaming_response,
)


# ---------------------------------------------------------------------------
# register_post_commit
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRegisterPostCommit:
    def test_calls_fn_immediately_outside_request_context(self):
        called = []
        def cb(a, b=None):
            called.append((a, b))
        register_post_commit(cb, 1, b='x')
        assert called == [(1, 'x')]

    def test_error_in_fn_does_not_raise_outside_request_context(self):
        def bad_cb():
            raise RuntimeError('callback failed')
        # Should not raise
        register_post_commit(bad_cb)

    def test_fn_queued_in_request_context(self, app):
        with app.test_request_context():
            from flask import g
            called = []
            def cb():
                called.append(True)
            register_post_commit(cb)
            assert hasattr(g, '_post_commit_callbacks')
            assert len(g._post_commit_callbacks) == 1
            # callback not yet called
            assert called == []

    def test_multiple_callbacks_queued(self, app):
        with app.test_request_context():
            from flask import g
            register_post_commit(lambda: None)
            register_post_commit(lambda: None)
            assert len(g._post_commit_callbacks) == 2

    def test_args_and_kwargs_stored(self, app):
        with app.test_request_context():
            from flask import g
            sentinel = MagicMock()
            register_post_commit(sentinel, 'arg1', key='val')
            fn, args, kwargs = g._post_commit_callbacks[0]
            assert fn is sentinel
            assert args == ('arg1',)
            assert kwargs == {'key': 'val'}


# ---------------------------------------------------------------------------
# run_post_commit_callbacks
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRunPostCommitCallbacks:
    def test_runs_all_callbacks(self, app):
        with app.test_request_context():
            from flask import g
            results = []
            g._post_commit_callbacks = [
                (lambda: results.append(1), (), {}),
                (lambda: results.append(2), (), {}),
            ]
            run_post_commit_callbacks()
            assert results == [1, 2]

    def test_clears_callbacks_after_run(self, app):
        with app.test_request_context():
            from flask import g
            g._post_commit_callbacks = [(lambda: None, (), {})]
            run_post_commit_callbacks()
            assert g._post_commit_callbacks == []

    def test_error_in_callback_does_not_raise(self, app):
        with app.test_request_context():
            from flask import g
            def bad():
                raise RuntimeError('fail in callback')
            g._post_commit_callbacks = [(bad, (), {})]
            run_post_commit_callbacks()  # should not raise

    def test_no_callbacks_no_error(self, app):
        with app.test_request_context():
            from flask import g
            g._post_commit_callbacks = []
            run_post_commit_callbacks()  # should not raise

    def test_no_op_outside_request_context(self):
        # Should return early without error
        run_post_commit_callbacks()

    def test_callbacks_with_args_and_kwargs(self, app):
        with app.test_request_context():
            from flask import g
            received = []
            def cb(a, b=None):
                received.append((a, b))
            g._post_commit_callbacks = [(cb, ('hello',), {'b': 'world'})]
            run_post_commit_callbacks()
            assert received == [('hello', 'world')]


# ---------------------------------------------------------------------------
# safe_rollback
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSafeRollback:
    def test_rollback_called_on_session(self, app):
        with app.app_context():
            with patch('app.extensions.db') as mock_db:
                safe_rollback(reason='test')
                mock_db.session.rollback.assert_called_once()

    def test_does_not_raise_when_rollback_fails(self, app):
        with app.app_context():
            with patch('app.extensions.db') as mock_db:
                mock_db.session.rollback.side_effect = Exception('DB error')
                safe_rollback(reason='test')  # should not raise

    def test_no_reason_works(self, app):
        with app.app_context():
            with patch('app.extensions.db') as mock_db:
                safe_rollback()
                mock_db.session.rollback.assert_called_once()

    def test_clears_post_commit_callbacks(self, app):
        with app.test_request_context():
            from flask import g
            g._post_commit_callbacks = [('fn', (), {})]
            with patch('app.extensions.db'):
                safe_rollback(reason='clearing')
            assert g._post_commit_callbacks == []


# ---------------------------------------------------------------------------
# safe_remove
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSafeRemove:
    def test_removes_session_in_app_context(self, app):
        with app.app_context():
            with patch('app.extensions.db') as mock_db:
                safe_remove(reason='test')
                mock_db.session.remove.assert_called_once()

    def test_does_not_raise_outside_app_context(self):
        # Outside any app context -> silently skip
        safe_remove(reason='no-context')

    def test_does_not_raise_when_remove_fails(self, app):
        with app.app_context():
            with patch('app.extensions.db') as mock_db:
                mock_db.session.remove.side_effect = Exception('remove failed')
                safe_remove()  # should not raise

    def test_no_reason_works(self, app):
        with app.app_context():
            with patch('app.extensions.db') as mock_db:
                safe_remove()
                mock_db.session.remove.assert_called_once()


# ---------------------------------------------------------------------------
# request_transaction_rollback
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRequestTransactionRollback:
    def test_sets_force_rollback_flag_in_request_context(self, app):
        with app.test_request_context():
            from flask import g
            with patch('app.extensions.db'):
                request_transaction_rollback(reason='test')
            assert getattr(g, '_auto_txn_force_rollback', False) is True

    def test_calls_safe_rollback(self, app):
        with app.test_request_context():
            with patch('app.utils.transactions.safe_rollback') as mock_rb:
                request_transaction_rollback(reason='manual')
                mock_rb.assert_called_once_with(reason='manual')

    def test_safe_rollback_called_without_reason(self, app):
        with app.test_request_context():
            with patch('app.utils.transactions.safe_rollback') as mock_rb:
                request_transaction_rollback()
                # reason defaults to 'manual_request' in safe_rollback call
                mock_rb.assert_called_once_with(reason='manual_request')

    def test_works_outside_request_context(self):
        with patch('app.utils.transactions.safe_rollback') as mock_rb:
            request_transaction_rollback(reason='outside')
            mock_rb.assert_called_once_with(reason='outside')


# ---------------------------------------------------------------------------
# atomic
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAtomic:
    def test_commits_on_success(self, app):
        with app.app_context():
            with patch('app.extensions.db') as mock_db:
                with atomic():
                    pass
                mock_db.session.commit.assert_called_once()

    def test_rollback_on_exception(self, app):
        with app.app_context():
            with patch('app.extensions.db') as mock_db, \
                 patch('app.utils.transactions.safe_rollback') as mock_rb:
                with pytest.raises(ValueError):
                    with atomic():
                        raise ValueError('fail')
                mock_rb.assert_called_once_with(reason='atomic_exception')

    def test_re_raises_exception(self, app):
        with app.app_context():
            with patch('app.extensions.db'), \
                 patch('app.utils.transactions.safe_rollback'):
                with pytest.raises(RuntimeError, match='expected'):
                    with atomic():
                        raise RuntimeError('expected')

    def test_remove_session_when_flag_set(self, app):
        with app.app_context():
            with patch('app.extensions.db'), \
                 patch('app.utils.transactions.safe_remove') as mock_remove:
                with atomic(remove_session=True):
                    pass
                mock_remove.assert_called_once_with(reason='atomic_finally')

    def test_no_remove_session_by_default(self, app):
        with app.app_context():
            with patch('app.extensions.db'), \
                 patch('app.utils.transactions.safe_remove') as mock_remove:
                with atomic():
                    pass
                mock_remove.assert_not_called()

    def test_remove_session_called_even_on_exception(self, app):
        with app.app_context():
            with patch('app.extensions.db'), \
                 patch('app.utils.transactions.safe_rollback'), \
                 patch('app.utils.transactions.safe_remove') as mock_remove:
                with pytest.raises(ValueError):
                    with atomic(remove_session=True):
                        raise ValueError('fail')
                mock_remove.assert_called_once_with(reason='atomic_finally')


# ---------------------------------------------------------------------------
# no_auto_transaction / force_transaction decorators
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTransactionDecorators:
    def test_no_auto_transaction_sets_attribute(self):
        def my_view():
            pass
        decorated = no_auto_transaction(my_view)
        assert getattr(decorated, '_no_auto_transaction', False) is True

    def test_no_auto_transaction_returns_original_function(self):
        def my_view():
            return 'ok'
        decorated = no_auto_transaction(my_view)
        assert decorated() == 'ok'

    def test_force_transaction_sets_attribute(self):
        def my_view():
            pass
        decorated = force_transaction(my_view)
        assert getattr(decorated, '_force_transaction', False) is True

    def test_force_transaction_returns_original_function(self):
        def my_view():
            return 42
        decorated = force_transaction(my_view)
        assert decorated() == 42


# ---------------------------------------------------------------------------
# is_view_opted_out / is_view_forced
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestViewFlagHelpers:
    def test_opted_out_when_attribute_true(self):
        fn = MagicMock()
        fn._no_auto_transaction = True
        assert is_view_opted_out(fn) is True

    def test_not_opted_out_when_attribute_false(self):
        fn = MagicMock()
        fn._no_auto_transaction = False
        assert is_view_opted_out(fn) is False

    def test_not_opted_out_when_attribute_missing(self):
        def plain_view():
            pass
        assert is_view_opted_out(plain_view) is False

    def test_not_opted_out_when_none(self):
        assert is_view_opted_out(None) is False

    def test_forced_when_attribute_true(self):
        fn = MagicMock()
        fn._force_transaction = True
        assert is_view_forced(fn) is True

    def test_not_forced_when_attribute_false(self):
        fn = MagicMock()
        fn._force_transaction = False
        assert is_view_forced(fn) is False

    def test_not_forced_when_attribute_missing(self):
        def plain_view():
            pass
        assert is_view_forced(plain_view) is False

    def test_not_forced_when_none(self):
        assert is_view_forced(None) is False


# ---------------------------------------------------------------------------
# is_streaming_response
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestIsStreamingResponse:
    def test_is_streamed_true(self):
        response = MagicMock()
        response.is_streamed = True
        assert is_streaming_response(response) is True

    def test_is_streamed_false(self):
        response = MagicMock()
        response.is_streamed = False
        response.headers = {'Content-Type': 'application/json'}
        assert is_streaming_response(response) is False

    def test_sse_content_type_detected(self):
        response = MagicMock()
        response.is_streamed = False
        response.headers = {'Content-Type': 'text/event-stream'}
        assert is_streaming_response(response) is True

    def test_sse_content_type_case_insensitive(self):
        response = MagicMock()
        response.is_streamed = False
        response.headers = {'Content-Type': 'Text/Event-Stream; charset=utf-8'}
        assert is_streaming_response(response) is True

    def test_normal_json_response_not_streaming(self):
        response = MagicMock()
        response.is_streamed = False
        response.headers = {'Content-Type': 'application/json'}
        assert is_streaming_response(response) is False

    def test_no_headers_attribute(self):
        response = MagicMock()
        response.is_streamed = False
        del response.headers
        # Should not raise; headers is None -> content_type = ""
        result = is_streaming_response(response)
        assert result is False

    def test_exception_in_detection_returns_false(self):
        response = MagicMock()
        response.is_streamed = False
        type(response).headers = property(lambda self: (_ for _ in ()).throw(Exception('attr error')))
        result = is_streaming_response(response)
        assert result is False

    def test_none_headers_does_not_raise(self):
        response = MagicMock()
        response.is_streamed = False
        response.headers = None
        result = is_streaming_response(response)
        assert result is False
