/**
 * AG Grid Helper — Actions column, selection checkbox, colDef helpers, pinning
 * @module ag-grid-helper-columns
 * Loaded via ag_grid_includes.html (after ag-grid-helper-core.js).
 */
(function(global) {
    'use strict';

    var AgGridHelper = global.AgGridHelper;
    if (!AgGridHelper) {
        throw new Error('ag-grid-helper-columns.js: AgGridHelper must be loaded first (ag-grid-helper-core.js)');
    }

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
    
                this.gridApi.addEventListener('columnPinned', function() {
                    self.scheduleCheckboxWidthEnforcement();
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
                if (typeof AgGridHelper.ensureSelectionColumnFirst === 'function') {
                    AgGridHelper.ensureSelectionColumnFirst(self.gridApi, self.gridDiv);
                }
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
         * Identify checkbox selection column ids (API + DOM)
         * @param {Object} gridApi
         * @param {HTMLElement} [gridDiv]
         * @returns {Array<string>}
         */
        AgGridHelper.getSelectionColumnIds = function(gridApi, gridDiv) {
            const ids = new Set();
            const knownIds = ['ag-Grid-SelectionColumn', 'ag-Grid-AutoColumn'];
    
            knownIds.forEach(function(colId) {
                if (gridApi && typeof gridApi.getColumn === 'function') {
                    try {
                        if (gridApi.getColumn(colId)) {
                            ids.add(colId);
                        }
                    } catch (e) {
                        // ignore
                    }
                }
            });
    
            if (gridApi && typeof gridApi.getColumns === 'function') {
                const columns = gridApi.getColumns();
                if (Array.isArray(columns)) {
                    columns.forEach(function(column) {
                        if (AgGridHelper.isSelectionCheckboxColumn(column)) {
                            const colId = (typeof column.getColId === 'function')
                                ? column.getColId()
                                : (column.colId || (column.getColDef && column.getColDef().field));
                            if (colId) {
                                ids.add(colId);
                            }
                        }
                    });
                }
            }
    
            if (!ids.size && gridDiv) {
                const headerCells = gridDiv.querySelectorAll('.ag-header-cell');
                headerCells.forEach(function(cell) {
                    if (cell.querySelector('.ag-header-select-all, .ag-header-checkbox')) {
                        const colId = cell.getAttribute('col-id');
                        if (colId) {
                            ids.add(colId);
                        }
                    }
                });
            }
    
            if (!ids.size && gridDiv) {
                const checkboxCells = gridDiv.querySelectorAll('.ag-center-cols-container .ag-row:first-child .ag-cell, .ag-pinned-left-cols-container .ag-row:first-child .ag-cell');
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
         * Prepend selection column ids to a column order array
         * @param {Object} gridApi
         * @param {HTMLElement} [gridDiv]
         * @param {Array<string>} columnOrder
         * @returns {Array<string>}
         */
        AgGridHelper.prependSelectionColumnOrder = function(gridApi, gridDiv, columnOrder) {
            const selectionIds = AgGridHelper.getSelectionColumnIds(gridApi, gridDiv);
            const order = Array.isArray(columnOrder) ? columnOrder.slice() : [];
            if (!selectionIds.length) {
                return order;
            }
            const rest = order.filter(function(colId) {
                return selectionIds.indexOf(colId) === -1;
            });
            return selectionIds.concat(rest);
        };
    
        /**
         * Identify checkbox selection columns by inspecting the column definitions and DOM
         * @returns {Array<string>}
         */
        AgGridHelper.prototype.getCheckboxColumnIds = function() {
            return AgGridHelper.getSelectionColumnIds(this.gridApi, this.gridDiv);
        };
    
        /**
         * Determine whether a given column instance represents the checkbox selection column
         * @param {Object} column - Column instance
         * @returns {boolean}
         */
        AgGridHelper.isSelectionCheckboxColumn = function(column) {
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
            const normalized = String(colId).toLowerCase();
            return normalized.includes('checkbox') || normalized.includes('selection');
        };
    
        AgGridHelper.prototype.isCheckboxColumn = function(column) {
            return AgGridHelper.isSelectionCheckboxColumn(column);
        };
    
        /**
         * Keep row-selection checkbox column(s) first (pinned left, index 0).
         * @param {Object} gridApi - AG Grid API instance
         * @param {HTMLElement} [gridDiv] - Optional grid root for DOM fallback detection
         */
        AgGridHelper.ensureSelectionColumnFirst = function(gridApi, gridDiv) {
            if (!gridApi || typeof gridApi.getColumns !== 'function') {
                return;
            }
    
            const selectionIds = AgGridHelper.getSelectionColumnIds(gridApi, gridDiv);
            if (!selectionIds.length) {
                return;
            }
    
            const columns = gridApi.getColumns();
            if (!columns || !columns.length) {
                return;
            }
    
            const selectionSet = new Set(selectionIds);
            const selectionCols = [];
            const otherCols = [];
    
            columns.forEach(function(column) {
                const colId = column.getColId();
                if (selectionSet.has(colId) || AgGridHelper.isSelectionCheckboxColumn(column)) {
                    selectionCols.push(column);
                    return;
                }
                otherCols.push(column);
            });
    
            if (!selectionCols.length) {
                return;
            }
    
            const state = [];
    
            selectionCols.forEach(function(column) {
                state.push({
                    colId: column.getColId(),
                    pinned: AgGridHelper.shouldDisableColumnPinning() ? null : 'left'
                });
            });
    
            otherCols.forEach(function(column) {
                const colId = column.getColId();
                let pinned = column.getPinned ? column.getPinned() : null;
                if (pinned === true) {
                    pinned = 'left';
                }
                if (pinned === false) {
                    pinned = null;
                }
                const entry = { colId: colId, pinned: pinned || null };
                if (column.isVisible && !column.isVisible()) {
                    entry.hide = true;
                }
                state.push(entry);
            });
    
            try {
                gridApi.applyColumnState({
                    state: state,
                    applyOrder: true
                });
            } catch (e) {
                console.warn('AgGridHelper: ensureSelectionColumnFirst applyColumnState failed', e);
            }
    
            if (typeof gridApi.moveColumns === 'function') {
                try {
                    gridApi.moveColumns(selectionIds, 0);
                } catch (e) {
                    console.warn('AgGridHelper: ensureSelectionColumnFirst moveColumns failed', e);
                }
            } else if (typeof gridApi.moveColumn === 'function') {
                selectionIds.forEach(function(colId, index) {
                    try {
                        gridApi.moveColumn(colId, index);
                    } catch (e) {
                        // ignore per-column failures
                    }
                });
            }
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

            function columnNeedsAutoDetect(colDef) {
                if (!colDef || colDef.filter === false || colDef.skipAutoDetect === true) {
                    return false;
                }
                if (typeof colDef.filter === 'string') {
                    if (colDef.filter === 'agTextColumnFilter') {
                        return true;
                    }
                    return false;
                }
                if (typeof colDef.filter === 'function') {
                    return false;
                }
                if (colDef.cellRenderer && !colDef.field) {
                    return false;
                }
                return true;
            }

            var needsDetection = false;
            for (var ci = 0; ci < columnDefs.length; ci++) {
                if (columnNeedsAutoDetect(columnDefs[ci])) {
                    needsDetection = true;
                    break;
                }
            }
            if (!needsDetection) {
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
                if (colDef.filter === false || colDef.skipAutoDetect === true) return true;
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
         * True if a column definition is the standard actions column.
         * @param {Object} colDef
         * @returns {boolean}
         */
        AgGridHelper.isActionsColumn = function(colDef) {
            if (!colDef) {
                return false;
            }
            var id = colDef.colId || colDef.field;
            return id === 'actions';
        };
    
        /**
         * Application metadata for a column def (AG Grid allows colDef.context).
         * @param {Object} colDef
         * @returns {Object}
         * @private
         */
        AgGridHelper.getColDefHelperMeta = function(colDef) {
            if (!colDef) {
                return {};
            }
            if (!colDef.context || typeof colDef.context !== 'object' || Array.isArray(colDef.context)) {
                colDef.context = {};
            }
            if (!colDef.context.__agGridHelper || typeof colDef.context.__agGridHelper !== 'object') {
                colDef.context.__agGridHelper = {};
            }
            return colDef.context.__agGridHelper;
        };
    
        /**
         * Minimum desktop width for inline icon action buttons (not the mobile ⋮ menu).
         * @param {Object} colDef
         * @returns {number}
         */
        AgGridHelper.getActionsColumnDesktopMinWidth = function(colDef) {
            var meta = AgGridHelper.getColDefHelperMeta(colDef);
            var desktop = meta.actionsDesktopWidth || {};
            var fromDef = colDef.minWidth || colDef.width || 120;
            var fromSnapshot = desktop.minWidth || desktop.width || 0;
            return Math.max(fromDef, fromSnapshot, 132);
        };
    
        /**
         * Apply desktop-only safeguards so the actions column is not shrunk by sizeColumnsToFit
         * or a previously saved mobile width.
         * @param {Object} colDef
         */
        AgGridHelper.applyActionsColumnDesktopLayout = function(colDef) {
            if (!colDef || AgGridHelper.isCoarsePointerDevice()) {
                return;
            }
            var minW = AgGridHelper.getActionsColumnDesktopMinWidth(colDef);
            colDef.minWidth = Math.max(colDef.minWidth || 0, minW);
            if (!colDef.width || colDef.width < minW) {
                colDef.width = Math.max(colDef.width || 0, minW);
            }
            if (colDef.suppressSizeToFit !== false) {
                colDef.suppressSizeToFit = true;
            }
        };
    
        /**
         * Wrap actions column renderers so mobile uses a vertical-dots overflow menu.
         * @param {Array} columnDefs
         */
        AgGridHelper.wrapActionsColumnRenderers = function(columnDefs) {
            if (!Array.isArray(columnDefs)) {
                return;
            }
            columnDefs.forEach(function(colDef) {
                var meta = AgGridHelper.getColDefHelperMeta(colDef);
                if (!AgGridHelper.isActionsColumn(colDef) || meta.actionsMobileWrapped) {
                    return;
                }
                if (!meta.skipMobileActionsOverflow &&
                    typeof AgGridRenderers !== 'undefined' &&
                    typeof AgGridRenderers.wrapActionsCellRenderer === 'function' &&
                    colDef.cellRenderer) {
                    colDef.cellRenderer = AgGridRenderers.wrapActionsCellRenderer(colDef.cellRenderer);
                }
                meta.actionsMobileWrapped = true;
                if (!AgGridHelper.isCoarsePointerDevice()) {
                    AgGridHelper.applyActionsColumnDesktopLayout(colDef);
                }
                AgGridHelper.applyActionsColumnMobileWidths([colDef]);
            });
        };
    
        /**
         * Re-apply mobile/desktop actions column widths (after pinActionsColumn, sizeColumnsToFit, etc.).
         * @param {Array} columnDefs
         * @param {Object} [gridApi]
         */
        AgGridHelper.syncActionsColumnLayout = function(columnDefs, gridApi) {
            AgGridHelper.applyActionsColumnMobileWidths(columnDefs, gridApi);
        };
    
        /**
         * Narrow the actions column on mobile; restore typical widths on desktop.
         * @param {Array} columnDefs
         * @param {Object} [gridApi]
         */
        AgGridHelper.applyActionsColumnMobileWidths = function(columnDefs, gridApi) {
            if (!Array.isArray(columnDefs)) {
                return;
            }
    
            var mobile = AgGridHelper.isCoarsePointerDevice();
            var state = [];
    
            columnDefs.forEach(function(colDef) {
                if (!AgGridHelper.isActionsColumn(colDef)) {
                    return;
                }
    
                var meta = AgGridHelper.getColDefHelperMeta(colDef);
                if (!meta.actionsDesktopWidth) {
                    var snapshotWidth = colDef.width;
                    var snapshotMin = colDef.minWidth;
                    var snapshotMax = colDef.maxWidth;
                    if (mobile && (snapshotWidth <= 44 || snapshotMin <= 44)) {
                        snapshotWidth = 120;
                        snapshotMin = 100;
                        snapshotMax = 180;
                    }
                    meta.actionsDesktopWidth = {
                        width: snapshotWidth,
                        minWidth: snapshotMin,
                        maxWidth: snapshotMax
                    };
                }
    
                if (mobile) {
                    if (meta.actionsDesktopHeaderName === undefined) {
                        meta.actionsDesktopHeaderName = colDef.headerName;
                    }
                    colDef.headerName = '';
                    colDef.pinned = 'right';
                    colDef.lockPinned = true;
                    colDef.width = 40;
                    colDef.minWidth = 40;
                    colDef.maxWidth = 44;
                    colDef.suppressSizeToFit = true;
                } else {
                    if (meta.actionsDesktopHeaderName !== undefined) {
                        colDef.headerName = meta.actionsDesktopHeaderName;
                    }
                    var desktop = meta.actionsDesktopWidth || {};
                    if (desktop.width) {
                        colDef.width = desktop.width;
                    }
                    if (desktop.minWidth) {
                        colDef.minWidth = desktop.minWidth;
                    }
                    if (desktop.maxWidth) {
                        colDef.maxWidth = desktop.maxWidth;
                    }
                    AgGridHelper.applyActionsColumnDesktopLayout(colDef);
                }
    
                if (gridApi && typeof gridApi.applyColumnState === 'function') {
                    var colState = {
                        colId: colDef.colId || colDef.field || 'actions',
                        width: Math.max(
                            colDef.width || 0,
                            mobile ? 40 : AgGridHelper.getActionsColumnDesktopMinWidth(colDef)
                        )
                    };
                    if (mobile) {
                        colState.pinned = 'right';
                    }
                    state.push(colState);
                }
            });
    
            if (gridApi && state.length) {
                try {
                    gridApi.applyColumnState({ state: state, applyOrder: false });
                } catch (e) {
                    // Non-fatal
                }
            }
    
            if (gridApi && typeof gridApi.refreshHeader === 'function') {
                try {
                    gridApi.refreshHeader();
                } catch (e) {
                    // Non-fatal
                }
            }
        };
    
        /**
         * Move app-specific colDef keys into colDef.context so AG Grid v31+ validation stays quiet.
         * @param {Array} columnDefs
         * @returns {Array}
         */
        AgGridHelper.normalizeCustomColDefProps = function(columnDefs) {
            if (!Array.isArray(columnDefs)) {
                return columnDefs;
            }
            columnDefs.forEach(function(def) {
                if (!def || typeof def !== 'object') {
                    return;
                }
                if (def.children && def.children.length) {
                    AgGridHelper.normalizeCustomColDefProps(def.children);
                }
                var ctx = def.context;
                if (!ctx || typeof ctx !== 'object') {
                    ctx = {};
                    def.context = ctx;
                }
                if (typeof def.exportValueGetter === 'function') {
                    ctx.exportValueGetter = def.exportValueGetter;
                    delete def.exportValueGetter;
                }
                if (def.exportAlways === true) {
                    ctx.exportAlways = true;
                    delete def.exportAlways;
                }
            });
            return columnDefs;
        };
    
        /**
         * Read export helpers stored on colDef.context (or legacy top-level props).
         * @param {Object} colDef
         * @returns {{exportValueGetter: Function|null, exportAlways: boolean}}
         */
        AgGridHelper.getColDefExportProps = function(colDef) {
            var ctx = (colDef && colDef.context) || {};
            return {
                exportValueGetter: typeof ctx.exportValueGetter === 'function'
                    ? ctx.exportValueGetter
                    : (colDef && typeof colDef.exportValueGetter === 'function' ? colDef.exportValueGetter : null),
                exportAlways: ctx.exportAlways === true || (colDef && colDef.exportAlways === true)
            };
        };
    
        /**
         * Remove pinned flags from column definitions before grid init on mobile.
         * @param {Array} columnDefs
         * @returns {Array}
         */
        AgGridHelper.stripColumnPinsFromColDefs = function(columnDefs) {
            if (!columnDefs || !columnDefs.length) {
                return columnDefs;
            }
            var mobile = AgGridHelper.shouldDisableColumnPinning();
            return columnDefs.map(function(def) {
                var copy = Object.assign({}, def);
                if (mobile && AgGridHelper.isActionsColumn(copy)) {
                    copy.pinned = 'right';
                    copy.lockPinned = true;
                    copy.headerName = '';
                } else if (copy.pinned) {
                    copy.pinned = null;
                }
                if (copy.children && copy.children.length) {
                    copy.children = AgGridHelper.stripColumnPinsFromColDefs(copy.children);
                }
                return copy;
            });
        };
    
        /**
         * Ensure no column is narrower than its colDef minWidth (or width when minWidth is unset).
         * Useful after sizeColumnsToFit or restoring saved column widths from localStorage.
         *
         * @param {Object} gridApi - AG Grid API instance
         */
        AgGridHelper.enforceColumnMinWidths = function(gridApi) {
            if (!gridApi || typeof gridApi.getColumns !== 'function') {
                return;
            }
    
            var columns = gridApi.getColumns();
            if (!columns || !columns.length) {
                return;
            }
    
            var state = [];
            columns.forEach(function(col) {
                var def = col.getColDef();
                var minW;
                if (AgGridHelper.isActionsColumn(def)) {
                    if (AgGridHelper.isCoarsePointerDevice()) {
                        minW = Math.min(def.minWidth || 40, 44);
                    } else {
                        minW = AgGridHelper.getActionsColumnDesktopMinWidth(def);
                    }
                } else {
                    minW = def.minWidth || def.width;
                }
                if (!minW) {
                    return;
                }
                if (col.getActualWidth() < minW) {
                    state.push({ colId: col.getColId(), width: minW });
                }
            });
    
            if (!state.length || typeof gridApi.applyColumnState !== 'function') {
                return;
            }
    
            try {
                gridApi.applyColumnState({ state: state });
            } catch (e) {
                console.warn('AgGridHelper: enforceColumnMinWidths failed:', e);
            }
        };
    
        /**
         * Utility function to pin actions column to right
         * Call after grid is initialized to ensure actions column stays pinned
         *
         * @param {Object} gridApi - AG Grid API instance
         * @param {Array} columnOrder - Optional array of column IDs in desired order
         * @param {Object} visibilityManager - Optional ColumnVisibilityManager (preserves saved pins)
         */
        AgGridHelper.pinActionsColumn = function(gridApi, columnOrder, visibilityManager) {
            if (!gridApi || typeof gridApi.applyColumnState !== 'function') {
                return;
            }
    
            var gridDiv = null;
            if (gridApi.getGridElement && typeof gridApi.getGridElement === 'function') {
                gridDiv = gridApi.getGridElement();
            } else if (gridApi.eGridDiv) {
                gridDiv = gridApi.eGridDiv;
            }
    
            if (AgGridHelper.shouldDisableColumnPinning()) {
                AgGridHelper.syncColumnPinningForViewport(gridApi, visibilityManager);
                return;
            }
    
            var mgr = visibilityManager ||
                (window.gridHelper && window.gridHelper.columnVisibilityManager) ||
                window.columnVisibilityManager;
    
            function savedPin(colId) {
                if (!mgr || typeof mgr.getSavedPin !== 'function') {
                    return null;
                }
                return mgr.getSavedPin(colId);
            }
    
            try {
                var selectionIds = AgGridHelper.getSelectionColumnIds(gridApi, gridDiv);
                var mergedOrder = columnOrder && Array.isArray(columnOrder)
                    ? AgGridHelper.prependSelectionColumnOrder(gridApi, gridDiv, columnOrder)
                    : selectionIds.slice();
    
                var state;
                if (mergedOrder.length) {
                    state = mergedOrder.map(function(colId) {
                        if (selectionIds.indexOf(colId) !== -1) {
                            return { colId: colId, pinned: 'left' };
                        }
                        return {
                            colId: colId,
                            pinned: colId === 'actions' ? 'right' : savedPin(colId)
                        };
                    });
                } else {
                    state = [{ colId: 'actions', pinned: 'right' }];
                }
    
                gridApi.applyColumnState({
                    state: state,
                    applyOrder: mergedOrder.length > 0
                });
                AgGridHelper.ensureSelectionColumnFirst(gridApi, gridDiv);
                if (typeof gridApi.getColumnDefs === 'function') {
                    AgGridHelper.syncActionsColumnLayout(gridApi.getColumnDefs(), gridApi);
                }
            } catch (e) {
                console.warn('AgGridHelper: Could not pin actions column:', e);
            }
        };

})(typeof window !== 'undefined' ? window : this);
