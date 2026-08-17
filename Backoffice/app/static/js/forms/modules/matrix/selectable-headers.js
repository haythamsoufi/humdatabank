/** Selectable column-header dropdowns for matrix items.
 *
 * When a column has header_type="selectable" in its matrix config, the
 * <th> in the entry form renders a <select> instead of static text.
 * The user's choice is stored in matrix.data under the key
 * "col_header|{columnName}" and serialised into the hidden field
 * alongside cell values.
 *
 * Key-format note
 * ───────────────
 * "col_header|SP1" is safe because:
 *   • No leading "_"    → not stripped by __reorderMatrixData
 *   • Ends with "|SP1"  → __parseMatrixCellKey (looks for "_SP1" suffix) ignores it
 *   • Pipe "|" is never used in Form-Builder column codes
 */
import { debugLog, debugWarn } from '../debug.js';
import { _t } from './shared.js';
import { __serializeMatrixData } from './formatting.js';

const HEADER_KEY_PREFIX = 'col_header|';
const HEADER_GO_UNMATCHED_PREFIX = 'col_header_go_unmatched|';
const ROW_GO_UNMATCHED_KEY_PREFIX = 'row_go_unmatched|';
const GO_UNMATCHED_TOOLTIP = 'Not matched in GO API — imported from Excel';

/**
 * True for matrix-data keys that store metadata and must NOT be treated as
 * cell data: selectable column-header choices and GO-unmatched flags.
 * Used by collectMatrixData to avoid deleting these as "stale cell keys".
 */
export function __isMatrixHeaderDataKey(key) {
    if (typeof key !== 'string') return false;
    return (
        key.startsWith(HEADER_KEY_PREFIX) ||
        key.startsWith(HEADER_GO_UNMATCHED_PREFIX) ||
        key.startsWith(ROW_GO_UNMATCHED_KEY_PREFIX)
    );
}

/**
 * True when a column has header_type="selectable" and no value has been chosen
 * yet in its header dropdown/free-text input. Cells in such a column stay
 * disabled until the header value is set, mirroring the server-rendered state
 * in matrix_table.html.
 * @param {Object|null} matrix - matrices.get(fieldId) entry (needs .config.columns and .data)
 * @param {string} columnName
 * @returns {boolean}
 */
export function __matrixCellIsHeaderGated(matrix, columnName) {
    if (!matrix || !columnName) return false;
    const columns = matrix.config?.columns || [];
    const column = columns.find((c) => c && typeof c === 'object' && c.name === columnName);
    if (!column || column.header_type !== 'selectable') return false;

    const saved = matrix.data ? matrix.data[HEADER_KEY_PREFIX + String(columnName)] : null;
    return !(saved && String(saved).trim());
}

