/**
 * Shared utilities for admin analytics AG Grid pages (login logs, session logs).
 */
(function(global) {
    'use strict';

    function esc(s) {
        if (typeof global.esc === 'function') return global.esc(s);
        if (s === null || s === undefined) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function mapAnalyticsUserRow(item) {
        var u = item.user;
        return Object.assign({}, item, {
            user_id: u ? u.id : null,
            user_name: u ? (u.name || u.email || '') : '',
            user_email: u ? (u.email || '') : ''
        });
    }

    global.AnalyticsGridCommon = {
        esc: esc,
        mapAnalyticsUserRow: mapAnalyticsUserRow
    };
}(typeof window !== 'undefined' ? window : this));
