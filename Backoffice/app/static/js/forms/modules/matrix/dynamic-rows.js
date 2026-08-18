/** Dynamic matrix rows: add, remove, restore, sort, and legend highlighting. */
import { debugLog, debugError, debugWarn } from '../debug.js';
import { _t, __canEditMatrixContainer, ROW_TOTAL_COLUMN_NAME } from './shared.js';
import {
    __configFlag,
    __getSavedMatrixCellScalar,
    __parseMatrixCellKey,
    __resolveColumnMaxDecimals,
    __serializeMatrixData,
    __setMatrixNumericCellDisplay,
} from './formatting.js';
import {
    __ROW_TOTAL_INPUT_CLASS,
    __ROW_TOTAL_INPUT_WRAPPER_CLASS,
    __createRowTotalConflictIndicator,
    __rowTotalCellKey,
    __rowTotalManualEnabled,
    __rowTotalValidation,
} from './totals.js';

const ROW_GO_UNMATCHED_PREFIX = 'row_go_unmatched|';

export const matrixDynamicRowsMixin = {

/**
 * Add dynamic row to matrix
 * @param {string} fieldId - Matrix field ID
 * @param {string} rowLabel - Row label/name
 * @param {Object} rowData - Row data object
 * @param {string|null} rowId - Row ID (optional)
 * @param {boolean} isAutoLoaded - Whether this row was auto-loaded (default: false)
 */
addDynamicRow(fieldId, rowLabel, rowData, rowId = null, isAutoLoaded = false) {
    const fieldIdStr = String(fieldId || '');
    const container = document.querySelector(`[data-field-id="${fieldIdStr}"]`);

    // Find tbody - try by ID first, then via container (works with repeat sections)
    let tbody = document.getElementById(`matrix-tbody-${fieldIdStr}`);
    if (!tbody && container) {
        // Find tbody within container (works with repeat sections where IDs are transformed)
        tbody = container.querySelector('tbody[id*="matrix-tbody-"]') || container.querySelector('tbody');
    }

    // Ensure matrix is registered (important when matrices are injected after initial init)
    let matrixInfo = this.matrices.get(fieldIdStr);
    if (container && (!matrixInfo || !matrixInfo.config || !matrixInfo.config.columns)) {
        matrixInfo = this._registerMatrixFromDom(container, fieldIdStr) || matrixInfo;
    }
    // If we have a matrix record but the container changed (dynamic DOM), keep it in sync
    if (matrixInfo && container && matrixInfo.container !== container) {
        matrixInfo.container = container;
    }

    debugLog('matrix-handler', '[ADD DYNAMIC ROW] Finding elements', {
        fieldId: fieldIdStr,
        hasContainer: !!container,
        foundTbody: !!tbody,
        tbodyId: tbody?.id,
        hasMatrixInfo: !!matrixInfo,
        hasColumns: !!(matrixInfo && matrixInfo.config && matrixInfo.config.columns)
    });

    if (!tbody || !matrixInfo || !matrixInfo.config.columns) {
        debugWarn('matrix-handler', '[ADD DYNAMIC ROW] Missing required elements', {
            hasTbody: !!tbody,
            hasMatrixInfo: !!matrixInfo,
            hasColumns: !!(matrixInfo && matrixInfo.config && matrixInfo.config.columns),
            containerId: container?.id
        });
        return;
    }

    const columns = matrixInfo.config.columns;

    // Get row ID from rowData using helper method
    const finalRowId = this.extractRowId(rowData, rowLabel, rowId);

    // Debug logging
    debugLog('matrix-handler', `Adding dynamic row:`, {
        fieldId,
        rowLabel,
        providedRowId: rowId,
        rowData_id: rowData?.id,
        rowData__id: rowData?._id,
        finalRowId
    });

    // Check if row already exists (by ID if available, otherwise by label)
    const existingRow = finalRowId !== rowLabel
        ? tbody.querySelector(`tr[data-row-id="${finalRowId}"]`)
        : tbody.querySelector(`tr[data-row-label="${rowLabel}"]`);
    if (existingRow) {
        debugLog('matrix-handler', `Row already exists, skipping: ${rowLabel} (ID: ${finalRowId})`);
        return;
    }

    // Create new row
    const row = document.createElement('tr');
    row.className = 'matrix-data-row group';
    row.setAttribute('role', 'row');
    row.setAttribute('data-row-label', rowLabel);
    row.setAttribute('data-row-id', finalRowId);
    row.setAttribute('data-row-data', JSON.stringify(rowData));
    row.setAttribute('data-is-auto-loaded', isAutoLoaded ? 'true' : 'false');
    const groupByCol = matrixInfo.config?.group_by_column;
    if (groupByCol && rowData && rowData[groupByCol]) {
        row.setAttribute('data-group', rowData[groupByCol]);
    }

    // Create row header cell
    const headerCell = document.createElement('td');
    headerCell.className = 'border border-gray-300 font-medium text-gray-700 bg-gray-50';
    headerCell.setAttribute('role', 'rowheader');
    headerCell.setAttribute('scope', 'row');
    // Set dynamic width constraints: min-width for small content, max-width threshold for text wrapping
    // Width will grow naturally based on content and available space, but wrap at 400px threshold
    headerCell.style.minWidth = '80px';
    headerCell.style.maxWidth = '400px';
    headerCell.style.wordWrap = 'break-word';
    headerCell.style.overflowWrap = 'break-word';
    headerCell.style.whiteSpace = 'normal';
    headerCell.style.verticalAlign = 'middle';

    // Apply beige highlight to row header if this is a manually added row and highlighting is enabled
    const matrix = this.matrices.get(fieldIdStr);
    const autoLoadEnabled = __configFlag(matrix?.config?.auto_load_entities, false);
    const highlightManualRows = __configFlag(matrix?.config?.highlight_manual_rows, autoLoadEnabled);
    if (matrix && matrix.config && highlightManualRows && !isAutoLoaded) {
        headerCell.style.backgroundColor = '#f5f5dc'; // Beige color
        headerCell.classList.add('matrix-manual-row-header');
    }

    const labelSpan = document.createElement('span');
    labelSpan.textContent = rowLabel;
    labelSpan.style.wordWrap = 'break-word';
    labelSpan.style.overflowWrap = 'break-word';

    // Only add remove button for manually added rows (not auto-loaded) on editable forms
    if (!isAutoLoaded && this._canEditMatrix(container)) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'remove-matrix-row-btn ml-1 text-red-600 hover:text-red-800 text-xs opacity-0 group-hover:opacity-100 transition-opacity duration-200';
        btn.title = _t('Remove row');

        const icon = document.createElement('i');
        icon.className = 'fas fa-times w-3 h-3';
        btn.appendChild(icon);

        // Inline with label text so the X sits on the last wrapped line, not a new row
        labelSpan.appendChild(btn);
    }

    headerCell.appendChild(labelSpan);
    row.appendChild(headerCell);

    // Create data cells
    columns.forEach((column, columnIndex) => {
        const columnName = typeof column === 'object' ? column.name : column;
        const columnType = typeof column === 'object' ? column.type : 'number';
        const columnDisplayName = this.getColumnDisplayName(column);
        // Check if this is a variable column (new structure: is_variable, or legacy: type === 'variable')
        const isVariable = typeof column === 'object' && (column.is_variable === true || column.type === 'variable');

        // Determine if this is a readonly variable column
        const isReadonlyVariable = isVariable &&
            (typeof column === 'object' ? (column.variable_readonly !== false) : true);

        const cell = document.createElement('td');
        cell.className = `border border-gray-300 px-2 py-1${columnType === 'tick' ? ' text-center' : ''}${isReadonlyVariable ? ' bg-gray-100' : ''}`;
        cell.setAttribute('role', 'gridcell');

        // Use row ID instead of row label for the cell key
        const cellKey = `${finalRowId}_${columnName}`;
        const input = document.createElement('input');
        const columnMaxDecimals = __resolveColumnMaxDecimals(typeof column === 'object' ? column : null);

        if (isVariable) {
            // Variable column - type can be number or tick, will be resolved via API
            const variableName = typeof column === 'object' ? (column.variable || column.variable_name) : null;
            const variableReadonly = typeof column === 'object' ? (column.variable_readonly !== false) : true;
            const variableSaveValue = typeof column === 'object' ? (column.variable_save_value !== false) : true;

            if (columnType === 'tick') {
                // Variable tick column
                input.type = 'checkbox';
                input.className = `w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 mx-auto${variableReadonly ? ' opacity-50' : ''}`;
                input.value = '1';
                input.setAttribute('data-column-type', 'variable');
                input.setAttribute('data-variable-name', variableName || '');
                input.setAttribute('data-variable-save-value', variableSaveValue ? 'true' : 'false');
                input.setAttribute('data-variable-readonly', variableReadonly ? 'true' : 'false');
                input.setAttribute('aria-label', `Variable tick for ${rowLabel} and ${columnDisplayName}`);
            } else {
                // Variable number column
                input.type = 'number';
            input.className = variableReadonly
                ? 'w-full px-2 py-1 border-0 bg-transparent focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500'
                : 'w-full px-2 py-1 border-0 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500';
                input.min = '0';
                input.step = '0.01';
            input.value = '';
            input.setAttribute('data-column-type', 'variable');
            input.setAttribute('data-variable-name', variableName || '');
            input.setAttribute('data-variable-save-value', variableSaveValue ? 'true' : 'false');
            input.setAttribute('data-variable-readonly', variableReadonly ? 'true' : 'false');
            if (columnMaxDecimals !== null) input.setAttribute('data-max-decimals', String(columnMaxDecimals));
            input.setAttribute('aria-label', `Variable value for ${rowLabel} and ${columnDisplayName}`);
            }
        } else if (columnType === 'tick') {
            input.type = 'checkbox';
            input.className = 'w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 mx-auto';
            input.value = '1';
            input.setAttribute('data-column-type', 'tick');
            input.setAttribute('aria-label', `Tick for ${rowLabel} and ${columnDisplayName}`);
        } else {
            input.type = 'number';
            input.className = 'w-full px-2 py-1 border-0 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500';
            input.min = '0';
            input.step = '0.01';
            input.value = '';
            input.setAttribute('data-column-type', 'number');
            if (columnMaxDecimals !== null) input.setAttribute('data-max-decimals', String(columnMaxDecimals));
            input.setAttribute('aria-label', `Value for ${rowLabel} and ${columnDisplayName}`);
        }

        input.setAttribute('data-row', rowLabel);
        input.setAttribute('data-row-id', finalRowId);
        input.setAttribute('data-column', columnName);
        input.setAttribute('data-cell-key', cellKey);

        const variableReadonlyForCell = isVariable
            ? (typeof column === 'object' ? (column.variable_readonly !== false) : true)
            : false;
        this._applyMatrixInputEditability(input, container, variableReadonlyForCell);

        cell.appendChild(input);
        row.appendChild(cell);
    });

    // Create total cell if needed
    if (matrixInfo.config.show_row_totals !== false) {
        const totalCell = document.createElement('td');
        const isManualTotal = __rowTotalManualEnabled(matrixInfo.config);
        totalCell.className = isManualTotal && this._canEditMatrix(container)
            ? 'border border-gray-300 px-2 py-1'
            : 'border border-gray-300 px-2 py-1 bg-gray-100';
        totalCell.setAttribute('role', 'gridcell');

        if (isManualTotal) {
            const totalCellKey = __rowTotalCellKey(finalRowId);
            const wrapper = document.createElement('div');
            wrapper.className = __ROW_TOTAL_INPUT_WRAPPER_CLASS;

            const totalInput = document.createElement('input');
            totalInput.type = 'number';
            totalInput.className = __ROW_TOTAL_INPUT_CLASS;
            totalInput.setAttribute('data-row', rowLabel);
            totalInput.setAttribute('data-row-id', finalRowId);
            totalInput.setAttribute('data-column', ROW_TOTAL_COLUMN_NAME);
            totalInput.setAttribute('data-cell-key', totalCellKey);
            totalInput.setAttribute('data-is-row-total', 'true');
            totalInput.setAttribute('data-row-total-validation', __rowTotalValidation(matrixInfo.config));
            totalInput.setAttribute('data-original-value', '0');
            totalInput.setAttribute('aria-label', `Total for row ${rowLabel}`);
            totalInput.min = '0';
            totalInput.step = '0.01';
            this._applyMatrixInputEditability(totalInput, container, false);

            const indicator = __createRowTotalConflictIndicator();

            wrapper.appendChild(totalInput);
            wrapper.appendChild(indicator);
            totalCell.appendChild(wrapper);
        } else {
            const totalSpan = document.createElement('span');
            totalSpan.className = 'matrix-row-total inline-block w-full px-2 py-1 text-center text-sm font-medium';
            totalSpan.setAttribute('data-row', rowLabel);
            totalSpan.setAttribute('data-row-id', finalRowId);
            totalSpan.setAttribute('aria-label', `Total for row ${rowLabel}`);
            totalSpan.textContent = '0';
            totalCell.appendChild(totalSpan);
        }

        row.appendChild(totalCell);
    }

    // Insert data rows after the totals row (always first) and before the search bar when present
    const insertBefore = this._getMatrixDataRowInsertBefore(tbody);
    if (insertBefore) {
        tbody.insertBefore(row, insertBefore);
    } else {
        tbody.appendChild(row);
    }
    this._ensureTotalsRowAtTop(tbody);

    // Update totals and hidden data
    this.calculateMatrixTotals(fieldIdStr);

    // Defer variable resolution to batch with other rows
    // This prevents individual API calls for each row
    this.scheduleVariableResolution(fieldIdStr);

    this._lockMatrixContainerIfReadOnly(container);

    debugLog('matrix-handler', `Added dynamic row "${rowLabel}" to matrix ${fieldIdStr}`);
}

