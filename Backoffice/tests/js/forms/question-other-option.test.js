/**
 * Unit tests for question-other-option.js (allow_other single- and multi-choice).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugWarn: vi.fn(),
  debugError: vi.fn(),
}));

const OTHER_SENTINEL = '__other__';

async function loadOtherOption() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/question-other-option.js');
}

function change(el) {
  el.dispatchEvent(new Event('change', { bubbles: true }));
}

function typeInput(el, value) {
  el.value = value;
  el.dispatchEvent(new Event('input', { bubbles: true }));
}

function mountSingleChoice({
  allowOther = true,
  selected = '',
  fieldId = '10',
  otherHidden = true,
  otherValue = '',
  wrapInBlock = true,
  extraSelectAttrs = '',
} = {}) {
  const allowAttr = allowOther ? 'data-allow-other="true"' : '';
  const otherClass = otherHidden ? 'other-text-input hidden' : 'other-text-input';
  const select = `
    <select name="field_value[${fieldId}]" id="field-${fieldId}"
            data-field-item-id="${fieldId}" ${allowAttr} ${extraSelectAttrs}>
      <option value="">Select...</option>
      <option value="alpha">Alpha</option>
      <option value="${OTHER_SENTINEL}">Other (please specify)...</option>
    </select>
    <input type="text"
           name="field_other_text[${fieldId}]"
           id="other-text-${fieldId}"
           class="${otherClass}"
           data-for-field="${fieldId}"
           value="${otherValue}">`;
  document.body.innerHTML = wrapInBlock
    ? `<div class="form-item-block">${select}</div>`
    : select;
  const selectEl = document.querySelector('select');
  if (selected) selectEl.value = selected;
  return {
    select: selectEl,
    otherInput: document.getElementById(`other-text-${fieldId}`),
  };
}

function mountMultiChoice({
  allowOther = true,
  otherChecked = false,
  otherValue = '',
  otherHidden = true,
  fieldId = '20',
  includeOtherCheckbox = true,
} = {}) {
  const allowAttr = allowOther ? 'data-allow-other="true"' : '';
  const otherClass = otherHidden ? 'other-text-input hidden' : 'other-text-input';
  const otherCb = includeOtherCheckbox
    ? `<div class="option-item">
         <label>
           <input type="checkbox" class="other-option-checkbox" ${otherChecked ? 'checked' : ''}>
           <span>Other (please specify)...</span>
         </label>
       </div>`
    : '';
  document.body.innerHTML = `
    <div class="form-item-block">
      <div class="relative" data-field-item-id="${fieldId}" ${allowAttr}>
        <button type="button" class="multi-select-btn">
          <span class="multi-select-text">Select options...</span>
        </button>
        <div class="multi-select-dropdown">
          <div class="option-item">
            <label>
              <input type="checkbox" name="field_value[${fieldId}]" value="red">
              <span>Red</span>
            </label>
          </div>
          ${otherCb}
        </div>
      </div>
      <input type="text"
             name="field_other_text[${fieldId}]"
             id="other-text-${fieldId}"
             class="${otherClass}"
             data-for-field="${fieldId}"
             value="${otherValue}">
    </div>`;
  return {
    wrapper: document.querySelector('[data-field-item-id]'),
    dropdown: document.querySelector('.multi-select-dropdown'),
    otherCheckbox: document.querySelector('.other-option-checkbox'),
    regularCheckbox: document.querySelector('input[value="red"]'),
    otherInput: document.getElementById(`other-text-${fieldId}`),
    textSpan: document.querySelector('.multi-select-text'),
  };
}

describe('question-other-option', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  describe('appendOtherOptionToSelect', () => {
    it('is a no-op unless data-allow-other is true', async () => {
      document.body.innerHTML = `
        <select>
          <option value="alpha">Alpha</option>
        </select>`;
      const select = document.querySelector('select');
      const { appendOtherOptionToSelect } = await loadOtherOption();

      appendOtherOptionToSelect(select);

      expect(select.querySelector(`option[value="${OTHER_SENTINEL}"]`)).toBeNull();
      expect(select.options.length).toBe(1);
    });

    it('appends an Other option using the sentinel value', async () => {
      document.body.innerHTML = `
        <select data-allow-other="true">
          <option value="alpha">Alpha</option>
        </select>`;
      const select = document.querySelector('select');
      const { appendOtherOptionToSelect } = await loadOtherOption();

      appendOtherOptionToSelect(select);

      const opt = select.querySelector(`option[value="${OTHER_SENTINEL}"]`);
      expect(opt).not.toBeNull();
      expect(opt.value).toBe(OTHER_SENTINEL);
      expect(opt.textContent).toBe('Other (please specify)...');
    });

    it('is idempotent and will not duplicate the Other option', async () => {
      document.body.innerHTML = `
        <select data-allow-other="true">
          <option value="alpha">Alpha</option>
        </select>`;
      const select = document.querySelector('select');
      const { appendOtherOptionToSelect } = await loadOtherOption();

      appendOtherOptionToSelect(select);
      appendOtherOptionToSelect(select);

      expect(select.querySelectorAll(`option[value="${OTHER_SENTINEL}"]`)).toHaveLength(1);
    });
  });

  describe('appendOtherOptionToMultiDropdown', () => {
    it('is a no-op without a [data-allow-other=true] wrapper', async () => {
      document.body.innerHTML = `<div class="multi-select-dropdown"></div>`;
      const dropdown = document.querySelector('.multi-select-dropdown');
      const { appendOtherOptionToMultiDropdown } = await loadOtherOption();

      appendOtherOptionToMultiDropdown(dropdown);

      expect(dropdown.querySelector('.other-option-checkbox')).toBeNull();
    });

    it('appends an Other checkbox when the wrapper allows it', async () => {
      const { dropdown } = mountMultiChoice({ includeOtherCheckbox: false });
      const { appendOtherOptionToMultiDropdown } = await loadOtherOption();

      appendOtherOptionToMultiDropdown(dropdown);

      const cb = dropdown.querySelector('.other-option-checkbox');
      expect(cb).not.toBeNull();
      expect(cb.type).toBe('checkbox');
      expect(cb.nextElementSibling.textContent).toBe('Other (please specify)...');
    });

    it('is a no-op when .other-option-checkbox is already present', async () => {
      const { dropdown } = mountMultiChoice({ includeOtherCheckbox: true });
      const { appendOtherOptionToMultiDropdown } = await loadOtherOption();

      appendOtherOptionToMultiDropdown(dropdown);

      expect(dropdown.querySelectorAll('.other-option-checkbox')).toHaveLength(1);
    });
  });

  describe('restoreOtherSelectionForCalculatedList', () => {
    it('is a no-op when savedValue is empty or allow_other is off', async () => {
      const { select, otherInput } = mountSingleChoice({
        allowOther: false,
        otherHidden: true,
      });
      // strip the sentinel so we can see whether restore appended it
      select.querySelector(`option[value="${OTHER_SENTINEL}"]`)?.remove();
      const { restoreOtherSelectionForCalculatedList } = await loadOtherOption();

      restoreOtherSelectionForCalculatedList(select, '');
      restoreOtherSelectionForCalculatedList(select, 'custom');

      expect(select.value).not.toBe(OTHER_SENTINEL);
      expect(otherInput.classList.contains('hidden')).toBe(true);
      expect(otherInput.value).toBe('');
    });

    it('sets the select to the sentinel, fills the other input, and unhides it', async () => {
      const { select, otherInput } = mountSingleChoice({
        allowOther: true,
        otherHidden: true,
        otherValue: '',
      });
      const { restoreOtherSelectionForCalculatedList } = await loadOtherOption();

      restoreOtherSelectionForCalculatedList(select, 'my custom value');

      expect(select.value).toBe(OTHER_SENTINEL);
      expect(otherInput.value).toBe('my custom value');
      expect(otherInput.classList.contains('hidden')).toBe(false);
    });

    it('finds the other input by data-field-item-id when it is not in a form-item-block', async () => {
      document.body.innerHTML = `
        <select data-allow-other="true" data-field-item-id="99">
          <option value="alpha">Alpha</option>
        </select>
        <input id="other-text-99" class="other-text-input hidden" value="">`;
      const select = document.querySelector('select');
      const otherInput = document.getElementById('other-text-99');
      const { restoreOtherSelectionForCalculatedList } = await loadOtherOption();

      restoreOtherSelectionForCalculatedList(select, 'via field id');

      expect(select.value).toBe(OTHER_SENTINEL);
      expect(otherInput.value).toBe('via field id');
      expect(otherInput.classList.contains('hidden')).toBe(false);
    });

    it('finds the other input via the field id in the select name', async () => {
      document.body.innerHTML = `
        <select data-allow-other="true" name="field_value[77]">
          <option value="alpha">Alpha</option>
        </select>
        <input id="other-text-77" class="other-text-input hidden" value="">`;
      const select = document.querySelector('select');
      const otherInput = document.getElementById('other-text-77');
      const { restoreOtherSelectionForCalculatedList } = await loadOtherOption();

      restoreOtherSelectionForCalculatedList(select, 'via name');

      expect(select.value).toBe(OTHER_SENTINEL);
      expect(otherInput.value).toBe('via name');
      expect(otherInput.classList.contains('hidden')).toBe(false);
    });
  });

  describe('initQuestionOtherOption', () => {
    it('shows the other text input when Other is selected', async () => {
      const { select, otherInput } = mountSingleChoice({
        allowOther: true,
        otherHidden: true,
      });
      const { initQuestionOtherOption } = await loadOtherOption();
      initQuestionOtherOption();

      select.value = OTHER_SENTINEL;
      change(select);

      expect(otherInput.classList.contains('hidden')).toBe(false);
    });

    it('hides and clears the other text input when a regular option is selected', async () => {
      const { select, otherInput } = mountSingleChoice({
        allowOther: true,
        selected: OTHER_SENTINEL,
        otherHidden: false,
        otherValue: 'typed earlier',
      });
      const { initQuestionOtherOption } = await loadOtherOption();
      initQuestionOtherOption();

      select.value = 'alpha';
      change(select);

      expect(otherInput.classList.contains('hidden')).toBe(true);
      expect(otherInput.value).toBe('');
    });

    it('does not reveal the other input when the select does not allow Other', async () => {
      const { select, otherInput } = mountSingleChoice({
        allowOther: false,
        otherHidden: true,
      });
      const { initQuestionOtherOption } = await loadOtherOption();
      initQuestionOtherOption();

      select.value = OTHER_SENTINEL;
      change(select);

      expect(otherInput.classList.contains('hidden')).toBe(true);
    });

    it('shows the other text input when the multi-choice Other checkbox is checked', async () => {
      const { otherCheckbox, otherInput } = mountMultiChoice({
        otherChecked: false,
        otherHidden: true,
      });
      const { initQuestionOtherOption } = await loadOtherOption();
      initQuestionOtherOption();

      otherCheckbox.checked = true;
      change(otherCheckbox);

      expect(otherInput.classList.contains('hidden')).toBe(false);
    });

    it('hides and clears the other text input when the multi-choice Other checkbox is unchecked', async () => {
      const { otherCheckbox, otherInput } = mountMultiChoice({
        otherChecked: true,
        otherHidden: false,
        otherValue: 'something else',
      });
      const { initQuestionOtherOption } = await loadOtherOption();
      initQuestionOtherOption();

      otherCheckbox.checked = false;
      change(otherCheckbox);

      expect(otherInput.classList.contains('hidden')).toBe(true);
      expect(otherInput.value).toBe('');
    });

    it('refreshes the multi-select button text from a pre-checked Other value on init', async () => {
      const { textSpan } = mountMultiChoice({
        otherChecked: true,
        otherHidden: false,
        otherValue: 'Custom colour',
      });
      const { initQuestionOtherOption } = await loadOtherOption();

      initQuestionOtherOption();

      expect(textSpan.textContent).toBe('Custom colour');
    });

    it('updates the multi-select button when Other text is typed', async () => {
      const { otherCheckbox, otherInput, textSpan, regularCheckbox } = mountMultiChoice({
        otherChecked: true,
        otherHidden: false,
        otherValue: '',
      });
      regularCheckbox.checked = true;
      const { initQuestionOtherOption } = await loadOtherOption();
      initQuestionOtherOption();

      typeInput(otherInput, 'Teal');

      expect(textSpan.textContent).toBe('Red, Teal');
      expect(otherCheckbox.checked).toBe(true);
    });
  });
});
