/**
 * Unit tests for formatting.js (thousands-separator overlay on number inputs).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
}));

async function loadFormatting() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/formatting.js');
}

describe('formatting', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  describe('formatNumberWithCommas / removeCommas', () => {
    it('inserts thousands separators and preserves decimals', async () => {
      const { formatNumberWithCommas } = await loadFormatting();

      expect(formatNumberWithCommas('1234')).toBe('1,234');
      expect(formatNumberWithCommas('1234567')).toBe('1,234,567');
      expect(formatNumberWithCommas('1234567.89')).toBe('1,234,567.89');
      expect(formatNumberWithCommas(1000)).toBe('1,000');
    });

    it('returns empty string for falsy values', async () => {
      const { formatNumberWithCommas, removeCommas } = await loadFormatting();

      expect(formatNumberWithCommas('')).toBe('');
      expect(formatNumberWithCommas(null)).toBe('');
      expect(formatNumberWithCommas(undefined)).toBe('');
      expect(formatNumberWithCommas(0)).toBe('');
      expect(removeCommas('')).toBe('');
      expect(removeCommas(null)).toBe('');
    });

    it('strips commas from formatted strings', async () => {
      const { removeCommas } = await loadFormatting();

      expect(removeCommas('1,234')).toBe('1234');
      expect(removeCommas('1,234,567.89')).toBe('1234567.89');
    });
  });

  describe('setupNumberInputFormatting', () => {
    it('wraps the input and adds a formatted overlay', async () => {
      const { setupNumberInputFormatting } = await loadFormatting();
      document.body.innerHTML = '<input type="number" id="n" value="">';
      const input = document.getElementById('n');

      setupNumberInputFormatting(input);

      const container = input.closest('.number-input-container');
      expect(container).toBeTruthy();
      expect(container.contains(input)).toBe(true);
      expect(container.querySelector('.formatted-number')).toBeTruthy();
    });

    it('hides the overlay when the value is empty', async () => {
      const { setupNumberInputFormatting } = await loadFormatting();
      document.body.innerHTML = '<input type="number" id="n" value="">';
      const input = document.getElementById('n');

      setupNumberInputFormatting(input);

      const overlay = input.parentElement.querySelector('.formatted-number');
      expect(overlay.textContent).toBe('');
      expect(overlay.style.display).toBe('none');
    });

    it('shows comma-formatted value on blur and hides overlay on focus', async () => {
      const { setupNumberInputFormatting } = await loadFormatting();
      document.body.innerHTML = '<input type="number" id="n" value="1234567">';
      const input = document.getElementById('n');

      setupNumberInputFormatting(input);

      const overlay = input.parentElement.querySelector('.formatted-number');
      expect(overlay.textContent).toBe('1,234,567');
      expect(overlay.style.display).toBe('flex');

      input.focus();
      expect(overlay.style.display).toBe('none');

      input.blur();
      expect(overlay.style.display).toBe('flex');
      expect(overlay.textContent).toBe('1,234,567');
    });

    it('does not re-init when already inside .number-input-container', async () => {
      const { setupNumberInputFormatting } = await loadFormatting();
      document.body.innerHTML = `
        <div class="number-input-container">
          <input type="number" id="n" value="1000">
        </div>`;
      const input = document.getElementById('n');
      const originalParent = input.parentElement;

      setupNumberInputFormatting(input);

      expect(input.parentElement).toBe(originalParent);
      expect(originalParent.querySelectorAll('.formatted-number')).toHaveLength(0);
      expect(document.querySelectorAll('.number-input-container')).toHaveLength(1);
    });
  });

  describe('initFormatting', () => {
    it('no-ops when there is no form', async () => {
      const { initFormatting } = await loadFormatting();
      document.body.innerHTML = '<input type="number" id="n" value="1000">';

      initFormatting();

      expect(document.querySelector('.number-input-container')).toBeNull();
      expect(document.getElementById('n').parentElement).toBe(document.body);
    });

    it('formats number inputs inside a form', async () => {
      const { initFormatting } = await loadFormatting();
      document.body.innerHTML = `
        <form>
          <input type="number" id="n" value="2500">
          <input type="text" id="t" value="2500">
        </form>`;

      initFormatting();

      const numberInput = document.getElementById('n');
      expect(numberInput.closest('.number-input-container')).toBeTruthy();
      expect(numberInput.parentElement.querySelector('.formatted-number').textContent).toBe('2,500');
      expect(document.getElementById('t').closest('.number-input-container')).toBeNull();
    });
  });
});
