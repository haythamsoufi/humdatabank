export const HiddenControlsMixin = {
    /**
     * Invariant: if a UI section is hidden, all non-hidden form controls inside it are disabled.
     *
     * - Only re-enables controls we disabled (data-fbDisabledByHidden), preserving other disabled reasons.
     * - Complements item-type switching (which already disables whole type containers) and covers nested panels
     *   toggled by inline scripts (e.g. question options/list-library panes).
     */
    enforceHiddenControlsDisabled: function(rootEl) {
        const root = rootEl || this.modalElement;
        if (!root) return;

        const isActuallyHidden = (el) => {
            if (!el) return true;
            try {
                if (el.closest && el.closest('.hidden')) return true;
                const inlineDisplay = el.style && el.style.display;
                const inlineVisibility = el.style && el.style.visibility;
                if (inlineDisplay === 'none' || inlineVisibility === 'hidden') return true;
                if (el.offsetParent === null) return true;
                const style = window.getComputedStyle(el);
                return style.display === 'none' || style.visibility === 'hidden';
            } catch (_e) {
                return false;
            }
        };

        root.querySelectorAll('input, select, textarea, button').forEach((el) => {
            if (!el) return;
            if (el.tagName.toLowerCase() === 'input' && el.type === 'hidden') return;
            if (el.type === 'submit') return;

            const hidden = isActuallyHidden(el);
            if (hidden) {
                if (!el.disabled) {
                    try { el.dataset.fbDisabledByHidden = '1'; } catch (_e) {}
                    el.disabled = true;
                }
            } else {
                try {
                    if (el.dataset && el.dataset.fbDisabledByHidden === '1') {
                        el.disabled = false;
                        delete el.dataset.fbDisabledByHidden;
                    }
                } catch (_e) {}
            }
        });
    },

    setupHiddenDisableObserver: function() {
        if (!this.modalElement || typeof MutationObserver === 'undefined') return;

        try {
            if (this._hiddenDisableObserver) this._hiddenDisableObserver.disconnect();
        } catch (_e) {}

        const schedule = () => {
            if (this._hiddenDisableQueued) return;
            this._hiddenDisableQueued = true;
            requestAnimationFrame(() => {
                this._hiddenDisableQueued = false;
                try { this.enforceHiddenControlsDisabled(this.modalElement); } catch (_e) {}
            });
        };

        try {
            this._hiddenDisableObserver = new MutationObserver(() => schedule());
            this._hiddenDisableObserver.observe(this.modalElement, {
                subtree: true,
                childList: true,
                attributes: true,
                attributeFilter: ['class', 'style', 'hidden', 'aria-hidden']
            });
        } catch (_e) {
            this._hiddenDisableObserver = null;
        }

        schedule();
    },
};
