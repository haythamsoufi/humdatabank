"""
Patch manage_translations.html:
1. Add translations data JSON block
2. Add allLanguageNames JSON block  
3. Add config bootstrap
4. Replace blocks 2,3,8 with static file reference
"""

TEMPLATE_PATH = 'Backoffice/app/templates/admin/translations/manage_translations.html'

with open(TEMPLATE_PATH, encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

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

# block indices: 0=auto-translate config (keep), 1=export, 2=translations grid, 3=edit modal
block2_start, block2_end = script_blocks[1]   # export logic
block3_start, block3_end = script_blocks[2]   # translations grid
block8_start, block8_end = script_blocks[3]   # edit modal

# Build:
# 1. translationsData JSON block (replaces the big data loop in block 3)
# 2. allLanguageNames JSON block (new, for cfg)
# 3. Config bootstrap
# 4. Static JS reference

translations_data_json = '''<script type="application/json" id="translations-grid-data">[
    {%- for msgid in all_msgids -%}
    {
        "msgid": {{ msgid|tojson }},
        "source": {{ msgid_sources.get(msgid, _('Unknown'))|tojson }},
        "removed": {{ (msgid in obsolete_msgids)|tojson }},
        {% for code in languages %}"{{ code }}": {{ translation_data.get(code, {}).get('translations', {}).get(msgid, '')|tojson }},
        {% endfor %}"edit_url": {{ url_for('utilities.edit_translation', msgid=msgid)|tojson }}
    }{%- if not loop.last -%},{%- endif -%}
    {%- endfor -%}
]</script>
<script id="all-language-names-json" type="application/json">{{ ALL_LANGUAGES_DISPLAY_NAMES | tojson | safe }}</script>'''

config_bootstrap = '''<script nonce="{{ csp_nonce() }}">
window.manageTranslationsConfig = {
    languages: JSON.parse((document.getElementById('languages-json') || {}).textContent || '[]'),
    languageNames: JSON.parse((document.getElementById('language-names-json') || {}).textContent || '{}'),
    allLanguageNames: JSON.parse((document.getElementById('all-language-names-json') || {}).textContent || '{}'),
    urls: {
        exportPo: {{ url_for('utilities.export_translations')|tojson }},
        compilePo: {{ url_for('utilities.compile_translations')|tojson }},
        editTranslation: {{ url_for('utilities.edit_translation')|tojson }},
        deleteRemovedTranslation: {{ url_for('utilities.delete_removed_translation')|tojson }}
    },
    t: {
        sourceCol: {{ _('Source')|tojson }},
        msgIdCol: {{ _('Message ID')|tojson }},
        actionsCol: {{ _('Actions')|tojson }},
        unknown: {{ _('Unknown')|tojson }},
        removed: {{ _('Removed')|tojson }},
        removedFromSource: {{ _('This string was removed from source code')|tojson }},
        containsPlaceholders: {{ _('Contains format placeholders - preserve them in translations')|tojson }},
        editAllTranslations: {{ _('Edit all translations')|tojson }},
        permanentlyDelete: {{ _('Permanently delete this removed string from all .po files')|tojson }},
        compileWarning: {{ _('Compiling translations will restart the application. This may cause a brief interruption in service. Do you want to continue?')|tojson }},
        compilingText: {{ _('Compiling...')|tojson }},
        continueBtn: {{ _('Continue')|tojson }},
        cancel: {{ _('Cancel')|tojson }},
        compileTitle: {{ _('Compile Translations?')|tojson }},
        noFieldsNeedTranslation: {{ _('No translation fields found that need translation')|tojson }},
        translationStopped: {{ _('Translation stopped by user.')|tojson }},
        translationCompleted: {{ _('Translation completed!')|tojson }},
        unknownError: {{ _('Unknown error')|tojson }},
        skipped: {{ _('Skipped')|tojson }},
        translationFor: {{ _('translation for')|tojson }},
        properNounOrTech: {{ _('proper noun or technical term, no translation available')|tojson }},
        translated: {{ _('Translated')|tojson }},
        failedToTranslate: {{ _('Failed to translate')|tojson }},
        toText: {{ _('to')|tojson }},
        blockedByWaf: {{ _('Blocked by WAF for translation')|tojson }},
        networkError: {{ _('Network error for translation')|tojson }},
        missingPlaceholders: {{ _('Missing placeholders')|tojson }},
        allPlaceholdersMustBePreserved: {{ _('All placeholders from the original text must be preserved.')|tojson }},
        failedToLoadData: {{ _('Failed to load translation data')|tojson }},
        savingText: {{ _('Saving...')|tojson }},
        couldNotPrepareDelete: {{ _('Could not prepare delete request')|tojson }},
        removedObsolete: {{ _('Removed obsolete entries')|tojson }},
        deleteFailed: {{ _('Delete failed')|tojson }},
        permanentDeleteConfirm: {{ _('This permanently deletes the obsolete (#~) entry for this message from every locale .po file. Active strings are not affected. Continue?')|tojson }},
        deleteRemovedTitle: {{ _('Delete removed string?')|tojson }},
        deleteBtn: {{ _('Delete')|tojson }},
        validationError: {{ _('Translation Validation Error')|tojson }},
        fixErrorsBeforeSaving: {{ _('Please fix these errors before saving.')|tojson }},
        failedToSave: {{ _('Failed to save translation')|tojson }},
        savedSuccessfully: {{ _('Translation saved successfully')|tojson }},
        translatingText: {{ _('Translating...')|tojson }},
        noSourceText: {{ _('Please ensure English or Message ID has text to translate from.')|tojson }},
        nothingToTranslate: {{ _('Nothing to translate \u2014 all enabled language fields already have values.')|tojson }},
        autoTranslateFailed: {{ _('Auto-translate failed.')|tojson }},
        clearConfirm: {{ _('Are you sure you want to clear all translation fields except English? This action cannot be undone.')|tojson }},
        cleared1: {{ _('Cleared 1 translation field.')|tojson }},
        cleared: {{ _('Cleared')|tojson }},
        translationFields: {{ _('translation fields.')|tojson }},
        noFieldsToClear: {{ _('No translation fields to clear.')|tojson }},
        clearBtn: {{ _('Clear')|tojson }},
        clearTitle: {{ _('Clear Translations?')|tojson }},
        translationLabel: {{ _('Translation')|tojson }}
    }
};
</script>
<script src="{{ static_url('js/admin/manage-translations.js') }}" nonce="{{ csp_nonce() }}"></script>'''

# Build the new lines:
# Keep: everything before block2_start
# Add: translations_data_json + allLanguageNames (before block2)
# Add: config_bootstrap (after existing JSON blocks, replacing blocks 2,3,8)
# Remove: block2, block3, block8

new_lines = (
    lines[:block2_start] +
    translations_data_json.split('\n') +
    [''] +
    config_bootstrap.split('\n') +
    lines[block8_end+1:]
)

with open(TEMPLATE_PATH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

print(f"Done. Template now has {len(new_lines)} lines (was {len(lines)})")
