/**
 * Emergency operations plugin — WAF HTML must not render in error UI.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('/static/js/forms/modules/debug.js', () => ({
  debugPluginLog: vi.fn(),
  debugPluginError: vi.fn(),
  debugPluginWarn: vi.fn(),
}));

function html502Response() {
  const body = '<!DOCTYPE html><html><body>502 Bad Gateway</body></html>';
  return {
    ok: false,
    status: 502,
    statusText: 'Bad Gateway',
    headers: { get: () => 'text/html' },
    clone: function () { return this; },
    text: async () => body,
    json: async () => { throw new SyntaxError("Unexpected token '<'"); },
  };
}

describe('emergency_operations_field gateway errors', () => {
  beforeEach(async () => {
    document.body.innerHTML = `
      <div data-field-id="eo1" data-country-iso="CH">
        <div class="plugin-field-content">
          <div class="emops-body">
            <div class="emops-list"></div>
          </div>
        </div>
      </div>
    `;
    window.responseAsResult = async (response) => {
      if (!response.ok) {
        return { ok: false, status: response.status, data: { error: `HTTP ${response.status}` } };
      }
      return { ok: true, status: response.status, data: await response.json() };
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(html502Response()));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete window.responseAsResult;
    delete window.EmergencyOperationsField;
    document.body.innerHTML = '';
    sessionStorage.clear();
    vi.resetModules();
  });

  it('shows bounded error text, not raw HTML', async () => {
    const { EmergencyOperationsField } = await import(
      '../../../plugins/emergency_operations/static/js/emergency_operations_field.js'
    );
    const field = new EmergencyOperationsField('eo1');
    field.config = {};
    await field.fetchOperations();

    const list = document.querySelector('.emops-list');
    expect(list.textContent).toMatch(/Failed to load operations/i);
    expect(list.textContent).toMatch(/502|HTTP/);
    expect(list.innerHTML).not.toMatch(/<!DOCTYPE/);
    expect(list.innerHTML).not.toMatch(/<html>/i);
  });
});
