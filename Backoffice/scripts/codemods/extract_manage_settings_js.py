"""
Extract inline JS from manage_settings.html into manage-settings.js.
"""
import re

TEMPLATE_PATH = 'Backoffice/app/templates/admin/settings/manage_settings.html'
OUTPUT_JS_PATH = 'Backoffice/app/static/js/admin/manage-settings.js'

with open(TEMPLATE_PATH, encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
print(f"Total lines: {len(lines)}")

# Find all nonce script blocks (not json/module blocks, not src blocks)
script_blocks = []
current_start = None
for i, ln in enumerate(lines):
    if '<script nonce=' in ln and current_start is None:
        current_start = i
    elif '</script>' in ln and current_start is not None:
        script_blocks.append((current_start, i))
        current_start = None

print(f"Nonce script blocks: {len(script_blocks)}")
for s, e in script_blocks:
    jinja_count = sum(1 for l in lines[s+1:e] if '{{' in l or '{%' in l)
    print(f"  Lines {s+1}-{e+1} ({e-s} lines, {jinja_count} Jinja)")

# Build a comprehensive translation map
TRANS_REPLACEMENTS = [
    # Exact string replacements: (old_pattern, new_js_expression)
    # Block 1749-1891
    ('var L_PW_WILL_CLEAR = {{ _("Will be cleared on save") | tojson }};', 'var L_PW_WILL_CLEAR = cfg.t.willBeClearedOnSave;'),
    ('var L_PW_ENTER_NEW = {{ _("Enter new value\u2026") | tojson }};', 'var L_PW_ENTER_NEW = cfg.t.enterNewValue;'),
    ("toggleBtn.textContent = anyOpen ? '{{ _(\"Expand all\") }}' : '{{ _(\"Collapse all\") }}';",
     "toggleBtn.textContent = anyOpen ? cfg.t.expandAll : cfg.t.collapseAll;"),
    ("var msg = '{{ _(\"Reset all AI settings to their defaults? This will remove all database-saved overrides. Continue?\") }}';",
     'var msg = cfg.t.resetAiConfirm;'),
    ("((window.getFetch && window.getFetch()) || fetch)('{{ url_for(\"settings.api_ai_settings_reset\") }}'",
     "((window.getFetch && window.getFetch()) || fetch)(cfg.urls.apiAiReset"),
    ("if (window.showAlert) window.showAlert(data.message || '{{ _(\"Reset failed.\") }}', 'error');",
     "if (window.showAlert) window.showAlert(data.message || cfg.t.resetFailed, 'error');"),
    ("if (window.showAlert) window.showAlert('{{ _(\"Network error.\") }}', 'error');",
     "if (window.showAlert) window.showAlert(cfg.t.networkError, 'error');"),
    ("window.showConfirmation(msg, doReset, null, '{{ _(\"Reset\") }}', '{{ _(\"Cancel\") }}', '{{ _(\"Reset AI Settings\") }}'",
     "window.showConfirmation(msg, doReset, null, cfg.t.resetBtn, cfg.t.cancel, cfg.t.resetAiTitle"),
    # Block 1893-1941
    ("placeholder: '{{ _(\"Select users\u2026\") }}',", "placeholder: cfg.t.selectUsers,"),
    # Block 1943-2004
    ("btn.innerHTML = '<i class=\"fas fa-spinner fa-spin text-[10px]\"></i> {{ _(\"Checking\u2026\") }}';",
     "btn.innerHTML = '<i class=\"fas fa-spinner fa-spin text-[10px]\"></i> ' + cfg.t.checkingText + '';"),
    ("((window.getFetch && window.getFetch()) || fetch)('{{ url_for(\"settings.api_check_updates\") }}')",
     "((window.getFetch && window.getFetch()) || fetch)(cfg.urls.apiCheckUpdates)"),
    ("btn.innerHTML = '<i class=\"fas fa-exclamation-triangle text-[10px] text-amber-500\"></i> {{ _(\"Error\u2026\") }}';",
     "btn.innerHTML = '<i class=\"fas fa-exclamation-triangle text-[10px] text-amber-500\"></i> ' + cfg.t.errorText + '';"),
    ("'<span class=\"text-xs text-gray-500\">v{{ config.APP_VERSION }}</span>' +",
     "'<span class=\"text-xs text-gray-500\">v' + (cfg.appVersion || '') + '</span>' +"),
    ("'<i class=\"fas fa-arrow-up text-[10px]\"></i> v' + esc(data.latest_version) + ' {{ _(\"available\") }}'",
     "'<i class=\"fas fa-arrow-up text-[10px]\"></i> v' + esc(data.latest_version) + ' ' + cfg.t.availableText"),
    ("btn.innerHTML = '<i class=\"fas fa-check text-[10px] text-green-600\"></i> {{ _(\"Up to date\") }}';",
     "btn.innerHTML = '<i class=\"fas fa-check text-[10px] text-green-600\"></i> ' + cfg.t.upToDate + '';"),
    ("btn.innerHTML = '<i class=\"fas fa-exclamation-triangle text-[10px] text-amber-500\"></i> {{ _(\"Failed\u2026\") }}';",
     "btn.innerHTML = '<i class=\"fas fa-exclamation-triangle text-[10px] text-amber-500\"></i> ' + cfg.t.failedText + '';"),
    ("btn.innerHTML = '<i class=\"fas fa-sync-alt text-[10px]\"></i> {{ _(\"Updates\") }}';",
     "btn.innerHTML = '<i class=\"fas fa-sync-alt text-[10px]\"></i> ' + cfg.t.updatesText + '';"),
    # Block 2489-2732
    ("var order = pinBase({{ (current_supported or []) | tojson }});",
     "var order = pinBase(cfg.currentSupported || []);"),
    # Block 2735-4120
    ("var EMAIL_PREVIEW_URL = {{ url_for('settings.api_settings_email_template_preview') | tojson }};",
     "var EMAIL_PREVIEW_URL = cfg.urls.emailPreview;"),
    ("var EMAIL_TEST_SEND_URL = {{ url_for('settings.api_settings_email_template_test_send') | tojson }};",
     "var EMAIL_TEST_SEND_URL = cfg.urls.emailTestSend;"),
    ("var L_TINYMCE_VAR_TIP = {{ _('Click to switch: edit the template with Jinja placeholders, or see sample values rendered.') | tojson }};",
     "var L_TINYMCE_VAR_TIP = cfg.t.tinymceVarTip;"),
    ("var L_TINYMCE_VAR_BTN = {{ _('Variables') | tojson }};",
     "var L_TINYMCE_VAR_BTN = cfg.t.variables;"),
    ("var MSG_TINYMCE_VAR_PREVIEW_FAIL = {{ _('Could not load sample values for this template.') | tojson }};",
     "var MSG_TINYMCE_VAR_PREVIEW_FAIL = cfg.t.couldNotLoadSampleValues;"),
    ("var MSG_TINYMCE_VAR_PREVIEW_EMPTY = {{ _('Add some template content first, then show sample values.') | tojson }};",
     "var MSG_TINYMCE_VAR_PREVIEW_EMPTY = cfg.t.addContentFirst;"),
    ("var EMAIL_SEED_URL = {{ url_for('settings.api_settings_email_templates_seed') | tojson }};",
     "var EMAIL_SEED_URL = cfg.urls.emailSeed;"),
    ("var MSG_SEED_CONFIRM_FORCE = {{ _('Replace every email and notification template with the built-in defaults? This will overwrite custom changes.') | tojson }};",
     "var MSG_SEED_CONFIRM_FORCE = cfg.t.seedConfirmForce;"),
    ("var L_SEED_BODIES = {{ _('Template HTML') | tojson }};", "var L_SEED_BODIES = cfg.t.templateHtml;"),
    ("var L_SEED_PREFILL = {{ _('Notification pre-fill') | tojson }};", "var L_SEED_PREFILL = cfg.t.notificationPrefill;"),
    ("var L_SEED_UPD = {{ _('updated from defaults') | tojson }};", "var L_SEED_UPD = cfg.t.updatedFromDefaults;"),
    ("var L_SEED_LEFT = {{ _('left unchanged') | tojson }};", "var L_SEED_LEFT = cfg.t.leftUnchanged;"),
    ("var MSG_EMAIL_AUTOTRANS_EN_EMPTY = {{ _('The English version of this template is empty. Add or save some content first.') | tojson }};",
     "var MSG_EMAIL_AUTOTRANS_EN_EMPTY = cfg.t.enTemplateEmpty;"),
    ("var MSG_TEST_EMAIL_NO_ADDR = {{ _('Your user account has no email address. Add one in your profile, then try again.') | tojson }};",
     "var MSG_TEST_EMAIL_NO_ADDR = cfg.t.noEmailAddr;"),
    ("var MSG_TEST_EMAIL_SENT = {{ _('Test email sent to') | tojson }};",
     "var MSG_TEST_EMAIL_SENT = cfg.t.testEmailSent;"),
    ("var MSG_TEST_EMAIL_FAIL = {{ _('Test email could not be sent. Check the message below or your mail server settings.') | tojson }};",
     "var MSG_TEST_EMAIL_FAIL = cfg.t.testEmailFail;"),
    ("var TINYMCE_BASE_URL = {{ url_for('static', filename='libs/tinymce')|tojson }};",
     "var TINYMCE_BASE_URL = cfg.urls.tinymceBase;"),
    ("window.showAlert({{ _('The visual editor could not be loaded. Check your network, then refresh the page.') | tojson }}, 'error');",
     "window.showAlert(cfg.t.editorLoadFailed, 'error');"),
    ("var msg = {{ _('Auto-translate is not available. Refresh the page and try again.') | tojson }};",
     "var msg = cfg.t.autoTranslateUnavailable;"),
    ("{{ _('Translation failed: invalid response from the server.') | tojson }},",
     "cfg.t.translationInvalidResponse,"),
    ("(res && res.message) || {{ _('No translation was returned for this language.') | tojson }},",
     "(res && res.message) || cfg.t.noTranslationReturned,"),
    ("(err && err.message) || {{ _('Translation request failed.') | tojson }},",
     "(err && err.message) || cfg.t.translationRequestFailed,"),
    ("window.showAlert({{ _('This language has no template content to send. Add HTML in the editor or pick another language.') | tojson }}, 'warning');",
     "window.showAlert(cfg.t.noTemplateContent, 'warning');"),
    ("if (window.showAlert) window.showAlert({{ _('Could not prepare the email body.') | tojson }}, 'error');",
     "if (window.showAlert) window.showAlert(cfg.t.couldNotPrepareEmailBody, 'error');"),
    ("if (window.showAlert) window.showAlert({{ _('Network error while sending test email.') | tojson }}, 'error');",
     "if (window.showAlert) window.showAlert(cfg.t.networkErrorSendingEmail, 'error');"),
    ("var line = describeSeedStats(r.payload.stats) || {{ _('Seeding completed.') | tojson }};",
     "var line = describeSeedStats(r.payload.stats) || cfg.t.seedingCompleted;"),
    ("if (window.showAlert) window.showAlert({{ _('Network error while seeding templates.') | tojson }}, 'error');",
     "if (window.showAlert) window.showAlert(cfg.t.networkErrorSeeding, 'error');"),
    # Block 4185-4724
    ("var _clientLogFallback = {{ config.CLIENT_CONSOLE_LOGGING | tojson }};",
     "var _clientLogFallback = cfg.clientConsoleLogs || false;"),
    ("var noChangesMsg = {{ _('No settings were changed.') | tojson }};",
     "var noChangesMsg = cfg.t.noChanges;"),
    ("var emailSavedMsg = {{ _('Settings saved successfully.') | tojson }};",
     "var emailSavedMsg = cfg.t.settingsSaved;"),
    ("var savingLabel = {{ _('Saving...') | tojson }};",
     "var savingLabel = cfg.t.savingLabel;"),
    ("var BRANDING_UPLOAD_URL = {{ url_for('settings.branding_assets_upload') | tojson }};",
     "var BRANDING_UPLOAD_URL = cfg.urls.brandingUpload;"),
    ("var BRANDING_UPLOAD_ENABLED = {{ (visual_branding_upload_available | default(false)) | tojson }};",
     "var BRANDING_UPLOAD_ENABLED = cfg.brandingUploadEnabled || false;"),
]

def transform_js(js_lines):
    result = []
    for line in js_lines:
        for old, new in TRANS_REPLACEMENTS:
            if old in line:
                line = line.replace(old, new)
        result.append(line)
    return result

# Collect all nonce blocks and transform
all_blocks_js = []
for idx, (s, e) in enumerate(script_blocks):
    js_content = lines[s+1:e]
    transformed = transform_js(js_content)
    all_blocks_js.append((idx+1, s, e, transformed))

# Write static JS file
output_lines = [
    '/* Auto-generated from manage_settings.html — DO NOT edit template inline JS */',
    '/* Config is bootstrapped via window.settingsPageConfig in the template */',
    '',
    '(function () {',
    "    'use strict';",
    '    var cfg = window.settingsPageConfig || {};',
    '',
]
for block_num, s, e, transformed in all_blocks_js:
    output_lines.append(f'    // --- Block {block_num} (original lines {s+1}-{e+1}) ---')
    output_lines.extend(transformed)
    output_lines.append('')

output_lines.append('}());')

with open(OUTPUT_JS_PATH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(output_lines))

print(f"Written {len(output_lines)} lines to {OUTPUT_JS_PATH}")

remaining = [(i+1, l) for i, l in enumerate(output_lines) if '{{' in l or '{%' in l]
print(f"Remaining Jinja: {len(remaining)}")
for ln, l in remaining[:20]:
    print(f"  {ln}: {l.strip()[:100]}")
