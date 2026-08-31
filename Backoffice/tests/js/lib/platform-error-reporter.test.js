/**
 * Unit tests for platform-error-reporter.js's request-body telemetry: when a
 * fetch()-based save is blocked by the WAF (403/502/503/504 with no
 * X-App-Origin header), the reporter should attach a best-effort field count
 * / approximate byte size for the request that failed, so a future incident
 * doesn't hit the same "no evidence" dead end this one did.
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
