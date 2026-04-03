/**
 * AG Grid Helper Utility
 * Centralized initialization and configuration for AG Grid across all templates
 *
 * Features:
 * - Unified grid initialization with API detection
 * - Default grid options with sensible defaults
 * - Column Visibility Manager integration
 * - Button styling utilities
 * - Common helper functions
 *
 * Usage:
 *   const gridHelper = new AgGridHelper({
 *     containerId: 'myGrid',
 *     templateId: 'my-template',
 *     columnDefs: [...],
 *     rowData: [...],
 *     options: { ... }
 *   });
 *   const gridApi = gridHelper.initialize();
 */

(function() {
    'use strict';

    /**
     * Get AG Grid localeText translations
     * Reads from window.agGridTranslations or i18n-json script tag
     * @returns {Object} localeText object for AG Grid
     */
    function getAgGridLocaleText() {
        const localeText = {};

        // Try to get from window.agGridTranslations (set by templates)
        if (window.agGridTranslations && window.agGridTranslations.localeText) {
            return window.agGridTranslations.localeText;
        }

        // Try to get from i18n-json script tag
        try {
            const i18nEl = document.getElementById('i18n-json');
            if (i18nEl) {
                const i18n = JSON.parse(i18nEl.textContent);
                // Map common AG Grid localeText keys
                if (i18n.agGridNoRowsToShow) localeText.noRowsToShow = i18n.agGridNoRowsToShow;
                if (i18n.agGridLoadingOoo) localeText.loadingOoo = i18n.agGridLoadingOoo;
                if (i18n.agGridPage) localeText.page = i18n.agGridPage;
                if (i18n.agGridMore) localeText.more = i18n.agGridMore;
                if (i18n.agGridTo) localeText.to = i18n.agGridTo;
                if (i18n.agGridOf) localeText.of = i18n.agGridOf;
                if (i18n.agGridNext) localeText.next = i18n.agGridNext;
                if (i18n.agGridLast) localeText.last = i18n.agGridLast;
                if (i18n.agGridFirst) localeText.first = i18n.agGridFirst;
                if (i18n.agGridPrevious) localeText.previous = i18n.agGridPrevious;
                if (i18n.agGridLoading) localeText.loading = i18n.agGridLoading;
                if (i18n.agGridNoRowsToShow) localeText.noRowsToShow = i18n.agGridNoRowsToShow;
                if (i18n.agGridFilterOoo) localeText.filterOoo = i18n.agGridFilterOoo;
                if (i18n.agGridEquals) localeText.equals = i18n.agGridEquals;
                if (i18n.agGridNotEqual) localeText.notEqual = i18n.agGridNotEqual;
                if (i18n.agGridLessThan) localeText.lessThan = i18n.agGridLessThan;
                if (i18n.agGridGreaterThan) localeText.greaterThan = i18n.agGridGreaterThan;
                if (i18n.agGridInRange) localeText.inRange = i18n.agGridInRange;
                if (i18n.agGridContains) localeText.contains = i18n.agGridContains;
                if (i18n.agGridNotContains) localeText.notContains = i18n.agGridNotContains;
                if (i18n.agGridStartsWith) localeText.startsWith = i18n.agGridStartsWith;
                if (i18n.agGridEndsWith) localeText.endsWith = i18n.agGridEndsWith;
                if (i18n.agGridAndCondition) localeText.andCondition = i18n.agGridAndCondition;
                if (i18n.agGridOrCondition) localeText.orCondition = i18n.agGridOrCondition;
                if (i18n.agGridApplyFilter) localeText.applyFilter = i18n.agGridApplyFilter;
                if (i18n.agGridResetFilter) localeText.resetFilter = i18n.agGridResetFilter;
                if (i18n.agGridClearFilter) localeText.clearFilter = i18n.agGridClearFilter;
                if (i18n.agGridPageSize) localeText.pageSize = i18n.agGridPageSize;
                if (i18n.agGridPageSizeSelectorLabel) localeText.pageSizeSelectorLabel = i18n.agGridPageSizeSelectorLabel;
                if (i18n.agGridAriaPageSizeSelectorLabel) localeText.ariaPageSizeSelectorLabel = i18n.agGridAriaPageSizeSelectorLabel;
                if (i18n.agGridFirstPage) localeText.firstPage = i18n.agGridFirstPage;
                if (i18n.agGridPreviousPage) localeText.previousPage = i18n.agGridPreviousPage;
                if (i18n.agGridNextPage) localeText.nextPage = i18n.agGridNextPage;
                if (i18n.agGridLastPage) localeText.lastPage = i18n.agGridLastPage;
            }
        } catch (e) {
            // Ignore parsing errors
        }

        if (Object.keys(localeText).length > 0) {
            return localeText;
        }

        return null;
    }

    /**
     * Fallback copy to clipboard for older browsers or when clipboard API fails
     * @param {string} text - Text to copy
     */
    function fallbackCopyToClipboard(text) {
        try {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
        } catch (e) {
            console.warn('AgGridHelper: Copy to clipboard failed', e);
        }
    }

    /**
     * AG Grid Helper Class
     * @param {Object} config - Configuration object
     * @param {string} config.containerId - DOM ID of grid container
     * @param {string} config.templateId - Unique template identifier for persistence
     * @param {Array} config.columnDefs - Column definitions array
     * @param {Array} config.rowData - Initial row data (optional)
     * @param {Object} config.options - Additional grid options
     * @param {Object} config.columnVisibilityOptions - Column Visibility Manager options
     */
    function AgGridHelper(config) {
        if (!config || !config.containerId || !config.templateId || !config.columnDefs) {
            throw new Error('AgGridHelper: containerId, templateId, and columnDefs are required');
        }

        this.config = {
            containerId: config.containerId,
            templateId: config.templateId,
            columnDefs: config.columnDefs,
            rowData: config.rowData || [],
            options: config.options || {},
            columnVisibilityOptions: config.columnVisibilityOptions || {},
            heightOptions: Object.assign({
                // Minimum height mode:
                // - 'viewport': Fill available viewport height (screen height minus top bar)
                // - number: Fixed minimum height in pixels
                // - 'auto': Smart calculation based on row count and minRowsToShow
                minHeight: 'viewport',
                // Height of the app's top navigation bar (layout.html uses h-16 = 64px)
                topBarHeight: 64,
                // Minimum height for empty state (shows "No rows" message nicely)
                emptyStateHeight: 200,
                // Default max height is viewport-aware so grids use available screen space on large displays
                // Supported values:
                // - number (px)
                // - 'viewport' (fill available viewport height beneath grid)
                maxHeight: 'viewport',
                // Extra padding subtracted from viewport calculations
                // Accounts for page content padding, card margins, pagination bar, etc.
                // Larger offset = smaller grid height
                viewportOffset: 120,
                // Approximate row height including increased padding (16px top + 16px bottom = 32px padding + ~18px content)
                rowHeight: 50,
                // Approximate header height
                headerHeight: 48,
                // Approximate pagination bar height
                paginationHeight: 52,
                // Minimum rows to show space for when minHeight is 'auto' (even if fewer rows exist)
                minRowsToShow: 3,
                // Maximum rows to show before scrolling (0 = no limit, use maxHeight)
                maxRowsToShow: 0,
                // Absolute minimum height (floor) to prevent grids from being too small
                absoluteMinHeight: 300
            }, config.heightOptions || {}),
            checkboxColumnWidth: typeof config.checkboxColumnWidth === 'number' ? config.checkboxColumnWidth : 56
        };

        this.gridApi = null;
        this.columnApi = null;
        this.columnVisibilityManager = null;
        this.gridDiv = null;
        this.checkboxWidthTimeout = null;
        // Track whether we've already called sizeColumnsToFit().
        // Repeated calls (e.g., after height recalculation) can effectively "fight" user-driven column resizing
        // by continuously re-fitting widths to the container.
        this._hasSizedColumnsToFit = false;
    }

    /**
     * Get default grid options
     * @returns {Object} Default grid options
     */
    AgGridHelper.prototype.getDefaultGridOptions = function() {
        const localeText = getAgGridLocaleText();
        // Detect RTL mode from the global page direction and/or language markers.
        // Note: the app sets html[dir="rtl"] at runtime for Arabic in `static/js/layout.js`.
        const docDir = document.documentElement.getAttribute('dir');
        const dataLang = (document.documentElement.getAttribute('data-language') || document.body.getAttribute('data-language') || '').toLowerCase();
        const isRtl = docDir === 'rtl' || dataLang === 'ar';
        const options = {
            columnDefs: this.config.columnDefs,
            rowData: this.config.rowData,
            components: typeof CustomSetFilter !== 'undefined' ? {
                customSetFilter: CustomSetFilter
            } : {},
            defaultColDef: {
                sortable: true,
                resizable: true,
                filter: true,
                wrapText: true,
                autoHeight: true,
                cellStyle: {
                    'display': 'flex',
                    'align-items': 'center',
                    'justify-content': 'flex-start'
                }
            },
            // Enable AG Grid built-in RTL layout when the app is in RTL mode.
            // This ensures AG Grid adds `.ag-rtl` and flips internal UI appropriately.
            enableRtl: isRtl,
            pagination: true,
            paginationPageSize: 50,
            paginationPageSizeSelector: [25, 50, 100, 200, 10000],
            animateRows: true,
            rowSelection: {
                mode: 'multiRow',
                enableClickSelection: false,
                // Only select rows that are currently visible after filtering,
                // so bulk actions don't apply to filtered-out rows (replaces
                // deprecated headerCheckboxSelectionFilteredOnly as of v32.2).
                selectAll: 'filtered'
            },
            cellSelection: false,
            // Ensure the auto-generated selection column checkbox is vertically centered.
            // The defaultColDef.cellStyle does NOT apply to the selection column, so we
            // must configure it separately via selectionColumnDef (ag-grid v32+).
            selectionColumnDef: {
                cellStyle: {
                    'display': 'flex',
                    'align-items': 'center',
                    'justify-content': 'center'
                }
            }
        };

        // Custom context menu is applied via DOM (setupContextMenuFallback) so it works in Community edition.
        // If using Enterprise, you can override with options.getContextMenuItems.

        // Add localeText if translations are available
        // Use getLocaleText callback for dynamic translations (more reliable than static localeText)
        if (localeText) {
            // Store localeText for getLocaleText callback
            this._localeText = localeText;
            // Use getLocaleText callback for dynamic translation lookup
            options.getLocaleText = function(params) {
                // params.key is the translation key (e.g., 'pageSize')
                // params.defaultValue is the English default
                if (this._localeText && this._localeText[params.key]) {
                    return this._localeText[params.key];
                }
                return params.defaultValue;
            }.bind(this);
        }

        return options;
    };

    /**
     * Build custom context menu items for right-click on a cell.
     * Returns: Copy cell, Export table to Excel.
     * @param {Object} params - AG Grid context menu params (node, column, value, api, etc.)
     * @returns {Array} Array of context menu item descriptors
     */
    AgGridHelper.prototype.buildContextMenuItems = function(params) {
        const self = this;
        const items = [];

        items.push({
            name: 'Copy cell',
            action: function() {
                const value = params.value;
                const text = value == null ? '' : String(value);
                if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
                    navigator.clipboard.writeText(text).catch(function() {
                        fallbackCopyToClipboard(text);
                    });
                } else {
                    fallbackCopyToClipboard(text);
                }
            }
        });

        items.push({
            name: 'Export table to Excel',
            action: function() {
                const api = params.api || self.gridApi;
                if (api) {
                    self.exportTableToCSV(api, 'export.csv');
                }
            }
        });

        return items;
    };

    /**
     * Merge default options with custom options
     * @returns {Object} Merged grid options
     */
    AgGridHelper.prototype.buildGridOptions = function() {
        const defaults = this.getDefaultGridOptions();
        const custom = this.config.options || {};

        // Deep merge for nested objects
        const merged = Object.assign({}, defaults, custom);

        // Deep merge defaultColDef
        if (custom.defaultColDef) {
            merged.defaultColDef = Object.assign({}, defaults.defaultColDef, custom.defaultColDef);
        }

        // Deep merge rowSelection
        if (custom.rowSelection) {
            merged.rowSelection = Object.assign({}, defaults.rowSelection, custom.rowSelection);
        }

        // Deep merge selectionColumnDef
        if (custom.selectionColumnDef) {
            merged.selectionColumnDef = Object.assign({}, defaults.selectionColumnDef, custom.selectionColumnDef);
        }

        // Merge components
        if (custom.components) {
            merged.components = Object.assign({}, defaults.components, custom.components);
        }

        // Deep merge getLocaleText callback (important: preserve both if they exist)
        if (defaults.getLocaleText && custom.getLocaleText) {
            // If both exist, use custom but fall back to defaults
            const defaultCallback = defaults.getLocaleText;
            const customCallback = custom.getLocaleText;
            merged.getLocaleText = function(params) {
                const customResult = customCallback(params);
                if (customResult !== params.defaultValue) {
                    return customResult;
                }
                return defaultCallback(params);
            };
        } else if (defaults.getLocaleText) {
            merged.getLocaleText = defaults.getLocaleText;
        } else if (custom.getLocaleText) {
            merged.getLocaleText = custom.getLocaleText;
        }

        return merged;
    };

    /**
     * Detect and get the appropriate AG Grid API
     * @returns {Function|null} Grid constructor or createGrid function
     */
    AgGridHelper.prototype.detectGridApi = function() {
        if (typeof agGrid === 'undefined') {
            console.error('AgGridHelper: agGrid is not defined. Ensure ag-grid-community.min.js is loaded.');
            return null;
        }

        // Try createGrid API first (v31+)
        if (typeof agGrid.createGrid === 'function') {
            return agGrid.createGrid;
        }

        // Try Grid constructor (older API)
        if (typeof agGrid.Grid === 'function') {
            return agGrid.Grid;
        }

        // Search for Grid constructor
        const agGridKeys = Object.keys(agGrid);
        for (let i = 0; i < agGridKeys.length; i++) {
            const key = agGridKeys[i];
            if (key === 'Grid' && typeof agGrid[key] === 'function') {
                return agGrid[key];
            }
        }

        console.error('AgGridHelper: Could not find AG Grid API. Available keys:', agGridKeys.slice(0, 20));
        return null;
    };

    /**
     * Get the actual grid API from the grid instance
     * This method is used internally and handles both API versions
     * @param {Object} gridInstance - Grid instance returned from createGrid or Grid constructor
     * @returns {Object} Grid API object
     * @private
     */
    AgGridHelper.prototype.getGridApi = function(gridInstance) {
        // For createGrid API (v31+), the API might be in gridInstance.api
        if (gridInstance && gridInstance.api && typeof gridInstance.api.getColumns === 'function') {
            return gridInstance.api;
        }
        // For older Grid API, the instance itself is the API
        if (gridInstance && typeof gridInstance.getColumns === 'function') {
            return gridInstance;
        }
        // Fallback: return the instance as-is
        return gridInstance;
    };

    /**
     * Wait for the grid container element to appear in the DOM
     * @param {number} maxWaitMs - Maximum time to wait in milliseconds (default: 3000)
     * @returns {Promise<HTMLElement|null>} Promise that resolves with the element or null
     */
    AgGridHelper.prototype.waitForContainer = function(maxWaitMs) {
        maxWaitMs = maxWaitMs || 3000;
        const startTime = Date.now();
        const checkInterval = 100;

        return new Promise(function(resolve) {
            const checkContainer = function() {
                const element = document.querySelector('#' + this.config.containerId);
                if (element) {
                    resolve(element);
                    return;
                }

                const elapsed = Date.now() - startTime;
                if (elapsed < maxWaitMs) {
                    setTimeout(checkContainer.bind(this), checkInterval);
                } else {
                    console.error('AgGridHelper: Grid container #' + this.config.containerId + ' not found after ' + maxWaitMs + 'ms');
                    resolve(null);
                }
            }.bind(this);

            checkContainer();
        }.bind(this));
    };

    /**
     * Initialize the grid
     * @returns {Object|null} Grid API instance or null if failed
     */
    AgGridHelper.prototype.initialize = function() {
        // Get grid container - try immediately first
        this.gridDiv = document.querySelector('#' + this.config.containerId);

        if (!this.gridDiv) {
            // Container not found immediately - log warning but return null
            // The caller should use waitForContainer and initializeAsync for async scenarios
            console.warn('AgGridHelper: Grid container #' + this.config.containerId + ' not found. Consider using waitForContainer() before initialize() or use initializeAsync()');
            return null;
        }

        return this._doInitialize();
    };

    /**
     * Initialize the grid asynchronously (waits for container to appear)
     * @param {number} maxWaitMs - Maximum time to wait for container in milliseconds
     * @returns {Promise<Object|null>} Promise that resolves with Grid API instance or null
     */
    AgGridHelper.prototype.initializeAsync = function(maxWaitMs) {
        const self = this;
        return this.waitForContainer(maxWaitMs).then(function(container) {
            if (!container) {
                return null;
            }
            self.gridDiv = container;
            return self._doInitialize();
        });
    };

    /**
     * Internal method to perform the actual grid initialization
     * @returns {Object|null} Grid API instance or null if failed
     * @private
     */
    AgGridHelper.prototype._doInitialize = function() {
        if (!this.gridDiv) {
            console.error('AgGridHelper: Grid container #' + this.config.containerId + ' not found');
            return null;
        }

        // Detect grid API
        const GridConstructor = this.detectGridApi();
        if (!GridConstructor) {
            return null;
        }

        // Build grid options
        const gridOptions = this.buildGridOptions();
        this._gridOptions = gridOptions;

        try {
            // Initialize grid based on API type
            let gridInstance;
            if (GridConstructor === agGrid.createGrid) {
                // New createGrid API (v31+)
                gridInstance = GridConstructor(this.gridDiv, gridOptions);
                // For createGrid, the instance itself has the API methods
                // Check if it has api property, otherwise use instance directly
                this.gridApi = (gridInstance.api && typeof gridInstance.api.getColumns === 'function')
                    ? gridInstance.api
                    : gridInstance;
                this.gridInstance = gridInstance;
            } else {
                // Old Grid constructor API
                gridInstance = new GridConstructor(this.gridDiv, gridOptions);
                // For old API, instance itself is the API
                this.gridApi = gridInstance;
                this.gridInstance = gridInstance;
            }

            if (!this.columnApi) {
                if (gridInstance && gridInstance.columnApi) {
                    this.columnApi = gridInstance.columnApi;
                } else if (gridInstance && gridInstance.api && gridInstance.api.columnApi) {
                    this.columnApi = gridInstance.api.columnApi;
                } else if (gridOptions && gridOptions.columnApi) {
                    this.columnApi = gridOptions.columnApi;
                } else if (this.gridApi && this.gridApi.columnApi) {
                    this.columnApi = this.gridApi.columnApi;
                }
            }

            // Initialize Column Visibility Manager
            this.initializeColumnVisibilityManager();

            // Initialize Clear All Filters Button
            this.initializeClearFiltersButton();

            // Ensure cell alignment is applied after grid initialization
            this.ensureCellAlignment();

            // Listen for pagination changes to recalculate height
            this.setupPaginationListener();

            // Keep height responsive to viewport changes (e.g., large screens, browser resize)
            this.setupWindowResizeListener();

            // Setup checkbox column width handling
            this.setupCheckboxColumnWidthHandling();

            // Ensure filter menu input spacing is applied reliably
            this.setupFilterMenuInputSpacing();

            // Re-evaluate auto-detected filters when filters change
            this.setupAutoDetectFiltersReevaluation();

            // Emit selection-changed events so templates can show bulk-action UI
            this.setupSelectionChangedDispatcher();

            // Custom right-click context menu (Copy cell, Export table to Excel) – works in Community edition
            this.setupContextMenuFallback();

            // Set dynamic height after a short delay to ensure:
            // 1. Grid is fully rendered and positioned in the DOM
            // 2. Any content above the grid has loaded
            // 3. The viewport calculation is accurate
            const self = this;
            setTimeout(function() {
                // Clear any early cached value to ensure fresh calculation
                self._cachedViewportMinHeight = null;
                self.setDynamicHeight();
            }, 150);

            // Expose to window for debugging
            window.gridApi = this.gridApi;
            window.columnVisibilityManager = this.columnVisibilityManager;
            window.gridHelper = this; // Expose helper instance

            return this.gridApi;
        } catch (error) {
            console.error('AgGridHelper: Error initializing grid:', error);
            return null;
        }
    };

    /**
     * Re-evaluate auto-detected column filters whenever the user applies filters.
     * This uses the currently displayed rows (after filters) to decide if a column
     * should stay on text filter or switch to the unique-items custom set filter.
     *
     * Notes:
     * - Only active when AgGridHelper.create(..., { autoDetectFilters: true }) (default).
     * - Attempts to preserve column state + filter model during columnDefs update.
     */
    AgGridHelper.prototype.setupAutoDetectFiltersReevaluation = function() {
        if (this._autoDetectFiltersListenerAttached) {
            return;
        }
        if (!this._autoDetectFiltersEnabled) {
            return;
        }
        if (!this.gridApi || typeof this.gridApi.addEventListener !== 'function') {
            return;
        }

        const self = this;
        const handler = function() {
            // Debounce slightly; AG Grid can fire filterChanged frequently.
            if (self._autoDetectFiltersReevalTimer) {
                clearTimeout(self._autoDetectFiltersReevalTimer);
            }
            self._autoDetectFiltersReevalTimer = setTimeout(function() {
                self.reEvaluateAutoDetectedFilters();
            }, 50);
        };

        this.gridApi.addEventListener('filterChanged', handler);
        this._autoDetectFiltersListenerAttached = true;
        this._autoDetectFiltersListener = handler;
    };

    AgGridHelper.prototype.reEvaluateAutoDetectedFilters = function() {
        const api = this.gridApi;
        if (!api || !this.config || !Array.isArray(this.config.columnDefs)) {
            return;
        }

        // Build displayed rows snapshot
        const displayedRows = [];
        if (typeof api.forEachNodeAfterFilter === 'function') {
            api.forEachNodeAfterFilter(function(node) {
                if (node && node.data) {
                    displayedRows.push(node.data);
                }
            });
        } else if (typeof api.forEachNode === 'function') {
            api.forEachNode(function(node) {
                if (node && node.data && (node.displayed === true || node.displayed === undefined)) {
                    displayedRows.push(node.data);
                }
            });
        }
        if (!displayedRows.length) {
            return;
        }

        // Track existing filter choices
        const before = {};
        this.config.columnDefs.forEach(function(cd) {
            if (cd && cd.field) {
                before[cd.field] = cd.filter;
            }
        });

        // Re-run detection on displayed data
        const detectOpts = Object.assign({}, this._autoDetectFilterOptions || {});
        AgGridHelper.autoDetectColumnFilters(this.config.columnDefs, displayedRows, detectOpts);

        // See if anything changed
        let changed = false;
        this.config.columnDefs.forEach(function(cd) {
            if (cd && cd.field) {
                if (before[cd.field] !== cd.filter) {
                    changed = true;
                }
            }
        });
        if (!changed) {
            return;
        }

        // Preserve filter model and column state where possible
        let filterModel = null;
        try {
            if (typeof api.getFilterModel === 'function') {
                filterModel = api.getFilterModel();
            }
        } catch (e) {
            filterModel = null;
        }

        let colState = null;
        const colApi = this.getColumnApi && this.getColumnApi();
        try {
            if (colApi && typeof colApi.getColumnState === 'function') {
                colState = colApi.getColumnState();
            }
        } catch (e) {
            colState = null;
        }

        // Apply updated colDefs (API differs by AG Grid version)
        try {
            if (typeof api.setGridOption === 'function') {
                api.setGridOption('columnDefs', this.config.columnDefs);
            } else if (typeof api.setColumnDefs === 'function') {
                api.setColumnDefs(this.config.columnDefs);
            }
        } catch (e) {
            // If we can't apply new coldefs, stop here
            return;
        }

        // Restore column state
        try {
            if (colState && colApi && typeof colApi.applyColumnState === 'function') {
                colApi.applyColumnState({ state: colState, applyOrder: true });
            }
        } catch (e) {
            // ignore
        }

        // Restore filter model
        try {
            if (filterModel && typeof api.setFilterModel === 'function') {
                api.setFilterModel(filterModel);
            }
        } catch (e) {
            // ignore
        }
    };

    /**
     * Initialize Column Visibility Manager
     */
    AgGridHelper.prototype.initializeColumnVisibilityManager = function() {
        if (typeof ColumnVisibilityManager === 'undefined') {
            console.warn('AgGridHelper: ColumnVisibilityManager is not available');
            return;
        }

        if (!this.gridApi) {
            console.warn('AgGridHelper: gridApi is not available for ColumnVisibilityManager');
            return;
        }

        try {
            const defaultOptions = {
                persistOnChange: true,
                showPanelButton: true,
                enableExport: false,
                enableReset: true
            };

            const options = Object.assign({}, defaultOptions, this.config.columnVisibilityOptions);

            // Pass containerId to ColumnVisibilityManager so it can find the correct placeholder
            options.containerId = this.config.containerId;

            // Also pass buttonPlaceholderId if provided
            if (this.config.columnVisibilityOptions && this.config.columnVisibilityOptions.buttonPlaceholderId) {
                options.buttonPlaceholderId = this.config.columnVisibilityOptions.buttonPlaceholderId;
            }

            this.columnVisibilityManager = new ColumnVisibilityManager(
                this.gridApi,
                this.config.templateId,
                options
            );

            // Apply button styling
            this.styleColumnVisibilityButton();

        } catch (error) {
            console.error('AgGridHelper: Error initializing ColumnVisibilityManager:', error);
        }
    };

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
        // Try window.agGridTranslations first
        if (window.agGridTranslations && window.agGridTranslations[key]) {
            return window.agGridTranslations[key];
        }

        // Try i18n-json
        try {
            const i18nEl = document.getElementById('i18n-json');
            if (i18nEl && i18nEl.textContent) {
                const i18n = JSON.parse(i18nEl.textContent);
                if (i18n && i18n[key]) {
                    return i18n[key];
                }
            }
        } catch (e) {
            // Ignore parsing errors
        }

        return defaultValue;
    };

    /**
     * Style the Clear Filters Button
     */
    AgGridHelper.prototype.styleClearFiltersButton = function() {
        if (!this.clearFiltersButton) return;

        const button = this.clearFiltersButton;

        // Apply styles matching the column visibility button
        button.style.cssText = [
            'padding: 8px 16px !important',
            'background: #ffffff !important',
            'border: 1px solid #d1d5db !important',
            'border-radius: 6px !important',
            'cursor: pointer !important',
            'font-size: 14px !important',
            'color: #374151 !important',
            'display: none',  // Hidden by default, shown when filters active
            'align-items: center !important',
            'gap: 6px !important',
            'transition: all 0.2s ease !important',
            'box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important',
            'font-weight: 500 !important',
            'white-space: nowrap !important',
            'font-family: inherit !important'
        ].join('; ');

        // Style icon
        const iconElement = button.querySelector('i');
        if (iconElement) {
            iconElement.style.cssText = 'font-size: 14px !important; color: #dc2626 !important;';
        }

        // Apply hover styles
        if (!button.dataset.hoverListeners) {
            button.addEventListener('mouseenter', function() {
                this.style.background = '#fef2f2';
                this.style.borderColor = '#fecaca';
                this.style.boxShadow = '0 2px 4px rgba(220, 38, 38, 0.15)';
            });

            button.addEventListener('mouseleave', function() {
                this.style.background = '#ffffff';
                this.style.borderColor = '#d1d5db';
                this.style.boxShadow = '0 1px 3px rgba(0, 0, 0, 0.1)';
            });

            button.addEventListener('mousedown', function() {
                this.style.transform = 'translateY(1px)';
                this.style.boxShadow = '0 1px 2px rgba(0, 0, 0, 0.1)';
            });

            button.addEventListener('mouseup', function() {
                this.style.transform = '';
            });

            button.dataset.hoverListeners = 'true';
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
        this.clearFiltersButton.style.display = hasActiveFilters ? 'inline-flex' : 'none';
    };

    /**
     * Ensure all cells have center vertical alignment and proper padding
     * This method applies alignment styles after grid initialization to override
     * any ag-grid defaults that might set top alignment
     */
    AgGridHelper.prototype.ensureCellAlignment = function() {
        if (!this.gridDiv) {
            return;
        }

        // Use requestAnimationFrame to ensure DOM is ready
        const self = this;
        requestAnimationFrame(function() {
            // Find all cells in the grid and ensure they have center alignment and padding
            const cells = self.gridDiv.querySelectorAll('.ag-cell');
            cells.forEach(function(cell) {
                // Ensure cell has flex display and center alignment
                if (cell.style.display !== 'flex') {
                    cell.style.display = 'flex';
                }
                if (cell.style.alignItems !== 'center') {
                    cell.style.alignItems = 'center';
                }

                // Ensure proper padding is applied
                // Check if cell has wrapped text (white-space: normal or word-wrap)
                const hasWrappedText = cell.style.whiteSpace === 'normal' ||
                                     cell.style.wordWrap === 'break-word' ||
                                     cell.style.wordWrap === 'break-word' ||
                                     cell.getAttribute('style') && (
                                         cell.getAttribute('style').includes('white-space: normal') ||
                                         cell.getAttribute('style').includes('white-space:normal') ||
                                         cell.getAttribute('style').includes('word-wrap')
                                     );

                if (hasWrappedText) {
                    // Extra padding for cells with wrapped text
                    if (!cell.style.paddingTop || parseInt(cell.style.paddingTop) < 18) {
                        cell.style.paddingTop = '18px';
                    }
                    if (!cell.style.paddingBottom || parseInt(cell.style.paddingBottom) < 18) {
                        cell.style.paddingBottom = '18px';
                    }
                } else {
                    // Standard padding for regular cells
                    if (!cell.style.paddingTop || parseInt(cell.style.paddingTop) < 16) {
                        cell.style.paddingTop = '16px';
                    }
                    if (!cell.style.paddingBottom || parseInt(cell.style.paddingBottom) < 16) {
                        cell.style.paddingBottom = '16px';
                    }
                }
            });

            // Also ensure cell wrappers have center alignment
            const cellWrappers = self.gridDiv.querySelectorAll('.ag-cell-wrapper');
            cellWrappers.forEach(function(wrapper) {
                if (wrapper.style.alignItems !== 'center') {
                    wrapper.style.alignItems = 'center';
                }
            });
        });
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

        const self = this;
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
                mutation.removedNodes.forEach(function(node) {
                    if (!(node instanceof HTMLElement)) {
                        return;
                    }
                    if ((node.classList && node.classList.contains('ag-filter-menu')) ||
                        (node.querySelector && node.querySelector('.ag-filter-menu'))) {
                        setTimeout(function() {
                            if (!self.isFilterMenuOpen()) {
                                self.setDynamicHeight();
                            }
                        }, 0);
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
     * Detect if any filter menu popup is currently open.
     * @returns {boolean}
     */
    AgGridHelper.prototype.isFilterMenuOpen = function() {
        return !!document.querySelector('.ag-filter-menu');
    };

    /**
     * Setup listener for pagination changes to recalculate height
     */
    AgGridHelper.prototype.setupPaginationListener = function() {
        if (!this.gridApi) {
            return;
        }

        const self = this;

        // Listen for pagination changed event
        if (typeof this.gridApi.addEventListener === 'function') {
            this.gridApi.addEventListener('paginationChanged', function() {
                setTimeout(function() {
                    self.setDynamicHeight();
                }, 100);
            });
        }

        // Also listen for model updated (when rows are added/removed)
        if (typeof this.gridApi.addEventListener === 'function') {
            this.gridApi.addEventListener('modelUpdated', function() {
                setTimeout(function() {
                    self.setDynamicHeight();
                }, 100);
            });
        }
    };

    /**
     * Setup listener for window resize to keep grid height responsive
     */
    AgGridHelper.prototype.setupWindowResizeListener = function() {
        if (!this.gridDiv) return;

        const self = this;
        if (this._agGridHelperResizeListenerAttached) return;
        this._agGridHelperResizeListenerAttached = true;

        let resizeTimeout = null;
        window.addEventListener('resize', function() {
            if (resizeTimeout) clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(function() {
                // Clear cached viewport height so it recalculates on resize
                self._cachedViewportMinHeight = null;
                self.setDynamicHeight();
            }, 120);
        });
    };

    /**
     * Resolve a numeric minHeight (px) from heightOptions
     * Supports 'viewport' (fill available screen), 'auto' (based on rows), or fixed number
     * Caches the viewport calculation to prevent recalculation on subsequent calls
     * @param {Object} heightOptions
     * @param {boolean} paginationEnabled - Whether pagination is enabled
     * @returns {number} min height in px
     * @private
     */
    AgGridHelper.prototype.resolveMinHeightPx = function(heightOptions, paginationEnabled) {
        const opts = heightOptions || {};
        const raw = opts.minHeight;
        const absoluteMin = opts.absoluteMinHeight || 300;
        const topBarHeight = opts.topBarHeight || 64;
        const viewportOffset = opts.viewportOffset || 48;
        const headerHeight = opts.headerHeight || 48;
        const rowHeight = opts.rowHeight || 50;
        const paginationHeight = opts.paginationHeight || 52;
        const minRowsToShow = opts.minRowsToShow || 3;

        // 'viewport' mode: Fill available viewport height (screen minus top bar)
        // This ensures the grid fills the screen and page scrolls if there's content above
        if (raw === 'viewport') {
            // Use cached value if available (prevents height jumping on recalculations)
            // Cache is invalidated on window resize via setupWindowResizeListener
            if (this._cachedViewportMinHeight && this._cachedViewportMinHeight > 0) {
                return this._cachedViewportMinHeight;
            }

            try {
                const viewportH = window.innerHeight || document.documentElement.clientHeight || 800;
                // Calculate: viewport height - top bar - minimal offset
                // This makes the grid fill the screen height, causing page to scroll
                // if there's content above the grid
                const availableHeight = Math.floor(viewportH - topBarHeight - viewportOffset);

                // Cache the calculated value
                this._cachedViewportMinHeight = Math.max(absoluteMin, availableHeight);
                return this._cachedViewportMinHeight;
            } catch (e) {
                return absoluteMin;
            }
        }

        // 'auto' mode: Calculate based on minRowsToShow
        if (raw === 'auto') {
            const minContentHeight = minRowsToShow * rowHeight;
            const calculatedMin = headerHeight + minContentHeight + (paginationEnabled ? paginationHeight : 0);
            return Math.max(absoluteMin, calculatedMin);
        }

        // Explicit number
        if (typeof raw === 'number' && isFinite(raw)) {
            return Math.max(absoluteMin, raw);
        }

        // Fallback to absoluteMin
        return absoluteMin;
    };

    /**
     * Resolve a numeric maxHeight (px) from heightOptions
     * @param {Object} heightOptions
     * @returns {number} max height in px
     * @private
     */
    AgGridHelper.prototype.resolveMaxHeightPx = function(heightOptions) {
        const raw = heightOptions ? heightOptions.maxHeight : undefined;

        // Explicit number
        if (typeof raw === 'number' && isFinite(raw)) {
            return raw;
        }

        // Default / viewport-aware
        if (raw === 'viewport' || raw === undefined || raw === null) {
            const offset = (heightOptions && typeof heightOptions.viewportOffset === 'number' && isFinite(heightOptions.viewportOffset))
                ? heightOptions.viewportOffset
                : 24;
            return this.getViewportAvailableHeightPx(offset);
        }

        // Fallback to legacy default (avoid hard-coding 600 everywhere)
        return 600;
    };

    /**
     * Compute available viewport height under the grid container.
     * @param {number} offset - extra padding to subtract from viewport bottom
     * @returns {number}
     * @private
     */
    AgGridHelper.prototype.getViewportAvailableHeightPx = function(offset) {
        try {
            if (!this.gridDiv || !this.gridDiv.getBoundingClientRect) return 600;
            const rect = this.gridDiv.getBoundingClientRect();
            const viewportH = window.innerHeight || document.documentElement.clientHeight || 800;
            const available = Math.floor(viewportH - rect.top - (offset || 0));
            // Keep sane bounds
            return Math.max(150, available);
        } catch (e) {
            return 600;
        }
    };

    /**
     * Calculate and set dynamic height based on row count
     * When autoHeight is enabled, measures actual rendered row heights
     * Otherwise uses fixed rowHeight for calculation
     * Constrained by minHeight and maxHeight
     *
     * Height calculation logic:
     * 1. Empty state: Uses emptyStateHeight (shows "No rows" message nicely)
     * 2. Few rows: Uses minHeight or calculated height (whichever is larger)
     * 3. Many rows: Caps at maxHeight (viewport-aware or fixed)
     */
    AgGridHelper.prototype.setDynamicHeight = function() {
        if (!this.gridDiv || !this.gridApi) {
            return;
        }

        // Avoid reflow while filter menu is open to prevent popup closing
        if (this.isFilterMenuOpen()) {
            return;
        }

        // If the grid is not visible yet (e.g., inside a hidden container/tab),
        // delay height calculation until it becomes visible so viewport measurements are correct.
        if (typeof this.isGridVisible === 'function' && !this.isGridVisible()) {
            const self = this;
            this._agGridHelperVisibilityRetryCount = (this._agGridHelperVisibilityRetryCount || 0) + 1;
            if (this._agGridHelperVisibilityRetryCount <= 25) {
                setTimeout(function() {
                    self.setDynamicHeight();
                }, 200);
            }
            return;
        }
        this._agGridHelperVisibilityRetryCount = 0;

        const self = this;
        // Use double requestAnimationFrame to ensure grid is fully rendered and measured
        requestAnimationFrame(function() {
            requestAnimationFrame(function() {
                const opts = self.config.heightOptions;

                // Extract configuration with defaults
                const headerHeight = opts.headerHeight || 48;
                const rowHeight = opts.rowHeight || 50;
                const paginationHeight = opts.paginationHeight || 52;
                const emptyStateHeight = opts.emptyStateHeight || 200;
                const minRowsToShow = opts.minRowsToShow || 3;
                const maxRowsToShow = opts.maxRowsToShow || 0;

                // Check if autoHeight is enabled
                const autoHeightEnabled = self.hasAutoRowHeight();

                // Check if pagination is enabled
                const paginationEnabled = self.config.options.pagination !== false;
                const pageSize = self.config.options.paginationPageSize || 50;

                // Get total row count
                let totalRowCount = 0;
                if (typeof self.gridApi.getDisplayedRowCount === 'function') {
                    totalRowCount = self.gridApi.getDisplayedRowCount();
                } else if (self.config.rowData) {
                    totalRowCount = self.config.rowData.length;
                }

                // Handle empty state - use viewport-aware height for empty grids too
                if (totalRowCount === 0) {
                    const resolvedMinHeight = self.resolveMinHeightPx(opts, paginationEnabled);
                    const emptyContentHeight = headerHeight + emptyStateHeight + (paginationEnabled ? paginationHeight : 0);
                    // Use the larger of: empty content height or viewport-aware min height
                    const emptyHeight = Math.max(emptyContentHeight, resolvedMinHeight);
                    self.applyGridHeight(emptyHeight, resolvedMinHeight, emptyHeight);
                    return;
                }

                // Calculate rows to display
                let rowsToDisplay = totalRowCount;
                if (paginationEnabled) {
                    rowsToDisplay = Math.min(totalRowCount, pageSize);
                }
                if (maxRowsToShow > 0) {
                    rowsToDisplay = Math.min(rowsToDisplay, maxRowsToShow);
                }

                // Calculate content height
                let contentHeight = 0;

                if (autoHeightEnabled) {
                    // Measure actual rendered row heights when autoHeight is enabled
                    const renderedRows = self.gridDiv.querySelectorAll('.ag-row:not(.ag-header-row)');
                    let measuredHeight = 0;
                    let measuredCount = 0;

                    renderedRows.forEach(function(row) {
                        const h = row.offsetHeight || row.clientHeight;
                        if (h > 0) {
                            measuredHeight += h;
                            measuredCount++;
                        }
                    });

                    if (measuredCount > 0) {
                        contentHeight = measuredHeight;
                    } else {
                        // Fallback: estimate with 20% buffer for variable heights
                        contentHeight = rowsToDisplay * (rowHeight * 1.2);
                    }
                } else {
                    // Fixed row height calculation
                    contentHeight = rowsToDisplay * rowHeight;
                }

                // Calculate total height
                let calculatedHeight = headerHeight + contentHeight;
                if (paginationEnabled) {
                    calculatedHeight += paginationHeight;
                }

                // Calculate minHeight (can be 'viewport', 'auto', or a fixed number)
                const resolvedMinHeight = self.resolveMinHeightPx(opts, paginationEnabled);

                // Get maxHeight (viewport-aware or fixed)
                const maxHeight = self.resolveMaxHeightPx(opts);

                // Effective min height is the resolved value
                const effectiveMinHeight = resolvedMinHeight;

                // Apply constraints
                const safeMaxHeight = Math.max(effectiveMinHeight, maxHeight);
                const finalHeight = Math.max(effectiveMinHeight, Math.min(safeMaxHeight, calculatedHeight));

                self.applyGridHeight(finalHeight, effectiveMinHeight, safeMaxHeight);
            });
        });
    };

    /**
     * Apply calculated heights to the grid element
     * @param {number} height - The calculated height
     * @param {number} minHeight - The minimum height
     * @param {number} maxHeight - The maximum height
     */
    AgGridHelper.prototype.applyGridHeight = function(height, minHeight, maxHeight) {
        if (!this.gridDiv) return;

        this.gridDiv.style.height = height + 'px';
        this.gridDiv.style.minHeight = minHeight + 'px';
        this.gridDiv.style.maxHeight = maxHeight + 'px';

        // Re-layout after height change (doLayout does not override user column widths)
        const self = this;
        const apiToUse = (this.gridApi && this.gridApi.api && typeof this.gridApi.api.doLayout === 'function')
            ? this.gridApi.api
            : this.gridApi;

        // Optional: fit columns to container once on init.
        // This preserves the existing "nice initial fit" behavior, without constantly overriding manual resizes.
        const sizeToFitEnabled = !(this.config && this.config.options && this.config.options.sizeColumnsToFitOnInit === false);

        const shouldDoLayout = apiToUse && typeof apiToUse.doLayout === 'function';
        const shouldSizeToFit = sizeToFitEnabled &&
            !this._hasSizedColumnsToFit &&
            apiToUse && typeof apiToUse.sizeColumnsToFit === 'function';

        if (shouldDoLayout || shouldSizeToFit) {
            setTimeout(function() {
                if (self.isGridVisible && typeof self.isGridVisible === 'function' && !self.isGridVisible()) {
                    self.scheduleCheckboxWidthEnforcement();
                    return;
                }

                try {
                    if (shouldDoLayout) {
                        apiToUse.doLayout();
                    }
                } catch (e) {
                    // Non-fatal
                }

                try {
                    if (shouldSizeToFit) {
                        apiToUse.sizeColumnsToFit();
                        self._hasSizedColumnsToFit = true;
                    }
                } catch (e) {
                    // Non-fatal
                }

                self.scheduleCheckboxWidthEnforcement();
            }, 100);
        } else {
            this.scheduleCheckboxWidthEnforcement();
        }
    };

    /**
     * Apply styling to column visibility button and handle positioning
     */
    AgGridHelper.prototype.styleColumnVisibilityButton = function() {
        const self = this;

        // Helper function to move button container to placeholder if needed
        const moveButtonToPlaceholder = function(buttonContainer, placeholderId) {
            if (!buttonContainer || !placeholderId) return false;

            const placeholder = document.getElementById(placeholderId);
            if (!placeholder) return false;

            // Check if already in placeholder
            if (buttonContainer.parentElement === placeholder) {
                return true;
            }

            // Always move if not in placeholder (regardless of current parent)
            if (buttonContainer.parentElement !== placeholder) {
                placeholder.appendChild(buttonContainer);
                return true;
            }

            return false;
        };

        // Helper function to ensure button has only icon (fallback for edge cases)
        const ensureIconOnly = function(button) {
            if (!button) return;
            const columnsIcon = button.querySelector('i.fas.fa-columns');
            if (columnsIcon) {
                // Check if there's text content (excluding the icon)
                const textNodes = Array.from(button.childNodes).filter(function(node) {
                    return node.nodeType === 3 && node.textContent.trim() !== ''; // Text nodes
                });
                const hasText = textNodes.length > 0 || (button.textContent.trim() !== '' && button.textContent.trim() !== columnsIcon.textContent.trim());
                if (hasText) {
                    // Preserve title attribute if it exists
                    const title = button.getAttribute('title');
                    button.innerHTML = columnsIcon.outerHTML;
                    if (title) {
                        button.setAttribute('title', title);
                    }
                }
            }
        };

        // Helper function to style placeholder
        const stylePlaceholder = function(placeholder) {
            if (!placeholder) return;
            placeholder.style.cssText = 'display: flex !important; align-items: center !important; justify-content: flex-end !important; margin: 0 !important;';
        };

        // Helper function to style a single button
        const styleButton = function(button) {
            if (!button) return;

            // Ensure icon-only (fallback check, button should already be icon-only)
            ensureIconOnly(button);

            // Mark as styled but allow re-styling for icon check
            if (button.dataset.styled === 'true') {
                // Still check icon even if already styled (in case text was re-added)
                ensureIconOnly(button);
                return;
            }

            // Apply base styles
            button.style.cssText = [
                'padding: 8px 16px !important',
                'background: #ffffff !important',
                'border: 1px solid #d1d5db !important',
                'border-radius: 6px !important',
                'cursor: pointer !important',
                'font-size: 14px !important',
                'color: #374151 !important',
                'display: inline-flex !important',
                'align-items: center !important',
                'gap: 6px !important',
                'transition: all 0.2s ease !important',
                'box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important',
                'font-weight: 500 !important',
                'white-space: nowrap !important',
                // IMPORTANT: inherit app font so Arabic uses Tajawal (and other locales use the global font)
                'font-family: inherit !important'
            ].join('; ');

            // Style icon (re-query after potentially changing innerHTML)
            const iconElement = button.querySelector('i');
            if (iconElement) {
                iconElement.style.cssText = 'font-size: 14px !important; color: #6b7280 !important;';
            }

            // Apply hover styles via event listeners (only once)
            if (!button.dataset.hoverListeners) {
                button.addEventListener('mouseenter', function() {
                    this.style.background = '#f9fafb';
                    this.style.borderColor = '#9ca3af';
                    this.style.boxShadow = '0 2px 4px rgba(0, 0, 0, 0.15)';
                });

                button.addEventListener('mouseleave', function() {
                    this.style.background = '#ffffff';
                    this.style.borderColor = '#d1d5db';
                    this.style.boxShadow = '0 1px 3px rgba(0, 0, 0, 0.1)';
                });

                button.addEventListener('mousedown', function() {
                    this.style.transform = 'translateY(1px)';
                    this.style.boxShadow = '0 1px 2px rgba(0, 0, 0, 0.1)';
                });

                button.addEventListener('mouseup', function() {
                    this.style.transform = '';
                });
                button.dataset.hoverListeners = 'true';
            }

            button.dataset.styled = 'true';
        };

        // Try to find and style the button for this specific grid instance
        const findAndStyleButton = function() {
            const columnVisibilityOptions = self.config.columnVisibilityOptions || {};
            const buttonPlaceholderId = columnVisibilityOptions.buttonPlaceholderId;

            let button = null;
            let buttonContainer = null;
            let placeholder = null;

            // First, try to find button within the specific placeholder for this grid
            if (buttonPlaceholderId) {
                placeholder = document.getElementById(buttonPlaceholderId);
                if (placeholder) {
                    button = placeholder.querySelector('.ag-column-visibility-button');
                    buttonContainer = placeholder.querySelector('.ag-column-visibility-button-container');
                    stylePlaceholder(placeholder);
                }
            }

            // Fallback: try to find button near this grid's container
            // Only look in containers that are siblings or parents of THIS grid
            if (!button && self.gridDiv) {
                // Get the grid container ID to match against
                const gridContainerId = self.config.containerId;

                // Look for button container near THIS specific grid
                // Check parent containers of this grid
                let searchContainer = self.gridDiv.parentElement;
                while (searchContainer && searchContainer !== document.body) {
                    // Check if this container has the grid or is a table container for this grid
                    const hasThisGrid = searchContainer.querySelector('#' + gridContainerId) !== null;
                    if (hasThisGrid) {
                        button = searchContainer.querySelector('.ag-column-visibility-button');
                        buttonContainer = button ? button.closest('.ag-column-visibility-button-container') : null;
                        if (buttonContainer) break;
                    }
                    searchContainer = searchContainer.parentElement;
                }

                // Also check the grid div itself and immediate parent
                if (!button) {
                    button = self.gridDiv.querySelector('.ag-column-visibility-button');
                    buttonContainer = button ? button.closest('.ag-column-visibility-button-container') : null;
                }
                if (!button && self.gridDiv.parentElement) {
                    button = self.gridDiv.parentElement.querySelector('.ag-column-visibility-button');
                    buttonContainer = button ? button.closest('.ag-column-visibility-button-container') : null;
                }
            }

            // Only move button if it's actually near THIS grid (not another grid's button)
            if (buttonContainer && buttonPlaceholderId) {
                // Verify this button container is actually related to this grid
                const containerParent = buttonContainer.parentElement;
                const isNearThisGrid = self.gridDiv && (
                    containerParent === self.gridDiv.parentElement ||
                    containerParent.contains(self.gridDiv) ||
                    self.gridDiv.parentElement && self.gridDiv.parentElement.contains(buttonContainer)
                );

                // Also check if button is already in the correct placeholder
                const isInCorrectPlaceholder = buttonContainer.parentElement &&
                    buttonContainer.parentElement.id === buttonPlaceholderId;

                if (isNearThisGrid || isInCorrectPlaceholder) {
                    const moved = moveButtonToPlaceholder(buttonContainer, buttonPlaceholderId);
                    // Re-get placeholder after move
                    placeholder = document.getElementById(buttonPlaceholderId);
                    if (placeholder) {
                        stylePlaceholder(placeholder);
                        // If moved, re-query button from placeholder
                        if (moved) {
                            button = placeholder.querySelector('.ag-column-visibility-button');
                        }
                    }
                }
            }

            // Ensure placeholder is styled even if no button found yet
            if (buttonPlaceholderId && !placeholder) {
                placeholder = document.getElementById(buttonPlaceholderId);
                if (placeholder) {
                    stylePlaceholder(placeholder);
                }
            }

            if (button) {
                styleButton(button);
            } else {
                // If we can't find the specific button, style all buttons as fallback
                // This ensures all buttons get styled even if the specific one isn't found yet
                const allButtons = document.querySelectorAll('.ag-column-visibility-button');
                allButtons.forEach(function(btn) {
                    styleButton(btn);
                });
            }
        };

        // Set up MutationObserver to watch for button insertion
        const setupButtonObserver = function() {
            const columnVisibilityOptions = self.config.columnVisibilityOptions || {};
            const buttonPlaceholderId = columnVisibilityOptions.buttonPlaceholderId;

            if (!buttonPlaceholderId) return;

            const placeholder = document.getElementById(buttonPlaceholderId);
            if (!placeholder) {
                // Retry if placeholder not found yet
                setTimeout(setupButtonObserver, 100);
                return;
            }

            // Style placeholder immediately
            stylePlaceholder(placeholder);

            // Also style any existing containers
            const existingContainers = placeholder.querySelectorAll('.ag-column-visibility-button-container');
            existingContainers.forEach(function(container) {
                container.style.cssText = 'display: inline-block !important; margin: 0 !important; text-align: left !important; width: auto !important;';
                const btn = container.querySelector('.ag-column-visibility-button');
                if (btn) {
                    styleButton(btn);
                }
            });

            // Watch for button container insertion and text changes
            const observer = new MutationObserver(function(mutations) {
                const gridContainerId = self.config.containerId;

                mutations.forEach(function(mutation) {
                    mutation.addedNodes.forEach(function(node) {
                        if (node.nodeType === 1) {
                            // Check if it's a button container
                            if (node.classList && node.classList.contains('ag-column-visibility-button-container')) {
                                // Only move if this button is related to THIS grid
                                // Check if button container is near this grid's container
                                const isRelatedToThisGrid = self.gridDiv && (
                                    mutation.target === self.gridDiv ||
                                    mutation.target === self.gridDiv.parentElement ||
                                    (mutation.target.contains && mutation.target.contains(self.gridDiv)) ||
                                    (self.gridDiv.parentElement && self.gridDiv.parentElement.contains(node))
                                );

                                // Also check if it's already in the correct placeholder
                                const isInCorrectPlaceholder = node.parentElement &&
                                    node.parentElement.id === buttonPlaceholderId;

                                if (isRelatedToThisGrid || isInCorrectPlaceholder) {
                                    // Move to placeholder if needed
                                    moveButtonToPlaceholder(node, buttonPlaceholderId);

                                    // Style the container
                                    node.style.cssText = 'display: inline-block !important; margin: 0 !important; text-align: left !important; width: auto !important;';

                                    // Style the button
                                    const btn = node.querySelector('.ag-column-visibility-button');
                                    if (btn) {
                                        styleButton(btn);
                                    }
                                }
                            }
                            // Also check if a button was added directly
                            if (node.classList && node.classList.contains('ag-column-visibility-button')) {
                                // Only style if it's related to this grid
                                const isRelated = self.gridDiv && (
                                    mutation.target === self.gridDiv ||
                                    mutation.target === self.gridDiv.parentElement ||
                                    (mutation.target.contains && mutation.target.contains(self.gridDiv))
                                );
                                if (isRelated) {
                                    styleButton(node);
                                }
                            }
                            // Check for buttons added to existing containers
                            const buttons = node.querySelectorAll && node.querySelectorAll('.ag-column-visibility-button');
                            if (buttons && buttons.length > 0) {
                                buttons.forEach(function(btn) {
                                    const isRelated = self.gridDiv && (
                                        mutation.target === self.gridDiv ||
                                        mutation.target === self.gridDiv.parentElement ||
                                        (mutation.target.contains && mutation.target.contains(self.gridDiv))
                                    );
                                    if (isRelated) {
                                        styleButton(btn);
                                    }
                                });
                            }
                        }
                    });

                    // Watch for text/content changes in buttons (fallback)
                    if (mutation.type === 'childList' || mutation.type === 'characterData') {
                        const target = mutation.target;
                        if (target.classList && target.classList.contains('ag-column-visibility-button')) {
                            ensureIconOnly(target);
                        }
                        // Also check if mutation happened inside a button
                        const button = target.closest && target.closest('.ag-column-visibility-button');
                        if (button) {
                            ensureIconOnly(button);
                        }
                    }
                });

                // Also check existing containers in THIS placeholder only
                const containers = placeholder.querySelectorAll('.ag-column-visibility-button-container');
                containers.forEach(function(container) {
                    container.style.cssText = 'display: inline-block !important; margin: 0 !important; text-align: left !important; width: auto !important;';
                    const btn = container.querySelector('.ag-column-visibility-button');
                    if (btn) {
                        styleButton(btn);
                    }
                });
            });

            // Observe placeholder and grid container
            observer.observe(placeholder, { childList: true, subtree: true, characterData: true });
            if (self.gridDiv) {
                // Watch the grid div itself
                observer.observe(self.gridDiv, { childList: true, subtree: true, characterData: true });

                // Watch parent containers
                const gridParent = self.gridDiv.closest('[id*="table-container"], [id*="Grid"], .bg-white');
                if (gridParent && gridParent !== placeholder) {
                    observer.observe(gridParent, { childList: true, subtree: true, characterData: true });
                }

                // Also watch the grid's parent's parent to catch table containers
                if (self.gridDiv.parentElement) {
                    observer.observe(self.gridDiv.parentElement, { childList: true, subtree: true, characterData: true });
                }
            }
        };

        // Set up observer
        setupButtonObserver();

        // Try immediately, then retry after delays to handle async button creation
        findAndStyleButton();
        setTimeout(findAndStyleButton, 300);
        setTimeout(findAndStyleButton, 600);
        setTimeout(findAndStyleButton, 1000);

        // Also set up a global observer to catch buttons created elsewhere
        // Use multiple timeouts to catch buttons that are updated after creation
        // ColumnVisibilityManager updates button text at 100ms, so we check after that
        const processAllButtons = function() {
            const columnVisibilityOptions = self.config.columnVisibilityOptions || {};
            const phId = columnVisibilityOptions.buttonPlaceholderId;
            const gridContainerId = self.config.containerId;

            if (!phId || !self.gridDiv) return;

            // Only process buttons that are related to THIS grid
            // Find buttons near this grid's container
            let searchScope = self.gridDiv.parentElement;
            const buttonsToProcess = [];

            // Look for buttons in the same parent container as this grid
            if (searchScope) {
                const buttons = searchScope.querySelectorAll('.ag-column-visibility-button');
                buttons.forEach(function(btn) {
                    const btnContainer = btn.closest('.ag-column-visibility-button-container');
                    // Check if button is near this grid
                    if (btnContainer && (
                        btnContainer.parentElement === searchScope ||
                        searchScope.contains(btnContainer)
                    )) {
                        buttonsToProcess.push({button: btn, container: btnContainer});
                    }
                });
            }

            // Process buttons found near this grid
            buttonsToProcess.forEach(function(item) {
                styleButton(item.button);
                // Move to correct placeholder
                if (item.container && phId) {
                    moveButtonToPlaceholder(item.container, phId);
                }
            });

            // Ensure placeholder is styled
            if (phId) {
                const ph = document.getElementById(phId);
                if (ph) stylePlaceholder(ph);
            }
        };

        setTimeout(processAllButtons, 150);
        setTimeout(processAllButtons, 500);
        setTimeout(processAllButtons, 1500);

        // Set up a global observer to watch all buttons for text changes (fallback)
        const globalObserver = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'childList' || mutation.type === 'characterData') {
                    const button = mutation.target.closest && mutation.target.closest('.ag-column-visibility-button');
                    if (button) {
                        ensureIconOnly(button);
                    }
                    // Also check if target is a button itself
                    if (mutation.target.classList && mutation.target.classList.contains('ag-column-visibility-button')) {
                        ensureIconOnly(mutation.target);
                    }
                }
            });
        });

        // Observe all existing and future buttons
        setTimeout(function() {
            const allButtons = document.querySelectorAll('.ag-column-visibility-button');
            allButtons.forEach(function(btn) {
                globalObserver.observe(btn, { childList: true, subtree: true, characterData: true });
            });
        }, 200);

        // Also watch document for new buttons
        const documentObserver = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === 1) {
                        const buttons = node.querySelectorAll ? node.querySelectorAll('.ag-column-visibility-button') : [];
                        if (node.classList && node.classList.contains('ag-column-visibility-button')) {
                            buttons.push(node);
                        }
                        buttons.forEach(function(btn) {
                            styleButton(btn);
                            globalObserver.observe(btn, { childList: true, subtree: true, characterData: true });
                        });
                    }
                });
            });
        });
        documentObserver.observe(document.body, { childList: true, subtree: true });
    };

    /**
     * Update grid data
     * @param {Array} rowData - New row data
     */
    AgGridHelper.prototype.setRowData = function(rowData) {
        if (!this.gridApi) {
            console.warn('AgGridHelper: gridApi not available');
            return;
        }

        // Update config rowData
        this.config.rowData = rowData || [];

        // Handle both createGrid API (v31+) and old Grid API
        // Try setGridOption first (createGrid API)
        if (typeof this.gridApi.setGridOption === 'function') {
            this.gridApi.setGridOption('rowData', rowData);
        }
        // Fallback to setRowData (old API)
        else if (typeof this.gridApi.setRowData === 'function') {
            this.gridApi.setRowData(rowData);
        }
        // Try on gridInstance if available (createGrid API)
        else if (this.gridInstance && typeof this.gridInstance.setGridOption === 'function') {
            this.gridInstance.setGridOption('rowData', rowData);
        }
        else {
            console.warn('AgGridHelper: Unable to set row data - API method not found');
        }

        // Recalculate height after data is updated
        const self = this;
        setTimeout(function() {
            self.setDynamicHeight();
        }, 100);
    };

    /**
     * Get selected rows
     * Only returns rows that are currently displayed (visible after filtering)
     * This ensures that when filters are applied, "select all" only selects visible rows
     * @returns {Array} Array of selected row data
     */
    AgGridHelper.prototype.getSelectedRows = function() {
        if (!this.gridApi) {
            return [];
        }

        // Prefer selected nodes when available (most consistent across AG Grid versions)
        // Filter to only include displayed nodes (visible after filtering)
        if (typeof this.gridApi.getSelectedNodes === 'function') {
            try {
                const nodes = this.gridApi.getSelectedNodes() || [];
                return nodes
                    .filter(function(node) {
                        // Only include nodes that are currently displayed (visible after filtering)
                        // node.displayed === true means the node passes all filters and is visible
                        // If displayed property doesn't exist, assume it's displayed (backward compatibility)
                        return node && (node.displayed === true || node.displayed === undefined);
                    })
                    .map(function(node) { return node ? node.data : null; })
                    .filter(function(row) { return row !== null && row !== undefined; });
            } catch (e) {
                // fall through
            }
        }

        // Fallback: iterate through displayed nodes only
        const selectedRows = [];
        // Use forEachNodeAfterFilter if available to only iterate displayed nodes
        if (typeof this.gridApi.forEachNodeAfterFilter === 'function') {
            this.gridApi.forEachNodeAfterFilter(function(node) {
                if (node.isSelected()) {
                    selectedRows.push(node.data);
                }
            });
        } else if (typeof this.gridApi.forEachNode === 'function') {
            // Fallback: iterate all nodes but filter by displayed property
            this.gridApi.forEachNode(function(node) {
                // Only include selected nodes that are displayed (visible after filtering)
                if (node.isSelected() && (node.displayed === true || node.displayed === undefined)) {
                    selectedRows.push(node.data);
                }
            });
        } else if (typeof this.gridApi.getSelectedRows === 'function') {
            // Last resort: use getSelectedRows (may include filtered rows in some AG Grid versions)
            // This is less ideal but better than nothing
            return this.gridApi.getSelectedRows();
        }
        return selectedRows;
    };

    /**
     * Get a consistent snapshot of current selection.
     * @param {string} idField - Field name containing the ID (default: 'id')
     * @returns {{selectedRows: Array, selectedIds: Array, selectedCount: number}}
     */
    AgGridHelper.prototype.getSelectionSnapshot = function(idField) {
        idField = idField || 'id';
        const selectedRows = this.getSelectedRows();
        const selectedIds = selectedRows.map(function(row) {
            return row ? row[idField] : null;
        }).filter(function(id) {
            return id !== null && id !== undefined;
        });
        return {
            selectedRows: selectedRows,
            selectedIds: selectedIds,
            selectedCount: selectedRows.length
        };
    };

    /**
     * Get selected row IDs
     * @param {string} idField - Field name containing the ID (default: 'id')
     * @returns {Array} Array of selected IDs
     */
    AgGridHelper.prototype.getSelectedRowIds = function(idField) {
        idField = idField || 'id';
        const selectedRows = this.getSelectedRows();
        return selectedRows.map(function(row) {
            return row[idField];
        }).filter(function(id) {
            return id !== null && id !== undefined;
        });
    };

    /**
     * Dispatch a DOM event with current selection details.
     * Events are dispatched on the grid element AND on document for convenience.
     *
     * Event name: 'ag-grid-selection-changed'
     * detail: { gridId, templateId, selectedCount, selectedIds, selectedRows }
     */
    AgGridHelper.prototype.dispatchSelectionChanged = function() {
        try {
            const snapshot = this.getSelectionSnapshot('id');
            const detail = Object.assign({
                gridId: this.config.containerId,
                templateId: this.config.templateId
            }, snapshot);

            // Note: CustomEvent cannot be re-dispatched; create separate instances.
            if (this.gridDiv && typeof this.gridDiv.dispatchEvent === 'function') {
                this.gridDiv.dispatchEvent(new CustomEvent('ag-grid-selection-changed', { detail: detail }));
            }
            if (typeof document !== 'undefined' && document && typeof document.dispatchEvent === 'function') {
                document.dispatchEvent(new CustomEvent('ag-grid-selection-changed', { detail: detail }));
            }
        } catch (e) {
            // Never break grid usage due to selection event issues
        }
    };

    /**
     * Attach a selectionChanged listener and emit selection events.
     * Safe to call multiple times; only attaches once per helper instance.
     */
    AgGridHelper.prototype.setupSelectionChangedDispatcher = function() {
        if (this._selectionChangedDispatcherAttached) {
            return;
        }
        this._selectionChangedDispatcherAttached = true;

        const self = this;
        const emit = function() {
            self.dispatchSelectionChanged();
        };

        // Prefer native grid events when available
        if (this.gridApi && typeof this.gridApi.addEventListener === 'function') {
            try {
                this.gridApi.addEventListener('selectionChanged', emit);
                // Some AG Grid versions fire rowSelected more reliably for checkbox selection.
                this.gridApi.addEventListener('rowSelected', emit);
            } catch (e) {
                // Ignore
            }
        }

        // Emit once after init so UI can reflect default/remembered selection state
        setTimeout(function() {
            emit();
        }, 0);
    };

    /**
     * Setup custom right-click context menu (Copy cell, Export table to Excel).
     * Uses DOM listener so it works in AG Grid Community edition (context menu is Enterprise-only).
     */
    AgGridHelper.prototype.setupContextMenuFallback = function() {
        if (!this.gridDiv || !this.gridApi) {
            return;
        }
        if (this._contextMenuFallbackAttached) {
            return;
        }
        this._contextMenuFallbackAttached = true;

        const self = this;

        this.gridDiv.addEventListener('contextmenu', function(ev) {
            const cell = ev.target.closest && ev.target.closest('.ag-cell');
            if (!cell) {
                return;
            }
            ev.preventDefault();
            ev.stopPropagation();

            const rowEl = cell.closest && cell.closest('.ag-row');
            const rowIndexAttr = rowEl && (rowEl.getAttribute('row-index') || rowEl.getAttribute('data-row-index'));
            const rowIndex = rowIndexAttr != null ? parseInt(rowIndexAttr, 10) : -1;
            const colId = cell.getAttribute('col-id') || cell.getAttribute('data-col-id') || '';

            let cellValue = '';
            let rowNodeForCopy = null;
            if (self.gridApi && rowIndex >= 0 && colId) {
                if (typeof self.gridApi.getDisplayedRowAtIndex === 'function') {
                    const rowNode = self.gridApi.getDisplayedRowAtIndex(rowIndex);
                    if (rowNode && rowNode.data) {
                        rowNodeForCopy = rowNode;
                        var val = rowNode.data[colId];
                        if (self._gridOptions && typeof self._gridOptions.processCellForClipboard === 'function') {
                            var column = (self.gridApi.getColumn && self.gridApi.getColumn(colId)) || (self.columnApi && self.columnApi.getColumn && self.columnApi.getColumn(colId));
                            var processed = self._gridOptions.processCellForClipboard({
                                value: val,
                                node: rowNode,
                                column: column,
                                api: self.gridApi,
                                columnApi: self.columnApi,
                                context: self._gridOptions.context,
                                type: 'clipboard'
                            });
                            cellValue = processed == null ? '' : String(processed);
                        } else {
                            cellValue = val == null ? '' : String(val);
                        }
                    }
                } else if (typeof self.gridApi.forEachNodeAfterFilterAndSort === 'function') {
                    var idx = 0;
                    self.gridApi.forEachNodeAfterFilterAndSort(function(node) {
                        if (idx === rowIndex && node.data) {
                            rowNodeForCopy = node;
                            var val = node.data[colId];
                            if (self._gridOptions && typeof self._gridOptions.processCellForClipboard === 'function') {
                                var column = (self.gridApi.getColumn && self.gridApi.getColumn(colId)) || (self.columnApi && self.columnApi.getColumn && self.columnApi.getColumn(colId));
                                var processed = self._gridOptions.processCellForClipboard({
                                    value: val,
                                    node: node,
                                    column: column,
                                    api: self.gridApi,
                                    columnApi: self.columnApi,
                                    context: self._gridOptions.context,
                                    type: 'clipboard'
                                });
                                cellValue = processed == null ? '' : String(processed);
                            } else {
                                cellValue = val == null ? '' : String(val);
                            }
                        }
                        idx += 1;
                    });
                }
            }

            const api = self.gridApi;
            const menu = document.createElement('div');
            menu.className = 'ag-grid-custom-context-menu';
            menu.setAttribute('role', 'menu');
            menu.style.cssText = 'position:fixed;z-index:10000;min-width:180px;background:#fff;border:1px solid #d1d5db;border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,0.15);padding:4px 0;font-family:inherit;font-size:14px;';

            function addItem(label, action) {
                const item = document.createElement('div');
                item.setAttribute('role', 'menuitem');
                item.textContent = label;
                item.style.cssText = 'padding:8px 14px;cursor:pointer;white-space:nowrap;';
                item.addEventListener('mouseenter', function() {
                    item.style.background = '#f3f4f6';
                });
                item.addEventListener('mouseleave', function() {
                    item.style.background = '';
                });
                item.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    action();
                    closeMenu();
                });
                menu.appendChild(item);
            }

            addItem('Copy cell', function() {
                const text = cellValue;
                if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
                    navigator.clipboard.writeText(text).catch(function() {
                        fallbackCopyToClipboard(text);
                    });
                } else {
                    fallbackCopyToClipboard(text);
                }
            });

            addItem('Export table to Excel', function() {
                self.exportTableToCSV(api, 'export.csv');
            });

            document.body.appendChild(menu);

            const x = ev.clientX;
            const y = ev.clientY;
            const menuRect = menu.getBoundingClientRect();
            const vw = window.innerWidth || document.documentElement.clientWidth;
            const vh = window.innerHeight || document.documentElement.clientHeight;
            let left = x;
            let top = y;
            if (x + menuRect.width > vw) {
                left = vw - menuRect.width - 8;
            }
            if (y + menuRect.height > vh) {
                top = vh - menuRect.height - 8;
            }
            if (left < 8) left = 8;
            if (top < 8) top = 8;
            menu.style.left = left + 'px';
            menu.style.top = top + 'px';

            function closeMenu() {
                if (menu.parentNode) {
                    menu.parentNode.removeChild(menu);
                }
                document.removeEventListener('click', closeMenu);
                document.removeEventListener('keydown', onKey);
            }

            function onKey(e) {
                if (e.key === 'Escape') {
                    closeMenu();
                }
            }

            document.addEventListener('click', closeMenu);
            document.addEventListener('keydown', onKey);
            setTimeout(function() {
                document.addEventListener('click', closeMenu);
            }, 0);
        }.bind(this));
    };

    /**
     * Refresh grid (recalculate row heights, etc.)
     */
    AgGridHelper.prototype.refresh = function() {
        if (!this.gridApi) {
            return;
        }

        // Check if auto row height is enabled
        // Auto row height is enabled if defaultColDef has autoHeight: true
        // or if any column definition has autoHeight: true
        const hasAutoHeight = this.hasAutoRowHeight();

        // Only call resetRowHeights if auto row height is NOT enabled
        // When auto row height is enabled, AG Grid automatically calculates heights
        if (!hasAutoHeight && typeof this.gridApi.resetRowHeights === 'function') {
            this.gridApi.resetRowHeights();
        }

        const self = this;
        const apiToUse = (this.gridApi && this.gridApi.api && typeof this.gridApi.api.doLayout === 'function')
            ? this.gridApi.api
            : this.gridApi;

        const forceSizeToFit = !!(this.config && this.config.options && this.config.options.sizeColumnsToFitOnRefresh === true);
        const shouldSizeToFit = (apiToUse && typeof apiToUse.sizeColumnsToFit === 'function') &&
            (forceSizeToFit || !this._hasSizedColumnsToFit);
        const shouldDoLayout = apiToUse && typeof apiToUse.doLayout === 'function';

        if (shouldDoLayout || shouldSizeToFit) {
            setTimeout(function() {
                // Only act if grid is visible (prevents fighting with hidden tabs/containers)
                if (self.isGridVisible && typeof self.isGridVisible === 'function' && !self.isGridVisible()) {
                    self.scheduleCheckboxWidthEnforcement();
                    return;
                }

                try {
                    if (shouldDoLayout) {
                        apiToUse.doLayout();
                    }
                } catch (e) {
                    // Non-fatal
                }

                try {
                    if (shouldSizeToFit) {
                        apiToUse.sizeColumnsToFit();
                        self._hasSizedColumnsToFit = true;
                    }
                } catch (e) {
                    // Non-fatal
                }

                self.scheduleCheckboxWidthEnforcement();
            }, 100);
        } else {
            this.scheduleCheckboxWidthEnforcement();
        }
    };

    /**
     * Check if the grid is visible (has width > 0)
     * @returns {boolean} True if grid is visible
     */
    AgGridHelper.prototype.isGridVisible = function() {
        if (!this.gridDiv) {
            return false;
        }
        const rect = this.gridDiv.getBoundingClientRect();
        const style = window.getComputedStyle(this.gridDiv);
        // Check if element has width > 0 and is not hidden
        return rect.width > 0 &&
               style.display !== 'none' &&
               style.visibility !== 'hidden' &&
               style.opacity !== '0';
    };

    /**
     * Check if auto row height is enabled in the grid
     * @returns {boolean} True if auto row height is enabled
     */
    AgGridHelper.prototype.hasAutoRowHeight = function() {
        // Check defaultColDef from custom options (overrides)
        const customDefaultColDef = this.config.options?.defaultColDef;
        if (customDefaultColDef && customDefaultColDef.autoHeight === true) {
            return true;
        }

        // Check defaultColDef from default options (helper default)
        const defaultOptions = this.getDefaultGridOptions();
        if (defaultOptions.defaultColDef && defaultOptions.defaultColDef.autoHeight === true) {
            // Only return true if not explicitly overridden to false
            if (!customDefaultColDef || customDefaultColDef.autoHeight !== false) {
                return true;
            }
        }

        // Check if any column has autoHeight enabled
        if (this.config.columnDefs && Array.isArray(this.config.columnDefs)) {
            for (let i = 0; i < this.config.columnDefs.length; i++) {
                if (this.config.columnDefs[i].autoHeight === true) {
                    return true;
                }
            }
        }

        return false;
    };

    /**
     * Export selected rows to CSV
     * @param {string} filename - Filename for export (default: 'export.csv')
     */
    AgGridHelper.prototype.exportSelectedToCSV = function(filename) {
        filename = filename || 'export.csv';
        const selectedRows = this.getSelectedRows();

        if (selectedRows.length === 0) {
            console.warn('AgGridHelper: No rows selected for export');
            return;
        }

        // Simple CSV export
        const headers = this.config.columnDefs
            .filter(function(col) { return col.field && !col.hide; })
            .map(function(col) { return col.headerName || col.field; });

        const rows = selectedRows.map(function(row) {
            return this.config.columnDefs
                .filter(function(col) { return col.field && !col.hide; })
                .map(function(col) {
                    const value = row[col.field];
                    // Escape CSV values
                    if (value === null || value === undefined) return '';
                    const str = String(value).replace(/"/g, '""');
                    return str.includes(',') || str.includes('\n') ? '"' + str + '"' : str;
                });
        }, this);

        const csv = [headers.join(','), ...rows.map(function(row) { return row.join(','); })].join('\n');

        // Download
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.click();
    };

    /**
     * Export full table (all displayed rows after filter/sort) to CSV.
     * Used by the context menu "Export table to Excel" (Excel opens CSV files).
     * @param {Object} api - AG Grid API (from params.api or this.gridApi)
     * @param {string} filename - Filename for export (default: 'export.csv')
     */
    AgGridHelper.prototype.exportTableToCSV = function(api, filename) {
        filename = filename || 'export.csv';
        if (!api) {
            api = this.gridApi;
        }
        if (!api) {
            console.warn('AgGridHelper: No grid API for export');
            return;
        }

        var visibleCols = [];
        if (typeof api.getColumns === 'function') {
            var cols = api.getColumns();
            if (cols && cols.length) {
                visibleCols = cols
                    .filter(function(col) {
                        var def = col.getColDef ? col.getColDef() : (col.colDef || {});
                        var field = def.field || (col.getColId ? col.getColId() : col.colId);
                        var visible = col.getVisible ? col.getVisible() : (col.visible !== false);
                        return field && visible;
                    })
                    .map(function(col) {
                        var def = col.getColDef ? col.getColDef() : (col.colDef || {});
                        return {
                            field: def.field || (col.getColId ? col.getColId() : col.colId),
                            headerName: def.headerName || def.field || (col.getColId ? col.getColId() : col.colId)
                        };
                    });
            }
        }
        if (!visibleCols.length) {
            var columnDefs = this.config.columnDefs || [];
            visibleCols = columnDefs.filter(function(col) { return col.field && col.hide !== true; });
        }
        var headers = visibleCols.map(function(col) { return col.headerName || col.field; });

        const rowData = [];
        if (typeof api.forEachNodeAfterFilterAndSort === 'function') {
            api.forEachNodeAfterFilterAndSort(function(node) {
                if (node && node.data) {
                    const row = visibleCols.map(function(col) {
                        const value = node.data[col.field];
                        if (value === null || value === undefined) return '';
                        const str = String(value).replace(/"/g, '""');
                        return str.includes(',') || str.includes('\n') ? '"' + str + '"' : str;
                    });
                    rowData.push(row);
                }
            });
        } else if (typeof api.forEachNode === 'function') {
            api.forEachNode(function(node) {
                if (node && node.data && (node.displayed === true || node.displayed === undefined)) {
                    const row = visibleCols.map(function(col) {
                        const value = node.data[col.field];
                        if (value === null || value === undefined) return '';
                        const str = String(value).replace(/"/g, '""');
                        return str.includes(',') || str.includes('\n') ? '"' + str + '"' : str;
                    });
                    rowData.push(row);
                }
            });
        }

        const csv = [headers.join(','), ...rowData.map(function(row) { return row.join(','); })].join('\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.click();
    };

    /**
     * Get column API reference if available
     * @returns {Object|null}
     */
    AgGridHelper.prototype.getColumnApi = function() {
        if (this.columnApi) {
            return this.columnApi;
        }
        if (this.gridInstance) {
            if (this.gridInstance.columnApi) {
                this.columnApi = this.gridInstance.columnApi;
                return this.columnApi;
            }
            if (this.gridInstance.api && this.gridInstance.api.columnApi) {
                this.columnApi = this.gridInstance.api.columnApi;
                return this.columnApi;
            }
        }
        if (this.gridApi && this.gridApi.columnApi) {
            this.columnApi = this.gridApi.columnApi;
            return this.columnApi;
        }
        return null;
    };

    /**
     * Setup listeners to keep checkbox columns at a fixed width
     */
    AgGridHelper.prototype.setupCheckboxColumnWidthHandling = function() {
        const self = this;
        this.scheduleCheckboxWidthEnforcement();

        if (this.gridApi && typeof this.gridApi.addEventListener === 'function') {
            this.gridApi.addEventListener('gridSizeChanged', function() {
                self.scheduleCheckboxWidthEnforcement();
            });

            this.gridApi.addEventListener('columnResized', function(event) {
                if (!event) {
                    return;
                }
                const affectedColumns = [];
                if (event.column) {
                    affectedColumns.push(event.column);
                }
                if (Array.isArray(event.columns)) {
                    Array.prototype.push.apply(affectedColumns, event.columns);
                }
                const shouldLock = affectedColumns.some(function(column) {
                    return self.isCheckboxColumn(column);
                });
                if (shouldLock) {
                    self.scheduleCheckboxWidthEnforcement();
                }
            });

            this.gridApi.addEventListener('columnMoved', function(event) {
                if (event && event.column && self.isCheckboxColumn(event.column)) {
                    self.scheduleCheckboxWidthEnforcement();
                }
            });
        }
    };

    /**
     * Debounced enforcement helper
     */
    AgGridHelper.prototype.scheduleCheckboxWidthEnforcement = function() {
        if (!this.gridApi) {
            return;
        }
        if (this.checkboxWidthTimeout) {
            clearTimeout(this.checkboxWidthTimeout);
        }
        const self = this;
        this.checkboxWidthTimeout = setTimeout(function() {
            self.enforceCheckboxColumnWidth();
        }, 80);
    };

    /**
     * Force checkbox columns to stay at their configured width
     */
    AgGridHelper.prototype.enforceCheckboxColumnWidth = function() {
        const columnIds = this.getCheckboxColumnIds();
        if (!columnIds.length) {
            return;
        }

        const columnApi = this.getColumnApi();
        const width = this.config.checkboxColumnWidth || 56;

        columnIds.forEach(function(colId) {
            this.applyCheckboxWidthConstraints(columnApi, colId, width);
        }, this);

        if (columnApi && typeof columnApi.refreshHeader === 'function') {
            columnApi.refreshHeader();
        } else if (this.gridApi && typeof this.gridApi.refreshHeader === 'function') {
            this.gridApi.refreshHeader();
        }
    };

    /**
     * Identify checkbox selection columns by inspecting the column definitions and DOM
     * @returns {Array<string>}
     */
    AgGridHelper.prototype.getCheckboxColumnIds = function() {
        const ids = new Set();

        if (this.gridApi && typeof this.gridApi.getColumns === 'function') {
            const columns = this.gridApi.getColumns();
            if (Array.isArray(columns)) {
                columns.forEach(function(column) {
                    if (this.isCheckboxColumn(column)) {
                        const colId = (typeof column.getColId === 'function')
                            ? column.getColId()
                            : (column.colId || (column.getColDef && column.getColDef().field));
                        if (colId) {
                            ids.add(colId);
                        }
                    }
                }, this);
            }
        }

        if (!ids.size && this.gridDiv) {
            const headerCells = this.gridDiv.querySelectorAll('.ag-header-cell');
            headerCells.forEach(function(cell) {
                if (cell.querySelector('.ag-header-select-all')) {
                    const colId = cell.getAttribute('col-id');
                    if (colId) {
                        ids.add(colId);
                    }
                }
            });
        }

        if (!ids.size && this.gridDiv) {
            const checkboxCells = this.gridDiv.querySelectorAll('.ag-center-cols-container .ag-row:first-child .ag-cell');
            checkboxCells.forEach(function(cell) {
                if (cell.querySelector('.ag-selection-checkbox')) {
                    const colId = cell.getAttribute('col-id');
                    if (colId) {
                        ids.add(colId);
                    }
                }
            });
        }

        return Array.from(ids);
    };

    /**
     * Determine whether a given column instance represents the checkbox selection column
     * @param {Object} column - Column instance
     * @returns {boolean}
     */
    AgGridHelper.prototype.isCheckboxColumn = function(column) {
        if (!column) {
            return false;
        }
        const colDef = (typeof column.getColDef === 'function') ? column.getColDef() : (column.colDef || {});
        if (!colDef) {
            return false;
        }
        if (colDef.checkboxSelection === true || colDef.headerCheckboxSelection === true || colDef.__checkboxColumn === true) {
            return true;
        }
        const colId = (typeof column.getColId === 'function') ? column.getColId() : (colDef.colId || colDef.field || '');
        if (!colId) {
            return false;
        }
        const normalized = colId.toLowerCase();
        return normalized.includes('checkbox') || normalized.includes('selection');
    };

    /**
     * Apply width constraints to checkbox columns
     * @param {Object|null} columnApi
     * @param {string} colId
     * @param {number} width
     */
    AgGridHelper.prototype.applyCheckboxWidthConstraints = function(columnApi, colId, width) {
        if (!colId) {
            return;
        }

        let applied = false;

        if (columnApi && typeof columnApi.applyColumnState === 'function') {
            try {
                columnApi.applyColumnState({
                    state: [{
                        colId: colId,
                        width: width,
                        maxWidth: width,
                        minWidth: width
                    }],
                    applyOrder: false
                });
                applied = true;
            } catch (error) {
                console.warn('AgGridHelper: Unable to apply checkbox column state for', colId, error);
            }
        }

        if (!applied && columnApi && typeof columnApi.setColumnWidth === 'function') {
            try {
                columnApi.setColumnWidth(colId, width, true);
                applied = true;
            } catch (error) {
                console.warn('AgGridHelper: Unable to set checkbox column width for', colId, error);
            }
        }

        if (!applied && this.gridApi && typeof this.gridApi.setColumnWidth === 'function') {
            try {
                this.gridApi.setColumnWidth(colId, width, true);
            } catch (error) {
                console.warn('AgGridHelper: Fallback width application failed for', colId, error);
            }
        }

        const column = columnApi && typeof columnApi.getColumn === 'function'
            ? columnApi.getColumn(colId)
            : (this.gridApi && typeof this.gridApi.getColumn === 'function' ? this.gridApi.getColumn(colId) : null);

        if (column && typeof column.getColDef === 'function') {
            const colDef = column.getColDef();
            colDef.minWidth = width;
            colDef.maxWidth = width;
            colDef.width = width;
            colDef.resizable = false;
            colDef.suppressSizeToFit = true;
            colDef.__checkboxColumn = true;
        }
    };

    // -----------------------------------------------------------------
    //  Auto-detect filter type per column
    // -----------------------------------------------------------------

    /**
     * Analyse row data and choose the best AG Grid filter for each column.
     *
     * Rules (applied only to columns that have NOT set an explicit filter):
     *  1. Columns with filter:false or a named filter string → skip.
     *  2. If all non-empty values are numeric → agNumberColumnFilter.
     *  3. If unique value count ≤ threshold → customSetFilter.
     *  4. Otherwise → agTextColumnFilter.
     *
     * @param {Array}  columnDefs  - Mutable array of column definitions.
     * @param {Array}  rowData     - The row data that will feed the grid.
     * @param {Object} [opts]
     * @param {number} [opts.maxUniqueValues=150]  - Max distinct values for set-filter.
     * @param {number} [opts.maxValueLengthForSetFilter=40] - Max value length to consider categorical.
     * @param {number} [opts.forceSetFilterWhenUniqueCountLe=25] - Always use set-filter when uniques are very low.
     * @param {number} [opts.sampleSize=0]        - If > 0, sample this many rows (0 = all).
     */
    AgGridHelper.autoDetectColumnFilters = function(columnDefs, rowData, opts) {
        if (!Array.isArray(columnDefs) || !Array.isArray(rowData) || rowData.length === 0) {
            return;
        }
        if (typeof CustomSetFilter === 'undefined') {
            return;
        }

        opts = opts || {};
        // Debug logging is OFF by default; enable with { autoDetectFilterOptions: { debug: true } }
        var debug = opts.debug === true;
        var log = function() {};
        if (debug) {
            log = function() {
                try {
                    if (typeof window !== 'undefined' && typeof window.__clientLog === 'function') {
                        window.__clientLog.apply(window, arguments);
                    } else if (typeof console !== 'undefined' && console.log) {
                        console.log.apply(console, arguments);
                    }
                } catch (e) {
                    // ignore
                }
            };
        }

        var maxUnique  = (typeof opts.maxUniqueValues === 'number') ? opts.maxUniqueValues : 150;
        var maxLenForSet = (typeof opts.maxValueLengthForSetFilter === 'number')
            ? opts.maxValueLengthForSetFilter
            : 40;
        var forceSetWhenUniquesLe = (typeof opts.forceSetFilterWhenUniqueCountLe === 'number')
            ? opts.forceSetFilterWhenUniqueCountLe
            : 25;
        var sampleSize = (typeof opts.sampleSize === 'number' && opts.sampleSize > 0)
            ? Math.min(opts.sampleSize, rowData.length)
            : rowData.length;

        var rows = (sampleSize < rowData.length)
            ? rowData.slice(0, sampleSize)
            : rowData;

        var NUMERIC_RE = /^-?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;

        function shouldSkip(colDef) {
            if (colDef.filter === false) return true;
            // If template explicitly chose a non-default filter, respect it.
            // But treat agTextColumnFilter as "default" so auto-detection can override it.
            if (typeof colDef.filter === 'string') {
                if (colDef.filter === 'agTextColumnFilter') return false;
                if (colDef.filter !== 'true') return true;
            }
            if (typeof colDef.filter === 'function') return true;
            if (colDef.cellRenderer && !colDef.field) return true;
            return false;
        }

        function getFieldValue(row, colDef) {
            if (colDef.field) {
                var parts = colDef.field.split('.');
                var v = row;
                for (var i = 0; i < parts.length && v != null; i++) {
                    v = v[parts[i]];
                }
                return v;
            }
            return undefined;
        }

        columnDefs.forEach(function(colDef) {
            if (shouldSkip(colDef)) {
                if (debug) {
                    log('[AgGridHelper][autoDetectFilters] skip', {
                        field: colDef.field,
                        headerName: colDef.headerName,
                        filter: colDef.filter
                    });
                }
                return;
            }

            var uniqueSet = {};
            var uniqueCount = 0;
            var nonEmpty = 0;
            var allNumeric = true;
            var exceeded = false;
            var maxLenSeen = 0;

            for (var r = 0; r < rows.length; r++) {
                var raw = getFieldValue(rows[r], colDef);
                if (raw == null || raw === '') continue;

                var vals = Array.isArray(raw) ? raw : [raw];
                for (var vi = 0; vi < vals.length; vi++) {
                    var s = String(vals[vi]).trim();
                    if (s === '') continue;
                    nonEmpty++;
                    if (s.length > maxLenSeen) {
                        maxLenSeen = s.length;
                    }

                    if (allNumeric && !NUMERIC_RE.test(s)) {
                        allNumeric = false;
                    }

                    if (!uniqueSet[s]) {
                        uniqueSet[s] = true;
                        uniqueCount++;
                        if (uniqueCount > maxUnique) {
                            exceeded = true;
                            break;
                        }
                    }
                }
                if (exceeded) break;
            }

            if (nonEmpty === 0) return;

            if (allNumeric && nonEmpty > 0) {
                colDef.filter = 'agNumberColumnFilter';
            } else if (!exceeded && (uniqueCount <= forceSetWhenUniquesLe || maxLenSeen <= maxLenForSet)) {
                colDef.filter = 'customSetFilter';
            } else {
                colDef.filter = 'agTextColumnFilter';
            }

            if (debug) {
                log('[AgGridHelper][autoDetectFilters] choose', {
                    field: colDef.field,
                    headerName: colDef.headerName,
                    chosen: colDef.filter,
                    nonEmpty: nonEmpty,
                    uniqueCount: uniqueCount,
                    maxUniqueValues: maxUnique,
                    maxValueLength: maxLenSeen,
                    maxValueLengthForSetFilter: maxLenForSet,
                    forceSetFilterWhenUniqueCountLe: forceSetWhenUniquesLe,
                    sampledRows: rows.length
                });
            }
        });
    };

    /**
     * Static factory method for quick grid creation
     * Reduces boilerplate in templates by handling common initialization patterns
     *
     * @param {string} gridId - The DOM ID of the grid container
     * @param {string} templateId - Unique template identifier for persistence
     * @param {Array} columnDefs - Column definitions array
     * @param {Array} rowData - Initial row data
     * @param {Object} options - Additional options
     * @param {Object} options.gridOptions - AG Grid options
     * @param {Object} options.columnVisibility - Column visibility manager options
     * @param {Object} options.height - Height options
     * @param {boolean} options.autoShow - Auto show grid after init (default: true)
     * @param {string} options.loadingId - Custom loading element ID (default: gridId + '-loading')
     * @param {string} options.containerId - Custom container element ID (default: gridId + '-container')
     * @param {Function} options.onReady - Callback when grid is ready
     * @param {boolean} options.autoDetectFilters - Automatically detect filter types (default: true)
     * @param {Object} options.autoDetectFilterOptions - Options for auto-detection ({maxUniqueValues, sampleSize})
     * @returns {Object} { helper: AgGridHelper, api: gridApi }
     */
    AgGridHelper.create = function(gridId, templateId, columnDefs, rowData, options) {
        options = options || {};

        // Auto-detect filter types unless explicitly disabled
        if (options.autoDetectFilters !== false && Array.isArray(columnDefs) && Array.isArray(rowData)) {
            AgGridHelper.autoDetectColumnFilters(columnDefs, rowData, options.autoDetectFilterOptions);
        }

        var gridOptions = options.gridOptions || {};
        var columnVisibilityOptions = options.columnVisibility || {};
        var heightOptions = options.height || {};
        var autoShow = options.autoShow !== false;
        var loadingId = options.loadingId || (gridId + '-loading');
        var containerId = options.containerId || (gridId + '-container');

        // Merge default grid options
        var mergedGridOptions = Object.assign({
            getRowHeight: function() {
                return null; // Auto-height by default
            }
        }, gridOptions);

        // Merge default column visibility options
        var mergedColumnVisibility = Object.assign({
            persistOnChange: true,
            showPanelButton: true,
            enableExport: false,
            enableReset: true
        }, columnVisibilityOptions);

        // Create helper instance
        var helper = new AgGridHelper({
            containerId: gridId,
            templateId: templateId,
            columnDefs: columnDefs,
            rowData: rowData || [],
            options: mergedGridOptions,
            columnVisibilityOptions: mergedColumnVisibility,
            heightOptions: heightOptions
        });

        // Persist auto-detection settings on the helper instance (used for re-evaluation on filterChanged)
        helper._autoDetectFiltersEnabled = options.autoDetectFilters !== false;
        helper._autoDetectFilterOptions = options.autoDetectFilterOptions || {};

        // Initialize the grid
        var api = helper.initialize();

        // Handle auto-show of grid container
        if (autoShow && api) {
            var loadingEl = document.getElementById(loadingId);
            var containerEl = document.getElementById(containerId);

            setTimeout(function() {
                if (loadingEl) {
                    // Try jQuery fadeOut if available, otherwise just hide
                    if (typeof jQuery !== 'undefined' && jQuery.fn && jQuery.fn.fadeOut) {
                        jQuery(loadingEl).fadeOut(300);
                    } else {
                        loadingEl.style.display = 'none';
                    }
                }
                if (containerEl) {
                    containerEl.style.display = 'block';
                }

                // Refresh grid to ensure proper sizing
                if (helper.isGridVisible()) {
                    helper.refresh();
                }

                // Call onReady callback if provided
                if (typeof options.onReady === 'function') {
                    options.onReady(api, helper);
                }
            }, 100);
        }

        return {
            helper: helper,
            api: api
        };
    };

    /**
     * Static async factory method for grids that may not be immediately visible
     * Waits for the container to appear in the DOM before initializing
     *
     * @param {string} gridId - The DOM ID of the grid container
     * @param {string} templateId - Unique template identifier for persistence
     * @param {Array} columnDefs - Column definitions array
     * @param {Array} rowData - Initial row data
     * @param {Object} options - Additional options (same as create())
     * @param {number} options.maxWait - Maximum time to wait for container (default: 3000ms)
     * @returns {Promise<Object>} Promise resolving to { helper: AgGridHelper, api: gridApi }
     */
    AgGridHelper.createAsync = function(gridId, templateId, columnDefs, rowData, options) {
        options = options || {};
        var maxWait = options.maxWait || 3000;

        return new Promise(function(resolve, reject) {
            var startTime = Date.now();
            var checkInterval = 100;

            function checkContainer() {
                var container = document.getElementById(gridId);
                if (container) {
                    try {
                        var result = AgGridHelper.create(gridId, templateId, columnDefs, rowData, options);
                        resolve(result);
                    } catch (error) {
                        reject(error);
                    }
                    return;
                }

                var elapsed = Date.now() - startTime;
                if (elapsed < maxWait) {
                    setTimeout(checkContainer, checkInterval);
                } else {
                    reject(new Error('AgGridHelper: Grid container #' + gridId + ' not found after ' + maxWait + 'ms'));
                }
            }

            checkContainer();
        });
    };

    /**
     * Utility function to pin actions column to right
     * Call after grid is initialized to ensure actions column stays pinned
     *
     * @param {Object} gridApi - AG Grid API instance
     * @param {Array} columnOrder - Optional array of column IDs in desired order
     */
    AgGridHelper.pinActionsColumn = function(gridApi, columnOrder) {
        if (!gridApi || typeof gridApi.applyColumnState !== 'function') {
            return;
        }

        try {
            var state;
            if (columnOrder && Array.isArray(columnOrder)) {
                state = columnOrder.map(function(colId) {
                    return {
                        colId: colId,
                        pinned: colId === 'actions' ? 'right' : null
                    };
                });
            } else {
                state = [{ colId: 'actions', pinned: 'right' }];
            }

            gridApi.applyColumnState({
                state: state,
                defaultState: { pinned: null },
                applyOrder: columnOrder ? true : false
            });
        } catch (e) {
            console.warn('AgGridHelper: Could not pin actions column:', e);
        }
    };

    // Export to global scope
    window.AgGridHelper = AgGridHelper;

})();
