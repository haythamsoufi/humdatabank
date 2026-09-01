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
// This module splits any oversized value across sibling form fields
// (`name`, `name__c1`, `name__c2`, ...) immediately before submission so
// an argument-*length* rule cannot fire. Covered: matrix/plugin hidden
// inputs, and any other `b64:`-prefixed value (narrative text, emergency
// metadata, repeat-group fields). Base64 *inflates* size, so encoding
// without chunking can trip 920370 on long answers. Selects are skipped.
//
// Server reassembly: get_possibly_chunked_form_value() /
// read_waf_protected_form_value() in processors/_common.py. Repeat-group
// parsing skips `__cN` sibling keys so they are not mistaken for new fields.

const CHUNKABLE_HIDDEN_SELECTOR = [
    '.form-item-block[data-item-type="matrix"] input[type="hidden"][name]',
    '.form-item-block[data-item-type="plugin"] input[type="hidden"][name]',
].join(', ');

// Conservative margin under OWASP CRS's *documented example* tx.arg_length
// default (400 bytes) for the 920370 "Argument value too long" rule. Azure
// does not disclose its actual configured value, so this stays well below
// even the smallest plausible real-world threshold.
const MAX_CHUNK_BYTES = 350;

const CHUNK_NAME_RE = /__c\d+$/;

function isOversized(value) {
    return typeof value === 'string' && value.length > MAX_CHUNK_BYTES;
}

export function findChunkableMatrixInputs(formEl) {
    if (!formEl || typeof formEl.querySelectorAll !== 'function') return [];
    const seen = new Set();
    const out = [];

    const consider = (el) => {
        if (!el || el.disabled || !el.name || el.tagName === 'SELECT') return;
        if (CHUNK_NAME_RE.test(el.name)) return;
        if (seen.has(el)) return;
        const value = el.value;
        if (!isOversized(value)) return;
        const block = el.closest('.form-item-block');
        const itemType = block && block.getAttribute('data-item-type');
        if (itemType === 'matrix' || itemType === 'plugin' || value.startsWith('b64:')) {
            seen.add(el);
            out.push(el);
        }
    };

    Array.from(formEl.querySelectorAll(CHUNKABLE_HIDDEN_SELECTOR)).forEach(consider);
    Array.from(formEl.querySelectorAll('input[name], textarea[name]')).forEach(consider);
    return out;
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
        if (event.defaultPrevented) return;
        const restore = chunkLargeMatrixFields(target);
        // Validation (or another listener) may preventDefault after we run.
        // Restore on the next tick so the user never sees a half-chunked form.
        setTimeout(() => {
            try {
                if (event.defaultPrevented) restore();
            } catch (_) { /* no-op */ }
        }, 0);
    });
}
