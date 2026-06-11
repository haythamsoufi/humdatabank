"""
Unit tests for app/utils/profile_utils.py

Covers: generate_random_color, generate_color_from_email, get_user_profile_color,
        display_initials, display_initials_for_user, is_valid_hex_color
"""
import pytest
from unittest.mock import MagicMock


@pytest.mark.unit
class TestGenerateRandomColor:
    def test_returns_color_from_palette(self):
        from app.utils.profile_utils import generate_random_color, PROFILE_COLORS
        color = generate_random_color()
        assert color in PROFILE_COLORS

    def test_always_returns_valid_hex(self):
        from app.utils.profile_utils import generate_random_color
        for _ in range(30):
            color = generate_random_color()
            assert color.startswith("#")
            assert len(color) == 7


@pytest.mark.unit
class TestGenerateColorFromEmail:
    def test_none_email_returns_first_color(self):
        from app.utils.profile_utils import generate_color_from_email, PROFILE_COLORS
        assert generate_color_from_email(None) == PROFILE_COLORS[0]

    def test_empty_email_returns_first_color(self):
        from app.utils.profile_utils import generate_color_from_email, PROFILE_COLORS
        assert generate_color_from_email("") == PROFILE_COLORS[0]

    def test_deterministic_for_same_email(self):
        from app.utils.profile_utils import generate_color_from_email
        email = "user@example.com"
        assert generate_color_from_email(email) == generate_color_from_email(email)

    def test_case_insensitive(self):
        from app.utils.profile_utils import generate_color_from_email
        assert generate_color_from_email("User@Example.COM") == generate_color_from_email("user@example.com")

    def test_returns_value_from_palette(self):
        from app.utils.profile_utils import generate_color_from_email, PROFILE_COLORS
        result = generate_color_from_email("test@example.org")
        assert result in PROFILE_COLORS

    def test_different_emails_may_produce_different_colors(self):
        from app.utils.profile_utils import generate_color_from_email
        emails = [f"user{i}@example.com" for i in range(20)]
        colors = {generate_color_from_email(e) for e in emails}
        assert len(colors) > 1


@pytest.mark.unit
class TestGetUserProfileColor:
    def test_none_user_returns_first_color(self):
        from app.utils.profile_utils import get_user_profile_color, PROFILE_COLORS
        assert get_user_profile_color(None) == PROFILE_COLORS[0]

    def test_user_with_custom_color_returns_it(self):
        from app.utils.profile_utils import get_user_profile_color
        user = MagicMock()
        user.profile_color = "#FF5733"
        user.email = "user@example.com"
        assert get_user_profile_color(user) == "#FF5733"

    def test_user_with_default_blue_uses_email_hash(self):
        from app.utils.profile_utils import get_user_profile_color, generate_color_from_email
        user = MagicMock()
        user.profile_color = "#3B82F6"
        user.email = "user@example.com"
        result = get_user_profile_color(user)
        assert result == generate_color_from_email("user@example.com")

    def test_user_with_no_profile_color_uses_email_hash(self):
        from app.utils.profile_utils import get_user_profile_color, generate_color_from_email
        user = MagicMock()
        user.profile_color = None
        user.email = "alice@example.com"
        result = get_user_profile_color(user)
        assert result == generate_color_from_email("alice@example.com")

    def test_user_with_empty_profile_color_uses_email_hash(self):
        from app.utils.profile_utils import get_user_profile_color, generate_color_from_email
        user = MagicMock()
        user.profile_color = ""
        user.email = "bob@example.com"
        result = get_user_profile_color(user)
        assert result == generate_color_from_email("bob@example.com")


