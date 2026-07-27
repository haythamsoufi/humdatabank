"""Fix remaining Jinja in manage-settings.js - second pass"""

JS_PATH = 'Backoffice/app/static/js/admin/manage-settings.js'

with open(JS_PATH, encoding='utf-8') as f:
    content = f.read()

FIXES = [
    # audienceCheckbox with full text
    ("audienceCheckbox('na_fp_', 'focal_points', 'audience_focal_points', {{ _('Notify focal points (assignment editor/submitter)')|tojson }})",
     "audienceCheckbox('na_fp_', 'focal_points', 'audience_focal_points', cfg.t.notifyFocalPoints)"),
    ("audienceCheckbox('na_au_', 'admin_users', 'audience_admin_users', {{ _('Notify entity-assigned admins (admin role on this entity)')|tojson }})",
     "audienceCheckbox('na_au_', 'admin_users', 'audience_admin_users', cfg.t.notifyOrgAdmins)"),
    ("audienceCheckbox('na_sm_', 'system_managers', 'audience_system_managers', {{ _('Notify deployment-wide system managers')|tojson }})",
     "audienceCheckbox('na_sm_', 'system_managers', 'audience_system_managers', cfg.t.notifySystemManagers)"),
    # Failed text (no ellipsis, just "Failed")
    ('btn.innerHTML = \'<i class="fas fa-exclamation-triangle text-[10px] text-amber-500"></i> {{ _("Failed") }}\';',
     "btn.innerHTML = '<i class=\"fas fa-exclamation-triangle text-[10px] text-amber-500\"></i> ' + cfg.t.failedText + '';"),
    # Long translation strings
    ("var L_TINYMCE_VAR_TIP = {{ _('Click to switch: edit the template with Jinja placeholders, or see sample values rendered.') | tojson }};",
     "var L_TINYMCE_VAR_TIP = cfg.t.tinymceVarTip;"),
    ("var MSG_SEED_CONFIRM_FORCE = {{ _('Replace every email and notification template with the built-in defaults? This will overwrite custom changes.') | tojson }};",
     "var MSG_SEED_CONFIRM_FORCE = cfg.t.seedConfirmForce;"),
    ("var MSG_EMAIL_AUTOTRANS_EN_EMPTY = {{ _('The English version of this template is empty. Add or save some content first.') | tojson }};",
     "var MSG_EMAIL_AUTOTRANS_EN_EMPTY = cfg.t.enTemplateEmpty;"),
    ("var MSG_TEST_EMAIL_FAIL = {{ _('Test email could not be sent. Check the message below or your mail server settings.') | tojson }};",
     "var MSG_TEST_EMAIL_FAIL = cfg.t.testEmailFail;"),
    ("window.showAlert({{ _('This language has no template content to send. Add HTML in the editor or pick another language.') | tojson }}, 'warning');",
     "window.showAlert(cfg.t.noTemplateContent, 'warning');"),
    # api_settings_email_templates URL
    ("var resp = await ((window.getFetch && window.getFetch()) || fetch)('{{ url_for(\"settings.api_settings_email_templates\") }}', {",
     "var resp = await ((window.getFetch && window.getFetch()) || fetch)(cfg.urls.apiEmailTemplates, {"),
]

for old, new in FIXES:
    if old in content:
        content = content.replace(old, new)
        print(f"Fixed: {old[:60]}...")
    else:
        print(f"NOT FOUND: {repr(old[:80])}")

# Check remaining Jinja
lines = content.split('\n')
remaining = [(i+1, l) for i, l in enumerate(lines) if '{{' in l or '{%' in l]
print(f"\nRemaining Jinja: {len(remaining)}")
for ln, l in remaining[:20]:
    print(f"  {ln}: {repr(l.strip()[:100])}")

with open(JS_PATH, 'w', encoding='utf-8') as f:
    f.write(content)
print("\nDone")
