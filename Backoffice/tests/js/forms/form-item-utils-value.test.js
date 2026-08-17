/**
 * getUnifiedFieldValue must treat 0 as a real value, not "missing".
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugWarn: vi.fn(),
  debugError: vi.fn(),
}));

async function loadUtils() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/form-item-utils.js');
}

describe('getUnifiedFieldValue', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    delete window.existingData;
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.existingData;
  });

  it('returns 0 from a number input instead of falling through to existing data', async () => {
    document.body.innerHTML = `
      <div class="form-item-block" data-item-id="question_10">
        <input id="field-question_10" type="number" name="field_value[10]" value="0">
      </div>`;
    window.existingData = { 'field_value[question_10]': 99 };
    const { getUnifiedFieldValue } = await loadUtils();

    expect(getUnifiedFieldValue('question_10', 'total', true)).toBe(0);
  });

  it('returns 0 from existing data when the DOM input is empty', async () => {
    document.body.innerHTML = `
      <div class="form-item-block" data-item-id="question_10">
        <input id="field-question_10" type="number" name="field_value[10]" value="">
      </div>`;
    window.existingData = { 'field_value[question_10]': 0 };
    const { getUnifiedFieldValue } = await loadUtils();

    expect(getUnifiedFieldValue('question_10', 'total', true)).toBe(0);
  });
});
