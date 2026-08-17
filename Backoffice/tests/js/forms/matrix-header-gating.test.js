/**
 * Selectable column-header gating: cells in a column with header_type="selectable"
 * must stay disabled until a value has been chosen in that column's header
 * (see app/static/js/forms/modules/matrix/selectable-headers.js).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugError: vi.fn(),
  debugWarn: vi.fn(),
}));

vi.mock('../../../app/static/js/forms/modules/matrix/shared.js', () => ({
  _t: (k) => k,
}));

describe('__matrixCellIsHeaderGated', () => {
  it('is false for columns that are not selectable-header, regardless of data', async () => {
    const { __matrixCellIsHeaderGated } = await import(
      '../../../app/static/js/forms/modules/matrix/selectable-headers.js'
    );
    const matrix = { config: { columns: [{ name: 'SP1', type: 'number' }] }, data: {} };
    expect(__matrixCellIsHeaderGated(matrix, 'SP1')).toBe(false);
  });

  it('is true for a selectable-header column with no saved header value yet', async () => {
    const { __matrixCellIsHeaderGated } = await import(
      '../../../app/static/js/forms/modules/matrix/selectable-headers.js'
    );
    const matrix = { config: { columns: [{ name: 'SP1', header_type: 'selectable' }] }, data: {} };
    expect(__matrixCellIsHeaderGated(matrix, 'SP1')).toBe(true);
  });

  it('is false once a header value has been saved for that column', async () => {
    const { __matrixCellIsHeaderGated } = await import(
      '../../../app/static/js/forms/modules/matrix/selectable-headers.js'
    );
    const matrix = {
      config: { columns: [{ name: 'SP1', header_type: 'selectable' }] },
      data: { 'col_header|SP1': 'Region A' },
    };
    expect(__matrixCellIsHeaderGated(matrix, 'SP1')).toBe(false);
  });

  it('treats a whitespace-only saved header value as still gated', async () => {
    const { __matrixCellIsHeaderGated } = await import(
      '../../../app/static/js/forms/modules/matrix/selectable-headers.js'
    );
    const matrix = {
      config: { columns: [{ name: 'SP1', header_type: 'selectable' }] },
      data: { 'col_header|SP1': '   ' },
    };
    expect(__matrixCellIsHeaderGated(matrix, 'SP1')).toBe(true);
  });

  it('does not confuse one column with another sharing a name prefix', async () => {
    const { __matrixCellIsHeaderGated } = await import(
      '../../../app/static/js/forms/modules/matrix/selectable-headers.js'
    );
    const matrix = {
      config: { columns: [{ name: 'SP1', header_type: 'selectable' }, { name: 'SP1_extra', header_type: 'selectable' }] },
      data: { 'col_header|SP1': 'Region A' },
    };
    expect(__matrixCellIsHeaderGated(matrix, 'SP1')).toBe(false);
    expect(__matrixCellIsHeaderGated(matrix, 'SP1_extra')).toBe(true);
  });

  it('fails open (not gated) when matrix or column name is missing/unmatched', async () => {
    const { __matrixCellIsHeaderGated } = await import(
      '../../../app/static/js/forms/modules/matrix/selectable-headers.js'
    );
    expect(__matrixCellIsHeaderGated(null, 'SP1')).toBe(false);
    expect(__matrixCellIsHeaderGated({ config: { columns: [] }, data: {} }, '')).toBe(false);
    expect(__matrixCellIsHeaderGated({ config: { columns: [] }, data: {} }, 'Unknown')).toBe(false);
  });

  it('__isMatrixHeaderDataKey identifies selectable-header and GO-unmatched metadata keys', async () => {
    const { __isMatrixHeaderDataKey } = await import(
      '../../../app/static/js/forms/modules/matrix/selectable-headers.js'
    );
    // Standard selectable-header value
    expect(__isMatrixHeaderDataKey('col_header|SP1')).toBe(true);
    // GO-unmatched flags must also be treated as metadata (not stale cell keys)
    expect(__isMatrixHeaderDataKey('col_header_go_unmatched|EA2')).toBe(true);
    expect(__isMatrixHeaderDataKey('row_go_unmatched|MDRAF070')).toBe(true);
    // Regular cell keys and internal underscored keys should still be false
    expect(__isMatrixHeaderDataKey('row1_SP1')).toBe(false);
    expect(__isMatrixHeaderDataKey('_table')).toBe(false);
  });
});

describe('GO-unmatched selectable headers', () => {
  let matrixSelectableHeadersMixin;

  beforeEach(async () => {
    document.body.innerHTML = '';
    ({ matrixSelectableHeadersMixin } = await import(
      '../../../app/static/js/forms/modules/matrix/selectable-headers.js'
    ));
  });

  function makeHandler(matrix) {
    return Object.assign(
      { matrices: new Map([['967', matrix]]), _applyMatrixInputEditability: vi.fn() },
      matrixSelectableHeadersMixin
    );
  }

  it('_restoreHeaderSelectValue flags unmatched Excel appeals instead of injecting normal GO options', () => {
    document.body.innerHTML = `
      <div class="matrix-container" data-field-id="967">
        <table><thead><tr><th>
          <div class="matrix-header-picker">
            <button type="button" class="matrix-header-picker-trigger">
              <span class="matrix-header-picker-label"></span>
            </button>
            <ul class="matrix-header-picker-menu hidden"></ul>
            <select class="matrix-header-select" data-field-id="967" data-col-name="EA2">
              <option value="">Select...</option>
              <option value="GO appeal (MDR001)">GO appeal (MDR001)</option>
            </select>
          </div>
        </th></tr></thead></table>
      </div>`;
    const selectEl = document.querySelector('.matrix-header-select');
    const matrix = {
      container: document.querySelector('.matrix-container'),
      config: { columns: [{ name: 'EA2', header_type: 'selectable' }] },
      data: {
        'col_header|EA2': 'Afghanistan: Population Movement (MDRAF070)',
        'col_header_go_unmatched|EA2': 1,
      },
    };
    const handler = makeHandler(matrix);

    handler._restoreHeaderSelectValue(selectEl, '967');
    handler._syncHeaderPickerUI(selectEl);

    const unmatchedOpt = selectEl.querySelector('option[data-go-unmatched="true"]');
    expect(unmatchedOpt).not.toBeNull();
    expect(unmatchedOpt.value).toBe('Afghanistan: Population Movement (MDRAF070)');
    // No suffix — label is plain value text; tooltip is on the element instead
    expect(unmatchedOpt.textContent).toBe('Afghanistan: Population Movement (MDRAF070)');
    expect(unmatchedOpt.title).toContain('Not matched in GO');
    expect(selectEl.value).toBe('Afghanistan: Population Movement (MDRAF070)');
    expect(document.querySelector('.matrix-header-picker--go-unmatched')).not.toBeNull();
  });
});

describe('matrixSelectableHeadersMixin gating helpers', () => {
  let matrixSelectableHeadersMixin;

  beforeEach(async () => {
    document.body.innerHTML = '';
    ({ matrixSelectableHeadersMixin } = await import(
      '../../../app/static/js/forms/modules/matrix/selectable-headers.js'
    ));
  });

  function makeHandler(matrix) {
    return Object.assign(
      { matrices: new Map([['1', matrix]]), _applyMatrixInputEditability: vi.fn() },
      matrixSelectableHeadersMixin
    );
  }

  it('_applyHeaderGatingForColumn re-applies editability to every cell in that column only', () => {
    document.body.innerHTML = `
      <div class="matrix-container">
        <table><tbody>
          <tr><td><input data-column="SP1" data-cell-key="r1_SP1"></td></tr>
          <tr><td><input data-column="SP1" data-cell-key="r2_SP1"></td></tr>
          <tr><td><input data-column="Other" data-cell-key="r1_Other"></td></tr>
        </tbody></table>
      </div>`;
    const container = document.querySelector('.matrix-container');
    const matrix = {
      container,
      config: { columns: [{ name: 'SP1', header_type: 'selectable' }, { name: 'Other' }] },
      data: {},
    };
    const handler = makeHandler(matrix);

    handler._applyHeaderGatingForColumn('1', 'SP1');

    expect(handler._applyMatrixInputEditability).toHaveBeenCalledTimes(2);
    const touchedKeys = handler._applyMatrixInputEditability.mock.calls
      .map((call) => call[0].dataset.cellKey)
      .sort();
    expect(touchedKeys).toEqual(['r1_SP1', 'r2_SP1']);
  });

  it('_applyHeaderGatingForColumn forwards the column variable_readonly flag', () => {
    document.body.innerHTML = `
      <div class="matrix-container">
        <table><tbody>
          <tr><td><input data-column="VarCol"></td></tr>
        </tbody></table>
      </div>`;
    const container = document.querySelector('.matrix-container');
    const matrix = {
      container,
      config: {
        columns: [{ name: 'VarCol', header_type: 'selectable', is_variable: true, variable_readonly: false }],
      },
      data: {},
    };
    const handler = makeHandler(matrix);

    handler._applyHeaderGatingForColumn('1', 'VarCol');

    expect(handler._applyMatrixInputEditability).toHaveBeenCalledTimes(1);
    const [, , variableReadonlyArg] = handler._applyMatrixInputEditability.mock.calls[0];
    expect(variableReadonlyArg).toBe(false);
  });

  it('_applyHeaderGatingForMatrix re-syncs every selectable-header column and skips plain columns', () => {
    document.body.innerHTML = `
      <div class="matrix-container">
        <table><tbody>
          <tr>
            <td><input data-column="SP1"></td>
            <td><input data-column="SP2"></td>
            <td><input data-column="Plain"></td>
          </tr>
        </tbody></table>
      </div>`;
    const container = document.querySelector('.matrix-container');
    const matrix = {
      container,
      config: {
        columns: [
          { name: 'SP1', header_type: 'selectable' },
          { name: 'SP2', header_type: 'selectable' },
          { name: 'Plain' },
        ],
      },
      data: {},
    };
    const handler = makeHandler(matrix);

    handler._applyHeaderGatingForMatrix('1');

    expect(handler._applyMatrixInputEditability).toHaveBeenCalledTimes(2);
  });

  it('_saveHeaderValue persists the value, updates the hidden field, and re-syncs cell editability', () => {
    document.body.innerHTML = `
      <div class="matrix-container">
        <table><tbody>
          <tr><td><input data-column="SP1" data-cell-key="r1_SP1"></td></tr>
        </tbody></table>
      </div>
      <input type="hidden" id="hidden-field">`;
    const container = document.querySelector('.matrix-container');
    const hiddenField = document.getElementById('hidden-field');
    const matrix = {
      container,
      hiddenField,
      config: { columns: [{ name: 'SP1', header_type: 'selectable' }] },
      data: {},
    };
    const handler = makeHandler(matrix);

    handler._saveHeaderValue('1', 'SP1', 'Region A');

    expect(matrix.data['col_header|SP1']).toBe('Region A');
    expect(hiddenField.value).toContain('Region A');
    expect(handler._applyMatrixInputEditability).toHaveBeenCalledTimes(1);

    handler._applyMatrixInputEditability.mockClear();
    handler._saveHeaderValue('1', 'SP1', '');

    expect(matrix.data['col_header|SP1']).toBeUndefined();
    expect(handler._applyMatrixInputEditability).toHaveBeenCalledTimes(1);
  });
});
