/**
 * Numeric Formatting Module
 * - Adds thousands separators in inputs themselves (no overlays)
 * - Converts numeric inputs to text with inputmode="decimal"
 * - Formats on blur, unformats on focus and before submit
 * - Works with readonly calculated fields too
 * - Runs immediately to prevent HTML5 validation issues
 */

const formatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 20 });

// Detect locale decimal and grouping separators once (e.g. "," and "." for en; "'" and "." for de-CH)
let __decimalSep = '.';
let __groupSep = ',';
try {
    const parts = formatter.formatToParts(1234.5);
    for (const p of parts) {
        if (p.type === 'decimal') __decimalSep = p.value;
        if (p.type === 'group') __groupSep = p.value;
    }
} catch (_) {
    // Fallback: infer from toLocaleString
    const s = (1.1).toLocaleString();
    const m = s.match(/[^0-9]/);
    if (m) __decimalSep = m[0];
}

// Escape a single character for use in RegExp (e.g. '.' -> '\.', "'" -> "'")
function __escapeForRegex(char) {
    if (char.length === 0) return '';
    return char.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Detect coarse (touch) pointers – treat as mobile for input UX
const IS_COARSE = (function() {
    try {
        return typeof window !== 'undefined' &&
               window.matchMedia &&
               window.matchMedia('(pointer: coarse)').matches;
    } catch (_) { return false; }
})();

function unformat(value) {
    if (value == null) return '';
    // Normalize sentinel strings
    const rawStr = String(value).trim();
    if (rawStr === 'None' || rawStr === 'undefined' || rawStr === 'null' || rawStr === '') return '';

    // Normalize spaces (NBSP, narrow NBSP) and remove all spaces
    let str = rawStr.replace(/\u00A0|\u202F/g, ' ').replace(/\s+/g, '');

    // Always remove apostrophes (common grouping separator, e.g. de-CH: 12'345)
    str = str.replace(/'/g, '');

    /**
     * Heuristic normalization that tolerates pasted values from other locales.
     * Goal: end with a JS-parseable number string using '.' as decimal separator and no grouping.
     *
     * Rules:
     * - If both ',' and '.' appear, the rightmost of them is assumed to be the decimal separator.
     *   The other becomes grouping and is removed.
     * - If only one of ',' or '.' appears, use locale as a tie-breaker when ambiguous (e.g. "1.234").
     * - If a separator repeats (e.g. "1,234,567"), treat it as grouping.
     */
    const hasComma = str.includes(',');
    const hasDot = str.includes('.');

    const removeAll = (s, ch) => s.split(ch).join('');

    // Remove locale-specific grouping sep early (when it's not one of the two main separators)
    if (__groupSep && __groupSep !== ',' && __groupSep !== '.' && __groupSep !== "'") {
        const groupEsc = __escapeForRegex(__groupSep);
        if (groupEsc) str = str.replace(new RegExp(groupEsc, 'g'), '');
    }

    if (hasComma && hasDot) {
        const lastComma = str.lastIndexOf(',');
        const lastDot = str.lastIndexOf('.');
        const decimalChar = lastComma > lastDot ? ',' : '.';
        const groupChar = decimalChar === ',' ? '.' : ',';

        str = removeAll(str, groupChar);
        if (decimalChar === ',') str = str.replace(/,/g, '.');
        // If decimalChar is '.', keep it as-is
    } else if (hasComma) {
        const commaCount = (str.match(/,/g) || []).length;
        if (commaCount > 1) {
            // 1,234,567 -> grouping
            str = removeAll(str, ',');
        } else {
            const idx = str.indexOf(',');
            const digitsAfter = str.length - idx - 1;
            const digitsBefore = idx;

            // If locale uses comma as decimal, prefer comma as decimal unless it looks like pure grouping (x,xxx)
            const looksLikeGrouping = (digitsAfter === 3 && digitsBefore >= 1 && digitsBefore <= 3);
            if (__decimalSep === ',' && !looksLikeGrouping) {
                str = str.replace(/,/g, '.');
            } else if (__decimalSep !== ',' && looksLikeGrouping) {
                str = removeAll(str, ',');
            } else {
                // Default: treat single comma as decimal
                str = str.replace(/,/g, '.');
            }
        }
    } else if (hasDot) {
        const dotCount = (str.match(/\./g) || []).length;
        if (dotCount > 1) {
            // 1.234.567 -> grouping
            str = removeAll(str, '.');
        } else {
            const idx = str.indexOf('.');
            const digitsAfter = str.length - idx - 1;
            const digitsBefore = idx;
            const looksLikeGrouping = (digitsAfter === 3 && digitsBefore >= 1 && digitsBefore <= 3);

            // If locale decimal is comma and group is dot, "1.234" is more likely grouping than decimal.
            if (__decimalSep === ',' && __groupSep === '.' && looksLikeGrouping) {
                str = removeAll(str, '.');
            }
            // Else keep single dot as decimal
        }
    }

    return str;
}

function isNumericString(value) {
    if (value == null || value === '') return false;
    const raw = unformat(value);
    if (raw === '' || raw === '-' || raw === '+') return false;
    return !isNaN(Number(raw));
}

function formatInPlace(input) {
    const raw = unformat(input.value);
    if (raw === '' || !isNumericString(raw)) return;
    const num = Number(raw);
    input.value = formatter.format(num);
}

function markNumeric(input) {
    input.dataset.numeric = 'true';
    input.inputMode = 'decimal';
    // On mobile/coarse pointers, keep native number inputs for better keyboards
    if (IS_COARSE) return;
    try { input.type = 'text'; } catch (_) {}
}

// Debug flag (reads from same localStorage key system as debug.js)
const __nfDebug = (() => {
    try { return localStorage.getItem('ifrc:debug:module:numeric-formatting') === '1'; } catch (_) { return false; }
})();

function setupNumericFormatting() {
    // Pick up existing number inputs and anything already marked numeric
    const inputs = document.querySelectorAll('input[type="number"], input[data-numeric="true"]');

    if (__nfDebug) {
        const inMatrix = document.querySelectorAll('.matrix-container input[type="number"], .matrix-container input[data-numeric="true"]').length;
        console.log(`[numeric-formatting] setupNumericFormatting: ${inputs.length} inputs (${inMatrix} in matrix), readyState=${document.readyState}`);
    }

    inputs.forEach(input => {
        // Matrix cells are supported now (matrix-handler parses unformatted values)

        // Clean up the value IMMEDIATELY to prevent HTML5 validation errors
        const currentValue = input.value;
        if (currentValue && (currentValue.includes(',') || currentValue.includes("'") || currentValue === 'None' || currentValue === 'null' || currentValue === 'undefined')) {
            const cleanValue = unformat(currentValue);
            input.value = cleanValue;
        }

        // Mark as numeric; convert to text on non-mobile for formatting support
        markNumeric(input);

        // Readonly/disabled: format only on non-mobile
        if (input.readOnly || input.disabled) {
            if (!IS_COARSE) formatInPlace(input);
            return;
        }

        // Initial pretty display if a value is present (non-mobile)
        if (!IS_COARSE && isNumericString(input.value)) formatInPlace(input);

        // On mobile, avoid formatting on focus/blur to keep native number behavior
        if (!IS_COARSE) {
            input.addEventListener('focus', () => {
                // Show raw digits for editing
                input.value = unformat(input.value);
            });

            // Apply formatting when the user leaves the field in various ways
            function scheduleFormat() {
                // Ensure it's text before applying formatted commas
                markNumeric(input);
                // Run after other listeners that might change the value
                try { requestAnimationFrame(() => formatInPlace(input)); } catch (_) { /* no-op */ }
                setTimeout(() => formatInPlace(input), 0);
            }

            input.addEventListener('blur', scheduleFormat);
            input.addEventListener('change', scheduleFormat);
            input.addEventListener('focusout', scheduleFormat);
        }

        input.addEventListener('input', () => {
            // Allow digits, separators (comma, apostrophe), minus, plus, dot/comma
            input.value = input.value.replace(/[^0-9,.\u0027\-+ \u00A0\u202F]/g, '');
        });
    });

    // Ensure raw numbers get submitted
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', () => {
            form.querySelectorAll('input[data-numeric="true"]').forEach(el => {
                el.value = unformat(el.value);
            });
        });
    });
}

