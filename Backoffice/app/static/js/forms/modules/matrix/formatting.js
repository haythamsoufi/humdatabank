/** Matrix number/cell formatting helpers. */

import { _t, ROW_TOTAL_COLUMN_NAME } from './shared.js';

export const __matrixIntegerFormatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
// Locale-aware formatter for variable/tooltip display (preserves decimals)

export const __matrixNumberFormatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 20 });

export const __WHOLE_NUMBER_VIOLATION_INPUT_CLASSES = [
    'bg-red-100', 'border', 'border-red-400', 'rounded-sm', 'ring-1', 'ring-red-300',
];

export const __WHOLE_NUMBER_VIOLATION_CELL_CLASS = 'bg-red-50';

export function __formatInteger(value) {
    try {
        const num = Number(value || 0);
        if (!isFinite(num)) return '0';
        return __matrixIntegerFormatter.format(Math.round(num));
    } catch (e) {
        return String(Math.round(Number(value || 0)) || 0);
    }
}

/** Raw integer string for input.value — number inputs reject locale grouping (e.g. "1,042,052"). */
export function __integerInputValue(value) {
    if (value === '' || value == null) return '';
    const num = Number(value);
    if (!isFinite(num)) return '';
    return String(Math.round(num));
}


export function __setMatrixNumericInputValue(input, value) {
    if (!input) return;
    input.value = __integerInputValue(value);
    if (typeof window.__numericFormatInPlace === 'function') {
        window.__numericFormatInPlace(input);
    }
}

export function __formatNumberForDisplay(value) {
    if (value == null || value === '') return null;
    const raw = (typeof window.__numericUnformat === 'function')
        ? window.__numericUnformat(String(value))
        : String(value).trim().replace(/,/g, '');
    if (raw === '') return null;
    const num = Number(raw);
    if (!isFinite(num)) return String(value);
    try {
        return __matrixNumberFormatter.format(num);
    } catch (e) {
        return String(value);
    }
}

/**
 * Coerce config flags that may be stored as boolean/number/string.
 * Treats "true"/"1"/"yes"/"on" as true and "false"/"0"/"no"/"off" as false.
 * Uses defaultWhenMissing only when value is null/undefined.
 */
/**
 * Resolve the maximum decimal places for a matrix column (rounding on save/display).
 * Returns null for legacy columns (bare 'number') so they keep open-ended parsing.
 */
export function __resolveColumnMaxDecimals(column) {
    if (!column || typeof column !== 'object') return null;
    if (column.type === 'number_whole') return 0;
    if (column.type === 'number_decimal') {
        const parsed = parseInt(column.decimals, 10);
        return Number.isFinite(parsed) && parsed >= 0 ? parsed : 2;
    }
    return null;
}

/** Read the max-decimals hint stashed on a matrix cell input (see __resolveColumnMaxDecimals). */
export function __readMatrixMaxDecimals(input) {
    const raw = input && input.dataset ? input.dataset.maxDecimals : undefined;
    if (raw === undefined || raw === null || raw === '') return undefined;
    const parsed = parseInt(raw, 10);
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
}


export function __rawValueHasNonZeroFraction(rawValue, maxDecimals) {
    if (rawValue === null || rawValue === undefined || rawValue === '') return false;
    if (maxDecimals === 0 && typeof window !== 'undefined'
        && typeof window.__matrixWholeNumberHasFraction === 'function') {
        return window.__matrixWholeNumberHasFraction(rawValue);
    }
    const unformatFn = typeof window !== 'undefined' ? window.__numericUnformat : null;
    const rawString = (typeof unformatFn === 'function')
        ? unformatFn(String(rawValue), maxDecimals)
        : String(rawValue).trim().replace(/,/g, '');
    if (!rawString) return false;
    const num = parseFloat(rawString);
    if (!isFinite(num)) return false;
    return Math.abs(num - Math.round(num)) > 1e-9;
}


