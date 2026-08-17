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

export const matrixSelectableHeadersMixin = {

/**
 * Return the matrix-data dict key for a column's selected header value.
 */
_headerDataKey(columnName) {
    return HEADER_KEY_PREFIX + String(columnName || '');
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
    if (!saved) return;

    if (Array.from(selectEl.options).some(o => o.value === saved)) {
        selectEl.value = saved;
        return;
    }

    // Saved value is a free-text "Other" entry
    const otherOpt = selectEl.querySelector('option[value="__other__"]');
    if (otherOpt) {
        selectEl.value = '__other__';
        const container = selectEl.closest('.matrix-container');
        const otherInput = container?.querySelector(
            `.matrix-header-other-input[data-col-name="${colName}"]`
        );
        if (otherInput) otherInput.value = saved;
    }
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

    const placeholder = selectEl.dataset.headerPlaceholder || _t('Select...');
    const selectedOpt = selectEl.options[selectEl.selectedIndex];
    const hasValue = !!selectEl.value;

    if (selectEl.disabled && !hasValue && selectedOpt?.textContent === _t('Loading...')) {
        labelEl.textContent = _t('Loading...');
        labelEl.classList.add('matrix-header-picker-label--placeholder');
    } else if (hasValue && selectedOpt) {
        labelEl.textContent = selectedOpt.textContent;
        labelEl.classList.toggle('matrix-header-picker-label--placeholder', selectEl.value === '');
    } else {
        labelEl.textContent = placeholder;
        labelEl.classList.add('matrix-header-picker-label--placeholder');
    }

    if (trigger) {
        trigger.disabled = selectEl.disabled;
        trigger.setAttribute('aria-expanded', picker.classList.contains('is-open') ? 'true' : 'false');
    }

    menuEl.replaceChildren();
    Array.from(selectEl.options).forEach(opt => {
        const li = document.createElement('li');
        li.className = 'matrix-header-picker-option';
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
    if (value) {
        matrix.data[key] = value;
    } else {
        delete matrix.data[key];
    }

    if (matrix.hiddenField) {
        matrix.hiddenField.value = __serializeMatrixData(matrix.data);
    }
    debugLog('matrix-handler', `[SEL-HDR] header "${colName}"="${value}" saved for field ${fieldId}`);
},

};
