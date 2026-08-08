/**
 * Gateway / WAF HTML error page handling in api-fetch.js helpers.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

function mockResponse({ ok, status, contentType, body }) {
  const textBody = typeof body === 'string' ? body : JSON.stringify(body);
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Bad Gateway',
    headers: {
      get: (name) => (String(name).toLowerCase() === 'content-type' ? contentType : null),
    },
    clone: function () { return this; },
    text: async () => textBody,
    json: async () => JSON.parse(textBody),
  };
}

describe('api-fetch gateway HTML handling', () => {
  beforeEach(async () => {
    vi.resetModules();
    await import('../../../app/static/js/lib/api-fetch.js');
  });

  afterEach(() => {
    vi.resetModules();
  });

  it('responseAsResult returns ok:false for 502 HTML body without throwing', async () => {
    const response = mockResponse({
      ok: false,
      status: 502,
      contentType: 'text/html',
      body: '<!DOCTYPE html><html><body>Bad Gateway</body></html>',
    });
    const result = await window.responseAsResult(response);
    expect(result.ok).toBe(false);
    expect(result.status).toBe(502);
    expect(result.data.error).toMatch(/502/);
    expect(result.data.error).not.toMatch(/<!DOCTYPE/);
  });

  it('parseHttpError skips HTML bodies in error message', async () => {
    const response = mockResponse({
      ok: false,
      status: 403,
      contentType: 'text/html',
      body: '<!DOCTYPE html><html><body>Forbidden</body></html>',
    });
    const err = await window.parseHttpError(response);
    expect(err.message).toMatch(/403/);
    expect(err.message).not.toMatch(/<!DOCTYPE/);
  });

  it('apiFetch returns null for 200 non-JSON without throwing', async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockResponse({
      ok: true,
      status: 200,
      contentType: 'text/html',
      body: '<!DOCTYPE html><html></html>',
    }));
    vi.stubGlobal('fetch', fetchMock);
    window.getFetch = () => fetchMock;

    const data = await window.apiFetch('/api/test');
    expect(data).toBeNull();
    vi.unstubAllGlobals();
    delete window.getFetch;
  });
});