@pytest.mark.unit
class TestDisplayInitials:
    def test_two_name_parts(self):
        from app.utils.profile_utils import display_initials
        assert display_initials("John Doe") == "JD"

    def test_three_parts_uses_first_two(self):
        from app.utils.profile_utils import display_initials
        assert display_initials("John Michael Doe") == "JM"

    def test_single_name_two_chars(self):
        from app.utils.profile_utils import display_initials
        assert display_initials("John") == "JO"

    def test_single_char_name(self):
        from app.utils.profile_utils import display_initials
        assert display_initials("J") == "J"

    def test_empty_name_falls_back_to_email(self):
        from app.utils.profile_utils import display_initials
        assert display_initials(email="john@example.com") == "JO"

    def test_email_without_at_uses_whole_local(self):
        from app.utils.profile_utils import display_initials
        assert display_initials(email="jo") == "JO"

    def test_no_name_no_email_returns_question_mark(self):
        from app.utils.profile_utils import display_initials
        assert display_initials() == "?"

    def test_whitespace_name_returns_question_mark(self):
        from app.utils.profile_utils import display_initials
        assert display_initials("   ") == "?"

    def test_name_takes_precedence_over_email(self):
        from app.utils.profile_utils import display_initials
        assert display_initials("Jane Smith", "jane@example.com") == "JS"

    def test_output_is_uppercase(self):
        from app.utils.profile_utils import display_initials
        assert display_initials("jane doe") == "JD"

    def test_email_only_at_start_returns_question_mark(self):
        from app.utils.profile_utils import display_initials
        # "@domain.com" -> local part is "" -> returns "?"
        assert display_initials(email="@domain.com") == "?"

    def test_none_name_treated_as_empty(self):
        from app.utils.profile_utils import display_initials
        assert display_initials(name=None, email="ab@x.com") == "AB"


@pytest.mark.unit
class TestDisplayInitialsForUser:
    def test_none_returns_question_mark(self):
        from app.utils.profile_utils import display_initials_for_user
        assert display_initials_for_user(None) == "?"

    def test_user_with_name_and_email(self):
        from app.utils.profile_utils import display_initials_for_user
        user = MagicMock()
        user.name = "Jane Doe"
        user.email = "jane@example.com"
        assert display_initials_for_user(user) == "JD"

    def test_user_without_name_attr_uses_email(self):
        from app.utils.profile_utils import display_initials_for_user
        user = MagicMock(spec=["email"])
        user.email = "john@example.com"
        result = display_initials_for_user(user)
        assert result == "JO"

    def test_user_without_any_attr_returns_question_mark(self):
        from app.utils.profile_utils import display_initials_for_user
        user = MagicMock(spec=[])
        result = display_initials_for_user(user)
        assert result == "?"

    def test_user_with_single_name(self):
        from app.utils.profile_utils import display_initials_for_user
        user = MagicMock()
        user.name = "Alice"
        user.email = None
        assert display_initials_for_user(user) == "AL"


@pytest.mark.unit
class TestIsValidHexColor:
    def test_valid_with_hash(self):
        from app.utils.profile_utils import is_valid_hex_color
        assert is_valid_hex_color("#FF0000") is True

    def test_valid_without_hash(self):
        from app.utils.profile_utils import is_valid_hex_color
        assert is_valid_hex_color("FF0000") is True

    def test_valid_lowercase(self):
        from app.utils.profile_utils import is_valid_hex_color
        assert is_valid_hex_color("#ff0000") is True

    def test_valid_mixed_case(self):
        from app.utils.profile_utils import is_valid_hex_color
        assert is_valid_hex_color("#aAbBcC") is True

    def test_invalid_too_short(self):
        from app.utils.profile_utils import is_valid_hex_color
        assert is_valid_hex_color("#FFF") is False

    def test_invalid_too_long(self):
        from app.utils.profile_utils import is_valid_hex_color
        assert is_valid_hex_color("#FFFFFFF") is False

    def test_invalid_non_hex_chars(self):
        from app.utils.profile_utils import is_valid_hex_color
        assert is_valid_hex_color("#GGGGGG") is False

    def test_none_is_invalid(self):
        from app.utils.profile_utils import is_valid_hex_color
        assert is_valid_hex_color(None) is False

    def test_integer_is_invalid(self):
        from app.utils.profile_utils import is_valid_hex_color
        assert is_valid_hex_color(123456) is False

    def test_empty_string_is_invalid(self):
        from app.utils.profile_utils import is_valid_hex_color
        assert is_valid_hex_color("") is False

    def test_valid_all_zeros(self):
        from app.utils.profile_utils import is_valid_hex_color
        assert is_valid_hex_color("#000000") is True

    def test_valid_all_fs(self):
        from app.utils.profile_utils import is_valid_hex_color
        assert is_valid_hex_color("#FFFFFF") is True
