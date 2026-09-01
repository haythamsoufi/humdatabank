// WAF-safe matrix field chunking.
//
// Why this exists
// ----------------
// Large matrix tables serialize into one JSON blob, base64-wrapped with a
// `b64:` prefix to dodge WAF content-signature rules (see
// __serializeMatrixData in modules/matrix/formatting.js). Base64 inflates
// the JSON by ~33%, and a single `field_value[id]` argument holding that
// whole blob can trip a *separate* WAF rule family that signature-avoidance
// does nothing for: OWASP CRS's per-argument length limit (920360-920390,
// e.g. `920370` "Argument value too long", documented example default
// `tx.arg_length=400`). A real production save payload analyzed 2026-09-01
// contained a single 48-key matrix argument at 1384 bytes (b64-wrapped) —
// see the "Azure App Gateway WAF Rules the App Should Respect" section of
// docs/runbooks/incidents/waf-403-form-payload-refactor-guide.md.
//
// This module splits any matrix hidden-field value above a conservative
// byte threshold across multiple actual form fields
// (`field_value[id]`, `field_value[id]__c1`, `field_value[id]__c2`, ...)
// immediately before submission, so the WAF sees several small arguments
// instead of one large one — an argument-*length* rule cannot fire
// regardless of how large the *total* table is. Reassembled transparently
// server-side by get_possibly_chunked_form_value()
// (app/services/forms/processors/_common.py) before the existing
// decode_b64_matrix_json() call, so nothing downstream of that changes.
//
// Known gap: only matrix fields are covered so far (this is the one field
// type with concrete evidence — see above). Plugin fields (`field_value[id]`
// JSON via the same `b64:` convention, see processors/plugin.py) are not yet
// chunked; extend MATRIX_HIDDEN_SELECTOR/this module's call sites if a
// plugin field is later implicated the same way.

const MATRIX_HIDDEN_SELECTOR =
    '.form-item-block[data-item-type="matrix"] input[type="hidden"][name^="field_value["]';

// Conservative margin under OWASP CRS's *documented example* tx.arg_length
// default (400 bytes) for the 920370 "Argument value too long" rule. Azure
// does not disclose its actual configured value, so this stays well below
// even the smallest plausible real-world threshold.
const MAX_CHUNK_BYTES = 350;

export function findChunkableMatrixInputs(formEl) {
    if (!formEl || typeof formEl.querySelectorAll !== 'function') return [];
    return Array.from(formEl.querySelectorAll(MATRIX_HIDDEN_SELECTOR)).filter((el) => !el.disabled && el.name);
}

function splitIntoChunks(value, maxBytes) {
    const chunks = [];
    for (let i = 0; i < value.length; i += maxBytes) {
        chunks.push(value.slice(i, i + maxBytes));
    }
    return chunks;
}

/**
 * Split any over-threshold matrix hidden-field value across sibling hidden
 * inputs (`__c1`, `__c2`, ...) in place, on the live DOM.
 *
 * Returns a restore() function that removes the injected sibling inputs and
 * puts the original single value back on the real matrix hidden input —
 * call it after an AJAX submit completes (success or failure) so the
 * in-memory matrix-handler state (which still expects one full-value hidden
 * input) is undisturbed. Native (non-AJAX) submits don't need restore(): the
 * page navigates away before any in-memory state would matter again.
 */
export function chunkLargeMatrixFields(formEl) {
    const inputs = findChunkableMatrixInputs(formEl);
    const injectedInputs = [];
    const originalValues = new Map();

    inputs.forEach((input) => {
        const value = input.value;
        if (!value || value.length <= MAX_CHUNK_BYTES) return; // already WAF-safe length

        const chunks = splitIntoChunks(value, MAX_CHUNK_BYTES);
        if (chunks.length < 2) return;

        originalValues.set(input, value);
        input.value = chunks[0];

        const baseName = input.name;
        let insertAfter = input;
        for (let i = 1; i < chunks.length; i += 1) {
            const chunkInput = document.createElement('input');
            chunkInput.type = 'hidden';
            chunkInput.name = `${baseName}__c${i}`;
            chunkInput.value = chunks[i];
            // Insert after the previously-inserted chunk (not always after
            // `input`), so DOM/document order matches chunk order — not
            // load-bearing for FormData (which reads names, not positions),
            // but keeps things sane for anything else that walks the DOM.
            insertAfter.insertAdjacentElement('afterend', chunkInput);
            insertAfter = chunkInput;
            injectedInputs.push(chunkInput);
        }
    });

    return function restoreChunkedMatrixFields() {
        injectedInputs.forEach((el) => {
            try { el.remove(); } catch (_) { /* no-op */ }
        });
        originalValues.forEach((value, input) => {
            try { input.value = value; } catch (_) { /* no-op */ }
        });
    };
}

let _nativeSubmitChunkerInstalled = false;

/**
 * Install a document-level `submit` listener that chunks large matrix
 * fields before the browser serializes a *native* (non-AJAX) form submit.
 * Mirrors installNativeSubmitTextEncoder() in question-text-waf-encode.js.
 */
export function installNativeSubmitMatrixChunker() {
    if (_nativeSubmitChunkerInstalled || typeof document === 'undefined') return;
    _nativeSubmitChunkerInstalled = true;

    document.addEventListener('submit', (event) => {
        const target = event.target;
        if (!target || typeof target.matches !== 'function' || !target.matches('form')) return;
        // No restore call here: this submit navigates the page away, so the
        // injected chunk inputs are never shown to the user.
        chunkLargeMatrixFields(target);
    });
}
