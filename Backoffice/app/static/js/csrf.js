// Expose on window for modules (e.g. form_builder) that need CSRF
function getCSRFToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (!metaTag) {
        console.error('CSRF token meta tag not found');
        return null;
    }
    return metaTag.getAttribute('content');
}

// Function to refresh CSRF token
async function refreshCSRFToken() {
    try {
        const response = await fetch('/admin/api/refresh-csrf-token', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin', // Ensure session cookies are sent
            cache: 'no-cache' // Always get fresh token
        });

        if (response.ok) {
            const data = await response.json();
            if (data.csrf_token) {
                // Update meta tag
                const metaTag = document.querySelector('meta[name="csrf-token"]');
                if (metaTag) {
                    metaTag.setAttribute('content', data.csrf_token);
                }

                // Update all hidden CSRF inputs in forms
                document.querySelectorAll('input[name="csrf_token"]').forEach(input => {
                    input.value = data.csrf_token;
                });

                // Update any JavaScript variables that hold the CSRF token
                if (window.rawCsrfTokenValue !== undefined) {
                    window.rawCsrfTokenValue = data.csrf_token;
                }

                return data.csrf_token;
            }
        }
        throw new Error('Failed to refresh CSRF token');
    } catch (error) {
        console.error('Error refreshing CSRF token:', error);
        return null;
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
        const fetchFn = (typeof window.getCsrfAwareFetch === 'function' && window.getCsrfAwareFetch()) || fetch;
        const response = await fetchFn(window.location.href, {
            method: 'GET',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        if (!response.ok) return null;
        const html = await response.text();
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const newToken = doc.querySelector('input[name="csrf_token"]')?.value;
        if (!newToken) return null;
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) metaTag.setAttribute('content', newToken);
        document.querySelectorAll('input[name="csrf_token"]').forEach(input => { input.value = newToken; });
        if (window.rawCsrfTokenValue !== undefined) window.rawCsrfTokenValue = newToken;
        return newToken;
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

    // Add CSRF token to all AJAX requests
    let originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function(data) {
        this.setRequestHeader('X-CSRFToken', getCSRFToken());
        originalSend.apply(this, arguments);
    };

    // Periodically refresh CSRF token (every 45 minutes)
    setInterval(refreshCSRFToken, 45 * 60 * 1000);
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
                if (newToken && newToken !== getCSRFToken()) {
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