export function __applyWholeNumberViolationHighlight(input, violated) {
    if (!input || input.type === 'checkbox') return;
    const cell = input.closest('td');
    const titleKey = 'whole-number-violation';

    if (violated) {
        input.classList.remove('border-0', 'bg-transparent', 'bg-yellow-100', 'border-yellow-300', 'ring-yellow-300');
        input.classList.add(...__WHOLE_NUMBER_VIOLATION_INPUT_CLASSES);
        if (cell) {
            cell.classList.remove('bg-yellow-100');
            cell.classList.add(__WHOLE_NUMBER_VIOLATION_CELL_CLASS);
        }
        input.setAttribute('data-whole-number-violation', 'true');
        input.setAttribute('aria-invalid', 'true');
        input.dataset.violationTitleKey = titleKey;
        input.setAttribute(
            'title',
            typeof _t === 'function'
                ? _t('This column requires a whole number. Please correct the decimal value.')
                : 'This column requires a whole number. Please correct the decimal value.'
        );
        return;
    }

    input.classList.remove(...__WHOLE_NUMBER_VIOLATION_INPUT_CLASSES);
    input.removeAttribute('data-whole-number-violation');
    input.removeAttribute('aria-invalid');
    if (input.dataset.violationTitleKey === titleKey) {
        input.removeAttribute('title');
        delete input.dataset.violationTitleKey;
    }
    if (cell) cell.classList.remove(__WHOLE_NUMBER_VIOLATION_CELL_CLASS);
    if (!input.classList.contains('bg-yellow-100') && !input.classList.contains('bg-gray-100')) {
        input.classList.add('border-0');
    }
}


export function __syncWholeNumberViolationHighlight(input) {
    if (!input || input.type === 'checkbox') return false;
    if (input.getAttribute('data-is-row-total') === 'true') return false;
    const maxDecimals = __readMatrixMaxDecimals(input);
    const violated = maxDecimals === 0 && __rawValueHasNonZeroFraction(input.value, maxDecimals);
    __applyWholeNumberViolationHighlight(input, violated);
    return violated;
}

/** Display a matrix numeric cell; preserve fractional values on whole-number columns and highlight them. */
export function __setMatrixNumericCellDisplay(input, rawValue) {
    if (!input || input.type === 'checkbox') return;

    if (rawValue !== undefined && rawValue !== null) {
        input.value = rawValue;
    }

    const maxDecimals = __readMatrixMaxDecimals(input);
    const violated = maxDecimals === 0 && __rawValueHasNonZeroFraction(input.value, maxDecimals);

    if (violated) {
        const unformatFn = typeof window !== 'undefined' ? window.__numericUnformat : null;
        const normalized = typeof unformatFn === 'function'
            ? unformatFn(String(input.value), maxDecimals)
            : String(input.value).trim().replace(/,/g, '');
        if (normalized !== '') input.value = normalized;
        __applyWholeNumberViolationHighlight(input, true);
        return;
    }

    __applyWholeNumberViolationHighlight(input, false);
    if (typeof window.__numericFormatInPlace === 'function') {
        window.__numericFormatInPlace(input);
    }
}

/**
 * Parse a matrix numeric cell: unformat with standard separator rules, then round to column precision.
 */
export function __parseMatrixNumericCellValue(rawValue, maxDecimals) {
    if (rawValue === null || rawValue === undefined) return rawValue;
    if (typeof rawValue === 'string' && rawValue.trim() === '') return rawValue;

    const unformatFn = typeof window !== 'undefined' ? window.__numericUnformat : null;
    const rawString = (typeof unformatFn === 'function')
        ? unformatFn(String(rawValue), maxDecimals)
        : String(rawValue).trim().replace(/,/g, '');

    if (rawString === '' || rawString === '-' || rawString === '+') return rawValue;

    const num = parseFloat(rawString);
    if (!isFinite(num)) return rawValue;

    if (typeof maxDecimals === 'number' && isFinite(maxDecimals) && maxDecimals >= 0) {
        const factor = Math.pow(10, maxDecimals);
        return Math.round(num * factor) / factor;
    }
    return num;
}


export function __configFlag(value, defaultWhenMissing = false) {
    if (value === undefined || value === null) return defaultWhenMissing;
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return value === 1;
    if (typeof value === 'string') {
        const v = value.trim().toLowerCase();
        if (v === 'true' || v === '1' || v === 'yes' || v === 'y' || v === 'on') return true;
        if (v === 'false' || v === '0' || v === 'no' || v === 'n' || v === 'off') return false;
    }
    return Boolean(value);
}


