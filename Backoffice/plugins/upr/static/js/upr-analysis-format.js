/* UPR Analysis — number formatting shared by every renderer (tab, export, slides).
 * A view carries raw numbers plus a format name (see plugins/upr/analysis_spec.py);
 * this module turns a number into text so a KPI, a chart axis, a tooltip and a
 * table cell always agree. */
(function (global) {
    'use strict';

    var root = global.UprAnalysis = global.UprAnalysis || {};

    function isNumber(value) {
        return typeof value === 'number' && !isNaN(value);
    }

    function int(value) {
        if (!isNumber(value)) return '—';
        return Math.round(value).toLocaleString();
    }

    function money(value) {
        if (!isNumber(value)) return '—';
        var abs = Math.abs(value);
        if (abs >= 1e9) return (value / 1e9).toFixed(1).replace(/\.0$/, '') + 'B';
        if (abs >= 1e6) return (value / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
        if (abs >= 1e3) return (value / 1e3).toFixed(0) + 'K';
        return Math.round(value).toLocaleString();
    }

    function pct(value) {
        if (!isNumber(value)) return '—';
        return (Math.round(value * 10) / 10) + '%';
    }

    function absInt(value) {
        return isNumber(value) ? int(Math.abs(value)) : '—';
    }

    var FORMATTERS = { int: int, money: money, pct: pct, abs_int: absInt };

    /** Formatter for a view ``format`` name; unknown names fall back to ``int``. */
    function formatter(name) {
        return FORMATTERS[name] || int;
    }

    function format(value, name) {
        return formatter(name)(value);
    }

    /** A table cell: number, text, empty, or ``{value, midyear}``. */
    function rawValue(cell) {
        if (cell && typeof cell === 'object' && Object.prototype.hasOwnProperty.call(cell, 'value')) return cell.value;
        return cell;
    }

    function cellText(cell) {
        var value = rawValue(cell);
        if (isNumber(value)) return Math.round(value).toLocaleString();
        if (value == null || value === '') return '—';
        return String(value);
    }

    /** Fill ``{name}`` placeholders (the server's interface strings use them). */
    function fill(template, values) {
        return String(template == null ? '' : template).replace(/\{(\w+)\}/g, function (match, key) {
            return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : match;
        });
    }

    root.format = {
        fill: fill,
        int: int,
        money: money,
        pct: pct,
        absInt: absInt,
        formatter: formatter,
        format: format,
        rawValue: rawValue,
        cellText: cellText
    };
})(typeof window !== 'undefined' ? window : globalThis);
