"""Fetch and parse official INFORM Excel releases (Risk, Severity, Climate Change)."""

from __future__ import annotations

import io
import json
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin
from urllib.request import Request, urlopen

from openpyxl import load_workbook

from plugins.upr.analysis.flow import inform_class
from plugins.upr.secondary import paths
from plugins.upr.secondary.io import write_json
from plugins.upr.secondary.registry import touch_source

DRMCK_BASE = "https://drmkc.jrc.ec.europa.eu"
RISK_PAGE = f"{DRMCK_BASE}/inform-index/INFORM-Risk/Results-and-data"
SEVERITY_PAGE = f"{DRMCK_BASE}/inform-index/INFORM-Severity/Results-and-data"
CLIMATE_PAGE = f"{DRMCK_BASE}/inform-index/INFORM-Climate-Change/INFORM-Climate-Change-Tool"
PUBLICATIONS_PAGE = f"{DRMCK_BASE}/inform-index/About/Publications"
HDX_SEVERITY_PACKAGE = "https://data.humdata.org/api/3/action/package_show?id=inform-global-crisis-severity-index"

_UA = {
    "User-Agent": "HumanitarianDatabank-UPR/1.0",
    "Accept": "*/*",
}


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _http_get(url: str, *, referer: str | None = None, timeout: int = 180, retries: int = 4) -> bytes:
    headers = dict(_UA)
    if referer:
        headers["Referer"] = referer
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 — fixed DRMCK/HDX hosts
                return response.read()
        except (HTTPError, URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Failed to download {url}: {last_error}")


def _abs_url(href: str) -> str:
    if href.startswith("http"):
        return href
    if " " in href:
        parts = href.split("/")
        parts[-1] = quote(parts[-1])
        href = "/".join(parts)
    return urljoin(DRMCK_BASE + "/", href.lstrip("/"))


def _xlsx_links(html: str) -> list[str]:
    found = re.findall(r'href=["\']([^"\']+\.xlsx[^"\']*)["\']', html, flags=re.I)
    out: list[str] = []
    seen: set[str] = set()
    for href in found:
        url = _abs_url(href.split("?")[0])
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _filename(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def discover_risk_xlsx_url() -> tuple[str, str]:
    html = _http_get(RISK_PAGE, timeout=90).decode("utf-8", "replace")
    links = [
        url
        for url in _xlsx_links(html)
        if "trend" not in url.lower() and "subnational" not in url.lower()
    ]
    if not links:
        raise RuntimeError("No INFORM Risk Excel link found on results page")
    links.sort(
        key=lambda url: (
            0 if re.search(r"mid[_-]?\d{4}|mid\d{4}", url, flags=re.I) else 1,
            _filename(url).lower(),
        )
    )
    url = links[0]
    return url, _filename(url)


def discover_severity_xlsx_url() -> tuple[str, str]:
    # Prefer DRMCK Severity folder links from Publications (stable Portal paths).
    for page in (SEVERITY_PAGE, PUBLICATIONS_PAGE):
        try:
            html = _http_get(page, timeout=90).decode("utf-8", "replace")
        except RuntimeError:
            continue
        links = [url for url in _xlsx_links(html) if "/severity/" in url.lower()]
        if not links:
            continue
        links.sort(key=_severity_sort_key, reverse=True)
        url = links[0]
        return url, _filename(url)

    # Fallback: HDX package (same Excel releases).
    payload = json.loads(_http_get(HDX_SEVERITY_PACKAGE, timeout=90).decode("utf-8"))
    resources = (payload.get("result") or {}).get("resources") or []
    xlsx = [
        row
        for row in resources
        if str(row.get("format") or "").lower() in {"xlsx", "xls"}
        or str(row.get("url") or "").lower().endswith(".xlsx")
    ]
    if not xlsx:
        raise RuntimeError("No INFORM Severity Excel found on DRMCK or HDX")
    xlsx.sort(key=lambda row: _severity_sort_key(str(row.get("name") or row.get("url") or "")), reverse=True)
    url = str(xlsx[0]["url"])
    return url, str(xlsx[0].get("name") or _filename(url))


def _severity_sort_key(text: str) -> int:
    match = re.search(r"(20\d{2})(0[1-9]|1[0-2])", text or "")
    return int(match.group(1) + match.group(2)) if match else 0


def _climate_link_rank(url: str) -> tuple[int, str]:
    """Prefer full 'all scenarios' workbook over brochure extract."""
    text = unquote(url).lower()
    if "all scenarios" in text or "all_scenarios" in text:
        return (0, text)
    if "cc risk" in text or "climate change risk" in text:
        return (1, text)
    if "brochure data" in text:
        return (2, text)
    if "climate" in text or re.search(r"(^|/)inform[_% ]?cc", text):
        return (3, text)
    return (9, text)


def discover_climate_xlsx_url() -> tuple[str, str]:
    pages = (
        CLIMATE_PAGE,
        f"{DRMCK_BASE}/inform-index/INFORM-Climate-Change/Results-and-data",
        PUBLICATIONS_PAGE,
    )
    candidates: list[str] = []
    for page in pages:
        try:
            html = _http_get(page, timeout=90).decode("utf-8", "replace")
        except RuntimeError:
            continue
        candidates.extend(_xlsx_links(html))

    # Stable Portal path if the HTML scrape is empty / rate-limited.
    candidates.append(
        f"{DRMCK_BASE}/inform-index/portals/0/InfoRM/2022/INFORM%20CC%20Risk%20Index%20all%20scenarios.xlsx"
    )
    candidates.append(
        f"{DRMCK_BASE}/inform-index/Portals/0/InfoRM/2022/INFORM%20CC%20Brochure%20data.xlsx"
    )

    ranked = sorted(set(candidates), key=_climate_link_rank)
    preferred = [url for url in ranked if _climate_link_rank(url)[0] < 9]
    if not preferred:
        raise RuntimeError("No INFORM Climate Change Excel link found")
    url = preferred[0]
    return url, unquote(_filename(url))


def _norm_header(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _norm_risk_class(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip().lower().replace("-", " ").replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    mapping = {
        "very low": "very_low",
        "low": "low",
        "medium": "medium",
        "high": "high",
        "very high": "very_high",
    }
    if text in mapping:
        return mapping[text]
    return str(value).strip()


def _sheet_rows(raw: bytes, sheet_predicate) -> list[tuple[Any, ...]]:
    wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    chosen = None
    for name in wb.sheetnames:
        if sheet_predicate(name):
            chosen = name
            break
    if chosen is None:
        raise RuntimeError(f"Excel sheet not found among: {wb.sheetnames}")
    return list(wb[chosen].iter_rows(values_only=True))


def _find_header_row(rows: list[tuple[Any, ...]], *required: str) -> tuple[int, dict[str, int]]:
    needed = {_norm_header(name) for name in required}
    for index, row in enumerate(rows[:30]):
        headers = {_norm_header(cell): i for i, cell in enumerate(row or ()) if cell not in (None, "")}
        if needed.issubset(headers):
            return index, headers
    raise RuntimeError(f"Could not find header row with columns {sorted(needed)}")


def parse_inform_risk_xlsx(raw: bytes) -> tuple[dict[str, float], dict[str, str], str | None]:
    rows = _sheet_rows(raw, lambda name: name.lower().startswith("inform risk"))
    header_i, headers = _find_header_row(rows, "iso3")
    iso_i = headers["iso3"]
    score_i = next((headers[k] for k in headers if k in {"inform_risk", "risk"} or "inform_risk" in k), None)
    class_i = next((headers[k] for k in headers if "risk_class" in k or k == "class"), None)
    scores: dict[str, float] = {}
    classes: dict[str, str] = {}
    for row in rows[header_i + 1 :]:
        if not row or iso_i >= len(row):
            continue
        iso3 = str(row[iso_i] or "").strip().upper()
        if len(iso3) != 3 or not iso3.isalpha():
            continue
        if score_i is not None and score_i < len(row) and row[score_i] not in (None, ""):
            try:
                score = float(row[score_i])
            except (TypeError, ValueError):
                score = None
            else:
                scores[iso3] = score
                if class_i is None:
                    classes[iso3] = inform_class(score)
        if class_i is not None and class_i < len(row):
            label = _norm_risk_class(row[class_i])
            if label and not str(row[class_i]).replace(".", "", 1).isdigit():
                classes[iso3] = label
            elif iso3 in scores:
                classes[iso3] = inform_class(scores[iso3])
    edition = None
    about = _sheet_rows(raw, lambda name: name.lower() == "about")
    for row in about[:8]:
        cell = next((c for c in (row or ()) if c not in (None, "")), None)
        if cell and re.search(r"\d{4}", str(cell)):
            edition = str(cell).strip()
            break
    return scores, classes, edition


def parse_inform_severity_xlsx(raw: bytes) -> tuple[dict[str, str], str | None]:
    rows = _sheet_rows(
        raw,
        lambda name: "severity" in name.lower() and "country" in name.lower(),
    )
    header_i, headers = _find_header_row(rows, "iso3")
    iso_i = headers["iso3"]
    # Prefer textual category (Very Low–Very High); fall back to numeric 1–5.
    text_keys = [k for k in headers if "severity" in k and "category" in k]
    score_i = next((headers[k] for k in headers if k in {"inform_severity_index", "inform_severity"}), None)
    cat_text_i = None
    cat_num_i = None
    for key in text_keys:
        # Duplicate header names collapse in dict — scan raw header row instead.
        pass
    header_row = rows[header_i]
    for idx, cell in enumerate(header_row or ()):
        label = _norm_header(cell)
        if label == "inform_severity_category":
            sample_vals = [rows[j][idx] for j in range(header_i + 1, min(header_i + 8, len(rows))) if rows[j] and idx < len(rows[j])]
            if any(isinstance(v, str) and not str(v).replace(".", "", 1).isdigit() for v in sample_vals):
                cat_text_i = idx
            elif cat_num_i is None:
                cat_num_i = idx
        if label in {"inform_severity_index", "inform_severity"} and score_i is None:
            score_i = idx

    best: dict[str, tuple[float, str]] = {}
    for row in rows[header_i + 1 :]:
        if not row or iso_i >= len(row):
            continue
        iso3 = str(row[iso_i] or "").strip().upper()
        if len(iso3) != 3 or not iso3.isalpha():
            continue
        label = None
        rank = 0.0
        if cat_text_i is not None and cat_text_i < len(row) and isinstance(row[cat_text_i], str):
            label = str(row[cat_text_i]).strip()
            rank = {"very low": 1, "low": 2, "medium": 3, "high": 4, "very high": 5}.get(label.lower(), 0)
        elif cat_num_i is not None and cat_num_i < len(row) and row[cat_num_i] not in (None, ""):
            try:
                rank = float(row[cat_num_i])
            except (TypeError, ValueError):
                rank = 0.0
            label = str(row[cat_num_i]).strip()
        if score_i is not None and score_i < len(row) and row[score_i] not in (None, ""):
            try:
                rank = max(rank, float(row[score_i]))
            except (TypeError, ValueError):
                pass
            if not label:
                label = str(row[score_i]).strip()
        if not label:
            continue
        current = best.get(iso3)
        if current is None or rank >= current[0]:
            best[iso3] = (rank, label)

    edition = None
    title = rows[0][0] if rows and rows[0] else None
    if title:
        edition = str(title).strip()
    return {iso3: label for iso3, (_rank, label) in best.items()}, edition


def parse_inform_climate_xlsx(raw: bytes) -> tuple[dict[str, float], str | None]:
    rows = _sheet_rows(raw, lambda name: "risk components" in name.lower() or name.lower().startswith("inform cc"))
    header_i, headers = _find_header_row(rows, "iso3", "indicatorid", "indicatorscore")
    iso_i = headers["iso3"] if "iso3" in headers else headers.get("iso")
    ind_i = headers["indicatorid"]
    score_i = headers["indicatorscore"]
    year_i = headers.get("year")
    scenario_i = headers.get("scenario")
    if iso_i is None:
        raise RuntimeError("Climate Excel missing Iso3 column")

    values: dict[str, float] = {}
    for row in rows[header_i + 1 :]:
        if not row or max(iso_i, ind_i, score_i) >= len(row):
            continue
        if str(row[ind_i] or "").strip().upper() != "INFORM":
            continue
        year = None
        if year_i is not None and year_i < len(row) and row[year_i] not in (None, ""):
            try:
                year = int(row[year_i])
            except (TypeError, ValueError):
                year = None
        scenario = str(row[scenario_i] or "") if scenario_i is not None and scenario_i < len(row) else ""
        # Baseline current risk (not future RCP scenarios).
        if year not in (None, 2022) and "2022" not in scenario:
            continue
        if "RCP" in scenario.upper():
            continue
        iso3 = str(row[iso_i] or "").strip().upper()
        if len(iso3) != 3 or not iso3.isalpha():
            continue
        try:
            values[iso3] = float(row[score_i])
        except (TypeError, ValueError):
            continue

    edition = None
    try:
        about = _sheet_rows(raw, lambda name: name.lower() == "about")
        for row in about[:8]:
            cell = next((c for c in (row or ()) if c not in (None, "")), None)
            if cell and re.search(r"\d{4}", str(cell)):
                edition = f"INFORM Climate Change {cell}".strip()
                break
    except RuntimeError:
        edition = "INFORM Climate Change"
    return values, edition or "INFORM Climate Change"


def refresh_inform_risk() -> dict[str, Any]:
    url, name = discover_risk_xlsx_url()
    raw = _http_get(url, referer=RISK_PAGE)
    scores, classes, edition = parse_inform_risk_xlsx(raw)
    edition = edition or name
    paths.ensure_dirs()
    payload = {
        "edition": edition,
        "source_url": url,
        "updated_at": _now(),
        "scores": scores,
        "class_by_iso3": classes,
    }
    write_json(paths.GLOBAL_FILES["inform_risk"], payload)
    touch_source(
        "inform_risk",
        row_count=max(len(scores), len(classes)),
        edition=edition,
        source="INFORM DRMCK Excel",
        extra={"source_url": url},
    )
    return {"row_count": max(len(scores), len(classes)), "edition": edition, "source_url": url}


def refresh_inform_severity() -> dict[str, Any]:
    url, name = discover_severity_xlsx_url()
    referer = SEVERITY_PAGE if "drmkc.jrc.ec.europa.eu" in url else "https://data.humdata.org/"
    raw = _http_get(url, referer=referer)
    values, edition = parse_inform_severity_xlsx(raw)
    edition = edition or name
    paths.ensure_dirs()
    payload = {"updated_at": _now(), "source_url": url, "edition": edition, "by_iso3": values}
    write_json(paths.GLOBAL_FILES["inform_severity"], payload)
    touch_source(
        "inform_severity",
        row_count=len(values),
        edition=edition,
        source="INFORM DRMCK/HDX Excel",
        extra={"source_url": url},
    )
    return {"row_count": len(values), "edition": edition, "source_url": url}


def refresh_inform_climate() -> dict[str, Any]:
    url, name = discover_climate_xlsx_url()
    raw = _http_get(url, referer=CLIMATE_PAGE)
    values, edition = parse_inform_climate_xlsx(raw)
    edition = edition or name
    paths.ensure_dirs()
    payload = {"updated_at": _now(), "source_url": url, "edition": edition, "by_iso3": values}
    write_json(paths.GLOBAL_FILES["inform_climate"], payload)
    touch_source(
        "inform_climate",
        row_count=len(values),
        edition=edition,
        source="INFORM DRMCK Excel",
        extra={"source_url": url},
    )
    return {"row_count": len(values), "edition": edition, "source_url": url}
