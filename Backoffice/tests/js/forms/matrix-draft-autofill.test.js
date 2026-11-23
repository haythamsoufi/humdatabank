/**
 * Auto-filled variable cells must not be captured into local drafts, while edited
 * cells still are. Draft restore must be able to read both raw and b64 payloads.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugError: vi.fn(),
  debugWarn: vi.fn(),
}));

const FIELD_ID = '77';

const b64 = (obj) => `b64:${btoa(unescape(encodeURIComponent(JSON.stringify(obj))))}`;

describe('__deserializeMatrixData', () => {
  it('reads raw JSON, b64 payloads and rejects invalid input', async () => {
    const { __deserializeMatrixData } = await import('../../../app/static/js/forms/modules/matrix/formatting.js');
    expect(__deserializeMatrixData('{"1_A":"x"}')).toEqual({ '1_A': 'x' });
    expect(__deserializeMatrixData(b64({ '1_A': 'é' }))).toEqual({ '1_A': 'é' });
    expect(__deserializeMatrixData('')).toBeNull();
    expect(__deserializeMatrixData('b64:***')).toBeNull();
    expect(__deserializeMatrixData('not json')).toBeNull();
  });
});

describe('matrix draft handling', () => {
  let matrixHandler;
  let deserialize;

  beforeEach(async () => {
    ({ matrixHandler } = await import('../../../app/static/js/forms/modules/matrix-handler.js'));
    ({ __deserializeMatrixData: deserialize } = await import('../../../app/static/js/forms/modules/matrix/formatting.js'));
  });

  afterEach(() => {
    matrixHandler.matrices.clear();
    document.body.innerHTML = '';
  });

  function build(payload, autoFilled, editedKeys = []) {
    document.body.innerHTML = `
      <div class="matrix-container" data-field-id="${FIELD_ID}">
        <input type="hidden" name="field_value[${FIELD_ID}]" value="">
        <input data-cell-key="1_Planned"><input data-cell-key="1_Actual">
      </div>`;
    const container = document.querySelector('.matrix-container');
    const hidden = container.querySelector('input[type="hidden"]');
    hidden.value = payload;
    editedKeys.forEach((key) => {
      container.querySelector(`input[data-cell-key="${key}"]`).dataset.userEdited = '1';
    });
    matrixHandler.matrices.set(FIELD_ID, {
      container,
      hiddenField: hidden,
      config: { columns: [] },
      data: {},
      autoFilledVariableCells: new Set(autoFilled),
    });
    return hidden;
  }

  it('parseExistingData reads b64 payloads and drops metadata keys', () => {
    build(b64({ '1_Planned': '5', _meta: 1 }), []);
    const container = document.querySelector('.matrix-container');
    expect(matrixHandler.parseExistingData(container)).toEqual({ '1_Planned': '5' });
  });

  it('parseExistingData returns an empty object for unreadable payloads', () => {
    build('b64:***', []);
    const container = document.querySelector('.matrix-container');
    expect(matrixHandler.parseExistingData(container)).toEqual({});
  });

  it('strips auto-filled cells for the callback and restores the field afterwards', () => {
    const original = b64({ '1_Planned': '10', '1_Actual': '7' });
    const hidden = build(original, ['1_Planned']);
    let seen;
    matrixHandler.withAutoFilledCellsStripped(() => { seen = deserialize(hidden.value); });
    expect(seen).toEqual({ '1_Actual': '7' });
    expect(hidden.value).toBe(original);
  });

  it('keeps auto-filled cells the user has edited', () => {
    const hidden = build(b64({ '1_Planned': '99', '1_Actual': '7' }), ['1_Planned'], ['1_Planned']);
    let seen;
    matrixHandler.withAutoFilledCellsStripped(() => { seen = deserialize(hidden.value); });
    expect(seen).toEqual({ '1_Planned': '99', '1_Actual': '7' });
  });

  it('restores the field and returns the callback result even when the callback throws', () => {
    const original = b64({ '1_Planned': '10' });
    const hidden = build(original, ['1_Planned']);
    expect(() => matrixHandler.withAutoFilledCellsStripped(() => { throw new Error('boom'); })).toThrow('boom');
    expect(hidden.value).toBe(original);
    expect(matrixHandler.withAutoFilledCellsStripped(() => 42)).toBe(42);
  });

  it('leaves the field untouched when nothing is auto-filled', () => {
    const original = b64({ '1_Actual': '7' });
    const hidden = build(original, []);
    let during;
    matrixHandler.withAutoFilledCellsStripped(() => { during = hidden.value; });
    expect(during).toBe(original);
  });
});

describe('addDynamicRow de-duplication', () => {
  it('does not add a second row when the existing row label differs from its id', async () => {
    const { matrixHandler } = await import('../../../app/static/js/forms/modules/matrix-handler.js');
    document.body.innerHTML = `
      <div class="matrix-container" data-field-id="${FIELD_ID}">
        <table><tbody id="matrix-tbody-${FIELD_ID}">
          <tr class="matrix-data-row" data-row-id="2" data-row-label="Entity 2"></tr>
        </tbody></table>
      </div>`;
    const container = document.querySelector('.matrix-container');
    matrixHandler.matrices.set(FIELD_ID, {
      container, config: { columns: [{ name: 'Actual', type: 'number' }] }, data: {},
    });
    matrixHandler.addDynamicRow(FIELD_ID, '2', { _id: '2', id: '2' }, '2', false);
    expect(document.querySelectorAll('tr.matrix-data-row')).toHaveLength(1);
    matrixHandler.matrices.clear();
  });
});

describe('addDynamicRow header gating', () => {
  afterEach(async () => {
    const { matrixHandler } = await import('../../../app/static/js/forms/modules/matrix-handler.js');
    matrixHandler.variableResolutionDebounceTimers?.forEach((id) => clearTimeout(id));
    matrixHandler.variableResolutionDebounceTimers?.clear();
    matrixHandler.matrices.clear();
    document.body.innerHTML = '';
  });

  it('greys a selectable column that has no header value on a newly added row', async () => {
    const { matrixHandler } = await import('../../../app/static/js/forms/modules/matrix-handler.js');
    document.body.innerHTML = `
      <div class="matrix-container" data-field-id="${FIELD_ID}" data-can-edit="true">
        <table><tbody id="matrix-tbody-${FIELD_ID}"></tbody></table>
      </div>`;
    const container = document.querySelector('.matrix-container');
    matrixHandler.matrices.set(FIELD_ID, {
      container,
      config: {
        row_mode: 'list_library',
        show_row_totals: false,
        show_column_totals: false,
        columns: [
          { name: 'EA3', type: 'number', header_type: 'selectable' },
          { name: 'SP2', type: 'number' },
        ],
      },
      data: {},
    });

    matrixHandler.addDynamicRow(FIELD_ID, 'Bhutan Red Cross Society', { _id: '49', id: '49' }, '49', false);

    const emergency = container.querySelector('input[data-column="EA3"]');
    const disasters = container.querySelector('input[data-column="SP2"]');
    expect(emergency.disabled).toBe(true);
    expect(emergency.closest('td').classList.contains('matrix-cell-header-gated')).toBe(true);
    expect(disasters.disabled).toBe(false);
    expect(disasters.closest('td').classList.contains('matrix-cell-header-gated')).toBe(false);
  });
});
