"""
Patch manage_settings.html:
- Add config bootstrap
- Replace all nonce script blocks with static JS reference
"""

TEMPLATE_PATH = 'Backoffice/app/templates/admin/settings/manage_settings.html'

with open(TEMPLATE_PATH, encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
print(f"Total lines: {len(lines)}")

# Find all nonce script blocks
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
    print(f"  Lines {s+1}-{e+1}")

# First nonce block starts at script_blocks[0]
# Last nonce block ends at script_blocks[-1]
first_start = script_blocks[0][0]
last_end = script_blocks[-1][1]

config_bootstrap = '''<script nonce="{{ csp_nonce() }}">
window.settingsPageConfig = {
    appVersion: {{ config.APP_VERSION|tojson }},
    clientConsoleLogs: {{ config.CLIENT_CONSOLE_LOGGING|tojson }},
    brandingUploadEnabled: {{ (visual_branding_upload_available | default(false))|tojson }},
    currentSupported: {{ (current_supported or [])|tojson }},
    urls: {
        apiAiReset: {{ url_for('settings.api_ai_settings_reset')|tojson }},
        apiCheckUpdates: {{ url_for('settings.api_check_updates')|tojson }},
        emailPreview: {{ url_for('settings.api_settings_email_template_preview')|tojson }},
        emailTestSend: {{ url_for('settings.api_settings_email_template_test_send')|tojson }},
        emailSeed: {{ url_for('settings.api_settings_email_templates_seed')|tojson }},
        emailTemplates: {{ url_for('settings.api_settings_email_templates')|tojson }},
        tinymceBase: {{ url_for('static', filename='libs/tinymce')|tojson }},
        brandingUpload: {{ url_for('settings.branding_assets_upload')|tojson }},
        apiSettingsSave: {{ url_for('settings.api_settings_save')|tojson }}
    },
    t: {
        willBeClearedOnSave: {{ _('Will be cleared on save')|tojson }},
        enterNewValue: {{ _('Enter new value\u2026')|tojson }},
        expandAll: {{ _('Expand all')|tojson }},
        collapseAll: {{ _('Collapse all')|tojson }},
        resetAiConfirm: {{ _('Reset all AI settings to their defaults? This will remove all database-saved overrides.')|tojson }},
        resetFailed: {{ _('Reset failed.')|tojson }},
        networkError: {{ _('Network error.')|tojson }},
        resetBtn: {{ _('Reset')|tojson }},
        cancel: {{ _('Cancel')|tojson }},
        resetAiTitle: {{ _('Reset AI Settings?')|tojson }},
        selectUsers: {{ _('Select users\u2026')|tojson }},
        checkingText: {{ _('Checking\u2026')|tojson }},
        errorText: {{ _('Error')|tojson }},
        availableText: {{ _('available')|tojson }},
        upToDate: {{ _('Up to date')|tojson }},
        failedText: {{ _('Failed')|tojson }},
        updatesText: {{ _('Updates')|tojson }},
        priorityNormal: {{ _('Normal')|tojson }},
        priorityHigh: {{ _('High')|tojson }},
        priorityUrgent: {{ _('Urgent')|tojson }},
        priorityLow: {{ _('Low')|tojson }},
        audienceNaTitle: {{ _('Not applicable for this notification type (no delivery on this channel).')|tojson }},
        colGroup: {{ _('Group')|tojson }},
        colType: {{ _('Type')|tojson }},
        colRecipients: {{ _('Recipients')|tojson }},
        colFocalPoints: {{ _('Focal points')|tojson }},
        colOrgAdmins: {{ _('Org admins')|tojson }},
        colSystemManagers: {{ _('System managers')|tojson }},
        colTtl: {{ _('TTL')|tojson }},
        colPriority: {{ _('Priority')|tojson }},
        notifyFocalPoints: {{ _('Notify focal points (assignment editor/submitter)')|tojson }},
        notifyOrgAdmins: {{ _('Notify entity-assigned admins (admin_core / admin_*, not system managers)')|tojson }},
        notifySystemManagers: {{ _('Notify deployment-wide system managers')|tojson }},
        tinymceVarTip: {{ _('Click to switch: edit the template with Jinja placeholders, or see sample values (server-rendered preview, not saved).')|tojson }},
        variables: {{ _('Variables')|tojson }},
        couldNotLoadSampleValues: {{ _('Could not load sample values for this template.')|tojson }},
        addContentFirst: {{ _('Add some template content first, then show sample values.')|tojson }},
        seedConfirmForce: {{ _('Replace every email and notification template with the built-in defaults from this version? Custom HTML and pre-fill text will be lost.')|tojson }},
        templateHtml: {{ _('Template HTML')|tojson }},
        notificationPrefill: {{ _('Notification pre-fill')|tojson }},
        updatedFromDefaults: {{ _('updated from defaults')|tojson }},
        leftUnchanged: {{ _('left unchanged')|tojson }},
        enTemplateEmpty: {{ _('The English version of this template is empty. Add or save English text first, then try again.')|tojson }},
        noEmailAddr: {{ _('Your user account has no email address. Add one in your profile, then try again.')|tojson }},
        testEmailSent: {{ _('Test email sent to')|tojson }},
        testEmailFail: {{ _('Test email could not be sent. Check the message below or your mail settings.')|tojson }},
        editorLoadFailed: {{ _('The visual editor could not be loaded. Check your network, then refresh the page.')|tojson }},
        autoTranslateUnavailable: {{ _('Auto-translate is not available. Refresh the page and try again.')|tojson }},
        translationInvalidResponse: {{ _('Translation failed: invalid response from the server.')|tojson }},
        noTranslationReturned: {{ _('No translation was returned for this language.')|tojson }},
        translationRequestFailed: {{ _('Translation request failed.')|tojson }},
        noTemplateContent: {{ _('This language has no template content to send. Add HTML in the editor or pick another language tab.')|tojson }},
        couldNotPrepareEmailBody: {{ _('Could not prepare the email body.')|tojson }},
        networkErrorSendingEmail: {{ _('Network error while sending test email.')|tojson }},
        seedingCompleted: {{ _('Seeding completed.')|tojson }},
        seedingFailed: {{ _('Seeding failed')|tojson }},
        networkErrorSeeding: {{ _('Network error while seeding templates.')|tojson }},
        noChanges: {{ _('No settings were changed.')|tojson }},
        settingsSaved: {{ _('Settings saved successfully.')|tojson }},
        savingLabel: {{ _('Saving...')|tojson }}
    }
};
</script>
<script src="{{ static_url('js/admin/manage-settings.js') }}" nonce="{{ csp_nonce() }}"></script>'''

# Build new lines: keep everything before first script block, add config, then rest after last script block
new_lines = (
    lines[:first_start] +
    config_bootstrap.split('\n') +
    lines[last_end+1:]
)

with open(TEMPLATE_PATH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print(f"Done. Template now has {len(new_lines)} lines (was {len(lines)})")
