/**
 * Unit tests for repeat-sections.js entry limits and select restore.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugWarn: vi.fn(),
  debugError: vi.fn(),
}));

async function loadRepeatSections() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/repeat-sections.js');
}

function optionHtml(options) {
  return options
    .map(({ value, text }) => `<option value="${value}">${text}</option>`)
    .join('');
}

function mountRepeatSection({
  sectionId = 5,
  maxEntries = '2',
  includeOptionLimit = true,
  options = [
    { value: '', text: 'Choose' },
    { value: 'x', text: 'X' },
    { value: 'y', text: 'Y' },
  ],
  maxOtherEntries = '0',
  extraEntriesHtml = '',
} = {}) {
  const maxAttr = maxEntries == null ? '' : `data-max-entries="${maxEntries}"`;
  const limitSelect = includeOptionLimit
    ? `<select data-limit-entries-to-option-count="true" data-field-item-id="47" data-max-other-entries="${maxOtherEntries}">
          ${optionHtml(options)}
        </select>`
    : '';

  document.body.innerHTML = `
    <div id="section-container-${sectionId}" data-section-type="repeat" ${maxAttr}>
      <span id="repeat-limit-text-${sectionId}" class="text-gray-500"></span>
      <div id="repeat-entries-${sectionId}">
        <div class="repeat-entry" data-repeat-instance="1" id="repeat-entry-${sectionId}-1">
          <div class="form-item-block" data-item-id="47">
            <input name="repeat_${sectionId}_1_field_0" value="a">
            ${limitSelect}
          </div>
        </div>
        ${extraEntriesHtml}
      </div>
    </div>`;
}

function mountSelect(attrs = '', options = [
  { value: '', text: 'Choose' },
  { value: 'x', text: 'X' },
  { value: 'y', text: 'Y' },
]) {
  document.body.innerHTML = `<select id="test-select" ${attrs}>${optionHtml(options)}</select>`;
  return document.getElementById('test-select');
}

function stubWindowHelpers() {
  window.showAlert = vi.fn();
  window.t = (k) => k;
  window.REPEAT_SECTION_LABELS = { entry: 'Entry' };
  window.addListenersToRepeatEntry = vi.fn();
  window.cleanupInputValues = vi.fn();
  window.applyUniqueSectionOptions = vi.fn();
}

describe('repeat-sections entries', () => {
  beforeEach(() => {
    stubWindowHelpers();
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.showAlert;
    delete window.t;
    delete window.REPEAT_SECTION_LABELS;
    delete window.addListenersToRepeatEntry;
    delete window.cleanupInputValues;
    delete window.applyUniqueSectionOptions;
    delete window.preserveCalculatedSelectStaleValue;
    delete window.refreshCalculatedSelect;
    delete window.__repeatSectionsInitializing;
  });

  it('getEffectiveRepeatEntryMax uses data-max-entries', async () => {
    mountRepeatSection({ maxEntries: '3', includeOptionLimit: false });
    const { getEffectiveRepeatEntryMax } = await loadRepeatSections();

    expect(getEffectiveRepeatEntryMax(5)).toBe(3);
  });

  it('getEffectiveRepeatEntryMax uses option-count and ignores empty and __other__', async () => {
    mountRepeatSection({
      maxEntries: null,
      options: [
        { value: '', text: 'Choose' },
        { value: 'x', text: 'X' },
        { value: 'y', text: 'Y' },
        { value: '__other__', text: 'Other' },
      ],
    });
    const { getEffectiveRepeatEntryMax } = await loadRepeatSections();

    expect(getEffectiveRepeatEntryMax(5)).toBe(2);
  });

  it('getEffectiveRepeatEntryMax is the min of data-max-entries and option count', async () => {
    mountRepeatSection({ maxEntries: '5' });
    const { getEffectiveRepeatEntryMax } = await loadRepeatSections();

    expect(getEffectiveRepeatEntryMax(5)).toBe(2);

    document.getElementById('section-container-5').setAttribute('data-max-entries', '1');
    expect(getEffectiveRepeatEntryMax(5)).toBe(1);
  });

  it('getEffectiveRepeatEntryMax adds data-max-other-entries to the option count', async () => {
    mountRepeatSection({ maxEntries: null, maxOtherEntries: '2' });
    const { getEffectiveRepeatEntryMax } = await loadRepeatSections();

    expect(getEffectiveRepeatEntryMax(5)).toBe(4);
  });

  it('getEffectiveRepeatEntryMax counts the same data-field-item-id once', async () => {
    mountRepeatSection({
      maxEntries: null,
      options: [
        { value: '', text: 'Choose' },
        { value: 'x', text: 'X' },
        { value: 'y', text: 'Y' },
        { value: 'z', text: 'Z' },
      ],
      extraEntriesHtml: `
        <div class="repeat-entry" data-repeat-instance="2" id="repeat-entry-5-2">
          <div class="form-item-block" data-item-id="47">
            <select data-limit-entries-to-option-count="true" data-field-item-id="47" data-max-other-entries="0">
              <option value="">Choose</option>
              <option value="x">X</option>
            </select>
          </div>
        </div>`,
    });
    const { getEffectiveRepeatEntryMax } = await loadRepeatSections();

    // Second entry has only 1 real option; if the same field-item-id were
    // counted again the min would be 1. First occurrence has 3.
    expect(getEffectiveRepeatEntryMax(5)).toBe(3);
  });

  it('getEffectiveRepeatEntryMax returns null when there is no limit', async () => {
    mountRepeatSection({ maxEntries: null, includeOptionLimit: false });
    const { getEffectiveRepeatEntryMax } = await loadRepeatSections();

    expect(getEffectiveRepeatEntryMax(5)).toBeNull();
  });

  it('updateRepeatLimitText shows current/max under the cap', async () => {
    mountRepeatSection({ maxEntries: '2', includeOptionLimit: false });
    const { updateRepeatLimitText } = await loadRepeatSections();

    updateRepeatLimitText(5);

    const el = document.getElementById('repeat-limit-text-5');
    expect(el.textContent).toBe('Max entries: 1/2');
    expect(el.classList.contains('text-gray-500')).toBe(true);
    expect(el.classList.contains('text-red-600')).toBe(false);
    expect(el.classList.contains('font-semibold')).toBe(false);
  });

  it('updateRepeatLimitText adds the red class when at the cap', async () => {
    mountRepeatSection({ maxEntries: '1', includeOptionLimit: false });
    const { updateRepeatLimitText } = await loadRepeatSections();

    updateRepeatLimitText(5);

    const el = document.getElementById('repeat-limit-text-5');
    expect(el.textContent).toBe('Max entries: 1/1');
    expect(el.classList.contains('text-red-600')).toBe(true);
    expect(el.classList.contains('font-semibold')).toBe(true);
    expect(el.classList.contains('text-gray-500')).toBe(false);
  });

  it('addRepeatEntry under max returns true and creates instance 2', async () => {
    mountRepeatSection();
    const { addRepeatEntry } = await loadRepeatSections();

    const added = addRepeatEntry(5);

    expect(added).toBe(true);
    const second = document.querySelector('.repeat-entry[data-repeat-instance="2"]');
    expect(second).not.toBeNull();
    expect(second.id).toBe('repeat-entry-5-2');
    expect(document.querySelectorAll('#repeat-entries-5 .repeat-entry')).toHaveLength(2);
    expect(document.getElementById('repeat-limit-text-5').textContent).toBe('Max entries: 2/2');
  });

  it('addRepeatEntry at max returns false, alerts, and does not add an entry', async () => {
    mountRepeatSection({ maxEntries: '1' });
    const { addRepeatEntry } = await loadRepeatSections();

    const added = addRepeatEntry(5);

    expect(added).toBe(false);
    expect(window.showAlert).toHaveBeenCalled();
    expect(document.querySelectorAll('#repeat-entries-5 .repeat-entry')).toHaveLength(1);
    expect(document.querySelector('.repeat-entry[data-repeat-instance="2"]')).toBeNull();
  });

  it('addRepeatEntry at max with silent:true does not alert', async () => {
    mountRepeatSection({ maxEntries: '1' });
    const { addRepeatEntry } = await loadRepeatSections();

    const added = addRepeatEntry(5, { silent: true });

    expect(added).toBe(false);
    expect(window.showAlert).not.toHaveBeenCalled();
    expect(document.querySelectorAll('#repeat-entries-5 .repeat-entry')).toHaveLength(1);
  });

  it('setSelectValueWithFallback matches an option value', async () => {
    const select = mountSelect();
    const { setSelectValueWithFallback } = await loadRepeatSections();

    setSelectValueWithFallback(select, 'y');

    expect(select.value).toBe('y');
  });

  it('setSelectValueWithFallback matches an option by text', async () => {
    const select = mountSelect();
    const { setSelectValueWithFallback } = await loadRepeatSections();

    setSelectValueWithFallback(select, 'X');

    expect(select.value).toBe('x');
  });

  it('setSelectValueWithFallback clears the select for empty or falsy values', async () => {
    const select = mountSelect();
    select.value = 'x';
    const { setSelectValueWithFallback } = await loadRepeatSections();

    setSelectValueWithFallback(select, '');
    expect(select.value).toBe('');

    select.value = 'x';
    setSelectValueWithFallback(select, null);
    expect(select.value).toBe('');
  });

  it('setSelectValueWithFallback restores the previous value when unmatched', async () => {
    const select = mountSelect();
    select.value = 'x';
    const { setSelectValueWithFallback } = await loadRepeatSections();

    setSelectValueWithFallback(select, 'not-an-option');

    expect(select.value).toBe('x');
  });

  it('setSelectValueWithFallback restores an unmatched value as Other when allowed', async () => {
    const select = mountSelect('data-allow-other="true"');
    const { setSelectValueWithFallback } = await loadRepeatSections();

    setSelectValueWithFallback(select, 'custom-label');

    expect(select.value).toBe('__other__');
  });

  it('setSelectValueWithFallback preserves a stale calculated-list value', async () => {
    const select = mountSelect('data-options-source="calculated"');
    window.preserveCalculatedSelectStaleValue = vi.fn();
    const { setSelectValueWithFallback } = await loadRepeatSections();

    setSelectValueWithFallback(select, 'stale-op');

    expect(window.preserveCalculatedSelectStaleValue).toHaveBeenCalledWith(select, 'stale-op');
  });

  it('setSelectValueWithFallback coerces {name, code} emergency-operation objects', async () => {
    const select = mountSelect('', [
      { value: '', text: 'Choose' },
      { value: 'Flood (FL-01)', text: 'Flood (FL-01)' },
    ]);
    const { setSelectValueWithFallback } = await loadRepeatSections();

    setSelectValueWithFallback(select, { name: 'Flood', code: 'FL-01' });

    expect(select.value).toBe('Flood (FL-01)');
  });

  it('waitForCalculatedSelectOptions resolves immediately when options already exist', async () => {
    const select = mountSelect();
    window.refreshCalculatedSelect = vi.fn();
    const { waitForCalculatedSelectOptions } = await loadRepeatSections();

    await expect(waitForCalculatedSelectOptions(select, { timeoutMs: 200 })).resolves.toBeUndefined();
    expect(window.refreshCalculatedSelect).not.toHaveBeenCalled();
  });

  it('waitForCalculatedSelectOptions resolves when a second option is added', async () => {
    const select = mountSelect('', [{ value: '', text: 'Choose' }]);
    window.refreshCalculatedSelect = vi.fn();
    const { waitForCalculatedSelectOptions } = await loadRepeatSections();

    const pending = waitForCalculatedSelectOptions(select, { timeoutMs: 500 });
    expect(window.refreshCalculatedSelect).toHaveBeenCalledWith(select);

    const extra = document.createElement('option');
    extra.value = 'x';
    extra.textContent = 'X';
    select.appendChild(extra);

    await expect(pending).resolves.toBeUndefined();
  });
});
