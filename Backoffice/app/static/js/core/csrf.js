// Expose on window for modules (e.g. form_builder) that need CSRF
function getCSRFToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (!metaTag) {
        console.error('CSRF token meta tag not found');
        return null;
    }
    return metaTag.getAttribute('content');
}

function shouldUseAdminCsrfRefresh() {
    return window.location.pathname.startsWith('/admin');
}

const CSRF_REFRESH_INTERVAL_MS = 30 * 60 * 1000;
const CSRF_PRE_SUBMIT_REFRESH_AFTER_MS = 25 * 60 * 1000;
const CSRF_WAKE_REFRESH_AFTER_MS = 5 * 60 * 1000;
// Server WTF_CSRF_TIME_LIMIT is 3600s; refresh well before that hard cutoff.
const CSRF_SERVER_MAX_AGE_MS = 55 * 60 * 1000;
const CSRF_REFRESH_AT_STORAGE_KEY = 'csrf_last_refresh_at';

let csrfRefreshTimerId = null;
let csrfSessionExpired = false;
let csrfLastRefreshAt = Date.now();
let csrfRefreshPromise = null;
let csrfWakeRefreshPromise = null;
let csrfTabHiddenAt = null;

const _nativeFetch = window.fetch.bind(window);

function handleCsrfSessionExpired() {
    if (csrfSessionExpired) return;
    csrfSessionExpired = true;
    if (csrfRefreshTimerId !== null) {
        clearInterval(csrfRefreshTimerId);
        csrfRefreshTimerId = null;
    }
}

// IMPORTANT: localStorage is used ONLY to coordinate refresh *timing* across tabs
// (so N open tabs don't each redundantly hit the refresh endpoint). It must NEVER
// be used to push a cached token *value* into the DOM: localStorage persists across
// logins/logouts and (on a dev box that restarts on every file save) across
// SECRET_KEY rotations, so a stored value can belong to a completely different
// session than the one the browser's current cookie carries. Writing such a value
// into an already-correct, freshly-rendered form silently corrupts a valid token
// and produces "The CSRF tokens do not match." The only token values that may ever
// be written into the DOM are (a) the one the server rendered into this exact page,
// or (b) one this tab obtained itself via a real network refresh call.
function applyCsrfToken(token) {
    if (!token) return null;

    _applyCsrfTokenToDom(token);

    csrfLastRefreshAt = Date.now();
    try {
        localStorage.setItem(CSRF_REFRESH_AT_STORAGE_KEY, String(csrfLastRefreshAt));
    } catch (_) { /* localStorage unavailable */ }
    return token;
}

function effectiveCsrfLastRefreshAt() {
    return Math.max(csrfLastRefreshAt, _crossTabLastRefreshAt());
}

function isCsrfTokenStale(maxAgeMs = CSRF_PRE_SUBMIT_REFRESH_AFTER_MS) {
    const ageMs = Date.now() - effectiveCsrfLastRefreshAt();
    return ageMs >= maxAgeMs || ageMs >= CSRF_SERVER_MAX_AGE_MS;
}

function waitForPendingCsrfRefresh() {
    if (csrfSessionExpired) {
        return Promise.resolve(null);
    }
    const pending = csrfWakeRefreshPromise || csrfRefreshPromise;
    return pending ? pending.catch(() => null) : Promise.resolve(null);
}

function isUnsafeHttpMethod(method) {
    return ['POST', 'PUT', 'PATCH', 'DELETE'].includes(String(method || 'GET').toUpperCase());
}

function isSameOriginRequest(input) {
    try {
        const url = typeof input === 'string' ? input : (input && input.url);
        if (!url) return false;
        return new URL(url, window.location.href).origin === window.location.origin;
    } catch (_) {
        return false;
    }
}

function getRequestMethod(input, init) {
    if (init && init.method) return String(init.method).toUpperCase();
    if (input instanceof Request && input.method) return String(input.method).toUpperCase();
    return 'GET';
}

function mergeCsrfHeaders(init, token) {
    const nextInit = { ...(init || {}) };
    const headers = new Headers(nextInit.headers || {});
    if (token) {
        headers.set('X-CSRFToken', token);
    }
    if (!headers.has('X-Requested-With')) {
        headers.set('X-Requested-With', 'XMLHttpRequest');
    }
    nextInit.headers = headers;
    if (nextInit.body instanceof FormData && token) {
        nextInit.body.set('csrf_token', token);
    }
    return nextInit;
}

