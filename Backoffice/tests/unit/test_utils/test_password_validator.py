"""
Unit tests for password validation utilities.
"""
import pytest
from app.utils.password_validator import (
    PasswordValidator,
    validate_password_strength,
    get_password_strength
)


@pytest.mark.unit
class TestPasswordValidator:
    """Test password validation."""

    def test_valid_password(self):
        """Test that a valid password passes validation."""
        # Use a password without sequential characters (123, 456, 789 are sequential)
        # Use non-sequential numbers like 247 or 592 instead
        is_valid, errors = PasswordValidator.validate_password("ValidPass247!")
        assert is_valid is True
        assert len(errors) == 0

    def test_password_too_short(self):
        """Test that short passwords are rejected."""
        is_valid, errors = PasswordValidator.validate_password("Short1!")
        assert is_valid is False
        assert any("at least" in error.lower() for error in errors)

    def test_password_too_long(self):
        """Test that very long passwords are rejected."""
        long_password = "A" * 129 + "1!"
        is_valid, errors = PasswordValidator.validate_password(long_password)
        assert is_valid is False
        assert any("no more than" in error.lower() for error in errors)

    def test_password_missing_uppercase(self):
        """Test that passwords without uppercase are rejected."""
        is_valid, errors = PasswordValidator.validate_password("lowercase123!")
        assert is_valid is False
        assert any("uppercase" in error.lower() for error in errors)

    def test_password_missing_lowercase(self):
        """Test that passwords without lowercase are rejected."""
        is_valid, errors = PasswordValidator.validate_password("UPPERCASE123!")
        assert is_valid is False
        assert any("lowercase" in error.lower() for error in errors)

    def test_password_missing_digit(self):
        """Test that passwords without digits are rejected."""
        is_valid, errors = PasswordValidator.validate_password("NoDigits!")
        assert is_valid is False
        assert any("number" in error.lower() for error in errors)

    def test_password_missing_special(self):
        """Test that passwords without special characters are rejected."""
        is_valid, errors = PasswordValidator.validate_password("NoSpecial123")
        assert is_valid is False
        assert any("special" in error.lower() for error in errors)

    def test_common_password_rejected(self):
        """Test that common passwords are rejected."""
        is_valid, errors = PasswordValidator.validate_password("password123")
        assert is_valid is False
        assert any("common" in error.lower() for error in errors)

    def test_password_contains_email(self):
        """Test that passwords containing email are rejected."""
        is_valid, errors = PasswordValidator.validate_password(
            "john@example.com123!",
            user_email="john@example.com"
        )
        assert is_valid is False
        assert any("email" in error.lower() for error in errors)

    def test_password_contains_name(self):
        """Test that passwords containing name are rejected."""
        is_valid, errors = PasswordValidator.validate_password(
            "JohnDoe123!",
            user_name="John Doe"
        )
        assert is_valid is False
        assert any("name" in error.lower() for error in errors)

    def test_repetitive_characters(self):
        """Test that passwords with repetitive characters are rejected."""
        is_valid, errors = PasswordValidator.validate_password("AAAA1234!")
        assert is_valid is False
        assert any("repetitive" in error.lower() or "repeated" in error.lower() for error in errors)

    def test_sequential_characters(self):
        """Test that passwords with sequential characters are rejected."""
        is_valid, errors = PasswordValidator.validate_password("ABC123!")
        assert is_valid is False
        assert any("sequential" in error.lower() for error in errors)

    def test_custom_min_length(self):
        """Test custom minimum length requirement."""
        is_valid, errors = PasswordValidator.validate_password(
            "Pass123!",
            min_length=10
        )
        assert is_valid is False
        assert any("10" in error for error in errors)

    def test_password_strength_score_weak(self):
        """Test password strength scoring for weak passwords."""
        result = PasswordValidator.get_strength_score("weak")
        assert result['score'] < 30
        assert result['strength'] == 'weak'

    def test_password_strength_score_strong(self):
        """Test password strength scoring for strong passwords."""
        result = PasswordValidator.get_strength_score("VeryStrongPassword123!@#")
        assert result['score'] >= 80
        assert result['strength'] == 'strong'

    def test_validate_password_strength_function(self):
        """Test convenience function for password validation."""
        # Use a password without sequential characters (123, 456, 789 are sequential)
        # Use non-sequential numbers like 247 or 592 instead
        is_valid, errors = validate_password_strength("ValidPass247!")
        assert is_valid is True
        assert len(errors) == 0

    def test_get_password_strength_function(self):
        """Test convenience function for password strength."""
        result = get_password_strength("Test123!")
        assert 'score' in result
        assert 'strength' in result
        assert 'feedback' in result
        assert isinstance(result['score'], int)
        assert 0 <= result['score'] <= 100
