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
// Repeat-group instances rename `field_value[id]` to
// `repeat_<sectionId>_<instance>_field_<fieldIndex>_<inputIndex>` on clone
// (see repeat-sections.js::updateRepeatFieldAttributes). Those inputs keep
// `data-question-type` on `.form-item-block`, so the selectors below cover
// both top-level and repeat free-text questions.
//
// Also wrapped (same `b64:` convention):
//   - `*_emergency_metadata` / `field_disagg_metadata[id]` hidden JSON
//   - `select[data-lookup-list-id="emergency_operations"]` display values
//     (`Name (CODE)` parentheses trip REQUEST-942-*)
//   - `select[data-allow-other="true"]` (single_choice "Other" sentinel) and
//     its sibling `.other-text-input` free-text field — see
//     question-other-option.js. The literal `__other__` sentinel value is
//     itself enough to trip the WAF (observed in prod: a
//     `repeat_<section>_<instance>_field_<index>_<inputIndex>` field set to
//     `__other__` alone, no other content, was blocked) — a double-underscore
//     token reads like the Python/PHP "dunder" magic-method names
//     (`__class__`, `__construct`, ...) that generic RCE/SSTI signatures key
//     on, so it isn't just a size/punctuation issue like the rest of this
//     module. Wrapping unconditionally sidesteps needing to prove the exact
//     rule ID.
//
// Empty unused sex/age/sexage/indirect_reach inputs are stripped from the
// AJAX FormData (and already name-stripped on native submit by
// form-optimization.js). That cuts ~300 arguments on a typical UPR page.

const FREE_TEXT_SELECTOR = [
    '.form-item-block[data-item-type="question"][data-question-type="text"] input[name^="field_value["]',
    '.form-item-block[data-item-type="question"][data-question-type="textarea"] textarea[name^="field_value["]',
    '.form-item-block[data-item-type="question"][data-question-type="text"] input[name^="repeat_"]',
    '.form-item-block[data-item-type="question"][data-question-type="textarea"] textarea[name^="repeat_"]',
    'input.other-text-input[name]',
].join(', ');

const JSON_HIDDEN_SELECTOR =
    'input[name$="_emergency_metadata"], input[name^="field_disagg_metadata["]';

// Covers every single_choice select that can carry the `__other__` sentinel
// (any question with "allow other" enabled), plus the emergency-operations
// lookup select specifically (its real `Name (CODE)` display value is risky
// even without "allow other" — see comment above).
const PROTECTED_SELECT_SELECTOR =
    'select[data-lookup-list-id="emergency_operations"], select[data-allow-other="true"]';

/** Empty unused disaggregation keys — safe to omit (backend treats missing = empty). */
export const EMPTY_DISAGG_NAME_RE =
    /^(?:(?:indicator|dynamic)_\d+_|repeat_\d+_\d+_field_\d+_)(?:sex_|age_|sexage_|indirect_reach$)/;

/** unescape+encodeURIComponent makes btoa() safe for non-ASCII narrative text. */
export function encodeB64(text) {
    try {
        return 'b64:' + btoa(unescape(encodeURIComponent(text)));
    } catch (_) {
        return text;
    }
}

function _enabledNamedInputs(formEl, selector) {
    if (!formEl || typeof formEl.querySelectorAll !== 'function') return [];
    return Array.from(formEl.querySelectorAll(selector)).filter((el) => !el.disabled && el.name);
}

export function findFreeTextQuestionInputs(formEl) {
    return _enabledNamedInputs(formEl, FREE_TEXT_SELECTOR);
}

export function findWafSensitiveInputs(formEl) {
    return [
        ...findFreeTextQuestionInputs(formEl),
        ..._enabledNamedInputs(formEl, JSON_HIDDEN_SELECTOR),
        ..._enabledNamedInputs(formEl, PROTECTED_SELECT_SELECTOR),
    ];
}

/**
 * Drop empty unused sex/age/sexage/indirect_reach keys and empty file parts
 * from a FormData snapshot. Does not touch total_value / standard_value /
 * reporting_mode (those keys being present vs empty is meaningful).
 */
export function pruneEmptyWafRiskFields(formData) {
    if (!formData || typeof formData.entries !== 'function') return formData;
    const toDelete = [];
    for (const [key, value] of formData.entries()) {
        if (typeof File !== 'undefined' && value instanceof File) {
            if (!value.name && value.size === 0) toDelete.push(key);
            continue;
        }
        if (value !== '' && value != null) continue;
        if (EMPTY_DISAGG_NAME_RE.test(key)) toDelete.push(key);
    }
    toDelete.forEach((key) => formData.delete(key));
    return formData;
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
function _encodeSelectInPlace(select, wrapped) {
    // Setting select.value to a string that matches no <option> clears the
    // control in browsers. Add a temporary option, then restore/remove it.
    let option = Array.from(select.options).find((o) => o.value === wrapped);
    let created = false;
    if (!option) {
        option = document.createElement('option');
        option.value = wrapped;
        option.hidden = true;
        option.dataset.wafTemp = '1';
        select.appendChild(option);
        created = true;
    }
    select.value = wrapped;
    return function restoreSelect() {
        try {
            if (created && option.parentNode) option.remove();
        } catch (_) { /* no-op */ }
    };
}

export function encodeFreeTextQuestionFields(formEl) {
    const inputs = findWafSensitiveInputs(formEl);
    const originalValues = new Map();
    const extraRestores = [];

    inputs.forEach((input) => {
        const value = input.value;
        if (!value) return; // nothing to protect on an empty field
        if (typeof value === 'string' && value.startsWith('b64:')) return; // already wrapped
        originalValues.set(input, value);
        const wrapped = encodeB64(value);
        if (input.tagName === 'SELECT') {
            extraRestores.push(_encodeSelectInPlace(input, wrapped));
        } else {
            input.value = wrapped;
        }
    });

    return function restoreFreeTextQuestionFields() {
        extraRestores.forEach((fn) => {
            try { fn(); } catch (_) { /* no-op */ }
        });
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
        if (event.defaultPrevented) return;
        const restore = encodeFreeTextQuestionFields(target);
        // Validation (or another listener) may preventDefault after we run.
        // Restore on the next tick so the user never sees base64 in the inputs.
        setTimeout(() => {
            try {
                if (event.defaultPrevented) restore();
            } catch (_) { /* no-op */ }
        }, 0);
    });
}
