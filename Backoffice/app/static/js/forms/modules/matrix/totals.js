/** Matrix row/column totals helpers and calculations. */

import { debugLog, debugError, debugWarn } from '../debug.js';
import { _t, __canEditMatrixContainer, ROW_TOTAL_COLUMN_NAME } from './shared.js';
import {
    __formatInteger,
    __integerInputValue,
    __setMatrixNumericInputValue,
    __serializeMatrixData,
    __configFlag,
    __cellValueToNumber,
    __getMatrixColumnNames,
    __parseMatrixCellKey,
} from './formatting.js';

export { ROW_TOTAL_COLUMN_NAME };

export const __ROW_TOTAL_CONFLICT_INDICATOR_BASE =
    'row-total-conflict shrink-0 flex items-center justify-center mr-1.5 pointer-events-none';

export const __ROW_TOTAL_INPUT_WRAPPER_CLASS = 'flex items-center w-full gap-1.5 px-1';

export const __ROW_TOTAL_INPUT_CLASS =
    'row-total-input flex-1 min-w-0 px-2 py-1 border-0 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-center text-sm font-medium';


export function __isRowTotalCellKey(key) {
    return typeof key === 'string' && key.endsWith(`_${ROW_TOTAL_COLUMN_NAME}`);
}


export function __rowTotalCellKey(rowId) {
    return `${rowId}_${ROW_TOTAL_COLUMN_NAME}`;
}


export function __rowTotalManualEnabled(config) {
    return __configFlag(config?.row_total_manual_enabled, false);
}


export function __rowTotalValidation(config) {
    const mode = config?.row_total_validation;
    if (mode === 'strict' || mode === 'partial') return mode;
    return 'none';
}


export function __parseRowTotalManualValue(raw) {
    if (raw == null || raw === '') return null;
    const plain = (typeof window !== 'undefined' && typeof window.__numericUnformat === 'function')
        ? window.__numericUnformat(String(raw))
        : String(raw);
    const num = Number(plain);
    return Number.isFinite(num) ? num : null;
}


export function __rowTotalConflictType(autoSum, manualVal, validation) {
    const manual = __parseRowTotalManualValue(manualVal);
    if (manual == null) return null;
    const auto = Number(autoSum) || 0;
    if (validation === 'strict' && manual !== auto) return 'error';
    if (validation === 'partial' && manual < auto) return 'error';
    if (manual !== auto) return 'warning';
    return null;
}


export function __rowTotalConflictMessage(manualVal, autoSum) {
    return `Manual total ${__formatInteger(manualVal)} differs from breakdown sum ${__formatInteger(autoSum)}`;
}


export function __rowTotalConflictIndicatorSvg(variant) {
    const colorClass = variant === 'error' ? 'text-red-400' : 'text-amber-400';
    return `<svg class="row-total-conflict-icon h-5 w-5 ${colorClass}" width="20" height="20" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg>`;
}


export function __createRowTotalConflictIndicator() {
    const indicator = document.createElement('span');
    indicator.className = `${__ROW_TOTAL_CONFLICT_INDICATOR_BASE} hidden`;
    indicator.setAttribute('aria-hidden', 'true');
    indicator.innerHTML = __rowTotalConflictIndicatorSvg('warning');
    return indicator;
}


export function __syncRowTotalConflictIndicator(indicator, conflictType, msg) {
    if (!indicator) return;
    if (conflictType) {
        indicator.className = __ROW_TOTAL_CONFLICT_INDICATOR_BASE;
        indicator.innerHTML = __rowTotalConflictIndicatorSvg(conflictType === 'error' ? 'error' : 'warning');
        indicator.removeAttribute('title');
        indicator.removeAttribute('aria-hidden');
        indicator.setAttribute('role', 'img');
        indicator.setAttribute('aria-label', msg);
    } else {
        indicator.className = `${__ROW_TOTAL_CONFLICT_INDICATOR_BASE} hidden`;
        indicator.innerHTML = __rowTotalConflictIndicatorSvg('warning');
        indicator.removeAttribute('title');
        indicator.removeAttribute('aria-label');
        indicator.removeAttribute('role');
        indicator.setAttribute('aria-hidden', 'true');
    }
}


