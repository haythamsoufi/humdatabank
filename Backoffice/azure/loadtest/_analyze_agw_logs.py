"""One-off AGW log analysis for prod load test 2026-07-23."""
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

ACCESS = Path(r"c:\Humanitarian Databank\AGWAccessLogs_2026.07.23_databank_prod-listener.csv")
FIREWALL = Path(r"c:\Humanitarian Databank\AGWFirewallLogs_2026.07.23_databank.ifrc.org.csv")
WINDOW_START = datetime(2026, 7, 23, 14, 28, 0)
WINDOW_END = datetime(2026, 7, 23, 14, 36, 0)


def parse_ts(raw: str):
    s = (raw or "").strip().strip('"')
    s = s.replace(". ", "-", 3).replace("  ", " ")
    # 2026-07-23-14:30:47.000 -> fix date/time separator
    if len(s) >= 19 and s[10] == "-":
        s = s[:10] + " " + s[11:]
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def load_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    rows = load_csv(ACCESS)
    print(f"Access log rows: {len(rows)}")
    times = [parse_ts(r.get("TimeGenerated [UTC]", "")) for r in rows]
    times = [t for t in times if t]
    if times:
        print(f"Access time range: {min(times)} -> {max(times)}")

    window = [(t, r) for r in rows if (t := parse_ts(r.get("TimeGenerated [UTC]", ""))) and WINDOW_START <= t <= WINDOW_END]
    print(f"Rows in load-test window: {len(window)}")

    print("\nHttpStatus in window:")
    for code, n in Counter(r.get("HttpStatus") for _, r in window).most_common():
        print(f"  {code}: {n}")

    bad502 = [(t, r) for t, r in window if r.get("HttpStatus") == "502"]
    print(f"\n502 in window: {len(bad502)}")
    if bad502:
        print("ServerStatus on 502:", dict(Counter(r.get("ServerStatus") for _, r in bad502)))
        print("ErrorInfo on 502:")
        for k, v in Counter(r.get("ErrorInfo") for _, r in bad502).most_common():
            print(f"  {k}: {v}")
        print("\nTop URIs on 502:")
        for uri, n in Counter(r.get("RequestUri") for _, r in bad502).most_common(15):
            print(f"  {n:4d}  {uri}")
        print("\n502 by minute:")
        for minute, n in sorted(Counter(t.strftime("%H:%M") for t, _ in bad502).items()):
            print(f"  {minute}: {n}")
        lats = []
        for _, r in bad502:
            try:
                lats.append(float(r.get("TimeTaken") or 0))
            except (TypeError, ValueError):
                pass
        if lats:
            lats.sort()
            print(f"\n502 TimeTaken: min={lats[0]:.3f} p50={lats[len(lats)//2]:.3f} max={lats[-1]:.3f}")

    for code in ("200", "502", "504"):
        vals = []
        for _, r in window:
            if r.get("HttpStatus") == code:
                try:
                    vals.append(float(r.get("TimeTaken") or 0))
                except (TypeError, ValueError):
                    pass
        if vals:
            vals.sort()
            p95 = vals[int(len(vals) * 0.95)]
            print(f"\n{code} TimeTaken: n={len(vals)} p50={vals[len(vals)//2]:.3f} p95={p95:.3f} max={vals[-1]:.3f}")

    # Load test Chrome UA traffic in window
    chrome120 = [(t, r) for t, r in window if "Chrome/120" in (r.get("UserAgent") or "")]
    print(f"\nChrome/120 UA rows in window (Locust): {len(chrome120)}")
    if chrome120:
        print("  HttpStatus:", dict(Counter(r.get("HttpStatus") for _, r in chrome120)))

    fw = load_csv(FIREWALL)
    print(f"\nFirewall rows: {len(fw)}")
    fw_window = [r for r in fw if (t := parse_ts(r.get("TimeGenerated [UTC]", ""))) and WINDOW_START <= t <= WINDOW_END]
    print(f"Firewall in window: {len(fw_window)}")
    print("WAF Action in window:", dict(Counter(r.get("Action") for r in fw_window)))

    blocked = [r for r in fw if (r.get("Action") or "").lower() == "blocked"]
    print(f"\nTotal WAF blocked all day: {len(blocked)}")
    print("Top blocked RuleId:", Counter(r.get("RuleId") for r in blocked).most_common(10))

    blocked_window = [r for r in fw_window if (r.get("Action") or "").lower() == "blocked"]
    print(f"WAF blocked in window: {len(blocked_window)}")
    for r in blocked_window[:10]:
        print(" ", r.get("TimeGenerated [UTC]"), r.get("RuleId"), (r.get("RequestUri") or "")[:70])


if __name__ == "__main__":
    main()
