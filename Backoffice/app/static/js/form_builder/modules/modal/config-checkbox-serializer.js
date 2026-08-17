/**
 * Serialize boolean config-panel checkboxes as explicit hidden inputs.
 *
 * HTML checkboxes are absent from FormData when unchecked.  Write one
 * always-enabled hidden input per checkbox onto the form root
 * (`name="<key>"`, value `"true"` / `"false"`).
 *
 * Do NOT write into `input[name="matrix_config"]` — that field lives inside
 * the disabled matrix panel for non-matrix item types.
 *
 * @module config-checkbox-serializer
 */

import { setHiddenField } from '../rules/form-serialization.js';

/**
 * Config-panel checkboxes that must always be present in the submit payload.
 *
 * Keep in sync with PRESERVE_EXISTING_BOOL_FIELDS in item_config_fields.py.
 */
export const CONFIG_CHECKBOXES = [
    { selector: '#item-allow-over-100',                    key: 'allow_over_100' },
    { selector: '#item-exclude-from-completion-rate',      key: 'exclude_from_completion_rate' },
    { selector: '#item-unique-options-in-section',         key: 'unique_options_in_section' },
    { selector: '#item-limit-entries-to-option-count',     key: 'limit_entries_to_option_count' },
    { selector: '#item-use-as-repeat-entry-title',         key: 'use_as_repeat_entry_title' },
    { selector: '#item-question-allow-other',              key: 'allow_other' },
];

function hiddenFieldId(key) {
    return `item-config-flag-${key}`;
}

/**
 * @param {HTMLElement} modalElement
 * @param {HTMLFormElement} form
 * @param {Array<{selector: string, key: string}>} [checkboxes]
 */
export function serializeConfigCheckboxes(modalElement, form, checkboxes = CONFIG_CHECKBOXES) {
    if (!modalElement || !form) return;

    checkboxes.forEach(({ selector, key }) => {
        const cb = modalElement.querySelector(selector);
        if (!cb) return;

        setHiddenField(form, key, cb.checked ? 'true' : 'false', {
            id: hiddenFieldId(key),
            disabled: false,
        });

        // Prevent the live checkbox from also submitting (checked → "on" plus hidden "true").
        if (cb.name) {
            cb.removeAttribute('name');
        }
    });
}
