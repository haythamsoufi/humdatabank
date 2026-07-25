/**
 * AG Grid Helper — Toolbar, filter persistence, result count, column-visibility button styling
 * @module ag-grid-helper-toolbar
 * Loaded via ag_grid_includes.html (after ag-grid-helper-core.js).
 */
(function(global) {
    'use strict';

    var AgGridHelper = global.AgGridHelper;
    if (!AgGridHelper) {
        throw new Error('ag-grid-helper-toolbar.js: AgGridHelper must be loaded first (ag-grid-helper-core.js)');
    }

        /**
         * Initialize Clear All Filters Button
         * Creates a button that appears when filters are active and clears all filters when clicked
         */
        AgGridHelper.prototype.initializeClearFiltersButton = function() {
            if (!this.gridApi) {
                console.warn('AgGridHelper: gridApi is not available for Clear Filters Button');
                return;
            }
    
            const self = this;
    
            // Create the clear filters button
            const button = document.createElement('button');
            button.className = 'ag-clear-filters-button';
            button.innerHTML = '<i class="fas fa-filter-circle-xmark"></i>';
            button.title = this.getTranslation('clearAllFilters', 'Clear All Filters');
            button.style.display = 'none'; // Hidden by default
    
            // Store reference for later access
            this.clearFiltersButton = button;
    
            // Click handler to clear all filters
            button.addEventListener('click', function() {
                if (self.gridApi && typeof self.gridApi.setFilterModel === 'function') {
                    self.gridApi.setFilterModel(null);
                }
            });
    
            // Function to find and insert the button (may be called with retry)
            const insertClearFiltersButton = function() {
                // Find the placeholder where column visibility button is placed
                const columnVisibilityOptions = self.config.columnVisibilityOptions || {};
                let buttonPlaceholderId = columnVisibilityOptions.buttonPlaceholderId;
    
                // Try to find a suitable placeholder
                let placeholder = null;
                if (buttonPlaceholderId) {
                    placeholder = document.getElementById(buttonPlaceholderId);
                }
    
                // Fallback: look for column-visibility-button-placeholder near this grid
                if (!placeholder && self.gridDiv) {
                    // Check parent containers
                    let searchContainer = self.gridDiv.parentElement;
                    while (searchContainer && searchContainer !== document.body) {
                        placeholder = searchContainer.querySelector('#column-visibility-button-placeholder');
                        if (placeholder) break;
                        placeholder = searchContainer.querySelector('[id*="column-visibility-button-placeholder"]');
                        if (placeholder) break;
                        searchContainer = searchContainer.parentElement;
                    }
                }
    
                // Find the column visibility button container
                let columnVisibilityContainer = null;
    
                if (placeholder) {
                    columnVisibilityContainer = placeholder.querySelector('.ag-column-visibility-button-container');
                }
    
                // Fallback: search near the grid (anywhere in parent tree)
                if (!columnVisibilityContainer && self.gridDiv) {
                    let searchContainer = self.gridDiv.parentElement;
                    while (searchContainer && searchContainer !== document.body) {
                        columnVisibilityContainer = searchContainer.querySelector('.ag-column-visibility-button-container');
                        if (columnVisibilityContainer) break;
                        searchContainer = searchContainer.parentElement;
                    }
                }
    
                // Last fallback: search entire document for button container
                if (!columnVisibilityContainer) {
                    columnVisibilityContainer = document.querySelector('.ag-column-visibility-button-container');
                }
    
                if (columnVisibilityContainer) {
                    // Check if button is already inserted (avoid duplicates)
                    if (columnVisibilityContainer.querySelector('.ag-clear-filters-button')) {
                        return true; // Already inserted
                    }
    
                    // Insert the clear filters button BEFORE the column visibility button (inside same container)
                    const columnVisibilityButton = columnVisibilityContainer.querySelector('.ag-column-visibility-button');
                    if (columnVisibilityButton) {
                        columnVisibilityContainer.insertBefore(button, columnVisibilityButton);
                    } else {
                        // Prepend to container
                        columnVisibilityContainer.insertBefore(button, columnVisibilityContainer.firstChild);
                    }
    
                    // Ensure the container uses flex layout for horizontal alignment
                    columnVisibilityContainer.style.display = 'flex';
                    columnVisibilityContainer.style.alignItems = 'center';
                    columnVisibilityContainer.style.gap = '8px';

                    return true; // Success
                } else if (placeholder) {
                    // Check if button is already inserted
                    if (placeholder.querySelector('.ag-clear-filters-button')) {
                        return true; // Already inserted
                    }
    
                    // Fallback: insert directly into placeholder with flex styling
                    placeholder.style.display = 'flex';
                    placeholder.style.alignItems = 'center';
                    placeholder.style.gap = '8px';
                    placeholder.appendChild(button);

                    return true; // Success
                }

                return false; // Container not found
            };
    
            // Try to insert immediately
            if (!insertClearFiltersButton()) {
                // Retry after a short delay (column visibility manager might not have created container yet)
                setTimeout(function() {
                    if (!insertClearFiltersButton()) {
                        // Final retry with longer delay
                        setTimeout(function() {
                            insertClearFiltersButton();
                        }, 200);
                    }
                }, 50);
            }
    
            // Apply styling to the button
            this.styleClearFiltersButton();
    
            // Listen for filter changes
            this.setupClearFiltersButtonListener();
    
            // Initial check for existing filters
            this.updateClearFiltersButtonVisibility();
        };
    
        /**
         * Get translation for a key with fallback
         * @param {string} key - Translation key
         * @param {string} defaultValue - Default value if translation not found
         * @returns {string} Translated string
         */
        AgGridHelper.prototype.getTranslation = function(key, defaultValue) {
            if (typeof AgGridUtils !== 'undefined' && typeof AgGridUtils.getTranslation === 'function') {
                return AgGridUtils.getTranslation(key, defaultValue);
            }
            return defaultValue;
        };
    
        /**
         * Style the Clear Filters Button
         */
        AgGridHelper.prototype.styleClearFiltersButton = function() {
            if (!this.clearFiltersButton) return;

            const button = this.clearFiltersButton;
            button.classList.add('ag-clear-filters-button');
            if (!button.style.display || button.style.display === '') {
                button.style.display = 'none';
            }
        };
    
        /**
         * Setup listener for filter changes
         */
        AgGridHelper.prototype.setupClearFiltersButtonListener = function() {
            if (!this.gridApi) return;
    
            const self = this;
    
            // Listen for filter changes
            if (typeof this.gridApi.addEventListener === 'function') {
                this.gridApi.addEventListener('filterChanged', function() {
                    self.updateClearFiltersButtonVisibility();
                });
            }
        };
    
        /**
         * Update the visibility of the Clear Filters Button based on active filters
         */
        AgGridHelper.prototype.updateClearFiltersButtonVisibility = function() {
            if (!this.clearFiltersButton || !this.gridApi) return;
    
            // Check if any filters are active
            let hasActiveFilters = false;
    
            if (typeof this.gridApi.isAnyFilterPresent === 'function') {
                hasActiveFilters = this.gridApi.isAnyFilterPresent();
            } else if (typeof this.gridApi.getFilterModel === 'function') {
                const filterModel = this.gridApi.getFilterModel();
                hasActiveFilters = filterModel && Object.keys(filterModel).length > 0;
            }
    
            // Show/hide button based on filter state
            var newDisplay = hasActiveFilters ? 'inline-flex' : 'none';
            this.clearFiltersButton.style.display = newDisplay;
        };
    
        /**
         * Get storage key for persisted filter state.
         * @returns {string}
         */
        AgGridHelper.prototype.getFilterStorageKey = function() {
            return 'ag-grid-filter-model-' + (this.config.templateId || this.config.containerId || 'default');
        };
    
        /**
         * Persist the current filter model for this grid.
         */
        AgGridHelper.prototype.saveCurrentFilterModel = function() {
            if (!this.config.filterPersistence || this._suppressFilterPersistence || !this.gridApi) {
                return;
            }
            if (typeof this.gridApi.getFilterModel !== 'function') {
                return;
            }
    
            try {
                const filterModel = this.gridApi.getFilterModel() || {};
                const hasFilters = Object.keys(filterModel).length > 0;
                if (hasFilters) {
                    localStorage.setItem(this.getFilterStorageKey(), JSON.stringify(filterModel));
                } else {
                    localStorage.removeItem(this.getFilterStorageKey());
                }
            } catch (e) {
                console.warn('AgGridHelper: Failed to persist filter model:', e);
            }
        };
    
        /**
         * Restore the saved filter model for this grid.
         */
        AgGridHelper.prototype.restoreSavedFilterModel = function() {
            if (!this.config.filterPersistence || !this.gridApi || typeof this.gridApi.setFilterModel !== 'function') {
                return false;
            }
    
            let saved = null;
            try {
                saved = localStorage.getItem(this.getFilterStorageKey());
            } catch (e) {
                return false;
            }
            if (!saved) {
                return false;
            }
    
            let filterModel = null;
            try {
                filterModel = JSON.parse(saved);
            } catch (e) {
                try {
                    localStorage.removeItem(this.getFilterStorageKey());
                } catch (removeError) {
                    // Ignore storage cleanup failures
                }
                return false;
            }
    
            if (!filterModel || typeof filterModel !== 'object' || Object.keys(filterModel).length === 0) {
                return false;
            }
    
            const self = this;
            this._suppressFilterPersistence = true;
            try {
                const maybePromise = this.gridApi.setFilterModel(filterModel);
                const finish = function() {
                    self._suppressFilterPersistence = false;
                    self.updateClearFiltersButtonVisibility();
                    self.updateResultCount();
                };
                if (maybePromise && typeof maybePromise.then === 'function') {
                    maybePromise.then(finish).catch(function() {
                        self._suppressFilterPersistence = false;
                    });
                } else {
                    setTimeout(finish, 0);
                }
                return true;
            } catch (e) {
                this._suppressFilterPersistence = false;
                console.warn('AgGridHelper: Failed to restore filter model:', e);
                return false;
            }
        };
    
        /**
         * Save filters whenever the grid filter model changes.
         */
        AgGridHelper.prototype.setupFilterPersistenceListener = function() {
            if (this._filterPersistenceListenerAttached || !this.gridApi || typeof this.gridApi.addEventListener !== 'function') {
                return;
            }
            if (!this.config.filterPersistence) {
                return;
            }
    
            const self = this;
            this.gridApi.addEventListener('filterChanged', function() {
                self.saveCurrentFilterModel();
            });
            this._filterPersistenceListenerAttached = true;
        };
    
    
        /**
         * True when an element is the title/meta block beside a grid toolbar (not the actions column).
         * @param {Element} el
         * @returns {boolean}
         */
        AgGridHelper.isGridHeaderMetaElement = function(el) {
            if (!el || !el.getAttribute) {
                return false;
            }
            if (el.getAttribute('role') === 'dialog' || el.classList.contains('modal-backdrop')) {
                return false;
            }
            if (el.classList && el.classList.contains('ag-grid-header-actions')) {
                return false;
            }
            try {
                if (window.getComputedStyle(el).position === 'fixed') {
                    return false;
                }
            } catch (e) { /* ignore */ }
            if (el.matches && el.matches('[data-ag-grid-title-group], h1, h2, h3, h4')) {
                return true;
            }
            if (el.querySelector && el.querySelector('[data-ag-grid-title-group], h1, h2, h3, h4')) {
                return true;
            }
            if (el.querySelector && el.querySelector('label') && el.querySelector('p')) {
                return true;
            }
            return false;
        };
    
        /**
         * Resolve the column-visibility placeholder for this grid instance.
         * @param {AgGridHelper} helper
         * @returns {HTMLElement|null}
         */
        AgGridHelper.resolveColumnVisibilityPlaceholder = function(helper) {
            if (!helper) {
                return null;
            }
            const columnVisibilityOptions = helper.config.columnVisibilityOptions || {};
            const configuredPlaceholderId = columnVisibilityOptions.buttonPlaceholderId;
            const gridPlaceholderId = helper.gridDiv && helper.gridDiv.getAttribute('data-placeholder-id');
            const placeholderId = configuredPlaceholderId || gridPlaceholderId || 'column-visibility-button-placeholder';
    
            let placeholder = placeholderId ? document.getElementById(placeholderId) : null;
            if (!placeholder && helper.gridDiv) {
                let searchContainer = helper.gridDiv.parentElement;
                while (searchContainer && searchContainer !== document.body) {
                    placeholder = searchContainer.querySelector(
                        '[id*="column-visibility-button-placeholder"], [id*="-colvis"], [id*="col-vis"]'
                    );
                    if (placeholder) {
                        break;
                    }
                    searchContainer = searchContainer.parentElement;
                }
            }
            return placeholder;
        };
    
        /**
         * True when an element contains the grid root (must never receive ag-grid-header-toolbar).
         * @param {Element|null} el
         * @param {HTMLElement|null} gridDiv
         * @returns {boolean}
         */
        AgGridHelper.elementContainsGrid = function(el, gridDiv) {
            return !!(gridDiv && el && el !== gridDiv && typeof el.contains === 'function' && el.contains(gridDiv));
        };
    
        /**
         * Resolve the DOM node that should receive ag-grid-header-toolbar styling.
         * Central rules for standard (ag_grid_container) and custom template layouts.
         *
         * @param {AgGridHelper} helper
         * @param {HTMLElement} placeholder
         * @param {HTMLElement} placeholderParent
         * @returns {HTMLElement|null}
         */
        AgGridHelper.resolveToolbarRoot = function(helper, placeholder, placeholderParent) {
            if (!placeholder || !placeholderParent) {
                return null;
            }
    
            const gridDiv = helper && helper.gridDiv;
            const containsGrid = function(el) {
                return AgGridHelper.elementContainsGrid(el, gridDiv);
            };
    
            // Explicit markers from ag_grid_header_toolbar / ag_grid_container.
            let node = placeholderParent;
            while (node && node !== document.body) {
                if (node.getAttribute && node.getAttribute('data-ag-grid-toolbar') === 'true') {
                    return node;
                }
                if (node.classList && node.classList.contains('ag-grid-header-toolbar')) {
                    return node;
                }
                node = node.parentElement;
            }
    
            const outer = placeholderParent.parentElement;
            if (outer && !containsGrid(outer)) {
                if (outer.getAttribute && outer.getAttribute('data-ag-grid-toolbar') === 'true') {
                    return outer;
                }
                if (outer.classList && outer.classList.contains('ag-grid-header-toolbar')) {
                    return outer;
                }
                const hasMetaSibling = Array.prototype.some.call(outer.children || [], function(child) {
                    return child !== placeholderParent && AgGridHelper.isGridHeaderMetaElement(child);
                });
                if (hasMetaSibling) {
                    return outer;
                }
            }
    
            if (!containsGrid(placeholderParent)) {
                return placeholderParent;
            }
    
            return placeholderParent;
        };
    
        /**
         * Put title/meta, record count, and column-visibility controls on one toolbar row.
         * @param {AgGridHelper} helper
         * @param {HTMLElement} [countEl]
         * @returns {Object|null}
         */
        AgGridHelper.normalizeGridHeaderLayout = function(helper, countEl) {
            const placeholder = AgGridHelper.resolveColumnVisibilityPlaceholder(helper);
            if (!placeholder || !placeholder.parentElement) {
                return null;
            }
    
            const placeholderParent = placeholder.parentElement;
            const headerRow = AgGridHelper.resolveToolbarRoot(helper, placeholder, placeholderParent);
            if (!headerRow || AgGridHelper.elementContainsGrid(headerRow, helper && helper.gridDiv)) {
                return null;
            }
    
            headerRow.classList.add('ag-grid-header-toolbar');
            if (headerRow.getAttribute && headerRow.getAttribute('data-ag-grid-toolbar') !== 'true') {
                headerRow.setAttribute('data-ag-grid-toolbar', 'true');
            }
    
            let metaEl = null;
            Array.prototype.some.call(headerRow.children || [], function(child) {
                if (child === placeholderParent) {
                    return false;
                }
                if (AgGridHelper.isGridHeaderMetaElement(child)) {
                    metaEl = child;
                    return true;
                }
                return false;
            });
            if (metaEl) {
                metaEl.classList.add('ag-grid-header-meta');
            }
    
            placeholderParent.classList.add('ag-grid-header-actions');
            if (placeholderParent.classList) {
                placeholderParent.classList.add('ag-grid-toolbar-row');
            }
    
            if (countEl) {
                const gridId = helper.config.containerId;
                Array.prototype.forEach.call(
                    document.querySelectorAll('.ag-grid-result-count[data-grid-id="' + gridId + '"]'),
                    function(el) {
                        if (el !== countEl) {
                            el.remove();
                        }
                    }
                );
    
                const countMount = metaEl || placeholderParent;
                let mounted = countMount.querySelector('.ag-grid-result-count[data-grid-id="' + gridId + '"]');
                if (mounted && mounted !== countEl) {
                    mounted.remove();
                }
                if (metaEl) {
                    if (countEl.parentElement !== metaEl) {
                        metaEl.appendChild(countEl);
                    }
                } else if (countEl.parentElement !== placeholderParent || countEl.nextElementSibling !== placeholder) {
                    placeholderParent.insertBefore(countEl, placeholder);
                }
            }
    
            return {
                headerRow: headerRow,
                metaEl: metaEl,
                placeholder: placeholder,
                placeholderParent: placeholderParent,
                countEl: countEl || null
            };
        };
    
    
        /**
         * Initialize a live result-count label above the grid.
         */
        AgGridHelper.prototype.initializeResultCount = function() {
            if (!this.gridApi) {
                return;
            }
    
            const self = this;
            const countEl = document.createElement('div');
            countEl.className = 'ag-grid-result-count';
            countEl.setAttribute('data-grid-id', this.config.containerId);
            this.resultCountElement = countEl;
    
            const insertResultCount = function() {
                const layout = AgGridHelper.normalizeGridHeaderLayout(self, countEl);
                if (layout && layout.countEl) {
                    self.resultCountElement = layout.countEl;
                    return true;
                }
    
                if (self.gridDiv && self.gridDiv.parentElement) {
                    const parent = self.gridDiv.parentElement;
                    const existing = parent.querySelector('.ag-grid-result-count[data-grid-id="' + self.config.containerId + '"]');
                    if (existing) {
                        self.resultCountElement = existing;
                        return true;
                    }
                    const countRow = document.createElement('div');
                    countRow.className = 'ag-grid-result-count-row ag-grid-toolbar-row ag-grid-header-toolbar';
                    countRow.setAttribute('data-ag-grid-toolbar', 'true');
                    countRow.appendChild(countEl);
                    parent.insertBefore(countRow, self.gridDiv);
                    return true;
                }
    
                return false;
            };
    
            if (!insertResultCount()) {
                setTimeout(function() {
                    if (!insertResultCount()) {
                        setTimeout(insertResultCount, 200);
                    }
                }, 50);
            }
    
            if (typeof this.gridApi.addEventListener === 'function') {
                this.gridApi.addEventListener('filterChanged', function() {
                    self.updateResultCount();
                });
                this.gridApi.addEventListener('modelUpdated', function() {
                    self.updateResultCount();
                });
            }
    
            setTimeout(function() {
                self.updateResultCount();
            }, 0);
        };
    
        /**
         * Override total row count for the result-count label (e.g. server-side pagination).
         * @param {number|null} total - Total matching rows from the server, or null to clear
         */
        AgGridHelper.prototype.setResultCountTotal = function(total) {
            if (total == null || isNaN(total)) {
                this._resultCountTotal = null;
            } else {
                this._resultCountTotal = Number(total);
            }
            this.updateResultCount();
        };
    
        /**
         * Update the live result-count label.
         */
        AgGridHelper.prototype.updateResultCount = function() {
            if (!this.resultCountElement || !this.gridApi) {
                return;
            }
    
            let displayedCount = 0;
            if (typeof this.gridApi.getDisplayedRowCount === 'function') {
                displayedCount = this.gridApi.getDisplayedRowCount();
            } else if (Array.isArray(this.config.rowData)) {
                displayedCount = this.config.rowData.length;
            }
    
            let totalCount = displayedCount;
            if (this._resultCountTotal != null && !isNaN(this._resultCountTotal)) {
                totalCount = this._resultCountTotal;
            } else if (Array.isArray(this.config.rowData)) {
                totalCount = this.config.rowData.length;
            }
    
            const showingText = this.getTranslation('showing', 'Showing');
            const ofText = this.getTranslation('of', 'of');
            const recordText = this.getTranslation('record', 'record');
            const recordsText = this.getTranslation('records', 'records');
            const noun = totalCount === 1 ? recordText : recordsText;
    
            if (displayedCount === totalCount) {
                this.resultCountElement.textContent = totalCount + ' ' + noun;
            } else {
                this.resultCountElement.textContent = showingText + ' ' + displayedCount + ' ' + ofText + ' ' + totalCount + ' ' + noun;
            }
        };
    
        /**
         * Header filter gestures: the label can overlap the filter icon before/after
         * sizeColumnsToFit, so pointerdown may hit the button while click lands on the label.
         * CSS (pointer-events on label) is the primary fix; this handler stops document-level
         * close on the opening click and opens the filter when click did not reach the button.
         */
        AgGridHelper.prototype.setupHeaderFilterClickBridge = function() {
            if (!this.gridDiv || !this.gridApi || this._headerFilterClickBridgeAttached) {
                return;
            }
            this._headerFilterClickBridgeAttached = true;

            var self = this;
            var filterGestureColId = null;
            var filterGestureTimer = null;

            function getFilterButtonContext(ev) {
                var button = ev.target.closest && ev.target.closest('.ag-header-cell-filter-button');
                if (!button) {
                    return null;
                }
                var headerCell = button.closest && button.closest('.ag-header-cell');
                if (!headerCell) {
                    return null;
                }
                return {
                    button: button,
                    headerCell: headerCell,
                    colId: headerCell.getAttribute('col-id')
                };
            }

            function clearFilterGesture() {
                filterGestureColId = null;
                if (filterGestureTimer) {
                    clearTimeout(filterGestureTimer);
                    filterGestureTimer = null;
                }
            }

            function openFilterIfClosed(colId) {
                if (!colId || self.isFilterMenuOpen()) {
                    return;
                }
                if (typeof self.gridApi.showColumnFilter !== 'function') {
                    return;
                }
                try {
                    self.gridApi.showColumnFilter(colId);
                } catch (e1) {
                    try {
                        var column = typeof self.gridApi.getColumn === 'function'
                            ? self.gridApi.getColumn(colId)
                            : null;
                        if (column) {
                            self.gridApi.showColumnFilter(column);
                        }
                    } catch (e2) {
                        // Non-fatal
                    }
                }
            }

            this.gridDiv.addEventListener('click', function(ev) {
                var ctx = getFilterButtonContext(ev);
                if (ctx) {
                    ev.stopPropagation();
                    clearFilterGesture();
                    return;
                }

                if (!filterGestureColId) {
                    return;
                }

                var headerCell = ev.target.closest && ev.target.closest('.ag-header-cell');
                var colId = headerCell && headerCell.getAttribute('col-id');
                if (colId !== filterGestureColId) {
                    return;
                }

                ev.stopPropagation();
                var gestureColId = filterGestureColId;
                clearFilterGesture();
                openFilterIfClosed(gestureColId);
            }, false);

            this.gridDiv.addEventListener('pointerdown', function(ev) {
                if (ev.button !== 0) {
                    return;
                }
                var ctx = getFilterButtonContext(ev);
                if (!ctx) {
                    clearFilterGesture();
                    return;
                }
                filterGestureColId = ctx.colId;
                if (filterGestureTimer) {
                    clearTimeout(filterGestureTimer);
                }
                filterGestureTimer = setTimeout(function() {
                    filterGestureTimer = null;
                    if (!filterGestureColId) {
                        return;
                    }
                    var pendingColId = filterGestureColId;
                    clearFilterGesture();
                    openFilterIfClosed(pendingColId);
                }, 120);
            }, true);
        };

        /**
         * Ensure filter popup input spacing to avoid icon overlap.
         */
        AgGridHelper.prototype.setupFilterMenuInputSpacing = function() {
            if (this._filterMenuDebugObserver) {
                return;
            }
    
            const parsePx = function(value, fallback) {
                if (!value) {
                    return fallback;
                }
                const parsed = parseFloat(value);
                return Number.isFinite(parsed) ? parsed : fallback;
            };
    
            const applyFilterMenuSpacing = function(menuEl) {
                if (!menuEl) {
                    return;
                }
    
                const inputs = menuEl.querySelectorAll('.ag-filter-filter .ag-input-field-input');
                if (!inputs.length) {
                    return;
                }
    
                const menuStyles = window.getComputedStyle(menuEl);
                const iconSize = parsePx(menuStyles.getPropertyValue('--ag-icon-size'), 16);
                const gridSize = parsePx(menuStyles.getPropertyValue('--ag-grid-size'), 8);
                const paddingValue = (iconSize + gridSize * 2) + 'px';
    
                const isRtl = menuEl.classList.contains('ag-rtl') ||
                    document.documentElement.getAttribute('dir') === 'rtl';
    
                inputs.forEach(function(input) {
                    if (isRtl) {
                        input.style.paddingLeft = gridSize + 'px';
                        input.style.paddingRight = paddingValue;
                    } else {
                        input.style.paddingLeft = paddingValue;
                        input.style.paddingRight = gridSize + 'px';
                    }
                });
            };
    
            const observer = new MutationObserver(function(mutations) {
                mutations.forEach(function(mutation) {
                    mutation.addedNodes.forEach(function(node) {
                        if (!(node instanceof HTMLElement)) {
                            return;
                        }
                        if (node.classList && node.classList.contains('ag-filter-menu')) {
                            applyFilterMenuSpacing(node);
                            return;
                        }
                        const menu = node.querySelector && node.querySelector('.ag-filter-menu');
                        if (menu) {
                            applyFilterMenuSpacing(menu);
                        }
                    });
                });
            });
    
            observer.observe(document.body, { childList: true, subtree: true });
            this._filterMenuDebugObserver = observer;
    
            // Apply spacing to any existing filter menus immediately
            document.querySelectorAll('.ag-filter-menu').forEach(function(menuEl) {
                applyFilterMenuSpacing(menuEl);
            });
        };
    
        /**
         * Detect if any column filter popup is currently open.
         * CustomSetFilter uses .ag-custom-set-filter; built-in filters use .ag-filter-menu.
         * @returns {boolean}
         */
        AgGridHelper.prototype.isFilterMenuOpen = function() {
            if (document.querySelector('.ag-filter-menu, .ag-custom-set-filter')) {
                return true;
            }
            var popups = document.querySelectorAll('.ag-popup, .ag-popup-child');
            for (var i = 0; i < popups.length; i++) {
                var popup = popups[i];
                if (popup.querySelector(
                    '.ag-filter-menu, .ag-custom-set-filter, .ag-filter, .ag-custom-set-filter-list, .ag-set-filter-list'
                )) {
                    return true;
                }
            }
            return false;
        };
    
        /**
         * Move column-visibility button into the template toolbar placeholder.
         * Visual styling is handled by ag-column-visibility-manager.css.
         */
        AgGridHelper.prototype.styleColumnVisibilityButton = function() {
            const self = this;
            const columnVisibilityOptions = self.config.columnVisibilityOptions || {};
            const buttonPlaceholderId = columnVisibilityOptions.buttonPlaceholderId;

            function ensureIconOnly(button) {
                if (!button) return;
                const columnsIcon = button.querySelector('i.fas.fa-columns');
                if (!columnsIcon) return;
                const textNodes = Array.from(button.childNodes).filter(function(node) {
                    return node.nodeType === 3 && node.textContent.trim() !== '';
                });
                if (textNodes.length > 0) {
                    const title = button.getAttribute('title');
                    button.innerHTML = columnsIcon.outerHTML;
                    if (title) {
                        button.setAttribute('title', title);
                    }
                }
            }

            function moveButtonToPlaceholder(buttonContainer, placeholderId) {
                if (!buttonContainer || !placeholderId) return;
                const placeholder = document.getElementById(placeholderId);
                if (!placeholder || buttonContainer.parentElement === placeholder) return;
                placeholder.appendChild(buttonContainer);
            }

            function findButtonElements() {
                let button = null;
                let buttonContainer = null;

                if (buttonPlaceholderId) {
                    const placeholder = document.getElementById(buttonPlaceholderId);
                    if (placeholder) {
                        button = placeholder.querySelector('.ag-column-visibility-button');
                        buttonContainer = placeholder.querySelector('.ag-column-visibility-button-container');
                    }
                }

                if (!button && self.gridDiv) {
                    let searchContainer = self.gridDiv.parentElement;
                    while (searchContainer && searchContainer !== document.body) {
                        buttonContainer = searchContainer.querySelector('.ag-column-visibility-button-container');
                        if (buttonContainer) {
                            button = buttonContainer.querySelector('.ag-column-visibility-button');
                            break;
                        }
                        searchContainer = searchContainer.parentElement;
                    }
                }

                return { button: button, buttonContainer: buttonContainer };
            }

            function applyPlacement() {
                const found = findButtonElements();
                if (found.buttonContainer && buttonPlaceholderId) {
                    moveButtonToPlaceholder(found.buttonContainer, buttonPlaceholderId);
                }
                const placed = findButtonElements();
                if (placed.button) {
                    placed.button.classList.add('ag-grid-toolbar-btn');
                    ensureIconOnly(placed.button);
                }
            }

            applyPlacement();
            setTimeout(applyPlacement, 150);
            setTimeout(applyPlacement, 500);
        };

})(typeof window !== 'undefined' ? window : this);
