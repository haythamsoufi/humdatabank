"""
Unit tests for api_key_management.py to achieve 100% code coverage.

Covers: APIKey, APIKeyUsage, resolve_api_key_data_access
"""
import pytest
from datetime import timedelta
from unittest.mock import patch

from app.models.api_key_management import (
    APIKey,
    APIKeyUsage,
    resolve_api_key_data_access,
    API_KEY_DATA_READ_ALL,
    API_KEY_DATA_READ_SCOPED,
    API_KEY_DATA_NONE,
)
from app.utils.datetime_helpers import utcnow
from tests.factories import create_test_user, create_test_api_key


@pytest.mark.unit
class TestResolveApiKeyDataAccess:
    """Tests for resolve_api_key_data_access function."""

    def test_none_permissions_returns_read_all(self):
        """None permissions returns read_all."""
        mode, scope = resolve_api_key_data_access(None)
        assert mode == API_KEY_DATA_READ_ALL
        assert scope is None

    def test_non_dict_permissions_returns_read_all(self):
        """Non-dict permissions returns read_all."""
        mode, scope = resolve_api_key_data_access('read_all')
        assert mode == API_KEY_DATA_READ_ALL
        assert scope is None

    def test_empty_dict_returns_read_all(self):
        """Empty dict permissions returns read_all."""
        mode, scope = resolve_api_key_data_access({})
        assert mode == API_KEY_DATA_READ_ALL
        assert scope is None

    def test_explicit_read_all(self):
        """Explicit read_all returns read_all."""
        mode, scope = resolve_api_key_data_access({'data': 'read_all'})
        assert mode == API_KEY_DATA_READ_ALL
        assert scope is None

    def test_data_none_in_dict(self):
        """data=None in dict returns read_all."""
        mode, scope = resolve_api_key_data_access({'data': None})
        assert mode == API_KEY_DATA_READ_ALL

    def test_read_scoped_with_ids(self):
        """read_scoped with template_ids and country_ids."""
        permissions = {
            'data': 'read_scoped',
            'template_ids': [1, 2, 3],
            'country_ids': [10, 20],
        }
        mode, scope = resolve_api_key_data_access(permissions)
        assert mode == API_KEY_DATA_READ_SCOPED
        assert scope is not None
        assert scope['template_ids'] == [1, 2, 3]
        assert scope['country_ids'] == [10, 20]

    def test_read_scoped_with_none_ids(self):
        """read_scoped with None values in id lists - filters out None."""
        permissions = {
            'data': 'read_scoped',
            'template_ids': [1, None, 2],
            'country_ids': None,
        }
        mode, scope = resolve_api_key_data_access(permissions)
        assert mode == API_KEY_DATA_READ_SCOPED
        assert 1 in scope['template_ids']
        assert 2 in scope['template_ids']
        assert scope['country_ids'] == []

    def test_read_scoped_empty_lists(self):
        """read_scoped with empty lists."""
        permissions = {'data': 'read_scoped'}
        mode, scope = resolve_api_key_data_access(permissions)
        assert mode == API_KEY_DATA_READ_SCOPED
        assert scope['template_ids'] == []
        assert scope['country_ids'] == []

    def test_data_none_perm_returns_none(self):
        """data='none' returns none access."""
        mode, scope = resolve_api_key_data_access({'data': 'none'})
        assert mode == API_KEY_DATA_NONE
        assert scope is None

    def test_unknown_perm_returns_read_all(self):
        """Unknown data permission returns read_all."""
        mode, scope = resolve_api_key_data_access({'data': 'unknown_perm'})
        assert mode == API_KEY_DATA_READ_ALL


