/**
 * Optimized Disaggregation Calculator
 * Centralized calculation engine for form totals
 */

import { debugLog, debugError, debugWarn } from './debug.js';

// ============================================================================
// CORE CALCULATION ENGINE
// ============================================================================

class CalculationEngine {
    constructor() {
        this.inputsWithListeners = new Set();
        this.debounceTimers = new Map();
        this.DEBOUNCE_DELAY = 100;
        this.numberFormatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 20 });
    }

    /**
     * Initialize the calculation engine
     */
    init() {
        this.reset();
        this.setupListeners();
        this.calculateAll();
        this.setupRepeatEntryListener();
    }

    /**
     * Reset all state and timers
     */
    reset() {
        this.inputsWithListeners.clear();
        this.debounceTimers.forEach(timer => clearTimeout(timer));
        this.debounceTimers.clear();
    }

    /**
     * Set up event listeners for input changes
     */
    setupListeners() {
        // Main disaggregation inputs
        const containers = document.querySelectorAll('.disaggregation-inputs');
        containers.forEach(container => {
            const inputs = container.querySelectorAll('input[data-numeric="true"], input[type="number"]');
            inputs.forEach(input => this.addInputListener(input, container));
        });

        // Indirect reach inputs - both standard and repeat patterns
        const indirectInputs = document.querySelectorAll('input[name*="_indirect_reach"], input[name*="indirect_reach"]');
        debugLog('disaggregation-calculator', `Found ${indirectInputs.length} indirect reach inputs during setup`);
        indirectInputs.forEach((input, index) => {
            debugLog('disaggregation-calculator', `Setting up listener for indirect input ${index + 1}: ${input.name}`);
            this.addIndirectListener(input);
        });
    }

    /**
     * Add listener to individual input
     */
    addInputListener(input, container) {
        const inputId = this.getInputId(input, container);
        if (this.inputsWithListeners.has(inputId)) return;

        ['input', 'blur'].forEach(eventType => {
            input.addEventListener(eventType, () => {
                if (this.isContainerVisible(container)) {
                    // Pass the specific container context to ensure we work within the same repeat entry
                    this.debouncedCalculationWithContext(container, inputId, input);
                }
            });
        });

        this.inputsWithListeners.add(inputId);
    }

    /**
     * Add listener to indirect reach input
     */
    addIndirectListener(input) {
        const inputId = `indirect-${input.name || input.id}`;
        if (this.inputsWithListeners.has(inputId)) {
            debugLog('disaggregation-calculator', `Skipping duplicate listener for input: ${input.name}`);
            return;
        }

        debugLog('disaggregation-calculator', `Adding indirect reach listener to input: ${input.name || input.id}`);

        input.addEventListener('input', () => {
            debugLog('disaggregation-calculator', `🔄 INDIRECT REACH INPUT CHANGED: ${input.name}, value: ${input.value}`);

            // Handle both standard and repeat section naming patterns
            let match = input.name.match(/(indicator|dynamic)_(\d+)_indirect_reach/);

            // Try repeat section pattern if standard pattern doesn't match
            if (!match) {
                // First try the pattern for repeat section indirect reach fields
                const repeatMatch = input.name.match(/repeat_\d+_\d+_field_\d+_indirect_reach/);
                debugLog('disaggregation-calculator', `Trying repeat pattern match for ${input.name}: ${repeatMatch ? 'MATCHED' : 'NO MATCH'}`);

                if (repeatMatch) {
                    // For repeat sections, we need to find the parent ID from the container
                    const container = input.closest('.form-item-block');
                    const repeatEntry = input.closest('.repeat-entry');

                    debugLog('disaggregation-calculator', `Repeat pattern matched - container: ${container ? 'found' : 'not found'}, repeatEntry: ${repeatEntry ? repeatEntry.id : 'not found'}`);

                    if (container && repeatEntry) {
                        const parentId = container.getAttribute('data-item-id');
                        const itemType = container.getAttribute('data-item-type') === 'indicator' ? 'indicator' : 'dynamic';

                        debugLog('disaggregation-calculator', `Processing repeat indirect reach change: parentId=${parentId}, itemType=${itemType}, repeatEntry=${repeatEntry.id}`);

                        if (parentId) {
                            // Find the active container within the same repeat entry
                            const activeContainer = repeatEntry.querySelector(`.disaggregation-inputs[data-parent-id="${parentId}"][data-item-type="${itemType}"]`);
                            debugLog('disaggregation-calculator', `Looking for container with selector: .disaggregation-inputs[data-parent-id="${parentId}"][data-item-type="${itemType}"] - ${activeContainer ? 'FOUND' : 'NOT FOUND'}`);

                            if (activeContainer && this.isContainerVisible(activeContainer)) {
                                const disaggregationTotal = this.calculateContainerTotal(activeContainer);
                                debugLog('disaggregation-calculator', `Calculated disaggregation total: ${disaggregationTotal}`);
                                this.updateTotalFieldWithContext(parentId, itemType, disaggregationTotal, repeatEntry);
                            } else {
                                debugLog('disaggregation-calculator', `No active container found within repeat entry for ${itemType}-${parentId}`);
                            }
                        }
                    } else {
                        debugLog('disaggregation-calculator', `Missing container or repeat entry context for ${input.name}`);
                    }
                    return;
                }

                // Try alternative pattern in case the naming is different
                const altMatch = input.name.match(/.*indirect_reach/);
                if (altMatch) {
                    debugLog('disaggregation-calculator', `Alternative pattern matched for ${input.name} - checking for repeat context`);
                    const repeatEntry = input.closest('.repeat-entry');
                    if (repeatEntry) {
                        const container = input.closest('.form-item-block');
                        if (container) {
                            const parentId = container.getAttribute('data-item-id');
                            const itemType = container.getAttribute('data-item-type') === 'indicator' ? 'indicator' : 'dynamic';
                            if (parentId && itemType) {
                                debugLog('disaggregation-calculator', `Alternative pattern processing: parentId=${parentId}, itemType=${itemType}`);
                                const activeContainer = repeatEntry.querySelector(`.disaggregation-inputs[data-parent-id="${parentId}"][data-item-type="${itemType}"]`);
                                if (activeContainer && this.isContainerVisible(activeContainer)) {
                                    const disaggregationTotal = this.calculateContainerTotal(activeContainer);
                                    this.updateTotalFieldWithContext(parentId, itemType, disaggregationTotal, repeatEntry);
                                    return;
                                }
                            }
                        }
                    }
                }
            }

            // Handle standard pattern
            if (match) {
                const [, itemType, parentId] = match;
                debugLog('disaggregation-calculator', `Processing standard indirect reach change: parentId=${parentId}, itemType=${itemType}`);
                const activeContainer = this.findActiveContainer(parentId, itemType);
                if (activeContainer) {
                    const disaggregationTotal = this.calculateContainerTotal(activeContainer);
                    this.updateTotalField(parentId, itemType, disaggregationTotal);
                }
            }
        });

        this.inputsWithListeners.add(inputId);
    }

    /**
     * Set up listener for repeat entries
     */
    setupRepeatEntryListener() {
        document.addEventListener('repeatEntryAdded', () => {
            this.reinitialize();
        });
    }

    /**
     * Generate unique input identifier
     */
    getInputId(input, container) {
        const inputName = input.name || input.id || '';
        const parentId = container.getAttribute('data-parent-id') || '';
        const mode = container.getAttribute('data-mode') || '';
        return `${inputName}-${parentId}-${mode}`;
    }

    /**
     * Check if container is visible
     */
    isContainerVisible(container) {
        const style = window.getComputedStyle(container);
        return style.display !== 'none' && style.visibility !== 'hidden';
    }

    /**
     * Debounced calculation to prevent rapid successive calls
     */
    debouncedCalculation(container, inputId) {
        if (this.debounceTimers.has(inputId)) {
            clearTimeout(this.debounceTimers.get(inputId));
        }

        this.debounceTimers.set(inputId, setTimeout(() => {
            this.calculateContainer(container);
            this.debounceTimers.delete(inputId);
        }, this.DEBOUNCE_DELAY));
    }

    /**
     * Debounced calculation with repeat entry context
     */
    debouncedCalculationWithContext(container, inputId, triggerInput) {
        if (this.debounceTimers.has(inputId)) {
            clearTimeout(this.debounceTimers.get(inputId));
        }

        this.debounceTimers.set(inputId, setTimeout(() => {
            this.calculateContainerWithContext(container, triggerInput);
            this.debounceTimers.delete(inputId);
        }, this.DEBOUNCE_DELAY));
    }

    /**
     * Calculate total for all visible containers
     */
    calculateAll() {
        const containers = document.querySelectorAll('.disaggregation-inputs');
        containers.forEach(container => {
            if (this.isContainerVisible(container)) {
                this.calculateContainer(container);
            }
        });
    }

    /**
     * Calculate total for a specific container
     */
    calculateContainer(container) {
        if (!this.isContainerVisible(container)) return;

        const parentId = container.getAttribute('data-parent-id');
        const itemType = container.getAttribute('data-item-type');
        const mode = container.getAttribute('data-mode');

        const total = this.calculateContainerTotal(container);
        this.updateMainField(parentId, itemType, mode, total);
        this.updateTotalField(parentId, itemType, total);
    }

    /**
     * Calculate total for a specific container with repeat entry context
     */
    calculateContainerWithContext(container, triggerInput) {
        if (!this.isContainerVisible(container)) return;

        const parentId = container.getAttribute('data-parent-id');
        const itemType = container.getAttribute('data-item-type');
        const mode = container.getAttribute('data-mode');

        // Find the repeat entry context from the trigger input
        const repeatEntry = triggerInput.closest('.repeat-entry');
        debugLog('disaggregation-calculator', `calculateContainerWithContext: parentId=${parentId}, itemType=${itemType}, repeatEntry=${repeatEntry ? repeatEntry.id : 'none'}`);

        const total = this.calculateContainerTotal(container);
        this.updateMainFieldWithContext(parentId, itemType, mode, total, repeatEntry);
        this.updateTotalFieldWithContext(parentId, itemType, total, repeatEntry);
    }

    /**
     * Calculate the sum of inputs in a container
     */
    calculateContainerTotal(container) {
        const mode = container.getAttribute('data-mode');
        const parentId = container.getAttribute('data-parent-id');
        const itemType = container.getAttribute('data-item-type');

        let total = 0;
        const inputs = container.querySelectorAll('input[data-numeric="true"]:not([readonly]), input[type="number"]:not([readonly])');

        inputs.forEach(input => {
            // Skip main value fields in disaggregation modes
            if (mode !== 'total' && this.isMainValueField(input, parentId)) {
                return;
            }

            const raw = (typeof window.__numericUnformat === 'function') ? window.__numericUnformat(input.value) : input.value;
            const value = parseFloat(raw) || 0;
            total += value;
        });

        return total;
    }

    /**
     * Check if input is a main value field
     */
    isMainValueField(input, parentId) {
        const name = input.name || '';
        const id = input.id || '';

        return name.includes(`_${parentId}_total_value`) ||
               id.includes(`-total-${parentId}`) ||
               id === `field-${parentId}`;
    }

    /**
     * Update the main value field
     */
    updateMainField(parentId, itemType, mode, total) {
        const mainField = this.findMainField(parentId, itemType);
        if (!mainField) return;

        if (mode !== 'total') {
            // For disaggregation modes, update with calculated total
            const newValue = total > 0 ? total : '';
            if (mainField.value !== newValue.toString()) {
                mainField.value = newValue;
            }
        }
    }

    /**
     * Update the main value field with repeat entry context
     */
    updateMainFieldWithContext(parentId, itemType, mode, total, repeatEntry) {
        const mainField = this.findMainFieldWithContext(parentId, itemType, repeatEntry);
        if (!mainField) return;

        if (mode !== 'total') {
            // For disaggregation modes, update with calculated total
            const newValue = total > 0 ? total : '';
            if (mainField.value !== newValue.toString()) {
                mainField.value = newValue;
            }
        }
    }

    /**
     * Update the Total (Direct + Indirect) readonly field
     */
    updateTotalField(parentId, itemType, disaggregationTotal) {
        debugLog('disaggregation-calculator', `updateTotalField called for ${itemType}-${parentId}, disaggregationTotal=${disaggregationTotal}`);

        const totalField = this.findTotalField(parentId, itemType);
        if (!totalField) {
            debugLog('disaggregation-calculator', `No calculated total field found for ${itemType}-${parentId}`);
            return;
        }

        debugLog('disaggregation-calculator', `Found calculated total field with id="${totalField.id}"`);

        const indirectField = this.findIndirectField(parentId, itemType);
        // Always unformat before parsing to handle commas/spaces on mobile/locales
        const rawIndirect = indirectField ? (typeof window.__numericUnformat === 'function' ? window.__numericUnformat(indirectField.value) : indirectField.value) : '';
        const indirectValue = rawIndirect ? (parseFloat(rawIndirect) || 0) : 0;
        const finalTotal = disaggregationTotal + indirectValue;

        debugLog('disaggregation-calculator', `Setting calculated total field ${totalField.id} to value=${finalTotal} (disaggregation=${disaggregationTotal} + indirect=${indirectValue})`);
        if (finalTotal > 0) {
            // If the field is type=number (common on mobile), avoid writing formatted strings
            if (totalField.type === 'number') {
                totalField.value = finalTotal;
            } else if (totalField.dataset && totalField.dataset.numeric === 'true') {
                totalField.value = this.numberFormatter.format(finalTotal);
            } else {
                totalField.value = finalTotal;
            }
        } else {
            totalField.value = '';
        }
    }

    /**
     * Update the Total (Direct + Indirect) readonly field with repeat entry context
     */
    updateTotalFieldWithContext(parentId, itemType, disaggregationTotal, repeatEntry) {
        debugLog('disaggregation-calculator', `updateTotalFieldWithContext called for ${itemType}-${parentId}, disaggregationTotal=${disaggregationTotal}, repeatEntry=${repeatEntry ? repeatEntry.id : 'none'}`);

        const totalField = this.findTotalFieldWithContext(parentId, itemType, repeatEntry);
        if (!totalField) {
            debugLog('disaggregation-calculator', `No calculated total field found for ${itemType}-${parentId} in repeat entry ${repeatEntry ? repeatEntry.id : 'none'}`);
            return;
        }

        debugLog('disaggregation-calculator', `Found calculated total field with id="${totalField.id}"`);

        const indirectField = this.findIndirectFieldWithContext(parentId, itemType, repeatEntry);
        // Always unformat before parsing to handle commas/spaces on mobile/locales
        const rawIndirect = indirectField ? (typeof window.__numericUnformat === 'function' ? window.__numericUnformat(indirectField.value) : indirectField.value) : '';
        const indirectValue = rawIndirect ? (parseFloat(rawIndirect) || 0) : 0;
        const finalTotal = disaggregationTotal + indirectValue;

        // Debug logging for indirect reach value
        if (indirectField) {
            debugLog('disaggregation-calculator', `Indirect field found: id="${indirectField.id}", name="${indirectField.name}", value="${indirectField.value}", parsed=${indirectValue}`);
        } else {
            debugLog('disaggregation-calculator', `No indirect field found for ${itemType}-${parentId} in repeat entry ${repeatEntry ? repeatEntry.id : 'none'}`);
        }

        debugLog('disaggregation-calculator', `Setting calculated total field ${totalField.id} to value=${finalTotal} (disaggregation=${disaggregationTotal} + indirect=${indirectValue})`);
        if (finalTotal > 0) {
            // If the field is type=number (common on mobile), avoid writing formatted strings
            if (totalField.type === 'number') {
                totalField.value = finalTotal;
            } else if (totalField.dataset && totalField.dataset.numeric === 'true') {
                totalField.value = this.numberFormatter.format(finalTotal);
            } else {
                totalField.value = finalTotal;
            }
        } else {
            totalField.value = '';
        }
    }

    /**
     * Find main value field using multiple strategies
     */
    findMainField(parentId, itemType) {
        // Try repeat context first
        const activeContainer = this.findActiveContainer(parentId, itemType);
        if (activeContainer) {
            const repeatEntry = activeContainer.closest('.repeat-entry');
            if (repeatEntry) {
                debugLog('disaggregation-calculator', `Looking for main field in repeat entry: ${repeatEntry.id}`);

                // Look for total value fields with the repeat naming pattern
                let repeatField = repeatEntry.querySelector(`input[name*="repeat_"][name*="_total_value"]`);
                if (repeatField) {
                    debugLog('disaggregation-calculator', `Found repeat main field with total_value pattern: ${repeatField.name}`);
                    return repeatField;
                }

                // Look for standard value fields with the repeat naming pattern
                repeatField = repeatEntry.querySelector(`input[name*="repeat_"][name*="_standard_value"]`);
                if (repeatField) {
                    debugLog('disaggregation-calculator', `Found repeat main field with standard_value pattern: ${repeatField.name}`);
                    return repeatField;
                }

                // Legacy fallback pattern
                repeatField = repeatEntry.querySelector(`input[name*="repeat_"][name$="_4"]`);
                if (repeatField) {
                    debugLog('disaggregation-calculator', `Found repeat main field with legacy _4 pattern: ${repeatField.name}`);
                    return repeatField;
                }

                debugLog('disaggregation-calculator', `No repeat main field found for ${itemType}-${parentId}`);
            }
        }

        // Standard selectors for non-repeat sections
        let field = document.querySelector(`input[name="${itemType}_${parentId}_total_value"]`);
        if (field) {
            debugLog('disaggregation-calculator', `Found standard main field: ${field.name}`);
            return field;
        }

        debugLog('disaggregation-calculator', `No main field found for ${itemType}-${parentId}`);
        return null;
    }

    /**
     * Find Total (Direct + Indirect) readonly field
     */
    findTotalField(parentId, itemType) {
        debugLog('disaggregation-calculator', `findTotalField called for ${itemType}-${parentId}`);

        // Try repeat context first to find the specific field within the same repeat entry
        const activeContainer = this.findActiveContainer(parentId, itemType);
        if (activeContainer) {
            const repeatEntry = activeContainer.closest('.repeat-entry');
            if (repeatEntry) {
                debugLog('disaggregation-calculator', `Looking for calculated total field in repeat entry: ${repeatEntry.id}`);

                // Try to find calculated total field with the new repeat naming pattern
                const repeatTotalField = repeatEntry.querySelector(`input[id*="total-calculated-${parentId}"][readonly]`);
                if (repeatTotalField) {
                    debugLog('disaggregation-calculator', `Found repeat calculated total field with id="${repeatTotalField.id}"`);
                    return repeatTotalField;
                }

                // Fallback: find the form block and look for readonly number fields
                const formBlock = repeatEntry.querySelector(`.form-item-block[data-item-id="${parentId}"]`);
                if (formBlock) {
                    const readonlyFields = formBlock.querySelectorAll('input[readonly]');
                    debugLog('disaggregation-calculator', `Found ${readonlyFields.length} readonly fields in form block`);

                    // Look for fields with calculated total patterns in their IDs
                    for (let input of readonlyFields) {
                        if (input.id.includes('total-calculated') || input.id.includes('calculated')) {
                            debugLog('disaggregation-calculator', `Found calculated total field by pattern matching: ${input.id}`);
                            return input;
                        }
                    }

                    // Return first readonly field as fallback
                    if (readonlyFields.length > 0) {
                        debugLog('disaggregation-calculator', `Using first readonly field as fallback: ${readonlyFields[0].id}`);
                        return readonlyFields[0];
                    }
                }
            }
        }

        // Standard selectors for non-repeat sections
        let field = document.querySelector(`input[id="${itemType}-total-calculated-${parentId}"]`) ||
                   document.querySelector(`input[id="total-calculated-${parentId}"]`);

        if (field) {
            debugLog('disaggregation-calculator', `Found standard calculated total field with id="${field.id}"`);
            return field;
        } else {
            debugLog('disaggregation-calculator', `No calculated total field found for ${itemType}-${parentId}`);
        }

        return null;
    }

    /**
     * Find Total (Direct + Indirect) readonly field with repeat entry context
     */
    findTotalFieldWithContext(parentId, itemType, repeatEntry) {
        debugLog('disaggregation-calculator', `findTotalFieldWithContext called for ${itemType}-${parentId} in repeat entry: ${repeatEntry ? repeatEntry.id : 'none'}`);

        if (!repeatEntry) {
            // Fall back to standard method if no repeat context
            return this.findTotalField(parentId, itemType);
        }

        // Search only within the specific repeat entry
        debugLog('disaggregation-calculator', `Looking for calculated total field in repeat entry: ${repeatEntry.id}`);

        // Try to find calculated total field with the new repeat naming pattern
        const repeatTotalField = repeatEntry.querySelector(`input[id*="total-calculated-${parentId}"][readonly]`);
        if (repeatTotalField) {
            debugLog('disaggregation-calculator', `Found repeat calculated total field with id="${repeatTotalField.id}"`);
            return repeatTotalField;
        }

        // Fallback: find the form block and look for readonly number fields within this repeat entry
                const formBlock = repeatEntry.querySelector(`.form-item-block[data-item-id="${parentId}"]`);
                if (formBlock) {
                    const readonlyFields = formBlock.querySelectorAll('input[readonly]');
            debugLog('disaggregation-calculator', `Found ${readonlyFields.length} readonly fields in form block within repeat entry`);

            // Look for fields with calculated total patterns in their IDs
                    for (let input of readonlyFields) {
                if (input.id.includes('total-calculated') || input.id.includes('calculated')) {
                    debugLog('disaggregation-calculator', `Found calculated total field by pattern matching: ${input.id}`);
                    return input;
                }
            }

            // Return first readonly field as fallback
            if (readonlyFields.length > 0) {
                debugLog('disaggregation-calculator', `Using first readonly field as fallback: ${readonlyFields[0].id}`);
                return readonlyFields[0];
            }
        }

        debugLog('disaggregation-calculator', `No calculated total field found for ${itemType}-${parentId} in repeat entry ${repeatEntry.id}`);
        return null;
    }

    /**
     * Find indirect reach field
     */
    findIndirectField(parentId, itemType) {
        // Try repeat context first
        const activeContainer = this.findActiveContainer(parentId, itemType);
        if (activeContainer) {
            const repeatEntry = activeContainer.closest('.repeat-entry');
            if (repeatEntry) {
                debugLog('disaggregation-calculator', `Looking for indirect reach field in repeat entry: ${repeatEntry.id}`);

                // Look for indirect reach fields within this specific repeat entry
                const indirectFields = repeatEntry.querySelectorAll('input[name*="_indirect_reach"]:not([readonly])');
                if (indirectFields.length > 0) {
                    debugLog('disaggregation-calculator', `Found indirect reach field in repeat entry: ${indirectFields[0].name}`);
                    return indirectFields[0];
                }
            }
        }

        // Standard selector for non-repeat sections
        let field = document.querySelector(`input[name="${itemType}_${parentId}_indirect_reach"]:not([readonly])`);
        if (field) {
            debugLog('disaggregation-calculator', `Found standard indirect reach field: ${field.name}`);
            return field;
        }

        debugLog('disaggregation-calculator', `No indirect reach field found for ${itemType}-${parentId}`);
        return null;
    }

    /**
     * Find indirect reach field with repeat entry context
     */
    findIndirectFieldWithContext(parentId, itemType, repeatEntry) {
        debugLog('disaggregation-calculator', `findIndirectFieldWithContext called for ${itemType}-${parentId} in repeat entry: ${repeatEntry ? repeatEntry.id : 'none'}`);

        if (!repeatEntry) {
            // Fall back to standard method if no repeat context
            return this.findIndirectField(parentId, itemType);
        }

        // Search only within the specific repeat entry
        debugLog('disaggregation-calculator', `Looking for indirect reach field in repeat entry: ${repeatEntry.id}`);

        // Debug: Let's see what inputs are actually in this repeat entry
        const allInputs = repeatEntry.querySelectorAll('input');
        debugLog('disaggregation-calculator', `🔍 ALL inputs in ${repeatEntry.id}:`, allInputs.length);

        const indirectCandidates = Array.from(allInputs).filter(input =>
            input.name && (input.name.includes('indirect') || input.name.includes('reach'))
        );
        debugLog('disaggregation-calculator', `🎯 Indirect/reach candidates in ${repeatEntry.id}:`, indirectCandidates.length);

        if (indirectCandidates.length > 0) {
            indirectCandidates.forEach((inp, idx) => {
                debugLog('disaggregation-calculator', `  → ${idx + 1}. NAME: "${inp.name}", ID: "${inp.id}", TYPE: "${inp.type}", READONLY: ${inp.readOnly}, VALUE: "${inp.value}"`);
            });
        } else {
            // If no indirect candidates found, let's see ALL inputs to understand what's there
            debugLog('disaggregation-calculator', `🔍 No indirect/reach candidates found. Showing first 10 inputs:`);
            Array.from(allInputs).slice(0, 10).forEach((inp, idx) => {
                debugLog('disaggregation-calculator', `  ${idx + 1}. NAME: "${inp.name || 'NO NAME'}", ID: "${inp.id || 'NO ID'}", TYPE: "${inp.type}"`);
            });
        }

        // Try multiple selectors to find indirect reach fields
        let indirectFields = repeatEntry.querySelectorAll('input[name*="_indirect_reach"]:not([readonly])');
        debugLog('disaggregation-calculator', `Selector 1 (_indirect_reach): found ${indirectFields.length} fields`);

        if (indirectFields.length === 0) {
            indirectFields = repeatEntry.querySelectorAll('input[name*="indirect_reach"]:not([readonly])');
            debugLog('disaggregation-calculator', `Selector 2 (indirect_reach): found ${indirectFields.length} fields`);
        }

        if (indirectFields.length === 0) {
            // Try without the readonly filter in case that's the issue
            indirectFields = repeatEntry.querySelectorAll('input[name*="indirect_reach"]');
            debugLog('disaggregation-calculator', `Selector 3 (indirect_reach, including readonly): found ${indirectFields.length} fields`);
        }

        if (indirectFields.length > 0) {
            debugLog('disaggregation-calculator', `✅ Found indirect reach field in repeat entry: ${indirectFields[0].name} (readonly: ${indirectFields[0].readOnly})`);
            return indirectFields[0];
        }

        debugLog('disaggregation-calculator', `❌ No indirect reach field found for ${itemType}-${parentId} in repeat entry ${repeatEntry.id}`);
        return null;
    }

    /**
     * Find main value field with repeat entry context
     */
    findMainFieldWithContext(parentId, itemType, repeatEntry) {
        debugLog('disaggregation-calculator', `findMainFieldWithContext called for ${itemType}-${parentId} in repeat entry: ${repeatEntry ? repeatEntry.id : 'none'}`);

        if (!repeatEntry) {
            // Fall back to standard method if no repeat context
            return this.findMainField(parentId, itemType);
        }

        // Search only within the specific repeat entry
        debugLog('disaggregation-calculator', `Looking for main field in repeat entry: ${repeatEntry.id}`);

        // Look for total value fields with the repeat naming pattern
        let repeatField = repeatEntry.querySelector(`input[name*="repeat_"][name*="_total_value"]`);
        if (repeatField) {
            debugLog('disaggregation-calculator', `Found repeat main field with total_value pattern: ${repeatField.name}`);
            return repeatField;
        }

        // Look for standard value fields with the repeat naming pattern
        repeatField = repeatEntry.querySelector(`input[name*="repeat_"][name*="_standard_value"]`);
        if (repeatField) {
            debugLog('disaggregation-calculator', `Found repeat main field with standard_value pattern: ${repeatField.name}`);
            return repeatField;
        }

        // Legacy fallback pattern
        repeatField = repeatEntry.querySelector(`input[name*="repeat_"][name$="_4"]`);
        if (repeatField) {
            debugLog('disaggregation-calculator', `Found repeat main field with legacy _4 pattern: ${repeatField.name}`);
            return repeatField;
        }

        debugLog('disaggregation-calculator', `No main field found for ${itemType}-${parentId} in repeat entry ${repeatEntry.id}`);
        return null;
    }

    /**
     * Find active (visible) disaggregation container
     */
    findActiveContainer(parentId, itemType) {
        // Find all containers for this parent and item type
        const containers = document.querySelectorAll(`.disaggregation-inputs[data-parent-id="${parentId}"][data-item-type="${itemType}"]`);

        // Return the first visible one
        for (let container of containers) {
            if (this.isContainerVisible(container)) {
                debugLog('disaggregation-calculator', `Found active container for ${itemType}-${parentId}: ${container.getAttribute('data-mode')}`);
                return container;
            }
        }

        debugLog('disaggregation-calculator', `No active container found for ${itemType}-${parentId}`);
        return null;
    }

    /**
     * Recalculate when disaggregation mode changes
     */
    recalculateOnModeChange(fieldId, selectedMode, itemType) {
        const container = document.querySelector(`.disaggregation-inputs[data-parent-id="${fieldId}"][data-item-type="${itemType}"][data-mode="${selectedMode}"]`);

        if (container) {
            // Small delay to ensure container is visible
            setTimeout(() => {
                this.calculateContainer(container);
            }, 50);
        }
    }

    /**
     * Reinitialize for new content (like repeat entries)
     */
    reinitialize() {
        debugLog('disaggregation-calculator', 'Reinitializing disaggregation calculator...');
        this.reset();
        this.setupListeners();
        this.calculateAll();
        debugLog('disaggregation-calculator', 'Disaggregation calculator reinitialized');
    }

    /**
     * Add listeners to a specific repeat entry (called when new repeat entries are created)
     */
    addListenersToRepeatEntry(repeatEntry) {
        if (!repeatEntry) return;

        debugLog('disaggregation-calculator', `Adding listeners to repeat entry: ${repeatEntry.id}`);

        // Add listeners to disaggregation inputs within this repeat entry
        const containers = repeatEntry.querySelectorAll('.disaggregation-inputs');
        containers.forEach(container => {
            const inputs = container.querySelectorAll('input[data-numeric="true"], input[type="number"]');
            inputs.forEach(input => this.addInputListener(input, container));
        });

        // Add listeners to indirect reach inputs within this repeat entry
        const indirectInputs = repeatEntry.querySelectorAll('input[name*="_indirect_reach"], input[name*="indirect_reach"]');
        debugLog('disaggregation-calculator', `Found ${indirectInputs.length} indirect reach inputs in repeat entry ${repeatEntry.id}`);
        indirectInputs.forEach((input, index) => {
            debugLog('disaggregation-calculator', `Setting up listener for repeat indirect input ${index + 1}: ${input.name}`);
            this.addIndirectListener(input);
        });

        // Calculate totals for the new repeat entry
        this.calculateRepeatEntry(repeatEntry);
    }

    /**
     * Calculate totals for all containers within a specific repeat entry
     */
    calculateRepeatEntry(repeatEntry) {
        if (!repeatEntry) return;

        const containers = repeatEntry.querySelectorAll('.disaggregation-inputs');
        containers.forEach(container => {
            if (this.isContainerVisible(container)) {
                this.calculateContainer(container);
            }
        });
    }

    /**
     * Force recalculate all totals
     */
    forceRecalculateAll() {
        this.debounceTimers.forEach(timer => clearTimeout(timer));
        this.debounceTimers.clear();
        this.calculateAll();
    }

    /**
     * Force recalculate specific field
     */
    forceRecalculateField(fieldId, itemType) {
        const containers = document.querySelectorAll(`.disaggregation-inputs[data-parent-id="${fieldId}"][data-item-type="${itemType}"]`);
        containers.forEach(container => {
            this.calculateContainer(container);
        });
    }
}

