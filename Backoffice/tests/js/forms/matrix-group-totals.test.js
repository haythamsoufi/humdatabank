/**
 * Optional subtotal row under each matrix row group.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugError: vi.fn(),
  debugWarn: vi.fn(),
}));

const FIELD_ID = '1303';

const columns = [
  { name: 'Planned', type: 'number_whole' },
  { name: 'Spent', type: 'number_whole' },
];

function dataRow(id, label, group) {
  return `<tr class="matrix-data-row" data-row-id="${id}" data-row-label="${label}" data-group="${group}">
    <td role="rowheader">${label}</td>
  </tr>`;
}

function mount(handler, { groupTotals = true } = {}) {
  document.body.innerHTML = `
    <div class="matrix-container" data-field-id="${FIELD_ID}">
      <table><tbody id="matrix-tbody-${FIELD_ID}">
        ${dataRow('1', 'Benin', 'Africa')}
        ${dataRow('2', 'Togo', 'Africa')}
        ${dataRow('3', 'Cuba', 'Americas')}
      </tbody></table>
    </div>
  `;
  handler.matrices.set(FIELD_ID, {
    container: document.querySelector('.matrix-container'),
    config: {
      group_by_column: 'region',
      group_table_enabled: true,
      group_totals_enabled: groupTotals,
      show_row_totals: true,
      show_column_totals: false,
      columns,
    },
    data: {
      '1_Planned': 100,
      '1_Spent': 40,
      '2_Planned': 50,
      '2_Spent': 10,
      '3_Planned': 5,
      '3_Spent': 1,
    },
  });
}

function groupTotal(group, column) {
  const row = document.querySelector(`tr.matrix-group-header-row[data-group="${group}"]`);
  return row?.querySelector(`.matrix-group-total[data-column="${column}"]`)?.textContent;
}

describe('matrix group totals', () => {
  let matrixHandler;

  beforeEach(async () => {
    ({ matrixHandler } = await import('../../../app/static/js/forms/modules/matrix-handler.js'));
    matrixHandler.matrices.clear();
  });

  afterEach(() => {
    matrixHandler.matrices.clear();
    document.body.innerHTML = '';
  });

  it('adds a subtotal row per group and sums its rows', () => {
    mount(matrixHandler);

    matrixHandler.sortMatrixRows(FIELD_ID);

    expect(groupTotal('Africa', 'Planned')).toBe('150');
    expect(groupTotal('Africa', 'Spent')).toBe('50');
    expect(document.querySelector('tr.matrix-group-header-row[data-group="Africa"] .matrix-group-row-total').textContent)
      .toBe('200');
    expect(groupTotal('Americas', 'Planned')).toBe('5');
    expect(groupTotal('Americas', 'Spent')).toBe('1');
    expect(document.querySelector('tr.matrix-group-header-row[data-group="Africa"] td[role="rowheader"]').textContent)
      .toContain('Africa');
    expect(document.querySelectorAll('tr.matrix-group-total-row')).toHaveLength(0);

    const order = [...document.querySelectorAll('#matrix-tbody-1303 > tr')].map((row) => (
      row.classList.contains('matrix-group-header-row') ? `header:${row.dataset.group}` : row.dataset.rowLabel
    ));
    expect(order).toEqual(['header:Africa', 'Benin', 'Togo', 'header:Americas', 'Cuba']);
  });

  it('keeps the subtotal visible when the group is collapsed', () => {
    mount(matrixHandler);
    matrixHandler.sortMatrixRows(FIELD_ID);

    document.querySelector('tr.matrix-group-header-row[data-group="Africa"]').click();

    const hidden = [...document.querySelectorAll('tr.matrix-data-row.hidden')]
      .map((row) => row.dataset.rowLabel);
    expect(hidden).toEqual(['Benin', 'Togo']);
    expect(groupTotal('Africa', 'Planned')).toBe('150');
    expect(document.querySelector('tr[data-row-label="Cuba"]').classList.contains('hidden')).toBe(false);
  });

  it('adds no subtotal rows when the option is off', () => {
    mount(matrixHandler, { groupTotals: false });

    matrixHandler.sortMatrixRows(FIELD_ID);

    expect(document.querySelectorAll('.matrix-group-total')).toHaveLength(0);
    expect(document.querySelector('tr.matrix-group-header-row[data-group="Africa"] td').colSpan).toBeGreaterThan(1);
    expect(document.querySelectorAll('tr.matrix-group-header-row')).toHaveLength(2);
  });
});
