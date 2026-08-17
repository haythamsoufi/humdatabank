/**
 * Unit tests for data-availability.js (DNA / NA field disabling).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugWarn: vi.fn(),
}));

function ensureCssEscape() {
  if (!globalThis.CSS) {
    globalThis.CSS = {};
  }
  if (typeof globalThis.CSS.escape !== 'function') {
    globalThis.CSS.escape = (ident) => String(ident).replace(/[^a-zA-Z0-9_\-]/g, (ch) => `\\${ch}`);
  }
}

async function loadDataAvailability() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/data-availability.js');
}

function setupIndicatorForm({ dna = false, na = false, value = '99' } = {}) {
  document.body.innerHTML = `
    <div id="entry-form-ui">
      <div class="form-item-block" data-item-id="12">
        <input name="indicator_12_total_value" value="${value}">
        <input type="radio" name="indicator_12_reporting_mode" value="total" checked>
        <input type="checkbox" name="indicator_12_data_not_available" ${dna ? 'checked' : ''}>
        <input type="checkbox" name="indicator_12_not_applicable" ${na ? 'checked' : ''}>
      </div>
    </div>`;
}

function setupRepeatForm({ dna = false, na = false, value = '42' } = {}) {
  document.body.innerHTML = `
    <div id="entry-form-ui">
      <div class="form-item-block" data-item-id="23">
        <input name="repeat_23_1_field_0_value" value="${value}">
        <input type="checkbox" name="repeat_23_1_field_0_data_not_available" ${dna ? 'checked' : ''}>
        <input type="checkbox" name="repeat_23_1_field_0_not_applicable" ${na ? 'checked' : ''}>
      </div>
    </div>`;
}

function setupDynamicForm({ dna = false, na = false, value = '7' } = {}) {
  document.body.innerHTML = `
    <div id="entry-form-ui">
      <div class="form-item-block" data-item-id="pending_xyz">
        <input name="dynamic_pending_xyz_value" value="${value}">
        <input type="checkbox" name="dynamic_pending_xyz_data_not_available" ${dna ? 'checked' : ''}>
        <input type="checkbox" name="dynamic_pending_xyz_not_applicable" ${na ? 'checked' : ''}>
      </div>
    </div>`;
}

function setChecked(el, checked) {
  el.checked = checked;
  el.dispatchEvent(new Event('change', { bubbles: true }));
}

function valueInput(name) {
  return document.querySelector(`input[name="${name}"]`);
}

function expectDisabledCleared(input) {
  expect(input.disabled).toBe(true);
  expect(input.value).toBe('');
  expect(input.getAttribute('data-availability-disabled')).toBe('true');
}

function expectEnabled(input, { value } = {}) {
  expect(input.disabled).toBe(false);
  expect(input.hasAttribute('data-availability-disabled')).toBe(false);
  if (value !== undefined) {
    expect(input.value).toBe(value);
  }
}

describe('data-availability', () => {
  beforeEach(() => {
    ensureCssEscape();
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('init with both checked unchecks NA, keeps DNA, and clears+disables the value', async () => {
    setupIndicatorForm({ dna: true, na: true });
    const { initDataAvailability } = await loadDataAvailability();
    initDataAvailability();

    expect(valueInput('indicator_12_data_not_available').checked).toBe(true);
    expect(valueInput('indicator_12_not_applicable').checked).toBe(false);
    expectDisabledCleared(valueInput('indicator_12_total_value'));
  });

  it('init with DNA checked clears, disables, and sets data-availability-disabled', async () => {
    setupIndicatorForm({ dna: true });
    const { initDataAvailability } = await loadDataAvailability();
    initDataAvailability();

    expectDisabledCleared(valueInput('indicator_12_total_value'));
    expect(valueInput('indicator_12_data_not_available').checked).toBe(true);
  });

  it('init with neither checked preserves value and leaves the input enabled', async () => {
    setupIndicatorForm({ value: '99' });
    const { initDataAvailability } = await loadDataAvailability();
    initDataAvailability();

    expectEnabled(valueInput('indicator_12_total_value'), { value: '99' });
    expect(valueInput('indicator_12_reporting_mode').checked).toBe(true);
    expect(valueInput('indicator_12_reporting_mode').disabled).toBe(false);
  });

  it('checking DNA clears the value, disables the field, and unchecks NA', async () => {
    setupIndicatorForm({ na: true, value: '99' });
    const { initDataAvailability } = await loadDataAvailability();
    initDataAvailability();

    expect(valueInput('indicator_12_not_applicable').checked).toBe(true);
    expectDisabledCleared(valueInput('indicator_12_total_value'));

    valueInput('indicator_12_total_value').value = 'restored';
    setChecked(valueInput('indicator_12_data_not_available'), true);

    expect(valueInput('indicator_12_not_applicable').checked).toBe(false);
    expect(valueInput('indicator_12_data_not_available').checked).toBe(true);
    expectDisabledCleared(valueInput('indicator_12_total_value'));
  });

  it('checking NA unchecks DNA and disables the field', async () => {
    setupIndicatorForm({ dna: true, value: '99' });
    const { initDataAvailability } = await loadDataAvailability();
    initDataAvailability();

    expect(valueInput('indicator_12_data_not_available').checked).toBe(true);

    setChecked(valueInput('indicator_12_not_applicable'), true);

    expect(valueInput('indicator_12_data_not_available').checked).toBe(false);
    expect(valueInput('indicator_12_not_applicable').checked).toBe(true);
    expectDisabledCleared(valueInput('indicator_12_total_value'));
  });

  it('unchecking DNA with NA off re-enables the input', async () => {
    setupIndicatorForm({ dna: true, value: '99' });
    const { initDataAvailability } = await loadDataAvailability();
    initDataAvailability();

    expectDisabledCleared(valueInput('indicator_12_total_value'));

    setChecked(valueInput('indicator_12_data_not_available'), false);

    expectEnabled(valueInput('indicator_12_total_value'));
    expect(valueInput('indicator_12_data_not_available').checked).toBe(false);
  });

  it('unchecking DNA while NA is still checked leaves the field disabled', async () => {
    setupIndicatorForm({ na: true, value: '99' });
    const { initDataAvailability } = await loadDataAvailability();
    initDataAvailability();

    const dna = valueInput('indicator_12_data_not_available');
    dna.checked = true;
    setChecked(dna, false);

    expect(valueInput('indicator_12_not_applicable').checked).toBe(true);
    expectDisabledCleared(valueInput('indicator_12_total_value'));
  });

  it('leaves DNA and NA checkboxes enabled when the value field is disabled', async () => {
    setupIndicatorForm({ dna: true });
    const { initDataAvailability } = await loadDataAvailability();
    initDataAvailability();

    expectDisabledCleared(valueInput('indicator_12_total_value'));
    expect(valueInput('indicator_12_data_not_available').disabled).toBe(false);
    expect(valueInput('indicator_12_not_applicable').disabled).toBe(false);
    expect(valueInput('indicator_12_data_not_available').hasAttribute('data-availability-disabled')).toBe(false);
    expect(valueInput('indicator_12_not_applicable').hasAttribute('data-availability-disabled')).toBe(false);
  });

  it('repeat_ naming disables and clears the value in the same form-item-block', async () => {
    setupRepeatForm({ dna: true, value: '42' });
    const { initDataAvailability } = await loadDataAvailability();
    initDataAvailability();

    expectDisabledCleared(valueInput('repeat_23_1_field_0_value'));

    setChecked(valueInput('repeat_23_1_field_0_data_not_available'), false);
    expectEnabled(valueInput('repeat_23_1_field_0_value'));

    setChecked(valueInput('repeat_23_1_field_0_not_applicable'), true);
    expect(valueInput('repeat_23_1_field_0_data_not_available').checked).toBe(false);
    expectDisabledCleared(valueInput('repeat_23_1_field_0_value'));
  });

  it('dynamic_pending_ naming disables and clears the value when DNA is checked', async () => {
    setupDynamicForm({ value: '7' });
    const { initDataAvailability } = await loadDataAvailability();
    initDataAvailability();

    expectEnabled(valueInput('dynamic_pending_xyz_value'), { value: '7' });

    setChecked(valueInput('dynamic_pending_xyz_data_not_available'), true);

    expectDisabledCleared(valueInput('dynamic_pending_xyz_value'));
    expect(valueInput('dynamic_pending_xyz_not_applicable').checked).toBe(false);

    setChecked(valueInput('dynamic_pending_xyz_not_applicable'), true);
    expect(valueInput('dynamic_pending_xyz_data_not_available').checked).toBe(false);
    expectDisabledCleared(valueInput('dynamic_pending_xyz_value'));
  });

  it('repeatEntryAdded unchecks DNA on the new container and re-enables inputs', async () => {
    setupRepeatForm({ dna: true, na: true, value: '42' });
    const { initDataAvailability } = await loadDataAvailability();
    initDataAvailability();

    expect(valueInput('repeat_23_1_field_0_data_not_available').checked).toBe(true);
    expectDisabledCleared(valueInput('repeat_23_1_field_0_value'));

    const container = document.querySelector('#entry-form-ui');
    document.dispatchEvent(new CustomEvent('repeatEntryAdded', { detail: { container } }));

    expect(valueInput('repeat_23_1_field_0_data_not_available').checked).toBe(false);
    expect(valueInput('repeat_23_1_field_0_not_applicable').checked).toBe(false);
    expectEnabled(valueInput('repeat_23_1_field_0_value'));
  });

  it('init with only NA checked clears and disables the value', async () => {
    setupIndicatorForm({ na: true, value: '99' });
    const { initDataAvailability } = await loadDataAvailability();
    initDataAvailability();

    expect(valueInput('indicator_12_not_applicable').checked).toBe(true);
    expect(valueInput('indicator_12_data_not_available').checked).toBe(false);
    expectDisabledCleared(valueInput('indicator_12_total_value'));
  });

  it('checking DNA from a clean form clears the value and disables the field', async () => {
    setupIndicatorForm({ value: '99' });
    const { initDataAvailability } = await loadDataAvailability();
    initDataAvailability();

    setChecked(valueInput('indicator_12_data_not_available'), true);

    expect(valueInput('indicator_12_not_applicable').checked).toBe(false);
    expectDisabledCleared(valueInput('indicator_12_total_value'));
  });
});
