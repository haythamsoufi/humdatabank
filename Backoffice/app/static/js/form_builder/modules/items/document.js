// Document item logic extracted from item-modal.js

const PRESET_MONTH_NAMES = {
    '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr',
    '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Aug',
    '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec'
};

const PRESET_YEAR_SELECT_IDS = [
    'item-doc-preset-single-year',
    'item-doc-preset-start-year',
    'item-doc-preset-end-year',
    'item-doc-preset-start-month-year',
    'item-doc-preset-end-month-year'
];

function _q(modalElement, id) {
    return modalElement.querySelector(`#${id}`);
}

function ensureItemDocPresetYearSelects(modalElement) {
    if (!modalElement) return;
    const currentYear = new Date().getFullYear();

    PRESET_YEAR_SELECT_IDS.forEach((id) => {
        const el = _q(modalElement, id);
        if (!el || el.tagName !== 'SELECT') return;

        const hasYearOptions = Array.from(el.options || []).some((o) => /^\d{4}$/.test(String(o.value || '')));
        if (!hasYearOptions) {
            const minYearAttr = parseInt(el.getAttribute('data-year-min') || el.getAttribute('min') || '2000', 10);
            const maxYearAttr = parseInt(el.getAttribute('data-year-max') || el.getAttribute('max') || '2100', 10);
            const minYear = Number.isFinite(minYearAttr) ? minYearAttr : 2000;
            const hardMax = Number.isFinite(maxYearAttr) ? maxYearAttr : 2100;
            const maxYear = Math.min(hardMax, currentYear + 5);

            const placeholderOption = (el.options && el.options.length > 0 && !el.options[0].value)
                ? el.options[0].cloneNode(true)
                : null;

            el.innerHTML = '';
            if (placeholderOption) el.appendChild(placeholderOption);

            for (let y = maxYear; y >= minYear; y -= 1) {
                const opt = document.createElement('option');
                opt.value = String(y);
                opt.textContent = String(y);
                el.appendChild(opt);
            }
        }
    });
}

function toggleItemDocPresetPeriodFields(modalElement) {
    const periodType = _q(modalElement, 'item-doc-preset-period-type')?.value || 'single-year';
    modalElement.querySelectorAll('.item-doc-preset-period-fields').forEach((field) => {
        field.classList.add('hidden');
    });
    if (periodType === 'single-year') {
        _q(modalElement, 'item-doc-preset-single-year-fields')?.classList.remove('hidden');
    } else if (periodType === 'year-range') {
        _q(modalElement, 'item-doc-preset-year-range-fields')?.classList.remove('hidden');
    } else if (periodType === 'month-range') {
        _q(modalElement, 'item-doc-preset-month-range-fields')?.classList.remove('hidden');
    }
}

function generateItemDocPresetPeriodName(modalElement) {
    if (!modalElement) return '';
    const periodType = _q(modalElement, 'item-doc-preset-period-type')?.value || 'single-year';
    let periodName = '';

    if (periodType === 'single-year') {
        const year = _q(modalElement, 'item-doc-preset-single-year')?.value;
        if (year) periodName = year;
    } else if (periodType === 'year-range') {
        const startYear = _q(modalElement, 'item-doc-preset-start-year')?.value;
        const endYear = _q(modalElement, 'item-doc-preset-end-year')?.value;
        if (startYear && endYear) {
            periodName = startYear === endYear ? startYear : `${startYear}-${endYear}`;
        }
    } else if (periodType === 'month-range') {
        const startYear = _q(modalElement, 'item-doc-preset-start-month-year')?.value;
        const startMonth = _q(modalElement, 'item-doc-preset-start-month')?.value;
        const endYear = _q(modalElement, 'item-doc-preset-end-month-year')?.value;
        const endMonth = _q(modalElement, 'item-doc-preset-end-month')?.value;

        if (startYear && startMonth && endYear && endMonth) {
            const startMonthName = PRESET_MONTH_NAMES[startMonth];
            const endMonthName = PRESET_MONTH_NAMES[endMonth];

            if (startYear === endYear && startMonth === endMonth) {
                periodName = `${startMonthName} ${startYear}`;
            } else if (startYear === endYear) {
                periodName = `${startMonthName}-${endMonthName} ${startYear}`;
            } else {
                periodName = `${startMonthName} ${startYear}-${endMonthName} ${endYear}`;
            }
        }
    }

    const hidden = _q(modalElement, 'item-doc-preset-period-value');
    if (hidden) hidden.value = periodName || '';
    return periodName || '';
}

