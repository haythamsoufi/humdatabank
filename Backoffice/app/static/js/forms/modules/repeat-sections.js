/**
 * Repeat Sections Module
 *
 * Handles dynamic repeat sections in forms, allowing users to create multiple instances
 * of a group of fields. This module now uses unified data availability handling that
 * is consistent with standard sections.
 *
 * Data availability flags are parsed from multiple formats:
 * - Legacy: {value: "data", data_not_available: true} (object with top-level flags)
 * - Unified: '{"value": "data", "data_not_available": true}' (JSON string with embedded flags)
 * - Simple: "data" (just the value)
 */

import { debugLog, debugWarn, debugError } from './debug.js';
import { updateFieldVisibility } from './field-management.js';
import { applyLayoutToContainer } from './layout.js';
import { setupNumberInputFormatting } from './formatting.js';
import { reinitializeDisaggregationCalculator } from './disaggregation-calculator.js';

/**
 * Parse a field value that might contain data availability flags in various formats
 * @param {*} fieldData - The field data from the backend
 * @returns {Object} - {value, dataNotAvailable, notApplicable}
 */
function parseFieldDataWithAvailability(fieldData) {
    let fieldValue, dataNotAvailable = false, notApplicable = false;

    if (typeof fieldData === 'object' && fieldData !== null && 'value' in fieldData) {
        // Current structure with data availability flags at top level
        fieldValue = fieldData.value;
        dataNotAvailable = fieldData.data_not_available || false;
        notApplicable = fieldData.not_applicable || false;
    } else if (typeof fieldData === 'string' && fieldData.startsWith('{')) {
        // Potential unified format: data availability flags might be embedded in JSON value
        try {
            const parsedData = JSON.parse(fieldData);
            if (typeof parsedData === 'object' && parsedData !== null &&
                ('data_not_available' in parsedData || 'not_applicable' in parsedData)) {
                // Unified format with embedded flags
                fieldValue = parsedData.value;
                dataNotAvailable = parsedData.data_not_available || false;
                notApplicable = parsedData.not_applicable || false;
            } else {
                // Regular JSON value without data availability flags
                fieldValue = fieldData;
            }
        } catch (e) {
            // Not valid JSON, treat as simple string
            fieldValue = fieldData;
        }
    } else {
        // Legacy structure - just the value
        fieldValue = fieldData;
    }

    return { value: fieldValue, dataNotAvailable, notApplicable };
}

export function initRepeatSections() {
    setupRepeatSections();
    loadExistingRepeatData();
}

function setupRepeatSections() {
    const form = document.querySelector('form');
    if (!form) {
        debugWarn('repeat-sections', 'No form found, skipping repeat sections setup');
        return;
    }

    const allElementsWithAddRepeat = document.querySelectorAll('[id*="add-repeat"]');
    const allSectionContainers = document.querySelectorAll('[id^="section-container-"]');

    // First check if there are any repeat sections at all
    const repeatSections = document.querySelectorAll('[data-section-type="repeat"]');
    debugLog('repeat-sections', `Found ${repeatSections.length} sections with data-section-type="repeat"`);

    // If there are no repeat sections, there's nothing to set up - this is normal
    if (repeatSections.length === 0) {
        debugLog('repeat-sections', 'No repeat sections found in form - skipping setup');
        return;
    }

    // Set up add buttons for each repeat section.
    //
    // IMPORTANT: In some contexts (e.g. preview), the repeat interface (and its buttons) can be rendered
    // outside the <form> element. If we only query within the form, we can miss the buttons and never
    // attach handlers, making "Add Entry" appear broken even though the button exists in the DOM.
    //
    // So: query at document-level and also install a delegated click handler as a robust fallback.
    const addButtons = document.querySelectorAll('[id^="add-repeat-entry-btn-"]');
    debugLog('repeat-sections', `Found ${addButtons.length} repeat section buttons`);

    if (addButtons.length === 0) {
        debugWarn('repeat-sections', '⚠️ No repeat buttons found! Let me check what might be wrong...');

        repeatSections.forEach((section, index) => {
            const sectionId = section.id.replace('section-container-', '');
            debugLog('repeat-sections', `  Repeat section ${index + 1}: ID=${sectionId}`);

            // Check if the repeat interface elements exist
            const repeatInterface = document.getElementById(`repeat-interface-${sectionId}`);
            const repeatEntries = document.getElementById(`repeat-entries-${sectionId}`);
            const addButton = document.getElementById(`add-repeat-entry-btn-${sectionId}`);

            debugLog('repeat-sections', `    repeat-interface-${sectionId}: ${repeatInterface ? 'EXISTS' : 'MISSING'}`);
            debugLog('repeat-sections', `    repeat-entries-${sectionId}: ${repeatEntries ? 'EXISTS' : 'MISSING'}`);
            debugLog('repeat-sections', `    add-repeat-entry-btn-${sectionId}: ${addButton ? 'EXISTS' : 'MISSING'}`);

            if (!addButton) {
                debugError('repeat-sections', `❌ Button add-repeat-entry-btn-${sectionId} is missing from DOM!`);
                debugLog('repeat-sections', 'This means the HTML template repeat interface is not rendering properly.');
            }

            // Check if the interface exists but is hidden/removed
            if (repeatInterface) {
                const isVisible = repeatInterface.offsetParent !== null;
                const computedStyle = window.getComputedStyle(repeatInterface);
                debugLog('repeat-sections', `    repeat-interface-${sectionId} visibility: ${isVisible ? 'VISIBLE' : 'HIDDEN'}`);
                debugLog('repeat-sections', `    repeat-interface-${sectionId} display: ${computedStyle.display}`);
                debugLog('repeat-sections', `    repeat-interface-${sectionId} opacity: ${computedStyle.opacity}`);
            }
        });
    } else {
        debugLog('repeat-sections', `✅ Found repeat buttons: ${Array.from(addButtons).map(btn => btn.id).join(', ')}`);
    }

    // Delegated click handler (installed once) so clicks work even if:
    // - the button is outside the <form>
    // - the button is injected later
    // - the click lands on a child icon element
    if (!window.__repeatSectionsAddEntryDelegatedHandlerInstalled) {
        window.__repeatSectionsAddEntryDelegatedHandlerInstalled = true;
        document.addEventListener('click', (e) => {
            const target = e.target;
            if (!(target instanceof Element)) return;

            const button = target.closest('[id^="add-repeat-entry-btn-"]');
            if (!button) return;

            // Prevent default if the repeat UI uses <a> tags, and avoid double-handling.
            e.preventDefault();

            // Resolve sectionId from attribute first, then from the element id.
            let sectionId = button.getAttribute('data-section-id') || button.dataset.sectionId;
            if (!sectionId && button.id) {
                const match = button.id.match(/^add-repeat-entry-btn-(\d+)$/);
                if (match) sectionId = match[1];
            }

            debugLog('repeat-sections', `Clicked add-repeat-entry button: ${button.id} (sectionId=${sectionId || 'missing'})`);

            if (sectionId) {
                addRepeatEntry(sectionId);
            } else {
                debugWarn('repeat-sections', 'Add-repeat button click ignored: could not resolve section id');
            }
        }, true); // capture=true to beat other handlers that might stopPropagation
        debugLog('repeat-sections', '✅ Installed delegated Add Entry click handler');
    }

    // Set up delete buttons for existing repeat entries
    setupDeleteButtons();

    // Auto-create Entry #1 for each repeat section
    createInitialRepeatEntries();
}

function createInitialRepeatEntries() {
    // Auto-create Entry #1 for each repeat section
    const repeatSections = document.querySelectorAll('[data-section-type="repeat"]');
    repeatSections.forEach(sectionContainer => {
        const sectionId = sectionContainer.id.replace('section-container-', '');
        const repeatContainer = document.getElementById(`repeat-entries-${sectionId}`);

        if (repeatContainer && repeatContainer.children.length === 0) {
            debugLog('repeat-sections', `Auto-creating Entry #1 for repeat section ${sectionId}`);
            createRepeatEntry(sectionId, true); // true = is initial entry
        }

        // Update limit text display (for both new and existing entries)
        updateRepeatLimitText(sectionId);
    });
}

/**
 * Update the max entries limit text display
 * @param {string} sectionId - The section ID
 */
function updateRepeatLimitText(sectionId) {
    const limitTextElement = document.getElementById(`repeat-limit-text-${sectionId}`);
    if (!limitTextElement) {
        return; // No limit text element found
    }

    const sectionContainer = document.getElementById(`section-container-${sectionId}`);
    if (!sectionContainer) {
        return;
    }

    const maxEntries = sectionContainer.getAttribute('data-max-entries');
    if (!maxEntries) {
        return; // No max entries limit set
    }

    const maxEntriesNum = parseInt(maxEntries, 10);
    if (isNaN(maxEntriesNum)) {
        return;
    }

    const repeatContainer = document.getElementById(`repeat-entries-${sectionId}`);
    if (!repeatContainer) {
        return;
    }

    const currentEntries = repeatContainer.querySelectorAll('.repeat-entry').length;

    // Update text to show current/max format
    limitTextElement.textContent = `Max entries: ${currentEntries}/${maxEntriesNum}`;

    // Add visual indicator if limit is reached
    if (currentEntries >= maxEntriesNum) {
        limitTextElement.classList.add('text-red-600', 'font-semibold');
        limitTextElement.classList.remove('text-gray-500');
    } else {
        limitTextElement.classList.remove('text-red-600', 'font-semibold');
        limitTextElement.classList.add('text-gray-500');
    }
}

