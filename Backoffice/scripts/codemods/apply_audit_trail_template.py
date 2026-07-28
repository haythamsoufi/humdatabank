#!/usr/bin/env python3
"""Replace inline scripts in audit_trail.html with static JS + bootstrap."""
from pathlib import Path

import migrate_template_js as mig

ROOT = Path(__file__).resolve().parents[2]
template = ROOT / "app/templates/admin/analytics/audit_trail.html"
html = template.read_text(encoding="utf-8")

scripts = mig.extract_scripts(html)
if not scripts:
    raise SystemExit("no scripts found")

combined_cfg = {"translations": {}, "urls": {}}
for _, _, content, is_mod in scripts:
    if is_mod:
        continue
    _, cfg = mig.build_bootstrap(content)
    combined_cfg["translations"].update(cfg["translations"])
    combined_cfg["urls"].update(cfg["urls"])

# Friendly URL keys used by audit-trail.js
combined_cfg["urls"] = {
    "auditTrail": '{{ url_for("analytics.audit_trail")|tojson }}',
    "sessionLogs": '{{ url_for("analytics.session_logs")|tojson }}',
}

bootstrap = mig.render_bootstrap_jinja(combined_cfg, "auditTrailConfig")
# Inject pageData from server
bootstrap = bootstrap.replace(
    "</script>",
    "window.auditTrailConfig.pageData = {{ audit_trail_page_data|tojson }};\n</script>",
    1,
)

new_html = html
for start, end, _, is_mod in reversed(scripts):
    if not is_mod:
        new_html = new_html[:start] + new_html[end:]

first_start = min(s[0] for s in scripts if not s[3])
injection = (
    '\n<script src="{{ static_url(\'js/components/multiselect-dropdown.js\') }}"></script>\n'
)
new_html = new_html[:first_start] + injection + new_html[first_start:]

# Replace extra_js block tail: find extra_js and append bootstrap + src after ag_grid_js()
marker = "{{ ag_grid_js() }}"
if marker not in new_html:
    raise SystemExit("ag_grid_js marker missing")
extra = (
    "\n"
    + bootstrap
    + '\n<script src="{{ static_url(\'js/admin/audit-trail.js\') }}"></script>\n'
)
new_html = new_html.replace(marker, marker + extra, 1)

template.write_text(new_html, encoding="utf-8")
print("Updated", template)