function parseAndPopulateItemDocPresetPeriod(modalElement, periodStr) {
    if (!modalElement || !periodStr || periodStr === 'None' || periodStr === 'null') return;

    ensureItemDocPresetYearSelects(modalElement);

    const periodTypeSelect = _q(modalElement, 'item-doc-preset-period-type');
    if (!periodTypeSelect) return;

    const yearPattern = /^(\d{4})$/;
    const yearRangePattern = /^(\d{4})-(\d{4})$/;
    const monthPattern = /^([A-Za-z]{3})\s+(\d{4})$/;
    const monthRangePattern = /^([A-Za-z]{3})\s+(\d{4})-([A-Za-z]{3})\s+(\d{4})$/;
    const monthYearRangePattern = /^([A-Za-z]{3})-([A-Za-z]{3})\s+(\d{4})$/;

    const monthToNumber = {
        Jan: '01', Feb: '02', Mar: '03', Apr: '04',
        May: '05', Jun: '06', Jul: '07', Aug: '08',
        Sep: '09', Oct: '10', Nov: '11', Dec: '12'
    };

    if (yearPattern.test(periodStr)) {
        const match = periodStr.match(yearPattern);
        periodTypeSelect.value = 'single-year';
        const singleYearField = _q(modalElement, 'item-doc-preset-single-year');
        if (singleYearField) singleYearField.value = match[1];
    } else if (yearRangePattern.test(periodStr)) {
        const match = periodStr.match(yearRangePattern);
        periodTypeSelect.value = 'year-range';
        const startYearField = _q(modalElement, 'item-doc-preset-start-year');
        const endYearField = _q(modalElement, 'item-doc-preset-end-year');
        if (startYearField) startYearField.value = match[1];
        if (endYearField) endYearField.value = match[2];
    } else if (monthRangePattern.test(periodStr)) {
        const match = periodStr.match(monthRangePattern);
        periodTypeSelect.value = 'month-range';
        const startMonthSelect = _q(modalElement, 'item-doc-preset-start-month');
        const startMonthYearField = _q(modalElement, 'item-doc-preset-start-month-year');
        const endMonthSelect = _q(modalElement, 'item-doc-preset-end-month');
        const endMonthYearField = _q(modalElement, 'item-doc-preset-end-month-year');

        if (startMonthSelect) startMonthSelect.value = monthToNumber[match[1]];
        if (startMonthYearField) startMonthYearField.value = match[2];
        if (endMonthSelect) endMonthSelect.value = monthToNumber[match[3]];
        if (endMonthYearField) endMonthYearField.value = match[4];
    } else if (monthYearRangePattern.test(periodStr)) {
        const match = periodStr.match(monthYearRangePattern);
        periodTypeSelect.value = 'month-range';
        const startMonthSelect = _q(modalElement, 'item-doc-preset-start-month');
        const startMonthYearField = _q(modalElement, 'item-doc-preset-start-month-year');
        const endMonthSelect = _q(modalElement, 'item-doc-preset-end-month');
        const endMonthYearField = _q(modalElement, 'item-doc-preset-end-month-year');

        if (startMonthSelect) startMonthSelect.value = monthToNumber[match[1]];
        if (startMonthYearField) startMonthYearField.value = match[3];
        if (endMonthSelect) endMonthSelect.value = monthToNumber[match[2]];
        if (endMonthYearField) endMonthYearField.value = match[3];
    } else if (monthPattern.test(periodStr)) {
        const match = periodStr.match(monthPattern);
        periodTypeSelect.value = 'month-range';
        const startMonthSelect = _q(modalElement, 'item-doc-preset-start-month');
        const startMonthYearField = _q(modalElement, 'item-doc-preset-start-month-year');
        const endMonthSelect = _q(modalElement, 'item-doc-preset-end-month');
        const endMonthYearField = _q(modalElement, 'item-doc-preset-end-month-year');

        if (startMonthSelect) startMonthSelect.value = monthToNumber[match[1]];
        if (startMonthYearField) startMonthYearField.value = match[2];
        if (endMonthSelect) endMonthSelect.value = monthToNumber[match[1]];
        if (endMonthYearField) endMonthYearField.value = match[2];
    }

    toggleItemDocPresetPeriodFields(modalElement);
    generateItemDocPresetPeriodName(modalElement);
}

