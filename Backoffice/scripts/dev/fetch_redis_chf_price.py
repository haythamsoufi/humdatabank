#!/usr/bin/env python3
"""Fetch Azure Managed Redis B0 West Europe CHF list prices (public retail API)."""
import json
import urllib.parse
import urllib.request

HOURS_PER_MONTH = 730  # Azure retail API bills per hour; ~730 h/month


def fetch(filter_expr: str) -> list:
    url = (
        "https://prices.azure.com/api/retail/prices?"
        + urllib.parse.urlencode({"$filter": filter_expr, "currencyCode": "CHF"})
    )
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.load(resp).get("Items", [])


def main() -> None:
    b0 = fetch(
        "armRegionName eq 'westeurope' and skuName eq 'B0' and "
        "productName eq 'Azure Managed Redis - Balanced' and type eq 'Consumption'"
    )
    if not b0:
        print("No B0 consumption meter found")
        return
    hourly = b0[0]["retailPrice"]
    monthly_one_node = round(hourly * HOURS_PER_MONTH, 2)
    monthly_two_node = round(hourly * 2 * HOURS_PER_MONTH, 2)
    print("Azure Managed Redis Balanced B0 — West Europe — CHF (retail API, Consumption)")
    print(f"  Hourly (one node):     CHF {hourly:.4f} / hour")
    print(f"  Monthly (one node):    ~CHF {monthly_one_node} / month  (730 h)")
    print(f"  Monthly (two-node HA): ~CHF {monthly_two_node} / month  (730 h × 2 nodes)")


if __name__ == "__main__":
    main()
