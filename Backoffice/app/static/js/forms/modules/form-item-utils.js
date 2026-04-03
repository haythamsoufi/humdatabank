/**
 * Form Item Utilities Module
 *
 * Provides reusable utilities for form item handling across all contexts:
 * - Main sections
 * - Sub-sections
 * - Repeat entries
 * - Dynamic indicators
 *
 * This eliminates code duplication and ensures consistent behavior.
 */

import { debugLog, debugWarn, debugError } from './debug.js';

/**
 * Unified field value retrieval that works across all contexts
 * @param {string} fieldId - The field ID to get value for
 * @param {string} mode - Disaggregation mode ('total', 'sex', 'age', 'sex_age')
 * @param {boolean} preferCurrent - Whether to prefer current DOM values over existing data
 * @returns {*} The field value or null if not found/empty
 */
export function getUnifiedFieldValue(fieldId, mode = 'total', preferCurrent = false) {
    if (fieldId === null || fieldId === undefined) {
        return null;
    }

    // Built-in metadata tokens (used in relevance/validation rules)
    // Supported formats:
    // - "entity_name" (token key)
    // - "metadata:entity_name"
    // - "metadata_entity_name"
    const rawId = String(fieldId);
    const metadataContext = (window && window.metadataContext && typeof window.metadataContext === 'object')
        ? window.metadataContext
        : null;

    if (metadataContext) {
        let metaKey = rawId;
        if (metaKey.startsWith('metadata:')) {
            metaKey = metaKey.slice('metadata:'.length);
        } else if (metaKey.startsWith('metadata_')) {
            metaKey = metaKey.slice('metadata_'.length);
        }

        if (Object.prototype.hasOwnProperty.call(metadataContext, metaKey)) {
            const v = metadataContext[metaKey];
            return (v === undefined || v === null) ? null : v;
        }
    }

    const normalizedFieldId = rawId.replace(/^indicator_/, '');

    // Check if field is disabled by data availability
    if (isFieldDisabledByDataAvailability(normalizedFieldId)) {
        return null;
    }

    if (preferCurrent) {
        return getCurrentDOMValue(fieldId, mode) || getExistingDataValue(fieldId, mode);
    } else {
        return getExistingDataValue(fieldId, mode) || getCurrentDOMValue(fieldId, mode);
    }
}

/**
 * Get current value from DOM elements
 * @param {string} fieldId - The field ID
 * @param {string} mode - Disaggregation mode
 * @returns {*} Current DOM value or null
 */
function getCurrentDOMValue(fieldId, mode) {
    const normalizedFieldId = fieldId.toString().replace(/^indicator_/, '');

    // Try multiple field patterns for different contexts
    const fieldPatterns = [
        // Standard patterns
        `field-${fieldId}`,
        `field-${normalizedFieldId}`,
        // Repeat patterns
        `repeat_*_field_*_*`,
        // Dynamic patterns
        `dynamic_${fieldId}_*`,
        `dynamic_${normalizedFieldId}_*`
    ];

    // Try yes/no checkboxes first (most common)
    for (const pattern of fieldPatterns) {
        const yesNoValue = getYesNoCheckboxValue(pattern, fieldId, normalizedFieldId);
        if (yesNoValue !== null) {
            return yesNoValue;
        }
    }

    // Try regular inputs
    let input = findFieldInput(fieldId, normalizedFieldId);
    if (input) {
        return getInputValue(input);
    }

    // Try to get value from data attributes (for plugin fields)
    const dataAttributeValue = getDataAttributeValue(fieldId, normalizedFieldId);
    if (dataAttributeValue !== null) {
        return dataAttributeValue;
    }

    // Try disaggregation inputs for indicator fields
    const disaggregationValue = getDisaggregationValue(fieldId, normalizedFieldId, mode);
    if (disaggregationValue !== null) {
        return disaggregationValue;
    }

    return null;
}

/**
 * Get value from existing data store
 * @param {string} fieldId - The field ID
 * @param {string} mode - Disaggregation mode
 * @returns {*} Existing data value or null
 */
