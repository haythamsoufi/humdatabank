/**
 * AG Grid shared utilities — i18n, HTML escaping, device detection.
 * Load after ag-grid-community.min.js and before other ag-grid helper modules.
 */
(function(global) {
    'use strict';

    var AgGridUtils = {};

    /**
     * Get translation from window.agGridTranslations or #i18n-json.
     * @param {string} key
     * @param {string} defaultValue
     * @returns {string}
     */
    AgGridUtils.getTranslation = function(key, defaultValue) {
        if (global.agGridTranslations && global.agGridTranslations[key]) {
            return global.agGridTranslations[key];
        }

        try {
            var i18nEl = global.document && global.document.getElementById('i18n-json');
            if (i18nEl && i18nEl.textContent) {
                var i18n = JSON.parse(i18nEl.textContent);
                if (i18n && i18n[key] !== null && i18n[key] !== undefined && i18n[key] !== '') {
                    return i18n[key];
                }
            }
        } catch (e) {
            // Ignore parsing errors
        }

        return defaultValue;
    };

    /**
     * Escape HTML to prevent XSS.
     * @param {*} text
     * @returns {string}
     */
    AgGridUtils.escapeHtml = function(text) {
        if (text === null || text === undefined) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    };

    /**
     * Escape value for HTML attributes.
     * @param {*} value
     * @returns {string}
     */
    AgGridUtils.escapeHtmlAttr = function(value) {
        return AgGridUtils.escapeHtml(value);
    };

    /**
     * True on phones/tablets where nested grid scroll feels awkward.
     * @returns {boolean}
     */
    AgGridUtils.isCoarsePointerDevice = function() {
        try {
            if (global.matchMedia && global.matchMedia('(hover: none) and (pointer: coarse)').matches) {
                return true;
            }
            if (global.matchMedia && global.matchMedia('(max-width: 768px)').matches) {
                return true;
            }
        } catch (e) {
            // matchMedia unavailable — fall through to width check
        }
        return (global.innerWidth || 0) <= 768;
    };

    global.AgGridUtils = AgGridUtils;

    // Backward-compatible global aliases used by admin page scripts
    global.escapeHtmlAttr = AgGridUtils.escapeHtmlAttr;

})(typeof window !== 'undefined' ? window : this);
