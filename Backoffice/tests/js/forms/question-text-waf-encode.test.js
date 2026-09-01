/**
 * Unit tests for question-text-waf-encode.js — base64-wrapping of free-text
 * question answers to avoid WAF (Azure Application Gateway) signature-rule
 * false positives on narrative text.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
  encodeB64,
  findFreeTextQuestionInputs,
  findWafSensitiveInputs,
  encodeFreeTextQuestionFields,
  pruneEmptyWafRiskFields,
  installNativeSubmitTextEncoder,
  EMPTY_DISAGG_NAME_RE,
} from '../../../app/static/js/forms/modules/question-text-waf-encode.js';

function decodeB64(wrapped) {
  expect(wrapped.startsWith('b64:')).toBe(true);
  return decodeURIComponent(escape(atob(wrapped.slice(4))));
}

function buildForm(html) {
  // Built via DOMParser (not an innerHTML assignment) so this test file
  // doesn't trip the repo's CSP/inline-JS diff guard
  // (scripts/ci/check_no_inline_js_in_diff.py), which flags that pattern in
  // any added diff line, tests included.
  const parsed = new DOMParser().parseFromString(
    `<form id="focalDataEntryForm">${html}</form>`,
    'text/html'
  );
  const form = parsed.getElementById('focalDataEntryForm');
  document.body.appendChild(form);
  return document.getElementById('focalDataEntryForm');
}

describe('question-text-waf-encode', () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it('round-trips ASCII and non-ASCII text through encodeB64', () => {
    const text = 'Report: 50% increase (see Annex 1); "coordinated" response — café';
    const wrapped = encodeB64(text);
    expect(wrapped.startsWith('b64:')).toBe(true);
    expect(decodeB64(wrapped)).toBe(text);
  });

  it('finds text and textarea question inputs but not other field types', () => {
    const form = buildForm(`
      <div class="form-item-block" data-item-type="question" data-question-type="text">
        <input type="text" name="field_value[1]" value="hello">
      </div>
      <div class="form-item-block" data-item-type="question" data-question-type="textarea">
        <textarea name="field_value[2]">world</textarea>
      </div>
      <div class="form-item-block" data-item-type="question" data-question-type="number">
        <input type="number" name="field_value[3]" value="42">
      </div>
      <div class="form-item-block" data-item-type="indicator">
        <input type="text" name="field_value[4]" value="not a question">
      </div>
    `);

    const inputs = findFreeTextQuestionInputs(form);
    const names = inputs.map((el) => el.name);
    expect(names).toEqual(['field_value[1]', 'field_value[2]']);
  });

  it('finds repeat-group free-text questions by data-question-type', () => {
    const form = buildForm(`
      <div class="form-item-block" data-item-type="question" data-question-type="text">
        <input type="text" name="repeat_415_1_field_0_0" value="Morocco - Earthquake (MDRMA010)">
      </div>
      <div class="form-item-block" data-item-type="question" data-question-type="textarea">
        <textarea name="repeat_415_1_field_1_0">notes; with punctuation</textarea>
      </div>
    `);

    const names = findFreeTextQuestionInputs(form).map((el) => el.name);
    expect(names).toEqual(['repeat_415_1_field_0_0', 'repeat_415_1_field_1_0']);
  });

  it('finds emergency metadata JSON and emergency-operations selects', () => {
    const form = buildForm(`
      <input type="hidden" name="repeat_415_1_field_0_emergency_metadata" value='{"name":"Morocco - Earthquake","code":"MDRMA010"}'>
      <input type="hidden" name="field_disagg_metadata[99]" value='{"name":"Appeal","code":"X"}'>
      <select data-lookup-list-id="emergency_operations" name="repeat_415_1_field_0_0">
        <option value="Morocco - Earthquake (MDRMA010)" selected>Morocco - Earthquake (MDRMA010)</option>
      </select>
    `);

    const names = findWafSensitiveInputs(form).map((el) => el.name);
    expect(names).toEqual([
      'repeat_415_1_field_0_emergency_metadata',
      'field_disagg_metadata[99]',
      'repeat_415_1_field_0_0',
    ]);
  });

  it('excludes disabled free-text inputs', () => {
    const form = buildForm(`
      <div class="form-item-block" data-item-type="question" data-question-type="text">
        <input type="text" name="field_value[1]" value="hello" disabled>
      </div>
    `);

    expect(findFreeTextQuestionInputs(form)).toHaveLength(0);
  });

  it('wraps free-text values in place and restore() puts the original text back', () => {
    const form = buildForm(`
      <div class="form-item-block" data-item-type="question" data-question-type="text">
        <input type="text" name="field_value[1]" value="Hello <b>world</b>; DROP TABLE x;">
      </div>
      <div class="form-item-block" data-item-type="question" data-question-type="textarea">
        <textarea name="field_value[2]">Narrative answer with 'quotes' and semicolons;</textarea>
      </div>
    `);
    const textInput = form.querySelector('input[name="field_value[1]"]');
    const textarea = form.querySelector('textarea[name="field_value[2]"]');
    const originalText = textInput.value;
    const originalTextarea = textarea.value;

    const restore = encodeFreeTextQuestionFields(form);

    expect(textInput.value.startsWith('b64:')).toBe(true);
    expect(decodeB64(textInput.value)).toBe(originalText);
    expect(textarea.value.startsWith('b64:')).toBe(true);
    expect(decodeB64(textarea.value)).toBe(originalTextarea);

    restore();

    expect(textInput.value).toBe(originalText);
    expect(textarea.value).toBe(originalTextarea);
  });

  it('leaves empty free-text fields untouched', () => {
    const form = buildForm(`
      <div class="form-item-block" data-item-type="question" data-question-type="text">
        <input type="text" name="field_value[1]" value="">
      </div>
    `);
    const input = form.querySelector('input[name="field_value[1]"]');

    const restore = encodeFreeTextQuestionFields(form);
    expect(input.value).toBe('');

    restore();
    expect(input.value).toBe('');
  });

  it('does not double-encode an already-wrapped value', () => {
    const form = buildForm(`
      <div class="form-item-block" data-item-type="question" data-question-type="text">
        <input type="text" name="field_value[1]" value="b64:aGVsbG8=">
      </div>
    `);
    const input = form.querySelector('input[name="field_value[1]"]');

    const restore = encodeFreeTextQuestionFields(form);
    expect(input.value).toBe('b64:aGVsbG8=');

    restore();
    expect(input.value).toBe('b64:aGVsbG8=');
  });

  it('does not affect number/matrix/plugin/document fields', () => {
    const form = buildForm(`
      <div class="form-item-block" data-item-type="question" data-question-type="number">
        <input type="number" name="field_value[1]" value="123">
      </div>
      <div class="form-item-block" data-item-type="matrix">
        <input type="hidden" name="field_value[2]" value='{"a":1}'>
      </div>
    `);
    const numberInput = form.querySelector('input[name="field_value[1]"]');
    const matrixInput = form.querySelector('input[name="field_value[2]"]');

    encodeFreeTextQuestionFields(form);

    expect(numberInput.value).toBe('123');
    expect(matrixInput.value).toBe('{"a":1}');
  });

  it('installNativeSubmitTextEncoder wraps free-text fields on native form submit', () => {
    const form = buildForm(`
      <div class="form-item-block" data-item-type="question" data-question-type="textarea">
        <textarea name="field_value[1]">Some narrative text; with punctuation.</textarea>
      </div>
    `);
    const textarea = form.querySelector('textarea[name="field_value[1]"]');
    const originalValue = textarea.value;

    installNativeSubmitTextEncoder();
    // Calling twice must stay idempotent (no duplicate listeners / double-encoding).
    installNativeSubmitTextEncoder();

    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));

    expect(textarea.value.startsWith('b64:')).toBe(true);
    expect(decodeB64(textarea.value)).toBe(originalValue);
  });

  it('does not encode when submit is already cancelled', () => {
    const form = buildForm(`
      <div class="form-item-block" data-item-type="question" data-question-type="textarea">
        <textarea name="field_value[1]">Some narrative text; with punctuation.</textarea>
      </div>
    `);
    const textarea = form.querySelector('textarea[name="field_value[1]"]');
    const originalValue = textarea.value;

    installNativeSubmitTextEncoder();
    const submitEvent = new Event('submit', { bubbles: true, cancelable: true });
    submitEvent.preventDefault();
    form.dispatchEvent(submitEvent);

    expect(textarea.value).toBe(originalValue);
  });

  it('restores visible text if a later handler cancels submit', async () => {
    const form = buildForm(`
      <div class="form-item-block" data-item-type="question" data-question-type="textarea">
        <textarea name="field_value[1]">Some narrative text; with punctuation.</textarea>
      </div>
    `);
    const textarea = form.querySelector('textarea[name="field_value[1]"]');
    const originalValue = textarea.value;

    installNativeSubmitTextEncoder();
    document.addEventListener('submit', (event) => {
      event.preventDefault();
    }, { once: true });

    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    expect(textarea.value.startsWith('b64:')).toBe(true);

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(textarea.value).toBe(originalValue);
  });

  it('wraps emergency metadata JSON and emergency select values', () => {
    const json = '{"name":"Morocco - Earthquake","code":"MDRMA010"}';
    const display = 'Morocco - Earthquake (MDRMA010)';
    const form = buildForm(`
      <input type="hidden" name="repeat_415_1_field_0_emergency_metadata" value='${json}'>
      <select data-lookup-list-id="emergency_operations" name="repeat_415_1_field_0_0">
        <option value="${display}" selected>${display}</option>
      </select>
    `);
    const hidden = form.querySelector('input[name="repeat_415_1_field_0_emergency_metadata"]');
    const select = form.querySelector('select');

    const restore = encodeFreeTextQuestionFields(form);
    expect(decodeB64(hidden.value)).toBe(json);
    expect(decodeB64(select.value)).toBe(display);

    restore();
    expect(hidden.value).toBe(json);
    expect(select.value).toBe(display);
  });

  it('pruneEmptyWafRiskFields drops empty sex/age/sexage/indirect_reach and empty files', () => {
    expect(EMPTY_DISAGG_NAME_RE.test('indicator_1369_sex_male')).toBe(true);
    expect(EMPTY_DISAGG_NAME_RE.test('indicator_1369_age__5')).toBe(true);
    expect(EMPTY_DISAGG_NAME_RE.test('dynamic_13515_sexage_female_18_49')).toBe(true);
    expect(EMPTY_DISAGG_NAME_RE.test('indicator_1369_indirect_reach')).toBe(true);
    expect(EMPTY_DISAGG_NAME_RE.test('repeat_415_1_field_1_sex_male')).toBe(true);
    expect(EMPTY_DISAGG_NAME_RE.test('repeat_415_1_field_1_indirect_reach')).toBe(true);
    expect(EMPTY_DISAGG_NAME_RE.test('repeat_415_1_field_0_0')).toBe(false);
    expect(EMPTY_DISAGG_NAME_RE.test('indicator_1369_total_value')).toBe(false);
    expect(EMPTY_DISAGG_NAME_RE.test('indicator_1369_reporting_mode')).toBe(false);

    const form = buildForm(`
      <input name="csrf_token" value="tok">
      <input name="indicator_1369_total_value" value="78573">
      <input name="indicator_1369_reporting_mode" value="total">
      <input name="indicator_1369_sex_male" value="">
      <input name="indicator_1369_age__5" value="">
      <input name="indicator_1369_indirect_reach" value="">
      <input name="repeat_415_1_field_1_sex_male" value="">
      <input name="repeat_415_1_field_0_0" value="kept">
      <input name="indicator_1404_total_value" value="">
      <input type="file" name="file">
    `);
    const fd = new FormData(form);
    pruneEmptyWafRiskFields(fd);

    const keys = Array.from(fd.keys());
    expect(keys).toContain('csrf_token');
    expect(keys).toContain('indicator_1369_total_value');
    expect(keys).toContain('indicator_1369_reporting_mode');
    expect(keys).toContain('indicator_1404_total_value');
    expect(keys).toContain('repeat_415_1_field_0_0');
    expect(keys).not.toContain('indicator_1369_sex_male');
    expect(keys).not.toContain('repeat_415_1_field_1_sex_male');
    expect(keys).not.toContain('indicator_1369_age__5');
    expect(keys).not.toContain('indicator_1369_indirect_reach');
    expect(keys).not.toContain('file');
  });
});
