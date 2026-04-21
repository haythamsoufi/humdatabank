import { getUnifiedFieldValue, setUnifiedFieldValue, initializeFieldListeners } from './form-item-utils.js';
import { debugLog, debugWarn, debugError } from './debug.js';

export function initFieldManagement() {
    initializeFieldListeners();
    setupDisaggregationRadioHandlers();

    // Make functions globally available for conditions (legacy compatibility)
    window.getFieldValue = getUnifiedFieldValue;
    window.getCurrentFieldValue = (fieldId, mode) => getUnifiedFieldValue(fieldId, mode, true);
}

/**
 * Set up event delegation for disaggregation mode radio buttons
 * This replaces inline onchange handlers to comply with CSP
 */
function setupDisaggregationRadioHandlers() {
    debugLog('field-management', 'Setting up disaggregation radio button handlers...');

    // Use event delegation to handle all disaggregation radio buttons
    document.addEventListener('change', function(event) {
        const radio = event.target;

        // Check if this is a disaggregation mode radio button
        if (radio.type === 'radio' &&
            (radio.name.includes('_reporting_mode') || radio.name.includes('reporting_mode'))) {

            // Extract field ID and item type from the radio button's attributes or name
            // Radio names: "indicator_123_reporting_mode", "dynamic_456_reporting_mode", or
            // for pending (dynamically added) indicators: "dynamic_pending_1234567890_abc_reporting_mode"
            const nameMatch = radio.name.match(/^(indicator|dynamic)_(.+)_reporting_mode$/);
            if (nameMatch) {
                const itemType = nameMatch[1]; // 'indicator' or 'dynamic'
                const idFromName = nameMatch[2]; // This is field ID for indicators, assignment ID for dynamic
                const selectedMode = radio.value;

                let fieldId = idFromName;

                // For dynamic indicators, the name contains the assignment ID, not the field ID
                // We need to find the field container with this assignment ID to get the actual field ID
                if (itemType === 'dynamic') {
                    const fieldContainer = radio.closest('[data-assignment-id]');
                    if (fieldContainer) {
                        const assignmentId = fieldContainer.getAttribute('data-assignment-id');
                        // Verify the assignment ID matches what we extracted from the name
                        if (assignmentId === idFromName) {
                            // Get the field ID from the container's data-item-id
                            const containerFieldId = fieldContainer.getAttribute('data-item-id');
                            if (containerFieldId) {
                                fieldId = containerFieldId;
                            }
                        }
                    }
                }

                debugLog('field-management', `Disaggregation radio changed: fieldId=${fieldId}, mode=${selectedMode}, type=${itemType}`);

                // Call the toggle function with the extracted parameters
                if (window.toggleDisaggregationInputs) {
                    window.toggleDisaggregationInputs(fieldId, selectedMode, itemType, radio);
                }
            }
        }
    });

    debugLog('field-management', '✅ Disaggregation radio button handlers setup completed');
}

export function getFieldValue(fieldId, mode = 'total') {
    // Use unified field value retrieval
    return getUnifiedFieldValue(fieldId, mode, false);
}

export function getIndirectReachValue(fieldId, itemType = 'indicator') {
    // Normalize field ID
    const normalizedFieldId = fieldId.toString().replace(/^indicator_/, '');

    // Check if this field is disabled by data availability checkboxes
    const isDataNotAvailable = isFieldDisabledByDataAvailability(normalizedFieldId);
    if (isDataNotAvailable) {
        return null;
    }

    // Try to find the indirect reach input
    const indirectReachInput = document.querySelector(`input[name="${itemType}_${fieldId}_indirect_reach"]`) ||
                               document.querySelector(`input[name="${itemType}_${normalizedFieldId}_indirect_reach"]`);

    if (indirectReachInput) {
        const value = getInputValue(indirectReachInput);
        return value;
    }

    // Check existing data for indirect reach value in disaggregation structure
    if (window.existingData) {
        const dataKey = `field_value[${normalizedFieldId}]`;
        const existingValue = window.existingData[dataKey];

        // Handle both object and JSON string formats
        let parsedValue = existingValue;
        if (typeof existingValue === 'string' && (existingValue.includes('{') || existingValue.includes('['))) {
            try {
                parsedValue = JSON.parse(existingValue);
            } catch (e) {
                // If parsing fails, use original value
                parsedValue = existingValue;
            }
        }

        if (parsedValue && typeof parsedValue === 'object' && parsedValue.values && parsedValue.values.indirect !== undefined) {
            return parsedValue.values.indirect;
        }
    }

    return null;
}

export function getCurrentFieldValue(fieldId, mode = 'total') {
    // Use unified field value retrieval with preference for current DOM values
    return getUnifiedFieldValue(fieldId, mode, true);
}

function isFieldDisabledByDataAvailability(normalizedFieldId) {
    // Check for data availability checkboxes that would disable this field
    const dataNotAvailableCheckbox = document.querySelector(`input[name="indicator_${normalizedFieldId}_data_not_available"]`);
    const notApplicableCheckbox = document.querySelector(`input[name="indicator_${normalizedFieldId}_not_applicable"]`);

    // If either checkbox is checked, the field is considered disabled/empty
    const isDataNotAvailable = dataNotAvailableCheckbox && dataNotAvailableCheckbox.checked;
    const isNotApplicable = notApplicableCheckbox && notApplicableCheckbox.checked;

    if (isDataNotAvailable || isNotApplicable) {
        return true;
    }

    return false;
}

