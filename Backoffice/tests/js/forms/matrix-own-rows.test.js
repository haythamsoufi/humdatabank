/**
 * Matrix option "also list rows from another form filled by the same entity":
 * without entry-bootstrap the client fetches those rows itself, they survive the
 * reverse-lookup tick filter, and the request is skipped when the option is off or
 * bootstrap already listed the rows.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugError: vi.fn(),
  debugWarn: vi.fn(),
}));

const FIELD_ID = '1303';
const OWN_ROWS_URL = '/api/v1/matrix/own-rows';
const OWN_ROWS_SPEC = {
  enabled: true,
  source_template_id: 23,
  source_form_item_id: 1433,
  source_assignment_period: '__latest__',
};

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    headers: { get: () => 'application/json' },
    json: async () => body,
  };
}

const country = (id) => ({ entity_id: id, entity_type: 'country' });

/**
 * Reverse lookup lists countries 1 and 3; only 1 is ticked. The entity's own report
 * lists 2 and 1.
 */
function installFetch({ ownRowsStatus = 200, ownRowsBody = { entities: [country(2), country(1)], entity_type: 'country' } } = {}) {
  const calls = [];
  const ticks = { 1: 1, 3: 0 };
  const fetchMock = vi.fn(async (url, opts = {}) => {
    const body = opts.body ? JSON.parse(opts.body) : {};
    calls.push({ url, body });
    if (url === '/api/v1/variables/resolve') {
      if (Array.isArray(body.row_entity_ids)) {
        const results = {};
        for (const id of body.row_entity_ids) results[id] = { src_supported: ticks[id] ?? 0 };
        return jsonResponse({ results });
      }
      return jsonResponse({
        variables: { src_supported: JSON.stringify({ entities: [country(1), country(3)], entity_type: 'country' }) },
      });
    }
    if (url === OWN_ROWS_URL) return jsonResponse(ownRowsBody, ownRowsStatus);
    if (url === '/forms/matrix/search-rows') {
      return jsonResponse({
        success: true,
        options: [1, 2, 3].map((id) => ({ id, value: `Country ${id}`, data: { id } })),
      });
    }
    return jsonResponse({ error: 'unexpected' }, 404);
  });
  window.getFetch = () => fetchMock;
  return calls;
}

async function buildHandler({ ownRowsSpec = OWN_ROWS_SPEC, aesId = '4751' } = {}) {
  const { matrixAutoLoadMixin } = await import('../../../app/static/js/forms/modules/matrix/auto-load.js');
  document.body.innerHTML = `
    ${aesId ? `<input type="hidden" name="assignment_entity_status_id" value="${aesId}">` : ''}
    <div class="matrix-container" data-field-id="${FIELD_ID}"><table><tbody></tbody></table></div>
  `;
  const config = {
    lookup_list_id: 'country_map',
    auto_load_entities: true,
    columns: [{ name: 'Supported', type: 'tick', is_variable: true, variable: 'src_supported' }],
  };
  if (ownRowsSpec) config.include_own_matrix_rows = ownRowsSpec;
  return Object.assign({}, matrixAutoLoadMixin, {
    matrices: new Map([[FIELD_ID, { container: document.querySelector('.matrix-container'), config, data: {} }]]),
    batchOperationsInProgress: new Set(),
    variableResolutionDebounceTimers: new Map(),
    pendingVariableResolution: new Set(),
    getTemplateId: () => 22,
    getCsrfToken: () => 'tok',
    addDynamicRow: vi.fn((_fieldId, _label, _rowData, rowId) => {
      const tr = document.createElement('tr');
      tr.className = 'matrix-data-row';
      tr.setAttribute('data-row-id', rowId);
      tr.setAttribute('data-is-auto-loaded', 'true');
      const td = document.createElement('td');
      td.setAttribute('role', 'rowheader');
      tr.appendChild(td);
      document.querySelector('.matrix-container tbody').appendChild(tr);
    }),
    sortMatrixRows: vi.fn(),
    calculateMatrixTotals: vi.fn(),
    resolveVariablesForAllRows: vi.fn(),
    applyDuplicateEntityHighlighting: vi.fn(),
    updateLegendVisibility: vi.fn(),
    _lockMatrixContainerIfReadOnly: vi.fn(),
  });
}

const addedRowIds = (handler) => handler.addDynamicRow.mock.calls.map((call) => call[3]);

const stripedRowIds = () => [...document.querySelectorAll('td.matrix-own-row-header')]
  .map((td) => td.closest('tr').dataset.rowId);

const hostRowIds = () => [...document.querySelectorAll('td.matrix-host-row-header')]
  .map((td) => td.closest('tr').dataset.rowId);

