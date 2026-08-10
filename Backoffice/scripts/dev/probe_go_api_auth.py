"""Compare GO API auth: legacy goadmin (no auth) vs go-api AppealsD365 (IFRC basic auth)."""

from __future__ import annotations

import os
import sys
import time

# Load Backoffice/.env (this file lives in Backoffice/scripts/dev/)
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
env_path = os.path.join(basedir, ".env")
if os.path.exists(env_path):
    with open(env_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

import requests
from requests.auth import HTTPBasicAuth

USER = (os.environ.get("IFRC_API_USER") or os.environ.get("IFRC_API_USERNAME") or "").strip()
PASSWORD = (os.environ.get("IFRC_API_PASSWORD") or "").strip()

HEADERS = {"User-Agent": "IFRC-Network-Databank/1.0", "Accept": "application/json"}


def probe(label: str, url: str, *, auth=None, params=None) -> None:
    try:
        resp = requests.get(url, headers=HEADERS, auth=auth, params=params, timeout=120)
        ctype = resp.headers.get("Content-Type", "")
        preview = resp.text[:120].replace("\n", " ")
        print(f"{label}")
        print(f"  status={resp.status_code} bytes={len(resp.content)} type={ctype[:50]}")
        print(f"  preview={preview}")
        if resp.ok and "json" in ctype.lower():
            data = resp.json()
            if isinstance(data, list):
                code = data[0].get("APP_code") if data else None
                print(f"  json list len={len(data)} first APP_code={code}")
            elif isinstance(data, dict) and "results" in data:
                results = data.get("results") or []
                code = results[0].get("code") if results else None
                print(f"  json results len={len(results)} total={data.get('count')} first code={code}")
    except Exception as exc:
        print(f"{label}")
        print(f"  ERROR {type(exc).__name__}: {exc}")
    print()


def main() -> int:
    print("=== Credential source ===")
    if USER and PASSWORD:
        print(f"  IFRC_API_USER set (len={len(USER)})")
        print(f"  IFRC_API_PASSWORD set (len={len(PASSWORD)})")
        auth = HTTPBasicAuth(USER, PASSWORD)
    else:
        print("  IFRC_API_USER / IFRC_API_PASSWORD not set in .env")
        auth = None

    print("=== Legacy EmOps endpoint (no auth — as in plugin today) ===")
    probe(
        "GET goadmin.ifrc.org/api/v2/appeal/",
        "https://goadmin.ifrc.org/api/v2/appeal/",
        params={"format": "json", "limit": 3, "end_date__gte": "2026-01-01"},
    )

    if not auth:
        print("Skipping go-api probes — no IFRC basic auth configured.")
        return 1

    print("=== go-api AppealsD365 (IFRC basic auth — same as PublicSiteAppeals) ===")
    time.sleep(2)
    probe(
        "GET go-api.ifrc.org/api/AppealsD365?APP_code=MDRJM005",
        "https://go-api.ifrc.org/api/AppealsD365",
        auth=auth,
        params={"APP_code": "MDRJM005"},
    )
    time.sleep(2)
    probe(
        "GET go-api.ifrc.org/api/AppealsD365 (bulk)",
        "https://go-api.ifrc.org/api/AppealsD365",
        auth=auth,
    )
    time.sleep(2)
    probe(
        "GET go-api.ifrc.org/Api/PublicSiteAppeals (reference)",
        "https://go-api.ifrc.org/Api/PublicSiteAppeals",
        auth=auth,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
