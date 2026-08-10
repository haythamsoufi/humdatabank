"""Download and analyze go-api AppealsD365 responses."""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone

def _load_dotenv() -> None:
    basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env_path = os.path.join(basedir, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _basic_auth_header() -> dict:
    _load_dotenv()
    user = (os.environ.get("IFRC_API_USER") or os.environ.get("IFRC_API_USERNAME") or "").strip()
    password = (os.environ.get("IFRC_API_PASSWORD") or "").strip()
    if not user or not password:
        raise RuntimeError("IFRC_API_USER and IFRC_API_PASSWORD must be set in Backoffice/.env")
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}
NS = {"d": "http://schemas.datacontract.org/2004/07/GO.Domain"}
FOCUS = ["MDRS2001", "MDRS1007", "MGR65002", "MDRMM023", "MDRJM005", "MDRNG045"]
FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "tests", "fixtures", "appeals_d365_sample.json"
)


def fetch(url: str, accept: str) -> tuple[str, bytes]:
    headers = {
        **_basic_auth_header(),
        "Accept": accept,
        "User-Agent": "IFRC-Network-Databank/1.0",
    }
    req = urllib.request.Request(url, headers=headers)
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return resp.headers.get("Content-Type", ""), resp.read()
        except Exception as exc:  # pragma: no cover - network probe
            last_err = exc
            time.sleep(6 * (attempt + 1))
    raise last_err  # type: ignore[misc]


def parse_appeal_element(el: ET.Element) -> dict:
    item: dict = {}
    for child in el:
        tag = child.tag.split("}")[-1]
        if tag == "Details":
            details = []
            for det in child.findall("d:AppealDetail", NS):
                row = {
                    c.tag.split("}")[-1]: (c.text.strip() if c.text else None)
                    for c in det
                }
                details.append(row)
            item["Details"] = details
        else:
            item[tag] = child.text.strip() if child.text else None
    return item


def parse_payload(body: bytes, content_type: str) -> list[dict]:
    text = body.decode("utf-8", errors="replace").lstrip()
    if "json" in content_type.lower() or text.startswith("["):
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        raise ValueError(f"Unexpected JSON root: {type(data)}")

    root = ET.fromstring(body)
    # Namespace-agnostic fallback: any element ending in AppealD365
    items = []
    for el in root.iter():
        if el.tag.endswith("AppealD365"):
            items.append(parse_appeal_element(el))
    if items:
        return items

    # Last resort: regex count sanity check
    codes = re.findall(r"<APP_code>([^<]+)</APP_code>", text)
    if codes:
        raise ValueError(
            f"XML contained {len(codes)} APP_code tags but ElementTree found 0 AppealD365 nodes"
        )
    return []


def analyze(items: list[dict], label: str) -> None:
    print(f"\n=== {label}: {len(items)} records ===")
    src = Counter((r.get("source") or "(empty)").strip() for r in items)
    print("source top:", src.most_common(8))

    with_gec = [r for r in items if (r.get("GEC_code") or "").strip()]
    multi = [r for r in with_gec if ";" in (r.get("GEC_code") or "")]
    print(f"GEC_code present: {len(with_gec)}, multi-country: {len(multi)}")

    idx = {(r.get("APP_code") or "").upper(): r for r in items}
    for code in FOCUS:
        row = idx.get(code)
        if not row:
            print(f"  {code}: NOT FOUND")
            continue
        print(
            f"  {code}: {row.get('APP_name')} | source={row.get('source')} | "
            f"GEC={row.get('GEC_code')} | status={row.get('APP_status')}"
        )


def main() -> int:
    results: dict = {"fetched_at": datetime.now(timezone.utc).isoformat(), "probes": []}

    for accept in ("application/json", "application/xml", "*/*"):
        try:
            ctype, body = fetch("https://go-api.ifrc.org/api/AppealsD365", accept)
            items = parse_payload(body, ctype)
            probe = {
                "accept": accept,
                "content_type": ctype,
                "bytes": len(body),
                "record_count": len(items),
            }
            results["probes"].append(probe)
            analyze(items, f"FULL LIST accept={accept!r}")
            if len(items) > 1:
                results["full_list"] = {
                    "accept": accept,
                    "content_type": ctype,
                    "total": len(items),
                    "items_sample": items[:3],
                }
                idx = {(r.get("APP_code") or "").upper(): r for r in items}
                results["focus"] = {c: idx[c] for c in FOCUS if c in idx}
                results["grouped_sample"] = [
                    r for r in items if "(G)" in (r.get("source") or "")
                ][:8]
                results["multi_gec_sample"] = [
                    r
                    for r in items
                    if (r.get("GEC_code") or "").strip() and ";" in (r.get("GEC_code") or "")
                ][:8]
                break
        except Exception as exc:
            results["probes"].append({"accept": accept, "error": str(exc)})
            print(f"accept={accept!r} FAILED: {exc}")

    # Per-code probes
    per_code = {}
    for code in FOCUS:
        try:
            ctype, body = fetch(
                f"https://go-api.ifrc.org/api/AppealsD365?APP_code={code}",
                "application/json",
            )
            items = parse_payload(body, ctype)
            per_code[code] = {
                "content_type": ctype,
                "bytes": len(body),
                "records": items,
            }
            print(f"\nPER-CODE {code}: {len(items)} record(s), GEC={items[0].get('GEC_code') if items else None}")
        except Exception as exc:
            per_code[code] = {"error": str(exc)}
            print(f"\nPER-CODE {code} FAILED: {exc}")
        time.sleep(2)

    results["per_code"] = {
        code: (
            {k: v for k, v in data.items() if k != "records"}
            | {"record_count": len(data.get("records") or []), "record": (data.get("records") or [None])[0]}
        )
        for code, data in per_code.items()
    }

    os.makedirs(os.path.dirname(FIXTURE_PATH), exist_ok=True)
    with open(FIXTURE_PATH, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print(f"\nWrote {FIXTURE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
