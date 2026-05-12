import random
import hashlib
from typing import Any, Optional

# Predefined color palette for profile icons
PROFILE_COLORS = [
    '#3B82F6',  # Blue
    '#EF4444',  # Red
    '#10B981',  # Green
    '#F59E0B',  # Yellow
    '#8B5CF6',  # Purple
    '#F97316',  # Orange
    '#EC4899',  # Pink
    '#06B6D4',  # Cyan
    '#84CC16',  # Lime
    '#F43F5E',  # Rose
    '#6366F1',  # Indigo
    '#14B8A6',  # Teal
    '#FBBF24',  # Amber
    '#A855F7',  # Violet
    '#E11D48',  # Rose
    '#0EA5E9',  # Sky
    '#22C55E',  # Emerald
    '#F59E0B',  # Amber
    '#8B5CF6',  # Violet
    '#EC4899',  # Pink
]

def generate_random_color():
    """Generate a random color from the predefined palette."""
    return random.choice(PROFILE_COLORS)

def generate_color_from_email(email):
    """Generate a consistent color based on email address."""
    if not email:
        return PROFILE_COLORS[0]

    # Create a hash from the email
    hash_object = hashlib.md5(email.lower().encode())
    hash_hex = hash_object.hexdigest()

    # Use the hash to select a color
    color_index = int(hash_hex[:8], 16) % len(PROFILE_COLORS)
    return PROFILE_COLORS[color_index]

def get_user_profile_color(user):
    """Get the profile color for a user, generating one if not set."""
    if not user:
        return PROFILE_COLORS[0]

    if user.profile_color and user.profile_color != '#3B82F6':  # Default blue
        return user.profile_color

    # Generate a consistent color based on email
    return generate_color_from_email(user.email)

def display_initials(name: Optional[str] = None, email: Optional[str] = None) -> str:
    """
    Two-character label for profile avatars (matches user form colour preview JS).
    With two or more name tokens: first letter of the first two tokens.
    With one token: up to two letters from that token. Else: first two of email local-part.
    """
    n = (name or '').strip()
    if n:
        parts = n.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        if parts:
            return parts[0][:2].upper()
        return '?'
    if email:
        local = (email.split('@', 1)[0] if '@' in email else email)[:2]
        return local.upper() if local else '?'
    return '?'


def display_initials_for_user(user: Any) -> str:
    """Initials for a User-like object with optional .name and .email."""
    if user is None:
        return '?'
    return display_initials(
        name=getattr(user, 'name', None),
        email=getattr(user, 'email', None),
    )


def is_valid_hex_color(color):
    """Validate if a string is a valid hex color."""
    if not color or not isinstance(color, str):
        return False

    # Remove # if present
    if color.startswith('#'):
        color = color[1:]

    # Check if it's a valid 6-digit hex color
    if len(color) != 6:
        return False

    try:
        int(color, 16)
        return True
    except ValueError:
        return False