function addRepeatEntry(sectionId) {
    debugLog('repeat-sections', `Adding repeat entry for section ${sectionId}`);

    // Check max entries limit
    const sectionContainer = document.getElementById(`section-container-${sectionId}`);
    if (sectionContainer) {
        const maxEntries = sectionContainer.getAttribute('data-max-entries');
        if (maxEntries) {
            const maxEntriesNum = parseInt(maxEntries, 10);
            if (!isNaN(maxEntriesNum)) {
                const repeatContainer = document.getElementById(`repeat-entries-${sectionId}`);
                if (repeatContainer) {
                    const currentEntries = repeatContainer.querySelectorAll('.repeat-entry').length;
                    if (currentEntries >= maxEntriesNum) {
                        debugWarn('repeat-sections', `Cannot add more entries: reached maximum of ${maxEntriesNum}`);
                        const msg = `Maximum number of entries (${maxEntriesNum}) has been reached for this repeat group.`;
                        if (window.showAlert) window.showAlert(msg, 'warning');
                        else console.warn(msg);
                        return;
                    }
                }
            }
        }
    }

    createRepeatEntry(sectionId, false); // false = not initial entry
    updateRepeatLimitText(sectionId); // Update limit display after adding
}

function createRepeatEntry(sectionId, isInitialEntry = false) {
    // Get the section container
    const sectionContainer = document.getElementById(`section-container-${sectionId}`);
    if (!sectionContainer) {
        debugError('repeat-sections', `Could not find section container for section ${sectionId}`);
        return;
    }

    // Get the repeat entries container
    const repeatContainer = document.getElementById(`repeat-entries-${sectionId}`);
    if (!repeatContainer) {
        debugError('repeat-sections', `Could not find repeat entries container for section ${sectionId}`);
        return;
    }

    // Get the current number of entries
    const existingEntries = repeatContainer.querySelectorAll('.repeat-entry');
    const instanceNumber = existingEntries.length + 1;

    // Find fields to use
    let fieldsToUse;
    if (isInitialEntry) {
        // Initial entry: move original fields
        fieldsToUse = Array.from(sectionContainer.querySelectorAll('.form-item-block:not([data-repeat-instance]):not(.layout-ignore .form-item-block):not(.layout-ignore)'));
        debugLog('repeat-sections', `Initial entry: Moving ${fieldsToUse.length} original fields to Entry #1`);
    } else {
        // Subsequent entries: clone from Entry #1
        const firstEntry = repeatContainer.querySelector('.repeat-entry[data-repeat-instance="1"]');
        if (!firstEntry) {
            debugError('repeat-sections', `Entry #1 not found for cloning`);
            return;
        }
        fieldsToUse = Array.from(firstEntry.querySelectorAll('.form-item-block'));
        debugLog('repeat-sections', `Adding entry: Cloning ${fieldsToUse.length} fields from Entry #1`);
    }

    if (fieldsToUse.length === 0) {
        debugWarn('repeat-sections', `No fields found in section ${sectionId} to repeat`);
        return;
    }

    // Create new repeat entry container
    const repeatEntry = document.createElement('div');
    repeatEntry.className = 'repeat-entry border-2 border-green-200 rounded-lg p-4 bg-green-50 mb-4';
    repeatEntry.id = `repeat-entry-${sectionId}-${instanceNumber}`;
    repeatEntry.setAttribute('data-repeat-instance', instanceNumber);

    // Add header with entry number and delete button
    const header = document.createElement('div');
    header.className = 'flex items-center justify-between mb-4 pb-2 border-b border-green-300';

    const entryLabel = document.createElement('h5');
    entryLabel.className = 'font-semibold text-green-800 flex items-center';
    const icon = document.createElement('i');
    icon.className = 'fas fa-copy w-4 h-4 mr-2';
    entryLabel.appendChild(icon);
    entryLabel.appendChild(document.createTextNode(`${window.REPEAT_SECTION_LABELS?.entry || 'Entry'} #${instanceNumber}`));

    const deleteButton = document.createElement('button');
    deleteButton.type = 'button';
    deleteButton.className = 'text-red-600 hover:text-red-800 transition-colors p-1';
    const deleteIcon = document.createElement('i');
    deleteIcon.className = 'fas fa-trash w-4 h-4';
    deleteButton.appendChild(deleteIcon);
    deleteButton.title = window.REPEAT_SECTION_LABELS?.deleteThisEntry || 'Delete this entry';
    deleteButton.addEventListener('click', function() {
        const confirmMessage = window.REPEAT_SECTION_LABELS?.confirmDeleteEntry || 'Are you sure you want to delete this entry?';
        if (window.showDangerConfirmation) {
            window.showDangerConfirmation(
                confirmMessage,
                () => {
                    repeatEntry.remove();
                    repeatEntry.remove();
                    debugLog('repeat-sections', `Deleted repeat entry #${instanceNumber} for section ${sectionId}`);
                    updateRepeatLimitText(sectionId); // Update limit display after removing
                },
                null,
                'Delete',
                'Cancel',
                'Delete Entry?'
            );
        } else if (window.showConfirmation) {
            window.showConfirmation(
                confirmMessage,
                () => {
                    repeatEntry.remove();
                    debugLog('repeat-sections', `Deleted repeat entry #${instanceNumber} for section ${sectionId}`);
                    updateRepeatLimitText(sectionId); // Update limit display after removing
                },
                null,
                'Delete',
                'Cancel',
                'Delete Entry?'
            );
        } else {
            console.warn('Confirmation dialog not available:', confirmMessage);
        }
    });

    header.appendChild(entryLabel);
    header.appendChild(deleteButton);
    repeatEntry.appendChild(header);

    // Process fields - move for first entry, clone for subsequent entries
    const fieldsContainer = document.createElement('div');
    fieldsContainer.className = 'space-y-4';

    fieldsToUse.forEach((field, fieldIndex) => {
        let processedField;

        if (isInitialEntry) {
            // Initial entry: move original field (remove from original location)
            processedField = field;
            field.remove(); // Remove from original location
            debugLog('repeat-sections', `Moved original field ${fieldIndex + 1} to Entry #1`);
        } else {
            // Subsequent entries: clone field
            processedField = field.cloneNode(true);
            debugLog('repeat-sections', `Cloned field ${fieldIndex + 1} for new entry`);
        }

        // Update field IDs and names for the repeat instance
        updateRepeatFieldAttributes(processedField, sectionId, instanceNumber, fieldIndex, field);

        // Clear any existing values (except for initial entry which keeps original values)
        if (!isInitialEntry) {
            clearFieldValues(processedField);
        } else {
            // For initial entry, still set default reporting modes to ensure proper state
            setDefaultReportingModes(processedField);
        }

        fieldsContainer.appendChild(processedField);
    });

    repeatEntry.appendChild(fieldsContainer);
    repeatContainer.appendChild(repeatEntry);

    // Apply layout to the newly created repeat entry
    applyLayoutToContainer(repeatEntry);

    // Ensure default radio button states for the entire repeat entry
    if (!isInitialEntry) {
        setDefaultReportingModes(repeatEntry);
    }

    // Reinitialize all form features for the repeat entry
    reinitializeFormFeatures(repeatEntry);

    if (isInitialEntry) {
        debugLog('repeat-sections', `✅ Created initial Entry #${instanceNumber} for section ${sectionId}`);
    } else {
        debugLog('repeat-sections', `✅ Added repeat entry #${instanceNumber} for section ${sectionId}`);
    }
}

