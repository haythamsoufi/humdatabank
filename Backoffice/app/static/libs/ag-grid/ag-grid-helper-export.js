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
         * Returns: Copy cell, Export table to Excel.
         * @param {Object} params - AG Grid context menu params (node, column, value, api, etc.)
         * @returns {Array} Array of context menu item descriptors
         */
        AgGridHelper.prototype.buildContextMenuItems = function(params) {
            const self = this;
            const items = [];
    
            items.push({
                name: self.getTranslation('copyCell', 'Copy cell'),
                action: function() {
                    const value = params.value;
                    const text = value == null ? '' : String(value);
                    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
                        navigator.clipboard.writeText(text).catch(function() {
                            AgGridHelper.fallbackCopyToClipboard(text);
                        });
                    } else {
                        AgGridHelper.fallbackCopyToClipboard(text);
                    }
                }
            });
    
            items.push({
                name: self.getTranslation('exportTableToExcel', 'Export table to Excel'),
                action: function() {
                    const api = params.api || self.gridApi;
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
         * Setup custom right-click context menu (Copy URL on endpoint links, Copy cell, Export table to Excel).
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
                        const url = endpointLink.href;
                        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
                            navigator.clipboard.writeText(url).catch(function() {
                                AgGridHelper.fallbackCopyToClipboard(url);
                            });
                        } else {
                            AgGridHelper.fallbackCopyToClipboard(url);
                        }
                    });
                }
    
                addItem(self.getTranslation('copyCell', 'Copy cell'), function() {
                    const text = cellValue;
                    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
                        navigator.clipboard.writeText(text).catch(function() {
                            AgGridHelper.fallbackCopyToClipboard(text);
                        });
                    } else {
                        AgGridHelper.fallbackCopyToClipboard(text);
                    }
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
         * Escape a value for CSV and quote when needed.
         * @param {*} value
         * @returns {string}
         */
        AgGridHelper.prototype.formatCsvCell = function(value) {
            if (value === null || value === undefined) {
                return '';
            }
            if (typeof value === 'boolean') {
                value = value ? 'true' : 'false';
            } else if (Array.isArray(value)) {
                value = value.join('; ');
            } else if (typeof value === 'object') {
                try {
                    value = JSON.stringify(value);
                } catch (e) {
                    value = String(value);
                }
            }
            var str = String(value).replace(/\r\n/g, '\n').replace(/\r/g, '\n').replace(/"/g, '""');
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
            var visibleCols = [];
            if (typeof api.getColumns === 'function') {
                var cols = api.getColumns();
                if (cols && cols.length) {
                    visibleCols = cols
                        .filter(function(col) {
                            var def = col.getColDef ? col.getColDef() : (col.colDef || {});
                            var field = def.field || (col.getColId ? col.getColId() : col.colId);
                            var visible = col.getVisible ? col.getVisible() : (col.visible !== false);
                            // Skip selection / auto-group utility columns
                            if (!field || field === 'ag-Grid-SelectionColumn' || field === 'ag-Grid-AutoColumn') {
                                return false;
                            }
                            var exportProps = AgGridHelper.getColDefExportProps(def);
                            // Include visible columns, plus any marked exportAlways (even if hidden)
                            return visible || exportProps.exportAlways;
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
                var columnDefs = this.config.columnDefs || [];
                visibleCols = columnDefs
                    .filter(function(col) {
                        var exportProps = AgGridHelper.getColDefExportProps(col);
                        return col.field && (col.hide !== true || exportProps.exportAlways);
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
            var headers = visibleCols.map(function(col) { return col.headerName || col.field; });
    
            const rowData = [];
            function pushExportRow(node) {
                if (!node || !node.data) {
                    return;
                }
                rowData.push(visibleCols.map(function(col) {
                    return self.formatCsvCell(self.getExportCellValue(col, node));
                }));
            }
    
            if (typeof api.forEachNodeAfterFilterAndSort === 'function') {
                api.forEachNodeAfterFilterAndSort(pushExportRow);
            } else if (typeof api.forEachNode === 'function') {
                api.forEachNode(function(node) {
                    if (node && (node.displayed === true || node.displayed === undefined)) {
                        pushExportRow(node);
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

})(typeof window !== 'undefined' ? window : this);
