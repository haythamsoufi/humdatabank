import { debugLog, debugWarn } from './debug.js';

const MODULE_NAME = 'data-availability';

export function initDataAvailability() {
    debugLog(MODULE_NAME, '\n=== INITIALIZING DATA AVAILABILITY ===');
    setupDataAvailabilityCheckboxes();
}

function setupDataAvailabilityCheckboxes() {
    debugLog(MODULE_NAME, '\n=== SETTING UP DATA AVAILABILITY CHECKBOXES ===');

    // First, fix any invalid states (both checkboxes checked)
    const allFields = document.querySelectorAll('.form-item-block');
    debugLog(MODULE_NAME, 'Found form fields:', allFields.length);

    allFields.forEach((field, index) => {
        debugLog(MODULE_NAME, `\nProcessing field ${index + 1}/${allFields.length}`);
        const dataNotAvailable = field.querySelector('input[name*="_data_not_available"]');
        const notApplicable = field.querySelector('input[name*="_not_applicable"]');

        debugLog(MODULE_NAME, 'Data not available checkbox:', dataNotAvailable?.name);
        debugLog(MODULE_NAME, 'Not applicable checkbox:', notApplicable?.name);

        if (dataNotAvailable && notApplicable && dataNotAvailable.checked && notApplicable.checked) {
            debugLog(MODULE_NAME, 'Found field with both checkboxes checked - fixing invalid state');
            // If both are checked, uncheck the "not applicable" one
            notApplicable.checked = false;
        }

        // Handle initial state - if either checkbox is checked, disable and clear the field
        if ((dataNotAvailable && dataNotAvailable.checked) || (notApplicable && notApplicable.checked)) {
            debugLog(MODULE_NAME, 'Found field with data availability checkbox checked - disabling and clearing field');
            toggleFieldInputs(field, true);
        }
    });

    // Use event delegation so that data availability works for:
    // - Standard sections (indicator/question)
    // - Dynamic indicator sections (server-rendered and newly added via render-pending)
    // - Repeat sections (initial and newly added entries)
    const formRoot = document.querySelector('#entry-form-ui') || document;
    formRoot.addEventListener('change', function(event) {
        const checkbox = event.target;
        if (checkbox.type !== 'checkbox' || !checkbox.name) return;
        if (!checkbox.name.includes('_data_not_available') && !checkbox.name.includes('_not_applicable')) return;

        debugLog(MODULE_NAME, '\n=== CHECKBOX CHANGE EVENT (delegated) ===');
        debugLog(MODULE_NAME, 'Checkbox:', checkbox.name);
        debugLog(MODULE_NAME, 'New state:', checkbox.checked);

        const currentFieldInfo = getFieldInfo(checkbox.name);
        if (!currentFieldInfo) {
            debugWarn(MODULE_NAME, 'Could not parse checkbox name:', checkbox.name);
            return;
        }

        const fieldContainer = findFieldContainer(checkbox);
        if (!fieldContainer) {
            debugWarn(MODULE_NAME, 'Could not find field container for checkbox:', checkbox.name);
            return;
        }

        const oppositeType = currentFieldInfo.checkboxType === 'data_not_available' ? 'not_applicable' : 'data_not_available';
        let oppositeCheckbox;

        if (currentFieldInfo.type === 'dynamic') {
            const prefix = currentFieldInfo.namePrefix || 'dynamic_';
            const oppositeCheckboxName = `${prefix}${currentFieldInfo.fieldId}_${oppositeType}`;
            oppositeCheckbox = document.querySelector(`input[name="${CSS.escape(oppositeCheckboxName)}"]`);
        } else if (currentFieldInfo.type === 'repeat') {
            oppositeCheckbox = fieldContainer.querySelector(`input[name*="${oppositeType}"]`);
        } else {
            const oppositeCheckboxName = `${currentFieldInfo.type}_${currentFieldInfo.fieldId}_${oppositeType}`;
            oppositeCheckbox = document.querySelector(`input[name="${CSS.escape(oppositeCheckboxName)}"]`);
        }

        debugLog(MODULE_NAME, 'Found opposite checkbox:', oppositeCheckbox?.name);

        if (checkbox.checked) {
            debugLog(MODULE_NAME, 'Checkbox checked - disabling and clearing field');
            if (oppositeCheckbox) oppositeCheckbox.checked = false;
            toggleFieldInputs(fieldContainer, true);
        } else {
            debugLog(MODULE_NAME, 'Checkbox unchecked - re-enabling if opposite not checked');
            if (!oppositeCheckbox || !oppositeCheckbox.checked) {
                toggleFieldInputs(fieldContainer, false);
            }
        }
        debugLog(MODULE_NAME, '=== END CHECKBOX CHANGE EVENT ===\n');
    });

    debugLog(MODULE_NAME, '=== FINISHED SETTING UP DATA AVAILABILITY (delegated) ===\n');
}

