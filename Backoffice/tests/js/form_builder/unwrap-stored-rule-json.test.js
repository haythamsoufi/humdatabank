import { describe, it, expect } from 'vitest';
import { unwrapStoredRuleJson } from '../../../app/static/js/form_builder/modules/rules/form-serialization.js';

const rule = {
  logic: 'AND',
  conditions: [{ item_id: 'assignment_period', condition_type: 'equal_to', value: '2026' }],
};

describe('unwrapStoredRuleJson', () => {
  it('returns empty for blank or empty-condition payloads', () => {
    expect(unwrapStoredRuleJson('')).toBe('');
    expect(unwrapStoredRuleJson('null')).toBe('');
    expect(unwrapStoredRuleJson('{}')).toBe('');
    expect(unwrapStoredRuleJson(JSON.stringify({ logic: 'AND', conditions: [] }))).toBe('');
  });

  it('keeps a normal rule JSON string', () => {
    expect(JSON.parse(unwrapStoredRuleJson(JSON.stringify(rule)))).toEqual(rule);
  });

  it('unwraps a JSON string of a JSON string', () => {
    const doubleEncoded = JSON.stringify(JSON.stringify(rule));
    expect(JSON.parse(unwrapStoredRuleJson(doubleEncoded))).toEqual(rule);
  });
});
