"""
Export all FDRS document URLs with HTTP probe status to Excel.

Works in this repo or as a single copied file (no Backoffice app required).

Standalone:
    pip install pandas openpyxl
    python export_fdrs_document_url_status.py --api-key YOUR_KEY

In Backoffice (reads FDRS_DATA_API_KEY from env / .env):
    python scripts/dev/export_fdrs_document_url_status.py
    python scripts/dev/export_fdrs_document_url_status.py --limit 50

On HTTP 403/404, retries once without a trailing _1 / _2 filename suffix
(the API catalog sometimes includes a suffix the file store does not).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MAYBE_BACKOFFICE = os.path.dirname(os.path.dirname(SCRIPT_DIR))
IN_BACKOFFICE = os.path.isdir(os.path.join(_MAYBE_BACKOFFICE, "app")) and os.path.isfile(
    os.path.join(_MAYBE_BACKOFFICE, "config.py")
)
BACKOFFICE_DIR = _MAYBE_BACKOFFICE if IN_BACKOFFICE else None

DEFAULT_BASE = "https://data-api.ifrc.org"
DEFAULT_OUTPUT = (
    os.path.join(BACKOFFICE_DIR, "instance", "fdrs_document_url_status.xlsx")
    if BACKOFFICE_DIR
    else os.path.join(os.getcwd(), "fdrs_document_url_status.xlsx")
)
_DUP_SUFFIX_RE = re.compile(r"_([1-9]\d?)(\.[A-Za-z0-9]+)$")


def _load_api_key(explicit: Optional[str]) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    key = (os.environ.get("FDRS_DATA_API_KEY") or "").strip()
    if key:
        return key
    env_candidates = [
        os.path.join(SCRIPT_DIR, ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]
    if BACKOFFICE_DIR:
        env_candidates.append(os.path.join(BACKOFFICE_DIR, ".env"))
    for env_path in env_candidates:
        if not os.path.isfile(env_path):
            continue
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("FDRS_DATA_API_KEY="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    raise SystemExit(
        "FDRS_DATA_API_KEY is required (--api-key, env, or .env)."
    )


def encode_document_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def url_without_duplicate_suffix(url: str) -> Optional[str]:
    raw = (url or "").strip()
    if not raw:
        return None
    parts = urllib.parse.urlsplit(raw)
    dirname, sep, filename = (parts.path or "").rpartition("/")
    if not filename:
        return None
    new_name, n = _DUP_SUFFIX_RE.subn(r"\2", filename, count=1)
    if n != 1 or new_name == filename:
        return None
    new_path = f"{dirname}{sep}{new_name}" if sep else new_name
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, new_path, parts.query, parts.fragment)
    )


def probe_url(url: str, *, timeout: int = 25) -> Tuple[int, str]:
    """GET with Range bytes=0-0; returns (status_code, detail)."""
    raw = (url or "").strip()
    if not raw:
        return 0, "empty_url"
    enc = encode_document_url(raw)
    req = urllib.request.Request(
        enc,
        headers={"User-Agent": "HumanitarianDatabank-FDRS-url-export/1.0", "Range": "bytes=0-0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ct = (resp.headers.get("Content-Type") or "")[:80]
            return int(resp.status), ct
    except urllib.error.HTTPError as e:
        reason = (getattr(e, "reason", "") or "")[:80]
        return int(e.code), reason
    except Exception as e:
        return -1, type(e).__name__


def _json_get(url: str, *, timeout: int) -> Any:
    req = urllib.request.Request(
        url, headers={"User-Agent": "HumanitarianDatabank-FDRS-url-export/1.0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_country_map(base_url: str, api_key: str) -> Dict[str, str]:
    qs = urllib.parse.urlencode({"apiKey": api_key})
    url = f"{base_url.rstrip('/')}/api/entities/ns?{qs}"
    try:
        data = _json_get(url, timeout=120)
    except Exception as e:
        print(f"Warning: country map failed ({type(e).__name__}); ISO3 may be blank.", flush=True)
        return {}
    rows = data if isinstance(data, list) else []
    out: Dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        don = (row.get("KPI_DON_code") or row.get("DonCode") or "").strip()
        iso3 = (row.get("iso_3") or row.get("ISO3") or "").strip()
        if don:
            out[don] = iso3
    return out


def fetch_fdrs_documents(base_url: str, api_key: str) -> List[Dict[str, Any]]:
    print("Fetching FDRS document catalog...", flush=True)
    qs = urllib.parse.urlencode(
        {"apiKey": api_key, "showunpublished": "true", "force": "true"}
    )
    url = f"{base_url.rstrip('/')}/api/documents?{qs}"
    payload = _json_get(url, timeout=180)
    if not isinstance(payload, list):
        raise SystemExit("Unexpected documents API response (not a list).")
    don_to_iso = _fetch_country_map(base_url, api_key)
    flat: List[Dict[str, Any]] = []
    for ns_block in payload:
        if not isinstance(ns_block, dict):
            continue
        don_code = (ns_block.get("code") or "").strip()
        iso3 = don_to_iso.get(don_code, "")
        for doc in ns_block.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            rec = dict(doc)
            rec["don_code"] = don_code
            rec["iso3"] = iso3
            flat.append(rec)
    print(f"Loaded {len(flat)} documents.", flush=True)
    return flat


def document_is_public(approval_status: Any, public_code: Any) -> bool:
    """FDRS Public 1–3 or ApprovalStatus ``(Public)``. Private 403s are expected."""
    approval = (str(approval_status) if approval_status is not None else "").strip()
    if approval.endswith("(Private)"):
        return False
    if approval.endswith("(Public)"):
        return True
    try:
        code = int(public_code) if public_code is not None and str(public_code).strip() != "" else None
    except (TypeError, ValueError):
        code = None
    return code in (1, 2, 3)


def _probe_row(doc: Dict[str, Any]) -> Dict[str, Any]:
    url = (doc.get("url") or "").strip()
    status, detail = probe_url(url)
    fallback_url = ""
    fallback_http_status: Optional[int] = None
    if status in (403, 404):
        alt = url_without_duplicate_suffix(url)
        if alt:
            fallback_url = alt
            fb_status, fb_detail = probe_url(alt)
            fallback_http_status = fb_status
            if fb_status in (200, 206):
                status, detail = fb_status, fb_detail
    is_public = document_is_public(doc.get("ApprovalStatus"), doc.get("Public"))
    return {
        "don_code": doc.get("don_code") or "",
        "iso3": doc.get("iso3") or "",
        "year": doc.get("year"),
        "year_text": doc.get("YearText") or "",
        "document_type": doc.get("document_type") or "",
        "document_type_id": doc.get("document_typeId"),
        "name": doc.get("name") or "",
        "lang_code": doc.get("LangCode") or "",
        "approval_status": doc.get("ApprovalStatus") or "",
        "public": doc.get("Public"),
        "is_public": is_public,
        "modified_at": doc.get("ModifiedAt") or "",
        "url": url,
        "url_encoded": encode_document_url(url) if url else "",
        "fallback_url": fallback_url,
        "fallback_http_status": fallback_http_status,
        "http_status": status,
        "http_detail": detail,
        "downloadable": status in (200, 206),
    }


def export_url_status_excel(
    *,
    output_path: str,
    api_key: Optional[str] = None,
    base_url: str = DEFAULT_BASE,
    workers: int = 20,
    limit: Optional[int] = None,
) -> str:
    import pandas as pd

    key = _load_api_key(api_key)
    documents = fetch_fdrs_documents(base_url, key)
    if limit is not None:
        documents = documents[: int(limit)]

    total = len(documents)
    if total == 0:
        raise SystemExit("No documents returned from FDRS API.")

    rows: List[Optional[Dict[str, Any]]] = [None] * total
    done = 0
    workers = max(1, min(int(workers), 64))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_probe_row, doc): i for i, doc in enumerate(documents)}
        for fut in as_completed(futures):
            idx = futures[fut]
            rows[idx] = fut.result()
            done += 1
            if done == 1 or done % 250 == 0 or done == total:
                print(f"Probed {done}/{total}...", flush=True)

    assert all(r is not None for r in rows)
    df = pd.DataFrame(rows)  # type: ignore[arg-type]

    def _pct(part: int, whole: int) -> str:
        if whole <= 0:
            return "0.0%"
        return f"{100.0 * part / whole:.1f}%"

    summary = df["http_status"].value_counts().sort_index()
    print("\nStatus summary:")
    for code, count in summary.items():
        count_i = int(count)
        extra = ""
        if int(code) == 403:
            blocked = df[df["http_status"] == 403]
            pub = int(blocked["is_public"].sum())
            priv = int((~blocked["is_public"]).sum())
            extra = (
                f"  (public: {pub} {_pct(pub, count_i)} unexpected, "
                f"private: {priv} {_pct(priv, count_i)} expected)"
            )
        print(f"  {code}: {count_i} ({_pct(count_i, total)}){extra}")
    ok = int(df["downloadable"].sum())
    print(f"Downloadable (200/206): {ok}/{total} ({100.0 * ok / total:.1f}%)")
    fallback_tried = int(df["fallback_url"].fillna("").astype(str).str.len().gt(0).sum())
    fallback_ok = int(
        (
            df["fallback_url"].fillna("").astype(str).str.len().gt(0)
            & df["fallback_http_status"].isin([200, 206])
        ).sum()
    )
    print(f"Suffix fallback tried: {fallback_tried}; recovered: {fallback_ok}")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    scanned_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.sort_values(["year", "iso3", "document_type", "name"], na_position="last").to_excel(
            writer, sheet_name="documents", index=False
        )
        summary_rows = []
        for code, count in summary.items():
            count_i = int(count)
            sub = df[df["http_status"] == code]
            pub = int(sub["is_public"].sum())
            priv = int((~sub["is_public"]).sum())
            summary_rows.append(
                {
                    "http_status": str(code),
                    "count": count_i,
                    "pct_of_total": round(100.0 * count_i / total, 1) if total else 0.0,
                    "public": pub,
                    "public_pct": round(100.0 * pub / count_i, 1) if count_i else 0.0,
                    "private": priv,
                    "private_pct": round(100.0 * priv / count_i, 1) if count_i else 0.0,
                }
            )
        summary_df = pd.DataFrame(summary_rows)
        summary_df.to_excel(writer, sheet_name="summary", index=False)
        blocked = df[df["http_status"] == 403]
        n403 = int(len(blocked))
        pub403 = int(blocked["is_public"].sum())
        priv403 = int((~blocked["is_public"]).sum())
        meta_df = pd.DataFrame(
            [
                {"key": "scanned_at_utc", "value": scanned_at},
                {"key": "total_documents", "value": total},
                {"key": "downloadable_count", "value": ok},
                {"key": "http_403_public_unexpected", "value": pub403},
                {"key": "http_403_public_unexpected_pct", "value": round(100.0 * pub403 / n403, 1) if n403 else 0.0},
                {"key": "http_403_private_expected", "value": priv403},
                {"key": "http_403_private_expected_pct", "value": round(100.0 * priv403 / n403, 1) if n403 else 0.0},
                {"key": "suffix_fallback_tried", "value": fallback_tried},
                {"key": "suffix_fallback_recovered", "value": fallback_ok},
                {"key": "workers", "value": workers},
                {"key": "base_url", "value": base_url},
            ]
        )
        meta_df.to_excel(writer, sheet_name="meta", index=False)

    print(f"\nWrote {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export FDRS document URL HTTP status to Excel.",
        epilog=(
            "Standalone:  python export_fdrs_document_url_status.py --api-key YOUR_KEY\n"
            "Backoffice:  python scripts/dev/export_fdrs_document_url_status.py"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help="Output .xlsx path")
    parser.add_argument("--api-key", default=None, help="FDRS data API key (default: env / .env)")
    parser.add_argument("--base-url", default=DEFAULT_BASE, help="FDRS data API base URL")
    parser.add_argument("--workers", type=int, default=20, help="Concurrent probe workers")
    parser.add_argument("--limit", type=int, default=None, help="Probe only first N documents (testing)")
    args = parser.parse_args()
    export_url_status_excel(
        output_path=args.output,
        api_key=args.api_key,
        base_url=args.base_url,
        workers=args.workers,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
