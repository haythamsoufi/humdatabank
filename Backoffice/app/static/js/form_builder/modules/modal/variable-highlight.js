/**
 * VariableHighlightMixin
 *
 * Native <input>/<textarea> elements cannot colour part of their own text, so
 * template variables like `[assignment_period]` normally render as plain text.
 * This mixin paints a transparent "backdrop" layer behind the caret that mirrors
 * the field value and wraps every `[token]` in a coloured span:
 *   - known variable (template var / built-in metadata / plugin var) → indigo
 *   - unknown token (typo / not yet defined)                         → amber
 *
 * The field keeps its own border/background; only its text is made transparent
 * (the caret stays visible via caret-color), and the backdrop shows the colours
 * in perfect alignment. Spans use colour + background only (no padding/weight
 * changes) so horizontal metrics match the real text exactly.
 *
 * Fields are enhanced lazily (on focus/input) and via a MutationObserver so that
 * dynamically-added rows (matrix columns/groups) are handled without touching
 * their creation code.
 */

const VH_ENHANCED = 'vhEnhanced';

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function getKnownVariableKeys() {
    const keys = new Set();
    try {
        const templateVariables = window.templateVariables || {};
        Object.keys(templateVariables).forEach(k => keys.add(String(k).toLowerCase()));
    } catch (_e) {}
    try {
        (Array.isArray(window.builtInMetadataVariables) ? window.builtInMetadataVariables : [])
            .forEach(m => m && m.key && keys.add(String(m.key).toLowerCase()));
    } catch (_e) {}
    try {
        (Array.isArray(window.pluginLabelVariables) ? window.pluginLabelVariables : [])
            .forEach(p => p && p.key && keys.add(String(p.key).toLowerCase()));
    } catch (_e) {}
    return keys;
}

