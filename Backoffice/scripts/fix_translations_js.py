"""Fix remaining Jinja in manage-translations.js"""

JS_PATH = 'Backoffice/app/static/js/admin/manage-translations.js'

with open(JS_PATH, encoding='utf-8') as f:
    content = f.read()

# Fix containsPlaceholders pattern (appears twice - in source column and language columns template)
old = '{{ _("Contains format placeholders - preserve them in translations") | replace("%", "%%") }}'
new = '" + cfg.t.containsPlaceholders + "'
content = content.replace(old, new)

# Fix compiling message
old2 = '{{ _("Compiling translations will restart the application. This may cause a brief interruption in service. Do you want to continue?") }}'
new2 = '" + cfg.t.compileWarning + "'
content = content.replace(old2, new2)

# Fix Compiling... text  
old3 = '{{ _("Compiling...") }}'
new3 = '" + cfg.t.compilingText + "'
content = content.replace(old3, new3)

# Fix template literal with translation for (backtick string issue)
# Line 826: `" + cfg.t.skipped + " ${translation.language} ... {{ _("proper noun or technical term, no translation available") }}`
old4 = '{{ _("proper noun or technical term, no translation available") }}'
new4 = '" + cfg.t.properNounOrTech + "'
content = content.replace(old4, new4)

# Fix URL fetch patterns (single-quoted fetch URLs)
old5 = "fetch('{{ url_for(\"utilities.edit_translation\") }}?msgid_b64=' + encodeURIComponent(msgidB64), {"
new5 = "fetch(cfg.urls.editTranslation + '?msgid_b64=' + encodeURIComponent(msgidB64), {"
content = content.replace(old5, new5)

old6 = "fetchFn('{{ url_for(\"utilities.delete_removed_translation\") }}', {"
new6 = "fetchFn(cfg.urls.deleteRemovedTranslation, {"
content = content.replace(old6, new6)

# Fix long confirmation message
old7 = '{{ _("This permanently deletes the obsolete (#~) entry for this message from every locale .po file. Active strings are not affected. Continue?") }}'
new7 = '" + cfg.t.permanentDeleteConfirm + "'
content = content.replace(old7, new7)

# Fix deleteRemovedTitle and deleteBtn that got wrapped in extra quotes
# Pattern: '"' + cfg.t.deleteRemovedTitle + '"' should be just cfg.t.deleteRemovedTitle
# in context: var confirmTitle = '" + cfg.t.deleteRemovedTitle + "';
content = content.replace("var confirmTitle = '\" + cfg.t.deleteRemovedTitle + \"';", 'var confirmTitle = cfg.t.deleteRemovedTitle;')
content = content.replace("var confirmTitle = '\" + cfg.t.deleteRemovedTitle + \"'\n", 'var confirmTitle = cfg.t.deleteRemovedTitle;\n')

# Fix deleteBtn in showDangerConfirmation call
content = content.replace("'\" + cfg.t.deleteBtn + \"'", 'cfg.t.deleteBtn')
content = content.replace("'\" + cfg.t.clearBtn + \"'", 'cfg.t.clearBtn')
content = content.replace("'\" + cfg.t.clearTitle + \"'", 'cfg.t.clearTitle')
content = content.replace("'\" + cfg.t.deleteRemovedTitle + \"'", 'cfg.t.deleteRemovedTitle')
content = content.replace("'\" + cfg.t.couldNotPrepareDelete + \"'", 'cfg.t.couldNotPrepareDelete')

# For the compile msg, fix the broken string concat in assignment
content = content.replace(
    "const msg = '\" + cfg.t.compileWarning + \"';",
    'const msg = cfg.t.compileWarning;'
)

# Fix compileBtn.innerHTML pattern
content = content.replace(
    "compileBtn.innerHTML = '<i class=\"fas fa-spinner fa-spin mr-2\"></i>\" + cfg.t.compilingText + \"';",
    "compileBtn.innerHTML = '<i class=\"fas fa-spinner fa-spin mr-2\"></i>' + cfg.t.compilingText;"
)

# Various show alert calls that have '" + cfg.t.xxx + "' pattern instead of just cfg.t.xxx
import re
# Replace: window.showAlert('...' + '..." + cfg.t.xxx + "...') → use cfg.t.xxx directly
# These patterns need to be cleaned up
content = re.sub(r"showAlert\('\" \+ (cfg\.t\.\w+) \+ \"'", r"showAlert(\1", content)
content = re.sub(r"showAlert\(\" \+ (cfg\.t\.\w+) \+ \"", r"showAlert(" + r"\1", content)

# Fix patterns like: '..." + cfg.t.xxx + "...' in assignments
# e.g., var m = '...' + '...' + '...'
# Look for: '\"' + cfg.t.xxx + '\"' patterns in string assignments
# These are common where the replacement used '" + cfg.t.xxx + "' instead of '+ cfg.t.xxx +'

# Fix validation error multi-line
content = content.replace(
    "'\" + cfg.t.validationError + \"'",
    'cfg.t.validationError'
)
content = content.replace(
    "'\" + cfg.t.fixErrorsBeforeSaving + \"'",
    'cfg.t.fixErrorsBeforeSaving'
)

# The " + cfg.t.xxx + " pattern appears as broken string concat in many places
# Let's fix common patterns
# Pattern: '...' + '...' + '..." + cfg.t.xxx + "...'
# This means the replacement split a string: was '... {{ _(...) }}...' → '..." + cfg.t.xxx + "...'
# We need the final string to be proper: '...' + cfg.t.xxx + '...'

# Find remaining Jinja
lines = content.split('\n')
remaining = [(i+1, l) for i, l in enumerate(lines) if '{{' in l or '{%' in l]
print(f'Remaining Jinja: {len(remaining)}')
for ln, l in remaining[:20]:
    print(f'  {ln}: {l.strip()[:100]}')

with open(JS_PATH, 'w', encoding='utf-8') as f:
    f.write(content)
print('\nDone')