function getExistingDataValue(fieldId, mode) {
    const normalizedFieldId = fieldId.toString().replace(/^indicator_/, '');
    const dataKey = `field_value[${normalizedFieldId}]`;

    if (!window.existingData || !window.existingData[dataKey]) {
        return null;
    }

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

    // Handle complex indicator data structure
    if (typeof parsedValue === 'object' && parsedValue !== null) {
        if (parsedValue.mode && parsedValue.values) {
            if (parsedValue.mode === 'total' && parsedValue.values.total !== undefined) {
                return parsedValue.values.total;
            }
            return parsedValue.values[mode] || parsedValue.values.value;
        }
    }

    return parsedValue;
}

/**
 * Check if field is disabled by data availability checkboxes
 * @param {string} normalizedFieldId - The normalized field ID
 * @returns {boolean} True if field is disabled
 */
function isFieldDisabledByDataAvailability(normalizedFieldId) {
    // Prefer exact name matches (fast). Substring matches across the whole DOM can become
    // expensive on large forms with many dynamic indicators.
    const id = String(normalizedFieldId);

    const exactNames = [
        `indicator_${id}_data_not_available`,
        `indicator_${id}_not_applicable`,
        `field_${id}_data_not_available`,
        `field_${id}_not_applicable`
    ];

    for (const name of exactNames) {
        const group = document.getElementsByName(name);
        if (!group || !group.length) continue;
        for (const el of group) {
            if (el && el.type === 'checkbox' && el.checked) return true;
        }
    }

    // Fallback for repeat entries which include "_field_<id>_" segments.
    const fallbackSelectors = [
        `input[type="checkbox"]:checked[name*="_field_${id}_"][name$="_data_not_available"]`,
        `input[type="checkbox"]:checked[name*="_field_${id}_"][name$="_not_applicable"]`
    ];
    for (const sel of fallbackSelectors) {
        if (document.querySelector(sel)) return true;
    }

    return false;
}

/**
 * Get yes/no checkbox value for a field
 * @param {string} pattern - Search pattern
 * @param {string} fieldId - Original field ID
 * @param {string} normalizedFieldId - Normalized field ID
 * @returns {string|null} 'yes', 'no', or null
 */
function getYesNoCheckboxValue(pattern, fieldId, normalizedFieldId) {
    // NOTE: This function used to scan *all* checkboxes in the document for each lookup.
    // With many dynamic indicators (each adding many inputs), that becomes extremely slow.
    // Prefer exact name lookups (fast) and only fall back to targeted substring searches.

    // The "pattern" arg is kept for backward compatibility with older call sites.
    void pattern;

    const candidateNames = [
        `indicator_${fieldId}_standard_value`,
        `indicator_${normalizedFieldId}_standard_value`,
        `field_value[${fieldId}]`,
        `field_value[${normalizedFieldId}]`
    ];

    for (const name of candidateNames) {
        const group = document.getElementsByName(name);
        if (group && group.length) {
            for (const el of group) {
                if (!el || el.type !== 'checkbox') continue;
                if (el.value !== 'yes' && el.value !== 'no') continue;
                if (el.checked) return el.value;
            }
            // Group exists but nothing checked → treat as empty.
            return null;
        }
    }

    // Fallback for repeat fields with names like "..._field_<id>_..."
    const id = String(fieldId);
    const nid = String(normalizedFieldId);
    const fallbackSelectors = [
        `input[type="checkbox"][value="yes"]:checked[name*="_field_${id}_"]`,
        `input[type="checkbox"][value="no"]:checked[name*="_field_${id}_"]`,
        `input[type="checkbox"][value="yes"]:checked[name*="_field_${nid}_"]`,
        `input[type="checkbox"][value="no"]:checked[name*="_field_${nid}_"]`
    ];

    for (const sel of fallbackSelectors) {
        const el = document.querySelector(sel);
        if (el) return el.value;
    }

    return null;
}

/**
 * Find input element for a field across all contexts
 * @param {string} fieldId - Original field ID
 * @param {string} normalizedFieldId - Normalized field ID
 * @returns {Element|null} Input element or null
 */
