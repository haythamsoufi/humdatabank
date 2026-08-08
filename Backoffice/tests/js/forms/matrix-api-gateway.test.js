/**
 * Matrix API gateway failure detection and safe JSON parsing.
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

vi.mock('../../../app/static/js/forms/modules/matrix/formatting.js', () => ({}));

describe('matrix/api gateway helpers', () => {
  beforeEach(async () => {
    window.responseAsResult = async (response) => {
      if (!response.ok) {
        return { ok: false, status: response.status, data: { error: `HTTP ${response.status}` } };
      }
      const ct = response.headers.get('Content-Type') || '';
      if (!ct.includes('application/json')) {
        return { ok: false, status: response.status, data: { error: 'Non-JSON response' } };
      }
      return { ok: true, status: response.status, data: await response.json() };
    };
  });

  it('isGatewayClassFailure detects 502/504', async () => {
    const { isGatewayClassFailure, isGatewayClassError } = await import(
      '../../../app/static/js/forms/modules/matrix/api.js'
    );
    expect(isGatewayClassFailure(502)).toBe(true);
    expect(isGatewayClassFailure(504)).toBe(true);
    expect(isGatewayClassFailure(403)).toBe(true);
    expect(isGatewayClassFailure(500)).toBe(false);
    expect(isGatewayClassError({ status: 502, message: 'HTTP 502' })).toBe(true);
    expect(isGatewayClassError({ message: "Unexpected token '<'" })).toBe(true);
  });

  it('mhResponseAsResult rejects HTML 502 without parsing JSON', async () => {
    const { mhResponseAsResult } = await import(
      '../../../app/static/js/forms/modules/matrix/api.js'
    );
    const response = {
      ok: false,
      status: 502,
      headers: { get: () => 'text/html' },
      clone: function () { return this; },
      text: async () => '<!DOCTYPE html>',
      json: async () => { throw new SyntaxError("Unexpected token '<'"); },
    };
    const result = await mhResponseAsResult(response);
    expect(result.ok).toBe(false);
    expect(result.status).toBe(502);
  });

  it('resolveVariablesForAllRows does not fan out per-row on gateway failure', async () => {
    const { matrixApiMixin } = await import(
      '../../../app/static/js/forms/modules/matrix/api.js'
    );

    document.body.innerHTML = `
      <table id="matrix-1">
        <tr class="matrix-data-row" data-row-id="1" data-row-data='{"id":1}'>
          <td><input data-column-type="variable" data-variable-name="v1"></td>
        </tr>
        <tr class="matrix-data-row" data-row-id="2" data-row-data='{"id":2}'>
          <td><input data-column-type="variable" data-variable-name="v1"></td>
        </tr>
      </table>
    `;

    const resolveVariablesForRow = vi.fn();
    const showMatrixError = vi.fn();
    const handler = Object.assign({}, matrixApiMixin, {
      matrices: new Map([['f1', { container: document.getElementById('matrix-1'), config: {}, data: {}, lookupRefs: {} }]]),
      getTemplateId: () => 10,
      _buildVarsBody: (body) => body,
      resolveVariablesForRow,
      showMatrixError,
      calculateMatrixTotals: vi.fn(),
      applyVariableLookupComparison: vi.fn(),
      _lockMatrixContainerIfReadOnly: vi.fn(),
      getCsrfToken: () => 'tok',
    });

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
      headers: { get: () => 'text/html' },
      clone: function () { return this; },
      text: async () => '<!DOCTYPE html><html></html>',
      json: async () => { throw new SyntaxError("Unexpected token '<'"); },
    }));

    await handler.resolveVariablesForAllRows('f1');

    expect(showMatrixError).toHaveBeenCalledWith('f1', expect.any(String));
    expect(resolveVariablesForRow).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