// Run immediately, even before DOM is ready, to catch any existing inputs
function setupNumericFormattingEarly() {
    try {
        setupNumericFormatting();
    } catch (_) {}
}

// Run multiple times to catch all possible timing scenarios
setupNumericFormattingEarly(); // Immediate execution

if (document.readyState === 'loading') {
    // Run when DOM content is loaded
    document.addEventListener('DOMContentLoaded', setupNumericFormatting);

    // Also run on HTML parsing (earlier than DOMContentLoaded)
    document.addEventListener('readystatechange', () => {
        if (document.readyState === 'interactive') {
            setupNumericFormatting();
        }
    });
} else {
    // DOM already ready; initialize immediately
    setupNumericFormatting();
}

// Also use MutationObserver to catch dynamically added inputs
if (typeof MutationObserver !== 'undefined') {
    const _numericSelector = 'input[type="number"], input[data-numeric="true"]';

    const observer = new MutationObserver(mutations => {
        let hasNewInputs = false;
        mutations.forEach(mutation => {
            mutation.addedNodes.forEach(node => {
                if (node.nodeType === 1) { // Element node
                    if (node.matches && node.matches(_numericSelector)) {
                        hasNewInputs = true;
                    } else if (node.querySelectorAll) {
                        if (node.querySelectorAll(_numericSelector).length > 0) hasNewInputs = true;
                    }
                }
            });
        });

        if (hasNewInputs) {
            setTimeout(setupNumericFormatting, 0);
        }
    });

    observer.observe(document.body || document.documentElement, {
        childList: true,
        subtree: true
    });
}