function findFieldInput(fieldId, normalizedFieldId) {
    // Try direct ID lookup first
    let input = document.getElementById(`field-${fieldId}`) || document.getElementById(`field-${normalizedFieldId}`);

    if (!input) {
        // Try finding field container and get its input
        const fieldContainer = document.querySelector(`[data-item-id="${fieldId}"]`) ||
                              document.querySelector(`[data-item-id="${normalizedFieldId}"]`);
        if (fieldContainer) {
            input = fieldContainer.querySelector('input, select, textarea');
        }
    }

    return input;
}

/**
 * Get disaggregation value for indicator fields
 * @param {string} fieldId - Original field ID
 * @param {string} normalizedFieldId - Normalized field ID
 * @param {string} mode - Disaggregation mode
 * @returns {*} Disaggregation value or null
 */
function getDisaggregationValue(fieldId, normalizedFieldId, mode) {
    const inputPatterns = [
        `input[name="indicator_${fieldId}_total_value"]`,
        `input[name="indicator_${fieldId}_standard_value"]`,
        `input[name="indicator_${normalizedFieldId}_total_value"]`,
        `input[name="indicator_${normalizedFieldId}_standard_value"]`,
        `input[name="dynamic_${fieldId}_total_value"]`,
        `input[name="dynamic_${fieldId}_standard_value"]`,
        `input[name="dynamic_${normalizedFieldId}_total_value"]`,
        `input[name="dynamic_${normalizedFieldId}_standard_value"]`,
        // Repeat patterns
        `input[name*="repeat_"][name*="_field_"][name*="_total_value"]`,
        `input[name*="repeat_"][name*="_field_"][name*="_standard_value"]`
    ];

    for (const pattern of inputPatterns) {
        const input = document.querySelector(pattern);
        if (input && (input.name.includes(fieldId) || input.name.includes(normalizedFieldId))) {
            const value = getInputValue(input);
            if (value !== null && value !== '' && value !== undefined) {
                return value;
            }
        }
    }

    return null;
}

/**
 * Get value from data attributes (for plugin fields)
 * @param {string} fieldId - The field ID
 * @param {string} normalizedFieldId - The normalized field ID
 * @returns {*} Data attribute value or null
 */
function getDataAttributeValue(fieldId, normalizedFieldId) {
    // Plugin measure: plugin_<numericId>_<measureId> -> find field by base id, read data-<measureId> (underscores to dashes)
    let actualFieldId = fieldId;
    let measureId = null;
    if (fieldId.includes('_') && fieldId.startsWith('plugin_')) {
        const parts = fieldId.split('_');
        if (parts.length >= 3) {
            actualFieldId = parts[1];
            measureId = parts.slice(2).join('_');
        }
    }

    const fieldSelectors = [
        `[data-field-id="${actualFieldId}"]`,
        `[data-field-id="${fieldId}"]`,
        `[data-field-id="${normalizedFieldId}"]`,
        `[data-item-id="${fieldId}"]`,
        `[data-item-id="${normalizedFieldId}"]`,
        `#field-${fieldId}`,
        `#field-${normalizedFieldId}`
    ];

    for (const selector of fieldSelectors) {
        const fieldElement = document.querySelector(selector);
        if (!fieldElement) continue;

        if (measureId) {
            const attr = 'data-' + measureId.replace(/_/g, '-');
            const value = fieldElement.getAttribute(attr);
            if (value !== null && value !== undefined) {
                const numValue = parseFloat(value);
                return !isNaN(numValue) && value.trim() !== '' ? numValue : value;
            }
            continue;
        }

        const dataAttributes = ['data-operations-count', 'data-count', 'data-value', 'data-total', 'data-amount'];
        for (const attr of dataAttributes) {
            const value = fieldElement.getAttribute(attr);
            if (value !== null && value !== undefined && value !== '') {
                const numValue = parseFloat(value);
                return !isNaN(numValue) ? numValue : value;
            }
        }
        if (fieldElement.dataset.operationsCount) {
            const value = fieldElement.dataset.operationsCount;
            const numValue = parseFloat(value);
            return !isNaN(numValue) ? numValue : value;
        }
    }

    if (measureId) {
        const attr = 'data-' + measureId.replace(/_/g, '-');
        const el = document.querySelector(`[data-field-id="${actualFieldId}"]`);
        if (el) {
            const value = el.getAttribute(attr);
            if (value !== null && value !== undefined) {
                const numValue = parseFloat(value);
                return !isNaN(numValue) && value.trim() !== '' ? numValue : value;
            }
        }
    }

    return null;
}

