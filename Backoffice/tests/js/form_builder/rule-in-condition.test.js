import { describe, it, expect, beforeEach } from 'vitest';
import { RuleBuilder } from '../../../app/static/js/form_builder/modules/rules/conditions.js';

const NAMES = [
  { name: 'Bangladesh', iso3: 'BGD' },
  { name: 'Indonesia', iso3: 'IDN' },
  { name: 'Pakistan', iso3: 'PAK' },
  { name: 'Syrian Arab Republic', iso3: 'SYR' },
];

describe('RuleBuilder country membership', () => {
  beforeEach(() => {
    RuleBuilder._setCountryCatalog(null);
  });

  it('collapses an OR of country equals into one is-in list of names', () => {
    RuleBuilder._setCountryCatalog(NAMES);
    const text = RuleBuilder.parseRuleToText(JSON.stringify({
      logic: 'OR',
      conditions: [
        { item_id: 'country_iso', condition_type: 'equal_to', value: 'BGD' },
        { item_id: 'country_iso', condition_type: 'equal_to', value: 'IDN' },
        { item_id: 'country_iso', condition_type: 'equal_to', value: 'SYR' },
      ],
    }));
    expect(text).toBe('Country is in {Bangladesh, Indonesia, Syrian Arab Republic}');
    expect(text).not.toMatch(/ISO|BGD|IDN|SYR/);
  });

  it('keeps a single country equals as equals, using the country name', () => {
    RuleBuilder._setCountryCatalog(NAMES);
    const text = RuleBuilder.parseRuleToText(JSON.stringify({
      logic: 'OR',
      conditions: [
        { item_id: 'country_iso', condition_type: 'equal_to', value: 'BGD' },
      ],
    }));
    expect(text).toBe('Country equals "Bangladesh"');
  });

  it('formats a stored in-list with country names', () => {
    RuleBuilder._setCountryCatalog(NAMES);
    const text = RuleBuilder.parseRuleToText({
      logic: 'OR',
      conditions: [
        { item_id: 'country_iso', condition_type: 'in', value: ['PAK', 'SYR'] },
      ],
    });
    expect(text).toBe('Country is in {Pakistan, Syrian Arab Republic}');
  });

  it('does not show ISO codes before country names are known', () => {
    const text = RuleBuilder.parseRuleToText({
      logic: 'OR',
      conditions: [
        { item_id: 'country_iso', condition_type: 'in', value: ['PAK', 'SYR'] },
      ],
    });
    expect(text).toBe('Country is in 2 countries');
  });
});
