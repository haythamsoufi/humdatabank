/**
 * Inline translation review tool — pointer-mode selection + modal editor.
 *
 * Architecture notes
 * ──────────────────
 * • Markers (invisible Unicode tag-block chars) are injected server-side on
 *   every page load for eligible users, independent of the session "active"
 *   flag.  No page reload is needed to enable the tool.
 * • Clicking the FAB toggles client-side selection mode only. The session flag
 *   is persisted via POST so the state survives a manual page refresh.
 * • After saving a translation the DOM is patched in place — no reload needed.
 */
(function () {
    'use strict';

    const MARKER_START = '\u{e0001}';
    const MARKER_END   = '\u{e0002}';
    const MARKER_BASE  = 0xE0100;

    const PLACEHOLDER_NAMED_RE  = /%\([^)]+\)[sd]/g;
    const PLACEHOLDER_SIMPLE_RE = /(?<!%\([^)]*)\%(?:[sd]|\.\d+[fd])/g;

    const config = window.__translationReviewConfig || {};

    function _csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    if (!config.enabled || !config.canUse) return;

    /* ── DOM refs ─────────────────────────────────────────────────────────── */

    const fab        = document.getElementById('translationReviewFAB');
    const modal      = document.getElementById('translation-review-modal');
    const englishField = document.getElementById('translation-review-english');
    const editor     = document.getElementById('translation-review-editor');
    const localeLabel  = document.getElementById('translation-review-locale-label');
    const errorBox   = document.getElementById('translation-review-error');
    const saveBtn    = document.getElementById('translation-review-save');

    let active          = !!config.active;
    let hoveredElement  = null;
    let currentMsgid    = '';
    let requiredPlaceholders = [];

    /* ── Marker codec ─────────────────────────────────────────────────────── */

    /**
     * Decode all msgids hidden inside invisible markers within `text`.
     * Uses codePointAt so supplementary characters (U+E0100+) are read
     * correctly as full code points rather than surrogate halves.
     */
    function decodeMarkers(text) {
        if (!text || text.indexOf(MARKER_START) === -1) return [];
        const found = [];
        const seen  = new Set();
        let index   = 0;
        while (true) {
            const start = text.indexOf(MARKER_START, index);
            if (start === -1) break;
            const end = text.indexOf(MARKER_END, start + MARKER_START.length);
            if (end === -1) break;
            const encoded = text.slice(start + MARKER_START.length, end);
            try {
                const bytes  = Array.from(encoded, (ch) => ch.codePointAt(0) - MARKER_BASE);
                const msgid  = new TextDecoder('utf-8').decode(new Uint8Array(bytes));
                if (!seen.has(msgid)) { seen.add(msgid); found.push(msgid); }
            } catch (_) { /* ignore malformed markers */ }
            index = end + MARKER_END.length;
        }
        return found;
    }

    /**
     * Encode a msgid back into the same marker sequence the server produces.
     * Used to locate the exact marker in a text node so we can patch the
     * translated text in front of it after a save.
     */
    function encodeMarker(msgid) {
        const bytes = new TextEncoder().encode(msgid);
        const chars = Array.from(bytes, (b) => String.fromCodePoint(MARKER_BASE + b)).join('');
        return MARKER_START + chars + MARKER_END;
    }

    /* ── Placeholder helpers ──────────────────────────────────────────────── */

    function extractPlaceholders(str) {
        if (!str) return [];
        const named  = str.match(PLACEHOLDER_NAMED_RE)  || [];
        const simple = str.match(PLACEHOLDER_SIMPLE_RE) || [];
        return [...new Set([...named, ...simple])].sort();
    }

    function validatePlaceholders(sourceText, translationText) {
        const src = extractPlaceholders(sourceText);
        if (!src.length) return { valid: true, missing: [], extra: [] };
        const tgt = extractPlaceholders(translationText);
        return {
            valid:   src.every((t) => tgt.includes(t)) && tgt.every((t) => src.includes(t)),
            missing: src.filter((t) => !tgt.includes(t)),
            extra:   tgt.filter((t) => !src.includes(t)),
        };
    }

    /* ── DOM scanning ─────────────────────────────────────────────────────── */

    function collectCandidateTexts(element) {
        const candidates = [];
        const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
            if (node.nodeValue && node.nodeValue.indexOf(MARKER_START) !== -1)
                candidates.push(node.nodeValue);
        }
        ['title', 'aria-label', 'placeholder', 'alt', 'value'].forEach((attr) => {
            if (element.hasAttribute && element.hasAttribute(attr)) {
                const v = element.getAttribute(attr);
                if (v && v.indexOf(MARKER_START) !== -1) candidates.push(v);
            }
        });
        return candidates;
    }

    function findMsgidInElement(element) {
        let current = element;
        while (current && current !== document.body) {
            for (const text of collectCandidateTexts(current)) {
                const decoded = decodeMarkers(text);
                if (decoded.length) return decoded[0];
            }
            current = current.parentElement;
        }
        return null;
    }

    /* ── DOM patching after save (no reload) ─────────────────────────────── */

    /**
     * Replace the translated text preceding a specific marker sequence within a
     * raw text value.  Handles nodes that contain multiple markers by locating
     * the previous MARKER_END to find where the preceding translation begins.
     */
    function _replaceInText(raw, marker, newText) {
        const pos = raw.indexOf(marker);
        if (pos === -1) return raw;
        const prevEnd = raw.lastIndexOf(MARKER_END, pos - 1);
        const textStart = prevEnd === -1 ? 0 : prevEnd + MARKER_END.length;
        return raw.slice(0, textStart) + newText + raw.slice(pos);
    }

    /**
     * Walk the entire DOM and patch every text node / attribute / document.title
     * that contains the marker for `msgid`, replacing its visible translated text
     * with `newText`.  The marker itself is preserved so future edits still work.
     */
    function patchDomWithNewTranslation(msgid, newText) {
        const marker = encodeMarker(msgid);

        // Text nodes
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
            if (node.nodeValue && node.nodeValue.includes(marker))
                node.nodeValue = _replaceInText(node.nodeValue, marker, newText);
        }

        // Attributes
        ['title', 'aria-label', 'placeholder', 'alt', 'value'].forEach((attr) => {
            document.querySelectorAll(`[${attr}]`).forEach((el) => {
                const val = el.getAttribute(attr);
                if (val && val.includes(marker))
                    el.setAttribute(attr, _replaceInText(val, marker, newText));
            });
        });

        // Document title
        if (document.title.includes(marker))
            document.title = _replaceInText(document.title, marker, newText);
    }

    /* ── Toast notification ───────────────────────────────────────────────── */

    let _toastTimer = null;

    function showSaveToast() {
        let toast = document.getElementById('tr-save-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'tr-save-toast';
            toast.textContent = '✓ ' + ((config.i18n && config.i18n.saved) || 'Saved');
            document.body.appendChild(toast);
        }
        clearTimeout(_toastTimer);
        toast.classList.add('visible');
        _toastTimer = setTimeout(() => toast.classList.remove('visible'), 2400);
    }

    /* ── Mode switching ───────────────────────────────────────────────────── */

    function setReviewMode(enabled) {
        active = !!enabled;
        document.body.classList.toggle('translation-review-mode', active);
        if (fab) {
            fab.classList.toggle('active', active);
            fab.setAttribute('aria-pressed', active ? 'true' : 'false');
            const label = fab.querySelector('.fab-label');
            if (label) {
                label.textContent = active
                    ? ((config.i18n && config.i18n.reviewMode) || 'Review mode')
                    : ((config.i18n && config.i18n.translate)  || 'Translate');
            }
        }
        if (!active) clearHover();
    }

    function clearHover() {
        if (hoveredElement) {
            hoveredElement.classList.remove('translation-review-hover');
            hoveredElement = null;
        }
    }

    /* ── Toggle (no page reload) ──────────────────────────────────────────── */

    async function postToggle() {
        const data = await window.apiFetch(config.urls.toggle, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': _csrfToken(),
            },
            body: JSON.stringify({}),
            credentials: 'same-origin',
        });
        if (!data || data.success === false)
            throw new Error((data && (data.message || data.error)) || 'Toggle failed');
        setReviewMode(data.active);
    }

    /* ── Error display ────────────────────────────────────────────────────── */

    function showError(message) {
        if (!errorBox) return;
        if (!message) {
            errorBox.classList.add('hidden');
            errorBox.textContent = '';
            return;
        }
        errorBox.classList.remove('hidden');
        errorBox.textContent = message;
    }

    /* ── Editor serialisation ─────────────────────────────────────────────── */

    function serializeEditor() {
        let out = '';
        editor.childNodes.forEach((node) => {
            if (node.nodeType === Node.TEXT_NODE) {
                out += node.textContent;
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                out += node.classList.contains('i18n-placeholder-chip')
                    ? (node.getAttribute('data-token') || node.textContent || '')
                    : (node.textContent || '');
            }
        });
        return out;
    }

    function appendChip(token) {
        const chip = document.createElement('span');
        chip.className = 'i18n-placeholder-chip';
        chip.setAttribute('contenteditable', 'false');
        chip.setAttribute('data-token', token);
        chip.textContent = token;
        editor.appendChild(chip);
    }

    function renderEditor(text, placeholders) {
        editor.innerHTML = '';
        if (!text) { placeholders.forEach(appendChip); validateEditor(); return; }
        const tokens = [...placeholders].sort((a, b) => b.length - a.length);
        let remaining = text;
        while (remaining.length) {
            let matched = false;
            for (const token of tokens) {
                const idx = remaining.indexOf(token);
                if (idx === -1) continue;
                if (idx > 0) editor.appendChild(document.createTextNode(remaining.slice(0, idx)));
                appendChip(token);
                remaining = remaining.slice(idx + token.length);
                matched = true;
                break;
            }
            if (!matched) { editor.appendChild(document.createTextNode(remaining)); remaining = ''; }
        }
        validateEditor();
    }

    function validateEditor() {
        const text       = serializeEditor();
        const validation = validatePlaceholders(currentMsgid, text);
        if (!validation.valid) {
            const parts = [];
            if (validation.missing.length)
                parts.push(((config.i18n && config.i18n.missingPlaceholders) || 'Missing placeholders') + ': ' + validation.missing.join(', '));
            if (validation.extra.length)
                parts.push(((config.i18n && config.i18n.extraPlaceholders) || 'Unexpected placeholders') + ': ' + validation.extra.join(', '));
            showError(parts.join(' '));
            if (saveBtn) saveBtn.disabled = true;
            return false;
        }
        showError('');
        if (saveBtn) saveBtn.disabled = false;
        return true;
    }

    /* ── Modal open / close ───────────────────────────────────────────────── */

    function closeModal() {
        if (modal) modal.classList.add('hidden');
        currentMsgid = '';
        requiredPlaceholders = [];
        showError('');
    }

    function openModal(msgid) {
        currentMsgid         = msgid;
        requiredPlaceholders = extractPlaceholders(msgid);
        if (englishField) englishField.value = msgid;
        editor.innerHTML = '';
        showError('');
        if (saveBtn) saveBtn.disabled = true;

        const msgidB64 = btoa(unescape(encodeURIComponent(msgid)));
        const url = `${config.urls.getString}?msgid_b64=${encodeURIComponent(msgidB64)}&locale=${encodeURIComponent(config.locale)}`;

        window.apiFetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' })
            .then((data) => {
                if (!data || data.success === false)
                    throw new Error((data && data.message) || 'Failed to load translation');
                if (localeLabel && data.language_display_name)
                    localeLabel.textContent = data.language_display_name;
                renderEditor(data.current_translation || '', requiredPlaceholders);
                if (modal) modal.classList.remove('hidden');
            })
            .catch((err) => {
                showError(err.message || 'Failed to load translation');
                if (modal) modal.classList.remove('hidden');
            });
    }

    /* ── Save (patch DOM in place, no reload) ────────────────────────────── */

    async function saveTranslation() {
        if (!validateEditor()) return;
        const translation = serializeEditor();
        if (saveBtn) saveBtn.disabled = true;
        try {
            const data = await window.apiFetch(config.urls.saveString, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': _csrfToken(),
                },
                credentials: 'same-origin',
                body: JSON.stringify({ msgid: currentMsgid, locale: config.locale, translation }),
            });
            if (!data || data.success === false)
                throw new Error((data && (data.message || data.error)) || 'Save failed');

            // Patch every DOM occurrence of this string — no reload needed
            const newText = (data && data.new_translation) || translation;
            patchDomWithNewTranslation(currentMsgid, newText);
            closeModal();
            showSaveToast();
        } catch (error) {
            showError(error.message || 'Save failed');
            if (saveBtn) saveBtn.disabled = false;
        }
    }

    /* ── Event listeners ──────────────────────────────────────────────────── */

    if (fab) {
        fab.addEventListener('click', () => {
            postToggle().catch((err) => console.error('[TranslationReview] toggle failed:', err));
        });
    }

    // Hover: highlight the nearest ancestor that contains a marker
    document.addEventListener('mouseover', (event) => {
        if (!active) return;
        const target = event.target;
        if (!(target instanceof Element)) return;
        if (target.closest('#translationReviewFAB, #translation-review-modal, #aiChatbotFAB, #aiChatWidget')) {
            clearHover();
            return;
        }
        const msgid = findMsgidInElement(target);
        if (!msgid) { clearHover(); return; }
        if (hoveredElement !== target) {
            clearHover();
            hoveredElement = target;
            hoveredElement.classList.add('translation-review-hover');
        }
    }, true);

    // Click: open modal for the hovered/clicked marked element
    document.addEventListener('click', (event) => {
        if (!active) return;
        const target = event.target;
        if (!(target instanceof Element)) return;
        if (target.closest('#translationReviewFAB, #translation-review-modal')) return;
        const msgid = findMsgidInElement(target);
        if (!msgid) return;
        event.preventDefault();
        event.stopPropagation();
        openModal(msgid);
    }, true);

    // Escape: exit review mode (no reload)
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            if (modal && !modal.classList.contains('hidden')) {
                closeModal();
                return;
            }
            if (active) {
                setReviewMode(false);
                // Persist deactivation in session (fire-and-forget)
                fetch(config.urls.toggle, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': _csrfToken(),
                    },
                    body: JSON.stringify({ active: false }),
                    credentials: 'same-origin',
                }).catch(() => {});
            }
        }
    });

    // Cancel button inside modal
    const cancelBtn = document.getElementById('translation-review-cancel');
    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);

    // Editor events
    editor.addEventListener('input', validateEditor);
    editor.addEventListener('paste', (event) => {
        event.preventDefault();
        const text = (event.clipboardData || window.clipboardData).getData('text/plain');
        document.execCommand('insertText', false, text);
    });

    if (saveBtn) saveBtn.addEventListener('click', saveTranslation);

    if (window.ModalUtils && modal) window.ModalUtils.makeModal('#translation-review-modal');

    // Apply initial mode without reload
    setReviewMode(active);
})();
