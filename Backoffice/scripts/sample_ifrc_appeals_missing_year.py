#!/usr/bin/env python3
"""
Print sample IFRC PublicSiteAppeals rows where year is null using the same rule
as app/routes/ai_documents/ifrc.py list_ifrc_api_documents (``IFRC_APPEALS_TITLE_YEAR_RE``
on AppealOrigType + ' ' + AppealsName).

Run from Backoffice/:
  python scripts/sample_ifrc_appeals_missing_year.py
  python scripts/sample_ifrc_appeals_missing_year.py --sample 25

Requires .env with IFRC_API_USER and IFRC_API_PASSWORD (same as fetch_ifrc_api_types.py).

By default this uses the same AppealsTypeId filter as mobile unified planning and
``/api/mobile/v1/data/unified-planning-config`` (``app.utils.constants.APPEALS_TYPE_DEFAULT_IDS_STR``:
Plan, Mid-Year Report, Annual Report). The admin IFRC tab in ``documents.html`` often
sends ``appeals_type_ids=all`` when every type checkbox is selected — that is a wider
feed than unified planning alone.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Keep in sync with app.routes.ai_documents.helpers.IFRC_APPEALS_TITLE_YEAR_RE
_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")

# Same as app.utils.constants.APPEALS_TYPE_DEFAULT_IDS_STR / mobile unified-planning-config.
_DEFAULT_UNIFIED_PLANNING_APPEALS_TYPE_IDS = "1851,10009,10011"


def _load_dotenv() -> None:
    basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(basedir, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _parse_year(item: dict) -> int | None:
    appeal_orig_type = (item.get("AppealOrigType") or "") or ""
    appeals_name = (item.get("AppealsName") or "") or ""
    m = _YEAR_RE.search(appeal_orig_type + " " + appeals_name)
    if m:
        return int(m.group(1))
    return None


def _truncate(s: str, max_len: int = 140) -> str:
    s = (s or "").replace("\n", " ").replace("\r", " ").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sample",
        type=int,
        default=20,
        help="How many no-year rows to print (default 20)",
    )
    parser.add_argument(
        "--appeals-type-id",
        type=str,
        default=_DEFAULT_UNIFIED_PLANNING_APPEALS_TYPE_IDS,
        metavar="IDS",
        help=(
            "AppealsTypeId query for IFRC PublicSiteAppeals (default: unified planning "
            f"{_DEFAULT_UNIFIED_PLANNING_APPEALS_TYPE_IDS}). Use 'all' for no type filter."
        ),
    )
    args = parser.parse_args()

    _load_dotenv()
    user = (os.environ.get("IFRC_API_USER") or os.environ.get("IFRC_API_USERNAME") or "").strip()
    password = (os.environ.get("IFRC_API_PASSWORD") or "").strip()
    if not user or not password:
        logger.error("Set IFRC_API_USER and IFRC_API_PASSWORD in Backoffice/.env")
        return 1

    import requests
    from requests.auth import HTTPBasicAuth

    base = "https://go-api.ifrc.org/Api/PublicSiteAppeals"
    q = (args.appeals_type_id or "").strip()
    if q.lower() == "all":
        url = base
    else:
        url = f"{base}?AppealsTypeId={q}"

    auth = HTTPBasicAuth(user, password)
    headers = {"User-Agent": "hum-databank-scripts/1.0", "Accept": "application/json"}
    logger.info("GET %s", url)
    try:
        r = requests.get(url, headers=headers, auth=auth, timeout=60)
        r.raise_for_status()
    except requests.RequestException as e:
        logger.error("Request failed: %s", e)
        return 1
    data = r.json()
    if not isinstance(data, list):
        logger.error("Expected JSON list, got %s", type(data).__name__)
        return 1

    no_year: list[dict] = []
    visible = 0
    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get("Hidden"):
            continue
        base_dir = (item.get("BaseDirectory") or "").strip()
        base_file = (item.get("BaseFileName") or "").strip()
        if not base_dir or not base_file:
            continue
        visible += 1
        if _parse_year(item) is None:
            no_year.append(item)

    logger.info("Non-hidden rows with URL parts: %s", visible)
    logger.info("Rows with no year (IFRC_APPEALS_TITLE_YEAR_RE on orig+name): %s", len(no_year))
    if not no_year:
        return 0

    keys = (
        "AppealsName",
        "AppealOrigType",
        "AppealsDate",
        "AppealsTypeId",
        "LocationCountryCode",
        "LocationCountryName",
        "BaseDirectory",
        "BaseFileName",
    )
    for i, item in enumerate(no_year[: max(1, args.sample)]):
        logger.info("")
        logger.info("--- Sample %s / %s ---", i + 1, min(args.sample, len(no_year)))
        for k in keys:
            v = item.get(k)
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)[:200]
            logger.info("%s: %s", k, _truncate(str(v) if v is not None else "", 200))
    if len(no_year) > args.sample:
        logger.info("")
        logger.info("(Omitted %s more no-year rows; increase --sample)", len(no_year) - args.sample)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
