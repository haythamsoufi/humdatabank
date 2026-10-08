/**
 * Order matrix row headers. Period labels (2026, Jan-Jun 2026, Q3 2025)
 * follow calendar order. Every other label uses numeric alphabetical order.
 */

const MONTH_NUMBERS = {
    jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
    jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
};

const MONTH = 'jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?';
const MONTH_RANGE = new RegExp(`^(${MONTH})\\s*[-–—]\\s*(${MONTH})\\s+(\\d{4})$`, 'i');
const MONTH_YEAR = new RegExp(`^(${MONTH})\\s+(\\d{4})$`, 'i');
const QUARTER = /^q([1-4])\s+(\d{4})$/i;
const ANNUAL = /^(?:annual\s+)?(\d{4})$/i;
const YEAR_SPAN = /^(\d{4})\s*[-/]\s*(\d{2,4})$/;

function monthNumber(token) {
    return MONTH_NUMBERS[String(token || '').slice(0, 3).toLowerCase()] || null;
}

/** Calendar key YYYYMM, or null when the label is not a period. Annual years use month 00. */
export function matrixRowPeriodKey(label) {
    const text = String(label || '').trim();
    if (!text) return null;

    let match = text.match(MONTH_RANGE);
    if (match) {
        const month = monthNumber(match[1]);
        return month ? (Number(match[3]) * 100) + month : null;
    }
    match = text.match(QUARTER);
    if (match) {
        return (Number(match[2]) * 100) + ((Number(match[1]) - 1) * 3) + 1;
    }
    match = text.match(MONTH_YEAR);
    if (match) {
        const month = monthNumber(match[1]);
        return month ? (Number(match[2]) * 100) + month : null;
    }
    match = text.match(ANNUAL);
    if (match) return Number(match[1]) * 100;
    match = text.match(YEAR_SPAN);
    if (match) return Number(match[1]) * 100;
    return null;
}

export function compareMatrixRowLabels(leftLabel, rightLabel) {
    const left = String(leftLabel || '').trim();
    const right = String(rightLabel || '').trim();
    const leftKey = matrixRowPeriodKey(left);
    const rightKey = matrixRowPeriodKey(right);
    if (leftKey != null && rightKey != null) {
        if (leftKey !== rightKey) return leftKey - rightKey;
    } else if (leftKey != null || rightKey != null) {
        return leftKey != null ? -1 : 1;
    }
    return left.localeCompare(right, undefined, { numeric: true, sensitivity: 'base' });
}
