/**
 * Regression tests for matrix-aware numeric unformatting (comma = thousands when maxDecimals is set).
 */
import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest';

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

    it('treats grouped thousands with trailing zeros when maxDecimals is 0', () => {
        expect(window.__numericUnformat('300,000', 0)).toBe('300000');
        expect(window.__numericUnformat('232,000', 0)).toBe('232000');
    });

    it('keeps ambiguous US-style decimal paste when maxDecimals is 0', () => {
        expect(window.__numericUnformat('1234.56', 0)).toBe('1234.56');
    });
});

describe('matrix numeric input sanitization', () => {
    it('whole-number matrix cells preserve a decimal point for validation', () => {
        expect(window.__sanitizeMatrixNumericInputValue('12-3,4.5a', 0)).toBe('1234.5');
        expect(window.__sanitizeMatrixNumericInputValue('1234.56', 0)).toBe('1234.56');
    });

    it('decimal matrix cells allow digits and one decimal point', () => {
        expect(window.__sanitizeMatrixNumericInputValue('1,234.56.7', 2)).toBe('1234.567');
    });

    it('decimal matrix cells strip minus signs', () => {
        expect(window.__sanitizeMatrixNumericInputValue('-12.3', 2)).toBe('12.3');
    });
});

describe('numeric-formatting in-place display', () => {
    it('converts number inputs to text before applying grouped formatting', () => {
        const input = document.createElement('input');
        input.type = 'number';
        input.value = '232000';
        window.__numericFormatInPlace(input);
        expect(input.type).toBe('text');
        expect(input.value).toBe('232,000');
    });
});

describe('numeric-formatting unformat with maxDecimals (EU locale)', () => {
    beforeAll(async () => {
        vi.stubGlobal('Intl', {
            NumberFormat: class {
                constructor(_locale, _options) {}
                formatToParts() {
                    return [
                        { type: 'integer', value: '1' },
                        { type: 'group', value: '.' },
                        { type: 'integer', value: '234' },
                        { type: 'decimal', value: ',' },
                        { type: 'fraction', value: '5' },
                    ];
                }
                format(value) {
                    return String(value);
                }
            },
        });
        vi.resetModules();
        await import('../../../app/static/js/forms/modules/numeric-formatting.js');
    });

    afterAll(() => {
        vi.unstubAllGlobals();
        vi.resetModules();
    });

    it('parses dot-grouped whole numbers shown in de-AT/de-DE display', () => {
        expect(window.__numericUnformat('232.000', 0)).toBe('232000');
        expect(window.__numericUnformat('488.516', 0)).toBe('488516');
        expect(window.__numericUnformat('187.700', 0)).toBe('187700');
        expect(window.__numericUnformat('9.100.000', 0)).toBe('9100000');
        expect(window.__numericUnformat('3.165.230', 0)).toBe('3165230');
    });

    it('preserves EU decimal paste for whole-number validation', () => {
        expect(window.__numericUnformat('1234,56', 0)).toBe('1234.56');
    });

    it('preserves US-style decimal paste for whole-number validation', () => {
        expect(window.__numericUnformat('1234.56', 0)).toBe('1234.56');
    });
});
