"""Load secondary snapshots for the master extract."""

from __future__ import annotations

from typing import Any

from plugins.upr.secondary import paths
from plugins.upr.secondary.io import read_json
from plugins.upr.secondary.planning_bundle import planning_bundle_by_iso3


def _by_iso3_map(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    for key in ("by_iso3", "values", "scores"):
        block = payload.get(key)
        if isinstance(block, dict):
            return {str(k).strip().upper(): v for k, v in block.items() if k}
    return {}


def load_population() -> dict[str, Any]:
    return _by_iso3_map(read_json(paths.GLOBAL_FILES["population"], default={}))


def load_poverty() -> dict[str, Any]:
    return _by_iso3_map(read_json(paths.GLOBAL_FILES["poverty"], default={}))


def load_income_groups() -> dict[str, Any]:
    return _by_iso3_map(read_json(paths.GLOBAL_FILES["income_groups"], default={}))


def load_inform_risk() -> dict[str, Any]:
    path = paths.GLOBAL_FILES["inform_risk"]
    if not path.is_file():
        path = paths.LEGACY_INFORM_RISK
    payload = read_json(path, default={}) or {}
    scores = _by_iso3_map(payload)
    from plugins.upr.flow import inform_class, inform_class_label

    # Prefer class codes when present; always export human-readable labels
    # (Very High), matching INFORM Severity Category in the master extract.
    classes = payload.get("class_by_iso3") if isinstance(payload, dict) else None
    if isinstance(classes, dict) and classes:
        return {
            str(k).strip().upper(): inform_class_label(v)
            for k, v in classes.items()
            if k and inform_class_label(v)
        }
    out: dict[str, Any] = {}
    for iso3, score in scores.items():
        try:
            out[iso3] = inform_class_label(inform_class(float(score)))
        except (TypeError, ValueError):
            label = inform_class_label(score)
            if label:
                out[iso3] = label
    return out


def load_inform_severity() -> dict[str, Any]:
    return _by_iso3_map(read_json(paths.GLOBAL_FILES["inform_severity"], default={}))


def load_inform_climate() -> dict[str, Any]:
    return _by_iso3_map(read_json(paths.GLOBAL_FILES["inform_climate"], default={}))


def load_hdi() -> dict[str, dict[str, Any]]:
    payload = read_json(paths.GLOBAL_FILES["hdi"], default={}) or {}
    block = payload.get("by_iso3") if isinstance(payload, dict) else None
    if not isinstance(block, dict):
        return {}
    return {str(k).strip().upper(): (v if isinstance(v, dict) else {"score": v}) for k, v in block.items() if k}


def load_multilateral(round_code: str) -> dict[str, list[str]]:
    """ISO3 → list of PNS names providing multilateral support in that round."""
    path = paths.round_file("multilateral", round_code)
    payload = read_json(path, default={}) or {}
    out: dict[str, list[str]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        iso3 = str(row.get("iso3") or "").strip().upper()
        ns = str(row.get("ns") or "").strip()
        if not iso3 or not ns:
            continue
        out.setdefault(iso3, [])
        if ns not in out[iso3]:
            out[iso3].append(ns)
    for iso3 in out:
        out[iso3].sort()
    return out


def load_eas_sprm_ops(round_code: str) -> dict[str, float]:
    """ISO3 → SPRM/OPS CHF amount for the round."""
    path = paths.round_file("eas_sprm_ops", round_code)
    payload = read_json(path, default={}) or {}
    out: dict[str, float] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        iso3 = str(row.get("iso3") or "").strip().upper()
        try:
            value = float(row.get("value"))
        except (TypeError, ValueError):
            continue
        if not iso3 or value == 0:
            continue
        out[iso3] = out.get(iso3, 0) + value
    return out


def load_secondary_for_iso3(iso3: str) -> dict[str, Any]:
    """Flat secondary attributes for one country (master long/wide)."""
    code = (iso3 or "").strip().upper()
    if not code:
        return {}
    hdi = load_hdi().get(code) or {}
    poverty = load_poverty().get(code)
    attrs: dict[str, Any] = {
        "Total Population": load_population().get(code),
        "Income Group": load_income_groups().get(code),
        "INFORM Risk Class": load_inform_risk().get(code),
        "INFORM Severity Category": load_inform_severity().get(code),
        "INFORM Climate change Risk": load_inform_climate().get(code),
        "Poverty": poverty.get("value") if isinstance(poverty, dict) else poverty,
        "HDI Score": hdi.get("score"),
        "HDI Rank": hdi.get("rank"),
        "HDI Tier": hdi.get("tier"),
        "Part of Bundle": planning_bundle_by_iso3().get(code),
    }
    return {key: value for key, value in attrs.items() if value is not None and value != ""}
