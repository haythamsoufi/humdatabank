"""Active IFRC GO operations for a country or region.

Figures match the GO emergencies and regional operations pages:

* ``GET /api/v2/appeal/aggregated/`` — active DREF and appeal counts, people
  targeted, and funding.
* ``GET /api/v2/appeal/?status=0`` — the active operations behind those totals.
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any

import requests

logger = logging.getLogger(__name__)

GO_API_ROOT = "https://goadmin.ifrc.org/api/v2"
_PAGE_LIMIT = 200
_MAX_PAGES = 2
_TIMEOUT_SECONDS = 12
_CACHE_TTL_SECONDS = 10 * 60
_COUNTRY_OPERATION_LIMIT = 8
_REGION_OPERATION_LIMIT = 5
_REGION_COUNTRY_LIMIT = 8

# GO region ids. Middle East is matched before Africa, and Europe before Asia,
# because "Europe and Central Asia" contains "asia".
_GO_REGION_RULES = (
    ("middle east", 4),
    ("mena", 4),
    ("europe", 3),
    ("asia", 2),
    ("america", 1),
    ("africa", 0),
)

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = Lock()


def reset_go_operations_cache_for_tests() -> None:
    with _cache_lock:
        _cache.clear()


def go_region_id(region_name: str | None) -> int | None:
    """Map a Databank region name onto a GO region id, or None when unknown."""
    text = " ".join((region_name or "").lower().split())
    if not text:
        return None
    for needle, region_id in _GO_REGION_RULES:
        if needle in text:
            return region_id
    return None


def _number(raw: Any) -> float:
    if isinstance(raw, bool) or raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return 0.0


def _whole(raw: Any) -> int:
    return int(round(_number(raw)))


def parse_aggregated(payload: Any) -> dict[str, Any]:
    """Headline figures from ``/appeal/aggregated/``."""
    data = payload if isinstance(payload, dict) else {}
    requested = data.get("amount_requested_dref_included")
    if requested is None:
        requested = data.get("amount_requested")
    funded = data.get("amount_funded_dref_included")
    if funded is None:
        funded = data.get("amount_funded")
    return {
        "active_drefs": _whole(data.get("active_drefs")),
        "active_appeals": _whole(data.get("active_appeals")),
        "people_targeted": _whole(data.get("target_population")),
        "amount_requested": _number(requested),
        "amount_funded": _number(funded),
    }


def operation_query_params(
    *,
    iso3: str | None = None,
    region_id: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(aggregated params, appeal-list params)``.

    ``/appeal/aggregated/`` filters a country with ``iso3``. ``country__iso3`` is
    ignored there and the response is the worldwide total. The appeal list uses
    ``country__iso3``.
    """
    if iso3:
        code = iso3.strip().upper()
        return {"iso3": code}, {"country__iso3": code}
    if region_id is not None:
        scope = {"region": int(region_id)}
        return scope, dict(scope)
    return {}, {}


def parse_active_appeals(items: Any, *, iso3: str | None = None) -> list[dict[str, Any]]:
    """Active appeal rows. Closed, malformed, or other-country rows are dropped."""
    if not isinstance(items, list):
        return []
    wanted = (iso3 or "").strip().upper() or None
    operations: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("status") != 0 and str(item.get("status_display") or "").lower() != "active":
            continue
        country = item.get("country") if isinstance(item.get("country"), dict) else {}
        code = str(country.get("iso3") or "").strip().upper()
        if wanted and code != wanted:
            continue
        dtype = item.get("dtype") if isinstance(item.get("dtype"), dict) else {}
        start = str(item.get("start_date") or "")[:10]
        name = str(item.get("name") or "").strip() or str(item.get("code") or "").strip()
        if not name:
            continue
        operations.append({
            "name": name,
            "code": str(item.get("code") or "").strip() or None,
            "appeal_type": str(item.get("atype_display") or "").strip() or "Operation",
            "disaster_type": str(dtype.get("name") or "").strip() or None,
            "country_name": str(country.get("name") or "").strip() or None,
            "iso3": str(country.get("iso3") or "").strip().upper() or None,
            "people_targeted": _whole(item.get("num_beneficiaries")),
            "amount_requested": _number(item.get("amount_requested")),
            "amount_funded": _number(item.get("amount_funded")),
            "start_date": start or None,
        })
    return operations


def operations_by_country(operations: list[dict[str, Any]], *, limit: int = _REGION_COUNTRY_LIMIT) -> list[dict[str, Any]]:
    """Active-operation counts and people targeted, largest countries first."""
    grouped: dict[str, dict[str, Any]] = {}
    for operation in operations:
        key = operation.get("iso3") or operation.get("country_name") or ""
        if not key:
            continue
        row = grouped.get(key)
        if row is None:
            row = {
                "name": operation.get("country_name") or key,
                "iso3": operation.get("iso3"),
                "operations": 0,
                "people_targeted": 0,
            }
            grouped[key] = row
        row["operations"] += 1
        row["people_targeted"] += int(operation.get("people_targeted") or 0)
    ranked = sorted(grouped.values(), key=lambda row: (-row["people_targeted"], -row["operations"], row["name"]))
    return ranked[:limit]