// Listen for repeat entry additions to reinitialize data availability
document.addEventListener('repeatEntryAdded', function(event) {
    debugLog(MODULE_NAME, '\n=== REPEAT ENTRY ADDED - REINITIALIZING DATA AVAILABILITY ===');
    const container = event.detail.container;
    if (container) {
        debugLog(MODULE_NAME, 'Reinitializing data availability for new repeat entry');

        // For newly created repeat entries, we should NOT auto-disable fields based on initial checkbox states
        // because they are created clean. Only respond to user interactions via event delegation.

        // However, we should still ensure all data availability checkboxes start unchecked
        const fields = container.querySelectorAll('.form-item-block');
        fields.forEach((field, index) => {
            const dataNotAvailable = field.querySelector('input[name*="_data_not_available"]');
            const notApplicable = field.querySelector('input[name*="_not_applicable"]');

            // Ensure data availability checkboxes start unchecked
            if (dataNotAvailable && dataNotAvailable.checked) {
                debugLog(MODULE_NAME, `⚠️ Forcing data_not_available checkbox to unchecked state in new repeat entry`);
                dataNotAvailable.checked = false;
            }
            if (notApplicable && notApplicable.checked) {
                debugLog(MODULE_NAME, `⚠️ Forcing not_applicable checkbox to unchecked state in new repeat entry`);
                notApplicable.checked = false;
            }

            // Ensure all fields in the new repeat entry are enabled and clean
            const allInputs = field.querySelectorAll('input, select, textarea');
            const multiSelectButtons = field.querySelectorAll('.multi-select-btn');

            allInputs.forEach(input => {
                // Skip data availability checkboxes
                if (input.name.includes('_data_not_available') || input.name.includes('_not_applicable')) {
                    return;
                }

                // Remove any data-availability-disabled attributes and ensure enabled state
                if (input.hasAttribute('data-availability-disabled')) {
                    debugLog(MODULE_NAME, `🧽 Cleaning up input ${input.name} in new repeat entry`);
                    input.removeAttribute('data-availability-disabled');
                    input.disabled = false;
                    input.style.opacity = '';
                    input.style.backgroundColor = '';
                    input.style.cursor = '';
                    input.style.pointerEvents = '';
                }
            });

            multiSelectButtons.forEach(button => {
                if (button.hasAttribute('data-availability-disabled')) {
                    debugLog(MODULE_NAME, `🧽 Cleaning up multi-select button in new repeat entry`);
                    button.removeAttribute('data-availability-disabled');
                    button.disabled = false;
                    button.style.opacity = '';
                    button.style.backgroundColor = '';
                    button.style.cursor = '';
                    button.style.pointerEvents = '';
                }
            });
        });

        debugLog(MODULE_NAME, '✅ New repeat entry is clean and ready for user interaction');
    }
    debugLog(MODULE_NAME, '=== FINISHED REINITIALIZING DATA AVAILABILITY FOR REPEAT ENTRY ===\n');
});

