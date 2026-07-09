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
        refreshMultiSelectButtonTextFromContext(cb);
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
        refreshMultiSelectButtonTextFromContext(target);
    }
}

function onDocumentInput(e) {
    const target = e.target;
    // When the user types in the Other free-text field, always attempt to refresh
    // the multi-select button label. refreshMultiSelectButtonTextFromContext is a
    // no-op for single-choice (no .multi-select-dropdown found), so it's safe to
    // call unconditionally here.
    if (target.classList.contains('other-text-input')) {
        refreshMultiSelectButtonTextFromContext(target);
    }
}

function findOtherTextInput(contextElement) {
    // Prefer searching within the nearest .form-item-block (one field per block).
    // The other-text-input may be a sibling of the select/wrapper div, not a
    // descendant, so we search the common ancestor block.
    const block = contextElement.closest('.form-item-block, .repeat-entry');
    if (block) {
        const input = block.querySelector('.other-text-input');
        if (input) return input;
    }

    const fieldId = contextElement.dataset?.fieldItemId
        || contextElement.dataset?.forField
        || extractFieldId(contextElement.name);
    if (fieldId) {
        return document.getElementById(`other-text-${fieldId}`);
    }
    return null;
}

function findMultiSelectParts(contextElement) {
    // The multi-select wrapper div (which carries data-allow-other) may be an
    // ANCESTOR of contextElement (when it's a checkbox inside the dropdown) OR a
    // SIBLING (when contextElement is the other-text-input that sits next to the
    // wrapper inside .form-item-block).  Handle both cases.
    let wrapper = contextElement.closest('[data-allow-other="true"]');

    if (!wrapper) {
        // contextElement is likely the other-text-input — find the wrapper in the
        // same .form-item-block / .repeat-entry ancestor.
        const block = contextElement.closest('.form-item-block, .repeat-entry');
        if (block) wrapper = block.querySelector('[data-allow-other="true"]');
    }
    if (!wrapper) return null;

    // The other-text-input is a SIBLING of the wrapper div (rendered by the
    // partial after the wrapper's closing tag), so search the parent block.
    const parentBlock = wrapper.closest('.form-item-block, .repeat-entry');
    const otherInput = parentBlock ? parentBlock.querySelector('.other-text-input') : null;

    return {
        btn: wrapper.querySelector('.multi-select-btn'),
        dropdown: wrapper.querySelector('.multi-select-dropdown'),
        otherInput,
        textSpan: wrapper.querySelector('.multi-select-text'),
    };
}

function handleSingleChoiceChange(select) {
    const otherInput = findOtherTextInput(select);
    if (!otherInput) return;

    if (select.value === OTHER_SENTINEL) {
        showOtherInput(otherInput);
    } else {
        hideOtherInput(otherInput);
    }
}

function handleMultiOtherToggle(checkbox) {
    const otherInput = findOtherTextInput(checkbox);
    if (!otherInput) return;

    if (checkbox.checked) {
        showOtherInput(otherInput);
        refreshMultiSelectButtonTextFromContext(checkbox);
    } else {
        hideOtherInput(otherInput);
        refreshMultiSelectButtonTextFromContext(checkbox);
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
function refreshMultiSelectButtonTextFromContext(contextElement) {
    const parts = findMultiSelectParts(contextElement);
    if (!parts?.btn || !parts.dropdown || !parts.textSpan) return;

    const labels = [];

    // Collect regular (non-Other) checked options
    parts.dropdown.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
        if (cb.classList.contains('other-option-checkbox')) return;
        const span = cb.nextElementSibling;
        if (span) labels.push(span.textContent.trim());
    });

    // Add Other typed value if checked
    const otherCb = parts.dropdown.querySelector('.other-option-checkbox');
    if (otherCb?.checked && parts.otherInput) {
        const typedVal = parts.otherInput.value.trim();
        if (typedVal) labels.push(typedVal);
    }

    parts.textSpan.textContent = labels.length > 0 ? labels.join(', ') : 'Select options...';
}

function extractFieldId(name) {
    if (!name) return null;
    const bracketMatch = name.match(/\[(\d+)\]/);
    if (bracketMatch) return bracketMatch[1];
    return null;
}

// Re-run after repeat sections add new entries
document.addEventListener('repeatEntryAdded', () => {
    document.querySelectorAll('.other-option-checkbox:checked').forEach(cb => {
        refreshMultiSelectButtonTextFromContext(cb);
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

export function appendOtherOptionToMultiDropdown(dropdown) {
    const wrapper = dropdown.closest('[data-allow-other="true"]');
    if (!wrapper || wrapper.dataset.allowOther !== 'true') return;
    if (dropdown.querySelector('.other-option-checkbox')) return;

    const divider = document.createElement('div');
    divider.className = 'option-item border-t border-gray-100 mt-1 pt-1';

    const label = document.createElement('label');
    label.className = 'inline-flex items-center cursor-pointer w-full';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'other-option-checkbox form-checkbox h-4 w-4 text-green-600 border-gray-300 rounded focus:ring-green-500';

    const span = document.createElement('span');
    span.className = 'ml-2 text-sm text-gray-500 italic';
    span.textContent = 'Other (please specify)...';

    label.appendChild(cb);
    label.appendChild(span);
    divider.appendChild(label);
    dropdown.appendChild(divider);
}

/** Restore a saved custom value for calculated lists with allow_other enabled. */
export function restoreOtherSelectionForCalculatedList(selectElement, savedValue) {
    if (!savedValue || selectElement.dataset.allowOther !== 'true') return;

    appendOtherOptionToSelect(selectElement);
    selectElement.value = OTHER_SENTINEL;

    const otherInput = findOtherTextInput(selectElement);
    if (otherInput) {
        otherInput.value = savedValue;
        otherInput.classList.remove('hidden');
    }

    debugLog(MODULE, `Restored calculated-list Other value for field ${selectElement.dataset.fieldItemId || selectElement.id}`);
}