function updateRepeatFieldAttributes(fieldElement, sectionId, instanceNumber, fieldIndex, originalField) {
    // Update all input, select, and textarea elements
    const inputs = fieldElement.querySelectorAll('input, select, textarea');

    // Pre-calculate field types for all inputs BEFORE any renaming to avoid count issues
    const fieldTypeMap = new Map();
    Array.from(inputs).forEach((input, inputIndex) => {
        const originalName = input.name;

        const isYesNoField = input.type === 'checkbox' && (input.value === 'yes' || input.value === 'no');
        const isRadioButton = input.type === 'radio';
        const isDataAvailabilityCheckbox = originalName.includes('_data_not_available') || originalName.includes('_not_applicable');

        // Normalize the base name to handle both original and already-cloned patterns
        let baseName = originalName;
        if (originalName.startsWith('repeat_')) {
            // Extract base name from already-cloned repeat field names
            const match = originalName.match(/^repeat_\d+_\d+_field_(\d+)(?:_\d+)?$/);
            if (match) {
                baseName = `field_${match[1]}`;
            }
        } else if (originalName.includes('field_value[')) {
            // Extract base name from field_value[X] pattern
            const match = originalName.match(/field_value\[(\d+)\]/);
            if (match) {
                baseName = `field_${match[1]}`;
            }
        }

        // Count ALL checkboxes with the same logical field (before any renaming)
        const relatedCheckboxes = Array.from(inputs).filter(i => {
            if (i.type !== 'checkbox') return false;

            let iBaseName = i.name;
            if (i.name.startsWith('repeat_')) {
                const match = i.name.match(/^repeat_\d+_\d+_field_(\d+)(?:_\d+)?$/);
                if (match) {
                    iBaseName = `field_${match[1]}`;
                }
            } else if (i.name.includes('field_value[')) {
                const match = i.name.match(/field_value\[(\d+)\]/);
                if (match) {
                    iBaseName = `field_${match[1]}`;
                }
            }

            return iBaseName === baseName;
        });

        const isMultiSelectField = input.type === 'checkbox' &&
                                   !isYesNoField &&
                                   !isDataAvailabilityCheckbox &&
                                   relatedCheckboxes.length > 1;

        fieldTypeMap.set(input, {
            isYesNoField,
            isRadioButton,
            isDataAvailabilityCheckbox,
            isMultiSelectField,
            relatedCheckboxCount: relatedCheckboxes.length
        });
    });

    // Debug: Check for indirect reach fields BEFORE transformation
    const preIndirectFields = fieldElement.querySelectorAll('input[name*="indirect_reach"]');
    if (preIndirectFields.length > 0) {
        debugLog('repeat-sections', `🎯 FOUND ${preIndirectFields.length} indirect reach fields BEFORE transformation in field ${fieldIndex}:`);
        preIndirectFields.forEach((field, idx) => {
            debugLog('repeat-sections', `  ${idx + 1}. PRE-TRANSFORM: name="${field.name}", id="${field.id}"`);
        });
    } else {
        debugLog('repeat-sections', `❌ NO indirect reach fields found in fieldElement before transformation (field ${fieldIndex})`);
        debugLog('repeat-sections', `   Searched in: ${fieldElement.tagName}${fieldElement.className ? '.' + fieldElement.className.replace(' ', '.') : ''}`);
    }

    inputs.forEach((input, inputIndex) => {
        const originalName = input.name;
        const originalId = input.id;

        // Create new name and ID for repeat field
        let newName, newId;

        // Get pre-calculated field types
        const fieldTypes = fieldTypeMap.get(input);
        const {isYesNoField, isRadioButton, isDataAvailabilityCheckbox, isMultiSelectField} = fieldTypes;

        // Special logging for indirect reach fields
        const isIndirectReach = originalName.includes('indirect_reach');
        if (isIndirectReach) {
            debugLog('repeat-sections', `🟡 PROCESSING INDIRECT REACH FIELD: ${originalName} → transforming...`);
        }

        debugLog('repeat-sections', `🔧 Renaming ${originalName} (value: ${input.value}) - isMultiSelect: ${isMultiSelectField}, isYesNo: ${isYesNoField}, isRadio: ${isRadioButton}, isDataAvail: ${isDataAvailabilityCheckbox}`);

        if (isYesNoField) {
            // For YesNo checkboxes, use the same name but different IDs
            newName = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_standard_value`;
            newId = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_${input.value}`;
        } else if (/^(indicator|dynamic)_\d+_.+$/i.test(originalName)) {
            // Preserve disaggregation and other indicator/dynamic suffixes
            // Example matches:
            //  - indicator_47_total_value
            //  - indicator_47_reporting_mode (handled below for radios but safe here if not radio)
            //  - indicator_47_sex_male
            //  - indicator_47_age_5_17
            //  - indicator_47_sexage_female_18_49
            //  - indicator_47_indirect_reach
            //  - dynamic_123_total_value, etc.
            const suffix = originalName.replace(/^(indicator|dynamic)_\d+_/i, '');
            newName = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_${suffix}`;
            newId = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_${suffix}_${inputIndex}`;
        } else if (/^repeat_\d+_\d+_field_\d+_.+$/i.test(originalName)) {
            // Handle already-transformed repeat fields (for Entry #2, #3, etc.)
            // Example matches:
            //  - repeat_23_1_field_1_indirect_reach
            //  - repeat_23_1_field_1_total_value
            //  - repeat_23_1_field_1_sex_male
            const suffixMatch = originalName.match(/^repeat_\d+_\d+_field_\d+_(.+)$/i);
            if (suffixMatch) {
                const suffix = suffixMatch[1];
                newName = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_${suffix}`;
                newId = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_${suffix}_${inputIndex}`;
            } else {
                // Fallback if pattern doesn't match
                newName = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_${inputIndex}`;
                newId = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_${inputIndex}`;
            }
        } else if (isMultiSelectField) {
            // For multi-select checkboxes, all checkboxes for the same field should have the same name
            newName = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}`;
            newId = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_${inputIndex}`;
            debugLog('repeat-sections', `🔄 Multi-select checkbox: ${originalName} → ${newName} (value: ${input.value})`);
        } else if (input.type === 'checkbox' && !isYesNoField && !isDataAvailabilityCheckbox) {
            // Fallback: treat any remaining checkbox (that's not yes/no or data availability) as multi-select
            // This ensures consistency even if detection logic fails
            newName = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}`;
            newId = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_${inputIndex}`;
            debugLog('repeat-sections', `🔄 Fallback multi-select checkbox: ${originalName} → ${newName} (value: ${input.value})`);
        } else if (isRadioButton) {
            // For radio buttons, preserve the base name structure for mutual exclusivity
            // Extract the base pattern and add repeat prefix
            if (originalName.includes('_reporting_mode')) {
                newName = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_reporting_mode`;
            } else {
                newName = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_radio`;
            }
            newId = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_${input.value}`;
        } else if (isDataAvailabilityCheckbox) {
            // For data availability checkboxes, preserve the suffix pattern
            if (originalName.includes('_data_not_available')) {
                newName = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_data_not_available`;
                newId = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_data_not_available`;
            } else if (originalName.includes('_not_applicable')) {
                newName = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_not_applicable`;
                newId = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_not_applicable`;
            } else {
                newName = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_${inputIndex}`;
                newId = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_${inputIndex}`;
            }
        } else {
            newName = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_${inputIndex}`;
            newId = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_${inputIndex}`;
        }

        input.name = newName;
        input.id = newId;

        // Special logging for indirect reach fields
        if (isIndirectReach) {
            debugLog('repeat-sections', `🟢 INDIRECT REACH FIELD TRANSFORMED: ${originalName} → ${newName} (ID: ${originalId} → ${newId})`);
        }

        // Update corresponding label
        const label = fieldElement.querySelector(`label[for="${originalId}"]`);
        if (label) {
            label.setAttribute('for', newId);
        }

        debugLog('repeat-sections', `Updated field: ${originalName} → ${newName} (ID: ${originalId} → ${newId})`);
    });

    // Debug: Verify indirect reach fields AFTER transformation
    const postIndirectFields = fieldElement.querySelectorAll('input[name*="indirect_reach"]');
    if (postIndirectFields.length > 0) {
        debugLog('repeat-sections', `🎯 VERIFIED ${postIndirectFields.length} indirect reach fields AFTER transformation:`);
        postIndirectFields.forEach((field, idx) => {
            debugLog('repeat-sections', `  ${idx + 1}. POST-TRANSFORM: name="${field.name}", id="${field.id}"`);
        });
    } else {
        debugLog('repeat-sections', `❌ NO indirect reach fields found after transformation in field ${fieldIndex}`);
    }

    // Update ALL elements with IDs (excluding form inputs already handled above) to ensure uniqueness
    const allElementsWithIds = fieldElement.querySelectorAll('[id]');
    const formInputs = fieldElement.querySelectorAll('input, select, textarea');

    allElementsWithIds.forEach((element, index) => {
        // Skip if this is a form input (already handled above)
        if (Array.from(formInputs).includes(element)) {
            return;
        }

        const originalId = element.id;
        let newId;

        // Preserve semantic IDs for calculated total fields that the disaggregation calculator needs
        if (originalId.includes('-total-calculated-') || originalId.includes('-indirect-reach-')) {
            // Extract the field number from the original ID
            const fieldNumberMatch = originalId.match(/(?:indicator|dynamic)-(?:total-calculated|indirect-reach)-(\d+)/);
            if (fieldNumberMatch) {
                const fieldNumber = fieldNumberMatch[1];
                // Create a unique but semantically meaningful ID for repeat sections
                if (originalId.includes('indicator-total-calculated-')) {
                    newId = `repeat-${sectionId}-${instanceNumber}-indicator-total-calculated-${fieldNumber}`;
                } else if (originalId.includes('dynamic-total-calculated-')) {
                    newId = `repeat-${sectionId}-${instanceNumber}-dynamic-total-calculated-${fieldNumber}`;
                } else if (originalId.includes('indicator-indirect-reach-')) {
                    newId = `repeat-${sectionId}-${instanceNumber}-indicator-indirect-reach-${fieldNumber}`;
                } else if (originalId.includes('dynamic-indirect-reach-')) {
                    newId = `repeat-${sectionId}-${instanceNumber}-dynamic-indirect-reach-${fieldNumber}`;
                } else {
                    newId = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_elem_${index}`;
                }
            } else {
                newId = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_elem_${index}`;
            }
        } else {
            // Use generic ID for other elements
            newId = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_elem_${index}`;
        }

        element.id = newId;

        // Update any labels that reference this element
        const labelsForElement = fieldElement.querySelectorAll(`label[for="${originalId}"]`);
        labelsForElement.forEach(label => {
            label.setAttribute('for', newId);
        });

        debugLog('repeat-sections', `Updated non-input element ID: ${originalId} → ${newId}`);
    });

    // Update data attributes
    fieldElement.setAttribute('data-repeat-instance', instanceNumber);
    fieldElement.setAttribute('data-section-id', sectionId);

    // Update data-field-id attributes for multi-select components to ensure unique identifiers
    const elementsWithFieldId = fieldElement.querySelectorAll('[data-field-id]');
    elementsWithFieldId.forEach(element => {
        const originalFieldId = element.getAttribute('data-field-id');
        const newFieldId = `repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_id`;
        element.setAttribute('data-field-id', newFieldId);
        debugLog('repeat-sections', `Updated data-field-id: ${originalFieldId} → ${newFieldId} for ${element.tagName}`);
    });

    // CRITICAL: Update data-parent-id attributes for disaggregation calculator compatibility
    const disaggregationContainers = fieldElement.querySelectorAll('.disaggregation-inputs[data-parent-id]');
    disaggregationContainers.forEach(container => {
        const originalParentId = container.getAttribute('data-parent-id');
        // For repeat sections, we keep the original field ID as the parent ID since that's what the calculator expects
        // The calculator will use field scope detection to find the right instance
        debugLog('repeat-sections', `Keeping data-parent-id as ${originalParentId} for calculator compatibility in disaggregation container`);
    });

    // Update calculated-total-section data-parent-id if it exists
    const calculatedTotalSections = fieldElement.querySelectorAll('.calculated-total-section[data-parent-id]');
    calculatedTotalSections.forEach(section => {
        const originalParentId = section.getAttribute('data-parent-id');
        debugLog('repeat-sections', `Keeping calculated-total-section data-parent-id as ${originalParentId} for calculator compatibility`);
    });

    // Update relevance conditions if any
    const relevanceAttr = fieldElement.getAttribute('data-relevance');
    if (relevanceAttr) {
        try {
            const conditions = JSON.parse(relevanceAttr);
            updateRelevanceConditions(conditions, instanceNumber);
            fieldElement.setAttribute('data-relevance', JSON.stringify(conditions));
        } catch (error) {
            debugWarn('repeat-sections', `Error updating relevance conditions for field ${fieldElement.getAttribute('data-field-id')}:`, error);
        }
    }
}

