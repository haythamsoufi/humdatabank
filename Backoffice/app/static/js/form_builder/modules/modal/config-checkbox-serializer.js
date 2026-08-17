/**
 * Serialize boolean config-panel checkboxes as explicit hidden inputs.
 *
 * HTML checkboxes are absent from FormData when unchecked, which makes it
 * impossible for the backend to distinguish "user unchecked this box" from
 * "this box was not part of the payload".
 *
 * Do NOT write into `input[name="config"]`. That field is `#item-matrix-config`,
 * which lives inside `#item-matrix-fields`. For non-matrix items that panel is
 * hidden and every input in it is disabled, so FormData drops the value.
 *
 * Instead, write one always-enabled hidden input per checkbox onto the form
 * root (`name="<key>"`, value `"true"` / `"false"`). The backend already
 * treats those keys as explicit booleans.
 *
 * @module config-checkbox-serializer
 */

/**
 * Config-panel checkboxes that must always be present in the submit payload,
 * regardless of whether they are checked or not.
 *
 * Add new entries here whenever a new config checkbox is introduced in the
 * item modal and its backend handler uses preserve-existing fallback logic.
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
 * Write the current checked state of every config-panel checkbox as a
 * form-root hidden input that cannot be disabled by the matrix/type panels.
 *
 * Only checkboxes that are found in `modalElement` are written — if the
 * element is absent (because the checkbox is not rendered for this item type)
 * no hidden input is created, so the backend preserves the stored value.
 *
 * @param {HTMLElement} modalElement - The item-modal root element.
 * @param {HTMLFormElement} form - The form that will be submitted.
 * @param {Array<{selector: string, key: string}>} [checkboxes] - Defaults to CONFIG_CHECKBOXES.
 */
export function serializeConfigCheckboxes(modalElement, form, checkboxes = CONFIG_CHECKBOXES) {
    if (!modalElement || !form) return;

    checkboxes.forEach(({ selector, key }) => {
        const cb = modalElement.querySelector(selector);
        if (!cb) return;

        const fieldId = hiddenFieldId(key);
        let field = form.querySelector(`#${fieldId}`);
        if (!field) {
            field = document.createElement('input');
            field.type = 'hidden';
            field.id = fieldId;
            form.appendChild(field);
        }
        field.name = key;
        field.disabled = false;
        field.value = cb.checked ? 'true' : 'false';
        // Prevent the live checkbox from also submitting (checked → "on" plus
        // hidden "true" becomes an array that the backend does not treat as true).
        if (cb.name) {
            cb.removeAttribute('name');
        }
    });
}