/**
 * Schedule variable resolution for a matrix (batched)
 * This debounces resolution so multiple rows added quickly are resolved in one batch
 */,


/**
 * Return true when matrix config defines at least one variable column.
 * @param {Object} matrixConfig
 * @returns {boolean}
 */
_matrixHasVariableColumns(matrixConfig) {
    return (matrixConfig?.columns || []).some((col) =>
        typeof col === 'object' && (col.is_variable === true || col.type === 'variable'));
}

/**
 * Return the column-totals row in a matrix tbody, if present.
 * @param {HTMLTableSectionElement} tbody
 * @returns {HTMLTableRowElement|null}
 */,


/**
 * Clean up tooltip event listeners and scroll handlers for a row
 */
cleanupRowTooltips(row) {
    if (!row) return;

    // Find all cells in the row that might have tooltip handlers
    const cells = row.querySelectorAll('td');
    cells.forEach(cell => {
        // Remove event listeners if they exist
        if (cell._variableTooltipMouseEnter) {
            cell.removeEventListener('mouseenter', cell._variableTooltipMouseEnter);
            delete cell._variableTooltipMouseEnter;
        }
        if (cell._variableTooltipMouseLeave) {
            cell.removeEventListener('mouseleave', cell._variableTooltipMouseLeave);
            delete cell._variableTooltipMouseLeave;
        }
        if (cell._variableTooltipMouseMove) {
            cell.removeEventListener('mousemove', cell._variableTooltipMouseMove);
            delete cell._variableTooltipMouseMove;
        }

        // Remove scroll handler if it exists
        if (cell._variableTooltipScrollHandler) {
            window.removeEventListener('scroll', cell._variableTooltipScrollHandler, true);
            delete cell._variableTooltipScrollHandler;
        }

        // Clean up stored references
        delete cell._variableOriginalValue;
        delete cell._variableInput;

        // Find and remove associated tooltip from DOM
        const input = cell.querySelector('input[data-cell-key]');
        if (input) {
            const cellKey = input.getAttribute('data-cell-key');
            if (cellKey) {
                const tooltipId = `variable-tooltip-${cellKey}`;
                const tooltip = document.getElementById(tooltipId);
                if (tooltip) {
                    tooltip.remove();
                }
            }
        }
    });
}

