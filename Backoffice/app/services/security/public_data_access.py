"""
Validation helpers for unauthenticated public reads of GET /api/v1/data.

Public callers receive only FormData rows whose form items have config privacy
'public' (enforced downstream by query_form_data for anonymous viewers).
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from app.utils.api_helpers import api_error

PUBLIC_DATA_MAX_PER_PAGE = 5000

# Fact-row fields kept when include_dimensions is not requested (AI / Custom GPT integrations).
PUBLIC_DATA_SLIM_ROW_FIELDS = frozenset(
    {
        'id',
        'field_type',
        'data_type',
        'submission_type',
        'submission_id',
        'form_item_id',
        'template_id',
        'period_name',
        'country_id',
        'value',
        'num_value',
        'data_status',
    }
)


def _truthy_flag(value: Any) -> bool:
    return str(value or '').strip().lower() in ('1', 'true', 'yes', 'y')


def _arg_int(args: Mapping[str, Any], key: str) -> Optional[int]:
    raw = args.get(key)
    if raw is None or str(raw).strip() == '':
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _arg_str(args: Mapping[str, Any], key: str) -> str:
    return str(args.get(key) or '').strip()


def public_data_scope_present(args: Mapping[str, Any]) -> bool:
    """Return True when the request includes at least one narrowing filter."""
    if _arg_int(args, 'indicator_bank_id'):
        return True

    raw_ibids = _arg_str(args, 'indicator_bank_ids')
    if raw_ibids:
        for part in raw_ibids.split(','):
            token = part.strip().lstrip('-')
            if token.isdigit() and int(token) > 0:
                return True

    if _arg_int(args, 'template_id'):
        return True
    if _arg_int(args, 'country_id'):
        return True
    if _arg_str(args, 'country_iso2'):
        return True
    if _arg_str(args, 'country_iso3'):
        return True
    if _arg_str(args, 'period_name'):
        return True
    if _arg_int(args, 'assignment_id'):
        return True
    if _arg_int(args, 'assigned_form_id'):
        return True
    if _arg_int(args, 'submission_id'):
        return True
    if _arg_int(args, 'item_id'):
        return True
    return False


def public_include_dimensions(args: Mapping[str, Any]) -> bool:
    """Public callers omit heavy dimension tables unless include_dimensions=true."""
    return _truthy_flag(args.get('include_dimensions'))


def slim_public_data_rows(rows: list) -> list:
    """Project fact rows to a compact shape for public API consumers."""
    slimmed = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        slimmed.append({key: row.get(key) for key in PUBLIC_DATA_SLIM_ROW_FIELDS if key in row})
    return slimmed


def validate_public_data_request(args: Mapping[str, Any]):
    """
    Validate query params for unauthenticated public /api/v1/data access.

    Returns None when allowed, or a Flask Response (401/400) when rejected.
    """
    if not public_data_scope_present(args):
        return api_error(
            'Authentication required for unscoped data requests. '
            'Provide at least one filter (e.g. indicator_bank_id, template_id, '
            'country_id, country_iso2, country_iso3, or period_name), '
            'or authenticate with an API key.',
            401,
            extra={
                'hint': (
                    'Public access returns only form items marked privacy=public. '
                    'Use Authorization: Bearer YOUR_API_KEY for full dataset access.'
                ),
            },
        )

    if _truthy_flag(args.get('analysis')):
        return api_error('analysis mode requires authentication', 401)

    if _truthy_flag(args.get('include_non_reported')):
        return api_error('include_non_reported requires authentication', 401)

    return None