export function __teardownRowTotalConflictTooltip(cell) {
    if (!cell) return;
    const tooltipId = cell._rowTotalTooltipId;
    if (tooltipId) {
        document.getElementById(tooltipId)?.remove();
    }
    if (cell._rowTotalTooltipHideTimeout) {
        clearTimeout(cell._rowTotalTooltipHideTimeout);
        cell._rowTotalTooltipHideTimeout = null;
    }
    const trigger = cell._rowTotalTooltipTrigger || cell;
    ['_rowTotalTooltipMouseEnter', '_rowTotalTooltipMouseMove', '_rowTotalTooltipMouseLeave'].forEach((key) => {
        const handler = trigger[key];
        if (handler) {
            trigger.removeEventListener('mouseenter', handler);
            trigger.removeEventListener('mousemove', handler);
            trigger.removeEventListener('mouseleave', handler);
            delete trigger[key];
        }
    });
    if (cell._rowTotalTooltipScrollHandler) {
        window.removeEventListener('scroll', cell._rowTotalTooltipScrollHandler, true);
        delete cell._rowTotalTooltipScrollHandler;
    }
    delete cell._rowTotalTooltipId;
    delete cell._rowTotalTooltipTrigger;
    delete cell._rowTotalInput;
    delete cell._rowTotalAutoSum;
    delete cell._rowTotalManualVal;
    delete cell._rowTotalValidation;
    delete cell._rowTotalConflictType;
    delete cell._rowTotalConflictMessage;
}


export function __applyRowTotalTooltipStyles(el) {
    el.style.cssText = `
        position: fixed;
        padding: 8px 12px;
        background-color: #333;
        color: white;
        border-radius: 4px;
        font-size: 12px;
        white-space: normal;
        z-index: 10000;
        opacity: 0;
        pointer-events: none;
        transition: opacity 0.2s;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        max-width: 280px;
    `;
}


export function __populateRowTotalConflictTooltip(tooltip, cell) {
    if (!tooltip || !cell) return;
    const input = cell._rowTotalInput;
    const autoSum = cell._rowTotalAutoSum;
    const manualVal = cell._rowTotalManualVal;
    const conflictType = cell._rowTotalConflictType;
    const cellKey = input?.getAttribute('data-cell-key') || '';
    const rowId = input?.getAttribute('data-row-id') || '';

    tooltip.replaceChildren();

    const title = document.createElement('div');
    title.style.fontWeight = 'bold';
    title.style.marginBottom = '4px';
    title.textContent = conflictType === 'error' ? _t('Total mismatch') : _t('Manual total');

    const summaryRow = document.createElement('div');
    summaryRow.style.lineHeight = '1.4';
    summaryRow.style.marginBottom = '2px';

    const manualLine = document.createElement('div');
    manualLine.textContent = `${_t('Manual total:')} ${__formatInteger(manualVal)}`;

    const breakdownLine = document.createElement('div');
    breakdownLine.textContent = `${_t('Breakdown sum:')} ${__formatInteger(autoSum)}`;

    summaryRow.append(manualLine, breakdownLine);

    const tooltipChildren = [title, summaryRow];
    const matrixContainer = input?.closest('.matrix-container');
    if (__canEditMatrixContainer(matrixContainer)) {
        const restoreRow = document.createElement('div');
        restoreRow.style.marginTop = '6px';
        restoreRow.style.paddingTop = '4px';
        restoreRow.style.borderTop = '1px solid rgba(255,255,255,0.3)';
        const restoreBtn = document.createElement('button');
        restoreBtn.type = 'button';
        restoreBtn.className = 'row-total-restore';
        restoreBtn.setAttribute('data-cell-key', cellKey);
        restoreBtn.setAttribute('data-row-id', rowId);
        restoreBtn.setAttribute('aria-label', _t('Restore to calculated'));
        restoreBtn.style.cssText = 'background:#555;color:white;border:none;border-radius:3px;padding:4px 8px;font-size:11px;cursor:pointer;display:inline-flex;align-items:center;gap:4px;';
        restoreBtn.textContent = `↩ ${_t('Restore to calculated')}`;
        restoreBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (typeof window.matrixHandler?.handleRowTotalRestore === 'function') {
                window.matrixHandler.handleRowTotalRestore(restoreBtn);
            }
            const currentTooltip = cell._rowTotalTooltipId ? document.getElementById(cell._rowTotalTooltipId) : null;
            if (currentTooltip) {
                currentTooltip.style.opacity = '0';
                currentTooltip.style.pointerEvents = 'none';
            }
        });
        restoreRow.appendChild(restoreBtn);
        tooltipChildren.push(restoreRow);
    }
    tooltip.append(...tooltipChildren);
}