function redirectToLoginAfterSessionExpiry() {
    const next = window.location.pathname + window.location.search + window.location.hash;
    window.location.href = '/login?next=' + encodeURIComponent(next);
}

/**
 * Interpret a CSRF-refresh-endpoint response.
 *
 * IMPORTANT: only treat the session as *actually* expired (latching
 * csrfSessionExpired, which permanently blocks further refresh attempts and
 * eventually forces a redirect to /login) when we have a reliable signal:
 * - 401/403 status, or
 * - fetch followed a redirect (response.redirected) — this is what happens
 *   when @login_required / @admin_required redirects an anonymous request
 *   to the login page; fetch transparently follows it and lands on login
 *   HTML with a 200 status.
 *
 * A bare non-JSON/non-ok response that was NOT redirected (e.g. a transient
 * 500/502/503 rendering an HTML error page during a deploy or proxy hiccup)
 * is NOT a session-expiry signal — it's thrown instead so the caller treats
 * it as a recoverable failure and can retry on the next stale check, rather
 * than permanently disabling CSRF refresh and force-logging the user out for
 * an unrelated infrastructure blip.
 */
async function _parseCsrfRefreshResponse(response, label) {
    if (response.status === 401 || response.status === 403) {
        handleCsrfSessionExpired();
        return null;
    }

    const contentType = response.headers.get('content-type') || '';
    if (!response.ok || !contentType.includes('application/json')) {
        if (response.redirected) {
            handleCsrfSessionExpired();
            return null;
        }
        throw new Error(`${label} returned non-JSON response (status ${response.status})`);
    }

    const data = await response.json();
    if (data.csrf_token) {
        return applyCsrfToken(data.csrf_token);
    }

    throw new Error(`Failed to refresh CSRF token (${label})`);
}

async function refreshCSRFTokenViaAdminApi() {
    const response = await _nativeFetch('/admin/api/refresh-csrf-token', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin',
        cache: 'no-cache'
    });

    return _parseCsrfRefreshResponse(response, 'Admin CSRF refresh');
}

/**
 * Refresh CSRF token via GET /api/v1/csrf-token for any logged-in (non-admin) session.
 * Avoids re-fetching the full page HTML (~1.9 MB) that refreshCsrfFromCurrentPage() would do.
 */
async function refreshCSRFTokenViaSessionApi() {
    const response = await _nativeFetch('/api/v1/csrf-token', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin',
        cache: 'no-cache'
    });

    return _parseCsrfRefreshResponse(response, 'Session CSRF refresh');
}

// Function to refresh CSRF token
async function refreshCSRFToken() {
    if (csrfSessionExpired) return null;
    if (csrfRefreshPromise) return csrfRefreshPromise;

    csrfRefreshPromise = (async () => {
        if (shouldUseAdminCsrfRefresh()) {
            return await refreshCSRFTokenViaAdminApi();
        }
        // For authenticated non-admin sessions use the lightweight JSON endpoint to avoid
        // re-fetching the full page HTML (~1.9 MB on large assignment forms).
        if (window.__userIsAuthenticated) {
            return await refreshCSRFTokenViaSessionApi();
        }
        // Fallback for anonymous public form sessions (no login, /api/v1/csrf-token not available).
        if (typeof refreshCsrfFromCurrentPage === 'function') {
            return await refreshCsrfFromCurrentPage();
        }
        return null;
    })();

    try {
        return await csrfRefreshPromise;
    } catch (error) {
        if (!csrfSessionExpired) {
            console.warn('Error refreshing CSRF token:', error);
        }
        return null;
    } finally {
        csrfRefreshPromise = null;
    }
}

// Cross-tab-aware "last refreshed at": another tab may have refreshed more
// recently than this one's in-memory csrfLastRefreshAt (set only by this tab's
// own applyCsrfToken calls). Used by the wake path so N open tabs don't each
// independently re-refresh on focus/visibility just because their own timer
// hasn't fired yet — consistent with the periodic-interval gate below.
function _crossTabLastRefreshAt() {
    try {
        return parseInt(localStorage.getItem(CSRF_REFRESH_AT_STORAGE_KEY), 10) || 0;
    } catch (_) {
        return 0;
    }
}

function _applyCsrfTokenToDom(token) {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) {
        metaTag.setAttribute('content', token);
    }

    document.querySelectorAll('input[name="csrf_token"]').forEach(input => {
        input.value = token;
    });

    if (window.rawCsrfTokenValue !== undefined) {
        window.rawCsrfTokenValue = token;
    }
}

