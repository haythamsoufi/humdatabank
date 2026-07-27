"""
Extract inline JS from manage_translations.html into manage-translations.js.
"""
import re

TEMPLATE_PATH = 'Backoffice/app/templates/admin/translations/manage_translations.html'
OUTPUT_JS_PATH = 'Backoffice/app/static/js/admin/manage-translations.js'

with open(TEMPLATE_PATH, encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

# Find nonce script blocks
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
    print(f"  Lines {s+1}-{e+1} ({e-s} lines)")

# Block indices:
# 0: auto-translate config reader (541-576) - already clean, keep as-is
# 1: export/utility logic (581-736)
# 2: translations grid (738-1507) with heavy Jinja
# 3: edit modal (1536-2019)
# (Blocks 4-7 are JSON data blocks, not nonce blocks)
assert len(script_blocks) == 4, f"Expected 4 nonce blocks, found {len(script_blocks)}"

block2_start, block2_end = script_blocks[1]  # 582-737 (export logic)
block3_start, block3_end = script_blocks[2]  # 739-1508 (translations grid)
block8_start, block8_end = script_blocks[3]  # 1537-2020 (edit modal)

# --- TRANS_MAP: text substitutions ---
TRANS_MAP = {
    # Block 2 (in string literals, not tojson)
    
    # Block 3 translations
    "'{{ _(\"Source\") }}'": 'cfg.t.sourceCol',
    "'{{ _(\"Unknown\") }}'": 'cfg.t.unknown',
    "'{{ _(\"Removed\") }}'": 'cfg.t.removed',
    '"{{ _(\"This string was removed from source code\") }}"': 'cfg.t.removedFromSource',
    '"{{ _(\"Contains format placeholders - preserve them in translations\") | replace(\\"%\\", \\"%%\\") }}"': 'cfg.t.containsPlaceholders',
    "'{{ _(\"Message ID\") }}'": 'cfg.t.msgIdCol',
    "'{{ _(\"Actions\") }}'": 'cfg.t.actionsCol',
    '"{{ _(\"Edit all translations\") }}"': 'cfg.t.editAllTranslations',
    '"{{ _(\"Permanently delete this removed string from all .po files\") }}"': 'cfg.t.permanentlyDelete',
    # Block 3 compile
    "'{{ _(\"Compiling translations will restart the application. This may cause a brief interruption in service. Continue?\") }}'": 'cfg.t.compileWarning',
    "'{{ _(\"Compiling...\") }}'": 'cfg.t.compilingText',
    "'{{ _(\"Continue\") }}'": 'cfg.t.continueBtn',
    "'{{ _(\"Cancel\") }}'": 'cfg.t.cancel',
    "'{{ _(\"Compile Translations?\") }}'": 'cfg.t.compileTitle',
    # Auto-translate
    "'{{ _(\"No translation fields found that need translation\") }}'": 'cfg.t.noFieldsNeedTranslation',
    "'{{ _(\"Translation stopped by user.\") }}'": 'cfg.t.translationStopped',
    "'{{ _(\"Translation completed!\") }}'": 'cfg.t.translationCompleted',
    "'{{ _(\"Unknown error\") }}'": 'cfg.t.unknownError',
    # Block 8 translations
    '{{ _("Missing placeholders") }}': '" + cfg.t.missingPlaceholders + "',
    '{{ _("All placeholders from the original text must be preserved.") }}': '" + cfg.t.allPlaceholdersMustBePreserved + "',
    '{{ _("Failed to load translation data") }}': '" + cfg.t.failedToLoadData + "',
    '"{{ _(\'Saving...\') | tojson }}"': 'cfg.t.savingText',
    "'{{ _(\\\"Saving...\\\") }}'" : 'cfg.t.savingText',
    '{{ _("Could not prepare delete request") }}': '" + cfg.t.couldNotPrepareDelete + "',
    '{{ _("Removed obsolete entries") }}': '" + cfg.t.removedObsolete + "',
    '{{ _("Delete failed") }}': '" + cfg.t.deleteFailed + "',
    '{{ _("This permanently deletes the obsolete (#~) entry for this message from every locale .po file. Action cannot be undone.") }}': '" + cfg.t.permanentDeleteConfirm + "',
    '{{ _("Delete removed string?") }}': '" + cfg.t.deleteRemovedTitle + "',
    '{{ _("Delete") }}': '" + cfg.t.deleteBtn + "',
    '{{ _("Translation Validation Error") }}': '" + cfg.t.validationError + "',
    '{{ _("Please fix these errors before saving.") }}': '" + cfg.t.fixErrorsBeforeSaving + "',
    '{{ _("Failed to save translation") }}': '" + cfg.t.failedToSave + "',
    '{{ _("Translation saved successfully") }}': '" + cfg.t.savedSuccessfully + "',
    '{{ _("Translating...") }}': '" + cfg.t.translatingText + "',
    '{{ _("Please ensure English or Message ID has text to translate from.") }}': '" + cfg.t.noSourceText + "',
    '{{ _("Nothing to translate \u2014 all enabled language fields already have values.") }}': '" + cfg.t.nothingToTranslate + "',
    '{{ _("Auto-translate failed.") }}': '" + cfg.t.autoTranslateFailed + "',
    '{{ _("Are you sure you want to clear all translation fields except English? This action cannot be undone.") }}': '" + cfg.t.clearConfirm + "',
    '{{ _("Cleared 1 translation field.") }}': '" + cfg.t.cleared1 + "',
    '{{ _("Cleared") }}': '" + cfg.t.cleared + "',
    '{{ _("translation fields.") }}': '" + cfg.t.translationFields + "',
    '{{ _("No translation fields to clear.") }}': '" + cfg.t.noFieldsToClear + "',
    '{{ _("Clear") }}': '" + cfg.t.clearBtn + "',
    '{{ _("Clear Translations?") }}': '" + cfg.t.clearTitle + "',
    '{{ _("Translation") }}': '" + cfg.t.translationLabel + "',
    # Auto-translate template literals (backtick strings - these are complex)
    '{{ _("Skipped") }}': '" + cfg.t.skipped + "',
    '{{ _("translation for") }}': '" + cfg.t.translationFor + "',
    '{{ _("proper noun or technical term") }}': '" + cfg.t.properNounOrTech + "',
    '{{ _("Translated") }}': '" + cfg.t.translated + "',
    '{{ _("Failed to translate") }}': '" + cfg.t.failedToTranslate + "',
    '{{ _("to") }}': '" + cfg.t.toText + "',
    '{{ _("Blocked by WAF for translation") }}': '" + cfg.t.blockedByWaf + "',
    '{{ _("Network error for translation") }}': '" + cfg.t.networkError + "',
}

URL_MAP = {
    '"{{ url_for(\'utilities.export_translations\') }}"': 'cfg.urls.exportPo',
    '"{{ url_for("utilities.compile_translations") }}"': 'cfg.urls.compilePo',
    "'{{ url_for(\"utilities.compile_translations\") }}'": 'cfg.urls.compilePo',
    '"{{ url_for("utilities.edit_translation") }}"': 'cfg.urls.editTranslation',
    '"{{ url_for("utilities.delete_removed_translation") }}"': 'cfg.urls.deleteRemovedTranslation',
    "'{{ url_for(\"utilities.edit_translation\") }}'": 'cfg.urls.editTranslation',
}

def transform_block(js_lines):
    result = []
    i = 0
    in_translations_data = False
    in_language_cols = False

    while i < len(js_lines):
        line = js_lines[i]

        # translationsData block
        if '// Transform translations data for ag-grid.' in line or (
            'const REMOVED_PREFIX' in line and not in_translations_data):
            pass  # Keep the REMOVED_PREFIX line
        if 'const translationsData = [' in line:
            in_translations_data = True
            result.append('        const translationsData = (function() {')
            result.append('            var el = document.getElementById(\'translations-grid-data\');')
            result.append('            if (!el) return [];')
            result.append('            try { return JSON.parse(el.textContent || \'[]\'); } catch(e) { return []; }')
            result.append('        })();')
            i += 1
            continue
        if in_translations_data:
            if line.strip() == '];':
                in_translations_data = False
            i += 1
            continue

        # Language column defs loop: '}{% for code in languages %},' → dynamic generation
        stripped = line.strip()
        if stripped.startswith('}{% for code in languages %},'):
            # End the previous column and start dynamic language columns
            result.append('        }')
            result.append('    ].concat((cfg.languages || []).map(function(code) {')
            result.append('        var langName = (cfg.languageNames && cfg.languageNames[code]) || (cfg.allLanguageNames && cfg.allLanguageNames[code]) || code.toUpperCase();')
            result.append('        return {')
            result.append('            field: code,')
            result.append("            headerName: langName,")
            result.append('            width: 250,')
            result.append('            minWidth: 200,')
            result.append('            maxWidth: 400,')
            result.append("            filter: 'agTextColumnFilter',")
            result.append('            sortable: true,')
            result.append('            wrapText: true,')
            result.append('            cellRenderer: function(params) {')
            result.append("                const value = params.value || '';")
            result.append("                const hasPlaceholders = /%\\([^)]+\\)[sd]|%(?:[sd]|\\.\\d+[fd])/.test(value);")
            result.append("                let display = value.replace(/</g, '&lt;').replace(/>/g, '&gt;');")
            result.append('                if (hasPlaceholders) {')
            result.append("                    display = '<span class=\"inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800 mr-1\" title=\"' + cfg.t.containsPlaceholders + '\"><i class=\"fas fa-code mr-1\"></i>' + display + '</span>';")
            result.append('                }')
            result.append("                return '<div title=\"' + value.replace(/\"/g, '&quot;') + '\">' + display + '</div>';")
            result.append('            },')
            result.append('            cellStyle: function(params) {')
            result.append("                const baseStyle = { 'white-space': 'normal', 'word-wrap': 'break-word', 'line-height': '1.4' };")
            result.append('                if (params.data && params.data.removed) {')
            result.append("                    baseStyle['background-color'] = '#fff7f7';")
            result.append("                    baseStyle['color'] = '#9ca3af';")
            result.append('                }')
            result.append('                return baseStyle;')
            result.append('            }')
            result.append('        };')
            result.append('    }))')
            in_language_cols = True
            i += 1
            continue
        if in_language_cols:
            if stripped.startswith('}{% endfor %},'):
                in_language_cols = False
                # Continue with the rest of the columnDefs (actions column)
                result.append('    .concat([{')
            i += 1
            continue

        # After language cols, the actions column closing
        if '];\n' in line or (stripped == '];' and not in_translations_data):
            # This might be the end of columnDefs - add extra ]
            pass

        # languages/languageNames/allLanguageNames from JSON blocks instead of inline
        if 'const languages = {{ (languages or []) | tojson | safe }};' in line:
            result.append("        const languages = JSON.parse((document.getElementById('languages-json') || {}).textContent || '[]');")
            i += 1
            continue
        if 'const languageNames = {{ (language_names or {}) | tojson | safe }};' in line:
            result.append("        const languageNames = JSON.parse((document.getElementById('language-names-json') || {}).textContent || '{}');")
            i += 1
            continue
        if 'const allLanguageNames = {{ (ALL_LANGUAGES_DISPLAY_NAMES or {}) | tojson | safe }};' in line:
            result.append('        const allLanguageNames = cfg.allLanguageNames || {};')
            i += 1
            continue

        # .concat({{ (languages or []) | tojson | safe }}) for sort
        line = line.replace('.concat({{ (languages or []) | tojson | safe }})', '.concat(cfg.languages || [])')

        # URL replacements
        for jinja_expr, js_expr in URL_MAP.items():
            line = line.replace(jinja_expr, js_expr)

        # Translation replacements (exact string)
        for jinja_expr, js_expr in TRANS_MAP.items():
            line = line.replace(jinja_expr, js_expr)

        # saveBtnText.textContent - specific pattern
        line = line.replace(
            "saveBtnText.textContent = {{ _('Saving...') | tojson }};",
            "saveBtnText.textContent = cfg.t.savingText;"
        )

        result.append(line)
        i += 1

    return result

# Transform all blocks
b2_lines = transform_block(lines[block2_start+1:block2_end])
b3_lines = transform_block(lines[block3_start+1:block3_end])
b8_lines = transform_block(lines[block8_start+1:block8_end])

# Write static JS file
output_lines = [
    '/* Auto-generated from manage_translations.html — DO NOT edit template inline JS */',
    '/* Config is bootstrapped via window.manageTranslationsConfig in the template */',
    '',
    '(function () {',
    "    'use strict';",
    '    var cfg = window.manageTranslationsConfig || {};',
    '',
    '    // --- Export and utility logic ---',
]
output_lines.extend(b2_lines)
output_lines.append('')
output_lines.append('    // --- Translations grid ---')
output_lines.extend(b3_lines)
output_lines.append('')
output_lines.append('    // --- Edit translation modal ---')
output_lines.extend(b8_lines)
output_lines.append('')
output_lines.append('}());')

with open(OUTPUT_JS_PATH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(output_lines))

print(f"Written {len(output_lines)} lines to {OUTPUT_JS_PATH}")

# Check for remaining Jinja
remaining = [(i+1, l) for i, l in enumerate(output_lines) if '{{' in l or '{%' in l]
print(f"Remaining Jinja lines: {len(remaining)}")
for ln, l in remaining[:30]:
    print(f"  {ln}: {l.strip()[:100]}")