function getInputValue(element) {
    if (!element) return null;

    switch (element.type) {
        case 'checkbox':
            // For yes/no pairs (or any checkbox group sharing the same name) return the checked value in the group.
            if (element.name) {
                const safeName = (window.CSS && CSS.escape) ? CSS.escape(element.name) : element.name.replace(/"/g, '\"');
                const group = document.querySelectorAll(`input[name="${safeName}"]`);
                for (const cb of group) {
                    if (cb.checked) {
                        return cb.value;
                    }
                }
                // Explicitly return null when no checkbox in the group is selected
                return null;
            }
            return element.checked ? element.value : null;
        case 'radio':
            // For radio buttons, find the checked one in the group
            const checkedRadio = document.querySelector(`input[name="${element.name}"]:checked`);
            return checkedRadio ? checkedRadio.value : null;
        case 'select-one':
        case 'select-multiple':
            return element.value || null;
        case 'number':
            // Handle number inputs specially to distinguish between 0 and empty
            if (element.value === '') return null;
            const numValue = parseFloat(element.value);
            return isNaN(numValue) ? null : numValue;
        default:
            // For text, textarea, etc.
            return element.value || null;
    }
}

export function updateFieldVisibility(field) {
    // Use unified field visibility handling
    import('./form-item-utils.js').then(module => {
        module.updateFieldVisibility(field);
    });
}

function evaluateCondition(condition, triggerField) {
    if (!condition) return true;

    // Handle different condition structures
    if (condition.conditions && Array.isArray(condition.conditions)) {
        // New structure: { logic_type: "AND", conditions: [...] }
        const logicType = (condition.logic_type || 'AND').toUpperCase();

        if (logicType === 'AND') {
            return condition.conditions.every(c => evaluateSingleCondition(c));
        } else if (logicType === 'OR') {
            return condition.conditions.some(c => evaluateSingleCondition(c));
        }
    }

    // Handle AND conditions
    if (condition.AND) {
        return condition.AND.every(subCondition => evaluateCondition(subCondition, triggerField));
    }

    // Handle OR conditions
    if (condition.OR) {
        return condition.OR.some(subCondition => evaluateCondition(subCondition, triggerField));
    }

    // Handle NOT conditions
    if (condition.NOT) {
        return !evaluateCondition(condition.NOT, triggerField);
    }

    return evaluateSingleCondition(condition);
}

function evaluateSingleCondition(condition) {
    const { operator, field_id, item_id, field, value } = condition;
    const targetFieldId = field_id || item_id || field;

    if (!targetFieldId) {
        return true;
    }

    const fieldValue = getFieldValue(targetFieldId);

    // Handle empty/null values consistently
    const isFieldEmpty = !fieldValue || String(fieldValue).trim() === '' || String(fieldValue) === 'null' || String(fieldValue) === 'undefined';
    const isConditionValueEmpty = !value || String(value).trim() === '' || String(value) === 'null' || String(value) === 'undefined';

    switch (operator) {
        case 'EQUALS':
        case 'equals':
            if (isFieldEmpty && isConditionValueEmpty) return true;
            if (isFieldEmpty || isConditionValueEmpty) return false;
            return String(fieldValue) === String(value);
        case 'NOT_EQUALS':
        case 'not_equals':
            if (isFieldEmpty && isConditionValueEmpty) return false;
            if (isFieldEmpty || isConditionValueEmpty) return true;
            return String(fieldValue) !== String(value);
        case 'GREATER_THAN':
        case 'greater_than':
            if (isFieldEmpty) return false;
            return parseFloat(fieldValue) > parseFloat(value);
        case 'LESS_THAN':
        case 'less_than':
            if (isFieldEmpty) return false;
            return parseFloat(fieldValue) < parseFloat(value);
        case 'CONTAINS':
        case 'contains':
            if (isFieldEmpty) return false;
            return String(fieldValue).includes(String(value));
        case 'NOT_CONTAINS':
        case 'not_contains':
            if (isFieldEmpty) return true;
            return !String(fieldValue).includes(String(value));
        case 'IS_EMPTY':
        case 'is_empty':
            return isFieldEmpty;
        case 'IS_NOT_EMPTY':
        case 'is_not_empty':
            return !isFieldEmpty;
        default:
            return true;
    }
}

// Make toggleDisaggregationInputs available globally since it's used in inline event handlers
window.toggleDisaggregationInputs = function(fieldId, selectedMode, itemType, triggerElement = null) {

    debugLog('field-management', `toggleDisaggregationInputs called for field ${fieldId}, mode=${selectedMode}, type=${itemType}`);

    let searchScope = document;
    let scopeInfo = "global";

    // If we have a trigger element (like a radio button), check if it's in a repeat entry
    if (triggerElement) {
        const repeatEntry = triggerElement.closest('.repeat-entry');
        if (repeatEntry) {
            searchScope = repeatEntry;
            scopeInfo = `repeat entry ${repeatEntry.id}`;
        }
    }

    const containers = searchScope.querySelectorAll(`.disaggregation-inputs[data-parent-id="${fieldId}"][data-item-type="${itemType}"]`);

    // Hide all containers in this scope
    containers.forEach((container, index) => {
        const mode = container.getAttribute('data-mode');
        container.style.display = 'none';
    });

    // Show selected container in this scope
    const selectedContainer = searchScope.querySelector(`.disaggregation-inputs[data-parent-id="${fieldId}"][data-item-type="${itemType}"][data-mode="${selectedMode}"]`);
    if (selectedContainer) {
        selectedContainer.style.display = 'block';

        // Clear all disaggregation input values when switching modes to prevent value replication
        if (selectedMode !== 'total') {
            const disaggregationInputs = selectedContainer.querySelectorAll('input[data-numeric="true"]:not([readonly])');
            disaggregationInputs.forEach(input => {
                const oldValue = input.value;
                input.value = '';
                // Trigger change event to notify other systems
                input.dispatchEvent(new Event('change', { bubbles: true }));
            });
        }
    }

    // Show/hide calculated total section based on selected mode and indirect reach
    const calculatedTotalSection = searchScope.querySelector(`.calculated-total-section[data-parent-id="${fieldId}"]`);
    debugLog('field-management', `Looking for calculated total section with selector: .calculated-total-section[data-parent-id="${fieldId}"] in scope: ${scopeInfo}`);
    debugLog('field-management', `Found calculated total section:`, calculatedTotalSection);

    if (calculatedTotalSection) {
        // Since .calculated-total-section only exists for fields WITHOUT indirect reach
        // (fields with indirect reach show calculated total adjacent to indirect input),
        // we can simplify the logic: hide for Total Only, show for disaggregation modes

        debugLog('field-management', `Field ${fieldId} - selectedMode=${selectedMode} (calculated-total-section exists, so no indirect reach)`);

        if (selectedMode === 'total') {
            // Hide calculated total for Total Only mode (no indirect reach by definition)
            debugLog('field-management', `Hiding calculated total for field ${fieldId} (Total Only mode)`);
            calculatedTotalSection.style.display = 'none';
        } else {
            // Show calculated total for disaggregation modes (sex, age, sex_age)
            debugLog('field-management', `Showing calculated total for field ${fieldId} (disaggregation mode)`);
            calculatedTotalSection.style.display = 'block';
        }
    }

    // Trigger recalculation of totals for the newly visible container
    // Pass the trigger element context so the calculator can find the right repeat entry
    if (window.recalculateTotalsOnModeChange) {
        debugLog('field-management', `Triggering recalculation for field ${fieldId}, mode ${selectedMode}, type ${itemType}`);
        window.recalculateTotalsOnModeChange(fieldId, selectedMode, itemType);

        // For repeat sections, we need to ensure the calculator reinitializes to find the correct fields
        if (triggerElement && triggerElement.closest('.repeat-entry') && window.reinitializeDisaggregationCalculator) {
            debugLog('field-management', `Reinitializing disaggregation calculator for repeat section context`);
            // Small delay to ensure DOM updates are complete
            setTimeout(() => {
                window.reinitializeDisaggregationCalculator();
            }, 50);
        }
    }

};

function setupFieldListeners() {

    // Get all form inputs
    const allInputs = document.querySelectorAll('input, select, textarea');

    allInputs.forEach(input => {
        // Skip non-form inputs
        if (!input.name || input.type === 'hidden') return;

        const eventType = input.type === 'checkbox' || input.type === 'radio' ? 'change' : 'input';

        input.addEventListener(eventType, function() {
            // Debounce the relevance checking
            clearTimeout(window.relevanceCheckTimeout);
            window.relevanceCheckTimeout = setTimeout(() => {
                // Prefer the debounced relevance API from conditions.js to avoid
                // re-entrancy loops and to respect plugin readiness gating.
                if (window.requestRelevanceRecheck) {
                    window.requestRelevanceRecheck('field-management:input');
                } else if (window.checkAllRelevanceConditions) {
                    window.checkAllRelevanceConditions({ reason: 'field-management:input' });
                }
            }, 250);
        });
    });
}

function processNumericValue(value) {
    if (value === null || value === undefined || value === 'None' || value === '') {
        return '';
    }
    return value;
}

function setFieldValue(fieldId, value, mode = 'total') {
    const regularInput = document.getElementById(`field-${fieldId}`);
    if (!regularInput) {
        console.warn(`No input found for field ${fieldId}`);
        return;
    }

    if (regularInput.type === 'number') {
        regularInput.value = processNumericValue(value);
        return;
    }

    // Handle disaggregated data
    if (mode !== 'total' && typeof value === 'object') {
        Object.entries(value).forEach(([key, val]) => {
            const input = document.querySelector(`[name="indicator_${fieldId}_${mode}_${key}"]`);
            if (input) {
                input.value = processNumericValue(val);
            }
        });
        return;
    }

    regularInput.value = value || '';
}
