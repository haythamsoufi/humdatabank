/** Shared matrix helpers used across submodules. */

export const ROW_TOTAL_COLUMN_NAME = 'Total';

/**
 * Index among data columns where the row-total column is rendered.
 * Missing or invalid positions keep the historical placement (after every data column).
 * Returns null when row totals are turned off.
 */
export function __rowTotalColumnIndex(config, columnCount) {
    if (config?.show_row_totals === false) return null;
    const count = Number.isFinite(columnCount) && columnCount > 0 ? Math.trunc(columnCount) : 0;
    const raw = config?.row_total_position;
    const n = typeof raw === 'number'
        ? raw
        : (typeof raw === 'string' && raw.trim() !== '' ? Number(raw) : NaN);
    if (!Number.isFinite(n)) return count;
    const index = Math.trunc(n);
    if (index < 0) return 0;
    if (index > count) return count;
    return index;
}

export const _t = (k) => (typeof window.t === 'function' ? window.t(k) : k);

/** Whether matrix cell values may be edited (mirrors server can_edit / entry form POST availability). */
export function __canEditMatrixContainer(container) {
    if (container) {
        const attr = container.getAttribute('data-can-edit');
        if (attr === 'true') return true;
        if (attr === 'false') return false;
    }
    const jsContext = document.getElementById('entry-form-js-context');
    if (jsContext?.getAttribute('data-can-edit') === 'false') {
        return false;
    }
    return !!document.getElementById('focalDataEntryForm');
}