function findFieldContainer(checkbox) {
    // Start from the checkbox and go up the DOM tree to find the field container
    let container = checkbox.closest('[data-item-id]');
    if (!container) {
        // Fallback: try to find by going up to form-item-block
        container = checkbox.closest('.form-item-block');
    }
    return container;
}

function getFieldInfo(checkboxName) {
    debugLog(MODULE_NAME, `Analyzing checkbox name: ${checkboxName}`);

    let match;

    // Pattern 1: indicator_123_data_not_available or indicator_123_not_applicable
    match = checkboxName.match(/^(indicator|question)_(\d+)_(data_not_available|not_applicable)$/);
    if (match) {
        return {
            type: match[1],
            fieldId: match[2],
            checkboxType: match[3],
            fullFieldId: match[2]
        };
    }

    // Pattern 2a: indicator_dynamic_11_data_not_available (dynamic section checkboxes from template)
    match = checkboxName.match(/^indicator_dynamic_(.+)_(data_not_available|not_applicable)$/);
    if (match) {
        return {
            type: 'dynamic',
            fieldId: match[1],
            checkboxType: match[2],
            fullFieldId: match[1],
            namePrefix: 'indicator_dynamic_'
        };
    }

    // Pattern 2b: dynamic_123_... or dynamic_pending_... (numeric or pending assignment IDs)
    match = checkboxName.match(/^dynamic_(.+)_(data_not_available|not_applicable)$/);
    if (match) {
        return {
            type: 'dynamic',
            fieldId: match[1],
            checkboxType: match[2],
            fullFieldId: match[1],
            namePrefix: 'dynamic_'
        };
    }

    // Pattern 3: repeat fields - e.g., repeat_23_1_field_0_data_not_available
    match = checkboxName.match(/^repeat_(\d+)_(\d+)_field_(\d+)_(data_not_available|not_applicable)$/);
    if (match) {
        return {
            type: 'repeat',
            sectionId: match[1],
            instanceNumber: match[2],
            fieldIndex: match[3],
            checkboxType: match[4],
            fullFieldId: `${match[1]}_${match[2]}_${match[3]}`
        };
    }

    debugLog(MODULE_NAME, `Could not parse checkbox name: ${checkboxName}`);
    return null;
}