function updateRelevanceConditions(conditions, instanceNumber) {
    if (!conditions) return;

    // Handle AND conditions
    if (conditions.AND) {
        conditions.AND.forEach(condition => updateRelevanceConditions(condition, instanceNumber));
    }

    // Handle OR conditions
    if (conditions.OR) {
        conditions.OR.forEach(condition => updateRelevanceConditions(condition, instanceNumber));
    }

    // Handle NOT conditions
    if (conditions.NOT) {
        updateRelevanceConditions(conditions.NOT, instanceNumber);
    }

    // Handle basic conditions
    if (conditions.field) {
        conditions.field = `${conditions.field}_${instanceNumber}`;
    }
}

function clearFieldValues(fieldElement) {
    // Check if this is a matrix field
    const matrixContainer = fieldElement.querySelector('.matrix-container');

    if (matrixContainer) {
        debugLog('repeat-sections', `🔷 Detected matrix field - clearing matrix data`);

        // Clear the hidden field that stores matrix JSON data
        const hiddenField = matrixContainer.querySelector('input[type="hidden"]');
        if (hiddenField) {
            const emptyMatrixData = '';
            hiddenField.value = emptyMatrixData;
            debugLog('repeat-sections', `🧹 Cleared matrix hidden field ${hiddenField.name} to empty value`);
        }

        // Clear all matrix cell inputs
        const matrixInputs = matrixContainer.querySelectorAll('input[data-cell-key], input[data-column-type]');
        matrixInputs.forEach(input => {
            if (input.type !== 'hidden') {
                input.value = '';
                debugLog('repeat-sections', `🧹 Cleared matrix cell input ${input.name || input.id}`);
            }
        });

        // Clear row and column totals
        const totals = matrixContainer.querySelectorAll('.matrix-row-total, .matrix-column-total');
        totals.forEach(total => {
            total.textContent = '0';
        });

        // Remove all matrix rows from the tbody (keep header)
        const tbody = matrixContainer.querySelector('tbody[id*="matrix-tbody"], tbody');
        if (tbody) {
            const rows = Array.from(tbody.querySelectorAll('tr.matrix-row, tr[data-row-id]'));
            rows.forEach(row => row.remove());
            debugLog('repeat-sections', `🧹 Removed ${rows.length} matrix rows from tbody`);
        }

        // Also clear the search input
        const searchInput = matrixContainer.querySelector('input[type="text"][id*="matrix-row-search"]');
        if (searchInput) {
            searchInput.value = '';
            debugLog('repeat-sections', `🧹 Cleared matrix search input`);
        }

        // Don't clear matrix handler data here - it will be reinitialized in reinitializeFormFeatures
        // Just ensure the hidden field is cleared properly
        return; // Don't clear other inputs as they're already handled above
    }

    // For non-matrix fields, use the standard clearing logic
    const inputs = fieldElement.querySelectorAll('input, select, textarea');
    debugLog('repeat-sections', `🧹 Clearing values for ${inputs.length} inputs in cloned field`);

    inputs.forEach((input, index) => {
        switch (input.type) {
            case 'checkbox':
                input.checked = false;
                debugLog('repeat-sections', `🔲 Cleared checkbox ${input.name} (value: ${input.value})`);
                break;
            case 'radio':
                input.checked = false;
                debugLog('repeat-sections', `📻 Cleared radio ${input.name} (value: ${input.value})`);
                break;
            case 'select-one':
            case 'select-multiple':
                input.selectedIndex = 0; // Reset to first option (usually empty/default)
                debugLog('repeat-sections', `📋 Reset select ${input.name} to first option`);
                break;
            default:
                input.value = '';
                debugLog('repeat-sections', `📝 Cleared input ${input.name}`);
        }
    });

    // CRITICAL: Double-check that data availability checkboxes are definitely cleared
    // This prevents the data-availability module from finding checked checkboxes and disabling fields
    const dataAvailabilityCheckboxes = fieldElement.querySelectorAll('input[type="checkbox"][name*="_data_not_available"], input[type="checkbox"][name*="_not_applicable"]');
    debugLog('repeat-sections', `🔍 Double-checking ${dataAvailabilityCheckboxes.length} data availability checkboxes are cleared`);

    dataAvailabilityCheckboxes.forEach(checkbox => {
        if (checkbox.checked) {
            debugLog('repeat-sections', `⚠️ Found checked data availability checkbox ${checkbox.name} - forcibly clearing it`);
            checkbox.checked = false;
            // Remove any data-availability-disabled attributes that might have been set
            checkbox.removeAttribute('data-availability-disabled');
        }
    });

    // Also remove any data-availability-disabled attributes from all inputs and buttons to ensure clean state
    const allInteractiveElements = fieldElement.querySelectorAll('input, select, textarea, button');
    allInteractiveElements.forEach(element => {
        if (element.hasAttribute('data-availability-disabled')) {
            debugLog('repeat-sections', `🧽 Removing data-availability-disabled from ${element.tagName} ${element.name || element.id}`);
            element.removeAttribute('data-availability-disabled');
            // Also ensure it's not disabled
            element.disabled = false;
            element.style.opacity = '';
            element.style.backgroundColor = '';
            element.style.cursor = '';
            element.style.pointerEvents = '';
        }
    });

    // Set default radio button states for reporting modes
    setDefaultReportingModes(fieldElement);
}

function setDefaultReportingModes(fieldElement) {
    // Find all radio buttons for reporting modes
    const reportingModeRadios = fieldElement.querySelectorAll('input[type="radio"][name*="_reporting_mode"]');

    debugLog('repeat-sections', `Setting default reporting modes for ${reportingModeRadios.length} radio groups`);

    // Group radio buttons by field (since each field can have multiple radio buttons for different modes)
    const radioGroups = {};
    reportingModeRadios.forEach(radio => {
        const fieldMatch = radio.name.match(/^(.*?)_reporting_mode$/);
        if (fieldMatch) {
            const baseName = fieldMatch[1];
            if (!radioGroups[baseName]) {
                radioGroups[baseName] = [];
            }
            radioGroups[baseName].push(radio);
        }
    });

    // For each radio group, set "total" as default
    Object.keys(radioGroups).forEach(baseName => {
        const radios = radioGroups[baseName];
        debugLog('repeat-sections', `Processing radio group: ${baseName} with ${radios.length} options`);

        // Find and check the "total" radio button
        const totalRadio = radios.find(radio => radio.value === 'total');
        if (totalRadio) {
            totalRadio.checked = true;
            debugLog('repeat-sections', `✅ Set ${baseName} to "total" mode`);

            // Extract field ID for disaggregation containers
            const fieldIdMatch = baseName.match(/(?:indicator_|dynamic_\d+_)(\d+)$/);
            if (fieldIdMatch) {
                const fieldId = fieldIdMatch[1];
                const itemType = baseName.includes('dynamic_') ? 'dynamic' : 'indicator';

                // Use shared disaggregation logic to show total container
                showDefaultDisaggregationContainer(fieldElement, fieldId, itemType);
            }
        } else {
            debugLog('repeat-sections', `⚠️ No "total" radio found for ${baseName}`);
        }
    });
}

function showDefaultDisaggregationContainer(containerElement, fieldId, itemType) {
    // Use the shared disaggregation logic instead of manually showing/hiding containers
    // The disaggregation calculator will handle the container visibility automatically
    // when the radio button change event is triggered

    debugLog('repeat-sections', `🔄 Using shared disaggregation logic for field ${fieldId} (${itemType})`);

    // Find the radio button for this field and trigger the change event
    const radioButtons = containerElement.querySelectorAll(`input[type="radio"][name*="_reporting_mode"]`);
    const totalRadio = Array.from(radioButtons).find(radio => radio.value === 'total');

    if (totalRadio) {
        // Trigger the change event to let the disaggregation calculator handle the container visibility
        totalRadio.dispatchEvent(new Event('change'));
        debugLog('repeat-sections', `✅ Triggered change event for total radio button in field ${fieldId}`);
    } else {
        debugLog('repeat-sections', `⚠️ No total radio button found for field ${fieldId}`);
    }
}

function setupDeleteButtons() {
    // Delete buttons are now handled directly in the addRepeatEntry function
    // No need for event delegation since each button gets its own click handler
    debugLog('repeat-sections', 'Delete buttons are handled inline for each repeat entry');
}

