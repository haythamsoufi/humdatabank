/**
 * Unit tests for checkbox-handlers.js (yes/no mutual exclusivity and clear signals).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
}));

async function loadCheckboxHandlers() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/checkbox-handlers.js');
}

function setupYesNoPair() {
  document.body.innerHTML = `
    <form id="entry-form">
      <input type="checkbox" name="field_value[10]" value="yes">
      <input type="checkbox" name="field_value[10]" value="no">
    </form>`;
  window.t = (k) => k;
  window.requestRelevanceRecheck = vi.fn();
}

function yesBox() {
  return document.querySelector('input[name="field_value[10]"][value="yes"]');
}

function noBox() {
  return document.querySelector('input[name="field_value[10]"][value="no"]');
}

function clearFieldInput() {
  return document.querySelector('input[name="field_value[10]_clear_field"]');
}

describe('checkbox-handlers', () => {
  beforeEach(() => {
    setupYesNoPair();
  });

  afterEach(() => {
    delete window.requestRelevanceRecheck;
    delete window.checkAllRelevanceConditions;
    delete window.__ifrcConditionsIsClearing;
    delete window.handleYesNoCheckbox;
    delete window.handleYesNoUncheck;
    delete window.t;
    document.body.innerHTML = '';
  });

  it('handleYesNoCheckbox unchecks the other box with the same name', async () => {
    const { handleYesNoCheckbox } = await loadCheckboxHandlers();
    noBox().checked = true;
    yesBox().checked = true;

    handleYesNoCheckbox(yesBox(), 'field_value[10]');

    expect(yesBox().checked).toBe(true);
    expect(noBox().checked).toBe(false);
  });

  it('handleYesNoCheckbox removes the clear_field input when a box is checked', async () => {
    const { handleYesNoCheckbox } = await loadCheckboxHandlers();
    const clear = document.createElement('input');
    clear.type = 'hidden';
    clear.name = 'field_value[10]_clear_field';
    clear.value = 'CLEAR_FIELD_VALUE';
    yesBox().after(clear);
    yesBox().checked = true;

    handleYesNoCheckbox(yesBox(), 'field_value[10]');

    expect(clearFieldInput()).toBeNull();
  });

  it('handleYesNoCheckbox requests relevance recheck on a microtask', async () => {
    const { handleYesNoCheckbox } = await loadCheckboxHandlers();
    yesBox().checked = true;

    handleYesNoCheckbox(yesBox(), 'field_value[10]');

    expect(window.requestRelevanceRecheck).not.toHaveBeenCalled();
    await Promise.resolve();
    expect(window.requestRelevanceRecheck).toHaveBeenCalledWith('yesno:check');
  });

  it('handleYesNoUncheck inserts CLEAR_FIELD_VALUE after the box when none remain checked', async () => {
    const { handleYesNoUncheck } = await loadCheckboxHandlers();
    yesBox().checked = false;
    noBox().checked = false;

    handleYesNoUncheck(yesBox(), 'field_value[10]');

    const clear = clearFieldInput();
    expect(clear).not.toBeNull();
    expect(clear.type).toBe('hidden');
    expect(clear.value).toBe('CLEAR_FIELD_VALUE');
    expect(yesBox().nextSibling).toBe(clear);
  });

  it('handleYesNoUncheck does not insert a clear signal if another box is still checked', async () => {
    const { handleYesNoUncheck } = await loadCheckboxHandlers();
    yesBox().checked = false;
    noBox().checked = true;

    handleYesNoUncheck(yesBox(), 'field_value[10]');

    expect(clearFieldInput()).toBeNull();
  });

  it('handleYesNoUncheck skips recheck while conditions are clearing', async () => {
    const { handleYesNoUncheck } = await loadCheckboxHandlers();
    window.__ifrcConditionsIsClearing = true;
    yesBox().checked = false;
    noBox().checked = false;

    handleYesNoUncheck(yesBox(), 'field_value[10]');
    await Promise.resolve();

    expect(window.requestRelevanceRecheck).not.toHaveBeenCalled();
    expect(clearFieldInput()).not.toBeNull();
  });

  it('handleYesNoUncheck requests relevance recheck on a microtask', async () => {
    const { handleYesNoUncheck } = await loadCheckboxHandlers();
    yesBox().checked = false;
    noBox().checked = false;

    handleYesNoUncheck(yesBox(), 'field_value[10]');

    expect(window.requestRelevanceRecheck).not.toHaveBeenCalled();
    await Promise.resolve();
    expect(window.requestRelevanceRecheck).toHaveBeenCalledWith('yesno:uncheck');
  });

  it('initCheckboxHandlers enforces exclusivity when a field_value yes/no box is checked', async () => {
    const { initCheckboxHandlers } = await loadCheckboxHandlers();
    initCheckboxHandlers();
    noBox().checked = true;

    yesBox().checked = true;
    yesBox().dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();

    expect(yesBox().checked).toBe(true);
    expect(noBox().checked).toBe(false);
    expect(clearFieldInput()).toBeNull();
    expect(window.requestRelevanceRecheck).toHaveBeenCalledWith('yesno:check');
  });

  it('initCheckboxHandlers inserts a clear signal when the last yes/no box is unchecked', async () => {
    const { initCheckboxHandlers } = await loadCheckboxHandlers();
    initCheckboxHandlers();
    yesBox().checked = true;

    yesBox().checked = false;
    yesBox().dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();

    const clear = clearFieldInput();
    expect(clear).not.toBeNull();
    expect(clear.value).toBe('CLEAR_FIELD_VALUE');
    expect(window.requestRelevanceRecheck).toHaveBeenCalledWith('yesno:uncheck');
  });

  it('initCheckboxHandlers ignores checkboxes that are not yes/no field values', async () => {
    document.body.innerHTML = `
      <form>
        <input type="checkbox" name="other_flag" value="yes">
        <input type="checkbox" name="field_value[10]" value="maybe">
      </form>`;
    const { initCheckboxHandlers } = await loadCheckboxHandlers();
    initCheckboxHandlers();

    const other = document.querySelector('input[name="other_flag"]');
    other.checked = true;
    other.dispatchEvent(new Event('change', { bubbles: true }));
    const maybe = document.querySelector('input[value="maybe"]');
    maybe.checked = true;
    maybe.dispatchEvent(new Event('change', { bubbles: true }));
    await Promise.resolve();

    expect(window.requestRelevanceRecheck).not.toHaveBeenCalled();
  });
});
