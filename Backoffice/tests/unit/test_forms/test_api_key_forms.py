"""Unit tests for app/forms/system/api_key_forms.py — targets 100% coverage."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from werkzeug.datastructures import ImmutableMultiDict

pytestmark = [pytest.mark.unit]


def _future_dt():
    """Timezone-aware future datetime."""
    return datetime.now(timezone.utc) + timedelta(hours=24)


def _past_dt():
    """Timezone-aware past datetime."""
    return datetime.now(timezone.utc) - timedelta(hours=1)


# ---------------------------------------------------------------------------
# APIKeyForm
# ---------------------------------------------------------------------------

class TestAPIKeyForm:
    def test_valid_minimal(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyForm
            form = APIKeyForm(data={'client_name': 'Mobile App'})
            assert form.validate() is True

    def test_missing_client_name(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyForm
            form = APIKeyForm(data={})
            assert form.validate() is False
            assert 'client_name' in form.errors

    def test_client_name_too_long(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyForm
            form = APIKeyForm(data={'client_name': 'x' * 256})
            assert form.validate() is False
            assert 'client_name' in form.errors

    def test_optional_description(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyForm
            form = APIKeyForm(formdata=ImmutableMultiDict([
                ('client_name', 'App'),
                ('client_description', 'A nice description'),
            ]))
            assert form.validate() is True

    def test_description_too_long(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyForm
            form = APIKeyForm(formdata=ImmutableMultiDict([
                ('client_name', 'App'),
                ('client_description', 'x' * 1001),
            ]))
            assert form.validate() is False
            assert 'client_description' in form.errors

    def test_rate_limit_valid(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyForm
            form = APIKeyForm(formdata=ImmutableMultiDict([
                ('client_name', 'App'),
                ('rate_limit_per_minute', '100'),
            ]))
            assert form.validate() is True

    def test_rate_limit_too_low(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyForm
            form = APIKeyForm(formdata=ImmutableMultiDict([
                ('client_name', 'App'),
                ('rate_limit_per_minute', '0'),
            ]))
            assert form.validate() is False
            assert 'rate_limit_per_minute' in form.errors

    def test_rate_limit_too_high(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyForm
            form = APIKeyForm(formdata=ImmutableMultiDict([
                ('client_name', 'App'),
                ('rate_limit_per_minute', '10001'),
            ]))
            assert form.validate() is False
            assert 'rate_limit_per_minute' in form.errors

    def test_expiry_in_future_passes(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyForm
            future = datetime.utcnow() + timedelta(hours=24)
            # Mock utcnow to return naive datetime so WTForms DateTimeField comparison works
            with patch('app.forms.system.api_key_forms.utcnow', return_value=datetime.utcnow()):
                form = APIKeyForm(formdata=ImmutableMultiDict([
                    ('client_name', 'App'),
                    ('expires_at', future.strftime('%Y-%m-%dT%H:%M')),
                ]))
                assert form.validate() is True

    def test_expiry_in_past_fails(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyForm
            past = datetime.utcnow() - timedelta(hours=1)
            with patch('app.forms.system.api_key_forms.utcnow', return_value=datetime.utcnow()):
                form = APIKeyForm(formdata=ImmutableMultiDict([
                    ('client_name', 'App'),
                    ('expires_at', past.strftime('%Y-%m-%dT%H:%M')),
                ]))
                result = form.validate()
            assert result is False
            assert 'expires_at' in form.errors

    def test_validate_expires_at_past_directly(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyForm
            from wtforms.validators import ValidationError
            from unittest.mock import MagicMock
            form = APIKeyForm(data={'client_name': 'App'})
            field = MagicMock()
            # Use naive datetime for direct comparison (both naive)
            past_naive = datetime.utcnow() - timedelta(hours=1)
            field.data = past_naive
            with patch('app.forms.system.api_key_forms.utcnow', return_value=datetime.utcnow()):
                with pytest.raises(ValidationError, match="future"):
                    form.validate_expires_at(field)

    def test_validate_expires_at_none_passes(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyForm
            from unittest.mock import MagicMock
            form = APIKeyForm(data={'client_name': 'App'})
            field = MagicMock()
            field.data = None
            form.validate_expires_at(field)  # should not raise


# ---------------------------------------------------------------------------
# APIKeyEditForm
# ---------------------------------------------------------------------------

class TestAPIKeyEditForm:
    def test_valid_minimal(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyEditForm
            form = APIKeyEditForm(data={'client_name': 'Updated App'})
            assert form.validate() is True

    def test_missing_client_name(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyEditForm
            form = APIKeyEditForm(data={})
            assert form.validate() is False
            assert 'client_name' in form.errors

    def test_future_expiry_passes(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyEditForm
            future = datetime.utcnow() + timedelta(hours=24)
            with patch('app.forms.system.api_key_forms.utcnow', return_value=datetime.utcnow()):
                form = APIKeyEditForm(formdata=ImmutableMultiDict([
                    ('client_name', 'App'),
                    ('expires_at', future.strftime('%Y-%m-%dT%H:%M')),
                ]))
                assert form.validate() is True

    def test_past_expiry_fails(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyEditForm
            past = datetime.utcnow() - timedelta(hours=1)
            with patch('app.forms.system.api_key_forms.utcnow', return_value=datetime.utcnow()):
                form = APIKeyEditForm(formdata=ImmutableMultiDict([
                    ('client_name', 'App'),
                    ('expires_at', past.strftime('%Y-%m-%dT%H:%M')),
                ]))
                result = form.validate()
            assert result is False
            assert 'expires_at' in form.errors

    def test_validate_expires_at_past_directly(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyEditForm
            from wtforms.validators import ValidationError
            from unittest.mock import MagicMock
            form = APIKeyEditForm(data={'client_name': 'App'})
            field = MagicMock()
            past_naive = datetime.utcnow() - timedelta(hours=1)
            field.data = past_naive
            with patch('app.forms.system.api_key_forms.utcnow', return_value=datetime.utcnow()):
                with pytest.raises(ValidationError):
                    form.validate_expires_at(field)

    def test_validate_expires_at_none_passes(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyEditForm
            from unittest.mock import MagicMock
            form = APIKeyEditForm(data={'client_name': 'App'})
            field = MagicMock()
            field.data = None
            form.validate_expires_at(field)  # should not raise


# ---------------------------------------------------------------------------
# APIKeyRevokeForm
# ---------------------------------------------------------------------------

class TestAPIKeyRevokeForm:
    def test_valid_with_reason(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyRevokeForm
            form = APIKeyRevokeForm(data={'revocation_reason': 'Key compromised'})
            assert form.validate() is True

    def test_valid_without_reason(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyRevokeForm
            form = APIKeyRevokeForm(data={})
            assert form.validate() is True

    def test_reason_too_long(self, app):
        with app.app_context():
            from app.forms.system.api_key_forms import APIKeyRevokeForm
            form = APIKeyRevokeForm(formdata=ImmutableMultiDict([
                ('revocation_reason', 'x' * 501),
            ]))
            assert form.validate() is False
            assert 'revocation_reason' in form.errors
