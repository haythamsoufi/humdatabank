/**
 * Tests for app/static/js/form_builder/modules/csrf-handler.js
 *
 * CsrfHandler delegates to window globals (window.getCSRFToken,
 * window.refreshCSRFToken, window.csrfFetch).  Tests mock those globals
 * directly so no network calls are made.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// utils.js must be loaded first so window.Utils is available for CsrfHandler.init
import '../../../app/static/js/form_builder/modules/utils.js';
import { CsrfHandler } from '../../../app/static/js/form_builder/modules/csrf-handler.js';

function clearCsrfState() {
    CsrfHandler._token = null;
    delete window.getCSRFToken;
    delete window.refreshCSRFToken;
    delete window.getFetch;
    delete window.rawCsrfTokenValue;
    document.getElementById('csrf-token-data')?.remove();
}

// ---------------------------------------------------------------------------
// getToken
// ---------------------------------------------------------------------------

describe('CsrfHandler.getToken', () => {
    beforeEach(clearCsrfState);

    it('returns cached _token when already set', () => {
        CsrfHandler._token = 'cached-token';
        expect(CsrfHandler.getToken()).toBe('cached-token');
    });

    it('falls back to window.getCSRFToken when no cached token', () => {
        window.getCSRFToken = () => 'from-window';
        expect(CsrfHandler.getToken()).toBe('from-window');
    });

    it('caches the result from window.getCSRFToken', () => {
        window.getCSRFToken = () => 'fetched-token';
        CsrfHandler.getToken();
        delete window.getCSRFToken;
        expect(CsrfHandler._token).toBe('fetched-token');
    });

    it('returns null when no source available', () => {
        expect(CsrfHandler.getToken()).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// init
// ---------------------------------------------------------------------------

describe('CsrfHandler.init', () => {
    beforeEach(clearCsrfState);

    it('reads token from #csrf-token-data when value is a plain string', () => {
        const el = document.createElement('script');
        el.type = 'application/json';
        el.id = 'csrf-token-data';
        el.textContent = '"my-csrf-token"';
        document.body.appendChild(el);

        CsrfHandler.init();
        expect(CsrfHandler._token).toBe('my-csrf-token');
    });

    it('reads token from #csrf-token-data when value is an object with csrf_token', () => {
        const el = document.createElement('script');
        el.type = 'application/json';
        el.id = 'csrf-token-data';
        el.textContent = JSON.stringify({ csrf_token: 'object-token' });
        document.body.appendChild(el);

        CsrfHandler.init();
        expect(CsrfHandler._token).toBe('object-token');
    });

    it('also sets window.rawCsrfTokenValue when parsing succeeds', () => {
        const el = document.createElement('script');
        el.type = 'application/json';
        el.id = 'csrf-token-data';
        el.textContent = '"raw-token"';
        document.body.appendChild(el);

        CsrfHandler.init();
        expect(window.rawCsrfTokenValue).toBe('raw-token');
    });

    it('falls back to window.getCSRFToken when #csrf-token-data is absent', () => {
        window.getCSRFToken = () => 'fallback-token';
        CsrfHandler.init();
        expect(CsrfHandler._token).toBe('fallback-token');
    });

    it('handles malformed JSON in #csrf-token-data gracefully', () => {
        const el = document.createElement('script');
        el.type = 'application/json';
        el.id = 'csrf-token-data';
        el.textContent = 'NOT_VALID_JSON';
        document.body.appendChild(el);

        expect(() => CsrfHandler.init()).not.toThrow();
    });
});

// ---------------------------------------------------------------------------
// addToForm
// ---------------------------------------------------------------------------

describe('CsrfHandler.addToForm', () => {
    beforeEach(() => { CsrfHandler._token = 'stored-token'; });

    it('sets the value of a csrf_token input', () => {
        const form = document.createElement('form');
        const input = document.createElement('input');
        input.name = 'csrf_token';
        form.appendChild(input);

        CsrfHandler.addToForm(form);
        expect(input.value).toBe('stored-token');
    });

    it('uses an explicitly provided token instead of the stored one', () => {
        const form = document.createElement('form');
        const input = document.createElement('input');
        input.name = 'csrf_token';
        form.appendChild(input);

        CsrfHandler.addToForm(form, 'override-token');
        expect(input.value).toBe('override-token');
    });

    it('does nothing when form has no csrf input', () => {
        const form = document.createElement('form');
        expect(() => CsrfHandler.addToForm(form)).not.toThrow();
    });

    it('handles null form gracefully', () => {
        expect(() => CsrfHandler.addToForm(null)).not.toThrow();
    });
});

// ---------------------------------------------------------------------------
// safeFetch
// ---------------------------------------------------------------------------

describe('CsrfHandler.safeFetch', () => {
    let mockFetch;

    beforeEach(() => {
        CsrfHandler._token = 'csrf-123';
        mockFetch = vi.fn().mockResolvedValue({ ok: true, status: 200 });
        window.getFetch = () => mockFetch;
    });

    afterEach(() => {
        delete window.getFetch;
        vi.restoreAllMocks();
    });

    it('adds X-CSRFToken header from the stored token', async () => {
        await CsrfHandler.safeFetch('/api/test');
        const [, opts] = mockFetch.mock.calls[0];
        expect(opts.headers.get('X-CSRFToken')).toBe('csrf-123');
    });

    it('does not overwrite an X-CSRFToken header already in options', async () => {
        await CsrfHandler.safeFetch('/api/test', {
            headers: { 'X-CSRFToken': 'caller-token' },
        });
        const [, opts] = mockFetch.mock.calls[0];
        expect(opts.headers.get('X-CSRFToken')).toBe('caller-token');
    });

    it('passes through other headers unchanged', async () => {
        await CsrfHandler.safeFetch('/api/test', {
            headers: { 'Content-Type': 'application/json' },
        });
        const [, opts] = mockFetch.mock.calls[0];
        expect(opts.headers.get('Content-Type')).toBe('application/json');
    });

    it('calls the correct URL', async () => {
        await CsrfHandler.safeFetch('/admin/api/test');
        expect(mockFetch.mock.calls[0][0]).toBe('/admin/api/test');
    });

    it('omits the CSRF header when no token is available', async () => {
        CsrfHandler._token = null;
        delete window.getCSRFToken;
        await CsrfHandler.safeFetch('/api/no-token');
        const [, opts] = mockFetch.mock.calls[0];
        expect(opts.headers).toBeUndefined();
    });
});

// ---------------------------------------------------------------------------
// refreshToken
// ---------------------------------------------------------------------------

describe('CsrfHandler.refreshToken', () => {
    afterEach(() => {
        delete window.refreshCSRFToken;
        CsrfHandler._token = null;
    });

    it('calls window.refreshCSRFToken and caches the new token', async () => {
        window.refreshCSRFToken = vi.fn().mockResolvedValue('new-token');
        const token = await CsrfHandler.refreshToken();
        expect(token).toBe('new-token');
        expect(CsrfHandler._token).toBe('new-token');
    });

    it('returns null when window.refreshCSRFToken is not available', async () => {
        const token = await CsrfHandler.refreshToken();
        expect(token).toBeNull();
    });
});