function refreshCSRFTokenIfStale(maxAgeMs = CSRF_PRE_SUBMIT_REFRESH_AFTER_MS) {
    if (csrfSessionExpired) return Promise.resolve(null);
    if (!isCsrfTokenStale(maxAgeMs)) return Promise.resolve(getCSRFToken());
    return refreshCSRFToken();
}

function ensureFreshCsrfTokenForSubmit() {
    if (csrfSessionExpired) {
        redirectToLoginAfterSessionExpiry();
        return Promise.resolve(null);
    }
    return waitForPendingCsrfRefresh()
        .then(() => {
            if (csrfSessionExpired) {
                redirectToLoginAfterSessionExpiry();
                return null;
            }
            if (!isCsrfTokenStale()) {
                return getCSRFToken();
            }
            return refreshCSRFToken();
        })
        .then((token) => {
            if (!token) {
                if (csrfSessionExpired) {
                    redirectToLoginAfterSessionExpiry();
                }
                return null;
            }
            return token;
        });
}

function isUnsafeSameOriginForm(form) {
    if (!(form instanceof HTMLFormElement)) return false;

    const method = (form.getAttribute('method') || 'GET').toUpperCase();
    if (method === 'GET' || method === 'DIALOG') return false;

    try {
        const action = form.getAttribute('action') || window.location.href;
        return new URL(action, window.location.href).origin === window.location.origin;
    } catch (_) {
        return false;
    }
}

function submitFormAfterCsrfRefresh(form, submitter) {
    form.dataset.csrfRefreshSubmit = '1';

    if (form.requestSubmit) {
        try {
            if (submitter && submitter.form === form) {
                form.requestSubmit(submitter);
            } else {
                form.requestSubmit();
            }
            return;
        } catch (error) {
            console.warn('CSRF pre-submit requestSubmit failed; falling back to submit()', error);
        }
    }

    form.submit();
}

function handleStaleCsrfFormSubmit(event) {
    const form = event.target;
    if (!isUnsafeSameOriginForm(form)) return;
    if (event.defaultPrevented) return;

    if (form.dataset.csrfRefreshSubmit === '1') {
        delete form.dataset.csrfRefreshSubmit;
        return;
    }

    if (!csrfWakeRefreshPromise && !isCsrfTokenStale()) return;

    event.preventDefault();
    const submitter = event.submitter || null;

    ensureFreshCsrfTokenForSubmit()
        .catch(() => null)
        .then((token) => {
            if (!token) return;
            submitFormAfterCsrfRefresh(form, submitter);
        });
}

function refreshCsrfOnPageWake(event) {
    const forceRefresh = event && event.type === 'pageshow' && event.persisted;
    if (!forceRefresh && document.visibilityState === 'hidden') {
        csrfTabHiddenAt = Date.now();
        return;
    }

    let maxAge = forceRefresh ? 0 : CSRF_WAKE_REFRESH_AFTER_MS;
    if (csrfTabHiddenAt && (Date.now() - csrfTabHiddenAt) >= CSRF_WAKE_REFRESH_AFTER_MS) {
        maxAge = 0;
    }
    csrfTabHiddenAt = null;

    csrfWakeRefreshPromise = refreshCSRFTokenIfStale(maxAge)
        .catch(() => null)
        .finally(() => {
            csrfWakeRefreshPromise = null;
        });
}

function patchProgrammaticFormSubmit() {
    const originalSubmit = HTMLFormElement.prototype.submit;
    HTMLFormElement.prototype.submit = function patchedFormSubmit() {
        const form = this;
        if (!isUnsafeSameOriginForm(form)) {
            originalSubmit.call(form);
            return;
        }
        if (form.dataset.csrfRefreshSubmit === '1') {
            delete form.dataset.csrfRefreshSubmit;
            originalSubmit.call(form);
            return;
        }

        if (!csrfWakeRefreshPromise && !isCsrfTokenStale()) {
            originalSubmit.call(form);
            return;
        }

        ensureFreshCsrfTokenForSubmit()
            .catch(() => null)
            .then((token) => {
                if (!token) return;
                form.dataset.csrfRefreshSubmit = '1';
                originalSubmit.call(form);
            });
    };
}

