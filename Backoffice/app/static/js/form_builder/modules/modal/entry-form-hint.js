// Entry form hint — shared item-level guidance shown on the data entry form.

import { updateDescriptionHintSectionLayout } from './description-hint-ui.js';

export const DEFAULT_ENTRY_FORM_HINT_TEXT =
    'Number format: Use "." for decimals and "," for thousands (e.g. 1,234.56). Values are rounded to each column\'s allowed decimal places.';

export const DEFAULT_ENTRY_FORM_HINT_STYLE = 'warning';

const HINT_STYLES = new Set(['normal', 'info', 'warning', 'tip', 'important']);

function normalizeHintStyle(style) {
    const normalized = String(style || '').trim().toLowerCase();
    return HINT_STYLES.has(normalized) ? normalized : DEFAULT_ENTRY_FORM_HINT_STYLE;
}

function parseBool(val) {
    return val === true || val === 'true' || val === 1 || val === '1';
}

function matrixHasNumericColumn(matrixConfig) {
    const columns = matrixConfig?.columns;
    if (!Array.isArray(columns)) return false;
    return columns.some((col) => {
        if (!col || typeof col !== 'object') return true;
        return col.type !== 'tick';
    });
}

function resolveHintConfigFromItemData(itemData) {
    const config = itemData?.config || {};
    let showHint = parseBool(config.show_hint);
    let hintText = config.hint_text || '';
    let hintTranslations = config.hint_text_translations || {};
    let hintStyle = normalizeHintStyle(config.hint_style);

    if (!showHint) {
        const matrixConfig = config.matrix_config || itemData?.matrix_config;
        if (matrixConfig?.show_format_hint === true && matrixHasNumericColumn(matrixConfig)) {
            showHint = true;
            hintText = matrixConfig.format_hint_text || DEFAULT_ENTRY_FORM_HINT_TEXT;
            hintTranslations = matrixConfig.format_hint_text_translations || {};
            hintStyle = DEFAULT_ENTRY_FORM_HINT_STYLE;
        }
    }

    return { showHint, hintText, hintTranslations, hintStyle };
}

export function updateEntryFormHintVisibility(modalElement) {
    const checkbox = modalElement?.querySelector('#item-show-entry-form-hint');
    const wrapper = modalElement?.querySelector('#item-entry-form-hint-text-wrapper');
    const translationsBtn = modalElement?.querySelector('.item-hint-translations-btn');
    const styleSelect = modalElement?.querySelector('#item-entry-form-hint-style');
    if (!checkbox || !wrapper) return;
    const expanded = checkbox.checked;
    wrapper.classList.toggle('hidden', !expanded);
    if (translationsBtn) translationsBtn.classList.toggle('hidden', !expanded);
    if (styleSelect) styleSelect.classList.toggle('hidden', !expanded);
    if (modalElement) updateDescriptionHintSectionLayout(modalElement);
}

export function maybeSuggestMatrixDefaultHint(modalElement) {
    const checkbox = modalElement?.querySelector('#item-show-entry-form-hint');
    const textInput = modalElement?.querySelector('#item-entry-form-hint-text');
    if (!checkbox?.checked || !textInput || textInput.value.trim()) return;

    const columnsContainer = modalElement.querySelector('#matrix-columns-container');
    if (!columnsContainer) return;

    const hasNumericColumn = Array.from(columnsContainer.querySelectorAll('.matrix-column')).some((colEl) => {
        const typeSelect = colEl.querySelector('.matrix-column-type');
        const colType = typeSelect?.value || 'number_whole';
        return colType !== 'tick';
    });

    if (hasNumericColumn) {
        textInput.value = DEFAULT_ENTRY_FORM_HINT_TEXT;
    }
}

export function populateEntryFormHintFields(modalElement, itemData) {
    if (!modalElement) return;

    const checkbox = modalElement.querySelector('#item-show-entry-form-hint');
    const textInput = modalElement.querySelector('#item-entry-form-hint-text');
    const translationsInput = modalElement.querySelector('#item-entry-form-hint-text-translations');
    const styleSelect = modalElement.querySelector('#item-entry-form-hint-style');

    const { showHint, hintText, hintTranslations, hintStyle } = resolveHintConfigFromItemData(itemData);

    if (checkbox) checkbox.checked = showHint;
    if (textInput) textInput.value = hintText || '';
    if (styleSelect) styleSelect.value = hintStyle;
    if (translationsInput) {
        translationsInput.value = JSON.stringify(hintTranslations && typeof hintTranslations === 'object' ? hintTranslations : {});
    }

    updateEntryFormHintVisibility(modalElement);
}

export function resetEntryFormHintState(modalElement) {
    if (!modalElement) return;

    const checkbox = modalElement.querySelector('#item-show-entry-form-hint');
    const textInput = modalElement.querySelector('#item-entry-form-hint-text');
    const translationsInput = modalElement.querySelector('#item-entry-form-hint-text-translations');
    const styleSelect = modalElement.querySelector('#item-entry-form-hint-style');

    if (checkbox) checkbox.checked = false;
    if (textInput) textInput.value = '';
    if (styleSelect) styleSelect.value = DEFAULT_ENTRY_FORM_HINT_STYLE;
    if (translationsInput) translationsInput.value = '{}';

    updateEntryFormHintVisibility(modalElement);
}

export function setupEntryFormHintListeners(modalElement) {
    if (!modalElement) return;

    const checkbox = modalElement.querySelector('#item-show-entry-form-hint');
    const textInput = modalElement.querySelector('#item-entry-form-hint-text');

    if (checkbox && !checkbox._entryFormHintListenerAdded) {
        checkbox.addEventListener('change', () => {
            updateEntryFormHintVisibility(modalElement);
            maybeSuggestMatrixDefaultHint(modalElement);
        });
        checkbox._entryFormHintListenerAdded = true;
    }

    if (textInput && !textInput._entryFormHintListenerAdded) {
        textInput._entryFormHintListenerAdded = true;
    }
}
