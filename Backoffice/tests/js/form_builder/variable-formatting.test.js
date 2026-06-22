/**
 * Tests for app/static/js/form_builder/modules/variables/variable-formatting.js
 *
 * VariableFormatter.formatVariablesInText, extractVariables, and
 * extractVariablesFromObject are pure logic functions that require only
 * jsdom for DOMParser (used internally by formatVariablesInText).
 */
import { describe, it, expect } from 'vitest';
import { VariableFormatter } from '../../../app/static/js/form_builder/modules/variables/variable-formatting.js';

// ---------------------------------------------------------------------------
// formatVariablesInText
// ---------------------------------------------------------------------------

describe('VariableFormatter.formatVariablesInText', () => {
    it('returns null/undefined unchanged', () => {
        expect(VariableFormatter.formatVariablesInText(null)).toBeNull();
        expect(VariableFormatter.formatVariablesInText(undefined)).toBeUndefined();
    });

    it('returns plain text without variables unchanged', () => {
        const text = 'Hello world, no brackets here';
        expect(VariableFormatter.formatVariablesInText(text)).toBe(text);
    });

    it('wraps [variable] in a variable-formatted badge', () => {
        const result = VariableFormatter.formatVariablesInText('[country_name]');
        expect(result).toContain('variable-formatted');
        expect(result).toContain('[country_name]');
    });

    it('wraps [[var]+N] formula in a variable-formatted badge', () => {
        const result = VariableFormatter.formatVariablesInText('[[period]+1]');
        expect(result).toContain('variable-formatted');
        expect(result).toContain('[[period]+1]');
    });

    it('wraps [[var]-N] formula (subtraction)', () => {
        const result = VariableFormatter.formatVariablesInText('[[year]-2]');
        expect(result).toContain('variable-formatted');
        expect(result).toContain('[[year]-2]');
    });

    it('handles multiple variables in the same string', () => {
        const result = VariableFormatter.formatVariablesInText('Hello [name], it is [year]');
        expect(result).toContain('[name]');
        expect(result).toContain('[year]');
        const badgeCount = (result.match(/variable-formatted/g) || []).length;
        expect(badgeCount).toBeGreaterThanOrEqual(2);
    });

    it('handles text with both formula and simple variable', () => {
        const result = VariableFormatter.formatVariablesInText('[[period]+1] covers [country]');
        expect(result).toContain('variable-formatted');
    });

    it('returns an empty string unchanged', () => {
        expect(VariableFormatter.formatVariablesInText('')).toBe('');
    });
});

// ---------------------------------------------------------------------------
// extractVariables
// ---------------------------------------------------------------------------

describe('VariableFormatter.extractVariables', () => {
    it('returns empty array for null/undefined/empty input', () => {
        expect(VariableFormatter.extractVariables(null)).toEqual([]);
        expect(VariableFormatter.extractVariables(undefined)).toEqual([]);
        expect(VariableFormatter.extractVariables('')).toEqual([]);
    });

    it('returns empty array when no variables present', () => {
        expect(VariableFormatter.extractVariables('plain text')).toEqual([]);
    });

    it('extracts a single simple variable', () => {
        const vars = VariableFormatter.extractVariables('Hello [country_name]');
        expect(vars).toContain('country_name');
        expect(vars.length).toBe(1);
    });

    it('extracts multiple distinct simple variables', () => {
        const vars = VariableFormatter.extractVariables('[a] and [b] and [c]');
        expect(vars).toContain('a');
        expect(vars).toContain('b');
        expect(vars).toContain('c');
        expect(vars.length).toBe(3);
    });

    it('deduplicates repeated variable names', () => {
        const vars = VariableFormatter.extractVariables('[name] hello [name] again');
        expect(vars.filter(v => v === 'name').length).toBe(1);
    });

    it('extracts variable name from formula [[var]+N]', () => {
        const vars = VariableFormatter.extractVariables('[[period]+1] summary');
        expect(vars).toContain('period');
    });

    it('extracts from formula and simple variable together', () => {
        const vars = VariableFormatter.extractVariables('[[year]-1] for [country]');
        expect(vars).toContain('year');
        expect(vars).toContain('country');
    });

    it('handles underscore and numeric variable names', () => {
        const vars = VariableFormatter.extractVariables('[my_var_1] [var2]');
        expect(vars).toContain('my_var_1');
        expect(vars).toContain('var2');
    });
});

// ---------------------------------------------------------------------------
// extractVariablesFromObject
// ---------------------------------------------------------------------------

describe('VariableFormatter.extractVariablesFromObject', () => {
    it('handles null/undefined gracefully', () => {
        const vars = new Set();
        expect(() => VariableFormatter.extractVariablesFromObject(null, vars)).not.toThrow();
        expect(() => VariableFormatter.extractVariablesFromObject(undefined, vars)).not.toThrow();
        expect(vars.size).toBe(0);
    });

    it('extracts from a plain string', () => {
        const vars = new Set();
        VariableFormatter.extractVariablesFromObject('[country]', vars);
        expect([...vars]).toContain('country');
    });

    it('extracts from a flat object', () => {
        const vars = new Set();
        VariableFormatter.extractVariablesFromObject({ label: '[country_name]', description: '[year]' }, vars);
        expect([...vars]).toContain('country_name');
        expect([...vars]).toContain('year');
    });

    it('extracts from a nested object', () => {
        const vars = new Set();
        VariableFormatter.extractVariablesFromObject({ outer: { inner: '[deep_var]' } }, vars);
        expect([...vars]).toContain('deep_var');
    });

    it('extracts from an array of strings', () => {
        const vars = new Set();
        VariableFormatter.extractVariablesFromObject(['[a]', 'plain', '[b]'], vars);
        expect([...vars]).toContain('a');
        expect([...vars]).toContain('b');
    });

    it('extracts from an array of objects', () => {
        const vars = new Set();
        VariableFormatter.extractVariablesFromObject(
            [{ label: '[x]' }, { label: '[y]' }],
            vars,
        );
        expect([...vars]).toContain('x');
        expect([...vars]).toContain('y');
    });

    it('does not recurse infinitely on deeply nested input', () => {
        const vars = new Set();
        let deep = { value: '[leaf]' };
        for (let i = 0; i < 15; i++) deep = { child: deep };
        expect(() => VariableFormatter.extractVariablesFromObject(deep, vars)).not.toThrow();
    });

    it('accumulates into an existing Set', () => {
        const vars = new Set(['existing']);
        VariableFormatter.extractVariablesFromObject('[new_var]', vars);
        expect([...vars]).toContain('existing');
        expect([...vars]).toContain('new_var');
    });
});
