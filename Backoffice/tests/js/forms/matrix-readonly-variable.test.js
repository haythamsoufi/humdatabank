/**
 * Read-only variable columns ignore previously saved cells, even when an older
 * config still has variable_save_value: true.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { __variableColumnPersistsValue } from '../../../app/static/js/forms/modules/matrix/formatting.js';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugError: vi.fn(),
  debugWarn: vi.fn(),
}));

const plannedColumn = {
  name: 'SP1 Planned',
  type: 'tick',
  is_variable: true,
  variable: 'planned_sp1',
  variable_readonly: true,
  variable_save_value: true,
};

describe('read-only variable columns', () => {
  it('does not persist a read-only column when save value is still ticked in config', () => {
    expect(__variableColumnPersistsValue(plannedColumn)).toBe(false);
    expect(__variableColumnPersistsValue({
      ...plannedColumn,
      variable_readonly: false,
      variable_save_value: true,
    })).toBe(true);
    expect(__variableColumnPersistsValue({
      ...plannedColumn,
      variable_readonly: false,
      variable_save_value: false,
    })).toBe(false);
  });

  describe('matrix restore and save', () => {
    let matrixHandler;

    beforeEach(async () => {
      document.body.innerHTML = `
        <div class="matrix-container" data-field-id="1407" data-can-edit="true">
          <input type="hidden" name="field_value[1407]" value="">
          <table><tbody>
            <tr>
              <td>
                <input type="checkbox" data-cell-key="10_SP1 Planned" data-column="SP1 Planned"
                       data-column-type="variable" data-variable-name="planned_sp1"
                       data-variable-save-value="false" data-variable-readonly="true" value="1">
              </td>
              <td>
                <input type="checkbox" data-cell-key="10_SP1 Supported" data-column="SP1 Supported"
                       data-column-type="tick" value="1" checked>
              </td>
            </tr>
          </tbody></table>
        </div>
      `;
      ({ matrixHandler } = await import('../../../app/static/js/forms/modules/matrix-handler.js'));
      const container = document.querySelector('.matrix-container');
      matrixHandler.matrices.set('1407', {
        container,
        config: {
          columns: [
            plannedColumn,
            { name: 'SP1 Supported', type: 'tick' },
          ],
        },
        data: {
          '10_SP1 Planned': '0',
          '10_SP1 Supported': '1',
        },
        hiddenField: container.querySelector('input[type="hidden"]'),
        lookupRefs: {},
      });
    });

    afterEach(() => {
      matrixHandler.matrices.clear();
      document.body.innerHTML = '';
    });

    it('does not restore a saved tick into a read-only variable cell', () => {
      const planned = document.querySelector('input[data-cell-key="10_SP1 Planned"]');
      planned.checked = false;

      matrixHandler.restoreStaticMatrixValues('1407');

      expect(planned.checked).toBe(false);
      expect(matrixHandler.matrices.get('1407').data).not.toHaveProperty('10_SP1 Planned');
      expect(document.querySelector('input[data-cell-key="10_SP1 Supported"]').checked).toBe(true);
    });

    it('drops the read-only column from the payload on save', () => {
      matrixHandler.collectMatrixData();
      const hidden = document.querySelector('input[type="hidden"]');
      const payload = JSON.parse(atob(hidden.value.slice(4)));
      expect(payload).not.toHaveProperty('10_SP1 Planned');
      expect(payload['10_SP1 Supported']).toBe(1);
    });
  });
});