/**
 * Handle remove row button click
 */,


/**
 * Handle remove row button click
 */
handleRemoveRowClick(button) {
    const row = button.closest('tr');
    const container = row?.closest('.matrix-container');
    if (container && !this._canEditMatrix(container)) return;

    // Check if row is actually connected to the DOM
    if (!row || !row.parentElement || !row.isConnected) {
        debugLog('matrix-handler', 'Row is detached or already being processed - ignoring click');
        return;
    }

    const rowLabel = row.getAttribute('data-row-label');
    const rowId = row.getAttribute('data-row-id');

    if (!rowId) {
        debugError('matrix-handler', 'Cannot remove row: missing data-row-id attribute', { rowLabel });
        if (window.showAlert) {
            window.showAlert(_t('Error: Cannot remove row. Please refresh the page and try again.'), 'error');
        } else {
            (window.__clientWarn || console.warn)(_t('Error: Cannot remove row. Please refresh the page and try again.'));
        }
        return;
    }

    // Check if this row is already being removed
    if (this.rowsBeingRemoved.has(rowId)) {
        debugLog('matrix-handler', `Row "${rowLabel}" (ID: ${rowId}) is already being removed - ignoring duplicate click`);
        return;
    }

    // Mark row as being removed
    this.rowsBeingRemoved.add(rowId);

    const fieldId = container?.dataset?.fieldId;

    if (!container) {
        this.rowsBeingRemoved.delete(rowId); // Clean up tracking
        debugError('matrix-handler', 'Cannot find .matrix-container parent', {
            button, row, rowLabel, rowId
        });
        return;
    }

    if (!fieldId) {
        this.rowsBeingRemoved.delete(rowId); // Clean up tracking
        debugError('matrix-handler', 'Could not find fieldId', { row, container, fieldId });
        return;
    }

    const performRemove = () => {
        // Clean up tooltip event listeners and handlers before removing row
        this.cleanupRowTooltips(row);

        // Get matrix info
        const matrix = this.matrices.get(fieldId);

        // Remove all cell data for this row from matrix.data
        if (matrix && matrix.data) {
            // Get all cell keys that belong to this row
            // Cell keys are standardized to format: "rowId_columnName"
            const cellKeysToRemove = [];
            Object.keys(matrix.data).forEach(cellKey => {
                // Skip metadata fields
                if (cellKey.startsWith('_')) {
                    return;
                }

                const parsed = __parseMatrixCellKey(cellKey, matrix.config);
                if (parsed && parsed.rowId === String(rowId)) {
                    cellKeysToRemove.push(cellKey);
                }
            });

            // Also remove the GO-unmatched sentinel flag for this row (format:
            // "row_go_unmatched|<rowId>"). __parseMatrixCellKey uses the
            // "rowId_columnName" convention and returns null for pipe-separated
            // keys, so the sentinel is never caught by the loop above.
            const unmatchedFlagKey = `${ROW_GO_UNMATCHED_PREFIX}${rowId}`;
            if (unmatchedFlagKey in matrix.data) {
                cellKeysToRemove.push(unmatchedFlagKey);
            }

            // Remove all cell keys for this row
            cellKeysToRemove.forEach(cellKey => {
                delete matrix.data[cellKey];
                debugLog('matrix-handler', `Removed cell data: ${cellKey}`);
            });

            // Cache hidden field reference if not already cached
            if (!matrix.hiddenField) {
                matrix.hiddenField = container.querySelector('input[type="hidden"]');
            }

            // Update hidden field
            if (matrix.hiddenField) {
                this.sanitizeMatrixData(matrix);
                matrix.hiddenField.value = __serializeMatrixData(matrix.data);
                debugLog('matrix-handler', `Updated hidden field after row removal:`, matrix.data);
            }
        }

        // Remove the DOM element
        row.remove();
        this.calculateMatrixTotals(fieldId);

        // Reapply duplicate highlighting after removal (in case removal fixed duplicates)
        this.applyDuplicateEntityHighlighting(fieldId);

        // Update legend visibility after removing row
        this.updateLegendVisibility(fieldId);

        debugLog('matrix-handler', `Removed row "${rowLabel}" (ID: ${rowId}) from matrix ${fieldId}`);
    };

    // Confirm removal (avoid native confirm)
    const confirmMessage = `${_t('Are you sure you want to remove the row')} "${rowLabel}"?`;
    const cleanupTracking = () => this.rowsBeingRemoved.delete(rowId);
    const onConfirm = () => {
        try {
            performRemove();
        } finally {
            cleanupTracking();
        }
    };
    const onCancel = () => cleanupTracking();

    if (window.showDangerConfirmation) {
        window.showDangerConfirmation(confirmMessage, onConfirm, onCancel, _t('Remove'), _t('Cancel'), _t('Remove Row?'));
        return;
    }
    if (window.showConfirmation) {
        window.showConfirmation(confirmMessage, onConfirm, onCancel, _t('Remove'), _t('Cancel'), _t('Remove Row?'));
        return;
    }

    (window.__clientWarn || console.warn)('Confirmation dialog not available:', confirmMessage);
    cleanupTracking();
    return;
}