// ============================================================================
// GLOBAL INTERFACE
// ============================================================================

// Create singleton instance
const calculationEngine = new CalculationEngine();

// Initialize when DOM is ready
export function initDisaggregationCalculator() {
    calculationEngine.init();
}

// Reset function for re-initialization
export function resetDisaggregationCalculator() {
    calculationEngine.reset();
}

// Recalculate when mode changes
export function recalculateTotalsOnModeChange(fieldId, selectedMode, itemType) {
    calculationEngine.recalculateOnModeChange(fieldId, selectedMode, itemType);
}

// Reinitialize for new content
export function reinitializeDisaggregationCalculator() {
    calculationEngine.reinitialize();
}

// Force recalculation functions
export function forceRecalculateAllTotals() {
    calculationEngine.forceRecalculateAll();
}

export function forceRecalculateFieldTotals(fieldId, itemType) {
    calculationEngine.forceRecalculateField(fieldId, itemType);
}

// Expose method to add listeners to new repeat entries
export function addListenersToRepeatEntry(repeatEntry) {
    calculationEngine.addListenersToRepeatEntry(repeatEntry);
}

// Make functions globally available
window.recalculateTotalsOnModeChange = recalculateTotalsOnModeChange;
window.forceRecalculateAllTotals = forceRecalculateAllTotals;
window.forceRecalculateFieldTotals = forceRecalculateFieldTotals;
window.reinitializeDisaggregationCalculator = reinitializeDisaggregationCalculator;
window.addListenersToRepeatEntry = addListenersToRepeatEntry;
