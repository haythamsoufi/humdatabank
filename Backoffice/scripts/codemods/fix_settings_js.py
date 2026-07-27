"""Fix remaining Jinja in manage-settings.js"""

JS_PATH = 'Backoffice/app/static/js/admin/manage-settings.js'

with open(JS_PATH, encoding='utf-8') as f:
    content = f.read()

FIXES = [
    # Block 1 (notification grid)
    ("normal: {{ _('Normal')|tojson }},", "normal: cfg.t.priorityNormal,"),
    ("high: {{ _('High')|tojson }},", "high: cfg.t.priorityHigh,"),
    ("urgent: {{ _('Urgent')|tojson }},", "urgent: cfg.t.priorityUrgent,"),
    ("low: {{ _('Low')|tojson }}", "low: cfg.t.priorityLow"),
    ("var AUDIENCE_NA_TITLE = {{ _('Not applicable for this notification type (no delivery on this channel).')|tojson }};",
     "var AUDIENCE_NA_TITLE = cfg.t.audienceNaTitle;"),
    ("headerName: {{ _('Group')|tojson }},", "headerName: cfg.t.colGroup,"),
    ("headerName: {{ _('Type')|tojson }},", "headerName: cfg.t.colType,"),
    ("headerName: {{ _('Recipients')|tojson }},", "headerName: cfg.t.colRecipients,"),
    ("headerName: {{ _('Focal points')|tojson }},", "headerName: cfg.t.colFocalPoints,"),
    ("headerName: {{ _('Org admins')|tojson }},", "headerName: cfg.t.colOrgAdmins,"),
    ("headerName: {{ _('System managers')|tojson }},", "headerName: cfg.t.colSystemManagers,"),
    ("headerName: {{ _('TTL')|tojson }},", "headerName: cfg.t.colTtl,"),
    ("headerName: {{ _('Priority')|tojson }},", "headerName: cfg.t.colPriority,"),
    # audienceCheckbox calls
    ("audienceCheckbox('na_fp_', 'focal_points', 'audience_focal_points', {{ _('Notify focal points (assignment contacts)') | tojson }}",
     "audienceCheckbox('na_fp_', 'focal_points', 'audience_focal_points', cfg.t.notifyFocalPoints"),
    ("audienceCheckbox('na_au_', 'admin_users', 'audience_admin_users', {{ _('Notify entity-assigned admins (admin role on this entity)') | tojson }}",
     "audienceCheckbox('na_au_', 'admin_users', 'audience_admin_users', cfg.t.notifyOrgAdmins"),
    ("audienceCheckbox('na_sm_', 'system_managers', 'audience_system_managers', {{ _('Notify deployment-wide system managers') | tojson }}",
     "audienceCheckbox('na_sm_', 'system_managers', 'audience_system_managers', cfg.t.notifySystemManagers"),
    # Block 1749 - reset AI (different text from template)
    ("var msg = '{{ _(\"Reset all AI settings to their defaults? This will remove all database-saved overrides.\") }}';",
     "var msg = cfg.t.resetAiConfirm;"),
    ("window.showConfirmation(msg, doReset, null, '{{ _(\"Reset\") }}', '{{ _(\"Cancel\") }}', '{{ _(\"Reset AI Settings?\") }}');",
     "window.showConfirmation(msg, doReset, null, cfg.t.resetBtn, cfg.t.cancel, cfg.t.resetAiTitle);"),
    # Block 1943 - Error/Failed unicode variants
    ('btn.innerHTML = \'<i class="fas fa-exclamation-triangle text-[10px] text-amber-500"></i> {{ _("Error") }}\';',
     "btn.innerHTML = '<i class=\"fas fa-exclamation-triangle text-[10px] text-amber-500\"></i> ' + cfg.t.errorText + '';"),
    # Handle the Failed... case
    ('btn.innerHTML = \'<i class="fas fa-exclamation-triangle text-[10px] text-amber-500"></i> {{ _("Failed\u2026") }}\';',
     "btn.innerHTML = '<i class=\"fas fa-exclamation-triangle text-[10px] text-amber-500\"></i> ' + cfg.t.failedText + '';"),
    # Also handle the variant with unicode in single-quoted JS string
]

for old, new in FIXES:
    if old in content:
        content = content.replace(old, new)
        print(f"Fixed: {old[:60]}...")
    else:
        print(f"NOT FOUND: {old[:60]}...")

# Check remaining Jinja
lines = content.split('\n')
remaining = [(i+1, l) for i, l in enumerate(lines) if '{{' in l or '{%' in l]
print(f"\nRemaining Jinja: {len(remaining)}")
for ln, l in remaining[:20]:
    print(f"  {ln}: {repr(l.strip()[:100])}")

with open(JS_PATH, 'w', encoding='utf-8') as f:
    f.write(content)
print("\nDone")
