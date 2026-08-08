/**
 * Discussion comment API — parseDiscussionJsonResponse on gateway HTML.
 */
import { describe, it, expect, beforeEach } from 'vitest';

function mockResponse({ ok, status, contentType, body }) {
  const textBody = typeof body === 'string' ? body : JSON.stringify(body);
  return {
    ok,
    status,
    headers: {
      get: (name) => (String(name).toLowerCase() === 'content-type' ? contentType : null),
    },
    clone: function () { return this; },
    text: async () => textBody,
    json: async () => JSON.parse(textBody),
  };
}

describe('discussion parseDiscussionJsonResponse', () => {
  beforeEach(async () => {
    await import('../../../app/static/js/lib/api-fetch.js');
  });

  it('returns bounded error for 403 HTML without SyntaxError', async () => {
    const { parseDiscussionJsonResponse } = await import(
      '../../../app/static/js/forms/modules/discussion.js'
    );
    const response = mockResponse({
      ok: false,
      status: 403,
      contentType: 'text/html',
      body: '<!DOCTYPE html><html><body>Forbidden</body></html>',
    });
    const parsed = await parseDiscussionJsonResponse(response);
    expect(parsed.ok).toBe(false);
    expect(parsed.error).toMatch(/403/);
    expect(parsed.error).not.toMatch(/<!DOCTYPE/);
  });
});
