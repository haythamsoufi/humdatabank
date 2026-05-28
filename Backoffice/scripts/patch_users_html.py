path = 'app/templates/admin/user_management/users.html'
with open(path, encoding='utf-8') as f:
    content = f.read()

old_start = '\n\n    // Helper function to render entities\n    function renderEntities(user) {'
bootstrap = '''
<script nonce="{{ csp_nonce() }}">
window.usersGridConfig = window.usersGridConfig || {};
window.usersGridConfig.t = {
    id_e369853d: {{ _('ID')|tojson }},
    user_8f9bfe9d: {{ _('User')|tojson }},
    email_ce8ae9da: {{ _('Email')|tojson }},
    title_b78a3223: {{ _('Title')|tojson }},
    role_2e083440: {{ _('Role')|tojson }},
    status_ec53a8c4: {{ _('Status')|tojson }},
    entities_3b4d9c2e: {{ _('Entities')|tojson }},
    global_f2a89e71: {{ _('Global')|tojson }},
    countries_790d59ef: {{ _('countries')|tojson }},
    other_countries_b1e7b76a: {{ _('other countries')|tojson }},
    branches_7cddf5f4: {{ _('branches')|tojson }},
    sub_branches_2d3b75e2: {{ _('sub-branches')|tojson }},
    local_units_4a0dc5ea: {{ _('local units')|tojson }},
    divisions_8b9c5a88: {{ _('divisions')|tojson }},
    departments_6a7e3c44: {{ _('departments')|tojson }},
    regional_offices_a5bf1c32: {{ _('regional offices')|tojson }},
    clusters_f8d4c77a: {{ _('clusters')|tojson }},
};
</script>
<script src="{{ static_url('js/admin/users-grid.js') }}"></script>
{% endblock %}'''

idx = content.find(old_start)
if idx == -1:
    print('start marker not found')
else:
    end_idx = content.find('    </script>\n{% endblock %}', idx)
    if end_idx == -1:
        print('end marker not found')
    else:
        end_idx2 = end_idx + len('    </script>\n{% endblock %}')
        new_content = content[:idx] + bootstrap + content[end_idx2:]
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print('Done, saved', len(new_content), 'chars')
