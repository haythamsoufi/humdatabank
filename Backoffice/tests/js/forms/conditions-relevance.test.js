/**
 * Unit tests for conditions.js hide/show + clear-on-hide relevance behavior.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugWarn: vi.fn(),
}));

const EQUALS_YES = '{"logic":"AND","conditions":[{"condition_type":"equals","item_id":"1","value":"yes"}]}';
const EQUALS_YES_NUMERIC_ID = '{"logic":"AND","conditions":[{"condition_type":"equals","item_id":1,"value":"yes"}]}';

async function loadConditions() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/conditions.js');
}

function sourceField(value = 'yes') {
  return `
    <div class="form-item-block" data-item-id="question_1">
      <input id="field-question_1" name="field_value[1]" value="${value}">
    </div>`;
}

function dependentField({ wrapper = true } = {}) {
  const block = `
    <div class="form-item-block" data-item-id="question_2"
         data-relevance-condition='${EQUALS_YES}'>
      <input id="field-question_2" name="field_value[2]" value="keep-me">
    </div>`;
  if (!wrapper) return block;
  return `<div class="flex-shrink-0 min-w-0">${block}</div>`;
}

function sectionBlock({ hidden = false, pageNumber = '1' } = {}) {
  const hiddenClass = hidden ? ' relevance-hidden' : '';
  return `
    <div id="section-container-99" class="${hiddenClass.trim()}"
         data-section-type="standard" data-page-number="${pageNumber}"
         data-relevance-condition='${EQUALS_YES}'>
      <input name="field_value[50]" value="section-val">
    </div>
    <nav><ul><li><a data-section-id="section-container-99">Sec</a></li></ul></nav>`;
}

function cleanupGlobals() {
  delete window.requestRelevanceRecheck;
  delete window.existingData;
  delete window.__ifrcPagination;
  delete window.checkAllRelevanceConditions;
  delete window.checkFieldRelevance;
  delete window.clearFieldValues;
  delete window.loadSavedFieldValues;
  delete window.collectHiddenFieldsForSubmission;
  delete window.debugFieldValue;
}

describe('conditions relevance (hide/show + clear-on-hide)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanupGlobals();
    document.body.innerHTML = '';
  });

  it('shows the dependent field and preserves its value when the trigger matches', async () => {
    document.body.innerHTML = `${sourceField('yes')}${dependentField()}`;
    const { checkAllRelevanceConditions } = await loadConditions();

    checkAllRelevanceConditions();

    const field = document.querySelector('[data-item-id="question_2"]');
    expect(field.classList.contains('relevance-visible')).toBe(true);
    expect(field.classList.contains('relevance-hidden')).toBe(false);
    expect(field.classList.contains('relevance-processed')).toBe(true);
    expect(document.getElementById('field-question_2').value).toBe('keep-me');
  });

  it('hides the dependent field and clears its input when the trigger does not match', async () => {
    vi.useFakeTimers();
    document.body.innerHTML = `${sourceField('no')}${dependentField()}`;
    const { checkAllRelevanceConditions } = await loadConditions();

    checkAllRelevanceConditions();

    const field = document.querySelector('[data-item-id="question_2"]');
    expect(field.classList.contains('relevance-hidden')).toBe(true);
    expect(field.classList.contains('relevance-visible')).toBe(false);
    expect(document.getElementById('field-question_2').value).toBe('');
  });

  it('hides the flex-shrink-0 min-w-0 layout wrapper when the field is hidden', async () => {
    vi.useFakeTimers();
    document.body.innerHTML = `${sourceField('no')}${dependentField()}`;
    const { checkAllRelevanceConditions } = await loadConditions();

    checkAllRelevanceConditions();

    const wrapper = document.querySelector('.flex-shrink-0.min-w-0');
    expect(wrapper.classList.contains('hidden')).toBe(true);
    expect(wrapper.style.display).toBe('none');
  });

  it('leaves a parent that is not a layout wrapper alone when hiding', async () => {
    vi.useFakeTimers();
    document.body.innerHTML = `
      ${sourceField('no')}
      <div id="plain-parent" class="some-other-wrapper">
        ${dependentField({ wrapper: false })}
      </div>`;
    const { checkAllRelevanceConditions } = await loadConditions();

    checkAllRelevanceConditions();

    const parent = document.getElementById('plain-parent');
    expect(parent.classList.contains('hidden')).toBe(false);
    expect(parent.style.display).not.toBe('none');
    expect(document.querySelector('[data-item-id="question_2"]').classList.contains('relevance-hidden')).toBe(true);
  });

  it('hides the row when every layout wrapper in it is hidden', async () => {
    vi.useFakeTimers();
    document.body.innerHTML = `
      ${sourceField('no')}
      <div id="the-row">
        ${dependentField()}
      </div>`;
    const { checkAllRelevanceConditions } = await loadConditions();

    checkAllRelevanceConditions();

    const row = document.getElementById('the-row');
    expect(row.classList.contains('hidden')).toBe(true);
    expect(row.style.display).toBe('none');
  });

  it('does not hide the row when a sibling layout wrapper is still visible', async () => {
    vi.useFakeTimers();
    document.body.innerHTML = `
      ${sourceField('no')}
      <div id="the-row">
        ${dependentField()}
        <div class="flex-shrink-0 min-w-0" id="sibling-wrapper">
          <div class="form-item-block" data-item-id="question_3">
            <input id="field-question_3" name="field_value[3]" value="other">
          </div>
        </div>
      </div>`;
    const { checkAllRelevanceConditions } = await loadConditions();

    checkAllRelevanceConditions();

    expect(document.getElementById('the-row').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('sibling-wrapper').classList.contains('hidden')).toBe(false);
  });

  it('shows a section (display not none, relevance-visible) when the condition is met', async () => {
    document.body.innerHTML = `${sourceField('yes')}${sectionBlock()}`;
    const { checkAllRelevanceConditions } = await loadConditions();

    checkAllRelevanceConditions();

    const section = document.getElementById('section-container-99');
    expect(section.classList.contains('relevance-visible')).toBe(true);
    expect(section.classList.contains('relevance-hidden')).toBe(false);
    expect(section.style.display).not.toBe('none');
    expect(section.querySelector('input').value).toBe('section-val');
  });

  it('keeps an already-hidden section hidden and does not clear its values', async () => {
    document.body.innerHTML = `${sourceField('no')}${sectionBlock({ hidden: true })}`;
    const { checkAllRelevanceConditions } = await loadConditions();

    checkAllRelevanceConditions();

    const section = document.getElementById('section-container-99');
    expect(section.classList.contains('relevance-hidden')).toBe(true);
    expect(section.classList.contains('relevance-visible')).toBe(false);
    expect(section.querySelector('input').value).toBe('section-val');
  });

  it('hides a previously visible section and clears its values when the condition fails', async () => {
    vi.useFakeTimers();
    document.body.innerHTML = `${sourceField('no')}${sectionBlock()}`;
    const { checkAllRelevanceConditions } = await loadConditions();

    checkAllRelevanceConditions();

    const section = document.getElementById('section-container-99');
    expect(section.classList.contains('relevance-hidden')).toBe(true);
    expect(section.classList.contains('relevance-visible')).toBe(false);
    expect(section.style.display).toBe('none');
    expect(section.querySelector('input').value).toBe('');
  });

  it('hides the nav link parent li when the section is hidden', async () => {
    vi.useFakeTimers();
    document.body.innerHTML = `${sourceField('no')}${sectionBlock()}`;
    const { checkAllRelevanceConditions } = await loadConditions();

    checkAllRelevanceConditions();

    const navLink = document.querySelector('[data-section-id="section-container-99"]');
    const parentLi = navLink.closest('li');
    expect(parentLi.style.display).toBe('none');
    expect(parentLi.classList.contains('hidden')).toBe(true);
  });

  it('does not force-show a relevant section that is on another paginated page', async () => {
    document.body.innerHTML = `
      <div id="sections-container" data-is-paginated="true">
        ${sourceField('yes')}
        ${sectionBlock({ pageNumber: '2' })}
      </div>`;
    window.__ifrcPagination = { getCurrentPageNumber: () => 1 };
    const { checkAllRelevanceConditions } = await loadConditions();

    checkAllRelevanceConditions();

    const section = document.getElementById('section-container-99');
    expect(section.classList.contains('relevance-visible')).toBe(true);
    expect(section.style.display).toBe('none');
    expect(section.style.getPropertyPriority('display')).toBe('important');
  });

  it('does not throw when data-relevance-condition is invalid JSON', async () => {
    document.body.innerHTML = `
      ${sourceField('yes')}
      <div class="form-item-block" data-item-id="question_2" data-relevance-condition="not-json{">
        <input id="field-question_2" name="field_value[2]" value="keep-me">
      </div>`;
    const { checkAllRelevanceConditions } = await loadConditions();

    expect(() => checkAllRelevanceConditions()).not.toThrow();
    expect(document.getElementById('field-question_2').value).toBe('keep-me');
  });

  it('dispatches ifrc:relevance-settled after a successful check with no pending pass', async () => {
    document.body.innerHTML = `${sourceField('yes')}${dependentField()}`;
    const { checkAllRelevanceConditions } = await loadConditions();
    const settled = vi.fn();
    document.addEventListener('ifrc:relevance-settled', settled);

    checkAllRelevanceConditions();

    expect(settled).toHaveBeenCalledTimes(1);
  });

  it('clears matching hidden inputs when a field is hidden', async () => {
    vi.useFakeTimers();
    document.body.innerHTML = `
      ${sourceField('no')}
      ${dependentField()}
      <input type="hidden" name="field_value[question_2]" value="hidden-keep">`;
    const { checkAllRelevanceConditions } = await loadConditions();

    checkAllRelevanceConditions();

    expect(document.querySelector('input[name="field_value[question_2]"]').value).toBe('');
    expect(document.getElementById('field-question_2').value).toBe('');
  });

  it('applies field visibility when the condition uses a numeric item_id', async () => {
    document.body.innerHTML = `
      ${sourceField('yes')}
      <div class="flex-shrink-0 min-w-0">
        <div class="form-item-block" data-item-id="question_2"
             data-relevance-condition='${EQUALS_YES_NUMERIC_ID}'>
          <input id="field-question_2" name="field_value[2]" value="keep-me">
        </div>
      </div>`;
    const { checkAllRelevanceConditions } = await loadConditions();

    expect(() => checkAllRelevanceConditions()).not.toThrow();
    const field = document.querySelector('[data-item-id="question_2"]');
    expect(field.classList.contains('relevance-visible')).toBe(true);
    expect(document.getElementById('field-question_2').value).toBe('keep-me');
  });

  it('evaluateConditions returns true when equals matches and false when it does not', async () => {
    document.body.innerHTML = sourceField('yes');
    const { evaluateConditions } = await loadConditions();

    expect(evaluateConditions({
      logic: 'AND',
      conditions: [{ condition_type: 'equals', item_id: 1, value: 'yes' }],
    })).toBe(true);
    expect(evaluateConditions({
      logic: 'AND',
      conditions: [{ condition_type: 'equals', item_id: 1, value: 'no' }],
    })).toBe(false);
  });
});
