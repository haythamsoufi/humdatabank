/** Shared matrix helpers used across submodules. */

export const ROW_TOTAL_COLUMN_NAME = 'Total';

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