def _rank_operations(operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        operations,
        key=lambda row: (-int(row.get("people_targeted") or 0), row.get("start_date") or "", row["name"]),
    )


def build_operations_payload(
    aggregated: Any,
    appeals: list[dict[str, Any]],
    *,
    operation_limit: int,
    include_countries: bool,
    iso3: str | None = None,
) -> dict[str, Any]:
    active = _rank_operations(parse_active_appeals(appeals, iso3=iso3))
    payload: dict[str, Any] = {
        "summary": parse_aggregated(aggregated),
        "operations": active[:operation_limit],
    }
    if include_countries:
        payload["by_country"] = operations_by_country(active)
    return payload


def _get_json(session: requests.Session, path: str, params: dict[str, Any]) -> Any:
    response = session.get(
        f"{GO_API_ROOT}{path}",
        params={"format": "json", **params},
        timeout=_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    response.raise_for_status()
    return response.json()


def operations_payloads_from_appeals(appeals: list) -> dict[str, dict[str, Any]]:
    """Split active appeals into the per-country operations payload.

    Summary figures are the sums of those appeals. Countries with no active
    appeal are omitted; callers fill an empty payload for the rest.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for operation in parse_active_appeals(appeals):
        code = operation.get("iso3") or ""
        if not code:
            continue
        grouped.setdefault(code, []).append(operation)

    payloads: dict[str, dict[str, Any]] = {}
    for code, operations in grouped.items():
        ranked = _rank_operations(operations)
        drefs = 0
        appeal_count = 0
        people = 0
        requested = 0.0
        funded = 0.0
        for operation in ranked:
            kind = str(operation.get("appeal_type") or "").lower()
            if "dref" in kind:
                drefs += 1
            else:
                appeal_count += 1
            people += int(operation.get("people_targeted") or 0)
            requested += float(operation.get("amount_requested") or 0)
            funded += float(operation.get("amount_funded") or 0)
        payloads[code] = {
            "summary": {
                "active_drefs": drefs,
                "active_appeals": appeal_count,
                "people_targeted": people,
                "amount_requested": requested,
                "amount_funded": funded,
            },
            "operations": ranked[:_COUNTRY_OPERATION_LIMIT],
            "available": True,
            "supported": True,
        }
    return payloads


def fetch_operations_by_iso3() -> tuple[dict[str, dict[str, Any]], bool]:
    """Every country's active operations from one worldwide appeal list.

    ``available`` is false when GO cannot be reached. The result is cached
    with the other GO responses.
    """
    cache_key = "all-countries"
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1], True

    try:
        with requests.Session() as session:
            session.headers.update(
                {"User-Agent": "hum-databank-backoffice/1.0", "Accept": "application/json"}
            )
            appeals = _active_appeals(session, {}, pages=5)
    except (requests.RequestException, ValueError) as exc:
        logger.warning("GO operations %s failed: %s", cache_key, exc)
        return {}, False

    payloads = operations_payloads_from_appeals(appeals)
    with _cache_lock:
        _cache[cache_key] = (time.monotonic(), payloads)
    return payloads, True


def _active_appeals(
    session: requests.Session,
    scope: dict[str, Any],
    pages: int | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page_limit = _MAX_PAGES if pages is None else pages
    for _ in range(page_limit):
        payload = _get_json(
            session,
            "/appeal/",
            {**scope, "status": 0, "limit": _PAGE_LIMIT, "offset": offset},
        )
        if not isinstance(payload, dict):
            break
        page = payload.get("results")
        if not isinstance(page, list) or not page:
            break
        rows.extend(page)
        if not payload.get("next") or len(page) < _PAGE_LIMIT:
            break
        offset += _PAGE_LIMIT
    return rows


def fetch_operations(
    *,
    iso3: str | None = None,
    region_id: int | None = None,
) -> tuple[dict[str, Any], bool]:
    """Return ``(payload, available)``. ``available`` is false when GO cannot be reached."""
    aggregated_params, appeals_params = operation_query_params(iso3=iso3, region_id=region_id)
    if iso3:
        cache_key = f"country:{aggregated_params['iso3']}"
        operation_limit = _COUNTRY_OPERATION_LIMIT
        include_countries = False
    elif region_id is not None:
        cache_key = f"region:{aggregated_params['region']}"
        operation_limit = _REGION_OPERATION_LIMIT
        include_countries = True
    else:
        return build_operations_payload({}, [], operation_limit=0, include_countries=False), True

    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(cache_key)
        if cached is not None and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1], True

    try:
        with requests.Session() as session:
            session.headers.update(
                {"User-Agent": "hum-databank-backoffice/1.0", "Accept": "application/json"}
            )
            aggregated = _get_json(session, "/appeal/aggregated/", aggregated_params)
            appeals = _active_appeals(session, appeals_params)
    except (requests.RequestException, ValueError) as exc:
        logger.warning("GO operations %s failed: %s", cache_key, exc)
        return build_operations_payload({}, [], operation_limit=operation_limit, include_countries=include_countries), False

    payload = build_operations_payload(
        aggregated,
        appeals,
        operation_limit=operation_limit,
        include_countries=include_countries,
        iso3=iso3.strip().upper() if iso3 else None,
    )
    with _cache_lock:
        _cache[cache_key] = (time.monotonic(), payload)
    return payload, True
