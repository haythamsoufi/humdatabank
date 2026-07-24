#!/usr/bin/env python3
"""List P26 discrepancy examples between PNS Data sheet and UPR Data import."""

from __future__ import annotations

import sys
from pathlib import Path

script_dir = Path(__file__).resolve().parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

from compare_upr_pns_data_sheets import (  # noqa: E402
    PNS_BREAKDOWN_COLS,
    load_pns_data_sheet,
    pns_data_p26_records,
    upr_data_p26_pns_funding,
)
from import_upr_excel_data import (  # noqa: E402
    _t22_pns_import_cell_value,
    is_planning_funding_requirement_row,
    load_upr_data_sheet,
    parse_pns_reported_yes,
    parse_value_num,
)


def import_display(cv, pv):
    cell = _t22_pns_import_cell_value(cv, pv)
    if cell is None:
        return None
    if isinstance(cell, dict):
        return "CLEARED"
    return cell


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "instance/upr_import_uploads/9ec694e0700f44118e286780e3c4295e.xlsx"
    _, pns_rows = load_pns_data_sheet(path)
    _, upr_rows = load_upr_data_sheet(path)
    pns = pns_data_p26_records(pns_rows, "P26")
    upr = upr_data_p26_pns_funding(upr_rows, "P26")
    common = set(pns.keys()) & {k for k, v in upr.items() if v.get("areas")}
    upr_only = sorted({k for k, v in upr.items() if v.get("areas")} - set(pns.keys()))

    print("=== A. TOTAL FUNDING MISMATCHES (PNS sheet total vs what we import) ===\n")
    for key in sorted(common):
        rec = pns[key]
        metrics = rec["metrics"]
        areas = upr[key]["areas"]
        pns_total = metrics.get("Funding Requirement")
        u = areas.get("Total", {})
        cv, pv = u.get("country_value"), u.get("pns_value")
        iv = import_display(cv, pv)
        if pns_total == iv or (pns_total is None and iv is None):
            continue
        print(f"  {rec['ns']} x {rec['country']}")
        print(f"    PNS Data:  Funding Requirement = {metrics.get('Funding Requirement')} (Confirmed Funding ignored)")
        print(f"    UPR Total: Country Value = {cv}, PNS Value = {pv}  ->  import = {iv}")
        sp_parts = [f"{a}={metrics.get(a)}" for a in PNS_BREAKDOWN_COLS if metrics.get(a)]
        if sp_parts:
            print(f"    PNS Data SP/EF: {', '.join(sp_parts)}")
        print()

    print("=== B. BREAKDOWN: PNS sheet value != UPR PNS Value (both present) ===\n")
    n = 0
    for key in sorted(common):
        rec = pns[key]
        for area in PNS_BREAKDOWN_COLS:
            ps = rec["metrics"].get(area)
            u = upr[key]["areas"].get(area, {})
            cv, pv = u.get("country_value"), u.get("pns_value")
            if ps is not None and pv is not None and abs(ps - pv) > 0.01:
                print(
                    f"  {rec['ns']} x {rec['country']} [{area}]: "
                    f"PNS sheet = {ps:,.0f} | UPR PNS = {pv:,.0f} | Country = {cv}"
                )
                n += 1
                if n >= 8:
                    break
        if n >= 8:
            break
    print("  (more rows exist in this category)\n")

    print("=== C. BREAKDOWN: PNS sheet has value, UPR PNS Value blank -> import CLEARED ===\n")
    n = 0
    for key in sorted(common):
        rec = pns[key]
        for area in PNS_BREAKDOWN_COLS:
            ps = rec["metrics"].get(area)
            u = upr[key]["areas"].get(area, {})
            cv, pv = u.get("country_value"), u.get("pns_value")
            if ps is not None and pv is None:
                print(
                    f"  {rec['ns']} x {rec['country']} [{area}]: "
                    f"PNS sheet = {ps:,.0f} | UPR PNS = blank | Country = {cv}"
                )
                n += 1
                if n >= 8:
                    break
        if n >= 8:
            break
    print()

    print("=== D. BREAKDOWN: PNS sheet blank, UPR has PNS Value -> import uses UPR PNS ===\n")
    n = 0
    for key in sorted(common):
        rec = pns[key]
        for area in PNS_BREAKDOWN_COLS:
            ps = rec["metrics"].get(area)
            u = upr[key]["areas"].get(area, {})
            cv, pv = u.get("country_value"), u.get("pns_value")
            if ps is None and pv is not None:
                print(
                    f"  {rec['ns']} x {rec['country']} [{area}]: "
                    f"PNS sheet = blank | UPR PNS = {pv:,.0f} | Country = {cv}"
                )
                n += 1
                if n >= 8:
                    break
        if n >= 8:
            break
    print()

    print("=== E. UPR PNS reported=Yes but row NOT on PNS Data sheet ===\n")
    for key in upr_only[:10]:
        areas = upr[key]["areas"]
        bits = []
        for area, d in list(areas.items())[:3]:
            bits.append(f"{area}: PNS={d.get('pns_value')} Country={d.get('country_value')}")
        print(f"  {key[0]} x {key[1]}")
        print(f"    {('; '.join(bits))}")
    print(f"\n  Total UPR-only pairs: {len(upr_only)}\n")

    print("=== F. CLEARED rows (PNS reported=Yes, Country Value set, PNS Value blank) ===\n")
    n = 0
    for row in upr_rows:
        if str(row.get("Round") or "").strip().upper() != "P26":
            continue
        if str(row.get("Section") or "").strip() != "Funding":
            continue
        if str(row.get("Entity") or "").strip().upper() != "PNS":
            continue
        if not is_planning_funding_requirement_row(row):
            continue
        if not parse_pns_reported_yes(row):
            continue
        cv = parse_value_num(row.get("Country Value"))
        pv = parse_value_num(row.get("PNS Value"))
        if cv and pv is None:
            print(
                f"  {row.get('NS')} x {row.get('Country')} Area={row.get('Area')}: "
                f"Country={cv:,.0f}, PNS=blank -> import CLEARED"
            )
            n += 1
            if n >= 8:
                break
    print()


if __name__ == "__main__":
    main()
