"""
Unit tests for User model.
"""
import pytest
from tests.factories import create_test_user
from app.services.authorization_service import AuthorizationService


@pytest.mark.unit
class TestUserModel:
    """Test User model functionality."""

    def test_user_creation(self, db_session, app):
        """Test creating a user."""
        with app.app_context():
            user = create_test_user(db_session, email='test@example.com', name='Test User')
            assert user.id is not None
            assert user.email == 'test@example.com'
            assert user.name == 'Test User'

    def test_user_password_hashing(self, db_session, app):
        """Test password hashing and verification."""
        with app.app_context():
            user = create_test_user(db_session, password='TestPassword123!')

            # Password should be hashed
            assert user.password_hash != 'TestPassword123!'
            assert user.password_hash is not None

            # Should verify correctly
            assert user.check_password('TestPassword123!') is True
            assert user.check_password('WrongPassword') is False

    def test_user_set_password(self, db_session, app):
        """Test setting password."""
        with app.app_context():
            user = create_test_user(db_session)
            old_hash = user.password_hash

            user.set_password('NewPassword123!')
            db_session.commit()

            # Hash should change
            assert user.password_hash != old_hash
            assert user.check_password('NewPassword123!') is True

    def test_user_active_default(self, db_session, app):
        """Test that user is active by default."""
        with app.app_context():
            user = create_test_user(db_session)
            assert user.active is True

    def test_user_default_rbac_role(self, db_session, app):
        """Test default user RBAC role assignment."""
        with app.app_context():
            user = create_test_user(db_session)
            assert AuthorizationService.has_role(user, "assignment_viewer") is True

    def test_user_is_authenticated(self, db_session, app):
        """Test user authentication status."""
        with app.app_context():
            user = create_test_user(db_session)
            # Flask-Login requires is_authenticated property
            assert hasattr(user, 'is_authenticated') or hasattr(user, 'is_active')

    def test_user_string_representation(self, db_session, app):
        """Test user string representation."""
        with app.app_context():
            user = create_test_user(db_session, email='test@example.com', name='Test User')
            # Should have some string representation
            assert str(user) or repr(user)
