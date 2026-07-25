/**
 * AG Grid Helper — Dynamic height, mobile viewport, scroll chaining
 * @module ag-grid-helper-viewport
 * Loaded via ag_grid_includes.html (after ag-grid-helper-core.js).
 */
(function(global) {
    'use strict';

    var AgGridHelper = global.AgGridHelper;
    if (!AgGridHelper) {
        throw new Error('ag-grid-helper-viewport.js: AgGridHelper must be loaded first (ag-grid-helper-core.js)');
    }

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
                    const opts = self.config.heightOptions || {};
    
                    // Embed mode: size grid to the immediate parent (e.g. flex slot in a modal) so the grid
                    // does not overflow and cover footer actions below.
                    if (opts.useParentContainerHeight) {
                        const parent = self.gridDiv && self.gridDiv.parentElement;
                        if (parent) {
                            let h = parent.clientHeight;
                            if (h < 8) {
                                self._useParentHeightRetry = (self._useParentHeightRetry || 0) + 1;
                                if (self._useParentHeightRetry <= 50) {
                                    setTimeout(function() {
                                        self.setDynamicHeight();
                                    }, 50);
                                }
                                return;
                            }
                            self._useParentHeightRetry = 0;
                            const floor = typeof opts.absoluteMinHeight === 'number' ? opts.absoluteMinHeight : 150;
                            h = Math.max(floor, h);
                            self.applyGridHeight(h, h, h);
                            return;
                        }
                    }
    
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
    
                    // Handle empty state
                    if (totalRowCount === 0) {
                        if (AgGridHelper.shouldUseTouchPageScroll(opts)) {
                            if (self._touchPageScrollLayout) {
                                self.restoreDesktopGridLayout();
                            }
                            const emptyContentHeight = headerHeight + emptyStateHeight +
                                (paginationEnabled ? paginationHeight : 0);
                            self.applyGridHeight(emptyContentHeight, emptyContentHeight, emptyContentHeight);
                            return;
                        }
                        const resolvedMinHeight = self.resolveMinHeightPx(opts, paginationEnabled);
                        const emptyContentHeight = headerHeight + emptyStateHeight + (paginationEnabled ? paginationHeight : 0);
                        const emptyHeight = Math.max(emptyContentHeight, resolvedMinHeight);
                        self.applyGridHeight(emptyHeight, resolvedMinHeight, emptyHeight);
                        return;
                    }
    
                    // Phone: size grid to row content; page scroll handles overflow (no empty body gap).
                    if (AgGridHelper.shouldUseTouchPageScroll(opts)) {
                        self.applyTouchPageScrollLayout();
                        return;
                    }
    
                    if (self._touchPageScrollLayout) {
                        self.restoreDesktopGridLayout();
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
         * Mobile layout: shrink grid to row content so the page scrolls (no empty body viewport).
         */
        AgGridHelper.prototype.applyTouchPageScrollLayout = function() {
            if (!this.gridDiv) {
                return;
            }
    
            var api = this.gridApi;
            if (api && typeof api.setGridOption === 'function') {
                api.setGridOption('domLayout', 'autoHeight');
            } else if (this.gridInstance && typeof this.gridInstance.setGridOption === 'function') {
                this.gridInstance.setGridOption('domLayout', 'autoHeight');
            }
    
            this.gridDiv.style.height = 'auto';
            this.gridDiv.style.minHeight = '0';
            this.gridDiv.style.maxHeight = 'none';
            this._touchPageScrollLayout = true;
        };
    
        /**
         * Restore normal fixed-height grid layout on desktop after mobile autoHeight mode.
         */
        AgGridHelper.prototype.restoreDesktopGridLayout = function() {
            if (!this.gridDiv) {
                return;
            }
    
            var api = this.gridApi;
            if (api && typeof api.setGridOption === 'function') {
                api.setGridOption('domLayout', 'normal');
            } else if (this.gridInstance && typeof this.gridInstance.setGridOption === 'function') {
                this.gridInstance.setGridOption('domLayout', 'normal');
            }
    
            this.gridDiv.style.height = '';
            this.gridDiv.style.minHeight = '';
            this.gridDiv.style.maxHeight = '';
            this._touchPageScrollLayout = false;
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
         * Resolve the AG Grid root DOM element from an element or API reference.
         * @param {HTMLElement|Object} gridRootOrApi
         * @returns {HTMLElement|null}
         * @private
         */
        AgGridHelper._resolveGridElement = function(gridRootOrApi) {
            if (!gridRootOrApi) {
                return null;
            }
            if (gridRootOrApi.nodeType === 1) {
                return gridRootOrApi;
            }
            if (typeof gridRootOrApi.getGridElement === 'function') {
                return gridRootOrApi.getGridElement();
            }
            if (gridRootOrApi.eGridDiv) {
                return gridRootOrApi.eGridDiv;
            }
            return null;
        };
    
        /**
         * Find the nearest scrollable ancestor above an element (e.g. main.admin-scroll-main).
         * @param {HTMLElement} element
         * @returns {HTMLElement}
         * @private
         */
        AgGridHelper._findScrollableAncestor = function(element) {
            var el = element && element.parentElement;
            while (el) {
                if (el === document.body || el === document.documentElement) {
                    break;
                }
                try {
                    var style = window.getComputedStyle(el);
                    var overflowY = style.overflowY;
                    if ((overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay') &&
                        el.scrollHeight > el.clientHeight + 1) {
                        return el;
                    }
                } catch (e) {
                    // Ignore getComputedStyle failures and keep walking up.
                }
                el = el.parentElement;
            }
            return document.scrollingElement || document.documentElement;
        };
    
        /** Pixels from top/bottom of grid body before wheel scroll chains to the page. */
        AgGridHelper.SCROLL_CHAIN_EDGE_TOLERANCE = 8;
    
        /**
         * True on phones/tablets where nested scroll areas feel awkward.
         * @returns {boolean}
         */
        AgGridHelper.isCoarsePointerDevice = function() {
            if (typeof AgGridUtils !== 'undefined' && typeof AgGridUtils.isCoarsePointerDevice === 'function') {
                return AgGridUtils.isCoarsePointerDevice();
            }
            return (window.innerWidth || 0) <= 768;
        };
    
        /**
         * On touch devices, prefer page scroll over a viewport-capped grid body scroller.
         * @param {Object} heightOptions
         * @returns {boolean}
         */
        AgGridHelper.shouldUseTouchPageScroll = function(heightOptions) {
            var opts = heightOptions || {};
            if (opts.useParentContainerHeight) {
                return false;
            }
            if (opts.mobilePageScroll === false) {
                return false;
            }
            if (opts.mobilePageScroll === true) {
                return AgGridHelper.isCoarsePointerDevice();
            }
            if (!AgGridHelper.isCoarsePointerDevice()) {
                return false;
            }
            var minRaw = opts.minHeight;
            var maxRaw = opts.maxHeight;
            var usesViewportSizing = (minRaw === 'viewport' || minRaw === undefined || minRaw === null) &&
                (maxRaw === 'viewport' || maxRaw === undefined || maxRaw === null);
            return usesViewportSizing;
        };
    
        /**
         * Pinned columns consume scarce horizontal space on phones; disable pinning there.
         * @returns {boolean}
         */
        AgGridHelper.shouldDisableColumnPinning = function() {
            return AgGridHelper.isCoarsePointerDevice();
        };
    
        /**
         * Pin the compact actions column on the right for mobile layouts.
         * @param {Object} gridApi
         */
        AgGridHelper.pinMobileActionsColumn = function(gridApi) {
            if (!gridApi || !AgGridHelper.isCoarsePointerDevice()) {
                return;
            }
            if (typeof gridApi.applyColumnState !== 'function') {
                return;
            }
            try {
                gridApi.applyColumnState({
                    state: [{ colId: 'actions', pinned: 'right' }],
                    applyOrder: false
                });
            } catch (e) {
                console.warn('AgGridHelper: pinMobileActionsColumn failed:', e);
            }
        };
    
        /**
         * Unpin every column (including selection/actions with lockPinned defaults).
         * @param {Object} gridApi
         */
        AgGridHelper.clearAllColumnPins = function(gridApi) {
            if (!gridApi || typeof gridApi.getColumns !== 'function') {
                return;
            }
            try {
                var columns = gridApi.getColumns() || [];
                var state = columns.map(function(col) {
                    return { colId: col.getColId(), pinned: null };
                });
                if (state.length && typeof gridApi.applyColumnState === 'function') {
                    gridApi.applyColumnState({ state: state, applyOrder: false });
                }
                if (typeof gridApi.getGridOption === 'function' && typeof gridApi.setGridOption === 'function') {
                    var selectionDef = gridApi.getGridOption('selectionColumnDef');
                    if (selectionDef && selectionDef.pinned) {
                        gridApi.setGridOption('selectionColumnDef', Object.assign({}, selectionDef, {
                            pinned: null,
                            lockPinned: false
                        }));
                    }
                }
            } catch (e) {
                console.warn('AgGridHelper: clearAllColumnPins failed:', e);
            }
        };
    
        /**
         * Apply or restore column pinning based on current viewport (mobile vs desktop).
         * @param {Object} gridApi
         * @param {Object} [visibilityManager]
         */
        AgGridHelper.syncColumnPinningForViewport = function(gridApi, visibilityManager) {
            if (!gridApi) {
                return;
            }
    
            var gridDiv = null;
            if (typeof gridApi.getGridElement === 'function') {
                gridDiv = gridApi.getGridElement();
            } else if (gridApi.eGridDiv) {
                gridDiv = gridApi.eGridDiv;
            }
    
            if (AgGridHelper.shouldDisableColumnPinning()) {
                AgGridHelper.clearAllColumnPins(gridApi);
                AgGridHelper.pinMobileActionsColumn(gridApi);
                AgGridHelper.ensureSelectionColumnFirst(gridApi, gridDiv);
                return;
            }
    
            if (visibilityManager && typeof visibilityManager.applyColumnState === 'function') {
                visibilityManager.applyColumnState();
            }
            AgGridHelper.ensureSelectionColumnFirst(gridApi, gridDiv);
        };
    
        /**
         * Viewport edge state for scroll chaining (handles sub-pixel gaps at scroll end).
         * @param {HTMLElement} viewport
         * @returns {{ atTop: boolean, atBottom: boolean, maxScroll: number }}
         * @private
         */
        AgGridHelper._scrollChainViewportEdges = function(viewport) {
            var tolerance = AgGridHelper.SCROLL_CHAIN_EDGE_TOLERANCE || 8;
            var scrollTop = viewport.scrollTop;
            var clientHeight = viewport.clientHeight;
            var scrollHeight = viewport.scrollHeight;
            var maxScroll = scrollHeight - clientHeight;
            var gapToBottom = scrollHeight - (scrollTop + clientHeight);
            return {
                maxScroll: maxScroll,
                atTop: scrollTop <= tolerance,
                atBottom: maxScroll <= 0 || gapToBottom <= tolerance
            };
        };
    
        /**
         * Allow vertical wheel scrolling to continue on the page once the grid body hits its limit.
         * Applies to all grids initialized via AgGridHelper; call manually for direct agGrid.createGrid().
         *
         * @param {HTMLElement|Object} gridRootOrApi - Grid container element or AG Grid API
         */
        AgGridHelper.enablePageScrollChaining = function(gridRootOrApi) {
            var gridRoot = AgGridHelper._resolveGridElement(gridRootOrApi);
            if (!gridRoot || gridRoot.getAttribute('data-ag-scroll-chain') === '1') {
                return;
            }
    
            function attachScrollChain() {
                var viewport = gridRoot.querySelector('.ag-body-viewport');
                if (!viewport || viewport.getAttribute('data-ag-scroll-chain') === '1') {
                    return !!viewport;
                }
    
                viewport.setAttribute('data-ag-scroll-chain', '1');
                var pageScroller = AgGridHelper._findScrollableAncestor(gridRoot);
                var touchChain = { lastY: 0, active: false };
    
                // Capture on the grid root so chaining works over pinned columns, cells, headers, etc.
                gridRoot.addEventListener('wheel', function(e) {
                    var deltaY = e.deltaY;
                    if (!deltaY) {
                        return;
                    }
    
                    var edges = AgGridHelper._scrollChainViewportEdges(viewport);
                    if (edges.maxScroll <= 0) {
                        return;
                    }
    
                    if ((deltaY < 0 && edges.atTop) || (deltaY > 0 && edges.atBottom)) {
                        e.preventDefault();
                        e.stopPropagation();
                        pageScroller.scrollBy({ top: deltaY, left: 0, behavior: 'auto' });
                    }
                }, { capture: true, passive: false });
    
                gridRoot.addEventListener('touchstart', function(e) {
                    if (e.touches.length !== 1) {
                        touchChain.active = false;
                        return;
                    }
                    touchChain.active = true;
                    touchChain.lastY = e.touches[0].clientY;
                }, { capture: true, passive: true });
    
                gridRoot.addEventListener('touchmove', function(e) {
                    if (!touchChain.active || e.touches.length !== 1) {
                        return;
                    }
                    var currentY = e.touches[0].clientY;
                    var deltaY = touchChain.lastY - currentY;
                    touchChain.lastY = currentY;
                    if (!deltaY) {
                        return;
                    }
    
                    var edges = AgGridHelper._scrollChainViewportEdges(viewport);
                    if (edges.maxScroll <= 0) {
                        return;
                    }
    
                    if ((deltaY < 0 && edges.atTop) || (deltaY > 0 && edges.atBottom)) {
                        pageScroller.scrollBy({ top: deltaY, left: 0, behavior: 'auto' });
                    }
                }, { capture: true, passive: true });
    
                gridRoot.addEventListener('touchend', function() {
                    touchChain.active = false;
                }, { capture: true, passive: true });
                gridRoot.addEventListener('touchcancel', function() {
                    touchChain.active = false;
                }, { capture: true, passive: true });
    
                return true;
            }
    
            if (!attachScrollChain()) {
                var attempts = 0;
                var timer = setInterval(function() {
                    attempts += 1;
                    if (attachScrollChain() || attempts >= 20) {
                        clearInterval(timer);
                    }
                }, 50);
            }
    
            gridRoot.setAttribute('data-ag-scroll-chain', '1');
        };

})(typeof window !== 'undefined' ? window : this);
