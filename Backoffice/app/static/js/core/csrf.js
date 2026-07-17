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

const CSRF_REFRESH_INTERVAL_MS = 45 * 60 * 1000;
const CSRF_PRE_SUBMIT_REFRESH_AFTER_MS = 40 * 60 * 1000;
const CSRF_WAKE_REFRESH_AFTER_MS = 20 * 60 * 1000;

let csrfRefreshTimerId = null;
let csrfSessionExpired = false;
let csrfLastRefreshAt = Date.now();
let csrfRefreshPromise = null;

function handleCsrfSessionExpired() {
    if (csrfSessionExpired) return;
    csrfSessionExpired = true;
    if (csrfRefreshTimerId !== null) {
        clearInterval(csrfRefreshTimerId);
        csrfRefreshTimerId = null;
    }
}

function applyCsrfToken(token) {
    if (!token) return null;

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

    csrfLastRefreshAt = Date.now();
    try {
        localStorage.setItem('csrf_last_refresh_at', String(csrfLastRefreshAt));
    } catch (_) { /* localStorage unavailable */ }
    return token;
}

async function refreshCSRFTokenViaAdminApi() {
    const response = await fetch('/admin/api/refresh-csrf-token', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin',
        cache: 'no-cache'
    });

    if (response.status === 401 || response.status === 403) {
        handleCsrfSessionExpired();
        return null;
    }

    const contentType = response.headers.get('content-type') || '';
    if (!response.ok || !contentType.includes('application/json')) {
        if (response.redirected || contentType.includes('text/html')) {
            handleCsrfSessionExpired();
            return null;
        }
        throw new Error('Admin CSRF refresh returned non-JSON response');
    }

    const data = await response.json();
    if (data.csrf_token) {
        return applyCsrfToken(data.csrf_token);
    }

    throw new Error('Failed to refresh CSRF token');
}

/**
 * Refresh CSRF token via GET /api/v1/csrf-token for any logged-in (non-admin) session.
 * Avoids re-fetching the full page HTML (~1.9 MB) that refreshCsrfFromCurrentPage() would do.
 */
async function refreshCSRFTokenViaSessionApi() {
    const response = await fetch('/api/v1/csrf-token', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin',
        cache: 'no-cache'
    });

    if (response.status === 401 || response.status === 403) {
        handleCsrfSessionExpired();
        return null;
    }

    const contentType = response.headers.get('content-type') || '';
    if (!response.ok || !contentType.includes('application/json')) {
        if (response.redirected || contentType.includes('text/html')) {
            handleCsrfSessionExpired();
            return null;
        }
        throw new Error('Session CSRF refresh returned non-JSON response');
    }

    const data = await response.json();
    if (data.csrf_token) {
        return applyCsrfToken(data.csrf_token);
    }

    throw new Error('Failed to refresh CSRF token via session API');
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
        return parseInt(localStorage.getItem('csrf_last_refresh_at'), 10) || 0;
    } catch (_) {
        return 0;
    }
}

function refreshCSRFTokenIfStale(maxAgeMs = CSRF_PRE_SUBMIT_REFRESH_AFTER_MS) {
    if (csrfSessionExpired) return Promise.resolve(null);
    const lastRefreshAt = Math.max(csrfLastRefreshAt, _crossTabLastRefreshAt());
    if ((Date.now() - lastRefreshAt) < maxAgeMs) return Promise.resolve(getCSRFToken());
    return refreshCSRFToken();
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

    if ((Date.now() - csrfLastRefreshAt) < CSRF_PRE_SUBMIT_REFRESH_AFTER_MS) return;

    event.preventDefault();
    const submitter = event.submitter || null;

    refreshCSRFToken()
        .catch(() => null)
        .then(() => submitFormAfterCsrfRefresh(form, submitter));
}

function refreshCsrfOnPageWake(event) {
    const forceRefresh = event && event.type === 'pageshow' && event.persisted;
    if (!forceRefresh && document.visibilityState === 'hidden') return;

    const maxAge = forceRefresh ? 0 : CSRF_WAKE_REFRESH_AFTER_MS;
    refreshCSRFTokenIfStale(maxAge).catch(() => null);
}

/**
 * Refresh CSRF token by re-fetching the current page and parsing the token from HTML.
 * Use for public forms where /admin/api/refresh-csrf-token is not available (admin-only).
 * Updates meta tag, all form inputs, and window.rawCsrfTokenValue.
 * @returns {Promise<string|null>} The new token or null
 */
async function refreshCsrfFromCurrentPage() {
    try {
        const fetchFn = (typeof window.getCsrfAwareFetch === 'function' && window.getCsrfAwareFetch()) || fetch;
        const response = await fetchFn(window.location.href, {
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

// Add CSRF token to all AJAX requests
document.addEventListener('DOMContentLoaded', function() {
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
    let originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function(data) {
        var token = getCSRFToken();
        if (token) {
            try { this.setRequestHeader('X-CSRFToken', token); } catch (_) {}
        }
        originalSend.apply(this, arguments);
    };

    // Periodically refresh CSRF token (every 45 minutes).
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

    let retryCount = 0;
    const maxRetries = 1; // Limit retry attempts

    const makeRequest = async (token) => {
        // Security: Validate token format
        if (!token || typeof token !== 'string' || token.length < 10) {
            throw new Error('Invalid CSRF token format');
        }

        const headers = {
            'X-CSRFToken': token,
            'X-Requested-With': 'XMLHttpRequest',
            ...options.headers
        };

        // If using FormData, add CSRF token to it
        if (options.body instanceof FormData) {
            options.body.set('csrf_token', token);
        }

        return fetch(url, {
            ...options,
            headers,
            credentials: 'same-origin' // Ensure cookies are sent
        });
    };

    let response = await makeRequest(getCSRFToken());

    // If we get a 400 error (likely CSRF expired), try refreshing the token once
    if (response.status === 400 && retryCount < maxRetries) {
        try {
            const responseClone = response.clone();
            const text = await responseClone.text();
            if (text.includes('CSRF token has expired') || text.includes('CSRF')) {
                console.log('CSRF token expired, attempting to refresh...');
                retryCount++;
                const newToken = await refreshCSRFToken();
                if (newToken) {
                    console.log('CSRF token refreshed, retrying request...');
                    response = await makeRequest(newToken);
                } else {
                    console.error('CSRF token refresh failed or returned same token');
                }
            }
        } catch (error) {
            console.error('Error during CSRF token refresh:', error);
        }
    }

    return response;
};
window.getCSRFToken = getCSRFToken;
window.refreshCSRFToken = refreshCSRFToken;
window.refreshCsrfFromCurrentPage = refreshCsrfFromCurrentPage;
