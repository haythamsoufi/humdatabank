"""
Patch manage_assignment.html to replace inline script blocks with:
1. JSON data block for entityManagementData
2. Config bootstrap
3. Static JS file reference
"""

TEMPLATE_PATH = 'Backoffice/app/templates/admin/assignments/manage_assignment.html'

with open(TEMPLATE_PATH, encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# Find the first inline script block (line 772 in 1-indexed = index 771)
main_start = None
main_end = None
for i, ln in enumerate(lines):
    if i >= 771 and '<script nonce=' in ln and main_start is None:
        main_start = i
    elif '</script>' in ln and main_start is not None and main_end is None:
        main_end = i
        break

print(f"Main script block: lines {main_start+1} to {main_end+1}")

# Find the second inline script block (around index 3525)
second_start = None
second_end = None
for i, ln in enumerate(lines):
    if i >= 3525 and '<script nonce=' in ln and second_start is None:
        second_start = i
    elif '</script>' in ln and second_start is not None and second_end is None:
        second_end = i
        break

print(f"Second script block: lines {second_start+1} to {second_end+1}")

# Build replacement for the first block
replacement_first = '''<script type="application/json" id="entity-management-data">[
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
    "has_public_url": {{ (assignment.has_public_url() if assignment else false)|tojson }},
    "edit_url": "#",
    "remove_from_public_url": {{ (url_for('assignment_management.remove_country_from_public', assignment_id=assignment.id, country_id=aes.entity_id) if assignment and assignment.has_public_url() and aes.entity_type == 'country' else '')|tojson }},
    "add_to_public_url": {{ (url_for('assignment_management.add_country_to_public', assignment_id=assignment.id, country_id=aes.entity_id) if assignment and assignment.has_public_url() and aes.entity_type == 'country' else '')|tojson }},
    "remove_country_url": {{ (url_for('assignment_management.remove_country_from_assignment', assignment_id=assignment.id, country_id=aes.entity_id) if assignment and aes.entity_type == 'country' else '')|tojson }},
    "remove_entity_url": {{ (url_for('assignment_management.remove_entity_from_assignment', assignment_id=assignment.id, status_id=aes.id) if assignment and aes.entity_type != 'country' else '')|tojson }},
    "remove_confirm": {{ ('Are you sure you want to remove ' + EntityService.get_entity_name(aes.entity_type, aes.entity_id, include_hierarchy=True) + ' from this assignment and delete its data?')|tojson }},
    "remove_public_confirm": {{ ('Remove ' + EntityService.get_entity_name(aes.entity_type, aes.entity_id, include_hierarchy=True) + ' from public reporting?')|tojson }}
}{% if not loop.last %},{% endif %}
{% endfor %}
]</script>
<script nonce="{{ csp_nonce() }}">
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
</script>
<script src="{{ static_url('js/admin/manage-assignment.js') }}" nonce="{{ csp_nonce() }}"></script>'''

# Build new lines list
new_lines = (
    lines[:main_start] +
    replacement_first.split('\n') +
    lines[main_end+1:second_start] +
    ['<script src="{{ static_url(\'js/admin/manage-assignment.js\') }}" nonce="{{ csp_nonce() }}"></script>'] +
    lines[second_end+1:]
)

# Wait - the second script block is already included via the static JS file
# The second_start to second_end block should just be removed (not replaced with another ref)
# since manage-assignment.js already includes that logic

new_lines = (
    lines[:main_start] +
    replacement_first.split('\n') +
    lines[main_end+1:second_start] +
    lines[second_end+1:]
)

with open(TEMPLATE_PATH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print(f"Done. Template now has {len(new_lines)} lines (was {len(lines)})")
print(f"Script block 1 replaced (was lines {main_start+1}-{main_end+1})")
print(f"Script block 2 removed (was lines {second_start+1}-{second_end+1})")
