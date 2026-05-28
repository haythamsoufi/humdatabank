"""Fix remaining Jinja in manage-settings.js - third pass using line numbers"""
import re

JS_PATH = 'Backoffice/app/static/js/admin/manage-settings.js'

with open(JS_PATH, encoding='utf-8') as f:
    content = f.read()

# Use regex to replace all remaining {{ _('...') | tojson }} patterns
def make_cfg_key(text):
    """Generate a cfg.t key from translation text"""
    # Map known texts to cfg keys
    MAP = {
        'Notify entity-assigned admins (admin_core / admin_*, not system managers)': 'notifyOrgAdmins',
        'Click to switch: edit the template with Jinja placeholders, or see sample values (server-rendered preview, not saved).': 'tinymceVarTip',
        'Replace every email and notification template with the built-in defaults from this version? Custom HTML and pre-fill text will be lost.': 'seedConfirmForce',
        'The English version of this template is empty. Add or save some content first.': 'enTemplateEmpty',
        'Test email could not be sent. Check the message below or your mail server settings.': 'testEmailFail',
        'This language has no template content to send. Add HTML in the editor or pick another language tab.': 'noTemplateContent',
        'Seeding failed': 'seedingFailed',
    }
    for k, v in MAP.items():
        if k in text:
            return 'cfg.t.' + v
    return None

# Find all {{ _('...') | tojson }} and {{ _('...') |tojson }} patterns
pattern = re.compile(r"\{\{\s*_\('([^']+)'\)\s*\|?\s*tojson\s*\}\}")

def replacer(m):
    text = m.group(1)
    key = make_cfg_key(text)
    if key:
        return key
    return m.group(0)  # Keep if not found

content_new = pattern.sub(replacer, content)

# Also handle double-quoted variants
pattern2 = re.compile(r'\{\{\s*_\("([^"]+)"\)\s*\|?\s*tojson\s*\}\}')

def replacer2(m):
    text = m.group(1)
    key = make_cfg_key(text)
    if key:
        return key
    return m.group(0)

content_new = pattern2.sub(replacer2, content_new)

# Handle the Seeding failed in inline expression
# var err = (...) : ({{ _('Seeding failed') | tojson }} + (r.status ? ...))
content_new = content_new.replace(
    "({{ _('Seeding failed') | tojson }} + (r.status ? ' (' + r.status + ')' : ''))",
    "(cfg.t.seedingFailed + (r.status ? ' (' + r.status + ')' : ''))"
)

# Check remaining Jinja
lines = content_new.split('\n')
remaining = [(i+1, l) for i, l in enumerate(lines) if '{{' in l or '{%' in l]
print(f"Remaining Jinja: {len(remaining)}")
for ln, l in remaining[:20]:
    print(f"  {ln}: {repr(l.strip()[:100])}")

if remaining:
    print("\nThese will be fixed manually or need config bootstrap updates.")

with open(JS_PATH, 'w', encoding='utf-8') as f:
    f.write(content_new)
print("\nDone")
