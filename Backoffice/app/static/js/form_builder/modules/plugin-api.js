// Plugin API — pure HTTP client for plugin endpoints.
// No DOM concerns; all transport/auth goes through CsrfHandler.safeFetch.
import { CsrfHandler } from './csrf-handler.js';

export async function fetchBaseTemplate() {
    const response = await CsrfHandler.safeFetch('/admin/api/plugins/base-template', {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
    });
    if (response.redirected || !response.ok) {
        const err = new Error(response.redirected ? 'session_expired' : `HTTP ${response.status}`);
        err.status = response.status;
        throw err;
    }
    return response.text();
}

export async function fetchFieldBuilderConfig(fieldTypeId, existingConfig = null) {
    const method = existingConfig ? 'POST' : 'GET';
    // WAF: wrap existing plugin config in { payload: b64 } so arbitrary config values
    // don't trigger OWASP CRS rules. get_request_data() unwraps transparently on the server.
    const body = existingConfig
        ? JSON.stringify({ payload: btoa(unescape(encodeURIComponent(JSON.stringify({ existing_config: existingConfig })))) })
        : undefined;
    const response = await CsrfHandler.safeFetch(
        `/admin/api/plugins/field-types/${fieldTypeId}/render-builder`,
        { method, headers: { 'Content-Type': 'application/json' }, body }
    );
    if (!response.ok) {
        const err = new Error(`HTTP ${response.status}`);
        err.status = response.status;
        throw err;
    }
    return response.json();
}
