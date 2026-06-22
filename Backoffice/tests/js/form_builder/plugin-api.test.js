/**
 * Tests for app/static/js/form_builder/modules/plugin-api.js
 *
 * plugin-api.js is a pure HTTP client that delegates all transport
 * to CsrfHandler.safeFetch.  We mock that method so no real network
 * calls are made.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../../../app/static/js/form_builder/modules/csrf-handler.js', () => ({
    CsrfHandler: {
        safeFetch: vi.fn(),
    },
}));

import { fetchBaseTemplate, fetchFieldBuilderConfig } from '../../../app/static/js/form_builder/modules/plugin-api.js';
import { CsrfHandler } from '../../../app/static/js/form_builder/modules/csrf-handler.js';

// ---------------------------------------------------------------------------
// fetchBaseTemplate
// ---------------------------------------------------------------------------

describe('fetchBaseTemplate', () => {
    beforeEach(() => vi.resetAllMocks());

    it('calls the correct endpoint with GET', async () => {
        CsrfHandler.safeFetch.mockResolvedValue({
            ok: true,
            redirected: false,
            text: async () => '<div>template</div>',
        });

        await fetchBaseTemplate();

        expect(CsrfHandler.safeFetch).toHaveBeenCalledWith(
            '/admin/api/plugins/base-template',
            expect.objectContaining({ method: 'GET' }),
        );
    });

    it('returns the response text on success', async () => {
        CsrfHandler.safeFetch.mockResolvedValue({
            ok: true,
            redirected: false,
            text: async () => '<div>my-template</div>',
        });

        const result = await fetchBaseTemplate();
        expect(result).toBe('<div>my-template</div>');
    });

    it('throws "session_expired" when response is redirected', async () => {
        CsrfHandler.safeFetch.mockResolvedValue({ ok: true, redirected: true });
        await expect(fetchBaseTemplate()).rejects.toThrow('session_expired');
    });

    it('throws with status code when response is not ok', async () => {
        CsrfHandler.safeFetch.mockResolvedValue({ ok: false, redirected: false, status: 503 });
        await expect(fetchBaseTemplate()).rejects.toThrow('HTTP 503');
    });

    it('sets err.status on thrown error for non-ok response', async () => {
        CsrfHandler.safeFetch.mockResolvedValue({ ok: false, redirected: false, status: 403 });
        const err = await fetchBaseTemplate().catch(e => e);
        expect(err.status).toBe(403);
    });
});

// ---------------------------------------------------------------------------
// fetchFieldBuilderConfig
// ---------------------------------------------------------------------------

describe('fetchFieldBuilderConfig', () => {
    beforeEach(() => vi.resetAllMocks());

    it('uses GET when no existing config is provided', async () => {
        CsrfHandler.safeFetch.mockResolvedValue({
            ok: true,
            json: async () => ({ fields: [] }),
        });

        await fetchFieldBuilderConfig('my-field');

        expect(CsrfHandler.safeFetch).toHaveBeenCalledWith(
            '/admin/api/plugins/field-types/my-field/render-builder',
            expect.objectContaining({ method: 'GET' }),
        );
    });

    it('uses POST when existing config is provided', async () => {
        CsrfHandler.safeFetch.mockResolvedValue({
            ok: true,
            json: async () => ({ fields: [] }),
        });

        await fetchFieldBuilderConfig('my-field', { color: 'red' });

        expect(CsrfHandler.safeFetch).toHaveBeenCalledWith(
            '/admin/api/plugins/field-types/my-field/render-builder',
            expect.objectContaining({ method: 'POST' }),
        );
    });

    it('includes a body (WAF-safe base64 payload) in POST requests', async () => {
        CsrfHandler.safeFetch.mockResolvedValue({
            ok: true,
            json: async () => ({ fields: [] }),
        });

        await fetchFieldBuilderConfig('my-field', { foo: 'bar' });

        const [, opts] = CsrfHandler.safeFetch.mock.calls[0];
        expect(opts.body).toBeTruthy();
        const parsed = JSON.parse(opts.body);
        expect(parsed).toHaveProperty('payload');
        // Verify payload is valid base64 that round-trips to the original config
        const decoded = JSON.parse(decodeURIComponent(escape(atob(parsed.payload))));
        expect(decoded.existing_config).toEqual({ foo: 'bar' });
    });

    it('returns parsed JSON on success', async () => {
        const mockData = { fields: [{ name: 'foo', type: 'text' }] };
        CsrfHandler.safeFetch.mockResolvedValue({
            ok: true,
            json: async () => mockData,
        });

        const result = await fetchFieldBuilderConfig('my-field');
        expect(result).toEqual(mockData);
    });

    it('throws with status code when response is not ok', async () => {
        CsrfHandler.safeFetch.mockResolvedValue({ ok: false, status: 404 });
        await expect(fetchFieldBuilderConfig('missing-type')).rejects.toThrow('HTTP 404');
    });

    it('sets err.status on thrown error', async () => {
        CsrfHandler.safeFetch.mockResolvedValue({ ok: false, status: 500 });
        const err = await fetchFieldBuilderConfig('bad').catch(e => e);
        expect(err.status).toBe(500);
    });

    it('uses the correct field type ID in the URL', async () => {
        CsrfHandler.safeFetch.mockResolvedValue({
            ok: true,
            json: async () => ({}),
        });

        await fetchFieldBuilderConfig('custom-slider');

        expect(CsrfHandler.safeFetch.mock.calls[0][0]).toContain('/custom-slider/render-builder');
    });
});
