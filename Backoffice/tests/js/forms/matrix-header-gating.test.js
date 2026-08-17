/**
 * Selectable column-header gating: cells in a column with header_type="selectable"
 * must stay disabled until a value has been chosen in that column's header
 * (see app/static/js/forms/modules/matrix/selectable-headers.js).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugError: vi.fn(),
  debugWarn: vi.fn(),
}));

vi.mock('../../../app/static/js/forms/modules/matrix/shared.js', () => ({
  _t: (k) => k,
  __canEditMatrixContainer: (container) => container?.getAttribute('data-can-edit') !== 'false',
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

  it('_saveHeaderValue keeps the GO-unmatched flag unless the caller clears it', () => {
    document.body.innerHTML = `
      <div class="matrix-container">
        <table><tbody><tr><td><input data-column="SP1"></td></tr></tbody></table>
      </div>`;
    const matrix = {
      container: document.querySelector('.matrix-container'),
      config: { columns: [{ name: 'SP1', header_type: 'selectable' }] },
      data: { 'col_header_go_unmatched|SP1': 1 },
    };
    const handler = makeHandler(matrix);

    handler._saveHeaderValue('1', 'SP1', 'Imported value');
    expect(matrix.data['col_header_go_unmatched|SP1']).toBe(1);

    handler._saveHeaderValue('1', 'SP1', 'Typed by hand', { clearGoUnmatched: true });
    expect(matrix.data['col_header_go_unmatched|SP1']).toBeUndefined();
  });

  it('_saveHeaderValue tolerates a matrix registered without a data dict', () => {
    document.body.innerHTML = `
      <div class="matrix-container">
        <table><tbody><tr><td><input data-column="SP1"></td></tr></tbody></table>
      </div>`;
    const matrix = {
      container: document.querySelector('.matrix-container'),
      config: { columns: [{ name: 'SP1', header_type: 'selectable' }] },
    };
    const handler = makeHandler(matrix);

    expect(() => handler._saveHeaderValue('1', 'SP1', 'Region A')).not.toThrow();
    expect(matrix.data['col_header|SP1']).toBe('Region A');
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

describe('selectable header picker: values, option lists and keyboard', () => {
  let matrixSelectableHeadersMixin;

  beforeEach(async () => {
    document.body.innerHTML = '';
    ({ matrixSelectableHeadersMixin } = await import(
      '../../../app/static/js/forms/modules/matrix/selectable-headers.js'
    ));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  /**
   * Mirrors the col_header_content macro in
   * app/templates/forms/entry_form/partials/matrix_table.html.
   */
  function mountPicker({ options = ['Region A'], allowOther = false, listLibrary = false } = {}) {
    const optionTags = options.map((o) => `<option value="${o}">${o}</option>`).join('');
    document.body.innerHTML = `
      <div class="matrix-container" data-field-id="1" data-can-edit="true">
        <table>
          <thead><tr><th>
            <div class="matrix-header-picker">
              <button type="button" class="matrix-header-picker-trigger" role="combobox"
                      aria-haspopup="listbox" aria-expanded="false">
                <span class="matrix-header-picker-label"></span>
              </button>
              <select class="matrix-header-select matrix-header-select-native"
                      data-field-id="1" data-col-name="SP1"
                      data-header-source="${listLibrary ? 'list_library' : 'manual'}"
                      ${listLibrary ? 'data-header-lookup-list-id="9" data-header-list-display-column="name"' : ''}
                      data-header-allow-other="${allowOther}"
                      tabindex="-1" aria-hidden="true">
                <option value="">Select...</option>
                ${optionTags}
                ${allowOther ? '<option value="__other__">Other (please specify)...</option>' : ''}
              </select>
              <ul class="matrix-header-picker-menu hidden" role="listbox"></ul>
            </div>
            ${allowOther ? '<input type="text" class="matrix-header-other-input hidden" data-field-id="1" data-col-name="SP1">' : ''}
          </th></tr></thead>
          <tbody><tr><td><input data-column="SP1" data-cell-key="r1_SP1"></td></tr></tbody>
        </table>
        <input type="hidden" name="field_value[1]">
      </div>`;

    const container = document.querySelector('.matrix-container');
    return {
      container,
      selectEl: container.querySelector('.matrix-header-select'),
      trigger: container.querySelector('.matrix-header-picker-trigger'),
      label: container.querySelector('.matrix-header-picker-label'),
      menu: container.querySelector('.matrix-header-picker-menu'),
      otherInput: container.querySelector('.matrix-header-other-input'),
      hiddenField: container.querySelector('input[type="hidden"]'),
    };
  }

  function makeHandler(container, data, extra = {}) {
    const matrix = {
      container,
      hiddenField: container.querySelector('input[type="hidden"]'),
      config: { columns: [{ name: 'SP1', header_type: 'selectable' }] },
      data,
    };
    const handler = Object.assign(
      {
        matrices: new Map([['1', matrix]]),
        _applyMatrixInputEditability: vi.fn(),
        getAssignmentEntityStatusId: () => null,
        ...extra,
      },
      matrixSelectableHeadersMixin
    );
    return { handler, matrix };
  }

  function press(handler, trigger, key) {
    handler.handleHeaderPickerKeydown({ target: trigger, key, preventDefault: () => {} });
  }

  it('switching to Other clears the previous value instead of leaving it persisted', () => {
    const { container, selectEl, otherInput } = mountPicker({ allowOther: true });
    const { handler, matrix } = makeHandler(container, { 'col_header|SP1': 'Region A' });
    selectEl.value = 'Region A';

    selectEl.value = '__other__';
    handler.handleHeaderSelectChange(selectEl);

    expect(matrix.data['col_header|SP1']).toBeUndefined();
    expect(matrix.hiddenField.value).not.toContain('Region A');
    expect(otherInput.classList.contains('hidden')).toBe(false);
  });

  it('typing a free-text header persists it and drops the GO-unmatched provenance', () => {
    const { container, selectEl, otherInput } = mountPicker({ allowOther: true });
    const { handler, matrix } = makeHandler(container, {
      'col_header|SP1': 'Afghanistan: Population Movement (MDRAF070)',
      'col_header_go_unmatched|SP1': 1,
    });
    selectEl.value = '__other__';
    otherInput.value = 'Typed by hand';

    handler.handleHeaderOtherInputChange(otherInput, { immediate: true });

    expect(matrix.data['col_header|SP1']).toBe('Typed by hand');
    expect(matrix.data['col_header_go_unmatched|SP1']).toBeUndefined();
    expect(document.querySelector('.matrix-header-picker--go-unmatched')).toBeNull();
  });

  it('re-selecting the injected GO-unmatched option keeps the flag', () => {
    const { container, selectEl } = mountPicker({ options: ['GO appeal (MDR001)'] });
    const { handler, matrix } = makeHandler(container, {
      'col_header|SP1': 'Afghanistan: Population Movement (MDRAF070)',
      'col_header_go_unmatched|SP1': 1,
    });

    handler._restoreHeaderSelectValue(selectEl, '1');
    handler.handleHeaderSelectChange(selectEl);

    expect(matrix.data['col_header|SP1']).toBe('Afghanistan: Population Movement (MDRAF070)');
    expect(matrix.data['col_header_go_unmatched|SP1']).toBe(1);
  });

  it('shows a stored value that is no longer in the option list rather than blanking the header', () => {
    const { container, selectEl, label } = mountPicker({ options: ['Region A'] });
    const { handler } = makeHandler(container, { 'col_header|SP1': 'Renamed region' });

    handler._restoreHeaderSelectValue(selectEl, '1');
    handler._syncHeaderPickerUI(selectEl);

    expect(selectEl.value).toBe('Renamed region');
    expect(selectEl.querySelector('option[data-stored-header-value="true"]')).not.toBeNull();
    expect(label.textContent).toBe('Renamed region');
    expect(label.classList.contains('matrix-header-picker-label--placeholder')).toBe(false);
  });

  it('restoring after an import that cleared the header resets the dropdown', async () => {
    const { container, selectEl, label, otherInput } = mountPicker({ allowOther: true });
    const { handler } = makeHandler(container, {});
    selectEl.value = '__other__';
    otherInput.value = 'Stale text';
    otherInput.classList.remove('hidden');

    await handler.restoreSelectableHeadersFromData('1');

    expect(selectEl.value).toBe('');
    expect(otherInput.value).toBe('');
    expect(otherInput.classList.contains('hidden')).toBe(true);
    expect(label.textContent).toBe('Select...');
  });

  it('surfaces a failed lookup-list fetch in the header label', async () => {
    const { container, selectEl, label } = mountPicker({ listLibrary: true, options: [] });
    const { handler } = makeHandler(container, {}, {
      _fetchMatrixSearchOptionsCached: vi.fn().mockRejectedValue(new Error('gateway timeout')),
    });

    await handler._initOneHeaderSelect(selectEl, '1');

    expect(selectEl.dataset.headerState).toBe('error');
    expect(label.textContent).toBe('Error loading options');
    expect(label.classList.contains('matrix-header-picker-label--error')).toBe(true);
  });

  it('shares one lookup-list load when init and restore race, so options are not duplicated', async () => {
    const { container, selectEl } = mountPicker({ listLibrary: true, options: [] });
    const fetchOptions = vi.fn().mockResolvedValue([{ value: 'Region A' }, { value: 'Region B' }]);
    const { handler } = makeHandler(container, {}, { _fetchMatrixSearchOptionsCached: fetchOptions });

    await Promise.all([
      handler._loadHeaderListOptions(selectEl, '1', '9', 'name', false),
      handler._loadHeaderListOptions(selectEl, '1', '9', 'name', false),
    ]);

    expect(fetchOptions).toHaveBeenCalledTimes(1);
    const values = Array.from(selectEl.options).map((o) => o.value);
    expect(values).toEqual(['', 'Region A', 'Region B']);
  });

  it('supports arrow-key navigation and Enter selection without a mouse', () => {
    const { container, selectEl, trigger, menu } = mountPicker({ options: ['Region A', 'Region B'] });
    const { handler, matrix } = makeHandler(container, {});
    const onChange = (e) => handler.handleHeaderSelectChange(e.target);
    document.addEventListener('change', onChange);

    try {
      handler._syncHeaderPickerUI(selectEl);
      press(handler, trigger, 'ArrowDown');
      expect(trigger.getAttribute('aria-expanded')).toBe('true');

      press(handler, trigger, 'ArrowDown');
      const active = menu.querySelector('.matrix-header-picker-option.is-active');
      expect(active.dataset.value).toBe('Region A');
      expect(trigger.getAttribute('aria-activedescendant')).toBe(active.id);

      press(handler, trigger, 'Enter');

      expect(selectEl.value).toBe('Region A');
      expect(matrix.data['col_header|SP1']).toBe('Region A');
      expect(trigger.getAttribute('aria-expanded')).toBe('false');
      expect(trigger.hasAttribute('aria-activedescendant')).toBe(false);
    } finally {
      document.removeEventListener('change', onChange);
    }
  });

  it('closes the menu on Escape and marks the selected option for assistive tech', () => {
    const { container, selectEl, trigger, menu } = mountPicker({ options: ['Region A'] });
    const { handler } = makeHandler(container, { 'col_header|SP1': 'Region A' });
    selectEl.value = 'Region A';
    handler._syncHeaderPickerUI(selectEl);

    expect(menu.querySelector('[aria-selected="true"]').dataset.value).toBe('Region A');

    handler.handleHeaderPickerToggle(trigger);
    expect(trigger.getAttribute('aria-expanded')).toBe('true');

    press(handler, trigger, 'Escape');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(menu.classList.contains('hidden')).toBe(true);
  });

  it('debounces free-text edits and flushes them on demand', () => {
    vi.useFakeTimers();
    const { container, selectEl, otherInput } = mountPicker({ allowOther: true });
    const { handler, matrix } = makeHandler(container, {});
    selectEl.value = '__other__';

    otherInput.value = 'Reg';
    handler.handleHeaderOtherInputChange(otherInput);
    otherInput.value = 'Region A';
    handler.handleHeaderOtherInputChange(otherInput);

    expect(matrix.data['col_header|SP1']).toBeUndefined();

    handler.flushPendingHeaderEdits();

    expect(matrix.data['col_header|SP1']).toBe('Region A');

    vi.advanceTimersByTime(1000);
    expect(handler._headerOtherSaveTimers.size).toBe(0);
  });
});