export function __positionRowTotalConflictTooltip(tooltip, anchorEl) {
    if (!tooltip || !anchorEl || !anchorEl.isConnected) return;
    const anchorRect = anchorEl.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();

    let top = anchorRect.top - tooltipRect.height - 8;
    let left = anchorRect.left + (anchorRect.width / 2) - (tooltipRect.width / 2);

    if (left < 10) {
        left = 10;
    } else if (left + tooltipRect.width > window.innerWidth - 10) {
        left = window.innerWidth - tooltipRect.width - 10;
    }
    if (top < 10) {
        top = anchorRect.bottom + 8;
    }

    tooltip.style.top = `${top}px`;
    tooltip.style.left = `${left}px`;
}


export function __setupRowTotalConflictTooltip(cell, input) {
    if (!cell || !input) return;

    const cellKey = input.getAttribute('data-cell-key') || 'unknown';
    const tooltipId = `row-total-tooltip-${cellKey}`;
    cell._rowTotalTooltipId = tooltipId;
    cell._rowTotalTooltipTrigger = cell;
    cell._rowTotalInput = input;

    let tooltip = document.getElementById(tooltipId);
    if (!tooltip) {
        tooltip = document.createElement('div');
        tooltip.id = tooltipId;
        tooltip.className = 'row-total-conflict-tooltip';
        __applyRowTotalTooltipStyles(tooltip);
        if (!tooltip._rowTotalTooltipListenersAttached) {
            tooltip._rowTotalTooltipListenersAttached = true;
            tooltip._rowTotalCell = cell;
            tooltip.addEventListener('mouseenter', () => {
                if (cell._rowTotalTooltipHideTimeout) {
                    clearTimeout(cell._rowTotalTooltipHideTimeout);
                    cell._rowTotalTooltipHideTimeout = null;
                }
            });
            tooltip.addEventListener('mouseleave', () => {
                tooltip.style.opacity = '0';
                tooltip.style.pointerEvents = 'none';
            });
        }
        document.body.appendChild(tooltip);
    }

    const updateTooltip = () => {
        if (!cell.isConnected || !input.isConnected) return;
        __populateRowTotalConflictTooltip(tooltip, cell);
        __positionRowTotalConflictTooltip(tooltip, cell);
    };

    const mouseEnterHandler = () => {
        if (!cell.isConnected) return;
        if (cell._rowTotalTooltipHideTimeout) {
            clearTimeout(cell._rowTotalTooltipHideTimeout);
            cell._rowTotalTooltipHideTimeout = null;
        }
        updateTooltip();
        tooltip.style.opacity = '1';
        tooltip.style.pointerEvents = 'auto';
    };
    const mouseMoveHandler = () => {
        if (!cell.isConnected) return;
        if (tooltip.style.opacity === '1') {
            updateTooltip();
        }
    };
    const mouseLeaveHandler = () => {
        if (!cell.isConnected) return;
        if (cell._rowTotalTooltipHideTimeout) clearTimeout(cell._rowTotalTooltipHideTimeout);
        cell._rowTotalTooltipHideTimeout = setTimeout(() => {
            cell._rowTotalTooltipHideTimeout = null;
            const currentTooltip = document.getElementById(tooltipId);
            if (currentTooltip) {
                currentTooltip.style.opacity = '0';
                currentTooltip.style.pointerEvents = 'none';
            }
        }, 150);
    };

    cell._rowTotalTooltipMouseEnter = mouseEnterHandler;
    cell._rowTotalTooltipMouseMove = mouseMoveHandler;
    cell._rowTotalTooltipMouseLeave = mouseLeaveHandler;
    cell.addEventListener('mouseenter', mouseEnterHandler);
    cell.addEventListener('mousemove', mouseMoveHandler);
    cell.addEventListener('mouseleave', mouseLeaveHandler);

    const scrollHandler = () => {
        if (!cell.isConnected) {
            window.removeEventListener('scroll', scrollHandler, true);
            delete cell._rowTotalTooltipScrollHandler;
            return;
        }
        const currentTooltip = document.getElementById(tooltipId);
        if (currentTooltip && currentTooltip.style.opacity === '1') {
            updateTooltip();
        }
    };
    window.addEventListener('scroll', scrollHandler, true);
    cell._rowTotalTooltipScrollHandler = scrollHandler;
}


