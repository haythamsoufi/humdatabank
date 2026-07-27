"""
Patch user_form.html to replace inline script blocks with config bootstrap + static JS reference.
"""

TEMPLATE_PATH = 'Backoffice/app/templates/admin/user_management/user_form.html'

with open(TEMPLATE_PATH, encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# Find all script blocks
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
    print(f"  Lines {s+1}-{e+1}")

# Find the first block that's before the hierarchical entity selector script src
# (line ~3148), which is a static script tag, not an inline block
# All nonce blocks should be replaced

# Also find the hierarchical-entity-selector.js include (static ref)
hier_line_idx = None
for i, ln in enumerate(lines):
    if 'hierarchical-entity-selector.js' in ln:
        hier_line_idx = i
        print(f"hierarchical-entity-selector.js at line {i+1}")
        break

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

# Replace all inline nonce script blocks with the config bootstrap only once (before first block)
# Keep all non-script content
# The first script block starts at script_blocks[0][0], last at script_blocks[-1][1]

first_block_start = script_blocks[0][0]
last_block_end = script_blocks[-1][1]

new_lines = (
    lines[:first_block_start] +
    config_bootstrap.split('\n') +
    lines[last_block_end+1:]
)

with open(TEMPLATE_PATH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print(f"\nDone. Template now has {len(new_lines)} lines (was {len(lines)})")
