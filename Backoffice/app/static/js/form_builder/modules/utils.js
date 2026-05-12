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
        return 'id-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    },

    // Deep clone object
    deepClone: function(obj) {
        return JSON.parse(JSON.stringify(obj));
    },

    // Sanitize HTML
    sanitizeHtml: function(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
};

// Make Utils available globally
window.Utils = Utils;
