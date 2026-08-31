/**
 * Unit tests for question-text-waf-encode.js — base64-wrapping of free-text
 * question answers to avoid WAF (Azure Application Gateway) signature-rule
 * false positives on narrative text.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
  encodeB64,
  findFreeTextQuestionInputs,
  encodeFreeTextQuestionFields,
  installNativeSubmitTextEncoder,
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

    const submitEvent = new Event('submit', { bubbles: true, cancelable: true });
    submitEvent.preventDefault();
    form.dispatchEvent(submitEvent);

    expect(textarea.value.startsWith('b64:')).toBe(true);
    expect(decodeB64(textarea.value)).toBe(originalValue);
  });
});
