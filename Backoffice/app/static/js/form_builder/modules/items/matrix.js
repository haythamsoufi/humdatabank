// Matrix item logic extracted from item-modal.js
// Depends on global Utils and standard DOM APIs

import { FALSY_CONFIG_STRINGS, TRUTHY_CONFIG_STRINGS } from '../../../lib/matrix-boolean.js';
import { checkFormulaSyntax, compileCalculation } from '../../../forms/modules/matrix/calculation.js';

/** Same grey as a normal matrix column header (Tailwind bg-gray-100). */
const DEFAULT_MATRIX_GROUP_HEADER_COLOR = '#f3f4f6';
const GROUP_HEADER_COLOR_KEY = 'header_color';
/** Omitted when it matches the automatic contrast for the background. */
const GROUP_HEADER_TEXT_COLOR_KEY = 'header_text_color';
/** Older configs used one flag for headers and cells. Still read, no longer written. */
const GROUP_APPLY_COLOR_KEY = 'apply_color_to_columns';
const GROUP_APPLY_HEADER_COLOR_KEY = 'apply_color_to_headers';
const GROUP_APPLY_CELL_COLOR_KEY = 'apply_color_to_cells';
/**
 * Subgroups are stored in column_groups under "<group>::<subgroup>", and each of
 * their columns carries `group` (outer) and `subgroup` (inner). Keep in sync with
 * the matrix_table.html and export_pdf.html templates.
 */
const SUBGROUP_KEY_SEPARATOR = '::';
// Row totals are saved as "{row}_Total"; "_row_total" is the variable-lookup sentinel.
const RESERVED_COLUMN_CODES = new Set(['total', '_row_total']);

function normalizeMatrixGroupHeaderColor(value) {
    const raw = String(value || '').trim().toLowerCase();
    return /^#[0-9a-f]{6}$/.test(raw) ? raw : '';
}

/** Colour to persist. The default grey is omitted so existing groups stay unchanged. */
function customMatrixGroupHeaderColor(value) {
    const normalized = normalizeMatrixGroupHeaderColor(value);
    return normalized && normalized !== DEFAULT_MATRIX_GROUP_HEADER_COLOR ? normalized : '';
}

function groupColorFlagOn(value) {
    return value === true || value === 'true' || value === 1;
}

/** A specific headers/cells flag wins. The old combined flag still turns both on. */
function savedGroupColorFlag(translations, key) {
    if (!translations || typeof translations !== 'object') return false;
    if (Object.prototype.hasOwnProperty.call(translations, key)) {
        return groupColorFlagOn(translations[key]);
    }
    return groupColorFlagOn(translations[GROUP_APPLY_COLOR_KEY]);
}

/** #rgb or #rrggbb, stored as #rrggbb. Empty when the text is not a colour yet. */
function expandHexColor(value) {
    const raw = String(value || '').trim().toLowerCase();
    if (/^#[0-9a-f]{3}$/.test(raw)) {
        return `#${raw[1]}${raw[1]}${raw[2]}${raw[2]}${raw[3]}${raw[3]}`;
    }
    return normalizeMatrixGroupHeaderColor(raw);
}

function clamp01(value) {
    return Math.min(1, Math.max(0, value));
}

function hexToHsv(hex) {
    const raw = normalizeMatrixGroupHeaderColor(hex) || DEFAULT_MATRIX_GROUP_HEADER_COLOR;
    const r = parseInt(raw.slice(1, 3), 16) / 255;
    const g = parseInt(raw.slice(3, 5), 16) / 255;
    const b = parseInt(raw.slice(5, 7), 16) / 255;
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const delta = max - min;
    let h = 0;
    if (delta !== 0) {
        if (max === r) h = ((g - b) / delta) % 6;
        else if (max === g) h = (b - r) / delta + 2;
        else h = (r - g) / delta + 4;
        h *= 60;
        if (h < 0) h += 360;
    }
    return { h, s: max === 0 ? 0 : delta / max, v: max };
}

function hsvToHex(h, s, v) {
    const hue = ((h % 360) + 360) % 360;
    const c = v * s;
    const x = c * (1 - Math.abs((hue / 60) % 2 - 1));
    const m = v - c;
    let r = 0;
    let g = 0;
    let b = 0;
    if (hue < 60) [r, g, b] = [c, x, 0];
    else if (hue < 120) [r, g, b] = [x, c, 0];
    else if (hue < 180) [r, g, b] = [0, c, x];
    else if (hue < 240) [r, g, b] = [0, x, c];
    else if (hue < 300) [r, g, b] = [x, 0, c];
    else [r, g, b] = [c, 0, x];
    const channel = (n) => Math.round((n + m) * 255).toString(16).padStart(2, '0');
    return `#${channel(r)}${channel(g)}${channel(b)}`;
}

function hexLuminance(value) {
    const raw = normalizeMatrixGroupHeaderColor(value) || DEFAULT_MATRIX_GROUP_HEADER_COLOR;
    const r = parseInt(raw.slice(1, 3), 16);
    const g = parseInt(raw.slice(3, 5), 16);
    const b = parseInt(raw.slice(5, 7), 16);
    return (r * 0.299) + (g * 0.587) + (b * 0.114);
}

/** Dark header fills use white text; light fills use the same grey as other columns. */
function matrixGroupHeaderTextColor(value) {
    return hexLuminance(value) >= 160 ? '#4b5563' : '#ffffff';
}

/**
 * Text colour to persist. Empty when unset or equal to the automatic contrast,
 * so changing the background still updates the text until someone picks a colour.
 */
function customMatrixGroupHeaderTextColor(background, value) {
    const normalized = normalizeMatrixGroupHeaderColor(value);
    if (!normalized || normalized === matrixGroupHeaderTextColor(background)) return '';
    return normalized;
}

const truthyMatrixValues = TRUTHY_CONFIG_STRINGS;
const falsyMatrixValues = FALSY_CONFIG_STRINGS;

const isTruthyMatrixValue = (value) => {
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return value !== 0;
    if (typeof value === 'string') {
        const normalized = value.trim().toLowerCase();
        if (truthyMatrixValues.has(normalized)) return true;
        if (falsyMatrixValues.has(normalized)) return false;
    }
    if (value === null || value === undefined) return false;
    return Boolean(value);
};

const shouldCheckMatrixCheckbox = (configValue, optionValue) => {
    if (Array.isArray(configValue)) {
        return configValue.some(val => String(val) === String(optionValue));
    }
    if (typeof configValue === 'string') {
        const normalized = configValue.trim().toLowerCase();
        if (optionValue !== undefined && optionValue !== null && optionValue !== '') {
            if (String(configValue) === String(optionValue)) {
                return true;
            }
            if (truthyMatrixValues.has(normalized)) return true;
            if (falsyMatrixValues.has(normalized)) return false;
            return false;
        }
        if (truthyMatrixValues.has(normalized)) return true;
        if (falsyMatrixValues.has(normalized)) return false;
    }
    return isTruthyMatrixValue(configValue);
};

