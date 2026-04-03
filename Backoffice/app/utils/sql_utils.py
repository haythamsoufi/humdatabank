"""
SQL utility functions for safe query building.

Security utilities for sanitizing user input in SQL queries,
particularly for LIKE/ILIKE pattern matching.
"""


def escape_like_wildcards(value: str) -> str:
    """
    Escape SQL LIKE/ILIKE wildcards (% and _) in user input.

    This prevents users from manipulating search patterns by injecting
    wildcards. Use this for any user-provided search terms used with
    .ilike() or .like() queries.

    Args:
        value: The user input string to escape

    Returns:
        The escaped string safe for use in LIKE patterns

    Example:
        # User input: "test%"
        # Without escaping: matches anything starting with "test"
        # With escaping: matches only "test%"

        search = escape_like_wildcards(user_input)
        query.filter(Model.field.ilike(f'%{search}%'))
    """
    if value is None:
        return ''
    # Escape backslash first (it's the escape character)
    result = str(value).replace('\\', '\\\\')
    # Then escape the wildcards
    result = result.replace('%', '\\%')
    result = result.replace('_', '\\_')
    return result


def safe_ilike_pattern(value: str, prefix: bool = True, suffix: bool = True) -> str:
    """
    Create a safe ILIKE pattern from user input.

    Escapes wildcards in the user input and optionally adds % prefix/suffix.

    Args:
        value: The user input string
        prefix: If True, adds % at the start for "contains" matching
        suffix: If True, adds % at the end for "contains" matching

    Returns:
        A safe pattern string for use with .ilike()

    Example:
        # For "contains" search:
        pattern = safe_ilike_pattern(user_input)  # Returns '%escaped_input%'

        # For "starts with" search:
        pattern = safe_ilike_pattern(user_input, prefix=False)  # Returns 'escaped_input%'

        # For exact match:
        pattern = safe_ilike_pattern(user_input, prefix=False, suffix=False)
    """
    escaped = escape_like_wildcards(value)
    result = ''
    if prefix:
        result = '%'
    result += escaped
    if suffix:
        result += '%'
    return result
