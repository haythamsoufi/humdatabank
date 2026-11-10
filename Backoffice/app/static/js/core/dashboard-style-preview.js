/**
 * Dev-only UI style preview switcher (dashboard + entry form).
 * Requires .ui-style-root and optional #ui-style-preview (DEBUG + loopback).
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'uiStylePreview';
    var LEGACY_STORAGE_KEY = 'dashboardStylePreview';
    var ALLOWED = ['ifrc', 'erp', 'legacy'];
    /* Production/staging always use legacy until a shipped style is chosen. */
    var DEFAULT_STYLE = 'legacy';

    function normalizeStyle(value) {
        return ALLOWED.indexOf(value) !== -1 ? value : DEFAULT_STYLE;
    }

    function readStoredStyle() {
        try {
            var stored = window.localStorage.getItem(STORAGE_KEY);
            if (stored == null) {
                stored = window.localStorage.getItem(LEGACY_STORAGE_KEY);
            }
            return normalizeStyle(stored);
        } catch (err) {
            return DEFAULT_STYLE;
        }
    }

    function writeStoredStyle(style) {
        try {
            window.localStorage.setItem(STORAGE_KEY, style);
        } catch (err) {
            /* ignore quota / private mode */
        }
    }

    function applyStyle(root, style, previewEnabled) {
        var next = previewEnabled ? normalizeStyle(style) : DEFAULT_STYLE;
        root.setAttribute('data-ui-style', next);
        return next;
    }

    function syncButtons(switcher, activeStyle) {
        if (!switcher) {
            return;
        }
        switcher.querySelectorAll('[data-ui-style-option]').forEach(function (btn) {
            var option = btn.getAttribute('data-ui-style-option');
            var isActive = option === activeStyle;
            btn.classList.toggle('is-active', isActive);
            btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });
    }

    function init() {
        var root = document.querySelector('.ui-style-root');
        if (!root) {
            return;
        }

        var previewEnabled = root.getAttribute('data-style-preview') === '1';
        var active = applyStyle(
            root,
            previewEnabled ? readStoredStyle() : DEFAULT_STYLE,
            previewEnabled
        );

        if (!previewEnabled) {
            return;
        }

        var switcher = document.getElementById('ui-style-preview');
        syncButtons(switcher, active);

        if (!switcher) {
            return;
        }

        switcher.addEventListener('click', function (event) {
            var btn = event.target.closest('[data-ui-style-option]');
            if (!btn || !switcher.contains(btn)) {
                return;
            }
            var next = normalizeStyle(btn.getAttribute('data-ui-style-option'));
            writeStoredStyle(next);
            active = applyStyle(root, next, true);
            syncButtons(switcher, active);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