export function __syncRowTotalCellHighlight(cell, highlighted) {
    if (!cell) return;
    const input = cell.querySelector('.row-total-input');
    const matrixContainer = cell.closest('.matrix-container');
    const isEditableManualTotal = input && __canEditMatrixContainer(matrixContainer);

    cell.classList.toggle('bg-orange-50', !!highlighted);
    if (isEditableManualTotal) {
        cell.classList.remove('bg-gray-100');
    } else {
        cell.classList.toggle('bg-gray-100', !highlighted);
    }
}


export function __updateRowTotalConflict(input, autoSum, manualVal, validation, isManuallyModified = false) {
    if (!input) return null;
    const cell = input.closest('td') || input.parentElement;
    let indicator = cell?.querySelector('.row-total-conflict');
    if (!indicator && cell) {
        const wrapper = input.parentElement;
        if (wrapper) {
            indicator = __createRowTotalConflictIndicator();
            wrapper.appendChild(indicator);
        }
    }
    const conflictType = __rowTotalConflictType(autoSum, manualVal, validation);
    const shouldHighlight = !!isManuallyModified || !!conflictType;

    input.classList.remove('border-orange-400', 'border-red-500', 'ring-1', 'ring-orange-300', 'ring-red-300');
    __syncRowTotalCellHighlight(cell, shouldHighlight);
    cell.classList.toggle('cursor-help', !!conflictType);
    if (conflictType) {
        const msg = __rowTotalConflictMessage(manualVal, autoSum);
        __syncRowTotalConflictIndicator(indicator, conflictType, msg, input);
        cell._rowTotalAutoSum = autoSum;
        cell._rowTotalManualVal = manualVal;
        cell._rowTotalValidation = validation;
        cell._rowTotalConflictType = conflictType;
        cell._rowTotalConflictMessage = msg;
        if (!cell._rowTotalTooltipId) {
            __setupRowTotalConflictTooltip(cell, input);
        } else {
            cell._rowTotalInput = input;
            cell._rowTotalTooltipTrigger = cell;
            const tooltip = document.getElementById(cell._rowTotalTooltipId);
            if (tooltip && tooltip.style.opacity === '1') {
                __populateRowTotalConflictTooltip(tooltip, cell);
                __positionRowTotalConflictTooltip(tooltip, cell);
            }
        }
        input.classList.add(conflictType === 'error' ? 'border-red-500' : 'border-orange-400');
        input.classList.add(conflictType === 'error' ? 'ring-red-300' : 'ring-orange-300', 'ring-1');
    } else {
        cell.classList.remove('cursor-help');
        __syncRowTotalConflictIndicator(indicator, null, '', input);
        __teardownRowTotalConflictTooltip(cell);
    }
    return conflictType;
}


export function __storedRowTotalManualScalar(stored) {
    if (stored === null || stored === undefined || stored === '') return null;
    if (typeof stored === 'object') {
        if (stored.isModified && stored.modified !== '' && stored.modified != null) {
            return __parseRowTotalManualValue(stored.modified);
        }
        return null;
    }
    return __parseRowTotalManualValue(stored);
}


export function __computedRowTotalFromData(data, rowId, columns) {
    let rowTotal = 0;
    (columns || []).forEach((column) => {
        const columnName = typeof column === 'object' ? column.name : column;
        const cellKey = `${rowId}_${columnName}`;
        rowTotal += __cellValueToNumber(data[cellKey]);
    });
    return rowTotal;
}


export function __effectiveRowTotalValue(data, rowId, columns, rowTotalManual) {
    const computed = __computedRowTotalFromData(data, rowId, columns);
    if (!rowTotalManual) return computed;
    const manualScalar = __storedRowTotalManualScalar(data[__rowTotalCellKey(rowId)]);
    return manualScalar != null ? manualScalar : computed;
}

