"""
Fetch and merge FDRS data following the Power Query pipeline:

- 2_FDRS Codebook API (indicator) -> 3_FDRS Codebook API : List IDs (valid KPI codes, exclude IP)
- FDRS - Data API (fdrsdata, reported)
- FDRS - ImputedValue API (fdrsdata or imputed source)
- Country Map (entities/ns or optional Excel URL)
- FDRS: combine reported + imputed, group by (KPI_code, DonCode, year), merge Country Map -> ISO3
- FDRS Data: filter Value not null/empty, add Tokens/BaseKPI, year as text
- NewAgeGroups: age group mapping (embedded base64 table)
- disagg: Sex/AgeGroup from Tokens, merge NewAgeGroups, group by (ISO3, year, BaseKPI) -> JSON values

Output: FDRS Data rows (ISO3, year, KPI_code, Value, BaseKPI, Tokens) and disagg lookup (ISO3, year, KPI_code) -> disagg_data JSON.

---
What's excluded / left out (may need processing later)
------------------------------------------------------
Codebook (fetch_codebook):
  - KPI_Note in: deprecated age range, Official End of Day Rate, World Development Indicators.
  - KPI_Code in: noPeopleReached Development/Health/Services Direct/Indirect (6 codes).
  - UNIT_Code=logical and (KPI_Code contains "age" or "sex") — logical age/sex metadata rows.
  - KPI_Code contains "IsImputedInPublic"; ends with _Public, _ddd, _wgq. (_IsDataNotAvailable and _isDataNotCollected are included for import into data_not_available/not_applicable.)

Valid KPI list (get_valid_kpi_codes):
  - Rows where KPI_Section.Type == "IP" (imputed-only section) — not in valid list (imputed values still fetched separately).

FDRS Data (build_fdrs_data):
  - Rows with Value null or empty.
  - KPI_code containing _D_Tot (direct-total aggregations discarded; we use detailed numbers).
  - KPI_code ending with _Validated (true/false KPI level status; excluded as "KPI level status").
  - KPI_code ending with _IP, _Public, _ddd, _wgq. (_IsDataNotAvailable and _isDataNotCollected are included and mapped to data_not_available / not_applicable in import.)
  - Main value: for base KPI_Climate, the CPD row (KPI_Climate_CPD) is the total when there is no _Tot; BaseKPI stays e.g. KPI_Climate (see import _pick_total_row_for_base).

Disagg (build_disagg):
  - Rows without both sex and age in KPI_code tokens.
  - Age groups not in NewAgeGroups mapping (original FDRS band has no mapped "new" band).

Main value (ready-to-import):
  - Only aggregate Tot row (base_kpi + "_Tot") supplies the main value; Tot_M, Tot_F and all variant rows are not used for the main field (they feed disagg_data or are dropped for value).
"""

import base64
import hashlib
import json
import logging
import os
import re
import zlib
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default directory for imputed values cache (under Backoffice/instance when running from app).
def _default_imputed_cache_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "instance", "fdrs_imputed_cache")

# Data API (data-api.ifrc.org)
DEFAULT_DATA_API_BASE = "https://data-api.ifrc.org"

# When years aren't explicitly provided, keep a conservative default window.
# This should match the importer/UI expectation (see import_fdrs_form_data.py help text).
DEFAULT_FDRS_YEARS_START = 2010
DEFAULT_FDRS_YEARS_END = 2024  # inclusive

# KPI codes that use the full code as BaseKPI (indicator bank uses full code, not first-two-tokens)
# KPI_pr_sex and KPI_sg_sex are questions linked directly to form_items (no indicator bank)
_BASE_KPI_FULL_CODES = frozenset({
    "KPI_IncomeLC_CHF", "KPI_expenditureLC_CHF",
    "KPI_pr_sex", "KPI_sg_sex",
})

# NewAgeGroups: AgeGroup -> New (from Power Query base64 compressed JSON)
_NEW_AGE_GROUPS_B64 = (
    "XY1LCoAwDETvknULSf89hQcoZVaCa/H+mFaE6ibJe0yY1sgzfCVDUmyo1E3TC+5r+BHRSp4cGXEKxuTACP+PqKxjQGKkNb5dx34qP3uYzMhrQjy0amlMELdy4Tfdbw=="
)


def _decode_new_age_groups() -> Dict[str, str]:
    """Decode NewAgeGroups table (AgeGroup -> New) from Power Query base64."""
    out = {}
    try:
        raw = base64.b64decode(_NEW_AGE_GROUPS_B64)
        dec = zlib.decompress(raw, -zlib.MAX_WBITS)
        data = json.loads(dec.decode("utf-8"))
        for row in data if isinstance(data, list) else []:
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                out[str(row[0]).strip()] = str(row[1]).strip()
    except Exception as e:
        logger.debug("NewAgeGroups decode failed: %s", e)
    return out


