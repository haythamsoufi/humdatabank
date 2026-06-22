// utils.js - General utility functions

const Utils = {
    // Default module name when formBuilderDebug is used (set via setDebugModule before calling debugLog).
    _debugModule: 'data-manager',

    setDebugModule: function(module) {
        this._debugModule = module || 'data-manager';
    },

    // Debug logging: when formBuilderDebug exists (form builder page), respect its toggles; otherwise localhost-only.
    debugLog: function(message, data = null) {
        if (typeof window.formBuilderDebug !== 'undefined' && window.formBuilderDebug && window.formBuilderDebug.log) {
            const module = this._debugModule || 'data-manager';
            if (window.formBuilderDebug.isEnabled && window.formBuilderDebug.isEnabled(module)) {
                window.formBuilderDebug.log(module, message, data !== null ? data : undefined);
            }
            return;
        }
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            console.log(message, data);
        }
    },

    // Show/hide elements
    showElement: function(element) {
        if (element) {
            element.classList.remove('hidden');
            element.style.display = '';
            // Re-enable any form controls we disabled when hiding this element.
            try {
                const controls = element.querySelectorAll('input, select, textarea, button');
                controls.forEach((el) => {
                    // Only re-enable controls that we disabled.
                    if (el && el.dataset && el.dataset.utilsDisabledByHide === '1') {
                        el.disabled = false;
                        delete el.dataset.utilsDisabledByHide;
                    }
                });
            } catch (_e) {}
        }
    },

    hideElement: function(element) {
        if (element) {
            element.classList.add('hidden');
            element.style.display = 'none';
            // IMPORTANT: Hidden form controls (especially checked checkboxes) still submit.
            // Disable controls when hiding, and restore only those we disabled when showing.
            try {
                const controls = element.querySelectorAll('input, select, textarea, button');
                controls.forEach((el) => {
                    if (!el) return;
                    // Never disable hidden inputs (our app uses many hidden fields for serialization).
                    if (el.tagName && el.tagName.toLowerCase() === 'input' && el.type === 'hidden') return;
                    // If already disabled, do nothing (and don't mark).
                    if (el.disabled) return;
                    el.disabled = true;
                    if (el.dataset) el.dataset.utilsDisabledByHide = '1';
                });
            } catch (_e) {}
        }
    },

    // Toggle element visibility
    toggleElement: function(element) {
        if (element) {
            element.classList.toggle('hidden');
        }
    },

    // Get element by ID with error handling
    getElementById: function(id) {
        const element = document.getElementById(id);
        if (!element) {
            console.warn(`Element with id '${id}' not found`);
        }
        return element;
    },

    // Get element by selector with error handling
    querySelector: function(selector) {
        const element = document.querySelector(selector);
        if (!element) {
            console.warn(`Element with selector '${selector}' not found`);
        }
        return element;
    },

    // Show success message
    showSuccess: function(message) {
        this.showFlashMessage(message, 'success');
    },

    // Show error message
    showError: function(message) {
        this.showFlashMessage(message, 'danger');
    },

    // Show flash message using centralized helper from flash-messages.js
    showFlashMessage: function(message, type = 'info') {
        if (typeof window.showFlashMessage === 'function') {
            window.showFlashMessage(message, type);
        }
    },

    // Generate unique ID
    generateUniqueId: function() {
        return 'id-' + Date.now() + '-' + Math.random().toString(36).substring(2, 11);
    },

    // Deep clone object
    deepClone: function(obj) {
        return JSON.parse(JSON.stringify(obj));
    },

    // Sanitize HTML (text-only escape for plain strings)
    sanitizeHtml: function(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },

    // Safe DOM insertion for server-rendered HTML fragments.
    // Strips scripts, iframes, on* handlers, and dangerous href/src protocols.
    setSanitizedHtml: function(container, html) {
        if (!container) return;
        container.replaceChildren();
        if (typeof html !== 'string' || !html.trim()) return;

        const doc = new DOMParser().parseFromString(html, 'text/html');
        const root = doc.body;
        if (!root) return;

        root.querySelectorAll('script, iframe, object, embed, style, meta, link, base, form').forEach((el) => el.remove());
        root.querySelectorAll('*').forEach((el) => {
            [...el.attributes].forEach((attr) => {
                const name = String(attr.name || '').toLowerCase();
                const value = String(attr.value || '').trim().toLowerCase().replace(/[\s\x00-\x1f]/g, '');

                if (name.startsWith('on')) {
                    el.removeAttribute(attr.name);
                    return;
                }

                if (name === 'href' || name === 'src' || name === 'xlink:href' || name === 'formaction') {
                    if (
                        value.startsWith('javascript:') ||
                        value.startsWith('data:') ||
                        value.startsWith('vbscript:') ||
                        value.startsWith('file:') ||
                        value.startsWith('about:')
                    ) {
                        el.removeAttribute(attr.name);
                    }
                }
            });
        });

        const fragment = document.createDocumentFragment();
        while (root.firstChild) fragment.appendChild(root.firstChild);
        container.appendChild(fragment);
    }
};

// Make Utils available globally
window.Utils = Utils;