function updateDocumentPeriodPanelsVisibility(modalElement) {
    if (!modalElement) return;
    const showYear = modalElement.querySelector('#item-document-show-year')?.checked;
    const periodTypeOptions = modalElement.querySelector('#period-type-options');
    const fixedBlock = modalElement.querySelector('#document-fixed-period-block');
    if (periodTypeOptions) periodTypeOptions.classList.toggle('hidden', !showYear);
    if (fixedBlock) fixedBlock.classList.toggle('hidden', !!showYear);
}

function isPresetAssignmentMode(modalElement) {
    const r = modalElement.querySelector('#item-doc-preset-mode-assignment');
    return !!(r && r.checked);
}

function updatePresetModeUi(modalElement) {
    if (!modalElement) return;
    const customWrap = modalElement.querySelector('#document-fixed-period-custom-fields');
    const hint = modalElement.querySelector('#item-doc-preset-assignment-hint');
    const useAssignment = isPresetAssignmentMode(modalElement);
    if (customWrap) customWrap.classList.toggle('hidden', useAssignment);
    if (hint) hint.classList.toggle('hidden', !useAssignment);
}

export const DocumentItem = {
    setup(modalElement) {
        if (modalElement._documentChangeHandler) {
            document.removeEventListener('change', modalElement._documentChangeHandler);
        }
        if (modalElement._showYearChangeHandler) {
            const sy = modalElement.querySelector('#item-document-show-year');
            if (sy) sy.removeEventListener('change', modalElement._showYearChangeHandler);
            modalElement._showYearChangeHandler = null;
        }

        modalElement._documentChangeHandler = (e) => {
            if (!modalElement.contains(e.target)) return;
            const t = e.target;
            if (t && t.name === 'preset_period_mode') {
                updatePresetModeUi(modalElement);
                const mh = _q(modalElement, 'item-doc-preset-mode-hidden');
                if (isPresetAssignmentMode(modalElement)) {
                    const h = _q(modalElement, 'item-doc-preset-period-value');
                    if (h) h.value = '';
                    if (mh) mh.value = 'assignment';
                } else {
                    if (mh) mh.value = 'custom';
                    generateItemDocPresetPeriodName(modalElement);
                }
                return;
            }
            if (t && t.id === 'item-doc-preset-period-type') {
                toggleItemDocPresetPeriodFields(modalElement);
            }
            if (!isPresetAssignmentMode(modalElement) && t && t.closest && t.closest('#document-fixed-period-custom-fields')) {
                generateItemDocPresetPeriodName(modalElement);
            }
        };

        const showYearCb = modalElement.querySelector('#item-document-show-year');
        modalElement._showYearChangeHandler = () => {
            updateDocumentPeriodPanelsVisibility(modalElement);
            updatePresetModeUi(modalElement);
            if (!showYearCb?.checked) {
                if (!isPresetAssignmentMode(modalElement)) {
                    ensureItemDocPresetYearSelects(modalElement);
                    toggleItemDocPresetPeriodFields(modalElement);
                    generateItemDocPresetPeriodName(modalElement);
                } else {
                    const h = _q(modalElement, 'item-doc-preset-period-value');
                    if (h) h.value = '';
                }
            }
        };
        if (showYearCb) {
            showYearCb.addEventListener('change', modalElement._showYearChangeHandler);
        }

        document.addEventListener('change', modalElement._documentChangeHandler);

        ensureItemDocPresetYearSelects(modalElement);
        toggleItemDocPresetPeriodFields(modalElement);
        updateDocumentPeriodPanelsVisibility(modalElement);
        updatePresetModeUi(modalElement);
        const modeHiddenSetup = _q(modalElement, 'item-doc-preset-mode-hidden');
        if (!isPresetAssignmentMode(modalElement)) {
            generateItemDocPresetPeriodName(modalElement);
            if (modeHiddenSetup) modeHiddenSetup.value = 'custom';
        } else {
            const h = _q(modalElement, 'item-doc-preset-period-value');
            if (h) h.value = '';
            if (modeHiddenSetup) modeHiddenSetup.value = 'assignment';
        }
    },

    teardown(modalElement) {
        if (!modalElement) return;
        if (modalElement._documentChangeHandler) {
            document.removeEventListener('change', modalElement._documentChangeHandler);
            modalElement._documentChangeHandler = null;
        }
        if (modalElement._showYearChangeHandler) {
            const sy = modalElement.querySelector('#item-document-show-year');
            if (sy) sy.removeEventListener('change', modalElement._showYearChangeHandler);
            modalElement._showYearChangeHandler = null;
        }
    },

    /** Sync hidden preset_period (and preset_period_mode_value) before item modal form submit.
     *  The hidden mode input guarantees the mode is always submitted even when radios are disabled. */
    syncPresetPeriodToHidden(modalElement) {
        if (!modalElement) return;
        const showYear = modalElement.querySelector('#item-document-show-year')?.checked;
        const hidden = modalElement.querySelector('#item-doc-preset-period-value');
        const modeHidden = modalElement.querySelector('#item-doc-preset-mode-hidden');

        if (showYear) {
            if (hidden) hidden.value = '';
            if (modeHidden) modeHidden.value = 'custom';
            return;
        }

        // Force-enable radios so the checked one is always reflected in FormData too
        const rCustom = modalElement.querySelector('#item-doc-preset-mode-custom');
        const rAssign = modalElement.querySelector('#item-doc-preset-mode-assignment');
        if (rCustom) rCustom.disabled = false;
        if (rAssign) rAssign.disabled = false;

        if (isPresetAssignmentMode(modalElement)) {
            if (hidden) hidden.value = '';
            if (modeHidden) modeHidden.value = 'assignment';
            return;
        }

        if (modeHidden) modeHidden.value = 'custom';
        ensureItemDocPresetYearSelects(modalElement);
        generateItemDocPresetPeriodName(modalElement);
    },

    populateForm(modalElement, itemData) {
        try {
            const typeSelect = modalElement.querySelector('#item-document-type');
            if (typeSelect) {
                let docType = null;
                if (itemData && itemData.config && itemData.config.document_type) {
                    docType = itemData.config.document_type;
                } else if (itemData && itemData.document_type) {
                    docType = itemData.document_type;
                }
                if (docType && typeof docType === 'string') {
                    typeSelect.value = docType;
                } else {
                    typeSelect.value = '';
                }
            }
        } catch (e) {
            // Non-fatal UI population error
        }

        const maxDocumentsInput = modalElement.querySelector('#item-document-max-documents');
        if (maxDocumentsInput) {
            let maxDocsValue = null;

            if (itemData.config && itemData.config.max_documents) {
                maxDocsValue = itemData.config.max_documents;
            } else if (itemData.max_documents) {
                maxDocsValue = itemData.max_documents;
            }

            if (maxDocsValue) {
                maxDocumentsInput.value = maxDocsValue;
            } else {
                maxDocumentsInput.value = '';
            }
        }

        const showLanguageCheckbox = modalElement.querySelector('#item-document-show-language');
        const showTypeCheckbox = modalElement.querySelector('#item-document-show-type');
        const showYearCheckbox = modalElement.querySelector('#item-document-show-year');
        const showPublicCheckbox = modalElement.querySelector('#item-document-show-public');

        if (showLanguageCheckbox) {
            showLanguageCheckbox.checked = itemData?.config?.show_language !== false;
        }
        if (showTypeCheckbox) {
            showTypeCheckbox.checked = itemData?.config?.show_document_type || false;
        }
        if (showYearCheckbox) {
            showYearCheckbox.checked = itemData?.config?.show_year || false;
        }
        if (showPublicCheckbox) {
            showPublicCheckbox.checked = itemData?.config?.show_public_checkbox || false;
        }

        const entityRepoToggle = modalElement.querySelector('#item-document-entity-repo');
        if (entityRepoToggle) {
            entityRepoToggle.checked = Boolean(itemData?.config?.cross_assignment_period_reuse);
        }

        const singleYearCheckbox = modalElement.querySelector('#item-document-period-single-year');
        const yearRangeCheckbox = modalElement.querySelector('#item-document-period-year-range');
        const monthRangeCheckbox = modalElement.querySelector('#item-document-period-month-range');

        if (singleYearCheckbox) {
            singleYearCheckbox.checked = itemData?.config?.allow_single_year !== false;
        }
        if (yearRangeCheckbox) {
            yearRangeCheckbox.checked = itemData?.config?.allow_year_range !== false;
        }
        if (monthRangeCheckbox) {
            monthRangeCheckbox.checked = itemData?.config?.allow_month_range !== false;
        }

        updateDocumentPeriodPanelsVisibility(modalElement);

        if (showYearCheckbox?.checked) {
            const presetHidden = modalElement.querySelector('#item-doc-preset-period-value');
            if (presetHidden) presetHidden.value = '';
        }

        const usePresetAssignment = Boolean(itemData?.config?.preset_period_use_assignment);
        const rCustom = modalElement.querySelector('#item-doc-preset-mode-custom');
        const rAssign = modalElement.querySelector('#item-doc-preset-mode-assignment');
        const modeHidden = modalElement.querySelector('#item-doc-preset-mode-hidden');
        if (rCustom && rAssign) {
            // Force-enable radios before setting state so the change is visible
            rCustom.disabled = false;
            rAssign.disabled = false;
            if (usePresetAssignment && !showYearCheckbox?.checked) {
                rAssign.checked = true;
                rCustom.checked = false;
                if (modeHidden) modeHidden.value = 'assignment';
            } else {
                rCustom.checked = true;
                rAssign.checked = false;
                if (modeHidden) modeHidden.value = 'custom';
            }
        }
        updatePresetModeUi(modalElement);

        if (usePresetAssignment && !showYearCheckbox?.checked) {
            ensureItemDocPresetYearSelects(modalElement);
            const periodTypeSelect = modalElement.querySelector('#item-doc-preset-period-type');
            if (periodTypeSelect) periodTypeSelect.value = 'single-year';
            toggleItemDocPresetPeriodFields(modalElement);
            PRESET_YEAR_SELECT_IDS.forEach((id) => {
                const el = modalElement.querySelector(`#${id}`);
                if (el && el.tagName === 'SELECT') el.value = '';
            });
            const presetHidden = modalElement.querySelector('#item-doc-preset-period-value');
            if (presetHidden) presetHidden.value = '';
        } else {
            const preset = !showYearCheckbox?.checked ? itemData?.config?.preset_period : null;
            if (preset && typeof preset === 'string' && preset.trim()) {
                parseAndPopulateItemDocPresetPeriod(modalElement, preset.trim());
            } else {
                ensureItemDocPresetYearSelects(modalElement);
                const periodTypeSelect = modalElement.querySelector('#item-doc-preset-period-type');
                if (periodTypeSelect) periodTypeSelect.value = 'single-year';
                toggleItemDocPresetPeriodFields(modalElement);
                PRESET_YEAR_SELECT_IDS.forEach((id) => {
                    const el = modalElement.querySelector(`#${id}`);
                    if (el && el.tagName === 'SELECT') el.value = '';
                });
                generateItemDocPresetPeriodName(modalElement);
            }
        }
    }
};
