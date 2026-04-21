#!/usr/bin/env python3
"""
Fetch available document types from IFRC GO API.
Run from Backoffice/ with: python scripts/fetch_ifrc_api_types.py
Requires .env with IFRC_API_USER and IFRC_API_PASSWORD.
"""
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Load .env
basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(basedir, ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

user = os.environ.get("IFRC_API_USER") or os.environ.get("IFRC_API_USERNAME", "").strip()
password = os.environ.get("IFRC_API_PASSWORD", "").strip()
if not user or not password:
    logger.error("Set IFRC_API_USER and IFRC_API_PASSWORD in .env")
    sys.exit(1)

import requests
from requests.auth import HTTPBasicAuth

auth = HTTPBasicAuth(user, password)
headers = {"User-Agent": "IFRC-Network-Databank/1.0", "Accept": "application/json"}

# 1. Try PublicSiteTypes endpoint (lists appeal types)
logger.info("--- 1. GET api/PublicSiteTypes ---")
try:
    r = requests.get(
        "https://go-api.ifrc.org/Api/PublicSiteTypes",
        headers=headers,
        auth=auth,
        timeout=15,
    )
    logger.info("Status: %s", r.status_code)
    if r.ok:
        data = r.json()
        logger.info("Response (first 2000 chars): %s", str(data)[:2000])
        if isinstance(data, list):
            logger.info("Total types: %d", len(data))
            for i, t in enumerate(data[:30]):
                logger.info("  [%d] %s", i, t)
        else:
            logger.info("Type: %s, keys: %s", type(data), data.keys() if isinstance(data, dict) else 'N/A')
    else:
        logger.info("Body: %s", r.text[:500])
except Exception as e:
    logger.error("Error: %s", e)

# 2. Fetch PublicSiteAppeals with NO AppealsTypeId filter (empty or omit)
logger.info("\n--- 2. GET PublicSiteAppeals (no type filter) ---")
try:
    r = requests.get(
        "https://go-api.ifrc.org/Api/PublicSiteAppeals",
        headers=headers,
        auth=auth,
        timeout=15,
    )
    logger.info("Status: %s", r.status_code)
    if r.ok:
        data = r.json()
        if isinstance(data, list):
            logger.info("Total appeals: %d", len(data))
            # Collect unique AppealsTypeId + AppealOrigType
            seen = set()
            types_list = []
            for item in data[:200]:
                tid = item.get("AppealsTypeId")
                orig = (item.get("AppealOrigType") or "").strip()
                key = (tid, orig)
                if key not in seen:
                    seen.add(key)
                    types_list.append({"AppealsTypeId": tid, "AppealOrigType": orig})
            logger.info("Unique AppealsTypeId + AppealOrigType (from first 200):")
            for t in sorted(types_list, key=lambda x: (x["AppealsTypeId"] or 0, x["AppealOrigType"])):
                logger.info("  AppealsTypeId=%r AppealOrigType=%r", t['AppealsTypeId'], t['AppealOrigType'])
            # Also sample first item
            if data:
                logger.info("Sample first item keys: %s", list(data[0].keys()))
        else:
            logger.info("Response: %s", str(data)[:500])
    else:
        logger.info("Body: %s", r.text[:500])
except Exception as e:
    logger.error("Error: %s", e)

# 3. Fetch with current filter (1851,10009,10011)
logger.info("\n--- 3. GET PublicSiteAppeals?AppealsTypeId=1851,10009,10011 ---")
try:
    r = requests.get(
        "https://go-api.ifrc.org/Api/PublicSiteAppeals?AppealsTypeId=1851,10009,10011",
        headers=headers,
        auth=auth,
        timeout=15,
    )
    logger.info("Status: %s", r.status_code)
    if r.ok:
        data = r.json()
        if isinstance(data, list):
            logger.info("Total: %d", len(data))
            seen = set()
            for item in data[:100]:
                tid = item.get("AppealsTypeId")
                orig = (item.get("AppealOrigType") or "").strip()
                key = (tid, orig)
                if key not in seen:
                    seen.add(key)
                    logger.info("  AppealsTypeId=%s AppealOrigType=%r", tid, orig)
        else:
            logger.info("Response: %s", str(data)[:300])
    else:
        logger.info("Body: %s", r.text[:300])
except Exception as e:
    logger.error("Error: %s", e)
