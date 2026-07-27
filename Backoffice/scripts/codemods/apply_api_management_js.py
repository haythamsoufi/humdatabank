#!/usr/bin/env python3
"""Replace API management tab + registry inline scripts with static JS."""
from pathlib import Path
import re

import migrate_template_js as mig

ROOT = Path(__file__).resolve().parents[1]
template = ROOT / "app/templates/admin/api_management.html"
html = template.read_text(encoding="utf-8")

registry_chunk = (ROOT / "scripts/_api_registry_script.html").read_text(encoding="utf-8")
m = re.search(
    r'<script\s+nonce="\{\{\s*csp_nonce\(\)\s*\}\}">\s*(.*)</script>',
    registry_chunk,
    re.DOTALL,
)
if not m:
    raise SystemExit("registry script parse failed")
_, registry_cfg = mig.build_bootstrap(m.group(1))
bootstrap = mig.render_bootstrap_jinja(registry_cfg, "apiMgmtRegistryConfig")

tabs_marker = '<script nonce="{{ csp_nonce() }}">\n(function () {\n    window.__apiMgmtUrlExtra'
registry_marker = "// ── Endpoint Registry"

tabs_start = html.find(tabs_marker)
if tabs_start < 0:
    raise SystemExit("tabs block not found")
tabs_end = html.find("</script>", tabs_start) + len("</script>")

reg_start = html.find(registry_marker)
reg_start = html.rfind("<script nonce=", tabs_end, reg_start)
reg_end = html.find("</script>", reg_start) + len("</script>")

replacement = (
    '<script src="{{ static_url(\'js/admin/api-management-tabs.js\') }}"></script>\n'
    + bootstrap
    + '\n<script src="{{ static_url(\'js/admin/api-management-registry.js\') }}"></script>\n'
)

new_html = html[:tabs_start] + replacement + html[reg_end:]
template.write_text(new_html, encoding="utf-8")
print("Updated", template)
