"""Build tabular previews of stored secondary snapshots for the settings UI."""

from __future__ import annotations

from typing import Any

from plugins.upr.secondary import paths
from plugins.upr.secondary.io import read_json
from plugins.upr.secondary.loaders import (
    load_eas_sprm_ops,
    load_hdi,
    load_income_groups,
    load_inform_climate,
    load_inform_risk,
    load_inform_severity,
    load_multilateral,
    load_population,
    load_poverty,
)
from plugins.upr.secondary.registry import list_round_files, source_status


def _cap(rows: list[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], int]:
    total = len(rows)
    if limit > 0 and total > limit:
        return rows[:limit], total
    return rows, total


def preview_source(
    source_id: str,
    *,
    round_code: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Return columns + sample rows for a secondary source."""
    status = source_status(source_id)
    if not status.get("id"):
        raise ValueError(f"Unknown source: {source_id}")

    limit = max(1, min(int(limit or 100), 500))
    code = (round_code or "").strip().upper() or None
    columns: list[str]
    rows: list[dict[str, Any]]
    note = None

    if source_id == "population":
        columns = ["iso3", "value"]
        rows = [{"iso3": k, "value": v} for k, v in sorted(load_population().items())]
    elif source_id == "poverty":
        columns = ["iso3", "value", "year"]
        rows = []
        for iso3, payload in sorted(load_poverty().items()):
            if isinstance(payload, dict):
                rows.append({"iso3": iso3, "value": payload.get("value"), "year": payload.get("year")})
            else:
                rows.append({"iso3": iso3, "value": payload, "year": None})
    elif source_id == "income_groups":
        columns = ["iso3", "income_group"]
        rows = [{"iso3": k, "income_group": v} for k, v in sorted(load_income_groups().items())]
    elif source_id == "inform_risk":
        columns = ["iso3", "risk_class"]
        rows = [{"iso3": k, "risk_class": v} for k, v in sorted(load_inform_risk().items())]
    elif source_id == "inform_severity":
        columns = ["iso3", "severity"]
        rows = [{"iso3": k, "severity": v} for k, v in sorted(load_inform_severity().items())]
    elif source_id == "inform_climate":
        columns = ["iso3", "climate_risk"]
        rows = [{"iso3": k, "climate_risk": v} for k, v in sorted(load_inform_climate().items())]
    elif source_id == "hdi":
        columns = ["iso3", "score", "rank", "tier"]
        rows = []
        for iso3, payload in sorted(load_hdi().items()):
            entry = payload if isinstance(payload, dict) else {"score": payload}
            rows.append(
                {
                    "iso3": iso3,
                    "score": entry.get("score"),
                    "rank": entry.get("rank"),
                    "tier": entry.get("tier"),
                }
            )
    elif source_id == "multilateral":
        rounds = list_round_files("multilateral")
        if not code:
            code = (rounds[0]["round"] if rounds else None)
        if not code:
            return {
                "id": source_id,
                "label": status.get("label"),
                "round": None,
                "rounds": [],
                "columns": ["iso3", "ns"],
                "rows": [],
                "total": 0,
                "limit": limit,
                "truncated": False,
                "note": "No rounds uploaded yet.",
                "status": status,
            }
        mapping = load_multilateral(code)
        columns = ["iso3", "ns"]
        rows = [{"iso3": iso3, "ns": ns} for iso3, names in sorted(mapping.items()) for ns in names]
        note = f"Round {code}"
        path = paths.round_file("multilateral", code)
        payload = read_json(path, default={}) or {}
        stats = payload.get("stats") if isinstance(payload, dict) else None
        if isinstance(stats, dict) and stats.get("year_window"):
            note = f"Round {code}; year window {stats['year_window']}"
    elif source_id == "eas_sprm_ops":
        rounds = list_round_files("eas_sprm_ops")
        if not code:
            code = (rounds[0]["round"] if rounds else None)
        if not code:
            return {
                "id": source_id,
                "label": status.get("label"),
                "round": None,
                "rounds": [],
                "columns": ["iso3", "value"],
                "rows": [],
                "total": 0,
                "limit": limit,
                "truncated": False,
                "note": "No rounds uploaded yet.",
                "status": status,
            }
        mapping = load_eas_sprm_ops(code)
        columns = ["iso3", "value"]
        rows = [{"iso3": k, "value": v} for k, v in sorted(mapping.items())]
        note = f"Round {code}"
    else:
        raise ValueError(f"Preview is not available for {source_id}")

    sample, total = _cap(rows, limit)
    rounds_meta = status.get("rounds") if source_id in {"multilateral", "eas_sprm_ops"} else None
    return {
        "id": source_id,
        "label": status.get("label"),
        "round": code,
        "rounds": rounds_meta or [],
        "columns": columns,
        "rows": sample,
        "total": total,
        "limit": limit,
        "truncated": total > len(sample),
        "note": note,
        "edition": status.get("edition"),
        "updated_at": status.get("updated_at"),
        "status": status,
    }
