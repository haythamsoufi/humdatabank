/** Matrix validation helpers. */

import { _t } from './shared.js';
import { __readMatrixMaxDecimals, __rawValueHasNonZeroFraction, __syncWholeNumberViolationHighlight } from './formatting.js';
import { __rowTotalManualEnabled, __rowTotalValidation, __updateRowTotalConflict, __storedRowTotalManualScalar } from './totals.js';

export const matrixValidationMixin = {
/**
 * Return the first validation message for a matrix cell, or null if valid.
 */
getMatrixInputValidationMessage(input) {
    if (!input || input.type === 'checkbox') return null;
    if (input.getAttribute('data-is-row-total') === 'true') return null;

    const container = input.closest('.matrix-container');
    const fieldId = container?.dataset?.fieldId;
    if (!fieldId || !this.matrices.get(fieldId)) return null;

    const value = parseFloat(
        window.__numericUnformat
            ? window.__numericUnformat(input.value, __readMatrixMaxDecimals(input))
            : input.value
    );
    const errors = [];

    if (input.value && isNaN(value)) {
        errors.push(_t('Please enter a valid number'));
    }
    if (!isNaN(value) && value < 0) {
        errors.push(_t('Value cannot be negative'));
    }

    const maxDecimals = __readMatrixMaxDecimals(input);
    if (maxDecimals === 0 && input.value && __rawValueHasNonZeroFraction(input.value, maxDecimals)) {
        errors.push(_t('This column requires a whole number. Please correct the decimal value.'));
    }

    return errors[0] || null;
},


buildMatrixValidationError(input, message, type = 'matrix_cell') {
    const matrixContainer = input?.closest?.('.matrix-container');
    const formItemBlock = matrixContainer?.closest('.form-item-block');
    const fieldId = matrixContainer?.dataset?.fieldId;

    let matrixLabel = '';
    if (fieldId) {
        const labelEl = document.getElementById(`field-${fieldId}`);
        if (labelEl) matrixLabel = labelEl.textContent.replace(/\*/g, '').trim();
    }
    if (!matrixLabel && formItemBlock) {
        const labelEl = formItemBlock.querySelector('label');
        if (labelEl) matrixLabel = labelEl.textContent.replace(/\*/g, '').trim();
    }

    const rowLabel = input.getAttribute('data-row') || input.getAttribute('data-row-id') || '';
    const columnLabel = input.getAttribute('data-column') || '';

    let fullMessage = message;
    const locationParts = [];
    if (matrixLabel) locationParts.push(matrixLabel);
    if (rowLabel && columnLabel) locationParts.push(`${rowLabel} / ${columnLabel}`);
    else if (columnLabel) locationParts.push(columnLabel);
    if (locationParts.length) {
        fullMessage = `${locationParts.join(' — ')}: ${message}`;
    }

    return {
        field: input,
        container: formItemBlock || matrixContainer || input,
        message: fullMessage,
        type,
    };
},

/**
 * Collect matrix validation errors for the form-level error summary.
 */
collectMatrixValidationErrors() {
    const errors = [];

    this.matrices.forEach((matrix, fieldId) => {
        if (!matrix.container.isConnected) {
            this.cleanupMatrix(fieldId);
            return;
        }

        const container = matrix.container;
        const formItemBlock = container.closest('.form-item-block');
        const inputs = container.querySelectorAll('input[type="number"], input[data-numeric="true"]');

        inputs.forEach((input) => {
            const message = this.getMatrixInputValidationMessage(input);
            if (message) {
                errors.push(this.buildMatrixValidationError(input, message));
                this.showInputError(input, message);
            } else {
                this.clearInputError(input);
            }
        });

        if (matrix.config.is_required) {
            const hasData = this.hasMatrixData(fieldId);
            if (!hasData) {
                const msg = _t('This field is required. Please enter at least one value.');
                this.showMatrixError(fieldId, msg);
                const fallbackField = container.querySelector('input[data-cell-key]') || container;
                let matrixLabel = '';
                const labelEl = fieldId ? document.getElementById(`field-${fieldId}`) : null;
                if (labelEl) matrixLabel = labelEl.textContent.replace(/\*/g, '').trim();
                errors.push({
                    field: fallbackField,
                    container: formItemBlock || container,
                    message: matrixLabel ? `${matrixLabel}: ${msg}` : msg,
                    type: 'matrix_required',
                });
            } else {
                this.clearMatrixError(fieldId);
            }
        } else {
            this.clearMatrixError(fieldId);
        }

        if (__rowTotalManualEnabled(matrix.config) && !this.validateRowTotalConflictsForMatrix(fieldId)) {
            const validation = __rowTotalValidation(matrix.config);
            const msg = validation === 'partial'
                ? _t('One or more manual row totals are lower than the breakdown sum.')
                : _t('One or more row totals do not match their breakdown sums. Correct the totals or use “Restore to calculated”.');
            const fallbackField = container.querySelector('input.row-total-input')
                || container.querySelector('input[data-cell-key]')
                || container;
            let matrixLabel = '';
            const labelEl = fieldId ? document.getElementById(`field-${fieldId}`) : null;
            if (labelEl) matrixLabel = labelEl.textContent.replace(/\*/g, '').trim();
            errors.push({
                field: fallbackField,
                container: formItemBlock || container,
                message: matrixLabel ? `${matrixLabel}: ${msg}` : msg,
                type: 'matrix_row_total',
            });
        }
    });

    return errors;
},

/**
 * Validate a single matrix input
 */
validateMatrixInput(input) {
    const message = this.getMatrixInputValidationMessage(input);
    if (message) {
        this.showInputError(input, message);
        return false;
    }
    this.clearInputError(input);
    return true;
},

/**
 * Validate all matrices
 */
validateAllMatrices() {
    return this.collectMatrixValidationErrors().length === 0;
},

/**
 * Validate row-total conflicts for a single matrix field.
 */
validateRowTotalConflictsForMatrix(fieldId) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix || !matrix.container.isConnected) return true;
    if (!__rowTotalManualEnabled(matrix.config)) return true;

    const validation = __rowTotalValidation(matrix.config);
    const inputs = matrix.container.querySelectorAll('input.row-total-input');
    let matrixValid = true;

    inputs.forEach((input) => {
        const autoSum = parseFloat(input.getAttribute('data-original-value')) || 0;
        const stored = matrix.data[input.dataset.cellKey];
        const manualScalar = __storedRowTotalManualScalar(stored);
        const manualVal = manualScalar != null ? manualScalar : autoSum;
        const isManuallyModified = manualScalar != null && manualScalar !== autoSum;
        const conflictType = __updateRowTotalConflict(input, autoSum, isManuallyModified ? manualVal : '', validation, isManuallyModified);
        if (conflictType === 'error') {
            matrixValid = false;
        }
    });

    if (!matrixValid) {
        const msg = validation === 'partial'
            ? _t('One or more manual row totals are lower than the breakdown sum.')
            : _t('One or more row totals do not match their breakdown sums. Correct the totals or use “Restore to calculated”.');
        this.showMatrixError(fieldId, msg);
    }

    return matrixValid;
},

