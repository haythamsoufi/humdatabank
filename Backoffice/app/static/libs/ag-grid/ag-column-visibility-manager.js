/**
 * AG Grid Column Visibility Manager
 * Manages column show/hide functionality with template-specific persistence
 * Features:
 * - Show/hide columns dynamically
 * - Save column visibility state per template
 * - Restore saved column visibility on page load
 * - Column visibility panel UI
 * - Export/import column configurations
 */

(function() {
    'use strict';

    /**
     * Ensure common ag-grid translations are available in i18n-json
     * This function populates missing translation keys in the i18n-json element
     * by checking if they exist in the page's translation system
     * IMPORTANT: This function only adds missing keys and never overwrites existing translations
     */
    function ensureCommonTranslations() {
        try {
            const i18nEl = document.getElementById('i18n-json');
            if (!i18nEl) {
                return;
            }

            // Check if i18n-json has content (might be empty if script hasn't executed yet)
            const currentContent = i18nEl.textContent.trim();
            if (!currentContent || currentContent === '') {
                // Script hasn't executed yet, skip for now
                return;
            }

            let i18n = {};
            try {
                i18n = JSON.parse(currentContent);
            } catch (e) {
                // If parsing fails, don't modify anything
                return;
            }

            // Common ag-grid translation keys that should be available
            const commonKeys = {
                'columns': 'Columns',
                'showHideColumns': 'Show/Hide Columns',
                'columnVisibility': 'Column Visibility',
                'searchColumns': 'Search columns...',
                'resetToDefault': 'Reset to Default',
                'showAll': 'Show All',
                'columnCannotBeHidden': 'This column cannot be hidden',
                'noColumnsFound': 'No columns found',
                'clearAllFilters': 'Clear All Filters',
                'pinColumn': 'Pin column',
                'unpinColumn': 'Unpin column',
                'columnCannotBeUnpinned': 'This column cannot be unpinned'
            };

            let updated = false;
            // Check each common key and add ONLY if missing (never overwrite existing)
            for (const key in commonKeys) {
                // Check if key exists and has a non-empty value
                // Only add if key is completely missing (not just empty)
                const keyExists = (key in i18n);
                const hasValue = keyExists && i18n[key] !== null && i18n[key] !== undefined && String(i18n[key]).trim() !== '';

                // Only add the key if it doesn't exist at all (not if it exists but is empty)
                // This ensures we never overwrite existing translations, even if they're empty strings
                if (!keyExists) {
                    // Try to get from window.agGridTranslations first
                    if (window.agGridTranslations && window.agGridTranslations[key]) {
                        i18n[key] = window.agGridTranslations[key];
                        updated = true;
                    } else {
                        // Use default English value only if key is truly missing
                        i18n[key] = commonKeys[key];
                        updated = true;
                    }
                }
                // If key exists (even with empty value), we don't touch it - preserve existing translations
            }

            // Update i18n-json element ONLY if we added missing keys (never overwrite existing)
            if (updated) {
                i18nEl.textContent = JSON.stringify(i18n);
            }
        } catch (e) {
            // Silently fail - translations will fall back to defaults
            console.warn('ensureCommonTranslations: Error ensuring translations', e);
        }
    }

    /**
     * Get cached i18n translations object
     * @returns {Object|null} Parsed i18n object or null
     */
    function getCachedI18n() {
        // Return cached version if available
        if (getCachedI18n._cache !== null && getCachedI18n._cacheTime) {
            // Cache is valid for 1 second (in case i18n-json is updated)
            if (Date.now() - getCachedI18n._cacheTime < 1000) {
                return getCachedI18n._cache;
            }
        }

        // Try to parse i18n-json
        try {
            const i18nEl = document.getElementById('i18n-json');
            if (i18nEl && i18nEl.textContent) {
                const i18n = JSON.parse(i18nEl.textContent);
                getCachedI18n._cache = i18n;
                getCachedI18n._cacheTime = Date.now();
                return i18n;
            }
        } catch (e) {
            // Ignore parsing errors
        }

        return null;
    }
    getCachedI18n._cache = null;
    getCachedI18n._cacheTime = null;

    /**
     * Translation utility for ag-grid components
     * Reads translations from window.agGridTranslations or falls back to English
     * @param {string} key - Translation key
     * @param {string} defaultValue - Default English value
     * @returns {string} Translated string
     */
    function getTranslation(key, defaultValue) {
        // Ensure common translations are available (only runs once, and only when DOM is ready)
        if (!getTranslation._initialized) {
            // Only run if DOM is ready
            if (document.readyState === 'loading') {
                // DOM not ready yet, wait for it
                document.addEventListener('DOMContentLoaded', function() {
                    ensureCommonTranslations();
                    getTranslation._initialized = true;
                    getCachedI18n._cache = null;
                    getCachedI18n._cacheTime = null;
                });
            } else {
                // DOM is ready, run immediately
                ensureCommonTranslations();
                getTranslation._initialized = true;
                // Clear cache after ensuring translations so we get fresh data
                getCachedI18n._cache = null;
                getCachedI18n._cacheTime = null;
            }
        }

        // Try to get from window.agGridTranslations (set by templates) - highest priority
        if (typeof AgGridUtils !== 'undefined' && typeof AgGridUtils.getTranslation === 'function') {
            return AgGridUtils.getTranslation(key, defaultValue);
        }

        // Fallback to default English value
        return defaultValue;
    }

    // Initialize flag for ensureCommonTranslations
    getTranslation._initialized = false;

    /**
     * Normalize AG Grid pinned values for localStorage (false/true -> null/'left')
     * @param {string|boolean|null|undefined} pinned
     * @returns {string|null}
     */
    function normalizePinnedValue(pinned) {
        if (pinned === 'left' || pinned === 'right') {
            return pinned;
        }
        if (pinned === true) {
            return 'left';
        }
        return null;
    }

    /**
     * Column Visibility Manager
     * @param {Object} gridApi - AG Grid API instance
     * @param {string} templateId - Unique identifier for the template/page
     * @param {Object} options - Configuration options
     */
    function ColumnVisibilityManager(gridApi, templateId, options) {
        this.gridApi = gridApi;
        this.templateId = templateId || 'default';
        this.options = Object.assign({
            storageKey: 'ag-grid-column-visibility',
            persistOnChange: true,
            showPanelButton: true,
            panelPosition: 'top-right',
            enableExport: true,
            enableReset: true,
            enablePin: true,
            defaultPinSide: 'left'
        }, options || {});

        this.columnState = {};
        this.panelElement = null;
        this.panelButton = null;
        this.isPanelVisible = false;
        this._suppressPersist = false;
        this._initialStateFinalized = false;
        this._pinChangeInProgress = false;
        this._columnPinnedHandler = null;

        this.init();
    }

    ColumnVisibilityManager.prototype.init = function() {
        // Suppress writes while the grid (and page onReady hooks) apply default column state
        this._suppressPersist = true;

        // Load saved column visibility + pin state from localStorage
        this.loadSavedState();

        // Apply saved state to grid
        this.applyColumnState();

        // Listen for column visibility / pin changes
        if (this.options.persistOnChange) {
            this._onColumnStateChanged = this.onColumnVisibilityChanged.bind(this);
            this.gridApi.addEventListener('columnVisible', this._onColumnStateChanged);
            this.gridApi.addEventListener('columnPinned', this._onColumnStateChanged);
        }

        // Create panel button if enabled
        if (this.options.showPanelButton) {
            this.createPanelButton();
        }

        // Fallback when grids are not created via AgGridHelper.create (no finishInitialColumnState call)
        const self = this;
        setTimeout(function() {
            self.finishInitialColumnState();
        }, 300);
    };

    /**
     * Normalize pinned value (instance wrapper)
     */
    ColumnVisibilityManager.prototype.normalizePinnedValue = function(pinned) {
        return normalizePinnedValue(pinned);
    };

    /**
     * Pinned state to apply for a column (saved preference + lockPinned defaults)
     */
    ColumnVisibilityManager.prototype.resolvePinnedForApply = function(colDef, saved) {
        if (typeof AgGridHelper !== 'undefined' && AgGridHelper.shouldDisableColumnPinning()) {
            if (AgGridHelper.isActionsColumn(colDef)) {
                return 'right';
            }
            return null;
        }
        if (colDef.lockPinned && colDef.pinned) {
            return this.normalizePinnedValue(colDef.pinned);
        }
        if (saved && Object.prototype.hasOwnProperty.call(saved, 'pinned')) {
            return this.normalizePinnedValue(saved.pinned);
        }
        return null;
    };

    /**
     * Write columnState to localStorage (when persistence is enabled)
     */
    ColumnVisibilityManager.prototype.writeColumnStateToStorage = function() {
        if (this._suppressPersist || !this.options.persistOnChange) {
            return;
        }
        try {
            localStorage.setItem(this.getStorageKey(), JSON.stringify(this.columnState));
        } catch (e) {
            console.warn('Failed to write column state to storage:', e);
        }
    };

    /**
     * Update one column's saved pin and persist immediately
     */
    ColumnVisibilityManager.prototype.updateStoredColumnPin = function(field, pinned) {
        const apiToUse = this.getApiToUse();
        const column = apiToUse.getColumn ? apiToUse.getColumn(field) : null;
        const normalizedPin = this.normalizePinnedValue(pinned);

        if (!this.columnState[field]) {
            this.columnState[field] = {
                visible: column && column.isVisible ? column.isVisible() : true
            };
        }
        this.columnState[field].pinned = normalizedPin;
        this.writeColumnStateToStorage();
        return normalizedPin;
    };

    /**
     * After a pin change, re-order selection column then sync full state from the grid
     */
    ColumnVisibilityManager.prototype.finalizeColumnPinChange = function() {
        const self = this;
        this.ensureSelectionColumnFirst();
        window.setTimeout(function() {
            if (self.options.persistOnChange) {
                self.saveCurrentState();
            }
            self._pinChangeInProgress = false;
            if (self.panelElement && self.isPanelVisible) {
                self.updatePanel();
            }
        }, 50);
    };

    /**
     * Saved pin for a column id (used when merging with pinActionsColumn)
     */
    ColumnVisibilityManager.prototype.getSavedPin = function(colId) {
        const saved = this.columnState && this.columnState[colId];
        if (!saved || !Object.prototype.hasOwnProperty.call(saved, 'pinned')) {
            return null;
        }
        return this.normalizePinnedValue(saved.pinned);
    };

    /**
     * Re-apply persisted column state after grid/page onReady hooks (e.g. pinActionsColumn).
     * Enables localStorage persistence for pins as well as visibility.
     */
    ColumnVisibilityManager.prototype.finishInitialColumnState = function() {
        if (this._initialStateFinalized) {
            return;
        }
        this._initialStateFinalized = true;
        this.loadSavedState();
        this.applyColumnState();
        this._suppressPersist = false;
        this.ensureSelectionColumnFirst();
        this.saveCurrentState();
    };

    /**
     * Get storage key for this template
     */
    ColumnVisibilityManager.prototype.getStorageKey = function() {
        return `${this.options.storageKey}-${this.templateId}`;
    };

    /**
     * Load saved column visibility state from localStorage
     */
    ColumnVisibilityManager.prototype.loadSavedState = function() {
        try {
            const saved = localStorage.getItem(this.getStorageKey());
            if (saved) {
                this.columnState = JSON.parse(saved);
            } else {
                // Initialize with current column state
                this.saveCurrentState();
            }
        } catch (e) {
            console.warn('Failed to load column visibility state:', e);
            this.saveCurrentState();
        }
    };

    /**
     * Save current column visibility state to localStorage
     */
    ColumnVisibilityManager.prototype.saveCurrentState = function() {
        if (this._suppressPersist) {
            return;
        }

        try {
            const apiToUse = this.getApiToUse();
            const allColumns = apiToUse.getColumns ? apiToUse.getColumns() : null;
            if (!allColumns) return;

            const state = {};
            allColumns.forEach(function(column) {
                const colDef = column.getColDef();
                const field = colDef.field || colDef.colId;
                let pinned = column.getPinned ? column.getPinned() : null;
                if (this.isSelectionCheckboxColumn(column)) {
                    pinned = null;
                } else if (colDef.lockPinned && colDef.pinned) {
                    pinned = colDef.pinned;
                }
                state[field] = {
                    visible: column.isVisible(),
                    pinned: normalizePinnedValue(pinned),
                    width: column.getActualWidth(),
                    sort: column.getSort(),
                    sortIndex: column.getSortIndex()
                };
            }.bind(this));

            this.columnState = state;
            localStorage.setItem(this.getStorageKey(), JSON.stringify(state));
        } catch (e) {
            console.warn('Failed to save column visibility state:', e);
        }
    };

    /**
     * Apply saved column state to grid
     */
    ColumnVisibilityManager.prototype.applyColumnState = function() {
        if (!this.columnState || Object.keys(this.columnState).length === 0) {
            return;
        }

        try {
            const apiToUse = this.getApiToUse();
            const columnState = [];
            const allColumns = apiToUse.getColumns ? apiToUse.getColumns() : null;

            if (!allColumns) return;

            allColumns.forEach(function(column) {
                const colDef = column.getColDef();
                const field = colDef.field || colDef.colId;
                const saved = this.columnState[field];

                if (saved) {
                    const pinned = this.isSelectionCheckboxColumn(column)
                        ? null
                        : this.resolvePinnedForApply(colDef, saved);
                    var width = saved.width || colDef.width;
                    var minW = colDef.minWidth;
                    if (typeof AgGridHelper !== 'undefined' &&
                        AgGridHelper.isActionsColumn(colDef) &&
                        !AgGridHelper.isCoarsePointerDevice()) {
                        minW = AgGridHelper.getActionsColumnDesktopMinWidth(colDef);
                    }
                    if (minW && (!width || width < minW)) {
                        width = minW;
                    }
                    columnState.push({
                        colId: field,
                        hide: !saved.visible,
                        pinned: pinned,
                        width: width,
                        sort: saved.sort || null,
                        sortIndex: saved.sortIndex !== undefined ? saved.sortIndex : null
                    });
                }
            }.bind(this));

            if (columnState.length > 0 && apiToUse.applyColumnState) {
                apiToUse.applyColumnState({
                    state: columnState,
                    applyOrder: true
                });
                this.ensureSelectionColumnFirst();
                if (typeof AgGridHelper !== 'undefined' && typeof AgGridHelper.enforceColumnMinWidths === 'function') {
                    AgGridHelper.enforceColumnMinWidths(apiToUse);
                }
            }
        } catch (e) {
            console.warn('Failed to apply column state:', e);
        }
    };

    /**
     * Handle column visibility or pin change
     */
    ColumnVisibilityManager.prototype.onColumnVisibilityChanged = function() {
        if (this._suppressPersist || this._pinChangeInProgress) {
            return;
        }
        // Defer so AG Grid finishes applying column state before we read it back
        const self = this;
        window.setTimeout(function() {
            if (self._pinChangeInProgress) {
                return;
            }
            self.saveCurrentState();
            if (self.panelElement && self.isPanelVisible) {
                self.updatePanel();
            }
        }, 0);
    };

    /**
     * Show/hide a column
     */
    ColumnVisibilityManager.prototype.setColumnVisible = function(field, visible) {
        const apiToUse = this.getApiToUse();

        // Use applyColumnState as the primary method (most reliable)
        let success = false;

        try {
            const allColumns = apiToUse.getColumns ? apiToUse.getColumns() : [];
            if (allColumns && allColumns.length > 0) {
                const self = this;
                const columnState = allColumns.map(function(col) {
                    const colDef = col.getColDef();
                    const colField = colDef.field || colDef.colId;
                    const isCurrentlyVisible = col.isVisible ? col.isVisible() : true;
                    const currentPinned = col.getPinned ? self.normalizePinnedValue(col.getPinned()) : null;
                    return {
                        colId: colField,
                        hide: colField === field ? !visible : !isCurrentlyVisible,
                        pinned: currentPinned
                    };
                });
                if (apiToUse.applyColumnState && typeof apiToUse.applyColumnState === 'function') {
                    apiToUse.applyColumnState({ state: columnState, applyOrder: false });
                    success = true;
                }
            }
        } catch (e) {
            // applyColumnState failed
        }

        // Fallback 1: Try setColumnVisible API method
        if (!success && typeof apiToUse.setColumnVisible === 'function') {
            try {
                apiToUse.setColumnVisible(field, visible);
                success = true;
            } catch (e) {
                // setColumnVisible failed
            }
        }

        // Fallback 2: Get column and set visibility directly
        if (!success) {
            try {
                const column = apiToUse.getColumn ? apiToUse.getColumn(field) : null;
                if (column && typeof column.setVisible === 'function') {
                    column.setVisible(visible);
                    success = true;
                }
            } catch (e) {
                // column.setVisible failed
            }
        }

        if (this.options.persistOnChange) {
            this.saveCurrentState();
        }
    };

    /**
     * Resolve the grid API (supports createGrid wrapper)
     */
    ColumnVisibilityManager.prototype.getApiToUse = function() {
        return (this.gridApi.api && typeof this.gridApi.api.applyColumnState === 'function')
            ? this.gridApi.api
            : this.gridApi;
    };

    /**
     * Whether a column is the row-selection checkbox column
     */
    ColumnVisibilityManager.prototype.isSelectionCheckboxColumn = function(column) {
        if (typeof AgGridHelper !== 'undefined' && typeof AgGridHelper.isSelectionCheckboxColumn === 'function') {
            return AgGridHelper.isSelectionCheckboxColumn(column);
        }
        return false;
    };

    /**
     * Keep selection checkbox column(s) at the beginning when columns are pinned
     */
    ColumnVisibilityManager.prototype.ensureSelectionColumnFirst = function() {
        if (typeof AgGridHelper !== 'undefined' && typeof AgGridHelper.ensureSelectionColumnFirst === 'function') {
            const apiToUse = this.getApiToUse();
            let gridDiv = null;
            if (apiToUse && apiToUse.getGridElement && typeof apiToUse.getGridElement === 'function') {
                gridDiv = apiToUse.getGridElement();
            } else if (apiToUse && apiToUse.eGridDiv) {
                gridDiv = apiToUse.eGridDiv;
            }
            AgGridHelper.ensureSelectionColumnFirst(apiToUse, gridDiv);
        }
    };

    /**
     * Preferred pin side for a column (colDef default or manager option)
     */
    ColumnVisibilityManager.prototype.getPreferredPinSide = function(colDef) {
        if (colDef && colDef.pinned === 'right') {
            return 'right';
        }
        if (this.options.defaultPinSide === 'right') {
            return 'right';
        }
        return 'left';
    };

    /**
     * Pin or unpin a column
     * @param {string} field - Column field / colId
     * @param {string|null} pinned - 'left', 'right', or null to unpin
     */
    ColumnVisibilityManager.prototype.setColumnPinned = function(field, pinned) {
        if (typeof AgGridHelper !== 'undefined' && AgGridHelper.shouldDisableColumnPinning()) {
            return;
        }
        const apiToUse = this.getApiToUse();
        const column = apiToUse.getColumn ? apiToUse.getColumn(field) : null;
        if (column && this.isSelectionCheckboxColumn(column)) {
            return;
        }

        this._pinChangeInProgress = true;
        const normalizedPin = this.updateStoredColumnPin(field, pinned);
        const self = this;
        let finalized = false;

        function finishPinChange() {
            if (finalized) {
                return;
            }
            finalized = true;
            if (self.gridApi && self._columnPinnedHandler) {
                self.gridApi.removeEventListener('columnPinned', self._columnPinnedHandler);
                self._columnPinnedHandler = null;
            }
            self.finalizeColumnPinChange();
        }

        if (this.gridApi && typeof this.gridApi.addEventListener === 'function') {
            this._columnPinnedHandler = finishPinChange;
            this.gridApi.addEventListener('columnPinned', this._columnPinnedHandler);
        }

        try {
            if (apiToUse.applyColumnState && typeof apiToUse.applyColumnState === 'function') {
                apiToUse.applyColumnState({
                    state: [{ colId: field, pinned: normalizedPin }],
                    applyOrder: false
                });
            }
        } catch (e) {
            console.warn('ColumnVisibilityManager: setColumnPinned failed', e);
            self._pinChangeInProgress = false;
            finishPinChange();
            return;
        }

        window.setTimeout(finishPinChange, 150);
    };

    /**
     * Toggle column pinned state
     */
    ColumnVisibilityManager.prototype.toggleColumnPinned = function(field) {
        if (typeof AgGridHelper !== 'undefined' && AgGridHelper.shouldDisableColumnPinning()) {
            return;
        }
        const apiToUse = this.getApiToUse();
        const column = apiToUse.getColumn ? apiToUse.getColumn(field) : null;
        if (!column) {
            return;
        }

        if (this.isSelectionCheckboxColumn(column)) {
            return;
        }

        const colDef = column.getColDef();
        if (colDef.lockPinned) {
            return;
        }

        const currentPinned = column.getPinned ? column.getPinned() : null;
        const isPinned = !!(currentPinned && currentPinned !== false);
        const newPinned = isPinned ? null : this.getPreferredPinSide(colDef);
        this.setColumnPinned(field, newPinned);
    };

    /**
     * Toggle column visibility
     */
    ColumnVisibilityManager.prototype.toggleColumn = function(field) {
        const column = this.gridApi.getColumn(field);
        if (column) {
            const isVisible = column.isVisible();
            this.setColumnVisible(field, !isVisible);
        }
    };

    /**
     * Show all columns
     */
    ColumnVisibilityManager.prototype.showAllColumns = function() {
        // Handle both Grid API and createGrid API
        const apiToUse = (this.gridApi.api && typeof this.gridApi.api.getColumns === 'function')
            ? this.gridApi.api
            : this.gridApi;

        const allColumns = apiToUse.getColumns ? apiToUse.getColumns() : [];
        if (allColumns && allColumns.length > 0) {
            // Build column state array for applyColumnState
            const columnState = [];

            allColumns.forEach(function(column) {
                const colDef = column.getColDef();
                const field = colDef.field || colDef.colId;

                // Only show if not locked
                if (!colDef.lockVisible) {
                    columnState.push({
                        colId: field,
                        hide: false  // Show all columns
                    });
                }
            });

            // Apply the column state using applyColumnState (most reliable method)
            if (columnState.length > 0 && apiToUse.applyColumnState && typeof apiToUse.applyColumnState === 'function') {
                try {
                    apiToUse.applyColumnState({
                        state: columnState,
                        applyOrder: false
                    });
                } catch (e) {
                    console.warn('ColumnVisibilityManager: applyColumnState failed in showAllColumns', e);
                    // Fallback: set visibility directly
                    allColumns.forEach(function(column) {
                        const colDef = column.getColDef();
                        if (!colDef.lockVisible) {
                            if (column.setVisible) {
                                column.setVisible(true);
                            }
                        }
                    });
                }
            } else {
                // Fallback: set visibility directly
                allColumns.forEach(function(column) {
                    const colDef = column.getColDef();
                    if (!colDef.lockVisible) {
                        if (column.setVisible) {
                            column.setVisible(true);
                        }
                    }
                });
            }

            this.saveCurrentState();
            if (this.panelElement && this.isPanelVisible) {
                this.updatePanel();
            }
        }
    };

    /**
     * Hide all columns except specified ones
     */
    ColumnVisibilityManager.prototype.hideAllColumnsExcept = function(fields) {
        const allColumns = this.gridApi.getColumns();
        if (allColumns) {
            allColumns.forEach(function(column) {
                const colDef = column.getColDef();
                const field = colDef.field || colDef.colId;
                if (!colDef.lockVisible && !fields.includes(field)) {
                    column.setVisible(false);
                }
            });
            this.saveCurrentState();
            if (this.panelElement && this.isPanelVisible) {
                this.updatePanel();
            }
        }
    };

    /**
     * Reset to default column visibility
     */
    ColumnVisibilityManager.prototype.resetToDefault = function() {
        localStorage.removeItem(this.getStorageKey());
        this.columnState = {};

        // Handle both Grid API and createGrid API
        const apiToUse = (this.gridApi.api && typeof this.gridApi.api.getColumns === 'function')
            ? this.gridApi.api
            : this.gridApi;

        // Reset all columns to their default visibility (from colDef)
        const allColumns = apiToUse.getColumns ? apiToUse.getColumns() : [];
        if (allColumns && allColumns.length > 0) {
            // Build column state array for applyColumnState
            const columnState = [];

            allColumns.forEach(function(column) {
                const colDef = column.getColDef();
                const field = colDef.field || colDef.colId;

                // Only reset if not locked
                if (!colDef.lockVisible) {
                    // Check if column has hide property in colDef (default visibility)
                    const shouldBeVisible = colDef.hide !== true;
                    const defaultPinned = this.normalizePinnedValue(colDef.pinned);
                    columnState.push({
                        colId: field,
                        hide: !shouldBeVisible,
                        pinned: defaultPinned
                    });
                }
            }.bind(this));

            // Apply the column state using applyColumnState (most reliable method)
            if (columnState.length > 0 && apiToUse.applyColumnState && typeof apiToUse.applyColumnState === 'function') {
                try {
                    apiToUse.applyColumnState({
                        state: columnState,
                        applyOrder: false
                    });
                } catch (e) {
                    console.warn('ColumnVisibilityManager: applyColumnState failed in resetToDefault', e);
                    // Fallback: set visibility directly
                    allColumns.forEach(function(column) {
                        const colDef = column.getColDef();
                        if (!colDef.lockVisible) {
                            const shouldBeVisible = colDef.hide !== true;
                            if (column.setVisible) {
                                column.setVisible(shouldBeVisible);
                            }
                        }
                    });
                }
            } else {
                // Fallback: set visibility directly
                allColumns.forEach(function(column) {
                    const colDef = column.getColDef();
                    if (!colDef.lockVisible) {
                        const shouldBeVisible = colDef.hide !== true;
                        if (column.setVisible) {
                            column.setVisible(shouldBeVisible);
                        }
                    }
                });
            }
        }

        // Save the new state
        this.saveCurrentState();

        // Update the panel to reflect changes
        if (this.panelElement && this.isPanelVisible) {
            this.updatePanel();
        }
    };

    /**
     * Export column configuration
     */
    ColumnVisibilityManager.prototype.exportConfiguration = function() {
        const config = {
            templateId: this.templateId,
            timestamp: new Date().toISOString(),
            columnState: this.columnState
        };

        const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `ag-grid-columns-${this.templateId}-${Date.now()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    /**
     * Import column configuration
     */
    ColumnVisibilityManager.prototype.importConfiguration = function(file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            try {
                const config = JSON.parse(e.target.result);
                if (config.columnState) {
                    this.columnState = config.columnState;
                    localStorage.setItem(this.getStorageKey(), JSON.stringify(this.columnState));
                    this.applyColumnState();
                    if (this.panelElement && this.isPanelVisible) {
                        this.updatePanel();
                    }
                    if (window.showAlert) window.showAlert('Column configuration imported successfully!', 'success');
                    else console.log('Column configuration imported');
                }
            } catch (err) {
                if (window.showAlert) window.showAlert('Failed to import configuration: ' + err.message, 'error');
                else console.error('Failed to import:', err.message);
            }
        }.bind(this);
        reader.readAsText(file);
    };

    /**
     * Create panel button
     */
    ColumnVisibilityManager.prototype.createPanelButton = function() {
        const button = document.createElement('button');
        button.className = 'ag-column-visibility-button';

        // Helper function to update button text with translations
        // By default, show only icon (text can be added via CSS/JS if needed)
        const updateButtonText = function() {
            const showHideText = getTranslation('showHideColumns', 'Show/Hide Columns');
            // Create button with icon only (no text by default)
            button.innerHTML = '<i class="fas fa-columns"></i>';
            button.title = showHideText;
        };

        // Set initial content (icon only)
        updateButtonText();

        // Update button after a short delay to ensure translations are loaded
        // This handles cases where i18n-json might load asynchronously
        const self = this;
        setTimeout(function() {
            // Clear cache to force re-reading i18n-json
            getCachedI18n._cache = null;
            getCachedI18n._cacheTime = null;
            // Re-ensure translations (in case they weren't available before)
            ensureCommonTranslations();
            // Update button (still icon only)
            updateButtonText();
        }, 100);

        button.addEventListener('click', function() {
            self.togglePanel();
        });

        this.panelButton = button;

        // Insert button into grid container or specified position
        let gridContainer = null;
        let containerElement = null; // The actual container div (with data-placeholder-id)

        // First, try to use buttonPlaceholderId if explicitly provided (highest priority)
        if (this.options.buttonPlaceholderId) {
            const placeholder = document.getElementById(this.options.buttonPlaceholderId);
            if (placeholder) {
                const buttonContainer = document.createElement('div');
                buttonContainer.className = 'ag-column-visibility-button-container';
                buttonContainer.appendChild(button);
                placeholder.appendChild(buttonContainer);
                return;
            }
        }

        // Second, try to find the container by containerId if provided
        if (this.options.containerId) {
            containerElement = document.getElementById(this.options.containerId);
            if (containerElement) {
                // Check if this container has the data-placeholder-id attribute
                const placeholderId = containerElement.getAttribute('data-placeholder-id');
                if (placeholderId) {
                    const placeholder = document.getElementById(placeholderId);
                    if (placeholder) {
                        const buttonContainer = document.createElement('div');
                        buttonContainer.className = 'ag-column-visibility-button-container';
                        buttonContainer.appendChild(button);
                        placeholder.appendChild(buttonContainer);
                        return;
                    }
                }
            }
        }

        // Try different ways to get grid element (for compatibility with different AG Grid APIs)
        if (typeof this.gridApi.getGridElement === 'function') {
            gridContainer = this.gridApi.getGridElement();
        } else if (this.gridApi.api && typeof this.gridApi.api.getGridElement === 'function') {
            gridContainer = this.gridApi.api.getGridElement();
        } else if (this.gridApi.eGridDiv) {
            // For createGrid API, the grid element might be stored in eGridDiv
            gridContainer = this.gridApi.eGridDiv;
        } else if (this.gridApi.gridElement) {
            gridContainer = this.gridApi.gridElement;
        }

        // If we have containerElement but not gridContainer, use containerElement
        if (!gridContainer && containerElement) {
            gridContainer = containerElement;
        }

        // Fallback: try to find grid element by common IDs
        if (!gridContainer) {
            gridContainer = document.querySelector('#dataExplorationGrid') ||
                          document.querySelector('#indicatorBankGrid') ||
                          document.querySelector('.ag-theme-alpine') ||
                          document.querySelector('[role="grid"]');
        }

        // Try to find a placeholder element first (for better positioning)
        // First, check if grid container or its parent has a data-placeholder-id attribute
        let placeholder = null;
        if (gridContainer) {
            // Check the grid container itself
            let checkElement = gridContainer;
            // If gridContainer is a child (like .ag-root-wrapper), find the parent container
            if (!checkElement.getAttribute('data-placeholder-id') && checkElement.parentElement) {
                // Traverse up to find the container with data-placeholder-id
                let parent = checkElement.parentElement;
                while (parent && parent !== document.body) {
                    const placeholderId = parent.getAttribute('data-placeholder-id');
                    if (placeholderId) {
                        placeholder = document.getElementById(placeholderId);
                        if (placeholder) break;
                    }
                    parent = parent.parentElement;
                }
            } else {
                const placeholderId = checkElement.getAttribute('data-placeholder-id');
                if (placeholderId) {
                    placeholder = document.getElementById(placeholderId);
                }
            }

            // If not found, look for placeholder in the same parent container
            if (!placeholder && gridContainer.parentElement) {
                // Look for any placeholder with "column-visibility-button-placeholder" in the ID
                const parentPlaceholders = gridContainer.parentElement.querySelectorAll('[id*="column-visibility-button-placeholder"]');
                if (parentPlaceholders.length > 0) {
                    placeholder = parentPlaceholders[0];
                }
            }
        }

        // Fallback to global placeholder search
        if (!placeholder) {
            placeholder = document.querySelector('#column-visibility-button-placeholder');
        }

        if (placeholder) {
            const buttonContainer = document.createElement('div');
            buttonContainer.className = 'ag-column-visibility-button-container';
            buttonContainer.appendChild(button);
            placeholder.appendChild(buttonContainer);
            return;
        }

        // Insert button before the grid container (not overlapping)
        if (gridContainer && gridContainer.parentElement) {
            const container = gridContainer.parentElement;
            const buttonContainer = document.createElement('div');
            buttonContainer.className = 'ag-column-visibility-button-container';
            buttonContainer.appendChild(button);
            // Insert before the grid container
            container.insertBefore(buttonContainer, gridContainer);
        } else if (gridContainer && gridContainer.previousElementSibling) {
            // If no parent, try inserting before grid
            const buttonContainer = document.createElement('div');
            buttonContainer.className = 'ag-column-visibility-button-container';
            buttonContainer.appendChild(button);
            if (gridContainer.parentElement) {
                gridContainer.parentElement.insertBefore(buttonContainer, gridContainer);
            }
        }
    };

    /**
     * Toggle visibility panel
     */
    ColumnVisibilityManager.prototype.togglePanel = function() {
        if (this.isPanelVisible) {
            this.hidePanel();
        } else {
            this.showPanel();
        }
    };

    /**
     * Show visibility panel
     */
    ColumnVisibilityManager.prototype.showPanel = function() {
        if (!this.panelElement) {
            this.createPanel();
        }
        // Show backdrop
        if (this.backdrop) {
            this.backdrop.style.display = 'block';
            this.backdrop.classList.add('active');
        }
        // Show panel (use setProperty with 'important' to override CSS and any previous hide state)
        this.panelElement.style.setProperty('display', 'flex', 'important');
        this.panelElement.style.setProperty('visibility', 'visible', 'important');
        this.panelElement.style.opacity = '1';
        this.isPanelVisible = true;
        this.updatePanel();
    };

    /**
     * Hide visibility panel
     */
    ColumnVisibilityManager.prototype.hidePanel = function() {
        // Hide backdrop
        if (this.backdrop) {
            this.backdrop.classList.remove('active');
            this.backdrop.style.display = 'none';
        }
        // Hide panel (use setProperty with 'important' to override CSS .ag-column-visibility-panel { display: flex !important } )
        if (this.panelElement) {
            this.panelElement.style.setProperty('display', 'none', 'important');
            this.panelElement.style.setProperty('visibility', 'hidden', 'important');
            this.isPanelVisible = false;
        }
    };

    /**
     * Create visibility panel UI
     */
    ColumnVisibilityManager.prototype.createPanel = function() {
        // Create backdrop
        const backdrop = document.createElement('div');
        backdrop.className = 'ag-column-visibility-backdrop';
        backdrop.style.cssText = 'position: fixed !important; top: 0 !important; left: 0 !important; right: 0 !important; bottom: 0 !important; background: rgba(0, 0, 0, 0.3) !important; z-index: 10000 !important; display: none !important;';
        backdrop.addEventListener('click', this.hidePanel.bind(this));
        this.backdrop = backdrop;
        document.body.appendChild(backdrop);

        // Create panel
        const panel = document.createElement('div');
        panel.className = 'ag-column-visibility-panel';
        panel.style.cssText = 'position: fixed !important; top: 50% !important; left: 50% !important; transform: translate(-50%, -50%) !important; width: 400px !important; max-width: 90vw !important; max-height: 80vh !important; background: #fff !important; border: 1px solid #d3d3d3 !important; border-radius: 8px !important; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3) !important; z-index: 10001 !important; display: none !important; flex-direction: column !important; overflow: hidden !important;';

        const header = document.createElement('div');
        header.className = 'ag-column-visibility-panel-header';
        header.style.cssText = 'padding: 12px 16px !important; border-bottom: 1px solid #e0e0e0 !important; display: flex !important; justify-content: space-between !important; align-items: center !important; background: #f8f9fa !important;';
        const headerTitle = document.createElement('h3');
        headerTitle.textContent = getTranslation('columnVisibility', 'Column Visibility');
        headerTitle.style.cssText = 'margin: 0 !important; font-size: 16px !important; font-weight: 600 !important; color: #000 !important;';
        const closeBtn = document.createElement('button');
        closeBtn.className = 'ag-column-visibility-close';
        closeBtn.innerHTML = '&times;';
        closeBtn.style.cssText = 'background: none !important; border: none !important; font-size: 24px !important; cursor: pointer !important; color: #666 !important; padding: 0 !important; width: 24px !important; height: 24px !important; display: flex !important; align-items: center !important; justify-content: center !important; border-radius: 4px !important; transition: all 0.2s ease !important;';
        closeBtn.addEventListener('click', this.hidePanel.bind(this));
        closeBtn.addEventListener('mouseenter', function() { this.style.background = '#f0f0f0'; this.style.color = '#000'; });
        closeBtn.addEventListener('mouseleave', function() { this.style.background = 'none'; this.style.color = '#666'; });
        header.appendChild(headerTitle);
        header.appendChild(closeBtn);

        const search = document.createElement('div');
        search.className = 'ag-column-visibility-search';
        search.style.cssText = 'padding: 12px 16px !important; border-bottom: 1px solid #e0e0e0 !important;';
        const searchInput = document.createElement('input');
        searchInput.type = 'text';
        searchInput.placeholder = getTranslation('searchColumns', 'Search columns...');
        searchInput.className = 'ag-column-visibility-search-input';
        searchInput.style.cssText = 'width: 100% !important; padding: 8px 12px !important; border: 1px solid #d3d3d3 !important; border-radius: 4px !important; font-size: 14px !important; box-sizing: border-box !important; background: #fff !important; color: #000 !important;';
        search.appendChild(searchInput);

        const list = document.createElement('div');
        list.className = 'ag-column-visibility-list';
        list.style.cssText = 'flex: 1 !important; overflow-y: auto !important; overflow-x: hidden !important; padding: 8px 0 !important; max-height: 400px !important;';

        const actions = document.createElement('div');
        actions.className = 'ag-column-visibility-actions';
        actions.style.cssText = 'padding: 12px 16px !important; border-top: 1px solid #e0e0e0 !important; display: flex !important; gap: 8px !important; flex-wrap: wrap !important; background: #f8f9fa !important;';

        const buttonStyle = 'padding: 6px 12px !important; border: 1px solid #d3d3d3 !important; border-radius: 4px !important; background: #fff !important; color: #000 !important; cursor: pointer !important; font-size: 13px !important; transition: all 0.15s ease !important; flex: 1 !important; min-width: 80px !important;';
        const primaryButtonStyle = 'padding: 6px 12px !important; border: 1px solid #4a90e2 !important; border-radius: 4px !important; background: #4a90e2 !important; color: #fff !important; cursor: pointer !important; font-size: 13px !important; transition: all 0.15s ease !important; flex: 1 !important; min-width: 80px !important;';

        if (this.options.enableReset) {
            const resetBtn = document.createElement('button');
            resetBtn.className = 'ag-column-visibility-action-btn';
            resetBtn.textContent = getTranslation('resetToDefault', 'Reset to Default');
            resetBtn.style.cssText = buttonStyle;
            resetBtn.addEventListener('click', this.resetToDefault.bind(this));
            resetBtn.addEventListener('mouseenter', function() { this.style.background = '#f0f0f0'; });
            resetBtn.addEventListener('mouseleave', function() { this.style.background = '#fff'; });
            actions.appendChild(resetBtn);
        }

        // Import/Export functionality removed - not needed

        const showAllBtn = document.createElement('button');
        showAllBtn.className = 'ag-column-visibility-action-btn ag-column-visibility-action-primary';
        showAllBtn.textContent = getTranslation('showAll', 'Show All');
        showAllBtn.style.cssText = primaryButtonStyle;
        showAllBtn.addEventListener('click', this.showAllColumns.bind(this));
        showAllBtn.addEventListener('mouseenter', function() { this.style.background = '#357abd'; });
        showAllBtn.addEventListener('mouseleave', function() { this.style.background = '#4a90e2'; });
        actions.appendChild(showAllBtn);

        panel.appendChild(header);
        panel.appendChild(search);
        panel.appendChild(list);
        panel.appendChild(actions);

        this.panelElement = panel;
        this.listElement = list;
        this.searchInput = searchInput;

        // Search functionality
        searchInput.addEventListener('input', this.onSearchChange.bind(this));

        // Insert panel into body (fixed position modal)
        document.body.appendChild(panel);

        // Backdrop handles outside clicks, no need for additional listener
    };

    /**
     * Update panel content
     */
    ColumnVisibilityManager.prototype.updatePanel = function() {
        if (!this.listElement) return;

        const apiToUse = this.getApiToUse();

        const allColumns = apiToUse.getColumns ? apiToUse.getColumns() : null;
        if (!allColumns) return;

        const searchTerm = this.searchInput ? this.searchInput.value.toLowerCase() : '';

        this.listElement.innerHTML = '';

        allColumns.forEach(function(column) {
            const colDef = column.getColDef();
            const field = colDef.field || colDef.colId;
            const headerName = colDef.headerName || field;
            const isVisible = column.isVisible();
            const isLocked = colDef.lockVisible || false;
            const isSelectionCol = this.isSelectionCheckboxColumn(column);
            const isPinned = (function() {
                const pinned = column.getPinned ? column.getPinned() : null;
                return !!(pinned && pinned !== false);
            })();
            const isPinLocked = colDef.lockPinned || isSelectionCol;

            // Filter by search term
            if (searchTerm && !headerName.toLowerCase().includes(searchTerm) && !field.toLowerCase().includes(searchTerm)) {
                return;
            }

            const item = document.createElement('div');
            item.className = 'ag-column-visibility-item' + (isLocked ? ' ag-column-visibility-item-locked' : '');
            item.style.cssText = 'display: flex !important; align-items: center !important; padding: 8px 16px !important; cursor: ' + (isLocked ? 'not-allowed' : 'pointer') + ' !important; transition: background-color 0.15s ease !important;';
            if (!isLocked) {
                item.addEventListener('mouseenter', function() { this.style.background = '#f0f0f0'; });
                item.addEventListener('mouseleave', function() { this.style.background = ''; });
            }

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = 'col-vis-' + field;
            checkbox.checked = isVisible;
            checkbox.disabled = isLocked;
            checkbox.style.cssText = 'margin-right: 10px !important; cursor: ' + (isLocked ? 'not-allowed' : 'pointer') + ' !important; width: 16px !important; height: 16px !important; flex-shrink: 0 !important;';
            checkbox.addEventListener('change', function() {
                this.setColumnVisible(field, checkbox.checked);
                // Update panel to reflect changes
                setTimeout(() => {
                    this.updatePanel();
                }, 100);
            }.bind(this));

            const label = document.createElement('label');
            label.htmlFor = 'col-vis-' + field;
            label.textContent = headerName;
            label.style.cssText = 'cursor: ' + (isLocked ? 'not-allowed' : 'pointer') + ' !important; user-select: none !important; flex: 1 !important; overflow: hidden !important; text-overflow: ellipsis !important; white-space: nowrap !important; color: ' + (isLocked ? '#999' : '#000') + ' !important; font-size: 14px !important;';
            if (isLocked) {
                label.title = getTranslation('columnCannotBeHidden', 'This column cannot be hidden');
                item.style.opacity = '0.6';
            }

            item.appendChild(checkbox);
            item.appendChild(label);

            if (this.options.enablePin && !isSelectionCol &&
                !(typeof AgGridHelper !== 'undefined' && AgGridHelper.shouldDisableColumnPinning())) {
                const pinBtn = document.createElement('button');
                pinBtn.type = 'button';
                pinBtn.className = 'ag-column-visibility-pin-btn' +
                    (isPinned ? ' ag-column-visibility-pin-btn--active' : '') +
                    (isPinLocked ? ' ag-column-visibility-pin-btn--locked' : '');
                pinBtn.innerHTML = '<i class="fas fa-thumbtack" aria-hidden="true"></i>';
                pinBtn.title = isPinLocked
                    ? getTranslation('columnCannotBeUnpinned', 'This column cannot be unpinned')
                    : (isPinned
                        ? getTranslation('unpinColumn', 'Unpin column')
                        : getTranslation('pinColumn', 'Pin column'));
                pinBtn.disabled = isPinLocked;
                pinBtn.setAttribute('aria-label', pinBtn.title);
                pinBtn.setAttribute('aria-pressed', isPinned ? 'true' : 'false');
                pinBtn.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (!isPinLocked) {
                        this.toggleColumnPinned(field);
                    }
                }.bind(this));
                item.appendChild(pinBtn);
            }

            this.listElement.appendChild(item);
        }.bind(this));

        if (this.listElement.children.length === 0) {
            const noResults = document.createElement('div');
            noResults.className = 'ag-column-visibility-no-results';
            noResults.textContent = getTranslation('noColumnsFound', 'No columns found');
            this.listElement.appendChild(noResults);
        }
    };

    /**
     * Handle search input change
     */
    ColumnVisibilityManager.prototype.onSearchChange = function() {
        this.updatePanel();
    };

    /**
     * Get current column state
     */
    ColumnVisibilityManager.prototype.getColumnState = function() {
        return Object.assign({}, this.columnState);
    };

    /**
     * Destroy manager and cleanup
     */
    ColumnVisibilityManager.prototype.destroy = function() {
        if (this.gridApi && this._columnPinnedHandler) {
            this.gridApi.removeEventListener('columnPinned', this._columnPinnedHandler);
            this._columnPinnedHandler = null;
        }
        if (this.backdrop && this.backdrop.parentElement) {
            this.backdrop.parentElement.removeChild(this.backdrop);
        }
        if (this.panelElement && this.panelElement.parentElement) {
            this.panelElement.parentElement.removeChild(this.panelElement);
        }
        if (this.panelButton && this.panelButton.parentElement) {
            this.panelButton.parentElement.removeChild(this.panelButton);
        }
    };

    // Export for global use
    if (typeof window !== 'undefined') {
        window.ColumnVisibilityManager = ColumnVisibilityManager;
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = ColumnVisibilityManager;
    }
})();
