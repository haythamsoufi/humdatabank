/**
 * Submit-time matrix cell and required-field validation.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugError: vi.fn(),
  debugWarn: vi.fn(),
}));

const FIXTURE = `
  <div class="form-item-block" data-item-id="99">
    <label id="field-99">People reached *</label>
    <div class="matrix-container" data-field-id="99" data-can-edit="true">
      <input type="hidden" name="field_value_99" value="">
      <table><tbody>
        <tr class="matrix-data-row">
          <td><input type="number" data-cell-key="r1_Amount" data-row="Row 1" data-column="Amount"
                     data-column-type="number" data-max-decimals="0"></td>
        </tr>
      </tbody></table>
    </div>
  </div>
`;

function registerMatrix(handler, { isRequired = false, data = {} } = {}) {
  const container = document.querySelector('.matrix-container');
  handler.matrices.set('99', {
    container,
    config: { columns: [{ name: 'Amount', type: 'number' }], is_required: isRequired },
    data: { ...data },
    hiddenField: container.querySelector('input[type="hidden"]'),
  });
  return container;
}

function cellInput() {
  return document.querySelector('input[data-cell-key="r1_Amount"]');
}

describe('matrixHandler submit validation', () => {
  let matrixHandler;

  beforeEach(async () => {
    window.t = (k) => k;
    document.body.innerHTML = FIXTURE;
    vi.resetModules();
    ({ matrixHandler } = await import('../../../app/static/js/forms/modules/matrix-handler.js'));
    registerMatrix(matrixHandler);
  });

  afterEach(() => {
    matrixHandler?.matrices.clear();
    document.body.innerHTML = '';
    delete window.t;
    delete window.__numericUnformat;
    delete window.__matrixWholeNumberHasFraction;
    delete window.matrixHandler;
  });

  it('returns null for an empty number input', () => {
    const input = cellInput();
    input.value = '';
    expect(matrixHandler.getMatrixInputValidationMessage(input)).toBeNull();
  });

  it('returns a valid-number error for non-numeric text', () => {
    const input = cellInput();
    input.type = 'text';
    input.dataset.numeric = 'true';
    input.value = 'abc';
    expect(matrixHandler.getMatrixInputValidationMessage(input)).toBe('Please enter a valid number');
  });

  it('returns a cannot-be-negative error for a negative value', () => {
    const input = cellInput();
    input.value = '-1';
    expect(matrixHandler.getMatrixInputValidationMessage(input)).toBe('Value cannot be negative');
  });

  it('returns a whole-number error for 1.5 when maxDecimals is 0', () => {
    const input = cellInput();
    input.value = '1.5';
    expect(matrixHandler.getMatrixInputValidationMessage(input)).toBe(
      'This column requires a whole number. Please correct the decimal value.'
    );
  });

  it('returns null for 2 when maxDecimals is 0', () => {
    const input = cellInput();
    input.value = '2';
    expect(matrixHandler.getMatrixInputValidationMessage(input)).toBeNull();
  });

  it('returns null for a checkbox input', () => {
    const input = document.createElement('input');
    input.type = 'checkbox';
    cellInput().closest('td').appendChild(input);
    expect(matrixHandler.getMatrixInputValidationMessage(input)).toBeNull();
  });

  it('returns null for a row-total input', () => {
    const input = cellInput();
    input.setAttribute('data-is-row-total', 'true');
    input.value = '-5';
    expect(matrixHandler.getMatrixInputValidationMessage(input)).toBeNull();
  });

  it('returns null when the matrix is not registered', () => {
    matrixHandler.matrices.clear();
    const input = cellInput();
    input.value = '-1';
    expect(matrixHandler.getMatrixInputValidationMessage(input)).toBeNull();
  });

  it('uses window.__numericUnformat when present', () => {
    window.__numericUnformat = vi.fn(() => 'not-a-number');
    const input = cellInput();
    input.value = '12';
    expect(matrixHandler.getMatrixInputValidationMessage(input)).toBe('Please enter a valid number');
    expect(window.__numericUnformat).toHaveBeenCalled();
  });

  it('buildMatrixValidationError prefixes label, row, and column', () => {
    const input = cellInput();
    const error = matrixHandler.buildMatrixValidationError(input, 'Value cannot be negative');
    expect(error.type).toBe('matrix_cell');
    expect(error.message).toBe('People reached — Row 1 / Amount: Value cannot be negative');
    expect(error.field).toBe(input);
  });

  it('collectMatrixValidationErrors reports matrix_required when required and empty', () => {
    const matrix = matrixHandler.matrices.get('99');
    matrix.config.is_required = true;
    matrix.data = {};

    const errors = matrixHandler.collectMatrixValidationErrors();
    const required = errors.filter((e) => e.type === 'matrix_required');
    expect(required).toHaveLength(1);
    expect(required[0].message).toBe(
      'People reached: This field is required. Please enter at least one value.'
    );
  });

  it('collectMatrixValidationErrors does not report required when matrix.data has a positive value', () => {
    const matrix = matrixHandler.matrices.get('99');
    matrix.config.is_required = true;
    matrix.data = { r1_Amount: 10 };
    cellInput().value = '10';

    const errors = matrixHandler.collectMatrixValidationErrors();
    expect(errors.filter((e) => e.type === 'matrix_required')).toEqual([]);
  });

  it('treats a stored zero as filled for required matrices', () => {
    const matrix = matrixHandler.matrices.get('99');
    matrix.config.is_required = true;
    matrix.data = { r1_Amount: 0 };

    const errors = matrixHandler.collectMatrixValidationErrors();
    expect(errors.filter((e) => e.type === 'matrix_required')).toEqual([]);
  });

  it('collectMatrixValidationErrors includes a cell error and shows it on the input', () => {
    const input = cellInput();
    input.value = '-1';

    const errors = matrixHandler.collectMatrixValidationErrors();
    expect(errors).toHaveLength(1);
    expect(errors[0].type).toBe('matrix_cell');
    expect(errors[0].message).toContain('Value cannot be negative');
    expect(input.classList.contains('border-red-500')).toBe(true);
    expect(input.parentNode.querySelector('.input-error-message').textContent).toBe(
      'Value cannot be negative'
    );
  });

  it('collectMatrixValidationErrors cleans up a disconnected container', () => {
    const container = document.querySelector('.matrix-container');
    container.remove();

    const errors = matrixHandler.collectMatrixValidationErrors();
    expect(errors).toEqual([]);
    expect(matrixHandler.matrices.has('99')).toBe(false);
  });
});
