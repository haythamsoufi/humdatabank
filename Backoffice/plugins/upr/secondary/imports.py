"""Import / refresh operations for secondary snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, BinaryIO

from plugins.upr.secondary import paths
from plugins.upr.secondary.io import write_json
from plugins.upr.secondary.registry import touch_source
from plugins.upr.secondary.tabular import (
    column_names,
    country_name_to_iso3,
    iso3_of,
    pick,
    resolve_iso3,
    rows_from_upload,
)
from plugins.upr.secondary.hdr import hdi_latest_by_iso3
from plugins.upr.secondary.inform import (
    refresh_inform_climate,
    refresh_inform_risk,
    refresh_inform_severity,
)
from plugins.upr.secondary.world_bank import (
    income_groups_by_iso3,
    population_latest_by_iso3,
    poverty_latest_by_iso3,
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace(" ", ""))
    except (TypeError, ValueError):
        return None


def refresh_population() -> dict[str, Any]:
    paths.ensure_dirs()
    values, max_year = population_latest_by_iso3()
    payload = {
        "indicator": "SP.POP.TOTL",
        "year": max_year,
        "updated_at": _now(),
        "by_iso3": values,
    }
    write_json(paths.GLOBAL_FILES["population"], payload)
    edition = (
        f"World Bank SP.POP.TOTL (latest through {max_year})"
        if max_year
        else "World Bank SP.POP.TOTL (latest)"
    )
    touch_source(
        "population",
        row_count=len(values),
        edition=edition,
        source="World Bank API",
    )
    return {"row_count": len(values), "year": max_year}


def refresh_poverty() -> dict[str, Any]:
    paths.ensure_dirs()
    values = poverty_latest_by_iso3()
    payload = {
        "indicator": "SI.POV.NAHC",
        "updated_at": _now(),
        "by_iso3": values,
    }
    write_json(paths.GLOBAL_FILES["poverty"], payload)
    touch_source(
        "poverty",
        row_count=len(values),
        edition="World Bank SI.POV.NAHC (latest year)",
        source="World Bank API",
    )
    return {"row_count": len(values)}


def refresh_income_groups() -> dict[str, Any]:
    paths.ensure_dirs()
    values = income_groups_by_iso3()
    payload = {"updated_at": _now(), "by_iso3": values, "source": "World Bank country API"}
    write_json(paths.GLOBAL_FILES["income_groups"], payload)
    touch_source(
        "income_groups",
        row_count=len(values),
        edition="World Bank incomeLevel (current)",
        source="World Bank API",
    )
    return {"row_count": len(values)}


def import_income_groups(filename: str, data: bytes | BinaryIO) -> dict[str, Any]:
    paths.ensure_dirs()
    values: dict[str, str] = {}
    for row in rows_from_upload(filename, data):
        iso3 = iso3_of(row)
        group = pick(row, "income_group", "income", "group", "value")
        if iso3 and group:
            values[iso3] = str(group).strip()
    payload = {"updated_at": _now(), "by_iso3": values}
    write_json(paths.GLOBAL_FILES["income_groups"], payload)
    touch_source(
        "income_groups",
        row_count=len(values),
        edition=filename,
        source="upload",
    )
    return {"row_count": len(values)}


def import_inform_risk(filename: str, data: bytes | BinaryIO, *, edition: str | None = None) -> dict[str, Any]:
    paths.ensure_dirs()
    scores: dict[str, float] = {}
    classes: dict[str, str] = {}
    for row in rows_from_upload(filename, data):
        iso3 = iso3_of(row)
        if not iso3:
            continue
        risk_class = pick(row, "risk_class", "class", "inform_risk_class", "value")
        score = _num(pick(row, "score", "risk", "inform_risk"))
        if risk_class and not str(risk_class).replace(".", "", 1).isdigit():
            classes[iso3] = str(risk_class).strip()
        if score is not None:
            scores[iso3] = score
    payload = {
        "edition": edition or filename,
        "updated_at": _now(),
        "scores": scores,
        "class_by_iso3": classes,
    }
    write_json(paths.GLOBAL_FILES["inform_risk"], payload)
    touch_source(
        "inform_risk",
        row_count=max(len(scores), len(classes)),
        edition=edition or filename,
        source="upload",
    )
    return {"row_count": max(len(scores), len(classes))}


def import_inform_severity(filename: str, data: bytes | BinaryIO) -> dict[str, Any]:
    paths.ensure_dirs()
    values: dict[str, Any] = {}
    for row in rows_from_upload(filename, data):
        iso3 = iso3_of(row)
        value = pick(row, "inform_severity_category", "severity", "category", "value")
        if iso3 and value is not None:
            values[iso3] = value if not isinstance(value, float) else value
            if isinstance(value, str):
                values[iso3] = value.strip()
    payload = {"updated_at": _now(), "by_iso3": values}
    write_json(paths.GLOBAL_FILES["inform_severity"], payload)
    touch_source("inform_severity", row_count=len(values), edition=filename, source="upload")
    return {"row_count": len(values)}


def import_inform_climate(filename: str, data: bytes | BinaryIO) -> dict[str, Any]:
    paths.ensure_dirs()
    values: dict[str, Any] = {}
    for row in rows_from_upload(filename, data):
        iso3 = iso3_of(row)
        value = pick(row, "inform_climate_change_risk", "climate", "risk", "value")
        if iso3 and value is not None:
            values[iso3] = value if isinstance(value, (int, float)) else str(value).strip()
    payload = {"updated_at": _now(), "by_iso3": values}
    write_json(paths.GLOBAL_FILES["inform_climate"], payload)
    touch_source("inform_climate", row_count=len(values), edition=filename, source="upload")
    return {"row_count": len(values)}


def refresh_hdi() -> dict[str, Any]:
    paths.ensure_dirs()
    values, year = hdi_latest_by_iso3()
    payload = {
        "updated_at": _now(),
        "year": year,
        "source": "UNDP HDR composite indices CSV",
        "by_iso3": values,
    }
    write_json(paths.GLOBAL_FILES["hdi"], payload)
    edition = f"UNDP HDR HDI {year}" if year else "UNDP HDR HDI"
    touch_source("hdi", row_count=len(values), edition=edition, source="UNDP HDR CSV")
    return {"row_count": len(values), "year": year}


def import_hdi(filename: str, data: bytes | BinaryIO) -> dict[str, Any]:
    paths.ensure_dirs()
    values: dict[str, dict[str, Any]] = {}
    for row in rows_from_upload(filename, data):
        iso3 = iso3_of(row)
        if not iso3:
            continue
        entry: dict[str, Any] = {}
        score = _num(pick(row, "hdi", "hdi_score", "score", "value"))
        rank = _num(pick(row, "hdi_rank", "rank"))
        tier = pick(row, "hdi_tier", "tier")
        if score is not None:
            entry["score"] = round(score, 3)
        if rank is not None:
            entry["rank"] = int(rank)
        if tier:
            entry["tier"] = str(tier).strip()
        if entry:
            values[iso3] = entry
    payload = {"updated_at": _now(), "by_iso3": values}
    write_json(paths.GLOBAL_FILES["hdi"], payload)
    touch_source("hdi", row_count=len(values), edition=filename, source="upload")
    return {"row_count": len(values)}


def _round_year(round_code: str, explicit: int | None = None) -> int | None:
    if explicit is not None:
        return int(explicit)
    digits = "".join(ch for ch in str(round_code or "") if ch.isdigit())
    if not digits:
        return None
    return 2000 + int(digits)


def _year_of(row: dict[str, Any]) -> int | None:
    raw = pick(row, "year", "yr", "calendar_year")
    if raw is None or raw == "":
        return None
    try:
        return int(float(str(raw).strip()[:4]))
    except (TypeError, ValueError):
        return None


def _year_window(round_year: int | None) -> set[int] | None:
    """Accept plan-round years ±1 (P27 → 2026–2028) when a Year column is present."""
    if round_year is None:
        return None
    return {round_year - 1, round_year, round_year + 1}


def _is_national_society_donor(row: dict[str, Any]) -> bool:
    """True when the row is a PNS donor, or when donor type is not present."""
    donor_type = pick(row, "donor_type", "type", "donor_category")
    if donor_type is None or donor_type == "":
        return True
    text = str(donor_type).strip().lower()
    return text in {
        "national society",
        "national societies",
        "ns",
        "pns",
        "red cross",
        "red crescent",
    }


def _ns_name_of(row: dict[str, Any]) -> str:
    raw = pick(
        row,
        "ns",
        "donor_name",
        "donor",
        "national_society",
        "pns",
        "pns_name",
        "participating_national_society",
        "society",
    )
    # Avoid treating a host country "name" column as the NS when donor_name exists elsewhere.
    if raw is None or raw == "":
        return ""
    return str(raw).strip()


def import_multilateral(
    round_code: str,
    filename: str,
    data: bytes | BinaryIO,
    *,
    year: int | None = None,
) -> dict[str, Any]:
    """Import host×PNS multilateral support rows for a planning round.

    Accepts either a simple ``iso3,ns`` sheet or a GO pledges export with
    ``Geographical focus``, ``Donor name``, ``Donor type``, ``Year``.
    """
    paths.ensure_dirs()
    code = (round_code or "").strip().upper()
    y = _round_year(code, year)
    years = _year_window(y)
    name_map = country_name_to_iso3()
    uploaded = rows_from_upload(filename, data)
    if not uploaded:
        raise ValueError("File has no data rows.")

    has_year_col = any(_year_of(row) is not None for row in uploaded[:50])
    has_donor_type = any(
        pick(row, "donor_type", "type", "donor_category") not in (None, "") for row in uploaded[:50]
    )
    rows_out: list[dict[str, Any]] = []
    unresolved: list[str] = []
    skipped_type = 0
    skipped_year = 0
    for row in uploaded:
        if has_donor_type and not _is_national_society_donor(row):
            skipped_type += 1
            continue
        if has_year_col and years is not None:
            row_year = _year_of(row)
            if row_year is not None and row_year not in years:
                skipped_year += 1
                continue
        ns = _ns_name_of(row)
        iso3 = resolve_iso3(row, name_map=name_map)
        if not iso3:
            label = str(
                pick(row, "geographical_focus", "country", "country_name", "host") or ""
            ).strip()
            if label and label not in unresolved and len(unresolved) < 12:
                unresolved.append(label)
            continue
        if not ns:
            continue
        rows_out.append({"iso3": iso3, "ns": ns})

    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for row in rows_out:
        key = (row["iso3"], row["ns"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    unique.sort(key=lambda r: (r["iso3"], r["ns"]))

    if not unique:
        cols = ", ".join(column_names(uploaded)[:16]) or "(none)"
        detail = []
        if unresolved:
            detail.append(f"unresolved countries: {', '.join(unresolved)}")
        if skipped_type:
            detail.append(f"skipped non-NS donors: {skipped_type}")
        if skipped_year:
            detail.append(f"skipped outside year window: {skipped_year}")
        extra = f" ({'; '.join(detail)})" if detail else ""
        raise ValueError(
            "No multilateral rows found. Need iso3+ns, or Geographical focus + Donor name "
            f"(National Society). Columns seen: {cols}.{extra}"
        )

    payload = {
        "round": code,
        "year": y,
        "updated_at": _now(),
        "rows": unique,
        "source_file": filename,
        "stats": {
            "uploaded_rows": len(uploaded),
            "kept_pairs": len(unique),
            "skipped_donor_type": skipped_type,
            "skipped_year": skipped_year,
            "unresolved_countries": unresolved,
            "year_window": sorted(years) if years else None,
        },
    }
    write_json(paths.round_file("multilateral", code), payload)
    touch_source(
        "multilateral",
        row_count=len(unique),
        edition=f"{code} ({filename})",
        source="upload",
        extra={"last_round": code},
    )
    return {
        "round": code,
        "year": y,
        "row_count": len(unique),
        "skipped_donor_type": skipped_type,
        "skipped_year": skipped_year,
        "unresolved_countries": unresolved,
    }


def import_eas_sprm_ops(
    round_code: str,
    filename: str,
    data: bytes | BinaryIO,
    *,
    year: int | None = None,
) -> dict[str, Any]:
    paths.ensure_dirs()
    code = (round_code or "").strip().upper()
    y = _round_year(code, year)
    years = _year_window(y)
    name_map = country_name_to_iso3()
    uploaded = rows_from_upload(filename, data)
    if not uploaded:
        raise ValueError("File has no data rows.")

    has_year_col = any(_year_of(row) is not None for row in uploaded[:50])
    by_iso: dict[str, float] = {}
    unresolved: list[str] = []
    skipped_year = 0
    for row in uploaded:
        if has_year_col and years is not None:
            row_year = _year_of(row)
            if row_year is not None and row_year not in years:
                skipped_year += 1
                continue
        iso3 = resolve_iso3(row, name_map=name_map)
        value = _num(
            pick(
                row,
                "value",
                "amount",
                "amount_(chf)",
                "amount_chf",
                "eas",
                "sprm",
                "chf",
                str(year or ""),
            )
        )
        if not iso3:
            label = str(
                pick(row, "geographical_focus", "country", "country_name", "host") or ""
            ).strip()
            if label and label not in unresolved and len(unresolved) < 12:
                unresolved.append(label)
            continue
        if value is None or value == 0:
            continue
        by_iso[iso3] = by_iso.get(iso3, 0) + value
    rows_out = [{"iso3": iso3, "value": value} for iso3, value in sorted(by_iso.items())]
    if not rows_out:
        cols = ", ".join(column_names(uploaded)[:16]) or "(none)"
        detail = f" Unresolved: {', '.join(unresolved)}." if unresolved else ""
        raise ValueError(
            f"No EAs SPRM/OPS rows found. Need iso3+value (or Geographical focus + Amount (CHF)). "
            f"Columns seen: {cols}.{detail}"
        )
    payload = {
        "round": code,
        "year": y,
        "updated_at": _now(),
        "rows": rows_out,
        "source_file": filename,
        "stats": {
            "uploaded_rows": len(uploaded),
            "kept_countries": len(rows_out),
            "skipped_year": skipped_year,
            "unresolved_countries": unresolved,
            "year_window": sorted(years) if years else None,
        },
    }
    write_json(paths.round_file("eas_sprm_ops", code), payload)
    touch_source(
        "eas_sprm_ops",
        row_count=len(rows_out),
        edition=f"{code} ({filename})",
        source="upload",
        extra={"last_round": code, "year": y},
    )
    return {
        "round": code,
        "year": y,
        "row_count": len(rows_out),
        "skipped_year": skipped_year,
        "unresolved_countries": unresolved,
    }


def delete_round_snapshot(kind: str, round_code: str) -> bool:
    path = paths.round_file(kind, round_code)
    if path.is_file():
        path.unlink()
        return True
    return False
