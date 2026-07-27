import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const CSRF_TOKEN_STORAGE_KEY = 'csrf_token_value';
const CSRF_REFRESH_AT_STORAGE_KEY = 'csrf_last_refresh_at';

let fetchMock;

function setupDom(token = 'initial-token-value-1234567890') {
    document.head.innerHTML = `<meta name="csrf-token" content="${token}">`;
    document.body.innerHTML = `
        <form id="test-form" method="POST" action="/save">
            <input type="hidden" name="csrf_token" value="${token}">
        </form>
    `;
}

function mockCsrfRefresh(token = 'refreshed-token-value-1234567890') {
    return {
        ok: true,
        status: 200,
        redirected: false,
        headers: { get: () => 'application/json' },
        json: async () => ({ csrf_token: token }),
    };
}

async function loadCsrfModule() {
    vi.resetModules();
    await import('../../../app/static/js/core/csrf.js');
    document.dispatchEvent(new Event('DOMContentLoaded'));
}

describe('csrf.js long-idle refresh handling', () => {
    beforeEach(() => {
        localStorage.clear();
        setupDom();
        window.__userIsAuthenticated = true;
        fetchMock = vi.fn().mockResolvedValue(mockCsrfRefresh());
        vi.stubGlobal('fetch', fetchMock);
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
        delete window.__userIsAuthenticated;
        delete window.refreshCSRFToken;
        delete window.refreshCSRFTokenIfStale;
        delete window.ensureFreshCsrfTokenForSubmit;
        delete window.getCSRFToken;
        delete window.csrfFetch;
    });

    it('stores the server token in localStorage on DOMContentLoaded', async () => {
        await loadCsrfModule();
        expect(localStorage.getItem(CSRF_TOKEN_STORAGE_KEY)).toBe('initial-token-value-1234567890');
    });

    it('syncs a fresher token from localStorage into the DOM', async () => {
        await loadCsrfModule();
        localStorage.setItem(CSRF_TOKEN_STORAGE_KEY, 'shared-token-value-1234567890');
        localStorage.setItem(CSRF_REFRESH_AT_STORAGE_KEY, String(Date.now()));

        window.dispatchEvent(new StorageEvent('storage', {
            key: CSRF_TOKEN_STORAGE_KEY,
            newValue: 'shared-token-value-1234567890',
            storageArea: localStorage,
        }));

        expect(document.querySelector('meta[name="csrf-token"]').getAttribute('content'))
            .toBe('shared-token-value-1234567890');
        expect(document.querySelector('input[name="csrf_token"]').value)
            .toBe('shared-token-value-1234567890');
    });

    it('refreshes before stale form submit after long idle', async () => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
        fetchMock.mockResolvedValue(mockCsrfRefresh());

        await loadCsrfModule();
        vi.advanceTimersByTime(26 * 60 * 1000);

        const token = await window.ensureFreshCsrfTokenForSubmit();
        expect(token).toBe('refreshed-token-value-1234567890');
        expect(fetchMock).toHaveBeenCalledWith('/api/v1/csrf-token', expect.any(Object));
    });

    it('csrfFetch retries once after a JSON CSRF failure', async () => {
        await loadCsrfModule();

        fetchMock
            .mockResolvedValueOnce({
                ok: false,
                status: 400,
                headers: { get: () => 'application/json' },
                clone: () => ({
                    json: async () => ({ csrf_refresh_required: true, error: 'CSRF validation failed' }),
                }),
            })
            .mockResolvedValueOnce(mockCsrfRefresh('retry-token-value-1234567890'))
            .mockResolvedValueOnce({
                ok: true,
                status: 200,
                headers: { get: () => 'application/json' },
            });

        const response = await window.csrfFetch('/api/example', { method: 'POST', body: '{}' });

        expect(response.status).toBe(200);
        expect(fetchMock).toHaveBeenCalledTimes(3);
    });

    it('patches global fetch to refresh before stale unsafe requests', async () => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
        fetchMock.mockImplementation((url) => {
            if (String(url).includes('/api/v1/csrf-token')) {
                return Promise.resolve(mockCsrfRefresh('idle-refreshed-token-1234567890'));
            }
            return Promise.resolve({
                ok: true,
                status: 200,
                headers: { get: () => 'application/json' },
                json: async () => ({ success: true }),
            });
        });

        await loadCsrfModule();
        vi.advanceTimersByTime(3 * 60 * 60 * 1000);

        const response = await window.fetch('/api/example', {
            method: 'POST',
            body: '{}',
            headers: { 'Content-Type': 'application/json' },
        });

        expect(fetchMock.mock.calls.some((call) => call[0] === '/api/v1/csrf-token')).toBe(true);
        expect(fetchMock.mock.calls.some((call) => call[0] === '/api/example')).toBe(true);
        expect(document.querySelector('meta[name="csrf-token"]').getAttribute('content'))
            .toBe('idle-refreshed-token-1234567890');
        expect(response.status).toBe(200);
    });

    it('does not proceed with unsafe fetch when refresh fails after long idle', async () => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
        fetchMock.mockResolvedValue({
            ok: false,
            status: 500,
            redirected: false,
            headers: { get: () => 'text/html' },
        });

        await loadCsrfModule();
        vi.advanceTimersByTime(3 * 60 * 60 * 1000);

        await expect(window.fetch('/api/example', {
            method: 'POST',
            body: '{}',
            headers: { 'Content-Type': 'application/json' },
        })).rejects.toThrow('CSRF token unavailable');

        expect(fetchMock.mock.calls.some((call) => call[0] === '/api/example')).toBe(false);
    });
});
