// Rule Builder Module
import { DataManager } from './data-manager.js';
// Utils is available globally from utils.js

// Mapping of condition types based on item input types – ported from the legacy builder
const conditionTypesMap = {
    'Number': [
        {value: 'equal_to', label: 'Equal to'},
        {value: 'not_equal_to', label: 'Not equal to'},
        {value: 'greater_than', label: 'Greater than (>)'},
        {value: 'greater_than_or_equal_to', label: 'Greater than or equal to (>=)'},
        {value: 'less_than', label: 'Less than (<)'},
        {value: 'less_than_or_equal_to', label: 'Less than or equal to (<=)'},
        {value: 'is_empty', label: 'Is empty'},
        {value: 'is_not_empty', label: 'Is not empty'}
    ],
    'text': [
        {value: 'equal_to', label: 'Equal to'},
        {value: 'not_equal_to', label: 'Not equal to'},
        {value: 'contains', label: 'Contains'},
        {value: 'not_contains', label: 'Does not contain'},
        {value: 'starts_with', label: 'Starts with'},
        {value: 'ends_with', label: 'Ends with'},
        {value: 'is_empty', label: 'Is empty'},
        {value: 'is_not_empty', label: 'Is not empty'}
    ],
    'textarea': [
        {value: 'equal_to', label: 'Equal to'},
        {value: 'not_equal_to', label: 'Not equal to'},
        {value: 'contains', label: 'Contains'},
        {value: 'not_contains', label: 'Does not contain'},
        {value: 'is_empty', label: 'Is empty'},
        {value: 'is_not_empty', label: 'Is not empty'}
    ],
    'yesno': [
        {value: 'is_yes', label: 'Is Yes'},
        {value: 'is_no', label: 'Is No'},
        {value: 'is_empty', label: 'Is empty (no answer)'},
        {value: 'is_not_empty', label: 'Is answered'}
    ],
    'single_choice': [
        {value: 'equal_to', label: 'Is'},
        {value: 'not_equal_to', label: 'Is not'},
        {value: 'is_empty', label: 'Is empty'},
        {value: 'is_not_empty', label: 'Is not empty'}
    ],
    'multiple_choice': [
        {value: 'contains', label: 'Contains'},
        {value: 'not_contains', label: 'Does not contain'},
        {value: 'is_empty', label: 'Is empty'},
        {value: 'is_not_empty', label: 'Is not empty'}
    ],
    'date': [
        {value: 'equal_to', label: 'Is'},
        {value: 'not_equal_to', label: 'Is not'},
        {value: 'greater_than', label: 'Is after'},
        {value: 'greater_than_or_equal_to', label: 'Is on or after'},
        {value: 'less_than', label: 'Is before'},
        {value: 'less_than_or_equal_to', label: 'Is on or before'},
        {value: 'is_empty', label: 'Is empty'},
        {value: 'is_not_empty', label: 'Is not empty'}
    ],
    'datetime': [
        {value: 'equal_to', label: 'Is'},
        {value: 'not_equal_to', label: 'Is not'},
        {value: 'greater_than', label: 'Is after'},
        {value: 'greater_than_or_equal_to', label: 'Is on or after'},
        {value: 'less_than', label: 'Is before'},
        {value: 'less_than_or_equal_to', label: 'Is on or before'},
        {value: 'is_empty', label: 'Is empty'},
        {value: 'is_not_empty', label: 'Is not empty'}
    ],
    'document': [
        {value: 'is_empty', label: 'Is empty (No document uploaded)'},
        {value: 'is_not_empty', label: 'Is not empty (Document uploaded)'}
    ]
};

// Built-in metadata tokens (available globally from form_builder.html)
function getBuiltInMetadataOptions() {
    const metadata = Array.isArray(window.builtInMetadataVariables) ? window.builtInMetadataVariables : [];
    // Map metadata keys to a simple type so the rule builder can choose condition operators.
    const typeByKey = {
        entity_id: 'Number',
        entity_name: 'text',
        entity_name_hierarchy: 'text',
        entity_type: 'text',
        template_name: 'text',
        assignment_period: 'text'
    };
    return metadata
        .map(m => {
            const key = String(m?.key || '').trim();
            if (!key) return null;
            return {
                key,
                label: String(m?.label || key),
                valueType: typeByKey[key] || 'text'
            };
        })
        .filter(Boolean);
}

/**
 * Resolve a template item (from allTemplateItems) by any id representation.
 *
 * Saved rules commonly store numeric IDs (e.g. "66"), while the in-page
 * `allTemplateItems` list uses prefixed string IDs (e.g. "question_66") AND
 * also exposes `item_id_raw` as the numeric primary key. We should prefer
 * matching on `item_id_raw` when possible to avoid "Unknown Item".
 */
function findTemplateItemByAnyId(allItems, idLike) {
    if (!Array.isArray(allItems) || allItems.length === 0) return null;
    if (idLike === null || idLike === undefined) return null;

    const raw = String(idLike).trim();
    if (!raw) return null;

    // 1) Exact match on the stored id (already prefixed, e.g. "question_66")
    let item = allItems.find(i => i && i.id !== undefined && String(i.id) === raw);
    if (item) return item;

    // 2) Numeric match on item_id_raw (preferred for DB-saved rules)
    const asInt = parseInt(raw, 10);
    if (!Number.isNaN(asInt)) {
        item = allItems.find(i => {
            if (!i) return false;
            const v = i.item_id_raw;
            if (v === null || v === undefined) return false;
            const n = parseInt(String(v), 10);
            return !Number.isNaN(n) && n === asInt;
        });
        if (item) return item;

        // 3) Numeric match by extracting the trailing numeric segment from id
        item = allItems.find(i => {
            const s = i && i.id !== undefined ? String(i.id) : '';
            const m = s.match(/_(\d+)$/);
            return m && parseInt(m[1], 10) === asInt;
        });
        if (item) return item;
    }

    return null;
}

