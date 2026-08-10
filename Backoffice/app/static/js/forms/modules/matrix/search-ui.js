/** Matrix search dropdown UI for dynamic row selection. */
import { debugLog, debugWarn } from '../debug.js';
import { _t } from './shared.js';

export const matrixSearchUiMixin = {

/**
 * Helper: Find results container for a given fieldId (works with repeat sections)
 */
_findResultsContainer(fieldId) {
    debugLog('matrix-handler', '[FIND RESULTS] Looking for results container', { fieldId });

    // First try by ID directly
    let resultsContainer = document.getElementById(`matrix-search-results-${fieldId}`);
    debugLog('matrix-handler', '[FIND RESULTS] Direct ID search', {
        searchedId: `matrix-search-results-${fieldId}`,
        found: !!resultsContainer,
        foundId: resultsContainer?.id
    });

    if (!resultsContainer) {
        // Find via matrix container (works with repeat sections where IDs are transformed)
        const matrix = this.matrices.get(fieldId);
        debugLog('matrix-handler', '[FIND RESULTS] Checking matrix map', {
            fieldId,
            hasMatrix: !!matrix,
            hasContainer: !!(matrix && matrix.container),
            containerId: matrix?.container?.id
        });

        if (matrix && matrix.container) {
            // The results container is a direct child of .matrix-container (position:absolute).
            // For repeat sections the ID is transformed, so fall back to a query.
            resultsContainer = matrix.container.querySelector('[id*="matrix-search-results-"]');

            debugLog('matrix-handler', '[FIND RESULTS] Container query result', {
                found: !!resultsContainer,
                foundId: resultsContainer?.id
            });
        }
    }

    return resultsContainer;
}

/**
 * Helper: Find search input for a given fieldId (works with repeat sections)
 */,


/**
 * Helper: Find search input for a given fieldId (works with repeat sections)
 */
_findSearchInput(fieldId) {
    // First try by ID directly
    let searchInput = document.getElementById(`matrix-row-search-${fieldId}`);

    if (!searchInput) {
        // Find via matrix container (works with repeat sections where IDs are transformed)
        const matrix = this.matrices.get(fieldId);
        if (matrix && matrix.container) {
            searchInput = matrix.container.querySelector('.matrix-add-row-interface input[type="text"]');
        }
    }

    return searchInput;
}

/**
 * Show search dropdown
 */,


/**
 * Show search dropdown
 */
showSearchDropdown(searchInput) {
    const fieldId = searchInput.dataset.fieldId;
    const resultsContainer = fieldId ? this._findResultsContainer(fieldId) : null;

    if (resultsContainer) {
        this._positionAndShowDropdown(searchInput, resultsContainer);
        if (!searchInput.value.trim()) {
            this.loadInitialSearchResults(searchInput);
        }
    } else {
        debugWarn('matrix-handler', '[SHOW DROPDOWN] Results container not found', { fieldId });
    }
}

/**
 * Position and show dropdown (helper method).
 *
 * The results container is position:absolute inside the position:relative
 * .matrix-container, so it grows the page height instead of overlaying
 * content as a fixed overlay.  The user can scroll the page to see both
 * the matrix and the full list at the same time.
 */,


/**
 * Position and show dropdown (helper method).
 *
 * The results container is position:absolute inside the position:relative
 * .matrix-container, so it grows the page height instead of overlaying
 * content as a fixed overlay.  The user can scroll the page to see both
 * the matrix and the full list at the same time.
 */
_positionAndShowDropdown(searchInput, resultsContainer) {
    const matrixContainer = searchInput.closest('.matrix-container');
    if (!matrixContainer) {
        resultsContainer.classList.remove('hidden');
        return;
    }

    const inputRect = searchInput.getBoundingClientRect();
    const containerRect = matrixContainer.getBoundingClientRect();

    // Coordinates are relative to .matrix-container (which is position:relative).
    // Always place below the search input — never flip above.
    const top = inputRect.bottom - containerRect.top + 2;
    const left = inputRect.left - containerRect.left;

    resultsContainer.style.position = 'absolute';
    resultsContainer.style.top = `${top}px`;
    resultsContainer.style.left = `${left}px`;
    resultsContainer.style.width = `${inputRect.width}px`;
    resultsContainer.style.bottom = '';
    resultsContainer.style.maxHeight = '';
    resultsContainer.style.overflowY = '';

    resultsContainer.classList.remove('hidden');
}

/**
 * Re-render dropdown results after a selection (keeps dropdown open)
 */,


/**
 * Re-render dropdown results after a selection (keeps dropdown open)
 */
_refreshDropdownResults(searchInput, fieldId) {
    const resultsContainer = fieldId ? this._findResultsContainer(fieldId) : null;
    if (resultsContainer) {
        this._positionAndShowDropdown(searchInput, resultsContainer);
    }
    // Re-run the same search the user had active; fall back to loading all.
    if (searchInput.value.trim()) {
        this.handleSearchInput(searchInput);
    } else {
        this.loadInitialSearchResults(searchInput);
    }
}

/**
 * Hide search dropdown
 */,


/**
 * Hide search dropdown
 */
hideSearchDropdown(searchInput) {
    const fieldId = searchInput.dataset.fieldId;
    const resultsContainer = fieldId ? this._findResultsContainer(fieldId) : null;
    if (resultsContainer) {
        resultsContainer.classList.add('hidden');
    }
}

/**
 * Reposition visible dropdowns on scroll/resize.
 *
 * With position:absolute inside the matrix-container the dropdown follows
 * the page scroll automatically.  We only need to recalculate left/top/width
 * (e.g. after a window resize changes the layout).
 */,


/**
 * Reposition visible dropdowns on scroll/resize.
 *
 * With position:absolute inside the matrix-container the dropdown follows
 * the page scroll automatically.  We only need to recalculate left/top/width
 * (e.g. after a window resize changes the layout).
 */
repositionVisibleDropdowns() {
    const visibleDropdowns = document.querySelectorAll('[id*="matrix-search-results-"]:not(.hidden)');

    visibleDropdowns.forEach(dropdown => {
        const matrixContainer = dropdown.closest('.matrix-container');
        if (!matrixContainer) return;

        const searchInput = matrixContainer.querySelector('.matrix-add-row-interface input[type="text"]');
        if (!searchInput) return;

        const inputRect = searchInput.getBoundingClientRect();
        const containerRect = matrixContainer.getBoundingClientRect();

        dropdown.style.top = `${inputRect.bottom - containerRect.top + 2}px`;
        dropdown.style.left = `${inputRect.left - containerRect.left}px`;
        dropdown.style.width = `${inputRect.width}px`;
    });
}

/**
 * Load initial search results when dropdown opens
 */,


/**
 * Load initial search results when dropdown opens
 */
async loadInitialSearchResults(searchInput) {
    const fieldId = searchInput.dataset.fieldId;
    const lookupListId = searchInput.dataset.lookupListId;
    const displayColumn = searchInput.dataset.displayColumn;
    const filters = JSON.parse(searchInput.dataset.filters || '[]');

    if (!lookupListId || !displayColumn) {
        this.showDropdownMessage(fieldId, _t('Matrix configuration is incomplete'));
        return;
    }

    this.showDropdownMessage(fieldId, _t('Loading...'), true);
    await this.searchListOptions(fieldId, lookupListId, displayColumn, filters, '');
}

/**
 * Handle search input for row selection
 */,


/**
 * Handle search input for row selection
 */
async handleSearchInput(searchInput) {
    const fieldId = searchInput.dataset.fieldId;
    const lookupListId = searchInput.dataset.lookupListId;
    const displayColumn = searchInput.dataset.displayColumn;
    const filters = JSON.parse(searchInput.dataset.filters || '[]');
    const searchTerm = searchInput.value.trim();

    // Show dropdown if hidden
    this.showSearchDropdown(searchInput);

    // Debounce search
    clearTimeout(this.searchTimeout);
    this.searchTimeout = setTimeout(() => {
        this.searchListOptions(fieldId, lookupListId, displayColumn, filters, searchTerm);
    }, 300);
}

/**
 * Build a stable cache key for a matrix search-row lookup configuration.
 * Same lookup_list_id + display_column + filters + plugin/assignment context
 * always returns the same underlying rows for the lifetime of the page.
 */,


/**
 * Render search results in dropdown
 */
renderSearchResults(fieldId, options) {
    const resultsContainer = this._findResultsContainer(fieldId);
    const fieldIdStr = String(fieldId || '');

    if (!resultsContainer) {
        debugWarn('matrix-handler', `Results container not found for field ${fieldId}`);
        return;
    }

    if (options.length === 0) {
        this.showDropdownMessage(fieldId, _t('No options found'));
        return;
    }

    // Snapshot/merge collapsed groups so state survives async refreshes (e.g. loading message).
    const collapsedGroups = new Set(this.collapsedDropdownGroups.get(fieldIdStr) || []);
    resultsContainer.querySelectorAll('.matrix-group-header').forEach(header => {
        const groupItems = header.nextElementSibling;
        if (groupItems && groupItems.classList.contains('matrix-group-items') && groupItems.classList.contains('hidden')) {
            collapsedGroups.add((header.querySelector('span')?.textContent ?? '').trim());
        }
    });
    this.collapsedDropdownGroups.set(fieldIdStr, collapsedGroups);

    resultsContainer.replaceChildren();

    const matrix = this.matrices.get(fieldId);
    const groupByColumn = matrix?.config?.group_by_column;
    const groupDropdownEnabled = matrix?.config?.group_dropdown_enabled !== false;

    // Build a reference to the live table body so we can mark already-added rows.
    const matrixContainer = matrix?.container || document.querySelector(`[data-field-id="${String(fieldId || '')}"]`);
    let tbody = document.getElementById(`matrix-tbody-${fieldId}`);
    if (!tbody && matrixContainer) {
        tbody = matrixContainer.querySelector('tbody[id*="matrix-tbody-"]') || matrixContainer.querySelector('tbody');
    }

    const createOptionEl = (option) => {
        const optionData = option.data || {};
        if (!optionData._id && !optionData.id && option.id) {
            optionData._id = option.id;
            optionData.id = option.id;
        }
        const item = document.createElement('div');
        item.className = 'p-3 hover:bg-blue-50 cursor-pointer border-b border-gray-100 matrix-search-option';
        item.dataset.fieldId = String(fieldId || '');
        item.dataset.optionValue = String(option.value || '');
        try { item.dataset.optionData = JSON.stringify(optionData); }
        catch (e) { item.dataset.optionData = JSON.stringify({}); }

        const title = document.createElement('div');
        title.className = 'font-medium text-sm flex items-center';
        title.textContent = String(option.value || '');
        item.appendChild(title);

        if (option.description) {
            const desc = document.createElement('div');
            desc.className = 'text-xs text-gray-600 mt-1';
            desc.textContent = String(option.description || '');
            item.appendChild(desc);
        }

        // Mark rows that are already in the matrix table.
        if (tbody) {
            const optionId = String(optionData._id || optionData.id || '');
            const label = String(option.value || '');
            const alreadyAdded = Array.from(tbody.querySelectorAll('tr.matrix-data-row')).some(tr =>
                (optionId && tr.dataset.rowId === optionId) || tr.dataset.rowLabel === label
            );
            if (alreadyAdded) {
                item.classList.add('opacity-50', 'pointer-events-none');
                const checkIcon = document.createElement('i');
                checkIcon.className = 'fas fa-check text-green-600 ml-2 flex-shrink-0';
                title.appendChild(checkIcon);
            }
        }

        return item;
    };

    if (groupByColumn && groupDropdownEnabled) {
        const groups = new Map();
        options.forEach(option => {
            const groupVal = (option.data && option.data[groupByColumn]) || 'Other';
            if (!groups.has(groupVal)) groups.set(groupVal, []);
            groups.get(groupVal).push(option);
        });

        groups.forEach((groupOptions, groupName) => {
            const groupNameKey = String(groupName || '').trim();
            const header = document.createElement('div');
            header.className = 'px-3 py-2 bg-gray-100 text-xs font-semibold text-gray-700 cursor-pointer flex items-center justify-between sticky top-0 matrix-group-header';
            header.innerHTML = `<span>${this._escapeHtml(groupName)}</span><i class="fas fa-chevron-down text-gray-400 transition-transform duration-200"></i>`;
            const groupContainer = document.createElement('div');
            groupContainer.className = 'matrix-group-items';
            groupOptions.forEach(option => groupContainer.appendChild(createOptionEl(option)));

            header.addEventListener('click', () => {
                const isHidden = groupContainer.classList.toggle('hidden');
                header.querySelector('i').classList.toggle('rotate-180', !isHidden);
                const currentCollapsedGroups = this.collapsedDropdownGroups.get(fieldIdStr) || new Set();
                if (isHidden) {
                    currentCollapsedGroups.add(groupNameKey);
                } else {
                    currentCollapsedGroups.delete(groupNameKey);
                }
                this.collapsedDropdownGroups.set(fieldIdStr, currentCollapsedGroups);
            });

            resultsContainer.appendChild(header);
            resultsContainer.appendChild(groupContainer);
        });

        // Restore group collapse state from before the re-render.
        if (collapsedGroups.size > 0) {
            resultsContainer.querySelectorAll('.matrix-group-header').forEach(header => {
                const label = (header.querySelector('span')?.textContent ?? '').trim();
                if (collapsedGroups.has(label)) {
                    header.nextElementSibling?.classList.add('hidden');
                    header.querySelector('i')?.classList.remove('rotate-180');
                }
            });
        }
    } else {
        options.forEach(option => resultsContainer.appendChild(createOptionEl(option)));
    }

    // Append "Other (please specify)..." when allow_other is enabled
    const matrixForOther = this.matrices.get(fieldId);
    const searchInputForOther = this._findSearchInput(fieldId);
    if (matrixForOther?.config?.allow_other || searchInputForOther?.dataset?.allowOther === 'true') {
        const separator = document.createElement('div');
        separator.className = 'border-t border-gray-200';
        resultsContainer.appendChild(separator);

        const otherItem = document.createElement('div');
        otherItem.className = 'p-3 hover:bg-blue-50 cursor-pointer matrix-other-option';
        otherItem.dataset.fieldId = String(fieldId || '');

        const title = document.createElement('div');
        title.className = 'text-sm text-gray-500 italic flex items-center';
        const icon = document.createElement('i');
        icon.className = 'fas fa-plus-circle mr-2 text-gray-400';
        title.appendChild(icon);
        title.appendChild(document.createTextNode(_t('Other (please specify)...')));
        otherItem.appendChild(title);
        resultsContainer.appendChild(otherItem);
    }
},


_escapeHtml(str) {
    if (str == null) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/**
 * Show message in dropdown
 */,


/**
 * Show message in dropdown
 */
showDropdownMessage(fieldId, message, isLoading = false) {
    const resultsContainer = this._findResultsContainer(fieldId);
    if (resultsContainer) {
        resultsContainer.replaceChildren();
        const wrap = document.createElement('div');
        wrap.className = 'p-3 text-gray-500 text-sm text-center';
        if (isLoading) {
            const icon = document.createElement('i');
            icon.className = 'fas fa-spinner fa-spin mr-2';
            wrap.appendChild(icon);
        }
        wrap.appendChild(document.createTextNode(String(message || '')));
        resultsContainer.appendChild(wrap);
    }
},

/**
 * Handle "Other (please specify)" option click: replace the option
 * with an inline text input so the user can type a custom row name.
 */
handleOtherRowOption(otherItem) {
    const fieldId = otherItem.dataset.fieldId;
    const container = document.querySelector(`.matrix-container[data-field-id="${fieldId}"]`);
    if (container && !this._canEditMatrix(container)) return;

    const inputWrapper = document.createElement('div');
    inputWrapper.className = 'p-3 border-t border-gray-200';

    const inputRow = document.createElement('div');
    inputRow.className = 'flex items-center gap-2';

    const textInput = document.createElement('input');
    textInput.type = 'text';
    textInput.className = 'flex-1 px-2 py-1 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500';
    textInput.placeholder = _t('Enter custom row name...');

    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'px-2 py-1 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md shrink-0';
    addBtn.textContent = _t('Add');

    const addCustomRow = () => {
        const label = textInput.value.trim();
        if (!label) return;
        this.addDynamicRow(fieldId, label, { _id: label, id: label }, label, false);
        setTimeout(() => {
            this.sortMatrixRows(fieldId);
            this.applyManualRowHighlighting(fieldId);
            this.updateLegendVisibility(fieldId);
        }, 50);
        const resultsContainer = this._findResultsContainer(fieldId);
        const searchInput = this._findSearchInput(fieldId);
        if (resultsContainer) resultsContainer.classList.add('hidden');
        if (searchInput) searchInput.value = '';
    };

    addBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        addCustomRow();
    });

    textInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            e.stopPropagation();
            addCustomRow();
        }
        if (e.key === 'Escape') {
            const resultsContainer = this._findResultsContainer(fieldId);
            if (resultsContainer) resultsContainer.classList.add('hidden');
        }
    });

    inputRow.appendChild(textInput);
    inputRow.appendChild(addBtn);
    inputWrapper.appendChild(inputRow);
    otherItem.replaceWith(inputWrapper);
    textInput.focus();
},

