"""Reporting-currency amounts and their Swiss-franc companions.

Income and expenditure keep the amount the focal point entered on the visible
form item. The Swiss-franc figure is a second form item (``fdrs_chf_companion``).
Income-source rows keep the entered amount in the Funding cell and the
Swiss-franc figure under ``_chf|{cell}`` in the same matrix JSON.

Rates come from IFRC ``GetCHFExchangeRate/{currency}/{date}`` using the
financial reporting end date (``KPI_EndDate``). ``chfExchangeRate`` is Swiss
francs per 1 unit of local currency, so Swiss francs = local amount × that
rate. ``exchange_rates.json`` can override a date or a year.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping, Optional

CHF_MATRIX_PREFIX = "_chf|"
CHF_SUFFIX = "_CHF"
REPORTING_CURRENCY_ITEM_ID = 918
REPORTING_END_DATE_ITEM_ID = 937

# Visible indicator code, companion indicator code.
CURRENCY_AMOUNT_PAIRS = (
    ("KPI_IncomeLC", "KPI_IncomeLC_CHF"),
    ("KPI_expenditureLC", "KPI_expenditureLC_CHF"),
)

_RATES_PATH = Path(__file__).resolve().parents[1] / "data" / "exchange_rates.json"
_YEAR_RE = re.compile(r"20\d{2}")
_IFRC_RATE_URL = "https://interfaces.ifrc.org/ExchangeRate/api/GetCHFExchangeRate"
_RATE_CACHE: dict[tuple[str, str], float] = {}


def is_chf_currency(code: Any) -> bool:
    return str(code or "").strip().upper() == "CHF"


def chf_matrix_key(cell_key: str) -> str:
    return f"{CHF_MATRIX_PREFIX}{cell_key}"


def income_source_slot(base_kpi: str, chf_to_row: Mapping[str, str]) -> Optional[tuple[str, str]]:
    """Return ``(row label, 'local'|'chf')`` when ``base_kpi`` is an income source."""
    code = (base_kpi or "").strip()
    if not code:
        return None
    if code in chf_to_row:
        return chf_to_row[code], "chf"
    chf_code = f"{code}{CHF_SUFFIX}"
    if chf_code in chf_to_row:
        return chf_to_row[chf_code], "local"
    return None


def is_local_income_kpi(base_kpi: str, chf_to_row: Mapping[str, str]) -> bool:
    slot = income_source_slot(base_kpi, chf_to_row)
    return slot is not None and slot[1] == "local"


def resolve_reported_amounts(
    local: Any,
    chf: Any,
    currency: Any,
) -> tuple[Any, Any]:
    """Pick the reporting-currency amount and the Swiss-franc amount.

    When the reporting currency is CHF the two figures are the same, so whichever
    side arrived fills both. When it is a local currency, the entered amount stays
    separate from the Swiss-franc figure. If only the Swiss-franc figure arrived,
    both sides keep that figure so existing CHF-only rows still show a number.
    """
    if is_chf_currency(currency):
        amount = local if local is not None else chf
        return amount, amount
    if local is not None:
        return local, chf
    if chf is not None:
        return chf, chf
    return None, None


def period_year(period_name: Any) -> str:
    text = str(period_name or "").strip()
    years = _YEAR_RE.findall(text)
    if years:
        return years[-1]
    return text[:4] if len(text) >= 4 and text[:4].isdigit() else text


def normalize_rate_date(value: Any) -> Optional[str]:
    """Return ``YYYY-MM-DD`` for an end date, or None when it is not a date."""
    text = str(value or "").strip()
    if not text or text.lower() in {"none", "null"}:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        day = text[:10]
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            return None
        return day
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def exchange_rate_date(value: Any) -> Optional[str]:
    """The IFRC rate date: the financial reporting end date as entered."""
    return normalize_rate_date(value)


def load_exchange_rates() -> dict[str, dict[str, float]]:
    """Year → currency code → Swiss francs per 1 local unit (optional overrides)."""
    try:
        raw = json.loads(_RATES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    table = raw.get("chf_per_unit") if isinstance(raw, dict) else None
    if not isinstance(table, dict):
        return {}
    out: dict[str, dict[str, float]] = {}
    for year, currencies in table.items():
        if not isinstance(currencies, dict):
            continue
        year_rates: dict[str, float] = {}
        for code, rate in currencies.items():
            number = _positive_rate(rate)
            if number is None:
                continue
            year_rates[str(code).strip().upper()] = number
        if year_rates:
            out[str(year).strip()] = year_rates
    return out


def parse_chf_exchange_rate(payload: Any) -> Optional[float]:
    """Read ``chfExchangeRate`` (Swiss francs per 1 unit of the requested currency)."""
    if not isinstance(payload, dict):
        return None
    return _positive_rate(payload.get("chfExchangeRate"))


def _exchange_api_key() -> str:
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            configured = (current_app.config.get("IFRC_EXCHANGE_RATE_API_KEY") or "").strip()
            if configured:
                return configured
    except Exception:
        pass
    return (os.environ.get("IFRC_EXCHANGE_RATE_API_KEY") or "").strip()


def fetch_ifrc_chf_rate(currency: str, on_date: Any) -> Optional[float]:
    """Ask IFRC for the Swiss-franc rate of one currency on ``on_date``."""
    code = (currency or "").strip().upper()
    day = normalize_rate_date(on_date)
    if not code or is_chf_currency(code) or not day:
        return None
    cached = _RATE_CACHE.get((code, day))
    if cached is not None:
        return cached
    api_key = _exchange_api_key()
    if not api_key:
        return None
    query = urllib.parse.urlencode({"apikey": api_key})
    url = f"{_IFRC_RATE_URL}/{urllib.parse.quote(code)}/{day}?{query}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError, ValueError):
        return None
    rate = parse_chf_exchange_rate(payload)
    if rate is not None:
        _RATE_CACHE[(code, day)] = rate
    return rate


def rate_for_date(on_date: Any, currency: Any) -> Optional[float]:
    """Swiss francs per 1 local unit on the financial reporting end date."""
    if is_chf_currency(currency):
        return None
    code = str(currency or "").strip().upper()
    day = normalize_rate_date(on_date)
    if not code or not day:
        return None
    table = load_exchange_rates()
    override = table.get(day, {}).get(code)
    if override is None:
        override = table.get(day[:4], {}).get(code)
    if override is not None:
        return override
    return fetch_ifrc_chf_rate(code, day)


def reporting_end_item(items: Any) -> Any:
    """The question that stores ``KPI_EndDate``."""
    fallback = None
    for item in items or []:
        if getattr(item, "id", None) == REPORTING_END_DATE_ITEM_ID:
            fallback = item
        if getattr(item, "item_type", None) != "question":
            continue
        label = (getattr(item, "label", None) or "").lower()
        if "financial reporting end" in label:
            return item
    return fallback


def end_date_from_items(items: Any, form_values: Mapping[str, Any]) -> str:
    """Posted financial reporting end date as ``YYYY-MM-DD``, or ``""``."""
    item = reporting_end_item(items)
    if item is None:
        raw = form_values.get(f"field_value[{REPORTING_END_DATE_ITEM_ID}]")
    else:
        raw = form_values.get(f"field_value[{item.id}]")
    return normalize_rate_date(raw) or ""


def local_to_chf(local: Any, rate: Any) -> Optional[int]:
    """Convert a reporting-currency amount to whole Swiss francs."""
    number = _decimal(local)
    rate_number = _decimal(rate)
    if number is None or rate_number is None or rate_number <= 0:
        return None
    converted = (number * rate_number).to_integral_value(rounding=ROUND_HALF_UP)
    return int(converted)


def merge_income_matrix_chf(
    incoming: Mapping[str, Any] | None,
    existing: Mapping[str, Any] | None,
    currency: Any,
    rate: Any,
    *,
    column: str = "Funding",
) -> dict[str, Any]:
    """Keep a Swiss-franc figure next to each Funding cell the form just saved.

    The matrix editor drops keys that start with ``_`` before submit. This puts
    them back: copy the cell when the currency is CHF, convert when a rate is
    loaded, and otherwise keep the stored figure when the entered amount did not
    change.
    """
    result = dict(incoming or {})
    previous = existing if isinstance(existing, dict) else {}
    suffix = f"_{column}"
    for key, value in list(result.items()):
        if not isinstance(key, str) or key.startswith("_") or not key.endswith(suffix):
            continue
        chf_key = chf_matrix_key(key)
        if is_chf_currency(currency):
            result[chf_key] = value
            continue
        converted = local_to_chf(value, rate) if rate else None
        if converted is not None:
            result[chf_key] = converted
            continue
        if previous.get(key) == value and chf_key in previous:
            result[chf_key] = previous[chf_key]
    return result


def is_fdrs_income_matrix(item: Any) -> bool:
    config = getattr(item, "config", None) or {}
    if isinstance(config, dict) and config.get("fdrs_income_sources"):
        return True
    if getattr(item, "item_type", None) != "matrix":
        return False
    if getattr(item, "template_id", None) not in (21, None):
        return False
    label = (getattr(item, "label", None) or "").lower()
    return "income" in label and "source" in label


def is_chf_companion_item(item: Any) -> bool:
    config = getattr(item, "config", None) or {}
    return isinstance(config, dict) and bool(config.get("fdrs_chf_companion"))


def currency_code_from_items(items: Any, form_values: Mapping[str, Any]) -> str:
    """Reporting-currency code posted with this form version."""
    for item in items or []:
        if getattr(item, "item_type", None) != "question":
            continue
        label = (getattr(item, "label", None) or "").lower()
        if "reporting currency" not in label:
            continue
        return str(form_values.get(f"field_value[{item.id}]") or "").strip()
    return str(form_values.get(f"field_value[{REPORTING_CURRENCY_ITEM_ID}]") or "").strip()


def copy_import_row(row: Mapping[str, Any], item_id: int) -> dict[str, Any]:
    copied = dict(row)
    copied["item_id"] = str(item_id)
    if "form_item_id" in copied:
        copied["form_item_id"] = str(item_id)
    return copied


def mirror_chf_currency_rows(
    rows: list[dict[str, Any]],
    pairs: list[tuple[int, int]],
    currency_by_assignment: Mapping[str, str],
) -> list[dict[str, Any]]:
    """When the reporting currency is CHF, copy a lone side onto the other item.

    Both KPIs normally arrive together and already match. This covers a row
    where only one of the pair was present.
    """
    if not pairs or not rows:
        return rows
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        assignment = str(row.get("assignment_entity_status_id") or "").strip()
        item = str(row.get("item_id") or row.get("form_item_id") or "").strip()
        if assignment and item:
            indexed[(assignment, item)] = row
    extra: list[dict[str, Any]] = []
    for local_id, chf_id in pairs:
        local_key = str(local_id)
        chf_key = str(chf_id)
        assignments = {
            assignment
            for assignment, item in indexed
            if item in (local_key, chf_key)
        }
        for assignment in assignments:
            if not is_chf_currency(currency_by_assignment.get(assignment)):
                continue
            local_row = indexed.get((assignment, local_key))
            chf_row = indexed.get((assignment, chf_key))
            if local_row is not None and chf_row is None:
                extra.append(copy_import_row(local_row, chf_id))
            elif chf_row is not None and local_row is None:
                extra.append(copy_import_row(chf_row, local_id))
    if not extra:
        return rows
    return [*rows, *extra]


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        number = value
    else:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        try:
            number = Decimal(text)
        except (InvalidOperation, ValueError):
            return None
    if not number.is_finite():
        return None
    return number


def _positive_rate(value: Any) -> Optional[float]:
    number = _decimal(value)
    if number is None or number <= 0:
        return None
    return float(number)