function patchGlobalFetch() {
    window.fetch = async function csrfAwareFetch(input, init) {
        const method = getRequestMethod(input, init);
        const unsafe = isUnsafeHttpMethod(method);
        const sameOrigin = isSameOriginRequest(input);
        let requestInit = init ? { ...init } : {};

        if (unsafe && sameOrigin) {
            await waitForPendingCsrfRefresh();
            const token = await ensureFreshCsrfTokenForSubmit();
            if (!token) {
                throw new Error('CSRF token unavailable');
            }
            requestInit = mergeCsrfHeaders(requestInit, token);
        }

        let response = await _nativeFetch(input, requestInit);

        if (unsafe && sameOrigin && await responseIndicatesCsrfFailure(response)) {
            const newToken = await refreshCSRFToken();
            if (newToken) {
                requestInit = mergeCsrfHeaders(requestInit, newToken);
                response = await _nativeFetch(input, requestInit);
            } else if (csrfSessionExpired) {
                redirectToLoginAfterSessionExpiry();
            }
        }

        return response;
    };
}

async function responseIndicatesCsrfFailure(response) {
    if (response.status !== 400 && response.status !== 403) return false;

    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
        try {
            const data = await response.clone().json();
            if (data && (data.csrf_refresh_required || data.error === 'CSRF validation failed')) {
                return true;
            }
            const message = String(data.message || data.error || '').toLowerCase();
            return message.includes('csrf');
        } catch (_) {
            return false;
        }
    }

    try {
        const text = await response.clone().text();
        return /csrf/i.test(text);
    } catch (_) {
        return false;
    }
}

/**
 * Refresh CSRF token by re-fetching the current page and parsing the token from HTML.
 * Use for public forms where /admin/api/refresh-csrf-token is not available (admin-only).
 * Updates meta tag, all form inputs, and window.rawCsrfTokenValue.
 * @returns {Promise<string|null>} The new token or null
 */
