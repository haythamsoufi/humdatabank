"""
Unit tests for error_handling utilities.

Covers: suppress_with_log, handle_view_exception, handle_json_view_exception.
"""
import logging
import pytest
from unittest.mock import MagicMock, patch, call

from app.utils.error_handling import (
    suppress_with_log,
    handle_view_exception,
    handle_json_view_exception,
)


# ---------------------------------------------------------------------------
# suppress_with_log
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSuppressWithLog:
    def test_no_exception_passes_through(self):
        result = []
        with suppress_with_log(ValueError):
            result.append('ran')
        assert result == ['ran']

    def test_suppresses_specified_exception(self):
        with suppress_with_log(ValueError, message='test suppression'):
            raise ValueError('intentional')
        # No exception raised -> test passes

    def test_does_not_suppress_unspecified_exception(self):
        with pytest.raises(RuntimeError):
            with suppress_with_log(ValueError, message='only suppresses ValueError'):
                raise RuntimeError('should propagate')

    def test_logs_message_on_exception(self):
        with patch('app.utils.error_handling.logger') as mock_logger:
            with suppress_with_log(TypeError, message='Optional op failed', log_level=logging.DEBUG):
                raise TypeError('bad type')
            mock_logger.log.assert_called_once()
            call_args = mock_logger.log.call_args
            assert 'Optional op failed' in call_args[0][1]

    def test_custom_log_level_used(self):
        with patch('app.utils.error_handling.logger') as mock_logger:
            with suppress_with_log(AttributeError, message='attr error', log_level=logging.WARNING):
                raise AttributeError('no attr')
            call_args = mock_logger.log.call_args
            assert call_args[0][0] == logging.WARNING

    def test_multiple_exception_types_all_suppressed(self):
        for exc_class in [ValueError, TypeError, AttributeError]:
            with suppress_with_log(ValueError, TypeError, AttributeError):
                raise exc_class('one of many')
            # All suppressed

    def test_exception_included_in_log_message(self):
        with patch('app.utils.error_handling.logger') as mock_logger:
            with suppress_with_log(KeyError, message='Missing key'):
                raise KeyError('some_key')
            logged_msg = mock_logger.log.call_args[0][1]
            assert 'Missing key' in logged_msg


