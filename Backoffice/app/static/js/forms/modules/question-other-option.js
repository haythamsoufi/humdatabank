/**
 * question-other-option.js
 *
 * Handles the "Other (please specify)" option for single_choice and multiple_choice
 * questions that have `allow_other` enabled.
 *
 * Single-choice: a `<select>` with an `<option value="__other__">` entry.
 *   - Selecting it reveals a free-text input below the select.
 *   - Deselecting hides and clears the input.
 *
 * Multiple-choice: a custom checkbox dropdown with an `.other-option-checkbox` item.
 *   - Checking it reveals a free-text input below the wrapper div.
 *   - Unchecking hides and clears the input.
 *   - The typed value is submitted via a real `<input name="field_other_text[id]">`.
 *
 * The module also updates the multi-select button text to reflect the Other value.
 */

import { debugLog } from './debug.js';

const MODULE = 'question-other-option';
const OTHER_SENTINEL = '__other__';

let _listenersAttached = false;

export function initQuestionOtherOption() {
    debugLog(MODULE, 'Initializing Other option handlers');
    attachListeners();
    // Update multi-select button text for any pre-loaded Other selections
    document.querySelectorAll('.other-option-checkbox:checked').forEach(cb => {
        const fieldId = cb.dataset.fieldId;
        if (fieldId) refreshMultiSelectButtonText(fieldId);
    });
}

function attachListeners() {
    if (_listenersAttached) return;
    _listenersAttached = true;

    // Single-choice: watch select changes
    document.addEventListener('change', onDocumentChange);

    // Keep multi-select button text in sync when the Other text input is typed in
    document.addEventListener('input', onDocumentInput);

    debugLog(MODULE, 'Other option listeners attached');
}

function onDocumentChange(e) {
    const target = e.target;

    // Single-choice select
    if (target.tagName === 'SELECT' && target.dataset.allowOther === 'true') {
        handleSingleChoiceChange(target);
        return;
    }

    // Multiple-choice "Other" toggle checkbox
    if (target.classList.contains('other-option-checkbox')) {
        handleMultiOtherToggle(target);
        return;
    }

    // Any other checkbox inside a multi-select dropdown that has allow_other
    if (target.type === 'checkbox' && target.closest('.multi-select-dropdown')) {
        const dropdown = target.closest('.multi-select-dropdown');
        const fieldId = dropdown?.dataset.fieldId;
        if (fieldId) refreshMultiSelectButtonText(fieldId);
    }
}

function onDocumentInput(e) {
    const target = e.target;
    if (target.classList.contains('other-text-input') && target.dataset.forField) {
        const fieldId = target.dataset.forField;
        // For multi-select: refresh the button text to show the typed value
        const multiWrapper = document.getElementById(`field-${fieldId}`);
        if (multiWrapper?.dataset.allowOther === 'true') {
            refreshMultiSelectButtonText(fieldId);
        }
    }
}

function handleSingleChoiceChange(select) {
    const fieldId = extractFieldId(select.name) || select.dataset.fieldItemId;
    const otherInput = fieldId ? document.getElementById(`other-text-${fieldId}`) : null;
    if (!otherInput) return;

    if (select.value === OTHER_SENTINEL) {
        showOtherInput(otherInput);
    } else {
        hideOtherInput(otherInput);
    }
}

function handleMultiOtherToggle(checkbox) {
    const fieldId = checkbox.dataset.fieldId;
    const otherInput = fieldId ? document.getElementById(`other-text-${fieldId}`) : null;
    if (!otherInput) return;

    if (checkbox.checked) {
        showOtherInput(otherInput);
        refreshMultiSelectButtonText(fieldId);
    } else {
        hideOtherInput(otherInput);
        refreshMultiSelectButtonText(fieldId);
    }
}

function showOtherInput(input) {
    input.classList.remove('hidden');
    input.focus();
}

function hideOtherInput(input) {
    input.classList.add('hidden');
    input.value = '';
}

/**
 * Rebuild the multi-select button label, substituting any "Other" value with
 * the typed free-text so the summary is accurate.
 */
function refreshMultiSelectButtonText(fieldId) {
    const btn = document.querySelector(`.multi-select-btn[data-field-id="${fieldId}"]`);
    const dropdown = document.querySelector(`.multi-select-dropdown[data-field-id="${fieldId}"]`);
    const otherInput = document.getElementById(`other-text-${fieldId}`);
    const textSpan = btn?.querySelector('.multi-select-text');
    if (!btn || !dropdown || !textSpan) return;

    const labels = [];

    // Collect regular (non-Other) checked options
    dropdown.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
        if (cb.classList.contains('other-option-checkbox')) return; // handled separately
        const span = cb.nextElementSibling;
        if (span) labels.push(span.textContent.trim());
    });

    // Add Other typed value if checked
    const otherCb = dropdown.querySelector('.other-option-checkbox');
    if (otherCb?.checked && otherInput) {
        const typedVal = otherInput.value.trim();
        if (typedVal) labels.push(typedVal);
    }

    textSpan.textContent = labels.length > 0 ? labels.join(', ') : 'Select options...';
}

function extractFieldId(name) {
    if (!name) return null;
    const m = name.match(/\[(\d+)\]/);
    return m ? m[1] : null;
}

// Re-run after repeat sections add new entries
document.addEventListener('repeatEntryAdded', () => {
    document.querySelectorAll('.other-option-checkbox:checked').forEach(cb => {
        const fieldId = cb.dataset.fieldId;
        if (fieldId) refreshMultiSelectButtonText(fieldId);
    });
});

// Expose for calculated-lists-runtime.js to call after populating options
export function appendOtherOptionToSelect(selectElement) {
    if (selectElement.dataset.allowOther !== 'true') return;
    if (selectElement.querySelector(`option[value="${OTHER_SENTINEL}"]`)) return;
    const opt = document.createElement('option');
    opt.value = OTHER_SENTINEL;
    opt.textContent = 'Other (please specify)...';
    selectElement.appendChild(opt);
}

export function appendOtherOptionToMultiDropdown(dropdown, fieldId) {
    const wrapper = document.getElementById(`field-${fieldId}`);
    if (!wrapper || wrapper.dataset.allowOther !== 'true') return;
    if (dropdown.querySelector('.other-option-checkbox')) return;

    const divider = document.createElement('div');
    divider.className = 'option-item border-t border-gray-100 mt-1 pt-1';

    const label = document.createElement('label');
    label.className = 'inline-flex items-center cursor-pointer w-full';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'other-option-checkbox form-checkbox h-4 w-4 text-green-600 border-gray-300 rounded focus:ring-green-500';
    cb.dataset.fieldId = fieldId;

    const span = document.createElement('span');
    span.className = 'ml-2 text-sm text-gray-500 italic';
    span.textContent = 'Other (please specify)...';

    label.appendChild(cb);
    label.appendChild(span);
    divider.appendChild(label);
    dropdown.appendChild(divider);
}