/**
 * Get existing rows in matrix
 */,



/**
 * Get existing rows in matrix
 */
getExistingRows(fieldId) {
    // Find tbody - try by ID first, then via container (works with repeat sections)
    let tbody = document.getElementById(`matrix-tbody-${fieldId}`);
    if (!tbody) {
        const container = document.querySelector(`[data-field-id="${fieldId}"]`);
        if (container) {
            tbody = container.querySelector('tbody[id*="matrix-tbody-"]') || container.querySelector('tbody');
        }
    }
    if (!tbody) return [];

    return Array.from(tbody.querySelectorAll('tr[data-row-label]'))
        .map(row => row.getAttribute('data-row-label'));
}

/**
 * Extract row information from saved data
 * Only accepts ID-based cell keys (standardized format: rowId_columnName)
 */,


/**
 * Extract row information from saved data
 * Only accepts ID-based cell keys (standardized format: rowId_columnName)
 */
extractRowInfoFromData(data, config) {
    const rowInfoMap = new Map(); // Map of rowId -> {rowId, rowName, cellKeys, values}

    Object.keys(data).forEach(cellKey => {
        // Skip metadata fields
        if (cellKey.startsWith('_')) {
            return;
        }

        const parsed = __parseMatrixCellKey(cellKey, config);
        if (!parsed) {
            return;
        }

        const { rowId, columnName } = parsed;

        // Verify this column exists in the configuration
        const columnExists = config.columns && config.columns.some(column => {
            const configColumnName = typeof column === 'object' ? column.name : column;
            return configColumnName === columnName;
        });
        const isRowTotalColumn = columnName === ROW_TOTAL_COLUMN_NAME
            && __configFlag(config?.show_row_totals, true);

        if (columnExists || isRowTotalColumn) {
            if (!rowInfoMap.has(rowId)) {
                rowInfoMap.set(rowId, {
                    rowId: rowId,
                    rowName: null, // Will be resolved from lookup list if needed
                    cellKeys: [],
                    values: {}
                });
            }
            rowInfoMap.get(rowId).cellKeys.push(cellKey);
            rowInfoMap.get(rowId).values[cellKey] = data[cellKey];
        }
    });

    return rowInfoMap;
}

/**
 * Resolve row IDs to names from lookup list
 */,


/**
 * Restore cell values for a row
 * Cell keys are already in standardized format (rowId_columnName)
 * Note: Variable columns are restored if variable_save_value is true, otherwise they are resolved fresh
 */
restoreRowData(fieldId, rowId, rowInfo) {
    const updatedMatrix = this.matrices.get(fieldId);
    if (!updatedMatrix) {
        debugWarn('matrix-handler', `Matrix not found for field ${fieldId} when restoring row data`);
        return;
    }

    const config = updatedMatrix.config;
    const columns = config.columns || [];

    rowInfo.cellKeys.forEach(cellKey => {
        const parsed = __parseMatrixCellKey(cellKey, config);
        if (!parsed) {
            debugWarn('matrix-handler', `Invalid cell key format: ${cellKey}`);
            return;
        }

        const { rowId: cellRowId, columnName } = parsed;
        if (cellRowId !== rowId) {
            debugWarn('matrix-handler', `Cell key row ID mismatch: expected ${rowId}, got ${cellRowId}`);
            return;
        }

        const column = columns.find(col => {
            const colName = typeof col === 'object' ? col.name : col;
            return colName === columnName;
        });

        // Check if this is a variable column (new structure: is_variable, or legacy: type === 'variable')
        const isVariable = column && typeof column === 'object' && (column.is_variable === true || column.type === 'variable');

        if (isVariable) {
            // Check if variable should be restored (variable_save_value: true)
            const variableSaveValue = column.variable_save_value !== false; // Default to true
            if (!variableSaveValue) {
                // This is a variable column that shouldn't be restored - it will be resolved fresh
                debugLog('matrix-handler', `Skipping restoration of variable column: ${cellKey} (variable_save_value=false, will be resolved fresh)`);
            // Remove from matrix data if it exists (it was saved but shouldn't be restored)
            if (updatedMatrix.data[cellKey] !== undefined) {
                delete updatedMatrix.data[cellKey];
            }
            return;
            }
            // If variable_save_value is true, continue to restore the saved value
            debugLog('matrix-handler', `Restoring variable column: ${cellKey} (variable_save_value=true)`);
        }

        const value = rowInfo.values[cellKey];

        if (value !== undefined && value !== null) {
            let displayValue = value;

            if (isVariable) {
                displayValue = __getSavedMatrixCellScalar(value);
                updatedMatrix.data[cellKey] = value;
            } else {
                updatedMatrix.data[cellKey] = value;
            }

            const input = updatedMatrix.container.querySelector(`input[data-cell-key="${cellKey}"]`);
            if (input) {
                if (input.type === 'checkbox') {
                    const checkedValue = displayValue == '1' || displayValue == 1 || displayValue === 'true' || displayValue === true;
                    input.checked = checkedValue;
                } else {
                    __setMatrixNumericCellDisplay(input, displayValue);
                }

                if (isVariable && column) {
                    const variableReadonly = typeof column === 'object' ? (column.variable_readonly !== false) : true;
                    this._applyMatrixInputEditability(input, updatedMatrix.container, variableReadonly);
                }
            } else {
                debugLog('matrix-handler', `Input not found for cell key: ${cellKey}`);
            }
        }
    });
}