export const RuleBuilder = {
    // Initialize rule displays in the template list
    initializeRuleDisplays() {
        const ruleElements = document.querySelectorAll('.rule-display');
        ruleElements.forEach((element) => {
            const ruleJson = element.getAttribute('data-rule-json');
            const ruleType = element.getAttribute('data-rule-type');

            if (ruleJson && ruleJson !== 'null' && ruleJson !== '{}' && ruleJson.trim() !== '') {
                try {
                    const humanText = this.parseRuleToText(ruleJson, ruleType);
                    element.textContent = humanText;
                    element.title = ruleJson;
                } catch (error) {
                    element.textContent = 'Error parsing rule';
                }
            } else {
                element.textContent = 'No rule defined';
            }
        });
    },

    // Parse rule JSON to human-readable text
    parseRuleToText(ruleJson, ruleType) {
        try {
            const rule = typeof ruleJson === 'string' ? JSON.parse(ruleJson) : ruleJson;

            if (!rule || !rule.conditions || rule.conditions.length === 0) {
                return 'No conditions defined';
            }

            const conditions = rule.conditions.map(condition => {
                const allItems = DataManager.getData('allTemplateItems') || [];
                const metadataOptions = getBuiltInMetadataOptions();

                // Handle both numeric IDs and prefixed IDs
                let item = null;
                let measureName = '';

                // Built-in metadata condition
                if (condition.item_id && typeof condition.item_id === 'string') {
                    const meta = metadataOptions.find(m => m.key === condition.item_id);
                    if (meta) {
                        let conditionText = '';
                        let valueDisplay = '';
                        if (condition.value_field_id !== null && condition.value_field_id !== undefined) {
                            valueDisplay = `field ID ${condition.value_field_id}`;
                        } else if (condition.value !== null && condition.value !== undefined) {
                            valueDisplay = `"${condition.value}"`;
                        }

                        switch (condition.condition_type) {
                            case 'is_empty':
                                conditionText = 'is empty';
                                break;
                            case 'is_not_empty':
                                conditionText = 'is not empty';
                                break;
                            case 'equals':
                            case 'equal_to':
                                conditionText = `equals ${valueDisplay}`;
                                break;
                            case 'not_equals':
                            case 'not_equal_to':
                                conditionText = `does not equal ${valueDisplay}`;
                                break;
                            case 'greater_than':
                                conditionText = `is greater than ${valueDisplay}`;
                                break;
                            case 'greater_than_or_equal_to':
                                conditionText = `is greater than or equal to ${valueDisplay}`;
                                break;
                            case 'less_than':
                                conditionText = `is less than ${valueDisplay}`;
                                break;
                            case 'less_than_or_equal_to':
                                conditionText = `is less than or equal to ${valueDisplay}`;
                                break;
                            case 'contains':
                                conditionText = `contains ${valueDisplay}`;
                                break;
                            case 'not_contains':
                                conditionText = `does not contain ${valueDisplay}`;
                                break;
                            default:
                                conditionText = `${condition.condition_type} ${valueDisplay}`;
                        }

                        return `Metadata: ${meta.label} ${conditionText}`;
                    }
                }

                if (condition.item_id && typeof condition.item_id === 'string' && condition.item_id.startsWith('plugin_')) {
                    // Plugin item ids can be:
                    // - "plugin_123" (base plugin item)
                    // - "plugin_123_measure_id" (a plugin measure)
                    const parts = condition.item_id.split('_');
                    if (parts.length >= 3) {
                        // Treat as plugin measure: base id = "plugin_123"
                        const baseFieldId = parts.slice(0, 2).join('_');
                        item = findTemplateItemByAnyId(allItems, baseFieldId);

                        const measureId = parts.slice(2).join('_');
                        if (item && item.plugin_measures) {
                            const measure = item.plugin_measures.find(m => m.id === measureId);
                            measureName = measure ? measure.name : measureId;
                        }
                    } else {
                        // Base plugin item: resolve as-is
                        item = findTemplateItemByAnyId(allItems, condition.item_id);
                    }
                } else {
                    // Numeric IDs (common) or already-prefixed IDs: resolve via helper
                    item = findTemplateItemByAnyId(allItems, condition.item_id);
                }

                let itemLabel = 'Unknown Item';
                if (item) {
                    itemLabel = item.label;
                    if (measureName) {
                        itemLabel = `${itemLabel} (${measureName})`;
                    }
                }

                let conditionText = '';
                // Check if using field reference or static value
                let valueDisplay = '';
                if (condition.value_field_id !== null && condition.value_field_id !== undefined) {
                    // Find the referenced field
                    const refItem = findTemplateItemByAnyId(allItems, condition.value_field_id);
                    if (refItem) {
                        valueDisplay = `field "${refItem.label}"`;
                    } else {
                        valueDisplay = `field ID ${condition.value_field_id}`;
                    }
                } else if (condition.value !== null && condition.value !== undefined) {
                    valueDisplay = `"${condition.value}"`;
                }

                switch (condition.condition_type) {
                    case 'is_empty':
                        conditionText = 'is empty';
                        break;
                    case 'is_not_empty':
                        conditionText = 'is not empty';
                        break;
                    case 'equals':
                    case 'equal_to':
                        conditionText = `equals ${valueDisplay}`;
                        break;
                    case 'not_equals':
                    case 'not_equal_to':
                        conditionText = `does not equal ${valueDisplay}`;
                        break;
                    case 'greater_than':
                        conditionText = `is greater than ${valueDisplay}`;
                        break;
                    case 'greater_than_or_equal_to':
                        conditionText = `is greater than or equal to ${valueDisplay}`;
                        break;
                    case 'less_than':
                        conditionText = `is less than ${valueDisplay}`;
                        break;
                    case 'less_than_or_equal_to':
                        conditionText = `is less than or equal to ${valueDisplay}`;
                        break;
                    case 'contains':
                        conditionText = `contains ${valueDisplay}`;
                        break;
                    case 'not_contains':
                        conditionText = `does not contain ${valueDisplay}`;
                        break;
                    default:
                        conditionText = `${condition.condition_type} ${valueDisplay}`;
                }

                return `${itemLabel} ${conditionText}`;
            });

            const logic = rule.logic || 'AND';
            return conditions.join(` ${logic} `);
        } catch (error) {
            return 'Invalid rule format';
        }
    },

    // Render rule builder UI
    renderRuleBuilder(containerElement, ruleJson, ruleType, currentItemId = null) {
        if (!containerElement) {
            return;
        }

        // Add CSS for dropdown styling
        if (!document.getElementById('rule-builder-dropdown-styles')) {
            const style = document.createElement('style');
            style.id = 'rule-builder-dropdown-styles';
            style.textContent = `
                .rule-item-select option {
                    white-space: normal;
                    word-wrap: break-word;
                    padding: 8px;
                    line-height: 1.4;
                }
                .rule-item-select {
                    max-width: 300px !important;
                }
                .rule-item-select option[data-is-current-item="true"] {
                    font-style: italic;
                    background-color: #f0f9ff;
                }
            `;
            document.head.appendChild(style);
        }

        containerElement.replaceChildren();
        const root = document.createElement('div');
        root.className = 'space-y-4';

        const logicRow = document.createElement('div');
        logicRow.className = 'flex items-center space-x-2';
        const logicLabel = document.createElement('label');
        logicLabel.className = 'text-sm font-medium text-gray-700';
        logicLabel.textContent = 'Logic:';
        const logicSelect = document.createElement('select');
        logicSelect.className = 'form-select text-sm border-gray-300 rounded-md rule-logic-select';
        ['AND', 'OR'].forEach((v) => {
            const opt = document.createElement('option');
            opt.value = v;
            opt.textContent = v;
            logicSelect.appendChild(opt);
        });
        logicRow.append(logicLabel, logicSelect);

        const conditionsContainer = document.createElement('div');
        conditionsContainer.className = 'rule-conditions-container';

        const addConditionBtn = document.createElement('button');
        addConditionBtn.type = 'button';
        addConditionBtn.className =
            'inline-flex items-center px-3 py-1 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 add-condition-btn';
        {
            const icon = document.createElement('i');
            icon.className = 'fas fa-plus w-3 h-3 mr-1';
            addConditionBtn.append(icon, document.createTextNode(' Add Condition'));
        }

        root.append(logicRow, conditionsContainer, addConditionBtn);
        containerElement.appendChild(root);

        // Initialize with existing rule data if provided
        if (ruleJson) {
            try {
                let rule;
                if (typeof ruleJson === 'string') {
                    try {
                        rule = JSON.parse(ruleJson);

                        // Check if the result is still a string (double-encoded JSON)
                        if (typeof rule === 'string') {
                            try {
                                rule = JSON.parse(rule);
                            } catch (secondParseError) {
                                // If it's still a string and not valid JSON, treat it as a malformed rule
                                rule = null;
                            }
                        }
                    } catch (parseError) {
                        rule = null; // Set to null instead of fallback to string
                    }
                } else {
                    rule = ruleJson;
                }

                // Only proceed if we have a valid rule object
                if (rule && typeof rule === 'object' && rule !== null) {
                    if (rule.logic) {
                        logicSelect.value = rule.logic;
                    }

                    if (rule.conditions && rule.conditions.length > 0) {
                        rule.conditions.forEach((condition, index) => {
                            this.addConditionLine(conditionsContainer, ruleType, condition, currentItemId);
                        });
                    }
                }
            } catch (error) {
                // Silently handle parsing errors
            }
        }

        // Add event listeners
        addConditionBtn.addEventListener('click', () => {
            this.addConditionLine(conditionsContainer, ruleType, null, currentItemId);
        });
    },

    // Add a new condition line to the rule builder
    addConditionLine(conditionsContainer, ruleType, conditionData = null, currentItemId = null) {
        if (!conditionsContainer) {
            return;
        }

        const conditionDiv = document.createElement('div');
        conditionDiv.className = 'flex items-center space-x-2 mb-2 condition-line';
        const itemSelect = document.createElement('select');
        itemSelect.className = 'form-select block w-1/3 text-sm border-gray-300 rounded-md rule-item-select';
        itemSelect.style.maxWidth = '300px';
        {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'Select Item...';
            itemSelect.appendChild(opt);
        }

        const conditionTypeSelect = document.createElement('select');
        conditionTypeSelect.className = 'form-select block w-1/4 text-sm border-gray-300 rounded-md rule-condition-type-select';
        {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'Select Condition...';
            conditionTypeSelect.appendChild(opt);
        }

        const valueContainer = document.createElement('div');
        valueContainer.className = 'w-1/3 rule-value-container';
        const valueInput = document.createElement('input');
        valueInput.type = 'text';
        valueInput.className = 'form-input block w-full text-sm border-gray-300 rounded-md rule-value-input';
        valueInput.placeholder = 'Value';
        valueContainer.appendChild(valueInput);

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'text-red-600 hover:text-red-800 remove-condition-btn';
        {
            const icon = document.createElement('i');
            icon.className = 'fas fa-times-circle w-5 h-5';
            removeBtn.appendChild(icon);
        }

        conditionDiv.append(itemSelect, conditionTypeSelect, valueContainer, removeBtn);

        conditionsContainer.appendChild(conditionDiv);

        // Add event listeners
        removeBtn.addEventListener('click', () => {
            conditionDiv.remove();
        });

        // Populate item select and set up change handlers
        this.populateItemSelect(itemSelect, ruleType, currentItemId);

        // Set up change handlers
        itemSelect.addEventListener('change', () => {
            this.updateConditionTypeSelect(conditionTypeSelect, valueContainer, itemSelect.value, ruleType);
        });

        conditionTypeSelect.addEventListener('change', () => {
            this.updateValueInput(valueContainer, itemSelect.value, conditionTypeSelect.value, null, null, currentItemId);
        });

        // Populate with existing data if provided
        if (conditionData) {
            let itemIdForDropdown = conditionData.item_id || '';
            let foundMatch = false;

            // First, try to set the value directly (in case it's already in the correct format)
            if (itemIdForDropdown) {
                itemSelect.value = itemIdForDropdown;
                if (itemSelect.value === itemIdForDropdown) {
                    foundMatch = true;
                }
            }

            // If direct match failed and it's a numeric ID, try to find the prefixed option
            if (!foundMatch && itemIdForDropdown && !isNaN(itemIdForDropdown)) {
                const options = itemSelect.querySelectorAll('option');
                for (const option of options) {
                    if (option.value && option.value.includes(`_${itemIdForDropdown}`)) {
                        itemSelect.value = option.value;
                        foundMatch = true;
                        break;
                    }
                }
            }

            // If we found a match, update the dependent fields
            if (foundMatch && itemSelect.value) {
                this.updateConditionTypeSelect(conditionTypeSelect, valueContainer, itemSelect.value, ruleType);

                // Set condition type after a brief delay to ensure the dropdown is populated
                setTimeout(() => {
                    if (conditionData.condition_type) {
                        conditionTypeSelect.value = conditionData.condition_type;

                        // Always update the value input, regardless of whether there's a value
                        // This ensures no-value conditions are handled properly
                        // Check if this condition uses a field reference (value_field_id) or static value
                        const valueFieldId = conditionData.value_field_id !== null && conditionData.value_field_id !== undefined
                            ? conditionData.value_field_id
                            : null;
                        this.updateValueInput(valueContainer, itemSelect.value, conditionData.condition_type, conditionData.value, valueFieldId, currentItemId);
                    }
                }, 50);
            }
        }
    },

    // Populate item select dropdown
    populateItemSelect(selectElement, ruleType, currentItemId = null) {
        const allItems = DataManager.getData('allTemplateItems') || [];
        const metadataOptions = getBuiltInMetadataOptions();

        // Clear existing options
        selectElement.replaceChildren();
        {
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select Item...';
            selectElement.appendChild(placeholder);
        }

        // Add Metadata group first
        if (metadataOptions.length > 0) {
            const og = document.createElement('optgroup');
            og.label = 'Metadata';
            metadataOptions.forEach(meta => {
                const opt = document.createElement('option');
                opt.value = meta.key; // store as token key (e.g. "entity_name")
                opt.textContent = `${meta.label}`;
                opt.dataset.itemType = meta.valueType;
                opt.dataset.itemModel = 'metadata';
                og.appendChild(opt);
            });
            selectElement.appendChild(og);
        }

        // Get items to use (either original or reloaded)
        let itemsToUse = allItems;

        // If no items are available, try to force reload the data
        if (allItems.length === 0) {
            DataManager.loadAllTemplateItems();
            const reloadedItems = DataManager.getData('allTemplateItems') || [];
            if (reloadedItems.length > 0) {
                itemsToUse = reloadedItems;
            }
        }

        // Helper function to create an option element
        const createOption = (item, isCurrentItem = false) => {
            if (item.item_model !== 'plugin') {
                const option = document.createElement('option');
                option.value = item.id;

                // Extract the numeric ID from the prefixed format for display
                let displayId = item.id;
                const match = item.id.match(/^(question_|indicator_|document_field_|matrix_|form_item_)(\d+)$/);
                if (match) {
                    displayId = match[2]; // Use just the numeric part
                }

                // Handle item type display - use item_model as fallback for document fields
                let displayType = item.type || item.item_model || 'Unknown';
                if (displayType === 'null' || displayType === null) {
                    // For document fields, use a more descriptive type
                    if (item.id && item.id.startsWith('document_field_')) {
                        displayType = 'Document';
                    } else if (item.id && item.id.startsWith('question_')) {
                        displayType = 'Question';
                    } else if (item.id && item.id.startsWith('indicator_')) {
                        displayType = 'Indicator';
                    } else if (item.id && item.id.startsWith('matrix_')) {
                        displayType = 'Matrix';
                    } else if (item.id && item.id.startsWith('form_item_')) {
                        // For form_item_ prefix, try to infer type from item.type or use a generic name
                        displayType = item.type || 'Item';
                    } else {
                        displayType = 'Item';
                    }
                }

                // Override specific item_model values for better display
                if (displayType === 'document_field' || displayType === 'Document Field') {
                    displayType = 'Document';
                } else if (displayType === 'question' || displayType === 'Question') {
                    displayType = 'Question';
                } else if (displayType === 'indicator' || displayType === 'Indicator') {
                    displayType = 'Indicator';
                } else if (displayType === 'matrix' || displayType === 'Matrix') {
                    displayType = 'Matrix';
                } else if (displayType === 'form_item') {
                    // For form_item model, use the actual type if available, otherwise use a generic name
                    displayType = item.type || 'Item';
                }

                // Format: "ID: Type: Label" (e.g., "66: Question: If answered yes...")
                // Truncate very long labels to prevent dropdown from being too wide
                let displayLabel = item.label;
                if (displayLabel.length > 80) {
                    displayLabel = displayLabel.substring(0, 77) + '...';
                }

                let textContent = `${displayId}: ${displayType}: ${displayLabel}`;
                if (isCurrentItem) {
                    // Add "(Current item)" in italic style indicator
                    textContent = `→ ${textContent} (Current item)`;
                    option.style.fontStyle = 'italic';
                    option.dataset.isCurrentItem = 'true';
                }

                option.textContent = textContent;
                option.dataset.itemType = item.type || item.item_model || '';
                option.dataset.itemModel = item.item_model || item.model || '';
                option.title = `${displayId}: ${displayType}: ${item.label}${isCurrentItem ? ' (Current item)' : ''}`;
                return option;
            } else {
                // Handle plugin items and their measures
                const pluginType = item.plugin_type || 'unknown';
                const measures = item.plugin_measures || [];
                const options = [];

                // Add the main plugin item
                const pluginOption = document.createElement('option');
                pluginOption.value = item.id;
                const displayPluginType = pluginType.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
                let pluginText = `${item.id.replace('plugin_', '')}: Plugin (${displayPluginType}): ${item.label}`;
                if (isCurrentItem) {
                    pluginText = `→ ${pluginText} (Current item)`;
                    pluginOption.style.fontStyle = 'italic';
                    pluginOption.dataset.isCurrentItem = 'true';
                }
                pluginOption.textContent = pluginText;
                pluginOption.dataset.itemType = 'plugin';
                pluginOption.dataset.itemModel = 'plugin';
                pluginOption.dataset.pluginType = pluginType;
                pluginOption.title = `${item.id.replace('plugin_', '')}: Plugin (${displayPluginType}): ${item.label}${isCurrentItem ? ' (Current item)' : ''}`;
                options.push(pluginOption);

                // Add each measure as a separate option
                measures.forEach(measure => {
                    const measureOption = document.createElement('option');
                    measureOption.value = `${item.id}_${measure.id}`;
                    let measureText = `${item.id.replace('plugin_', '')}: ${measure.name}: ${item.label}`;
                    if (isCurrentItem) {
                        measureText = `→ ${measureText} (Current item)`;
                        measureOption.style.fontWeight = 'bold';
                        measureOption.style.fontStyle = 'italic';
                        measureOption.dataset.isCurrentItem = 'true';
                    }
                    measureOption.textContent = measureText;
                    measureOption.dataset.itemType = 'plugin_measure';
                    measureOption.dataset.itemModel = 'plugin_measure';
                    measureOption.dataset.pluginType = pluginType;
                    measureOption.dataset.measureId = measure.id;
                    measureOption.dataset.dataAttribute = measure.data_attribute;
                    measureOption.dataset.valueType = measure.value_type;
                    measureOption.title = `${item.id.replace('plugin_', '')}: ${measure.name}: ${measure.description}${isCurrentItem ? ' (Current item)' : ''}`;
                    options.push(measureOption);
                });

                return options;
            }
        };

        // Separate current item from others
        const currentItem = currentItemId ? itemsToUse.find(item => item.id === currentItemId) : null;
        const otherItems = itemsToUse.filter(item => !currentItemId || item.id !== currentItemId);

        // Add current item first if it exists
        if (currentItem) {
            const currentOptions = createOption(currentItem, true);
            const optionsArray = Array.isArray(currentOptions) ? currentOptions : [currentOptions];
            optionsArray.forEach(opt => {
                selectElement.appendChild(opt);
            });
        }

        // Add all other items
        otherItems.forEach(item => {
            const options = createOption(item, false);
            if (Array.isArray(options)) {
                options.forEach(opt => selectElement.appendChild(opt));
            } else {
                selectElement.appendChild(options);
            }
        });
    },

    // Update condition type select based on selected item
    updateConditionTypeSelect(selectElement, valueContainer, selectedItemId, ruleType) {
        if (!selectElement) return;

        // Retrieve meta info from the selected option
        const selectedOption = selectElement.closest('div.condition-line')?.querySelector(`.rule-item-select option[value="${selectedItemId}"]`);
        const itemType = selectedOption?.dataset.itemType;
        const itemModel = selectedOption?.dataset.itemModel;

        let applicableConditionTypes = [];

        if (itemModel === 'metadata') {
            // Metadata tokens behave like simple text/number values
            if (itemType === 'Number') {
                applicableConditionTypes = conditionTypesMap['Number'];
            } else {
                applicableConditionTypes = conditionTypesMap['text'];
            }
        } else if (itemModel === 'indicator') {
            switch (itemType) {
                case 'yesno':
                case 'YesNo':
                case 'yes_no':
                    applicableConditionTypes = conditionTypesMap['yesno'];
                    break;
                case 'text':
                    applicableConditionTypes = conditionTypesMap['text'];
                    break;
                case 'date':
                    applicableConditionTypes = conditionTypesMap['date'];
                    break;
                default:
                    applicableConditionTypes = conditionTypesMap['Number'];
            }
        } else if (itemModel === 'question') {
            switch (itemType) {
                case 'number':
                    applicableConditionTypes = conditionTypesMap['Number'];
                    break;
                case 'yesno':
                case 'YesNo':
                case 'yes_no':
                    applicableConditionTypes = conditionTypesMap['yesno'];
                    break;
                case 'text':
                    applicableConditionTypes = conditionTypesMap['text'];
                    break;
                case 'single_choice':
                    applicableConditionTypes = conditionTypesMap['single_choice'];
                    break;
                case 'multiple_choice':
                    applicableConditionTypes = conditionTypesMap['multiple_choice'];
                    break;
                case 'textarea':
                    applicableConditionTypes = conditionTypesMap['textarea'];
                    break;
                default:
                    applicableConditionTypes = conditionTypesMap['text'];
            }
        } else if (itemModel === 'document_field') {
            applicableConditionTypes = conditionTypesMap['document'];
        } else if (itemModel === 'plugin' || itemModel === 'plugin_measure') {
            // Handle plugin items and their measures
            const valueType = selectedOption?.dataset.valueType || 'number';
            if (valueType === 'number') {
                applicableConditionTypes = conditionTypesMap['Number'];
            } else {
                applicableConditionTypes = conditionTypesMap['text'];
            }
        } else {
            // Fallback
            applicableConditionTypes = conditionTypesMap['text'];
        }

        // Populate select options
        selectElement.replaceChildren();
        {
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select Condition...';
            selectElement.appendChild(placeholder);
        }
        applicableConditionTypes.forEach(type => {
            const option = document.createElement('option');
            option.value = type.value;
            option.textContent = type.label;
            selectElement.appendChild(option);
        });
    },

    // Update value input based on condition type
    updateValueInput(containerElement, selectedItemId, selectedConditionType, existingValue = null, existingValueFieldId = null, currentItemId = null) {
        if (!containerElement) return;

        // Identify selected option meta
        const conditionLine = containerElement.closest('.condition-line');
        const itemSelect = conditionLine?.querySelector('.rule-item-select');
        const selectedOption = itemSelect?.querySelector(`option[value="${selectedItemId}"]`);
        const itemType = selectedOption?.dataset.itemType;
        const itemModel = selectedOption?.dataset.itemModel;

        // Special no-value conditions
        const noValueConditions = ['is_empty', 'is_not_empty', 'is_yes', 'is_no'];
        if (noValueConditions.includes(selectedConditionType)) {
            containerElement.replaceChildren();
            const span = document.createElement('span');
            span.className = 'text-gray-500 text-sm';
            span.textContent = 'No value needed';
            containerElement.appendChild(span);
            return;
        }

        // Clear container first
        containerElement.replaceChildren();

        // Create wrapper for value source selection
        const valueWrapper = document.createElement('div');
        valueWrapper.className = 'w-full space-y-2';

        // Create dropdown to select between static value and field reference
        const valueSourceSelect = document.createElement('select');
        valueSourceSelect.className = 'form-select block w-full text-sm border-gray-300 rounded-md rule-value-source-select mb-2';

        const customValueOpt = document.createElement('option');
        customValueOpt.value = 'static';
        customValueOpt.textContent = 'Static value';
        valueSourceSelect.appendChild(customValueOpt);

        const fieldRefOpt = document.createElement('option');
        fieldRefOpt.value = 'field';
        fieldRefOpt.textContent = 'Field reference';
        valueSourceSelect.appendChild(fieldRefOpt);

        // Create field reference dropdown (hidden initially)
        const fieldRefSelect = document.createElement('select');
        fieldRefSelect.className = 'form-select block w-full text-sm border-gray-300 rounded-md rule-value-field-select';
        fieldRefSelect.style.display = 'none';

        // Populate field reference dropdown
        const allItems = DataManager.getData('allTemplateItems') || [];
        const placeholderOpt = document.createElement('option');
        placeholderOpt.value = '';
        placeholderOpt.textContent = 'Select field...';
        fieldRefSelect.appendChild(placeholderOpt);

        allItems.forEach(item => {
            // Don't include the current item or the item being compared
            if (currentItemId && item.id === currentItemId) return;
            if (selectedItemId && item.id === selectedItemId) return;

            if (item.item_model !== 'plugin') {
                const option = document.createElement('option');
                option.value = item.id;

                // Extract numeric ID for display
                let displayId = item.id;
                const match = item.id.match(/^(question_|indicator_|document_field_|matrix_|form_item_)(\d+)$/);
                if (match) {
                    displayId = match[2];
                }

                let displayType = item.type || item.item_model || 'Unknown';
                if (displayType === 'null' || displayType === null) {
                    if (item.id && item.id.startsWith('document_field_')) {
                        displayType = 'Document';
                    } else if (item.id && item.id.startsWith('question_')) {
                        displayType = 'Question';
                    } else if (item.id && item.id.startsWith('indicator_')) {
                        displayType = 'Indicator';
                    } else if (item.id && item.id.startsWith('matrix_')) {
                        displayType = 'Matrix';
                    } else if (item.id && item.id.startsWith('form_item_')) {
                        // For form_item_ prefix, try to infer type from item.type or use a generic name
                        displayType = item.type || 'Item';
                    }
                }

                // Override specific item_model values for better display
                if (displayType === 'document_field' || displayType === 'Document Field') {
                    displayType = 'Document';
                } else if (displayType === 'question' || displayType === 'Question') {
                    displayType = 'Question';
                } else if (displayType === 'indicator' || displayType === 'Indicator') {
                    displayType = 'Indicator';
                } else if (displayType === 'matrix' || displayType === 'Matrix') {
                    displayType = 'Matrix';
                } else if (displayType === 'form_item') {
                    // For form_item model, use the actual type if available, otherwise use a generic name
                    displayType = item.type || 'Item';
                }

                let displayLabel = item.label;
                if (displayLabel.length > 60) {
                    displayLabel = displayLabel.substring(0, 57) + '...';
                }

                option.textContent = `${displayId}: ${displayType}: ${displayLabel}`;
                fieldRefSelect.appendChild(option);
            }
        });

        // Build appropriate input/select for static value
        let valueInput;

        // Yes/No select for yesno items
        if ((itemModel === 'question' && itemType === 'yesno') || (itemModel === 'indicator' && itemType === 'yesno')) {
            valueInput = document.createElement('select');
            valueInput.className = 'form-select block w-full text-sm border-gray-300 rounded-md rule-value-input';

            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select Option...';
            valueInput.appendChild(placeholder);

            const yesOpt = document.createElement('option');
            yesOpt.value = 'yes';
            yesOpt.textContent = 'Yes';
            if (existingValue === 'yes') yesOpt.selected = true;
            valueInput.appendChild(yesOpt);

            const noOpt = document.createElement('option');
            noOpt.value = 'no';
            noOpt.textContent = 'No';
            if (existingValue === 'no') noOpt.selected = true;
            valueInput.appendChild(noOpt);
        } else if (itemModel === 'question' && (itemType === 'single_choice' || itemType === 'multiple_choice')) {
            // Choice list select
            valueInput = document.createElement('select');
            valueInput.className = 'form-select block w-full text-sm border-gray-300 rounded-md rule-value-input';

            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select Option...';
            valueInput.appendChild(placeholder);

            // Retrieve question options
            const questionItem = allItems.find(i => i.id == selectedItemId);
            const optionsArray = questionItem?.options || [];
            optionsArray.forEach(opt => {
                const optEl = document.createElement('option');
                optEl.value = opt;
                optEl.textContent = opt;
                if (existingValue === opt) optEl.selected = true;
                valueInput.appendChild(optEl);
            });
        } else if (itemModel === 'indicator' || (itemModel === 'question' && itemType === 'number')) {
            // Number input
            valueInput = document.createElement('input');
            valueInput.type = 'number';
            valueInput.placeholder = 'Enter value...';
            valueInput.className = 'form-input block w-full text-sm border-gray-300 rounded-md rule-value-input';
            if (existingValue !== null && existingValue !== undefined) valueInput.value = existingValue;
        } else {
            // Default text input
            valueInput = document.createElement('input');
            valueInput.type = 'text';
            valueInput.placeholder = 'Enter value...';
            valueInput.className = 'form-input block w-full text-sm border-gray-300 rounded-md rule-value-input';
            if (existingValue !== null && existingValue !== undefined) valueInput.value = existingValue;
        }

        // Handle existing value: determine if it's a field reference or static value
        if (existingValueFieldId !== null && existingValueFieldId !== undefined) {
            // This is a field reference
            valueSourceSelect.value = 'field';
            fieldRefSelect.style.display = 'block';
            valueInput.style.display = 'none';

            // Find and select the matching field
            const options = fieldRefSelect.querySelectorAll('option');
            for (const option of options) {
                if (option.value) {
                    const match = option.value.match(/^(question_|indicator_|document_field_|matrix_|form_item_)(\d+)$/);
                    if (match && parseInt(match[2], 10) === parseInt(existingValueFieldId, 10)) {
                        fieldRefSelect.value = option.value;
                        break;
                    }
                }
            }
        } else {
            // This is a static value
            valueSourceSelect.value = 'static';
            fieldRefSelect.style.display = 'none';
            valueInput.style.display = 'block';
        }

        // Handle value source change
        valueSourceSelect.addEventListener('change', () => {
            if (valueSourceSelect.value === 'field') {
                fieldRefSelect.style.display = 'block';
                valueInput.style.display = 'none';
                valueInput.value = '';
            } else {
                fieldRefSelect.style.display = 'none';
                valueInput.style.display = 'block';
                fieldRefSelect.value = '';
            }
        });

        valueWrapper.appendChild(valueSourceSelect);
        valueWrapper.appendChild(fieldRefSelect);
        valueWrapper.appendChild(valueInput);
        containerElement.appendChild(valueWrapper);
    },

    // Serialize rule builder to JSON
    serializeRuleBuilder(containerElement) {
        if (!containerElement) return null;

        const logicSelect = containerElement.querySelector('.rule-logic-select');
        const conditionLines = containerElement.querySelectorAll('.condition-line');

        const conditions = [];
        conditionLines.forEach(line => {
            const itemSelect = line.querySelector('.rule-item-select');
            const conditionTypeSelect = line.querySelector('.rule-condition-type-select');
            const valueSourceSelect = line.querySelector('.rule-value-source-select');
            const valueInput = line.querySelector('.rule-value-input');
            const valueFieldSelect = line.querySelector('.rule-value-field-select');

            if (itemSelect.value && conditionTypeSelect.value) {
                // Extract numeric ID from prefixed format (e.g., "question_66" -> "66" or "form_item_967" -> "967")
                let itemId = itemSelect.value;
                const match = itemId.match(/^(question_|indicator_|document_field_|matrix_|form_item_)(\d+)$/);
                if (match) {
                    itemId = match[2]; // Use just the numeric part
                }

                const condition = {
                    item_id: itemId,
                    condition_type: conditionTypeSelect.value
                };

                // Check if using field reference or static value
                if (valueSourceSelect && valueSourceSelect.value === 'field' && valueFieldSelect && valueFieldSelect.value) {
                    // Field reference selected - extract numeric ID
                    let fieldId = valueFieldSelect.value;
                    const fieldMatch = fieldId.match(/^(question_|indicator_|document_field_|matrix_|form_item_)(\d+)$/);
                    if (fieldMatch) {
                        fieldId = parseInt(fieldMatch[2], 10);
                    }
                    condition.value_field_id = fieldId;
                } else if (valueInput && valueInput.value) {
                    // Static value
                    condition.value = valueInput.value;
                }

                conditions.push(condition);
            }
        });

        if (conditions.length === 0) return null;

        const ruleObject = {
            logic: logicSelect.value || 'AND',
            conditions: conditions
        };

        return JSON.stringify(ruleObject);
    },

    // Handle rule builder toggle
    handleRuleBuilderToggle(button, modal) {
        const targetSelector = button.getAttribute('data-target');
        const targetElement = modal.querySelector(targetSelector);
        const rightHalf = modal.querySelector('.modal-right-half');

        if (!targetElement || !rightHalf) return;

        // Toggle visibility
        Utils.toggleElement(targetElement);

        // Hide the right half if no rules are visible
        const visibleRules = rightHalf.querySelectorAll('.rule-section:not(.hidden), div[id$="-rule-section"]:not(.hidden)');
        if (visibleRules.length === 0) {
            Utils.hideElement(rightHalf);
            modal.classList.remove('md:grid-cols-2');
            // Revert modal width when no rule sections are visible
            const modalContent = modal.closest('.relative.p-6');
            if (modalContent) {
                modalContent.classList.remove('max-w-6xl');
                modalContent.classList.remove('max-w-4xl');
                modalContent.classList.add('max-w-xl');
            }
        } else {
            Utils.showElement(rightHalf);
            modal.classList.add('md:grid-cols-2');
            // Expand modal width when a rule section is shown
            const modalContent = modal.closest('.relative.p-6');
            if (modalContent) {
                modalContent.classList.remove('max-w-xl');
                modalContent.classList.remove('max-w-4xl');
                modalContent.classList.add('max-w-6xl');
            }
        }

        // Initialize rule builder if not already initialized
        const ruleBuilder = targetElement.querySelector('.rule-builder') || targetElement.querySelector('[id$="-rule-builder"]');
        if (ruleBuilder && ruleBuilder.innerHTML.trim() === '') {
            const ruleType = targetSelector.includes('validation') ? 'validation' : 'relevance';
            // Attempt to retrieve pre-existing rule JSON stored on the element
            let existingRuleJson = ruleBuilder.getAttribute('data-rule-json');
            if (existingRuleJson && existingRuleJson.trim() !== '' && existingRuleJson !== 'null' && existingRuleJson !== '{}') {
                try {
                    // Ensure parsable JSON – leave as string for renderRuleBuilder
                    JSON.parse(existingRuleJson);
            } catch (error) {
                existingRuleJson = null;
            }
            } else {
                existingRuleJson = null;
            }

            // Get current item ID from ItemModal and convert to prefixed format
            let currentItemId = null;
            if (window.ItemModal && window.ItemModal.currentItemId) {
                const numericId = window.ItemModal.currentItemId;
                const itemType = window.ItemModal.currentItemType || 'question';

                // Convert to prefixed format based on item type
                if (itemType === 'indicator') {
                    currentItemId = `indicator_${numericId}`;
                } else if (itemType === 'question') {
                    currentItemId = `question_${numericId}`;
                } else if (itemType === 'document_field') {
                    currentItemId = `document_field_${numericId}`;
                } else if (itemType === 'matrix') {
                    currentItemId = `matrix_${numericId}`;
                } else if (itemType && itemType.startsWith('plugin_')) {
                    currentItemId = `plugin_${numericId}`;
                } else {
                    // Try to find the item in allTemplateItems to get the correct prefix
                    const allItems = DataManager.getData('allTemplateItems') || [];
                    const foundItem = allItems.find(item => {
                        const match = item.id && item.id.match(/^.+_(\d+)$/);
                        return match && parseInt(match[1], 10) === parseInt(numericId, 10);
                    });
                    if (foundItem) {
                        currentItemId = foundItem.id;
                    } else {
                        // Fallback to question_ prefix
                        currentItemId = `question_${numericId}`;
                    }
                }
            }

            this.renderRuleBuilder(ruleBuilder, existingRuleJson, ruleType, currentItemId);
        }
    }
};

// Export for use in main.js
export default RuleBuilder;
