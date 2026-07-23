"""Extended AGW analysis - backend 502 details."""
import csv
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ACCESS = Path(r"c:\Humanitarian Databank\AGWAccessLogs_2026.07.23_databank_prod-listener.csv")
WINDOW_START = datetime(2026, 7, 23, 14, 28, 0)
WINDOW_END = datetime(2026, 7, 23, 14, 36, 0)


def parse_ts(raw: str):
    s = (raw or "").strip().strip('"')
    s = s.replace(". ", "-", 3).replace("  ", " ")
    if len(s) >= 19 and s[10] == "-":
        s = s[:10] + " " + s[11:]
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def ffloat(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


rows = list(csv.DictReader(ACCESS.open(encoding="utf-8-sig", newline="")))
window = [(parse_ts(r["TimeGenerated [UTC]"]), r) for r in rows]
window = [(t, r) for t, r in window if t and WINDOW_START <= t <= WINDOW_END]

bad502 = [r for t, r in window if r.get("HttpStatus") == "502"]
print("=== Sample 502 rows (first 5) ===")
for r in bad502[:5]:
    print({
        "time": r.get("TimeGenerated [UTC]"),
        "uri": r.get("RequestUri"),
        "HttpStatus": r.get("HttpStatus"),
        "ServerStatus": r.get("ServerStatus"),
        "ServerRouted": r.get("ServerRouted"),
        "TimeTaken": r.get("TimeTaken"),
        "ServerResponseLatency": r.get("ServerResponseLatency"),
        "ServerConnectTime": r.get("ServerConnectTime"),
        "ServerHeaderTime": r.get("ServerHeaderTime"),
        "ErrorInfo": r.get("ErrorInfo"),
        "ClientIp": r.get("ClientIp"),
    })

print("\n=== 502 latency fields ===")
for field in ("TimeTaken", "ServerResponseLatency", "ServerConnectTime", "ServerHeaderTime"):
    vals = [ffloat(r.get(field)) for r in bad502]
    vals = [v for v in vals if v is not None]
    if vals:
        vals.sort()
        print(f"{field}: min={vals[0]:.4f} p50={vals[len(vals)//2]:.4f} max={vals[-1]:.4f}")

# requests per second in 502 burst minutes
print("\n=== Request rate by minute (all statuses) ===")
by_min = defaultdict(lambda: Counter())
for t, r in window:
    by_min[t.strftime("%H:%M")][r.get("HttpStatus")] += 1
for minute in sorted(by_min):
    c = by_min[minute]
    total = sum(c.values())
    print(f"{minute}: total={total} 502={c.get('502',0)} 200={c.get('200',0)}")

# 499 analysis
bad499 = [r for t, r in window if r.get("HttpStatus") == "499"]
print(f"\n499 count: {len(bad499)}")
if bad499:
    print("499 URIs:", Counter(r.get("RequestUri") for r in bad499).most_common(8))

# All-day 502 outside window
outside502 = [r for r in rows if r.get("HttpStatus") == "502" and (not (t := parse_ts(r.get("TimeGenerated [UTC]", ""))) or not (WINDOW_START <= t <= WINDOW_END))]
print(f"\n502 outside load-test window (24h log): {len(outside502)}")

# python-requests UA all day
py_req = [r for r in rows if "python-requests" in (r.get("UserAgent") or "").lower()]
print(f"python-requests UA rows all day: {len(py_req)}")
if py_req:
    print("  statuses:", Counter(r.get("HttpStatus") for r in py_req))

# 403 all day
print("403 all day:", sum(1 for r in rows if r.get("HttpStatus") == "403"))

# Firewall - Matched vs Blocked
FW = Path(r"c:\Humanitarian Databank\AGWFirewallLogs_2026.07.23_databank.ifrc.org.csv")
fw = list(csv.DictReader(FW.open(encoding="utf-8-sig", newline="")))
print(f"\nFirewall export rows: {len(fw)} (may be sampled)")
print("Firewall actions:", Counter(r.get("Action") for r in fw))
print("Firewall time range:", min(parse_ts(r['TimeGenerated [UTC]']) for r in fw if parse_ts(r.get('TimeGenerated [UTC]',''))), "->", max(parse_ts(r['TimeGenerated [UTC]']) for r in fw if parse_ts(r.get('TimeGenerated [UTC]',''))))

# Any Detected/Blocked in firewall
for action in ("Blocked", "Detected", "Matched"):
    n = sum(1 for r in fw if (r.get("Action") or "").lower() == action.lower())
    if n:
        print(f"Firewall {action}: {n}")

PY