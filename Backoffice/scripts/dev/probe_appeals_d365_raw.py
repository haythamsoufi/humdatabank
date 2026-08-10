"""Raw bulk fetch diagnostics for AppealsD365."""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.request

from probe_appeals_d365 import _basic_auth_header  # noqa: E402 — dev script sibling import


def main() -> None:
    req = urllib.request.Request(
        "https://go-api.ifrc.org/api/AppealsD365",
        headers={
            **_basic_auth_header(),
            "Accept": "application/json",
            "User-Agent": "IFRC-Network-Databank/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read().decode("utf-8", errors="replace")

    print("bytes", len(body))
    print("starts with", body[:120])
    data = json.loads(body)
    print("parsed type", type(data).__name__)
    if isinstance(data, list):
        print("list length", len(data))
        for i, row in enumerate(data[:5]):
            print(
                f"  [{i}] code={row.get('APP_code')} name={row.get('APP_name')} "
                f"details={len(row.get('Details') or [])} source={row.get('source')}"
            )
        if len(data) == 1:
            row = data[0]
            print("single row keys", sorted(row.keys()))
            print("GEC", row.get("GEC_code"), "source", row.get("source"))

    codes = re.findall(r'"APP_code"\s*:\s*"([^"]+)"', body)
    print("APP_code regex count", len(codes), "unique", len(set(codes)))
    print("sample unique codes", sorted(set(codes))[:20])
    for focus in ["MDRS2001", "MDRS1007", "MGR65002", "MDRMM023"]:
        print(focus, "in body", focus in codes)


if __name__ == "__main__":
    main()
