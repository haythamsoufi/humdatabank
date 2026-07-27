"""
Extract inline JS from user_form.html into user-form.js.
"""
import re

TEMPLATE_PATH = 'Backoffice/app/templates/admin/user_management/user_form.html'
OUTPUT_JS_PATH = 'Backoffice/app/static/js/admin/user-form.js'

with open(TEMPLATE_PATH, encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# Find all script blocks (nonce ones with actual JS)
script_blocks = []
current_start = None
for i, ln in enumerate(lines):
    if '<script nonce=' in ln and current_start is None:
        current_start = i
    elif '</script>' in ln and current_start is not None:
        script_blocks.append((current_start, i))
        current_start = None

print(f"Found {len(script_blocks)} script blocks:")
for s, e in script_blocks:
    print(f"  Lines {s+1}-{e+1} ({e-s} lines)")

# --- Transformation rules ---
TRANS_MAP = {
    "{{ _('Are you sure you want to deactivate this user? They will not be able to log in.')|tojson|safe }}": 'cfg.t.deactivateConfirm',
    "{{ _('Are you sure you want to reactivate this user?')|tojson|safe }}": 'cfg.t.reactivateConfirm',
    "{{ _('Deactivate')|tojson|safe }}": 'cfg.t.deactivate',
    "{{ _('Cancel')|tojson|safe }}": 'cfg.t.cancel',
    "{{ _('Deactivate User?')|tojson|safe }}": 'cfg.t.deactivateUser',
    "{{ _('Could not load preview') }}": '" + cfg.t.couldNotLoadPreview + "',
    '{{ _("Could not load preview") }}': '" + cfg.t.couldNotLoadPreview + "',
    "{{ _('Could not load preview')|tojson|safe }}": 'cfg.t.couldNotLoadPreview',
    '{{ _("Loading...") }}': '" + cfg.t.loadingText + "',
    '{{ _("No related deletions detected.") }}': '" + cfg.t.noRelatedDeletions + "',
    '{{ _("will be unassigned") }}': '" + cfg.t.willBeUnassigned + "',
    '{{ _("The following will be unassigned (kept for history):") }}': '" + cfg.t.followingUnassigned + "',
    '{{ _("Failed to load preview.") }}': '" + cfg.t.failedToLoadPreview + "',
    '{{ _("Deleting...") }}': '" + cfg.t.deletingText + "',
    '{{ _("Your session has expired.") }}': '" + cfg.t.sessionExpired + "',
    '{{ _("Please log in again to reload analytics.") }}': '" + cfg.t.pleaseLogIn + "',
    '{{ _("Log in") }}': '" + cfg.t.logIn + "',
    '{{ _("Failed to load analytics.") }}': '" + cfg.t.failedToLoadAnalytics + "',
    '{{ _("Loading analytics...") }}': '" + cfg.t.loadingAnalytics + "',
    '{{ _("Failed to load analytics.") }}': '" + cfg.t.failedToLoadAnalytics + "',
}

URL_MAP = {
    '{{ url_for("auth.login") }}': '" + cfg.urls.loginUrl + "',
}

def transform_block(js_lines):
    result = []
    i = 0
    while i < len(js_lines):
        line = js_lines[i]

        # READ_ONLY
        line = line.replace(
            'const READ_ONLY = {{ (read_only or roles_read_only)|tojson|safe }};',
            'const READ_ONLY = cfg.readOnly;'
        )

        # userDeletionPreviewUrl
        line = re.sub(
            r'const userDeletionPreviewUrl = \{%.*?%\};',
            'const userDeletionPreviewUrl = cfg.urls.deletionPreview;',
            line
        )

        # isActive
        line = line.replace(
            'const isActive = {{ (user.active if user else false)|tojson|safe }};',
            'const isActive = cfg.isActive;'
        )

        # Translation replacements
        for jinja_expr, js_expr in TRANS_MAP.items():
            line = line.replace(jinja_expr, js_expr)

        # URL replacements
        for jinja_expr, js_expr in URL_MAP.items():
            line = line.replace(jinja_expr, js_expr)

        # targetUserId
        line = re.sub(
            r'targetUserId: \{%.*?%\},',
            'targetUserId: cfg.userId,',
            line
        )

        # defaultCountryId
        line = re.sub(
            r'const defaultCountryId = \{%.*?%\};',
            'const defaultCountryId = cfg.defaultCountryId;',
            line
        )

        # user.id direct references (remaining)
        line = re.sub(r'\{\{ user\.id \}\}', 'cfg.userId', line)

        # Jinja conditionals
        stripped = line.strip()
        if stripped == '{% if user %}':
            indent = len(line) - len(line.lstrip())
            result.append(' ' * indent + 'if (cfg.userId) {')
            i += 1
            continue
        elif stripped == '{% if not user %}':
            indent = len(line) - len(line.lstrip())
            result.append(' ' * indent + 'if (!cfg.userId) {')
            i += 1
            continue
        elif stripped == '{% endif %}':
            indent = len(line) - len(line.lstrip())
            result.append(' ' * indent + '}')
            i += 1
            continue
        elif stripped == '{% else %}':
            indent = len(line) - len(line.lstrip())
            result.append(' ' * indent + '} else {')
            i += 1
            continue
        elif stripped.startswith('{%- for country in user.countries'):
            # Replace with cfg.userCountryIds
            result.append('        const userCountryIds = new Set(cfg.userCountryIds || []);')
            i += 1
            while i < len(js_lines) and 'endfor' not in js_lines[i]:
                i += 1
            i += 1  # skip endfor
            continue

        result.append(line)
        i += 1
    return result

# Collect and transform all blocks
all_blocks_js = []
for idx, (s, e) in enumerate(script_blocks):
    js_content = lines[s+1:e]
    transformed = transform_block(js_content)
    all_blocks_js.append((idx+1, s, e, transformed))

# Write static JS file
output_lines = [
    '/* Auto-generated from user_form.html — DO NOT edit template inline JS */',
    '/* Config is bootstrapped via window.userFormConfig in the template */',
    '',
    '(function () {',
    "    'use strict';",
    '    var cfg = window.userFormConfig || {};',
    '',
]

for block_num, s, e, transformed in all_blocks_js:
    output_lines.append(f'    // --- Block {block_num} (original lines {s+1}-{e+1}) ---')
    output_lines.extend(transformed)
    output_lines.append('')

output_lines.append('}());')

with open(OUTPUT_JS_PATH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(output_lines))

print(f"\nWritten {len(output_lines)} lines to {OUTPUT_JS_PATH}")

# Check for remaining Jinja
remaining = [(i+1, l) for i, l in enumerate(output_lines) if '{{' in l or '{%' in l]
print(f"Remaining Jinja lines: {len(remaining)}")
for ln, l in remaining[:20]:
    print(f"  {ln}: {l.strip()[:100]}")

# --- Build template replacement ---
config_bootstrap = '''<script nonce="{{ csp_nonce() }}">
window.userFormConfig = {
    userId: {{ user.id if user else 'null' }},
    isNew: {{ 'true' if not user else 'false' }},
    isActive: {{ (user.active if user else false)|tojson }},
    readOnly: {{ (read_only or roles_read_only)|tojson }},
    defaultCountryId: {{ (user.countries.first().id if user and user.countries.first() else none)|tojson }},
    userCountryIds: [{% if user %}{%- for country in user.countries -%}{{ country.id }}{%- if not loop.last -%},{%- endif -%}{%- endfor -%}{% endif %}],
    urls: {
        deletionPreview: {% if user %}{{ url_for('user_management.user_deletion_preview', user_id=user.id)|tojson }}{% else %}null{% endif %},
        loginUrl: {{ url_for('auth.login')|tojson }}
    },
    t: {
        deactivate: {{ _('Deactivate')|tojson }},
        cancel: {{ _('Cancel')|tojson }},
        deactivateUser: {{ _('Deactivate User?')|tojson }},
        deactivateConfirm: {{ _('Are you sure you want to deactivate this user? They will not be able to log in.')|tojson }},
        reactivateConfirm: {{ _('Are you sure you want to reactivate this user?')|tojson }},
        couldNotLoadPreview: {{ _('Could not load preview')|tojson }},
        loadingText: {{ _('Loading...')|tojson }},
        noRelatedDeletions: {{ _('No related deletions detected.')|tojson }},
        willBeUnassigned: {{ _('will be unassigned')|tojson }},
        followingUnassigned: {{ _('The following will be unassigned (kept for history):')|tojson }},
        failedToLoadPreview: {{ _('Failed to load preview.')|tojson }},
        deletingText: {{ _('Deleting...')|tojson }},
        sessionExpired: {{ _("Your session has expired.")|tojson }},
        pleaseLogIn: {{ _("Please log in again to reload analytics.")|tojson }},
        logIn: {{ _("Log in")|tojson }},
        failedToLoadAnalytics: {{ _("Failed to load analytics.")|tojson }},
        loadingAnalytics: {{ _("Loading analytics...")|tojson }}
    }
};
</script>
<script src="{{ static_url('js/admin/user-form.js') }}" nonce="{{ csp_nonce() }}"></script>'''

print("\nConfig bootstrap:")
print(config_bootstrap[:300])
print(f"\nTotal bootstrap lines: {len(config_bootstrap.splitlines())}")