/**
 * Get value from input element with proper type handling
 * @param {Element} element - Input element
 * @returns {*} Input value with proper type conversion
 */
export function getInputValue(element) {
    if (!element) return null;

    switch (element.type) {
        case 'checkbox':
            // For yes/no pairs, return the checked value in the group
            if (element.name) {
                const group = document.querySelectorAll(`input[name="${element.name}"]`);
                for (const cb of group) {
                    if (cb.checked) {
                        return cb.value;
                    }
                }
                return null;
            }
            return element.checked ? element.value : null;

        case 'radio':
            const checkedRadio = document.querySelector(`input[name="${element.name}"]:checked`);
            return checkedRadio ? checkedRadio.value : null;

        case 'select-one':
        case 'select-multiple':
            return element.value || null;

        case 'number':
            if (element.value === '') return null;
            const numValue = parseFloat(element.value);
            return isNaN(numValue) ? null : numValue;

        default:
            return element.value || null;
    }
}

/**
 * Set value for a field across all contexts
 * @param {string} fieldId - Field ID
 * @param {*} value - Value to set
 * @param {string} mode - Disaggregation mode
 * @param {Element} container - Optional container to search within
 */
export function setUnifiedFieldValue(fieldId, value, mode = 'total', container = document) {
    const normalizedFieldId = fieldId.toString().replace(/^indicator_/, '');

    // Find the field input
    let input = container.querySelector(`#field-${fieldId}`) ||
                container.querySelector(`#field-${normalizedFieldId}`);

    if (!input) {
        // Try finding by data attribute
        const fieldContainer = container.querySelector(`[data-item-id="${fieldId}"]`) ||
                              container.querySelector(`[data-item-id="${normalizedFieldId}"]`);
        if (fieldContainer) {
            input = fieldContainer.querySelector('input, select, textarea');
        }
    }

    if (!input) {
        debugWarn('form-item-utils', `No input found for field ${fieldId}`);
        return;
    }

    // Set value based on input type
    switch (input.type) {
        case 'checkbox':
            if (value === 'yes' || value === 'no') {
                // Yes/no checkbox
                const group = container.querySelectorAll(`input[name="${input.name}"]`);
                group.forEach(cb => {
                    cb.checked = (cb.value === value);
                });
            } else if (Array.isArray(value)) {
                // Multi-choice checkboxes
                const group = container.querySelectorAll(`input[name="${input.name}"]`);
                group.forEach(cb => {
                    cb.checked = value.includes(cb.value);
                });
            } else {
                input.checked = !!value;
            }
            break;

        case 'radio':
            if (value) {
                const targetRadio = container.querySelector(`input[name="${input.name}"][value="${value}"]`);
                if (targetRadio) {
                    targetRadio.checked = true;
                }
            }
            break;

        default:
            input.value = value || '';
    }

    // Trigger change event
    input.dispatchEvent(new Event('change', { bubbles: true }));
}

/**
 * Update field visibility based on relevance conditions
 * @param {Element} field - Field element
 * @param {boolean} isVisible - Whether field should be visible
 */
export function updateFieldVisibility(field, isVisible = null) {
    if (!field) return;

    if (isVisible === null) {
        // Evaluate conditions if visibility not explicitly provided
        const conditions = field.getAttribute('data-relevance-condition');
        if (!conditions) {
            isVisible = true;
        } else {
            try {
                const parsedConditions = JSON.parse(conditions);
                isVisible = evaluateRelevanceConditions(parsedConditions);
            } catch (error) {
                debugWarn('form-item-utils', 'Error parsing relevance conditions:', error);
                isVisible = true; // Default to visible on error
            }
        }
    }

    // Apply visibility
    if (isVisible) {
        field.style.display = '';
        field.classList.remove('hidden');

        // Also show wrapper if it exists (for layout system)
        const wrapper = field.closest('[style*="width:"]');
        if (wrapper) {
            wrapper.classList.remove('hidden');
        }
    } else {
        field.style.display = 'none';
        field.classList.add('hidden');

        // Also hide wrapper if it exists
        const wrapper = field.closest('[style*="width:"]');
        if (wrapper) {
            wrapper.classList.add('hidden');
        }
    }
}

