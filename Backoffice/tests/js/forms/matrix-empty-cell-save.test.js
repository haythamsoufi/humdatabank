/**
 * Numeric matrix cells: empty inputs must not be coerced to 0 on save.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugError: vi.fn(),
  debugWarn: vi.fn(),
}));

describe('matrixHandler.updateMatrixData empty numeric cells', () => {
  let matrixHandler;

  beforeEach(async () => {
    document.body.innerHTML = `
      <div class="matrix-container" data-field-id="99" data-can-edit="true">
        <input type="hidden" name="field_value_99" value="">
        <table><tbody>
          <tr class="matrix-data-row">
            <td><input type="number" data-cell-key="row1_Amount" data-column="Amount" data-column-type="number"></td>
          </tr>
        </tbody></table>
      </div>
    `;
    ({ matrixHandler } = await import('../../../app/static/js/forms/modules/matrix-handler.js'));
    const container = document.querySelector('.matrix-container');
    matrixHandler.matrices.set('99', {
      container,
      config: { columns: [{ name: 'Amount', type: 'number' }] },
      data: {},
      hiddenField: container.querySelector('input[type="hidden"]'),
    });
  });

  afterEach(() => {
    matrixHandler.matrices.clear();
    document.body.innerHTML = '';
  });

  function inputEl() {
    return document.querySelector('input[data-cell-key="row1_Amount"]');
  }

  it('does not save 0 when the cell is cleared', () => {
    const input = inputEl();
    const matrix = matrixHandler.matrices.get('99');
    matrix.data['row1_Amount'] = 42;

    input.value = '';
    matrixHandler.updateMatrixData('99', input);

    expect(matrix.data).not.toHaveProperty('row1_Amount');
    expect(matrix.hiddenField.value).toBe('');
  });

  it('saves 0 when the user explicitly enters zero', () => {
    const input = inputEl();

    input.value = '0';
    matrixHandler.updateMatrixData('99', input);

    const matrix = matrixHandler.matrices.get('99');
    expect(matrix.data['row1_Amount']).toBe(0);
    expect(JSON.parse(matrix.hiddenField.value)).toEqual({ row1_Amount: 0 });
  });

  it('does not add a key for a cell that was never filled', () => {
    const input = inputEl();

    input.value = '';
    matrixHandler.updateMatrixData('99', input);

    const matrix = matrixHandler.matrices.get('99');
    expect(matrix.data).toEqual({});
    expect(matrix.hiddenField.value).toBe('');
  });
});
