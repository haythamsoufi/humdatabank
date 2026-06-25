"""Server-side aggregation helpers for the mobile disaggregation overview API."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from flask_login import AnonymousUserMixin

from app.utils.api_helpers import extract_numeric_value
from app.utils.api_serialization import _wrap_disagg_dict

_SEX_ALIASES = {
    'female': 'Female',
    'f': 'Female',
    'women': 'Female',
    'woman': 'Female',
    'male': 'Male',
    'm': 'Male',
    'men': 'Male',
    'man': 'Male',
    'other': 'Other',
    'non_binary': 'Other',
    'non-binary': 'Other',
    'unknown': 'Other',
}


def format_sex_category(key: str) -> str:
    if not key:
        return 'Unknown'
    normalized = str(key).strip().lower().replace('-', '_')
    return _SEX_ALIASES.get(normalized, str(key).strip().title())


def _parse_numeric(raw: Any) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    parsed = extract_numeric_value(raw)
    return float(parsed) if parsed is not None else 0.0


def _sum_nested_values(values: Any) -> float:
    if values is None:
        return 0.0
    if isinstance(values, (int, float, str)):
        return _parse_numeric(values)
    if isinstance(values, dict):
        total = 0.0
        for key, val in values.items():
            if isinstance(key, str) and key in ('direct', 'indirect'):
                total += _sum_nested_values(val)
            elif isinstance(val, dict):
                total += _sum_nested_values(val)
            else:
                total += _parse_numeric(val)
        return total
    if isinstance(values, list):
        return sum(_parse_numeric(v) for v in values)
    return 0.0


def item_numeric_total(value: Any, disagg_raw: Any) -> float:
    wrapped = _wrap_disagg_dict(disagg_raw) if disagg_raw else None
    if wrapped and wrapped.get('values'):
        return _sum_nested_values(wrapped['values'])
    return _parse_numeric(value)


def accumulate_disaggregation(
    disagg_raw: Any,
    *,
    by_sex: Dict[str, float],
    by_age: Dict[str, float],
) -> Optional[str]:
    """Merge one row's disaggregation into aggregate buckets. Returns mode or None."""
    wrapped = _wrap_disagg_dict(disagg_raw) if disagg_raw else None
    if not wrapped:
        return None
    values = wrapped.get('values') or {}
    if not isinstance(values, dict) or not values:
        return None

    mode = wrapped.get('mode')
    mode_str = str(mode).lower() if mode else ''

    if mode_str == 'sex':
        actual = values.get('direct') if isinstance(values.get('direct'), dict) else values
        if isinstance(actual, dict):
            for sex_key, sex_val in actual.items():
                if sex_key in ('direct', 'indirect'):
                    continue
                label = format_sex_category(str(sex_key))
                by_sex[label] = by_sex.get(label, 0.0) + _parse_numeric(sex_val)
        return 'sex'

    if mode_str == 'age':
        actual = values.get('direct') if isinstance(values.get('direct'), dict) else values
        if isinstance(actual, dict):
            for age_key, age_val in actual.items():
                if age_key in ('direct', 'indirect'):
                    continue
                label = str(age_key).strip()
                by_age[label] = by_age.get(label, 0.0) + _parse_numeric(age_val)
        return 'age'

    if mode_str == 'sex_age':
        for sex_key, age_map in values.items():
            if sex_key in ('direct', 'indirect') or not isinstance(age_map, dict):
                continue
            sex_label = format_sex_category(str(sex_key))
            for age_key, age_val in age_map.items():
                age_label = str(age_key).strip()
                numeric = _parse_numeric(age_val)
                by_sex[sex_label] = by_sex.get(sex_label, 0.0) + numeric
                by_age[age_label] = by_age.get(age_label, 0.0) + numeric
        return 'sex_age'

    # Matrix / plugin payloads — treat scalar entries as age-like buckets when possible.
    for key, val in values.items():
        if isinstance(val, dict):
            for sub_key, sub_val in val.items():
                label = str(sub_key).strip()
                by_age[label] = by_age.get(label, 0.0) + _parse_numeric(sub_val)
        else:
            label = str(key).strip()
            by_age[label] = by_age.get(label, 0.0) + _parse_numeric(val)
    return mode_str or 'matrix'


def resolve_optional_mobile_user():
    """Load the current user from session cookie or Bearer JWT when present."""
    from flask_login import current_user

    from app.utils.mobile_auth import _try_jwt_auth

    if not current_user.is_authenticated:
        _try_jwt_auth()
    if isinstance(current_user, AnonymousUserMixin) or not current_user.is_authenticated:
        return None
    return current_user


