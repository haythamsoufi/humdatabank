// csrf-handler.js - Thin wrapper over global csrf.js
//
// Delegates to window.getCSRFToken, window.refreshCSRFToken, window.csrfFetch.
// Form builder pages load csrf.js via layout before this module.

export const CsrfHandler = {
    _token: null,

    init: function() {
        // Prefer #csrf-token-data for form builder pages that inject it
        const tokenEl = typeof Utils !== 'undefined' && Utils.getElementById && Utils.getElementById('csrf-token-data');
        if (tokenEl) {
            try {
                const parsed = JSON.parse(tokenEl.textContent);
                this._token = typeof parsed === 'string' ? parsed : (parsed && parsed.csrf_token);
                if (this._token) window.rawCsrfTokenValue = this._token;
            } catch (_e) {}
        }
        if (!this._token && typeof window.getCSRFToken === 'function') {
            this._token = window.getCSRFToken();
        }
    },

    getToken: function() {
        if (this._token) return this._token;
        const t = typeof window.getCSRFToken === 'function' ? window.getCSRFToken() : null;
        if (t) this._token = t;
        return t;
    },

    refreshToken: async function() {
        const fn = typeof window.refreshCSRFToken === 'function' ? window.refreshCSRFToken : null;
        const refreshed = fn ? await fn() : null;
        if (refreshed) this._token = refreshed;
        return refreshed;
    },

    safeFetch: async function(url, options = {}) {
        const fetchFn = (window.getFetch && window.getFetch()) || window.fetch;
        return fetchFn.call(null, url, options);
    },

    addToForm: function(form, token = null) {
        const tokenValue = token || this.getToken();
        const csrfInput = form && form.querySelector('input[name*="csrf_token"]');
        if (csrfInput && tokenValue) csrfInput.value = tokenValue;
    }
};
