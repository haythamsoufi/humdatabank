"""Pull email_api log lines from prod application.log for Jul 12-13 2026."""
from __future__ import annotations

import os
import re

LOG_PATH = "/app/instance/logs/application.log"
OUT_PATH = "/tmp/email_api_log_extract.txt"

patterns = [
    re.compile(r"2026-07-12"),
    re.compile(r"2026-07-13"),
]
email_re = re.compile(r"email_api|welcome email|Failed to send|Email send returned False|anas\.alnajjar|youssouf\.fofana", re.I)

lines_out: list[str] = []
if os.path.isfile(LOG_PATH):
    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            if not any(p.search(line) for p in patterns):
                continue
            if email_re.search(line):
                lines_out.append(f"L{i}:{line.rstrip()}")
else:
    lines_out.append("missing application.log")

# Also dump full log date range coverage
if os.path.isfile(LOG_PATH):
    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as fh:
        all_lines = fh.readlines()
    lines_out.append("")
    lines_out.append(f"first_line={all_lines[0].rstrip() if all_lines else 'EMPTY'}")
    lines_out.append(f"last_line={all_lines[-1].rstrip() if all_lines else 'EMPTY'}")

# Check docker stdout log location
for candidate in [
    "/home/LogFiles",
    "/var/log",
]:
    lines_out.append(f"\n=== ls {candidate} ===")
    if os.path.isdir(candidate):
        for root, dirs, files in os.walk(candidate):
            depth = root.replace(candidate, "").count(os.sep)
            if depth > 2:
                dirs[:] = []
                continue
            for f in sorted(files):
                if any(x in f.lower() for x in ("docker", "application", "default")):
                    fp = os.path.join(root, f)
                    try:
                        sz = os.path.getsize(fp)
                    except OSError:
                        sz = -1
                    lines_out.append(f"  {fp} ({sz} bytes)")
    else:
        lines_out.append("  (not found)")

text = "\n".join(lines_out)
with open(OUT_PATH, "w", encoding="utf-8") as out:
    out.write(text)
print(text)
