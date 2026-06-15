"""One-off debug script for new_template.html JS."""
import re
from app import create_app
from app.forms.form_builder.template_forms import FormTemplateForm
from app.utils.form_localization import get_localized_template_name
from flask import render_template

app = create_app('development')
with app.app_context():
    form = FormTemplateForm()
    html = render_template(
        'admin/templates/new_template.html',
        form=form,
        title='Create',
        available_templates=[],
        get_localized_template_name=get_localized_template_name,
        template=None,
    )
    m = re.search(r"import\('([^']+)'\)", html)
    print('import url:', m.group(1) if m else 'NOT FOUND')
    scripts = re.findall(r'<script nonce[^>]*>(.*?)</script>', html, re.DOTALL)
    for i, s in enumerate(scripts):
        if 'excel-import-dropzone' in s:
            with open('_tmp_nt_script.js', 'w', encoding='utf-8') as f:
                f.write(s)
            print(f'wrote script block {i} ({len(s)} chars)')
            for line in s.splitlines():
                if 'Field' in line and 'const name' in line:
                    print(' ', line.strip())
