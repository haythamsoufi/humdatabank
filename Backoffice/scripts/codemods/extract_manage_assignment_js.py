"""
Extract inline JS from manage_assignment.html into manage-assignment.js.
Creates a JSON data block for entityManagementData and a config bootstrap.
"""
import re

TEMPLATE_PATH = 'Backoffice/app/templates/admin/assignments/manage_assignment.html'
OUTPUT_JS_PATH = 'Backoffice/app/static/js/admin/manage-assignment.js'

with open(TEMPLATE_PATH, encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# ------------------------------------------------------------------
# 1. Find the first script block (line 772 to the closing </script> at line 3450)
#    Find indices
# ------------------------------------------------------------------
def find_script_block_range(lines, search_text, start_from=0):
    start = None
    for i, ln in enumerate(lines):
        if i < start_from:
            continue
        if '<script nonce=' in ln and start is None:
            start = i
        elif '</script>' in ln and start is not None:
            return start, i
    return None, None

# First inline script block (line 772 in 1-indexed = index 771)
main_start, main_end = find_script_block_range(lines, '<script nonce=', start_from=771)
print(f"Main script block: lines {main_start+1} to {main_end+1}")

# Second inline script block (around line 3526)
second_start, second_end = find_script_block_range(lines, '<script nonce=', start_from=3525)
print(f"Second script block: lines {second_start+1} to {second_end+1}")

# ------------------------------------------------------------------
# 2. Extract the JS content from both blocks
# ------------------------------------------------------------------
main_js_lines = lines[main_start+1:main_end]  # exclude <script> and </script> lines
second_js_lines = lines[second_start+1:second_end]

# ------------------------------------------------------------------
# 3. Transform the JS content
#    Replace Jinja expressions with cfg.xxx references
# ------------------------------------------------------------------

def transform_js(js_lines):
    result = []
    i = 0
    in_entity_data_block = False
    skip_until_end_for = False
    skip_until_end_if = 0

    # Translation mapping: Jinja tojson expression → config key
    TRANS_MAP = {
        "{{ _('Remove')|tojson }}": 'cfg.t.remove',
        "{{ _('Cancel')|tojson }}": 'cfg.t.cancel',
        "{{ _('Remove entities')|tojson }}": 'cfg.t.removeEntities',
        "{{ _('Confirm')|tojson }}": 'cfg.t.confirm',
        "{{ _('Public reporting')|tojson }}": 'cfg.t.publicReporting',
        "{{ _('Create anyway')|tojson }}": 'cfg.t.createAnyway',
        "{{ _('Duplicate assignment')|tojson }}": 'cfg.t.duplicateAssignment',
        "{{ _('Create assignment')|tojson }}": 'cfg.t.createAssignment',
        "{{ _('Continue')|tojson }}": 'cfg.t.continueBtn',
        "{{ _('This assignment will be created without sending notifications to assigned entities. Do you want to continue?')|tojson }}": 'cfg.t.noNotifyMsg',
        "{{ _('Assigned entities (focal points) will be notified about this new assignment. Do you want to continue?')|tojson }}": 'cfg.t.notifyMsg',
        "{{ _('Confirm action')|tojson }}": 'cfg.t.confirmAction',
    }

    URL_MAP = {
        "{{ url_for('organization.api_get_part_of_programs') }}": 'cfg.urls.apiPartOfPrograms',
        "{{ url_for('organization.index') }}": 'cfg.urls.organizationIndex',
        "{{ url_for('assignment_management.check_assignment_duplicate') }}": 'cfg.urls.checkDuplicate',
        "{{ url_for('system_admin.manage_indicator_bank') | replace('/indicator-bank', '') }}": 'cfg.urls.adminBase',
    }

    while i < len(js_lines):
        line = js_lines[i]

        # Skip entity management data block (will be replaced with JSON script block read)
        if '// Transform assignment entities data for ag-grid' in line:
            # Skip until we find the end of the array (];)
            in_entity_data_block = True
            i += 1
            continue
        if in_entity_data_block:
            if line.strip() == '];':
                in_entity_data_block = False
                # Insert replacement code to read from JSON block
                result.append('        const entityManagementData = (function() {')
                result.append('            var el = document.getElementById(\'entity-management-data\');')
                result.append('            if (!el) return [];')
                result.append('            try { return JSON.parse(el.textContent || \'[]\'); } catch(e) { return []; }')
                result.append('        })();')
            i += 1
            continue

        # Replace assignment.id inline URL patterns
        line = re.sub(
            r'/admin/assignments/\{\{ assignment\.id \}\}/',
            "' + '/admin/assignments/' + cfg.assignmentId + '/",
            line
        )
        # Fix double-quoted string wrapping when we added concat
        # Pattern: fetch('/admin/assignments/' + cfg.assignmentId + '/entities/...',
        # The original was: fetch('/admin/assignments/{{ assignment.id }}/entities/...',
        # After replacement: fetch(' + '/admin/assignments/' + cfg.assignmentId + '/entities/...',
        # We need to clean up the leading quote:
        line = line.replace("fetch(' + '/admin/assignments/'", "fetch('/admin/assignments/'")
        line = line.replace("form.action = ' + '/admin/assignments/'", "form.action = '/admin/assignments/'")

        # targetAssignmentId
        line = line.replace('targetAssignmentId: {{ assignment.id }},', 'targetAssignmentId: cfg.assignmentId,')

        # periodName
        line = line.replace(
            "const existingPeriodName = JSON.parse('{{ (assignment.period_name if assignment and assignment.period_name else none) | tojson }}');",
            'const existingPeriodName = cfg.periodName;'
        )

        # hasPublicColumn
        line = line.replace(
            "const hasPublicColumn = {{ 'true' if (assignment and assignment.has_public_url()) else 'false' }};",
            'const hasPublicColumn = cfg.hasPublicUrl;'
        )

        # Translation replacements
        for jinja_expr, js_expr in TRANS_MAP.items():
            line = line.replace(jinja_expr, js_expr)

        # URL replacements
        for jinja_expr, js_expr in URL_MAP.items():
            line = line.replace('"' + jinja_expr + '"', js_expr)
            line = line.replace('"' + jinja_expr + '?tab=nss"', js_expr + ' + "?tab=nss"')

        # Handle DUPLICATE_CHECK_URL
        line = re.sub(
            r'const DUPLICATE_CHECK_URL = ".*?check_assignment_duplicate.*?";',
            'const DUPLICATE_CHECK_URL = cfg.urls.checkDuplicate;',
            line
        )

        # Handle TEMPLATES_API in second block
        line = re.sub(
            r'const TEMPLATES_API = ".*?manage_indicator_bank.*?";',
            'const TEMPLATES_API = cfg.urls.adminBase;',
            line
        )

        # Handle {% if assignment %} blocks - convert to runtime checks
        stripped = line.strip()
        if stripped == '{% if assignment %}':
            indent = len(line) - len(line.lstrip())
            result.append(' ' * indent + 'if (cfg.assignmentId) {')
            i += 1
            continue
        elif stripped == '{% if not assignment %}':
            indent = len(line) - len(line.lstrip())
            result.append(' ' * indent + 'if (!cfg.assignmentId) {')
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
        elif stripped.startswith('{% for ') and 'assignment_countries' in stripped:
            # The assignment_countries loop is handled in the config bootstrap, skip it
            # The loop generates: {{ aes.country.id }},
            # We replace the whole pattern with a read from cfg.assignmentCountryIds
            result.append('                const assignmentCountryIds = new Set(cfg.assignmentCountryIds || []);')
            # Skip until endfor
            i += 1
            while i < len(js_lines) and '{% endfor %}' not in js_lines[i]:
                i += 1
            i += 1  # skip endfor
            continue

        result.append(line)
        i += 1

    return result

transformed_main = transform_js(main_js_lines)
transformed_second = transform_js(second_js_lines)

# ------------------------------------------------------------------
# 4. Write the static JS file
# ------------------------------------------------------------------
js_output_lines = [
    '/* Auto-generated from manage_assignment.html - DO NOT edit template inline JS */',
    '/* Config is bootstrapped via window.manageAssignmentConfig in the template */',
    '',
    '(function () {',
    "    'use strict';",
    '    var cfg = window.manageAssignmentConfig || {};',
    '',
]

js_output_lines.extend(transformed_main)
js_output_lines.append('')
js_output_lines.append('// --- Template Data Owner Prefill ---')
js_output_lines.extend(transformed_second)
js_output_lines.append('}());')

with open(OUTPUT_JS_PATH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(js_output_lines))

print(f"Written {len(js_output_lines)} lines to {OUTPUT_JS_PATH}")

# ------------------------------------------------------------------
# 5. Build the new template section to replace the script blocks
# ------------------------------------------------------------------
# We need to:
# a) Add a JSON data block before the scripts
# b) Add the config bootstrap
# c) Reference the static JS file
# d) Remove the old inline script blocks

# Find the entityManagementData loop section (lines 1103-1134)
# to build a proper JSON block template

entity_data_json_template = '''<script type="application/json" id="entity-management-data">[
{% for aes in assignment_entities %}
{
    "id": {{ aes.id }},
    "entity_type": {{ (aes.entity_type or '')|tojson }},
    "entity_type_label": {{ (
        'Country' if aes.entity_type == 'country' else
        'NS Branch' if aes.entity_type == 'ns_branch' else
        'NS Sub-branch' if aes.entity_type == 'ns_subbranch' else
        'NS Local Unit' if aes.entity_type == 'ns_localunit' else
        'Division' if aes.entity_type == 'division' else
        'Department' if aes.entity_type == 'department' else
        'Regional Office' if aes.entity_type == 'regional_office' else
        'Cluster Office' if aes.entity_type == 'cluster_office' else
        (aes.entity_type | replace('_', ' ') | title)
    )|tojson }},
    "entity_name": {{ EntityService.get_entity_name(aes.entity_type, aes.entity_id, include_hierarchy=True)|tojson }},
    "entity_id": {{ aes.entity_id|tojson }},
    "status": {{ (aes.status or '')|tojson }},
    "due_date": {{ (aes.due_date|datetime_iso if aes.due_date else '')|tojson }},
    "is_public_available": {{ aes.is_public_available|tojson }},
    "has_public_url": {{ assignment.has_public_url()|tojson }},
    "edit_url": "#",
    "remove_from_public_url": {{ (url_for('assignment_management.remove_country_from_public', assignment_id=assignment.id, country_id=aes.entity_id) if assignment and assignment.has_public_url() and aes.entity_type == 'country' else '')|tojson }},
    "add_to_public_url": {{ (url_for('assignment_management.add_country_to_public', assignment_id=assignment.id, country_id=aes.entity_id) if assignment and assignment.has_public_url() and aes.entity_type == 'country' else '')|tojson }},
    "remove_country_url": {{ (url_for('assignment_management.remove_country_from_assignment', assignment_id=assignment.id, country_id=aes.entity_id) if assignment and aes.entity_type == 'country' else '')|tojson }},
    "remove_entity_url": {{ (url_for('assignment_management.remove_entity_from_assignment', assignment_id=assignment.id, status_id=aes.id) if assignment and aes.entity_type != 'country' else '')|tojson }},
    "remove_confirm": {{ ('Are you sure you want to remove ' + EntityService.get_entity_name(aes.entity_type, aes.entity_id, include_hierarchy=True) + ' from this assignment and delete its data?')|tojson }},
    "remove_public_confirm": {{ ('Remove ' + EntityService.get_entity_name(aes.entity_type, aes.entity_id, include_hierarchy=True) + ' from public reporting?')|tojson }}
}{% if not loop.last %},{% endif %}
{% endfor %}
]</script>'''

config_bootstrap = '''<script nonce="{{ csp_nonce() }}">
window.manageAssignmentConfig = {
    assignmentId: {{ assignment.id if assignment else 'null' }},
    isNew: {{ 'true' if not assignment else 'false' }},
    periodName: {{ (assignment.period_name if assignment and assignment.period_name else none)|tojson }},
    hasPublicUrl: {{ (assignment.has_public_url() if assignment else false)|tojson }},
    assignmentCountryIds: [
        {%- if assignment -%}
        {%- for aes in assignment_countries -%}
            {{ aes.country.id }}{%- if not loop.last -%},{%- endif -%}
        {%- endfor -%}
        {%- endif -%}
    ],
    urls: {
        apiPartOfPrograms: {{ url_for('organization.api_get_part_of_programs')|tojson }},
        organizationIndex: {{ url_for('organization.index')|tojson }},
        checkDuplicate: {{ url_for('assignment_management.check_assignment_duplicate')|tojson }},
        adminBase: {{ url_for('system_admin.manage_indicator_bank')|replace('/indicator-bank', '')|tojson }}
    },
    t: {
        remove: {{ _('Remove')|tojson }},
        cancel: {{ _('Cancel')|tojson }},
        removeEntities: {{ _('Remove entities')|tojson }},
        confirm: {{ _('Confirm')|tojson }},
        publicReporting: {{ _('Public reporting')|tojson }},
        createAnyway: {{ _('Create anyway')|tojson }},
        duplicateAssignment: {{ _('Duplicate assignment')|tojson }},
        createAssignment: {{ _('Create assignment')|tojson }},
        continueBtn: {{ _('Continue')|tojson }},
        noNotifyMsg: {{ _('This assignment will be created without sending notifications to assigned entities. Do you want to continue?')|tojson }},
        notifyMsg: {{ _('Assigned entities (focal points) will be notified about this new assignment. Do you want to continue?')|tojson }},
        confirmAction: {{ _('Confirm action')|tojson }}
    }
};
</script>'''

static_script_ref = '<script src="{{ static_url(\'js/admin/manage-assignment.js\') }}" nonce="{{ csp_nonce() }}"></script>'

print("Transformation summary:")
print(f"  - entity_data_json_template: {len(entity_data_json_template.splitlines())} lines")
print(f"  - config_bootstrap: {len(config_bootstrap.splitlines())} lines")
print()
print("Manual steps needed:")
print("  1. Replace the main script block (lines 772-3450) with entity_data_json_template + config_bootstrap + static_script_ref")
print("  2. Replace the second script block (lines 3526-3566) with the static_script_ref")
print()
print("Entity data JSON template:")
print(entity_data_json_template[:300])