export function __isEmptyVariableValue(value) {
    return value == null || value === '' || (typeof value === 'string' && value.trim() === '');
}


export function __parseMatrixNumericValue(raw) {
    if (__isEmptyVariableValue(raw)) return null;
    if (typeof raw === 'number' && isFinite(raw)) return raw;
    const rawString = (typeof window.__numericUnformat === 'function')
        ? window.__numericUnformat(String(raw))
        : String(raw).trim().replace(/,/g, '');
    if (!rawString) return null;
    const num = parseFloat(rawString);
    return isFinite(num) ? num : null;
}


export function __normalizeVariableNumericValue(raw) {
    const num = __parseMatrixNumericValue(raw);
    return num != null ? num : '';
}


export function __toVariableTickValue(value) {
    if (value === true || value === 1 || value === '1' || value === 'true') return '1';
    if (value === false || value === 0 || value === '0' || value === 'false') return '0';
    return __isEmptyVariableValue(value) ? '' : String(value);
}


export function __normalizeVariableCompareValue(value, maxDecimals) {
    if (__isEmptyVariableValue(value)) return '';
    const s = String(value);
    return (typeof window.__numericUnformat === 'function')
        ? window.__numericUnformat(s, maxDecimals)
        : s.replace(/,/g, '');
}


export function __getSavedMatrixCellScalar(savedValue) {
    if (savedValue === null || savedValue === undefined) return '';
    if (typeof savedValue === 'object') {
        if (savedValue.modified !== undefined && savedValue.modified !== null) {
            return savedValue.modified;
        }
        if (savedValue.original !== undefined && savedValue.original !== null) {
            return savedValue.original;
        }
        return '';
    }
    return savedValue;
}

/** Saved variable matrix cell explicitly overridden by the user (legacy { isModified } format). */
export function __savedVariableCellIsUserModified(savedValue) {
    return savedValue !== null && typeof savedValue === 'object' && savedValue.isModified === true;
}

/** Legacy lookup mirror blob that should refresh from source when lookup changes (not user submissions). */
export function __savedVariableCellIsStaleLookupMirror(savedValue) {
    return savedValue !== null && typeof savedValue === 'object' && savedValue.isModified !== true;
}


export function __formatLookupValueForInput(inputType, lookupValue) {
    if (inputType === 'checkbox') {
        return (lookupValue === '1' || lookupValue === 1 || lookupValue === true || lookupValue === 'true') ? '1' : '0';
    }
    return lookupValue !== null && lookupValue !== undefined ? String(lookupValue) : '';
}


export function __formatSavedScalarForInput(inputType, savedScalar) {
    if (inputType === 'checkbox') {
        return (savedScalar === '1' || savedScalar === 1 || savedScalar === true || savedScalar === 'true') ? '1' : '0';
    }
    return savedScalar !== null && savedScalar !== undefined ? String(savedScalar) : '';
}


export function __persistVariableCellScalar(rawValue, maxDecimals) {
    if (rawValue === null || rawValue === undefined) return '';
    const trimmed = String(rawValue).trim();
    if (trimmed === '') return '';
    return __normalizeVariableCompareValue(trimmed, maxDecimals);
}


export function __variableCellDiffersFromLookup(lookupValue, savedValue, inputType, maxDecimals) {
    if (inputType === 'checkbox') {
        const lookupNorm = __formatSavedScalarForInput('checkbox', lookupValue);
        if (lookupNorm === '') return false;
        const savedNorm = __formatSavedScalarForInput('checkbox', savedValue);
        return lookupNorm !== savedNorm;
    }
    const lookupNorm = __normalizeVariableCompareValue(lookupValue, maxDecimals);
    if (lookupNorm === '') return false;
    const savedNorm = __normalizeVariableCompareValue(savedValue, maxDecimals);
    return lookupNorm !== savedNorm;
}


export function __resolveMatrixLocalizedLabel(config, flatKey, translationsKey, defaultText) {
    let tk = 'en';
    const langMeta = document.documentElement.getAttribute('lang');
    if (langMeta) tk = langMeta.split('-')[0];
    const translations = config?.[translationsKey];
    if (translations && typeof translations === 'object') {
        const localized = translations[tk] || translations.en;
        if (localized && String(localized).trim()) return String(localized).trim();
    }
    const flat = config?.[flatKey];
    if (flat && String(flat).trim()) return String(flat).trim();
    return defaultText;
}