def _redact_url(url: str) -> str:
    """Redact sensitive query params (e.g. apiKey) from URLs for logs/errors."""
    try:
        parts = urllib.parse.urlsplit(url)
        if not parts.query:
            return url
        items = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        redacted = []
        for k, v in items:
            if k.lower() in ("apikey", "api_key", "token", "access_token", "key"):
                redacted.append((k, "REDACTED"))
            else:
                redacted.append((k, v))
        query = urllib.parse.urlencode(redacted, doseq=True)
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
    except Exception as e:
        logger.debug("URL redaction failed: %s", e)
        return url


def _get(
    url: str,
    api_key: Optional[str] = None,
    timeout: int = 120,
    headers: Optional[Dict[str, str]] = None,
) -> Any:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if api_key and not (headers and "Authorization" in headers):
        req.add_header(
            "Authorization",
            api_key if api_key.startswith("Bearer ") else f"Bearer {api_key}",
        )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        text = raw.decode("utf-8", errors="replace")
        return json.loads(text) if text else None
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body_bytes = e.read()  # type: ignore[attr-defined]
            body = body_bytes.decode("utf-8", errors="replace") if body_bytes else ""
        except Exception as e:
            logger.debug("Error reading HTTP error body: %s", e)
            body = ""
        reason = getattr(e, "reason", "")
        msg = f"HTTP {e.code} {reason} for {_redact_url(url)}"
        if body:
            msg += f": {body[:2000]}"
        raise RuntimeError(msg) from e
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        raise RuntimeError(f"Request failed for {_redact_url(url)}: {reason}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON from {_redact_url(url)}") from e


# ---------- Exclusion summary (what's left out) ----------


def new_exclusion_summary() -> Dict[str, Any]:
    """Return an empty exclusion summary dict for the pipeline to fill."""
    return {
        "codebook": [],           # list of {"KPI_Code": str, "reason": str}
        "valid_kpi_excluded_ip": [],  # list of KPI_Code (section type IP)
        "fdrs_data": {"count_by_reason": {}, "total_excluded": 0},
        "disagg": {"no_sex_or_age": 0, "age_not_in_mapping": 0, "age_groups_not_in_mapping": []},
        "ready_to_import": {"no_assignment": [], "no_indicator": [], "no_form_item": []},
    }


