/**
 * Unit tests for unique-section-options.js (one choice per section).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
}));

async function loadUniqueSectionOptions() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/unique-section-options.js');
}

function optionMarkup(value, label, { stale = false } = {}) {
  const staleAttr = stale ? ' data-stale-saved-value="true"' : '';
  return `<option value="${value}"${staleAttr}>${label}</option>`;
}

function setupTwoSelects({ firstValue = '', secondValue = '', secondStale = false } = {}) {
  document.body.innerHTML = `
    <div id="section-container-5">
      <select id="unique-first" data-unique-options-in-section="true" data-field-item-id="7">
        ${optionMarkup('', '')}
        ${optionMarkup('A', 'Option A')}
        ${optionMarkup('B', 'Option B')}
      </select>
      <div id="unique-second-scope">
        <select id="unique-second" data-unique-options-in-section="true" data-field-item-id="7">
          ${optionMarkup('', '')}
          ${optionMarkup('A', 'Option A', { stale: secondStale })}
          ${optionMarkup('B', 'Option B')}
        </select>
      </div>
    </div>`;
  document.getElementById('unique-first').value = firstValue;
  document.getElementById('unique-second').value = secondValue;
  window.t = (k) => k;
}

function firstSelect() {
  return document.getElementById('unique-first');
}

function secondSelect() {
  return document.getElementById('unique-second');
}

function optionByValue(select, value) {
  return Array.from(select.options).find((opt) => opt.value === value);
}

function multiOptionHtml(value, { checked = false } = {}) {
  const checkedAttr = checked ? ' checked' : '';
  return `
    <div class="option-item">
      <input type="checkbox" value="${value}"${checkedAttr}>
    </div>`;
}

function setupTwoMultiSelects({ firstChecked = [], secondChecked = [] } = {}) {
  const firstBoxes = ['A', 'B'].map((v) => multiOptionHtml(v, { checked: firstChecked.includes(v) })).join('');
  const secondBoxes = ['A', 'B'].map((v) => multiOptionHtml(v, { checked: secondChecked.includes(v) })).join('');
  document.body.innerHTML = `
    <div id="section-container-5">
      <div id="multi-first" data-unique-options-in-section="true" data-field-item-id="7" data-options-source="choices">
        <div class="multi-select-dropdown">${firstBoxes}</div>
      </div>
      <div id="multi-second-scope">
        <div id="multi-second" data-unique-options-in-section="true" data-field-item-id="7" data-options-source="choices">
          <div class="multi-select-dropdown">${secondBoxes}</div>
        </div>
      </div>
    </div>`;
  window.t = (k) => k;
}

function multiCheckbox(wrapperId, value) {
  return document.querySelector(`#${wrapperId} .option-item input[type="checkbox"][value="${value}"]`);
}

describe('unique-section-options', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    window.t = (k) => k;
  });

  afterEach(() => {
    vi.useRealTimers();
    delete window.applyUniqueSectionOptions;
    delete window.t;
    document.body.innerHTML = '';
  });

  it('disables and hides option A on the second select when the first has A', async () => {
    setupTwoSelects({ firstValue: 'A' });
    const { applyUniqueSectionOptions } = await loadUniqueSectionOptions();

    applyUniqueSectionOptions(document.getElementById('section-container-5'));

    const taken = optionByValue(secondSelect(), 'A');
    expect(taken.disabled).toBe(true);
    expect(taken.hidden).toBe(true);
    expect(optionByValue(secondSelect(), 'B').disabled).toBe(false);
    expect(optionByValue(firstSelect(), 'A').disabled).toBe(false);
  });

  it('clears the second select when it already has A and dispatches change', async () => {
    setupTwoSelects({ firstValue: 'A', secondValue: 'A' });
    const { applyUniqueSectionOptions } = await loadUniqueSectionOptions();
    const onChange = vi.fn();
    secondSelect().addEventListener('change', onChange);

    applyUniqueSectionOptions(document.getElementById('unique-second-scope'));

    expect(secondSelect().value).toBe('');
    expect(onChange).toHaveBeenCalled();
    expect(firstSelect().value).toBe('A');
  });

  it('keeps a stale saved value enabled and does not clear it', async () => {
    setupTwoSelects({ firstValue: 'A', secondValue: 'A', secondStale: true });
    const { applyUniqueSectionOptions } = await loadUniqueSectionOptions();
    const onChange = vi.fn();
    secondSelect().addEventListener('change', onChange);

    applyUniqueSectionOptions(document.getElementById('unique-second-scope'));

    const stale = optionByValue(secondSelect(), 'A');
    expect(secondSelect().value).toBe('A');
    expect(stale.disabled).toBe(false);
    expect(stale.hidden).toBe(false);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('hides and disables a multi-select option that is taken elsewhere', async () => {
    setupTwoMultiSelects({ firstChecked: ['A'] });
    const { applyUniqueSectionOptions } = await loadUniqueSectionOptions();

    applyUniqueSectionOptions(document.getElementById('section-container-5'));

    const taken = multiCheckbox('multi-second', 'A');
    expect(taken.disabled).toBe(true);
    expect(taken.closest('.option-item').style.display).toBe('none');
    expect(multiCheckbox('multi-second', 'B').disabled).toBe(false);
    expect(multiCheckbox('multi-first', 'A').disabled).toBe(false);
  });

  it('unchecks a multi-select option that is taken and already checked', async () => {
    setupTwoMultiSelects({ firstChecked: ['A'], secondChecked: ['A'] });
    const { applyUniqueSectionOptions } = await loadUniqueSectionOptions();

    applyUniqueSectionOptions(document.getElementById('multi-second-scope'));

    const taken = multiCheckbox('multi-second', 'A');
    expect(taken.checked).toBe(false);
    expect(taken.disabled).toBe(true);
    expect(taken.closest('.option-item').style.display).toBe('none');
    expect(multiCheckbox('multi-first', 'A').checked).toBe(true);
  });

  it('initUniqueSectionOptions re-applies uniqueness when a select changes', async () => {
    setupTwoSelects();
    const { initUniqueSectionOptions } = await loadUniqueSectionOptions();
    initUniqueSectionOptions();

    firstSelect().value = 'A';
    firstSelect().dispatchEvent(new Event('change', { bubbles: true }));

    const taken = optionByValue(secondSelect(), 'A');
    expect(taken.disabled).toBe(true);
    expect(taken.hidden).toBe(true);
  });

  it('initUniqueSectionOptions applies unique options after repeatEntryAdded', async () => {
    vi.useFakeTimers();
    setupTwoSelects({ firstValue: 'A' });
    const { initUniqueSectionOptions } = await loadUniqueSectionOptions();
    initUniqueSectionOptions();

    const container = document.createElement('div');
    container.innerHTML = `
      <select data-unique-options-in-section="true" data-field-item-id="7">
        <option value=""></option>
        <option value="A">Option A</option>
        <option value="B">Option B</option>
      </select>`;
    document.getElementById('section-container-5').appendChild(container);

    document.dispatchEvent(new CustomEvent('repeatEntryAdded', { detail: { container } }));
    vi.advanceTimersByTime(0);

    const added = optionByValue(container.querySelector('select'), 'A');
    expect(added.disabled).toBe(true);
    expect(added.hidden).toBe(true);
  });
});