/**
 * Restore cell values for static matrices (non-dynamic rows)
 */,


/**
 * Restore cell values for static matrices (non-dynamic rows)
 */
restoreStaticMatrixValues(fieldId) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix || !matrix.data) return;

    const data = matrix.data;
    const config = matrix.config;
    const columns = config.columns || [];
    const container = matrix.container;

    debugLog('matrix-handler', `Restoring static matrix values for field ${fieldId}`, data);

    // Iterate through all saved cell values
    Object.keys(data).forEach(cellKey => {
        // Skip metadata keys
        if (cellKey.startsWith('_')) {
            return;
        }

        const parsed = __parseMatrixCellKey(cellKey, config);
        if (!parsed) {
            return;
        }

        const { columnName } = parsed;
        const column = columns.find(col => {
            const colName = typeof col === 'object' ? col.name : col;
            return colName === columnName;
        });

        // Check if this is a variable column (new structure: is_variable, or legacy: type === 'variable')
        const isVariable = column && typeof column === 'object' && (column.is_variable === true || column.type === 'variable');

        if (isVariable) {
            // Check if variable should be restored (variable_save_value: true)
            const variableSaveValue = column.variable_save_value !== false; // Default to true
            if (!variableSaveValue) {
                // Skip restoration for variables that shouldn't be saved/restored
                debugLog('matrix-handler', `Skipping restoration of variable column: ${cellKey} (variable_save_value=false)`);
                return;
            }
            debugLog('matrix-handler', `Restoring variable column: ${cellKey} (variable_save_value=true)`);
        }

        const value = data[cellKey];
        if (value !== undefined && value !== null) {
            let displayValue = value;

            if (isVariable) {
                displayValue = __getSavedMatrixCellScalar(value);
                data[cellKey] = displayValue;
            }

            const input = container.querySelector(`input[data-cell-key="${cellKey}"]`);
            if (input) {
                if (input.type === 'checkbox') {
                    const checkedValue = displayValue == '1' || displayValue == 1 || displayValue === 'true' || displayValue === true;
                    input.checked = checkedValue;
                } else {
                    __setMatrixNumericCellDisplay(input, displayValue);
                }

                if (isVariable && column) {
                    const variableReadonly = typeof column === 'object' ? (column.variable_readonly !== false) : true;
                    this._applyMatrixInputEditability(input, container, variableReadonly);
                }

                debugLog('matrix-handler', `Restored value for cell ${cellKey}: ${displayValue}`);
            } else {
                debugLog('matrix-handler', `Input not found for cell key: ${cellKey}`);
            }
        }
    });

    // Recalculate totals after restoring values
    this.calculateMatrixTotals(fieldId);
    this.applyWholeNumberViolationHighlighting(fieldId);
    this.applyPrefilledCellHighlighting(fieldId);
    this._applyHeaderGatingForMatrix(fieldId);
    this._lockMatrixContainerIfReadOnly(container);

    if (matrix.hiddenField) {
        matrix.hiddenField.value = __serializeMatrixData(matrix.data);
    }
},

/**
 * Restore dynamic rows from saved data
 */
