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

const DEFAULT_GROUP_HEADER_COLOR = '#f3f4f6';

function _validGroupColor(value) {
    const raw = String(value || '').trim().toLowerCase();
    return /^#[0-9a-f]{6}$/.test(raw) && raw !== DEFAULT_GROUP_HEADER_COLOR ? raw : '';
}

function _validGroupTextColor(value) {
    const raw = String(value || '').trim().toLowerCase();
    return /^#[0-9a-f]{6}$/.test(raw) ? raw : '';
}

function _groupColorFlagOn(value) {
    return value === true || value === 1 || value === 'true';
}

function _columnGroupNames(column) {
    if (!column || typeof column !== 'object') return { group: '', subgroup: '' };
    return { group: column.group || '', subgroup: column.subgroup || '' };
}

function _groupAppliesColor(meta, target) {
    if (!meta || typeof meta !== 'object') return false;
    const key = target === 'headers' ? 'apply_color_to_headers' : 'apply_color_to_cells';
    if (Object.prototype.hasOwnProperty.call(meta, key)) return _groupColorFlagOn(meta[key]);
    return _groupColorFlagOn(meta.apply_color_to_columns);
}

/**
 * Fill and text from the group that opted in. A subgroup with a fill or a text
 * colour wins over its parent. Text is '' when that group left it automatic.
 */
function _columnGroupColors(columns, columnGroups, index, target) {
    const { group, subgroup } = _columnGroupNames(columns?.[index]);
    const groups = columnGroups && typeof columnGroups === 'object' ? columnGroups : {};
    const picked = (meta) => {
        if (!_groupAppliesColor(meta, target)) return null;
        const fill = _validGroupColor(meta?.header_color);
        const text = _validGroupTextColor(meta?.header_text_color);
        if (!fill && !text) return null;
        return { fill, text };
    };
    if (subgroup) {
        const sub = picked(groups[`${group}::${subgroup}`]);
        if (sub) return sub;
    }
    if (!group) return null;
    return picked(groups[group]);
}

/** Hex to paint on column headers or cells, or ''. A subgroup that opted in wins over its parent. */
export function matrixColumnFillColor(columns, columnGroups, index, target = 'cells') {
    return _columnGroupColors(columns, columnGroups, index, target)?.fill || '';
}

/** Custom text hex for column headers or cells, or '' when text was left automatic. */
export function matrixColumnTextColor(columns, columnGroups, index, target = 'cells') {
    return _columnGroupColors(columns, columnGroups, index, target)?.text || '';
}

/** Left or right boundary class for one data column. Empty when the edge is not a group break. */
export function matrixColumnEdgeClass(columns, index, edge) {
    const { group, subgroup } = _columnGroupNames(columns?.[index]);
    const otherIndex = edge === 'start' ? index - 1 : index + 1;
    const other = Array.isArray(columns) && otherIndex >= 0 && otherIndex < columns.length
        ? columns[otherIndex]
        : null;
    const otherNames = _columnGroupNames(other);
    if (group && group !== otherNames.group) {
        return edge === 'start' ? 'matrix-group-boundary-start' : 'matrix-group-boundary';
    }
    if (subgroup && subgroup !== otherNames.subgroup) {
        return edge === 'start' ? 'matrix-subgroup-boundary-start' : 'matrix-subgroup-boundary';
    }
    return '';
}

/** Thick group lines, and an optional column tint, on a data cell. */
export function applyMatrixColumnGroupChrome(cell, columns, columnGroups, index) {
    if (!cell || !Array.isArray(columns)) return;
    const start = matrixColumnEdgeClass(columns, index, 'start');
    const end = matrixColumnEdgeClass(columns, index, 'end');
    if (start) cell.classList.add(start);
    if (end) cell.classList.add(end);
    const fill = matrixColumnFillColor(columns, columnGroups, index, 'cells');
    const text = matrixColumnTextColor(columns, columnGroups, index, 'cells');
    if (!fill && !text) return;
    cell.classList.add('matrix-group-colored');
    if (fill) cell.style.setProperty('--matrix-group-color', fill);
    if (text) cell.style.setProperty('--matrix-group-text-color', text);
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
