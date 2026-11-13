"""
SQL utility functions for safe query building.

Security utilities for sanitizing user input in SQL queries,
particularly for LIKE/ILIKE pattern matching.

Every ``.ilike()`` / ``.like()`` / ``.contains()`` whose needle is influenced by a
user, an API client, an LLM tool call or imported data must go through this module
(``ilike_contains`` and friends for whole clauses, ``safe_ilike_pattern`` when a
pattern string is needed). ``tests/unit/test_utils/test_sql_like_safety.py``
scans the source tree and fails on raw interpolation.
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


LIKE_ESCAPE_CHAR = "\\"


def ilike_contains(column, value):
    """Case-insensitive "contains" match with user wildcards neutralised."""
    return column.ilike(safe_ilike_pattern(value), escape=LIKE_ESCAPE_CHAR)


def ilike_prefix(column, value):
    """Case-insensitive "starts with" match with user wildcards neutralised."""
    return column.ilike(safe_ilike_pattern(value, prefix=False), escape=LIKE_ESCAPE_CHAR)


def ilike_equals(column, value):
    """Case-insensitive equality via ILIKE with user wildcards neutralised."""
    return column.ilike(
        safe_ilike_pattern(value, prefix=False, suffix=False),
        escape=LIKE_ESCAPE_CHAR,
    )


def like_contains(column, value):
    """Case-sensitive "contains" match (e.g. against JSON cast to text) with wildcards neutralised."""
    return column.like(safe_ilike_pattern(value), escape=LIKE_ESCAPE_CHAR)


def contains_literal(column, value):
    """``column.contains(value)`` with wildcard autoescape enabled (SQLAlchemy defaults to off)."""
    return column.contains("" if value is None else str(value), autoescape=True)