function loadExistingRepeatData() {
    debugLog('repeat-sections', '📥 Loading existing repeat data...');

    // Get repeat groups data from global variable
    const repeatGroupsData = window.REPEAT_GROUPS_DATA || {};

    if (!repeatGroupsData || Object.keys(repeatGroupsData).length === 0) {
        debugLog('repeat-sections', '📭 No repeat groups data found');
        return;
    }

    debugLog('repeat-sections', `📊 Found repeat data for ${Object.keys(repeatGroupsData).length} sections:`, repeatGroupsData);

    // Load data for each section
    Object.keys(repeatGroupsData).forEach(sectionId => {
        debugLog('repeat-sections', `\n🏗️ Processing section ${sectionId}`);

        const sectionData = repeatGroupsData[sectionId];
        const repeatContainer = document.getElementById(`repeat-entries-${sectionId}`);
        if (!repeatContainer) {
            debugWarn('repeat-sections', `❌ No repeat container found for section ${sectionId}`);
            return;
        }

        // Sort instance numbers to ensure proper loading order
        const instanceNumbers = Object.keys(sectionData).map(num => parseInt(num)).sort((a, b) => a - b);
        debugLog('repeat-sections', `📋 Found ${instanceNumbers.length} instances: [${instanceNumbers.join(', ')}]`);

        instanceNumbers.forEach((instanceNumber, index) => {
            debugLog('repeat-sections', `\n📝 Processing instance ${instanceNumber} (${index + 1}/${instanceNumbers.length})`);

            const instanceData = sectionData[instanceNumber];
            debugLog('repeat-sections', `📊 Instance data:`, instanceData);

            // Check if this is the first instance and if Entry #1 already exists
            const existingEntries = repeatContainer.querySelectorAll('.repeat-entry');
            debugLog('repeat-sections', `📊 Current repeat entries: ${existingEntries.length}`);

            let currentEntry;

            if (instanceNumber === 1 && existingEntries.length > 0) {
                // For instance 1, use the existing Entry #1 (first entry)
                currentEntry = existingEntries[0];
                debugLog('repeat-sections', `✅ Using existing Entry #1 for instance ${instanceNumber}`);
            } else {
                // For other instances, create new repeat entry
                debugLog('repeat-sections', `🆕 Creating new repeat entry for instance ${instanceNumber}`);
                addRepeatEntry(sectionId);

                // Find the newly created repeat entry
                const newRepeatEntries = repeatContainer.querySelectorAll('.repeat-entry');
                currentEntry = newRepeatEntries[newRepeatEntries.length - 1];

                if (!currentEntry) {
                    debugWarn('repeat-sections', `❌ Could not find newly created repeat entry for instance ${instanceNumber}`);
                    return;
                }
                debugLog('repeat-sections', `✅ Created new repeat entry #${newRepeatEntries.length} for instance ${instanceNumber}`);
            }

            debugLog('repeat-sections', `🎯 Using repeat entry: ${currentEntry.id || 'no-id'} (data-repeat-instance: ${currentEntry.getAttribute('data-repeat-instance') || 'none'})`);

            // Fill in the values for this instance
            const fieldData = instanceData.data || instanceData;
            debugLog('repeat-sections', `🔍 Extracted field data:`, fieldData);
            debugLog('repeat-sections', `🔍 Field data keys: [${Object.keys(fieldData).join(', ')}]`);

            if (Object.keys(fieldData).length === 0) {
                debugLog('repeat-sections', `📭 No field data to load for instance ${instanceNumber}`);

                // Even if no data, make sure the entry is properly cleared (especially for cloned entries)
                if (instanceNumber > 1) {
                    debugLog('repeat-sections', `🧹 Entry ${instanceNumber} has no data - ensuring it's properly cleared`);
                    const allFields = currentEntry.querySelectorAll('[data-item-id]');
                    allFields.forEach(field => {
                        const fieldId = field.getAttribute('data-item-id');
                        debugLog('repeat-sections', `🧽 Ensuring field ${fieldId} is cleared in entry ${instanceNumber}`);

                        // Clear any values that might have been cloned
                        const inputs = field.querySelectorAll('input, select, textarea');
                        inputs.forEach(input => {
                            if (input.type === 'checkbox' || input.type === 'radio') {
                                if (!input.name.includes('_reporting_mode') || input.value !== 'total') {
                                    input.checked = false;
                                }
                            } else if (input.type === 'select-one') {
                                input.selectedIndex = 0;
                            } else {
                                input.value = '';
                            }
                        });
                    });
                }
                return;
            }

            debugLog('repeat-sections', `📋 Loading ${Object.keys(fieldData).length} field values into repeat entry`);
            Object.entries(fieldData).forEach(([fieldId, fieldData]) => {
                // Parse field data using unified utility function
                const { value: fieldValue, dataNotAvailable, notApplicable } = parseFieldDataWithAvailability(fieldData);

                debugLog('repeat-sections', `🔄 Loading field ${fieldId} = ${fieldValue} (data_not_available=${dataNotAvailable}, not_applicable=${notApplicable})`);

                loadFieldValue(currentEntry, fieldId, fieldValue, sectionId, instanceNumber, dataNotAvailable, notApplicable);
            });

            // Final cleanup: Clear any fields that exist in the form but don't have backend data
            if (instanceNumber > 1) {
                debugLog('repeat-sections', `🧹 Final cleanup for entry ${instanceNumber} - clearing fields without backend data`);
                const allFields = currentEntry.querySelectorAll('[data-item-id]');
                allFields.forEach(field => {
                    const fieldId = field.getAttribute('data-item-id');
                    if (!fieldData.hasOwnProperty(fieldId)) {
                        debugLog('repeat-sections', `🧽 Field ${fieldId} has no backend data - clearing any cloned values`);

                        // Clear multi-choice checkboxes specifically
                        const allCheckboxes = field.querySelectorAll('input[type="checkbox"]');
                        const multiChoiceCheckboxes = Array.from(allCheckboxes).filter(cb =>
                            !cb.value.match(/^(yes|no)$/) &&
                            !cb.name.includes('_data_not_available') &&
                            !cb.name.includes('_not_applicable')
                        );

                        multiChoiceCheckboxes.forEach(checkbox => {
                            if (checkbox.checked) {
                                debugLog('repeat-sections', `🔲 Clearing cloned checkbox ${checkbox.name} (value: ${checkbox.value})`);
                                checkbox.checked = false;
                            }
                        });

                        // Clear select fields
                        const selects = field.querySelectorAll('select');
                        selects.forEach(select => {
                            if (select.selectedIndex > 0) {
                                debugLog('repeat-sections', `📋 Resetting cloned select ${select.name}`);
                                select.selectedIndex = 0;
                            }
                        });
                    }
                });
            }
        });

        // Update limit text display after loading existing data
        updateRepeatLimitText(sectionId);
    });
}

/**
 * Set select value with fallback to text matching if value doesn't match
 */
function setSelectValueWithFallback(select, valueToSet) {
    if (!valueToSet) {
        select.value = '';
        return;
    }

    const originalValue = select.value;
    select.value = valueToSet;

    // Check if the value was actually set (it might not match any option value)
    if (select.value !== valueToSet && valueToSet) {
        debugLog('repeat-sections', `⚠️ Value "${valueToSet}" didn't match any option value, trying to match by text`);

        // Try to find an option by its text content
        let foundOption = null;
        const options = Array.from(select.options);
        for (const option of options) {
            // Check if the value matches the option's value or text
            if (option.value === valueToSet || option.textContent.trim() === valueToSet) {
                foundOption = option;
                break;
            }
        }

        if (foundOption) {
            select.value = foundOption.value;
            debugLog('repeat-sections', `✅ Found matching option by text, set value to: ${foundOption.value}`);
        } else {
            debugLog('repeat-sections', `❌ Could not find option matching "${valueToSet}"`);
            debugLog('repeat-sections', `📋 Available options (first 10):`,
                options.slice(0, 10).map(opt => `"${opt.value}" (text: "${opt.textContent.trim()}")`).join(', '));
            // Reset to original value if we couldn't find a match
            select.value = originalValue;
        }
    } else {
        debugLog('repeat-sections', `✅ Set select value: ${valueToSet} in ${select.name}`);
    }
}