/**
 * Evaluate relevance conditions
 * @param {Object} conditions - Parsed relevance conditions
 * @returns {boolean} Whether field should be visible
 */
function evaluateRelevanceConditions(conditions) {
    if (!conditions) return true;

    // Handle different condition structures
    if (conditions.conditions && Array.isArray(conditions.conditions)) {
        const logicType = (conditions.logic_type || 'AND').toUpperCase();

        if (logicType === 'AND') {
            return conditions.conditions.every(c => evaluateSingleCondition(c));
        } else if (logicType === 'OR') {
            return conditions.conditions.some(c => evaluateSingleCondition(c));
        }
    }

    // Handle legacy AND/OR conditions
    if (conditions.AND) {
        return conditions.AND.every(subCondition => evaluateRelevanceConditions(subCondition));
    }

    if (conditions.OR) {
        return conditions.OR.some(subCondition => evaluateRelevanceConditions(subCondition));
    }

    if (conditions.NOT) {
        return !evaluateRelevanceConditions(conditions.NOT);
    }

    return evaluateSingleCondition(conditions);
}

/**
 * Evaluate a single condition
 * @param {Object} condition - Single condition object
 * @returns {boolean} Condition result
 */
function evaluateSingleCondition(condition) {
    const { operator, field_id, item_id, field, value } = condition;
    const targetFieldId = field_id || item_id || field;

    if (!targetFieldId) {
        return true;
    }

    const fieldValue = getUnifiedFieldValue(targetFieldId);

    // Handle empty/null values consistently
    const isFieldEmpty = !fieldValue || String(fieldValue).trim() === '' ||
                        String(fieldValue) === 'null' || String(fieldValue) === 'undefined';
    const isConditionValueEmpty = !value || String(value).trim() === '' ||
                                 String(value) === 'null' || String(value) === 'undefined';

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

/**
 * Initialize field listeners for a container
 * @param {Element} container - Container to initialize listeners for
 */
export function initializeFieldListeners(container = document) {
    const inputs = container.querySelectorAll('input, select, textarea');

    inputs.forEach(input => {
        if (!input.name || input.type === 'hidden') return;

        const eventType = input.type === 'checkbox' || input.type === 'radio' ? 'change' : 'input';

        // Remove existing listeners to avoid duplicates
        input.removeEventListener(eventType, handleFieldChange);
        input.addEventListener(eventType, handleFieldChange);
    });
}

/**
 * Handle field change events
 * @param {Event} event - Change event
 */
function handleFieldChange(event) {
    // Debounce relevance checking
    clearTimeout(window.unifiedRelevanceCheckTimeout);
    window.unifiedRelevanceCheckTimeout = setTimeout(() => {
        // Prefer the centralized conditions.js engine when available (it handles
        // wrapper visibility, value clearing rules, and plugin readiness gating).
        if (window.requestRelevanceRecheck) {
            window.requestRelevanceRecheck('form-item-utils:input');
            return;
        }
        if (window.checkAllRelevanceConditions) {
            window.checkAllRelevanceConditions({ reason: 'form-item-utils:input' });
            return;
        }
        checkAllRelevanceConditions();
    }, 250);
}

/**
 * Check all relevance conditions in the form
 */
function checkAllRelevanceConditions() {
    // If the centralized conditions.js engine is present, delegate to it.
    // This avoids conflicting visibility rules and ensures plugin readiness is respected.
    if (window.requestRelevanceRecheck) {
        window.requestRelevanceRecheck('form-item-utils:checkAll');
        return;
    }
    if (window.checkAllRelevanceConditions) {
        window.checkAllRelevanceConditions({ reason: 'form-item-utils:checkAll' });
        return;
    }

    const fieldsWithConditions = document.querySelectorAll('[data-relevance-condition]');
    fieldsWithConditions.forEach(field => updateFieldVisibility(field));
}

/**
 * Safely set value for numeric input, handling JSON data structures
 * @param {HTMLInputElement} input - The input element
 * @param {*} value - The value to set
 */
function safeSetNumericInputValue(input, value) {
    if (!(input.type === 'number' || (input.dataset && input.dataset.numeric === 'true'))) {
        input.value = value;
        return;
    }

    // For numeric inputs, handle JSON values gracefully
    let processedValue = value;

    // Handle double-encoded JSON (with escaped quotes)
    if (typeof processedValue === 'string' && processedValue.startsWith('\\"') && processedValue.endsWith('\\"')) {
        try {
            // Remove the outer quotes and unescape
            processedValue = JSON.parse(processedValue);
            debugLog('form-item-utils', `Unescaped double-encoded value: ${processedValue}`);
        } catch (e) {
            debugLog('form-item-utils', `Failed to unescape double-encoded value: ${processedValue}`);
        }
    }

    if (typeof processedValue === 'string' && (processedValue.includes('{') || processedValue.includes('['))) {
        try {
            const parsed = JSON.parse(processedValue);
            if (typeof parsed === 'object' && parsed !== null) {
                // Extract numeric value from disaggregated data
                if (parsed.values && typeof parsed.values === 'object') {
                    const extractedValue = parsed.values.total || parsed.values.direct ||
                                         parsed.values[Object.keys(parsed.values)[0]] || '';
                    // Force set both value property and attribute to ensure it sticks
                    input.value = extractedValue;
                    input.setAttribute('value', extractedValue);
                    debugLog('form-item-utils', `Parsed JSON value for input ${input.name || input.id}: ${extractedValue}`);
                    return;
                }
            }
        } catch (e) {
            // JSON parsing failed, set empty value
            debugLog('form-item-utils', `Failed to parse JSON for input ${input.name || input.id}, setting empty`);
        }
        // Force set both value property and attribute
        input.value = '';
        input.setAttribute('value', '');
    } else {
        // Regular value, set normally
        input.value = processedValue;
        input.setAttribute('value', processedValue);
    }
}

/**
 * Copy form element values between elements (for layout system)
 * @param {Element} sourceField - Source field element
 * @param {Element} targetField - Target field element
 */
export function copyFormElementValues(sourceField, targetField) {
    // Get all form inputs in both fields
    const sourceInputs = sourceField.querySelectorAll('input, select, textarea');
    const targetInputs = targetField.querySelectorAll('input, select, textarea');

    if (sourceInputs.length === 0 || targetInputs.length === 0) {
        return;
    }

    // First, clean up any cloned numeric inputs that may have JSON in their value attributes
    targetInputs.forEach(input => {
        if (input.type === 'number' && input.hasAttribute('value')) {
            const attrValue = input.getAttribute('value');
            if (attrValue && typeof attrValue === 'string' &&
                (attrValue.includes('{') || attrValue.includes('['))) {
                debugLog('form-item-utils', `Cleaning cloned input attribute: ${input.name || input.id} = ${attrValue}`);
                safeSetNumericInputValue(input, attrValue);
            }
        }
    });

    // Copy values for all corresponding inputs
    sourceInputs.forEach((sourceInput, index) => {
        const targetInput = targetInputs[index];
        if (!targetInput) return;

        // Use safe value setting for numeric inputs
        safeSetNumericInputValue(targetInput, sourceInput.value);

        // Copy specific attributes
        const attributesToCopy = ['type', 'name', 'id', 'class', 'required', 'min', 'max', 'step'];
        attributesToCopy.forEach(attr => {
            if (sourceInput.hasAttribute(attr)) {
                targetInput.setAttribute(attr, sourceInput.getAttribute(attr));
            }
        });

        // Handle checkboxes and radios
        if (sourceInput.type === 'checkbox' || sourceInput.type === 'radio') {
            targetInput.checked = sourceInput.checked;
        }

        // Handle selects
        if (sourceInput.tagName === 'SELECT') {
            targetInput.selectedIndex = sourceInput.selectedIndex;
        }
    });
}

// Export utilities for global access
export {
    evaluateRelevanceConditions,
    evaluateSingleCondition,
    checkAllRelevanceConditions
};

/**
 * Set up global numeric input value handling to support JSON values
 * This prevents "cannot be parsed, or is out of range" errors
 */
export function setupNumericInputJsonSupport() {
    // Override the value setter for HTMLInputElement to handle JSON gracefully
    const originalValueDescriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');

    if (originalValueDescriptor) {
        Object.defineProperty(HTMLInputElement.prototype, 'value', {
            get: originalValueDescriptor.get,
            set: function(value) {
                // For numeric inputs (including data-numeric text), parse JSON values if needed
                if ((this.type === 'number' || (this.dataset && this.dataset.numeric === 'true')) && typeof value === 'string' &&
                    (value.includes('{') || value.includes('['))) {

                    let processedValue = value;

                    // Handle double-encoded JSON (with escaped quotes)
                    if (processedValue.startsWith('\\"') && processedValue.endsWith('\\"')) {
                        try {
                            processedValue = JSON.parse(processedValue);
                            debugLog('form-item-utils', `Auto-unescaped double-encoded value: ${processedValue}`);
                        } catch (e) {
                            debugLog('form-item-utils', `Auto-failed to unescape: ${processedValue}`);
                        }
                    }

                    try {
                        const parsed = JSON.parse(processedValue);
                        if (typeof parsed === 'object' && parsed !== null && parsed.values) {
                            // Extract numeric value from disaggregated data
                            const extractedValue = parsed.values.total || parsed.values.direct ||
                                                 parsed.values[Object.keys(parsed.values)[0]] || '';
                            debugLog('form-item-utils', `Auto-parsed JSON for numeric input ${this.name || this.id}: ${extractedValue}`);
                            originalValueDescriptor.set.call(this, extractedValue);
                            return;
                        }
                    } catch (e) {
                        // JSON parsing failed, set empty value to avoid browser errors
                        debugLog('form-item-utils', `Auto-cleared invalid JSON for numeric input ${this.name || this.id}`);
                        originalValueDescriptor.set.call(this, '');
                        return;
                    }
                    // Invalid JSON structure, clear the value
                    originalValueDescriptor.set.call(this, '');
                    return;
                }

                // Use original setter for all other cases
                originalValueDescriptor.set.call(this, value);
            },
            configurable: true,
            enumerable: true
        });
    }

    debugLog('form-item-utils', '🔧 Set up global numeric input JSON support');
}

/**
 * Clean up any inputs that might have JSON strings as values
 * This prevents "cannot be parsed, or is out of range" errors for numeric inputs
 */
export function cleanupInputValues() {
    const numericInputs = document.querySelectorAll('input[data-numeric="true"], input[type="number"]');

    numericInputs.forEach(input => {
        // Check both the value property and value attribute
        const currentValue = input.value;
        const attrValue = input.getAttribute('value');

        // Clean up the current value if it's JSON
        if (currentValue && typeof currentValue === 'string' &&
            (currentValue.includes('{') || currentValue.includes('['))) {
            debugLog('form-item-utils', `Cleaning current value: ${input.name || input.id} = ${currentValue}`);
            safeSetNumericInputValue(input, currentValue);
        }

        // Also clean up the attribute value if it's different and contains JSON
        if (attrValue && typeof attrValue === 'string' &&
            (attrValue.includes('{') || attrValue.includes('[')) &&
            attrValue !== currentValue) {
            debugLog('form-item-utils', `Cleaning attribute value: ${input.name || input.id} = ${attrValue}`);
            safeSetNumericInputValue(input, attrValue);
        }
    });

    debugLog('form-item-utils', `🧹 Cleaned up ${numericInputs.length} numeric inputs`);
}

// Make key functions globally available for legacy compatibility
window.getUnifiedFieldValue = getUnifiedFieldValue;
window.setUnifiedFieldValue = setUnifiedFieldValue;
window.updateFieldVisibility = updateFieldVisibility;
window.checkAllRelevanceConditions = checkAllRelevanceConditions;
window.cleanupInputValues = cleanupInputValues;
window.setupNumericInputJsonSupport = setupNumericInputJsonSupport;
