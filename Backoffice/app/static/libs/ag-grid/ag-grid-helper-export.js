/**
 * AG Grid Helper — Context menu and CSV export
 * @module ag-grid-helper-export
 * Loaded via ag_grid_includes.html (after ag-grid-helper-core.js).
 */
(function(global) {
    'use strict';

    var AgGridHelper = global.AgGridHelper;
    if (!AgGridHelper) {
        throw new Error('ag-grid-helper-export.js: AgGridHelper must be loaded first (ag-grid-helper-core.js)');
    }

        /**
         * Build custom context menu items for right-click on a cell.
         * Returns: Copy cell, Copy column, Copy table, Export table to Excel.
         * @param {Object} params - AG Grid context menu params (node, column, value, api, etc.)
         * @returns {Array} Array of context menu item descriptors
         */
        AgGridHelper.prototype.buildContextMenuItems = function(params) {
            const self = this;
            const items = [];
            const api = (params && params.api) || self.gridApi;
            const colId = self.getContextColumnId(params && params.column);
    
            items.push({
                name: self.getTranslation('copyCell', 'Copy cell'),
                action: function() {
                    const value = params.value;
                    const text = value == null ? '' : String(value);
                    self.copyTextToClipboard(text);
                }
            });

            items.push({
                name: self.getTranslation('copyColumn', 'Copy column'),
                action: function() {
                    self.copyColumnToClipboard(api, colId);
                }
            });

            items.push({
                name: self.getTranslation('copyTable', 'Copy table'),
                action: function() {
                    self.copyTableToClipboard(api);
                }
            });
    
            items.push({
                name: self.getTranslation('exportTableToExcel', 'Export table to Excel'),
                action: function() {
                    if (api) {
                        var exportName = (self.config && self.config.templateId)
                            ? (String(self.config.templateId).replace(/[^a-z0-9_-]+/gi, '_') + '.csv')
                            : 'export.csv';
                        self.exportTableToCSV(api, exportName);
                    }
                }
            });
    
            return items;
        };
    
        /**
         * Setup custom right-click context menu (Copy URL on endpoint links, Copy cell, Copy column, Copy table, Export table to Excel).
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
    
                const endpointLink = ev.target.closest && ev.target.closest('a.api-endpoint-link');
                if (endpointLink && endpointLink.href) {
                    const copyUrlLabel = (self.config.contextMenuLabels && self.config.contextMenuLabels.copyUrl)
                        || self.getTranslation('copyUrl', 'Copy URL');
                    addItem(copyUrlLabel, function() {
                        self.copyTextToClipboard(endpointLink.href);
                    });
                }
    
                addItem(self.getTranslation('copyCell', 'Copy cell'), function() {
                    self.copyTextToClipboard(cellValue);
                });

                addItem(self.getTranslation('copyColumn', 'Copy column'), function() {
                    self.copyColumnToClipboard(api, colId);
                });

                addItem(self.getTranslation('copyTable', 'Copy table'), function() {
                    self.copyTableToClipboard(api);
                });
    
                addItem(self.getTranslation('exportTableToExcel', 'Export table to Excel'), function() {
                    var exportName = (self.config && self.config.templateId)
                        ? (String(self.config.templateId).replace(/[^a-z0-9_-]+/gi, '_') + '.csv')
                        : 'export.csv';
                    self.exportTableToCSV(api, exportName);
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
    
        /**
         * Resolve a cell value for CSV/Excel export.
         * Prefers context.exportValueGetter (or legacy exportValueGetter), then valueGetter, then raw field data.
         * @param {Object} col - Column descriptor with field / getters / colDef
         * @param {Object} node - AG Grid row node (or { data: row })
         * @returns {*}
         */
        AgGridHelper.prototype.getExportCellValue = function(col, node) {
            if (!col || !node) {
                return '';
            }
            var data = node.data || {};
            var colDef = col.colDef || col;
            var params = {
                data: data,
                node: node,
                colDef: colDef,
                column: col.column || null,
                getValue: function() {
                    return col.field ? data[col.field] : undefined;
                }
            };
    
            var exportProps = AgGridHelper.getColDefExportProps(colDef);
            if (exportProps.exportValueGetter) {
                return exportProps.exportValueGetter(params);
            }
            if (typeof col.exportValueGetter === 'function') {
                return col.exportValueGetter(params);
            }
            if (typeof colDef.valueGetter === 'function') {
                return colDef.valueGetter(params);
            }
            if (typeof col.valueGetter === 'function') {
                return col.valueGetter(params);
            }
            if (col.field && Object.prototype.hasOwnProperty.call(data, col.field)) {
                return data[col.field];
            }
            return '';
        };

        /**
         * Column id from an AG Grid column, a colDef, or a context-menu column param.
         * @param {Object|string|null} column
         * @returns {string}
         */
        AgGridHelper.prototype.getContextColumnId = function(column) {
            if (!column) {
                return '';
            }
            if (typeof column === 'string') {
                return column;
            }
            if (typeof column.getColId === 'function') {
                return column.getColId() || '';
            }
            if (column.colId) {
                return column.colId;
            }
            var def = (typeof column.getColDef === 'function') ? column.getColDef() : (column.colDef || column);
            return (def && (def.colId || def.field)) || '';
        };

        /**
         * Write text to the clipboard, with a textarea fallback.
         * @param {string} text
         */
        AgGridHelper.prototype.copyTextToClipboard = function(text) {
            text = text == null ? '' : String(text);
            if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
                navigator.clipboard.writeText(text).catch(function() {
                    AgGridHelper.fallbackCopyToClipboard(text);
                });
            } else {
                AgGridHelper.fallbackCopyToClipboard(text);
            }
        };

        /**
         * Plain string for a cell value (no CSV/TSV quoting).
         * @param {*} value
         * @returns {string}
         */
        AgGridHelper.prototype.stringifyExportValue = function(value) {
            if (value === null || value === undefined) {
                return '';
            }
            if (typeof value === 'boolean') {
                return value ? 'true' : 'false';
            }
            if (Array.isArray(value)) {
                return value.join('; ');
            }
            if (typeof value === 'object') {
                try {
                    return JSON.stringify(value);
                } catch (e) {
                    return String(value);
                }
            }
            return String(value);
        };

        /**
         * Quote a cell for tab-separated clipboard text (Excel / Sheets paste).
         * @param {*} value
         * @returns {string}
         */
        AgGridHelper.prototype.formatClipboardCell = function(value) {
            var str = this.stringifyExportValue(value).replace(/\r\n/g, '\n').replace(/\r/g, '\n');
            if (/[\t\n"]/.test(str)) {
                return '"' + str.replace(/"/g, '""') + '"';
            }
            return str;
        };

        /**
         * Clipboard text for one cell.
         * Custom processCellForClipboard results win (same as Copy cell).
         * Otherwise the export value is used so valueGetters are included.
         * @param {Object} col
         * @param {Object} node
         * @returns {string}
         */
        AgGridHelper.prototype.getClipboardCellText = function(col, node) {
            if (!col || !node) {
                return '';
            }
            var data = node.data || {};
            var column = col.column || null;
            var colId = this.getContextColumnId(column) || col.field || '';
            var raw;
            if (colId && Object.prototype.hasOwnProperty.call(data, colId)) {
                raw = data[colId];
            } else if (col.field && Object.prototype.hasOwnProperty.call(data, col.field)) {
                raw = data[col.field];
            }

            if (this._gridOptions && typeof this._gridOptions.processCellForClipboard === 'function') {
                try {
                    var processed = this._gridOptions.processCellForClipboard({
                        value: raw,
                        node: node,
                        data: data,
                        column: column,
                        api: this.gridApi,
                        columnApi: this.columnApi,
                        context: this._gridOptions.context,
                        type: 'clipboard'
                    });
                    var rawEmpty = raw == null || raw === '';
                    var processedEmpty = processed == null || processed === '';
                    if (!(rawEmpty && processedEmpty) && processed !== raw) {
                        return this.stringifyExportValue(processed);
                    }
                } catch (e) {
                    // Fall through to the export value.
                }
            }
            return this.stringifyExportValue(this.getExportCellValue(col, node));
        };

        /**
         * Visible columns used by table export and clipboard copy.
         * @param {Object} api
         * @param {{includeHiddenExportAlways?: boolean, skipActions?: boolean}} [options]
         * @returns {Array}
         */
        AgGridHelper.prototype.getVisibleExportColumns = function(api, options) {
            options = options || {};
            var includeHiddenExportAlways = options.includeHiddenExportAlways !== false;
            var skipActions = options.skipActions === true;
            var visibleCols = [];

            if (api && typeof api.getColumns === 'function') {
                var cols = api.getColumns();
                if (cols && cols.length) {
                    visibleCols = cols
                        .filter(function(col) {
                            var def = col.getColDef ? col.getColDef() : (col.colDef || {});
                            var field = def.field || (col.getColId ? col.getColId() : col.colId);
                            var visible = col.getVisible ? col.getVisible() : (col.visible !== false);
                            if (!field || field === 'ag-Grid-SelectionColumn' || field === 'ag-Grid-AutoColumn') {
                                return false;
                            }
                            if (skipActions && AgGridHelper.isActionsColumn(def)) {
                                return false;
                            }
                            var exportProps = AgGridHelper.getColDefExportProps(def);
                            return visible || (includeHiddenExportAlways && exportProps.exportAlways);
                        })
                        .map(function(col) {
                            var def = col.getColDef ? col.getColDef() : (col.colDef || {});
                            var exportProps = AgGridHelper.getColDefExportProps(def);
                            return {
                                field: def.field || (col.getColId ? col.getColId() : col.colId),
                                headerName: def.headerName || def.field || (col.getColId ? col.getColId() : col.colId),
                                valueGetter: def.valueGetter,
                                exportValueGetter: exportProps.exportValueGetter,
                                colDef: def,
                                column: col
                            };
                        });
                }
            }

            if (!visibleCols.length) {
                var columnDefs = (this.config && this.config.columnDefs) || [];
                visibleCols = columnDefs
                    .filter(function(col) {
                        var exportProps = AgGridHelper.getColDefExportProps(col);
                        if (!col.field || (skipActions && AgGridHelper.isActionsColumn(col))) {
                            return false;
                        }
                        return col.hide !== true || (includeHiddenExportAlways && exportProps.exportAlways);
                    })
                    .map(function(col) {
                        var exportProps = AgGridHelper.getColDefExportProps(col);
                        return {
                            field: col.field,
                            headerName: col.headerName || col.field,
                            valueGetter: col.valueGetter,
                            exportValueGetter: exportProps.exportValueGetter,
                            colDef: col,
                            column: null
                        };
                    });
            }
            return visibleCols;
        };

        /**
         * Walk rows in filter/sort order (same set as Export table to Excel).
         * @param {Object} api
         * @param {Function} callback
         */
        AgGridHelper.prototype.forEachExportRow = function(api, callback) {
            if (!api || typeof callback !== 'function') {
                return;
            }
            if (typeof api.forEachNodeAfterFilterAndSort === 'function') {
                api.forEachNodeAfterFilterAndSort(function(node) {
                    if (node && node.data) {
                        callback(node);
                    }
                });
                return;
            }
            if (typeof api.forEachNode === 'function') {
                api.forEachNode(function(node) {
                    if (node && node.data && (node.displayed === true || node.displayed === undefined)) {
                        callback(node);
                    }
                });
            }
        };

        /**
         * Find one export column by col id, including columns omitted from a full-table copy.
         * @param {Object} api
         * @param {string} colId
         * @returns {Object|null}
         */
        AgGridHelper.prototype.getExportColumnById = function(api, colId) {
            if (!colId) {
                return null;
            }
            var cols = this.getVisibleExportColumns(api, {
                includeHiddenExportAlways: true,
                skipActions: false
            });
            var i;
            for (i = 0; i < cols.length; i++) {
                var id = this.getContextColumnId(cols[i].column) || cols[i].field;
                if (id === colId || cols[i].field === colId) {
                    return cols[i];
                }
            }

            var column = null;
            if (api && typeof api.getColumn === 'function') {
                column = api.getColumn(colId);
            }
            if (!column && this.columnApi && typeof this.columnApi.getColumn === 'function') {
                column = this.columnApi.getColumn(colId);
            }
            if (!column) {
                var columnDefs = (this.config && this.config.columnDefs) || [];
                for (i = 0; i < columnDefs.length; i++) {
                    var def = columnDefs[i];
                    if (def && (def.colId === colId || def.field === colId)) {
                        var fallbackProps = AgGridHelper.getColDefExportProps(def);
                        return {
                            field: def.field || colId,
                            headerName: def.headerName || def.field || colId,
                            valueGetter: def.valueGetter,
                            exportValueGetter: fallbackProps.exportValueGetter,
                            colDef: def,
                            column: null
                        };
                    }
                }
                return null;
            }

            var colDef = column.getColDef ? column.getColDef() : {};
            var exportProps = AgGridHelper.getColDefExportProps(colDef);
            return {
                field: colDef.field || colId,
                headerName: colDef.headerName || colDef.field || colId,
                valueGetter: colDef.valueGetter,
                exportValueGetter: exportProps.exportValueGetter,
                colDef: colDef,
                column: column
            };
        };

        /**
         * Tab-separated table, or one column as newline-separated values.
         * Copy table includes a header row. Copy column does not.
         * @param {Object} api
         * @param {{colId?: string, includeHeader?: boolean}} [options]
         * @returns {string}
         */
        AgGridHelper.prototype.buildClipboardText = function(api, options) {
            options = options || {};
            var self = this;
            var cols;
            if (options.colId) {
                var one = this.getExportColumnById(api, options.colId);
                cols = one ? [one] : [];
            } else {
                cols = this.getVisibleExportColumns(api, {
                    includeHiddenExportAlways: false,
                    skipActions: true
                });
            }
            if (!cols.length) {
                return '';
            }

            var lines = [];
            if (options.includeHeader) {
                lines.push(cols.map(function(col) {
                    return self.formatClipboardCell(col.headerName || col.field || '');
                }).join('\t'));
            }
            this.forEachExportRow(api, function(node) {
                lines.push(cols.map(function(col) {
                    return self.formatClipboardCell(self.getClipboardCellText(col, node));
                }).join('\t'));
            });
            return lines.join('\r\n');
        };

        /**
         * Copy the visible table (headers + filtered/sorted rows) to the clipboard.
         * @param {Object} [api]
         */
        AgGridHelper.prototype.copyTableToClipboard = function(api) {
            api = api || this.gridApi;
            this.copyTextToClipboard(this.buildClipboardText(api, { includeHeader: true }));
        };

        /**
         * Copy every filtered/sorted value in one column to the clipboard.
         * @param {Object} [api]
         * @param {string} colId
         */
        AgGridHelper.prototype.copyColumnToClipboard = function(api, colId) {
            api = api || this.gridApi;
            this.copyTextToClipboard(this.buildClipboardText(api, {
                colId: colId,
                includeHeader: false
            }));
        };
    
        /**
         * Escape a value for CSV and quote when needed.
         * @param {*} value
         * @returns {string}
         */
        AgGridHelper.prototype.formatCsvCell = function(value) {
            var str = this.stringifyExportValue(value).replace(/\r\n/g, '\n').replace(/\r/g, '\n').replace(/"/g, '""');
            return str.includes(',') || str.includes('\n') || str.includes('"') ? '"' + str + '"' : str;
        };
    
        /**
         * Export selected rows to CSV
         * @param {string} filename - Filename for export (default: 'export.csv')
         */
        AgGridHelper.prototype.exportSelectedToCSV = function(filename) {
            filename = filename || 'export.csv';
            const selectedRows = this.getSelectedRows();
            const self = this;
    
            if (selectedRows.length === 0) {
                console.warn('AgGridHelper: No rows selected for export');
                return;
            }
    
            const exportCols = this.config.columnDefs
                .filter(function(col) {
                    var exportProps = AgGridHelper.getColDefExportProps(col);
                    return col.field && (col.hide !== true || exportProps.exportAlways);
                });
            const headers = exportCols.map(function(col) { return col.headerName || col.field; });
    
            const rows = selectedRows.map(function(row) {
                return exportCols.map(function(col) {
                    return self.formatCsvCell(self.getExportCellValue(col, { data: row }));
                });
            });
    
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
    
            var self = this;
            var visibleCols = this.getVisibleExportColumns(api);
            var headers = visibleCols.map(function(col) { return col.headerName || col.field; });
    
            const rowData = [];
            this.forEachExportRow(api, function(node) {
                rowData.push(visibleCols.map(function(col) {
                    return self.formatCsvCell(self.getExportCellValue(col, node));
                }));
            });
    
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

})(typeof window !== 'undefined' ? window : this);