export const matrixTotalsMixin = {
/**
 * Calculate totals for a specific matrix
 */
calculateMatrixTotals(fieldId) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix) {
        debugError(`MatrixHandler: Matrix not found for field ${fieldId}`);
        return;
    }

    // Check if container is still in DOM
    if (!matrix.container.isConnected) {
        debugLog('matrix-handler', `Matrix container for ${fieldId} is no longer in DOM, cleaning up and skipping calculation`);
        this.cleanupMatrix(fieldId);
        return;
    }

    const container = matrix.container;
    const config = matrix.config;
    const data = matrix.data; // Use stored data instead of reading from DOM

    // For advanced mode, get rows from DOM; for manual mode, use config
    let rows;
    let rowIdMap = new Map(); // Map row labels to row IDs for ID-based cell keys
    if (config.row_mode === 'list_library') {
        // Get dynamic rows from DOM with both label and ID
        const rowElements = container.querySelectorAll('tr.matrix-data-row');
        rows = Array.from(rowElements).map(tr => {
            const rowLabel = tr.getAttribute('data-row-label');
            const rowId = tr.getAttribute('data-row-id');

            if (!rowId) {
                debugWarn('matrix-handler', `Row missing data-row-id attribute: ${rowLabel}`);
                // Fallback to label for backward compatibility, but log warning
                const fallbackId = rowLabel;
                if (rowLabel) {
                    rowIdMap.set(rowLabel, fallbackId);
                }
                return rowLabel || tr.querySelector('td[role="rowheader"]')?.textContent?.trim();
            }

            if (rowLabel && rowId) {
                rowIdMap.set(rowLabel, rowId);
            }
            return rowLabel || tr.querySelector('td[role="rowheader"]')?.textContent?.trim();
        }).filter(Boolean);
    } else {
        // Use static rows from config
        // For manual mode, row label IS the row ID (labels are unique within a matrix)
        // Rows may be plain strings (legacy) or {text, name_translations} objects.
        const rawRows = config.rows || [];
        rows = rawRows.map(r => (r && typeof r === 'object' ? (r.text || '') : r)).filter(Boolean);
        rows.forEach(row => {
            rowIdMap.set(row, row); // In manual mode, label = ID
        });
    }

    const columns = config.columns || [];
    const showRowTotals = config.show_row_totals !== false; // Default to true
    const showColumnTotals = config.show_column_totals !== false; // Default to true
    const rowTotalManual = __rowTotalManualEnabled(config);
    const rowTotalValidation = __rowTotalValidation(config);

    debugLog('matrix-handler', `Calculating totals for matrix ${fieldId}`, { rows, columns, showRowTotals, showColumnTotals, data });
    debugLog('matrix-handler', `Matrix data keys:`, Object.keys(data));
    debugLog('matrix-handler', `Matrix data values:`, Object.values(data));

    // Calculate row totals
    if (showRowTotals) {
        rows.forEach((row, rowIndex) => {
            let rowTotal = 0;

            // Get row ID (standardized: always use ID-based keys)
            const rowId = rowIdMap.get(row);
            if (!rowId) {
                debugWarn('matrix-handler', `No row ID found for row: ${row}, skipping total calculation`);
                return;
            }

            // Calculate row total by iterating through columns for this row
            columns.forEach((column, colIndex) => {
                const columnName = typeof column === 'object' ? column.name : column;
                const columnType = typeof column === 'object' ? column.type : 'number';
                // Always use ID-based cell key: rowId_columnName
                const cellKey = `${rowId}_${columnName}`;
                const rawValue = data[cellKey];
                const value = __cellValueToNumber(rawValue);

                if (columnType === 'tick') {
                    // For tick columns, count checked items (1) as 1, unchecked (0) as 0
                    rowTotal += value;
                } else {
                    // For number columns, sum the values
                    rowTotal += value;
                }

                debugLog('matrix-handler', `Row ${rowIndex}, Col ${colIndex} (${columnType}) = ${value}, running row total = ${rowTotal}`);
                debugLog('matrix-handler', `Looking for cellKey: "${cellKey}", found value: ${value}`);
            });

            // Find row total element by row ID (standardized)
            const totalCellKey = __rowTotalCellKey(rowId);
            if (rowTotalManual) {
                const stored = data[totalCellKey];
                const manualScalar = __storedRowTotalManualScalar(stored);
                const displayVal = manualScalar != null ? manualScalar : rowTotal;

                const totalInput = container.querySelector(`input.row-total-input[data-cell-key="${totalCellKey}"]`);
                if (totalInput) {
                    __setMatrixNumericInputValue(
                        totalInput,
                        displayVal !== '' && displayVal != null ? displayVal : ''
                    );
                    totalInput.setAttribute('data-original-value', String(rowTotal));
                    const isConflict = manualScalar != null && manualScalar !== rowTotal;
                    __updateRowTotalConflict(
                        totalInput,
                        rowTotal,
                        isConflict ? manualScalar : '',
                        rowTotalValidation,
                        isConflict
                    );
                }
            } else {
                const totalElement = container.querySelector(`.matrix-row-total[data-row-id="${rowId}"]`);
                debugLog('matrix-handler', `Looking for row total element with selector: .matrix-row-total[data-row-id="${rowId}"]`);
                debugLog('matrix-handler', `Found element:`, totalElement);
                if (totalElement) {
                    const newValue = __formatInteger(rowTotal);
                    totalElement.textContent = newValue;
                    totalElement.style.display = 'block';
                    totalElement.style.visibility = 'visible';

                    // Announce to screen readers
                    this.announceTotalUpdate(fieldId, 'row', newValue, row);

                    debugLog('matrix-handler', `Set row total for ${row} (ID: ${rowId}) = ${rowTotal}`);
                } else {
                    debugLog('matrix-handler', `Row total element not found for ${row} (ID: ${rowId})`);
                }
            }
        });
    }

    // Calculate column totals (optimized: build column map once)
    if (showColumnTotals) {
        // Build a map of column values for efficient lookup
        const columnValuesMap = new Map();
        Object.keys(data).forEach((key) => {
            // Skip metadata fields and persisted row-total cells (avoid double-counting)
            if (key.startsWith('_') || __isRowTotalCellKey(key)) {
                return;
            }

            const parsed = __parseMatrixCellKey(key, config);
            if (!parsed) return;

            const { columnName } = parsed;
            const value = data[key] || 0;

            if (!columnValuesMap.has(columnName)) {
                columnValuesMap.set(columnName, []);
            }
            columnValuesMap.get(columnName).push(value);
        });

        columns.forEach((column, colIndex) => {
            const columnName = typeof column === 'object' ? column.name : column;
            const columnType = typeof column === 'object' ? column.type : 'number';
            let columnTotal = 0;

            // Sum values from the pre-built map (use numeric coercion for variable column objects)
            const values = columnValuesMap.get(columnName) || [];
            values.forEach((rawValue) => {
                const value = __cellValueToNumber(rawValue);
                if (columnType === 'tick') {
                    // For tick columns, count checked items (1) as 1, unchecked (0) as 0
                    columnTotal += value;
                } else {
                    // For number columns, sum the values
                    columnTotal += value;
                }
            });

            // Ensure we're searching within the correct matrix container
            const totalElement = container.querySelector(`.matrix-column-total[data-column="${columnName}"]`);
            debugLog('matrix-handler', `Looking for column total element with selector: .matrix-column-total[data-column="${columnName}"] in container for field ${fieldId}`);
            debugLog('matrix-handler', `Container:`, container);
            debugLog('matrix-handler', `Found element:`, totalElement);
            if (totalElement) {
                debugLog('matrix-handler', `Element parent:`, totalElement.parentElement);
                debugLog('matrix-handler', `Element current text:`, totalElement.textContent);
            }
            if (totalElement) {
                const newValue = __formatInteger(columnTotal);
                totalElement.textContent = newValue;
                totalElement.style.display = 'block';
                totalElement.style.visibility = 'visible';

                // Announce to screen readers
                this.announceTotalUpdate(fieldId, 'column', newValue, this.getColumnDisplayName(column));

                debugLog('matrix-handler', `Set column total for ${column} = ${columnTotal} (formatted: ${newValue})`);
            } else {
                debugLog('matrix-handler', `Column total element not found for ${column}`);
            }
        });
    }

    // Calculate grand total (only if both row and column totals are shown)
    if (showRowTotals && showColumnTotals) {
        let grandTotal = 0;
        if (rowTotalManual) {
            // Manual row totals may differ from column sums — grand total = sum of effective row totals.
            rows.forEach((row) => {
                const rowId = rowIdMap.get(row);
                if (!rowId) return;
                grandTotal += __effectiveRowTotalValue(data, rowId, columns, true);
            });
        } else {
            Object.entries(data).forEach(([key, value]) => {
                if (key.startsWith('_') || __isRowTotalCellKey(key)) {
                    return;
                }
                grandTotal += __cellValueToNumber(value);
            });
        }

        const grandTotalElement = container.querySelector('.matrix-grand-total');
        if (grandTotalElement) {
            const newValue = __formatInteger(grandTotal);
            grandTotalElement.textContent = newValue;
            grandTotalElement.style.display = 'block';
            grandTotalElement.style.visibility = 'visible';

            // Announce to screen readers
            this.announceTotalUpdate(fieldId, 'grand', grandTotal.toFixed(0), '');

            debugLog(`MatrixHandler: Set grand total = ${grandTotal}`);
        } else {
            debugLog(`MatrixHandler: Grand total element not found`);
        }
    }

    debugLog(`MatrixHandler: Completed totals calculation for matrix ${fieldId}`);
},