/**
 * Validate row-total vs breakdown conflicts across all matrices.
 */
validateRowTotalConflicts() {
    let allValid = true;
    this.matrices.forEach((matrix, fieldId) => {
        if (!__rowTotalManualEnabled(matrix.config)) return;
        if (!this.validateRowTotalConflictsForMatrix(fieldId)) {
            allValid = false;
        }
    });
    return allValid;
},

/**
 * Check if matrix has any data
 */
hasMatrixData(fieldId) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix) return false;

    const data = matrix.data;
    return Object.values(data).some(value => value && value > 0);
},

/**
 * Show error for a specific input
 */
showInputError(input, message) {
    input.classList.add('border-red-500', 'focus:ring-red-500', 'focus:border-red-500');
    input.classList.remove('focus:ring-blue-500', 'focus:border-blue-500');

    // Add error message near the input
    let errorElement = input.parentNode.querySelector('.input-error-message');
    if (!errorElement) {
        errorElement = document.createElement('div');
        errorElement.className = 'input-error-message text-red-600 text-xs mt-1';
        input.parentNode.appendChild(errorElement);
    }
    errorElement.textContent = message;
    errorElement.style.display = 'block';
},

/**
 * Clear error for a specific input
 */
clearInputError(input) {
    input.classList.remove('border-red-500', 'focus:ring-red-500', 'focus:border-red-500');
    input.classList.add('focus:ring-blue-500', 'focus:border-blue-500');

    const errorElement = input.parentNode.querySelector('.input-error-message');
    if (errorElement) {
        errorElement.style.display = 'none';
    }
},

/**
 * Show error for entire matrix
 */
showMatrixError(fieldId, message) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix) return;

    const container = matrix.container;
    const errorElement = container.querySelector('#matrix-error-' + fieldId);
    if (errorElement) {
        errorElement.textContent = message;
        errorElement.style.display = 'block';
    }
},

/**
 * Clear error for entire matrix
 */
clearMatrixError(fieldId) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix) return;

    const container = matrix.container;
    const errorElement = container.querySelector('#matrix-error-' + fieldId);
    if (errorElement) {
        errorElement.style.display = 'none';
    }
},

/**
 * Highlight whole-number column cells that still contain a decimal fraction.
 */
applyWholeNumberViolationHighlighting(fieldId) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix?.container) return;

    matrix.container.querySelectorAll('input[data-cell-key]').forEach((input) => {
        if (input.type === 'checkbox') return;
        if (input.getAttribute('data-is-row-total') === 'true') return;
        __syncWholeNumberViolationHighlight(input);
    });
}
};