function loadFieldValue(repeatEntry, fieldId, fieldValue, sectionId, instanceNumber, dataNotAvailable = false, notApplicable = false) {
    debugLog('repeat-sections', `🔄 Loading field value for field ${fieldId} in repeat entry ${instanceNumber}`);

    // Find the field in this specific repeat entry
    const field = repeatEntry.querySelector(`[data-item-id="${fieldId}"]`);
    if (!field) {
        debugWarn('repeat-sections', `❌ Field ${fieldId} not found in repeat entry ${instanceNumber}`);
        return;
    }

    debugLog('repeat-sections', `✅ Found field ${fieldId} in repeat entry`);

    // Parse the field value if it's a JSON string
    let parsedData = null;
    let valueToSet = fieldValue;
    let reportingMode = 'total'; // default

    if (typeof fieldValue === 'object' && fieldValue !== null) {
        // Field value is already a JavaScript object
        parsedData = fieldValue;
        debugLog('repeat-sections', `📊 Field value is already an object:`, parsedData);

        if (parsedData.mode && parsedData.values) {
            // Structured indicator data with disaggregation
            reportingMode = parsedData.mode;
            debugLog('repeat-sections', `📊 Object data - Mode: ${reportingMode}, Values:`, parsedData.values);
            debugLog('repeat-sections', `🔑 Value keys found:`, Object.keys(parsedData.values));
        } else if (parsedData.data_not_available !== undefined || parsedData.not_applicable !== undefined) {
            // Unified format with embedded data availability flags
            valueToSet = parsedData.value;
            debugLog('repeat-sections', `🔧 Object format detected - extracted value: ${valueToSet}`);
        } else {
            // Check if this might be matrix data (rowId_column keys)
            const hasColumnKeys = Object.keys(parsedData).some(key =>
                (typeof key === 'string') &&
                !key.startsWith('_') &&
                (key.includes('_Column ') || key.includes('Column') || key.includes('_'))
            );

            if (hasColumnKeys) {
                // This is likely matrix data - keep as object to handle specially
                debugLog('repeat-sections', `🔷 Detected potential matrix data with column keys`);
                valueToSet = fieldValue; // Keep as object for matrix handling
            } else {
                // Other object data - treat as simple value
                valueToSet = fieldValue;
                debugLog('repeat-sections', `📋 Object without mode/values or data availability flags, using as simple value`);
            }
        }
    } else if (typeof fieldValue === 'string' && fieldValue.startsWith('{')) {
        // Field value is a JSON string that needs parsing
        try {
            parsedData = JSON.parse(fieldValue);
            debugLog('repeat-sections', `📊 Parsed JSON string:`, parsedData);

            if (parsedData.mode && parsedData.values) {
                // Structured indicator data with disaggregation
                reportingMode = parsedData.mode;
                debugLog('repeat-sections', `📊 Parsed JSON data - Mode: ${reportingMode}, Values:`, parsedData.values);
                debugLog('repeat-sections', `🔑 Value keys found:`, Object.keys(parsedData.values));
            } else if (parsedData.data_not_available !== undefined || parsedData.not_applicable !== undefined) {
                // Unified format with embedded data availability flags
                valueToSet = parsedData.value;
                // Update the data availability flags for this field (they were already set in the calling function)
                debugLog('repeat-sections', `🔧 Unified format detected - extracted value: ${valueToSet}`);
            } else {
                // Other JSON data - use as simple value
                valueToSet = fieldValue;
                debugLog('repeat-sections', `📋 JSON data without mode/values or data availability flags, using as simple value: ${valueToSet}`);
            }
        } catch (e) {
            debugWarn('repeat-sections', `❌ Failed to parse JSON value: ${fieldValue}`);
            valueToSet = fieldValue; // Use as simple value
        }
    } else {
        // Simple value
        debugLog('repeat-sections', `📄 Simple value (not JSON): ${fieldValue}`);

        // For checkboxes, handle yes/no values
        if (fieldValue === 'yes' || fieldValue === 'no') {
            debugLog('repeat-sections', `☑️ Detected checkbox value: ${fieldValue}`);
        }
    }

    // Find all inputs in this field
    const inputs = field.querySelectorAll('input, select, textarea');
    debugLog('repeat-sections', `🔍 Found ${inputs.length} inputs in field ${fieldId}`);

    // Detect the actual repeat entry number from input names (it might differ from instanceNumber)
    let actualRepeatNumber = instanceNumber;
    if (inputs.length > 0) {
        const sampleInputName = inputs[0].name;
        const match = sampleInputName.match(new RegExp(`repeat_${sectionId}_(\\d+)_`));
        if (match) {
            actualRepeatNumber = parseInt(match[1]);
            debugLog('repeat-sections', `🎯 Detected actual repeat entry number: ${actualRepeatNumber} (from input: ${sampleInputName})`);
        }
    }

    // Log first 10 inputs for debugging
    const inputSample = Array.from(inputs).slice(0, 10);
    debugLog('repeat-sections', `🔍 Input sample (first 10): [${inputSample.map(i => `${i.name}(${i.type}:${i.value})`).join(', ')}]`);

    // First, set the reporting mode radio button if this is indicator data with JSON structure
    if (parsedData && parsedData.mode) {
        const reportingRadios = field.querySelectorAll(`input[type="radio"][name*="repeat_${sectionId}_${actualRepeatNumber}"][name*="_reporting_mode"]`);
        debugLog('repeat-sections', `📻 Found ${reportingRadios.length} reporting mode radio buttons`);

        reportingRadios.forEach(radio => {
            if (radio.value === reportingMode) {
                radio.checked = true;
                debugLog('repeat-sections', `✅ Set reporting mode to "${reportingMode}" for ${radio.name}`);
                radio.dispatchEvent(new Event('change'));
            } else {
                radio.checked = false;
            }
        });
    }

    // Handle different field types
    if (parsedData && parsedData.values) {
        // JSON structured data (indicators with disaggregation)
        debugLog('repeat-sections', `📊 Processing structured data with mode: ${reportingMode}`);

        // Use the shared disaggregation logic instead of hardcoded mappings
        // The disaggregation calculator will handle the field updates automatically
        // when the radio button change event is triggered

        if (reportingMode === 'total' && (parsedData.values.total !== undefined || parsedData.values.direct !== undefined)) {
            // Total mode - find the main value field
            const totalInputs = Array.from(field.querySelectorAll(`input[name*="repeat_${sectionId}_${actualRepeatNumber}"][name*="_total_value"]`))
                .filter(input => (input.type === 'number' || input.dataset.numeric === 'true') && input.type !== 'checkbox' && input.type !== 'radio');
            debugLog('repeat-sections', `🔢 Found ${totalInputs.length} total value inputs`);

            const directValue = parsedData.values.direct !== undefined ? parsedData.values.direct : parsedData.values.total;
            totalInputs.forEach(input => {
                input.value = directValue;
                debugLog('repeat-sections', `✅ Set total/direct value: ${directValue} in ${input.name}`);
                input.dispatchEvent(new Event('change'));
            });

            // Handle indirect reach value for total mode
            if (parsedData.values.indirect !== undefined) {
                const indirectInputs = Array.from(field.querySelectorAll(`input[name*="repeat_${sectionId}_${actualRepeatNumber}"][name*="_indirect_reach"]`))
                    .filter(input => (input.type === 'number' || input.dataset.numeric === 'true') && input.type !== 'checkbox' && input.type !== 'radio');
                debugLog('repeat-sections', `🎯 Found ${indirectInputs.length} indirect reach inputs for total mode`);

                if (indirectInputs.length > 0) {
                    indirectInputs.forEach(input => {
                        input.value = parsedData.values.indirect;
                        debugLog('repeat-sections', `✅ Set indirect reach value (total mode): ${parsedData.values.indirect} in ${input.name}`);
                        input.dispatchEvent(new Event('change'));
                    });
                } else {
                    debugLog('repeat-sections', `⚠️ No indirect reach inputs found for total mode value: ${parsedData.values.indirect}`);
                }
            }

        } else {
            // For disaggregation modes (sex, age, sex_age), let the disaggregation calculator handle the field mapping
            // The radio button change event will trigger the disaggregation calculator to show the correct container
            // and the values will be set in the appropriate disaggregation inputs

            debugLog('repeat-sections', `🔄 Using shared disaggregation logic for ${reportingMode} mode`);

            // Set values for all disaggregation categories that exist in the data
            debugLog('repeat-sections', `🔍 Processing disaggregation data:`, parsedData.values);
            Object.entries(parsedData.values).forEach(([category, value]) => {
                debugLog('repeat-sections', `🎯 Processing category: "${category}" = ${value}`);
                if (value !== undefined && value !== null) {
                    if (category === 'indirect') {
                        // Special handling for indirect reach values
                        const indirectInputs = Array.from(field.querySelectorAll(`input[name*="repeat_${sectionId}_${actualRepeatNumber}"][name*="_indirect_reach"]`))
                            .filter(input => (input.type === 'number' || input.dataset.numeric === 'true') && input.type !== 'checkbox' && input.type !== 'radio');
                        debugLog('repeat-sections', `🎯 Looking for indirect reach inputs: found ${indirectInputs.length}`);

                        if (indirectInputs.length > 0) {
                            indirectInputs.forEach(input => {
                                input.value = value;
                                debugLog('repeat-sections', `✅ Set indirect reach value: ${value} in ${input.name}`);
                                input.dispatchEvent(new Event('change'));
                            });
                        } else {
                            debugLog('repeat-sections', `⚠️ No indirect reach inputs found for value: ${value}`);
                        }
                    } else if (category === 'direct' && typeof value === 'object' && value !== null) {
                        // Special handling for 'direct' when it contains disaggregation breakdown
                        debugLog('repeat-sections', `🔍 Direct value is an object, processing disaggregation breakdown:`, value);

                        Object.entries(value).forEach(([subCategory, subValue]) => {
                            if (subValue !== undefined && subValue !== null) {
                                const subCategorySelector = `input[name*="repeat_${sectionId}_${actualRepeatNumber}"][name*="_${subCategory}"]`;
                                debugLog('repeat-sections', `🔍 Looking for disaggregation "${subCategory}" with selector: ${subCategorySelector}`);

                                const subCategoryInputs = Array.from(field.querySelectorAll(subCategorySelector))
                                    .filter(input => (input.type === 'number' || input.dataset.numeric === 'true') && input.type !== 'checkbox' && input.type !== 'radio');
                                debugLog('repeat-sections', `🎯 Found ${subCategoryInputs.length} inputs for disaggregation "${subCategory}"`);

                                if (subCategoryInputs.length > 0) {
                                    subCategoryInputs.forEach((input, idx) => {
                                        input.value = subValue;
                                        debugLog('repeat-sections', `✅ Set ${subCategory} disaggregation value: ${subValue} in ${input.name} (${idx + 1}/${subCategoryInputs.length})`);
                                        input.dispatchEvent(new Event('change'));
                                    });
                                } else {
                                    debugLog('repeat-sections', `⚠️ No inputs found for disaggregation: "${subCategory}"`);
                                }
                            }
                        });
                    } else {
                        // Find inputs that match this category pattern
                        const categorySelector = `input[name*="repeat_${sectionId}_${actualRepeatNumber}"][name*="_${category}"]`;
                        debugLog('repeat-sections', `🔍 Looking for category "${category}" with selector: ${categorySelector}`);

                        const categoryInputs = Array.from(field.querySelectorAll(categorySelector))
                            .filter(input => (input.type === 'number' || input.dataset.numeric === 'true') && input.type !== 'checkbox' && input.type !== 'radio');
                        debugLog('repeat-sections', `🎯 Found ${categoryInputs.length} inputs for category "${category}"`);

                        if (categoryInputs.length > 0) {
                            categoryInputs.forEach((input, idx) => {
                                input.value = value;
                                debugLog('repeat-sections', `✅ Set ${category} value: ${value} in ${input.name} (${idx + 1}/${categoryInputs.length})`);
                                input.dispatchEvent(new Event('change'));
                            });
                        } else {
                            // Debug: Let's see what inputs are actually available in this field
                            const allNumberInputs = Array.from(field.querySelectorAll(`input[name*="repeat_${sectionId}_${actualRepeatNumber}"]`))
                                .filter(input => (input.type === 'number' || input.dataset.numeric === 'true') && input.type !== 'checkbox' && input.type !== 'radio');
                            debugLog('repeat-sections', `⚠️ No inputs found for category: "${category}"`);
                            debugLog('repeat-sections', `🔍 Available number inputs in this field (first 10):`,
                                Array.from(allNumberInputs).slice(0, 10).map(inp => inp.name)
                            );
                        }
                    }
                }
            });
        }

    } else {
        // Simple value (checkbox, text, select, etc.)
        debugLog('repeat-sections', `📝 Processing simple value: ${valueToSet}`);

        if (valueToSet === 'yes' || valueToSet === 'no') {
            // Yes/No checkbox field
            const checkboxInputs = field.querySelectorAll(`input[type="checkbox"][name*="repeat_${sectionId}_${actualRepeatNumber}"]`);
            debugLog('repeat-sections', `☑️ Found ${checkboxInputs.length} checkbox inputs for yes/no field`);

            checkboxInputs.forEach(input => {
                if ((valueToSet === 'yes' && input.value === 'yes') ||
                    (valueToSet === 'no' && input.value === 'no')) {
                    input.checked = true;
                    debugLog('repeat-sections', `✅ Set checkbox to ${valueToSet} for ${input.name}`);
                    // Don't dispatch change event for checkboxes to avoid missing handler errors
                } else {
                    input.checked = false;
                }
            });

        } else {
            // Check if this is a select field (single choice)
            const selectInputs = field.querySelectorAll(`select[name*="repeat_${sectionId}_${actualRepeatNumber}"]`);
            if (selectInputs.length > 0) {
                debugLog('repeat-sections', `📋 Found ${selectInputs.length} select inputs for single choice field`);
                selectInputs.forEach(select => {
                    const isCalculatedList = select.dataset.optionsSource === 'calculated';
                    const originalValue = select.value;

                    // For calculated lists, we might need to wait for options to load
                    if (isCalculatedList && valueToSet) {
                        debugLog('repeat-sections', `🔄 This is a calculated list, will set value after options load`);

                        // Store the value to set after options are loaded
                        select.dataset.pendingValue = valueToSet;

                        // If options are already loaded, try to set the value now
                        if (select.options.length > 1) { // More than just the placeholder
                            setSelectValueWithFallback(select, valueToSet);
                            delete select.dataset.pendingValue;
                        } else {
                            // Options not loaded yet - try to trigger refresh if available
                            if (window.refreshCalculatedSelect && typeof window.refreshCalculatedSelect === 'function') {
                                debugLog('repeat-sections', `🔄 Triggering calculated list refresh for ${select.id || select.name}`);
                                window.refreshCalculatedSelect(select);
                            }

                            // Poll for options to be loaded (with timeout)
                            let attempts = 0;
                            const maxAttempts = 20; // 2 seconds total (20 * 100ms)
                            const checkInterval = setInterval(() => {
                                attempts++;
                                if (select.options.length > 1) {
                                    // Options are now loaded
                                    clearInterval(checkInterval);
                                    setSelectValueWithFallback(select, valueToSet);
                                    delete select.dataset.pendingValue;
                                    debugLog('repeat-sections', `✅ Options loaded after ${attempts} attempts, value set`);
                                } else if (attempts >= maxAttempts) {
                                    // Timeout - try to set anyway (might work if options are there but not detected)
                                    clearInterval(checkInterval);
                                    setSelectValueWithFallback(select, valueToSet);
                                    delete select.dataset.pendingValue;
                                    debugLog('repeat-sections', `⚠️ Timeout waiting for options, attempted to set value anyway`);
                                }
                            }, 100);
                        }
                    } else {
                        // Regular select - set value directly
                        setSelectValueWithFallback(select, valueToSet);
                    }

                    select.dispatchEvent(new Event('change'));
                });
            } else {
                // First, check if this is a numeric value and look for number inputs
                const isNumericValue = !isNaN(parseFloat(valueToSet)) && isFinite(valueToSet);

                if (isNumericValue) {
                    debugLog('repeat-sections', `🔢 Processing numeric value: ${valueToSet}`);

                    // Look for number inputs with specific patterns first
                    let valueInputs = Array.from(field.querySelectorAll(`input[name*="repeat_${sectionId}_${actualRepeatNumber}"]`)).filter(input =>
                        (input.type === 'number' || input.dataset.numeric === 'true') && input.type !== 'checkbox' && input.type !== 'radio' && (
                            input.name.includes('_total_value') ||
                            input.name.includes('_standard_value') ||
                            input.name.endsWith('_4') ||
                            input.name.match(/field_\d+_\d+$/) // Match pattern like field_0_4, field_1_4, etc.
                        )
                    );

                    // If no specific pattern matches, try to find any number input
                    if (valueInputs.length === 0) {
                        valueInputs = Array.from(field.querySelectorAll(`input[name*="repeat_${sectionId}_${actualRepeatNumber}"]`))
                            .filter(input => (input.type === 'number' || input.dataset.numeric === 'true') && input.type !== 'checkbox' && input.type !== 'radio');
                        debugLog('repeat-sections', `🔍 No specific pattern matches found, using all number inputs: ${valueInputs.length}`);
                    }

                    debugLog('repeat-sections', `🔢 Found ${valueInputs.length} number inputs for numeric field`);
                    debugLog('repeat-sections', `🔍 Input names: [${valueInputs.map(i => i.name).join(', ')}]`);

                    valueInputs.forEach(input => {
                        input.value = valueToSet || '';
                        debugLog('repeat-sections', `✅ Set numeric value: ${valueToSet} in ${input.name}`);
                        input.dispatchEvent(new Event('change'));
                    });

                } else {
                    // Check if this is a multi-choice field (multiple checkboxes with different values)
                    // Only consider checkboxes that are NOT data availability flags
                    const allCheckboxes = field.querySelectorAll(`input[type="checkbox"][name*="repeat_${sectionId}_${actualRepeatNumber}"]`);
                    const multiChoiceCheckboxes = Array.from(allCheckboxes).filter(cb =>
                        !cb.value.match(/^(yes|no)$/) && // Exclude yes/no checkboxes
                        !cb.name.includes('_data_not_available') && // Exclude data availability checkboxes
                        !cb.name.includes('_not_applicable') // Exclude not applicable checkboxes
                    );

                    if (multiChoiceCheckboxes.length > 0) {
                        debugLog('repeat-sections', `☑️ Found ${multiChoiceCheckboxes.length} multi-choice checkbox inputs`);

                        // Parse the saved values (could be JSON array or comma-separated string)
                        let savedValues = [];
                        if (valueToSet) {
                            if (typeof valueToSet === 'string' && valueToSet.startsWith('[')) {
                                try {
                                    savedValues = JSON.parse(valueToSet);
                                } catch (e) {
                                    // If JSON parsing fails, try comma-separated
                                    savedValues = valueToSet.split(',').map(v => v.trim());
                                }
                            } else if (typeof valueToSet === 'string') {
                                // Comma-separated values
                                savedValues = valueToSet.split(',').map(v => v.trim());
                            } else if (Array.isArray(valueToSet)) {
                                savedValues = valueToSet;
                            } else {
                                savedValues = [valueToSet.toString()];
                            }
                        }

                        debugLog('repeat-sections', `📋 Parsed saved values for multi-choice: [${savedValues.join(', ')}]`);

                        // Set checkboxes based on saved values
                        multiChoiceCheckboxes.forEach(checkbox => {
                            const shouldBeChecked = savedValues.includes(checkbox.value);
                            checkbox.checked = shouldBeChecked;
                            debugLog('repeat-sections', `${shouldBeChecked ? '✅' : '⭕'} Set multi-choice checkbox ${checkbox.value} to ${shouldBeChecked} for ${checkbox.name}`);
                        });

                    } else {
                        // Check if this is a matrix field
                        const matrixContainer = field.querySelector('.matrix-container');
                        const looksLikeMatrixObject = matrixContainer && typeof valueToSet === 'object' && valueToSet !== null &&
                            Object.keys(valueToSet).some(key => typeof key === 'string' && !key.startsWith('_') && key.includes('_'));
                        if (looksLikeMatrixObject) {
                            // This is matrix data - set it on the hidden field and trigger matrix restoration
                            debugLog('repeat-sections', `🔷 Detected matrix field with object data - setting on hidden field`);

                            // Find the hidden field (matrix data field) - it's inside the matrix container
                            const hiddenField = matrixContainer.querySelector('input[type="hidden"]');

                            if (hiddenField) {
                                // Convert object to JSON string for the hidden field
                                const matrixPayload = { ...valueToSet };
                                const jsonValue = Object.keys(matrixPayload).length > 0 ? JSON.stringify(matrixPayload) : '';
                                hiddenField.value = jsonValue;
                                debugLog('repeat-sections', `✅ Set matrix data on hidden field ${hiddenField.name}: ${jsonValue.substring(0, 100)}...`);

                                // Get the transformed field ID
                                const transformedFieldId = matrixContainer.getAttribute('data-field-id');

                                // Update the matrix handler's data and restore rows
                                // Use a longer delay to ensure matrix handler has initialized
                                const restoreMatrixData = () => {
                                    if (window.matrixHandler) {
                                        debugLog('repeat-sections', `🔄 Updating matrix handler data for ${transformedFieldId}`);

                                        // Update the matrix data in the handler
                                        if (window.matrixHandler.matrices && window.matrixHandler.matrices.has(transformedFieldId)) {
                                            const matrix = window.matrixHandler.matrices.get(transformedFieldId);
                                            matrix.data = matrixPayload;

                                            // Restore the rows
                                            if (window.matrixHandler.restoreDynamicRows) {
                                                debugLog('repeat-sections', `🔄 Restoring dynamic rows for ${transformedFieldId}`);
                                                window.matrixHandler.restoreDynamicRows(transformedFieldId).then(() => {
                                                    debugLog('repeat-sections', `✅ Matrix rows restored for ${transformedFieldId}`);
                                                }).catch(err => {
                                                    debugWarn('repeat-sections', `❌ Error restoring matrix rows: ${err}`);
                                                });
                                            }
                                        } else {
                                            debugWarn('repeat-sections', `⚠️ Matrix not found in handler for ${transformedFieldId}, will retry...`);
                                            // Retry after a bit if matrix handler hasn't initialized yet
                                            setTimeout(restoreMatrixData, 300);
                                        }
                                    } else {
                                        debugWarn('repeat-sections', `⚠️ Matrix handler not available yet, will retry...`);
                                        setTimeout(restoreMatrixData, 300);
                                    }
                                };

                                // Initial delay to allow matrix handler to initialize
                                setTimeout(restoreMatrixData, 500);
                            } else {
                                debugWarn('repeat-sections', `❌ Matrix field detected but hidden field not found in container`);
                            }
                        } else {
                            // Regular text/select field - look for main value input
                            let valueInputs = Array.from(field.querySelectorAll(`input[name*="repeat_${sectionId}_${actualRepeatNumber}"]`)).filter(input =>
                                input.type === 'text' || input.type === 'hidden'
                            );

                            // Also check for select elements
                            const selectInputs = field.querySelectorAll(`select[name*="repeat_${sectionId}_${actualRepeatNumber}"]`);
                            valueInputs = valueInputs.concat(Array.from(selectInputs));

                            debugLog('repeat-sections', `📝 Found ${valueInputs.length} text/select inputs for simple field`);
                            debugLog('repeat-sections', `🔍 Input names: [${valueInputs.map(i => i.name).join(', ')}]`);

                            valueInputs.forEach(input => {
                                // Convert object to JSON string if needed
                                const valueToSetStr = (typeof valueToSet === 'object' && valueToSet !== null)
                                    ? JSON.stringify(valueToSet)
                                    : (valueToSet || '');
                                input.value = valueToSetStr;
                                debugLog('repeat-sections', `✅ Set text/select value: ${valueToSetStr} in ${input.name}`);
                                input.dispatchEvent(new Event('change'));
                            });
                        }
                    }
                }
            }
        }
    }

    // Handle data availability flags
    if (dataNotAvailable || notApplicable) {
        debugLog('repeat-sections', `📋 Setting data availability flags: dataNotAvailable=${dataNotAvailable}, notApplicable=${notApplicable}`);

        const dataNotAvailableCheckbox = field.querySelector(`input[name*="repeat_${sectionId}_${actualRepeatNumber}"][name*="_data_not_available"]`);
        const notApplicableCheckbox = field.querySelector(`input[name*="repeat_${sectionId}_${actualRepeatNumber}"][name*="_not_applicable"]`);

        if (dataNotAvailableCheckbox) {
            dataNotAvailableCheckbox.checked = dataNotAvailable;
            debugLog('repeat-sections', `✅ Set data not available checkbox: ${dataNotAvailable} for ${dataNotAvailableCheckbox.name}`);
        }

        if (notApplicableCheckbox) {
            notApplicableCheckbox.checked = notApplicable;
            debugLog('repeat-sections', `✅ Set not applicable checkbox: ${notApplicable} for ${notApplicableCheckbox.name}`);
        }

        // Trigger data availability logic to disable/enable fields as needed
        if (dataNotAvailable || notApplicable) {
            debugLog('repeat-sections', `🚫 Data availability flags are set - field should be disabled`);
            // The data-availability module should handle this via event delegation
        }
    }

    debugLog('repeat-sections', `🎉 Completed loading field ${fieldId} with ${reportingMode} mode`);
}