async restoreDynamicRows(fieldId) {
    // Mark that we're in a batch operation to prevent scheduled resolutions
    this.batchOperationsInProgress.add(fieldId);

    // Cancel any pending scheduled variable resolution immediately
    // We'll batch resolve all rows at the end
    if (this.variableResolutionDebounceTimers.has(fieldId)) {
        clearTimeout(this.variableResolutionDebounceTimers.get(fieldId));
        this.variableResolutionDebounceTimers.delete(fieldId);
    }
    this.pendingVariableResolution.delete(fieldId);

    const matrix = this.matrices.get(fieldId);
    if (!matrix || !matrix.data) {
        this.batchOperationsInProgress.delete(fieldId);
        return;
    }

    const data = matrix.data;
    const config = matrix.config;

    debugLog('matrix-handler', `Restoring dynamic rows for matrix ${fieldId}`, data);

    // For hybrid mode: collect static row IDs so we skip them here
    // (they're already rendered by Jinja and their cell values are filled by restoreStaticMatrixValues)
    const staticRowIds = new Set();
    if (config?.row_mode === 'hybrid' && Array.isArray(config.rows)) {
        config.rows.forEach(row => {
            const id = typeof row === 'string' ? row : (row.text || '');
            if (id) staticRowIds.add(id);
        });
    }

    // Extract row information from saved data
    const rowInfoMap = this.extractRowInfoFromData(data, config);

    // Drop static row entries — Jinja already rendered them
    staticRowIds.forEach(id => rowInfoMap.delete(id));

    debugLog('matrix-handler', `Found ${rowInfoMap.size} dynamic rows to restore:`, Array.from(rowInfoMap.keys()));

    // Resolve row IDs to names if needed
    await this.resolveRowIdsToNames(rowInfoMap, config.lookup_list_id, config.list_display_column);

    // Track which rows were auto-loaded (if auto_load_entities was enabled)
    // When restoring rows, we initially mark them as not auto-loaded.
    // If auto_load_entities is enabled, the autoLoadEntities function will later
    // mark matching rows as auto-loaded. Rows that don't match will remain as manually added.
    // This way, only rows that are truly manually added (not in the auto-load list) get highlighted.
    const isAutoLoaded = false; // Restored rows start as manually added, will be updated by autoLoadEntities if they match

    // Batch all row restoration operations
    const restorePromises = [];

    // Create rows for each unique row
    for (const [rowId, rowInfo] of rowInfoMap.entries()) {
        // rowId is now always the key (standardized)
        if (!rowInfo.rowId || rowInfo.rowId !== rowId) {
            debugWarn('matrix-handler', `Row info mismatch: key=${rowId}, rowInfo.rowId=${rowInfo.rowId}`);
            continue;
        }

        const rowName = rowInfo.rowName || rowId;
        const rowData = rowInfo.rowData || { _id: rowId, id: rowId };

        try {
            // Create the row using addDynamicRow which handles ID-based keys
            // Mark as not auto-loaded since we're restoring from saved data
            this.addDynamicRow(fieldId, rowName, rowData, rowId, isAutoLoaded);

            // Batch restore cell values (wait for DOM to be ready)
            restorePromises.push(
                new Promise(resolve => {
                    setTimeout(() => {
                        try {
                            this.restoreRowData(fieldId, rowId, rowInfo);
                        } catch (error) {
                            debugError('matrix-handler', `Error restoring row data for ${rowId}:`, error);
                        }
                        resolve();
                    }, 50);
                })
            );
        } catch (error) {
            debugError('matrix-handler', `Error adding dynamic row ${rowId}:`, error);
            // Continue with other rows even if one fails
        }
    }

    // Wait for all restorations to complete, then update hidden field and recalculate
    try {
        await Promise.all(restorePromises);
        const updatedMatrix = this.matrices.get(fieldId);
        if (updatedMatrix) {
            // Cancel any pending scheduled variable resolution (we'll batch resolve all at once)
            if (this.variableResolutionDebounceTimers.has(fieldId)) {
                clearTimeout(this.variableResolutionDebounceTimers.get(fieldId));
                this.variableResolutionDebounceTimers.delete(fieldId);
            }
            this.pendingVariableResolution.delete(fieldId);

            // Remove metadata keys before writing hidden field.
            this.sanitizeMatrixData(updatedMatrix);

            // Invalidate cache and refresh hidden field reference (DOM may have changed)
            updatedMatrix.hiddenField = updatedMatrix.container.querySelector('input[type="hidden"]');

            // Update hidden field
            if (updatedMatrix.hiddenField) {
                updatedMatrix.hiddenField.value = __serializeMatrixData(updatedMatrix.data);
            }

            // Recalculate totals after all rows are restored
            this.calculateMatrixTotals(fieldId);

            // Sort rows alphabetically after restoration
            this.sortMatrixRows(fieldId);

            // Batch resolve variables for all restored rows (optimized)
            await this.resolveVariablesForAllRows(fieldId);

            // Check for and highlight duplicates
            this.applyDuplicateEntityHighlighting(fieldId);

            this._applyGoUnmatchedRowHeadersFromData(fieldId);

            this.applyWholeNumberViolationHighlighting(fieldId);
            this.applyPrefilledCellHighlighting(fieldId);
            this._applyHeaderGatingForMatrix(fieldId);

            // Update legend visibility after restoration
            this.updateLegendVisibility(fieldId);

            this._lockMatrixContainerIfReadOnly(updatedMatrix.container);
        }
    } catch (error) {
        debugError('matrix-handler', 'Error restoring dynamic rows:', error);
    } finally {
        // Clear batch operation flag
        this.batchOperationsInProgress.delete(fieldId);
    }
},

/**
 * Highlight emergency-appeal rows imported from Excel when the code was not matched in GO.
 */
_applyGoUnmatchedRowHeadersFromData(fieldId) {
    const matrix = this.matrices.get(String(fieldId || ''));
    if (!matrix?.data || !matrix.container) return;

    Object.keys(matrix.data).forEach((key) => {
        if (!key.startsWith(ROW_GO_UNMATCHED_PREFIX)) return;
        const rowId = key.slice(ROW_GO_UNMATCHED_PREFIX.length);
        if (!rowId) return;
        const flag = matrix.data[key];
        if (!(flag === 1 || flag === '1' || flag === true)) return;

        const row = matrix.container.querySelector(`tr[data-row-id="${rowId}"]`);
        const headerCell = row?.querySelector('td[role="rowheader"]');
        if (headerCell) {
            headerCell.classList.add('matrix-go-unmatched-row-header');
            headerCell.setAttribute('title', _t('Not matched in GO API — imported from Excel'));
        }
    });
},

/**
 * Sort matrix rows alphabetically by row label
 */