/**
 * Calculate totals for all matrices
 */
calculateAllMatrices() {
    this.matrices.forEach((matrix, fieldId) => {
        this.calculateMatrixTotals(fieldId);
    });
},

/**
 * Clear matrix totals
 */
clearMatrixTotals(fieldId) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix) return;

    const container = matrix.container;

    // Clear row totals
    const rowTotals = container.querySelectorAll('.matrix-row-total');
    rowTotals.forEach(total => {
        total.textContent = '0';
    });

    // Clear column totals
    const columnTotals = container.querySelectorAll('.matrix-column-total');
    columnTotals.forEach(total => {
        total.textContent = '0';
    });

    // Clear grand total
    const grandTotal = container.querySelector('.matrix-grand-total');
    if (grandTotal) {
        grandTotal.textContent = '0';
    }
},

/**
 * Restore a manual row total to the auto-calculated breakdown sum.
 */
handleRowTotalRestore(button) {
    const cellKey = button.getAttribute('data-cell-key');
    if (!cellKey) return;

    let container = button.closest('.matrix-container');
    if (container && !this._canEditMatrix(container)) return;
    let input = container?.querySelector(`input.row-total-input[data-cell-key="${cellKey}"]`);
    if (!input) {
        input = document.querySelector(`input.row-total-input[data-cell-key="${cellKey}"]`);
        container = input?.closest('.matrix-container');
    }
    const fieldId = container?.dataset?.fieldId;
    if (!fieldId || !input) return;

    const matrix = this.matrices.get(fieldId);
    if (!matrix) return;

    const autoSum = parseFloat(input.getAttribute('data-original-value')) || 0;
    __setMatrixNumericInputValue(input, autoSum || '');
    delete matrix.data[cellKey];
    __updateRowTotalConflict(input, autoSum, '', __rowTotalValidation(matrix.config), false);
    if (matrix.hiddenField) {
        matrix.hiddenField.value = __serializeMatrixData(matrix.data);
    }
},

