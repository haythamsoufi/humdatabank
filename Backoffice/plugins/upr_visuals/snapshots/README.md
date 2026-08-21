# UPR visuals — IFRC Secretariat actuals snapshots

Temporary overlay for **IFRC Secretariat Funding and Expenditure** on Unified Country **Report** (template 33) Financial Overview visuals. Funding requirement still comes from the matching Unified Country Plan (template 24). PNS actuals still come from template 23.

Do **not** commit the source `.xlsx` (repo-wide gitignore). Commit the JSON so it deploys with the plugin.

## Current snapshot

| File | Round | Assignment `period_name` | Source workbook | Excel table |
|---|---|---|---|---|
| `myr26_ifrc_secretariat_actuals.json` | `MYR26` | `Jan-Jun 2026` | `System Financial Figures 2026.xlsx` | `Final` |

The loader in `plugins/upr_visuals/data.py` only applies this file when `period_to_round(period_name, "report") == "MYR26"`. Other rounds stay **Not reported** until a new snapshot is added **and** the loader is extended.

## Source workbook

Typical local path (not in git):

`System Financial Figures 2026.xlsx`

Sheets seen in the 2026 file:

| Sheet | Role |
|---|---|
| `Final (2)` | Contains Excel table **`Final`** (display name `Final`). This is the extract source. |
| `1_c_Country Map` | `iso_2` → `iso_3` for lookup fallback |
| `UPR Data` | Plan-side requirement totals — **do not** use for Funding/Expenditure |
| `Raw Data` / `Filtered out` | Line-level finance — already rolled into `Final` |

Confirm the table name in openpyxl (`ws.tables`) rather than the sheet tab. The 2026 file used sheet `Final (2)` + table `Final`.

### `Final` columns

| Column (header may contain a newline) | Maps to JSON |
|---|---|
| `ISO2` | `by_iso2` key |
| `Country` | `country` |
| `Longer-term Funding` | `longer_term.funding` |
| `Longer-term Expenditure` | `longer_term.expenditure` |
| `Emergency Operations Funding` | `emergency.funding` |
| `Emergency Operations Expenditure` | `emergency.expenditure` |
| `Regular Resources *` | Ignore (empty in 2026) |
| `Longer-term Funding Requirement` | Ignore (visual uses T24) |

## JSON contract

```json
{
  "source": "System Financial Figures 2026.xlsx",
  "table": "Final",
  "round": "MYR26",
  "period_name": "Jan-Jun 2026",
  "currency": "CHF",
  "by_iso2": {
    "AF": {
      "country": "Afghanistan",
      "iso3": "AFG",
      "longer_term": { "funding": 10621043, "expenditure": 3461570 },
      "emergency": { "funding": 1938683, "expenditure": 2929339 }
    }
  }
}
```

Rules:

1. Amounts are **integer CHF** (`int(round(raw))`).
2. Omit any amount **below 1,000 CHF**, including all **negatives**. The loader repeats this via `_IFRC_ACTUALS_MIN_CHF` in `data.py`.
3. Omit empty buckets and countries with no remaining amounts.
4. Key by uppercase ISO2. Include `iso3` from `1_c_Country Map` when available (loader falls back to ISO3 if ISO2 is missing on the country).
5. Pretty-print UTF-8 JSON with a trailing newline.

## How to re-extract

From `Backoffice/` (openpyxl required):

```python
import json
from pathlib import Path
import openpyxl

src = Path(r"C:\path\to\System Financial Figures 2026.xlsx")
out = Path("plugins/upr_visuals/snapshots/myr26_ifrc_secretariat_actuals.json")
min_chf = 1000

wb = openpyxl.load_workbook(src, data_only=True)

iso3_by_iso2 = {}
ws_map = wb["1_c_Country Map"]
headers = [c.value for c in next(ws_map.iter_rows(min_row=1, max_row=1))]
i2, i3 = headers.index("iso_2"), headers.index("iso_3")
for row in ws_map.iter_rows(min_row=2, values_only=True):
    iso2, iso3 = str(row[i2] or "").strip().upper(), str(row[i3] or "").strip().upper()
    if iso2 and iso3:
        iso3_by_iso2[iso2] = iso3

# Find the sheet that hosts table "Final"
ws = next(s for s in wb.worksheets if "Final" in (s.tables or {}))
headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]

def col(*needles):
    for h in headers:
        text = (h or "").replace("\n", " ")
        if all(n.lower() in text.lower() for n in needles):
            return h
    raise KeyError(needles)

def chf(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    rounded = int(round(number))
    return rounded if rounded >= min_chf else None

def bucket(funding, expenditure):
    out = {}
    if funding is not None:
        out["funding"] = funding
    if expenditure is not None:
        out["expenditure"] = expenditure
    return out

by_iso2 = {}
for row in ws.iter_rows(min_row=2, values_only=True):
    rec = dict(zip(headers, row))
    iso2 = str(rec.get("ISO2") or "").strip().upper()
    if not iso2:
        continue
    longer = bucket(chf(rec.get(col("Longer-term", "Funding"))), chf(rec.get(col("Longer-term", "Expenditure"))))
    emergency = bucket(
        chf(rec.get(col("Emergency Operations", "Funding"))),
        chf(rec.get(col("Emergency Operations", "Expenditure"))),
    )
    if not longer and not emergency:
        continue
    entry = {"country": str(rec.get("Country") or "").strip()}
    if iso2 in iso3_by_iso2:
        entry["iso3"] = iso3_by_iso2[iso2]
    if longer:
        entry["longer_term"] = longer
    if emergency:
        entry["emergency"] = emergency
    by_iso2[iso2] = entry
wb.close()

payload = {
    "_comment": (
        "Temporary overlay for IFRC Secretariat Funding/Expenditure in UPR report visuals. "
        "Extracted from System Financial Figures Excel table Final. "
        "Amounts below 1,000 CHF (including negatives) are omitted."
    ),
    "source": src.name,
    "table": "Final",
    "round": "MYR26",
    "period_name": "Jan-Jun 2026",
    "currency": "CHF",
    "by_iso2": dict(sorted(by_iso2.items())),
}
out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote {out} countries={len(by_iso2)}")
```

Sanity checks after extract:

- Afghanistan (`AF` / `AFG`) longer-term funding ≈ `10621043` (2026 file).
- Albania (`AL`) should be absent (negatives / sub-1,000 only).
- `python -m pytest plugins/upr_visuals/tests/test_data_helpers.py -k ifrc -q --no-cov`

## Adding another round

This is **not** automatic. You must:

1. Extract a new `*.json` next to this README (same schema, different `round` / `period_name`).
2. Teach `ifrc_secretariat_actuals_for_report` in `data.py` to load it for that round. Today the path and `MYR26` check are hardcoded.
3. Extend `plugins/upr_visuals/tests/test_data_helpers.py`.

Do not reuse the MYR26 file for AR / other mid-years.
