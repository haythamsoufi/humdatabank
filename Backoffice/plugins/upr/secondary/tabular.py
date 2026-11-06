"""Parse CSV / Excel uploads into row dicts."""

from __future__ import annotations

import csv
import io
import re
from functools import lru_cache
from typing import Any, BinaryIO, Iterable

# Header tokens that mark a usable Excel/CSV header row (any one is enough).
_HEADER_HINTS = {
    "iso3",
    "iso_3",
    "countryiso3code",
    "country_iso3",
    "geographical_focus",
    "donor_name",
    "donor",
    "ns",
    "income_group",
    "inform_risk",
    "risk_class",
    "hdi",
    "hdi_score",
    "value",
    "amount_(chf)",
    "amount",
}


def _norm_header(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("%", "pct")
    text = re.sub(r"[^\w]+", "_", text)
    return text.strip("_")


def rows_from_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    for raw in reader:
        rows.append({_norm_header(k): (v.strip() if isinstance(v, str) else v) for k, v in raw.items()})
    return rows


def _excel_header_index(matrix: list[tuple[Any, ...]]) -> int:
    for index, row in enumerate(matrix[:25]):
        headers = {_norm_header(cell) for cell in (row or ()) if cell not in (None, "")}
        if headers & _HEADER_HINTS:
            return index
    return 0


def rows_from_upload(filename: str, data: bytes | BinaryIO) -> list[dict[str, Any]]:
    name = (filename or "").lower()
    raw = data.read() if hasattr(data, "read") else data
    if isinstance(raw, str):
        raw_bytes = raw.encode("utf-8")
    else:
        raw_bytes = bytes(raw)
    if name.endswith(".csv") or name.endswith(".txt"):
        return rows_from_csv(raw_bytes.decode("utf-8-sig"))
    if name.endswith(".xlsx") or name.endswith(".xls"):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("openpyxl is required for Excel uploads") from exc
        wb = load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
        ws = wb.active
        matrix = list(ws.iter_rows(values_only=True))
        if not matrix:
            return []
        header_i = _excel_header_index(matrix)
        headers = [_norm_header(cell) for cell in (matrix[header_i] or ())]
        rows: list[dict[str, Any]] = []
        for values in matrix[header_i + 1 :]:
            item = {headers[i]: values[i] for i in range(min(len(headers), len(values))) if headers[i]}
            if any(v is not None and str(v).strip() != "" for v in item.values()):
                rows.append(item)
        return rows
    raise ValueError("Upload must be .csv or .xlsx")


def pick(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        key = _norm_header(name)
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def iso3_of(row: dict[str, Any]) -> str:
    raw = pick(
        row,
        "iso3",
        "iso_3",
        "countryiso3code",
        "country_iso3",
        "iso",
        "code",
    )
    text = str(raw or "").strip().upper()
    if len(text) == 3 and text.isalpha():
        return text
    return ""


def country_label_of(row: dict[str, Any]) -> str:
    """Host / country display name when ISO3 is absent (pledge exports)."""
    raw = pick(
        row,
        "geographical_focus",
        "country",
        "country_name",
        "host",
        "host_country",
        "nation",
        "name_of_country",
    )
    return str(raw or "").strip()


_COUNTRY_STOPWORDS = {"the", "of", "and", "de", "la", "le", "a"}


def _norm_country_key(value: str) -> str:
    text = str(value or "").strip().lower().replace("&", " and ").replace("'", "")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text.startswith("the "):
        text = text[4:]
    return text


def _core_country_key(value: str) -> str:
    """Order-insensitive key without stopwords (matches GO vs DB naming)."""
    words = [w for w in _norm_country_key(value).split() if w and w not in _COUNTRY_STOPWORDS]
    return " ".join(sorted(words))


# Common GO / UNDP / World Bank name variants → ISO3 (used when DB names differ).
_COUNTRY_ISO3_ALIASES = {
    "democratic republic of congo": "COD",
    "democratic republic of the congo": "COD",
    "congo dem rep": "COD",
    "drc": "COD",
    "dr congo": "COD",
    "congo brazzaville": "COG",
    "republic of congo": "COG",
    "solomon island": "SLB",
    "iran": "IRN",
    "iran islamic rep": "IRN",
    "venezuela": "VEN",
    "bolivia": "BOL",
    "tanzania": "TZA",
    "moldova": "MDA",
    "syria": "SYR",
    "laos": "LAO",
    "lao pdr": "LAO",
    "viet nam": "VNM",
    "south korea": "KOR",
    "north korea": "PRK",
    "democratic people republic of korea": "PRK",
    "democratic peoples republic of korea": "PRK",
    "russia": "RUS",
    "swaziland": "SWZ",
    "czech republic": "CZE",
    "turkey": "TUR",
    "turkiye": "TUR",
    "palestine": "PSE",
    "occupied palestinian territory": "PSE",
    "cape verde": "CPV",
    "ivory coast": "CIV",
    "cote divoire": "CIV",
    "brunei": "BRN",
    "micronesia": "FSM",
    "uk": "GBR",
    "usa": "USA",
    "us": "USA",
    "united states": "USA",
}


def _word_sort_key(value: str) -> str:
    return " ".join(sorted(_norm_country_key(value).split()))


@lru_cache(maxsize=1)
def country_name_to_iso3() -> dict[str, str]:
    """Normalized country name / short name → ISO3 (from Country table when available)."""
    out: dict[str, str] = {}
    try:
        from app.models import Country

        rows = Country.query.with_entities(
            Country.name,
            Country.short_name,
            Country.iso3,
        ).all()
    except Exception:
        rows = []

    def _remember(label: str, code: str) -> None:
        key = _norm_country_key(label)
        if not key:
            return
        out.setdefault(key, code)
        out.setdefault(_word_sort_key(key), code)
        out.setdefault(_core_country_key(key), code)

    for name, short_name, iso3 in rows:
        code = str(iso3 or "").strip().upper()
        if len(code) != 3:
            continue
        for label in (name, short_name):
            if label:
                _remember(str(label), code)

    for alias, code in _COUNTRY_ISO3_ALIASES.items():
        # Prefer DB-backed ISO3 when the code exists; still register the alias text.
        out.setdefault(alias, code)
        out.setdefault(_word_sort_key(alias), code)
        out.setdefault(_core_country_key(alias), code)
    return out


def resolve_iso3(row: dict[str, Any], *, name_map: dict[str, str] | None = None) -> str:
    """ISO3 from an iso3 column, or by resolving a country/host name."""
    code = iso3_of(row)
    if code:
        return code
    label = country_label_of(row)
    if not label:
        return ""
    mapping = name_map if name_map is not None else country_name_to_iso3()
    key = _norm_country_key(label)
    for candidate in (
        key,
        _word_sort_key(key),
        _core_country_key(key),
        f"{key}s",  # Solomon Island → Solomon Islands
    ):
        if candidate and candidate in mapping:
            return mapping[candidate]
    return ""


def column_names(rows: Iterable[dict[str, Any]], *, limit: int = 5) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key and key not in seen:
                seen.add(key)
                names.append(key)
        if len(names) >= 40:
            break
        limit -= 1
        if limit <= 0 and names:
            break
    return names
