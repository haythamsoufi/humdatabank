/**
 * Unit tests for platform-error-reporter.js's WAF-403 telemetry: when a
 * fetch()-based save is blocked (403/502/503/504 with no X-App-Origin
 * header), the reporter should attach field count / byte size, b64-wrap
 * coverage, and the page/script version the tab actually loaded so a
 * repeat ajax-save 403 can tell stale cached JS from a new WAF hit.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const WRAP_FLAGS = [
  '__humdbPlatformErrorFetchWrapped',
  '__humdbPlatformErrorJqBound',
  '__humdbWindowErrorBound',
  '__humdbUnhandledRejectionBound',
];

function mockResponse({ status = 403, headers = {} } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (name) => (headers[name.toLowerCase()] !== undefined ? headers[name.toLowerCase()] : null),
      entries: () => Object.entries(headers),
    },
  };
}

async function loadReporter() {
  vi.resetModules();
  return import('../../../app/static/js/lib/platform-error-reporter.js');
}

describe('platform-error-reporter request body telemetry', () => {
  let sendBeacon;

  beforeEach(() => {
    WRAP_FLAGS.forEach((flag) => delete window[flag]);
    try {
      sessionStorage.clear();
    } catch (_) { /* no-op */ }
    sendBeacon = vi.fn(() => true);
    vi.stubGlobal('navigator', { ...navigator, sendBeacon, userAgent: 'test-agent' });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    WRAP_FLAGS.forEach((flag) => delete window[flag]);
    delete window.ASSET_VERSION;
    document.head.innerHTML = '';
  });

  it('reports field count and approximate byte size for a FormData WAF 403', async () => {
    const underlyingFetch = vi.fn().mockResolvedValue(
      mockResponse({ status: 403, headers: {} }), // no X-App-Origin => looks like WAF
    );
    vi.stubGlobal('fetch', underlyingFetch);

    await loadReporter();

    const formData = new FormData();
    formData.set('csrf_token', 'tok');
    formData.set('field_value[10]', 'Hello world');

    await window.fetch('/forms/assignment/4100?ajax=1', { method: 'POST', body: formData });

    expect(sendBeacon).toHaveBeenCalledTimes(1);
    const [endpoint, blob] = sendBeacon.mock.calls[0];
    expect(endpoint).toBe('/api/v1/platform-error');
    const text = await blob.text();
    const payload = JSON.parse(text);

    expect(payload.error_code).toBe(403);
    expect(payload.request_field_count).toBe(2);
    // 'csrf_token' (10) + 'tok' (3) + 'field_value[10]' (15) + 'Hello world' (11) = 39
    expect(payload.request_approx_bytes).toBe(39);
    // Raw field_value is the stale-module signal: new ajax-save.js would b64-wrap it.
    expect(payload.request_b64_field_count).toBe(0);
    expect(payload.request_unwrapped_field_count).toBe(1);
    expect(payload.request_unwrapped_field_names).toEqual(['field_value[10]']);
    expect(payload.request_longest_field_name).toBe('field_value[10]');
    expect(payload.request_longest_field_bytes).toBe(11);
  });

  it('counts b64-wrapped vs unwrapped wrap-candidates on a mixed FormData 403', async () => {
    const underlyingFetch = vi.fn().mockResolvedValue(
      mockResponse({ status: 403, headers: { server: 'Microsoft-Azure-Application-Gateway/v2' } }),
    );
    vi.stubGlobal('fetch', underlyingFetch);

    await loadReporter();

    const formData = new FormData();
    formData.set('csrf_token', 'tok');
    formData.set('field_value[10]', 'b64:eyJ0ZXh0IjoiaGkifQ==');
    formData.set('field_value[11]', 'plain narrative that old JS would send raw');
    formData.set('field_other_text[11]', 'please specify');
    formData.set('action', 'save');

    await window.fetch('/assignment/1593?ajax=1', { method: 'POST', body: formData });

    const [, blob] = sendBeacon.mock.calls[0];
    const payload = JSON.parse(await blob.text());
    expect(payload.request_b64_field_count).toBe(1);
    expect(payload.request_unwrapped_field_count).toBe(2);
    expect(payload.request_unwrapped_field_names).toEqual([
      'field_value[11]',
      'field_other_text[11]',
    ]);
    expect(payload.response_server).toBe('Microsoft-Azure-Application-Gateway/v2');
  });

  it('logs page asset version and the loaded ajax-save.js ?v= on a WAF 403', async () => {
    window.ASSET_VERSION = 'deploy-waf-fix';
    vi.stubGlobal('performance', {
      getEntriesByType: (type) => {
        if (type !== 'resource') return [];
        return [{
          name: 'https://cdn.example/static/js/forms/modules/ajax-save.js?v=deploy-waf-fix.abc123def456',
          transferSize: 0,
          encodedBodySize: 18432,
        }];
      },
    });
    const underlyingFetch = vi.fn().mockResolvedValue(
      mockResponse({ status: 403, headers: {} }),
    );
    vi.stubGlobal('fetch', underlyingFetch);

    await loadReporter();

    const formData = new FormData();
    formData.set('field_value[1]', 'x');
    await window.fetch('/assignment/1593?ajax=1', { method: 'POST', body: formData });

    const [, blob] = sendBeacon.mock.calls[0];
    const payload = JSON.parse(await blob.text());
    expect(payload.asset_version).toBe('deploy-waf-fix');
    expect(payload.ajax_save_script_url).toContain('ajax-save.js?v=deploy-waf-fix.abc123def456');
    expect(payload.ajax_save_script_version).toBe('deploy-waf-fix.abc123def456');
    expect(payload.ajax_save_script_delivery).toBe('disk_cache');
    expect(payload.ajax_save_script_transfer_size).toBe(0);
    expect(payload.page_url).toBeTruthy();
  });

  it('falls back to the import-map ajax-save.js URL when resource timing is empty', async () => {
    window.ASSET_VERSION = 'pinned-sha';
    vi.stubGlobal('performance', {
      getEntriesByType: () => [],
    });
    document.head.innerHTML = `<script type="importmap">${JSON.stringify({
      scopes: {
        '/static/js/forms/modules/': {
          './ajax-save.js': '/static/js/forms/modules/ajax-save.js?v=pinned-sha.feedface9999',
        },
      },
    })}</script>`;
    const underlyingFetch = vi.fn().mockResolvedValue(
      mockResponse({ status: 403, headers: {} }),
    );
    vi.stubGlobal('fetch', underlyingFetch);

    await loadReporter();

    const formData = new FormData();
    formData.set('action', 'save');
    await window.fetch('/assignment/1593?ajax=1', { method: 'POST', body: formData });

    const [, blob] = sendBeacon.mock.calls[0];
    const payload = JSON.parse(await blob.text());
    expect(payload.ajax_save_script_url).toContain('ajax-save.js?v=pinned-sha.feedface9999');
    expect(payload.ajax_save_script_version).toBe('pinned-sha.feedface9999');
    expect(payload.asset_version).toBe('pinned-sha');
  });

  it('does not attach body telemetry for a normal (X-App-Origin) 403 from Flask itself', async () => {
    const underlyingFetch = vi.fn().mockResolvedValue(
      mockResponse({ status: 403, headers: { 'x-app-origin': '1' } }),
    );
    vi.stubGlobal('fetch', underlyingFetch);

    await loadReporter();

    const formData = new FormData();
    formData.set('field_value[1]', 'x');
    await window.fetch('/forms/assignment/1?ajax=1', { method: 'POST', body: formData });

    // Flask-origin errors are not WAF/platform errors — no beacon at all.
    expect(sendBeacon).not.toHaveBeenCalled();
  });

  it('omits body telemetry when there is no request body (e.g. a GET)', async () => {
    const underlyingFetch = vi.fn().mockResolvedValue(mockResponse({ status: 502, headers: {} }));
    vi.stubGlobal('fetch', underlyingFetch);

    await loadReporter();

    await window.fetch('/api/v1/some-endpoint');

    expect(sendBeacon).toHaveBeenCalledTimes(1);
    const [, blob] = sendBeacon.mock.calls[0];
    const payload = JSON.parse(await blob.text());
    expect(payload.request_field_count).toBeUndefined();
    expect(payload.request_approx_bytes).toBeUndefined();
  });

  it('reports approximate byte size for a plain string (JSON) body', async () => {
    const underlyingFetch = vi.fn().mockResolvedValue(mockResponse({ status: 503, headers: {} }));
    vi.stubGlobal('fetch', underlyingFetch);

    await loadReporter();

    const jsonBody = JSON.stringify({ a: 1, b: 'two' });
    await window.fetch('/api/v1/some-json-endpoint', { method: 'POST', body: jsonBody });

    const [, blob] = sendBeacon.mock.calls[0];
    const payload = JSON.parse(await blob.text());
    expect(payload.request_field_count).toBeUndefined();
    expect(payload.request_approx_bytes).toBe(jsonBody.length);
  });
});
