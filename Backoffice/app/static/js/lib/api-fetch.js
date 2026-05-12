/**
 * Centralized API fetch wrapper for Backoffice.
 * Combines CSRF handling, JSON parsing, and optional error display.
 *
 * Depends on: csrf.js (csrfFetch), confirm-dialogs.js (showAlert) - both loaded from core layout
 *
 * Usage:
 *   const data = await apiFetch('/admin/api/endpoint');  // GET, returns parsed JSON
 *   const data = await apiFetch('/admin/api/endpoint', { method: 'POST', body: JSON.stringify({...}) });
 *   const data = await apiFetch(url, { showAlertOnError: true });  // Show toast on HTTP error
 *
 * HTTP error parsing (parseHttpError):
 *   if (!response.ok) throw await (window.parseHttpError && window.parseHttpError(response)) || new Error(`HTTP ${response.status}`);
 */
(function() {
    'use strict';

    /**
     * Resolve fetch at call time (not module init). Head scripts use defer (e.g. csrf.js
     * defines window.getFetch), while this file runs sync at end of body — binding fetch
     * once at load would often capture plain fetch and omit CSRF headers on JSON POSTs.
     */
    function resolveFetchFn() {
        if (typeof window === 'undefined') {
            return typeof fetch !== 'undefined' ? fetch : null;
        }
        if (window.getFetch && typeof window.getFetch === 'function') {
            return window.getFetch();
        }
        return typeof fetch !== 'undefined' ? fetch : null;
    }

    /**
     * Parse HTTP error response and return an Error with the best available message.
     * Tries to extract error/message from JSON body; falls back to status text.
     *
     * @param {Response} response - Fetch Response (must have ok === false)
     * @returns {Promise<Error>} Error with .response and .status attached
     */
    async function parseHttpError(response) {
        let message = `HTTP ${response.status}: ${response.statusText || 'Unknown error'}`;
        try {
            const clone = response.clone();
            const data = await clone.json().catch(() => ({}));
            if (data && typeof data.error === 'string' && data.error.trim()) {
                message = data.error;
            } else if (data && typeof data.message === 'string' && data.message.trim()) {
                message = data.message;
            } else {
                const text = await response.text().catch(() => '');
                if (text && text.length < 300 && !text.trimStart().startsWith('<')) {
                    message = text.trim();
                }
            }
        } catch (_) {
            try {
                const text = await response.text();
                if (text && text.length < 300 && !text.trimStart().startsWith('<')) {
                    message = text.trim();
                }
            } catch (_2) {}
        }
        const err = new Error(message);
        err.response = response;
        err.status = response.status;
        return err;
    }

    /**
     * Sync helper: create Error from Response without parsing body.
     * Use when async parseHttpError is not practical (e.g. sync .then callbacks).
     *
     * @param {Response} response - Fetch Response
     * @param {string} [fallback] - Optional fallback message
     * @returns {Error}
     */
    function httpErrorSync(response, fallback) {
        const msg = fallback || `HTTP ${response.status}: ${response.statusText || 'Unknown error'}`;
        const err = new Error(msg);
        err.response = response;
        err.status = response.status;
        return err;
    }

    /**
     * Fetch with CSRF, parse JSON, optionally show errors.
     * @param {string} url - Request URL
     * @param {RequestInit & { showAlertOnError?: boolean, parseJson?: boolean }} [options]
     *   - showAlertOnError: if true, call showAlert on non-2xx response
     *   - parseJson: if true (default), parse response as JSON; if false, return raw Response
     * @returns {Promise<any>} Parsed JSON data, or throws on HTTP error
     */
    async function apiFetch(url, options = {}) {
        const { showAlertOnError = false, parseJson = true, ...fetchOptions } = options;

        const fetchFn = resolveFetchFn();
        if (!fetchFn) {
            throw new Error('No fetch implementation available');
        }
        const response = await fetchFn.call(null, url, fetchOptions);

        if (!response.ok) {
            const err = await parseHttpError(response);
            if (showAlertOnError && typeof window !== 'undefined' && window.showAlert) {
                window.showAlert(err.message, 'error');
            }
            throw err;
        }

        if (!parseJson) {
            return response;
        }

        const ct = response.headers.get('Content-Type') || '';
        if (!ct.includes('application/json')) {
            return null;
        }
        return response.json();
    }

    if (typeof window !== 'undefined') {
        window.apiFetch = apiFetch;
        /** Alias for apiFetch - use for JSON requests. Load api-fetch.js before modules that need fetchJson. */
        window.fetchJson = apiFetch;
        /** Parse HTTP error response; returns Promise<Error>. Use: throw await (window.parseHttpError && window.parseHttpError(r)) */
        window.parseHttpError = parseHttpError;
        /** Sync: create Error from Response. Use: throw (window.httpErrorSync && window.httpErrorSync(r)) */
        window.httpErrorSync = httpErrorSync;
    }
})();