/**
 * Select row option from search results
 */


/**
 * Select row option from search results
 */
selectRowOption(optionItem) {
    const fieldId = optionItem.dataset.fieldId;
    const container = document.querySelector(`.matrix-container[data-field-id="${fieldId}"]`);
    if (container && !this._canEditMatrix(container)) return;

    const optionValue = optionItem.dataset.optionValue;
    const optionData = JSON.parse(optionItem.dataset.optionData);

    // Get row ID from optionData using helper method
    const rowId = this.extractRowId(optionData, optionValue);

    // Debug logging
    debugLog('matrix-handler', `Selecting row option:`, {
        fieldId,
        optionValue,
        optionData,
        extractedRowId: rowId,
        has_id: !!optionData?.id,
        has__id: !!optionData?._id
    });

    // Add row to matrix with ID (manually added, so isAutoLoaded=false)
    debugLog('matrix-handler', '[SELECT ROW OPTION] About to call addDynamicRow', {
        fieldId,
        optionValue,
        rowId,
        optionDataKeys: Object.keys(optionData)
    });
    this.addDynamicRow(fieldId, optionValue, optionData, rowId, false);
    debugLog('matrix-handler', '[SELECT ROW OPTION] addDynamicRow completed');

    // Sort rows alphabetically after manual add, then reposition dropdown after reflow
    setTimeout(() => {
        this.sortMatrixRows(fieldId);
        this.applyManualRowHighlighting(fieldId);
        this.updateLegendVisibility(fieldId);
        // Wait for the browser to reflow the taller table before repositioning
        requestAnimationFrame(() => this.repositionVisibleDropdowns());
    }, 50);

    // Mark selected item visually and keep dropdown open for multi-select
    optionItem.classList.add('opacity-50', 'pointer-events-none');
    optionItem.insertAdjacentHTML('beforeend', '<i class="fas fa-check text-green-600 ml-auto"></i>');

    const searchInput = this._findSearchInput(fieldId);
    if (searchInput) {
        // Do NOT clear the input — preserve the user's search term so the
        // dropdown re-renders the same filtered list after selection.
        this._refreshDropdownResults(searchInput, fieldId);
        // Re-focus so the blur handler's active-element check passes and the
        // dropdown stays open for multi-select without requiring another click.
        searchInput.focus();
    }
}

/**
 * Add dynamic row to matrix
 * @param {string} fieldId - Matrix field ID
 * @param {string} rowLabel - Row label/name
 * @param {Object} rowData - Row data object
 * @param {string|null} rowId - Row ID (optional)
 * @param {boolean} isAutoLoaded - Whether this row was auto-loaded (default: false)
 */,
};