def fetch_codebook(
    base_url: str = DEFAULT_DATA_API_BASE,
    api_key: Optional[str] = None,
    exclusion_summary: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    GET /api/indicator. Apply Power Query filters: exclude KPI_Note list,
    exclude KPI_Code list, split KPI_Note by " - " -> KPI_Section, KPI_Section.Type.
    Filter: keep when UNIT_Code <> "logical" or KPI_Code has neither "age" nor "sex"; not IsImputedInPublic; not _Public; not _ddd; not _wgq. (_IsDataNotAvailable and _isDataNotCollected are kept.)
    """
    url = f"{base_url.rstrip('/')}/api/indicator"
    if api_key:
        url += f"?apiKey={urllib.parse.quote(api_key)}"
    data = _get(url, api_key=None)
    rows = data if isinstance(data, list) else []

    exclude_notes = (
        "KPI age range deprecated from 31st Dec 2016",
        "Official End of Day Rate, 31st Dec 2016",
        "World Development Indicators databank",
    )
    exclude_codes = (
        "KPI_noPeopleReachedDevelopmentDirect",
        "KPI_noPeopleReachedDevelopmentIndirect",
        "KPI_noPeopleReachedHealthDirect",
        "KPI_noPeopleReachedHealthIndirect",
        "KPI_noPeopleReachedServicesDirect",
        "KPI_noPeopleReachedServicesIndirect",
    )

    out = []
    codebook_excluded = (exclusion_summary or {}).get("codebook")
    if codebook_excluded is not None and not isinstance(codebook_excluded, list):
        codebook_excluded = None

    for r in rows:
        if not isinstance(r, dict):
            continue
        note = (r.get("KPI_Note") or "").strip()
        code = (r.get("KPI_Code") or r.get("KpiCode") or "").strip()
        if note in exclude_notes:
            if codebook_excluded is not None:
                codebook_excluded.append({"KPI_Code": code, "reason": "KPI_Note excluded"})
            continue
        if code in exclude_codes:
            if codebook_excluded is not None:
                codebook_excluded.append({"KPI_Code": code, "reason": "KPI_Code in exclude list"})
            continue
        unit = (r.get("UNIT_Code") or r.get("UnitCode") or "").strip()
        code_lower = (code or "").lower()
        if unit == "logical" and ("age" in code_lower or "sex" in code_lower):
            if codebook_excluded is not None:
                codebook_excluded.append({"KPI_Code": code, "reason": "UNIT_Code=logical and (age or sex) in KPI_Code"})
            continue
        if "IsImputedInPublic" in (code or ""):
            if codebook_excluded is not None:
                codebook_excluded.append({"KPI_Code": code, "reason": "IsImputedInPublic"})
            continue
        if (code or "").endswith("_Public"):
            if codebook_excluded is not None:
                codebook_excluded.append({"KPI_Code": code, "reason": "KPI_Code ends with _Public"})
            continue
        if (code or "").endswith("_ddd"):
            if codebook_excluded is not None:
                codebook_excluded.append({"KPI_Code": code, "reason": "KPI_Code ends with _ddd"})
            continue
        # _isDataNotCollected and _IsDataNotAvailable are included; import maps them to not_applicable / data_not_available
        if (code or "").endswith("_wgq"):
            if codebook_excluded is not None:
                codebook_excluded.append({"KPI_Code": code, "reason": "KPI_Code ends with _wgq"})
            continue

        section_full = note
        section = section_type = ""
        if " - " in section_full:
            parts = section_full.split(" - ", 1)
            section = (parts[0] or "").strip()
            section_type = (parts[1] or "").strip()
        else:
            section = section_full.strip()

        out.append({
            "KPI_Code": code,
            "KPI_Name": r.get("KPI_Name") or r.get("KpiName") or "",
            "KPI_Section": section,
            "KPI_Section.Type": section_type,
            "UNIT_Code": unit,
        })
    return out


def get_valid_kpi_codes(
    base_url: str = DEFAULT_DATA_API_BASE,
    api_key: Optional[str] = None,
    codebook: Optional[List[Dict[str, Any]]] = None,
    exclusion_summary: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """3_FDRS Codebook API : List IDs — KPI_Code where KPI_Section.Type <> 'IP'."""
    if codebook is None:
        codebook = fetch_codebook(base_url=base_url, api_key=api_key, exclusion_summary=exclusion_summary)
    excluded_ip = (exclusion_summary or {}).get("valid_kpi_excluded_ip") if exclusion_summary else None
    if excluded_ip is not None and not isinstance(excluded_ip, list):
        excluded_ip = None
    out = []
    for r in codebook:
        kpi = r["KPI_Code"]
        if (r.get("KPI_Section.Type") or "").strip().upper() == "IP":
            if excluded_ip is not None:
                excluded_ip.append(kpi)
            continue
        out.append(kpi)
    return out


# ---------- FDRS - Data API / FDRS - ImputedValue API ----------


def _fdrsdata_rows(
    raw_list: List[Dict],
    valid_kpi_codes: Optional[List[str]] = None,
    source_type: str = "Reported",
) -> List[Dict[str, Any]]:
    """
    Convert fdrsdata API response to rows: DonCode, year, KPI_code, value, State.
    Inner-join filter by valid KPIs (3_FDRS Codebook List IDs). value = first of
    IntValue, BoolValue, StrValue, DateValue; year kept as int for merge; value as text.
    """
    valid_set = set(valid_kpi_codes) if valid_kpi_codes else None
    out = []
    for row in raw_list or []:
        if not isinstance(row, dict):
            continue
        kpi = (row.get("KPICode") or row.get("KPI_code") or "").strip()
        if valid_set is not None and kpi not in valid_set:
            continue
        don_code = (row.get("DonCode") or row.get("id") or "").strip()
        year_raw = row.get("Year") or row.get("year")
        if year_raw is None:
            continue
        state = row.get("State")
        int_v = row.get("IntValue")
        bool_v = row.get("BoolValue")
        str_v = row.get("StrValue")
        date_v = row.get("DateValue")
        value = None
        for v in (int_v, bool_v, str_v, date_v):
            if v is not None:
                value = v
                break
        # Keep year as int (Power Query #date(_,1,1)); value as text or null
        if isinstance(year_raw, (int, float)):
            try:
                year_out = int(year_raw)
            except (TypeError, ValueError):
                year_out = year_raw
        else:
            year_out = year_raw
        out.append({
            "DonCode": don_code,
            "year": year_out,
            "KPI_code": kpi,
            "value": None if value is None else str(value),
            "State": state,
            "SourceType": source_type,
        })
    return out


def fetch_fdrsdata(
    base_url: str = DEFAULT_DATA_API_BASE,
    api_key: Optional[str] = None,
    years: Optional[List[int]] = None,
    valid_kpi_codes: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    FDRS - Data API: GET /api/fdrsdata with Query: year, apiKey, force, minstatus, showunpublished.
    Expand DonCode, Year, KPICode->KPI_code, IntValue, State, BoolValue, DateValue, StrValue;
    inner-join with ValidKPIs (3_FDRS List IDs); value = first of Int/Bool/Str/Date; output as text.
    """
    if years is None:
        years = list(range(DEFAULT_FDRS_YEARS_START, DEFAULT_FDRS_YEARS_END + 1))
    years_str = ",".join(str(y) for y in years)
    params = {
        "year": years_str,
        "force": "true",
        "minstatus": "100",
        "showunpublished": "true",
    }
    if api_key:
        params["apiKey"] = api_key
    url = f"{base_url.rstrip('/')}/api/fdrsdata?{urllib.parse.urlencode(params)}"
    data = _get(url, api_key=None)
    raw = data if isinstance(data, list) else []
    if valid_kpi_codes is None:
        valid_kpi_codes = get_valid_kpi_codes(base_url=base_url, api_key=api_key)
    return _fdrsdata_rows(raw, valid_kpi_codes=valid_kpi_codes, source_type="Reported")


def fetch_imputed_from_kpi_api(
    base_url: str = DEFAULT_DATA_API_BASE,
    api_key: Optional[str] = None,
    years: Optional[List[int]] = None,
    valid_kpi_codes: Optional[List[str]] = None,
    timeout_per_request: int = 30,
    progress_hook: Optional[Callable[[int, int, str, int], None]] = None,
) -> List[Dict[str, Any]]:
    """
    FDRS - ImputedValue API: GET /api/KpiImputedValue?kpicode=X&year=Y&apikey=KEY
    per (KPI, year) for KPIs that contain "_IP". Response: list of {doncode, value, source}.
    KPI_code in output has "_IP" removed for joining with reported data.
    """
    if years is None:
        years = list(range(DEFAULT_FDRS_YEARS_START, DEFAULT_FDRS_YEARS_END + 1))
    if valid_kpi_codes is None:
        valid_kpi_codes = get_valid_kpi_codes(base_url=base_url, api_key=api_key)
    kpis_with_ip = [k for k in valid_kpi_codes if k and "_IP" in k]
    base = base_url.rstrip("/")
    out = []
    done = 0
    total = max(1, len(kpis_with_ip) * len(years))
    for kpi in kpis_with_ip:
        for yr in years:
            done += 1
            if progress_hook and (done == 1 or done % 100 == 0 or done == total):
                try:
                    progress_hook(done, total, kpi, int(yr))
                except Exception as e:
                    logger.debug("progress_hook failed: %s", e)
            params = {"kpicode": kpi, "year": str(yr)}
            if api_key:
                params["apikey"] = api_key
            url = f"{base}/api/KpiImputedValue?{urllib.parse.urlencode(params)}"
            try:
                data = _get(url, api_key=None, timeout=timeout_per_request)
            except Exception as e:
                logger.debug("_get failed for kpi=%s yr=%s: %s", kpi, yr, e)
                continue
            rows = data if isinstance(data, list) else []
            kpi_clean = (kpi or "").replace("_IP", "")
            for r in rows:
                if not isinstance(r, dict):
                    continue
                don = (r.get("doncode") or r.get("DonCode") or "").strip()
                if not don:
                    continue
                val = r.get("value")
                out.append({
                    "DonCode": don,
                    "year": yr,
                    "KPI_code": kpi_clean,
                    "value": str(val) if val is not None else None,
                    "State": None,
                    "SourceType": "Imputed",
                })
    return out


# ---------- Imputed cache (file-based) ----------


def _imputed_cache_key(base_url: str, years: List[int]) -> str:
    """Stable cache key for (base_url, years)."""
    years_str = ",".join(str(y) for y in sorted(years)) if years else ""
    payload = f"{base_url.rstrip('/')}|{years_str}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _imputed_cache_path(cache_dir: str, base_url: str, years: List[int]) -> str:
    return os.path.join(cache_dir, f"imputed_{_imputed_cache_key(base_url, years)}.json")


def load_imputed_cache(
    cache_dir: str,
    base_url: str,
    years: List[int],
) -> Optional[List[Dict[str, Any]]]:
    """
    Load imputed rows from cache if present and valid.
    Returns None on miss or error (caller should fetch from API).
    """
    path = _imputed_cache_path(cache_dir, base_url, years)
    try:
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return None
        return data
    except Exception as e:
        logger.debug("FDRS data fetch failed: %s", e)
        return None


def save_imputed_cache(
    cache_dir: str,
    base_url: str,
    years: List[int],
    data: List[Dict[str, Any]],
) -> None:
    """Save imputed rows to cache. Creates cache_dir if needed."""
    path = _imputed_cache_path(cache_dir, base_url, years)
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        logger.debug("Imputed cache save failed for %s: %s", path, e)


# ---------- Country Map ----------


def fetch_country_map(
    base_url: str = DEFAULT_DATA_API_BASE,
    api_key: Optional[str] = None,
) -> Dict[str, str]:
    """Country map: DonCode (KPI_DON_code) -> ISO3. Uses GET /api/entities/ns (or optional Excel URL from env)."""
    url = f"{base_url.rstrip('/')}/api/entities/ns"
    if api_key:
        url += f"?apiKey={urllib.parse.quote(api_key)}"
    data = _get(url, api_key=None)
    rows = data if isinstance(data, list) else []
    out = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        don = (r.get("KPI_DON_code") or r.get("DonCode") or "").strip()
        if not don:
            continue
        iso3 = (r.get("iso_3") or r.get("ISO3") or "").strip()
        out[don] = iso3
    return out


# ---------- FDRS (combined) ----------


def build_fdrs_combined(
    reported_rows: List[Dict],
    imputed_rows: List[Dict],
    country_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    Combine Reported + Imputed: group by (KPI_code, DonCode, year).
    ReportedValue = first value where SourceType=Reported; ImputedValue = first where SourceType=Imputed.
    ValueStatus, Value (imputed wins; else published reported when State=500).
    Merge Country Map: DonCode -> ISO3.
    """
    key_to_reported = {}
    key_to_imputed = {}
    key_to_state = {}
    for r in reported_rows:
        key = (r.get("KPI_code") or "", r.get("DonCode") or "", r.get("year"))
        key_to_reported[key] = r.get("value")
        key_to_state[key] = r.get("State")
    for r in imputed_rows:
        key = (r.get("KPI_code") or "", r.get("DonCode") or "", r.get("year"))
        key_to_imputed[key] = r.get("value")

    all_keys = set(key_to_reported) | set(key_to_imputed)
    out = []
    for (kpi, don, year) in all_keys:
        key = (kpi, don, year)
        reported_val = key_to_reported.get(key)
        imputed_val = key_to_imputed.get(key)
        state = key_to_state.get(key)
        if imputed_val is not None:
            value_status = "Imputed"
            value = imputed_val
        elif reported_val is not None and state == 500:
            value_status = "Published Reported"
            value = reported_val
        elif reported_val is not None:
            value_status = "Unpublished Reported"
            value = None
        else:
            value_status = "Missing"
            value = None
        iso3 = country_map.get(don, "")
        out.append({
            "ISO3": iso3,
            "DonCode": don,
            "year": year,
            "KPI_code": kpi,
            "Value": value,
            "ValueStatus": value_status,
            "State": state,
        })
    return out


# ---------- FDRS Data ----------


def build_fdrs_data(
    fdrs_combined: List[Dict],
    exclusion_summary: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    From FDRS combined: exclude KPIs ending with _IP, _Public, _ddd, _wgq (include _IsDataNotAvailable and _isDataNotCollected for import); filter Value not null/empty;
    select ISO3, year, KPI_code, Value. Add Tokens, BaseKPI, year as text.
    """
    out = []
    fdrs_excl = (exclusion_summary or {}).get("fdrs_data")
    count_by_reason = fdrs_excl.get("count_by_reason", {}) if isinstance(fdrs_excl, dict) else {}
    total_excluded = 0

    for r in fdrs_combined:
        include_row, reason, year_text, tokens, base_kpi = _classify_fdrs_combined_row(r)
        if not include_row:
            if fdrs_excl is not None:
                count_by_reason[reason] = count_by_reason.get(reason, 0) + 1
                total_excluded += 1
            continue
        iso3 = (r.get("ISO3") or "").strip()
        kpi = (r.get("KPI_code") or "").strip()
        val = r.get("Value")
        out.append({
            "ISO3": iso3,
            "year": year_text,
            "KPI_code": kpi,
            "Value": str(val).strip(),
            "Tokens": tokens,
            "BaseKPI": base_kpi,
        })
    if fdrs_excl is not None and isinstance(fdrs_excl, dict):
        fdrs_excl["count_by_reason"] = count_by_reason
        fdrs_excl["total_excluded"] = total_excluded
    return out


def _classify_fdrs_combined_row(
    row: Dict[str, Any],
) -> Tuple[bool, str, str, List[str], str]:
    """
    Classify one combined FDRS row for FDRS Data stage filtering.
    Returns:
      (included_in_fdrs_data, reason, year_text, tokens, base_kpi)
    """
    val = row.get("Value")
    kpi = (row.get("KPI_code") or "").strip()
    reason = ""
    # Allow null/empty value for data-availability KPIs (import maps them to data_not_available/not_applicable)
    if not (kpi.endswith("_IsDataNotAvailable") or kpi.endswith("_isDataNotCollected")):
        if val is None or (isinstance(val, str) and not val.strip()):
            reason = "null_or_empty_value"
    if reason == "" and "_D_Tot" in kpi:
        # D_Tot rows are direct-total aggregations; we use detailed numbers and discard these.
        reason = "D_Tot_aggregation_discarded"
    elif reason == "" and kpi.endswith("_Validated"):
        # _Validated KPIs are true/false status flags (KPI level status), not indicator values.
        reason = "KPI_level_status"
    elif reason == "" and kpi.endswith("_IP"):
        reason = "ends_with_IP"
    elif reason == "" and kpi.endswith("_Public"):
        reason = "ends_with_Public"
    elif reason == "" and kpi.endswith("_ddd"):
        reason = "ends_with_ddd"
    # _isDataNotCollected and _IsDataNotAvailable are included; import maps to not_applicable / data_not_available
    elif reason == "" and kpi.endswith("_wgq"):
        reason = "ends_with_wgq"
    year = row.get("year")
    year_text = ""
    if year is not None:
        if hasattr(year, "year"):
            year_text = str(year.year)
        elif isinstance(year, str) and len(year) >= 4:
            year_text = year[:4]
        else:
            year_text = str(year)
    tokens = kpi.split("_") if kpi else []
    base_kpi = "_".join(tokens[:2]) if len(tokens) >= 2 else kpi
    # Keep full code as BaseKPI for specific KPIs (indicator bank uses full code)
    for full in _BASE_KPI_FULL_CODES:
        if kpi == full or kpi.startswith(full + "_"):
            base_kpi = full
            break
    return (reason == ""), reason, year_text, tokens, base_kpi


def build_fdrs_snapshot_rows(
    fdrs_combined: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Build a raw FDRS snapshot before ready-to-import transformation.
    Keeps original KPI_code and value fields and flags FDRS Data-stage filtering.
    """
    out: List[Dict[str, Any]] = []
    for r in fdrs_combined:
        include, reason, year_text, _, base_kpi = _classify_fdrs_combined_row(r)
        out.append({
            "ISO3": (r.get("ISO3") or "").strip(),
            "DonCode": (r.get("DonCode") or "").strip(),
            "year": year_text,
            "KPI_code": (r.get("KPI_code") or "").strip(),
            "BaseKPI": base_kpi,
            "Value": r.get("Value"),
            "ValueStatus": r.get("ValueStatus"),
            "State": r.get("State"),
            "in_fdrs_data_stage": "yes" if include else "no",
            "fdrs_data_filter_reason": reason,
        })
    return out


# ---------- disagg ----------


def _sex_from_tokens(tokens: List[str]) -> Optional[str]:
    """Return sex slug matching entry form: male, female, non_binary, unknown (system uses Unknown, not Other)."""
    if "UnknownSex" in tokens:
        return "unknown"
    if "OtherSex" in tokens:
        return "unknown"  # FDRS "Other" sex -> system "unknown"
    if "NonBinary" in tokens:
        return "non_binary"
    if "M" in tokens:
        return "male"
    if "F" in tokens:
        return "female"
    return None


def _age_group_from_tokens(tokens: List[str]) -> Optional[str]:
    try:
        p = tokens.index("age")
    except ValueError:
        return None
    if p >= len(tokens) - 1:
        return None
    return "_".join(tokens[p + 1:])


def _normalize_age_slug(age_group: str) -> str:
    """Normalize age slug to match entry form: lower + replace non-alphanumeric with _; FDRS 'Other' age -> 'unknown' (system uses Unknown)."""
    if not age_group:
        return age_group
    s = age_group.strip().lower()
    s = re.sub(r"[^a-z0-9_]", "_", s)
    if s == "80":
        return "80_"
    if s == "other":
        return "unknown"  # FDRS "Other" age -> system "unknown"
    return s


def build_disagg(
    fdrs_data: List[Dict],
    new_age_groups: Optional[Dict[str, str]] = None,
    exclusion_summary: Optional[Dict[str, Any]] = None,
) -> Dict[Tuple[str, str, str], str]:
    """
    Build disagg_data to match entry form / FormData.set_disaggregated_data:
    { "mode": "sex_age", "values": { "direct": { "male_5_17": n, "male_unknown": n, "female_unknown": n, "non_binary_50_": n, "non_binary_unknown": n, "unknown_unknown": n, ... }, "indirect": n } }.
    Direct: only rows that have both Sex and AgeGroup and (optionally) map to a valid NewAgeGroup.
    Indirect: rows with KPI_code == BaseKPI + "_I" are stored in values.indirect.
    Keys use sex_slug (male, female, non_binary, unknown) and age_slug (5_17, 50_, unknown, etc.). FDRS Other/OtherSex mapped to unknown to match system.
    When multiple original age groups map to the same new group, values are summed.
    """
    if new_age_groups is None:
        new_age_groups = _decode_new_age_groups()
    disagg_excl = (exclusion_summary or {}).get("disagg")
    no_sex_age = 0
    age_not_mapped = 0
    age_groups_not_mapped = set()

    rows_with_sex_age = []
    for r in fdrs_data:
        tokens = r.get("Tokens") or []
        sex = _sex_from_tokens(tokens)
        age_group = _age_group_from_tokens(tokens)
        if not sex or not age_group:
            if disagg_excl is not None:
                no_sex_age += 1
            continue
        if new_age_groups and age_group not in new_age_groups:
            if disagg_excl is not None:
                age_not_mapped += 1
                age_groups_not_mapped.add(age_group)
            continue
        # Use the NEW age group from mapping for the key (form expects new bands, not original FDRS bands)
        new_age = new_age_groups.get(age_group, age_group)
        age_slug = _normalize_age_slug(new_age)
        rows_with_sex_age.append({
            "ISO3": r.get("ISO3") or "",
            "year": r.get("year") or "",
            "BaseKPI": r.get("BaseKPI") or "",
            "sex": sex,
            "age_slug": age_slug,
            "Value": r.get("Value"),
        })
    from collections import defaultdict
    group: Dict[Tuple[str, str, str], List[Tuple[str, Any]]] = defaultdict(list)
    for r in rows_with_sex_age:
        key = (r["ISO3"], r["year"], r["BaseKPI"])
        group[key].append((f"{r['sex']}_{r['age_slug']}", r["Value"]))
    # KPIs ending with _I are the indirect value; add to disagg_data.values.indirect
    indirect_by_key: Dict[Tuple[str, str, str], Any] = {}
    for r in fdrs_data:
        kpi = (r.get("KPI_code") or "").strip()
        base = (r.get("BaseKPI") or "").strip()
        if not base or not kpi.endswith("_I") or kpi != base + "_I":
            continue
        key = (r.get("ISO3") or "", r.get("year") or "", base)
        val = r.get("Value")
        if val is not None and str(val).strip() != "":
            try:
                indirect_by_key[key] = int(float(val))
            except (TypeError, ValueError):
                indirect_by_key[key] = val
    out = {}
    for key, pairs in group.items():
        direct = {}
        for k, v in pairs:
            if k and v is not None:
                try:
                    n = int(float(v))
                    direct[k] = direct.get(k, 0) + n  # sum when multiple originals map to same new group
                except (TypeError, ValueError):
                    direct[k] = v
        if direct:
            payload = {"mode": "sex_age", "values": {"direct": direct, "indirect": indirect_by_key.get(key)}}
            out[key] = json.dumps(payload)
    # Keys that have only indirect (no sex/age rows) still get disagg_data with indirect
    for key, indirect_val in indirect_by_key.items():
        if key not in out:
            payload = {"mode": "total", "values": {"direct": {}, "indirect": indirect_val}}
            out[key] = json.dumps(payload)
    if disagg_excl is not None and isinstance(disagg_excl, dict):
        disagg_excl["no_sex_or_age"] = no_sex_age
        disagg_excl["age_not_in_mapping"] = age_not_mapped
        disagg_excl["age_groups_not_in_mapping"] = sorted(age_groups_not_mapped)
    return out


# ---------- Full pipeline ----------


def build_fdrs_table(
    base_url: str = DEFAULT_DATA_API_BASE,
    api_key: Optional[str] = None,
    years: Optional[List[int]] = None,
    imputed_url: Optional[str] = None,
    imputed_api_key: Optional[str] = None,
    use_imputed_cache: bool = True,
    cache_dir: Optional[str] = None,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    exclusion_summary: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[Tuple[str, str, str], str], Dict[str, Any], List[Dict[str, Any]]]:
    """
    Run the full pipeline: codebook -> valid KPIs -> Data API + Imputed API -> Country Map
    -> FDRS combined -> FDRS Data -> disagg.
    Returns (fdrs_data_rows, disagg_by_key, exclusion_summary, fdrs_snapshot_rows).
    If exclusion_summary is None, a new one is created and returned (describes what was excluded at each stage).
    When imputed_url is not set, imputed values are fetched per (KPI, year) from the API; this can be slow.
    use_imputed_cache=True (default) uses a file cache when available; use_imputed_cache=False forces a fresh fetch.
    cache_dir is the directory for the imputed cache; when None, _default_imputed_cache_dir() is used.
    """
    if years is None:
        years = list(range(DEFAULT_FDRS_YEARS_START, DEFAULT_FDRS_YEARS_END + 1))
    if exclusion_summary is None:
        exclusion_summary = new_exclusion_summary()

    def _progress(message: str, percent: Optional[float] = None, *, current: Optional[int] = None, total: Optional[int] = None) -> None:
        if not progress_cb:
            return
        payload: Dict[str, Any] = {
            "stage": "fetch_fdrs",
            "message": message,
            "percent": percent,
            "current": current,
            "total": total,
        }
        try:
            progress_cb(payload)
        except Exception as e:
            logger.debug("progress_cb failed: %s", e)

    _progress(f"Fetching codebook + valid KPIs ({min(years)}–{max(years)})...", percent=1.5)
    codebook = fetch_codebook(base_url=base_url, api_key=api_key, exclusion_summary=exclusion_summary)
    valid_kpis = get_valid_kpi_codes(
        base_url=base_url, api_key=api_key, codebook=codebook, exclusion_summary=exclusion_summary
    )
    _progress(f"Fetching reported fdrsdata ({len(years)} year(s))...", percent=2.5)
    reported = fetch_fdrsdata(
        base_url=base_url,
        api_key=api_key,
        years=years,
        valid_kpi_codes=valid_kpis,
    )
    imputed = []
    if imputed_url:
        _progress("Fetching imputed values (bulk URL)...", percent=5.5)
        try:
            data = _get(imputed_url, api_key=imputed_api_key)
            raw = data if isinstance(data, list) else (data.get("data") or data.get("rows") or [])
            for r in raw or []:
                if not isinstance(r, dict):
                    continue
                kpi = (r.get("KPI_code") or r.get("KPICode") or "").strip()
                if kpi not in valid_kpis:
                    continue
                don = (r.get("DonCode") or r.get("id.1") or r.get("id") or "").strip()
                yr = r.get("year") or r.get("Year")
                val = r.get("value")
                imputed.append({
                    "DonCode": don,
                    "year": yr,
                    "KPI_code": kpi,
                    "value": str(val) if val is not None else None,
                    "State": None,
                    "SourceType": "Imputed",
                })
        except Exception as e:
            logger.debug("Imputed row append failed: %s", e)
    else:
        _cache_dir = cache_dir if cache_dir is not None else _default_imputed_cache_dir()
        _years_list = list(years) if years else []
        if use_imputed_cache:
            imputed = load_imputed_cache(_cache_dir, base_url, _years_list) or []
            if imputed:
                _progress("Using cached imputed values.", percent=5.5)
            else:
                _progress("Fetching imputed values (KpiImputedValue)...", percent=4.0)

                def _imputed_hook(done: int, total: int, kpi: str, yr: int) -> None:
                    pct = 4.0 + (2.5 * (done / max(1, total)))
                    _progress(f"Fetching imputed values {done}/{total} - {kpi} {yr}", percent=pct, current=done, total=total)

                imputed = fetch_imputed_from_kpi_api(
                    base_url=base_url,
                    api_key=api_key,
                    years=years,
                    valid_kpi_codes=valid_kpis,
                    progress_hook=_imputed_hook if progress_cb else None,
                )
                save_imputed_cache(_cache_dir, base_url, _years_list, imputed)
        else:
            _progress("Fetching imputed values (KpiImputedValue, fresh)...", percent=4.0)

            def _imputed_hook(done: int, total: int, kpi: str, yr: int) -> None:
                pct = 4.0 + (2.5 * (done / max(1, total)))
                _progress(f"Fetching imputed values {done}/{total} - {kpi} {yr}", percent=pct, current=done, total=total)

            imputed = fetch_imputed_from_kpi_api(
                base_url=base_url,
                api_key=api_key,
                years=years,
                valid_kpi_codes=valid_kpis,
                progress_hook=_imputed_hook if progress_cb else None,
            )
            save_imputed_cache(_cache_dir, base_url, _years_list, imputed)
    _progress("Fetching country map...", percent=7.0)
    country_map = fetch_country_map(base_url=base_url, api_key=api_key)
    _progress("Building combined table + disaggregation...", percent=7.5)
    combined = build_fdrs_combined(reported, imputed, country_map)
    fdrs_snapshot_rows = build_fdrs_snapshot_rows(combined)
    fdrs_data = build_fdrs_data(combined, exclusion_summary=exclusion_summary)
    disagg_by_key = build_disagg(fdrs_data, exclusion_summary=exclusion_summary)
    _progress("FDRS fetch complete.", percent=8.0)
    return fdrs_data, disagg_by_key, exclusion_summary, fdrs_snapshot_rows
