/**
 * Planned bilateral support stays in step with the funding tables:
 * a PNS added to one table is copied to the others, and a funding amount
 * under a ticked column checks that column on planned bilateral support.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const SCRIPT = '../../../plugins/upr/static/js/upr-ns-row-sync.js';
const TICKS = ['SP1', 'SP2', 'EFs'];

function page() {
  document.body.innerHTML = `
    <div class="matrix-container" data-field-id="955" data-can-edit="true">
      <table><tbody id="matrix-tbody-955"></tbody></table>
    </div>
    <div class="matrix-container" data-field-id="967" data-can-edit="true">
      <table><tbody id="matrix-tbody-967"></tbody></table>
    </div>
    <div class="matrix-container" data-field-id="968" data-can-edit="true">
      <table><tbody id="matrix-tbody-968"></tbody></table>
    </div>
    <div class="matrix-container" data-field-id="974" data-can-edit="true">
      <table><tbody id="matrix-tbody-974"></tbody></table>
    </div>`;
}

function fundingCell(fieldId, rowId, column, value) {
  const input = document.createElement('input');
  input.type = 'number';
  input.value = value;
  input.dataset.rowId = rowId;
  input.dataset.column = column;
  const td = document.createElement('td');
  td.appendChild(input);
  const tr = document.createElement('tr');
  tr.className = 'matrix-data-row';
  tr.dataset.rowId = rowId;
  tr.dataset.rowLabel = 'Bhutan Red Cross Society';
  tr.dataset.rowData = JSON.stringify({ _id: rowId, id: rowId, name: 'Bhutan Red Cross Society' });
  tr.appendChild(td);
  document.querySelector('[data-field-id="' + fieldId + '"] tbody').appendChild(tr);
  return input;
}

function tickBox(rowId, column) {
  return document.querySelector(
    '[data-field-id="955"] input[type="checkbox"][data-row-id="' + rowId + '"][data-column="' + column + '"]'
  );
}

describe('UPR funding amount ticks planned bilateral support', () => {
  let updateMatrixData;
  let calculateMatrixTotals;

  beforeEach(async () => {
    vi.useFakeTimers();
    page();
    updateMatrixData = vi.fn();
    calculateMatrixTotals = vi.fn();
    window.matrixHandler = {
      matrices: new Map([
        ['955', {
          config: { columns: TICKS.map((name) => ({ name, type: 'tick' })) },
          data: {},
        }],
        ['967', { config: { columns: [] }, data: {} }],
        ['968', { config: { columns: [] }, data: {} }],
        ['974', { config: { columns: [] }, data: {} }],
      ]),
      _canEditMatrix: () => true,
      getInitStatus: () => ({ state: 'ready' }),
      updateMatrixData,
      calculateMatrixTotals,
      sortMatrixRows: vi.fn(),
      updateLegendVisibility: vi.fn(),
      addDynamicRow(fieldId, _label, _data, rowId) {
        if (fieldId !== '955') return;
        const tbody = document.querySelector('#matrix-tbody-955');
        if (tbody.querySelector('tr[data-row-id="' + rowId + '"]')) return;
        const tr = document.createElement('tr');
        tr.className = 'matrix-data-row';
        tr.dataset.rowId = rowId;
        TICKS.forEach((column) => {
          const input = document.createElement('input');
          input.type = 'checkbox';
          input.dataset.rowId = rowId;
          input.dataset.column = column;
          const td = document.createElement('td');
          td.appendChild(input);
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      },
    };
    vi.resetModules();
    await import(SCRIPT);
  });

  afterEach(() => {
    if (typeof window.__uprNsRowSyncStop === 'function') window.__uprNsRowSyncStop();
    vi.useRealTimers();
    document.body.innerHTML = '';
    delete window.matrixHandler;
    delete window.__uprNsRowSyncStop;
  });

  async function flush() {
    await vi.advanceTimersByTimeAsync(400);
  }

  function edit(input) {
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  it('ticks the funded strategic priority and leaves the other priorities clear', async () => {
    const disasters = fundingCell('967', '49', 'SP2', '324');
    const enabling = fundingCell('967', '49', 'EFs', '10');

    edit(disasters);
    edit(enabling);
    await flush();

    expect(tickBox('49', 'SP2').checked).toBe(true);
    expect(tickBox('49', 'EFs').checked).toBe(true);
    expect(tickBox('49', 'SP1').checked).toBe(false);
    expect(updateMatrixData).toHaveBeenCalledWith('955', tickBox('49', 'SP2'));
    expect(calculateMatrixTotals).toHaveBeenCalledWith('955');
  });

  it('does not tick from the second or third funding-requirement matrix', async () => {
    const secondYear = fundingCell('968', '49', 'SP2', '800');
    const thirdYear = fundingCell('974', '49', 'SP1', '1500');

    edit(secondYear);
    edit(thirdYear);
    await flush();

    expect(tickBox('49', 'SP1').checked).toBe(false);
    expect(tickBox('49', 'SP2').checked).toBe(false);
    expect(updateMatrixData).not.toHaveBeenCalledWith('955', expect.anything());
  });

  it('does not tick for zero, an emergency column, or a non-PNS row', async () => {
    const zero = fundingCell('967', '49', 'SP2', '0');
    const appeal = fundingCell('967', '49', 'EA3', '100');
    const secretariat = fundingCell('967', 'IFRC Secretariat', 'SP2', '500');

    edit(zero);
    edit(appeal);
    edit(secretariat);
    await flush();

    expect(tickBox('49', 'SP2').checked).toBe(false);
    expect(tickBox('49', 'SP1').checked).toBe(false);
    expect(updateMatrixData).not.toHaveBeenCalledWith('955', expect.anything());
  });

  it('does not clear a tick when the funding amount is removed', async () => {
    const input = fundingCell('967', '49', 'SP2', '324');
    edit(input);
    await flush();
    expect(tickBox('49', 'SP2').checked).toBe(true);

    updateMatrixData.mockClear();
    calculateMatrixTotals.mockClear();
    input.value = '';
    edit(input);
    await flush();

    expect(tickBox('49', 'SP2').checked).toBe(true);
    expect(updateMatrixData).not.toHaveBeenCalledWith('955', expect.anything());
    expect(calculateMatrixTotals).not.toHaveBeenCalled();
  });
});