// Expose helpers if needed elsewhere (e.g. matrix-handler for autoloaded variable values)
window.__numericUnformat = unformat;
window.__numericFormatInPlace = function formatInPlaceForInput(input) {
    if (!input || typeof input.value === 'undefined') return;
    try { formatInPlace(input); } catch (_) {}
};
window.__setupNumericFormatting = setupNumericFormatting;

// Global delegated handlers as a safety net in case elements are re-cloned and lose listeners
function shouldFormatInput(target) {
    if (!target) return false;
    if (IS_COARSE) return false; // Do not auto-format on mobile
    if (!(target.matches && (target.matches('input[type="number"]') || target.dataset.numeric === 'true'))) return false;
    return true;
}

function scheduleGlobalFormat(target) {
    try { markNumeric(target); } catch (_) {}
    try { requestAnimationFrame(() => formatInPlace(target)); } catch (_) {}
    setTimeout(() => formatInPlace(target), 0);
}

// Unformat on focus so the user edits raw digits (safety net for per-input
// listeners that may be lost when initLayout clones elements with cloneNode).
document.addEventListener('focus', (e) => {
    const target = e.target;
    if (shouldFormatInput(target)) {
        try { target.value = unformat(target.value); } catch (_) { /* no-op */ }
    }
}, true);

document.addEventListener('blur', (e) => {
    const target = e.target;
    if (shouldFormatInput(target)) {
        scheduleGlobalFormat(target);
    }
}, true);

document.addEventListener('change', (e) => {
    const target = e.target;
    if (shouldFormatInput(target)) {
        scheduleGlobalFormat(target);
    }
}, true);

// Global input sanitizer to prevent letters/non-numeric characters while typing
document.addEventListener('input', (e) => {
    const target = e.target;
    if (shouldFormatInput(target)) {
        try {
            // Allow digits, separators (comma, apostrophe), minus, plus, spaces (incl. NBSPs)
            target.value = String(target.value || '').replace(/[^0-9,.\u0027\-+ \u00A0\u202F]/g, '');
        } catch (_) { /* no-op */ }
    } else if (IS_COARSE && target && target.matches && target.matches('input[type="number"]')) {
        // On mobile, still sanitize obvious non-numeric characters
        try {
            target.value = String(target.value || '').replace(/[^0-9,\.\-+]/g, '');
        } catch (_) { /* no-op */ }
    }
}, true);