function toggleFieldInputs(fieldContainer, disable, processedIds = new Set()) {
    if (!fieldContainer) {
        debugWarn(MODULE_NAME, 'No field container provided to toggleFieldInputs');
        return;
    }

    debugLog(MODULE_NAME, '=== TOGGLING FIELD INPUTS ===');
    debugLog(MODULE_NAME, 'Container:', fieldContainer);
    debugLog(MODULE_NAME, 'Disable:', disable);

    // Get the field ID and check if we've already processed this container
    const fieldId = fieldContainer.getAttribute('data-item-id');
    debugLog(MODULE_NAME, 'Field ID:', fieldId);

    if (fieldId && processedIds.has(fieldId)) {
        debugLog(MODULE_NAME, 'Already processed field ID:', fieldId);
        return;
    }
    if (fieldId) {
        processedIds.add(fieldId);
        debugLog(MODULE_NAME, 'Added to processed IDs:', fieldId);
    }

    // Find all inputs in this field container
    const inputs = fieldContainer.querySelectorAll('input, select, textarea');
    debugLog(MODULE_NAME, 'Found inputs:', inputs.length);

    // Also find multi-select buttons
    const multiSelectButtons = fieldContainer.querySelectorAll('.multi-select-btn');
    debugLog(MODULE_NAME, 'Found multi-select buttons:', multiSelectButtons.length);

    inputs.forEach((input, index) => {
        debugLog(MODULE_NAME, `\nProcessing input ${index + 1}/${inputs.length}:`, input);
        debugLog(MODULE_NAME, 'Input name:', input.name);
        debugLog(MODULE_NAME, 'Input type:', input.type);
        debugLog(MODULE_NAME, 'Current value:', input.value);

        // Skip the data availability checkboxes themselves
        if (input.name.includes('_data_not_available') || input.name.includes('_not_applicable')) {
            debugLog(MODULE_NAME, 'Skipping data availability checkbox');
            return;
        }

        // Include indirect reach fields in the toggle (don't skip them)
        if (input.name.includes('_indirect_reach')) {
            debugLog(MODULE_NAME, 'Processing indirect reach field');
        }

        if (disable) {
            debugLog(MODULE_NAME, 'Disabling and clearing input');

            // Set data-availability-disabled attribute to track state
            input.setAttribute('data-availability-disabled', 'true');

            // Clear the input
            if (input.type === 'checkbox' || input.type === 'radio') {
                debugLog(MODULE_NAME, 'Clearing checkbox/radio');
                const oldValue = input.checked;
                input.checked = false;
                debugLog(MODULE_NAME, `Changed checked from ${oldValue} to ${input.checked}`);
            } else if (input.tagName.toLowerCase() === 'select') {
                debugLog(MODULE_NAME, 'Clearing select');
                const oldValue = input.selectedIndex;
                input.selectedIndex = 0;
                debugLog(MODULE_NAME, `Changed selectedIndex from ${oldValue} to ${input.selectedIndex}`);
            } else {
                debugLog(MODULE_NAME, 'Clearing text/number input');
                const oldValue = input.value;
                input.value = '';

                // Clear the formatted display if it exists
                const container = input.closest('.number-input-container');
                if (container) {
                    const formattedDisplay = container.querySelector('.formatted-number');
                    if (formattedDisplay) {
                        formattedDisplay.textContent = '';
                        formattedDisplay.style.display = 'none';
                    }
                }

                debugLog(MODULE_NAME, `Changed value from "${oldValue}" to "${input.value}"`);
            }

            // Apply disabled styling
            input.disabled = true;
            input.style.opacity = '0.5';
            input.style.backgroundColor = '#f3f4f6';
            // Ensure background override even when a CSS rule has `!important`
            input.style.setProperty('background', '#f3f4f6', 'important');
            input.style.cursor = 'not-allowed';
            input.style.pointerEvents = 'none';

            // Add MutationObserver to prevent value changes
            const observer = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    if (mutation.type === 'attributes' &&
                        (mutation.attributeName === 'value' ||
                         mutation.attributeName === 'data-value' ||
                         mutation.attributeName === 'valueAsNumber')) {
                        input.value = '';
                        input.valueAsNumber = NaN;
                    }
                });
            });

            observer.observe(input, {
                attributes: true,
                attributeFilter: ['value', 'data-value', 'valueAsNumber'],
                characterData: true,
                subtree: true
            });

            // Store the observer for cleanup
            input._availabilityObserver = observer;

            // Add input event listener to maintain disabled state
            const preventInput = (e) => {
                if (input.getAttribute('data-availability-disabled') === 'true') {
                    e.preventDefault();
                    e.stopImmediatePropagation(); // Stop other handlers
                    input.value = '';
                    if (input.type === 'number') {
                        input.valueAsNumber = NaN;
                        // Clear the formatted display if it exists
                        const container = input.closest('.number-input-container');
                        if (container) {
                            const formattedDisplay = container.querySelector('.formatted-number');
                            if (formattedDisplay) {
                                formattedDisplay.textContent = '';
                                formattedDisplay.style.display = 'none';
                            }
                        }
                    }
                    return false;
                }
            };

            // Add handlers for all possible input events
            ['input', 'change', 'keydown', 'keyup', 'mousedown', 'mouseup', 'focus'].forEach(eventType => {
                input.addEventListener(eventType, preventInput, { capture: true, passive: false });
            });

            // Store the handler for cleanup
            input._availabilityInputHandler = preventInput;

            debugLog(MODULE_NAME, 'Applied disabled styling and locked input');
        } else {
            debugLog(MODULE_NAME, 'Re-enabling input');

            // Remove data-availability-disabled attribute
            input.removeAttribute('data-availability-disabled');

            // Remove MutationObserver
            if (input._availabilityObserver) {
                input._availabilityObserver.disconnect();
                delete input._availabilityObserver;
            }

            // Remove input event listener
            if (input._availabilityInputHandler) {
                input.removeEventListener('input', input._availabilityInputHandler, true);
                delete input._availabilityInputHandler;
            }

            // Re-enable the input
            input.disabled = false;
            input.style.opacity = '';
            input.style.backgroundColor = '';
            // Remove the forced background when re-enabling
            input.style.removeProperty('background');
            input.style.cursor = '';
            input.style.pointerEvents = '';

            debugLog(MODULE_NAME, 'Removed disabled styling and unlocked input');
        }
    });

    // Handle multi-select buttons
    multiSelectButtons.forEach((button, index) => {
        debugLog(MODULE_NAME, `\nProcessing multi-select button ${index + 1}/${multiSelectButtons.length}:`, button);

        if (disable) {
            debugLog(MODULE_NAME, 'Disabling multi-select button');

            // Set data-availability-disabled attribute to track state
            button.setAttribute('data-availability-disabled', 'true');

            // Clear all selected options in the corresponding dropdown
            const fieldId = button.getAttribute('data-field-id');
            const dropdown = fieldContainer.querySelector(`.multi-select-dropdown[data-field-id="${fieldId}"]`);
            if (dropdown) {
                const checkboxes = dropdown.querySelectorAll('input[type="checkbox"]');
                checkboxes.forEach(checkbox => {
                    checkbox.checked = false;
                });

                // Update button text to show no selections
                const textSpan = button.querySelector('.multi-select-text');
                if (textSpan) {
                    textSpan.textContent = 'Select options...';
                }

                debugLog(MODULE_NAME, `Cleared ${checkboxes.length} multi-select checkboxes`);
            }

            // Apply disabled styling to button
            button.disabled = true;
            button.style.opacity = '0.5';
            button.style.backgroundColor = '#f3f4f6';
            button.style.cursor = 'not-allowed';
            button.style.pointerEvents = 'none';

            // Close any open dropdown
            if (dropdown) {
                dropdown.classList.add('hidden');
            }

            debugLog(MODULE_NAME, 'Applied disabled styling to multi-select button');
        } else {
            debugLog(MODULE_NAME, 'Re-enabling multi-select button');

            // Remove data-availability-disabled attribute
            button.removeAttribute('data-availability-disabled');

            // Re-enable the button
            button.disabled = false;
            button.style.opacity = '';
            button.style.backgroundColor = '';
            button.style.cursor = '';
            button.style.pointerEvents = '';

            debugLog(MODULE_NAME, 'Removed disabled styling from multi-select button');
        }
    });

    // Handle cloned fields in flexible layouts
    if (fieldId) {
        debugLog(MODULE_NAME, '\nChecking for cloned fields');
        const clonedFields = document.querySelectorAll(`[data-item-id="${fieldId}"][data-layout-clone="true"]`);
        debugLog(MODULE_NAME, 'Found cloned fields:', clonedFields.length);

        clonedFields.forEach((clonedField, index) => {
            debugLog(MODULE_NAME, `Processing clone ${index + 1}/${clonedFields.length}`);
            if (!processedIds.has(fieldId)) {
                debugLog(MODULE_NAME, 'Processing cloned field');
                toggleFieldInputs(clonedField, disable, processedIds);
            } else {
                debugLog(MODULE_NAME, 'Skipping already processed clone');
            }
        });
    }

    debugLog(MODULE_NAME, '=== FINISHED TOGGLING FIELD INPUTS ===\n');
}