function reinitializeFormFeatures(repeatEntry) {
    debugLog('repeat-sections', '🔄 Reinitializing form features for repeat entry...');

    // 1. Setup number input formatting for new inputs
    const numberInputs = repeatEntry.querySelectorAll('input[type="number"]');
    debugLog('repeat-sections', `Found ${numberInputs.length} number inputs to format`);
    numberInputs.forEach(input => {
        setupNumberInputFormatting(input);
    });

    // 2. Add disaggregation calculator listeners specifically to this repeat entry
    if (window.addListenersToRepeatEntry) {
        debugLog('repeat-sections', `Adding disaggregation calculator listeners to repeat entry: ${repeatEntry.id}`);
        window.addListenersToRepeatEntry(repeatEntry);
    } else {
        // Fallback to full reinitialize if the specific method isn't available
        if (window.reinitializeDisaggregationCalculator) {
            debugLog('repeat-sections', 'Falling back to full disaggregation calculator reinitialize');
            window.reinitializeDisaggregationCalculator();
        }
    }

    // 3. Reinitialize matrix handlers for any matrices in this repeat entry
    const matrixContainers = repeatEntry.querySelectorAll('.matrix-container');
    if (matrixContainers.length > 0 && window.matrixHandler) {
        debugLog('repeat-sections', `🔷 Found ${matrixContainers.length} matrix containers, reinitializing...`);

        matrixContainers.forEach(container => {
            const fieldId = container.getAttribute('data-field-id');
            if (fieldId) {
                // Reinitialize this matrix after a delay to ensure DOM is ready
                setTimeout(() => {
                    if (window.matrixHandler) {
                        debugLog('repeat-sections', `🔄 Reinitializing matrix ${fieldId}`);

                        // Remove old matrix entry if it exists (might be from previous instance)
                        if (window.matrixHandler.matrices && window.matrixHandler.matrices.has(fieldId)) {
                            window.matrixHandler.matrices.delete(fieldId);
                            debugLog('repeat-sections', `🗑️ Removed old matrix entry for ${fieldId}`);
                        }

                        // Fully reinitialize all matrices (this will pick up the new container)
                        if (window.matrixHandler.initializeMatrices) {
                            window.matrixHandler.initializeMatrices();
                            debugLog('repeat-sections', `✅ Reinitialized all matrices (including ${fieldId})`);
                        }
                    }
                }, 300);
            }
        });
    }

    // 4. Dispatch custom event to notify other modules to reinitialize their features
    const event = new CustomEvent('repeatEntryAdded', {
        detail: {
            container: repeatEntry,
            action: 'initialize'
        }
    });
    document.dispatchEvent(event);

    // 5. Since checkbox handlers and data availability use event delegation,
    // they should automatically work for dynamically added elements
    // The event we dispatched above will let other modules handle their own reinitialization

    debugLog('repeat-sections', '✅ Form features reinitialized for repeat entry');
}

