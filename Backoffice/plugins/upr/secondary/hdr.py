"""UNDP Human Development Report (HDI) CSV fetch."""

from __future__ import annotations

import csv
import io
import re
from typing import Any
from urllib.request import Request, urlopen

HDR_CSV_URL = (
    "https://hdr.undp.org/sites/default/files/2025_HDR/HDR25_Composite_indices_complete_time_series.csv"
)


def _decode_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def hdi_latest_by_iso3(*, url: str = HDR_CSV_URL) -> tuple[dict[str, dict[str, Any]], int | None]:
    """Parse HDR composite indices CSV → iso3 → {score, rank, tier}, plus score year."""
    request = Request(url, headers={"User-Agent": "HumanitarianDatabank-UPR/1.0"})
    with urlopen(request, timeout=180) as response:  # noqa: S310 — fixed UNDP host
        raw = response.read()
    reader = csv.DictReader(io.StringIO(_decode_csv(raw)))
    fieldnames = list(reader.fieldnames or [])
    score_years = sorted(
        int(match.group(1))
        for name in fieldnames
        for match in [re.fullmatch(r"hdi_(\d{4})", str(name or ""))]
        if match
    )
    if not score_years:
        return {}, None
    year = score_years[-1]
    score_key = f"hdi_{year}"
    rank_key = f"hdi_rank_{year}" if f"hdi_rank_{year}" in fieldnames else "hdi_rank_2023"

    out: dict[str, dict[str, Any]] = {}
    for row in reader:
        iso3 = str(row.get("iso3") or "").strip().upper()
        if len(iso3) != 3 or not iso3.isalpha():
            continue
        entry: dict[str, Any] = {}
        score_raw = row.get(score_key)
        if score_raw not in (None, ""):
            try:
                entry["score"] = round(float(str(score_raw).replace(",", "")), 3)
            except (TypeError, ValueError):
                pass
        rank_raw = row.get(rank_key)
        if rank_raw not in (None, ""):
            try:
                entry["rank"] = int(float(str(rank_raw).replace(",", "")))
            except (TypeError, ValueError):
                pass
        tier = str(row.get("hdicode") or "").strip()
        if tier:
            entry["tier"] = tier
        if entry:
            out[iso3] = entry
    return out, year
