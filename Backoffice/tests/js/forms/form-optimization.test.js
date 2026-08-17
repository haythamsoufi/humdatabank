/**
 * Unit tests for form-optimization.js (strip unused names on submit).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
}));

async function loadFormOptimization() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/form-optimization.js');
}

function submitForm(form) {
  form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
}

describe('form-optimization', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    delete window.__ifrcRestoreOptimizedNames;
    document.body.innerHTML = '';
  });

  it('strips empty demographic names including value 0', async () => {
    document.body.innerHTML = `
      <form id="f">
        <input name="ind_sexage_male" value="">
        <input name="ind_sex_female" value="0">
        <input name="ind_age_18" value="  ">
        <input name="ind_sexage_kept" value="12">
      </form>`;
    const { initFormOptimization } = await loadFormOptimization();
    initFormOptimization();

    submitForm(document.getElementById('f'));

    const empty = document.querySelector('[data-ifrc-original-name="ind_sexage_male"]');
    const zero = document.querySelector('[data-ifrc-original-name="ind_sex_female"]');
    const blank = document.querySelector('[data-ifrc-original-name="ind_age_18"]');
    expect(empty.getAttribute('name')).toBeNull();
    expect(zero.getAttribute('name')).toBeNull();
    expect(blank.getAttribute('name')).toBeNull();
    expect(document.querySelector('[name="ind_sexage_kept"]')).toBeTruthy();
  });

  it('strips hidden disaggregation inputs unless shouldNeverStripName', async () => {
    document.body.innerHTML = `
      <form id="f">
        <div class="disaggregation-inputs" style="display: none">
          <input name="hidden_plain" value="1">
          <input name="indicator_12_total" value="1">
          <input name="dynamic_3_value" value="1">
          <input name="repeat_4_1_field_2_value" value="1">
        </div>
        <div class="disaggregation-inputs" style="display: block">
          <input name="visible_plain" value="1">
        </div>
      </form>`;
    const { initFormOptimization } = await loadFormOptimization();
    initFormOptimization();

    submitForm(document.getElementById('f'));

    expect(document.querySelector('[data-ifrc-original-name="hidden_plain"]').getAttribute('name')).toBeNull();
    expect(document.querySelector('[name="indicator_12_total"]')).toBeTruthy();
    expect(document.querySelector('[name="dynamic_3_value"]')).toBeTruthy();
    expect(document.querySelector('[name="repeat_4_1_field_2_value"]')).toBeTruthy();
    expect(document.querySelector('[name="visible_plain"]')).toBeTruthy();
  });

  it('strips empty text/number/textarea except required, csrf, reporting_mode, dna/na', async () => {
    document.body.innerHTML = `
      <form id="f">
        <input type="text" name="empty_text" value="">
        <input type="number" name="empty_number" value="">
        <textarea name="empty_area"></textarea>
        <input type="text" name="required_empty" value="" required>
        <input type="text" name="csrf_token" value="">
        <input type="text" name="item_reporting_mode" value="">
        <input type="text" name="item_data_not_available" value="">
        <input type="text" name="item_not_applicable" value="">
        <input type="text" name="filled_text" value="keep">
      </form>`;
    const { initFormOptimization } = await loadFormOptimization();
    initFormOptimization();

    submitForm(document.getElementById('f'));

    expect(document.querySelector('[data-ifrc-original-name="empty_text"]').getAttribute('name')).toBeNull();
    expect(document.querySelector('[data-ifrc-original-name="empty_number"]').getAttribute('name')).toBeNull();
    expect(document.querySelector('[data-ifrc-original-name="empty_area"]').getAttribute('name')).toBeNull();
    expect(document.querySelector('[name="required_empty"]')).toBeTruthy();
    expect(document.querySelector('[name="csrf_token"]')).toBeTruthy();
    expect(document.querySelector('[name="item_reporting_mode"]')).toBeTruthy();
    expect(document.querySelector('[name="item_data_not_available"]')).toBeTruthy();
    expect(document.querySelector('[name="item_not_applicable"]')).toBeTruthy();
    expect(document.querySelector('[name="filled_text"]')).toBeTruthy();
  });

  it('strips unchecked non-required checkboxes', async () => {
    document.body.innerHTML = `
      <form id="f">
        <input type="checkbox" name="opt_in">
        <input type="checkbox" name="must_agree" required>
        <input type="checkbox" name="csrf_token">
        <input type="checkbox" name="already_on" checked>
      </form>`;
    const { initFormOptimization } = await loadFormOptimization();
    initFormOptimization();

    submitForm(document.getElementById('f'));

    expect(document.querySelector('[data-ifrc-original-name="opt_in"]').getAttribute('name')).toBeNull();
    expect(document.querySelector('[name="must_agree"]')).toBeTruthy();
    expect(document.querySelector('[name="csrf_token"]')).toBeTruthy();
    expect(document.querySelector('[name="already_on"]')).toBeTruthy();
  });

  it('stores original names on data-ifrc-original-name', async () => {
    document.body.innerHTML = `
      <form id="f">
        <input type="text" name="gone" value="">
      </form>`;
    const { initFormOptimization } = await loadFormOptimization();
    initFormOptimization();

    submitForm(document.getElementById('f'));

    const input = document.querySelector('input');
    expect(input.getAttribute('name')).toBeNull();
    expect(input.dataset.ifrcOriginalName).toBe('gone');
  });

  it('restores names on the next tick if a later handler preventDefault', async () => {
    document.body.innerHTML = `
      <form id="f">
        <input type="text" name="gone" value="">
      </form>`;
    const { initFormOptimization } = await loadFormOptimization();
    initFormOptimization();

    const form = document.getElementById('f');
    form.addEventListener('submit', (e) => e.preventDefault());

    submitForm(form);

    const input = document.querySelector('input');
    expect(input.getAttribute('name')).toBeNull();
    expect(input.dataset.ifrcOriginalName).toBe('gone');
    expect(typeof window.__ifrcRestoreOptimizedNames).toBe('function');

    vi.runAllTimers();

    expect(input.getAttribute('name')).toBe('gone');
    expect(input.dataset.ifrcOriginalName).toBeUndefined();
  });

  it('does not strip when submit is already defaultPrevented', async () => {
    document.body.innerHTML = `
      <form id="f">
        <input type="text" name="keep_me" value="">
      </form>`;
    const form = document.getElementById('f');
    form.addEventListener('submit', (e) => e.preventDefault());

    const { initFormOptimization } = await loadFormOptimization();
    initFormOptimization();

    submitForm(form);

    const input = document.querySelector('[name="keep_me"]');
    expect(input).toBeTruthy();
    expect(input.dataset.ifrcOriginalName).toBeUndefined();
  });
});
