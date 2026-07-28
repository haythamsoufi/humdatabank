/**
 * Regression tests for matrix-aware numeric unformatting (comma = thousands when maxDecimals is set).
 */
import { describe, it, expect, beforeAll } from 'vitest';

describe('numeric-formatting unformat with maxDecimals', () => {
    beforeAll(async () => {
        await import('../../../app/static/js/forms/modules/numeric-formatting.js');
    });

    it('treats a single comma as thousands when maxDecimals is 0', () => {
        expect(window.__numericUnformat('123,12', 0)).toBe('12312');
    });

    it('keeps dot as decimal when maxDecimals is 0', () => {
        expect(window.__numericUnformat('123.12', 0)).toBe('123.12');
    });

    it('uses locale heuristic when maxDecimals is omitted', () => {
        expect(window.__numericUnformat('123,12')).toBe('123.12');
    });
});

describe('matrix numeric input sanitization', () => {
    beforeAll(async () => {
        await import('../../../app/static/js/forms/modules/numeric-formatting.js');
    });

    it('whole-number matrix cells allow digits only', () => {
        expect(window.__sanitizeMatrixNumericInputValue('12-3,4.5a', 0)).toBe('12345');
    });

    it('decimal matrix cells allow digits and one decimal point', () => {
        expect(window.__sanitizeMatrixNumericInputValue('1,234.56.7', 2)).toBe('1234.567');
    });

    it('decimal matrix cells strip minus signs', () => {
        expect(window.__sanitizeMatrixNumericInputValue('-12.3', 2)).toBe('12.3');
    });
});
