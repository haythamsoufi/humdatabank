/** Variable column lookup comparison, tooltips, and modification indicators. */
import { debugLog } from '../debug.js';
import { _t } from './shared.js';
import {
    __formatLookupValueForInput,
    __formatNumberForDisplay,
    __getSavedMatrixCellScalar,
    __persistVariableCellScalar,
    __readMatrixMaxDecimals,
    __resolveMatrixLocalizedLabel,
    __serializeMatrixData,
    __setMatrixNumericCellDisplay,
    __variableCellDiffersFromLookup,
} from './formatting.js';
import { __inputValueForMatrixCompare } from './carry-forward.js';

export const matrixVariablesMixin = {

/**
 * Resolve customizable tooltip labels for variable lookup comparison.
 */
getVariableTooltipLabels(config) {
    return {
        lookupLabel: __resolveMatrixLocalizedLabel(
            config,
            'variable_lookup_tooltip_label',
            'variable_lookup_tooltip_label_translations',
            _t('Lookup value')
        ),
        submittedLabel: __resolveMatrixLocalizedLabel(
            config,
            'variable_submitted_tooltip_label',
            'variable_submitted_tooltip_label_translations',
            _t('Submitted value')
        ),
    };
},


applyVariableLookupComparison(fieldId) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix?.container) return;
    const labels = this.getVariableTooltipLabels(matrix.config);
    matrix.container.querySelectorAll('input[data-column-type="variable"]').forEach((input) => {
        if (input.getAttribute('data-variable-save-value') !== 'true') {
            this.updateVariableModificationIndicator(input, '', '', labels);
            return;
        }
        const cellKey = input.getAttribute('data-cell-key');
        const lookupValue = input.getAttribute('data-lookup-value')
            ?? (cellKey && matrix.lookupRefs ? matrix.lookupRefs[cellKey] : '')
            ?? '';
        const savedScalar = cellKey && matrix.data && matrix.data[cellKey] !== undefined
            ? __getSavedMatrixCellScalar(matrix.data[cellKey])
            : __inputValueForMatrixCompare(input);
        this.updateVariableModificationIndicator(input, lookupValue, savedScalar, labels);
    });
},


applyVariableLookupComparisonForInput(fieldId, input) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix || !input) return;
    const labels = this.getVariableTooltipLabels(matrix.config);
    if (input.getAttribute('data-variable-save-value') !== 'true') {
        this.updateVariableModificationIndicator(input, '', '', labels);
        return;
    }
    const cellKey = input.getAttribute('data-cell-key');
    const lookupValue = input.getAttribute('data-lookup-value')
        ?? (cellKey && matrix.lookupRefs ? matrix.lookupRefs[cellKey] : '')
        ?? '';
    const savedScalar = cellKey && matrix.data && matrix.data[cellKey] !== undefined
        ? __getSavedMatrixCellScalar(matrix.data[cellKey])
        : __inputValueForMatrixCompare(input);
    this.updateVariableModificationIndicator(input, lookupValue, savedScalar, labels);
}

/**
 * Update visual indicator for modified variable fields
 */,


/**
 * Update visual indicator for modified variable fields
 */