# ---------------------------------------------------------------------------
# handle_view_exception
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestHandleViewException:
    def test_returns_none_when_no_redirect(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback'):
                result = handle_view_exception(
                    ValueError('test'), 'An error occurred'
                )
            assert result is None

    def test_flashes_user_message(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback'), \
                 patch('app.utils.error_handling.flash') as mock_flash:
                handle_view_exception(ValueError('test'), 'User-visible error')
                mock_flash.assert_called_once_with('User-visible error', 'danger')

    def test_custom_flash_category(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback'), \
                 patch('app.utils.error_handling.flash') as mock_flash:
                handle_view_exception(
                    ValueError('test'), 'Warning msg', flash_category='warning'
                )
                mock_flash.assert_called_once_with('Warning msg', 'warning')

    def test_redirects_to_url_when_provided(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback'), \
                 patch('app.utils.error_handling.flash'):
                result = handle_view_exception(
                    ValueError('test'), 'Error', redirect_url='/dashboard'
                )
            assert result is not None
            assert result.status_code in (301, 302)

    def test_redirects_to_endpoint_when_provided(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback'), \
                 patch('app.utils.error_handling.flash'):
                # 'main.dashboard' might not exist in test app, so use a registered endpoint
                # Just test that redirect() is called with url_for result
                with patch('app.utils.error_handling.redirect') as mock_redirect, \
                     patch('app.utils.error_handling.url_for', return_value='/some/path') as mock_url_for:
                    handle_view_exception(
                        ValueError('test'), 'Error',
                        redirect_endpoint='some.endpoint',
                        redirect_kwargs={'id': 1}
                    )
                    mock_url_for.assert_called_once_with('some.endpoint', id=1)
                    mock_redirect.assert_called_once_with('/some/path')

    def test_abort_called_when_abort_on_unhandled(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback'), \
                 patch('app.utils.error_handling.flash'), \
                 patch('flask.abort') as mock_abort:
                handle_view_exception(
                    ValueError('test'), 'Error',
                    abort_on_unhandled=True, status_code=500
                )
                mock_abort.assert_called_once_with(500)

    def test_rollback_called(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback') as mock_rb, \
                 patch('app.utils.error_handling.flash'):
                handle_view_exception(ValueError('test'), 'Error')
                mock_rb.assert_called_once()

    def test_custom_rollback_reason(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback') as mock_rb, \
                 patch('app.utils.error_handling.flash'):
                handle_view_exception(
                    ValueError('test'), 'Error', rollback_reason='custom_rollback'
                )
                mock_rb.assert_called_once_with(reason='custom_rollback')

    def test_logs_error_with_exc_info(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback'), \
                 patch('app.utils.error_handling.flash'):
                # current_app.logger.error should be called with exc_info=True
                with patch.object(app.logger, 'error') as mock_log:
                    handle_view_exception(ValueError('test'), 'User message')
                    mock_log.assert_called_once()
                    call_kwargs = mock_log.call_args[1]
                    assert call_kwargs.get('exc_info') is True

    def test_custom_log_message(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback'), \
                 patch('app.utils.error_handling.flash'):
                with patch.object(app.logger, 'error') as mock_log:
                    handle_view_exception(
                        ValueError('test'), 'User msg',
                        log_message='Technical details for devs'
                    )
                    mock_log.assert_called_once_with('Technical details for devs', exc_info=True)

    def test_no_flash_when_message_empty(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback'), \
                 patch('app.utils.error_handling.flash') as mock_flash:
                handle_view_exception(ValueError('test'), user_message='')
                mock_flash.assert_not_called()

    def test_redirect_url_takes_priority_over_endpoint(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback'), \
                 patch('app.utils.error_handling.flash'), \
                 patch('app.utils.error_handling.redirect') as mock_redirect, \
                 patch('app.utils.error_handling.url_for') as mock_url_for:
                handle_view_exception(
                    ValueError('test'), 'Error',
                    redirect_url='/direct',
                    redirect_endpoint='some.endpoint'
                )
                mock_redirect.assert_called_once_with('/direct')
                mock_url_for.assert_not_called()


# ---------------------------------------------------------------------------
# handle_json_view_exception
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestHandleJsonViewException:
    def test_returns_json_error_tuple(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback'):
                resp, status = handle_json_view_exception(
                    ValueError('test'), 'Operation failed'
                )
        assert status == 500
        data = resp.get_json()
        assert data['error'] == 'Operation failed'
        assert data['success'] is False

    def test_custom_status_code(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback'):
                resp, status = handle_json_view_exception(
                    ValueError('test'), 'Bad input', status_code=400
                )
        assert status == 400

    def test_rollback_called(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback') as mock_rb:
                handle_json_view_exception(ValueError('test'), 'Error')
                mock_rb.assert_called_once()

    def test_custom_rollback_reason(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback') as mock_rb:
                handle_json_view_exception(
                    ValueError('test'), 'Error', rollback_reason='json_view'
                )
                mock_rb.assert_called_once_with(reason='json_view')

    def test_logs_error(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback'):
                with patch.object(app.logger, 'error') as mock_log:
                    handle_json_view_exception(ValueError('boom'), 'Oops')
                    mock_log.assert_called_once()
                    call_kwargs = mock_log.call_args[1]
                    assert call_kwargs.get('exc_info') is True

    def test_custom_log_message(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback'):
                with patch.object(app.logger, 'error') as mock_log:
                    handle_json_view_exception(
                        ValueError('test'), 'User msg',
                        log_message='Internal technical info'
                    )
                    mock_log.assert_called_once_with(
                        'Internal technical info', exc_info=True
                    )

    def test_default_log_message_when_none(self, app):
        with app.test_request_context():
            with patch('app.utils.error_handling.request_transaction_rollback'):
                with patch.object(app.logger, 'error') as mock_log:
                    handle_json_view_exception(ValueError('test'), '')
                    logged_msg = mock_log.call_args[0][0]
                    assert logged_msg  # fallback message used
