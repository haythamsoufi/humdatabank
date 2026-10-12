"""Validate matrix column codes before a matrix config is saved.

Saved cells are keyed ``"{rowId}_{columnCode}"`` and selectable headers
``"col_header|{columnCode}"``, so a column code has to be unique within its matrix and
must not collide with the keys the entry form reserves. The form builder checks the same
rules in the browser (``collectColumnCodeIssues`` in ``matrix.js``); this is the
server-side copy so API and AI-generated configs cannot bypass it.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Iterable, List

# Row-total columns are stored as "{row}_Total"; "_row_total" is the lookup sentinel.
RESERVED_COLUMN_CODES = frozenset({'total', '_row_total'})


def _has_label_text(column: dict) -> bool:
    translations = column.get('name_translations')
    if isinstance(translations, dict) and any(str(v or '').strip() for v in translations.values()):
        return True
    return bool(str(column.get('label') or '').strip())


def validate_matrix_columns(columns: Iterable[Any]) -> List[str]:
    """Human-readable problems with a matrix's column codes (empty list when valid)."""
    errors: List[str] = []
    dicts = [c for c in (columns or []) if isinstance(c, dict)]
    codes = [str(c.get('name') or '').strip() for c in dicts]
    counts = Counter(code for code in codes if code)

    reported: set = set()

    def add(message: str) -> None:
        if message not in reported:
            reported.add(message)
            errors.append(message)

    for column, code in zip(dicts, codes):
        if not code:
            is_variable = bool(column.get('is_variable') or column.get('type') == 'variable')
            if not is_variable and _has_label_text(column):
                add('A column has a label but no code. Give it a column code.')
            continue
        if counts[code] > 1:
            add(f'Column code "{code}" is used more than once. Column codes must be unique.')
        if code.casefold() in RESERVED_COLUMN_CODES:
            add(f'"{code}" is reserved and cannot be used as a column code.')
        if '|' in code:
            add(f'Column code "{code}" cannot contain "|".')
        if code.count('[') != code.count(']'):
            add(f'Column code "{code}" has unbalanced [ ] brackets.')
    return errors


def validate_matrix_config(matrix_config: Any) -> List[str]:
    """Same as :func:`validate_matrix_columns`, for a config dict or its JSON string."""
    if isinstance(matrix_config, (str, bytes)):
        try:
            matrix_config = json.loads(matrix_config)
        except (TypeError, ValueError):
            return []  # malformed JSON is reported by the code that parses it
    if not isinstance(matrix_config, dict):
        return []
    return validate_matrix_columns(matrix_config.get('columns'))