async function refreshCsrfFromCurrentPage() {
    try {
        const response = await _nativeFetch(window.location.href, {
            method: 'GET',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        if (!response.ok) return null;
        const html = await response.text();
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const newToken = doc.querySelector('input[name="csrf_token"]')?.value
            || doc.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        return applyCsrfToken(newToken);
    } catch (error) {
        console.warn('Failed to refresh CSRF token from page:', error);
        return null;
    }
}

// Patch fetch immediately so deferred modules cannot capture the native fetch.
patchGlobalFetch();

// Add CSRF token to all AJAX requests
document.addEventListener('DOMContentLoaded', function() {
    const initialToken = getCSRFToken();
    if (initialToken) {
        applyCsrfToken(initialToken);
    }
    patchProgrammaticFormSubmit();

    // Add CSRF token to non-GET forms only
    document.querySelectorAll('form').forEach(form => {
        const method = (form.getAttribute('method') || 'GET').toUpperCase();
        if (method !== 'GET' && !form.querySelector('input[name="csrf_token"]')) {
            const csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrf_token';
            csrfInput.value = getCSRFToken();
            form.appendChild(csrfInput);
        }
    });

    // Add CSRF token to same-origin XHR requests only; skip if token unavailable
    // to avoid sending a literal "null" header to third-party services.
    // NOTE: send() alone doesn't see the URL, so open() must capture it first —
    // without this, the origin check below is a no-op and the token leaks to
    // any third-party endpoint called via XHR (maps, translation APIs, etc.).
    let originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url) {
        this._csrfRequestUrl = url;
        return originalOpen.apply(this, arguments);
    };

    let originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function(data) {
        if (isSameOriginRequest(this._csrfRequestUrl)) {
            var token = getCSRFToken();
            if (token) {
                try { this.setRequestHeader('X-CSRFToken', token); } catch (_) {}
            }
        }
        originalSend.apply(this, arguments);
    };

    // Periodically refresh CSRF token (every 30 minutes).
    // Skip hidden tabs (wake handler refreshes on focus) and share a cross-tab
    // localStorage gate so N open tabs do not each hit the refresh endpoint.
    csrfRefreshTimerId = setInterval(function () {
        if (typeof document !== 'undefined' && document.hidden) return;
        const last = _crossTabLastRefreshAt();
        if (last && (Date.now() - last) < CSRF_WAKE_REFRESH_AFTER_MS) return;
        refreshCSRFToken();
    }, CSRF_REFRESH_INTERVAL_MS);
    document.addEventListener('submit', handleStaleCsrfFormSubmit, true);
    document.addEventListener('visibilitychange', refreshCsrfOnPageWake);
    window.addEventListener('focus', refreshCsrfOnPageWake);
    window.addEventListener('pageshow', refreshCsrfOnPageWake);
});

// Enhanced fetch wrapper that handles CSRF token expiration
/**
 * Returns the best available fetch function: apiFetch (JSON + errors) > csrfFetch > fetch.
 * Use for Backoffice API calls to avoid duplicating fetch selection logic.
 */
function getApiFetch() {
    if (typeof window !== 'undefined' && typeof window.apiFetch === 'function') {
        return window.apiFetch;
    }
    if (typeof window !== 'undefined' && typeof window.csrfFetch === 'function') {
        return window.csrfFetch;
    }
    return typeof fetch === 'function' ? fetch : null;
}

/** Returns CSRF-aware fetch (csrfFetch or fetch). Use instead of duplicating (getCsrfFetch && getCsrfFetch()) || fetch. */
function getFetch() {
    return (typeof window.getCsrfFetch === 'function' && window.getCsrfFetch()) || (typeof fetch !== 'undefined' ? fetch : null);
}

/**
 * Single source of truth for CSRF-aware fetch. Use this instead of repeating
 * (window.getFetch && window.getFetch()) || fetch across modules.
 * Call: (window.getCsrfAwareFetch && window.getCsrfAwareFetch()) || fetch
 * or:   window.getCsrfAwareFetch ? window.getCsrfAwareFetch() : fetch
 */
function getCsrfAwareFetch() {
    return (typeof window.getCsrfFetch === 'function' && window.getCsrfFetch()) ||
           (typeof window.getFetch === 'function' && window.getFetch()) ||
           (typeof fetch !== 'undefined' ? fetch : null);
}

/** Alias: returns csrfFetch or fetch (no JSON parsing). Use when you need raw Response. */
function getCsrfFetch() {
    if (typeof window !== 'undefined' && typeof window.csrfFetch === 'function') {
        return window.csrfFetch;
    }
    return typeof fetch === 'function' ? fetch : null;
}

/**
 * Convert an HTML form into a plain JS object suitable for JSON.stringify().
 * Multi-value fields (e.g. getlist checkboxes) become arrays automatically.
 */
function formDataToJson(form) {
    const fd = new FormData(form);
    const result = {};
    for (const [key, value] of fd.entries()) {
        if (key in result) {
            if (!Array.isArray(result[key])) result[key] = [result[key]];
            result[key].push(value);
        } else {
            result[key] = value;
        }
    }
    return result;
}

/**
 * Convert a FormData entries snapshot (array of [key, value]) into a plain object.
 * Used by form-submit-ui.js which snapshots FormData before the form is modified.
 */
function snapshotToJson(snapshot) {
    const result = {};
    for (const [key, value] of snapshot) {
        if (key in result) {
            if (!Array.isArray(result[key])) result[key] = [result[key]];
            result[key].push(value);
        } else {
            result[key] = value;
        }
    }
    return result;
}

window.formDataToJson = formDataToJson;
window.snapshotToJson = snapshotToJson;
window.getApiFetch = getApiFetch;
window.getCsrfFetch = getCsrfFetch;
window.getCsrfAwareFetch = getCsrfAwareFetch;
window.getFetch = getFetch;

window.csrfFetch = async function(url, options = {}) {
    // Security: Validate URL to prevent CSRF token leakage to external domains
    try {
        const urlObj = new URL(url, window.location.origin);
        if (urlObj.origin !== window.location.origin) {
            throw new Error('CSRF tokens can only be sent to same-origin requests');
        }
    } catch (error) {
        console.error('Invalid URL for CSRF fetch:', error);
        throw new Error('Invalid URL provided to csrfFetch');
    }

    await waitForPendingCsrfRefresh();
    await refreshCSRFTokenIfStale().catch(() => null);

    const token = getCSRFToken();
    if (!token) {
        if (csrfSessionExpired) {
            redirectToLoginAfterSessionExpiry();
        }
        throw new Error('CSRF token unavailable');
    }

    let response = await _nativeFetch(url, mergeCsrfHeaders({ ...options, credentials: 'same-origin' }, token));

    if (await responseIndicatesCsrfFailure(response)) {
        const newToken = await refreshCSRFToken();
        if (newToken) {
            response = await _nativeFetch(url, mergeCsrfHeaders({ ...options, credentials: 'same-origin' }, newToken));
        } else if (csrfSessionExpired) {
            redirectToLoginAfterSessionExpiry();
        }
    }

    return response;
};
window.getCSRFToken = getCSRFToken;
window.refreshCSRFToken = refreshCSRFToken;
window.refreshCSRFTokenIfStale = refreshCSRFTokenIfStale;
window.ensureFreshCsrfTokenForSubmit = ensureFreshCsrfTokenForSubmit;
window.waitForPendingCsrfRefresh = waitForPendingCsrfRefresh;
window.refreshCsrfFromCurrentPage = refreshCsrfFromCurrentPage;
