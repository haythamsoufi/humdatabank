#!/usr/bin/env python3
import re
from pathlib import Path

p = Path(__file__).resolve().parents[2] / "app/static/js/admin/audit-trail.js"
js = p.read_text(encoding="utf-8")
js = re.sub(r'">\s*\+\s*cfg\.t\.(\w+)\s*\+\s*</', r">' + cfg.t.\1 + '</", js)
js = re.sub(
    r"\(\s*v\s*\?\s*'\s*\+\s*cfg\.t\.(\w+)\s*\+\s*'\s*:\s*'\s*\+\s*cfg\.t\.(\w+)\s*\+\s*'\)",
    r"(v ? cfg.t.\1 : cfg.t.\2)",
    js,
)
p.write_text(js, encoding="utf-8")
print("ok", p)
