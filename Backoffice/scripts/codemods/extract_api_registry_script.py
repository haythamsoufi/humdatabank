#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / "app/templates/admin/api_management.html").read_text(encoding="utf-8")
marker = "// ── Endpoint Registry"
idx = html.find(marker)
if idx < 0:
    raise SystemExit("marker not found")
start = html.rfind("<script nonce=", 0, idx)
end = html.find("</script>", idx) + len("</script>")
(ROOT / "scripts/_api_registry_script.html").write_text(html[start:end], encoding="utf-8")
print("bytes", end - start)