describe('matrix rows from another form filled by the same entity', () => {
  beforeEach(() => {
    window.templateVariables = {
      src_supported: {
        entity_scope: 'entities_containing',
        source_template_id: 24,
        source_form_item_id: 967,
        source_assignment_period: '__current__',
      },
    };
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.getFetch;
    delete window.templateVariables;
    delete window.metadataContext;
    delete window.__entryBootstrap;
  });

  it('adds the own rows and keeps them through the tick filter', async () => {
    const calls = installFetch();
    const handler = await buildHandler();

    await handler.autoLoadEntities(FIELD_ID);

    expect(addedRowIds(handler)).toEqual(['1', '2']);
    // Country 1 is in the lookup too, so only country 2 is marked as an extra row.
    expect(stripedRowIds()).toEqual(['2']);
    expect(hostRowIds()).toEqual(['1']);
    const ownCalls = calls.filter((c) => c.url === OWN_ROWS_URL);
    expect(ownCalls).toHaveLength(1);
    expect(ownCalls[0].body).toEqual({ assignment_entity_status_id: 4751, form_item_id: 1303 });
  });

  it('sends the preview entity and period when there is no assignment', async () => {
    const calls = installFetch();
    const handler = await buildHandler({ aesId: null });
    window.metadataContext = { entity_id: '166', entity_type: 'country', assignment_period: '2027' };

    await handler.autoLoadEntities(FIELD_ID);

    expect(calls.find((c) => c.url === OWN_ROWS_URL).body).toEqual({
      preview_entity_id: 166,
      preview_entity_type: 'country',
      preview_period_name: '2027',
      form_item_id: 1303,
    });
    expect(addedRowIds(handler)).toEqual(['1', '2']);
  });

  it.each([
    ['missing', null],
    ['turned off', { ...OWN_ROWS_SPEC, enabled: false }],
    ['not a boolean', { ...OWN_ROWS_SPEC, enabled: 'true' }],
  ])('does not request own rows when the option is %s', async (_label, ownRowsSpec) => {
    const calls = installFetch();
    const handler = await buildHandler({ ownRowsSpec });

    await handler.autoLoadEntities(FIELD_ID);

    expect(calls.some((c) => c.url === OWN_ROWS_URL)).toBe(false);
    expect(addedRowIds(handler)).toEqual(['1']);
    expect(stripedRowIds()).toEqual([]);
    expect(hostRowIds()).toEqual([]);
  });

  it('still loads the lookup rows when the own-rows request fails', async () => {
    installFetch({ ownRowsStatus: 500, ownRowsBody: { error: 'Could not fetch matrix rows' } });
    const handler = await buildHandler();

    await handler.autoLoadEntities(FIELD_ID);

    expect(addedRowIds(handler)).toEqual(['1']);
    expect(stripedRowIds()).toEqual([]);
  });

  it('uses the entry-bootstrap rows without requesting own rows again', async () => {
    const calls = installFetch();
    window.__entryBootstrap = {
      auto_load: {
        [FIELD_ID]: {
          entities: [country(1), country(2)],
          entity_type: 'country',
          own_only_entity_ids: [2],
        },
      },
    };
    const handler = await buildHandler();

    await handler.autoLoadEntities(FIELD_ID);

    expect(calls.some((c) => c.url === OWN_ROWS_URL)).toBe(false);
    expect(addedRowIds(handler)).toEqual(['1', '2']);
    expect(stripedRowIds()).toEqual(['2']);
    expect(hostRowIds()).toEqual(['1']);
  });
});

