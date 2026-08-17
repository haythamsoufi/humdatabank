/** Selectable column-header dropdowns for matrix items.
 *
 * When a column has header_type="selectable" in its matrix config, the
 * <th> in the entry form renders a <select> instead of static text.
 * The user's choice is stored in matrix.data under the key
 * "col_header|{columnName}" and serialised into the hidden field
 * alongside cell values.
 *
 * The native <select> stays the source of truth for options and persistence;
 * the visible control is the custom .matrix-header-picker (button + listbox)
 * so a column header can wrap onto several lines. The native select is
 * aria-hidden/tabindex="-1" in matrix_table.html, so the picker itself has to
 * carry the full keyboard and ARIA behaviour.
 *
 * Key-format note
 * ───────────────
 * "col_header|SP1" is safe because:
 *   • No leading "_"    → not stripped by __reorderMatrixData
 *   • Ends with "|SP1"  → __parseMatrixCellKey (looks for "_SP1" suffix) ignores it
 *   • Pipe "|" is never used in Form-Builder column codes
 */
import { debugLog, debugWarn } from '../debug.js';
import { _t, __canEditMatrixContainer } from './shared.js';
import { __serializeMatrixData } from './formatting.js';

const HEADER_KEY_PREFIX = 'col_header|';
const HEADER_GO_UNMATCHED_PREFIX = 'col_header_go_unmatched|';
const ROW_GO_UNMATCHED_KEY_PREFIX = 'row_go_unmatched|';
const OTHER_VALUE = '__other__';

/** Free-text header edits save on a pause rather than on every keystroke. */
const OTHER_INPUT_SAVE_DELAY_MS = 250;

/** Resolved lazily: window.t is installed by layout.html after this module loads. */
const goUnmatchedTooltip = () => _t('Not matched in GO API — imported from Excel');

let headerPickerMenuSeq = 0;

/**
 * Find the free-text "Other" input belonging to a header select.
 * Matching on dataset rather than an interpolated attribute selector keeps
 * column names containing quotes from throwing (and "undefined" from matching).
 */
function findHeaderOtherInput(selectEl) {
    const colName = selectEl?.dataset?.colName;
    const scope = selectEl?.closest('th') || selectEl?.closest('.matrix-container');
    if (!colName || !scope) return null;
    return Array.from(scope.querySelectorAll('.matrix-header-other-input'))
        .find((el) => el.dataset.colName === colName) || null;
}

/** Inverse of findHeaderOtherInput: the header select an "Other" input belongs to. */
function findHeaderSelectForOtherInput(inputEl) {
    const colName = inputEl?.dataset?.colName;
    const scope = inputEl?.closest('th') || inputEl?.closest('.matrix-container');
    if (!colName || !scope) return null;
    return Array.from(scope.querySelectorAll('.matrix-header-select'))
        .find((el) => el.dataset.colName === colName) || null;
}

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
                label.setAttribute('title', goUnmatchedTooltip());
            } else {
                label.removeAttribute('title');
            }
        }
    }
},

/**
 * Point the select at its "Other" option and load `value` into the free-text
 * input. Returns false when the column has no "Other" option configured.
 */
_useOtherHeaderOption(selectEl, value) {
    if (!selectEl.querySelector(`option[value="${OTHER_VALUE}"]`)) return false;
    selectEl.value = OTHER_VALUE;
    const otherInput = findHeaderOtherInput(selectEl);
    if (otherInput) otherInput.value = value;
    return true;
},

/**
 * Add an option for a stored value that the current option list does not
 * contain — either an Excel import with no GO API match, or a list-library
 * entry that has since been renamed or filtered out. Without it the header
 * would render blank while the stored value still ungates the cells below.
 */
_injectStoredHeaderOption(selectEl, value, { goUnmatched = false } = {}) {
    selectEl.querySelectorAll('option[data-stored-header-value="true"]').forEach((o) => o.remove());
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = value;
    opt.dataset.storedHeaderValue = 'true';
    if (goUnmatched) {
        opt.dataset.goUnmatched = 'true';
        opt.title = goUnmatchedTooltip();
    }
    selectEl.appendChild(opt);
    selectEl.value = value;
},

