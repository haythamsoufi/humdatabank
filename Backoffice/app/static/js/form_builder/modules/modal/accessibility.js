export const AccessibilityMixin = {
    setupWindowResize: function() {
        let resizeTimeout;
        window.addEventListener('resize', () => {
            // Debounce resize events to avoid excessive calls
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(() => {
                // Only check scroll if modal is currently visible
                if (this.modalElement && !this.modalElement.classList.contains('hidden')) {
                    this.checkModalScroll();
                }
            }, 250);
        });
    },

    setupModalAria: function() {
        if (!this.modalElement) return;
        this.modalElement.setAttribute('role', 'dialog');
        this.modalElement.setAttribute('aria-modal', 'true');
        const titleElement = this.modalElement.querySelector('.modal-title');
        if (titleElement) {
            if (!titleElement.id) {
                titleElement.id = 'item-modal-title';
            }
            this.modalElement.setAttribute('aria-labelledby', titleElement.id);
        }
    },

    focusFirstField: function() {
        if (!this.modalElement) return;
        const focusableSelectors = [
            'input:not([type="hidden"]):not([disabled])',
            'select:not([disabled])',
            'textarea:not([disabled])',
            'button:not([disabled])',
            '[tabindex]:not([tabindex="-1"])'
        ].join(',');
        const focusables = Array.from(this.modalElement.querySelectorAll(focusableSelectors))
            .filter(el => el.offsetParent !== null);
        if (focusables.length > 0) {
            try {
                this._previousFocusedElement = document.activeElement;
                focusables[0].focus();
            } catch (e) {}
        }
    },

    setupFocusTrap: function() {
        if (!this.modalElement || this._focusTrapAttached) return;
        this._focusTrapAttached = true;
        this._focusTrapHandler = (e) => {
            if (e.key !== 'Tab') return;
            const focusableSelectors = [
                'a[href]',
                'button:not([disabled])',
                'textarea:not([disabled])',
                'input:not([type="hidden"]):not([disabled])',
                'select:not([disabled])',
                '[tabindex]:not([tabindex="-1"])'
            ].join(',');
            const nodes = Array.from(this.modalElement.querySelectorAll(focusableSelectors))
                .filter(el => el.offsetParent !== null);
            if (nodes.length === 0) return;
            const first = nodes[0];
            const last = nodes[nodes.length - 1];
            if (e.shiftKey) {
                if (document.activeElement === first) {
                    e.preventDefault();
                    last.focus();
                }
            } else {
                if (document.activeElement === last) {
                    e.preventDefault();
                    first.focus();
                }
            }
        };
        this.modalElement.addEventListener('keydown', this._focusTrapHandler, true);
    },

    teardownFocusTrap: function() {
        if (this.modalElement && this._focusTrapAttached && this._focusTrapHandler) {
            this.modalElement.removeEventListener('keydown', this._focusTrapHandler, true);
        }
        this._focusTrapAttached = false;
        this._focusTrapHandler = null;
        if (this._previousFocusedElement && typeof this._previousFocusedElement.focus === 'function') {
            try { this._previousFocusedElement.focus(); } catch (e) {}
        }
        this._previousFocusedElement = null;
    },
};