export const matrixSelectableHeadersMixin = {

/**
 * Return the matrix-data dict key for a column's selected header value.
 */
_headerDataKey(columnName) {
    return HEADER_KEY_PREFIX + String(columnName || '');
},

_headerGoUnmatchedDataKey(columnName) {
    return HEADER_GO_UNMATCHED_PREFIX + String(columnName || '');
},

_isHeaderGoUnmatched(fieldId, colName) {
    const matrix = this.matrices.get(String(fieldId || ''));
    if (!matrix?.data || !colName) return false;
    const flag = matrix.data[this._headerGoUnmatchedDataKey(colName)];
    return flag === 1 || flag === '1' || flag === true;
},

_setHeaderGoUnmatchedUI(selectEl, isUnmatched) {
    const picker = selectEl?.closest('.matrix-header-picker');
    if (picker) {
        picker.classList.toggle('matrix-header-picker--go-unmatched', !!isUnmatched);
        const label = picker.querySelector('.matrix-header-picker-label');
        if (label) {
            if (isUnmatched) {
                label.setAttribute('title', GO_UNMATCHED_TOOLTIP);
            } else {
                label.removeAttribute('title');
            }
        }
    }
},

_applyGoUnmatchedHeaderOption(selectEl, savedStr) {
    const otherOpt = selectEl.querySelector('option[value="__other__"]');
    if (otherOpt) {
        selectEl.value = '__other__';
        const container = selectEl.closest('.matrix-container');
        const colName = selectEl.dataset.colName;
        const otherInput = container?.querySelector(
            `.matrix-header-other-input[data-col-name="${colName}"]`
        );
        if (otherInput) otherInput.value = savedStr;
        return;
    }

    selectEl.querySelectorAll('option[data-go-unmatched="true"]').forEach(o => o.remove());
    const opt = document.createElement('option');
    opt.value = savedStr;
    opt.textContent = savedStr;
    opt.dataset.goUnmatched = 'true';
    opt.title = GO_UNMATCHED_TOOLTIP;
    selectEl.appendChild(opt);
    selectEl.value = savedStr;
},

/**
 * Initialize all selectable-header <select> elements for a matrix.
 * Called once after the matrix is registered in initializeMatrices().
 */
async initSelectableHeaders(fieldId) {
    const fieldIdStr = String(fieldId || '');
    const matrix = this.matrices.get(fieldIdStr);
    if (!matrix?.container) return;

    const selects = Array.from(
        matrix.container.querySelectorAll('thead .matrix-header-select')
    );
    if (selects.length === 0) return;

    debugLog('matrix-handler', `[SEL-HDR] Init ${selects.length} selectable header(s) for field ${fieldIdStr}`);

    await Promise.all(
        selects.map(sel => this._initOneHeaderSelect(sel, fieldIdStr))
    ).catch(err => debugWarn('matrix-handler', '[SEL-HDR] Init error:', err));

    // Sync cell editability with whatever header values were just restored
    // (server already renders the correct disabled state, but this keeps
    // the two in sync defensively, e.g. after async list-library loading).
    this._applyHeaderGatingForMatrix(fieldIdStr);
},

async _initOneHeaderSelect(selectEl, fieldId) {
    const source = selectEl.dataset.headerSource;
    const lookupListId = selectEl.dataset.headerLookupListId;
    const displayColumn = selectEl.dataset.headerListDisplayColumn;
    const allowOther = selectEl.dataset.headerAllowOther === 'true';

    this._syncHeaderPickerUI(selectEl);

    if (source === 'list_library' && lookupListId && displayColumn) {
        await this._loadHeaderListOptions(selectEl, fieldId, lookupListId, displayColumn, allowOther);
    } else {
        this._restoreHeaderSelectValue(selectEl, fieldId);
        this._updateHeaderOtherVisibility(selectEl);
        this._syncHeaderPickerUI(selectEl);
    }
},

/**
 * Fetch list-library options and populate the header <select>.
 * Reuses the same matrixSearchOptionsCache as the row-search dropdown.
 */
async _loadHeaderListOptions(selectEl, fieldId, lookupListId, displayColumn, allowOther) {
    const matrix = this.matrices.get(fieldId);
    const canEdit = matrix?.container?.dataset?.canEdit !== 'false';
    const placeholderOpt = selectEl.querySelector('option[value=""]');
    if (placeholderOpt) placeholderOpt.textContent = _t('Loading...');
    selectEl.disabled = true;
    const trigger = selectEl.closest('.matrix-header-picker')
        ?.querySelector('.matrix-header-picker-trigger');
    if (trigger) trigger.disabled = true;
    this._syncHeaderPickerUI(selectEl);

    try {
        // Prefer the plugin config saved specifically for this column's header
        // dropdown (e.g. Emergency Operations filters chosen in the "Selectable
        // header" panel); fall back to the matrix-level row list's plugin config
        // for older items that only ever had a single config panel.
        const colName = selectEl.dataset.colName;
        const columnDef = Array.isArray(matrix?.config?.columns)
            ? matrix.config.columns.find(c => c && c.name === colName)
            : null;
        const pluginConfig = columnDef?.header_plugin_config || matrix?.config?.plugin_config || null;
        const aesId = this.getAssignmentEntityStatusId();

        const allOptions = await this._fetchMatrixSearchOptionsCached(
            lookupListId, displayColumn, [], pluginConfig, aesId
        );

        // Clear non-placeholder / non-other options
        Array.from(selectEl.options).forEach(o => {
            if (o.value !== '' && o.value !== '__other__') o.remove();
        });
        if (placeholderOpt) {
            placeholderOpt.textContent = selectEl.dataset.headerPlaceholder || _t('Select...');
        }

        const otherOpt = selectEl.querySelector('option[value="__other__"]');
        allOptions.forEach(opt => {
            const el = document.createElement('option');
            el.value = String(opt.value || '');
            el.textContent = String(opt.value || '');
            otherOpt ? selectEl.insertBefore(el, otherOpt) : selectEl.appendChild(el);
        });

        if (allowOther && !selectEl.querySelector('option[value="__other__"]')) {
            const o = document.createElement('option');
            o.value = '__other__';
            o.textContent = _t('Other (please specify)...');
            selectEl.appendChild(o);
        }
    } catch (err) {
        debugWarn('matrix-handler', '[SEL-HDR] Failed to load list options:', err);
        if (placeholderOpt) placeholderOpt.textContent = _t('Error loading options');
    } finally {
        selectEl.disabled = !canEdit;
        const trigger = selectEl.closest('.matrix-header-picker')
            ?.querySelector('.matrix-header-picker-trigger');
        if (trigger) trigger.disabled = selectEl.disabled;
        this._restoreHeaderSelectValue(selectEl, fieldId);
        this._updateHeaderOtherVisibility(selectEl);
        this._syncHeaderPickerUI(selectEl);
    }
},

/**
 * Set the <select> value from matrix.data["col_header|{col}"].
 * If the saved value isn't in the option list it's treated as Other.
 */
_restoreHeaderSelectValue(selectEl, fieldId) {
    const matrix = this.matrices.get(String(fieldId || ''));
    if (!matrix?.data) return;

    const colName = selectEl.dataset.colName;
    if (!colName) return;

    const saved = matrix.data[this._headerDataKey(colName)];
    if (!saved) {
        this._setHeaderGoUnmatchedUI(selectEl, false);
        return;
    }

    const savedStr = String(saved).trim();
    if (!savedStr) {
        this._setHeaderGoUnmatchedUI(selectEl, false);
        return;
    }

    const isUnmatched = this._isHeaderGoUnmatched(fieldId, colName);

    if (!Array.from(selectEl.options).some(o => o.value === savedStr)) {
        if (isUnmatched) {
            this._applyGoUnmatchedHeaderOption(selectEl, savedStr);
            this._setHeaderGoUnmatchedUI(selectEl, true);
            return;
        }
        const otherOpt = selectEl.querySelector('option[value="__other__"]');
        if (otherOpt) {
            selectEl.value = '__other__';
            const container = selectEl.closest('.matrix-container');
            const otherInput = container?.querySelector(
                `.matrix-header-other-input[data-col-name="${colName}"]`
            );
            if (otherInput) otherInput.value = savedStr;
            this._setHeaderGoUnmatchedUI(selectEl, false);
            return;
        }
        debugWarn(
            'matrix-handler',
            `[SEL-HDR] Saved header "${savedStr}" for ${colName} is not in GO options and has no unmatched flag`
        );
    }

    selectEl.value = savedStr;
    this._setHeaderGoUnmatchedUI(selectEl, isUnmatched);
},

/**
 * Sync selectable column-header dropdowns from matrix.data (e.g. after Excel import).
 */
async restoreSelectableHeadersFromData(fieldId) {
    const fieldIdStr = String(fieldId || '');
    const matrix = this.matrices.get(fieldIdStr);
    if (!matrix?.container) return;

    const selects = Array.from(matrix.container.querySelectorAll('thead .matrix-header-select'));
    if (!selects.length) return;

    await Promise.all(
        selects.map(async (selectEl) => {
            const colName = selectEl.dataset.colName;
            const saved = matrix.data?.[this._headerDataKey(colName)];
            if (!saved || !String(saved).trim()) return;

            const source = selectEl.dataset.headerSource;
            const lookupListId = selectEl.dataset.headerLookupListId;
            const displayColumn = selectEl.dataset.headerListDisplayColumn;
            const hasRealOptions = Array.from(selectEl.options).some(
                o => o.value && o.value !== '__other__'
            );

            if (source === 'list_library' && lookupListId && displayColumn && !hasRealOptions) {
                await this._initOneHeaderSelect(selectEl, fieldIdStr);
            } else {
                this._restoreHeaderSelectValue(selectEl, fieldIdStr);
                this._updateHeaderOtherVisibility(selectEl);
                this._syncHeaderPickerUI(selectEl);
            }
        })
    ).catch(err => debugWarn('matrix-handler', '[SEL-HDR] Restore from data error:', err));
},

/**
 * Rebuild the custom header-picker label and menu from the (hidden) native
 * <select>. Keeps the visible control looking like a table header while the
 * native select continues to drive persistence.
 */
_syncHeaderPickerUI(selectEl) {
    const picker = selectEl?.closest('.matrix-header-picker');
    if (!picker) return;

    const labelEl = picker.querySelector('.matrix-header-picker-label');
    const menuEl = picker.querySelector('.matrix-header-picker-menu');
    const trigger = picker.querySelector('.matrix-header-picker-trigger');
    if (!labelEl || !menuEl) return;

    const fieldId = selectEl.dataset.fieldId || '';
    const colName = selectEl.dataset.colName || '';
    const isUnmatched = this._isHeaderGoUnmatched(fieldId, colName);
    const placeholder = selectEl.dataset.headerPlaceholder || _t('Select...');
    const selectedOpt = selectEl.options[selectEl.selectedIndex];
    const hasValue = !!selectEl.value;

    if (selectEl.disabled && !hasValue && selectedOpt?.textContent === _t('Loading...')) {
        labelEl.textContent = _t('Loading...');
        labelEl.classList.add('matrix-header-picker-label--placeholder');
    } else if (hasValue && selectedOpt) {
        if (isUnmatched && selectEl.value === '__other__') {
            const otherInput = selectEl.closest('.matrix-container')?.querySelector(
                `.matrix-header-other-input[data-col-name="${colName}"]`
            );
            const otherText = otherInput?.value?.trim();
            labelEl.textContent = otherText || selectedOpt.textContent;
        } else {
            labelEl.textContent = selectedOpt.textContent;
        }
        labelEl.classList.toggle('matrix-header-picker-label--placeholder', selectEl.value === '');
    } else {
        labelEl.textContent = placeholder;
        labelEl.classList.add('matrix-header-picker-label--placeholder');
    }

    this._setHeaderGoUnmatchedUI(selectEl, isUnmatched);

    if (trigger) {
        trigger.disabled = selectEl.disabled;
        trigger.setAttribute('aria-expanded', picker.classList.contains('is-open') ? 'true' : 'false');
    }

    menuEl.replaceChildren();
    Array.from(selectEl.options).forEach(opt => {
        const li = document.createElement('li');
        li.className = 'matrix-header-picker-option';
        if (opt.dataset.goUnmatched === 'true') {
            li.classList.add('matrix-header-picker-option--go-unmatched');
            li.title = GO_UNMATCHED_TOOLTIP;
        }
        li.setAttribute('role', 'option');
        li.dataset.value = opt.value;
        li.textContent = opt.textContent;
        if (opt.value === selectEl.value) li.classList.add('is-selected');
        if (opt.value === '') li.classList.add('is-placeholder');
        menuEl.appendChild(li);
    });
},

/** Close every open header picker (used before opening another). */
_closeAllHeaderPickers(exceptPicker = null) {
    document.querySelectorAll('.matrix-header-picker.is-open').forEach(picker => {
        if (exceptPicker && picker === exceptPicker) return;
        picker.classList.remove('is-open');
        const menu = picker.querySelector('.matrix-header-picker-menu');
        menu?.classList.add('hidden');
        picker.querySelector('.matrix-header-picker-trigger')
            ?.setAttribute('aria-expanded', 'false');
    });
},

/** Toggle the custom header picker menu open/closed. */
handleHeaderPickerToggle(triggerEl) {
    const picker = triggerEl?.closest('.matrix-header-picker');
    const selectEl = picker?.querySelector('.matrix-header-select');
    if (!picker || !selectEl || selectEl.disabled) return;

    const menu = picker.querySelector('.matrix-header-picker-menu');
    if (!menu) return;

    const willOpen = !picker.classList.contains('is-open');
    this._closeAllHeaderPickers(willOpen ? picker : null);

    picker.classList.toggle('is-open', willOpen);
    menu.classList.toggle('hidden', !willOpen);
    triggerEl.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
},

/** Select an option from the custom header picker menu. */
handleHeaderPickerOptionClick(optionEl) {
    const picker = optionEl?.closest('.matrix-header-picker');
    const selectEl = picker?.querySelector('.matrix-header-select');
    if (!picker || !selectEl) return;

    const value = optionEl.dataset.value ?? '';
    selectEl.value = value;
    selectEl.dispatchEvent(new Event('change', { bubbles: true }));

    this._closeAllHeaderPickers();
    this._syncHeaderPickerUI(selectEl);
},

/**
 * Show / hide the free-text Other input based on the select's current value.
 */
_updateHeaderOtherVisibility(selectEl) {
    const colName = selectEl.dataset.colName;
    const container = selectEl.closest('.matrix-container');
    const otherInput = container?.querySelector(
        `.matrix-header-other-input[data-col-name="${colName}"]`
    );
    if (!otherInput) return;

    if (selectEl.value === '__other__') {
        otherInput.classList.remove('hidden');
    } else {
        otherInput.classList.add('hidden');
        otherInput.value = '';
    }
},

/** Called when a .matrix-header-select changes. */
handleHeaderSelectChange(selectEl) {
    const fieldId = String(selectEl.dataset.fieldId || '');
    const colName = selectEl.dataset.colName;
    if (!fieldId || !colName) return;

    this._updateHeaderOtherVisibility(selectEl);
    this._syncHeaderPickerUI(selectEl);

    // Don't persist __other__ yet — wait for the text input
    if (selectEl.value !== '__other__') {
        const selectedOpt = selectEl.options[selectEl.selectedIndex];
        if (!selectedOpt?.dataset?.goUnmatched) {
            delete this.matrices.get(fieldId)?.data?.[this._headerGoUnmatchedDataKey(colName)];
        }
        this._saveHeaderValue(fieldId, colName, selectEl.value || '');
    }
},

/** Called when a .matrix-header-other-input receives input. */
handleHeaderOtherInputChange(inputEl) {
    const fieldId = String(inputEl.dataset.fieldId || '');
    const colName = inputEl.dataset.colName;
    if (!fieldId || !colName) return;
    this._saveHeaderValue(fieldId, colName, inputEl.value.trim());
},

/** Persist value → matrix.data and sync hidden field. */
_saveHeaderValue(fieldId, colName, value) {
    const matrix = this.matrices.get(String(fieldId || ''));
    if (!matrix) return;

    const key = this._headerDataKey(colName);
    const unmatchedKey = this._headerGoUnmatchedDataKey(colName);
    if (value) {
        matrix.data[key] = value;
    } else {
        delete matrix.data[key];
        delete matrix.data[unmatchedKey];
    }

    if (matrix.hiddenField) {
        matrix.hiddenField.value = __serializeMatrixData(matrix.data);
    }

    this._applyHeaderGatingForColumn(fieldId, colName);

    debugLog('matrix-handler', `[SEL-HDR] header "${colName}"="${value}" saved for field ${fieldId}`);
},

/**
 * Re-apply editability to every rendered cell of a header-gated column
 * (pre-rendered static rows and already-added dynamic rows), after its
 * header value changes.
 */
_applyHeaderGatingForColumn(fieldId, colName) {
    const matrix = this.matrices.get(String(fieldId || ''));
    if (!matrix?.container || !colName) return;

    const columns = matrix.config?.columns || [];
    const columnDef = columns.find((c) => c && typeof c === 'object' && c.name === colName);
    const isVariable = !!(columnDef && (columnDef.is_variable === true || columnDef.type === 'variable'));
    const variableReadonly = isVariable ? (columnDef.variable_readonly !== false) : false;

    matrix.container.querySelectorAll(`tbody input[data-column="${colName}"]`).forEach((input) => {
        this._applyMatrixInputEditability(input, matrix.container, variableReadonly);
    });
},

/**
 * Re-sync cell editability for every selectable-header column in a matrix.
 * Called after (re)loading matrix data (initial load, draft restore) so
 * already-rendered cells match the current header selections.
 */
_applyHeaderGatingForMatrix(fieldId) {
    const matrix = this.matrices.get(String(fieldId || ''));
    if (!matrix?.container) return;

    (matrix.config?.columns || []).forEach((column) => {
        if (column && typeof column === 'object' && column.header_type === 'selectable') {
            this._applyHeaderGatingForColumn(fieldId, column.name);
        }
    });
},

};
