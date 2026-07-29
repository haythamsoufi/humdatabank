/**
 * AG Grid Helper — core constructor, initialization, and factory methods.
 * @module ag-grid-helper-core
 * Other ag-grid-helper-*.js modules extend AgGridHelper.prototype / statics.
 */
(function(global) {
    'use strict';

        /** Standard line spacing for AG Grid body cells (matches ag-grid-common-styles.css). */
        var AG_GRID_CELL_LINE_HEIGHT = '1.4';
    
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
         * @param {boolean} [config.filterPersistence=true] - Persist filters in localStorage per templateId
         * @param {boolean} [config.autoDetectFilters=true] - Run autoDetectColumnFilters during initialization
         * @param {Object} [config.autoDetectFilterOptions] - Options for autoDetectColumnFilters (maxUniqueValues, sampleSize, …)
         */
        function AgGridHelper(config) {
            config = AgGridHelper._normalizeHelperConfig(config);
            if (!config || !config.containerId || !config.templateId || !config.columnDefs) {
                throw new Error('AgGridHelper: containerId, templateId, and columnDefs are required');
            }
    
            this._autoDetectFiltersEnabled = config.autoDetectFilters !== false;
            this._autoDetectFilterOptions = config.autoDetectFilterOptions || {};
    
            this.config = {
                containerId: config.containerId,
                templateId: config.templateId,
                columnDefs: config.columnDefs,
                rowData: config.rowData || [],
                options: config.options || {},
                columnVisibilityOptions: config.columnVisibilityOptions || {},
                filterPersistence: config.filterPersistence !== false,
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
                checkboxColumnWidth: typeof config.checkboxColumnWidth === 'number' ? config.checkboxColumnWidth : 56,
                showResultCount: config.showResultCount !== false,
                emptyMessage: config.emptyMessage || null,
            };
    
            this.gridApi = null;
            this.columnApi = null;
            this.columnVisibilityManager = null;
            this.gridDiv = null;
            this.checkboxWidthTimeout = null;
            this.columnFitTimeout = null;
            this.resultCountElement = null;
            /** When set, overrides rowData.length for the result-count label (server-paginated grids). */
            this._resultCountTotal = (config.resultCountTotal != null && !isNaN(config.resultCountTotal))
                ? Number(config.resultCountTotal)
                : null;
            this._suppressFilterPersistence = false;
            // Track whether we've already called sizeColumnsToFit().
            // Repeated calls (e.g., after height recalculation) can effectively "fight" user-driven column resizing
            // by continuously re-fitting widths to the container.
            this._hasSizedColumnsToFit = false;
        }

        AgGridHelper.fallbackCopyToClipboard = fallbackCopyToClipboard;
        AgGridHelper.getAgGridLocaleText = getAgGridLocaleText;

        /**
         * Normalize constructor config — accept create()-style aliases.
         * @param {Object} config
         * @returns {Object}
         */
        AgGridHelper._normalizeHelperConfig = function(config) {
            if (!config) {
                return config;
            }
            return Object.assign({}, config, {
                columnVisibilityOptions: config.columnVisibilityOptions || config.columnVisibility || {},
                heightOptions: config.heightOptions || config.height || {},
                options: config.options || config.gridOptions || {}
            });
        };

        /**
         * Normalize AgGridHelper.create() options — accept constructor-style aliases.
         * @param {Object} opts
         * @returns {Object}
         */
        AgGridHelper._normalizeCreateOptions = function(opts) {
            opts = opts || {};
            return Object.assign({}, opts, {
                gridOptions: opts.gridOptions || opts.options || {},
                columnVisibility: opts.columnVisibility || opts.columnVisibilityOptions || {},
                height: opts.height || opts.heightOptions || {}
            });
        };
    
        /** Options consumed by AgGridHelper only — not passed to AG Grid. */
        var HELPER_ONLY_GRID_OPTIONS = [
            'sizeColumnsToFitOnInit',
            'sizeColumnsToFitOnRefresh',
            'sizeColumnsToFitOnColumnChange'
        ];
    
        /**
         * Grid options that allow selecting/copying cell text (AG Grid defaults block this).
         * Merged into AgGridHelper defaults; use when calling agGrid.createGrid() directly.
         * @returns {Object}
         */
        AgGridHelper.getTextSelectionGridOptions = function() {
            return {
                enableCellTextSelection: true,
                ensureDomOrder: true,
                suppressCellFocus: false,
                overlayNoRowsTemplate: AgGridHelper.buildNoRowsOverlayTemplate()
            };
        };

        /**
         * Default empty-state copy (optionally overridden per grid).
         * @returns {{default: string, filtered: string}}
         */
        AgGridHelper.getEmptyStateMessages = function() {
            var t = window.agGridTranslations || {};
            return {
                default: t.noRecordsFound || 'No records found',
                filtered: t.noMatchingRecords || 'No records match your current filters'
            };
        };

        /**
         * Escape text for AG Grid overlay HTML templates.
         * @param {string} text
         * @returns {string}
         */
        AgGridHelper.escapeOverlayHtml = function(text) {
            if (text == null) {
                return '';
            }
            return String(text)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        };

        /**
         * Professional empty-state overlay markup for AG Grid.
         * @param {string} [message]
         * @returns {string}
         */
        AgGridHelper.buildNoRowsOverlayTemplate = function(message) {
            var copy = message || AgGridHelper.getEmptyStateMessages().default;
            var safe = AgGridHelper.escapeOverlayHtml(copy);
            return '' +
                '<div class="ag-grid-empty-state" role="status">' +
                    '<div class="ag-grid-empty-state__icon" aria-hidden="true">' +
                        '<i class="fas fa-inbox"></i>' +
                    '</div>' +
                    '<p class="ag-grid-empty-state__message">' + safe + '</p>' +
                '</div>';
        };

        /**
         * Resolve a grid-specific empty message from config, DOM, or defaults.
         * @param {string} gridId
         * @param {string} [configMessage]
         * @returns {string}
         */
        AgGridHelper.resolveEmptyMessage = function(gridId, configMessage) {
            if (configMessage) {
                return configMessage;
            }
            var gridEl = document.getElementById(gridId);
            if (gridEl) {
                var dataMessage = gridEl.getAttribute('data-empty-message');
                if (dataMessage) {
                    return dataMessage;
                }
            }
            var emptyEl = document.getElementById(gridId + '-empty');
            if (emptyEl) {
                var messageEl = emptyEl.querySelector('.ag-grid-empty-state__message, p');
                if (messageEl && messageEl.textContent.trim()) {
                    return messageEl.textContent.trim();
                }
            }
            return AgGridHelper.getEmptyStateMessages().default;
        };

        /**
         * @param {Object} gridApi
         * @returns {boolean}
         */
        AgGridHelper.hasActiveGridFilters = function(gridApi) {
            if (!gridApi || typeof gridApi.getFilterModel !== 'function') {
                return false;
            }
            var filterModel = gridApi.getFilterModel() || {};
            return Object.keys(filterModel).length > 0;
        };
    
        /**
         * Get default grid options
         * @returns {Object} Default grid options
         */
        AgGridHelper.prototype.getDefaultGridOptions = function() {
            const localeText = getAgGridLocaleText();
            // Detect RTL mode from the global page direction and/or language markers.
            // Note: the app sets html[dir="rtl"] at runtime for Arabic in `static/js/core/layout.js`.
            const docDir = document.documentElement.getAttribute('dir');
            const dataLang = (document.documentElement.getAttribute('data-language') || document.body.getAttribute('data-language') || '').toLowerCase();
            const isRtl = docDir === 'rtl' || dataLang === 'ar';
            const textSelection = AgGridHelper.getTextSelectionGridOptions();
            const emptyStateMessages = AgGridHelper.getEmptyStateMessages();
            this._emptyMessageDefault = AgGridHelper.resolveEmptyMessage(
                this.config.containerId,
                this.config.emptyMessage
            );
            this._emptyMessageFiltered = emptyStateMessages.filtered;
            const options = {
                columnDefs: this.config.columnDefs,
                rowData: this.config.rowData,
                enableCellTextSelection: textSelection.enableCellTextSelection,
                ensureDomOrder: textSelection.ensureDomOrder,
                suppressCellFocus: textSelection.suppressCellFocus,
                context: {
                    agGridHelperRowData: this.config.rowData || []
                },
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
                        'justify-content': 'flex-start',
                        'line-height': AG_GRID_CELL_LINE_HEIGHT,
                        'userSelect': 'text',
                        '-webkit-user-select': 'text'
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
                overlayNoRowsTemplate: AgGridHelper.buildNoRowsOverlayTemplate(this._emptyMessageDefault),
                // Ensure the auto-generated selection column checkbox is vertically centered.
                // The defaultColDef.cellStyle does NOT apply to the selection column, so we
                // must configure it separately via selectionColumnDef (ag-grid v32+).
                selectionColumnDef: {
                    pinned: AgGridHelper.shouldDisableColumnPinning() ? null : 'left',
                    lockPinned: !AgGridHelper.shouldDisableColumnPinning(),
                    suppressMovable: true,
                    width: this.config.checkboxColumnWidth,
                    minWidth: this.config.checkboxColumnWidth,
                    maxWidth: this.config.checkboxColumnWidth,
                    resizable: false,
                    headerClass: 'ag-selection-column-cell',
                    cellClass: 'ag-selection-column-cell',
                    cellStyle: {
                        'display': 'flex',
                        'align-items': 'center',
                        'justify-content': 'center',
                        'userSelect': 'none',
                        '-webkit-user-select': 'none'
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
         * Merge default options with custom options
         * @returns {Object} Merged grid options
         */
        AgGridHelper.prototype.buildGridOptions = function() {
            const defaults = this.getDefaultGridOptions();
            const custom = this.config.options || {};
    
            // Deep merge for nested objects
            const merged = Object.assign({}, defaults, custom);
    
            HELPER_ONLY_GRID_OPTIONS.forEach(function(key) {
                delete merged[key];
            });
    
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
    
            // Merge context so custom filters can always access the full helper rowData,
            // even if a page supplies its own AG Grid context object.
            merged.context = Object.assign({}, defaults.context || {}, custom.context || {});
    
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
    
            if (AgGridHelper.shouldDisableColumnPinning()) {
                if (merged.columnDefs) {
                    merged.columnDefs = AgGridHelper.stripColumnPinsFromColDefs(merged.columnDefs);
                }
                if (merged.selectionColumnDef) {
                    merged.selectionColumnDef = Object.assign({}, merged.selectionColumnDef, {
                        pinned: null,
                        lockPinned: false
                    });
                }
            }
    
            if (AgGridHelper.shouldUseTouchPageScroll(this.config.heightOptions || {})) {
                merged.domLayout = 'autoHeight';
            }
    
            if (merged.pagination === false) {
                merged.suppressPaginationPanel = true;
            }
    
            // When the grid body reaches its scroll limit, continue scrolling the page (or nearest scroll parent).
            var userOnGridReady = merged.onGridReady;
            merged.onGridReady = function(params) {
                var gridEl = null;
                if (params && params.api && typeof params.api.getGridElement === 'function') {
                    gridEl = params.api.getGridElement();
                }
                AgGridHelper.enablePageScrollChaining(gridEl || (params && params.api) || params);
                if (typeof userOnGridReady === 'function') {
                    userOnGridReady(params);
                }
            };
    
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
    
            // Match AgGridHelper.create(): pick customSetFilter vs text/number from rowData before grid builds.
            if (this._autoDetectFiltersEnabled !== false && typeof AgGridHelper.autoDetectColumnFilters === 'function') {
                AgGridHelper.autoDetectColumnFilters(
                    this.config.columnDefs,
                    this.config.rowData || [],
                    this._autoDetectFilterOptions || {}
                );
            }
    
            AgGridHelper.normalizeCustomColDefProps(this.config.columnDefs);
            AgGridHelper.wrapActionsColumnRenderers(this.config.columnDefs);
    
            // Detect grid API
            const GridConstructor = this.detectGridApi();
            if (!GridConstructor) {
                return null;
            }
    
            // Build grid options
            const gridOptions = this.buildGridOptions();
            this._gridOptions = gridOptions;
    
            try {
                const self = this;
    
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
    
                if (gridOptions.pagination === false && this.gridDiv && this.gridDiv.classList) {
                    this.gridDiv.classList.add('ag-grid-external-pagination');
                }
    
                // Initialize Column Visibility Manager
                this.initializeColumnVisibilityManager();
    
                // Restore saved column filters before toolbar state is calculated.
                this.restoreSavedFilterModel();
    
                // Persist column filters for this template/grid after user changes.
                this.setupFilterPersistenceListener();
    
                // Initialize Clear All Filters Button
                this.initializeClearFiltersButton();
    
                // Show live result count above the grid.
                if (this.config.showResultCount !== false) {
                    this.initializeResultCount();
                }
    
                // Ensure cell alignment is applied after grid initialization
                this.ensureCellAlignment();
    
                // Listen for pagination changes to recalculate height
                this.setupPaginationListener();
    
                // Keep height responsive to viewport changes (e.g., large screens, browser resize)
                this.setupWindowResizeListener();
    
                // Setup checkbox column width handling
                this.setupCheckboxColumnWidthHandling();
    
                // Re-fit columns when the visible column set changes after initialization.
                this.setupColumnFitOnStructureChange();
    
                // Ensure filter menu input spacing is applied reliably
                this.setupFilterMenuInputSpacing();
    
                // Header labels can overlap filter buttons after sizeColumnsToFit; bridge missed clicks.
                this.setupHeaderFilterClickBridge();

                // Passthrough header clicks (when labels don't receive pointer events) need explicit sort.
                this.setupHeaderSortClickBridge();

                this.setupEmptyStateOverlay();

                // Emit selection-changed events so templates can show bulk-action UI
                this.setupSelectionChangedDispatcher();
    
                // Custom right-click context menu (Copy cell, Export table to Excel) – works in Community edition
                this.setupContextMenuFallback();
    
                // Mobile: unpin columns so wide cells are not trapped in narrow pinned panes.
                self._mobileColumnPinningDisabled = AgGridHelper.shouldDisableColumnPinning();
                self._mobileActionsLayout = AgGridHelper.isCoarsePointerDevice();
                AgGridHelper.syncColumnPinningForViewport(self.gridApi, self.columnVisibilityManager);
                AgGridHelper.applyActionsColumnMobileWidths(self.config.columnDefs, self.gridApi);
    
                // Set dynamic height after a short delay to ensure:
                // 1. Grid is fully rendered and positioned in the DOM
                // 2. Any content above the grid has loaded
                // 3. The viewport calculation is accurate
                setTimeout(function() {
                    // Clear any early cached value to ensure fresh calculation
                    self._cachedViewportMinHeight = null;
                    self.setDynamicHeight();
                }, 150);
    
                // Expose to window for debugging
                window.gridApi = this.gridApi;
                window.columnVisibilityManager = this.columnVisibilityManager;
                window.gridHelper = this; // Expose helper instance

                // Auto-reveal when page uses ag_grid_body_wrap / ag_grid_container markup.
                // AgGridHelper.create() sets autoRevealAfterInit: false and reveals itself.
                if (this.config.autoRevealAfterInit !== false &&
                    document.getElementById(this.config.containerId + '-loading')) {
                    var revealSelf = this;
                    setTimeout(function() {
                        revealSelf.revealGridAfterInit();
                    }, 50);
                }

                return this.gridApi;
            } catch (error) {
                console.error('AgGridHelper: Error initializing grid:', error);
                return null;
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
    
                    var mobilePinningDisabled = AgGridHelper.shouldDisableColumnPinning();
                    if (mobilePinningDisabled !== self._mobileColumnPinningDisabled) {
                        self._mobileColumnPinningDisabled = mobilePinningDisabled;
                        AgGridHelper.syncColumnPinningForViewport(self.gridApi, self.columnVisibilityManager);
                    }
    
                    var mobileActionsLayout = AgGridHelper.isCoarsePointerDevice();
                    if (mobileActionsLayout !== self._mobileActionsLayout) {
                        self._mobileActionsLayout = mobileActionsLayout;
                        AgGridHelper.applyActionsColumnMobileWidths(self.config.columnDefs, self.gridApi);
                        if (self.gridApi && typeof self.gridApi.refreshCells === 'function') {
                            self.gridApi.refreshCells({ force: true });
                        }
                    }
                }, 120);
            });
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
            if (this._gridOptions && this._gridOptions.context) {
                this._gridOptions.context.agGridHelperRowData = this.config.rowData;
            }
    
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
                self.updateResultCount();
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
                            AgGridHelper.enforceColumnMinWidths(apiToUse);
                            AgGridHelper.syncActionsColumnLayout(self.config.columnDefs, apiToUse);
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
         * Size visible columns to the available grid width.
         * Used for structural column changes (show/hide/add/remove), not for regular
         * row/model refreshes, so normal manual resizing is not constantly overwritten.
         * @param {string} reason - Optional debug reason for the fit request
         */
        AgGridHelper.prototype.fitColumnsToAvailableWidth = function(reason) {
            if (!this.gridApi) {
                return;
            }
            if (this.config && this.config.options && this.config.options.sizeColumnsToFitOnColumnChange === false) {
                return;
            }
            if (this.isFilterMenuOpen && this.isFilterMenuOpen()) {
                return;
            }
            if (this.isGridVisible && typeof this.isGridVisible === 'function' && !this.isGridVisible()) {
                return;
            }

            this._columnFitInProgress = true;
    
            const apiToUse = (this.gridApi && this.gridApi.api && typeof this.gridApi.api.sizeColumnsToFit === 'function')
                ? this.gridApi.api
                : this.gridApi;
    
            if (!apiToUse || typeof apiToUse.sizeColumnsToFit !== 'function') {
                this._columnFitInProgress = false;
                return;
            }
    
            try {
                if (typeof apiToUse.doLayout === 'function') {
                    apiToUse.doLayout();
                }
            } catch (e) {
                // Non-fatal
            }
    
            try {
                apiToUse.sizeColumnsToFit();
                this._hasSizedColumnsToFit = true;
                this._lastColumnFitAt = Date.now();
                AgGridHelper.enforceColumnMinWidths(apiToUse);
                AgGridHelper.syncActionsColumnLayout(this.config.columnDefs, apiToUse);
            } catch (e) {
                // Non-fatal
            } finally {
                var self = this;
                setTimeout(function() {
                    self._columnFitInProgress = false;
                }, 200);
            }
    
            this.scheduleCheckboxWidthEnforcement();
        };
    
        /**
         * Debounce column fitting after visible-column structure changes.
         * @param {string} reason - Event/reason that requested fitting
         * @param {number} delayMs - Optional debounce delay
         */
        AgGridHelper.prototype.scheduleColumnsToFit = function(reason, delayMs) {
            if (!this.gridApi) {
                return;
            }
            if (this.config && this.config.options && this.config.options.sizeColumnsToFitOnColumnChange === false) {
                return;
            }

            // displayedColumnsChanged also fires when sizeColumnsToFit adjusts widths — ignore it.
            if (reason === 'displayedColumnsChanged') {
                return;
            }

            if (this._columnFitInProgress) {
                return;
            }

            var structuralReasons = {
                columnVisible: true,
                columnPinned: true,
                gridColumnsChanged: true,
                newColumnsLoaded: true
            };
            if (!structuralReasons[reason] &&
                this._lastColumnFitAt &&
                Date.now() - this._lastColumnFitAt < 400) {
                return;
            }
    
            if (this.columnFitTimeout) {
                clearTimeout(this.columnFitTimeout);
            }
    
            const self = this;
            this.columnFitTimeout = setTimeout(function() {
                self.fitColumnsToAvailableWidth(reason || 'column-structure-change');
            }, typeof delayMs === 'number' ? delayMs : 120);
        };
    
        /**
         * Listen for AG Grid column structure changes and re-fit visible columns.
         */
        AgGridHelper.prototype.setupColumnFitOnStructureChange = function() {
            if (this._columnFitOnStructureChangeAttached || !this.gridApi || typeof this.gridApi.addEventListener !== 'function') {
                return;
            }
            if (this.config && this.config.options && this.config.options.sizeColumnsToFitOnColumnChange === false) {
                return;
            }
    
            const self = this;
            const schedule = function(event) {
                const type = event && event.type ? event.type : 'column-structure-change';
                self.scheduleColumnsToFit(type);
            };
    
            [
                'columnVisible',
                'columnPinned',
                'gridColumnsChanged',
                'newColumnsLoaded'
            ].forEach(function(eventName) {
                try {
                    self.gridApi.addEventListener(eventName, schedule);
                } catch (e) {
                    // Some AG Grid versions may not expose every event.
                }
            });
    
            this._columnFitOnStructureChangeAttached = true;
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
         * Hide the standard ag_grid_container loading overlay so it cannot block taps/clicks.
         * @param {string|HTMLElement} loadingIdOrEl
         */
        AgGridHelper.hideGridLoadingOverlay = function(loadingIdOrEl) {
            var loadingEl = typeof loadingIdOrEl === 'string'
                ? document.getElementById(loadingIdOrEl)
                : loadingIdOrEl;
            if (!loadingEl) {
                return;
            }
            loadingEl.style.display = 'none';
            loadingEl.style.pointerEvents = 'none';
            loadingEl.setAttribute('aria-hidden', 'true');
            loadingEl.setAttribute('aria-busy', 'false');
            loadingEl.classList.add('is-hidden');
        };

        /**
         * Show the standard loading overlay (skeleton or spinner) before grid init.
         * @param {string|HTMLElement} loadingIdOrEl
         */
        AgGridHelper.showGridLoadingOverlay = function(loadingIdOrEl) {
            var loadingEl = typeof loadingIdOrEl === 'string'
                ? document.getElementById(loadingIdOrEl)
                : loadingIdOrEl;
            if (!loadingEl) {
                return;
            }
            loadingEl.style.display = 'flex';
            loadingEl.style.pointerEvents = 'auto';
            loadingEl.removeAttribute('aria-hidden');
            loadingEl.setAttribute('aria-busy', 'true');
            loadingEl.classList.remove('is-hidden');
        };

        /**
         * Reveal grid container and hide loading overlay (shared by create() and initialize()).
         * @param {string} gridId
         * @param {Object} [options]
         * @param {AgGridHelper} [options.helper]
         * @param {Function} [options.onReady]
         */
        AgGridHelper.revealGridContainer = function(gridId, options) {
            options = options || {};
            var helper = options.helper;
            var loadingEl = document.getElementById(gridId + '-loading');
            var containerEl = document.getElementById(gridId + '-container');
            AgGridHelper.hideGridLoadingOverlay(loadingEl);
            if (containerEl) {
                containerEl.style.display = 'block';
            }
            if (helper) {
                if (helper.isGridVisible && helper.isGridVisible()) {
                    helper.refresh();
                }
                if (helper.columnVisibilityManager &&
                    typeof helper.columnVisibilityManager.finishInitialColumnState === 'function') {
                    helper.columnVisibilityManager.finishInitialColumnState();
                }
                if (helper.gridApi) {
                    AgGridHelper.syncColumnPinningForViewport(helper.gridApi, helper.columnVisibilityManager);
                    AgGridHelper.enforceColumnMinWidths(helper.gridApi);
                }
            }
            if (typeof options.onReady === 'function' && helper && helper.gridApi) {
                options.onReady(helper.gridApi, helper);
            }
        };

        /**
         * Hide loading overlay and show grid container after initialization.
         * @param {Function} [onReady]
         */
        AgGridHelper.prototype.revealGridAfterInit = function(onReady) {
            AgGridHelper.revealGridContainer(this.config.containerId, {
                helper: this,
                onReady: onReady
            });
        };

        /**
         * Keep the no-rows overlay copy in sync with active filters.
         */
        AgGridHelper.prototype.setupEmptyStateOverlay = function() {
            if (!this.gridApi) {
                return;
            }

            var self = this;
            var refreshOverlayMessage = function() {
                if (!self.gridApi) {
                    return;
                }
                var message = AgGridHelper.hasActiveGridFilters(self.gridApi)
                    ? self._emptyMessageFiltered
                    : self._emptyMessageDefault;
                var template = AgGridHelper.buildNoRowsOverlayTemplate(message);

                if (typeof self.gridApi.setGridOption === 'function') {
                    self.gridApi.setGridOption('overlayNoRowsTemplate', template);
                } else if (self._gridOptions) {
                    self._gridOptions.overlayNoRowsTemplate = template;
                }

                if (self.gridApi.getDisplayedRowCount() === 0 &&
                    typeof self.gridApi.showNoRowsOverlay === 'function') {
                    self.gridApi.showNoRowsOverlay();
                }
            };

            this.gridApi.addEventListener('filterChanged', refreshOverlayMessage);
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
         * @param {boolean} options.persistFilters - Persist filters in browser localStorage (default: true)
         * @param {boolean} options.autoShow - Auto show grid after init (default: true)
         * @param {string} options.loadingId - Custom loading element ID (default: gridId + '-loading')
         * @param {string} options.containerId - Custom container element ID (default: gridId + '-container')
         * @param {Function} options.onReady - Callback when grid is ready
         * @param {boolean} options.autoDetectFilters - Automatically detect filter types (default: true)
         * @param {Object} options.autoDetectFilterOptions - Options for auto-detection ({maxUniqueValues, sampleSize})
         * @returns {Object} { helper: AgGridHelper, api: gridApi }
         */
        AgGridHelper.create = function(gridId, templateId, columnDefs, rowData, options) {
            options = AgGridHelper._normalizeCreateOptions(options);
    
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
    
            HELPER_ONLY_GRID_OPTIONS.forEach(function(key) {
                if (options[key] !== undefined) {
                    mergedGridOptions[key] = options[key];
                }
            });
    
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
                heightOptions: heightOptions,
                showResultCount: options.showResultCount !== false,
                filterPersistence: options.filterPersistence !== false && options.persistFilters !== false,
                autoDetectFilters: options.autoDetectFilters,
                autoDetectFilterOptions: options.autoDetectFilterOptions,
                autoRevealAfterInit: false,
                emptyMessage: options.emptyMessage || null
            });
    
            // Initialize the grid
            var api = helper.initialize();
    
            // Handle auto-show of grid container
            var loadingEl = document.getElementById(loadingId);
            var containerEl = document.getElementById(containerId);
            var revealGrid = function() {
                AgGridHelper.revealGridContainer(gridId, {
                    helper: helper,
                    onReady: options.onReady
                });
            };
    
            if (autoShow) {
                if (api) {
                    setTimeout(revealGrid, 100);
                } else {
                    revealGrid();
                }
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
         * Create a grid with optional tab-activation handling for hidden tab panels.
         * Defers initialization until the grid container is visible when deferUntilVisible is true.
         *
         * @param {string} gridId
         * @param {string} templateId
         * @param {Array} columnDefs
         * @param {Array} rowData
         * @param {Object} options - Same as create()
         * @param {Object} [tabConfig]
         * @param {string} [tabConfig.eventName='tab-activated'] - CustomEvent name to listen for
         * @param {string} [tabConfig.tabId] - When set, only react when event.detail.tab matches
         * @param {boolean} [tabConfig.deferUntilVisible=false] - Wait until grid has width before create()
         * @param {number} [tabConfig.minWidth=200] - Minimum clientWidth to treat grid as visible
         * @param {Function} [tabConfig.onTabActivated] - Called with (api, helper) when tab becomes active
         * @returns {{ helper: AgGridHelper|null, api: Object|null, init: Function }}
         */
        AgGridHelper.createTabAware = function(gridId, templateId, columnDefs, rowData, options, tabConfig) {
            tabConfig = tabConfig || {};
            options = AgGridHelper._normalizeCreateOptions(options);

            var result = { helper: null, api: null };
            var initialized = false;
            var minWidth = (typeof tabConfig.minWidth === 'number') ? tabConfig.minWidth : 200;

            function isGridVisibleEnough() {
                var el = document.getElementById(gridId);
                if (!el) {
                    return false;
                }
                var width = el.clientWidth || el.getBoundingClientRect().width;
                return width >= minWidth;
            }

            function runTabActivatedCallback() {
                if (typeof tabConfig.onTabActivated === 'function' && result.api) {
                    tabConfig.onTabActivated(result.api, result.helper);
                }
            }

            function initGrid() {
                if (initialized) {
                    return result;
                }
                if (tabConfig.deferUntilVisible && !isGridVisibleEnough()) {
                    return result;
                }
                initialized = true;
                var created = AgGridHelper.create(gridId, templateId, columnDefs, rowData, options);
                result.helper = created.helper;
                result.api = created.api;
                return result;
            }

            function onTabEvent(ev) {
                if (tabConfig.tabId && ev && ev.detail && ev.detail.tab !== tabConfig.tabId) {
                    return;
                }
                if (!initialized) {
                    initGrid();
                }
                runTabActivatedCallback();
            }

            if (tabConfig.eventName) {
                document.addEventListener(tabConfig.eventName, onTabEvent);
            }

            function bootstrap() {
                if (tabConfig.deferUntilVisible) {
                    if (isGridVisibleEnough()) {
                        initGrid();
                    }
                } else {
                    initGrid();
                }
                if (!tabConfig.eventName && typeof tabConfig.onTabActivated === 'function') {
                    runTabActivatedCallback();
                }
            }

            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', bootstrap);
            } else {
                bootstrap();
            }

            return {
                get helper() { return result.helper; },
                get api() { return result.api; },
                init: initGrid
            };
        };
    
        AgGridHelper.CELL_LINE_HEIGHT = AG_GRID_CELL_LINE_HEIGHT;
    

    global.AgGridHelper = AgGridHelper;

})(typeof window !== 'undefined' ? window : this);
