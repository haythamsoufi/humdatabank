/**
 * Unit tests for disability-questions.js (Washington Group block visibility).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
}));

async function loadDisabilityQuestions() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/disability-questions.js');
}

const FIXTURE = `
<div id="entry-form-ui">
  <div class="disability-questions">
    <input type="radio" class="disability-disaggregated-radio" name="d" value="yes">
    <input type="radio" class="disability-disaggregated-radio" name="d" value="no" checked>
    <div class="disability-washington-group-block hidden">
      <input type="radio" class="disability-washington-group-radio" name="wg" value="yes">
    </div>
  </div>
</div>`;

function wgBlock() {
  return document.querySelector('.disability-washington-group-block');
}

function radio(value) {
  return document.querySelector(`.disability-disaggregated-radio[value="${value}"]`);
}

function wgRadio() {
  return document.querySelector('.disability-washington-group-radio');
}

describe('disability-questions', () => {
  beforeEach(() => {
    document.body.innerHTML = FIXTURE;
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('keeps the Washington Group block hidden when no is selected', async () => {
    const { initDisabilityQuestions } = await loadDisabilityQuestions();
    initDisabilityQuestions();

    expect(wgBlock().classList.contains('hidden')).toBe(true);
  });

  it('removes hidden when changed to yes', async () => {
    const { initDisabilityQuestions } = await loadDisabilityQuestions();
    initDisabilityQuestions();

    const yes = radio('yes');
    yes.checked = true;
    yes.dispatchEvent(new Event('change', { bubbles: true }));

    expect(wgBlock().classList.contains('hidden')).toBe(false);
  });

  it('adds hidden and unchecks Washington Group radios when changed to no', async () => {
    const { initDisabilityQuestions } = await loadDisabilityQuestions();
    initDisabilityQuestions();

    const yes = radio('yes');
    yes.checked = true;
    yes.dispatchEvent(new Event('change', { bubbles: true }));
    wgRadio().checked = true;

    const no = radio('no');
    no.checked = true;
    no.dispatchEvent(new Event('change', { bubbles: true }));

    expect(wgBlock().classList.contains('hidden')).toBe(true);
    expect(wgRadio().checked).toBe(false);
  });

  it('re-syncs visibility on repeatEntryAdded', async () => {
    await loadDisabilityQuestions();

    const container = document.querySelector('#entry-form-ui');
    radio('yes').checked = true;
    expect(wgBlock().classList.contains('hidden')).toBe(true);

    document.dispatchEvent(new CustomEvent('repeatEntryAdded', {
      detail: { container },
    }));

    expect(wgBlock().classList.contains('hidden')).toBe(false);
  });
});
