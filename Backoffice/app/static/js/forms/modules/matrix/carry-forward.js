/** Matrix carry-forward reference helpers and highlighting. */

import { _t } from './shared.js';
import { __canEditMatrixContainer } from './shared.js';
import { __readMatrixMaxDecimals } from './formatting.js';


export function __parseCarryForwardRef(container) {
    const raw = container?.getAttribute?.('data-carry-forward-ref');
    if (!raw) return null;
    try {
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed : null;
    } catch (e) {
        return null;
    }
}


export function __normalizeMatrixCellValue(value) {
    if (value === null || value === undefined || value === '') return '';
    if (typeof value === 'object') {
        if (value.modified !== undefined && value.modified !== null && value.modified !== '') {
            return __normalizeMatrixCellValue(value.modified);
        }
        if (value.original !== undefined && value.original !== null && value.original !== '') {
            return __normalizeMatrixCellValue(value.original);
        }
        return '';
    }
    if (typeof value === 'boolean') return value ? '1' : '0';
    const str = String(value).trim();
    if (str === 'true') return '1';
    if (str === 'false') return '0';
    return str;
}


export function __matrixCellValuesMatch(currentValue, referenceValue) {
    return __normalizeMatrixCellValue(currentValue) === __normalizeMatrixCellValue(referenceValue);
}


export function __inputValueForMatrixCompare(input) {
    if (!input) return '';
    if (input.type === 'checkbox') {
        return input.checked ? '1' : '0';
    }
    return (typeof window.__numericUnformat === 'function')
        ? window.__numericUnformat(String(input.value || ''), __readMatrixMaxDecimals(input))
        : String(input.value || '').trim().replace(/,/g, '');
}

export const matrixCarryForwardMixin = {
/**
 * Highlight individual matrix cells that contain prefilled/carry-forward values.
 */
applyPrefilledCellHighlighting(fieldId) {
    const matrix = this.matrices.get(fieldId);
    if (!matrix || !matrix.container) {
        return;
    }

    const container = matrix.container;
    if (container.getAttribute('data-highlight-prefilled-cells') !== 'true') {
        return;
    }

    const carryForwardRef = matrix.carryForwardRef || __parseCarryForwardRef(container);
    matrix.carryForwardRef = carryForwardRef;
    const hasCarryForwardRef = carryForwardRef && Object.keys(carryForwardRef).length > 0;

    const prefilledTitle = container.getAttribute('data-prefilled-cell-title')
        || 'This is a prefilled value';

    const inputs = container.querySelectorAll('input[data-cell-key]');
    if (inputs.length === 0) {
        this.updateLegendVisibility(fieldId);
        return;
    }

    const clearPrefilledHighlight = (input) => {
        const cell = input.closest('td');
        if (input.type === 'checkbox') {
            input.classList.remove('ring-2', 'ring-yellow-300');
            if (cell) cell.classList.remove('bg-yellow-100');
        } else {
            input.classList.remove('bg-yellow-100', 'border', 'border-yellow-300', 'rounded-sm');
            if (cell) cell.classList.remove('bg-yellow-100');
            if (!input.classList.contains('border-0')) {
                input.classList.add('border-0');
            }
        }
        input.removeAttribute('title');
    };

    const applyPrefilledHighlight = (input) => {
        const cell = input.closest('td');
        if (input.type === 'checkbox') {
            input.classList.add('ring-2', 'ring-yellow-300');
            if (cell) cell.classList.add('bg-yellow-100');
        } else {
            input.classList.remove('bg-transparent', 'border-0');
            input.classList.add('bg-yellow-100', 'border', 'border-yellow-300', 'rounded-sm');
            if (cell) cell.classList.add('bg-yellow-100');
        }
        if (!input.disabled && !input.hasAttribute('readonly')) {
            input.setAttribute('title', prefilledTitle);
        }
    };

    inputs.forEach((input) => {
        if (input.getAttribute('data-whole-number-violation') === 'true') {
            return;
        }
        if (input.getAttribute('data-variable-readonly') === 'true') {
            return;
        }

        const cellKey = input.getAttribute('data-cell-key');
        if (hasCarryForwardRef) {
            if (!cellKey || !Object.prototype.hasOwnProperty.call(carryForwardRef, cellKey)) {
                clearPrefilledHighlight(input);
                return;
            }
            const currentValue = __inputValueForMatrixCompare(input);
            if (!__matrixCellValuesMatch(currentValue, carryForwardRef[cellKey])) {
                clearPrefilledHighlight(input);
                return;
            }
            applyPrefilledHighlight(input);
            return;
        }

        let hasValue = false;
        if (input.type === 'checkbox') {
            hasValue = input.checked;
        } else {
            hasValue = String(input.value || '').trim() !== '';
        }

        if (!hasValue) {
            clearPrefilledHighlight(input);
            return;
        }

        applyPrefilledHighlight(input);
    });

    this.updateLegendVisibility(fieldId);
},


_matrixHasPrefilledCellHighlights(container) {
    if (!container) return false;
    return Array.from(container.querySelectorAll('input[data-cell-key]')).some((input) => {
        if (input.getAttribute('data-variable-readonly') === 'true') {
            return false;
        }
        const cell = input.closest('td');
        return Boolean(
            cell?.classList.contains('bg-yellow-100')
            || input.classList.contains('bg-yellow-100')
            || input.classList.contains('ring-yellow-300')
        );
    });
}
};
