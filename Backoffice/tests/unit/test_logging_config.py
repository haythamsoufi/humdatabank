"""Tests for app/logging_config.py — full coverage of all branches."""

import logging
import pytest
from unittest.mock import MagicMock, patch
from flask import Flask

from app.logging_config import (
    StaticFileFilter,
    SQLAlchemyRelationshipFilter,
    configure_access_log_filters,
    validate_email_configuration,
)


# ---------------------------------------------------------------------------
# StaticFileFilter
# ---------------------------------------------------------------------------

class TestStaticFileFilter:
    def setup_method(self):
        self.filter = StaticFileFilter()

    def _make_record(self, message):
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=message, args=(), exc_info=None
        )
        return record

    def test_static_path_filtered_out(self):
        record = self._make_record("GET /static/main.css HTTP/1.1 200")
        assert self.filter.filter(record) is False

    def test_favicon_filtered_out(self):
        record = self._make_record("GET /favicon.ico HTTP/1.1 200")
        assert self.filter.filter(record) is False

    def test_manifest_webmanifest_filtered_out(self):
        record = self._make_record("GET /manifest.webmanifest HTTP/1.1 200")
        assert self.filter.filter(record) is False

    def test_manifest_filtered_out(self):
        record = self._make_record("GET /manifest HTTP/1.1 200")
        assert self.filter.filter(record) is False

    def test_normal_request_not_filtered(self):
        record = self._make_record("GET /dashboard HTTP/1.1 200")
        assert self.filter.filter(record) is True

    def test_api_request_not_filtered(self):
        record = self._make_record("GET /api/data HTTP/1.1 200")
        assert self.filter.filter(record) is True

    def test_record_without_getMessage(self):
        """Records that somehow lack getMessage should pass through."""
        record = MagicMock(spec=[])  # no getMessage attribute
        assert self.filter.filter(record) is True


# ---------------------------------------------------------------------------
# SQLAlchemyRelationshipFilter
# ---------------------------------------------------------------------------

class TestSQLAlchemyRelationshipFilter:
    def setup_method(self):
        self.filter = SQLAlchemyRelationshipFilter()

    def _make_record(self, name):
        record = logging.LogRecord(
            name=name, level=logging.DEBUG, pathname="", lineno=0,
            msg="test", args=(), exc_info=None
        )
        return record

    def test_sqlalchemy_orm_relationships_filtered(self):
        record = self._make_record("sqlalchemy.orm.relationships")
        assert self.filter.filter(record) is False

    def test_sqlalchemy_orm_strategies_filtered(self):
        record = self._make_record("sqlalchemy.orm.strategies")
        assert self.filter.filter(record) is False

    def test_sqlalchemy_engine_not_filtered(self):
        record = self._make_record("sqlalchemy.engine")
        assert self.filter.filter(record) is True

    def test_other_logger_not_filtered(self):
        record = self._make_record("myapp.models")
        assert self.filter.filter(record) is True

    def test_sqlalchemy_orm_not_filtered(self):
        """sqlalchemy.orm (without sub-module) should pass through."""
        record = self._make_record("sqlalchemy.orm")
        assert self.filter.filter(record) is True


# ---------------------------------------------------------------------------
# configure_access_log_filters
# ---------------------------------------------------------------------------

class TestConfigureAccessLogFilters:
    def test_adds_static_filter_to_gunicorn_access(self):
        flask_app = Flask(__name__)
        configure_access_log_filters(flask_app)

        gunicorn_logger = logging.getLogger('gunicorn.access')
        filter_types = [type(f) for f in gunicorn_logger.filters]
        assert StaticFileFilter in filter_types

    def test_adds_static_filter_to_werkzeug(self):
        flask_app = Flask(__name__)
        configure_access_log_filters(flask_app)

        werkzeug_logger = logging.getLogger('werkzeug')
        filter_types = [type(f) for f in werkzeug_logger.filters]
        assert StaticFileFilter in filter_types

    def test_adds_relationship_filter_to_sqlalchemy(self):
        flask_app = Flask(__name__)
        configure_access_log_filters(flask_app)

        sa_logger = logging.getLogger('sqlalchemy.orm')
        filter_types = [type(f) for f in sa_logger.filters]
        assert SQLAlchemyRelationshipFilter in filter_types

    def test_sqlalchemy_orm_set_to_warning(self):
        flask_app = Flask(__name__)
        configure_access_log_filters(flask_app)
        sa_logger = logging.getLogger('sqlalchemy.orm')
        assert sa_logger.level == logging.WARNING


# ---------------------------------------------------------------------------
# validate_email_configuration
# ---------------------------------------------------------------------------

class TestValidateEmailConfiguration:
    def _make_app(self, **config):
        flask_app = Flask(__name__)
        flask_app.config.update(config)
        return flask_app

    def test_warns_when_mail_default_sender_missing(self):
        flask_app = self._make_app(EMAIL_API_KEY="key", EMAIL_API_URL="url")
        with flask_app.app_context():
            with patch.object(flask_app.logger, 'warning') as mock_warn:
                validate_email_configuration(flask_app)
            mock_warn.assert_called()
            warning_msgs = [str(c) for c in mock_warn.call_args_list]
            assert any("MAIL_DEFAULT_SENDER" in m for m in warning_msgs)

    def test_warns_when_email_api_key_missing(self):
        flask_app = self._make_app(MAIL_DEFAULT_SENDER="sender@example.com", EMAIL_API_URL="url")
        with flask_app.app_context():
            with patch.object(flask_app.logger, 'warning') as mock_warn:
                validate_email_configuration(flask_app)
            mock_warn.assert_called()
            warning_msgs = [str(c) for c in mock_warn.call_args_list]
            assert any("EMAIL_API_KEY" in m for m in warning_msgs)

    def test_warns_when_email_api_url_missing(self):
        flask_app = self._make_app(MAIL_DEFAULT_SENDER="sender@example.com", EMAIL_API_KEY="key")
        with flask_app.app_context():
            with patch.object(flask_app.logger, 'warning') as mock_warn:
                validate_email_configuration(flask_app)
            mock_warn.assert_called()
            warning_msgs = [str(c) for c in mock_warn.call_args_list]
            assert any("EMAIL_API_URL" in m for m in warning_msgs)

    def test_logs_ok_when_all_configured(self):
        flask_app = self._make_app(
            MAIL_DEFAULT_SENDER="sender@example.com",
            EMAIL_API_KEY="key",
            EMAIL_API_URL="https://api.example.com",
        )
        with flask_app.app_context():
            with patch.object(flask_app.logger, 'debug') as mock_debug:
                validate_email_configuration(flask_app)
            mock_debug.assert_called()
            debug_msgs = [str(c) for c in mock_debug.call_args_list]
            assert any("[OK]" in m for m in debug_msgs)

    def test_logs_info_when_partially_configured(self):
        """When sender is set but API details incomplete, logs info (not debug OK)."""
        flask_app = self._make_app(MAIL_DEFAULT_SENDER="sender@example.com")
        with flask_app.app_context():
            with patch.object(flask_app.logger, 'info') as mock_info:
                validate_email_configuration(flask_app)
            mock_info.assert_called()

    def test_no_config_at_all(self):
        """Should not raise, just warn about missing items."""
        flask_app = Flask(__name__)
        with flask_app.app_context():
            # Should not raise
            validate_email_configuration(flask_app)
