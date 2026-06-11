"""
Export all FDRS document URLs with HTTP probe status to Excel.

Usage (from Backoffice/):
    python scripts/export_fdrs_document_url_status.py
    python scripts/export_fdrs_document_url_status.py --output instance/fdrs_document_urls.xlsx
    python scripts/export_fdrs_document_url_status.py --workers 24 --limit 100  # smoke test
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKOFFICE_DIR = os.path.dirname(SCRIPT_DIR)
for p in (BACKOFFICE_DIR, SCRIPT_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

DEFAULT_BASE = "https://data-api.ifrc.org"
DEFAULT_OUTPUT = os.path.join(BACKOFFICE_DIR, "instance", "fdrs_document_url_status.xlsx")


def _load_api_key(explicit: Optional[str]) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    key = (os.environ.get("FDRS_DATA_API_KEY") or "").strip()
    if key:
        return key
    env_path = os.path.join(BACKOFFICE_DIR, ".env")
    if os.path.isfile(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("FDRS_DATA_API_KEY="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    raise SystemExit(
        "FDRS_DATA_API_KEY is required (env, Backoffice/.env, or --api-key)."
    )


def encode_document_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


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


def _probe_row(doc: Dict[str, Any]) -> Dict[str, Any]:
    url = (doc.get("url") or "").strip()
    status, detail = probe_url(url)
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
        "modified_at": doc.get("ModifiedAt") or "",
        "url": url,
        "url_encoded": encode_document_url(url) if url else "",
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
    from fdrs_documents_sync import fetch_fdrs_documents_api

    key = _load_api_key(api_key)
    documents = fetch_fdrs_documents_api(base_url, key)
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

    status_order = [200, 206, 403, 404, 405, 500, 502, 503, -1, 0]
    summary = df["http_status"].value_counts().sort_index()
    print("\nStatus summary:")
    for code, count in summary.items():
        print(f"  {code}: {count}")
    ok = int(df["downloadable"].sum())
    print(f"Downloadable (200/206): {ok}/{total} ({100.0 * ok / total:.1f}%)")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    scanned_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.sort_values(["year", "iso3", "document_type", "name"], na_position="last").to_excel(
            writer, sheet_name="documents", index=False
        )
        summary_df = pd.DataFrame(
            {
                "http_status": summary.index.astype(str),
                "count": summary.values,
            }
        )
        summary_df.to_excel(writer, sheet_name="summary", index=False)
        meta_df = pd.DataFrame(
            [
                {"key": "scanned_at_utc", "value": scanned_at},
                {"key": "total_documents", "value": total},
                {"key": "downloadable_count", "value": ok},
                {"key": "workers", "value": workers},
                {"key": "base_url", "value": base_url},
            ]
        )
        meta_df.to_excel(writer, sheet_name="meta", index=False)

    print(f"\nWrote {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export FDRS document URL HTTP status to Excel.")
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
