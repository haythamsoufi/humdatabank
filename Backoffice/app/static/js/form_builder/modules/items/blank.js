/**
 * BlankBodyEditor — rich-text toolbar for the Blank/Note body text field.
 *
 * The editor is a contenteditable div. The canonical form value lives in the
 * hidden textarea (#item-question-definition), which is kept in sync via the
 * `input` event so syncUIToShared() always reads a current value.
 *
 * Toolbar commands use execCommand (still universally supported for simple
 * formatting). `styleWithCSS` is enabled so colours produce <span style="color">
 * rather than the legacy <font color> element.
 *
 * Paste strategy (aligned with MS Office clipboard):
 * - Prefer `text/html` when present (Word/Outlook) and sanitize to our allowlist
 * - Fall back to `text/plain` with newlines → <br> (Excel cells, Notepad)
 * Backend bleach sanitization remains the source of truth on save.
 */

/** Escape plain text and turn newlines into <br>. */
function plainTextToSafeHtml(text) {
    return String(text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\r\n|\r|\n/g, '<br>');
}

/** Extract a colour value from an inline style or font color attribute. */
function extractColor(el) {
    if (!el || el.nodeType !== 1) return null;
    const fromAttr = el.getAttribute && el.getAttribute('color');
    if (fromAttr && fromAttr.trim()) return fromAttr.trim();
    const style = (el.getAttribute && el.getAttribute('style')) || '';
    const m = /(?:^|;)\s*color\s*:\s*([^;]+)/i.exec(style);
    if (!m) return null;
    // Drop Word's empty/"windowtext" defaults
    const color = m[1].trim().replace(/^windowtext$/i, '');
    return color || null;
}

/**
 * Sanitize clipboard HTML (especially MS Word / Outlook) down to the same
 * allowlist the backend bleach sanitizer accepts:
 *   b/strong, i/em, span[style=color], font[color], br, a[href]
 * Block elements (p/div/li/…) become line breaks between their content.
 */
