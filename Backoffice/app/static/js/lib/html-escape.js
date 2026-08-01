/**
 * Minimal HTML escaping for building safe option/list markup strings.
 * Prefer textContent when possible; use esc() only when assembling HTML.
 */
(function () {
    'use strict';

    function esc(value) {
        if (value == null) return '';
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    window.esc = esc;
    window.HtmlEscape = { esc: esc };
})();
