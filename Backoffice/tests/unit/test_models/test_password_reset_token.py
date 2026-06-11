"""
Unit tests for password_reset_token.py to achieve 100% code coverage.

Covers: PasswordResetToken model methods: hash_token, is_valid, mark_as_used,
        revoke, revoke_all_user_tokens
"""
import pytest
from datetime import timedelta
from unittest.mock import patch

from app.models.password_reset_token import PasswordResetToken
from app.utils.datetime_helpers import utcnow
from tests.factories import create_test_user


@pytest.mark.unit
class TestPasswordResetToken:
    """Tests for PasswordResetToken model."""

    def _create_token(self, db_session, user, **kwargs):
        """Helper to create a PasswordResetToken."""
        token_str = 'my-secret-reset-token-12345'
        defaults = {
            'token_hash': PasswordResetToken.hash_token(token_str),
            'user_id': user.id,
            'user_email': user.email,
            'expires_at': utcnow() + timedelta(hours=1),
        }
        defaults.update(kwargs)
        token = PasswordResetToken(**defaults)
        db_session.add(token)
        db_session.commit()
        db_session.refresh(token)
        return token, token_str

    def test_hash_token(self):
        """Test hash_token returns SHA256 hex string."""
        result = PasswordResetToken.hash_token('my-token')
        assert isinstance(result, str)
        assert len(result) == 64  # SHA256 = 64 hex chars

    def test_hash_token_consistent(self):
        """Test hash_token is deterministic."""
        h1 = PasswordResetToken.hash_token('same-token')
        h2 = PasswordResetToken.hash_token('same-token')
        assert h1 == h2

    def test_hash_token_different_inputs(self):
        """Test hash_token produces different results for different inputs."""
        h1 = PasswordResetToken.hash_token('token-a')
        h2 = PasswordResetToken.hash_token('token-b')
        assert h1 != h2

    def test_create_token(self, db_session, app):
        """Test creating a password reset token."""
        with app.app_context():
            user = create_test_user(db_session)
            token, _ = self._create_token(db_session, user)
            assert token.id is not None
            assert token.user_id == user.id
            assert token.user_email == user.email
            assert token.is_used is False
            assert token.is_revoked is False

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            user = create_test_user(db_session)
            token, _ = self._create_token(db_session, user)
            result = repr(token)
            assert 'PasswordResetToken' in result
            assert str(user.id) in result

    def test_is_valid_true(self, db_session, app):
        """Test is_valid returns True when not used, not revoked, not expired."""
        with app.app_context():
            user = create_test_user(db_session)
            token, _ = self._create_token(db_session, user)
            assert token.is_valid() is True

    def test_is_valid_used(self, db_session, app):
        """Test is_valid returns False when token is used."""
        with app.app_context():
            user = create_test_user(db_session)
            token, _ = self._create_token(db_session, user, is_used=True)
            assert token.is_valid() is False

    def test_is_valid_revoked(self, db_session, app):
        """Test is_valid returns False when token is revoked."""
        with app.app_context():
            user = create_test_user(db_session)
            token, _ = self._create_token(db_session, user, is_revoked=True)
            assert token.is_valid() is False

    def test_is_valid_expired(self, db_session, app):
        """Test is_valid returns False when token is expired."""
        with app.app_context():
            user = create_test_user(db_session)
            past_time = utcnow() - timedelta(hours=1)
            token, _ = self._create_token(db_session, user, expires_at=past_time)
            assert token.is_valid() is False

    def test_mark_as_used(self, db_session, app):
        """Test mark_as_used sets is_used=True and used_at timestamp."""
        with app.app_context():
            user = create_test_user(db_session)
            token, _ = self._create_token(db_session, user)
            assert token.is_used is False
            token.mark_as_used()
            assert token.is_used is True
            assert token.used_at is not None

    def test_revoke(self, db_session, app):
        """Test revoke sets is_revoked=True and revoked_at timestamp."""
        with app.app_context():
            user = create_test_user(db_session)
            token, _ = self._create_token(db_session, user)
            assert token.is_revoked is False
            token.revoke()
            assert token.is_revoked is True
            assert token.revoked_at is not None

    def test_revoke_all_user_tokens(self, db_session, app):
        """Test revoke_all_user_tokens revokes all unused tokens for user."""
        with app.app_context():
            user = create_test_user(db_session)
            # Create 3 unused tokens
            tokens = []
            for i in range(3):
                import uuid
                t = PasswordResetToken(
                    token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                    user_id=user.id,
                    user_email=user.email,
                    expires_at=utcnow() + timedelta(hours=1),
                )
                db_session.add(t)
                tokens.append(t)
            db_session.commit()

            PasswordResetToken.revoke_all_user_tokens(user.id)

            # All should be revoked
            for t in tokens:
                db_session.refresh(t)
                assert t.is_revoked is True

    def test_revoke_all_user_tokens_skips_used(self, db_session, app):
        """Test revoke_all_user_tokens does not touch already-used tokens."""
        with app.app_context():
            user = create_test_user(db_session)
            import uuid
            # Create one used token
            used_token = PasswordResetToken(
                token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                user_id=user.id,
                user_email=user.email,
                expires_at=utcnow() + timedelta(hours=1),
                is_used=True,
            )
            db_session.add(used_token)
            db_session.commit()

            PasswordResetToken.revoke_all_user_tokens(user.id)

            # used token should not be touched (is_used stays True, is_revoked stays False)
            db_session.refresh(used_token)
            assert used_token.is_used is True

    def test_revoke_all_user_tokens_empty(self, db_session, app):
        """Test revoke_all_user_tokens with no tokens does nothing."""
        with app.app_context():
            user = create_test_user(db_session)
            # Should not raise
            PasswordResetToken.revoke_all_user_tokens(user.id)

    def test_token_with_optional_fields(self, db_session, app):
        """Test token with optional IP and user_agent."""
        with app.app_context():
            user = create_test_user(db_session)
            token, _ = self._create_token(
                db_session, user,
                ip_address='192.168.1.1',
                user_agent='Mozilla/5.0',
            )
            assert token.ip_address == '192.168.1.1'
            assert token.user_agent == 'Mozilla/5.0'