/**
 * Normalize matrix payload before saving.
 * Removes non-cell metadata keys that should not be persisted.
 * @param {Object} data - Matrix data object
 * @returns {Object} Sanitized object safe to persist
 */
export function __reorderMatrixData(data) {
    if (!data || typeof data !== 'object') {
        return data;
    }

    const reordered = {};

    // Keep insertion order of actual cell keys, but drop internal metadata keys.
    Object.keys(data).forEach(key => {
        if (String(key).startsWith('_')) return;
        const value = data[key];
        if (value && typeof value === 'object' && ('original' in value || 'modified' in value)) {
            if (!value.isModified
                && __isEmptyVariableValue(value.original)
                && __isEmptyVariableValue(value.modified)) {
                return;
            }
        }
        reordered[key] = value;
    });

    return reordered;
}


export function __serializeMatrixData(data) {
    const sanitized = __reorderMatrixData(data || {});
    if (!sanitized || typeof sanitized !== 'object') return '';
    const json = Object.keys(sanitized).length > 0 ? JSON.stringify(sanitized) : '';
    if (!json) return '';
    // Base64-encode to avoid WAF false-positives on JSON keys/values in
    // form-urlencoded bodies. Server decodes the b64: prefix before json.loads().
    // unescape+encodeURIComponent makes btoa() safe for non-ASCII row/column names.
    try {
        return 'b64:' + btoa(unescape(encodeURIComponent(json)));
    } catch (_) {
        return json;
    }
}


export function __getMatrixColumnNames(config) {
    const columns = config?.columns || [];
    return columns
        .map((column) => (typeof column === 'object' ? column.name : column))
        .filter(Boolean);
}

/**
 * Parse a matrix cell key (rowId_columnName) using configured column names.
 * Column names may contain underscores/spaces, so naive split('_') is unsafe.
 */
export function __parseMatrixCellKey(cellKey, config) {
    if (!cellKey || String(cellKey).startsWith('_')) return null;

    const key = String(cellKey);
    const columnNames = __getMatrixColumnNames(config);
    if (columnNames.length) {
        const sortedNames = [...columnNames].sort((a, b) => b.length - a.length);
        for (const columnName of sortedNames) {
            const suffix = `_${columnName}`;
            if (key.endsWith(suffix) && key.length > suffix.length) {
                return {
                    rowId: key.slice(0, -suffix.length),
                    columnName,
                };
            }
        }
        // Row total column is rendered when show_row_totals is on but not listed in config.columns.
        const totalSuffix = `_${ROW_TOTAL_COLUMN_NAME}`;
        if (__configFlag(config?.show_row_totals, true)
            && key.endsWith(totalSuffix)
            && key.length > totalSuffix.length) {
            return {
                rowId: key.slice(0, -totalSuffix.length),
                columnName: ROW_TOTAL_COLUMN_NAME,
            };
        }
        return null;
    }

    const lastUnderscore = key.lastIndexOf('_');
    if (lastUnderscore <= 0) return null;
    return {
        rowId: key.slice(0, lastUnderscore),
        columnName: key.slice(lastUnderscore + 1),
    };
}

/** Coerce a stored cell value to a number for totals (handles variable column { original, modified } objects). */
export function __cellValueToNumber(value) {
    if (value == null || value === '') return 0;
    if (typeof value === 'number' && isFinite(value)) return value;
    const toUnformattedNumber = (v) => {
        if (v == null) return 0;
        const s = String(v).trim();
        if (!s) return 0;
        const plain = (typeof window !== 'undefined' && typeof window.__numericUnformat === 'function')
            ? window.__numericUnformat(s)
            : s;
        const num = Number(plain);
        return isFinite(num) ? num : 0;
    };
    if (typeof value === 'object' && value.original !== undefined) {
        if (value.isModified) {
            return toUnformattedNumber(value.modified != null ? value.modified : '');
        }
        const display = value.modified != null && value.modified !== '' ? value.modified : value.original;
        return toUnformattedNumber(display);
    }
    return toUnformattedNumber(value);
}

/** Reserved column name for persisted manual/auto row totals. */
