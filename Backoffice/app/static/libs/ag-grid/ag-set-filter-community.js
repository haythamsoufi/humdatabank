/**
 * AG Grid Community Set Filter
 * A powerful custom filter component that mimics Enterprise Set Filter functionality
 * Features:
 * - Shows unique values from column data
 * - Search/filter functionality
 * - Select all/none
 * - Checkbox selection
 * - Proper integration with AG Grid filter API
 */

(function() {
    'use strict';

    /**
     * Translation utility for ag-grid components
     * Reads translations from window.agGridTranslations or falls back to English
     * @param {string} key - Translation key
     * @param {string} defaultValue - Default English value
     * @returns {string} Translated string
     */
    function getTranslation(key, defaultValue) {
        // Try to get from window.agGridTranslations (set by templates)
        if (window.agGridTranslations && window.agGridTranslations[key]) {
            return window.agGridTranslations[key];
        }
        // Try to get from i18n-json script tag
        try {
            const i18nEl = document.getElementById('i18n-json');
            if (i18nEl) {
                const i18n = JSON.parse(i18nEl.textContent);
                if (i18n[key]) {
                    return i18n[key];
                }
            }
        } catch (e) {
            // Ignore parsing errors
        }
        // Fallback to default English value
        return defaultValue;
    }

    // Custom Set Filter Component
    function CustomSetFilter() {
        this.uniqueValues = [];
        this.valueCounts = {}; // Track count for each value (all rows)
        this.availableValueCounts = {}; // Track count for each value (rows passing other filters)
        this.selectedValues = new Set();
        this.filteredValues = [];
        this.selectAllChecked = false;
        this.selectAllIndeterminate = false;
        // Standard filter properties
        this.filterType = 'text'; // Default to text filter
        this.filterCondition = 'contains'; // Default condition
        this.filterValue = ''; // Standard filter input value
    }

    CustomSetFilter.prototype.init = function(params) {
        this.params = params;
        this.hidePopup = (params && typeof params.hidePopup === 'function') ? params.hidePopup : null;
        this.filterChangedCallback = params.filterChangedCallback;
        this.valueGetter = params.valueGetter;
        this.doesRowPassOtherFilters = params.doesRowPassOtherFilters;

        // Get column field for fallback valueGetter
        this.columnField = params.colDef ? (params.colDef.field || params.colDef.colId) : null;
        this.colDef = params.colDef;

        // Create fallback valueGetter if not provided
        if (!this.valueGetter || typeof this.valueGetter !== 'function') {
            this.valueGetter = function(node) {
                if (!node || !node.data) return null;
                if (this.columnField) {
                    return node.data[this.columnField];
                }
                return null;
            }.bind(this);
        }

        // If column has a valueGetter, prefer it to avoid object values like [object Object]
        // (e.g. field holds an object but valueGetter returns a string for display/filtering).
        if (this.colDef && this.colDef.valueGetter && typeof this.colDef.valueGetter === 'function') {
            const originalValueGetter = this.valueGetter;
            const columnValueGetter = this.colDef.valueGetter;
            this.valueGetter = function(node) {
                // Prefer the column's valueGetter (templates often return a string here)
                try {
                    const v = columnValueGetter({ node: node, data: node.data });
                    if (v !== undefined && v !== null) {
                        return v;
                    }
                } catch (e) {
                    // ignore and fall back
                }

                // Fall back to AG Grid's provided valueGetter
                return originalValueGetter ? originalValueGetter(node) : undefined;
            }.bind(this);
        }

        // Extract unique values from all rows
        this.extractUniqueValues();

        // Create the filter UI
        this.createFilterUI();

        // Set initial state
        this.updateSelectAllState();

        // Listen for filter changes to refresh available values
        if (this.params.api) {
            this.onFilterChangedListener = this.onFilterChanged.bind(this);
            this.params.api.addEventListener('filterChanged', this.onFilterChangedListener);
        }

    };

    CustomSetFilter.prototype.extractUniqueValues = function() {
        const valueCountMap = {}; // Track count for each value (all rows)
        const availableValueCountMap = {}; // Track count for each value (rows passing other filters)

        // Ensure valueGetter is a function
        if (!this.valueGetter || typeof this.valueGetter !== 'function') {
            // Create a simple valueGetter using column field
            this.valueGetter = function(node) {
                if (!node || !node.data) return null;
                if (this.columnField) {
                    return node.data[this.columnField];
                }
                return null;
            }.bind(this);
        }

        // Helper to check if row passes other filters (excluding current column)
        // Note: This is only used as a fallback if forEachNodeAfterFilter is not available
        const checkOtherFilters = (node) => {
            // First try the built-in doesRowPassOtherFilters (excludes current filter automatically)
            if (this.doesRowPassOtherFilters && typeof this.doesRowPassOtherFilters === 'function') {
                try {
                    return this.doesRowPassOtherFilters(node);
                } catch (error) {
                    // doesRowPassOtherFilters failed, fall through to manual check
                }
            }

            // If doesRowPassOtherFilters not available, return true (assume all pass)
            // The manual check below is complex and error-prone, so we skip it
            return true;

            // Fallback: manually check all other column filters
            if (this.params.api && node) {
                try {
                    // Get all column filters except this one
                    const columns = this.params.api.getColumns();
                    if (columns) {
                        const currentColId = this.columnField || (this.params.colDef && (this.params.colDef.field || this.params.colDef.colId));

                        for (let i = 0; i < columns.length; i++) {
                            const col = columns[i];
                            const colId = col.getColId ? col.getColId() : (col.colId || col.field);

                            // Skip current column
                            if (colId === currentColId) {
                                continue;
                            }

                            // Try different ways to get filter instance
                            let filterInstance = null;

                            // Method 1: Try api.getFilterInstance (if available)
                            if (this.params.api.getFilterInstance && typeof this.params.api.getFilterInstance === 'function') {
                                try {
                                    filterInstance = this.params.api.getFilterInstance(colId);
                                } catch (e) {
                                    // Method not available, try next method
                                }
                            }

                            // Method 2: Try column.getFilterInstance (if available)
                            if (!filterInstance && col.getFilterInstance && typeof col.getFilterInstance === 'function') {
                                try {
                                    filterInstance = col.getFilterInstance();
                                } catch (e) {
                                    // Method not available
                                }
                            }

                            // Method 3: Try accessing filter through column's filter property
                            if (!filterInstance && col.filter) {
                                filterInstance = col.filter;
                            }

                            if (filterInstance) {
                                // Check if filter is active
                                if (filterInstance.isFilterActive && typeof filterInstance.isFilterActive === 'function') {
                                    if (filterInstance.isFilterActive()) {
                                        // Check if row passes this filter
                                        if (filterInstance.doesFilterPass && typeof filterInstance.doesFilterPass === 'function') {
                                            try {
                                                if (!filterInstance.doesFilterPass({ node: node })) {
                                                    return false;
                                                }
                                            } catch (e) {
                                                // Filter pass check failed
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    return true; // Row passes all other filters
                } catch (error) {
                    return true;
                }
            }

            return true; // If no way to check, assume all rows pass
        };

        // Get all row data from the grid
        // First, count all rows (for total counts)
        if (this.params.api && typeof this.params.api.forEachNode === 'function') {
            this.params.api.forEachNode(function(node) {
                if (node && node.data) {
                    try {
                        // AG Grid's filter valueGetter expects just the node object
                        const value = this.valueGetter(node);
                        const items = this.parseComplexValue(value, this.columnField);
                        // Count each individual item
                        items.forEach(function(item) {
                            if (item && item.trim() !== '') {
                                valueCountMap[item] = (valueCountMap[item] || 0) + 1;
                            }
                        });
                    } catch (error) {
                        // Value extraction failed for node
                    }
                }
            }.bind(this));
        }

        // Then, count only displayed rows (which already have other filters applied)
        // This is simpler and more reliable than manually checking filters
        if (this.params.api && typeof this.params.api.forEachNodeAfterFilter === 'function') {
            this.params.api.forEachNodeAfterFilter(function(node) {
                if (node && node.data) {
                    try {
                        // AG Grid's filter valueGetter expects just the node object
                        const value = this.valueGetter(node);
                        // Parse complex values to extract individual items
                        const items = this.parseComplexValue(value, this.columnField);
                        // Count each individual item in displayed rows (after other filters)
                        items.forEach(function(item) {
                            if (item && item.trim() !== '') {
                                availableValueCountMap[item] = (availableValueCountMap[item] || 0) + 1;
                            }
                        });
                    } catch (error) {
                        // Value extraction failed for displayed row
                    }
                }
            }.bind(this));
        } else if (this.params.api && typeof this.params.api.forEachNode === 'function') {
            // Fallback: use checkOtherFilters if forEachNodeAfterFilter not available
            this.params.api.forEachNode(function(node) {
                if (node && node.data) {
                    try {
                        // AG Grid's filter valueGetter expects just the node object
                        const value = this.valueGetter(node);
                        // Parse complex values to extract individual items
                        const items = this.parseComplexValue(value, this.columnField);
                        // Count occurrences in rows passing other filters
                        if (checkOtherFilters(node)) {
                            items.forEach(function(item) {
                                if (item && item.trim() !== '') {
                                    availableValueCountMap[item] = (availableValueCountMap[item] || 0) + 1;
                                }
                            });
                        }
                    } catch (error) {
                        // Value extraction failed
                    }
                }
            }.bind(this));
        }

        // Fallback: if no rows loaded yet, return empty array
        if (Object.keys(valueCountMap).length === 0) {
            // Try to get from rowData if available
            if (this.params.rowData && Array.isArray(this.params.rowData)) {
                this.params.rowData.forEach(function(row) {
                    try {
                        const node = { data: row };
                        // AG Grid's filter valueGetter expects just the node object
                        const value = this.valueGetter(node);
                        // Parse complex values to extract individual items
                        const items = this.parseComplexValue(value, this.columnField);
                        // Count each individual item
                        items.forEach(function(item) {
                            if (item && item.trim() !== '') {
                                valueCountMap[item] = (valueCountMap[item] || 0) + 1;

                                // Count occurrences in rows passing other filters
                                if (checkOtherFilters(node)) {
                                    availableValueCountMap[item] = (availableValueCountMap[item] || 0) + 1;
                                }
                            }
                        });
                    } catch (error) {
                        // Value extraction from rowData failed
                    }
                }.bind(this));
            }
        }

        // Store counts
        this.valueCounts = valueCountMap;
        this.availableValueCounts = availableValueCountMap;

        // Convert to sorted array
        this.uniqueValues = Object.keys(valueCountMap).sort((a, b) => {
            // Natural sort for better UX
            if (typeof a === 'string' && typeof b === 'string') {
                return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
            }
            return a > b ? 1 : a < b ? -1 : 0;
        });

        // Keep list narrowed to the search text when unique values refresh (filterChanged / GUI attach).
        this.filterValues();
    };

    CustomSetFilter.prototype.formatValue = function(value) {
        if (value === null || value === undefined) {
            return '';
        }
        if (typeof value === 'object') {
            return JSON.stringify(value);
        }
        return String(value);
    };

    /**
     * Parse complex values to extract individual items
     * - For Programs: Extract items from array
     * - For Sector/Sub-sector: Split by " / " to get individual items
     */
    CustomSetFilter.prototype.parseComplexValue = function(value, field) {
        if (!value || value === null || value === undefined) {
            return [];
        }

        // Programs column: value is an array
        if (field === 'related_programs_list') {
            if (Array.isArray(value)) {
                return value.map(item => String(item).trim()).filter(item => item !== '');
            }
            // If it's a string, try to parse as comma-separated
            if (typeof value === 'string') {
                return value.split(',').map(item => item.trim()).filter(item => item !== '');
            }
            return [];
        }

        // Tools column (e.g. AI reasoning traces): value is an array of tool names
        if (field === 'tools_used') {
            if (Array.isArray(value)) {
                return value.map(item => String(item).trim()).filter(item => item !== '');
            }
            if (typeof value === 'string') {
                return value.split(',').map(item => item.trim()).filter(item => item !== '');
            }
            return [];
        }

        // Sector and Sub-sector columns: value is a string like "Item1 / Item2 / Item3"
        // The valueGetter returns a string with " / " separator
        if (field === 'sector' || field === 'subsector') {
            if (typeof value === 'string' && value.trim() !== '') {
                // Split by " / " to get individual sector/subsector names
                return value.split(' / ').map(item => item.trim()).filter(item => item !== '');
            }
            // If it's an array, return as is
            if (Array.isArray(value)) {
                return value.map(item => String(item).trim()).filter(item => item !== '');
            }
            // If value is null/undefined/empty, try to get from data directly
            // This handles cases where valueGetter might return empty but data has values
            return [];
        }

        // Default: return as single item array
        return [String(value)];
    };

    CustomSetFilter.prototype.createFilterUI = function() {
        const container = document.createElement('div');
        container.className = 'ag-custom-set-filter';

        // Apply inline styles as fallback to ensure formatting
        container.style.cssText = `
            width: 240px !important;
            max-width: 280px !important;
            min-width: 200px !important;
            padding: 8px !important;
            /* IMPORTANT: inherit app font so Arabic uses Tajawal */
            font-family: inherit !important;
            font-size: 13px !important;
            background: #fff !important;
            border: 1px solid #d3d3d3 !important;
            border-radius: 4px !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15) !important;
            display: flex !important;
            flex-direction: column !important;
            gap: 6px !important;
            box-sizing: border-box !important;
        `;

        // Standard Filter Section (Condition dropdown + Search input)
        const standardFilterSection = document.createElement('div');
        standardFilterSection.className = 'ag-custom-set-filter-standard';
        standardFilterSection.style.cssText = `
            display: flex !important;
            flex-direction: column !important;
            gap: 6px !important;
            padding-bottom: 8px !important;
            border-bottom: 1px solid #e0e0e0 !important;
        `;

        // Condition dropdown
        const conditionContainer = document.createElement('div');
        conditionContainer.className = 'ag-custom-set-filter-condition';
        const conditionSelect = document.createElement('select');
        conditionSelect.className = 'ag-custom-set-filter-condition-select';
        conditionSelect.style.cssText = `
            width: 100% !important;
            padding: 6px 28px 6px 8px !important;
            border: 1px solid #d3d3d3 !important;
            border-radius: 4px !important;
            font-size: 13px !important;
            background: #fff !important;
            color: #000 !important;
            cursor: pointer !important;
            box-sizing: border-box !important;
            appearance: none !important;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23333' d='M6 9L1 4h10z'/%3E%3C/svg%3E") !important;
            background-repeat: no-repeat !important;
            background-position: right 6px center !important;
        `;
        conditionSelect.innerHTML = `
            <option value="equals">Equals</option>
            <option value="notEqual">Not equal</option>
            <option value="contains" selected>Contains</option>
            <option value="notContains">Not contains</option>
            <option value="startsWith">Starts with</option>
            <option value="endsWith">Ends with</option>
            <option value="blank">Blank</option>
            <option value="notBlank">Not blank</option>
        `;
        conditionSelect.value = this.filterCondition;
        conditionSelect.addEventListener('change', this.onConditionChange.bind(this));
        this.conditionSelect = conditionSelect;
        conditionContainer.appendChild(conditionSelect);
        standardFilterSection.appendChild(conditionContainer);

        // Standard filter input (for condition-based filtering)
        const filterInputContainer = document.createElement('div');
        filterInputContainer.className = 'ag-custom-set-filter-input';
        const filterInput = document.createElement('input');
        filterInput.type = 'text';
        filterInput.className = 'ag-custom-set-filter-input-field';
        filterInput.style.cssText = `
            width: 100% !important;
            padding: 6px 8px !important;
            border: 1px solid #d3d3d3 !important;
            border-radius: 4px !important;
            font-size: 13px !important;
            box-sizing: border-box !important;
            background: #fff !important;
            color: #000 !important;
        `;
        filterInput.placeholder = getTranslation('filterByConditionOrSearch', 'Filter by condition or search values...');
        filterInput.value = this.filterValue;
        filterInput.addEventListener('input', this.onFilterInputChange.bind(this));
        this.filterInput = filterInput;
        filterInputContainer.appendChild(filterInput);
        standardFilterSection.appendChild(filterInputContainer);

        container.appendChild(standardFilterSection);

        // Select all checkbox
        const selectAllContainer = document.createElement('div');
        selectAllContainer.className = 'ag-custom-set-filter-select-all';
        selectAllContainer.style.cssText = `
            padding: 6px 8px !important;
            border-bottom: 1px solid #e0e0e0 !important;
            display: flex !important;
            align-items: center !important;
            gap: 4px !important;
            font-weight: 600 !important;
            font-size: 12px !important;
            background: #f8f9fa !important;
            border-radius: 4px 4px 0 0 !important;
        `;
        const selectAllCheckbox = document.createElement('input');
        selectAllCheckbox.type = 'checkbox';
        selectAllCheckbox.className = 'ag-custom-set-filter-checkbox';
        selectAllCheckbox.id = 'select-all-checkbox';
        const isRtl = document.documentElement.getAttribute('dir') === 'rtl';
        if (isRtl) {
            selectAllCheckbox.style.marginLeft = '4px';
            selectAllCheckbox.style.marginRight = '0';
        } else {
            selectAllCheckbox.style.marginRight = '4px';
            selectAllCheckbox.style.marginLeft = '0';
        }
        selectAllCheckbox.addEventListener('change', this.onSelectAllChange.bind(this));
        this.selectAllCheckbox = selectAllCheckbox;

        const selectAllLabel = document.createElement('label');
        selectAllLabel.htmlFor = 'select-all-checkbox';
        selectAllLabel.className = 'ag-custom-set-filter-label';
        selectAllLabel.textContent = getTranslation('selectAll', 'Select All');

        selectAllContainer.appendChild(selectAllCheckbox);
        selectAllContainer.appendChild(selectAllLabel);
        container.appendChild(selectAllContainer);

        // Values list container
        const valuesContainer = document.createElement('div');
        valuesContainer.className = 'ag-custom-set-filter-list';
            valuesContainer.style.cssText = `
            max-height: 200px !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            border: 1px solid #e0e0e0 !important;
            border-top: none !important;
            border-radius: 0 0 4px 4px !important;
            background: #fff !important;
        `;
        this.valuesContainer = valuesContainer;
        container.appendChild(valuesContainer);

        // Buttons container
        const buttonsContainer = document.createElement('div');
        buttonsContainer.className = 'ag-custom-set-filter-buttons';
        buttonsContainer.style.cssText = `
            display: flex !important;
            gap: 4px !important;
            justify-content: flex-end !important;
        `;

        const applyButton = document.createElement('button');
        applyButton.className = 'ag-custom-set-filter-button ag-custom-set-filter-button-primary';
        applyButton.style.cssText = `
            padding: 6px 12px !important;
            border: 1px solid #4a90e2 !important;
            border-radius: 4px !important;
            background: #4a90e2 !important;
            color: #fff !important;
            cursor: pointer !important;
            font-size: 12px !important;
            font-weight: 500 !important;
            min-width: 60px !important;
        `;
        applyButton.textContent = getTranslation('apply', 'Apply');
        applyButton.addEventListener('click', this.onApply.bind(this));

        const clearButton = document.createElement('button');
        clearButton.className = 'ag-custom-set-filter-button';
        clearButton.style.cssText = `
            padding: 6px 12px !important;
            border: 1px solid #d3d3d3 !important;
            border-radius: 4px !important;
            background: #fff !important;
            color: #000 !important;
            cursor: pointer !important;
            font-size: 12px !important;
            font-weight: 500 !important;
            min-width: 60px !important;
        `;
        clearButton.textContent = getTranslation('clear', 'Clear');
        clearButton.addEventListener('click', this.onClear.bind(this));

        const resetButton = document.createElement('button');
        resetButton.className = 'ag-custom-set-filter-button';
        resetButton.style.cssText = `
            padding: 6px 12px !important;
            border: 1px solid #d3d3d3 !important;
            border-radius: 4px !important;
            background: #fff !important;
            color: #000 !important;
            cursor: pointer !important;
            font-size: 12px !important;
            font-weight: 500 !important;
            min-width: 60px !important;
        `;
        resetButton.textContent = getTranslation('reset', 'Reset');
        resetButton.addEventListener('click', this.onReset.bind(this));

        buttonsContainer.appendChild(applyButton);
        buttonsContainer.appendChild(clearButton);
        buttonsContainer.appendChild(resetButton);
        container.appendChild(buttonsContainer);

        // Count display
        const countDisplay = document.createElement('div');
        countDisplay.className = 'ag-custom-set-filter-count';
        countDisplay.style.cssText = `
            padding: 4px 8px !important;
            font-size: 11px !important;
            font-weight: 500 !important;
            color: #666 !important;
            text-align: center !important;
            background: #f8f9fa !important;
            border-radius: 4px !important;
            border: 1px solid #e0e0e0 !important;
            margin-top: 2px !important;
        `;
        this.countDisplay = countDisplay;
        container.appendChild(countDisplay);

        this.eGui = container;
        this.filterValues();
        this.renderValues();
        this.updateCount();
    };

    CustomSetFilter.prototype.onConditionChange = function(event) {
        this.filterCondition = event.target.value;
        this.filterChangedCallback();
    };

    CustomSetFilter.prototype.onFilterInputChange = function(event) {
        this.filterValue = event.target.value;
        // Also filter the unique values list using the same input
        this.filterValues();
        this.renderValues();
        this.updateSelectAllState();
        this.updateCount();
        this.filterChangedCallback();
    };

    CustomSetFilter.prototype.filterValues = function() {
        const searchText = this.filterValue ? this.filterValue.toLowerCase() : '';
        if (!searchText) {
            this.filteredValues = [...this.uniqueValues];
        } else {
            this.filteredValues = this.uniqueValues.filter(value => {
                return String(value).toLowerCase().includes(searchText);
            });
        }
    };

    CustomSetFilter.prototype.renderValues = function() {
        this.valuesContainer.innerHTML = '';

        if (this.filteredValues.length === 0) {
            const noResults = document.createElement('div');
            noResults.className = 'ag-custom-set-filter-no-results';
            noResults.textContent = getTranslation('noValuesFound', 'No values found');
            this.valuesContainer.appendChild(noResults);
            return;
        }

        // Limit display to prevent performance issues
        const maxDisplay = 1000;
        const valuesToShow = this.filteredValues.slice(0, maxDisplay);

        valuesToShow.forEach((value, index) => {
            // Check if value is available (has rows passing other filters)
            const availableCount = this.availableValueCounts && this.availableValueCounts[value] ? this.availableValueCounts[value] : 0;
            const totalCount = this.valueCounts && this.valueCounts[value] ? this.valueCounts[value] : 0;
            const isAvailable = availableCount > 0;

            const itemContainer = document.createElement('div');
            itemContainer.className = 'ag-custom-set-filter-item';
            itemContainer.style.cssText = `
                display: flex !important;
                align-items: center !important;
                padding: 4px 8px !important;
                cursor: ${isAvailable ? 'pointer' : 'not-allowed'} !important;
                transition: background-color 0.15s ease !important;
                border-bottom: 1px solid #f0f0f0 !important;
                opacity: ${isAvailable ? '1' : '0.5'} !important;
            `;

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = 'ag-custom-set-filter-checkbox';
            checkbox.style.cssText = `
                margin-right: 6px !important;
                cursor: ${isAvailable ? 'pointer' : 'not-allowed'} !important;
                width: 14px !important;
                height: 14px !important;
                flex-shrink: 0 !important;
                opacity: ${isAvailable ? '1' : '0.5'} !important;
            `;
            checkbox.id = 'filter-checkbox-' + index;
            checkbox.checked = this.selectedValues.has(value);
            checkbox.disabled = !isAvailable;
            if (isAvailable) {
                checkbox.addEventListener('change', () => this.onValueChange(value, checkbox.checked));
            }

            const label = document.createElement('label');
            label.htmlFor = 'filter-checkbox-' + index;
            label.className = 'ag-custom-set-filter-label';
            label.style.cssText = `
                cursor: ${isAvailable ? 'pointer' : 'not-allowed'} !important;
                user-select: none !important;
                flex: 1 !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
                white-space: nowrap !important;
                color: ${isAvailable ? '#000' : '#999'} !important;
                line-height: 1.4 !important;
                font-size: 12px !important;
            `;
            // Add count next to value - show available count if different from total
            let countText = '';
            if (isAvailable) {
                if (availableCount === totalCount) {
                    countText = '(' + availableCount + ')';
                } else {
                    countText = '(' + availableCount + '/' + totalCount + ')';
                }
            } else {
                countText = '(0/' + totalCount + ')';
            }
            label.innerHTML = value + ' <span style="color: #999; font-size: 11px; margin-left: 4px;">' + countText + '</span>';

            itemContainer.appendChild(checkbox);
            itemContainer.appendChild(label);
            this.valuesContainer.appendChild(itemContainer);
        });

        if (this.filteredValues.length > maxDisplay) {
            const moreResults = document.createElement('div');
            moreResults.className = 'ag-custom-set-filter-more-results';
            const moreCount = this.filteredValues.length - maxDisplay;
            const moreText = getTranslation('moreValuesUseFilter', 'use filter input above to narrow down');
            moreResults.textContent = `... and ${moreCount} more (${moreText})`;
            this.valuesContainer.appendChild(moreResults);
        }
    };

    CustomSetFilter.prototype.onValueChange = function(value, checked) {
        if (checked) {
            this.selectedValues.add(value);
        } else {
            this.selectedValues.delete(value);
        }
        this.updateSelectAllState();
        this.updateCount();
    };

    CustomSetFilter.prototype.onSelectAllChange = function(event) {
        const checked = event.target.checked;

        if (checked) {
            // Select all filtered values
            this.filteredValues.forEach(value => {
                this.selectedValues.add(value);
            });
        } else {
            // Deselect all filtered values
            this.filteredValues.forEach(value => {
                this.selectedValues.delete(value);
            });
        }

        this.renderValues();
        this.updateSelectAllState();
        this.updateCount();
    };

    CustomSetFilter.prototype.updateSelectAllState = function() {
        if (this.filteredValues.length === 0) {
            this.selectAllCheckbox.checked = false;
            this.selectAllCheckbox.indeterminate = false;
            return;
        }

        const selectedInFiltered = this.filteredValues.filter(v => this.selectedValues.has(v)).length;

        if (selectedInFiltered === 0) {
            this.selectAllCheckbox.checked = false;
            this.selectAllCheckbox.indeterminate = false;
        } else if (selectedInFiltered === this.filteredValues.length) {
            this.selectAllCheckbox.checked = true;
            this.selectAllCheckbox.indeterminate = false;
        } else {
            this.selectAllCheckbox.checked = false;
            this.selectAllCheckbox.indeterminate = true;
        }
    };

    CustomSetFilter.prototype.updateCount = function() {
        const total = this.uniqueValues.length;
        const selected = this.selectedValues.size;
        const filtered = this.filteredValues.length;

        let countText = `${selected} of ${total} selected`;
        if (this.filterValue && this.filterValue.trim() !== '') {
            countText += ` (${filtered} matching)`;
        }

        this.countDisplay.textContent = countText;
    };

    CustomSetFilter.prototype.onApply = function() {
        this.filterChangedCallback();
        var close = this.hidePopup || (this.params && this.params.hidePopup);
        if (typeof close === 'function') {
            close();
        }
    };

    CustomSetFilter.prototype.onClear = function() {
        // Clear both standard filter and set filter
        this.selectedValues.clear();
        this.filterValue = '';
        this.filterCondition = 'contains';
        if (this.filterInput) {
            this.filterInput.value = '';
        }
        if (this.conditionSelect) {
            this.conditionSelect.value = 'contains';
        }
        this.filterValues();
        this.renderValues();
        this.updateSelectAllState();
        this.updateCount();
        this.filterChangedCallback();
    };

    CustomSetFilter.prototype.onReset = function() {
        // Reset to show all values (select all)
        this.selectedValues.clear();
        this.uniqueValues.forEach(value => {
            this.selectedValues.add(value);
        });
        this.filterValue = '';
        this.filterCondition = 'contains';
        if (this.filterInput) {
            this.filterInput.value = '';
        }
        if (this.conditionSelect) {
            this.conditionSelect.value = 'contains';
        }
        this.filterValues();
        this.renderValues();
        this.updateSelectAllState();
        this.updateCount();
        this.filterChangedCallback();
    };

    CustomSetFilter.prototype.onFilterChanged = function(event) {
        // When other filters change, refresh available value counts
        // Always refresh when filterChanged event fires (it means another filter changed)
        // Use setTimeout to ensure filter state is updated before we check
        setTimeout(() => {
            this.extractUniqueValues();
            this.renderValues();
            this.updateSelectAllState();
        }, 10);
    };

    CustomSetFilter.prototype.afterGuiAttached = function(params) {
        if (params && typeof params.hidePopup === 'function') {
            this.hidePopup = params.hidePopup;
        }
        // Called when filter UI is attached/opened - refresh available values
        // This ensures values are updated when user opens the filter
        setTimeout(() => {
            this.extractUniqueValues();
            this.renderValues();
            this.updateSelectAllState();
        }, 10);
    };

    CustomSetFilter.prototype.destroy = function() {
        // Remove event listener when filter is destroyed
        if (this.params.api && this.onFilterChangedListener) {
            this.params.api.removeEventListener('filterChanged', this.onFilterChangedListener);
        }
    };

    CustomSetFilter.prototype.getGui = function() {
        return this.eGui;
    };

    CustomSetFilter.prototype.isFilterActive = function() {
        // Filter is active if either standard filter or set filter is active
        const standardFilterActive = this.filterValue && this.filterValue.trim() !== '';
        const setFilterActive = this.selectedValues.size > 0 && this.selectedValues.size < this.uniqueValues.length;
        return standardFilterActive || setFilterActive;
    };

    CustomSetFilter.prototype.doesFilterPass = function(params) {
        // Our valueGetter is normalized to accept a row node
        const node = params && (params.node || params);
        const value = this.valueGetter(node);

        // Parse complex values to extract individual items
        const items = this.parseComplexValue(value, this.columnField);

        // Check standard filter condition
        let passesStandardFilter = true;
        const standardFilterActive = this.filterValue && this.filterValue.trim() !== '';

        if (standardFilterActive) {
            const filterText = this.filterValue.toLowerCase();
            // Check if any of the parsed items match the filter
            passesStandardFilter = items.some(function(item) {
                const itemText = String(item).toLowerCase();
                switch (this.filterCondition) {
                    case 'equals':
                        return itemText === filterText;
                    case 'notEqual':
                        return itemText !== filterText;
                    case 'contains':
                        return itemText.includes(filterText);
                    case 'notContains':
                        return !itemText.includes(filterText);
                    case 'startsWith':
                        return itemText.startsWith(filterText);
                    case 'endsWith':
                        return itemText.endsWith(filterText);
                    case 'blank':
                        return !item || String(item).trim() === '';
                    case 'notBlank':
                        return item && String(item).trim() !== '';
                    default:
                        return itemText.includes(filterText);
                }
            }.bind(this));
        }

        // Check set filter (unique values selection)
        let passesSetFilter = true;
        const setFilterActive = this.selectedValues.size > 0 && this.selectedValues.size < this.uniqueValues.length;

        if (setFilterActive) {
            // Check if any of the parsed items are in the selected values
            passesSetFilter = items.some(function(item) {
                return this.selectedValues.has(String(item));
            }.bind(this));
        }

        // Both filters must pass if both are active (AND logic)
        // If only one is active, use that one
        if (standardFilterActive && setFilterActive) {
            return passesStandardFilter && passesSetFilter;
        } else if (standardFilterActive) {
            return passesStandardFilter;
        } else if (setFilterActive) {
            return passesSetFilter;
        }

        // No filters active
        return true;
    };

    CustomSetFilter.prototype.getModel = function() {
        if (!this.isFilterActive()) {
            return null;
        }
        return {
            filterType: 'customSet',
            condition: this.filterCondition,
            filter: this.filterValue,
            values: Array.from(this.selectedValues)
        };
    };

    CustomSetFilter.prototype.setModel = function(model) {
        if (model) {
            if (model.values) {
                this.selectedValues = new Set(model.values);
            }
            if (model.condition) {
                this.filterCondition = model.condition;
                if (this.conditionSelect) {
                    this.conditionSelect.value = model.condition;
                }
            }
            if (model.filter !== undefined) {
                this.filterValue = model.filter;
                if (this.filterInput) {
                    this.filterInput.value = model.filter;
                }
            }
        } else {
            this.selectedValues.clear();
            this.filterValue = '';
            this.filterCondition = 'contains';
        }
        this.renderValues();
        this.updateSelectAllState();
        this.updateCount();
    };

    CustomSetFilter.prototype.destroy = function() {
        // Cleanup if needed
    };

    // Register the filter component with AG Grid
    if (typeof agGrid !== 'undefined') {
        agGrid.CustomSetFilter = CustomSetFilter;
    }

    // Export for module systems
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = CustomSetFilter;
    }

    if (typeof window !== 'undefined') {
        window.CustomSetFilter = CustomSetFilter;
    }
})();