function sanitizeClipboardHtml(html) {
    if (!html) return '';

    // Word wraps the useful bit between these markers
    const start = html.indexOf('<!--StartFragment-->');
    const end = html.indexOf('<!--EndFragment-->');
    if (start !== -1 && end !== -1 && end > start) {
        html = html.slice(start + '<!--StartFragment-->'.length, end);
    }

    let doc;
    try {
        doc = new DOMParser().parseFromString(`<div id="__blank_paste_root">${html}</div>`, 'text/html');
    } catch (_e) {
        return plainTextToSafeHtml(html.replace(/<[^>]+>/g, ''));
    }
    const root = doc.getElementById('__blank_paste_root') || doc.body;
    if (!root) return '';

    const BLOCK = new Set(['p', 'div', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'section', 'article', 'header', 'footer']);
    const SKIP = new Set(['script', 'style', 'meta', 'link', 'xml', 'head', 'title', 'noscript']);

    function walk(node, out) {
        if (!node) return;

        if (node.nodeType === Node.TEXT_NODE) {
            // Word soft line-wraps show up as newlines between words; treat as spaces
            // so "across\nall" does not become "acrossall" after save.
            const t = (node.textContent || '').replace(/[\r\n]+/g, ' ');
            if (t) out.appendChild(document.createTextNode(t));
            return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return;

        const tag = node.tagName.toLowerCase();
        if (SKIP.has(tag)) return;

        if (tag === 'br') {
            out.appendChild(document.createElement('br'));
            return;
        }

        // Word list markers / conditional comments often leave empty o:p
        if (tag === 'o:p' || tag.includes(':')) {
            Array.from(node.childNodes).forEach((c) => walk(c, out));
            return;
        }

        let wrapper = null;
        if (tag === 'b' || tag === 'strong') {
            wrapper = document.createElement('b');
        } else if (tag === 'i' || tag === 'em') {
            wrapper = document.createElement('i');
        } else if (tag === 'a') {
            const href = (node.getAttribute('href') || '').trim();
            if (/^(https?:|mailto:)/i.test(href)) {
                wrapper = document.createElement('a');
                wrapper.setAttribute('href', href);
                wrapper.setAttribute('target', '_blank');
                wrapper.setAttribute('rel', 'noopener noreferrer');
            }
        } else if (tag === 'span' || tag === 'font') {
            const color = extractColor(node);
            if (color) {
                wrapper = document.createElement('span');
                wrapper.style.color = color;
            }
        }

        if (BLOCK.has(tag)) {
            const beforeCount = out.childNodes.length;
            const frag = document.createDocumentFragment();
            Array.from(node.childNodes).forEach((c) => walk(c, frag));
            out.appendChild(frag);
            const added = out.childNodes.length > beforeCount;
            const last = out.lastChild;
            const lastIsBr = last && last.nodeType === 1 && last.tagName === 'BR';
            // Empty Word paragraph → keep one blank line; otherwise add a single
            // break only if the block doesn't already end with <br> (avoids
            // doubling soft-breaks like <p>text<br></p>).
            if (!added || !lastIsBr) {
                out.appendChild(document.createElement('br'));
            }
            return;
        }

        if (wrapper) {
            Array.from(node.childNodes).forEach((c) => walk(c, wrapper));
            // Avoid empty wrappers
            if (wrapper.childNodes.length) out.appendChild(wrapper);
            return;
        }

        // Unknown inline (u, s, etc.) — keep children, drop the tag
        Array.from(node.childNodes).forEach((c) => walk(c, out));
    }

    const result = document.createElement('div');
    Array.from(root.childNodes).forEach((c) => walk(c, result));
    return result.innerHTML.replace(/(?:<br\s*\/?>)+\s*$/i, '');
}

/**
 * Build safe HTML for insertHTML from a paste event.
 * Prefers Office text/html; falls back to plain text with line breaks.
 */
function htmlFromPasteEvent(e) {
    const clip = e.clipboardData || window.clipboardData;
    if (!clip) return '';
    const html = clip.getData('text/html');
    if (html && html.trim()) {
        const cleaned = sanitizeClipboardHtml(html);
        if (cleaned && cleaned.trim()) return cleaned;
    }
    return plainTextToSafeHtml(clip.getData('text/plain') || '');
}

function insertPasteHtml(html) {
    if (!html) return;
    document.execCommand('insertHTML', false, html);
}

export const BlankBodyEditor = {
    _editor: null,
    _textarea: null,
    _toolbar: null,
    _linkPanel: null,
    _linkUrlInput: null,
    _linkApplyBtn: null,
    _linkRemoveBtn: null,
    _colorApplyBtn: null,   // left half of split button — applies current colour
    _colorTrigger: null,    // right half (chevron) — opens picker
    _colorDropdown: null,
    _colorBar: null,
    _colorLetter: null,
    _currentColor: '#374151',  // tracks last-chosen colour (Word-style)
    _savedRange: null,
    _initialized: false,

    init(modalElement) {
        if (!modalElement) return;
        this._editor      = modalElement.querySelector('#item-question-definition-editor');
        this._textarea    = modalElement.querySelector('#item-question-definition');
        this._toolbar     = modalElement.querySelector('#blank-body-toolbar');
        this._linkPanel   = modalElement.querySelector('#blank-body-link-panel');
        this._linkUrlInput  = modalElement.querySelector('#blank-body-link-url');
        this._linkApplyBtn  = modalElement.querySelector('#blank-body-link-apply');
        this._linkRemoveBtn = modalElement.querySelector('#blank-body-link-remove');
        this._colorApplyBtn = modalElement.querySelector('#blank-body-color-apply');
        this._colorTrigger  = modalElement.querySelector('#blank-body-color-trigger');
        this._colorDropdown = modalElement.querySelector('#blank-body-color-dropdown');
        this._colorBar      = modalElement.querySelector('#blank-body-color-bar');
        this._colorLetter   = modalElement.querySelector('#blank-body-color-letter');

        if (!this._editor || !this._textarea || !this._toolbar) return;

        if (!this._initialized) {
            this._setupSync();
            this._setupToolbar();
            this._setupColorDropdown();
            this._setupLinkPanel();
            // If anything still focuses the carrier textarea while blank mode is
            // active, bounce focus to the editor and block scroll-into-view.
            this._textarea?.addEventListener('focus', (e) => {
                if (!this._textarea?.classList.contains('sr-only')) return;
                e.preventDefault();
                this._textarea.blur();
                this._editor?.focus({ preventScroll: true });
            });
            this._initialized = true;
        }
    },

    // ── Show/hide ───────────────────────────────────────────────────────────

    show() {
        this._toolbar?.classList.remove('hidden');
        this._editor?.classList.remove('hidden');
        // Hide the plain textarea; keep it as the hidden form-value carrier
        this._textarea?.classList.add('sr-only');
        this._textarea?.setAttribute('tabindex', '-1');
        this._textarea?.setAttribute('aria-hidden', 'true');
        // Ensure the carrier stays enabled — enforceHiddenControlsDisabled can
        // otherwise disable sr-only fields (offsetParent === null) and wipe
        // definition on save via syncUIToShared.
        if (this._textarea) {
            if (this._textarea.dataset?.fbDisabledByHidden === '1') {
                delete this._textarea.dataset.fbDisabledByHidden;
            }
            this._textarea.disabled = false;
        }
        // Retarget the caption so clicking "Body text" focuses the editor,
        // not the sr-only textarea (which triggers scroll-into-view and shifts
        // the modal content sideways).
        this._bindCaptionToEditor();
    },

    hide() {
        this._closeColorDropdown();
        this._toolbar?.classList.add('hidden');
        this._editor?.classList.add('hidden');
        this._linkPanel?.classList.add('hidden');
        // Restore the plain textarea
        this._textarea?.classList.remove('sr-only');
        this._textarea?.removeAttribute('tabindex');
        this._textarea?.removeAttribute('aria-hidden');
        this._unbindCaptionFromEditor();
    },

    _getCaption() {
        const block = this._editor?.closest('.item-optional-description-block');
        return block?.querySelector('.item-show-description-label')
            || document.querySelector('#item-question-fields .item-show-description-label');
    },

    _onCaptionClick(e) {
        if (e.target.closest('.item-show-description-toggle')) return;
        e.preventDefault();
        this._editor?.focus({ preventScroll: true });
    },

    _bindCaptionToEditor() {
        const caption = this._getCaption();
        if (!caption) return;
        caption.classList.add('cursor-pointer');
        if (!this._captionClickBound) {
            this._captionClickBound = (e) => this._onCaptionClick(e);
            caption.addEventListener('click', this._captionClickBound);
        }
    },

    _unbindCaptionFromEditor() {
        const caption = this._getCaption();
        if (!caption) return;
        caption.classList.remove('cursor-pointer');
        if (this._captionClickBound) {
            caption.removeEventListener('click', this._captionClickBound);
            this._captionClickBound = null;
        }
    },

    // ── Population (called on edit) ──────────────────────────────────────────

    populate(html) {
        if (!this._editor) return;
        this._editor.innerHTML = html || '';
        if (this._textarea) this._textarea.value = html || '';
    },

    clear() {
        if (this._editor) this._editor.innerHTML = '';
        if (this._textarea) this._textarea.value = '';
    },

    // ── Internal ─────────────────────────────────────────────────────────────

    _syncToTextarea() {
        if (!this._textarea || !this._editor) return;
        // A lone <br> left after clearing content should be treated as empty
        const raw = this._editor.innerHTML;
        this._textarea.value = (raw === '<br>' || raw === '') ? '' : raw;
    },

    _saveSelection() {
        const sel = window.getSelection();
        this._savedRange = (sel && sel.rangeCount > 0) ? sel.getRangeAt(0).cloneRange() : null;
    },

    _restoreSelection() {
        if (!this._savedRange) return;
        const sel = window.getSelection();
        if (sel) {
            sel.removeAllRanges();
            sel.addRange(this._savedRange);
        }
    },

    /** Walk up from the selection's anchor node to find an enclosing <a>, if any. */
    _getSelectedLink() {
        const sel = window.getSelection();
        if (!sel || sel.rangeCount === 0) return null;
        let node = sel.getRangeAt(0).commonAncestorContainer;
        while (node && node !== this._editor) {
            if (node.nodeType === 1 && node.tagName === 'A') return node;
            node = node.parentNode;
        }
        return null;
    },

    _setupSync() {
        this._editor.addEventListener('input', () => {
            this._syncToTextarea();
        });

        // Paste: prefer MS Office text/html (Word/Outlook), fall back to plain text
        this._editor.addEventListener('paste', (e) => {
            e.preventDefault();
            insertPasteHtml(htmlFromPasteEvent(e));
            this._syncToTextarea();
        });
    },

    _setupToolbar() {
        // On mousedown, save selection BEFORE any possible focus movement.
        // The colour split-button and link button manage their own saving separately.
        this._toolbar.addEventListener('mousedown', (e) => {
            if (e.target.closest('#blank-body-color-wrapper')) return;
            if (e.target.closest('[data-cmd="createLink"]')) return;
            e.preventDefault();          // keep editor focus
            this._saveSelection();       // snapshot selection now
        });

        this._toolbar.addEventListener('click', (e) => {
            const fmtBtn = e.target.closest('.body-fmt-btn[data-cmd]');
            if (!fmtBtn) return;
            e.stopPropagation();

            if (fmtBtn.dataset.cmd === 'createLink') {
                this._openLinkPanel();
                return;
            }

            // Colour wrapper buttons are handled in _setupColorDropdown
            if (fmtBtn.closest('#blank-body-color-wrapper')) return;

            // Restore the selection saved on mousedown, then run the command
            this._restoreSelection();
            this._editor.focus();
            document.execCommand('styleWithCSS', false, false);
            document.execCommand(fmtBtn.dataset.cmd, false, null);
            this._syncToTextarea();
            this._updateActiveStates();
        });

        // Update active-state decorations as the cursor moves
        this._editor.addEventListener('keyup',       () => this._updateActiveStates());
        this._editor.addEventListener('mouseup',     () => this._updateActiveStates());
        this._editor.addEventListener('selectionchange', () => this._updateActiveStates());
    },

    _setupColorDropdown() {
        const wrapper = this._colorApplyBtn?.closest('#blank-body-color-wrapper');

        // ── Left half: apply current colour immediately ──────────────────────
        if (this._colorApplyBtn) {
            // Save selection on mousedown (before focus can shift)
            this._colorApplyBtn.addEventListener('mousedown', (e) => {
                e.preventDefault(); // keep editor focus
                this._saveSelection();
            });
            this._colorApplyBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this._applyCurrentColor();
            });
        }

        // ── Right half (chevron): open/close picker ──────────────────────────
        if (this._colorTrigger) {
            this._colorTrigger.addEventListener('mousedown', (e) => {
                e.preventDefault(); // keep editor focus
                this._saveSelection();
            });
            this._colorTrigger.addEventListener('click', (e) => {
                e.stopPropagation();
                this._toggleColorDropdown();
            });
        }

        // ── Dropdown swatches ────────────────────────────────────────────────
        if (this._colorDropdown) {
            this._colorDropdown.addEventListener('mousedown', (e) => {
                e.preventDefault(); // don't blur editor
            });
            this._colorDropdown.addEventListener('click', (e) => {
                const colorBtn = e.target.closest('.body-fmt-color-btn[data-color]');
                if (!colorBtn) return;
                e.stopPropagation();
                this._setCurrentColor(colorBtn.dataset.color);
                this._applyCurrentColor();
                this._closeColorDropdown();
            });
        }

        // ── Outside-click and Escape ─────────────────────────────────────────
        document.addEventListener('click', (e) => {
            if (this._colorDropdown?.classList.contains('hidden')) return;
            if (!wrapper?.contains(e.target)) this._closeColorDropdown();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !this._colorDropdown?.classList.contains('hidden')) {
                this._closeColorDropdown();
                this._editor?.focus();
            }
        });
    },

    _setCurrentColor(color) {
        this._currentColor = color;
        if (this._colorBar)    this._colorBar.style.background = color;
        if (this._colorLetter) this._colorLetter.style.color   = color;
    },

    _applyCurrentColor() {
        this._restoreSelection();
        this._editor?.focus();
        document.execCommand('styleWithCSS', false, true);
        document.execCommand('foreColor', false, this._currentColor);
        this._syncToTextarea();
        this._updateActiveStates();
    },

    _toggleColorDropdown() {
        if (this._colorDropdown?.classList.contains('hidden')) {
            this._openColorDropdown();
        } else {
            this._closeColorDropdown();
        }
    },

    _openColorDropdown() {
        this._colorDropdown?.classList.remove('hidden');
        this._colorTrigger?.setAttribute('aria-expanded', 'true');
    },

    _closeColorDropdown() {
        this._colorDropdown?.classList.add('hidden');
        this._colorTrigger?.setAttribute('aria-expanded', 'false');
    },

    _setupLinkPanel() {
        if (!this._linkPanel) return;

        // Prevent panel clicks from propagating to modal backdrop etc.
        this._linkPanel.addEventListener('mousedown', (e) => e.stopPropagation());

        // Apply on Enter key in the URL field
        this._linkUrlInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); this._applyLink(); }
            if (e.key === 'Escape') { e.preventDefault(); this._closeLinkPanel(); }
        });

        this._linkApplyBtn?.addEventListener('click', () => this._applyLink());
        this._linkRemoveBtn?.addEventListener('click', () => this._removeLink());

        this._linkPanel.querySelector('#blank-body-link-cancel')
            ?.addEventListener('click', () => this._closeLinkPanel());
    },

    _openLinkPanel() {
        if (!this._linkPanel || !this._linkUrlInput) return;
        // Save selection now — clicking the URL input will blur the editor
        this._saveSelection();

        const existingLink = this._getSelectedLink();
        this._linkUrlInput.value = existingLink ? existingLink.getAttribute('href') : '';

        if (this._linkRemoveBtn) {
            this._linkRemoveBtn.classList.toggle('hidden', !existingLink);
        }

        this._linkPanel.classList.remove('hidden');
        this._linkUrlInput.focus();
        this._linkUrlInput.select();

        // Highlight the link button as active
        this._toolbar.querySelector('[data-cmd="createLink"]')
            ?.classList.add('ring-2');
    },

    _closeLinkPanel() {
        this._linkPanel?.classList.add('hidden');
        this._toolbar.querySelector('[data-cmd="createLink"]')
            ?.classList.remove('ring-2');
        // Return focus to editor
        this._editor?.focus();
    },

    _applyLink() {
        const rawUrl = (this._linkUrlInput?.value || '').trim();
        if (!rawUrl) { this._closeLinkPanel(); return; }

        // Prepend https:// if the user typed a bare domain
        let url = rawUrl;
        if (!/^[a-z][a-z0-9+\-.]*:/i.test(url) && !url.startsWith('//')) {
            url = 'https://' + url;
        }

        this._restoreSelection();
        this._editor?.focus();

        // If the selection is collapsed (just a cursor), select the whole word
        const sel = window.getSelection();
        if (sel && sel.rangeCount > 0 && sel.getRangeAt(0).collapsed) {
            document.execCommand('selectWord');
        }

        document.execCommand('createLink', false, url);

        // Ensure links open in a new tab with safe rel
        this._editor?.querySelectorAll('a').forEach((a) => {
            a.setAttribute('target', '_blank');
            a.setAttribute('rel', 'noopener noreferrer');
        });

        this._syncToTextarea();
        this._closeLinkPanel();
        this._updateActiveStates();
    },

    _removeLink() {
        this._restoreSelection();
        this._editor?.focus();
        // Select the entire link if the cursor is just inside it
        const link = this._getSelectedLink();
        if (link) {
            const range = document.createRange();
            range.selectNodeContents(link);
            const sel = window.getSelection();
            sel?.removeAllRanges();
            sel?.addRange(range);
        }
        document.execCommand('unlink');
        this._syncToTextarea();
        this._closeLinkPanel();
    },

    _updateActiveStates() {
        if (!this._toolbar) return;
        const isBold   = document.queryCommandState('bold');
        const isItalic = document.queryCommandState('italic');
        this._toolbar.querySelector('[data-cmd="bold"]')
            ?.classList.toggle('ring-2', isBold);
        this._toolbar.querySelector('[data-cmd="italic"]')
            ?.classList.toggle('ring-2', isItalic);

        // Highlight link button when cursor is inside an <a>
        const isLink = !!this._getSelectedLink();
        this._toolbar.querySelector('[data-cmd="createLink"]')
            ?.classList.toggle('ring-2', isLink && !this._linkPanel?.classList.contains('hidden') === false);
    },
};

