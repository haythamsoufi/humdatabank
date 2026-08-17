/**
 * Unit tests for multi-select.js (dropdown open/close and checkbox labels).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
}));

import { initMultiSelect } from '../../../app/static/js/forms/modules/multi-select.js';

function optionItem(name, value, label, { checked = false } = {}) {
  return `
    <div class="option-item">
      <label class="inline-flex items-center cursor-pointer w-full">
        <input type="checkbox"
               name="${name}"
               value="${value}"
               class="form-checkbox h-4 w-4 text-green-600 border-gray-300 rounded focus:ring-green-500"
               ${checked ? 'checked' : ''}>
        <span class="ml-2 text-sm text-gray-700">${label}</span>
      </label>
    </div>`;
}

function mountMultiSelect({
  fieldId = '42',
  options = [
    { value: 'alpha', label: 'Alpha' },
    { value: 'bravo', label: 'Bravo' },
  ],
  checked = [],
  disabled = false,
  availabilityDisabled = false,
  extraFields = '',
} = {}) {
  const name = `field_value[${fieldId}]`;
  const optionHtml = options
    .map((opt) => optionItem(name, opt.value, opt.label, { checked: checked.includes(opt.value) }))
    .join('');
  document.body.innerHTML = `
    <div class="relative mt-2" id="field-${fieldId}" data-field-item-id="${fieldId}">
      <button type="button"
              class="multi-select-btn"
              data-field-id="${fieldId}"
              ${disabled ? 'disabled' : ''}
              ${availabilityDisabled ? 'data-availability-disabled="true"' : ''}>
        <span class="multi-select-text">Select options...</span>
      </button>
      <div class="multi-select-dropdown hidden" data-field-id="${fieldId}">
        ${optionHtml}
      </div>
    </div>
    ${extraFields}`;
}

function secondFieldHtml(fieldId = '99') {
  return `
    <div class="relative mt-2" id="field-${fieldId}" data-field-item-id="${fieldId}">
      <button type="button" class="multi-select-btn" data-field-id="${fieldId}">
        <span class="multi-select-text">Select options...</span>
      </button>
      <div class="multi-select-dropdown hidden" data-field-id="${fieldId}">
        ${optionItem(`field_value[${fieldId}]`, 'x', 'X-ray')}
      </div>
    </div>`;
}

function buttonFor(fieldId) {
  return document.querySelector(`.multi-select-btn[data-field-id="${fieldId}"]`);
}

function dropdownFor(fieldId) {
  return document.querySelector(`.multi-select-dropdown[data-field-id="${fieldId}"]`);
}

function buttonText(fieldId) {
  return buttonFor(fieldId).querySelector('.multi-select-text').textContent;
}

describe('initMultiSelect', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('sets the button label from already-checked options on init', () => {
    mountMultiSelect({ checked: ['alpha'] });
    initMultiSelect();
    expect(buttonText('42')).toBe('Alpha');
  });

  it('opens a hidden dropdown on button click and closes it on a second click', () => {
    mountMultiSelect();
    initMultiSelect();

    const btn = buttonFor('42');
    const dropdown = dropdownFor('42');
    expect(dropdown.classList.contains('hidden')).toBe(true);

    btn.click();
    expect(dropdown.classList.contains('hidden')).toBe(false);
    expect(dropdown.style.position).toBe('fixed');
    expect(dropdown.style.zIndex).toBe('9999');

    btn.click();
    expect(dropdown.classList.contains('hidden')).toBe(true);
  });

  it('closes an open dropdown when clicking outside', () => {
    mountMultiSelect();
    initMultiSelect();

    buttonFor('42').click();
    expect(dropdownFor('42').classList.contains('hidden')).toBe(false);

    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    expect(dropdownFor('42').classList.contains('hidden')).toBe(true);
  });

  it('does not close the dropdown when clicking inside it', () => {
    mountMultiSelect();
    initMultiSelect();

    buttonFor('42').click();
    const checkbox = dropdownFor('42').querySelector('input[type="checkbox"]');
    checkbox.dispatchEvent(new MouseEvent('click', { bubbles: true }));

    expect(dropdownFor('42').classList.contains('hidden')).toBe(false);
  });

  it('closes other dropdowns when opening a second field', () => {
    mountMultiSelect({ extraFields: secondFieldHtml('99') });
    initMultiSelect();

    buttonFor('42').click();
    expect(dropdownFor('42').classList.contains('hidden')).toBe(false);

    buttonFor('99').click();
    expect(dropdownFor('42').classList.contains('hidden')).toBe(true);
    expect(dropdownFor('99').classList.contains('hidden')).toBe(false);
  });

  it('updates the button label when checkboxes change', () => {
    mountMultiSelect();
    initMultiSelect();
    expect(buttonText('42')).toBe('Select options...');

    const [alpha, bravo] = dropdownFor('42').querySelectorAll('input[type="checkbox"]');
    alpha.checked = true;
    alpha.dispatchEvent(new Event('change', { bubbles: true }));
    expect(buttonText('42')).toBe('Alpha');
    expect(alpha.checked).toBe(true);
    expect(alpha.name).toBe('field_value[42]');
    expect(alpha.value).toBe('alpha');

    bravo.checked = true;
    bravo.dispatchEvent(new Event('change', { bubbles: true }));
    expect(buttonText('42')).toBe('Alpha, Bravo');

    alpha.checked = false;
    alpha.dispatchEvent(new Event('change', { bubbles: true }));
    expect(buttonText('42')).toBe('Bravo');

    bravo.checked = false;
    bravo.dispatchEvent(new Event('change', { bubbles: true }));
    expect(buttonText('42')).toBe('Select options...');
  });

  it('does not open a disabled button', () => {
    mountMultiSelect({ disabled: true });
    initMultiSelect();

    buttonFor('42').click();
    expect(dropdownFor('42').classList.contains('hidden')).toBe(true);
  });

  it('does not open a data-availability-disabled button and reverts checkbox changes', () => {
    mountMultiSelect({ availabilityDisabled: true });
    initMultiSelect();

    buttonFor('42').click();
    expect(dropdownFor('42').classList.contains('hidden')).toBe(true);

    const checkbox = dropdownFor('42').querySelector('input[type="checkbox"]');
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event('change', { bubbles: true }));
    expect(checkbox.checked).toBe(false);
    expect(buttonText('42')).toBe('Select options...');
  });

  it('re-initializes button labels after repeatEntryAdded', () => {
    mountMultiSelect();
    initMultiSelect();
    expect(buttonText('42')).toBe('Select options...');

    const checkbox = dropdownFor('42').querySelector('input[value="bravo"]');
    checkbox.checked = true;
    document.dispatchEvent(new CustomEvent('repeatEntryAdded'));
    expect(buttonText('42')).toBe('Bravo');
  });
});