sortMatrixRows(fieldId) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix || !matrix.container) {
        return;
    }

    let tbody = document.getElementById(`matrix-tbody-${fieldId}`);
    if (!tbody && matrix.container) {
        tbody = matrix.container.querySelector('tbody[id*="matrix-tbody-"]') || matrix.container.querySelector('tbody');
    }
    if (!tbody) {
        return;
    }

    // Remove any existing group header rows
    tbody.querySelectorAll('.matrix-group-header-row').forEach(h => h.remove());

    const dataRows = Array.from(tbody.querySelectorAll('tr.matrix-data-row'));
    if (dataRows.length <= 1 && !matrix.config?.group_by_column) {
        return;
    }

    const insertBefore = this._getMatrixDataRowInsertBefore(tbody);
    const groupByColumn = matrix.config?.group_by_column;
    const groupTableEnabled = matrix.config?.group_table_enabled !== false;
    const effectiveGroupByColumn = (groupByColumn && groupTableEnabled) ? groupByColumn : null;

    // Hybrid: separate pinned static rows (rendered by Jinja) from dynamic rows so static rows stay at the top.
    // We derive the static-row identity from config.rows rather than a DOM attribute so this
    // works even when data-is-static-row is absent (e.g. older cached renders or pre-migration items).
    const isHybrid = matrix.config?.row_mode === 'hybrid';
    const staticRowIds = new Set();
    if (isHybrid && Array.isArray(matrix.config.rows)) {
        matrix.config.rows.forEach(r => {
            const id = typeof r === 'string' ? r : (r.text || '');
            if (id) staticRowIds.add(id);
        });
    }
    const staticRows = isHybrid
        ? dataRows.filter(r => staticRowIds.has(r.dataset.rowId) || staticRowIds.has(r.dataset.rowLabel))
        : [];
    const sortableRows = isHybrid
        ? dataRows.filter(r => !staticRowIds.has(r.dataset.rowId) && !staticRowIds.has(r.dataset.rowLabel))
        : dataRows;

    sortableRows.sort((a, b) => {
        if (effectiveGroupByColumn) {
            const gA = (a.getAttribute('data-group') || 'zzz').toLowerCase();
            const gB = (b.getAttribute('data-group') || 'zzz').toLowerCase();
            if (gA !== gB) return gA.localeCompare(gB);
        }
        const labelA = (a.getAttribute('data-row-label') || '').toLowerCase().trim();
        const labelB = (b.getAttribute('data-row-label') || '').toLowerCase().trim();
        return labelA.localeCompare(labelB);
    });

    // Remove all sortable rows (static rows removed too so we can re-insert them at top)
    dataRows.forEach(row => row.remove());

    const colCount = matrix.config?.columns?.length || 1;
    const totalCols = colCount + 2;
    let lastGroup = null;

    // In hybrid mode, put pinned static rows back first (in their original config order)
    staticRows.forEach(row => {
        if (insertBefore) tbody.insertBefore(row, insertBefore);
        else tbody.appendChild(row);
    });

    sortableRows.forEach(row => {
        if (effectiveGroupByColumn) {
            const group = row.getAttribute('data-group') || 'Other';
            if (group !== lastGroup) {
                lastGroup = group;
                const headerRow = document.createElement('tr');
                headerRow.className = 'matrix-group-header-row bg-gray-100 cursor-pointer';
                headerRow.dataset.group = group;
                const td = document.createElement('td');
                td.colSpan = totalCols;
                td.className = 'px-3 py-2 text-xs font-semibold text-gray-700';
                td.innerHTML = `<i class="fas fa-chevron-down text-gray-400 mr-2 transition-transform duration-200"></i>${this._escapeHtml(group)}`;
                headerRow.appendChild(td);
                headerRow.addEventListener('click', () => {
                    const icon = headerRow.querySelector('i');
                    let next = headerRow.nextElementSibling;
                    while (next && next.classList.contains('matrix-data-row') && next.getAttribute('data-group') === group) {
                        next.classList.toggle('hidden');
                        next = next.nextElementSibling;
                    }
                    icon.classList.toggle('rotate-180');
                });
                if (insertBefore) tbody.insertBefore(headerRow, insertBefore);
                else tbody.appendChild(headerRow);
            }
        }
        if (insertBefore) tbody.insertBefore(row, insertBefore);
        else tbody.appendChild(row);
    });

    this._ensureTotalsRowAtTop(tbody);
    this.applyManualRowHighlighting(fieldId);
    debugLog('matrix-handler', `Sorted ${sortableRows.length} dynamic rows (+${staticRows.length} pinned) for matrix ${fieldId}${effectiveGroupByColumn ? ' with grouping by ' + effectiveGroupByColumn : ''}`);
}

/**
 * Detect and highlight duplicate entities with light red
 */,


/**
 * Detect and highlight duplicate entities with light red
 */
applyDuplicateEntityHighlighting(fieldId) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix || !matrix.container) {
        return;
    }

    // Track row IDs and their occurrences
    const rowIdCount = new Map();
    const rowIdRows = new Map();

    const dataRows = matrix.container.querySelectorAll('tr.matrix-data-row');
    dataRows.forEach(row => {
        const rowId = row.getAttribute('data-row-id');
        if (rowId) {
            const count = (rowIdCount.get(rowId) || 0) + 1;
            rowIdCount.set(rowId, count);

            if (!rowIdRows.has(rowId)) {
                rowIdRows.set(rowId, []);
            }
            rowIdRows.get(rowId).push(row);
        }
    });

    // Find duplicate row IDs (count > 1)
    const duplicateRowIds = Array.from(rowIdCount.entries())
        .filter(([rowId, count]) => count > 1)
        .map(([rowId]) => rowId);

    // Apply red highlighting to all rows with duplicate IDs
    dataRows.forEach(row => {
        const rowId = row.getAttribute('data-row-id');
        const headerCell = row.querySelector('td[role="rowheader"]');

        if (headerCell && rowId && duplicateRowIds.includes(rowId)) {
            // Apply light red background (but preserve beige if it's also manually added)
            const isManual = headerCell.classList.contains('matrix-manual-row-header');
            if (!isManual) {
                // Only apply red if not already beige (manual takes precedence visually)
                headerCell.style.backgroundColor = '#ffcccc'; // Light red
                headerCell.classList.add('matrix-duplicate-row-header');
            } else {
                // If it's both manual and duplicate, keep beige but add duplicate class for tracking
                headerCell.classList.add('matrix-duplicate-row-header');
            }
        } else if (headerCell) {
            // Remove duplicate highlighting if not a duplicate
            if (headerCell.classList.contains('matrix-duplicate-row-header') &&
                !headerCell.classList.contains('matrix-manual-row-header')) {
                headerCell.style.backgroundColor = '';
                headerCell.classList.remove('matrix-duplicate-row-header');
            } else if (headerCell.classList.contains('matrix-duplicate-row-header') &&
                       headerCell.classList.contains('matrix-manual-row-header')) {
                // Keep beige but remove duplicate class if no longer duplicate
                if (!duplicateRowIds.includes(rowId)) {
                    headerCell.classList.remove('matrix-duplicate-row-header');
                }
            }
        }
    });

    debugLog('matrix-handler', `Applied duplicate entity highlighting for matrix ${fieldId}`, {
        duplicateCount: duplicateRowIds.length,
        duplicateIds: duplicateRowIds
    });

    return duplicateRowIds.length > 0;
}

/**
 * Highlight whole-number column cells that still contain a decimal fraction.
 */,


/**
 * Apply beige highlighting to manually added row headers based on config
 */