describe('manually added row stripe', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('stripes the row header instead of filling it', async () => {
    const { matrixDynamicRowsMixin } = await import(
      '../../../app/static/js/forms/modules/matrix/dynamic-rows.js'
    );
    document.body.innerHTML = `
      <div class="matrix-container"><table><tbody>
        <tr class="matrix-data-row" data-row-id="1" data-is-auto-loaded="true">
          <td role="rowheader"></td>
        </tr>
        <tr class="matrix-data-row" data-row-id="2" data-is-auto-loaded="false">
          <td role="rowheader"></td>
        </tr>
      </tbody></table></div>
    `;
    const container = document.querySelector('.matrix-container');
    const handler = Object.assign({}, matrixDynamicRowsMixin, {
      matrices: new Map([[FIELD_ID, { container, config: { auto_load_entities: true, highlight_manual_rows: true } }]]),
      _matrixHasPrefilledCellHighlights: () => false,
      getCurrentLanguage: () => 'en',
    });

    handler.applyManualRowHighlighting(FIELD_ID);

    const header = (id) => document.querySelector(`tr[data-row-id="${id}"] td[role="rowheader"]`);
    expect(header('2').classList.contains('matrix-manual-row-header')).toBe(true);
    expect(header('2').style.backgroundColor).toBe('');
    expect(header('1').classList.contains('matrix-manual-row-header')).toBe(false);

    const legend = container.querySelector('.matrix-legend');
    expect(legend.style.display).toBe('block');
    expect(legend.textContent).toContain('Manually added row');
    expect(legend.querySelector('div[aria-label="Amber stripe for manually added rows"]').style.boxShadow)
      .toContain('inset');
  });

  it('adds a legend entry for rows carried over from your own form', async () => {
    const { matrixDynamicRowsMixin } = await import(
      '../../../app/static/js/forms/modules/matrix/dynamic-rows.js'
    );
    document.body.innerHTML = `
      <div class="matrix-container"><table><tbody>
        <tr class="matrix-data-row" data-row-id="2" data-row-origin="own">
          <td role="rowheader" class="matrix-own-row-header"></td>
        </tr>
      </tbody></table></div>
    `;
    const container = document.querySelector('.matrix-container');
    const handler = Object.assign({}, matrixDynamicRowsMixin, {
      matrices: new Map([[FIELD_ID, { container, config: { auto_load_entities: true } }]]),
      _matrixHasPrefilledCellHighlights: () => false,
      getCurrentLanguage: () => 'en',
    });

    handler.updateLegendVisibility(FIELD_ID);

    const legend = container.querySelector('.matrix-legend');
    expect(legend.style.display).toBe('block');
    expect(legend.textContent).toContain('Your past countries');
    expect(legend.textContent).toContain('no host country reported');
    expect(legend.querySelector('.matrix-legend-items')).not.toBeNull();
    expect(legend.querySelector('div[aria-label="Blue stripe for rows from your past reporting"]').style.boxShadow)
      .toContain('inset');
  });

  it('adds a legend entry for rows reported by a host country', async () => {
    const { matrixDynamicRowsMixin } = await import(
      '../../../app/static/js/forms/modules/matrix/dynamic-rows.js'
    );
    document.body.innerHTML = `
      <div class="matrix-container"><table><tbody>
        <tr class="matrix-data-row" data-row-id="1" data-row-origin="host">
          <td role="rowheader" class="matrix-host-row-header"></td>
        </tr>
        <tr class="matrix-data-row" data-row-id="2" data-row-origin="own">
          <td role="rowheader" class="matrix-own-row-header"></td>
        </tr>
      </tbody></table></div>
    `;
    const container = document.querySelector('.matrix-container');
    const handler = Object.assign({}, matrixDynamicRowsMixin, {
      matrices: new Map([[FIELD_ID, { container, config: { auto_load_entities: true } }]]),
      _matrixHasPrefilledCellHighlights: () => false,
      getCurrentLanguage: () => 'en',
    });

    handler.updateLegendVisibility(FIELD_ID);

    const legend = container.querySelector('.matrix-legend');
    const items = legend.querySelector('.matrix-legend-items');
    expect(legend.style.display).toBe('block');
    expect(legend.textContent).toContain('Reported by host country');
    expect(legend.textContent).toContain('Your past countries');
    expect(legend.textContent).toContain('no host country reported');
    expect(items).not.toBeNull();
    expect(legend.querySelector('div[aria-label="Green stripe for rows reported by a host country"]').style.boxShadow)
      .toContain('inset');
  });

  it('shows only the rows for the legend that was clicked', async () => {
    const { matrixDynamicRowsMixin } = await import(
      '../../../app/static/js/forms/modules/matrix/dynamic-rows.js'
    );
    document.body.innerHTML = `
      <div class="matrix-container"><table><tbody>
        <tr class="matrix-group-header-row" data-group="Africa"></tr>
        <tr class="matrix-data-row" data-row-id="1" data-row-label="Togo">
          <td role="rowheader" class="matrix-host-row-header"></td>
        </tr>
        <tr class="matrix-group-header-row" data-group="Asia"></tr>
        <tr class="matrix-data-row" data-row-id="2" data-row-label="Benin">
          <td role="rowheader" class="matrix-own-row-header"></td>
        </tr>
      </tbody></table></div>
    `;
    const container = document.querySelector('.matrix-container');
    const handler = Object.assign({}, matrixDynamicRowsMixin, {
      matrices: new Map([[FIELD_ID, { container, config: { auto_load_entities: true } }]]),
      _matrixHasPrefilledCellHighlights: () => false,
      getCurrentLanguage: () => 'en',
    });
    const visible = () => [...container.querySelectorAll('tr.matrix-data-row')]
      .filter((row) => !row.classList.contains('matrix-row-filtered-out'))
      .map((row) => row.dataset.rowLabel);

    handler.updateLegendVisibility(FIELD_ID);
    container.querySelector('[data-legend-filter="host"]').click();

    expect(visible()).toEqual(['Togo']);
    expect(container.querySelector('tr[data-group="Asia"]').classList.contains('matrix-row-filtered-out')).toBe(true);
    expect(container.querySelector('[data-legend-filter="host"]').getAttribute('aria-pressed')).toBe('true');
    expect(container.querySelector('[data-legend-filter="own"]').classList.contains('is-dimmed')).toBe(true);

    container.querySelector('[data-legend-clear]').click();
    expect(visible()).toEqual(['Togo', 'Benin']);
    expect(container.querySelector('[data-legend-clear]')).toBeNull();

    container.querySelector('[data-legend-filter="own"]').click();
    expect(visible()).toEqual(['Benin']);
  });
});

