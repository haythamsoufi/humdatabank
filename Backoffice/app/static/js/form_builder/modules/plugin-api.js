// Plugin API helpers for item modal
import { CsrfHandler } from './csrf-handler.js';

export async function loadBaseTemplate() {
    const response = await CsrfHandler.safeFetch('/admin/api/plugins/base-template', {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
    });
    return response.text();
}

export async function renderFieldBuilder(fieldTypeId, existingConfig) {
    const method = existingConfig ? 'POST' : 'GET';
    const body = existingConfig ? JSON.stringify({ existing_config: existingConfig }) : undefined;
    const response = await CsrfHandler.safeFetch(`/admin/api/plugins/field-types/${fieldTypeId}/render-builder`, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body
    });
    return response.json();
}