def can_view_disaggregation_country_details(user) -> bool:
    """Country-level disaggregation is limited to authenticated organization users."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    from app.services.authorization_service import AuthorizationService
    from app.services.data_retrieval_shared import can_view_non_public_form_items

    if can_view_non_public_form_items(user):
        return True

    try:
        if user.countries.count() > 0:
            return True
    except Exception:
        pass

    try:
        from app.models import UserEntityPermission

        return (
            UserEntityPermission.query.filter_by(
                user_id=user.id,
                entity_type='country',
            ).first()
            is not None
        )
    except Exception:
        return False


def get_disaggregation_country_scope(user) -> Optional[Set[int]]:
    """Return allowed country ids for country-level breakdowns.

    ``None`` means all countries. An empty set means no country breakdown.
    """
    if not can_view_disaggregation_country_details(user):
        return set()

    from app.services.authorization_service import AuthorizationService

    if AuthorizationService.is_admin(user) or AuthorizationService.is_system_manager(user):
        return None
    if AuthorizationService.has_rbac_permission(user, 'admin.countries.view'):
        return None
    if AuthorizationService.has_rbac_permission(user, 'admin.countries.edit'):
        return None

    from app.services.app_settings_service import is_organization_email

    if getattr(user, 'email', None) and is_organization_email(user.email):
        return None

    scoped: Set[int] = set()
    try:
        scoped.update(c.id for c in user.countries.all())
    except Exception:
        pass
    try:
        from app.models import UserEntityPermission

        scoped.update(
            p.entity_id
            for p in UserEntityPermission.query.filter_by(
                user_id=user.id,
                entity_type='country',
            ).all()
            if p.entity_id is not None
        )
    except Exception:
        pass

    return scoped or None


def sorted_breakdown(data: Dict[str, float]) -> List[Dict[str, Any]]:
    return [
        {'category': key, 'value': round(val, 2)}
        for key, val in sorted(data.items(), key=lambda item: item[1], reverse=True)
        if val > 0
    ]


def aggregate_disaggregation_rows(
    rows: Iterable[Tuple[int, str, Any, Any, Any]],
    *,
    country_names: Dict[int, str],
    country_regions: Optional[Dict[int, str]] = None,
    include_country_breakdown: bool = True,
) -> Dict[str, Any]:
    """Aggregate iterable of (country_id, period_name, value, disagg_raw, indicator_id optional)."""
    regions_map = country_regions or {}
    total = 0.0
    record_count = 0
    disaggregated_count = 0
    by_sex: Dict[str, float] = {}
    by_age: Dict[str, float] = {}
    by_country: Dict[int, Dict[str, Any]] = {}
    by_region: Dict[str, Dict[str, Any]] = {}
    trends: Dict[str, Dict[str, Any]] = {}

    for country_id, period_name, value, disagg_raw, _indicator_id in rows:
        record_count += 1
        row_total = item_numeric_total(value, disagg_raw)
        total += row_total

        period_key = period_name or 'Unknown'
        trend = trends.setdefault(
            period_key,
            {
                'period': period_key,
                'total': 0.0,
                'record_count': 0,
                'disaggregated_count': 0,
            },
        )
        trend['total'] += row_total
        trend['record_count'] += 1

        region_name = regions_map.get(country_id) or 'Other'
        region_bucket = by_region.setdefault(
            region_name,
            {
                'region': region_name,
                'value': 0.0,
                'record_count': 0,
                'disaggregated_count': 0,
                'country_ids': set(),
            },
        )
        region_bucket['value'] += row_total
        region_bucket['record_count'] += 1
        region_bucket['country_ids'].add(country_id)

        country_bucket = by_country.setdefault(
            country_id,
            {
                'country_id': country_id,
                'name': country_names.get(country_id, 'Unknown'),
                'value': 0.0,
                'record_count': 0,
                'disaggregated_count': 0,
            },
        )
        country_bucket['value'] += row_total
        country_bucket['record_count'] += 1

        mode = accumulate_disaggregation(disagg_raw, by_sex=by_sex, by_age=by_age)
        if mode:
            disaggregated_count += 1
            trend['disaggregated_count'] += 1
            country_bucket['disaggregated_count'] += 1
            region_bucket['disaggregated_count'] += 1

    disaggregation_rate = (
        round(100.0 * disaggregated_count / record_count, 1) if record_count else 0.0
    )

    country_list = []
    if include_country_breakdown:
        for bucket in by_country.values():
            rc = bucket['record_count'] or 0
            dc = bucket['disaggregated_count'] or 0
            country_list.append(
                {
                    'country_id': bucket['country_id'],
                    'name': bucket['name'],
                    'value': round(bucket['value'], 2),
                    'record_count': rc,
                    'disaggregated_count': dc,
                    'disaggregation_rate': round(100.0 * dc / rc, 1) if rc else 0.0,
                }
            )
        country_list.sort(key=lambda item: item['value'], reverse=True)

    region_list = []
    for bucket in by_region.values():
        rc = bucket['record_count'] or 0
        dc = bucket['disaggregated_count'] or 0
        region_list.append(
            {
                'region': bucket['region'],
                'value': round(bucket['value'], 2),
                'record_count': rc,
                'disaggregated_count': dc,
                'disaggregation_rate': round(100.0 * dc / rc, 1) if rc else 0.0,
                'country_count': len(bucket['country_ids']),
            }
        )
    region_list.sort(key=lambda item: item['value'], reverse=True)

    trend_list = []
    for bucket in trends.values():
        rc = bucket['record_count'] or 0
        dc = bucket['disaggregated_count'] or 0
        trend_list.append(
            {
                'period': bucket['period'],
                'total': round(bucket['total'], 2),
                'record_count': rc,
                'disaggregated_count': dc,
                'disaggregation_rate': round(100.0 * dc / rc, 1) if rc else 0.0,
            }
        )
    trend_list.sort(key=lambda item: item['period'])

    return {
        'total': round(total, 2),
        'record_count': record_count,
        'disaggregated_count': disaggregated_count,
        'disaggregation_rate': disaggregation_rate,
        'by_sex': sorted_breakdown(by_sex),
        'by_age': sorted_breakdown(by_age),
        'by_country': country_list[:25],
        'by_region': region_list,
        'trends': trend_list,
        'country_details_available': include_country_breakdown,
    }
