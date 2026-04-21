# Password strength validation utilities
"""
Server-side password strength validation.

Ensures passwords meet security requirements:
- Minimum length
- Complexity requirements
- Common password prevention
"""

import re
from typing import Dict, List, Tuple, Optional
from flask import current_app


class PasswordValidator:
    """Password strength validator with configurable requirements."""

    # Common weak passwords to reject
    COMMON_PASSWORDS = {
        'password', 'password123', '12345678', '123456789', '1234567890',
        'qwerty', 'abc123', 'letmein', 'welcome', 'admin', 'password1',
        'iloveyou', 'monkey', 'dragon', 'master', 'sunshine', 'princess'
    }

    # Minimum requirements
    MIN_LENGTH = 8
    MAX_LENGTH = 128

    @staticmethod
    def validate_password(password: str,
                         min_length: Optional[int] = None,
                         require_upper: bool = True,
                         require_lower: bool = True,
                         require_digit: bool = True,
                         require_special: bool = True,
                         reject_common: bool = True,
                         user_email: Optional[str] = None,
                         user_name: Optional[str] = None) -> Tuple[bool, List[str]]:
        """
        Validate password strength.

        Args:
            password: Password to validate
            min_length: Minimum length (default: 8)
            require_upper: Require uppercase letter
            require_lower: Require lowercase letter
            require_digit: Require digit
            require_special: Require special character
            reject_common: Reject common passwords
            user_email: User email (to check against password)
            user_name: User name (to check against password)

        Returns:
            Tuple: (is_valid: bool, errors: List[str])
        """
        errors = []

        if not password or not isinstance(password, str):
            return False, ["Password is required"]

        min_len = min_length or PasswordValidator.MIN_LENGTH

        # Check length
        if len(password) < min_len:
            errors.append(f"Password must be at least {min_len} characters long")
        if len(password) > PasswordValidator.MAX_LENGTH:
            errors.append(f"Password must be no more than {PasswordValidator.MAX_LENGTH} characters long")

        # Check complexity requirements
        if require_upper and not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")

        if require_lower and not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")

        if require_digit and not re.search(r'\d', password):
            errors.append("Password must contain at least one number")

        if require_special and not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\];\'/`~]', password):
            errors.append("Password must contain at least one special character")

        # Check against common passwords
        if reject_common and password.lower().strip() in PasswordValidator.COMMON_PASSWORDS:
            errors.append("Password is too common. Please choose a more unique password")

        # Check against user information
        if user_email:
            email_local = user_email.split('@')[0].lower()
            if email_local and len(email_local) >= 3 and email_local in password.lower():
                errors.append("Password cannot contain your email address")

        if user_name:
            name_parts = user_name.lower().split()
            for part in name_parts:
                if len(part) >= 3 and part in password.lower():
                    errors.append("Password cannot contain your name")

        # Check for repetitive characters
        if re.search(r'(.)\1{3,}', password):
            errors.append("Password cannot contain the same character repeated 4+ times")

        # Check for sequential characters
        if re.search(r'(012|123|234|345|456|567|678|789|890|abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)', password.lower()):
            errors.append("Password cannot contain sequential characters (e.g., 123, abc)")

        return len(errors) == 0, errors

    @staticmethod
    def get_strength_score(password: str) -> Dict[str, any]:
        """
        Calculate password strength score (0-100).

        Args:
            password: Password to score

        Returns:
            Dict with score and details:
            {
                'score': int (0-100),
                'strength': str ('weak', 'fair', 'good', 'strong'),
                'feedback': List[str]
            }
        """
        if not password:
            return {
                'score': 0,
                'strength': 'weak',
                'feedback': ['Password is required']
            }

        score = 0
        feedback = []

        # Length scoring (up to 25 points)
        length = len(password)
        if length >= 8:
            score += 10
        if length >= 12:
            score += 10
        if length >= 16:
            score += 5

        # Character variety (up to 40 points)
        if re.search(r'[a-z]', password):
            score += 10
        if re.search(r'[A-Z]', password):
            score += 10
        if re.search(r'\d', password):
            score += 10
        if re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\];\'/`~]', password):
            score += 10

        # Complexity bonus (up to 25 points)
        if length >= 12:
            # Check for mixed case
            if re.search(r'[a-z]', password) and re.search(r'[A-Z]', password):
                score += 5
            # Check for letters and numbers
            if re.search(r'[a-zA-Z]', password) and re.search(r'\d', password):
                score += 5
            # Check for special characters
            if re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\];\'/`~]', password):
                score += 5
            # Bonus for longer passwords
            if length >= 16:
                score += 10

        # Deductions (up to -30 points)
        if password.lower() in PasswordValidator.COMMON_PASSWORDS:
            score -= 30
            feedback.append("Password is too common")
        if re.search(r'(.)\1{3,}', password):
            score -= 10
            feedback.append("Contains repetitive characters")
        if re.search(r'(012|123|234|345|456|567|678|789|890|abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)', password.lower()):
            score -= 10
            feedback.append("Contains sequential characters")

        # Clamp score between 0 and 100
        score = max(0, min(100, score))

        # Determine strength category
        if score < 30:
            strength = 'weak'
        elif score < 60:
            strength = 'fair'
        elif score < 80:
            strength = 'good'
        else:
            strength = 'strong'

        return {
            'score': score,
            'strength': strength,
            'feedback': feedback
        }


def validate_password_strength(password: str, user_email: Optional[str] = None,
                               user_name: Optional[str] = None) -> Tuple[bool, List[str]]:
    """
    Convenience function to validate password strength.

    Args:
        password: Password to validate
        user_email: Optional user email for additional checks
        user_name: Optional user name for additional checks

    Returns:
        Tuple: (is_valid: bool, errors: List[str])
    """
    return PasswordValidator.validate_password(
        password,
        user_email=user_email,
        user_name=user_name
    )


def get_password_strength(password: str) -> Dict[str, any]:
    """
    Convenience function to get password strength score.

    Args:
        password: Password to score

    Returns:
        Dict with score and details
    """
    return PasswordValidator.get_strength_score(password)