updateVariableModificationIndicator(input, lookupValue, savedValue, labels = null) {
    if (!input) return;

    const container = input.closest('.matrix-container');
    const fieldId = container?.dataset?.fieldId;
    const matrix = fieldId ? this.matrices.get(fieldId) : null;
    const resolvedLabels = labels || this.getVariableTooltipLabels(matrix?.config || {});
    const isModified = __variableCellDiffersFromLookup(
        lookupValue,
        savedValue,
        input.type,
        __readMatrixMaxDecimals(input)
    );

    // Find the parent cell (td) to attach tooltip to
    const cell = input.closest('td');
    if (!cell) return;

    // Remove existing tooltip if any (from body)
    const existingTooltipId = `variable-tooltip-${input.getAttribute('data-cell-key')}`;
    const existingTooltip = document.getElementById(existingTooltipId);
    if (existingTooltip) {
        existingTooltip.remove();
    }

    // Remove existing event listeners (store them first if needed)
    const existingMouseEnter = cell._variableTooltipMouseEnter;
    const existingMouseLeave = cell._variableTooltipMouseLeave;
    const existingMouseMove = cell._variableTooltipMouseMove;
    if (existingMouseEnter) {
        cell.removeEventListener('mouseenter', existingMouseEnter);
    }
    if (existingMouseLeave) {
        cell.removeEventListener('mouseleave', existingMouseLeave);
    }
    if (existingMouseMove) {
        cell.removeEventListener('mousemove', existingMouseMove);
    }

    if (isModified) {
        // Check if this is a checkbox (tick column)
        const isCheckbox = input.type === 'checkbox';
        // Check if checkbox is editable (not readonly)
        const isEditable = !input.disabled && input.getAttribute('data-variable-readonly') !== 'true';

        if (isCheckbox && isEditable) {
            // For editable checkboxes: full opacity and orange color
            input.style.setProperty('opacity', '1', 'important');
            input.style.setProperty('accent-color', '#ff9800', 'important'); // Orange color
            // Remove any opacity classes that might be applied
            input.classList.remove('opacity-50', 'opacity-75');
            input.classList.add('variable-modified', 'variable-modified-checkbox');

            // Style the cell (td) background so the highlight fills the full cell height
            if (cell) {
                cell.style.setProperty('background-color', '#fff3e0', 'important'); // Light orange background
            }

            debugLog('matrix-handler', `Applying orange styling to modified editable variable checkbox: ${input.getAttribute('data-cell-key')}, lookup="${lookupValue}", saved="${savedValue}"`);
        } else if (isCheckbox && !isEditable) {
            // For readonly checkboxes: apply green to the cell (td) so it fills the full height
            if (cell) {
                cell.style.setProperty('background-color', '#d4edda', 'important');
            }
            input.classList.add('variable-modified');

            debugLog('matrix-handler', `Applying green highlight to modified readonly variable checkbox: ${input.getAttribute('data-cell-key')}, lookup="${lookupValue}", saved="${savedValue}"`);
        } else {
            // For number inputs: apply green to the cell (td) so it fills the full height,
            // and make the input itself transparent so the cell colour shows through.
            if (cell) {
                cell.style.setProperty('background-color', '#d4edda', 'important');
            }
            input.style.setProperty('background-color', 'transparent', 'important');
            input.classList.add('variable-modified');

            debugLog('matrix-handler', `Applying green highlight to modified variable cell: ${input.getAttribute('data-cell-key')}, lookup="${lookupValue}", saved="${savedValue}"`);
        }

        cell._variableLookupValue = lookupValue;
        cell._variableSubmittedValue = savedValue;
        cell._variableInput = input;

        // Create or get tooltip element - keep it in DOM for reuse
        let tooltip = document.getElementById(existingTooltipId);
        const applyTooltipStyles = (el) => {
            el.style.cssText = `
                position: fixed;
                padding: 8px 12px;
                background-color: #333;
                color: white;
                border-radius: 4px;
                font-size: 12px;
                white-space: nowrap;
                z-index: 10000;
                opacity: 0;
                pointer-events: none;
                transition: opacity 0.2s;
                box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            `;
        };
        const attachTooltipHoverListeners = (tipEl) => {
            if (tipEl._variableTooltipListenersAttached) return;
            tipEl._variableTooltipListenersAttached = true;
            tipEl._variableCell = cell;
            tipEl.addEventListener('mouseenter', () => {
                if (cell._variableTooltipHideTimeout) {
                    clearTimeout(cell._variableTooltipHideTimeout);
                    cell._variableTooltipHideTimeout = null;
                }
            });
            tipEl.addEventListener('mouseleave', () => {
                const t = document.getElementById(existingTooltipId);
                if (t) {
                    t.style.opacity = '0';
                    t.style.pointerEvents = 'none';
                }
            });
        };
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = existingTooltipId;
            tooltip.className = 'variable-modification-tooltip';
            applyTooltipStyles(tooltip);
            attachTooltipHoverListeners(tooltip);
            document.body.appendChild(tooltip);
        }

        // Update tooltip content and position function
        const updateTooltip = () => {
            // Check if cell and input still exist
            if (!cell.isConnected || !input.isConnected) {
                return;
            }
            const currentInput = cell._variableInput || input;
            if (!currentInput) {
                return;
            }
            const currentLookupValue = cell._variableLookupValue !== undefined ? cell._variableLookupValue : lookupValue;
            const currentSavedValue = cell._variableSubmittedValue !== undefined
                ? cell._variableSubmittedValue
                : (currentInput.type === 'checkbox'
                    ? (currentInput.checked ? '1' : '0')
                    : __inputValueForMatrixCompare(currentInput));

            if (tooltip) {
                tooltip.replaceChildren();
                const title = document.createElement('div');
                title.style.fontWeight = 'bold';
                title.style.marginBottom = '4px';
                title.textContent = _t('Modified value');

                const lookupRow = document.createElement('div');
                lookupRow.appendChild(document.createTextNode(`${resolvedLabels.lookupLabel}: `));
                const lookupText =
                    (currentLookupValue !== null && currentLookupValue !== undefined && currentLookupValue !== '')
                        ? (__formatNumberForDisplay(currentLookupValue) ?? String(currentLookupValue))
                        : _t('(empty)');
                lookupRow.appendChild(document.createTextNode(lookupText));

                const submittedRow = document.createElement('div');
                submittedRow.appendChild(document.createTextNode(`${resolvedLabels.submittedLabel}: `));
                submittedRow.appendChild(document.createTextNode(
                    String(currentSavedValue !== null && currentSavedValue !== undefined && currentSavedValue !== ''
                        ? (__formatNumberForDisplay(currentSavedValue) ?? String(currentSavedValue))
                        : _t('(empty)'))
                ));

                const tooltipChildren = [title, lookupRow, submittedRow];
                if (this._canEditMatrix(container)) {
                    const restoreRow = document.createElement('div');
                    restoreRow.style.marginTop = '6px';
                    restoreRow.style.paddingTop = '4px';
                    restoreRow.style.borderTop = '1px solid rgba(255,255,255,0.3)';
                    const restoreBtn = document.createElement('button');
                    restoreBtn.type = 'button';
                    restoreBtn.setAttribute('aria-label', `Restore ${resolvedLabels.lookupLabel.toLowerCase()}`);
                    restoreBtn.style.cssText = 'background:#555;color:white;border:none;border-radius:3px;padding:4px 8px;font-size:11px;cursor:pointer;display:inline-flex;align-items:center;gap:4px;';
                    restoreBtn.innerHTML = `↩ Restore ${resolvedLabels.lookupLabel.toLowerCase()}`;
                    restoreBtn.addEventListener('click', (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        const inp = cell._variableInput;
                        const lookup = cell._variableLookupValue;
                        if (!inp || !inp.isConnected) return;
                        const matrixContainer = inp.closest('.matrix-container') || inp.closest('[data-field-id]');
                        const restoreFieldId = matrixContainer ? (matrixContainer.getAttribute('data-field-id') || '') : '';
                        const cellKey = inp.getAttribute('data-cell-key');
                        const restoreMatrix = restoreFieldId ? this.matrices.get(restoreFieldId) : null;
                        const restoredDisplay = __formatLookupValueForInput(inp.type, lookup);
                        if (inp.type === 'checkbox') {
                            inp.checked = restoredDisplay === '1';
                        } else {
                            __setMatrixNumericCellDisplay(inp, restoredDisplay);
                        }
                        if (restoreMatrix && cellKey) {
                            restoreMatrix.data[cellKey] = inp.type === 'checkbox'
                                ? restoredDisplay
                                : __persistVariableCellScalar(
                                    restoredDisplay,
                                    __readMatrixMaxDecimals(inp)
                                );
                            this.sanitizeMatrixData(restoreMatrix);
                            if (restoreMatrix.hiddenField) {
                                restoreMatrix.hiddenField.value = __serializeMatrixData(restoreMatrix.data);
                            }
                        }
                        this.updateVariableModificationIndicator(inp, lookup, restoredDisplay, resolvedLabels);
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                    });
                    restoreRow.appendChild(restoreBtn);
                    tooltipChildren.push(restoreRow);
                }
                tooltip.append(...tooltipChildren);

                // Calculate position based on cell's bounding box
                const cellRect = cell.getBoundingClientRect();
                const tooltipRect = tooltip.getBoundingClientRect();

                // Position above the cell, centered horizontally
                let top = cellRect.top - tooltipRect.height - 5;
                let left = cellRect.left + (cellRect.width / 2) - (tooltipRect.width / 2);

                // Adjust if tooltip would go off screen
                if (left < 10) {
                    left = 10;
                } else if (left + tooltipRect.width > window.innerWidth - 10) {
                    left = window.innerWidth - tooltipRect.width - 10;
                }

                // If tooltip would go above viewport, show below instead
                if (top < 10) {
                    top = cellRect.bottom + 5;
                }

                tooltip.style.top = `${top}px`;
                tooltip.style.left = `${left}px`;
            }
        };

        // Create event handlers
        const mouseEnterHandler = () => {
            if (!cell.isConnected) return;
            if (cell._variableTooltipHideTimeout) {
                clearTimeout(cell._variableTooltipHideTimeout);
                cell._variableTooltipHideTimeout = null;
            }
            // Ensure tooltip exists in DOM (in case it was removed)
            if (!document.getElementById(existingTooltipId)) {
                const newTooltip = document.createElement('div');
                newTooltip.id = existingTooltipId;
                newTooltip.className = 'variable-modification-tooltip';
                applyTooltipStyles(newTooltip);
                attachTooltipHoverListeners(newTooltip);
                document.body.appendChild(newTooltip);
                tooltip = newTooltip;
            } else {
                tooltip = document.getElementById(existingTooltipId);
            }
            if (tooltip) {
                updateTooltip(); // Calculate position and update content
                tooltip.style.opacity = '1';
                tooltip.style.pointerEvents = 'auto';
            }
        };
        const mouseMoveHandler = () => {
            // Check if cell still exists
            if (!cell.isConnected) {
                return;
            }
            // Update position on mouse move in case of scrolling
            const currentTooltip = document.getElementById(existingTooltipId);
            if (currentTooltip && currentTooltip.style.opacity === '1') {
                tooltip = currentTooltip;
                updateTooltip();
            }
        };
        const mouseLeaveHandler = () => {
            if (!cell.isConnected) return;
            if (cell._variableTooltipHideTimeout) clearTimeout(cell._variableTooltipHideTimeout);
            // Delay hide so moving cursor to tooltip keeps it visible
            cell._variableTooltipHideTimeout = setTimeout(() => {
                cell._variableTooltipHideTimeout = null;
                const currentTooltip = document.getElementById(existingTooltipId);
                if (currentTooltip) {
                    currentTooltip.style.opacity = '0';
                    currentTooltip.style.pointerEvents = 'none';
                }
            }, 150);
        };

        // Store handlers for cleanup
        cell._variableTooltipMouseEnter = mouseEnterHandler;
        cell._variableTooltipMouseMove = mouseMoveHandler;
        cell._variableTooltipMouseLeave = mouseLeaveHandler;

        // Show tooltip on hover
        cell.addEventListener('mouseenter', mouseEnterHandler);
        cell.addEventListener('mousemove', mouseMoveHandler);
        cell.addEventListener('mouseleave', mouseLeaveHandler);

        // Also handle scroll to update position
        const scrollHandler = () => {
            // Check if cell and tooltip still exist before updating
            if (!cell.isConnected) {
                // Cell was removed, clean up
                window.removeEventListener('scroll', scrollHandler, true);
                delete cell._variableTooltipScrollHandler;
                return;
            }
            const currentTooltip = document.getElementById(existingTooltipId);
            if (currentTooltip && currentTooltip.style.opacity === '1') {
                updateTooltip();
            }
        };
        window.addEventListener('scroll', scrollHandler, true);
        cell._variableTooltipScrollHandler = scrollHandler;
    } else {
        // Remove modification styling
        const isCheckbox = input.type === 'checkbox';

        if (isCheckbox) {
            // Remove checkbox-specific styling
            input.style.removeProperty('opacity');
            input.style.removeProperty('accent-color');
            input.classList.remove('variable-modified', 'variable-modified-checkbox');

            // Remove cell background styling
            if (cell) {
                cell.style.removeProperty('background-color');
            }
        } else {
            // Remove number input styling — background lives on the cell (td), not the input
            input.style.removeProperty('background-color');
            input.classList.remove('variable-modified');
            if (cell) {
                cell.style.removeProperty('background-color');
            }
        }

        // Remove tooltip if it exists
        const tooltipToRemove = document.getElementById(existingTooltipId);
        if (tooltipToRemove) {
            tooltipToRemove.remove();
        }

        // Remove scroll handler if exists
        const scrollHandler = cell._variableTooltipScrollHandler;
        if (scrollHandler) {
            window.removeEventListener('scroll', scrollHandler, true);
            delete cell._variableTooltipScrollHandler;
        }

        // Clean up stored references
        delete cell._variableOriginalValue;
        delete cell._variableInput;
    }
}

/**
 * Escape HTML for tooltip display
 */,


/**
 * Escape HTML for tooltip display
 */
escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Restore cell values for a row
 * Cell keys are already in standardized format (rowId_columnName)
 * Note: Variable columns are restored if variable_save_value is true, otherwise they are resolved fresh
 */,
};
