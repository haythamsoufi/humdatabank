"""Extract contiguous application.log lines around failed welcome emails."""
from __future__ import annotations

import os

LOG_PATH = "/app/instance/logs/application.log"
OUT_PATH = "/tmp/email_failure_context.txt"

windows = [
    ("anas.alnajjar@ifrc.org", 798, 878),
    ("youssouf.fofana@croix-rouge.ml", 948, 1032),
]

lines_out: list[str] = []
with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as fh:
    all_lines = fh.readlines()

for label, start, end in windows:
    lines_out.append(f"=== {label} lines {start}-{end} ===")
    for i in range(start, min(end, len(all_lines)) + 1):
        lines_out.append(f"L{i}:{all_lines[i-1].rstrip()}")

text = "\n".join(lines_out)
with open(OUT_PATH, "w", encoding="utf-8") as out:
    out.write(text)
print(text)