export const MatrixItem = {
    /**
     * Sanitize server-provided HTML before inserting into the DOM (delegates to
     * Utils.setSanitizedHtml, which uses SafeDom.sanitizeHtml).
     */
    setSanitizedHtml(container, html) {
        Utils.setSanitizedHtml(container, html);
    },
    setup(modalElement) {
        this.resetState(modalElement);
        this.setupRowModeListeners(modalElement);
        this.initializeDefault(modalElement);
        this.setupEventListeners(modalElement);
        this.setupDisplayOptions(modalElement);
        this.setupListLibrary(modalElement);
        this.showVariableOptionsForAllColumns(modalElement);
        this.setupDragAndDrop(modalElement);
        this.updateConfig(modalElement);
    },

    teardown(modalElement) {
        if (!modalElement) return;
        if (modalElement._matrixChangeHandler) {
            document.removeEventListener('change', modalElement._matrixChangeHandler);
            modalElement._matrixChangeHandler = null;
        }
        if (modalElement._matrixClickHandler) {
            document.removeEventListener('click', modalElement._matrixClickHandler);
            modalElement._matrixClickHandler = null;
        }
        if (modalElement._matrixColumnCodeHandler) {
            document.removeEventListener('input', modalElement._matrixColumnCodeHandler);
            modalElement._matrixColumnCodeHandler = null;
        }
        if (modalElement._matrixColorPointerHandler) {
            document.removeEventListener('pointerdown', modalElement._matrixColorPointerHandler);
            modalElement._matrixColorPointerHandler = null;
        }
        if (modalElement._matrixColorKeyHandler) {
            document.removeEventListener('keydown', modalElement._matrixColorKeyHandler);
            modalElement._matrixColorKeyHandler = null;
        }
        if (modalElement._dndObserver) {
            modalElement._dndObserver.disconnect();
            modalElement._dndObserver = null;
        }
        const container = Utils.getElementById('matrix-columns-container');
        if (container) container._dndInitialized = false;
    },

    resetState(modalElement) {
        if (!modalElement) return;
        this._listConfigVersion = (this._listConfigVersion || 0) + 1;

        const rowsContainer = modalElement.querySelector('#matrix-rows-container');
        const columnsContainer = modalElement.querySelector('#matrix-columns-container');
        const manualSection = modalElement.querySelector('#matrix-manual-rows-section');
        const listLibrarySection = modalElement.querySelector('#matrix-list-library-section');
        const manualModeRadio = modalElement.querySelector('input[name="matrix_row_mode"][value="manual"]');
        const listSelect = modalElement.querySelector('#matrix-list-select');
        const displayColumnWrapper = modalElement.querySelector('#matrix-display-column-wrapper');
        const displayColumnSelect = modalElement.querySelector('#matrix-list-display-column');
        const groupByWrapper = modalElement.querySelector('#matrix-group-by-wrapper');
        const groupBySelect = modalElement.querySelector('#matrix-group-by-column');
        const groupControlsWrapper = modalElement.querySelector('#matrix-group-controls-wrapper');
        const filtersContainer = modalElement.querySelector('#matrix-list-filters-container');
        const filtersInput = modalElement.querySelector('#matrix-list-filters-json');
        const pluginConfigContainer = modalElement.querySelector('#matrix-plugin-config-container');
        const searchPlaceholderInput = modalElement.querySelector('#matrix-search-placeholder');
        const searchPlaceholderTranslationsInput = modalElement.querySelector('#matrix-search-placeholder-translations');
        const rowTotalsCheckbox = modalElement.querySelector('#matrix-show-row-totals');
        const columnTotalsCheckbox = modalElement.querySelector('#matrix-show-column-totals');
        const includeTotalsInApiCheckbox = modalElement.querySelector('#matrix-include-totals-in-api');
        const autoLoadCheckbox = modalElement.querySelector('#matrix-auto-load-entities');
        const highlightManualRowsCheckbox = modalElement.querySelector('#matrix-highlight-manual-rows');
        const legendTextInput = modalElement.querySelector('#matrix-legend-text');
        const legendTextTranslationsInput = modalElement.querySelector('#matrix-legend-text-translations');
        const legendHideInput = modalElement.querySelector('#matrix-legend-hide');

        if (rowsContainer) rowsContainer.replaceChildren();
        if (columnsContainer) columnsContainer.replaceChildren();
        if (manualModeRadio) manualModeRadio.checked = true;
        if (manualSection) Utils.showElement(manualSection);
        if (listLibrarySection) Utils.hideElement(listLibrarySection);
        if (listSelect) listSelect.value = '';
        if (displayColumnWrapper) Utils.hideElement(displayColumnWrapper);
        if (displayColumnSelect) {
            displayColumnSelect.replaceChildren();
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select Column...';
            displayColumnSelect.appendChild(placeholder);
        }
        if (groupByWrapper) Utils.hideElement(groupByWrapper);
        if (groupBySelect) {
            groupBySelect.replaceChildren();
            const noGroup = document.createElement('option');
            noGroup.value = '';
            noGroup.textContent = 'No grouping';
            groupBySelect.appendChild(noGroup);
        }
        if (groupControlsWrapper) groupControlsWrapper.classList.add('hidden');
        if (filtersContainer) filtersContainer.replaceChildren();
        if (filtersInput) filtersInput.value = '[]';
        if (pluginConfigContainer) {
            pluginConfigContainer.replaceChildren();
            pluginConfigContainer.style.display = 'none';
        }
        if (searchPlaceholderInput) searchPlaceholderInput.value = 'Search and select a row to add...';
        if (searchPlaceholderTranslationsInput) searchPlaceholderTranslationsInput.value = '{}';
        if (rowTotalsCheckbox) rowTotalsCheckbox.checked = true;
        if (columnTotalsCheckbox) columnTotalsCheckbox.checked = true;
        if (includeTotalsInApiCheckbox) includeTotalsInApiCheckbox.checked = true;
        const rowTotalManualCheckbox = modalElement.querySelector('#matrix-row-total-manual-enabled');
        const rowTotalValidationSelect = modalElement.querySelector('#matrix-row-total-validation');
        if (rowTotalManualCheckbox) rowTotalManualCheckbox.checked = false;
        if (rowTotalValidationSelect) rowTotalValidationSelect.value = 'none';
        this.updateRowTotalOptionsVisibility(modalElement);
        this.updateIncludeTotalsInApiVisibility(modalElement);
        if (autoLoadCheckbox) autoLoadCheckbox.checked = false;
        const includeOwnRowsCheckbox = modalElement.querySelector('#matrix-include-own-rows');
        const includeOwnRowsWrapper = modalElement.querySelector('#matrix-include-own-rows-wrapper');
        if (includeOwnRowsCheckbox) includeOwnRowsCheckbox.checked = false;
        if (includeOwnRowsWrapper) delete includeOwnRowsWrapper.dataset.pendingSpec;
        this._ownRowsLoadToken = (this._ownRowsLoadToken || 0) + 1;
        this.updateOwnRowsVisibility(modalElement);
        if (highlightManualRowsCheckbox) highlightManualRowsCheckbox.checked = false;
        if (legendTextInput) {
            legendTextInput.value = 'Manually added row';
            legendTextInput.disabled = false;
            legendTextInput.classList.remove('bg-gray-100', 'cursor-not-allowed');
        }
        if (legendTextTranslationsInput) legendTextTranslationsInput.value = '{}';
        if (legendHideInput) legendHideInput.value = 'false';
        const lookupTooltipLabelInput = modalElement.querySelector('#matrix-variable-lookup-tooltip-label');
        const lookupTooltipLabelTranslationsInput = modalElement.querySelector('#matrix-variable-lookup-tooltip-label-translations');
        const submittedTooltipLabelInput = modalElement.querySelector('#matrix-variable-submitted-tooltip-label');
        const submittedTooltipLabelTranslationsInput = modalElement.querySelector('#matrix-variable-submitted-tooltip-label-translations');
        if (lookupTooltipLabelInput) lookupTooltipLabelInput.value = 'Lookup value';
        if (lookupTooltipLabelTranslationsInput) lookupTooltipLabelTranslationsInput.value = '{}';
        if (submittedTooltipLabelInput) submittedTooltipLabelInput.value = 'Submitted value';
        if (submittedTooltipLabelTranslationsInput) submittedTooltipLabelTranslationsInput.value = '{}';
    },

    initializeDefault(modalElement) {
        const rowsContainer = Utils.getElementById('matrix-rows-container');
        const columnsContainer = Utils.getElementById('matrix-columns-container');
        if (!rowsContainer || !columnsContainer) {
            console.error('Matrix containers not found');
            return;
        }
        if (rowsContainer.children.length === 0) {
            this.addRow(modalElement, 'Row 1');
            this.addRow(modalElement, 'Row 2');
        }
        if (columnsContainer.children.length === 0) {
            this.addColumn(modalElement, 'Column 1', 'number_whole');
            this.addColumn(modalElement, 'Column 2', 'number_whole');
        }
        this.syncRowTotalColumn(modalElement);
    },

    showVariableOptionsForAllColumns(modalElement) {
        // Check if template has variables or built-in metadata tokens
        const templateVariables = window.templateVariables || {};
        const metadata = Array.isArray(window.builtInMetadataVariables) ? window.builtInMetadataVariables : [];
        const hasVariables = Object.keys(templateVariables).length > 0 || metadata.length > 0;

        if (!hasVariables) {
            return; // No variables, so don't show options
        }

        // Show variable options for all existing columns
        const columnsContainer = Utils.getElementById('matrix-columns-container');
        if (columnsContainer) {
            columnsContainer.querySelectorAll('.matrix-column').forEach(columnDiv => {
                const variableOptions = columnDiv.querySelector('.column-variable-options');
                if (variableOptions) {
                    variableOptions.style.display = 'flex';
                    variableOptions.classList.remove('hidden');
                }
            });
        }
    },

    setupEventListeners(modalElement) {
        // Remove existing handlers if present
        if (modalElement._matrixChangeHandler) {
            document.removeEventListener('change', modalElement._matrixChangeHandler);
            document.removeEventListener('click', modalElement._matrixClickHandler);
        }
        if (modalElement._matrixColumnCodeHandler) {
            document.removeEventListener('input', modalElement._matrixColumnCodeHandler);
        }
        if (modalElement._matrixColorPointerHandler) {
            document.removeEventListener('pointerdown', modalElement._matrixColorPointerHandler);
        }
        if (modalElement._matrixColorKeyHandler) {
            document.removeEventListener('keydown', modalElement._matrixColorKeyHandler);
        }

        modalElement._matrixChangeHandler = (e) => {
            if (
                e.target.classList.contains('row-text') ||
                e.target.classList.contains('column-text') ||
                e.target.classList.contains('group-label-text') ||
                e.target.classList.contains('group-header-color') ||
                e.target.classList.contains('group-header-text-color') ||
                e.target.classList.contains('group-header-color-hex') ||
                e.target.classList.contains('group-apply-header-color') ||
                e.target.classList.contains('group-apply-cell-color') ||
                e.target.classList.contains('column-type') ||
                e.target.classList.contains('column-decimals') ||
                e.target.classList.contains('column-variable-select') ||
                e.target.classList.contains('column-is-variable') ||
                e.target.classList.contains('column-variable-readonly') ||
                e.target.classList.contains('column-variable-save-value') ||
                e.target.classList.contains('column-selectable-header') ||
                e.target.classList.contains('column-header-source') ||
                e.target.classList.contains('column-header-list-select') ||
                e.target.classList.contains('column-header-list-display-column') ||
                e.target.classList.contains('column-header-placeholder') ||
                e.target.classList.contains('column-header-option-text') ||
                e.target.classList.contains('column-header-allow-other') ||
                e.target.classList.contains('column-include-in-row-total') ||
                e.target.classList.contains('column-calc-operation') ||
                e.target.classList.contains('column-calc-source') ||
                e.target.classList.contains('column-calc-subtrahend') ||
                e.target.classList.contains('column-calc-denominator') ||
                e.target.classList.contains('column-calc-formula') ||
                e.target.classList.contains('column-calc-decimals') ||
                e.target.classList.contains('column-calc-blank-as-zero') ||
                e.target.classList.contains('column-calc-readonly') ||
                e.target.classList.contains('column-calc-save-value')
            ) {
                // Show the "Decimals" input only for columns configured as Number (Decimal)
                if (e.target.classList.contains('column-type')) {
                    const columnDiv = e.target.closest('.matrix-column');
                    this.updateColumnDecimalsVisibility(columnDiv);
                    this.updateColumnCalculationVisibility(columnDiv);
                }
                if (e.target.classList.contains('column-text')) {
                    const cleaned = e.target.value.replace(/\s+/g, '');
                    if (cleaned !== e.target.value) e.target.value = cleaned;
                    this._renameCalculationSource(modalElement, e.target);
                }
                if (e.target.classList.contains('column-include-in-row-total')) {
                    const columnDiv = e.target.closest('.matrix-column');
                    if (columnDiv) columnDiv.dataset.includeTouched = '1';
                }
                if (e.target.classList.contains('column-calc-decimals')) {
                    const columnDiv = e.target.closest('.matrix-column');
                    if (columnDiv) columnDiv.dataset.decimalsTouched = '1';
                }
                if (e.target.classList.contains('column-calc-operation')) {
                    const columnDiv = e.target.closest('.matrix-column');
                    this._applyCalculationOperationDefaults(columnDiv);
                    this._syncCalculationPanel(columnDiv);
                }
                // Handle "Is Variable" checkbox change to show/hide variable selector and save/readonly options
                if (e.target.classList.contains('column-is-variable')) {
                    const columnDiv = e.target.closest('.matrix-column');
                    if (columnDiv) {
                        const variableSelect = columnDiv.querySelector('.column-variable-select');
                        const saveValueLabel = columnDiv.querySelector('.column-variable-save-value-label');
                        const readonlyLabel = columnDiv.querySelector('.column-variable-readonly-label');

                        if (e.target.checked) {
                            if (variableSelect) {
                                variableSelect.style.display = '';
                                variableSelect.classList.remove('hidden');
                                // Populate variable options if not already populated
                                if (variableSelect.options.length <= 1) {
                                    this.populateVariableOptions(variableSelect, modalElement);
                                }
                            }
                            // Show save value and readonly checkboxes
                            if (saveValueLabel) {
                                saveValueLabel.style.display = 'flex';
                            }
                            if (readonlyLabel) {
                                readonlyLabel.style.display = 'flex';
                            }
                            this.updateColumnVariableSaveValueState(columnDiv);
                        } else {
                            if (variableSelect) {
                                variableSelect.style.display = 'none';
                                variableSelect.classList.add('hidden');
                            }
                            // Hide save value and readonly checkboxes
                            if (saveValueLabel) {
                                saveValueLabel.style.display = 'none';
                            }
                            if (readonlyLabel) {
                                readonlyLabel.style.display = 'none';
                            }
                        }
                    }
                }
                // Update auto-load visibility when column variable status changes
                if (e.target.classList.contains('column-is-variable')) {
                    this.updateAutoLoadVisibility(modalElement);
                }
                if (e.target.classList.contains('column-variable-readonly')) {
                    const columnDiv = e.target.closest('.matrix-column');
                    if (columnDiv) {
                        this.updateColumnVariableSaveValueState(columnDiv);
                    }
                }
                // ── Selectable header controls ──────────────────────────────
                if (e.target.classList.contains('column-selectable-header')) {
                    const columnDiv = e.target.closest('.matrix-column');
                    if (columnDiv) {
                        if (e.target.checked) {
                            this._setColumnSelectableHeaderExpanded(columnDiv, true);
                            const source = columnDiv.querySelector('.column-header-source:checked')?.value || 'manual';
                            if (source === 'manual') this._ensureColumnHeaderOptionRow(columnDiv);
                        } else {
                            this._setColumnSelectableHeaderExpanded(columnDiv, false);
                        }
                    }
                }
                if (e.target.classList.contains('column-header-source')) {
                    const columnDiv = e.target.closest('.matrix-column');
                    const manualSec = columnDiv?.querySelector('.column-header-manual-section');
                    const listSec = columnDiv?.querySelector('.column-header-list-library-section');
                    const isLib = e.target.value === 'list_library';
                    manualSec?.classList.toggle('hidden', isLib);
                    listSec?.classList.toggle('hidden', !isLib);
                    if (!isLib && columnDiv) this._ensureColumnHeaderOptionRow(columnDiv);
                }
                if (e.target.classList.contains('column-header-list-select')) {
                    const columnDiv = e.target.closest('.matrix-column');
                    if (columnDiv) {
                        this.handleColumnHeaderListSelection(modalElement, columnDiv, e.target.value);
                    }
                }
                if (e.target.classList.contains('group-header-color') || e.target.classList.contains('group-header-text-color')) {
                    this._paintGroupHeader(e.target.closest('.matrix-group'));
                }
                if (e.target.classList.contains('group-header-color-hex')) {
                    this._commitGroupHexInput(e.target, { restoreInvalid: true });
                }
                this.updateConfig(modalElement);
            }
        };

        modalElement._matrixClickHandler = (e) => {
            const inColorPanel = !!e.target.closest?.('.group-color-panel');
            const colorToggle = e.target.closest?.('.group-color-toggle');
            const inCalcPicker = !!e.target.closest?.('.calc-column-picker-menu');
            const calcPickerToggle = e.target.closest?.('.calc-column-picker-toggle');
            if (!inCalcPicker) {
                modalElement.querySelectorAll('.calc-column-picker-menu:not(.hidden)').forEach(menu => {
                    if (calcPickerToggle && menu.parentElement?.contains(calcPickerToggle)) return;
                    menu.classList.add('hidden');
                    menu.parentElement?.querySelector('.calc-column-picker-toggle')?.setAttribute('aria-expanded', 'false');
                });
            }
            if (!inColorPanel) {
                modalElement.querySelectorAll('.group-color-panel:not(.hidden)').forEach(panel => {
                    if (colorToggle && panel.parentElement?.contains(colorToggle)) return;
                    panel.classList.add('hidden');
                    panel.parentElement?.querySelector('.group-color-toggle')?.setAttribute('aria-expanded', 'false');
                });
            }
            if (colorToggle && modalElement.contains(colorToggle)) {
                e.preventDefault();
                const panel = colorToggle.parentElement?.querySelector('.group-color-panel');
                if (!panel) return;
                const willOpen = panel.classList.contains('hidden');
                panel.classList.toggle('hidden', !willOpen);
                colorToggle.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
                if (willOpen) {
                    const groupEl = colorToggle.closest('.matrix-group');
                    this._syncGroupColorPanel(groupEl);
                    this._positionGroupColorPanel(panel, colorToggle);
                    const hex = panel.querySelector('.group-header-color-hex');
                    hex?.focus();
                    hex?.select();
                }
                return;
            }
            const colorTab = e.target.closest?.('.group-color-tab');
            if (colorTab && modalElement.contains(colorTab)) {
                e.preventDefault();
                const panel = colorTab.closest('.group-color-panel');
                const groupEl = colorTab.closest('.matrix-group');
                if (!panel || !groupEl) return;
                const nextTarget = colorTab.dataset.colorTarget === 'text' ? 'text' : 'background';
                panel.dataset.colorTarget = nextTarget;
                panel.querySelectorAll('.group-color-tab').forEach(tab => {
                    const selected = tab === colorTab;
                    tab.classList.toggle('is-active', selected);
                    tab.setAttribute('aria-selected', selected ? 'true' : 'false');
                });
                this._syncGroupColorPanel(groupEl);
                const hex = panel.querySelector('.group-header-color-hex');
                hex?.focus();
                hex?.select();
                return;
            }

            const target = e.target.closest('button');
            if (!target) return;


            if (target.id === 'add-matrix-row-btn') {
                e.preventDefault();
                this.addRow(modalElement);
                this.updateConfig(modalElement);
            } else if (target.classList.contains('remove-row-btn')) {
                e.preventDefault();
                this.removeRow(target);
                this.updateConfig(modalElement);
            } else if (target.classList.contains('move-row-up-btn')) {
                e.preventDefault();
                this.moveRow(target, 'up');
                this.updateConfig(modalElement);
            } else if (target.classList.contains('move-row-down-btn')) {
                e.preventDefault();
                this.moveRow(target, 'down');
                this.updateConfig(modalElement);
            } else if (target.id === 'add-matrix-column-btn') {
                e.preventDefault();
                this.addColumn(modalElement);
                this.updateConfig(modalElement);
            } else if (target.id === 'add-matrix-group-btn') {
                e.preventDefault();
                this.addGroup(modalElement);
                this.updateConfig(modalElement);
            } else if (target.classList.contains('matrix-group-toggle-btn')) {
                e.preventDefault();
                const groupDiv = target.closest('.matrix-group');
                if (groupDiv) {
                    this._setGroupCollapsed(groupDiv, !groupDiv.classList.contains('is-collapsed'));
                }
            } else if (target.classList.contains('add-column-to-group-btn')) {
                e.preventDefault();
                const groupDiv = target.closest('.matrix-group');
                if (groupDiv) {
                    this._setGroupCollapsed(groupDiv, false);
                    const groupColumnsContainer = groupDiv.querySelector(':scope > .matrix-group-columns');
                    this.addColumn(modalElement, '', 'number_whole', false, '', true, true, {}, groupColumnsContainer);
                    this.updateConfig(modalElement);
                }
            } else if (target.classList.contains('add-subgroup-to-group-btn')) {
                e.preventDefault();
                const groupDiv = target.closest('.matrix-group');
                // Only top-level groups can hold a subgroup.
                if (groupDiv && groupDiv.parentElement?.id === 'matrix-columns-container') {
                    this._setGroupCollapsed(groupDiv, false);
                    const groupColumnsContainer = groupDiv.querySelector(':scope > .matrix-group-columns');
                    this.addGroup(modalElement, '', {}, '', groupColumnsContainer);
                    this.updateConfig(modalElement);
                }
            } else if (target.classList.contains('duplicate-group-btn')) {
                e.preventDefault();
                const groupDiv = target.closest('.matrix-group');
                if (groupDiv) {
                    const copy = this.duplicateGroup(modalElement, groupDiv);
                    copy?.querySelector(':scope > .matrix-group-header .group-label-text')?.focus();
                    this.updateConfig(modalElement);
                }
            } else if (target.classList.contains('remove-group-btn')) {
                e.preventDefault();
                const groupDiv = target.closest('.matrix-group');
                if (groupDiv) groupDiv.remove();
                this.updateAutoLoadVisibility(modalElement);
                this.updateConfig(modalElement);
            } else if (target.classList.contains('remove-column-btn')) {
                e.preventDefault();
                this.removeColumn(target);
                this.updateConfig(modalElement);
            } else if (target.classList.contains('column-header-option-add-btn')) {
                e.preventDefault();
                const optionsList = target.closest('.column-header-option-row')?.parentElement;
                const newRow = this.addColumnHeaderOption(optionsList);
                newRow?.querySelector('.column-header-option-text')?.focus();
                this.updateConfig(modalElement);
            } else if (target.classList.contains('column-header-option-remove-btn')) {
                e.preventDefault();
                target.closest('.column-header-option-row')?.remove();
                this.updateConfig(modalElement);
            } else if (target.classList.contains('column-header-option-move-up-btn')) {
                e.preventDefault();
                const optionRow = target.closest('.column-header-option-row');
                const prev = optionRow?.previousElementSibling;
                if (prev) prev.before(optionRow);
                this.updateConfig(modalElement);
            } else if (target.classList.contains('column-header-option-move-down-btn')) {
                e.preventDefault();
                const optionRow = target.closest('.column-header-option-row');
                const next = optionRow?.nextElementSibling;
                if (next) next.after(optionRow);
                this.updateConfig(modalElement);
            } else if (target.classList.contains('calc-column-picker-toggle')) {
                e.preventDefault();
                const picker = target.closest('.calc-column-picker');
                const menu = picker?.querySelector('.calc-column-picker-menu');
                if (!menu || target.disabled) return;
                const willOpen = menu.classList.contains('hidden');
                menu.classList.toggle('hidden', !willOpen);
                target.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
            } else if (target.classList.contains('calc-column-picker-select-all') || target.classList.contains('calc-column-picker-clear')) {
                e.preventDefault();
                const menu = target.closest('.calc-column-picker-menu');
                const selectAll = target.classList.contains('calc-column-picker-select-all');
                menu?.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
                    checkbox.checked = selectAll;
                });
                this._syncCalculationPickerSummary(target.closest('.calc-column-picker'));
                this.updateConfig(modalElement);
            } else if (target.classList.contains('column-calc-bold')) {
                e.preventDefault();
                const columnDiv = target.closest('.matrix-column');
                const on = target.getAttribute('aria-pressed') === 'false';
                target.classList.toggle('is-on', on);
                target.setAttribute('aria-pressed', on ? 'true' : 'false');
                this.updateColumnCalculationVisibility(columnDiv);
                this.updateConfig(modalElement);
            } else if (target.classList.contains('column-selectable-header-toggle')) {
                e.preventDefault();
                const columnDiv = target.closest('.matrix-column');
                const checkbox = columnDiv?.querySelector('.column-selectable-header');
                if (!columnDiv || !checkbox?.checked) return;
                const wrapper = columnDiv.querySelector('.column-selectable-header-wrapper');
                const isExpanded = wrapper?.classList.contains('is-expanded');
                this._setColumnSelectableHeaderExpanded(columnDiv, !isExpanded);
            }
        };

        document.addEventListener('change', modalElement._matrixChangeHandler);
        modalElement._matrixColumnCodeHandler = (e) => {
            if (!modalElement.contains(e.target)) return;
            if (e.target.classList?.contains('group-header-color') || e.target.classList?.contains('group-header-text-color')) {
                this._paintGroupHeader(e.target.closest('.matrix-group'));
                this.updateConfig(modalElement);
                return;
            }
            if (e.target.classList?.contains('group-header-color-hex')) {
                this._commitGroupHexInput(e.target, { restoreInvalid: false });
                return;
            }
            if (e.target.classList?.contains('group-color-hue')) {
                this._commitGroupColorFromControls(e.target.closest('.matrix-group'));
                return;
            }
            if (!e.target.classList?.contains('column-text')) return;
            const cleaned = e.target.value.replace(/\s+/g, '');
            if (cleaned === e.target.value) return;
            const pos = e.target.selectionStart;
            e.target.value = cleaned;
            if (pos != null) {
                const next = Math.max(0, pos - 1);
                e.target.setSelectionRange(next, next);
            }
        };
        document.addEventListener('input', modalElement._matrixColumnCodeHandler);
        document.addEventListener('click', modalElement._matrixClickHandler);
        modalElement._matrixColorPointerHandler = (e) => {
            const sv = e.target.closest?.('.group-color-sv');
            if (!sv || !modalElement.contains(sv)) return;
            e.preventDefault();
            const move = (ev) => {
                if (ev.pointerId !== e.pointerId) return;
                this._setGroupColorFromSv(sv, ev);
            };
            const up = (ev) => {
                if (ev.pointerId !== e.pointerId) return;
                sv.removeEventListener('pointermove', move);
                sv.removeEventListener('pointerup', up);
                sv.removeEventListener('pointercancel', up);
            };
            sv.addEventListener('pointermove', move);
            sv.addEventListener('pointerup', up);
            sv.addEventListener('pointercancel', up);
            sv.setPointerCapture?.(e.pointerId);
            this._setGroupColorFromSv(sv, e);
        };
        modalElement._matrixColorKeyHandler = (e) => {
            if (e.key !== 'Escape') return;
            const open = modalElement.querySelectorAll('.group-color-panel:not(.hidden), .calc-column-picker-menu:not(.hidden)');
            if (!open.length) return;
            open.forEach(panel => {
                panel.classList.add('hidden');
                const toggle = panel.parentElement?.querySelector('.group-color-toggle, .calc-column-picker-toggle');
                toggle?.setAttribute('aria-expanded', 'false');
            });
        };
        document.addEventListener('pointerdown', modalElement._matrixColorPointerHandler);
        document.addEventListener('keydown', modalElement._matrixColorKeyHandler);
    },

    addRow(modalElement, text = '', nameTranslations = {}) {
        const rowsContainer = Utils.getElementById('matrix-rows-container');
        const template = Utils.getElementById('matrix-row-template');
        if (!rowsContainer || !template) {
            console.error('Matrix row container or template not found');
            return;
        }
        const clone = template.content.cloneNode(true);
        const input = clone.querySelector('.row-text');
        if (input) input.value = text || '';
        const translationsInput = clone.querySelector('.row-name-translations');
        if (translationsInput) {
            try {
                const normalized = (nameTranslations && typeof nameTranslations === 'object') ? nameTranslations : {};
                translationsInput.value = JSON.stringify(normalized);
            } catch (_) {
                translationsInput.value = '{}';
            }
        }
        rowsContainer.appendChild(clone);
    },

    /**
     * Add one manual "selectable header" option row (text input + move/remove/add
     * buttons) to a column's options list. Mirrors the single/multi choice question
     * options UI, but scoped per-column since each matrix column keeps its own
     * independent option list.
     */
    addColumnHeaderOption(optionsList, text = '') {
        const template = Utils.getElementById('matrix-column-header-option-template');
        if (!optionsList || !template) return null;
        const clone = template.content.cloneNode(true);
        const input = clone.querySelector('.column-header-option-text');
        if (input) input.value = text || '';
        optionsList.appendChild(clone);
        return optionsList.lastElementChild;
    },

    /**
     * Ensure a column's manual header-options list always has at least one row
     * once the manual source becomes visible, so there's always an "Add" button
     * to grow the list from (matching the question options UX).
     */
    _ensureColumnHeaderOptionRow(columnDiv) {
        const optionsList = columnDiv?.querySelector('.column-header-manual-options-list');
        if (!optionsList) return;
        if (!optionsList.querySelector('.column-header-option-row')) {
            this.addColumnHeaderOption(optionsList);
        }
    },

    /**
     * Expand or collapse a column's selectable-header config panel.
     * Collapsed by default; checking "Selectable header" expands it immediately.
     */
    _setColumnSelectableHeaderExpanded(columnDiv, expanded) {
        const wrapper = columnDiv?.querySelector('.column-selectable-header-wrapper');
        const opts = columnDiv?.querySelector('.column-selectable-header-options');
        const toggle = columnDiv?.querySelector('.column-selectable-header-toggle');
        const checkbox = columnDiv?.querySelector('.column-selectable-header');
        if (!wrapper || !opts) return;

        const isEnabled = !!checkbox?.checked;
        const show = expanded && isEnabled;

        wrapper.classList.toggle('is-expanded', show);
        opts.classList.toggle('hidden', !show);
        if (toggle) {
            toggle.disabled = !isEnabled;
            toggle.setAttribute('aria-expanded', show ? 'true' : 'false');
        }
    },

    /**
     * Show the "Decimals" input only when the column is configured as Number (Decimal).
     */
    updateColumnDecimalsVisibility(columnDiv) {
        if (!columnDiv) return;
        const typeSelect = columnDiv.querySelector('.column-type');
        const decimalsLabel = columnDiv.querySelector('.column-decimals-label');
        if (!decimalsLabel) return;
        decimalsLabel.style.display = (typeSelect?.value === 'number_decimal') ? 'flex' : 'none';
    },

    /**
     * Read-only variable columns cannot persist a user-edited value; disable Save value when checked.
     */
    updateColumnVariableSaveValueState(columnDiv) {
        if (!columnDiv) return;
        const saveValueLabel = columnDiv.querySelector('.column-variable-save-value-label');
        const saveValueCheckbox = columnDiv.querySelector('.column-variable-save-value');
        const readonlyCheckbox = columnDiv.querySelector('.column-variable-readonly');
        if (!saveValueCheckbox || !readonlyCheckbox) return;

        const isReadonly = readonlyCheckbox.checked;
        saveValueCheckbox.disabled = isReadonly;
        if (saveValueLabel) {
            saveValueLabel.classList.toggle('opacity-50', isReadonly);
            saveValueLabel.classList.toggle('cursor-not-allowed', isReadonly);
            saveValueLabel.classList.toggle('pointer-events-none', isReadonly);
        }
        if (isReadonly) {
            saveValueCheckbox.checked = false;
        }
    },

    /**
     * Normalize a stored/legacy column type to one of the explicit dropdown values.
     * Legacy configs (and the old 'variable' type marker, now represented via is_variable)
     * stored a generic 'number' type with no decimal-place limit; those default to Whole
     * in the UI. Saving the item persists the explicit type going forward.
     */
    _normalizeColumnTypeForUi(type) {
        if (type === 'tick') return 'tick';
        if (type === 'number_decimal') return 'number_decimal';
        if (type === 'calculated') return 'calculated';
        return 'number_whole';
    },

    /** The B control defaults to on. Only an explicit off turns bold off. */
    _calculationBoldOn(columnDiv) {
        const button = columnDiv?.querySelector('.column-calc-bold');
        if (!button) return true;
        return button.getAttribute('aria-pressed') !== 'false';
    },

    updateColumnCalculationVisibility(columnDiv) {
        if (!columnDiv) return;
        const type = columnDiv.querySelector('.column-type')?.value;
        const isCalculated = type === 'calculated';
        const panel = columnDiv.querySelector('.column-calculation-panel');
        const selectable = columnDiv.querySelector('.column-selectable-header-wrapper');
        const variableOptions = columnDiv.querySelector('.column-variable-options');
        const includeCheckbox = columnDiv.querySelector('.column-include-in-row-total');
        panel?.classList.toggle('hidden', !isCalculated);
        selectable?.classList.toggle('hidden', isCalculated);
        if (isCalculated) {
            if (variableOptions) variableOptions.style.display = 'none';
            const isVariableCheckbox = columnDiv.querySelector('.column-is-variable');
            if (isVariableCheckbox) isVariableCheckbox.checked = false;
            const variableSelect = columnDiv.querySelector('.column-variable-select');
            if (variableSelect) variableSelect.style.display = 'none';
            if (includeCheckbox && !columnDiv.dataset.includeTouched) includeCheckbox.checked = false;
            this._syncCalculationPanel(columnDiv);
        } else if (variableOptions) {
            const templateVariables = window.templateVariables || {};
            const metadata = Array.isArray(window.builtInMetadataVariables) ? window.builtInMetadataVariables : [];
            const hasVariables = Object.keys(templateVariables).length > 0 || metadata.length > 0;
            variableOptions.style.display = hasVariables ? 'flex' : 'none';
            if (includeCheckbox && !columnDiv.dataset.includeTouched) includeCheckbox.checked = true;
        }
    },

    _applyCalculationOperationDefaults(columnDiv) {
        if (!columnDiv || columnDiv.dataset.decimalsTouched) return;
        const operation = columnDiv.querySelector('.column-calc-operation')?.value || 'sum';
        const decimals = columnDiv.querySelector('.column-calc-decimals');
        if (!decimals) return;
        decimals.value = ['average', 'difference', 'percentage', 'product', 'formula'].includes(operation) ? '2' : '0';
    },

    _syncCalculationPanel(columnDiv) {
        if (!columnDiv) return;
        const operation = columnDiv.querySelector('.column-calc-operation')?.value || 'sum';
        columnDiv.querySelector('.column-calc-sources')?.classList.toggle('hidden', operation === 'formula');
        columnDiv.querySelector('.column-calc-subtrahends')?.classList.toggle('hidden', operation !== 'difference');
        columnDiv.querySelector('.column-calc-denominators')?.classList.toggle('hidden', operation !== 'percentage');
        columnDiv.querySelector('.column-calc-formula-wrap')?.classList.toggle('hidden', operation !== 'formula');
        const sourcesLabel = columnDiv.querySelector('.column-calc-sources-label');
        if (sourcesLabel) {
            if (operation === 'percentage') sourcesLabel.textContent = sourcesLabel.dataset.labelNumerator || 'Numerator';
            else if (operation === 'difference') sourcesLabel.textContent = sourcesLabel.dataset.labelAdd || 'Columns to add';
            else sourcesLabel.textContent = sourcesLabel.dataset.labelColumns || 'Columns';
        }
    },

    _renameCalculationSource(modalElement, input) {
        if (!modalElement || !input) return;
        const previous = input.dataset.prevName || '';
        const next = input.value.trim();
        if (previous && next && previous !== next) {
            modalElement.querySelectorAll('.column-calc-source, .column-calc-subtrahend, .column-calc-denominator').forEach((checkbox) => {
                if (checkbox.value === previous) checkbox.value = next;
            });
        }
        input.dataset.prevName = next;
    },

    _checkedCalculationNames(columnDiv, datasetKey, selector, availableNames) {
        const checked = new Set(
            Array.from(columnDiv.querySelectorAll(selector))
                .filter((checkbox) => checkbox.checked)
                .map((checkbox) => checkbox.value)
        );
        if (!columnDiv.dataset[datasetKey]) return checked;
        let saved = [];
        try {
            const parsed = JSON.parse(columnDiv.dataset[datasetKey]);
            saved = Array.isArray(parsed) ? parsed : [];
        } catch (_error) {
            saved = [];
        }
        const available = new Set(availableNames || []);
        const pending = [];
        saved.forEach((name) => {
            if (available.has(name)) checked.add(name);
            else pending.push(name);
        });
        if (pending.length) columnDiv.dataset[datasetKey] = JSON.stringify(pending);
        else delete columnDiv.dataset[datasetKey];
        return checked;
    },

    _pickerText(list, key, fallback) {
        const panel = list?.closest('.column-calculation-panel');
        const value = panel?.dataset?.[key];
        return value || fallback;
    },

    _syncCalculationPickerSummary(picker) {
        if (!picker) return;
        const boxes = Array.from(picker.querySelectorAll('input[type="checkbox"]'));
        const selected = boxes.filter((checkbox) => checkbox.checked).map((checkbox) => checkbox.value);
        const summary = picker.querySelector('.calc-column-picker-summary');
        const toggle = picker.querySelector('.calc-column-picker-toggle');
        const selectAll = picker.querySelector('.calc-column-picker-select-all');
        const clear = picker.querySelector('.calc-column-picker-clear');
        if (!summary) return;
        let text;
        let placeholder = false;
        if (!boxes.length) {
            text = this._pickerText(picker, 'pickerNone', 'No other columns');
            placeholder = true;
        } else if (!selected.length) {
            text = this._pickerText(picker, 'pickerSelect', 'Select columns');
            placeholder = true;
        } else if (selected.length === boxes.length) {
            text = this._pickerText(picker, 'pickerAll', 'All columns');
        } else {
            text = this._pickerText(picker, 'pickerNSelected', '%(count)s selected')
                .replace('%(count)s', String(selected.length));
        }
        summary.textContent = text;
        summary.classList.toggle('is-placeholder', placeholder);
        if (toggle) toggle.title = selected.join(', ');
        if (selectAll) selectAll.disabled = !boxes.length || selected.length === boxes.length;
        if (clear) clear.disabled = !selected.length;
    },

    _renderCalculationColumnPicker(list, inputClass, optionNames, checked, open) {
        list.classList.add('calc-column-picker');
        list.replaceChildren();

        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'calc-column-picker-toggle';
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        toggle.setAttribute('aria-haspopup', 'listbox');
        toggle.disabled = optionNames.length === 0;
        const summary = document.createElement('span');
        summary.className = 'calc-column-picker-summary';
        const chevron = document.createElement('i');
        chevron.className = 'fas fa-chevron-down calc-column-picker-chevron';
        chevron.setAttribute('aria-hidden', 'true');
        toggle.append(summary, chevron);

        const menu = document.createElement('div');
        menu.className = `calc-column-picker-menu${open ? '' : ' hidden'}`;
        menu.setAttribute('role', 'listbox');
        const actions = document.createElement('div');
        actions.className = 'calc-column-picker-actions';
        const selectAll = document.createElement('button');
        selectAll.type = 'button';
        selectAll.className = 'calc-column-picker-select-all';
        selectAll.textContent = this._pickerText(list, 'pickerSelectAll', 'Select all');
        const clear = document.createElement('button');
        clear.type = 'button';
        clear.className = 'calc-column-picker-clear';
        clear.textContent = this._pickerText(list, 'pickerDeselectAll', 'Deselect all');
        actions.append(selectAll, clear);

        const options = document.createElement('div');
        options.className = 'calc-column-picker-options';
        optionNames.forEach((name) => {
            const label = document.createElement('label');
            label.className = 'calc-column-picker-option';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = inputClass;
            checkbox.value = name;
            checkbox.checked = checked.has(name);
            const caption = document.createElement('span');
            caption.textContent = name;
            label.append(checkbox, caption);
            options.appendChild(label);
        });
        menu.append(actions, options);
        list.append(toggle, menu);
        this._syncCalculationPickerSummary(list);
    },

    refreshCalculationSourceLists(modalElement) {
        if (!modalElement) return;
        const columns = Array.from(modalElement.querySelectorAll('.matrix-column'));
        const names = columns
            .map((columnDiv) => columnDiv.querySelector('.column-text')?.value?.trim() || '')
            .filter(Boolean);
        columns.forEach((columnDiv) => {
            if (columnDiv.querySelector('.column-type')?.value !== 'calculated') return;
            const selfName = columnDiv.querySelector('.column-text')?.value?.trim() || '';
            const lists = [
                ['calcSources', '.column-calc-source-list', 'column-calc-source'],
                ['calcSubtrahends', '.column-calc-subtrahend-list', 'column-calc-subtrahend'],
                ['calcDenominators', '.column-calc-denominator-list', 'column-calc-denominator'],
            ];
            lists.forEach(([datasetKey, listSelector, inputClass]) => {
                const list = columnDiv.querySelector(listSelector);
                if (!list) return;
                const optionNames = names.filter((name) => name !== selfName);
                const checked = this._checkedCalculationNames(columnDiv, datasetKey, `.${inputClass}`, names);
                const existing = Array.from(list.querySelectorAll(`.${inputClass}`)).map((checkbox) => checkbox.value);
                const sameOptions = existing.length === optionNames.length
                    && existing.every((name, index) => name === optionNames[index]);
                if (sameOptions && list.querySelector('.calc-column-picker-toggle')) {
                    list.querySelectorAll(`.${inputClass}`).forEach((checkbox) => {
                        checkbox.checked = checked.has(checkbox.value);
                    });
                    this._syncCalculationPickerSummary(list);
                    return;
                }
                const menu = list.querySelector('.calc-column-picker-menu');
                const wasOpen = !!(menu && !menu.classList.contains('hidden'));
                this._renderCalculationColumnPicker(list, inputClass, optionNames, checked, wasOpen);
            });
            this._updateCalculationStatus(columnDiv, names.filter((name) => name !== selfName));
        });
    },

    _readCalculation(columnDiv) {
        const operation = columnDiv.querySelector('.column-calc-operation')?.value || 'sum';
        const selected = (selector) => Array.from(columnDiv.querySelectorAll(selector))
            .filter((checkbox) => checkbox.checked)
            .map((checkbox) => checkbox.value);
        const parsedDecimals = parseInt(columnDiv.querySelector('.column-calc-decimals')?.value, 10);
        const calculation = {
            operation,
            sources: selected('.column-calc-source'),
            subtrahends: selected('.column-calc-subtrahend'),
            denominators: selected('.column-calc-denominator'),
            decimals: Number.isFinite(parsedDecimals) ? Math.min(6, Math.max(0, parsedDecimals)) : 0,
            blank_as_zero: !!columnDiv.querySelector('.column-calc-blank-as-zero')?.checked,
            formula: columnDiv.querySelector('.column-calc-formula')?.value?.trim() || '',
        };
        if (operation !== 'formula') calculation.formula = compileCalculation(calculation);
        return calculation;
    },

    _updateCalculationStatus(columnDiv, knownNames) {
        const status = columnDiv.querySelector('.column-calc-status');
        if (!status) return;
        const calculation = this._readCalculation(columnDiv);
        const formula = calculation.formula || '';
        const emptyMessage = status.dataset.emptyMessage || 'Choose columns or enter a formula';
        const error = formula ? checkFormulaSyntax(formula, knownNames) : emptyMessage;
        status.textContent = error || formula;
        status.classList.toggle('text-red-600', !!error);
        status.classList.toggle('text-gray-500', !error);
    },

    _applyCalculationConfig(columnDiv, calculation, includeInRowTotal, calculationOptions = null) {
        if (!columnDiv) return;
        const type = columnDiv.querySelector('.column-type')?.value;
        const includeCheckbox = columnDiv.querySelector('.column-include-in-row-total');
        const isCalculated = type === 'calculated';
        const defaultInclude = !isCalculated;
        const include = includeInRowTotal === undefined || includeInRowTotal === null
            ? defaultInclude
            : includeInRowTotal !== false && includeInRowTotal !== 'false';
        if (includeCheckbox) {
            includeCheckbox.checked = !!include;
            if (!!include !== defaultInclude) columnDiv.dataset.includeTouched = '1';
        }
        const calcReadonly = columnDiv.querySelector('.column-calc-readonly');
        const calcSaveValue = columnDiv.querySelector('.column-calc-save-value');
        const boldButton = columnDiv.querySelector('.column-calc-bold');
        const readonlyFlag = calculationOptions ? calculationOptions.readonly : undefined;
        const saveFlag = calculationOptions ? calculationOptions.saveValue : undefined;
        const boldFlag = calculationOptions ? calculationOptions.bold : undefined;
        if (boldButton) {
            const boldOn = boldFlag === undefined || boldFlag === null
                ? true
                : boldFlag !== false && boldFlag !== 'false';
            boldButton.classList.toggle('is-on', boldOn);
            boldButton.setAttribute('aria-pressed', boldOn ? 'true' : 'false');
        }
        if (calcReadonly) {
            calcReadonly.checked = readonlyFlag === undefined || readonlyFlag === null
                ? true
                : readonlyFlag !== false && readonlyFlag !== 'false';
        }
        if (calcSaveValue) {
            calcSaveValue.checked = saveFlag === true || saveFlag === 'true';
        }
        if (!calculation || typeof calculation !== 'object') {
            this.updateColumnCalculationVisibility(columnDiv);
            return;
        }
        const operation = columnDiv.querySelector('.column-calc-operation');
        if (operation && calculation.operation) operation.value = calculation.operation;
        const formula = columnDiv.querySelector('.column-calc-formula');
        if (formula) formula.value = calculation.formula || '';
        const decimals = columnDiv.querySelector('.column-calc-decimals');
        if (decimals && calculation.decimals != null) {
            decimals.value = String(calculation.decimals);
            columnDiv.dataset.decimalsTouched = '1';
        }
        const blankAsZero = columnDiv.querySelector('.column-calc-blank-as-zero');
        if (blankAsZero) blankAsZero.checked = calculation.blank_as_zero !== false;
        columnDiv.dataset.calcSources = JSON.stringify(calculation.sources || []);
        columnDiv.dataset.calcSubtrahends = JSON.stringify(calculation.subtrahends || []);
        columnDiv.dataset.calcDenominators = JSON.stringify(calculation.denominators || []);
        this.updateColumnCalculationVisibility(columnDiv);
    },

    addColumn(modalElement, text = '', type = 'number_whole', isVariable = false, variableName = '', variableSaveValue = true, variableReadonly = true, nameTranslations = {}, targetContainer = null, decimals = 2, selectableHeaderConfig = null, calculation = null, includeInRowTotal = undefined, calculationOptions = null) {
        const columnsContainer = Utils.getElementById('matrix-columns-container');
        const template = Utils.getElementById('matrix-column-template');
        if (!template) {
            console.error('Matrix column template not found');
            return;
        }
        const clone = template.content.cloneNode(true);
        const columnDiv = clone.querySelector('.matrix-column');
        const input = clone.querySelector('.column-text');
        const translationsInput = clone.querySelector('.column-name-translations');
        const translateBtn = clone.querySelector('.matrix-column-translate-btn');
        const typeSelect = clone.querySelector('.column-type');
        const decimalsInput = clone.querySelector('.column-decimals');
        const variableSelect = clone.querySelector('.column-variable-select');
        const variableOptions = clone.querySelector('.column-variable-options');
        const isVariableCheckbox = clone.querySelector('.column-is-variable');
        const saveValueCheckbox = clone.querySelector('.column-variable-save-value');
        const readonlyCheckbox = clone.querySelector('.column-variable-readonly');

        // Every column clones the same <template>, so its two "Source" radios need a
        // name unique to THIS column's clone -- otherwise all columns' radios end up
        // sharing the template's literal name and become one giant mutually-exclusive
        // group across the whole modal (selecting "List Library" on one column would
        // silently uncheck it on another). Without any shared name at all, the browser
        // does not enforce mutual exclusivity between the two radios in the first place,
        // which is what let both "Manual" and "List Library" end up checked simultaneously.
        const headerSourceGroupName = `column-header-source-${Utils.generateUniqueId()}`;
        clone.querySelectorAll('.column-header-source').forEach(radio => {
            radio.name = headerSourceGroupName;
        });

        if (input) {
            input.value = text || '';
            input.dataset.prevName = (text || '').trim();
            // The code this column was saved under. Unlike prevName it never follows edits,
            // so on save it shows which columns were renamed (see collectColumnRenames).
            input.dataset.originalName = (text || '').trim();
        }
        if (translationsInput) {
            try {
                const normalized = (nameTranslations && typeof nameTranslations === 'object') ? nameTranslations : {};
                translationsInput.value = JSON.stringify(normalized);
                const hasAny = Object.values(normalized).some(v => String(v || '').trim());
                if (translateBtn) {
                    if (hasAny) translateBtn.classList.add('text-green-600');
                    else translateBtn.classList.remove('text-green-600');
                }
            } catch (_e) {
                translationsInput.value = '{}';
            }
        }
        if (typeSelect) {
            typeSelect.value = this._normalizeColumnTypeForUi(type);
        }
        if (decimalsInput) {
            const parsedDecimals = parseInt(decimals, 10);
            decimalsInput.value = String((Number.isFinite(parsedDecimals) && parsedDecimals >= 0) ? parsedDecimals : 2);
        }
        this.updateColumnDecimalsVisibility(columnDiv);

        // Check if template has variables defined
        const templateVariables = window.templateVariables || {};
        const metadata = Array.isArray(window.builtInMetadataVariables) ? window.builtInMetadataVariables : [];
        const hasVariables = Object.keys(templateVariables).length > 0 || metadata.length > 0;

        // Show/hide variable options based on whether template has variables
        if (variableOptions) {
            if (hasVariables) {
                variableOptions.style.display = 'flex';
                variableOptions.classList.remove('hidden');
            } else {
                variableOptions.style.display = 'none';
                variableOptions.classList.add('hidden');
            }
        }

        // Handle variable checkbox
        if (isVariableCheckbox) {
            isVariableCheckbox.checked = isVariable;
            // Show/hide variable selector and save/readonly options based on checkbox state
            const saveValueLabel = clone.querySelector('.column-variable-save-value-label');
            const readonlyLabel = clone.querySelector('.column-variable-readonly-label');

            if (isVariable) {
                if (variableSelect) {
                    variableSelect.style.display = '';
                    variableSelect.classList.remove('hidden');
                    this.populateVariableOptions(variableSelect, modalElement);
                    if (variableName) {
                        variableSelect.value = variableName;
                    }
                }
                // Show save value and readonly checkboxes
                if (saveValueLabel) {
                    saveValueLabel.style.display = 'flex';
                }
                if (readonlyLabel) {
                    readonlyLabel.style.display = 'flex';
                }
                if (saveValueCheckbox) {
                    saveValueCheckbox.checked = variableSaveValue !== false;
                }
                if (readonlyCheckbox) {
                    readonlyCheckbox.checked = variableReadonly !== false;
                }
                this.updateColumnVariableSaveValueState(columnDiv);
            } else {
                if (variableSelect) {
                    variableSelect.style.display = 'none';
                    variableSelect.classList.add('hidden');
                }
                // Hide save value and readonly checkboxes
                if (saveValueLabel) {
                    saveValueLabel.style.display = 'none';
                }
                if (readonlyLabel) {
                    readonlyLabel.style.display = 'none';
                }
            }
        }
        const appendTarget = targetContainer || columnsContainer;
        if (!appendTarget) {
            console.error('No container found to append column to');
            return;
        }
        // ── Restore selectable header config when populating from saved data ──
        if (selectableHeaderConfig && selectableHeaderConfig.header_type === 'selectable') {
            const shd = selectableHeaderConfig;
            const checkbox = clone.querySelector('.column-selectable-header');
            if (checkbox) {
                checkbox.checked = true;
                this._setColumnSelectableHeaderExpanded(columnDiv, true);
            }

            const placeholderInput = clone.querySelector('.column-header-placeholder');
            if (placeholderInput) placeholderInput.value = shd.header_placeholder || '';

            const source = shd.header_source || 'manual';
            const sourceRadio = clone.querySelector(`.column-header-source[value="${source}"]`);
            if (sourceRadio) {
                sourceRadio.checked = true;
                const manualSec = clone.querySelector('.column-header-manual-section');
                const listSec = clone.querySelector('.column-header-list-library-section');
                manualSec?.classList.toggle('hidden', source === 'list_library');
                listSec?.classList.toggle('hidden', source !== 'list_library');
            }

            if (source === 'manual') {
                const optionsList = clone.querySelector('.column-header-manual-options-list');
                const headerOptions = Array.isArray(shd.header_options) ? shd.header_options : [];
                if (optionsList) {
                    if (headerOptions.length) {
                        headerOptions.forEach(opt => this.addColumnHeaderOption(optionsList, opt));
                    } else {
                        this.addColumnHeaderOption(optionsList);
                    }
                }
            }

            if (source === 'list_library') {
                const listSelect = clone.querySelector('.column-header-list-select');
                if (listSelect && shd.header_lookup_list_id) {
                    listSelect.value = String(shd.header_lookup_list_id);
                    // Populate display column options, then restore the saved value
                    const colDiv = clone.querySelector('.matrix-column');
                    if (colDiv) {
                        this._populateColumnHeaderDisplayColumns(colDiv, listSelect.value);
                        if (shd.header_list_display_column) {
                            const displaySelect = colDiv.querySelector('.column-header-list-display-column');
                            if (displaySelect) displaySelect.value = shd.header_list_display_column;
                        }
                        // Load any plugin-specific config UI (e.g. Emergency Operations) for
                        // this column's header list, pre-filled with the saved values.
                        colDiv._pendingHeaderPluginConfig = shd.header_plugin_config || {};
                        this._loadColumnHeaderPluginConfig(modalElement, colDiv, listSelect.value);
                    }
                }
            }

            const allowOtherCb = clone.querySelector('.column-header-allow-other');
            if (allowOtherCb) allowOtherCb.checked = !!shd.header_allow_other;
        }
        appendTarget.appendChild(clone);
        this._applyCalculationConfig(columnDiv, calculation, includeInRowTotal, calculationOptions);
        this.refreshCalculationSourceLists(modalElement);
        // Bind custom tooltips on newly added column (e.g. Save value ?)
        if (typeof window.initTooltips === 'function') {
            window.initTooltips();
        }
        // Update auto-load visibility after adding column
        this.updateAutoLoadVisibility(modalElement);
    },

    /**
     * Add a column group. Pass `targetContainer` (a top-level group's
     * `.matrix-group-columns`) to create a subgroup inside it. Only two levels
     * are supported: groups inside a group cannot contain further groups.
     * Returns the new `.matrix-group` element.
     */
    addGroup(modalElement, label = '', labelTranslations = {}, headerColor = '', targetContainer = null) {
        const columnsContainer = targetContainer || Utils.getElementById('matrix-columns-container');
        const template = Utils.getElementById('matrix-group-template');
        if (!columnsContainer || !template) {
            console.error('Matrix group container or template not found');
            return null;
        }
        const clone = template.content.cloneNode(true);
        const groupEl = clone.querySelector('.matrix-group');
        const labelInput = clone.querySelector('.group-label-text');
        const labelTranslationsInput = clone.querySelector('.group-label-translations');
        const colorInput = clone.querySelector('.group-header-color');
        const textColorInput = clone.querySelector('.group-header-text-color');
        const applyHeaderInput = clone.querySelector('.group-apply-header-color');
        const applyCellInput = clone.querySelector('.group-apply-cell-color');
        const translations = (labelTranslations && typeof labelTranslations === 'object' && !Array.isArray(labelTranslations))
            ? { ...labelTranslations }
            : {};
        const storedColor = headerColor || translations[GROUP_HEADER_COLOR_KEY] || '';
        const storedTextColor = translations[GROUP_HEADER_TEXT_COLOR_KEY] || '';
        const applyHeaders = savedGroupColorFlag(translations, GROUP_APPLY_HEADER_COLOR_KEY);
        const applyCells = savedGroupColorFlag(translations, GROUP_APPLY_CELL_COLOR_KEY);
        delete translations[GROUP_HEADER_COLOR_KEY];
        delete translations[GROUP_HEADER_TEXT_COLOR_KEY];
        delete translations[GROUP_APPLY_COLOR_KEY];
        delete translations[GROUP_APPLY_HEADER_COLOR_KEY];
        delete translations[GROUP_APPLY_CELL_COLOR_KEY];
        if (labelInput) labelInput.value = label || '';
        if (labelTranslationsInput) {
            try {
                labelTranslationsInput.value = JSON.stringify(translations);
            } catch (_) {
                labelTranslationsInput.value = '{}';
            }
        }
        if (colorInput) {
            colorInput.value = normalizeMatrixGroupHeaderColor(storedColor) || DEFAULT_MATRIX_GROUP_HEADER_COLOR;
        }
        if (textColorInput) {
            textColorInput.value = customMatrixGroupHeaderTextColor(storedColor, storedTextColor);
        }
        const customColor = !!customMatrixGroupHeaderColor(storedColor)
            || !!customMatrixGroupHeaderTextColor(storedColor, storedTextColor);
        if (applyHeaderInput) applyHeaderInput.checked = applyHeaders && customColor;
        if (applyCellInput) applyCellInput.checked = applyCells && customColor;
        this._paintGroupHeader(groupEl);
        columnsContainer.appendChild(clone);
        this._syncGroupDepth();
        return groupEl;
    },

    /**
     * Mark each group as top-level or nested. Nested groups get a lighter indent
     * and lose the "Add Subgroup" button (two levels maximum).
     */
    _syncGroupDepth() {
        const root = Utils.getElementById('matrix-columns-container');
        if (!root) return;
        root.querySelectorAll('.matrix-group').forEach(groupEl => {
            const nested = groupEl.parentElement?.classList.contains('matrix-group-columns') === true;
            groupEl.dataset.depth = nested ? '2' : '1';
            groupEl.querySelector(':scope > .matrix-group-footer .add-subgroup-to-group-btn')
                ?.classList.toggle('hidden', nested);
            groupEl.classList.toggle('bg-white', nested);
        });
    },

    _groupLabel(groupEl) {
        return groupEl?.querySelector(':scope > .matrix-group-header .group-label-text')?.value?.trim() || '';
    },

    /** Label translations plus optional header colour for a group, as persisted in column_groups. */
    _groupMeta(groupEl) {
        const translationsInput = groupEl.querySelector(':scope > .matrix-group-header .group-label-translations');
        let labelTranslations = {};
        if (translationsInput?.value) {
            try { labelTranslations = JSON.parse(translationsInput.value) || {}; } catch (_) {}
        }
        if (!labelTranslations || typeof labelTranslations !== 'object' || Array.isArray(labelTranslations)) {
            labelTranslations = {};
        }
        delete labelTranslations[GROUP_HEADER_COLOR_KEY];
        delete labelTranslations[GROUP_HEADER_TEXT_COLOR_KEY];
        delete labelTranslations[GROUP_APPLY_COLOR_KEY];
        delete labelTranslations[GROUP_APPLY_HEADER_COLOR_KEY];
        delete labelTranslations[GROUP_APPLY_CELL_COLOR_KEY];
        const header = groupEl.querySelector(':scope > .matrix-group-header');
        // The default grey is not stored, so groups look like other columns.
        const backgroundValue = header?.querySelector('.group-header-color')?.value;
        const headerColor = customMatrixGroupHeaderColor(backgroundValue);
        const textColor = customMatrixGroupHeaderTextColor(
            backgroundValue,
            header?.querySelector('.group-header-text-color')?.value
        );
        if (headerColor) labelTranslations[GROUP_HEADER_COLOR_KEY] = headerColor;
        if (textColor) labelTranslations[GROUP_HEADER_TEXT_COLOR_KEY] = textColor;
        const applyHeaders = header?.querySelector('.group-apply-header-color')?.checked;
        const applyCells = header?.querySelector('.group-apply-cell-color')?.checked;
        const tinted = !!(headerColor || textColor);
        if (tinted && applyHeaders) labelTranslations[GROUP_APPLY_HEADER_COLOR_KEY] = true;
        if (tinted && applyCells) labelTranslations[GROUP_APPLY_CELL_COLOR_KEY] = true;
        return labelTranslations;
    },

    /**
     * Ordered list of the data columns saved for a top-level group, with the
     * subgroup label ('' for columns sitting directly in the group).
     * Unnamed groups and subgroups are skipped, matching updateConfig.
     */
    _collectGroupColumns(groupEl) {
        const result = [];
        const group = this._groupLabel(groupEl);
        if (!group) return result;
        const list = groupEl.querySelector(':scope > .matrix-group-columns');
        Array.from(list?.children || []).forEach(child => {
            if (child.classList.contains('matrix-column')) {
                result.push({ columnDiv: child, group, subgroup: '', subgroupEl: null });
            } else if (child.classList.contains('matrix-group')) {
                const subgroup = this._groupLabel(child);
                if (!subgroup) return;
                child.querySelectorAll(':scope > .matrix-group-columns > .matrix-column').forEach(columnDiv => {
                    result.push({ columnDiv, group, subgroup, subgroupEl: child });
                });
            }
        });
        return result;
    },

    /** Which colour the open picker is editing: background or text. */
    _groupColorTarget(groupEl) {
        const panel = groupEl?.querySelector(':scope > .matrix-group-header .group-color-panel');
        return panel?.dataset.colorTarget === 'text' ? 'text' : 'background';
    },

    _groupHeaderColors(groupEl) {
        const header = groupEl?.querySelector(':scope > .matrix-group-header');
        const background = normalizeMatrixGroupHeaderColor(header?.querySelector('.group-header-color')?.value)
            || DEFAULT_MATRIX_GROUP_HEADER_COLOR;
        const storedText = header?.querySelector('.group-header-text-color')?.value;
        const text = normalizeMatrixGroupHeaderColor(storedText) || matrixGroupHeaderTextColor(background);
        return { header, background, text };
    },

    /**
     * Preview the group colours on the builder group bar.
     * Default grey matches a normal matrix column header. Text follows the
     * saved text colour, or white/grey contrast when that was left automatic.
     */
    _paintGroupHeader(groupEl) {
        const { header, background, text } = this._groupHeaderColors(groupEl);
        if (!header) return;
        const lightText = hexLuminance(text) >= 160;
        header.style.backgroundColor = background;
        header.style.color = text;
        const labelInput = header.querySelector('.group-label-text');
        if (labelInput) {
            labelInput.style.color = text;
            labelInput.style.backgroundColor = lightText ? 'transparent' : '';
            labelInput.style.borderColor = lightText ? 'rgba(255,255,255,0.45)' : '';
        }
        header.querySelectorAll(':scope > label').forEach(caption => {
            caption.style.color = text;
        });
        const handle = header.querySelector('.matrix-drag-handle');
        if (handle) handle.style.color = lightText ? text : '';
        this._syncGroupColorPanel(groupEl);
    },

    /** Keep the swatch, hex field, and spectrum aligned with the colour being edited. */
    _syncGroupColorPanel(groupEl) {
        const { header, background, text } = this._groupHeaderColors(groupEl);
        if (!header) return;
        const active = this._groupColorTarget(groupEl) === 'text' ? text : background;
        const { h, s, v } = hexToHsv(active);
        const sv = header.querySelector('.group-color-sv');
        if (sv) {
            sv.dataset.s = String(s);
            sv.dataset.v = String(v);
            sv.style.backgroundColor = `hsl(${h} 100% 50%)`;
            const cursor = sv.querySelector('.group-color-sv-cursor');
            if (cursor) {
                cursor.style.left = `${s * 100}%`;
                cursor.style.top = `${(1 - v) * 100}%`;
            }
        }
        const hue = header.querySelector('.group-color-hue');
        if (hue && document.activeElement !== hue) hue.value = String(Math.round(h));
        const swatch = header.querySelector('.group-color-swatch');
        if (swatch) {
            swatch.style.backgroundColor = background;
            const letter = swatch.querySelector('.group-color-swatch-text');
            if (letter) letter.style.color = text;
        }
        const hexInput = header.querySelector('.group-header-color-hex');
        if (hexInput && document.activeElement !== hexInput) hexInput.value = active.toUpperCase();
        this._syncApplyColorOption(groupEl);
    },

    _positionGroupColorPanel(panel, toggle) {
        const rect = toggle.getBoundingClientRect();
        const width = panel.offsetWidth || 224;
        const height = panel.offsetHeight || 220;
        const margin = 8;
        const left = Math.max(margin, Math.min(rect.right - width, window.innerWidth - width - margin));
        let top = rect.bottom + 4;
        if (top + height > window.innerHeight - margin) {
            top = Math.max(margin, rect.top - height - 4);
        }
        panel.style.left = `${left}px`;
        panel.style.top = `${top}px`;
    },

    /** Write a background #rrggbb onto the group and refresh the builder preview. */
    _setGroupHeaderColor(groupEl, hex) {
        const input = groupEl?.querySelector(':scope > .matrix-group-header .group-header-color');
        const next = normalizeMatrixGroupHeaderColor(hex) || DEFAULT_MATRIX_GROUP_HEADER_COLOR;
        if (!input) return;
        if (input.value === next) {
            this._paintGroupHeader(groupEl);
            return;
        }
        input.value = next;
        input.dispatchEvent(new Event('input', { bubbles: true }));
    },

    /**
     * Write a text colour. The automatic contrast colour is stored as empty so
     * later background changes keep choosing the text colour.
     */
    _setGroupHeaderTextColor(groupEl, hex) {
        const header = groupEl?.querySelector(':scope > .matrix-group-header');
        const input = header?.querySelector('.group-header-text-color');
        if (!input) return;
        const next = customMatrixGroupHeaderTextColor(header.querySelector('.group-header-color')?.value, hex);
        if (input.value === next) {
            this._paintGroupHeader(groupEl);
            return;
        }
        input.value = next;
        input.dispatchEvent(new Event('input', { bubbles: true }));
    },

    _setActiveGroupColor(groupEl, hex) {
        if (this._groupColorTarget(groupEl) === 'text') this._setGroupHeaderTextColor(groupEl, hex);
        else this._setGroupHeaderColor(groupEl, hex);
    },

    _commitGroupHexInput(hexInput, { restoreInvalid = false } = {}) {
        const groupEl = hexInput?.closest('.matrix-group');
        if (!groupEl) return;
        const normalized = expandHexColor(hexInput.value);
        if (!normalized) {
            if (restoreInvalid) {
                const { background, text } = this._groupHeaderColors(groupEl);
                const current = this._groupColorTarget(groupEl) === 'text' ? text : background;
                hexInput.value = current.toUpperCase();
            }
            return;
        }
        this._setActiveGroupColor(groupEl, normalized);
    },

    _commitGroupColorFromControls(groupEl) {
        const header = groupEl?.querySelector(':scope > .matrix-group-header');
        if (!header) return;
        const hue = Number(header.querySelector('.group-color-hue')?.value || 0);
        const sv = header.querySelector('.group-color-sv');
        const s = Number(sv?.dataset.s);
        const v = Number(sv?.dataset.v);
        this._setActiveGroupColor(groupEl, hsvToHex(
            hue,
            Number.isFinite(s) ? clamp01(s) : 0,
            Number.isFinite(v) ? clamp01(v) : 1,
        ));
    },

    _setGroupColorFromSv(sv, event) {
        const rect = sv.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        sv.dataset.s = String(clamp01((event.clientX - rect.left) / rect.width));
        sv.dataset.v = String(clamp01(1 - ((event.clientY - rect.top) / rect.height)));
        this._commitGroupColorFromControls(sv.closest('.matrix-group'));
    },

    /** Header and cell tints apply once the background or the text colour is custom. */
    _syncApplyColorOption(groupEl) {
        const header = groupEl?.querySelector(':scope > .matrix-group-header');
        const input = header?.querySelector('.group-header-color');
        const textInput = header?.querySelector('.group-header-text-color');
        const options = header?.querySelectorAll('.group-apply-color-label');
        if (!options?.length) return;
        const custom = !!customMatrixGroupHeaderColor(input?.value)
            || !!customMatrixGroupHeaderTextColor(input?.value, textInput?.value);
        options.forEach(option => {
            option.classList.toggle('hidden', !custom);
            if (!custom) {
                const checkbox = option.querySelector('input[type="checkbox"]');
                if (checkbox) checkbox.checked = false;
            }
        });
    },

    /**
     * Collapse or expand a column group in the builder. UI-only state: collapsed
     * groups keep their columns in the DOM, so updateConfig still saves them.
     */
    _setGroupCollapsed(groupEl, collapsed) {
        if (!groupEl) return;
        // :scope > keeps nested subgroups from matching the parent's elements.
        const columns = groupEl.querySelector(':scope > .matrix-group-columns');
        const footer = groupEl.querySelector(':scope > .matrix-group-footer');
        const header = groupEl.querySelector(':scope > .matrix-group-header');
        const toggle = header?.querySelector('.matrix-group-toggle-btn');
        const icon = header?.querySelector('.matrix-group-toggle-icon');
        const count = header?.querySelector('.matrix-group-count');

        groupEl.classList.toggle('is-collapsed', collapsed);
        columns?.classList.toggle('hidden', collapsed);
        footer?.classList.toggle('hidden', collapsed);
        header?.classList.toggle('rounded-b-md', collapsed);
        if (icon) icon.style.transform = collapsed ? 'rotate(-90deg)' : '';
        if (toggle) {
            toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
            const title = collapsed ? toggle.dataset.expandTitle : toggle.dataset.collapseTitle;
            if (title) toggle.title = title;
        }
        if (count) {
            const n = columns ? columns.querySelectorAll('.matrix-column').length : 0;
            count.textContent = `(${n})`;
            count.classList.toggle('hidden', !collapsed);
        }
    },

    /** Add a column from a saved-style config object (as returned by _extractColumnConfig). */
    _addColumnFromConfig(modalElement, colData, targetContainer) {
        const isVariable = colData.is_variable || colData.type === 'variable';
        this.addColumn(
            modalElement, colData.name || '', colData.type, isVariable,
            colData.variable || colData.variable_name || '',
            colData.variable_save_value !== false, colData.variable_readonly !== false,
            colData.name_translations || {}, targetContainer, colData.decimals,
            colData.header_type ? colData : null, colData.calculation || null,
            colData.include_in_row_total,
            { readonly: colData.calculation_readonly, saveValue: colData.calculation_save_value, bold: colData.calculation_bold }
        );
        const columnDiv = targetContainer?.lastElementChild;
        // The copy is a new column: it was never saved under this code, so it is not a rename.
        const input = columnDiv?.querySelector('.column-text');
        if (input) input.dataset.originalName = '';
        return columnDiv;
    },

    /**
     * Duplicate a column group (or subgroup) with all its columns and subgroups.
     * The copy is inserted right after the original. Group labels and column codes
     * must stay unique, so the copy gets "(copy)" / "_copy" suffixes, and calculated
     * columns that reference columns inside the group point at the copied columns.
     * Returns the new `.matrix-group` element.
     */
    duplicateGroup(modalElement, groupEl) {
        const parent = groupEl?.parentElement;
        if (!groupEl || !parent) return null;

        const usedNames = new Set(
            Array.from(modalElement.querySelectorAll('.matrix-column .column-text'))
                .map(input => input.value.trim())
                .filter(Boolean)
        );
        const nameMap = new Map();
        const copyName = (name) => {
            if (nameMap.has(name)) return nameMap.get(name);
            let candidate = `${name}_copy`;
            let n = 2;
            while (usedNames.has(candidate)) candidate = `${name}_copy${n++}`;
            usedNames.add(candidate);
            nameMap.set(name, candidate);
            return candidate;
        };

        // Snapshot the original (unnamed, non-variable columns are not saved, so they are skipped).
        const snapshot = (el) => {
            const meta = this._groupMeta(el);
            const children = [];
            Array.from(el.querySelector(':scope > .matrix-group-columns')?.children || []).forEach(child => {
                if (child.classList.contains('matrix-column')) {
                    const cfg = this._extractColumnConfig(child);
                    if (!cfg) return;
                    if (cfg.name) copyName(cfg.name);
                    children.push({ type: 'column', cfg });
                } else if (child.classList.contains('matrix-group')) {
                    children.push({ type: 'group', ...snapshot(child) });
                }
            });
            return { label: this._groupLabel(el), meta, children };
        };
        const tree = snapshot(groupEl);

        const remapName = (name) => (nameMap.has(name) ? nameMap.get(name) : name);
        const remapFormula = (formula) => {
            let result = formula || '';
            nameMap.forEach((to, from) => {
                const escaped = from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                result = result.replace(
                    new RegExp(`(?<![A-Za-z0-9_])${escaped}(?![A-Za-z0-9_])`, 'g'),
                    () => to
                );
            });
            return result;
        };

        const siblingLabels = new Set(
            Array.from(parent.children)
                .filter(c => c.classList.contains('matrix-group'))
                .map(c => this._groupLabel(c))
        );
        let newLabel = tree.label;
        if (newLabel) {
            newLabel = `${tree.label} (copy)`;
            let n = 2;
            while (siblingLabels.has(newLabel)) newLabel = `${tree.label} (copy ${n++})`;
        }

        const build = (node, label, container) => {
            const translations = { ...node.meta };
            const color = translations[GROUP_HEADER_COLOR_KEY] || '';
            delete translations[GROUP_HEADER_COLOR_KEY];
            const newGroup = this.addGroup(modalElement, label, translations, color, container);
            const list = newGroup.querySelector(':scope > .matrix-group-columns');
            node.children.forEach(child => {
                if (child.type === 'group') {
                    build(child, child.label, list);
                    return;
                }
                const cfg = { ...child.cfg };
                if (cfg.name) cfg.name = remapName(cfg.name);
                if (cfg.calculation) {
                    const calc = { ...cfg.calculation };
                    ['sources', 'subtrahends', 'denominators'].forEach(key => {
                        if (Array.isArray(calc[key])) calc[key] = calc[key].map(remapName);
                    });
                    calc.formula = remapFormula(calc.formula);
                    cfg.calculation = calc;
                }
                this._addColumnFromConfig(modalElement, cfg, list);
            });
            return newGroup;
        };

        const newGroup = build(tree, newLabel, parent);
        groupEl.after(newGroup);
        this._setGroupCollapsed(newGroup, false);
        this._syncGroupDepth();
        this.refreshCalculationSourceLists(modalElement);
        this.updateAutoLoadVisibility(modalElement);
        return newGroup;
    },

    moveGroup(button, direction) {
        const group = button.closest('.matrix-group');
        const container = group ? group.parentElement : null;
        if (!group || !container) return;
        if (direction === 'up' && group.previousElementSibling) {
            container.insertBefore(group, group.previousElementSibling);
        } else if (direction === 'down' && group.nextElementSibling) {
            container.insertBefore(group.nextElementSibling, group);
        }
    },

    /**
     * Columns whose code was changed in this edit: [{from, to}].
     * Saved cell keys embed the column code, so the server uses this to offer moving
     * saved data to the new code. New columns (no original code) are never renames.
     */
    collectColumnRenames(modalElement) {
        const container = modalElement?.querySelector('#matrix-columns-container')
            || Utils.getElementById('matrix-columns-container');
        if (!container) return [];
        const renames = [];
        container.querySelectorAll('.matrix-column').forEach((columnDiv) => {
            const input = columnDiv.querySelector('.column-text');
            const from = (input?.dataset?.originalName || '').trim();
            const to = (input?.value || '').trim();
            if (from && to && from !== to) renames.push({ from, to });
        });
        return renames;
    },

    /**
     * Problems with the column codes in the modal: [{input, message}].
     * Mirrors app/services/forms/matrix_column_validation.py. Saved cells are keyed by
     * column code, so codes must be unique and must not collide with reserved keys.
     */
    collectColumnCodeIssues(modalElement) {
        const container = modalElement?.querySelector('#matrix-columns-container')
            || Utils.getElementById('matrix-columns-container');
        if (!container) return [];
        const entries = Array.from(container.querySelectorAll('.matrix-column')).map((columnDiv) => {
            const input = columnDiv.querySelector('.column-text');
            let hasLabel = false;
            try {
                const translations = JSON.parse(columnDiv.querySelector('.column-name-translations')?.value || '{}');
                hasLabel = Object.values(translations || {}).some((v) => String(v || '').trim());
            } catch (_e) { /* ignore malformed translations */ }
            return {
                input,
                code: (input?.value || '').trim(),
                isVariable: !!columnDiv.querySelector('.column-is-variable')?.checked,
                hasLabel,
            };
        }).filter((entry) => entry.input);

        const counts = new Map();
        entries.forEach(({ code }) => { if (code) counts.set(code, (counts.get(code) || 0) + 1); });

        const issues = [];
        entries.forEach(({ input, code, isVariable, hasLabel }) => {
            if (!code) {
                if (!isVariable && hasLabel) {
                    issues.push({ input, message: 'A column has a label but no code. Give it a column code.' });
                }
                return;
            }
            if (counts.get(code) > 1) {
                issues.push({ input, message: `Column code "${code}" is used more than once. Column codes must be unique.` });
            }
            if (RESERVED_COLUMN_CODES.has(code.toLowerCase())) {
                issues.push({ input, message: `"${code}" is reserved and cannot be used as a column code.` });
            }
            if (code.includes('|')) {
                issues.push({ input, message: `Column code "${code}" cannot contain "|".` });
            }
            if ((code.match(/\[/g) || []).length !== (code.match(/\]/g) || []).length) {
                issues.push({ input, message: `Column code "${code}" has unbalanced [ ] brackets.` });
            }
        });
        return issues;
    },

    /** Outline the offending column-code inputs and explain why in their tooltip. */
    markColumnCodeIssues(modalElement) {
        const container = modalElement?.querySelector('#matrix-columns-container')
            || Utils.getElementById('matrix-columns-container');
        if (!container) return [];
        const issues = this.collectColumnCodeIssues(modalElement);
        const byInput = new Map();
        issues.forEach(({ input, message }) => {
            byInput.set(input, [...(byInput.get(input) || []), message]);
        });
        container.querySelectorAll('.column-text').forEach((input) => {
            const messages = byInput.get(input);
            if (input.dataset.baseTitle === undefined) input.dataset.baseTitle = input.title || '';
            input.classList.toggle('border-red-500', !!messages);
            input.classList.toggle('focus:ring-red-500', !!messages);
            input.title = messages ? messages.join(' ') : input.dataset.baseTitle;
            if (messages) input.setAttribute('aria-invalid', 'true');
            else input.removeAttribute('aria-invalid');
        });
        return issues;
    },

    /** Expand any collapsed groups around a column so its input can be seen and focused. */
    revealColumnInput(input) {
        let group = input?.closest('.matrix-group');
        while (group) {
            this._setGroupCollapsed(group, false);
            group = group.parentElement?.closest('.matrix-group');
        }
        try {
            input.scrollIntoView({ block: 'center' });
            input.focus();
        } catch (_e) { /* not focusable */ }
    },

    /**
     * Extract the column config object from a .matrix-column DOM element.
     * Returns null if the column has no name and is not a variable column.
     */
    _extractColumnConfig(columnDiv) {
        const textInput = columnDiv.querySelector('.column-text');
        const translationsInput = columnDiv.querySelector('.column-name-translations');
        const typeSelect = columnDiv.querySelector('.column-type');
        const decimalsInput = columnDiv.querySelector('.column-decimals');
        const isVariableCheckbox = columnDiv.querySelector('.column-is-variable');
        const variableSelect = columnDiv.querySelector('.column-variable-select');
        const columnName = textInput?.value?.trim();
        const columnType = typeSelect?.value || 'number_whole';
        const isVariable = isVariableCheckbox?.checked || false;

        if (!columnName && !isVariable) return null;

        const columnConfig = {
            name: columnName || '',
            type: columnType
        };

        if (columnType === 'number_decimal') {
            const parsedDecimals = parseInt(decimalsInput?.value, 10);
            columnConfig.decimals = (Number.isFinite(parsedDecimals) && parsedDecimals >= 0) ? parsedDecimals : 2;
        }

        if (translationsInput && translationsInput.value) {
            try {
                const parsed = JSON.parse(translationsInput.value) || {};
                const hasAny = parsed && typeof parsed === 'object'
                    ? Object.values(parsed).some(v => String(v || '').trim())
                    : false;
                if (hasAny) columnConfig.name_translations = parsed;
            } catch (_) {}
        }

        if (columnType !== 'calculated' && isVariable && variableSelect?.value) {
            columnConfig.is_variable = true;
            columnConfig.variable = variableSelect.value;
            columnConfig.variable_name = variableSelect.value;
            const variableOptions = columnDiv.querySelector('.column-variable-options');
            const saveValueCheckbox = variableOptions?.querySelector('.column-variable-save-value');
            const readonlyCheckbox = variableOptions?.querySelector('.column-variable-readonly');
            const isReadonly = readonlyCheckbox ? readonlyCheckbox.checked : true;
            columnConfig.variable_readonly = isReadonly;
            columnConfig.variable_save_value = isReadonly
                ? false
                : (saveValueCheckbox ? saveValueCheckbox.checked : true);
        }

        const includeInRowTotal = columnDiv.querySelector('.column-include-in-row-total');
        if (columnType === 'calculated') {
            columnConfig.calculation = this._readCalculation(columnDiv);
            const calcReadonly = columnDiv.querySelector('.column-calc-readonly');
            const calcSaveValue = columnDiv.querySelector('.column-calc-save-value');
            if (calcReadonly && !calcReadonly.checked) columnConfig.calculation_readonly = false;
            if (calcSaveValue?.checked) columnConfig.calculation_save_value = true;
            if (!this._calculationBoldOn(columnDiv)) columnConfig.calculation_bold = false;
            if (includeInRowTotal?.checked) columnConfig.include_in_row_total = true;
        } else if (includeInRowTotal && !includeInRowTotal.checked) {
            columnConfig.include_in_row_total = false;
        }

        // ── Selectable header ──────────────────────────────────────────────
        const selectableHdrCheckbox = columnDiv.querySelector('.column-selectable-header');
        if (columnType !== 'calculated' && selectableHdrCheckbox?.checked) {
            columnConfig.header_type = 'selectable';

            const placeholderInput = columnDiv.querySelector('.column-header-placeholder');
            const placeholder = placeholderInput?.value?.trim();
            if (placeholder) columnConfig.header_placeholder = placeholder;

            const sourceRadio = columnDiv.querySelector('.column-header-source:checked');
            const source = sourceRadio?.value || 'manual';
            columnConfig.header_source = source;

            if (source === 'manual') {
                const opts = Array.from(columnDiv.querySelectorAll('.column-header-option-text'))
                    .map(input => input.value.trim())
                    .filter(Boolean);
                if (opts.length) columnConfig.header_options = opts;
            } else {
                const listId = columnDiv.querySelector('.column-header-list-select')?.value;
                const displayCol = columnDiv.querySelector('.column-header-list-display-column')?.value;
                if (listId) {
                    const parsedId = parseInt(listId, 10);
                    columnConfig.header_lookup_list_id = Number.isFinite(parsedId) ? parsedId : listId;
                }
                if (displayCol) columnConfig.header_list_display_column = displayCol;

                // Plugin-specific configuration for this column's header list (e.g. Emergency Operations)
                const pluginConfigContainer = columnDiv.querySelector('.column-header-plugin-config-container');
                if (pluginConfigContainer) {
                    const pluginConfig = this._extractPluginConfigFromContainer(pluginConfigContainer);
                    if (Object.keys(pluginConfig).length > 0) {
                        columnConfig.header_plugin_config = pluginConfig;
                    }
                }
            }

            const allowOtherCheckbox = columnDiv.querySelector('.column-header-allow-other');
            columnConfig.header_allow_other = !!allowOtherCheckbox?.checked;
        }

        return columnConfig;
    },

    /**
     * How many persisted data columns this top-level column-list child represents.
     * Unnamed non-variable columns are skipped, matching updateConfig.
     */
    _savedLeafCount(element) {
        if (!element) return 0;
        if (element.classList.contains('matrix-group')) {
            let count = 0;
            this._collectGroupColumns(element).forEach(({ columnDiv }) => {
                if (this._extractColumnConfig(columnDiv)) count += 1;
            });
            return count;
        }
        if (element.classList.contains('matrix-column')) {
            return this._extractColumnConfig(element) ? 1 : 0;
        }
        return 0;
    },

    /**
     * Index in the saved columns array where the row-total column currently sits.
     * Returns null when the total column is not in the list.
     */
    _rowTotalPositionFromDom(columnsContainer) {
        if (!columnsContainer) return null;
        let position = 0;
        let found = false;
        Array.from(columnsContainer.children).forEach(child => {
            if (found) return;
            if (child.classList.contains('matrix-row-total-column')) {
                found = true;
                return;
            }
            position += this._savedLeafCount(child);
        });
        return found ? position : null;
    },

    _createRowTotalColumnNode() {
        const template = Utils.getElementById('matrix-row-total-column-template');
        const source = template?.content?.querySelector('.matrix-row-total-column');
        return source ? source.cloneNode(true) : null;
    },

    /**
     * Show the row-total column in the table-columns list while Show Row Totals is on.
     * `position` is the count of data columns that should appear before it.
     * Omit position to append (historical default: last).
     */
    syncRowTotalColumn(modalElement, position) {
        const container = Utils.getElementById('matrix-columns-container')
            || modalElement?.querySelector('#matrix-columns-container');
        if (!container) return;
        const checkbox = modalElement?.querySelector('#matrix-show-row-totals')
            || Utils.getElementById('matrix-show-row-totals');
        const show = checkbox ? checkbox.checked : true;
        container.querySelectorAll('.matrix-row-total-column').forEach(el => el.remove());
        if (!show) return;

        const node = this._createRowTotalColumnNode();
        if (!node) return;

        let target = Infinity;
        if (position !== undefined && position !== null && position !== '') {
            const parsed = Number(position);
            if (Number.isFinite(parsed)) target = Math.max(0, Math.trunc(parsed));
        }

        let seen = 0;
        let beforeEl = null;
        for (const child of Array.from(container.children)) {
            if (seen >= target) {
                beforeEl = child;
                break;
            }
            const count = this._savedLeafCount(child);
            // A position that lands inside a group stays outside that group so the
            // group header is not split. Place the total after the group instead.
            if (child.classList.contains('matrix-group') && seen < target && target < seen + count) {
                seen += count;
                continue;
            }
            seen += count;
        }
        if (beforeEl) container.insertBefore(node, beforeEl);
        else container.appendChild(node);
    },

    /**
     * Populate the "Row Label Column" <select> for a selectable column header
     * configured as list_library, based on the chosen list's column metadata.
     */
    _populateColumnHeaderDisplayColumns(columnDiv, listId) {
        const displayColWrapper = columnDiv.querySelector('.column-header-display-col-wrapper');
        const displayColSelect = columnDiv.querySelector('.column-header-list-display-column');
        if (!displayColSelect) return;

        if (!listId) {
            displayColWrapper?.classList.add('hidden');
            return;
        }

        // Read column config from the selected list option's data-columns attribute
        const listSelect = columnDiv.querySelector('.column-header-list-select');
        const selectedOpt = listSelect?.querySelector(`option[value="${listId}"]`);
        let columns = [];
        try {
            columns = JSON.parse(selectedOpt?.dataset?.columns || '[]');
        } catch (_) {}

        displayColSelect.replaceChildren();
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = 'Select Column...';
        displayColSelect.appendChild(placeholder);

        columns.forEach(col => {
            const name = typeof col === 'string' ? col : (col.name || col.id || '');
            const label = typeof col === 'string' ? col : (col.label || col.name || col.id || name);
            if (!name) return;
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = label;
            displayColSelect.appendChild(opt);
        });

        displayColWrapper?.classList.remove('hidden');
    },

    setupDragAndDrop(modalElement) {
        const container = Utils.getElementById('matrix-columns-container');
        if (!container) return;
        if (container._dndInitialized) return;
        container._dndInitialized = true;

        let dragged = null;
        // mousedown origin — dragstart fires on the draggable element, not the handle,
        // so we cannot use e.target in dragstart to detect the handle. Track it here instead.
        let lastMousedownWasHandle = false;

        const indicator = document.createElement('div');
        indicator.className = 'matrix-dnd-indicator';
        indicator.style.cssText = 'height:2px;background:#6366f1;border-radius:1px;pointer-events:none;margin:1px 0;';
        // Group that a dragged group would be nested into (outlined while hovering).
        let nestTarget = null;
        const setNestTarget = (groupEl) => {
            if (nestTarget === groupEl) return;
            if (nestTarget) {
                nestTarget.style.outline = '';
                nestTarget.style.outlineOffset = '';
            }
            nestTarget = groupEl;
            if (nestTarget) {
                nestTarget.style.outline = '2px dashed #6366f1';
                nestTarget.style.outlineOffset = '2px';
            }
        };
        const removeIndicator = () => {
            indicator.remove();
            setNestTarget(null);
        };

        // The `.matrix-group-columns` list of the top-level group that contains `cols`
        // (itself when `cols` already belongs to a top-level group).
        const topLevelColumnsOf = (cols) => {
            let current = cols;
            while (current) {
                const group = current.closest('.matrix-group');
                if (!group) return null;
                if (group.parentElement === container) return current;
                current = group.parentElement?.closest('.matrix-group-columns') || null;
            }
            return null;
        };

        // ── Compute insertion target from pointer position ──
        const getInsertionInfo = (e) => {
            if (!dragged) return null;
            const isDraggingColumn = dragged.classList.contains('matrix-column');
            const isDraggingRowTotal = dragged.classList.contains('matrix-row-total-column');
            // A subgroup can move within its group, into another group, or out to the top level.
            // Top-level groups only reorder at the top level (use "Add Subgroup" to nest).
            const isDraggingSubgroup = dragged.classList.contains('matrix-group') && dragged.parentElement !== container;

            if (isDraggingSubgroup) {
                const header = e.target.closest('.matrix-group-header');
                const headerGroup = header?.closest('.matrix-group');
                let targetCols = null;
                if (headerGroup && headerGroup !== dragged && !headerGroup.classList.contains('is-collapsed')) {
                    targetCols = topLevelColumnsOf(headerGroup.parentElement === container
                        ? headerGroup.querySelector(':scope > .matrix-group-columns')
                        : headerGroup.parentElement);
                } else {
                    const pointerCols = e.target.closest('.matrix-group-columns');
                    targetCols = pointerCols ? topLevelColumnsOf(pointerCols) : null;
                }
                if (targetCols && !dragged.contains(targetCols)) {
                    const siblings = Array.from(targetCols.children).filter(c => c !== dragged && c !== indicator);
                    for (const sib of siblings) {
                        const r = sib.getBoundingClientRect();
                        if (e.clientY < r.top + r.height / 2) return { cont: targetCols, before: sib };
                    }
                    return { cont: targetCols, before: null };
                }
            }

            // A top-level group without subgroups of its own can be dropped into another
            // top-level group to become its subgroup (two levels maximum). The drop
            // nests when the pointer is in the target's column list or the middle of its
            // header; the top/bottom edge of a header, and anywhere else, still reorders.
            const isDraggingTopGroup = dragged.classList.contains('matrix-group')
                && dragged.parentElement === container
                && !dragged.querySelector('.matrix-group');
            if (isDraggingTopGroup) {
                let targetGroup = e.target.closest('.matrix-group');
                while (targetGroup && targetGroup.parentElement !== container) {
                    targetGroup = targetGroup.parentElement?.closest('.matrix-group') || null;
                }
                if (targetGroup && targetGroup !== dragged && !targetGroup.classList.contains('is-collapsed')) {
                    const targetCols = targetGroup.querySelector(':scope > .matrix-group-columns');
                    const header = targetGroup.querySelector(':scope > .matrix-group-header');
                    const inColumns = !!targetCols && !!e.target.closest('.matrix-group-columns') && targetCols.contains(e.target);
                    let inHeaderMiddle = false;
                    if (header && header.contains(e.target)) {
                        const r = header.getBoundingClientRect();
                        inHeaderMiddle = e.clientY > r.top + r.height * 0.25 && e.clientY < r.bottom - r.height * 0.25;
                    }
                    if (targetCols && (inColumns || inHeaderMiddle)) {
                        let before = null;
                        if (inColumns) {
                            for (const sib of Array.from(targetCols.children).filter(c => c !== indicator)) {
                                const r = sib.getBoundingClientRect();
                                if (e.clientY < r.top + r.height / 2) { before = sib; break; }
                            }
                        }
                        return { cont: targetCols, before, nestInto: targetGroup };
                    }
                } else if (targetGroup && targetGroup !== dragged && targetGroup.classList.contains('is-collapsed')) {
                    // Collapsed target: only its header is visible, so the middle band nests.
                    const header = targetGroup.querySelector(':scope > .matrix-group-header');
                    const targetCols = targetGroup.querySelector(':scope > .matrix-group-columns');
                    if (header && header.contains(e.target) && targetCols) {
                        const r = header.getBoundingClientRect();
                        if (e.clientY > r.top + r.height * 0.25 && e.clientY < r.bottom - r.height * 0.25) {
                            return { cont: targetCols, before: null, nestInto: targetGroup };
                        }
                    }
                }
            }

            if (isDraggingColumn && !isDraggingRowTotal) {
                // Over a group-columns area → insert inside the group at the right position
                const groupCols = e.target.closest('.matrix-group-columns');
                if (groupCols) {
                    const siblings = Array.from(groupCols.children).filter(c => c !== dragged && c !== indicator);
                    for (const sib of siblings) {
                        const r = sib.getBoundingClientRect();
                        if (e.clientY < r.top + r.height / 2) return { cont: groupCols, before: sib };
                    }
                    return { cont: groupCols, before: null };
                }
                // Over a group header → append into that group
                const groupHeader = e.target.closest('.matrix-group-header');
                if (groupHeader) {
                    const headerGroup = groupHeader.closest('.matrix-group');
                    // A collapsed group's column list is hidden; fall through to outer-level insertion.
                    if (headerGroup && !headerGroup.classList.contains('is-collapsed')) {
                        const gc = headerGroup.querySelector(':scope > .matrix-group-columns');
                        if (gc) return { cont: gc, before: null };
                    }
                }
            }

            // Outer-level insertion. The row-total column stays outside groups,
            // so a pointer inside a group's columns still targets the outer list.
            const pointerInsideGroupCols = e.target.closest('.matrix-group-columns');
            if (!pointerInsideGroupCols || isDraggingRowTotal || dragged.classList.contains('matrix-group')) {
                const siblings = Array.from(container.children).filter(c => c !== dragged && c !== indicator);
                for (const sib of siblings) {
                    const r = sib.getBoundingClientRect();
                    if (e.clientY < r.top + r.height / 2) return { cont: container, before: sib };
                }
                return { cont: container, before: null };
            }
            return null;
        };

        // Track whether the pointer went down on a drag handle before dragstart fires
        container.addEventListener('mousedown', (e) => {
            lastMousedownWasHandle = !!e.target.closest('.matrix-drag-handle');
        });

        container.addEventListener('dragstart', (e) => {
            if (!lastMousedownWasHandle) { e.preventDefault(); return; }
            lastMousedownWasHandle = false;

            // e.target is the draggable element itself (.matrix-column or .matrix-group)
            const t = e.target;
            if (t.classList.contains('matrix-column') || t.classList.contains('matrix-group') || t.classList.contains('matrix-row-total-column')) {
                dragged = t;
            } else {
                // Shouldn't happen, but bail safely
                e.preventDefault();
                return;
            }

            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', ''); // Firefox requires data

            // The browser's automatic drag image can bleed past the dragged element and
            // include the siblings/controls below it. Use a clone of just this element.
            try {
                const rect = dragged.getBoundingClientRect();
                const ghost = dragged.cloneNode(true);
                ghost.removeAttribute('id');
                ghost.querySelectorAll('[id]').forEach(n => n.removeAttribute('id'));
                // Radios sharing a name would otherwise interfere with the originals.
                ghost.querySelectorAll('input[name]').forEach(n => n.removeAttribute('name'));
                ghost.removeAttribute('draggable');
                ghost.style.cssText = `position:fixed;top:-10000px;left:-10000px;width:${rect.width}px;`
                    + 'margin:0;opacity:0.85;pointer-events:none;background:#fff;box-sizing:border-box;';
                document.body.appendChild(ghost);
                e.dataTransfer.setDragImage(
                    ghost,
                    Math.max(0, Math.min(e.clientX - rect.left, rect.width)),
                    Math.max(0, Math.min(e.clientY - rect.top, rect.height))
                );
                setTimeout(() => ghost.remove(), 0);
            } catch (_) { /* fall back to the browser's default drag image */ }

            // Defer visual change so the browser captures a non-dimmed drag ghost
            requestAnimationFrame(() => {
                if (dragged) {
                    dragged.style.opacity = '0.4';
                    dragged.style.outline = '2px solid #6366f1';
                    dragged.style.outlineOffset = '1px';
                }
            });
        });

        container.addEventListener('dragend', () => {
            if (dragged) {
                dragged.style.opacity = '';
                dragged.style.outline = '';
                dragged.style.outlineOffset = '';
                dragged = null;
            }
            removeIndicator();
            this.updateConfig(modalElement);
        });

        container.addEventListener('dragover', (e) => {
            if (!dragged) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            const info = getInsertionInfo(e);
            if (!info) { removeIndicator(); return; }
            setNestTarget(info.nestInto || null);
            if (info.before) {
                info.before.parentNode.insertBefore(indicator, info.before);
            } else {
                info.cont.appendChild(indicator);
            }
        });

        container.addEventListener('dragleave', (e) => {
            if (e.relatedTarget && container.contains(e.relatedTarget)) return;
            removeIndicator();
        });

        container.addEventListener('drop', (e) => {
            e.preventDefault();
            if (!dragged) return;
            const info = getInsertionInfo(e);
            removeIndicator();
            if (!info) return;
            // The row-total column and top-level groups stay at the outer level only.
            // A subgroup may also move into a (top-level) group's column list.
            const isSubgroup = dragged.classList.contains('matrix-group') && dragged.parentElement !== container;
            if ((dragged.classList.contains('matrix-group') || dragged.classList.contains('matrix-row-total-column')) && info.cont !== container) {
                // A top-level group is only accepted where getInsertionInfo chose to nest it.
                const nestsTopGroup = !!info.nestInto && !isSubgroup && dragged.classList.contains('matrix-group');
                if (!(isSubgroup || nestsTopGroup) || dragged.contains(info.cont)) return;
            }
            if (info.nestInto) this._setGroupCollapsed(info.nestInto, false);
            if (info.before) {
                info.cont.insertBefore(dragged, info.before);
            } else {
                info.cont.appendChild(dragged);
            }
            this._syncGroupDepth();
            this.updateConfig(modalElement);
        });

        // Set draggable="true" on all items, current and future
        const markDraggable = () => {
            container.querySelectorAll('.matrix-column:not([draggable]), .matrix-group:not([draggable]), .matrix-row-total-column:not([draggable])')
                .forEach(el => el.setAttribute('draggable', 'true'));
        };
        markDraggable();
        const obs = new MutationObserver(markDraggable);
        obs.observe(container, { childList: true, subtree: true });
        if (modalElement._dndObserver) modalElement._dndObserver.disconnect();
        modalElement._dndObserver = obs;
    },

    populateVariableOptions(variableSelect, modalElement) {
        // Get template variables from global scope (set in form_builder.html)
        const templateVariables = window.templateVariables || {};
        const metadata = Array.isArray(window.builtInMetadataVariables) ? window.builtInMetadataVariables : [];
        variableSelect.replaceChildren();
        {
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select Variable...';
            variableSelect.appendChild(placeholder);
        }

        // Metadata group (built-in tokens)
        if (metadata.length > 0) {
            const og = document.createElement('optgroup');
            og.label = 'Metadata';
            metadata.forEach((m) => {
                const key = String(m.key || '').trim();
                if (!key) return;
                const label = String(m.label || '').trim();
                const option = document.createElement('option');
                option.value = key;
                option.textContent = label ? `[${key}] — ${label}` : `[${key}]`;
                og.appendChild(option);
            });
            variableSelect.appendChild(og);
        }

        // Template variables group
        const variableNames = Object.keys(templateVariables);
        if (variableNames.length > 0) {
            const og = document.createElement('optgroup');
            og.label = 'Template Variables';
            variableNames.forEach((varName) => {
                const option = document.createElement('option');
                option.value = varName;
                option.textContent = `[${varName}]`;
                og.appendChild(option);
            });
            variableSelect.appendChild(og);
        }
    },

    removeRow(button) {
        const row = button.closest('.matrix-row');
        if (row) row.remove();
    },

    removeColumn(button) {
        const column = button.closest('.matrix-column');
        const modalElement = column?.closest('.modal') || document.querySelector('.item-modal');
        if (column) column.remove();
        // Update auto-load visibility after removing column
        if (modalElement) {
            this.updateAutoLoadVisibility(modalElement);
        }
    },

    moveRow(button, direction) {
        const row = button.closest('.matrix-row');
        const container = row ? row.parentElement : null;
        if (!row || !container) return;
        if (direction === 'up' && row.previousElementSibling) {
            container.insertBefore(row, row.previousElementSibling);
        } else if (direction === 'down' && row.nextElementSibling) {
            container.insertBefore(row.nextElementSibling, row);
        }
    },

    moveColumn(button, direction) {
        const column = button.closest('.matrix-column');
        const container = column ? column.parentElement : null;
        if (!column || !container) return;
        if (direction === 'up' && column.previousElementSibling) {
            container.insertBefore(column, column.previousElementSibling);
        } else if (direction === 'down' && column.nextElementSibling) {
            container.insertBefore(column.nextElementSibling, column);
        }
    },

    setupDisplayOptions(modalElement) {
        const rowTotalsCheckbox = Utils.getElementById('matrix-show-row-totals');
        const columnTotalsCheckbox = Utils.getElementById('matrix-show-column-totals');
        const includeTotalsInApiCheckbox = Utils.getElementById('matrix-include-totals-in-api');
        const rowTotalManualCheckbox = Utils.getElementById('matrix-row-total-manual-enabled');
        const rowTotalValidationSelect = Utils.getElementById('matrix-row-total-validation');
        const autoLoadCheckbox = Utils.getElementById('matrix-auto-load-entities');
        const autoLoadWrapper = Utils.getElementById('matrix-auto-load-entities-wrapper');
        const highlightManualRowsCheckbox = Utils.getElementById('matrix-highlight-manual-rows');
        const legendTextInput = Utils.getElementById('matrix-legend-text');
        const legendTextWrapper = Utils.getElementById('matrix-legend-text-wrapper');
        const legendHideBtn = Utils.getElementById('matrix-legend-hide-btn');
        const legendHideInput = Utils.getElementById('matrix-legend-hide');

        if (rowTotalsCheckbox) {
            if (!rowTotalsCheckbox._matrixConfigListenerAdded) {
                rowTotalsCheckbox.addEventListener('change', () => {
                    const columnsContainer = Utils.getElementById('matrix-columns-container');
                    if (rowTotalsCheckbox.checked) {
                        const raw = columnsContainer?.dataset.rowTotalPosition;
                        const remembered = raw === undefined || raw === '' ? undefined : Number(raw);
                        this.syncRowTotalColumn(
                            modalElement,
                            remembered !== undefined && Number.isFinite(remembered) ? remembered : undefined
                        );
                    } else if (columnsContainer) {
                        const current = this._rowTotalPositionFromDom(columnsContainer);
                        if (current !== null) columnsContainer.dataset.rowTotalPosition = String(current);
                        columnsContainer.querySelectorAll('.matrix-row-total-column').forEach(el => el.remove());
                    }
                    this.updateRowTotalOptionsVisibility(modalElement);
                    this.updateIncludeTotalsInApiVisibility(modalElement);
                    this.updateConfig(modalElement);
                });
                rowTotalsCheckbox._matrixConfigListenerAdded = true;
            }
        }
        if (rowTotalManualCheckbox) {
            if (!rowTotalManualCheckbox._matrixConfigListenerAdded) {
                rowTotalManualCheckbox.addEventListener('change', () => {
                    this.updateRowTotalOptionsVisibility(modalElement);
                    this.updateConfig(modalElement);
                });
                rowTotalManualCheckbox._matrixConfigListenerAdded = true;
            }
        }
        if (rowTotalValidationSelect) {
            if (!rowTotalValidationSelect._matrixConfigListenerAdded) {
                rowTotalValidationSelect.addEventListener('change', () => this.updateConfig(modalElement));
                rowTotalValidationSelect._matrixConfigListenerAdded = true;
            }
        }
        if (columnTotalsCheckbox) {
            if (!columnTotalsCheckbox._matrixConfigListenerAdded) {
                columnTotalsCheckbox.addEventListener('change', () => {
                    this.updateIncludeTotalsInApiVisibility(modalElement);
                    this.updateConfig(modalElement);
                });
                columnTotalsCheckbox._matrixConfigListenerAdded = true;
            }
        }
        if (includeTotalsInApiCheckbox) {
            if (!includeTotalsInApiCheckbox._matrixConfigListenerAdded) {
                includeTotalsInApiCheckbox.addEventListener('change', () => this.updateConfig(modalElement));
                includeTotalsInApiCheckbox._matrixConfigListenerAdded = true;
            }
        }
        if (autoLoadCheckbox) {
            if (!autoLoadCheckbox._matrixConfigListenerAdded) {
                autoLoadCheckbox.addEventListener('change', () => {
                    this.updateOwnRowsVisibility(modalElement);
                    this.updateConfig(modalElement);
                });
                autoLoadCheckbox._matrixConfigListenerAdded = true;
            }
        }
        const includeOwnRowsCheckbox = Utils.getElementById('matrix-include-own-rows');
        const ownRowsTemplateSelect = Utils.getElementById('matrix-own-rows-template');
        const ownRowsItemSelect = Utils.getElementById('matrix-own-rows-item');
        const ownRowsPeriodSelect = Utils.getElementById('matrix-own-rows-period');
        if (includeOwnRowsCheckbox && !includeOwnRowsCheckbox._matrixConfigListenerAdded) {
            includeOwnRowsCheckbox.addEventListener('change', () => {
                const wrapper = Utils.getElementById('matrix-include-own-rows-wrapper');
                if (!includeOwnRowsCheckbox.checked && wrapper) {
                    delete wrapper.dataset.pendingSpec;
                }
                this.updateOwnRowsVisibility(modalElement);
                if (includeOwnRowsCheckbox.checked) {
                    const selectedTemplate = Utils.getElementById('matrix-own-rows-template')?.value || '';
                    this._populateOwnRowsSelects(modalElement, selectedTemplate, '', '');
                }
                this.updateConfig(modalElement);
            });
            includeOwnRowsCheckbox._matrixConfigListenerAdded = true;
        }
        if (ownRowsTemplateSelect && !ownRowsTemplateSelect._matrixConfigListenerAdded) {
            ownRowsTemplateSelect.addEventListener('change', () => {
                if (this._ownRowsPopulating) return;
                const wrapper = Utils.getElementById('matrix-include-own-rows-wrapper');
                if (wrapper) delete wrapper.dataset.pendingSpec;
                this._populateOwnRowsSelects(modalElement, ownRowsTemplateSelect.value, '', '');
            });
            ownRowsTemplateSelect._matrixConfigListenerAdded = true;
        }
        [ownRowsItemSelect, ownRowsPeriodSelect].forEach(select => {
            if (select && !select._matrixConfigListenerAdded) {
                select.addEventListener('change', () => {
                    if (this._ownRowsPopulating) return;
                    const wrapper = Utils.getElementById('matrix-include-own-rows-wrapper');
                    if (wrapper) delete wrapper.dataset.pendingSpec;
                    this.updateConfig(modalElement);
                });
                select._matrixConfigListenerAdded = true;
            }
        });
        if (highlightManualRowsCheckbox) {
            if (!highlightManualRowsCheckbox._matrixHighlightListenerAdded) {
                highlightManualRowsCheckbox.addEventListener('change', () => {
                    // Show/hide legend text input based on checkbox state
                    this.updateLegendTextVisibility(modalElement);
                    this.updateConfig(modalElement);
                });
                highlightManualRowsCheckbox._matrixHighlightListenerAdded = true;
            }
        }
        if (legendTextInput) {
            if (!legendTextInput._matrixLegendListenerAdded) {
                legendTextInput.addEventListener('input', () => this.updateConfig(modalElement));
                legendTextInput.addEventListener('change', () => this.updateConfig(modalElement));
                legendTextInput._matrixLegendListenerAdded = true;
            }
        }
        if (legendHideBtn) {
            if (!legendHideBtn._matrixLegendHideListenerAdded) {
                legendHideBtn.addEventListener('click', () => {
                    this.toggleLegendHide(modalElement);
                });
                legendHideBtn._matrixLegendHideListenerAdded = true;
            }
        }

        // Check if any column is a variable and show/hide auto-load checkbox
        this.updateAutoLoadVisibility(modalElement);
        this.updateOwnRowsVisibility(modalElement);

        // Update legend text visibility on initial load
        this.updateLegendTextVisibility(modalElement);

        // Initialize legend hide button state
        this.initializeLegendHideButton(modalElement);
        this.updateRowTotalOptionsVisibility(modalElement);
        this.updateIncludeTotalsInApiVisibility(modalElement);
    },

    /**
     * Show/hide manual row total sub-options based on Show Row Totals / Allow manual.
     */
    updateRowTotalOptionsVisibility(modalElement) {
        const rowTotalsCheckbox = Utils.getElementById('matrix-show-row-totals');
        const optionsWrapper = Utils.getElementById('matrix-row-total-options-wrapper');
        const rowTotalManualCheckbox = Utils.getElementById('matrix-row-total-manual-enabled');
        const validationWrapper = Utils.getElementById('matrix-row-total-validation-wrapper');
        const showRowTotals = rowTotalsCheckbox ? rowTotalsCheckbox.checked : true;

        if (optionsWrapper) {
            if (showRowTotals) {
                optionsWrapper.classList.remove('hidden');
            } else {
                optionsWrapper.classList.add('hidden');
            }
        }

        if (validationWrapper) {
            const manualEnabled = rowTotalManualCheckbox ? rowTotalManualCheckbox.checked : false;
            if (showRowTotals && manualEnabled) {
                validationWrapper.classList.remove('hidden');
            } else {
                validationWrapper.classList.add('hidden');
            }
        }
    },

    /**
     * Hide the "Include Calculated Totals in API" toggle when neither Show Row Totals
     * nor Show Column Totals is enabled — with no totals shown at all, there is
     * nothing for the API-inclusion flag to control.
     */
    updateIncludeTotalsInApiVisibility(modalElement) {
        const rowTotalsCheckbox = Utils.getElementById('matrix-show-row-totals');
        const columnTotalsCheckbox = Utils.getElementById('matrix-show-column-totals');
        const wrapper = Utils.getElementById('matrix-include-totals-in-api-wrapper');
        if (!wrapper) return;
        const showRowTotals = rowTotalsCheckbox ? rowTotalsCheckbox.checked : true;
        const showColumnTotals = columnTotalsCheckbox ? columnTotalsCheckbox.checked : true;

        if (showRowTotals || showColumnTotals) {
            wrapper.classList.remove('hidden');
        } else {
            wrapper.classList.add('hidden');
        }
    },

    /**
     * Initialize legend hide button state on load
     */
    initializeLegendHideButton(modalElement) {
        const legendHideInput = Utils.getElementById('matrix-legend-hide');
        const legendTextInput = Utils.getElementById('matrix-legend-text');

        if (legendHideInput) {
            const isHidden = legendHideInput.value === 'true';

            // Update text input state
            if (legendTextInput) {
                if (isHidden) {
                    legendTextInput.disabled = true;
                    legendTextInput.classList.add('bg-gray-100', 'cursor-not-allowed');
                } else {
                    legendTextInput.disabled = false;
                    legendTextInput.classList.remove('bg-gray-100', 'cursor-not-allowed');
                }
            }
        }
    },

    /**
     * Show/hide legend text input based on highlight manual rows checkbox
     */
    updateLegendTextVisibility(modalElement) {
        const highlightManualRowsCheckbox = Utils.getElementById('matrix-highlight-manual-rows');
        const legendTextWrapper = Utils.getElementById('matrix-legend-text-wrapper');

        if (highlightManualRowsCheckbox && legendTextWrapper) {
            if (highlightManualRowsCheckbox.checked) {
                legendTextWrapper.classList.remove('hidden');
            } else {
                legendTextWrapper.classList.add('hidden');
            }
        }
    },

    /**
     * Toggle legend hide/show state
     */
    toggleLegendHide(modalElement) {
        const legendHideBtn = Utils.getElementById('matrix-legend-hide-btn');
        const legendHideInput = Utils.getElementById('matrix-legend-hide');
        const legendTextInput = Utils.getElementById('matrix-legend-text');

        if (!legendHideBtn || !legendHideInput) return;

        const isHidden = legendHideInput.value === 'true';
        const newState = !isHidden;
        legendHideInput.value = String(newState);

        // Update button icon, text, and title
        const icon = legendHideBtn.querySelector('i');
        const textSpan = legendHideBtn.querySelector('span');

        if (newState) {
            // Legend is hidden
            if (icon) {
                icon.className = 'fas fa-eye-slash w-4 h-4 mr-1';
            }
            if (textSpan) {
                textSpan.textContent = 'Legend hidden';
            } else {
                const span = document.createElement('span');
                span.textContent = 'Legend hidden';
                legendHideBtn.appendChild(span);
            }
            legendHideBtn.title = 'Legend is hidden - click to show';
            legendHideBtn.classList.remove('text-gray-600');
            legendHideBtn.classList.add('text-gray-500');

            // Grey out the text input
            if (legendTextInput) {
                legendTextInput.disabled = true;
                legendTextInput.classList.add('bg-gray-100', 'cursor-not-allowed');
            }
        } else {
            // Legend is shown
            if (icon) {
                icon.className = 'fas fa-eye w-4 h-4 mr-1';
            }
            if (textSpan) {
                textSpan.textContent = 'Legend shown';
            } else {
                const span = document.createElement('span');
                span.textContent = 'Legend shown';
                legendHideBtn.appendChild(span);
            }
            legendHideBtn.title = 'Legend is shown - click to hide';
            legendHideBtn.classList.remove('text-gray-500');
            legendHideBtn.classList.add('text-gray-600');

            // Enable the text input
            if (legendTextInput) {
                legendTextInput.disabled = false;
                legendTextInput.classList.remove('bg-gray-100', 'cursor-not-allowed');
            }
        }

        this.updateConfig(modalElement);
    },

    /**
     * Check if at least one column is a variable and show/hide auto-load checkbox
     */
    updateAutoLoadVisibility(modalElement) {
        const autoLoadWrapper = Utils.getElementById('matrix-auto-load-entities-wrapper');
        if (!autoLoadWrapper) return;

        const columnsContainer = Utils.getElementById('matrix-columns-container');
        if (!columnsContainer) {
            autoLoadWrapper.classList.add('hidden');
            return;
        }

        // Check if at least one column has is_variable checked
        const columns = columnsContainer.querySelectorAll('.matrix-column');
        let hasVariableColumn = false;

        columns.forEach(columnDiv => {
            const isVariableCheckbox = columnDiv.querySelector('.column-is-variable');
            if (isVariableCheckbox && isVariableCheckbox.checked) {
                hasVariableColumn = true;
            }
        });

        // Show/hide the auto-load checkbox based on whether any column is a variable
        if (hasVariableColumn) {
            autoLoadWrapper.classList.remove('hidden');
        } else {
            autoLoadWrapper.classList.add('hidden');
            // Also uncheck the checkbox if hidden
            const autoLoadCheckbox = Utils.getElementById('matrix-auto-load-entities');
            if (autoLoadCheckbox) {
                autoLoadCheckbox.checked = false;
            }
        }
        this.updateOwnRowsVisibility(modalElement);
    },

    /**
     * Show the "rows from another form" options only while auto-load is available and on.
     */
    updateOwnRowsVisibility(modalElement) {
        const autoLoadWrapper = Utils.getElementById('matrix-auto-load-entities-wrapper');
        const autoLoadCheckbox = Utils.getElementById('matrix-auto-load-entities');
        const wrapper = Utils.getElementById('matrix-include-own-rows-wrapper');
        const options = Utils.getElementById('matrix-include-own-rows-options');
        const includeCheckbox = Utils.getElementById('matrix-include-own-rows');
        if (!wrapper) return;

        const autoLoadAvailable = autoLoadWrapper && !autoLoadWrapper.classList.contains('hidden');
        const autoLoadOn = autoLoadCheckbox ? autoLoadCheckbox.checked : false;
        if (autoLoadAvailable && autoLoadOn) {
            wrapper.classList.remove('hidden');
        } else {
            wrapper.classList.add('hidden');
        }
        if (options) {
            const showOptions = autoLoadAvailable && autoLoadOn && includeCheckbox && includeCheckbox.checked;
            options.classList.toggle('hidden', !showOptions);
        }
    },

    _ownRowsOption(value, label) {
        const option = document.createElement('option');
        option.value = value == null ? '' : String(value);
        option.textContent = label;
        return option;
    },

    async _ownRowsCatalog(sourceTemplateId) {
        const mgr = window.templateVariablesManager;
        const templateId = window.templateId;
        const versionInput = document.querySelector('input[name="version_id"]');
        const versionId = versionInput ? versionInput.value : '';
        if (mgr && Array.isArray(mgr.allTemplates) && mgr.allTemplates.length) {
            let items = [];
            if (sourceTemplateId) {
                items = await mgr.loadFormItemsForTemplate(parseInt(sourceTemplateId, 10));
            }
            const assignments = mgr.assignmentsByTemplate || {};
            const periods = sourceTemplateId
                ? (assignments[sourceTemplateId] || assignments[String(sourceTemplateId)] || [])
                : [];
            return { templates: mgr.allTemplates, items: items || [], periods };
        }
        if (!templateId) return { templates: [], items: [], periods: [] };
        const params = new URLSearchParams();
        if (versionId) params.set('version_id', versionId);
        if (sourceTemplateId) params.set('source_template_id', String(sourceTemplateId));
        const response = await fetch(`/admin/templates/${templateId}/variables/options?${params}`, {
            credentials: 'same-origin',
            headers: { Accept: 'application/json' },
        });
        if (!response.ok) return { templates: [], items: [], periods: [] };
        const data = await response.json();
        const assignments = data.assignments_by_template || {};
        const periods = sourceTemplateId
            ? (assignments[sourceTemplateId] || assignments[String(sourceTemplateId)] || [])
            : [];
        return {
            templates: data.templates || [],
            items: data.form_items || [],
            periods,
        };
    },

    async _populateOwnRowsSelects(modalElement, selectedTemplateId, selectedItemId, selectedPeriod) {
        const templateSelect = Utils.getElementById('matrix-own-rows-template');
        const itemSelect = Utils.getElementById('matrix-own-rows-item');
        const periodSelect = Utils.getElementById('matrix-own-rows-period');
        if (!templateSelect || !itemSelect || !periodSelect) return;
        const token = (this._ownRowsLoadToken || 0) + 1;
        this._ownRowsLoadToken = token;
        const templateCatalog = await this._ownRowsCatalog(null);
        if (token !== this._ownRowsLoadToken) return;
        const templateId = selectedTemplateId ? String(selectedTemplateId) : '';
        this._ownRowsPopulating = true;
        try {
            templateSelect.replaceChildren(this._ownRowsOption('', 'Select a template'));
            (templateCatalog.templates || []).forEach(template => {
                const name = template.name || `Template ${template.id}`;
                templateSelect.appendChild(this._ownRowsOption(template.id, name));
            });
            if (templateId && !Array.from(templateSelect.options).some(option => option.value === templateId)) {
                templateSelect.appendChild(this._ownRowsOption(templateId, `Template ${templateId}`));
            }
            templateSelect.value = templateId;

            itemSelect.replaceChildren(this._ownRowsOption('', 'Select a matrix'));
            periodSelect.querySelectorAll('option[data-own-rows-period="concrete"]').forEach(option => option.remove());
            if (templateId) {
                const sourceCatalog = await this._ownRowsCatalog(templateId);
                if (token !== this._ownRowsLoadToken) return;
                (sourceCatalog.items || []).forEach(item => {
                    if (item.item_type !== 'matrix' && item.item_type !== 'matrix_table') return;
                    let label = (item.label || '').trim();
                    if (!label) {
                        const codes = Array.isArray(item.matrix_columns) ? item.matrix_columns : [];
                        const preview = codes.slice(0, 3).join(', ') + (codes.length > 3 ? ', …' : '');
                        label = preview ? `Matrix (${preview})` : 'Matrix';
                    }
                    itemSelect.appendChild(this._ownRowsOption(item.id, `${item.id}: ${label}`));
                });
                const itemId = selectedItemId ? String(selectedItemId) : '';
                if (itemId && !Array.from(itemSelect.options).some(option => option.value === itemId)) {
                    itemSelect.appendChild(this._ownRowsOption(itemId, `${itemId}: not in this template's published version`));
                }
                const seenPeriods = new Set(Array.from(periodSelect.options).map(option => option.value));
                (sourceCatalog.periods || []).forEach(period => {
                    const name = period.period_name || '';
                    if (!name || seenPeriods.has(name)) return;
                    seenPeriods.add(name);
                    const option = this._ownRowsOption(name, name);
                    option.dataset.ownRowsPeriod = 'concrete';
                    periodSelect.appendChild(option);
                });
                const period = selectedPeriod ? String(selectedPeriod) : '';
                if (period && !seenPeriods.has(period)) {
                    const option = this._ownRowsOption(period, period);
                    option.dataset.ownRowsPeriod = 'concrete';
                    periodSelect.appendChild(option);
                }
                if (itemId) itemSelect.value = itemId;
                if (period) periodSelect.value = period;
            }
        } finally {
            this._ownRowsPopulating = false;
        }
        if (token === this._ownRowsLoadToken) {
            this.updateConfig(modalElement);
        }
    },

    _readIncludeOwnMatrixRows() {
        const autoLoadCheckbox = Utils.getElementById('matrix-auto-load-entities');
        const includeCheckbox = Utils.getElementById('matrix-include-own-rows');
        const wrapper = Utils.getElementById('matrix-include-own-rows-wrapper');
        if (!autoLoadCheckbox || !autoLoadCheckbox.checked || !includeCheckbox || !includeCheckbox.checked) {
            return null;
        }
        const templateId = Utils.getElementById('matrix-own-rows-template')?.value || '';
        const itemId = Utils.getElementById('matrix-own-rows-item')?.value || '';
        const period = Utils.getElementById('matrix-own-rows-period')?.value || '';
        if (templateId && itemId && period) {
            const parsedTemplate = parseInt(templateId, 10);
            const parsedItem = parseInt(itemId, 10);
            if (!Number.isFinite(parsedTemplate) || !Number.isFinite(parsedItem)) return null;
            return {
                enabled: true,
                source_template_id: parsedTemplate,
                source_form_item_id: parsedItem,
                source_assignment_period: period,
            };
        }
        if (wrapper && wrapper.dataset.pendingSpec) {
            try {
                const pending = JSON.parse(wrapper.dataset.pendingSpec);
                if (pending && pending.enabled && pending.source_template_id && pending.source_form_item_id && pending.source_assignment_period) {
                    return pending;
                }
            } catch (_) {}
        }
        return null;
    },

    _restoreIncludeOwnMatrixRows(modalElement, spec) {
        const includeCheckbox = Utils.getElementById('matrix-include-own-rows');
        const wrapper = Utils.getElementById('matrix-include-own-rows-wrapper');
        const enabled = !!spec && spec.enabled === true;
        if (includeCheckbox) includeCheckbox.checked = enabled;
        if (wrapper) {
            if (enabled && spec.source_template_id && spec.source_form_item_id && spec.source_assignment_period) {
                wrapper.dataset.pendingSpec = JSON.stringify({
                    enabled: true,
                    source_template_id: parseInt(spec.source_template_id, 10),
                    source_form_item_id: parseInt(spec.source_form_item_id, 10),
                    source_assignment_period: String(spec.source_assignment_period),
                });
            } else {
                delete wrapper.dataset.pendingSpec;
            }
        }
        this.updateOwnRowsVisibility(modalElement);
        if (!enabled) return;
        this._populateOwnRowsSelects(
            modalElement,
            spec.source_template_id,
            spec.source_form_item_id,
            spec.source_assignment_period
        ).catch(error => {
            console.warn('Failed to load own-matrix row source options:', error);
        });
    },

    setupRowModeListeners(modalElement) {
        const rowModeRadios = modalElement.querySelectorAll('input[name="matrix_row_mode"]');
        const manualSection = modalElement.querySelector('#matrix-manual-rows-section');
        const listLibrarySection = modalElement.querySelector('#matrix-list-library-section');
        const hybridTabBar = modalElement.querySelector('#matrix-hybrid-tab-bar');
        const updateRowModeVisibility = () => {
            const selectedMode = modalElement.querySelector('input[name="matrix_row_mode"]:checked')?.value;
            if (selectedMode === 'manual') {
                Utils.showElement(manualSection);
                Utils.hideElement(listLibrarySection);
                Utils.hideElement(hybridTabBar);
                manualSection?.classList.remove('pt-4', 'border', 'border-t-0', 'border-gray-200', 'rounded-b-md', 'rounded-tr-md', 'p-4');
                listLibrarySection?.classList.remove('pt-4', 'border', 'border-t-0', 'border-gray-200', 'rounded-b-md', 'rounded-tr-md', 'p-4');
                manualSection?.classList.add('mb-4');
                listLibrarySection?.classList.add('mb-4');
            } else if (selectedMode === 'list_library') {
                Utils.hideElement(manualSection);
                Utils.showElement(listLibrarySection);
                Utils.hideElement(hybridTabBar);
                manualSection?.classList.remove('pt-4', 'border', 'border-t-0', 'border-gray-200', 'rounded-b-md', 'rounded-tr-md', 'p-4');
                listLibrarySection?.classList.remove('pt-4', 'border', 'border-t-0', 'border-gray-200', 'rounded-b-md', 'rounded-tr-md', 'p-4');
                manualSection?.classList.add('mb-4');
                listLibrarySection?.classList.add('mb-4');
            } else if (selectedMode === 'hybrid') {
                Utils.showElement(hybridTabBar);
                // Style both panels as tabbed panes
                [manualSection, listLibrarySection].forEach(sec => {
                    sec?.classList.add('border', 'border-t-0', 'border-gray-200', 'rounded-b-md', 'rounded-tr-md', 'p-4');
                    sec?.classList.remove('mb-4');
                });
                // Activate the Fixed Rows tab by default (unless list tab already active)
                const activeTab = hybridTabBar.querySelector('.matrix-hybrid-tab.border-orange-500');
                this._activateHybridTab(modalElement, activeTab?.dataset.target || 'matrix-manual-rows-section');
            }
            this.updateConfig(modalElement);
        };
        rowModeRadios.forEach(radio => {
            if (!radio._matrixRowModeListenerAdded) {
                radio.addEventListener('change', updateRowModeVisibility);
                radio._matrixRowModeListenerAdded = true;
            }
        });
        // Wire hybrid tab clicks
        hybridTabBar?.querySelectorAll('.matrix-hybrid-tab').forEach(tab => {
            if (!tab._hybridTabListenerAdded) {
                tab.addEventListener('click', () => this._activateHybridTab(modalElement, tab.dataset.target));
                tab._hybridTabListenerAdded = true;
            }
        });
        updateRowModeVisibility();
    },

    /** Switch the visible panel inside the hybrid tab layout. */
    _activateHybridTab(modalElement, targetId) {
        const manualSection = modalElement.querySelector('#matrix-manual-rows-section');
        const listLibrarySection = modalElement.querySelector('#matrix-list-library-section');
        const hybridTabBar = modalElement.querySelector('#matrix-hybrid-tab-bar');
        if (!hybridTabBar) return;

        // Panel visibility
        [manualSection, listLibrarySection].forEach(sec => {
            if (!sec) return;
            if (sec.id === targetId) {
                Utils.showElement(sec);
            } else {
                Utils.hideElement(sec);
            }
        });

        // Tab active styling
        hybridTabBar.querySelectorAll('.matrix-hybrid-tab').forEach(tab => {
            const isActive = tab.dataset.target === targetId;
            tab.classList.toggle('text-orange-600', isActive);
            tab.classList.toggle('border-orange-500', isActive);
            tab.classList.toggle('bg-white', isActive);
            tab.classList.toggle('text-gray-500', !isActive);
            tab.classList.toggle('border-transparent', !isActive);
            tab.classList.toggle('bg-transparent', !isActive);
        });
    },

    setupListLibrary(modalElement) {
        const listSelect = modalElement.querySelector('#matrix-list-select');
        const displayColumnSelect = modalElement.querySelector('#matrix-list-display-column');
        const groupBySelect = modalElement.querySelector('#matrix-group-by-column');
        const groupDropdownEnabled = modalElement.querySelector('#matrix-group-dropdown-enabled');
        const groupTableEnabled = modalElement.querySelector('#matrix-group-table-enabled');
        const groupTotalsEnabled = modalElement.querySelector('#matrix-group-totals-enabled');
        const addFilterBtn = modalElement.querySelector('#matrix-list-add-filter-btn');
        if (listSelect && displayColumnSelect) {
            if (!listSelect._matrixListSelectionListenerAdded) {
                listSelect.addEventListener('change', (e) => {
                    this.handleListSelection(modalElement, e.target.value);
                });
                listSelect._matrixListSelectionListenerAdded = true;
            }
        }
        if (displayColumnSelect) {
            if (!displayColumnSelect._matrixConfigListenerAdded) {
                displayColumnSelect.addEventListener('change', () => this.updateConfig(modalElement));
                displayColumnSelect._matrixConfigListenerAdded = true;
            }
        }
        if (groupBySelect) {
            if (!groupBySelect._matrixGroupingListenerAdded) {
                groupBySelect.addEventListener('change', () => {
                    this.updateGroupingControlsVisibility(modalElement);
                    this.updateConfig(modalElement);
                });
                groupBySelect._matrixGroupingListenerAdded = true;
            }
        }
        if (groupDropdownEnabled) {
            if (!groupDropdownEnabled._matrixConfigListenerAdded) {
                groupDropdownEnabled.addEventListener('change', () => this.updateConfig(modalElement));
                groupDropdownEnabled._matrixConfigListenerAdded = true;
            }
        }
        if (groupTableEnabled) {
            if (!groupTableEnabled._matrixConfigListenerAdded) {
                groupTableEnabled.addEventListener('change', () => {
                    this.updateGroupingControlsVisibility(modalElement);
                    this.updateConfig(modalElement);
                });
                groupTableEnabled._matrixConfigListenerAdded = true;
            }
        }
        if (groupTotalsEnabled && !groupTotalsEnabled._matrixConfigListenerAdded) {
            groupTotalsEnabled.addEventListener('change', () => this.updateConfig(modalElement));
            groupTotalsEnabled._matrixConfigListenerAdded = true;
        }
        const allowOtherCheckbox = modalElement.querySelector('#matrix-allow-other');
        if (allowOtherCheckbox && !allowOtherCheckbox._matrixConfigListenerAdded) {
            allowOtherCheckbox.addEventListener('change', () => this.updateConfig(modalElement));
            allowOtherCheckbox._matrixConfigListenerAdded = true;
        }
        if (addFilterBtn) {
            if (!addFilterBtn._matrixAddFilterListenerAdded) {
                addFilterBtn.addEventListener('click', () => {
                    this.addListFilter(modalElement);
                });
                addFilterBtn._matrixAddFilterListenerAdded = true;
            }
        }
    },

    async handleListSelection(modalElement, listId) {
        const version = this._listConfigVersion = (this._listConfigVersion || 0) + 1;
        const displayColumnWrapper = modalElement.querySelector('#matrix-display-column-wrapper');
        const displayColumnSelect = modalElement.querySelector('#matrix-list-display-column');
        const configContainer = modalElement.querySelector('#matrix-plugin-config-container');

        if (!listId) {
            Utils.hideElement(displayColumnWrapper);
            const groupByWrapper = modalElement.querySelector('#matrix-group-by-wrapper');
            if (groupByWrapper) Utils.hideElement(groupByWrapper);
            this.updateGroupingControlsVisibility(modalElement);
            if (configContainer) {
                configContainer.replaceChildren();
                configContainer.style.display = 'none';
            }
            return;
        }
        const selectedOption = modalElement.querySelector(`#matrix-list-select option[value="${listId}"]`);
        if (!selectedOption) return;
        const columnsConfig = JSON.parse(selectedOption.dataset.columns || '[]');
        displayColumnSelect.replaceChildren();
        {
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select Column...';
            displayColumnSelect.appendChild(placeholder);
        }
        columnsConfig.forEach(column => {
            // Skip name_translations field
            if (column.name === 'name_translations') {
                return;
            }

            const option = document.createElement('option');
            option.value = column.name;

            // Check if column is multilingual (has name_translations)
            const isMultilingual = column.multilingual === true ||
                                  (column.name === 'name' &&
                                   (listId === 'country_map' ||
                                    listId === 'national_society'));

            // Create display text with translation icon if multilingual
            let displayText = column.label || column.name;
            if (isMultilingual) {
                // Use Unicode translation icon (🌐) with tooltip
                displayText = `${displayText} 🌐`;
                option.dataset.multilingual = 'true';
                option.title = 'This field supports multiple languages and will display in the user\'s selected language';
            }

            option.textContent = displayText;
            displayColumnSelect.appendChild(option);
        });
        Utils.showElement(displayColumnWrapper);

        // Populate group-by column dropdown with same columns
        const groupByWrapper = modalElement.querySelector('#matrix-group-by-wrapper');
        const groupBySelect = modalElement.querySelector('#matrix-group-by-column');
        if (groupBySelect && groupByWrapper) {
            groupBySelect.replaceChildren();
            const noGroup = document.createElement('option');
            noGroup.value = '';
            noGroup.textContent = 'No grouping';
            groupBySelect.appendChild(noGroup);
            columnsConfig.forEach(column => {
                if (column.name === 'name_translations') return;
                const opt = document.createElement('option');
                opt.value = column.name;
                opt.textContent = column.label || column.name;
                groupBySelect.appendChild(opt);
            });
            Utils.showElement(groupByWrapper);
            this.updateGroupingControlsVisibility(modalElement);
        }

        // Get existing plugin config from matrix config if editing
        const configInput = Utils.getElementById('item-matrix-config');
        let existingConfig = {};
        if (configInput && configInput.value) {
            try {
                const matrixConfig = JSON.parse(configInput.value);
                existingConfig = matrixConfig.plugin_config || {};
            } catch (e) {
                // Ignore parse errors
            }
        }

        await this._loadListPluginConfigUI({
            configContainer,
            selectedOption,
            listId,
            existingConfig,
            onChange: () => this.updateConfig(modalElement),
            isStale: () => {
                const currentListSelect = modalElement.querySelector('#matrix-list-select');
                return this._listConfigVersion !== version || !currentListSelect || String(currentListSelect.value) !== String(listId);
            }
        });

        this.updateConfig(modalElement);
    },

    /**
     * Handle a change to a column's "Selectable header" list-library <select>.
     * Populates the row-label-column dropdown and loads any plugin-specific
     * config UI (e.g. Emergency Operations) for the chosen list, mirroring the
     * matrix-level "Table rows" list library flow above.
     */
    handleColumnHeaderListSelection(modalElement, columnDiv, listId) {
        this._populateColumnHeaderDisplayColumns(columnDiv, listId);
        this._loadColumnHeaderPluginConfig(modalElement, columnDiv, listId);
    },

    /**
     * Load (or clear) the plugin config UI for a column's selectable-header list.
     * Safe to call with an empty/falsy listId, which clears the panel.
     */
    async _loadColumnHeaderPluginConfig(modalElement, columnDiv, listId) {
        const configContainer = columnDiv.querySelector('.column-header-plugin-config-container');
        if (!configContainer) return;

        const version = (columnDiv._headerConfigVersion = (columnDiv._headerConfigVersion || 0) + 1);
        const listSelect = columnDiv.querySelector('.column-header-list-select');
        const selectedOption = listId ? listSelect?.querySelector(`option[value="${listId}"]`) : null;

        // Edit-mode restore stashes the saved plugin config on the column element
        // (see addColumn) so the freshly-fetched panel opens pre-filled.
        const existingConfig = columnDiv._pendingHeaderPluginConfig || {};
        columnDiv._pendingHeaderPluginConfig = null;

        await this._loadListPluginConfigUI({
            configContainer,
            selectedOption,
            listId,
            existingConfig,
            onChange: () => this.updateConfig(modalElement),
            isStale: () => columnDiv._headerConfigVersion !== version || String(listSelect?.value || '') !== String(listId || '')
        });

        this.updateConfig(modalElement);
    },

    /**
     * Generic: fetch and render a plugin's config-ui HTML into a container, wiring
     * up its exported JS handler (or falling back to basic change/input listeners).
     * Shared by the matrix-level "rows" list selector and each column's
     * "selectable header" list selector, since both resolve against the same
     * lookup-list / plugin config-ui API.
     *
     * @param {Object} opts
     * @param {HTMLElement} opts.configContainer - Where to render the fetched HTML
     * @param {HTMLOptionElement|null} opts.selectedOption - The chosen list's <option> (for data-has-config-ui / data-config-js-handler)
     * @param {string} opts.listId - The selected lookup list id
     * @param {Object} [opts.existingConfig] - Previously saved plugin config (for edit-mode restore)
     * @param {Function} opts.onChange - Called whenever a config value changes
     * @param {Function} [opts.isStale] - Called after the fetch resolves; skip applying results if it returns true
     */
    async _loadListPluginConfigUI({ configContainer, selectedOption, listId, existingConfig, onChange, isStale }) {
        if (!configContainer) return;

        const hasConfigUI = selectedOption?.dataset.hasConfigUi === 'true';
        if (!listId || !hasConfigUI) {
            configContainer.replaceChildren();
            configContainer.style.display = 'none';
            return;
        }

        try {
            const fetchFn = (window.getApiFetch && window.getApiFetch()) || ((url, opts) => ((window.getFetch && window.getFetch()) || fetch)(url, opts).then(r => r.ok ? r.json() : Promise.reject((window.httpErrorSync && window.httpErrorSync(r)) || new Error(`HTTP ${r.status}`))));
            const configB64 = btoa(unescape(encodeURIComponent(JSON.stringify(existingConfig || {}))));
            const data = await fetchFn(`/api/forms/lookup-lists/${encodeURIComponent(listId)}/config-ui?config_b64=${encodeURIComponent(configB64)}`).catch(() => null);
            if (typeof isStale === 'function' && isStale()) return;

            if (data && data.success && data.html) {
                this.setSanitizedHtml(configContainer, data.html);
                this._scopePluginConfigInputNames(configContainer);
                configContainer.style.display = 'block';
                await this._setupPluginConfigListeners(configContainer, selectedOption, listId, onChange);
            } else {
                configContainer.replaceChildren();
                configContainer.style.display = 'none';
            }
        } catch (error) {
            console.error('Error loading plugin config UI:', error);
            configContainer.replaceChildren();
            configContainer.style.display = 'none';
        }
    },

    updateGroupingControlsVisibility(modalElement) {
        const groupBySelect = modalElement.querySelector('#matrix-group-by-column');
        const controlsWrapper = modalElement.querySelector('#matrix-group-controls-wrapper');
        const dropdownCheckbox = modalElement.querySelector('#matrix-group-dropdown-enabled');
        const tableCheckbox = modalElement.querySelector('#matrix-group-table-enabled');
        const totalsCheckbox = modalElement.querySelector('#matrix-group-totals-enabled');
        const hasGroupingColumn = !!groupBySelect?.value;
        const tableGroupingOn = !tableCheckbox || tableCheckbox.checked;

        if (controlsWrapper) {
            if (hasGroupingColumn) {
                controlsWrapper.classList.remove('hidden');
            } else {
                controlsWrapper.classList.add('hidden');
            }
        }
        if (dropdownCheckbox) dropdownCheckbox.disabled = !hasGroupingColumn;
        if (tableCheckbox) tableCheckbox.disabled = !hasGroupingColumn;
        if (totalsCheckbox) totalsCheckbox.disabled = !hasGroupingColumn || !tableGroupingOn;
    },

    /**
     * Wire up change/input listeners for a freshly-rendered plugin config panel:
     * prefer the plugin's own exported JS handler (loaded from its static
     * directory if not already on window), falling back to generic listeners
     * that just call onChange for every input.
     */
    async _setupPluginConfigListeners(configContainer, selectedOption, listId, onChange) {
        const fallback = () => {
            configContainer.querySelectorAll('input, select, textarea').forEach(input => {
                input.addEventListener('change', onChange);
                input.addEventListener('input', onChange);
            });
        };

        // Check if the lookup list has a JavaScript handler specified
        const jsHandlerName = selectedOption?.dataset.configJsHandler;
        if (!jsHandlerName) {
            fallback();
            return;
        }

        // Try to load and call the plugin's JavaScript handler
        try {
            // Check if handler is already available globally
            let handler = window[jsHandlerName];

            // If not available, try to load it from the plugin's static directory
            if (!handler || typeof handler !== 'function') {
                // Try to import from the plugin's static JS directory
                // Plugin static files: /plugins/static/{plugin_name}/{path-under-plugin/static/}
                // e.g. /plugins/static/emergency_operations/js/matrix_config_handler.js
                const pluginName = this.getPluginNameFromListId(listId);
                if (pluginName) {
                    try {
                        // Prepend origin so the path resolves to the app server even when
                        // this module is served from a CDN (e.g. Azure Blob Storage).
                        const moduleUrl = `${window.location.origin}/plugins/static/${pluginName}/js/matrix_config_handler.js`;
                        const module = await import(moduleUrl);
                        handler = module[jsHandlerName] || module.default;
                    } catch (importError) {
                        console.warn(`Failed to import plugin handler for ${listId}:`, importError);
                    }
                }
            }

            // Call the plugin handler if found
            if (handler && typeof handler === 'function') {
                handler(configContainer, onChange);
            } else {
                console.warn(`Plugin config UI handler "${jsHandlerName}" not found for list ${listId}`);
                fallback();
            }
        } catch (error) {
            console.error(`Error setting up plugin config listeners for ${listId}:`, error);
            fallback();
        }
    },

    /**
     * Get plugin name from lookup list ID (for loading plugin-specific JS handlers)
     */
    getPluginNameFromListId(listId) {
        // Map known lookup list IDs to plugin names
        const pluginMap = {
            'emergency_operations': 'emergency_operations'
            // Add more mappings as needed
        };
        return pluginMap[listId] || null;
    },

    /**
     * Prefix plugin config input names with a per-panel scope id so identically-named
     * fields (e.g. emops_timeframe_mode) in the matrix rows panel and a column header
     * panel do not share one document-wide radio group.
     */
    _scopePluginConfigInputNames(container) {
        if (!container || container.dataset.pluginConfigScoped === 'true') return;
        const scope = Utils.generateUniqueId();
        container.dataset.pluginConfigScope = scope;
        container.dataset.pluginConfigScoped = 'true';
        container.querySelectorAll('input[name], select[name], textarea[name]').forEach(el => {
            const baseName = el.getAttribute('name');
            if (!baseName || baseName.includes('__')) return;
            el.dataset.configName = baseName;
            el.setAttribute('name', `${scope}__${baseName}`);
        });
    },

    _unscopePluginConfigKey(scopedName, container) {
        const scope = container?.dataset?.pluginConfigScope;
        if (scope && scopedName.startsWith(`${scope}__`)) {
            return scopedName.slice(scope.length + 2);
        }
        return scopedName;
    },

    /**
     * Generically read all named inputs inside a plugin config panel into a
     * plain object. Shared by the matrix-level "rows" plugin config panel and
     * each column's "selectable header" plugin config panel.
     */
    _extractPluginConfigFromContainer(container) {
        const pluginConfig = {};
        if (!container) return pluginConfig;

        const inputsByName = new Map();
        container.querySelectorAll('input, select, textarea').forEach(input => {
            const name = input.name;
            if (!name) return;
            const key = this._unscopePluginConfigKey(name, container);
            if (!inputsByName.has(key)) {
                inputsByName.set(key, []);
            }
            inputsByName.get(key).push(input);
        });

        inputsByName.forEach((inputs, name) => {
            const sample = inputs[0];
            if (sample.type === 'checkbox') {
                if (inputs.length === 1) {
                    pluginConfig[name] = inputs[0].checked;
                } else {
                    pluginConfig[name] = inputs
                        .filter(inp => inp.checked)
                        .map(inp => inp.value || true);
                }
            } else if (sample.type === 'radio') {
                const checked = inputs.find(inp => inp.checked);
                if (checked) {
                    pluginConfig[name] = checked.value;
                }
            } else if (sample.tagName === 'SELECT' && sample.multiple) {
                pluginConfig[name] = Array.from(sample.selectedOptions).map(opt => opt.value);
            } else if (sample.value !== undefined && sample.value !== null && sample.value !== '') {
                pluginConfig[name] = sample.value;
            }
        });

        return pluginConfig;
    },

    addListFilter(modalElement) {
        const filtersContainer = Utils.getElementById('matrix-list-filters-container');
        if (!filtersContainer) return;
        const filterDiv = document.createElement('div');
        filterDiv.className = 'matrix-filter-row flex items-center space-x-2 p-2 bg-gray-50 rounded border';
        const columnSelect = document.createElement('select');
        columnSelect.className = 'filter-column block w-1/3 py-1 pl-2 pr-7 border border-gray-300 bg-white rounded text-sm';
        columnSelect.replaceChildren();
        {
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Column...';
            columnSelect.appendChild(placeholder);
        }
        const listSelect = Utils.getElementById('matrix-list-select');
        const selectedListId = listSelect?.value;
        if (selectedListId) {
            const selectedOption = document.querySelector(`#matrix-list-select option[value="${selectedListId}"]`);
            if (selectedOption) {
                const columnsConfig = JSON.parse(selectedOption.dataset.columns || '[]');
                columnsConfig.forEach(column => {
                    const option = document.createElement('option');
                    option.value = column.name;
                    option.textContent = column.label || column.name;
                    columnSelect.appendChild(option);
                });
            }
        }
        const operatorSelect = document.createElement('select');
        operatorSelect.className = 'filter-operator block w-1/4 py-1 pl-2 pr-7 border border-gray-300 bg-white rounded text-sm';
        operatorSelect.replaceChildren();
        [
            ['equals', 'Equals'],
            ['not_equals', 'Not Equals'],
            ['contains', 'Contains'],
            ['not_contains', 'Not Contains']
        ].forEach(([value, label]) => {
            const opt = document.createElement('option');
            opt.value = value;
            opt.textContent = label;
            operatorSelect.appendChild(opt);
        });
        const valueInput = document.createElement('input');
        valueInput.type = 'text';
        valueInput.className = 'filter-value block w-1/3 py-1 px-2 border border-gray-300 rounded text-sm';
        valueInput.placeholder = 'Value...';
        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'text-red-600 hover:text-red-800 p-1';
        removeBtn.replaceChildren();
        {
            const icon = document.createElement('i');
            icon.className = 'fas fa-times w-3 h-3';
            removeBtn.appendChild(icon);
        }
        removeBtn.addEventListener('click', () => {
            filterDiv.remove();
            this.updateConfig(modalElement);
        });
        [columnSelect, operatorSelect, valueInput].forEach(element => {
            element.addEventListener('change', () => this.updateConfig(modalElement));
            element.addEventListener('input', () => this.updateConfig(modalElement));
        });
        filterDiv.appendChild(columnSelect);
        filterDiv.appendChild(operatorSelect);
        filterDiv.appendChild(valueInput);
        filterDiv.appendChild(removeBtn);
        filtersContainer.appendChild(filterDiv);
        this.updateConfig(modalElement);
    },

    updateConfig(modalElement) {
        const rowsContainer = Utils.getElementById('matrix-rows-container');
        const columnsContainer = Utils.getElementById('matrix-columns-container');
        const configInput = Utils.getElementById('item-matrix-config');
        if (!columnsContainer || !configInput) return;

        this.refreshCalculationSourceLists(modalElement);

        const columns = [];
        const column_groups = {};

        // Walk direct children: .matrix-group containers and standalone .matrix-column elements
        Array.from(columnsContainer.children).forEach(child => {
            if (child.classList.contains('matrix-group')) {
                const groupLabel = this._groupLabel(child);
                if (!groupLabel) return; // skip unnamed groups

                // Persist group label translations and an optional header colour.
                column_groups[groupLabel] = this._groupMeta(child);

                // Columns directly inside the group and inside its subgroups, in DOM order
                const seenSubgroups = new Set();
                this._collectGroupColumns(child).forEach(({ columnDiv, group, subgroup, subgroupEl }) => {
                    if (subgroup && !seenSubgroups.has(subgroupEl)) {
                        seenSubgroups.add(subgroupEl);
                        column_groups[`${group}${SUBGROUP_KEY_SEPARATOR}${subgroup}`] = this._groupMeta(subgroupEl);
                    }
                    const col = this._extractColumnConfig(columnDiv);
                    if (col) {
                        col.group = group;
                        if (subgroup) col.subgroup = subgroup;
                        columns.push(col);
                    }
                });
            } else if (child.classList.contains('matrix-column')) {
                const col = this._extractColumnConfig(child);
                if (col) columns.push(col);
            }
        });
        const showRowTotals = Utils.getElementById('matrix-show-row-totals')?.checked !== false;
        const showColumnTotals = Utils.getElementById('matrix-show-column-totals')?.checked !== false;
        const includeTotalsInApi = Utils.getElementById('matrix-include-totals-in-api')?.checked !== false;
        const rowTotalManualEnabled = Utils.getElementById('matrix-row-total-manual-enabled')?.checked === true;
        const rowTotalValidation = Utils.getElementById('matrix-row-total-validation')?.value || 'none';
        const autoLoadEntities = Utils.getElementById('matrix-auto-load-entities')?.checked === true;
        const highlightManualRows = Utils.getElementById('matrix-highlight-manual-rows')?.checked === true;
        const legendText = Utils.getElementById('matrix-legend-text')?.value?.trim() || 'Manually added row';
        const legendTextTranslationsInput = Utils.getElementById('matrix-legend-text-translations');
        const legendHideInput = Utils.getElementById('matrix-legend-hide');
        const legendHide = legendHideInput?.value === 'true';
        const selectedMode = modalElement.querySelector('input[name="matrix_row_mode"]:checked')?.value || 'manual';
        const config = {
            type: 'matrix',
            columns: columns,
            show_row_totals: showRowTotals,
            show_column_totals: showColumnTotals,
            include_calculated_totals_in_api: includeTotalsInApi,
            row_mode: selectedMode,
            highlight_manual_rows: highlightManualRows
        };

        if (showRowTotals) {
            config.row_total_manual_enabled = rowTotalManualEnabled;
            if (rowTotalManualEnabled) {
                config.row_total_validation = rowTotalValidation;
            }
            const rowTotalPosition = this._rowTotalPositionFromDom(columnsContainer);
            if (rowTotalPosition !== null && rowTotalPosition < columns.length) {
                config.row_total_position = rowTotalPosition;
            }
        }

        // Persist group label translations when groups are present
        if (Object.keys(column_groups).length > 0) {
            config.column_groups = column_groups;
        }

        // Add legend text and translations only if highlighting is enabled
        if (highlightManualRows) {
            config.legend_text = legendText;
            config.legend_hide = legendHide;
            if (legendTextTranslationsInput && legendTextTranslationsInput.value) {
                try {
                    const translations = JSON.parse(legendTextTranslationsInput.value);
                    if (Object.keys(translations).length > 0) {
                        config.legend_text_translations = translations;
                    }
                } catch (e) {
                    console.warn('Failed to parse legend text translations:', e);
                }
            }
        }

        // Add auto_load_entities only if at least one column is a variable
        const hasVariableColumn = columns.some(col => col.is_variable === true);
        if (hasVariableColumn) {
            config.auto_load_entities = autoLoadEntities;
            const ownMatrixRows = this._readIncludeOwnMatrixRows();
            if (ownMatrixRows) {
                config.include_own_matrix_rows = ownMatrixRows;
            }
        }

        const lookupTooltipLabelInput = Utils.getElementById('matrix-variable-lookup-tooltip-label');
        if (lookupTooltipLabelInput?.value?.trim()) {
            config.variable_lookup_tooltip_label = lookupTooltipLabelInput.value.trim();
        }
        const lookupTooltipLabelTranslationsInput = Utils.getElementById('matrix-variable-lookup-tooltip-label-translations');
        if (lookupTooltipLabelTranslationsInput?.value) {
            try {
                const parsed = JSON.parse(lookupTooltipLabelTranslationsInput.value);
                if (parsed && typeof parsed === 'object' && Object.values(parsed).some(v => String(v || '').trim())) {
                    config.variable_lookup_tooltip_label_translations = parsed;
                }
            } catch (_) {}
        }
        const submittedTooltipLabelInput = Utils.getElementById('matrix-variable-submitted-tooltip-label');
        if (submittedTooltipLabelInput?.value?.trim()) {
            config.variable_submitted_tooltip_label = submittedTooltipLabelInput.value.trim();
        }
        const submittedTooltipLabelTranslationsInput = Utils.getElementById('matrix-variable-submitted-tooltip-label-translations');
        if (submittedTooltipLabelTranslationsInput?.value) {
            try {
                const parsed = JSON.parse(submittedTooltipLabelTranslationsInput.value);
                if (parsed && typeof parsed === 'object' && Object.values(parsed).some(v => String(v || '').trim())) {
                    config.variable_submitted_tooltip_label_translations = parsed;
                }
            } catch (_) {}
        }

        if (selectedMode === 'manual' || selectedMode === 'hybrid') {
            if (rowsContainer) {
                const rows = [];
                rowsContainer.querySelectorAll('.matrix-row').forEach(rowDiv => {
                    const textInput = rowDiv.querySelector('.row-text');
                    const translationsInput = rowDiv.querySelector('.row-name-translations');
                    const text = textInput ? textInput.value.trim() : '';
                    if (!text) return;
                    let nameTranslations = {};
                    if (translationsInput && translationsInput.value) {
                        try {
                            const parsed = JSON.parse(translationsInput.value);
                            if (parsed && typeof parsed === 'object') {
                                const hasAny = Object.values(parsed).some(v => String(v || '').trim());
                                if (hasAny) nameTranslations = parsed;
                            }
                        } catch (_) {}
                    }
                    const rowEntry = { text };
                    if (Object.keys(nameTranslations).length > 0) rowEntry.name_translations = nameTranslations;
                    rows.push(rowEntry);
                });
                config.rows = rows;
            }
        }
        if (selectedMode === 'list_library' || selectedMode === 'hybrid') {
            const listSelect = Utils.getElementById('matrix-list-select');
            const displayColumnSelect = Utils.getElementById('matrix-list-display-column');
            const filtersContainer = Utils.getElementById('matrix-list-filters-container');
            const pluginConfigContainer = modalElement.querySelector('#matrix-plugin-config-container');

            if (listSelect?.value) {
                // Handle both numeric IDs and string IDs (for system lists like 'country_map')
                const listId = listSelect.value;
                const parsedId = parseInt(listId);
                // If it's a valid number, use it; otherwise use the string (for system lists)
                config.lookup_list_id = isNaN(parsedId) ? listId : parsedId;
            }
            if (displayColumnSelect?.value) {
                config.list_display_column = displayColumnSelect.value;
            }
            const groupByColumnSelect = Utils.getElementById('matrix-group-by-column');
            if (groupByColumnSelect?.value) {
                config.group_by_column = groupByColumnSelect.value;
                config.group_dropdown_enabled = Utils.getElementById('matrix-group-dropdown-enabled')?.checked !== false;
                config.group_table_enabled = Utils.getElementById('matrix-group-table-enabled')?.checked !== false;
                config.group_totals_enabled = Utils.getElementById('matrix-group-totals-enabled')?.checked === true;
            }
            const searchPlaceholderInput = Utils.getElementById('matrix-search-placeholder');
            if (searchPlaceholderInput?.value) {
                config.search_placeholder = searchPlaceholderInput.value;
            }
            const searchPlaceholderTranslationsInput = Utils.getElementById('matrix-search-placeholder-translations');
            if (searchPlaceholderTranslationsInput?.value) {
                try {
                    const parsed = JSON.parse(searchPlaceholderTranslationsInput.value);
                    if (parsed && typeof parsed === 'object' && Object.values(parsed).some(v => String(v || '').trim())) {
                        config.search_placeholder_translations = parsed;
                    }
                } catch (_) {}
            }
            if (filtersContainer) {
                const filters = [];
                filtersContainer.querySelectorAll('.matrix-filter-row').forEach(filterRow => {
                    const column = filterRow.querySelector('.filter-column')?.value;
                    const operator = filterRow.querySelector('.filter-operator')?.value;
                    const value = filterRow.querySelector('.filter-value')?.value;
                    if (column && operator && value) {
                        filters.push({ column, operator, value });
                    }
                });
                config.list_filters = filters;
            }

            const allowOtherCheckbox = Utils.getElementById('matrix-allow-other');
            config.allow_other = allowOtherCheckbox?.checked === true;

            // Collect plugin-specific configuration generically
            if (pluginConfigContainer) {
                const pluginConfig = this._extractPluginConfigFromContainer(pluginConfigContainer);
                if (Object.keys(pluginConfig).length > 0) {
                    config.plugin_config = pluginConfig;
                }
            }

            if (selectedMode !== 'hybrid') {
                config.rows = [];
            }
        }
        configInput.name = 'matrix_config';
        configInput.value = JSON.stringify(config);
        this.markColumnCodeIssues(modalElement);
        if (window.formBuilderDebug && window.formBuilderDebug.isEnabled && window.formBuilderDebug.isEnabled('matrix')) {
            window.formBuilderDebug.log('matrix', 'Updated matrix config:', config);
        }
    },

    populateForm(modalElement, itemData) {
        // Translations
        const labelTranslationsInput = modalElement.querySelector('#item-matrix-label-translations');
        const descriptionTranslationsInput = modalElement.querySelector('#item-matrix-description-translations');
        if (labelTranslationsInput && itemData.label_translations) {
            labelTranslationsInput.value = JSON.stringify(itemData.label_translations);
        }
        if (descriptionTranslationsInput && itemData.description_translations) {
            descriptionTranslationsInput.value = JSON.stringify(itemData.description_translations);
        }
        if (itemData.config) {
            try {
                let matrixConfig = typeof itemData.config === 'string' ? JSON.parse(itemData.config) : itemData.config;
                if (matrixConfig && matrixConfig.matrix_config && typeof matrixConfig.matrix_config === 'object') {
                    matrixConfig = matrixConfig.matrix_config;
                }
                const rowMode = matrixConfig.row_mode || 'manual';
                const rowModeRadio = modalElement.querySelector(`input[name="matrix_row_mode"][value="${rowMode}"]`);
                if (rowModeRadio) {
                    rowModeRadio.checked = true;
                    rowModeRadio.dispatchEvent(new Event('change'));
                }
                const rowsContainer = Utils.getElementById('matrix-rows-container');
                const columnsContainer = Utils.getElementById('matrix-columns-container');
                if (rowsContainer) rowsContainer.replaceChildren();
                if (columnsContainer) columnsContainer.replaceChildren();
                if (rowMode === 'manual') {
                    if (Array.isArray(matrixConfig.rows)) {
                        matrixConfig.rows.forEach(row => {
                            if (typeof row === 'string') {
                                this.addRow(modalElement, row);
                            } else if (row && typeof row === 'object') {
                                this.addRow(modalElement, row.text || '', row.name_translations || {});
                            }
                        });
                    }
                } else if (rowMode === 'list_library' || rowMode === 'hybrid') {
                    // Restore static rows for hybrid
                    if (rowMode === 'hybrid' && Array.isArray(matrixConfig.rows)) {
                        matrixConfig.rows.forEach(row => {
                            if (typeof row === 'string') {
                                this.addRow(modalElement, row);
                            } else if (row && typeof row === 'object') {
                                this.addRow(modalElement, row.text || '', row.name_translations || {});
                            }
                        });
                    }
                    if (matrixConfig.lookup_list_id) {
                        const listSelect = Utils.getElementById('matrix-list-select');
                        if (listSelect) {
                            listSelect.value = matrixConfig.lookup_list_id;
                            // handleListSelection is now async, wait for it to complete
                            this.handleListSelection(modalElement, matrixConfig.lookup_list_id).then(() => {
                                if (matrixConfig.list_display_column) {
                                    const displayColumnSelect = Utils.getElementById('matrix-list-display-column');
                                    if (displayColumnSelect) {
                                        displayColumnSelect.value = matrixConfig.list_display_column;
                                    }
                                }
                                if (matrixConfig.search_placeholder) {
                                    const searchPlaceholderInput = Utils.getElementById('matrix-search-placeholder');
                                    if (searchPlaceholderInput) {
                                        searchPlaceholderInput.value = matrixConfig.search_placeholder;
                                    }
                                }
                                if (matrixConfig.search_placeholder_translations) {
                                    const searchPlaceholderTranslationsInput = Utils.getElementById('matrix-search-placeholder-translations');
                                    if (searchPlaceholderTranslationsInput) {
                                        searchPlaceholderTranslationsInput.value = JSON.stringify(matrixConfig.search_placeholder_translations);
                                    }
                                }
                                if (matrixConfig.group_by_column) {
                                    const groupBySelect = Utils.getElementById('matrix-group-by-column');
                                    if (groupBySelect) {
                                        groupBySelect.value = matrixConfig.group_by_column;
                                    }
                                }
                                const groupDropdownEnabled = Utils.getElementById('matrix-group-dropdown-enabled');
                                const groupTableEnabled = Utils.getElementById('matrix-group-table-enabled');
                                const groupTotalsEnabled = Utils.getElementById('matrix-group-totals-enabled');
                                if (groupDropdownEnabled) {
                                    groupDropdownEnabled.checked = matrixConfig.group_dropdown_enabled !== false;
                                }
                                if (groupTableEnabled) {
                                    groupTableEnabled.checked = matrixConfig.group_table_enabled !== false;
                                }
                                if (groupTotalsEnabled) {
                                    groupTotalsEnabled.checked = matrixConfig.group_totals_enabled === true;
                                }
                                this.updateGroupingControlsVisibility(modalElement);

                                // Restore allow_other flag
                                const allowOtherCheckbox = Utils.getElementById('matrix-allow-other');
                                if (allowOtherCheckbox) {
                                    allowOtherCheckbox.checked = matrixConfig.allow_other === true;
                                }

                                // Restore plugin configuration generically if present
                                if (matrixConfig.plugin_config) {
                                    const pluginConfigContainer = modalElement.querySelector('#matrix-plugin-config-container');
                                    if (pluginConfigContainer) {
                                        // Restore all plugin config values generically
                                        Object.keys(matrixConfig.plugin_config).forEach(key => {
                                            const value = matrixConfig.plugin_config[key];
                                            const inputs = pluginConfigContainer.querySelectorAll(
                                                `[data-config-name="${key}"], [name="${key}"]`
                                            );

                                            inputs.forEach(input => {
                                                if (input.type === 'checkbox') {
                                                    input.checked = shouldCheckMatrixCheckbox(value, input.value || true);
                                                } else if (input.type === 'radio') {
                                                    input.checked = input.value === value;
                                                } else if (input.tagName === 'SELECT' && input.multiple) {
                                                    // For multi-select, set selected options
                                                    if (Array.isArray(value)) {
                                                        Array.from(input.options).forEach(opt => {
                                                            opt.selected = value.includes(opt.value);
                                                        });
                                                    }
                                                } else {
                                                    // For text inputs, textareas, and single selects
                                                    input.value = Array.isArray(value) ? value[0] : value;
                                                }
                                            });
                                        });
                                    }
                                }
                            });
                        }
                    }
                    if (Array.isArray(matrixConfig.list_filters)) {
                        const filtersContainer = Utils.getElementById('matrix-list-filters-container');
                        if (filtersContainer) {
                            filtersContainer.replaceChildren();
                            matrixConfig.list_filters.forEach(filter => {
                                this.addListFilter(modalElement);
                                const filterRow = filtersContainer.lastElementChild;
                                if (filterRow) {
                                    filterRow.querySelector('.filter-column').value = filter.column || '';
                                    filterRow.querySelector('.filter-operator').value = filter.operator || 'equals';
                                    filterRow.querySelector('.filter-value').value = filter.value || '';
                                }
                            });
                        }
                    }
                }
                if (Array.isArray(matrixConfig.columns)) {
                    const columnGroupsData = matrixConfig.column_groups || {};

                    // Rebuild ordered items: group containers and standalone columns in their original order
                    const orderedItems = [];
                    let lastGroupLabel = null;
                    matrixConfig.columns.forEach(columnData => {
                        const rawGroup = (columnData && typeof columnData === 'object') ? (columnData.group || '') : '';
                        if (rawGroup) {
                            if (rawGroup !== lastGroupLabel) {
                                orderedItems.push({ type: 'group', label: rawGroup, translations: columnGroupsData[rawGroup] || {}, columns: [] });
                                lastGroupLabel = rawGroup;
                            }
                            orderedItems[orderedItems.length - 1].columns.push(columnData);
                        } else {
                            orderedItems.push({ type: 'standalone', data: columnData });
                            lastGroupLabel = null;
                        }
                    });

                    orderedItems.forEach(item => {
                        if (item.type === 'group') {
                            const groupMeta = (item.translations && typeof item.translations === 'object' && !Array.isArray(item.translations))
                                ? item.translations
                                : {};
                            const headerColor = groupMeta[GROUP_HEADER_COLOR_KEY] || '';
                            const translations = { ...groupMeta };
                            delete translations[GROUP_HEADER_COLOR_KEY];
                            this.addGroup(modalElement, item.label, translations, headerColor);
                            const groupContainer = columnsContainer.lastElementChild;
                            const groupColumnsContainer = groupContainer?.querySelector(':scope > .matrix-group-columns');
                            // Consecutive columns sharing a `subgroup` label go into one subgroup.
                            let lastSubgroupLabel = '';
                            let subgroupColumnsContainer = null;
                            item.columns.forEach(colData => {
                                if (!colData || typeof colData !== 'object') return;
                                const subgroupLabel = colData.subgroup || '';
                                let targetColumns = groupColumnsContainer;
                                if (subgroupLabel) {
                                    if (subgroupLabel !== lastSubgroupLabel || !subgroupColumnsContainer) {
                                        const subMeta = columnGroupsData[`${item.label}${SUBGROUP_KEY_SEPARATOR}${subgroupLabel}`];
                                        const subMetaObj = (subMeta && typeof subMeta === 'object' && !Array.isArray(subMeta)) ? subMeta : {};
                                        const subTranslations = { ...subMetaObj };
                                        delete subTranslations[GROUP_HEADER_COLOR_KEY];
                                        const subgroupEl = this.addGroup(
                                            modalElement, subgroupLabel, subTranslations,
                                            subMetaObj[GROUP_HEADER_COLOR_KEY] || '', groupColumnsContainer
                                        );
                                        subgroupColumnsContainer = subgroupEl?.querySelector(':scope > .matrix-group-columns') || null;
                                    }
                                    targetColumns = subgroupColumnsContainer || groupColumnsContainer;
                                } else {
                                    subgroupColumnsContainer = null;
                                }
                                lastSubgroupLabel = subgroupLabel;
                                const isVariable = colData.is_variable || colData.type === 'variable';
                                this.addColumn(modalElement, colData.name || '', colData.type, isVariable, colData.variable || colData.variable_name || '', colData.variable_save_value !== false, colData.variable_readonly !== false, colData.name_translations || {}, targetColumns, colData.decimals, colData.header_type ? colData : null, colData.calculation || null, colData.include_in_row_total, { readonly: colData.calculation_readonly, saveValue: colData.calculation_save_value, bold: colData.calculation_bold });
                            });
                        } else {
                            const colData = item.data;
                            if (typeof colData === 'string') {
                                this.addColumn(modalElement, colData, 'number_whole');
                            } else if (colData && typeof colData === 'object' && (colData.name || colData.is_variable || colData.type === 'variable')) {
                                const isVariable = colData.is_variable || colData.type === 'variable';
                                this.addColumn(modalElement, colData.name || '', colData.type, isVariable, colData.variable || colData.variable_name || '', colData.variable_save_value !== false, colData.variable_readonly !== false, colData.name_translations || {}, null, colData.decimals, colData.header_type ? colData : null, colData.calculation || null, colData.include_in_row_total, { readonly: colData.calculation_readonly, saveValue: colData.calculation_save_value, bold: colData.calculation_bold });
                            }
                        }
                    });
                }
                const rowTotalsCheckbox = Utils.getElementById('matrix-show-row-totals');
                const columnTotalsCheckbox = Utils.getElementById('matrix-show-column-totals');
                const includeTotalsInApiCheckbox = Utils.getElementById('matrix-include-totals-in-api');
                const autoLoadCheckbox = Utils.getElementById('matrix-auto-load-entities');
                const highlightManualRowsCheckbox = Utils.getElementById('matrix-highlight-manual-rows');
                const legendTextInput = Utils.getElementById('matrix-legend-text');
                const legendTextTranslationsInput = Utils.getElementById('matrix-legend-text-translations');
                const legendHideInput = Utils.getElementById('matrix-legend-hide');
                const legendHideBtn = Utils.getElementById('matrix-legend-hide-btn');
                if (rowTotalsCheckbox) rowTotalsCheckbox.checked = matrixConfig.show_row_totals !== false;
                const rowTotalManualCheckbox = Utils.getElementById('matrix-row-total-manual-enabled');
                const rowTotalValidationSelect = Utils.getElementById('matrix-row-total-validation');
                if (rowTotalManualCheckbox) {
                    rowTotalManualCheckbox.checked = matrixConfig.row_total_manual_enabled === true;
                }
                if (rowTotalValidationSelect) {
                    rowTotalValidationSelect.value = matrixConfig.row_total_validation || 'none';
                }
                this.updateRowTotalOptionsVisibility(modalElement);
                if (columnTotalsCheckbox) columnTotalsCheckbox.checked = matrixConfig.show_column_totals !== false;
                if (includeTotalsInApiCheckbox) includeTotalsInApiCheckbox.checked = matrixConfig.include_calculated_totals_in_api !== false;
                this.updateIncludeTotalsInApiVisibility(modalElement);
                if (autoLoadCheckbox) autoLoadCheckbox.checked = matrixConfig.auto_load_entities === true;
                this._restoreIncludeOwnMatrixRows(modalElement, matrixConfig.include_own_matrix_rows);
                if (highlightManualRowsCheckbox) highlightManualRowsCheckbox.checked = matrixConfig.highlight_manual_rows === true;
                if (legendTextInput) {
                    legendTextInput.value = matrixConfig.legend_text || 'Manually added row';
                }
                if (legendTextTranslationsInput && matrixConfig.legend_text_translations) {
                    legendTextTranslationsInput.value = JSON.stringify(matrixConfig.legend_text_translations);
                }
                const lookupTooltipLabelInput = Utils.getElementById('matrix-variable-lookup-tooltip-label');
                const lookupTooltipLabelTranslationsInput = Utils.getElementById('matrix-variable-lookup-tooltip-label-translations');
                if (lookupTooltipLabelInput) {
                    lookupTooltipLabelInput.value = matrixConfig.variable_lookup_tooltip_label || 'Lookup value';
                }
                if (lookupTooltipLabelTranslationsInput && matrixConfig.variable_lookup_tooltip_label_translations) {
                    lookupTooltipLabelTranslationsInput.value = JSON.stringify(matrixConfig.variable_lookup_tooltip_label_translations);
                }
                const submittedTooltipLabelInput = Utils.getElementById('matrix-variable-submitted-tooltip-label');
                const submittedTooltipLabelTranslationsInput = Utils.getElementById('matrix-variable-submitted-tooltip-label-translations');
                if (submittedTooltipLabelInput) {
                    submittedTooltipLabelInput.value = matrixConfig.variable_submitted_tooltip_label || 'Submitted value';
                }
                if (submittedTooltipLabelTranslationsInput && matrixConfig.variable_submitted_tooltip_label_translations) {
                    submittedTooltipLabelTranslationsInput.value = JSON.stringify(matrixConfig.variable_submitted_tooltip_label_translations);
                }
                if (legendHideInput) {
                    const legendHide = matrixConfig.legend_hide === true;
                    legendHideInput.value = String(legendHide);
                    const legendTextInput = Utils.getElementById('matrix-legend-text');

                    // Update button icon, text, and input state based on saved state
                    if (legendHideBtn) {
                        const icon = legendHideBtn.querySelector('i');
                        const textSpan = legendHideBtn.querySelector('span');

                        if (legendHide) {
                            // Legend is hidden
                            if (icon) {
                                icon.className = 'fas fa-eye-slash w-4 h-4 mr-1';
                            }
                            if (textSpan) {
                                textSpan.textContent = 'Legend hidden';
                            } else {
                                const span = document.createElement('span');
                                span.textContent = 'Legend hidden';
                                legendHideBtn.appendChild(span);
                            }
                            legendHideBtn.title = 'Legend is hidden - click to show';
                            legendHideBtn.classList.remove('text-gray-600');
                            legendHideBtn.classList.add('text-gray-500');

                            // Grey out the text input
                            if (legendTextInput) {
                                legendTextInput.disabled = true;
                                legendTextInput.classList.add('bg-gray-100', 'cursor-not-allowed');
                            }
                        } else {
                            // Legend is shown
                            if (icon) {
                                icon.className = 'fas fa-eye w-4 h-4 mr-1';
                            }
                            if (textSpan) {
                                textSpan.textContent = 'Legend shown';
                            } else {
                                const span = document.createElement('span');
                                span.textContent = 'Legend shown';
                                legendHideBtn.appendChild(span);
                            }
                            legendHideBtn.title = 'Legend is shown - click to hide';
                            legendHideBtn.classList.remove('text-gray-500');
                            legendHideBtn.classList.add('text-gray-600');

                            // Enable the text input
                            if (legendTextInput) {
                                legendTextInput.disabled = false;
                                legendTextInput.classList.remove('bg-gray-100', 'cursor-not-allowed');
                            }
                        }
                    }
                }

                const rawRowTotalPosition = matrixConfig.row_total_position;
                this.syncRowTotalColumn(
                    modalElement,
                    (rawRowTotalPosition === undefined || rawRowTotalPosition === null || rawRowTotalPosition === '')
                        ? undefined
                        : Number(rawRowTotalPosition)
                );

                // Update auto-load visibility after columns are populated
                this.updateAutoLoadVisibility(modalElement);
                // Update legend text visibility after checkbox is set
                this.updateLegendTextVisibility(modalElement);
                this.updateConfig(modalElement);
            } catch (e) {
                console.error('Error parsing matrix config:', e);
                this.initializeDefault(modalElement);
            }
        } else {
            this.initializeDefault(modalElement);
        }
    }
};
