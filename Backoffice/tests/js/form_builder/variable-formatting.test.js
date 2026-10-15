/**
 * Tests for app/static/js/form_builder/modules/variables/variable-formatting.js
 *
 * VariableFormatter.formatVariablesInText, extractVariables, and
 * extractVariablesFromObject are pure logic functions that require only
 * jsdom for DOMParser (used internally by formatVariablesInText).
 */
import { describe, it, expect, beforeEach } from 'vitest';
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

// ---------------------------------------------------------------------------
// displayMatrixVariables
// ---------------------------------------------------------------------------

function mountMatrixRow({ itemId = 5, defined = ['fr_sp1'], hidden = false } = {}) {
    document.body.replaceChildren();
    const row = document.createElement('p');
    row.className = 'mb-1 matrix-variables-row';
    row.dataset.itemId = String(itemId);
    if (hidden) row.style.display = 'none';

    const heading = document.createElement('strong');
    heading.textContent = 'Variables:';
    const list = document.createElement('span');
    list.className = 'matrix-variables-list';
    defined.forEach((name) => {
        const chip = document.createElement('span');
        chip.className = 'variable-formatted';
        chip.dataset.variableName = name;
        chip.textContent = `[${name}]`;
        list.appendChild(chip);
    });
    row.append(heading, list);
    document.body.appendChild(row);
    return row;
}

function mountItemsData(items) {
    const data = document.createElement('script');
    data.id = 'all-template-items-data';
    data.type = 'application/json';
    data.textContent = JSON.stringify(items);
    document.body.appendChild(data);
}

describe('VariableFormatter.displayMatrixVariables', () => {
    beforeEach(() => {
        window.builtInMetadataVariables = [
            { key: 'assignment_year', label: 'Assignment Year' },
        ];
        window.pluginLabelVariables = [
            { key: 'EO1', label: 'Emergency operation' },
        ];
    });

    it('puts a system token on the same row, outlined, without a second heading', () => {
        const row = mountMatrixRow({ defined: ['fr_sp1', 'fr_sp2'] });
        mountItemsData([{
            id: 5,
            item_type: 'matrix',
            config: {
                matrix_config: {
                    columns: [
                        { name: 'SP1_[assignment_year]', is_variable: true, variable: 'fr_sp1' },
                        { name: 'SP2', is_variable: true, variable: 'fr_sp2' },
                    ],
                },
            },
        }]);

        VariableFormatter.displayMatrixVariables();

        expect(document.querySelectorAll('strong')).toHaveLength(1);
        expect(row.querySelector('ul')).toBeNull();
        expect(row.style.display).not.toBe('none');

        const names = [...row.querySelectorAll('[data-variable-name]')].map((el) => el.dataset.variableName);
        expect(names).toEqual(['fr_sp1', 'fr_sp2', 'assignment_year']);

        const system = row.querySelector('[data-variable-name="assignment_year"]');
        expect(system.classList.contains('variable-system')).toBe(true);
        expect(system.title).toBe('Assignment Year');
        expect(row.querySelector('[data-variable-name="fr_sp1"]').classList.contains('variable-system')).toBe(false);
    });

    it('does not duplicate column variables already rendered on the row', () => {
        mountMatrixRow({ defined: ['fr_sp1'] });
        mountItemsData([{
            id: 5,
            item_type: 'matrix',
            config: {
                matrix_config: {
                    columns: [{ name: '[fr_sp1] total', is_variable: true, variable: 'fr_sp1' }],
                },
            },
        }]);

        VariableFormatter.displayMatrixVariables();
        VariableFormatter.displayMatrixVariables();

        const matches = document.querySelectorAll('[data-variable-name="fr_sp1"]');
        expect(matches).toHaveLength(1);
    });

    it('shows the row when the only token is a system variable', () => {
        const row = mountMatrixRow({ defined: [], hidden: true });
        mountItemsData([{
            id: 5,
            item_type: 'matrix',
            config: {
                matrix_config: {
                    columns: [{ name: 'Year [[assignment_year]+1]' }],
                },
            },
        }]);

        VariableFormatter.displayMatrixVariables();

        expect(row.style.display).not.toBe('none');
        const chips = row.querySelectorAll('[data-variable-name]');
        expect(chips).toHaveLength(1);
        expect(chips[0].dataset.variableName).toBe('assignment_year');
        expect(chips[0].classList.contains('variable-system')).toBe(true);
    });

    it('keeps a referenced template variable in the filled style', () => {
        mountMatrixRow({ defined: [] , hidden: true });
        mountItemsData([{
            id: 5,
            item_type: 'matrix',
            config: {
                matrix_config: {
                    columns: [{ name: 'From [planned_total]' }],
                },
            },
        }]);

        VariableFormatter.displayMatrixVariables();

        const chip = document.querySelector('[data-variable-name="planned_total"]');
        expect(chip).not.toBeNull();
        expect(chip.classList.contains('variable-system')).toBe(false);
        expect(chip.className).toContain('bg-purple-100');
    });

    it('styles plugin label tokens like system variables', () => {
        mountMatrixRow({ defined: [], hidden: true });
        mountItemsData([{
            id: 5,
            item_type: 'matrix',
            config: { matrix_config: { columns: [{ name: '[EO1]' }] } },
        }]);

        VariableFormatter.displayMatrixVariables();

        const chip = document.querySelector('[data-variable-name="EO1"]');
        expect(chip.classList.contains('variable-system')).toBe(true);
        expect(chip.title).toBe('Emergency operation');
    });
});