export const VariableHighlightMixin = {
    /** True when a field is allowed to contain template variables. */
    isVariableField: function(el) {
        if (!el || el.nodeType !== 1) return false;
        const tag = el.tagName;
        if (tag !== 'INPUT' && tag !== 'TEXTAREA') return false;
        if (tag === 'INPUT') {
            const type = (el.getAttribute('type') || 'text').toLowerCase();
            if (type !== 'text' && type !== 'search') return false;
        }
        if (el.dataset && el.dataset.enableVariables === 'true') return true;
        const fieldType = el.getAttribute('data-field-type');
        if (fieldType === 'label' || fieldType === 'description') return true;
        return ['item-indicator-label', 'item-question-label', 'item-document-label',
                'item-matrix-label', 'item-plugin-label'].includes(el.id);
    },

    setupVariableHighlight: function() {
        // Lazily enhance + render whichever variable field the user touches.
        document.addEventListener('focusin', (e) => {
            const el = e.target;
            if (!this._vhInModal(el) || !this.isVariableField(el)) return;
            this._vhEnhanceField(el);
            this._vhRender(el);
        });

        document.addEventListener('input', (e) => {
            const el = e.target;
            if (!this._vhInModal(el) || !this.isVariableField(el)) return;
            this._vhEnhanceField(el);
            this._vhRender(el);
        });

        // Keep the backdrop aligned while a textarea/input scrolls its content.
        document.addEventListener('scroll', (e) => {
            const el = e.target;
            if (el && el.dataset && el.dataset[VH_ENHANCED] === 'true') {
                this._vhSyncScroll(el);
            }
        }, true);

        window.addEventListener('resize', () => {
            this._vhRenderAll();
        });

        this._vhSetupObserver();
    },

    _vhInModal: function(el) {
        return !!(el && el.closest && el.closest('#item-modal'));
    },

    _vhSetupObserver: function() {
        if (this._vhObserver) return;
        const modal = this.modalElement || (typeof Utils !== 'undefined' && Utils.getElementById
            ? Utils.getElementById('item-modal') : document.getElementById('item-modal'));
        if (!modal) return;
        this._vhObserver = new MutationObserver((mutations) => {
            let touched = false;
            for (const m of mutations) {
                m.addedNodes && m.addedNodes.forEach((node) => {
                    if (node.nodeType !== 1) return;
                    const candidates = [];
                    if (this.isVariableField(node)) candidates.push(node);
                    if (node.querySelectorAll) {
                        node.querySelectorAll('input, textarea').forEach((f) => {
                            if (this.isVariableField(f)) candidates.push(f);
                        });
                    }
                    candidates.forEach((f) => {
                        this._vhEnhanceField(f);
                        this._vhRender(f);
                        touched = true;
                    });
                });
            }
            if (touched) {
                // nudge alignment after layout settles
                requestAnimationFrame(() => this._vhRenderAll());
            }
        });
        this._vhObserver.observe(modal, { childList: true, subtree: true });
    },

    /** Re-render every enhanced field (e.g. after programmatic populate/reset). */
    refreshVariableHighlights: function() {
        this._vhSetupObserver();
        const modal = this.modalElement;
        if (!modal) return;
        modal.querySelectorAll('input, textarea').forEach((el) => {
            if (!this.isVariableField(el)) return;
            this._vhEnhanceField(el);
            this._vhRender(el);
        });
    },

    _vhRenderAll: function() {
        const modal = this.modalElement || document.getElementById('item-modal');
        if (!modal) return;
        modal.querySelectorAll('[data-vh-enhanced="true"]').forEach((el) => this._vhRender(el));
    },

    _vhEnhanceField: function(el) {
        if (!el || (el.dataset && el.dataset[VH_ENHANCED] === 'true')) return;
        const parent = el.parentNode;
        if (!parent) return;

        const cs = window.getComputedStyle(el);

        // Wrap the field so the backdrop can be positioned over it without
        // disturbing the surrounding fl/flex layout.
        const wrapper = document.createElement('div');
        wrapper.className = 'vh-wrap';
        wrapper.style.position = 'relative';
        wrapper.style.display = 'block';
        wrapper.style.flexGrow = cs.flexGrow;
        wrapper.style.flexShrink = cs.flexShrink;
        wrapper.style.flexBasis = cs.flexBasis;
        wrapper.style.alignSelf = cs.alignSelf;
        wrapper.style.margin = cs.margin;
        if (cs.minWidth && cs.minWidth !== '0px') wrapper.style.minWidth = cs.minWidth;
        if (cs.maxWidth && cs.maxWidth !== 'none') wrapper.style.maxWidth = cs.maxWidth;

        parent.insertBefore(wrapper, el);
        wrapper.appendChild(el);

        // Field fills the wrapper; the wrapper now owns the box geometry.
        el.style.margin = '0';
        el.style.minWidth = '0';
        el.style.flex = 'none';
        el.style.width = '100%';
        el.style.position = 'relative';
        el.style.background = 'transparent';
        el.style.zIndex = '1';
        // Keep the typed text invisible but the caret visible.
        if (!el.dataset.vhOrigColor) el.dataset.vhOrigColor = cs.color;
        el.style.caretColor = cs.color;
        el.style.color = 'transparent';
        // Match the backdrop wrapping behaviour for inputs.
        el.style.webkitTextFillColor = 'transparent';

        const backdrop = document.createElement('div');
        backdrop.className = 'vh-backdrop';
        backdrop.setAttribute('aria-hidden', 'true');
        const isTextarea = el.tagName === 'TEXTAREA';
        Object.assign(backdrop.style, {
            position: 'absolute',
            top: '0',
            left: '0',
            right: '0',
            bottom: '0',
            overflow: 'hidden',
            pointerEvents: 'none',
            zIndex: '2',
            boxSizing: cs.boxSizing,
            paddingTop: cs.paddingTop,
            paddingRight: cs.paddingRight,
            paddingBottom: cs.paddingBottom,
            paddingLeft: cs.paddingLeft,
            borderTopWidth: cs.borderTopWidth,
            borderRightWidth: cs.borderRightWidth,
            borderBottomWidth: cs.borderBottomWidth,
            borderLeftWidth: cs.borderLeftWidth,
            borderStyle: 'solid',
            borderColor: 'transparent',
            borderRadius: cs.borderRadius,
            fontFamily: cs.fontFamily,
            fontSize: cs.fontSize,
            fontWeight: cs.fontWeight,
            fontStyle: cs.fontStyle,
            lineHeight: cs.lineHeight,
            letterSpacing: cs.letterSpacing,
            textAlign: cs.textAlign,
            // Base colour = the field's own text colour so NON-variable text stays
            // visible; only [tokens] override this via .vh-var-* spans.
            color: el.dataset.vhOrigColor || cs.color,
        });

        const inner = document.createElement('div');
        inner.className = 'vh-backdrop-inner';
        inner.style.whiteSpace = isTextarea ? 'pre-wrap' : 'pre';
        inner.style.wordBreak = isTextarea ? 'break-word' : 'normal';
        inner.style.overflowWrap = isTextarea ? 'break-word' : 'normal';
        inner.style.willChange = 'transform';
        backdrop.appendChild(inner);
        wrapper.appendChild(backdrop);

        el.dataset[VH_ENHANCED] = 'true';
        el._vhBackdrop = backdrop;
        el._vhInner = inner;
    },

    _vhRender: function(el) {
        if (!el || !el._vhInner) return;
        const value = el.value || '';
        const known = getKnownVariableKeys();
        // Mirror the backend grammar (variable_resolution_service.py):
        //   - formula tokens  [[var]+1] / [[var]*2] / [[var]-5] / [[var]/2.5]  (matched first, whole)
        //   - simple tokens   [var]
        // The inner variable name decides known (indigo) vs unknown (amber);
        // the whole expression — including the arithmetic — is highlighted.
        const re = /\[\[(\w+)\]([+\-*/]\d+(?:\.\d+)?)\]|\[(\w+)\]/g;
        let html = '';
        let last = 0;
        let match;
        while ((match = re.exec(value)) !== null) {
            html += escapeHtml(value.slice(last, match.index));
            const varName = match[1] || match[3] || '';
            const cls = known.has(varName.toLowerCase()) ? 'vh-var-known' : 'vh-var-unknown';
            html += `<span class="${cls}">${escapeHtml(match[0])}</span>`;
            last = re.lastIndex;
        }
        html += escapeHtml(value.slice(last));
        // Trailing newline needs an extra line so textarea height matches.
        if (value.endsWith('\n')) html += '\n';
        el._vhInner.innerHTML = html;
        this._vhSyncScroll(el);
    },

    _vhSyncScroll: function(el) {
        if (!el || !el._vhInner) return;
        el._vhInner.style.transform =
            `translate(${-el.scrollLeft}px, ${-el.scrollTop}px)`;
    },
};