_applyGoUnmatchedHeaderOption(selectEl, savedStr) {
    if (this._useOtherHeaderOption(selectEl, savedStr)) return;
    this._injectStoredHeaderOption(selectEl, savedStr, { goUnmatched: true });
},

/** Reset a header select to "nothing chosen" (e.g. an import cleared the value). */
_clearHeaderSelectUI(selectEl) {
    selectEl.querySelectorAll('option[data-stored-header-value="true"]').forEach((o) => o.remove());
    selectEl.value = '';
    const otherInput = findHeaderOtherInput(selectEl);
    if (otherInput) {
        otherInput.value = '';
        otherInput.classList.add('hidden');
    }
    this._setHeaderGoUnmatchedUI(selectEl, false);
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
        selectEl.dataset.headerState = 'ready';
        this._restoreHeaderSelectValue(selectEl, fieldId);
        this._updateHeaderOtherVisibility(selectEl);
        this._syncHeaderPickerUI(selectEl);
    }
},

/**
 * Fetch list-library options and populate the header <select>.
 *
 * initializeMatrices() starts this without awaiting while loadMatrixData() may
 * ask for the same select again a moment later; sharing the in-flight promise
 * stops two clear-then-append cycles from interleaving and listing every
 * option twice.
 */
_loadHeaderListOptions(selectEl, fieldId, lookupListId, displayColumn, allowOther) {
    if (!this._headerListLoads) this._headerListLoads = new WeakMap();
    const inFlight = this._headerListLoads.get(selectEl);
    if (inFlight) return inFlight;

    const load = this._loadHeaderListOptionsNow(
        selectEl, fieldId, lookupListId, displayColumn, allowOther
    ).finally(() => this._headerListLoads.delete(selectEl));

    this._headerListLoads.set(selectEl, load);
    return load;
},

/**
 * Reuses the same matrixSearchOptionsCache as the row-search dropdown.
 */
