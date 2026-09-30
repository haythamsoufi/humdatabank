/**
 * Condition operators shared by the form builder (labels) and the entry form
 * (evaluation). The builder offers a catalog per field type. Evaluation also
 * accepts the legacy aliases ``equals`` / ``not_equals``.
 *
 * Text operators that only appear in the builder catalog (contains, starts
 * with, ends with) are listed for the picker. Evaluation of those ids stays
 * with the entry-form caller until a product rule defines them.
 */

export const conditionTypesMap = {
    'Number': [
        {value: 'equal_to', label: 'Equal to'},
        {value: 'not_equal_to', label: 'Not equal to'},
        {value: 'greater_than', label: 'Greater than (>)'},
        {value: 'greater_than_or_equal_to', label: 'Greater than or equal to (>=)'},
        {value: 'less_than', label: 'Less than (<)'},
        {value: 'less_than_or_equal_to', label: 'Less than or equal to (<=)'},
        {value: 'is_empty', label: 'Is empty'},
        {value: 'is_not_empty', label: 'Is not empty'}
    ],
    'text': [
        {value: 'equal_to', label: 'Equal to'},
        {value: 'not_equal_to', label: 'Not equal to'},
        {value: 'contains', label: 'Contains'},
        {value: 'not_contains', label: 'Does not contain'},
        {value: 'starts_with', label: 'Starts with'},
        {value: 'ends_with', label: 'Ends with'},
        {value: 'is_empty', label: 'Is empty'},
        {value: 'is_not_empty', label: 'Is not empty'}
    ],
    'textarea': [
        {value: 'equal_to', label: 'Equal to'},
        {value: 'not_equal_to', label: 'Not equal to'},
        {value: 'contains', label: 'Contains'},
        {value: 'not_contains', label: 'Does not contain'},
        {value: 'is_empty', label: 'Is empty'},
        {value: 'is_not_empty', label: 'Is not empty'}
    ],
    'yesno': [
        {value: 'is_yes', label: 'Is Yes'},
        {value: 'is_no', label: 'Is No'},
        {value: 'is_empty', label: 'Is empty (no answer)'},
        {value: 'is_not_empty', label: 'Is answered'}
    ],
    'single_choice': [
        {value: 'equal_to', label: 'Is'},
        {value: 'not_equal_to', label: 'Is not'},
        {value: 'is_empty', label: 'Is empty'},
        {value: 'is_not_empty', label: 'Is not empty'}
    ],
    'multiple_choice': [
        {value: 'contains', label: 'Contains'},
        {value: 'not_contains', label: 'Does not contain'},
        {value: 'is_empty', label: 'Is empty'},
        {value: 'is_not_empty', label: 'Is not empty'}
    ],
    'date': [
        {value: 'equal_to', label: 'Is'},
        {value: 'not_equal_to', label: 'Is not'},
        {value: 'greater_than', label: 'Is after'},
        {value: 'greater_than_or_equal_to', label: 'Is on or after'},
        {value: 'less_than', label: 'Is before'},
        {value: 'less_than_or_equal_to', label: 'Is on or before'},
        {value: 'is_empty', label: 'Is empty'},
        {value: 'is_not_empty', label: 'Is not empty'}
    ],
    'datetime': [
        {value: 'equal_to', label: 'Is'},
        {value: 'not_equal_to', label: 'Is not'},
        {value: 'greater_than', label: 'Is after'},
        {value: 'greater_than_or_equal_to', label: 'Is on or after'},
        {value: 'less_than', label: 'Is before'},
        {value: 'less_than_or_equal_to', label: 'Is on or before'},
        {value: 'is_empty', label: 'Is empty'},
        {value: 'is_not_empty', label: 'Is not empty'}
    ],
    'document': [
        {value: 'is_empty', label: 'Is empty (No document uploaded)'},
        {value: 'is_not_empty', label: 'Is not empty (Document uploaded)'}
    ]
};

function comparableConditionValue(value) {
    if (value === null || value === undefined) return '';
    return String(value).trim();
}

function parseComparableNumber(value) {
    if (value === null || value === undefined) return NaN;
    if (typeof value === 'number') return value;
    const str = String(value).trim();
    if (str === '') return NaN;
    const unformatted = typeof window.__numericUnformat === 'function'
        ? window.__numericUnformat(str)
        : str.replace(/,/g, '').replace(/'/g, '');
    return parseFloat(unformatted);
}

function isValueEmpty(value) {
    if (value === null || value === undefined) {
        return true;
    }
    if (typeof value === 'string') {
        return value.trim() === '';
    }
    if (typeof value === 'number') {
        return false;
    }
    if (Array.isArray(value)) {
        return value.length === 0;
    }
    if (typeof value === 'object') {
        return Object.keys(value).length === 0;
    }
    return false;
}

/**
 * Evaluate one condition. Returns ``undefined`` when ``conditionType`` is not
 * an operator the entry form implements (the caller treats that as not met).
 */
export function compareCondition(conditionType, actualValue, expectedValue) {
    switch (conditionType) {
        case 'is_empty':
            return isValueEmpty(actualValue);
        case 'is_not_empty':
            return !isValueEmpty(actualValue);
        case 'equals':
        case 'equal_to':
            return comparableConditionValue(actualValue) === comparableConditionValue(expectedValue);
        case 'not_equals':
        case 'not_equal_to':
            return comparableConditionValue(actualValue) !== comparableConditionValue(expectedValue);
        case 'is_yes':
            return actualValue !== null && actualValue !== undefined && String(actualValue).toLowerCase().trim() === 'yes';
        case 'is_no':
            return actualValue !== null && actualValue !== undefined && String(actualValue).toLowerCase().trim() === 'no';
        case 'greater_than': {
            const actualNum = parseComparableNumber(actualValue);
            const expectedNum = parseComparableNumber(expectedValue);
            return !isNaN(actualNum) && !isNaN(expectedNum) && actualNum > expectedNum;
        }
        case 'less_than': {
            const actualNum = parseComparableNumber(actualValue);
            const expectedNum = parseComparableNumber(expectedValue);
            return !isNaN(actualNum) && !isNaN(expectedNum) && actualNum < expectedNum;
        }
        case 'greater_than_or_equal_to': {
            const actualNum = parseComparableNumber(actualValue);
            const expectedNum = parseComparableNumber(expectedValue);
            return !isNaN(actualNum) && !isNaN(expectedNum) && actualNum >= expectedNum;
        }
        case 'less_than_or_equal_to': {
            const actualNum = parseComparableNumber(actualValue);
            const expectedNum = parseComparableNumber(expectedValue);
            return !isNaN(actualNum) && !isNaN(expectedNum) && actualNum <= expectedNum;
        }
        default:
            return undefined;
    }
}