/**
 * Announce total updates to screen readers
 */
announceTotalUpdate(fieldId, type, value, context) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix) return;

    const container = matrix.container;
    const announceElement = container.querySelector('#matrix-totals-announce-' + fieldId);
    if (announceElement) {
        let message = '';
        switch (type) {
            case 'row':
                message = `Row ${context} total: ${value}`;
                break;
            case 'column':
                message = `Column ${context} total: ${value}`;
                break;
            case 'grand':
                message = `Matrix grand total: ${value}`;
                break;
        }
        announceElement.textContent = message;
    }
},

/**
 * Return the column-totals row in a matrix tbody, if present.
 * @param {HTMLTableSectionElement} tbody
 * @returns {HTMLTableRowElement|null}
 */
_getMatrixTotalsRow(tbody) {
    if (!tbody) return null;
    return tbody.querySelector('.matrix-column-totals-row')
        || tbody.querySelector('tr .matrix-column-total')?.closest('tr')
        || null;
},

/**
 * Keep the column-totals row as the first row in tbody (below thead).
 * @param {HTMLTableSectionElement} tbody
 */
_ensureTotalsRowAtTop(tbody) {
    const totalsRow = this._getMatrixTotalsRow(tbody);
    if (totalsRow && tbody.firstElementChild !== totalsRow) {
        tbody.insertBefore(totalsRow, tbody.firstElementChild);
    }
},

/**
 * Where new data/group rows should be inserted: before the add-row search bar, or append.
 * @param {HTMLTableSectionElement} tbody
 * @returns {HTMLElement|null} insertBefore target, or null to appendChild
 */
_getMatrixDataRowInsertBefore(tbody) {
    if (!tbody) return null;
    return tbody.querySelector('.matrix-add-row-interface');
}
};