async _loadHeaderListOptionsNow(selectEl, fieldId, lookupListId, displayColumn, allowOther) {
    const matrix = this.matrices.get(fieldId);
    // Fall back to the server-rendered disabled state rather than assuming
    // editable when the matrix is not registered (read-only forms fail closed).
    const canEdit = matrix?.container
        ? __canEditMatrixContainer(matrix.container)
        : !selectEl.disabled;

    const placeholderOpt = selectEl.querySelector('option[value=""]');
    if (placeholderOpt) placeholderOpt.textContent = _t('Loading...');
    selectEl.dataset.headerState = 'loading';
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
            if (o.value !== '' && o.value !== OTHER_VALUE) o.remove();
        });
        if (placeholderOpt) {
            placeholderOpt.textContent = selectEl.dataset.headerPlaceholder || _t('Select...');
        }

        const otherOpt = selectEl.querySelector(`option[value="${OTHER_VALUE}"]`);
        allOptions.forEach(opt => {
            const el = document.createElement('option');
            el.value = String(opt.value || '');
            el.textContent = String(opt.value || '');
            otherOpt ? selectEl.insertBefore(el, otherOpt) : selectEl.appendChild(el);
        });

        if (allowOther && !selectEl.querySelector(`option[value="${OTHER_VALUE}"]`)) {
            const o = document.createElement('option');
            o.value = OTHER_VALUE;
            o.textContent = _t('Other (please specify)...');
            selectEl.appendChild(o);
        }
        selectEl.dataset.headerState = 'ready';
    } catch (err) {
        debugWarn('matrix-handler', '[SEL-HDR] Failed to load list options:', err);
        selectEl.dataset.headerState = 'error';
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
 * If the saved value isn't in the option list it's treated as Other, or shown
 * as a stored value when the column has no Other option.
 */
_restoreHeaderSelectValue(selectEl, fieldId) {
    const matrix = this.matrices.get(String(fieldId || ''));
    if (!matrix?.data) return;

    const colName = selectEl.dataset.colName;
    if (!colName) return;

    const saved = matrix.data[this._headerDataKey(colName)];
    const savedStr = saved == null ? '' : String(saved).trim();
    if (!savedStr) {
        this._clearHeaderSelectUI(selectEl);
        return;
    }

    const isUnmatched = this._isHeaderGoUnmatched(fieldId, colName);

    if (!Array.from(selectEl.options).some(o => o.value === savedStr)) {
        if (isUnmatched) {
            this._applyGoUnmatchedHeaderOption(selectEl, savedStr);
            this._setHeaderGoUnmatchedUI(selectEl, true);
            return;
        }
        if (this._useOtherHeaderOption(selectEl, savedStr)) {
            this._setHeaderGoUnmatchedUI(selectEl, false);
            return;
        }
        debugWarn(
            'matrix-handler',
            `[SEL-HDR] Saved header "${savedStr}" for ${colName} is not in the option list; showing it as a stored value`
        );
        this._injectStoredHeaderOption(selectEl, savedStr);
        this._setHeaderGoUnmatchedUI(selectEl, false);
        return;
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
            const saved = colName ? matrix.data?.[this._headerDataKey(colName)] : null;

            if (!saved || !String(saved).trim()) {
                // An import can clear a header that previously had a value;
                // leaving the old selection on screen would contradict the
                // (now gated) cells underneath it.
                this._clearHeaderSelectUI(selectEl);
                this._syncHeaderPickerUI(selectEl);
                return;
            }

            const source = selectEl.dataset.headerSource;
            const lookupListId = selectEl.dataset.headerLookupListId;
            const displayColumn = selectEl.dataset.headerListDisplayColumn;
            const hasRealOptions = Array.from(selectEl.options).some(
                o => o.value && o.value !== OTHER_VALUE
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

    if (!menuEl.id) menuEl.id = `matrix-header-picker-menu-${++headerPickerMenuSeq}`;

    const fieldId = selectEl.dataset.fieldId || '';
    const colName = selectEl.dataset.colName || '';
    const isUnmatched = this._isHeaderGoUnmatched(fieldId, colName);
    const placeholder = selectEl.dataset.headerPlaceholder || _t('Select...');
    const selectedOpt = selectEl.options[selectEl.selectedIndex];
    const hasValue = !!selectEl.value;
    const state = selectEl.dataset.headerState;

    labelEl.classList.remove('matrix-header-picker-label--error');
    if (state === 'loading' && !hasValue) {
        labelEl.textContent = _t('Loading...');
        labelEl.classList.add('matrix-header-picker-label--placeholder');
    } else if (state === 'error' && !hasValue) {
        // Without this the failed fetch is indistinguishable from an empty list.
        labelEl.textContent = _t('Error loading options');
        labelEl.classList.add('matrix-header-picker-label--placeholder');
        labelEl.classList.add('matrix-header-picker-label--error');
    } else if (hasValue && selectedOpt) {
        if (isUnmatched && selectEl.value === OTHER_VALUE) {
            const otherText = findHeaderOtherInput(selectEl)?.value?.trim();
            labelEl.textContent = otherText || selectedOpt.textContent;
        } else {
            labelEl.textContent = selectedOpt.textContent;
        }
        labelEl.classList.remove('matrix-header-picker-label--placeholder');
    } else {
        labelEl.textContent = placeholder;
        labelEl.classList.add('matrix-header-picker-label--placeholder');
    }

    this._setHeaderGoUnmatchedUI(selectEl, isUnmatched);

    const isOpen = picker.classList.contains('is-open');
    if (trigger) {
        trigger.disabled = selectEl.disabled;
        trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        trigger.setAttribute('aria-controls', menuEl.id);
    }

    menuEl.replaceChildren();
    Array.from(selectEl.options).forEach((opt, index) => {
        const li = document.createElement('li');
        li.className = 'matrix-header-picker-option';
        li.id = `${menuEl.id}-option-${index}`;
        if (opt.dataset.goUnmatched === 'true') {
            li.classList.add('matrix-header-picker-option--go-unmatched');
            li.title = goUnmatchedTooltip();
        }
        li.setAttribute('role', 'option');
        li.dataset.value = opt.value;
        li.textContent = opt.textContent;
        const isSelected = opt.value === selectEl.value;
        li.setAttribute('aria-selected', isSelected ? 'true' : 'false');
        if (isSelected) li.classList.add('is-selected');
        if (opt.value === '') li.classList.add('is-placeholder');
        menuEl.appendChild(li);
    });

    // Rebuilding the menu drops the previously active <li>; re-point the
    // trigger's aria-activedescendant at the equivalent new node.
    if (isOpen) {
        const previous = Number(picker.dataset.activeIndex ?? -1);
        this._setHeaderPickerActiveIndex(
            picker,
            previous >= 0 ? previous : Math.max(0, selectEl.selectedIndex)
        );
    } else {
        this._clearHeaderPickerActive(picker);
    }
},

/** All rendered option elements of a picker menu, in DOM order. */
_headerPickerOptionEls(picker) {
    return Array.from(picker?.querySelectorAll('.matrix-header-picker-option') || []);
},

/**
 * Move the keyboard "active option" (the listbox equivalent of focus — the
 * options themselves are not focusable, the trigger keeps DOM focus).
 */
_setHeaderPickerActiveIndex(picker, index) {
    const options = this._headerPickerOptionEls(picker);
    if (!options.length) {
        this._clearHeaderPickerActive(picker);
        return;
    }

    const clamped = Math.max(0, Math.min(Number(index) || 0, options.length - 1));
    options.forEach((el, i) => el.classList.toggle('is-active', i === clamped));
    picker.dataset.activeIndex = String(clamped);

    const activeEl = options[clamped];
    picker.querySelector('.matrix-header-picker-trigger')
        ?.setAttribute('aria-activedescendant', activeEl.id);
    if (typeof activeEl.scrollIntoView === 'function') {
        activeEl.scrollIntoView({ block: 'nearest' });
    }
},

_clearHeaderPickerActive(picker) {
    if (!picker) return;
    delete picker.dataset.activeIndex;
    this._headerPickerOptionEls(picker).forEach((el) => el.classList.remove('is-active'));
    picker.querySelector('.matrix-header-picker-trigger')?.removeAttribute('aria-activedescendant');
},

/** Close every open header picker (used before opening another). */
_closeAllHeaderPickers(exceptPicker = null) {
    document.querySelectorAll('.matrix-header-picker.is-open').forEach(picker => {
        if (exceptPicker && picker === exceptPicker) return;
        picker.classList.remove('is-open');
        const menu = picker.querySelector('.matrix-header-picker-menu');
        menu?.classList.add('hidden');
        this._resetHeaderPickerMenu(picker);
        this._clearHeaderPickerActive(picker);
        picker.querySelector('.matrix-header-picker-trigger')
            ?.setAttribute('aria-expanded', 'false');
    });
},

/**
 * Pin an open header menu with position:fixed so it is not clipped by
 * .matrix-table-scroll (overflow-x-auto) or other scroll ancestors.
 * The sizes mirror .matrix-header-picker-menu in forms.css — keep both in sync.
 */
_positionHeaderPickerMenu(picker) {
    const trigger = picker?.querySelector('.matrix-header-picker-trigger');
    const menu = picker?.querySelector('.matrix-header-picker-menu');
    if (!trigger || !menu) return;

    const rect = trigger.getBoundingClientRect();
    const viewportPadding = 8;
    const minWidth = 176; // 11rem
    const maxWidth = 288; // 18rem
    const preferredMaxHeight = 224; // 14rem
    const menuWidth = Math.min(maxWidth, Math.max(minWidth, rect.width));

    let left = rect.left + (rect.width / 2) - (menuWidth / 2);
    left = Math.max(viewportPadding, Math.min(left, window.innerWidth - menuWidth - viewportPadding));

    const spaceBelow = window.innerHeight - rect.bottom - viewportPadding;
    const spaceAbove = rect.top - viewportPadding;
    let top;
    let maxHeight;

    if (spaceBelow < 120 && spaceAbove > spaceBelow) {
        maxHeight = Math.min(preferredMaxHeight, Math.max(80, spaceAbove - 4));
        top = rect.top - maxHeight - 2;
    } else {
        maxHeight = Math.min(preferredMaxHeight, Math.max(80, spaceBelow - 4));
        top = rect.bottom + 2;
    }

    top = Math.max(viewportPadding, top);

    menu.classList.add('matrix-header-picker-menu--floating');
    menu.style.position = 'fixed';
    menu.style.top = `${top}px`;
    menu.style.left = `${left}px`;
    menu.style.width = `${menuWidth}px`;
    menu.style.maxHeight = `${maxHeight}px`;
    menu.style.transform = 'none';
},

/** Clear inline fixed positioning when a header picker closes. */
_resetHeaderPickerMenu(picker) {
    const menu = picker?.querySelector('.matrix-header-picker-menu');
    if (!menu) return;
    menu.classList.remove('matrix-header-picker-menu--floating');
    menu.style.position = '';
    menu.style.top = '';
    menu.style.left = '';
    menu.style.width = '';
    menu.style.maxHeight = '';
    menu.style.transform = '';
},

/** Reposition every open header picker (scroll / resize). */
repositionOpenHeaderPickers() {
    document.querySelectorAll('.matrix-header-picker.is-open').forEach((picker) => {
        this._positionHeaderPickerMenu(picker);
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

    if (willOpen) {
        this._positionHeaderPickerMenu(picker);
        this._setHeaderPickerActiveIndex(picker, Math.max(0, selectEl.selectedIndex));
    } else {
        this._resetHeaderPickerMenu(picker);
        this._clearHeaderPickerActive(picker);
    }
},

/**
 * Keyboard support for the custom header picker. The native <select> is
 * aria-hidden and tabindex="-1", so the trigger is the only tab stop and has
 * to provide the whole listbox interaction.
 */
handleHeaderPickerKeydown(event) {
    const trigger = event.target?.closest?.('.matrix-header-picker-trigger');
    if (!trigger) return;

    const picker = trigger.closest('.matrix-header-picker');
    const selectEl = picker?.querySelector('.matrix-header-select');
    if (!picker || !selectEl || selectEl.disabled) return;

    const key = event.key;
    const isOpen = picker.classList.contains('is-open');

    if (!isOpen) {
        if (key === 'ArrowDown' || key === 'ArrowUp' || key === 'Enter' || key === ' ') {
            event.preventDefault();
            this.handleHeaderPickerToggle(trigger);
        }
        return;
    }

    const options = this._headerPickerOptionEls(picker);
    const active = Number(picker.dataset.activeIndex ?? -1);

    switch (key) {
        case 'ArrowDown':
            event.preventDefault();
            this._setHeaderPickerActiveIndex(picker, active + 1);
            break;
        case 'ArrowUp':
            event.preventDefault();
            this._setHeaderPickerActiveIndex(picker, active - 1);
            break;
        case 'Home':
            event.preventDefault();
            this._setHeaderPickerActiveIndex(picker, 0);
            break;
        case 'End':
            event.preventDefault();
            this._setHeaderPickerActiveIndex(picker, options.length - 1);
            break;
        case 'Enter':
        case ' ':
            event.preventDefault();
            if (options[active]) this.handleHeaderPickerOptionClick(options[active]);
            trigger.focus();
            break;
        case 'Escape':
            event.preventDefault();
            this._closeAllHeaderPickers();
            trigger.focus();
            break;
        case 'Tab':
            this._closeAllHeaderPickers();
            break;
        default:
            break;
    }
},

/** Select an option from the custom header picker menu. */
handleHeaderPickerOptionClick(optionEl) {
    const picker = optionEl?.closest('.matrix-header-picker');
    const selectEl = picker?.querySelector('.matrix-header-select');
    if (!picker || !selectEl) return;

    const value = optionEl.dataset.value ?? '';
    selectEl.value = value;

    this._closeAllHeaderPickers();
    selectEl.dispatchEvent(new Event('change', { bubbles: true }));
    this._syncHeaderPickerUI(selectEl);
},

/**
 * Show / hide the free-text Other input based on the select's current value.
 */
_updateHeaderOtherVisibility(selectEl) {
    const otherInput = findHeaderOtherInput(selectEl);
    if (!otherInput) return;

    if (selectEl.value === OTHER_VALUE) {
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

    const selectedOpt = selectEl.options[selectEl.selectedIndex];
    const keepGoUnmatched = selectedOpt?.dataset?.goUnmatched === 'true';

    this._updateHeaderOtherVisibility(selectEl);
    this._syncHeaderPickerUI(selectEl);

    // "Other" persists whatever the free-text box currently holds — usually
    // nothing, which clears the stored value. Skipping the save here would
    // leave the previous choice persisted behind an empty-looking header.
    const otherInput = selectEl.value === OTHER_VALUE ? findHeaderOtherInput(selectEl) : null;
    const value = selectEl.value === OTHER_VALUE
        ? (otherInput?.value || '').trim()
        : (selectEl.value || '');

    this._saveHeaderValue(fieldId, colName, value, { clearGoUnmatched: !keepGoUnmatched });

    if (otherInput && typeof otherInput.focus === 'function') otherInput.focus();
},

/**
 * Called when a .matrix-header-other-input receives input.
 * Debounced: each save re-serialises the hidden field and re-applies
 * editability to every cell in the column.
 * @param {HTMLInputElement} inputEl
 * @param {{immediate?: boolean}} [options] - immediate on blur/change/submit
 */
handleHeaderOtherInputChange(inputEl, { immediate = false } = {}) {
    const fieldId = String(inputEl.dataset.fieldId || '');
    const colName = inputEl.dataset.colName;
    if (!fieldId || !colName) return;

    if (!this._headerOtherSaveTimers) this._headerOtherSaveTimers = new Map();
    const timers = this._headerOtherSaveTimers;
    const pending = timers.get(inputEl);
    if (pending) clearTimeout(pending);

    const commit = () => {
        timers.delete(inputEl);
        // Typing over an imported value makes it a manual entry, so the
        // "not matched in GO" provenance no longer applies.
        this._saveHeaderValue(fieldId, colName, inputEl.value.trim(), { clearGoUnmatched: true });
        const selectEl = findHeaderSelectForOtherInput(inputEl);
        if (selectEl) this._syncHeaderPickerUI(selectEl);
    };

    if (immediate) {
        timers.delete(inputEl);
        commit();
        return;
    }
    timers.set(inputEl, setTimeout(commit, OTHER_INPUT_SAVE_DELAY_MS));
},

/**
 * Commit any debounced free-text header edit right away. Called before the
 * entry form serialises matrix data so a submit mid-keystroke is not lost.
 */
flushPendingHeaderEdits() {
    const timers = this._headerOtherSaveTimers;
    if (!timers?.size) return;
    Array.from(timers.keys()).forEach((inputEl) => {
        this.handleHeaderOtherInputChange(inputEl, { immediate: true });
    });
},

/**
 * Persist value → matrix.data and sync hidden field.
 * @param {string} fieldId
 * @param {string} colName
 * @param {string} value
 * @param {{clearGoUnmatched?: boolean}} [options] - drop the GO-unmatched flag
 *   when the new value no longer comes from an unmatched Excel import.
 */
_saveHeaderValue(fieldId, colName, value, { clearGoUnmatched = false } = {}) {
    const matrix = this.matrices.get(String(fieldId || ''));
    if (!matrix) return;
    if (!matrix.data || typeof matrix.data !== 'object') matrix.data = {};

    const key = this._headerDataKey(colName);
    const unmatchedKey = this._headerGoUnmatchedDataKey(colName);
    if (value) {
        matrix.data[key] = value;
        if (clearGoUnmatched) delete matrix.data[unmatchedKey];
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

    matrix.container.querySelectorAll('tbody input[data-column]').forEach((input) => {
        if (input.dataset.column !== colName) return;
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