// Note: Multi-select, disaggregation, and data availability features are handled
// by their respective modules using event delegation and the 'repeatEntryAdded' event.
// Data availability handling is now unified with standard sections for consistency.
// Disaggregation logic is now shared with the main disaggregation calculator module.

// Export functions that might be needed by other modules
export {
    setupRepeatSections,
    loadExistingRepeatData,
    addRepeatEntry,
    updateRepeatLimitText,
    debugLog,
    debugWarn,
    debugError
};

// Add form submission validation to ensure yes/no data is sent
function validateYesNoDataOnSubmit() {
    const form = document.querySelector('form');
    if (!form) return;

    // Add event listener for form submission
    form.addEventListener('submit', function(e) {
        debugLog('repeat-sections', '🚀 Form submission - validating yes/no checkbox data...');

        // Find all yes/no checkboxes in repeat sections
        const yesNoCheckboxes = document.querySelectorAll('input[type="checkbox"][name*="repeat_"][name*="_standard_value"]');
        const checkedYesNoData = {};
        const expectedFormData = {};

        yesNoCheckboxes.forEach(checkbox => {
            if (checkbox.checked) {
                checkedYesNoData[checkbox.name] = checkbox.value;
                expectedFormData[checkbox.name] = checkbox.value;
            }
        });

        // Verify that the form data will include our expected data
        const formData = new FormData(form);
        const actualFormData = {};

        for (const [name, value] of formData.entries()) {
            if (name.includes('repeat_') && name.includes('_standard_value')) {
                actualFormData[name] = value;
            }
        }

        // Compare expected vs actual
        const missingData = {};
        for (const [name, value] of Object.entries(expectedFormData)) {
            if (!actualFormData.hasOwnProperty(name) || actualFormData[name] !== value) {
                missingData[name] = value;
            }
        }

        if (Object.keys(missingData).length > 0) {
            debugError('repeat-sections', '❌ MISSING YES/NO DATA IN FORM SUBMISSION:', missingData);
            debugLog('repeat-sections', 'Expected:', expectedFormData);
            debugLog('repeat-sections', 'Actual:', actualFormData);

            // Add missing data to form by creating hidden inputs
            for (const [name, value] of Object.entries(missingData)) {
                const hiddenInput = document.createElement('input');
                hiddenInput.type = 'hidden';
                hiddenInput.name = name;
                hiddenInput.value = value;
                form.appendChild(hiddenInput);
                debugLog('repeat-sections', `✅ Added missing yes/no data: ${name}=${value}`);
            }
        } else {
            debugLog('repeat-sections', '✅ All yes/no checkbox data is properly included in form submission');
            debugLog('repeat-sections', 'Yes/No data being sent:', actualFormData);
        }
    });
}

// Initialize the validation
validateYesNoDataOnSubmit();
