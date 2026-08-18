/**
 * Unit tests for submit-time validation in form-validation.js.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugWarn: vi.fn(),
}));

vi.mock('../../../app/static/js/forms/modules/sidebar-collapse.js', () => ({
  closeEntryFormMobileNav: vi.fn(),
}));

const BRANCHES_LT_UNITS = JSON.stringify({
  logic: 'AND',
  conditions: [{ condition_type: 'less_than', item_id: 30, value_field_id: 31 }],
});

function mountForm(innerHtml = '') {
  document.body.innerHTML = `
    <form id="focalDataEntryForm">
      ${innerHtml}
      <button type="submit" name="action" value="save">Save</button>
      <button type="submit" name="action" value="submit">Submit</button>
    </form>`;
}

function requiredBlock({ itemId = '10', value = '', extraClass = '', extraAttrs = '', extraInputs = '' } = {}) {
  return `
    <div class="form-item-block ${extraClass}" data-item-id="${itemId}" ${extraAttrs}>
      <label>People reached <span class="text-red-500">*</span></label>
      <input id="field-${itemId}" name="field_value[${itemId}]" required value="${value}">
      ${extraInputs}
    </div>`;
}

function conditionFields({ branchesValue = '', unitsValue = '' } = {}) {
  return `
    <div class="form-item-block" data-item-id="question_30"
         data-validation-condition='${BRANCHES_LT_UNITS}'
         data-validation-message="Branches must be less than local units">
      <label>Branches</label>
      <input id="field-question_30" name="field_value[30]" type="number" value="${branchesValue}">
    </div>
    <div class="form-item-block" data-item-id="question_31">
      <label>Local units</label>
      <input id="field-question_31" name="field_value[31]" type="number" value="${unitsValue}">
    </div>`;
}

async function loadValidator() {
  vi.resetModules();
  delete window.formValidator;
  const mod = await import('../../../app/static/js/forms/modules/form-validation.js');
  return mod;
}

async function createValidator(innerHtml = '') {
  mountForm(innerHtml);
  const { FormValidator } = await loadValidator();
  return new FormValidator();
}

function dispatchFormSubmit(submitter) {
  const form = document.getElementById('focalDataEntryForm');
  const event = new SubmitEvent('submit', {
    bubbles: true,
    cancelable: true,
    submitter,
  });
  if (submitter && event.submitter !== submitter) {
    Object.defineProperty(event, 'submitter', { value: submitter, configurable: true });
  }
  form.dispatchEvent(event);
  return event;
}

function errorTypes(validator) {
  return validator.errors.map((e) => e.type);
}

describe('form-validation', () => {
  beforeEach(() => {
    window.t = (k) => k;
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.t;
    delete window.formValidator;
    delete window.matrixHandler;
    delete window.FormSubmitGuard;
    delete window.debugValidation;
    delete window.validateForm;
    delete window.checkFormValidation;
    delete window.collectHiddenFieldsForSubmission;
    delete window.showFlashMessage;
  });

  it('validateForm returns true when the form has no required fields', async () => {
    const validator = await createValidator('');
    expect(validator.validateForm()).toBe(true);
    expect(validator.errors).toEqual([]);
  });

  it('reports a required error for an empty required form-item-block', async () => {
    const validator = await createValidator(requiredBlock({ value: '' }));
    expect(validator.validateForm()).toBe(false);
    expect(errorTypes(validator)).toContain('required');
    expect(validator.errors.length).toBeGreaterThan(0);
  });

  it('accepts a filled required form-item-block', async () => {
    const validator = await createValidator(requiredBlock({ value: '42' }));
    expect(validator.validateForm()).toBe(true);
    expect(validator.errors).toEqual([]);
  });

  it('treats number 0 as a filled required value', async () => {
    const validator = await createValidator(`
      <div class="form-item-block" data-item-id="10">
        <label>Count <span class="text-red-500">*</span></label>
        <input id="field-10" name="field_value[10]" type="number" required value="0">
      </div>`);
    expect(validator.validateForm()).toBe(true);
    expect(validator.errors).toEqual([]);
  });

  it('accepts a required yes/no field when a yes/no checkbox is checked', async () => {
    const validator = await createValidator(`
      <div class="form-item-block" data-item-id="15">
        <label>Ready <span class="text-red-500">*</span></label>
        <input type="checkbox" name="field_value[15]" value="yes" checked>
        <input type="checkbox" name="field_value[15]" value="no">
      </div>`);
    expect(validator.validateForm()).toBe(true);
    expect(validator.errors).toEqual([]);
  });

  it('skips a required field hidden by relevance-hidden', async () => {
    const validator = await createValidator(
      requiredBlock({ itemId: '11', extraClass: 'relevance-hidden' }),
    );
    expect(validator.validateForm()).toBe(true);
    expect(errorTypes(validator)).not.toContain('required');
  });

  it('skips a bare required input inside a relevance-hidden ancestor', async () => {
    const validator = await createValidator(`
      <div data-section-type="repeat" class="relevance-hidden">
        <div class="space-y-6">
          <input name="repeat_template_name" required>
        </div>
      </div>`);
    expect(validator.validateForm()).toBe(true);
    expect(errorTypes(validator)).not.toContain('required');
  });

  it('skips a required field inside a hidden layout wrapper', async () => {
    const validator = await createValidator(`
      <div class="flex-shrink-0 min-w-0 hidden">
        ${requiredBlock({ itemId: '11' })}
      </div>`);
    expect(validator.validateForm()).toBe(true);
    expect(errorTypes(validator)).not.toContain('required');
  });

  it('still validates required fields on a paginated display:none section', async () => {
    const validator = await createValidator(`
      <div id="sections-container" data-is-paginated="true">
        <div data-section-type="standard" data-page-number="2" style="display:none">
          ${requiredBlock({ itemId: '20', value: '' })}
        </div>
      </div>`);
    expect(validator.validateForm()).toBe(false);
    expect(errorTypes(validator)).toContain('required');
  });

  it('treats a checked data-not-available checkbox as answered', async () => {
    const validator = await createValidator(`
      <div class="form-item-block" data-item-id="12">
        <label>Ind <span class="text-red-500">*</span></label>
        <input name="indicator_12_total_value" required>
        <input type="checkbox" name="indicator_12_data_not_available" checked>
      </div>`);
    expect(validator.validateForm()).toBe(true);
    expect(errorTypes(validator)).not.toContain('required');
  });

  it('treats a checked not-applicable checkbox as answered', async () => {
    const validator = await createValidator(`
      <div class="form-item-block" data-item-id="12">
        <label>Ind <span class="text-red-500">*</span></label>
        <input name="indicator_12_total_value" required>
        <input type="checkbox" name="indicator_12_not_applicable" checked>
      </div>`);
    expect(validator.validateForm()).toBe(true);
    expect(errorTypes(validator)).not.toContain('required');
  });

  it('rejects a percentage over 100 when allow_over_100 is false', async () => {
    const validator = await createValidator(`
      <div class="form-item-block" data-item-id="13">
        <input data-field-type="percentage" name="pct" value="150"
               data-field-config='{"allow_over_100":false}'>
      </div>`);
    expect(validator.validateForm()).toBe(false);
    expect(errorTypes(validator)).toContain('percentage_max_validation');
  });

  it('accepts a percentage of 80', async () => {
    const validator = await createValidator(`
      <div class="form-item-block" data-item-id="13">
        <input data-field-type="percentage" name="pct" value="80"
               data-field-config='{"allow_over_100":false}'>
      </div>`);
    expect(validator.validateForm()).toBe(true);
    expect(errorTypes(validator)).not.toContain('percentage_max_validation');
  });

  it('accepts a percentage over 100 when allow_over_100 is true', async () => {
    const validator = await createValidator(`
      <div class="form-item-block" data-item-id="13">
        <input data-field-type="percentage" name="pct" value="150"
               data-field-config='{"allow_over_100":true}'>
      </div>`);
    expect(validator.validateForm()).toBe(true);
    expect(errorTypes(validator)).not.toContain('percentage_max_validation');
  });

  it('accepts a percentage over 100 when allow_over_100 is 1 or "true"', async () => {
    const asOne = await createValidator(`
      <div class="form-item-block" data-item-id="13">
        <input data-field-type="percentage" name="pct" value="150"
               data-field-config='{"allow_over_100":1}'>
      </div>`);
    expect(asOne.validateForm()).toBe(true);

    const asString = await createValidator(`
      <div class="form-item-block" data-item-id="13">
        <input data-field-type="percentage" name="pct" value="150"
               data-field-config='{"allow_over_100":"true"}'>
      </div>`);
    expect(asString.validateForm()).toBe(true);
  });

  // Regression test: numeric-formatting.js renders data-numeric="true" inputs with
  // thousands separators once the value reaches four digits (e.g. "1,500"). A bare
  // parseFloat("1,500") used to stop at the comma and return 1, silently letting an
  // over-100% value through instead of flagging it.
  it('rejects a comma-formatted percentage over 100 (data-numeric="true")', async () => {
    const validator = await createValidator(`
      <div class="form-item-block" data-item-id="13">
        <input data-field-type="percentage" data-numeric="true" name="pct" value="1,500"
               data-field-config='{"allow_over_100":false}'>
      </div>`);
    expect(validator.validateForm()).toBe(false);
    expect(errorTypes(validator)).toContain('percentage_max_validation');
  });

  it('skips hidden and disabled percentage fields', async () => {
    const validator = await createValidator(`
      <div class="form-item-block relevance-hidden" data-item-id="13">
        <input data-field-type="percentage" name="pct_hidden" value="150"
               data-field-config='{"allow_over_100":false}'>
      </div>
      <div class="form-item-block" data-item-id="14">
        <input data-field-type="percentage" name="pct_disabled" value="150" disabled
               data-field-config='{"allow_over_100":false}'>
      </div>`);
    expect(validator.validateForm()).toBe(true);
    expect(errorTypes(validator)).not.toContain('percentage_max_validation');
  });

  it('reports validation_condition with the custom message when greater/less-than fails', async () => {
    const validator = await createValidator(conditionFields({ branchesValue: '100', unitsValue: '50' }));
    expect(validator.validateForm()).toBe(false);
    const conditionErrors = validator.errors.filter((e) => e.type === 'validation_condition');
    expect(conditionErrors).toHaveLength(1);
    expect(conditionErrors[0].message).toBe('Branches must be less than local units');
  });

  it('skips a validation condition when the field itself is empty', async () => {
    const validator = await createValidator(conditionFields({ branchesValue: '', unitsValue: '50' }));
    expect(validator.validateForm()).toBe(true);
    expect(errorTypes(validator)).not.toContain('validation_condition');
  });

  it('skips a validation condition when the value_field_id target is empty', async () => {
    const validator = await createValidator(conditionFields({ branchesValue: '100', unitsValue: '' }));
    expect(validator.validateForm()).toBe(true);
    expect(errorTypes(validator)).not.toContain('validation_condition');
  });

  // Entry form uses data-item-id="961" (bare), not question_961. evaluateConditions
  // used to rewrite the id to question_961, read null for both sides, and flag a
  // violation even when 500 < 1200.
  it('does not flag validation_condition for entry-form bare numeric item ids', async () => {
    const validator = await createValidator(`
      <div class="form-item-block" data-item-id="963"
           data-validation-condition='${JSON.stringify({
             logic: 'AND',
             conditions: [{ condition_type: 'greater_than', item_id: '963', value_field_id: 961 }],
           })}'
           data-validation-message="Field 963 must be greater than field 961">
        <input name="indicator_963_total_value" value="1200">
      </div>
      <div class="form-item-block" data-item-id="961"
           data-validation-condition='${JSON.stringify({
             logic: 'AND',
             conditions: [{ condition_type: 'less_than', item_id: '961', value_field_id: 963 }],
           })}'
           data-validation-message="Field 961 must be less than field 963">
        <input name="indicator_961_total_value" value="500">
      </div>`);
    expect(validator.validateForm()).toBe(true);
    expect(errorTypes(validator)).not.toContain('validation_condition');
  });

  // Regression test for the reported bug: field 963 ("greater_than" value_field_id 961)
  // holds a comma-formatted value (data-numeric="true", set by numeric-formatting.js once
  // a number reaches four digits). A bare parseFloat("1,200") used to truncate to 1, so
  // 1200 was never seen as greater_than 500 and the rule appeared violated even though it
  // wasn't.
  it('does not flag validation_condition when the compared value is comma-formatted', async () => {
    const validator = await createValidator(`
      <div class="form-item-block" data-item-id="963"
           data-validation-condition='${JSON.stringify({
             logic: 'AND',
             conditions: [{ condition_type: 'greater_than', item_id: 963, value_field_id: 961 }],
           })}'
           data-validation-message="Field 963 must be greater than field 961">
        <input id="field-963" name="indicator_963_total_value" type="text" data-numeric="true" value="1,200">
      </div>
      <div class="form-item-block" data-item-id="961">
        <input id="field-961" name="indicator_961_total_value" type="number" value="500">
      </div>`);
    expect(validator.validateForm()).toBe(true);
    expect(errorTypes(validator)).not.toContain('validation_condition');
  });

  it('does not preventDefault on save submit', async () => {
    const validator = await createValidator(requiredBlock({ value: '' }));
    const saveBtn = document.querySelector('button[name="action"][value="save"]');
    const event = dispatchFormSubmit(saveBtn);
    expect(event.defaultPrevented).toBe(false);
    expect(validator.errors).toEqual([]);
  });

  it('preventDefault on submit when a required field is empty', async () => {
    window.showFlashMessage = vi.fn();
    const validator = await createValidator(requiredBlock({ value: '' }));
    const submitBtn = document.querySelector('button[name="action"][value="submit"]');
    const event = dispatchFormSubmit(submitBtn);
    expect(event.defaultPrevented).toBe(true);
    expect(errorTypes(validator)).toContain('required');
    expect(validator.errors.length).toBeGreaterThan(0);
  });

  it('runs validation for an unknown action and preventDefault on failure', async () => {
    window.showFlashMessage = vi.fn();
    const validator = await createValidator(requiredBlock({ value: '' }));
    const event = dispatchFormSubmit(null);
    expect(event.defaultPrevented).toBe(true);
    expect(errorTypes(validator)).toContain('required');
  });

  it('reports repeat_empty when a visible required template has no entries', async () => {
    const validator = await createValidator(`
      <div id="section-container-5" data-section-type="repeat">
        <h3>Locations</h3>
        <div class="space-y-6">
          <input name="template_field" required>
        </div>
      </div>`);
    expect(validator.validateForm()).toBe(false);
    expect(errorTypes(validator)).toContain('repeat_empty');
  });

  it('reports repeat_required when a repeat entry has an empty required field', async () => {
    const validator = await createValidator(`
      <div id="section-container-5" data-section-type="repeat">
        <h3>Locations</h3>
        <div class="repeat-entry">
          <input name="repeat_5_1_name" required value="">
        </div>
      </div>`);
    expect(validator.validateForm()).toBe(false);
    expect(errorTypes(validator)).toContain('repeat_required');
  });

  it('rejects non-numeric indirect reach and accepts a numeric value', async () => {
    const invalid = await createValidator(`
      <div class="form-item-block" data-item-id="40">
        <label>Indirect reach</label>
        <input name="indicator_40_indirect_reach" value="abc">
      </div>`);
    expect(invalid.validateForm()).toBe(false);
    expect(errorTypes(invalid)).toContain('indirect_reach_validation');

    const valid = await createValidator(`
      <div class="form-item-block" data-item-id="40">
        <label>Indirect reach</label>
        <input name="indicator_40_indirect_reach" value="42">
      </div>`);
    expect(valid.validateForm()).toBe(true);
    expect(errorTypes(valid)).not.toContain('indirect_reach_validation');
  });

  // Regression test: indirect reach counts are frequently >= 1000, so numeric-formatting.js
  // renders the input's value with thousands separators (data-numeric="true", e.g. "1,200").
  // `isNaN("1,200")` is true (Number() rejects grouping separators), so this used to reject a
  // perfectly valid reach count as "not a valid number".
  it('accepts a comma-formatted (data-numeric) indirect reach value', async () => {
    const validator = await createValidator(`
      <div class="form-item-block" data-item-id="40">
        <label>Indirect reach</label>
        <input name="indicator_40_indirect_reach" data-numeric="true" value="1,200">
      </div>`);
    expect(validator.validateForm()).toBe(true);
    expect(errorTypes(validator)).not.toContain('indirect_reach_validation');
  });

  it('skips a direct required field inside a modal dialog', async () => {
    const validator = await createValidator(`
      <div role="dialog">
        <input name="modal_field" required>
      </div>`);
    expect(validator.validateForm()).toBe(true);
    expect(errorTypes(validator)).not.toContain('required');
  });

  it('appends matrixHandler.collectMatrixValidationErrors to the error list', async () => {
    window.matrixHandler = {
      collectMatrixValidationErrors: vi.fn(() => ([
        {
          field: null,
          container: null,
          message: 'Bad matrix cell',
          type: 'matrix_cell',
        },
      ])),
    };
    const validator = await createValidator('');
    expect(validator.validateForm()).toBe(false);
    expect(errorTypes(validator)).toContain('matrix_cell');
    expect(window.matrixHandler.collectMatrixValidationErrors).toHaveBeenCalled();
  });
});
