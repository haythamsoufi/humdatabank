// WAF-safe free-text question encoding.
//
// Azure Application Gateway WAF's OWASP-managed signature rules
// (REQUEST-941-* XSS, REQUEST-942-* SQLi) scan raw request-body text for
// punctuation-heavy / HTML-like patterns. Narrative answers typed by real
// users (report text, notes, pasted rich text) can trip those rules even
// though they contain no attack payload — see
// docs/runbooks/incidents/waf-403-form-payload-refactor-guide.md.
//
// Matrix/plugin fields already dodge this by base64-wrapping their JSON with
// a `b64:` prefix (see modules/matrix/formatting.js::__serializeMatrixData).
// This module extends that exact convention to plain `text`/`textarea`
// question answers. Server-side, the same generic decoder
// (`decode_b64_matrix_json()` in app/services/forms/processors/_common.py) is
// reused by FormItemProcessor._process_question_data — a bare string without
// the `b64:` prefix is returned unchanged, so this is backwards-compatible
// with any client that hasn't picked up this change yet (deploy-order-safe).
//
// Trade-off (intentional, documented): base64-wrapping hides these answers
// from the WAF's signature inspection, the same trade-off already accepted
// for matrix/plugin JSON. Scope is deliberately narrow — only `text`/
// `textarea` *question* answers identified via `data-question-type` on their
// `.form-item-block` container (see entry_form.html) — so other field types
// (numbers, choices, matrix/plugin, which have their own protection) are
// untouched.
//
// Known gap: repeat-group instances rename `field_value[id]` inputs to
// `repeat_<sectionId>_<instance>_field_<fieldIndex>_<inputIndex>` on clone
// (see repeat-sections.js::updateRepeatFieldAttributes), so they fall outside
// the `field_value[` selector below and are NOT covered by this module. If
// WAF 403s are ever traced to a repeat-group free-text field, that rename
// step needs a matching data-question-type carry-over first.

const FREE_TEXT_SELECTOR =
    '.form-item-block[data-item-type="question"][data-question-type="text"] input[name^="field_value["], ' +
    '.form-item-block[data-item-type="question"][data-question-type="textarea"] textarea[name^="field_value["]';

/** unescape+encodeURIComponent makes btoa() safe for non-ASCII narrative text. */
export function encodeB64(text) {
    try {
        return 'b64:' + btoa(unescape(encodeURIComponent(text)));
    } catch (_) {
        return text;
    }
}

export function findFreeTextQuestionInputs(formEl) {
    if (!formEl || typeof formEl.querySelectorAll !== 'function') return [];
    return Array.from(formEl.querySelectorAll(FREE_TEXT_SELECTOR)).filter((el) => !el.disabled);
}

/**
 * Base64-wrap the *current* value of every free-text question input, in
 * place, on the live DOM element.
 *
 * Returns a `restore()` function that puts the original human-readable text
 * back into those same elements. Callers whose page stays open after this
 * (AJAX autosave) MUST call `restore()` as soon as they've read the mutated
 * value (e.g. right after `new FormData(form)`) — otherwise the visible
 * input/textarea would show base64 garbage to the user. Callers that trigger
 * a real browser navigation (native form submit) do not need to call
 * `restore()` since the page unloads before a repaint could show it.
 */
export function encodeFreeTextQuestionFields(formEl) {
    const inputs = findFreeTextQuestionInputs(formEl);
    const originalValues = new Map();

    inputs.forEach((input) => {
        const value = input.value;
        if (!value) return; // nothing to protect on an empty field
        if (typeof value === 'string' && value.startsWith('b64:')) return; // already wrapped
        originalValues.set(input, value);
        input.value = encodeB64(value);
    });

    return function restoreFreeTextQuestionFields() {
        originalValues.forEach((value, input) => {
            try { input.value = value; } catch (_) { /* no-op */ }
        });
    };
}

let _nativeSubmitEncoderInstalled = false;

/**
 * Install a document-level `submit` listener that base64-wraps free-text
 * question answers before the browser serializes a *native* (non-AJAX) form
 * submit. Mirrors matrix-handler.js's own
 * `document.addEventListener('submit', () => this.collectMatrixData())` hook,
 * so the final "Submit" action (which posts via a real browser form submit,
 * not fetch/FormData) gets the same WAF protection as the AJAX autosave path
 * wired up in ajax-save.js.
 *
 * Idempotent / safe to call once during page init.
 */
export function installNativeSubmitTextEncoder() {
    if (_nativeSubmitEncoderInstalled || typeof document === 'undefined') return;
    _nativeSubmitEncoderInstalled = true;

    document.addEventListener('submit', (event) => {
        const target = event.target;
        if (!target || typeof target.matches !== 'function' || !target.matches('form')) return;
        // No restore call here: this submit navigates the page away, so the
        // mutated (base64) value is never shown to the user.
        encodeFreeTextQuestionFields(target);
    });
}
