#!/usr/bin/env python3
"""Replace auto_translate_modal_js.html inline script with bootstrap + static JS."""
from pathlib import Path

import migrate_template_js as mig

ROOT = Path(__file__).resolve().parents[1]
template = ROOT / "app/templates/components/auto_translate_modal_js.html"
html = template.read_text(encoding="utf-8")
scripts = mig.extract_scripts(html)
if not scripts:
    raise SystemExit("no scripts")

combined_cfg = {"translations": {}, "urls": {}}
for _, _, content, is_mod in scripts:
    if is_mod:
        continue
    _, cfg = mig.build_bootstrap(content)
    combined_cfg["translations"].update(cfg["translations"])
    combined_cfg["urls"].update(cfg["urls"])

# Extra string that migrate may miss (nested quotes)
combined_cfg["translations"]["click_start_translation_blank_6e8f4a2b"] = (
    "Click 'Start Translation' to begin translating blank"
)
combined_cfg["translations"]["warning_selected_service_is_currently_un_e42e0e26"] = (
    "Warning: Selected service is currently unavailable. Translation may fail."
)

bootstrap_t = mig.render_bootstrap_jinja(combined_cfg, "autoTranslatePageConfig")
# Replace urls section with friendly keys
urls_block = """window.autoTranslatePageConfig.urls = {
  translationServices: {{ url_for('utilities.api_translation_services')|tojson }},
  autoTranslateSummary: {{ url_for('utilities.api_auto_translate_summary')|tojson }},
};"""
bootstrap_t = bootstrap_t.replace(
    "window.autoTranslatePageConfig.urls = {",
    urls_block.split("window.autoTranslatePageConfig.urls = {")[0] + urls_block,
)
# Remove auto-generated urls from render (hack: rebuild bootstrap manually)
lines = [f'<script nonce="{{{{ csp_nonce() }}}}">', "window.autoTranslatePageConfig = window.autoTranslatePageConfig || {};"]
lines.append("window.autoTranslatePageConfig.t = {")
for k, text in combined_cfg["translations"].items():
    esc = text.replace("'", "\\'")
    lines.append(f"  {k}: {{{{ _('{esc}')|tojson }}}},")
lines.append("};")
lines.append(urls_block)
lines.append(
    "{% if auto_translate_config is defined %}"
)
lines.append("window.autoTranslatePageConfig.runtimeConfig = {")
lines.append("  endpoint: {{ (auto_translate_config.endpoint if auto_translate_config.endpoint else none)|tojson }},")
lines.append("  item_type: {{ (auto_translate_config.item_type if auto_translate_config.item_type is defined and auto_translate_config.item_type else none)|tojson }},")
lines.append("  itemType: {{ (auto_translate_config.item_type if auto_translate_config.item_type is defined and auto_translate_config.item_type else none)|tojson }},")
lines.append("  permission_context: {{ (auto_translate_config.permission_context if auto_translate_config.permission_context is defined and auto_translate_config.permission_context else none)|tojson }},")
lines.append("  permission_code: {{ (auto_translate_config.permission_code if auto_translate_config.permission_code is defined and auto_translate_config.permission_code else none)|tojson }}")
lines.append("};")
lines.append("{% endif %}")
lines.append("(function() {")
lines.append("  var langEl = document.getElementById('auto-translate-lang-display-names');")
lines.append("  if (langEl) {")
lines.append("    try { window.autoTranslatePageConfig.languageDisplayNames = JSON.parse(langEl.textContent || '{}'); } catch (e) {}")
lines.append("  }")
lines.append("})();")
lines.append("</script>")

new_content = """{# Auto-Translate Modal JavaScript Component #}
{#
Usage: Include this after the modal HTML
Optional: auto_translate_config with endpoint, item_type, permission_context, permission_code
Pages may also set window.autoTranslateConfigFromTemplate via a JSON script tag before this include.
#}
<script type="application/json" id="auto-translate-lang-display-names">{
{% for lang_code in TRANSLATABLE_LANGUAGES %}
{% set lang_display = LANGUAGE_DISPLAY_NAMES.get(lang_code) or ALL_LANGUAGES_DISPLAY_NAMES.get(lang_code) or lang_code.upper() %}
{{ lang_code|tojson }}: {{ _(lang_display)|tojson }}{% if not loop.last %},{% endif %}
{% endfor %}
}</script>
""" + "\n".join(lines) + """
<script src="{{ static_url('js/admin/auto-translate.js') }}"></script>
"""

template.write_text(new_content, encoding="utf-8")
print("Updated", template)
