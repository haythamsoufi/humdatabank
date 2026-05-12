import { debugLog } from './debug.js';

export function initCheckboxHandlers() {
    setupYesNoCheckboxHandlers();
}

function setupYesNoCheckboxHandlers() {
    debugLog('🔄 Setting up Yes/No checkbox handlers...');

    // Use event delegation to handle all yes/no checkboxes, including dynamically added ones
    document.addEventListener('change', function(event) {
        const checkbox = event.target;

        // Check if this is a yes/no checkbox by looking for specific patterns
        if (checkbox.type === 'checkbox' &&
            (checkbox.value === 'yes' || checkbox.value === 'no') &&
            (checkbox.name.includes('_standard_value') ||
             checkbox.name.startsWith('field_value['))) {

            if (checkbox.checked) {
                handleYesNoCheckbox(checkbox, checkbox.name);
            } else {
                // Handle unchecking - ensure the field value is cleared
                handleYesNoUncheck(checkbox, checkbox.name);
            }
        }
    });

    debugLog('✅ Yes/No checkbox handlers setup completed');
}

export function handleYesNoCheckbox(clickedCheckbox, fieldName) {
    // Find all checkboxes with the same field name
    const checkboxes = document.querySelectorAll(`input[name="${fieldName}"]`);

    // Always ensure mutual exclusivity - if this checkbox is being checked, uncheck all others
    if (clickedCheckbox.checked) {
        checkboxes.forEach(checkbox => {
            if (checkbox !== clickedCheckbox) {
                checkbox.checked = false;
            }
        });

        // Remove any clear signal since we now have a selected value
        const clearInput = document.querySelector(`input[name="${fieldName}_clear_field"]`);
        if (clearInput) {
            clearInput.remove();
            debugLog(`🧹 Removed clear signal for ${fieldName} since checkbox is now selected`);
        }
    }

    // Additional safety check: if somehow both are checked, keep only the clicked one
    let checkedCount = 0;
    let checkedBoxes = [];
    checkboxes.forEach(checkbox => {
        if (checkbox.checked) {
            checkedCount++;
            checkedBoxes.push(checkbox);
        }
    });

    if (checkedCount > 1) {
        debugLog(`Warning: Found ${checkedCount} checked boxes, forcing mutual exclusivity`);
        checkboxes.forEach(checkbox => {
            if (checkbox !== clickedCheckbox) {
                checkbox.checked = false;
            }
        });
    }

    // Trigger relevance recalculation in a debounced, non-re-entrant way.
    // (Direct checkAll calls can cause runaway loops when conditions.js is clearing fields.)
    if (window.requestRelevanceRecheck) {
        Promise.resolve().then(() => window.requestRelevanceRecheck('yesno:check'));
    } else if (window.checkAllRelevanceConditions) {
        Promise.resolve().then(() => window.checkAllRelevanceConditions({ reason: 'yesno:check' }));
    }
}

export function handleYesNoUncheck(uncheckedCheckbox, fieldName) {
    debugLog(`🔄 Handling uncheck for checkbox: ${fieldName} value: ${uncheckedCheckbox.value}`);

    // Find all checkboxes with the same field name
    const checkboxes = document.querySelectorAll(`input[name="${fieldName}"]`);

    // Check if any checkbox in the group is still checked
    let anyStillChecked = false;
    checkboxes.forEach(checkbox => {
        if (checkbox.checked) {
            anyStillChecked = true;
        }
    });

    // Always clean up any existing clear indicator
    const existingClearInput = document.querySelector(`input[name="${fieldName}_cleared"]`);
    if (existingClearInput) {
        existingClearInput.remove();
    }

    // If no checkbox is checked anymore, add a special hidden input to signal clearing
    if (!anyStillChecked) {
        debugLog(`📭 All checkboxes unchecked for ${fieldName}, adding clear signal`);

        // Create a hidden input with a special value to signal clearing
        const clearInput = document.createElement('input');
        clearInput.type = 'hidden';
        clearInput.name = fieldName + '_clear_field';
        clearInput.value = 'CLEAR_FIELD_VALUE';

        // Insert it right after the unchecked checkbox
        uncheckedCheckbox.parentNode.insertBefore(clearInput, uncheckedCheckbox.nextSibling);

        debugLog(`✅ Added clear signal input for ${fieldName}`);
    }

    // After handling uncheck, trigger relevance recalculation (debounced).
    // If this change was caused by bulk-clearing hidden fields, conditions.js will schedule a single
    // relevance pass; don't cascade additional full scans.
    if (window.__ifrcConditionsIsClearing) {
        return;
    }

    if (window.requestRelevanceRecheck) {
        Promise.resolve().then(() => window.requestRelevanceRecheck('yesno:uncheck'));
    } else if (window.checkAllRelevanceConditions) {
        Promise.resolve().then(() => window.checkAllRelevanceConditions({ reason: 'yesno:uncheck' }));
    }
}

// Make functions globally available for debugging
window.handleYesNoUncheck = handleYesNoUncheck;
window.handleYesNoCheckbox = handleYesNoCheckbox;
