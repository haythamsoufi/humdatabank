/**
 * Editable variable matrix cells: values copied from the lookup must keep following
 * the lookup, and only a saved or user-edited value may be flagged as "modified".
 * Overlapping resolves must not let an older response overwrite a newer one.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugError: vi.fn(),
  debugWarn: vi.fn(),
}));

const FIELD_ID = '1407';
const CELL_KEY = '10_Planned';

const column = {
  name: 'Planned',
  type: 'number',
  is_variable: true,
  variable: 'planned_var',
  variable_readonly: false,
  variable_save_value: true,
};

function buildMatrix(matrixHandler, { data = {}, restored = false } = {}) {
  document.body.innerHTML = `
    <input type="hidden" name="assignment_entity_status_id" value="5">
    <input type="hidden" name="template_id" value="3">
    <div class="matrix-container" data-field-id="${FIELD_ID}" data-can-edit="true">
      <input type="hidden" name="field_value[${FIELD_ID}]" value="">
      <table><tbody>
        <tr class="matrix-data-row" data-row-id="10" data-row-data='{"id":10}'>
          <td>
            <input type="text" data-cell-key="${CELL_KEY}" data-column="Planned"
                   data-column-type="variable" data-variable-name="planned_var"
                   data-variable-save-value="true" data-variable-readonly="false">
          </td>
        </tr>
      </tbody></table>
    </div>
  `;
  const container = document.querySelector('.matrix-container');
  matrixHandler.matrices.set(FIELD_ID, {
    container,
    config: { columns: [column] },
    data,
    hiddenField: container.querySelector('input[type="hidden"]'),
    lookupRefs: {},
  });
  const input = document.querySelector(`input[data-cell-key="${CELL_KEY}"]`);
  if (restored && data[CELL_KEY] !== undefined) input.value = String(data[CELL_KEY]);
  return { input, row: document.querySelector('tr.matrix-data-row') };
}

describe('variable cell auto-fill', () => {
  let matrixHandler;

  beforeEach(async () => {
    ({ matrixHandler } = await import('../../../app/static/js/forms/modules/matrix-handler.js'));
  });

  afterEach(() => {
    matrixHandler.matrices.clear();
    matrixHandler._variableResolveIssued = undefined;
    matrixHandler._variableResolveApplied = undefined;
    document.body.innerHTML = '';
    delete window.getFetch;
  });

  function apply(input, row, value) {
    matrixHandler._applyResolvedVariablesToRow(
      FIELD_ID, '10', row, [input], { planned_var: value },
    );
  }

  it('shows the lookup and does not flag an unsaved cell', () => {
    const { input, row } = buildMatrix(matrixHandler);
    apply(input, row, 100);

    expect(input.value).toBe('100');
    expect(input.classList.contains('variable-modified')).toBe(false);
    expect(row.querySelector('td').style.backgroundColor).toBe('');
  });

  it('follows a changed lookup instead of flagging an unsaved cell as modified', () => {
    const { input, row } = buildMatrix(matrixHandler);
    apply(input, row, 100);
    apply(input, row, 250);

    expect(input.value).toBe('250');
    expect(matrixHandler.matrices.get(FIELD_ID).data[CELL_KEY]).toBe('250');
    expect(input.classList.contains('variable-modified')).toBe(false);
    expect(row.querySelector('td').style.backgroundColor).toBe('');
  });

  it('clears an auto-filled cell when the lookup becomes empty', () => {
    const { input, row } = buildMatrix(matrixHandler);
    apply(input, row, 100);
    apply(input, row, null);

    expect(input.value).toBe('');
    expect(matrixHandler.matrices.get(FIELD_ID).data).not.toHaveProperty(CELL_KEY);
    expect(input.classList.contains('variable-modified')).toBe(false);
  });

  it('keeps a saved value and flags it when it differs from the lookup', () => {
    const { input, row } = buildMatrix(matrixHandler, { data: { [CELL_KEY]: '100' }, restored: true });
    apply(input, row, 250);

    expect(input.value).toBe('100');
    expect(matrixHandler.matrices.get(FIELD_ID).data[CELL_KEY]).toBe('100');
    expect(input.classList.contains('variable-modified')).toBe(true);
  });

  it('keeps the user value once an auto-filled cell has been edited', () => {
    const { input, row } = buildMatrix(matrixHandler);
    apply(input, row, 100);

    input.value = '40';
    input.dataset.userEdited = '1';
    matrixHandler.matrices.get(FIELD_ID).data[CELL_KEY] = '40';
    apply(input, row, 250);

    expect(input.value).toBe('40');
    expect(matrixHandler.matrices.get(FIELD_ID).data[CELL_KEY]).toBe('40');
    expect(input.classList.contains('variable-modified')).toBe(true);
  });

  it('treats a cell restored after auto-fill as saved', () => {
    const { input, row } = buildMatrix(matrixHandler);
    apply(input, row, 100);

    matrixHandler.restoreStaticMatrixValues(FIELD_ID);
    const matrix = matrixHandler.matrices.get(FIELD_ID);
    matrix.data[CELL_KEY] = '70';
    matrix.autoFilledVariableCells.add(CELL_KEY);
    matrixHandler.restoreStaticMatrixValues(FIELD_ID);
    apply(input, row, 250);

    expect(input.value).toBe('70');
    expect(input.classList.contains('variable-modified')).toBe(true);
  });
});

describe('overlapping variable resolves', () => {
  let matrixHandler;

  beforeEach(async () => {
    ({ matrixHandler } = await import('../../../app/static/js/forms/modules/matrix-handler.js'));
  });

  afterEach(() => {
    matrixHandler.matrices.clear();
    matrixHandler._variableResolveIssued = undefined;
    matrixHandler._variableResolveApplied = undefined;
    document.body.innerHTML = '';
    delete window.getFetch;
    delete window.__entryBootstrap;
    delete window.__entryBootstrapPromise;
  });

  function jsonResponse(body) {
    return {
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      json: async () => body,
    };
  }

  it('drops an older response that arrives after a newer one was applied', async () => {
    const { input } = buildMatrix(matrixHandler);
    const pending = [];
    window.getFetch = () => vi.fn(() => new Promise((resolve) => { pending.push(resolve); }));

    const first = matrixHandler.resolveVariablesForAllRows(FIELD_ID);
    const second = matrixHandler.resolveVariablesForAllRows(FIELD_ID);
    await vi.waitFor(() => expect(pending.length).toBe(2));

    pending[1](jsonResponse({ results: { 10: { planned_var: 250 } } }));
    await second;
    pending[0](jsonResponse({ results: { 10: { planned_var: 100 } } }));
    await first;

    expect(input.value).toBe('250');
    expect(input.classList.contains('variable-modified')).toBe(false);
  });
});

describe('auto-load batch flag', () => {
  let matrixHandler;

  beforeEach(async () => {
    ({ matrixHandler } = await import('../../../app/static/js/forms/modules/matrix-handler.js'));
  });

  afterEach(() => {
    matrixHandler.matrices.clear();
    matrixHandler.batchOperationsInProgress.clear();
    document.body.innerHTML = '';
  });

  it('releases the batch flag when auto-load returns early', async () => {
    buildMatrix(matrixHandler);
    matrixHandler.matrices.get(FIELD_ID).config = { columns: [{ name: 'Plain', type: 'number' }] };

    await matrixHandler.autoLoadEntities(FIELD_ID);

    expect(matrixHandler.batchOperationsInProgress.has(FIELD_ID)).toBe(false);
  });

  it('releases the batch flag when the matrix is missing', async () => {
    await matrixHandler.autoLoadEntities('does-not-exist');

    expect(matrixHandler.batchOperationsInProgress.has('does-not-exist')).toBe(false);
  });
});

describe('auto-filled cells after a successful save', () => {
  let matrixHandler;

  beforeEach(async () => {
    ({ matrixHandler } = await import('../../../app/static/js/forms/modules/matrix-handler.js'));
  });

  afterEach(() => {
    matrixHandler.matrices.clear();
    document.body.innerHTML = '';
  });

  function applyTo(input, row, value) {
    matrixHandler._applyResolvedVariablesToRow(
      FIELD_ID, '10', row, [input], { planned_var: value },
    );
  }

  it('treats a persisted auto-filled value as saved and flags a later differing lookup', () => {
    const { input, row } = buildMatrix(matrixHandler);
    applyTo(input, row, 100);

    const snapshot = matrixHandler.snapshotAutoFilledVariableCells();
    matrixHandler.commitSavedVariableCells(snapshot);
    applyTo(input, row, 250);

    expect(input.value).toBe('100');
    expect(matrixHandler.matrices.get(FIELD_ID).data[CELL_KEY]).toBe('100');
    expect(input.classList.contains('variable-modified')).toBe(true);
  });

  it('keeps following the lookup when the value changed while the save was in flight', () => {
    const { input, row } = buildMatrix(matrixHandler);
    applyTo(input, row, 100);

    const snapshot = matrixHandler.snapshotAutoFilledVariableCells();
    applyTo(input, row, 250);
    matrixHandler.commitSavedVariableCells(snapshot);
    applyTo(input, row, 300);

    expect(input.value).toBe('300');
    expect(input.classList.contains('variable-modified')).toBe(false);
  });

  it('does not commit anything without a snapshot', () => {
    const { input, row } = buildMatrix(matrixHandler);
    applyTo(input, row, 100);

    matrixHandler.commitSavedVariableCells(null);
    applyTo(input, row, 250);

    expect(input.value).toBe('250');
    expect(input.classList.contains('variable-modified')).toBe(false);
  });
});

describe('disabled cells are not treated as user-cleared', () => {
  let matrixHandler;

  beforeEach(async () => {
    ({ matrixHandler } = await import('../../../app/static/js/forms/modules/matrix-handler.js'));
  });

  afterEach(() => {
    matrixHandler.matrices.clear();
    document.body.innerHTML = '';
  });

  it('keeps stored data for a disabled empty variable cell', () => {
    const { input } = buildMatrix(matrixHandler, { data: { [CELL_KEY]: '100' } });
    input.value = '';
    input.disabled = true;

    matrixHandler.updateMatrixData(FIELD_ID, input);

    expect(matrixHandler.matrices.get(FIELD_ID).data[CELL_KEY]).toBe('100');
  });

  it('does not persist a blank for a disabled empty variable cell that has no stored value', () => {
    const { input } = buildMatrix(matrixHandler);
    input.value = '';
    input.disabled = true;

    matrixHandler.syncMatrixDataFromInputs(FIELD_ID);

    const matrix = matrixHandler.matrices.get(FIELD_ID);
    expect(matrix.data).not.toHaveProperty(CELL_KEY);
    expect(matrix.hiddenField.value).toBe('');
  });

  it('keeps stored data for a disabled empty number cell', () => {
    const { input } = buildMatrix(matrixHandler, { data: { [CELL_KEY]: '7' } });
    input.dataset.columnType = 'number';
    input.value = '';
    input.disabled = true;

    matrixHandler.updateMatrixData(FIELD_ID, input);

    expect(matrixHandler.matrices.get(FIELD_ID).data[CELL_KEY]).toBe('7');
  });

  it('still clears a cell flagged as user-edited (data not available)', () => {
    const { input } = buildMatrix(matrixHandler, { data: { [CELL_KEY]: '7' } });
    input.dataset.columnType = 'number';
    input.value = '';
    input.disabled = true;
    input.dataset.userEdited = '1';

    matrixHandler.updateMatrixData(FIELD_ID, input);

    expect(matrixHandler.matrices.get(FIELD_ID).data).not.toHaveProperty(CELL_KEY);
  });
});
