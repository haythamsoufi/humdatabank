// calculated-lists.js - Module for handling calculated lists and their filters

// Utils is available globally from utils.js
import { DataManager } from './data-manager.js';

export const CalculatedLists = {
    _debug: function(...args) {
        if (window.formBuilderDebug && window.formBuilderDebug.isEnabled && window.formBuilderDebug.isEnabled('calculated-lists')) {
            window.formBuilderDebug.log('calculated-lists', ...args);
        }
    },

    _setSelectPlaceholder(selectEl, placeholderText) {
        if (!selectEl) return;
        selectEl.replaceChildren();
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = placeholderText;
        selectEl.appendChild(opt);
    },

    _setSanitizedHtml(container, html) {
        Utils.setSanitizedHtml(container, html);
    },

    // Initialize calculated lists functionality
    init: function() {
        this.setupEventListeners();
    },

    // Setup event listeners for calculated lists
    setupEventListeners: function() {
        if (!this._documentChangeHandler) {
            this._documentChangeHandler = (e) => {
                const id = e.target.id;

                // Handle calculated list selection to populate display column
                if (id === 'item-calculated-list-select') {
                    this.handleListSelection(e.target);
                }
            };
            document.addEventListener('change', this._documentChangeHandler);
        }

        // Add filter button for calculated lists
        const addFilterBtn = Utils.getElementById('item-calculated-list-add-filter-btn');
        if (addFilterBtn && !addFilterBtn.__handlerAdded) {
            addFilterBtn.__handlerAdded = true;
            addFilterBtn.addEventListener('click', () => {
                this.addFilter();
            });
        }
    },

    // Handle list selection and populate display column
    handleListSelection: function(selectElement) {
        const colWrapper = Utils.getElementById('item-calculated-display-column-wrapper');
        const colSelect = Utils.getElementById('item-calculated-list-display-column');

        if (!colSelect) return;

        // Clear existing options
        this._setSelectPlaceholder(colSelect, 'Select Column...');

        const selectedOption = selectElement.selectedOptions && selectElement.selectedOptions[0];
        if (selectedOption && selectedOption.dataset.columns) {
            try {
                const columns = JSON.parse(selectedOption.dataset.columns);
                let firstValue = null;

                columns.forEach((column) => {
                    // Skip name_translations field
                    if (column.name === 'name_translations') {
                        return;
                    }

                    const option = document.createElement('option');
                    option.value = column.name;

                    // Check if column is multilingual (has name_translations)
                    const isMultilingual = column.multilingual === true ||
                                          (column.name === 'name' &&
                                           (selectElement.value === 'country_map' ||
                                            selectElement.value === 'national_society'));

                    // Create display text with translation icon if multilingual
                    let displayText = column.label || column.name;
                    if (isMultilingual) {
                        // Use Unicode translation icon (🌐) with tooltip
                        displayText = `${displayText} 🌐`;
                        option.dataset.multilingual = 'true';
                        option.title = 'This field supports multiple languages and will display in the user\'s selected language';
                    }

                    option.textContent = displayText;
                    colSelect.appendChild(option);

                    if (!firstValue) firstValue = column.name;
                });

                // Auto-select first column by default
                if (firstValue && !colSelect.value) {
                    colSelect.value = firstValue;
                }

                Utils.showElement(colWrapper);
            } catch (err) {
                console.error('Failed to parse columns JSON:', err);
                Utils.hideElement(colWrapper);
            }
        } else {
            Utils.hideElement(colWrapper);
        }

        // Clear existing filters when list changes
        this.clearAllFilters();

        // Load plugin config UI if the selected list supports it
        this._loadPluginConfigUI(selectedOption, null);
    },

    // --- Plugin config UI (e.g. Emergency Operations) ---

    /**
     * Fetch and inject the plugin config UI for the selected list option.
     * @param {HTMLOptionElement|null} selectedOption - The chosen <option> element
     * @param {Object|null} existingConfig - Previously saved plugin config (for edit mode)
     */
    _loadPluginConfigUI: function(selectedOption, existingConfig) {
        const container = Utils.getElementById('question-plugin-config-container');
        const hiddenInput = Utils.getElementById('question-plugin-config-json');
        if (!container) return;

        // If populateForm placed a pending restore config (edit mode), use it instead of
        // the null passed by handleListSelection so we fetch the UI with saved values
        // and avoid a redundant second request.
        const configToLoad = existingConfig
            || (this._pendingRestoreConfig ? this._pendingRestoreConfig : null);
        // Consume it (restorePluginConfig skipped when _pendingRestoreConfig is already used here)
        this._pendingRestoreConfig = null;

        // Version counter: each call increments it so a stale fetch response is ignored.
        if (!this._configUIVersion) this._configUIVersion = 0;
        const version = ++this._configUIVersion;

        // Clear previous config UI and reset hidden input
        container.replaceChildren();
        if (hiddenInput) hiddenInput.value = '{}';

        if (!selectedOption || !selectedOption.dataset.hasConfigUi) return;

        const listId = selectedOption.value;
        // WAF: pass config as base64 so JSON values (dates, appeal names, etc.) don't trigger CRS rules.
        const configB64 = btoa(unescape(encodeURIComponent(JSON.stringify(configToLoad || {}))));
        const url = `/api/forms/lookup-lists/${encodeURIComponent(listId)}/config-ui?config_b64=${encodeURIComponent(configB64)}`;
        this._debug('[PluginConfig] fetching config UI, restoring config ->', configToLoad);

        ((window.getFetch && window.getFetch()) || fetch)(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                return r.json();
            })
            .then(data => {
                // Discard if a newer call has already started
                if (this._configUIVersion !== version) return;
                if (!data.success || !data.html) return;
                this._setSanitizedHtml(container, data.html);

                // Immediately sync the hidden input with whatever the server rendered
                // (covers edit-mode restore where the user saves without changing anything)
                this._serializePluginConfig(container);

                // Wire up the JS handler exported by the plugin
                const jsHandler = selectedOption.dataset.configJsHandler;
                if (!jsHandler) return;

                const updateCallback = () => this._serializePluginConfig(container);

                const doSetup = (fn) => fn(container, updateCallback);

                if (window[jsHandler]) {
                    doSetup(window[jsHandler]);
                } else {
                    // Derive plugin name from the list ID (convention: list ID === plugin name).
                    // Prepend origin so the path resolves to the app server even when
                    // this module is served from a CDN (e.g. Azure Blob Storage).
                    import(`${window.location.origin}/plugins/static/${listId}/js/matrix_config_handler.js`)
                        .then(mod => {
                            const fn = mod[jsHandler] || mod.default;
                            if (fn) doSetup(fn);
                            else console.warn(`Plugin handler "${jsHandler}" not found in module for list "${listId}"`);
                        })
                        .catch(err => console.warn(`Failed to load plugin config JS handler for "${listId}":`, err));
                }
            })
            .catch(err => {
                console.warn('Failed to fetch plugin config UI:', err);
                if (container) {
                    container.replaceChildren();
                    const msg = document.createElement('p');
                    msg.className = 'text-sm text-red-600 mt-1';
                    msg.textContent = 'Could not load configuration. Please try again.';
                    container.appendChild(msg);
                }
            });
    },

    /**
     * Read all named inputs from the config container and write the result to the
     * hidden #question-plugin-config-json input.
     */
    _serializePluginConfig: function(container) {
        const hiddenInput = Utils.getElementById('question-plugin-config-json');
        if (!hiddenInput || !container) return;

        const config = {};
        const inputs = container.querySelectorAll('input, select, textarea');

        // Group checkboxes with the same name as arrays
        const checkboxGroups = {};
        inputs.forEach(input => {
            const name = input.name;
            if (!name) return;
            if (input.type === 'checkbox') {
                if (!checkboxGroups[name]) checkboxGroups[name] = [];
                if (input.checked) checkboxGroups[name].push(input.value);
            } else if (input.type === 'radio') {
                if (input.checked) config[name] = input.value;
            } else {
                config[name] = input.value;
            }
        });

        Object.assign(config, checkboxGroups);
        hiddenInput.value = JSON.stringify(config);
        this._debug('[PluginConfig] serialized ->', hiddenInput.value);
    },

    /**
     * Get the current plugin config as a plain object (parsed from hidden input).
     */
    getPluginConfig: function() {
        const hiddenInput = Utils.getElementById('question-plugin-config-json');
        if (!hiddenInput || !hiddenInput.value) return {};
        try { return JSON.parse(hiddenInput.value); } catch (_) { return {}; }
    },

    /**
     * Restore the config UI for a list that was previously configured (edit mode).
     * Should be called after the list select value is set.
     * @param {Object} config - The saved plugin config object
     */
    restorePluginConfig: function(config) {
        const listSelect = Utils.getElementById('item-calculated-list-select');
        if (!listSelect) return;
        const selectedOption = listSelect.selectedOptions && listSelect.selectedOptions[0];
        if (selectedOption) {
            this._loadPluginConfigUI(selectedOption, config);
        }
    },

    // Add a new filter for calculated lists
    addFilter: function() {
        const listSelect = Utils.getElementById('item-calculated-list-select');
        if (!listSelect || !listSelect.value) {
            Utils.showError('Please select a list first');
            return;
        }

        const selectedOption = listSelect.options[listSelect.selectedIndex];
        if (!selectedOption || !selectedOption.dataset.columns) {
            Utils.showError('List columns not available');
            return;
        }

        let columns;
        try {
            columns = JSON.parse(selectedOption.dataset.columns);
        } catch (err) {
            Utils.showError('Invalid column configuration');
            return;
        }

        const container = Utils.getElementById('item-calculated-list-filters-container');
        const filterIndex = container.children.length;

        const filterDiv = this.createFilterElement(columns, filterIndex);
        container.appendChild(filterDiv);

        this.updateFiltersJson();
    },

    // Create a filter element
    createFilterElement: function(columns, filterIndex) {
        const filterDiv = document.createElement('div');
        filterDiv.className = 'filter-item border border-gray-200 rounded-lg p-3 bg-gray-50';
        filterDiv.dataset.filterIndex = filterIndex;

        const row = document.createElement('div');
        row.className = 'flex items-center space-x-2';

        const fieldSelect = document.createElement('select');
        fieldSelect.className = 'filter-field-select flex-1 text-sm border border-gray-300 rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500';
        fieldSelect.style.minWidth = '140px';
        this._setSelectPlaceholder(fieldSelect, 'Select Field');
        (columns || []).forEach((col) => {
            const name = col && col.name !== undefined && col.name !== null ? String(col.name) : '';
            if (!name) return;
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            fieldSelect.appendChild(opt);
        });

        const operatorSelect = document.createElement('select');
        operatorSelect.className = 'filter-operator-select flex-1 text-sm border border-gray-300 rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500';
        operatorSelect.style.minWidth = '120px';
        [
            ['eq', 'Equals'],
            ['ne', 'Not Equals'],
            ['contains', 'Contains'],
            ['startswith', 'Starts With'],
            ['gt', 'Greater Than'],
            ['gte', 'Greater Than or Equal'],
            ['lt', 'Less Than'],
            ['lte', 'Less Than or Equal']
        ].forEach(([value, label]) => {
            const opt = document.createElement('option');
            opt.value = value;
            opt.textContent = label;
            operatorSelect.appendChild(opt);
        });

        const valueSelect = document.createElement('select');
        valueSelect.className = 'filter-value-select flex-1 text-sm border border-gray-300 rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500';
        valueSelect.title = 'Select value source';
        valueSelect.style.minWidth = '140px';
        this._setSelectPlaceholder(valueSelect, 'Custom value');

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'remove-filter-btn text-red-600 hover:text-red-800 p-1 rounded hover:bg-red-50';
        {
            const icon = document.createElement('i');
            icon.className = 'fas fa-trash w-4 h-4';
            removeBtn.appendChild(icon);
        }

        row.append(fieldSelect, operatorSelect, valueSelect, removeBtn);

        const inputRow = document.createElement('div');
        inputRow.className = 'mt-2 w-full';

        const valueInput = document.createElement('input');
        valueInput.type = 'text';
        valueInput.className = 'filter-value-input w-full text-sm border border-gray-300 rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500';
        valueInput.placeholder = 'Enter custom value';
        valueInput.style.display = 'none';

        inputRow.appendChild(valueInput);
        filterDiv.append(row, inputRow);

        this.setupFilterElementListeners(filterDiv);

        // Populate the value select with available template items (questions & indicators)
        this.populateValueSelect(valueSelect);

        // Initialize the input field visibility based on the default selection
        if (valueSelect && valueInput) {
            if (valueSelect.value === '') {
                // Custom value is selected by default, show the input field
                valueInput.style.display = 'block';
            } else {
                // Field reference is selected, hide the input field
                valueInput.style.display = 'none';
            }
        }

        return filterDiv;
    },

    // Populate the value-select dropdown with all other template items (label)
    populateValueSelect: function(selectEl) {
        if (!selectEl) return;

        // Keep the "Custom value" option as first
        this._setSelectPlaceholder(selectEl, 'Custom value');

        // Add other template items
        const items = DataManager.getData('allTemplateItems') || [];
        items.forEach(it => {
            // Skip items that don't have an ID or label
            if (!it.id || !it.label) return;
            const opt = document.createElement('option');
            opt.value = it.id;
            opt.textContent = `Field: ${it.label}`;
            selectEl.appendChild(opt);
        });
    },

    // Setup event listeners for a filter element
    setupFilterElementListeners: function(filterDiv) {
        const removeBtn = filterDiv.querySelector('.remove-filter-btn');
        removeBtn.addEventListener('click', () => {
            filterDiv.remove();
            this.updateFiltersJson();
        });

        // Attach events to filter elements
        this.attachFilterEvents(filterDiv);
    },

    // Attach events to filter elements
    attachFilterEvents: function(filterDiv) {
        if (!filterDiv) return;

        const fieldSelect = filterDiv.querySelector('.filter-field-select');
        const operatorSelect = filterDiv.querySelector('.filter-operator-select');
        const valueSelect = filterDiv.querySelector('.filter-value-select');
        const valueInput = filterDiv.querySelector('.filter-value-input');

        const handler = () => {
            this._debug('Filter changed, updating JSON...');
            this.updateFiltersJson();
        };

        // Handle value source selection (custom value vs field reference)
        if (valueSelect) {
            valueSelect.addEventListener('change', () => {
                if (valueSelect.value === '') {
                    // Custom value selected - show text input
                    valueInput.style.display = 'block';
                    valueInput.value = '';
                    valueInput.focus();
                } else {
                    // Field reference selected - hide text input
                    valueInput.style.display = 'none';
                    valueInput.value = '';
                }
                handler();
            });
        }

        // Handle other form elements
        [fieldSelect, operatorSelect].forEach(element => {
            if (element) {
                element.addEventListener('change', handler);
                element.addEventListener('input', handler);
                element.addEventListener('blur', handler);
            }
        });

        // Handle text input changes
        if (valueInput) {
            valueInput.addEventListener('input', handler);
            valueInput.addEventListener('blur', handler);
        }
    },

    // Clear all filters for calculated lists
    clearAllFilters: function() {
        const container = Utils.getElementById('item-calculated-list-filters-container');
        if (container) {
            container.replaceChildren();
            this.updateFiltersJson();
        }
    },

    // Update the hidden JSON input with current filters
    updateFiltersJson: function() {
        const container = Utils.getElementById('item-calculated-list-filters-container');
        const jsonInput = Utils.getElementById('item-calculated-list-filters-json');

        if (!container || !jsonInput) {
            this._debug('Container or JSON input not found');
            return;
        }

        const filters = [];
        const filterItems = container.querySelectorAll('.filter-item');

        this._debug('Processing', filterItems.length, 'filter items');

        filterItems.forEach((item, index) => {
            const field = item.querySelector('.filter-field-select').value;
            const operator = item.querySelector('.filter-operator-select').value;
            const valueSelect = item.querySelector('.filter-value-select').value;
            const valueInput = item.querySelector('.filter-value-input').value;

            this._debug(`Filter ${index}:`, {
                field,
                operator,
                valueSelect,
                valueInput,
                valueSelectIsEmpty: valueSelect === '',
                valueInputTrimmed: valueInput.trim()
            });

            let filterObj = { field, op: operator };

            if (valueSelect === '') {
                // Custom value selected - use text input value
                if (valueInput.trim()) {
                    filterObj.value = valueInput.trim();
                    this._debug(`Filter ${index} using custom value:`, filterObj.value);
                } else {
                    this._debug(`Filter ${index} has empty custom value, skipping`);
                    return; // Skip this filter if no value provided
                }
            } else {
                // Field reference selected - extract numeric ID from prefixed format
                if (valueSelect.trim()) {
                    let fieldId = valueSelect.trim();

                    // Extract numeric ID from prefixed format (e.g., "question_200018" -> "200018")
                    const match = fieldId.match(/^(question_|indicator_|document_field_)(\d+)$/);
                    if (match) {
                        fieldId = parseInt(match[2], 10);
                        this._debug(`Extracted numeric ID from ${valueSelect.trim()}:`, fieldId);
                    } else {
                        this._debug('Using field ID as-is:', fieldId);
                    }

                    filterObj.value_field_id = fieldId;
                    this._debug(`Filter ${index} using field reference:`, filterObj.value_field_id);
                } else {
                    this._debug(`Filter ${index} has empty field ID, skipping`);
                    return; // Skip this filter if no field ID provided
                }
            }

            // Only push if we have field, operator, and either custom value or field reference
            if (field && operator && (filterObj.value !== undefined || filterObj.value_field_id !== undefined)) {
                filters.push(filterObj);
                this._debug(`Added filter ${index}:`, filterObj);
            } else {
                this._debug(`Skipping incomplete filter ${index}:`, { field, operator, filterObj });
            }
        });

        jsonInput.value = JSON.stringify(filters);
        this._debug('Updated calculated list filters:', filters);
        this._debug('JSON input value set to:', jsonInput.value);
    },

    // Populate calculated list filters from existing data
    populateFilters: function(filtersJson) {
        this._debug('populateFilters called with:', filtersJson);

        if (!filtersJson) {
            this._debug('No filters JSON provided');
            return;
        }

        let filters;
        try {
            filters = typeof filtersJson === 'string' ? JSON.parse(filtersJson) : filtersJson;
            this._debug('Parsed filters:', filters);
        } catch (err) {
            console.error('Failed to parse filters JSON:', err);
            return;
        }

        if (!Array.isArray(filters)) {
            this._debug('Filters is not an array:', typeof filters);
            return;
        }

        this._debug('About to populate', filters.length, 'filters');

        // Clear existing filters first
        this.clearAllFilters();

        // Get available columns for the selected list (if any)
        const columns = this.getAvailableColumns();

        // Add each filter
        filters.forEach((filter, index) => {
            this._debug(`Processing filter ${index}:`, filter);

            // Create filter element directly instead of calling addFilter()
            const container = Utils.getElementById('item-calculated-list-filters-container');
            const filterIndex = container.children.length;
            const filterDiv = this.createFilterElement(columns, filterIndex);
            container.appendChild(filterDiv);

            // Populate the filter with existing data
            const fieldSelect = filterDiv.querySelector('.filter-field-select');
            const operatorSelect = filterDiv.querySelector('.filter-operator-select');
            const valueSelect = filterDiv.querySelector('.filter-value-select');
            const valueInput = filterDiv.querySelector('.filter-value-input');

            if (fieldSelect) fieldSelect.value = filter.field || '';
            if (operatorSelect) operatorSelect.value = filter.op || 'eq';

            // Handle custom value vs field reference
            if ('value_field_id' in filter && filter.value_field_id !== null && filter.value_field_id !== undefined) {
                // Field reference - find the corresponding prefixed option in dropdown
                this._debug('Setting field reference:', filter.value_field_id);

                // Convert numeric ID back to prefixed format for dropdown selection
                let dropdownValue = '';
                if (valueSelect) {
                    const options = valueSelect.querySelectorAll('option');
                    for (const option of options) {
                        if (option.value) {
                            // Extract numeric part and compare
                            const match = option.value.match(/^(question_|indicator_|document_field_)(\d+)$/);
                            if (match && parseInt(match[2], 10) === filter.value_field_id) {
                                dropdownValue = option.value;
                                this._debug(`Found matching dropdown option: ${dropdownValue} for field ID:`, filter.value_field_id);
                                break;
                            }
                        }
                    }
                    valueSelect.value = dropdownValue;
                }

                if (valueInput) {
                    valueInput.style.display = 'none';
                    valueInput.value = '';
                }
            } else if ('value' in filter && filter.value) {
                // Custom value - select "Custom value" option and show/populate text input
                this._debug('Setting custom value:', filter.value);
                if (valueSelect) valueSelect.value = '';
                if (valueInput) {
                    valueInput.style.display = 'block';
                    valueInput.value = filter.value;
                }
            } else {
                // Default to custom value if neither is properly set
                this._debug('Defaulting to custom value mode for filter:', filter);
                if (valueSelect) valueSelect.value = '';
                if (valueInput) {
                    valueInput.style.display = 'block';
                    valueInput.value = '';
                }
            }

            // Ensure event handlers are properly attached
            this.attachFilterEvents(filterDiv);
        });

        this._debug('Finished populating filters, calling updateFiltersJson');
        this.updateFiltersJson();
    },

    // Get available columns for the selected list
    getAvailableColumns: function() {
        const listSelect = Utils.getElementById('item-calculated-list-select');
        if (!listSelect || !listSelect.value) return [];

        const selectedOption = listSelect.options[listSelect.selectedIndex];
        if (!selectedOption || !selectedOption.dataset.columns) return [];

        try {
            return JSON.parse(selectedOption.dataset.columns);
        } catch (err) {
            console.error('Failed to parse columns JSON:', err);
            return [];
        }
    },

    // Get current filters as an array
    getCurrentFilters: function() {
        const container = Utils.getElementById('item-calculated-list-filters-container');
        if (!container) return [];

        const filters = [];
        const filterItems = container.querySelectorAll('.filter-item');

        filterItems.forEach(item => {
            const field = item.querySelector('.filter-field-select').value;
            const operator = item.querySelector('.filter-operator-select').value;
            const valueSelect = item.querySelector('.filter-value-select').value;
            const valueInput = item.querySelector('.filter-value-input').value;

            if (field && operator) {
                const obj = { field, op: operator };

                if (valueSelect === '') {
                    // Custom value selected
                    if (valueInput.trim()) {
                        obj.value = valueInput.trim();
                        filters.push(obj);
                    }
                } else {
                    // Field reference selected — extract numeric ID from prefixed format
                    // (e.g. "question_200018" → 200018), matching updateFiltersJson logic
                    const match = valueSelect.match(/^(question_|indicator_|document_field_)(\d+)$/);
                    obj.value_field_id = match ? parseInt(match[2], 10) : parseInt(valueSelect, 10);
                    filters.push(obj);
                }
            }
        });

        return filters;
    },

    // Validate current filters
    validateFilters: function() {
        const filters = this.getCurrentFilters();
        const errors = [];

        filters.forEach((filter, index) => {
            if (!filter.field) {
                errors.push(`Filter ${index + 1}: Field is required`);
            }
            if (!filter.op) {
                errors.push(`Filter ${index + 1}: Operator is required`);
            }
            if (!filter.value && !filter.value_field_id) {
                errors.push(`Filter ${index + 1}: Value is required`);
            }
        });

        return errors;
    },

    // Reset to default state
    reset: function() {
        this._pendingRestoreConfig = null;
        this._configUIVersion = (this._configUIVersion || 0) + 1;
        this.clearAllFilters();

        const listSelect = Utils.getElementById('item-calculated-list-select');
        const colWrapper = Utils.getElementById('item-calculated-display-column-wrapper');
        const colSelect = Utils.getElementById('item-calculated-list-display-column');
        const filtersJsonInput = Utils.getElementById('item-calculated-list-filters-json');
        const pluginConfigContainer = Utils.getElementById('question-plugin-config-container');
        const pluginConfigInput = Utils.getElementById('question-plugin-config-json');

        if (listSelect) listSelect.value = '';
        if (colWrapper) Utils.hideElement(colWrapper);
        if (colSelect) this._setSelectPlaceholder(colSelect, 'Select Column...');
        if (filtersJsonInput) filtersJsonInput.value = '[]';
        if (pluginConfigContainer) pluginConfigContainer.replaceChildren();
        if (pluginConfigInput) pluginConfigInput.value = '{}';
    }
};

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    CalculatedLists.init();
});

// Export for global access
window.CalculatedLists = CalculatedLists;