@pytest.mark.unit
class TestAPIKey:
    """Tests for APIKey model."""

    def test_generate_key(self, db_session, app):
        """Test generate_key returns valid tuple."""
        with app.app_context():
            full_key, key_id, key_hash, key_prefix = APIKey.generate_key()
            assert len(full_key) > 0
            assert len(key_id) == 32  # 16 hex bytes = 32 chars
            assert len(key_hash) == 64  # SHA256 = 64 hex chars
            assert key_prefix == full_key[:8]

    def test_hash_key(self, db_session, app):
        """Test hash_key produces consistent hash."""
        with app.app_context():
            key = 'test-api-key-value'
            h1 = APIKey.hash_key(key)
            h2 = APIKey.hash_key(key)
            assert h1 == h2
            assert len(h1) == 64

    def test_create_api_key(self, db_session, app):
        """Test creating an API key."""
        with app.app_context():
            api_key_obj, full_key = create_test_api_key(db_session)
            assert api_key_obj.id is not None
            assert api_key_obj.is_active is True
            assert api_key_obj.is_revoked is False

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session, client_name='My Client')
            result = repr(api_key_obj)
            assert 'My Client' in result

    def test_verify_key_correct(self, db_session, app):
        """Test verify_key with correct key returns True."""
        with app.app_context():
            api_key_obj, full_key = create_test_api_key(db_session)
            assert api_key_obj.verify_key(full_key) is True

    def test_verify_key_incorrect(self, db_session, app):
        """Test verify_key with wrong key returns False."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            assert api_key_obj.verify_key('wrong-key') is False

    def test_status_active(self, db_session, app):
        """Test status is 'active' when is_active=True and not revoked/expired."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            assert api_key_obj.status == 'active'

    def test_status_revoked(self, db_session, app):
        """Test status is 'revoked' when is_revoked=True."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            api_key_obj.is_revoked = True
            assert api_key_obj.status == 'revoked'

    def test_status_disabled(self, db_session, app):
        """Test status is 'disabled' when is_active=False and not revoked."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            api_key_obj.is_active = False
            api_key_obj.is_revoked = False
            assert api_key_obj.status == 'disabled'

    def test_status_expired(self, db_session, app):
        """Test status is 'expired' when expires_at is in the past."""
        with app.app_context():
            past_time = utcnow() - timedelta(hours=1)
            api_key_obj, _ = create_test_api_key(db_session)
            api_key_obj.expires_at = past_time
            api_key_obj.is_active = True
            api_key_obj.is_revoked = False
            # expires_at is past => expired
            assert api_key_obj.status == 'expired'

    def test_status_future_expiry_active(self, db_session, app):
        """Test status is 'active' when expires_at is in the future."""
        with app.app_context():
            future_time = utcnow() + timedelta(days=30)
            api_key_obj, _ = create_test_api_key(db_session)
            api_key_obj.expires_at = future_time
            assert api_key_obj.status == 'active'

    def test_is_valid_active(self, db_session, app):
        """Test is_valid returns True when active."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            assert api_key_obj.is_valid() is True

    def test_is_valid_revoked(self, db_session, app):
        """Test is_valid returns False when revoked."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            api_key_obj.is_revoked = True
            assert api_key_obj.is_valid() is False

    def test_disable(self, db_session, app):
        """Test disable sets is_active=False."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            api_key_obj.disable()
            assert api_key_obj.is_active is False
            assert api_key_obj.is_revoked is False

    def test_disable_with_reason(self, db_session, app):
        """Test disable stores reason."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            api_key_obj.disable(reason='Suspicious activity')
            assert api_key_obj.revocation_reason == 'Suspicious activity'

    def test_enable(self, db_session, app):
        """Test enable sets is_active=True."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            api_key_obj.disable()
            api_key_obj.enable()
            assert api_key_obj.is_active is True

    def test_enable_revoked_raises(self, db_session, app):
        """Test enable raises ValueError when key is revoked."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            api_key_obj.is_revoked = True
            api_key_obj.is_active = False
            with pytest.raises(ValueError, match='Cannot enable a revoked'):
                api_key_obj.enable()

    def test_revoke(self, db_session, app):
        """Test revoke sets is_revoked=True."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            api_key_obj.revoke(reason='Compromised')
            assert api_key_obj.is_revoked is True
            assert api_key_obj.is_active is False
            assert api_key_obj.revocation_reason == 'Compromised'
            assert api_key_obj.revoked_at is not None

    def test_revoke_with_user(self, db_session, app):
        """Test revoke stores revoked_by_user_id."""
        with app.app_context():
            user = create_test_user(db_session)
            api_key_obj, _ = create_test_api_key(db_session)
            api_key_obj.revoke(revoked_by_user_id=user.id)
            assert api_key_obj.revoked_by_user_id == user.id

    def test_revoke_without_user(self, db_session, app):
        """Test revoke without revoked_by_user_id."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            api_key_obj.revoke()
            assert api_key_obj.is_revoked is True
            assert api_key_obj.revoked_by_user_id is None

    def test_update_last_used(self, db_session, app):
        """Test update_last_used updates last_used_at."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            assert api_key_obj.last_used_at is None
            api_key_obj.update_last_used()
            assert api_key_obj.last_used_at is not None

    def test_touch_last_used_updates_timestamp(self, db_session, app):
        """touch_last_used writes via an isolated session."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            assert api_key_obj.last_used_at is None
            APIKey.touch_last_used(api_key_obj.id, min_interval_seconds=0)
            db.session.refresh(api_key_obj)
            assert api_key_obj.last_used_at is not None

    def test_touch_last_used_throttled(self, db_session, app):
        """touch_last_used skips writes inside the min interval."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            APIKey.touch_last_used(api_key_obj.id, min_interval_seconds=3600)
            db.session.refresh(api_key_obj)
            first = api_key_obj.last_used_at
            assert first is not None
            APIKey.touch_last_used(api_key_obj.id, min_interval_seconds=3600)
            db.session.refresh(api_key_obj)
            assert api_key_obj.last_used_at == first


@pytest.mark.unit
class TestAPIKeyUsage:
    """Tests for APIKeyUsage model."""

    def test_create_usage(self, db_session, app):
        """Test creating an API key usage record."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            usage = APIKeyUsage(
                api_key_id=api_key_obj.id,
                endpoint='/api/data',
                method='GET',
                ip_address='127.0.0.1',
                status_code=200,
                response_time_ms=45.5,
            )
            db_session.add(usage)
            db_session.commit()
            db_session.refresh(usage)
            assert usage.id is not None
            assert usage.endpoint == '/api/data'
            assert usage.status_code == 200

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            usage = APIKeyUsage(
                api_key_id=api_key_obj.id,
                endpoint='/api/test',
                method='POST',
                ip_address='10.0.0.1',
                status_code=201,
                response_time_ms=120.0,
            )
            db_session.add(usage)
            db_session.commit()
            result = repr(usage)
            assert '/api/test' in result

    def test_with_optional_fields(self, db_session, app):
        """Test usage with optional fields."""
        with app.app_context():
            api_key_obj, _ = create_test_api_key(db_session)
            usage = APIKeyUsage(
                api_key_id=api_key_obj.id,
                endpoint='/api/data',
                method='GET',
                ip_address='127.0.0.1',
                status_code=200,
                response_time_ms=50.0,
                user_agent='TestClient/1.0',
                request_data={'query': 'test'},
            )
            db_session.add(usage)
            db_session.commit()
            db_session.refresh(usage)
            assert usage.user_agent == 'TestClient/1.0'
            assert usage.request_data == {'query': 'test'}
