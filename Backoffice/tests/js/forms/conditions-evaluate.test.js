/**
 * Decision-logic tests for evaluateConditions (entry-form relevance).
 *
 * Uses real field-management / form-item-utils against DOM fixtures.
 * Does not cover initConditions, CSS injection, or plugin-readiness waits.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugWarn: vi.fn(),
  debugError: vi.fn(),
}));

async function loadConditions() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/conditions.js');
}

function questionBlockHtml(id, value = '', { prefix = 'question' } = {}) {
  const itemId = `${prefix}_${id}`;
  return `
    <div class="form-item-block" data-item-id="${itemId}">
      <input id="field-${itemId}" name="field_value[${id}]" value="${value}">
    </div>`;
}

function yesNoBlockHtml(id, { prefix = 'question', checked } = {}) {
  const itemId = `${prefix}_${id}`;
  // After numeric IDs are rewritten to question_<id> / indicator_<id>,
  // getYesNoCheckboxValue looks up field_value[<prefixedId>] or
  // indicator_<numericId>_standard_value — not field_value[<bare id>].
  const name = prefix === 'indicator'
    ? `indicator_${id}_standard_value`
    : `field_value[${itemId}]`;
  const yesChecked = checked === 'yes' ? 'checked' : '';
  const noChecked = checked === 'no' ? 'checked' : '';
  return `
    <div class="form-item-block" data-item-id="${itemId}">
      <input type="checkbox" name="${name}" value="yes" ${yesChecked}>
      <input type="checkbox" name="${name}" value="no" ${noChecked}>
    </div>`;
}

function numericQuestionBlockHtml(id, value = '', { prefix = 'question' } = {}) {
  const itemId = `${prefix}_${id}`;
  // Mirrors what numeric-formatting.js does to a type="number" input once it has
  // been blurred: swap to type="text", mark data-numeric="true", and (for values
  // >= 1000) render thousands separators, e.g. "1200" -> "1,200".
  return `
    <div class="form-item-block" data-item-id="${itemId}">
      <input id="field-${itemId}" name="field_value[${id}]" data-numeric="true" value="${value}">
    </div>`;
}

function payload(conditions, logic = 'AND') {
  return { logic, conditions };
}

function cond(itemId, conditionType, value, extra = {}) {
  return { item_id: itemId, condition_type: conditionType, value, ...extra };
}

function resetWindowState() {
  document.body.innerHTML = '';
  delete window.existingData;
  delete window.metadataContext;
  delete window.__ifrcPluginVariables;
}

describe('evaluateConditions', () => {
  beforeEach(() => {
    resetWindowState();
  });

  afterEach(() => {
    resetWindowState();
    delete window.requestRelevanceRecheck;
    delete window.checkAllRelevanceConditions;
    delete window.checkFieldRelevance;
    delete window.clearFieldValues;
    delete window.loadSavedFieldValues;
    delete window.collectHiddenFieldsForSubmission;
    delete window.debugFieldValue;
    delete window.__ifrcConditionsIsClearing;
    delete window.__ifrcConditionsReady;
  });

  describe('defaults and parse behaviour', () => {
    it('returns true for an invalid JSON string (default visible)', async () => {
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions('{not-json')).toBe(true);
      expect(evaluateConditions('not json at all')).toBe(true);
    });

    it('returns true when conditions is null or missing', async () => {
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions({ conditions: null })).toBe(true);
      expect(evaluateConditions({ logic: 'AND' })).toBe(true);
    });

    it('returns true for an empty conditions array under AND (every of empty is true)', async () => {
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([], 'AND'))).toBe(true);
      expect(evaluateConditions(payload([]))).toBe(true);
    });

    it('returns false for an unknown condition type', async () => {
      document.body.innerHTML = questionBlockHtml(10, '42');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'not_a_real_type', '42')]))).toBe(false);
    });

    it('accepts a JSON string payload the same as an object', async () => {
      document.body.innerHTML = questionBlockHtml(10, '42');
      const { evaluateConditions } = await loadConditions();
      const obj = payload([cond(10, 'equals', '42')]);
      expect(evaluateConditions(obj)).toBe(true);
      expect(evaluateConditions(JSON.stringify(obj))).toBe(true);
    });

    it('unwraps a double-encoded JSON string and evaluates it', async () => {
      document.body.innerHTML = questionBlockHtml(10, '99');
      const { evaluateConditions } = await loadConditions();
      const inner = JSON.stringify(payload([cond(10, 'equals', '42')]));
      const doubleEncoded = JSON.stringify(inner);
      expect(evaluateConditions(doubleEncoded)).toBe(false);
      document.body.innerHTML = questionBlockHtml(10, '42');
      expect(evaluateConditions(doubleEncoded)).toBe(true);
    });
  });

  describe('AND / OR logic', () => {
    it('AND is true when every equals condition matches', async () => {
      document.body.innerHTML = questionBlockHtml(10, 'a') + questionBlockHtml(11, 'b');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([
        cond(10, 'equals', 'a'),
        cond(11, 'equals', 'b'),
      ], 'AND'))).toBe(true);
    });

    it('AND is false when one equals condition fails', async () => {
      document.body.innerHTML = questionBlockHtml(10, 'a') + questionBlockHtml(11, 'nope');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([
        cond(10, 'equals', 'a'),
        cond(11, 'equals', 'b'),
      ], 'AND'))).toBe(false);
    });

    it('OR is true when one condition matches', async () => {
      document.body.innerHTML = questionBlockHtml(10, 'a') + questionBlockHtml(11, 'nope');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([
        cond(10, 'equals', 'a'),
        cond(11, 'equals', 'b'),
      ], 'OR'))).toBe(true);
    });

    it('OR is false when every condition fails', async () => {
      document.body.innerHTML = questionBlockHtml(10, 'x') + questionBlockHtml(11, 'y');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([
        cond(10, 'equals', 'a'),
        cond(11, 'equals', 'b'),
      ], 'OR'))).toBe(false);
    });
  });

  describe('numeric item_id prefix resolution', () => {
    it('resolves numeric item_id 10 (and "10") to data-item-id="question_10"', async () => {
      document.body.innerHTML = questionBlockHtml(10, '42');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'equals', '42')]))).toBe(true);
      expect(evaluateConditions(payload([cond('10', 'equals', '42')]))).toBe(true);
      expect(evaluateConditions(payload([cond(10, 'equals', '99')]))).toBe(false);
    });

    it('resolves numeric item_id to indicator_10 when question_ is absent', async () => {
      document.body.innerHTML = questionBlockHtml(10, '99', { prefix: 'indicator' });
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'equals', '99')]))).toBe(true);
    });

    // Entry form renders data-item-id="{{ field.id }}" (bare number) and
    // name="indicator_<id>_total_value". Defaulting that to question_<id> made
    // getCurrentFieldValue miss the input, so greater_than/less_than always
    // compared null and validation fired even when the rule was satisfied.
    it('reads indicator_<id>_total_value even when a leftover #field-<id> exists', async () => {
      document.body.innerHTML = `
        <div id="field-961"></div>
        <div class="form-item-block" data-item-id="961" data-item-type="indicator">
          <input name="indicator_961_total_value" id="indicator-total-961" data-numeric="true" value="12">
        </div>
        <div id="field-963"></div>
        <div class="form-item-block" data-item-id="963" data-item-type="indicator">
          <input name="indicator_963_total_value" id="indicator-total-963" data-numeric="true" value="123">
        </div>`;
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([
        cond(961, 'less_than', null, { value_field_id: 963 }),
      ]))).toBe(true);
      expect(evaluateConditions(payload([
        cond(963, 'greater_than', null, { value_field_id: 961 }),
      ]))).toBe(true);
    });

    it('resolves numeric item_id to a bare data-item-id (entry form)', async () => {
      document.body.innerHTML = `
        <div class="form-item-block" data-item-id="961">
          <input name="indicator_961_total_value" value="500">
        </div>
        <div class="form-item-block" data-item-id="963">
          <input name="indicator_963_total_value" value="1200">
        </div>`;
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([
        cond(961, 'less_than', null, { value_field_id: 963 }),
      ]))).toBe(true);
      expect(evaluateConditions(payload([
        cond(963, 'greater_than', null, { value_field_id: 961 }),
      ]))).toBe(true);
    });

    it('keeps a numeric id when a .plugin-field-container[data-field-id] exists', async () => {
      // getDataAttributeValue reads data-operations-count (then data-count / data-value / …)
      // from [data-field-id="<id>"]. Prefix conversion is skipped so fieldId stays "10".
      document.body.innerHTML = `
        <div class="plugin-field-container" data-field-id="10" data-operations-count="7"></div>`;
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'equals', '7')]))).toBe(true);
      expect(evaluateConditions(payload([cond(10, 'greater_than', '5')]))).toBe(true);
    });
  });

  describe('is_empty / is_not_empty', () => {
    it('is_empty is true for an empty input', async () => {
      document.body.innerHTML = questionBlockHtml(10, '');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'is_empty')]))).toBe(true);
    });

    it('is_empty is false for the string "0"', async () => {
      document.body.innerHTML = questionBlockHtml(10, '0');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'is_empty')]))).toBe(false);
    });

    it('is_empty is false for numeric 0 from a plugin variable', async () => {
      window.__ifrcPluginVariables = { ZERO: 0 };
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond('[ZERO]', 'is_empty')]))).toBe(false);
      expect(evaluateConditions(payload([cond('var:ZERO', 'is_empty')]))).toBe(false);
    });

    it('is_empty is false for a type=number input of 0', async () => {
      document.body.innerHTML = `
        <div class="form-item-block" data-item-id="question_10">
          <input id="field-question_10" type="number" name="field_value[10]" value="0">
        </div>`;
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'is_empty')]))).toBe(false);
      expect(evaluateConditions(payload([cond(10, 'is_not_empty')]))).toBe(true);
      expect(evaluateConditions(payload([cond(10, 'equals', '0')]))).toBe(true);
      expect(evaluateConditions(payload([cond(10, 'equal_to', 0)]))).toBe(true);
    });

    it('is_empty is true for a whitespace-only string', async () => {
      document.body.innerHTML = questionBlockHtml(10, '');
      document.querySelector('#field-question_10').value = '   ';
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'is_empty')]))).toBe(true);
    });

    it('is_not_empty is the opposite of is_empty', async () => {
      document.body.innerHTML = questionBlockHtml(10, '');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'is_not_empty')]))).toBe(false);

      document.querySelector('#field-question_10').value = '0';
      expect(evaluateConditions(payload([cond(10, 'is_not_empty')]))).toBe(true);

      document.querySelector('#field-question_10').value = '   ';
      expect(evaluateConditions(payload([cond(10, 'is_not_empty')]))).toBe(false);
    });
  });

  describe('equals / not_equals', () => {
    it('equals and equal_to trim both sides before comparing', async () => {
      document.body.innerHTML = questionBlockHtml(10, '');
      document.querySelector('#field-question_10').value = '  hello  ';
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'equals', 'hello')]))).toBe(true);
      expect(evaluateConditions(payload([cond(10, 'equal_to', '  hello')]))).toBe(true);
      expect(evaluateConditions(payload([cond(10, 'equals', 'hello!')]))).toBe(false);
    });

    it('not_equals and not_equal_to are true when trimmed values differ', async () => {
      document.body.innerHTML = questionBlockHtml(10, 'alpha');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'not_equals', 'beta')]))).toBe(true);
      expect(evaluateConditions(payload([cond(10, 'not_equal_to', 'alpha')]))).toBe(false);
      expect(evaluateConditions(payload([cond(10, 'not_equals', '  alpha  ')]))).toBe(false);
    });
  });

  describe('is_yes / is_no', () => {
    it('is_yes is true only when the yes checkbox is checked', async () => {
      document.body.innerHTML = yesNoBlockHtml(10, { checked: 'yes' });
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'is_yes')]))).toBe(true);
      expect(evaluateConditions(payload([cond(10, 'is_no')]))).toBe(false);
    });

    it('is_no is true only when the no checkbox is checked', async () => {
      document.body.innerHTML = yesNoBlockHtml(10, { checked: 'no' });
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'is_no')]))).toBe(true);
      expect(evaluateConditions(payload([cond(10, 'is_yes')]))).toBe(false);
    });

    it('is_yes and is_no are both false when neither box is checked', async () => {
      document.body.innerHTML = yesNoBlockHtml(10, {});
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'is_yes')]))).toBe(false);
      expect(evaluateConditions(payload([cond(10, 'is_no')]))).toBe(false);
    });
  });

  describe('numeric comparisons', () => {
    it('greater_than is true only when actual is strictly greater', async () => {
      document.body.innerHTML = questionBlockHtml(10, '10');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'greater_than', '9')]))).toBe(true);
      expect(evaluateConditions(payload([cond(10, 'greater_than', '10')]))).toBe(false);
    });

    it('less_than is true only when actual is strictly less', async () => {
      document.body.innerHTML = questionBlockHtml(10, '10');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'less_than', '11')]))).toBe(true);
      expect(evaluateConditions(payload([cond(10, 'less_than', '10')]))).toBe(false);
    });

    it('greater_than_or_equal_to includes the equal boundary', async () => {
      document.body.innerHTML = questionBlockHtml(10, '10');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'greater_than_or_equal_to', '10')]))).toBe(true);
      expect(evaluateConditions(payload([cond(10, 'greater_than_or_equal_to', '11')]))).toBe(false);
    });

    it('less_than_or_equal_to includes the equal boundary', async () => {
      document.body.innerHTML = questionBlockHtml(10, '10');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'less_than_or_equal_to', '10')]))).toBe(true);
      expect(evaluateConditions(payload([cond(10, 'less_than_or_equal_to', '9')]))).toBe(false);
    });

    it('numeric comparisons are false when either side is non-numeric', async () => {
      document.body.innerHTML = questionBlockHtml(10, 'abc');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'greater_than', '5')]))).toBe(false);
      expect(evaluateConditions(payload([cond(10, 'less_than', '5')]))).toBe(false);
      expect(evaluateConditions(payload([cond(10, 'greater_than_or_equal_to', '5')]))).toBe(false);
      expect(evaluateConditions(payload([cond(10, 'less_than_or_equal_to', '5')]))).toBe(false);

      document.querySelector('#field-question_10').value = '8';
      expect(evaluateConditions(payload([cond(10, 'greater_than', 'nope')]))).toBe(false);
    });

    // Regression test: numeric-formatting.js renders data-numeric="true" inputs with
    // thousands separators once their value reaches four digits (e.g. "1,200"). A bare
    // parseFloat("1,200") stops at the comma and returns 1, which used to make this
    // condition wrongly evaluate to false even though 1200 > 999.
    it('handles comma-formatted (thousands separator) values correctly', async () => {
      document.body.innerHTML = numericQuestionBlockHtml(10, '1,200');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond(10, 'greater_than', '999')]))).toBe(true);
      expect(evaluateConditions(payload([cond(10, 'less_than', '999')]))).toBe(false);
      expect(evaluateConditions(payload([cond(10, 'equals', '1200')]))).toBe(true);
    });
  });

  describe('value_field_id', () => {
    it('compares field A to field B via value_field_id (5 < 10)', async () => {
      document.body.innerHTML = questionBlockHtml(5, '5') + questionBlockHtml(10, '10');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([
        cond(5, 'less_than', null, { value_field_id: 10 }),
      ]))).toBe(true);
      expect(evaluateConditions(payload([
        cond(5, 'greater_than', null, { value_field_id: 10 }),
      ]))).toBe(false);
      expect(evaluateConditions(payload([
        cond(10, 'greater_than_or_equal_to', null, { value_field_id: 5 }),
      ]))).toBe(true);
    });

    // Regression test for the reported bug: two cross-referencing indicator fields
    // (e.g. item 961 "less_than" value_field_id 963, and its mirror 963 "greater_than"
    // value_field_id 961) where one side's value crosses the 1000 thousands-separator
    // threshold. Before the fix, "1,200" parsed via parseFloat() truncated to 1, so
    // 963 (1200) was never seen as greater_than 961 (500) and the validation rule
    // incorrectly appeared violated.
    it('compares comma-formatted field A to plain field B via value_field_id (500 < 1,200)', async () => {
      document.body.innerHTML =
        numericQuestionBlockHtml(961, '500') + numericQuestionBlockHtml(963, '1,200');
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([
        cond(961, 'less_than', null, { value_field_id: 963 }),
      ]))).toBe(true);
      expect(evaluateConditions(payload([
        cond(963, 'greater_than', null, { value_field_id: 961 }),
      ]))).toBe(true);
    });
  });

  describe('plugin variables', () => {
    it('reads [SOME_VAR] and var:SOME_VAR from window.__ifrcPluginVariables', async () => {
      window.__ifrcPluginVariables = { SOME_VAR: 'hello' };
      const { evaluateConditions } = await loadConditions();
      expect(evaluateConditions(payload([cond('[SOME_VAR]', 'equals', 'hello')]))).toBe(true);
      expect(evaluateConditions(payload([cond('var:SOME_VAR', 'equal_to', 'hello')]))).toBe(true);
      expect(evaluateConditions(payload([cond('[SOME_VAR]', 'equals', 'other')]))).toBe(false);
    });
  });
});