applyManualRowHighlighting(fieldId) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix || !matrix.container || !matrix.config) {
        return;
    }

    const autoLoadEnabled = __configFlag(matrix.config.auto_load_entities, false);
    // Default to highlighting when auto-load is enabled (unless explicitly disabled)
    const highlightManualRows = __configFlag(matrix.config.highlight_manual_rows, autoLoadEnabled);
    if (!highlightManualRows) {
        // If highlighting is disabled, remove any existing highlights
        const allHeaderCells = matrix.container.querySelectorAll('tr.matrix-data-row td[role="rowheader"]');
        allHeaderCells.forEach(headerCell => {
            headerCell.style.backgroundColor = '';
            headerCell.classList.remove('matrix-manual-row-header');
            headerCell.classList.remove('matrix-duplicate-row-header');
        });
        // Hide legend if highlighting is disabled
        this.updateLegendVisibility(fieldId);
        return;
    }

    // Apply highlighting to row headers that are not auto-loaded
    const dataRows = matrix.container.querySelectorAll('tr.matrix-data-row');
    dataRows.forEach(row => {
        const headerCell = row.querySelector('td[role="rowheader"]');
        const isAutoLoaded = row.getAttribute('data-is-auto-loaded') === 'true';
        if (headerCell) {
            if (!isAutoLoaded) {
                headerCell.style.backgroundColor = '#f5f5dc'; // Beige color
                headerCell.classList.add('matrix-manual-row-header');
            } else {
                // Ensure auto-loaded rows don't have the highlight
                headerCell.style.backgroundColor = '';
                headerCell.classList.remove('matrix-manual-row-header');
            }
        }
    });

    // Also check for duplicates
    this.applyDuplicateEntityHighlighting(fieldId);

    // Update legend visibility after applying highlighting
    this.updateLegendVisibility(fieldId);

    debugLog('matrix-handler', `Applied manual row header highlighting for matrix ${fieldId} (enabled: ${highlightManualRows})`);
}

/**
 * Update legend visibility based on whether there are highlighted rows
 */,


/**
 * Update legend visibility based on whether there are highlighted rows
 */
updateLegendVisibility(fieldId) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix || !matrix.container || !matrix.config) {
        return;
    }

    const autoLoadEnabled = __configFlag(matrix.config.auto_load_entities, false);
    const highlightManualRows = __configFlag(matrix.config.highlight_manual_rows, autoLoadEnabled);
    const legendHide = __configFlag(matrix.config.legend_hide, false);

    const highlightedRows = matrix.container.querySelectorAll('tr.matrix-data-row td.matrix-manual-row-header');
    const duplicateRows = matrix.container.querySelectorAll('tr.matrix-data-row td.matrix-duplicate-row-header');
    const hasHighlightedRows = highlightedRows.length > 0;
    const hasDuplicateRows = duplicateRows.length > 0;
    const hasPrefilledCells = this._matrixHasPrefilledCellHighlights(matrix.container);
    const prefilledLegendEnabled = matrix.container.getAttribute('data-highlight-prefilled-cells') === 'true';

    const shouldShowManualLegend = highlightManualRows && !legendHide && hasHighlightedRows;
    const shouldShowDuplicateLegend = highlightManualRows && !legendHide && hasDuplicateRows;
    const shouldShowPrefilledLegend = prefilledLegendEnabled && hasPrefilledCells;
    const shouldShowLegend = shouldShowManualLegend || shouldShowDuplicateLegend || shouldShowPrefilledLegend;

    // Get or create legend element
    let legend = matrix.container.querySelector('.matrix-legend');
    if (!legend) {
        legend = document.createElement('div');
        legend.className = 'matrix-legend mb-2 p-2 bg-gray-50 border border-gray-200 rounded text-xs';
        legend.style.display = 'none';

        const table = matrix.container.querySelector('table');
        if (table) {
            table.parentNode.insertBefore(legend, table);
        } else {
            matrix.container.insertBefore(legend, matrix.container.firstChild);
        }
    }

    legend.replaceChildren();

    const legendItemsContainer = document.createElement('div');
    legendItemsContainer.className = 'flex flex-col gap-2';

    if (shouldShowPrefilledLegend) {
        const legendItem = document.createElement('div');
        legendItem.className = 'flex items-center space-x-2';

        const legendColor = document.createElement('div');
        legendColor.className = 'w-4 h-4 border border-yellow-300 rounded bg-yellow-100';
        legendColor.setAttribute('aria-label', 'Yellow highlight color for prefilled values');

        const legendTextSpan = document.createElement('span');
        legendTextSpan.className = 'text-gray-700 matrix-legend-text';
        legendTextSpan.textContent = matrix.container.getAttribute('data-prefilled-legend-text')
            || 'Prefilled value';

        legendItem.appendChild(legendColor);
        legendItem.appendChild(legendTextSpan);
        legendItemsContainer.appendChild(legendItem);
    }

    if (shouldShowManualLegend) {
        const legendItem = document.createElement('div');
        legendItem.className = 'flex items-center space-x-2';

        const legendColor = document.createElement('div');
        legendColor.className = 'w-4 h-4 border border-gray-300 rounded';
        legendColor.style.backgroundColor = '#f5f5dc';
        legendColor.setAttribute('aria-label', 'Beige highlight color');

        const legendTextSpan = document.createElement('span');
        legendTextSpan.className = 'text-gray-700 matrix-legend-text';
        let legendText = matrix.config.legend_text || 'Manually added row';

        if (matrix.config.legend_text_translations) {
            const currentLanguage = this.getCurrentLanguage();
            if (currentLanguage && matrix.config.legend_text_translations[currentLanguage]) {
                legendText = matrix.config.legend_text_translations[currentLanguage];
            }
        }
        legendTextSpan.textContent = legendText;

        legendItem.appendChild(legendColor);
        legendItem.appendChild(legendTextSpan);
        legendItemsContainer.appendChild(legendItem);
    }

    if (shouldShowDuplicateLegend) {
        const legendItem = document.createElement('div');
        legendItem.className = 'flex items-center space-x-2';

        const legendColor = document.createElement('div');
        legendColor.className = 'w-4 h-4 border border-gray-300 rounded';
        legendColor.style.backgroundColor = '#ffcccc';
        legendColor.setAttribute('aria-label', 'Red highlight color for duplicates');

        const legendTextSpan = document.createElement('span');
        legendTextSpan.className = 'text-gray-700 matrix-legend-text';
        legendTextSpan.textContent = _t('Duplicate entity');

        legendItem.appendChild(legendColor);
        legendItem.appendChild(legendTextSpan);
        legendItemsContainer.appendChild(legendItem);
    }

    legend.appendChild(legendItemsContainer);
    legend.style.display = shouldShowLegend ? 'block' : 'none';

    debugLog('matrix-handler', `Updated legend visibility for matrix ${fieldId}: ${shouldShowLegend ? 'shown' : 'hidden'}`, {
        hasHighlightedRows,
        hasDuplicateRows,
        hasPrefilledCells,
    });
}

/**
 * Get current user language from session or document
 */,
};