/**
 * BlankTranslationEditor — rich-text toolbar for the translation modal's
 * "Body text" (definitions) tab when the item type is Blank/Note.
 *
 * One shared toolbar is injected above the definitions tab panel; each
 * language gets its own contenteditable editor (kept in the DOM for reuse,
 * hidden/shown via activate/deactivate).  The canonical textarea for each
 * language stays in sync via `input` events so TranslationUtils.collectFields
 * can also read it as a fallback.
 */
export const BlankTranslationEditor = {
    _panelId: 'translation-definitions-tab-content',
    _toolbar: null,
    _colorBar: null,
    _colorLetter: null,
    _colorDropdown: null,
    _currentColor: '#374151',
    _focusedEditor: null,
    _savedRange: null,
    enabled: false,

    /** Set when the question type switches to blank. */
    enable() { this.enabled = true; },

    /** Set when the question type switches away from blank; hides editors. */
    disable() {
        this.enabled = false;
        this.deactivate();
    },

    /**
     * Show rich-text editors in the definitions tab.
     * Safe to call multiple times — editors are created once and refreshed
     * from the (already-populated) textarea values on subsequent calls.
     */
    activate() {
        if (!this.enabled) return;
        const panel = document.getElementById(this._panelId);
        if (!panel) return;

        // Inject shared toolbar once; show it on subsequent calls
        if (!this._toolbar) {
            this._toolbar = this._buildToolbar();
            panel.insertAdjacentElement('afterbegin', this._toolbar);
        } else {
            this._toolbar.classList.remove('hidden');
        }

        // Create or refresh per-language editors
        const langs = (window.TranslationModalUtils?.supportedLanguages || []).filter(c => c !== 'en');
        langs.forEach(code => {
            const fieldId  = `translation-translation-definitions-${code}`;
            const textarea = document.getElementById(fieldId);
            if (!textarea) return;

            let editor = document.getElementById(fieldId + '-editor');
            if (!editor) {
                editor = this._createEditorFor(textarea, code);
            }

            // Refresh from the textarea (populated by TranslationUtils.populateFields)
            editor.innerHTML = textarea.value || '';

            editor.classList.remove('hidden');
            textarea.classList.add('sr-only');
            textarea.setAttribute('tabindex', '-1');
            textarea.setAttribute('aria-hidden', 'true');
        });
    },

    /** Hide editors and restore plain textareas (called when type ≠ blank). */
    deactivate() {
        this._toolbar?.classList.add('hidden');
        const panel = document.getElementById(this._panelId);
        if (!panel) return;
        panel.querySelectorAll('.blank-trans-editor').forEach(ed => {
            ed.classList.add('hidden');
            const ta = document.getElementById(ed.dataset.textareaId);
            if (ta) {
                ta.classList.remove('sr-only');
                ta.removeAttribute('tabindex');
                ta.removeAttribute('aria-hidden');
            }
        });
    },

    // ── Internal ────────────────────────────────────────────────────────────

    _createEditorFor(textarea, langCode) {
        const editor = document.createElement('div');
        editor.id = textarea.id + '-editor';
        editor.dataset.textareaId = textarea.id;
        editor.className = [
            'blank-trans-editor blank-body-editor',
            'shadow-sm block w-full text-sm border border-gray-300 rounded-md',
            'px-2.5 py-2',
        ].join(' ');
        // Use inline styles for height constraints so they can never be purged
        // by the Tailwind build step or overridden by a missing stylesheet.
        editor.style.minHeight = '3.5rem';
        editor.style.maxHeight = '7rem';
        editor.style.overflowY = 'auto';
        editor.contentEditable = 'true';
        editor.spellcheck = true;

        const RTL = ['ar', 'fa', 'he', 'ur'];
        if (RTL.includes(langCode)) {
            editor.dir = 'rtl';
            editor.style.fontFamily = "'Tajawal', Arial, sans-serif";
        }

        editor.addEventListener('input', () => {
            const raw = editor.innerHTML;
            textarea.value = (raw === '<br>' || raw === '') ? '' : raw;
        });
        editor.addEventListener('focus', () => { this._focusedEditor = editor; });
        editor.addEventListener('paste', (e) => {
            e.preventDefault();
            insertPasteHtml(htmlFromPasteEvent(e));
            const ta = document.getElementById(editor.dataset.textareaId);
            if (ta) {
                const raw = editor.innerHTML;
                ta.value = (raw === '<br>' || raw === '') ? '' : raw;
            }
        });

        textarea.insertAdjacentElement('afterend', editor);
        return editor;
    },

    _buildToolbar() {
        const COLORS = [
            ['#374151', 'Dark (default)'],
            ['#dc2626', 'Red'],
            ['#f97316', 'Orange'],
            ['#ca8a04', 'Yellow'],
            ['#16a34a', 'Green'],
            ['#2563eb', 'Blue'],
            ['#7c3aed', 'Purple'],
            ['#6b7280', 'Grey'],
        ];

        const toolbar = document.createElement('div');
        toolbar.className = 'flex flex-wrap items-center gap-1 mb-3 px-1.5 py-1 border border-gray-200 rounded-md bg-gray-50';
        toolbar.innerHTML = `
<button type="button" class="blank-trans-fmt-btn body-fmt-btn flex items-center justify-center w-7 h-7 rounded hover:bg-gray-200 focus:outline-none text-sm font-bold text-gray-700" data-cmd="bold" title="Bold">B</button>
<button type="button" class="blank-trans-fmt-btn body-fmt-btn flex items-center justify-center w-7 h-7 rounded hover:bg-gray-200 focus:outline-none italic text-sm text-gray-700" data-cmd="italic" title="Italic"><i>I</i></button>
<span class="h-4 border-l border-gray-300 mx-0.5" aria-hidden="true"></span>
<div class="relative flex rounded overflow-visible" id="blank-trans-color-wrapper">
  <button type="button" id="blank-trans-color-apply"
          class="body-fmt-btn flex flex-col items-center justify-center px-1.5 h-7 rounded-l hover:bg-gray-200 focus:outline-none"
          title="Apply colour">
    <span id="blank-trans-color-letter" class="text-sm font-bold leading-none select-none" style="color:#374151">A</span>
    <span id="blank-trans-color-bar" class="block w-4 h-[3px] rounded-sm mt-0.5" style="background:#374151"></span>
  </button>
  <button type="button" id="blank-trans-color-trigger"
          class="body-fmt-btn flex items-center justify-center w-4 h-7 rounded-r hover:bg-gray-200 focus:outline-none"
          aria-expanded="false" title="Choose colour">
    <i class="fas fa-chevron-down text-[9px] text-gray-400" aria-hidden="true"></i>
  </button>
  <div id="blank-trans-color-dropdown"
       class="hidden absolute left-0 top-full mt-1 z-50 bg-white border border-gray-200 rounded-lg shadow-lg p-2"
       role="menu">
    <div class="blank-body-color-swatches">
      ${COLORS.map(([c, l]) =>
          `<button type="button" class="blank-trans-color-swatch rounded-full border-2 border-white ring-1 ring-gray-300 hover:ring-2 hover:ring-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all" style="background:${c}" data-color="${c}" title="${l}" role="menuitem"></button>`
      ).join('\n      ')}
    </div>
  </div>
</div>
<span class="h-4 border-l border-gray-300 mx-0.5" aria-hidden="true"></span>
<button type="button" class="blank-trans-fmt-btn body-fmt-btn flex items-center justify-center w-7 h-7 rounded hover:bg-gray-200 focus:outline-none text-gray-500" data-cmd="removeFormat" title="Clear formatting">
  <i class="fas fa-eraser text-xs"></i>
</button>`;

        this._colorBar      = toolbar.querySelector('#blank-trans-color-bar');
        this._colorLetter   = toolbar.querySelector('#blank-trans-color-letter');
        this._colorDropdown = toolbar.querySelector('#blank-trans-color-dropdown');

        this._setupToolbarEvents(toolbar);
        return toolbar;
    },

    _setupToolbarEvents(toolbar) {
        const colorWrapper = toolbar.querySelector('#blank-trans-color-wrapper');
        const colorApply   = toolbar.querySelector('#blank-trans-color-apply');
        const colorTrigger = toolbar.querySelector('#blank-trans-color-trigger');

        // Preserve selection on mousedown so focus doesn't get stolen
        toolbar.addEventListener('mousedown', (e) => {
            if (e.target.closest('#blank-trans-color-wrapper')) return;
            e.preventDefault();
            this._saveSelection();
        });

        // B / I / clear buttons
        toolbar.addEventListener('click', (e) => {
            const btn = e.target.closest('.blank-trans-fmt-btn[data-cmd]');
            if (!btn || btn.closest('#blank-trans-color-wrapper')) return;
            e.stopPropagation();
            this._restoreSelection();
            this._focusedEditor?.focus();
            document.execCommand('styleWithCSS', false, false);
            document.execCommand(btn.dataset.cmd, false, null);
            this._syncFocused();
        });

        // Colour apply (left half of split button)
        colorApply?.addEventListener('mousedown', (e) => {
            e.preventDefault();
            this._saveSelection();
        });
        colorApply?.addEventListener('click', (e) => {
            e.stopPropagation();
            this._applyCurrentColor();
        });

        // Colour trigger (right half — opens picker)
        colorTrigger?.addEventListener('mousedown', (e) => {
            e.preventDefault();
            this._saveSelection();
        });
        colorTrigger?.addEventListener('click', (e) => {
            e.stopPropagation();
            const hidden = this._colorDropdown?.classList.toggle('hidden');
            colorTrigger.setAttribute('aria-expanded', hidden ? 'false' : 'true');
        });

        // Colour swatches
        this._colorDropdown?.addEventListener('mousedown', (e) => e.preventDefault());
        this._colorDropdown?.addEventListener('click', (e) => {
            const swatch = e.target.closest('.blank-trans-color-swatch[data-color]');
            if (!swatch) return;
            e.stopPropagation();
            const color = swatch.dataset.color;
            this._currentColor = color;
            if (this._colorBar)    this._colorBar.style.background = color;
            if (this._colorLetter) this._colorLetter.style.color   = color;
            this._colorDropdown.classList.add('hidden');
            colorTrigger?.setAttribute('aria-expanded', 'false');
            this._applyCurrentColor();
        });

        // Close picker on outside click
        document.addEventListener('click', (e) => {
            if (!this._colorDropdown?.classList.contains('hidden') && !colorWrapper?.contains(e.target)) {
                this._colorDropdown?.classList.add('hidden');
                colorTrigger?.setAttribute('aria-expanded', 'false');
            }
        });
    },

    _saveSelection() {
        const sel = window.getSelection();
        this._savedRange = (sel && sel.rangeCount > 0) ? sel.getRangeAt(0).cloneRange() : null;
    },

    _restoreSelection() {
        if (!this._savedRange) return;
        const sel = window.getSelection();
        if (sel) { sel.removeAllRanges(); sel.addRange(this._savedRange); }
    },

    _applyCurrentColor() {
        this._restoreSelection();
        this._focusedEditor?.focus();
        document.execCommand('styleWithCSS', false, true);
        document.execCommand('foreColor', false, this._currentColor);
        this._syncFocused();
    },

    _syncFocused() {
        if (!this._focusedEditor) return;
        const ta = document.getElementById(this._focusedEditor.dataset.textareaId);
        if (ta) {
            const raw = this._focusedEditor.innerHTML;
            ta.value = (raw === '<br>' || raw === '') ? '' : raw;
        }
    },
};
