"""Scale stored percentage values (0–100) to API decimals (0–1).

Form entry and the database keep whole percents (25 means 25%). External
``/api/v1/data`` consumers receive a unit interval: 0, 0.25, 1, or >1 when
``allow_over_100`` is set. Conversion is response-only — it does not rewrite
stored FormData.
"""

from typing import Any, Iterable, Optional, Set

from app.utils.api_helpers import extract_numeric_value

PERCENTAGE_TYPE_ALIASES = frozenset({'percentage', 'percent', 'pct'})

_SCALAR_FIELDS = (
    'value',
    'num_value',
    'prefilled_value',
    'imputed_value',
    'answer_value',
)

_DISAGG_FIELDS = (
    'disaggregation_data',
    'prefilled_disaggregation_data',
    'imputed_disaggregation_data',
    'prefilled_disagg_data',
    'imputed_disagg_data',
)


def is_percentage_type(type_value: Any) -> bool:
    """True when an indicator/question type string is a percentage."""
    if type_value is None:
        return False
    return str(type_value).strip().lower() in PERCENTAGE_TYPE_ALIASES


def orm_item_is_percentage(form_item: Any) -> bool:
    """True when a FormItem (or indicator bank on it) is a percentage field."""
    if form_item is None:
        return False
    if is_percentage_type(getattr(form_item, 'type', None)):
        return True
    field_type = getattr(form_item, 'field_type_for_js', None)
    if is_percentage_type(field_type):
        return True
    bank = getattr(form_item, 'indicator_bank', None)
    if bank is not None and is_percentage_type(getattr(bank, 'type', None)):
        return True
    return False


def should_scale_percentage(*, form_item: Any = None, indicator_bank: Any = None) -> bool:
    if orm_item_is_percentage(form_item):
        return True
    if indicator_bank is not None and is_percentage_type(getattr(indicator_bank, 'type', None)):
        return True
    return False


def to_api_percentage_decimal(value: Any) -> Any:
    """Convert a stored 0–100 percentage (or nested numeric tree) to 0–1.

    Non-numeric leaves are left unchanged. Booleans are not treated as numbers.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return {key: to_api_percentage_decimal(val) for key, val in value.items()}
    if isinstance(value, list):
        return [to_api_percentage_decimal(item) for item in value]
    num = extract_numeric_value(value)
    if num is None:
        return value
    return num / 100.0


def scale_percentage_fact_row(row: Any) -> Any:
    """In-place: divide percentage scalars and disaggregation trees by 100."""
    if not isinstance(row, dict):
        return row
    for key in _SCALAR_FIELDS:
        if key in row and row[key] is not None:
            row[key] = to_api_percentage_decimal(row[key])
    if 'num_value' in row:
        row['num_value'] = extract_numeric_value(row.get('value'))
    for key in _DISAGG_FIELDS:
        if key in row and row[key] is not None:
            row[key] = to_api_percentage_decimal(row[key])
    return row


def apply_api_percentage_scale(
    payload: Any,
    *,
    form_item: Any = None,
    indicator_bank: Any = None,
) -> Any:
    """Scale a serialized fact row when the field is a percentage type."""
    if should_scale_percentage(form_item=form_item, indicator_bank=indicator_bank):
        return scale_percentage_fact_row(payload)
    return payload


def scale_percentage_rows(
    rows: Optional[Iterable[Any]],
    *,
    form_item_ids: Optional[Set[int]] = None,
    bank_ids: Optional[Set[int]] = None,
) -> None:
    """Scale matching fact rows in place (static via form_item_id, dynamic via bank id)."""
    form_item_ids = form_item_ids or set()
    bank_ids = bank_ids or set()
    if not form_item_ids and not bank_ids:
        return
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        fid = row.get('form_item_id')
        bid = row.get('indicator_bank_id')
        try:
            fid_match = fid is not None and int(fid) in form_item_ids
        except (TypeError, ValueError):
            fid_match = False
        try:
            bid_match = bid is not None and int(bid) in bank_ids
        except (TypeError, ValueError):
            bid_match = False
        if fid_match or bid_match:
            scale_percentage_fact_row(row)
