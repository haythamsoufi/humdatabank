/**
 * Regression tests for upr-excel-import-apply.js's warning propagation.
 *
 * Before this fix, failures inside applyStaticFields/applyMatrices (missing
 * form-item block, matrix control not yet registered, etc.) were only ever
 * logged via console.warn and were silently dropped from the `warnings`
 * array shown to the user in the page import notice — so a value from the
 * uploaded Excel file could fail to load into the form with zero visible
 * indication to the focal point doing the import.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/dynamic-indicators.js', () => ({
    addPendingDynamicIndicatorForImport: vi.fn().mockResolvedValue(null),
    findDynamicIndicatorFormBlock: (container, indicatorBankId) => {
        if (!container || indicatorBankId == null || indicatorBankId === '') return null;
        const bankId = String(indicatorBankId);
        return container.querySelector(`.form-item-block[data-indicator-bank-id="${bankId}"]`)
            || container.querySelector(
                `.form-item-block[data-assignment-id] .propose-changes-btn[data-indicator-id="${bankId}"]`
            )?.closest('.form-item-block')
            || null;
    },
    findLivePendingIndicatorBlock: (tempAssignmentId, fallbackElement = null) => {
        if (tempAssignmentId) {
            const live = document.querySelector(
                `.form-item-block[data-pending-assignment-id="${tempAssignmentId}"], `
                + `.form-item-block[data-assignment-id="${tempAssignmentId}"]`
            );
            if (live) return live;
        }
        return fallbackElement?.isConnected ? fallbackElement : null;
    },
}));

vi.mock('../../../app/static/js/forms/modules/repeat-sections.js', () => ({
    addRepeatEntry: vi.fn(),
    getEffectiveRepeatEntryMax: vi.fn().mockReturnValue(null),
    findRepeatFieldSelects: vi.fn().mockReturnValue([]),
    setSelectValueWithFallback: vi.fn(),
    waitForCalculatedSelectOptions: vi.fn().mockResolvedValue(undefined),
}));

async function importModule() {
    return import('../../../app/static/js/forms/modules/upr-excel-import-apply.js');
}

beforeEach(() => {
    document.body.innerHTML = '';
    delete window.matrixHandler;
    delete window.reinitializeDisaggregationCalculator;
    delete window.requestRelevanceRecheck;
    delete window.checkAllRelevanceConditions;
});

describe('applyUprExcelImportPayload — static fields', () => {
    it('applies a scalar value to an existing field and reports no warnings', async () => {
        document.body.innerHTML = `
            <div class="form-item-block" data-item-id="10" data-item-type="indicator">
                <input name="indicator_10_standard_value">
            </div>`;
        const { applyUprExcelImportPayload } = await importModule();

        const result = await applyUprExcelImportPayload({ fields: { 10: { value: '42' } } });

        expect(result.warnings).toEqual([]);
        expect(result.applied).toBe(1);
        expect(document.querySelector('[name="indicator_10_standard_value"]').value).toBe('42');
    });

    it('warns when the target field block is not present on the form', async () => {
        const { applyUprExcelImportPayload } = await importModule();

        const result = await applyUprExcelImportPayload({ fields: { 999: { value: '5' } } });

        expect(result.applied).toBe(0);
        expect(result.warnings.some((w) => (
            (typeof w === 'object' ? w.item_id : w) == 999
            || String(w.message || w).includes('999')
        ))).toBe(true);
    });

    it('warns when the block exists but has no matching input for the value', async () => {
        document.body.innerHTML = `
            <div class="form-item-block" data-item-id="11" data-item-type="indicator"></div>`;
        const { applyUprExcelImportPayload } = await importModule();

        const result = await applyUprExcelImportPayload({ fields: { 11: { value: '7' } } });

        expect(result.applied).toBe(0);
        expect(result.warnings.some((w) => (
            (typeof w === 'object' ? w.item_id : w) == 11
            || String(w.message || w).includes('11')
        ))).toBe(true);
    });
});

describe('applyUprExcelImportPayload — emergency operation repeat slots', () => {
    beforeEach(async () => {
        vi.clearAllMocks();
        // vi.clearAllMocks() only clears call history, not mockReturnValue/
        // mockImplementation overrides from a previous test — so this must be
        // reset explicitly, or a test that mocks a relocated select (below)
        // would leak into the next test and mask real failures.
        const repeatSections = await import('../../../app/static/js/forms/modules/repeat-sections.js');
        repeatSections.findRepeatFieldSelects.mockReturnValue([]);
    });

    it('waits for the calculated-list select to load its options before selecting the emergency operation', async () => {
        document.body.innerHTML = `
            <div id="repeat-entries-5">
                <div class="repeat-entry" id="repeat-entry-5-1" data-repeat-instance="1">
                    <div data-item-id="77">
                        <select data-options-source="calculated">
                            <option value="">-- Select --</option>
                        </select>
                    </div>
                </div>
            </div>`;

        const repeatSections = await import('../../../app/static/js/forms/modules/repeat-sections.js');
        repeatSections.waitForCalculatedSelectOptions.mockImplementation(async (select) => {
            const opt = document.createElement('option');
            opt.value = 'MDR Pakistan Floods (MDRPK001)';
            opt.textContent = 'MDR Pakistan Floods (MDRPK001)';
            select.appendChild(opt);
        });
        repeatSections.setSelectValueWithFallback.mockImplementation((select, val) => {
            select.value = val;
        });

        const { applyUprExcelImportPayload } = await importModule();
        const result = await applyUprExcelImportPayload({
            repeat_slots: [{
                repeat_section_id: '5',
                slot_num: 1,
                choice_item_id: '77',
                display_value: 'MDR Pakistan Floods (MDRPK001)',
            }],
        });

        expect(repeatSections.waitForCalculatedSelectOptions).toHaveBeenCalled();
        expect(document.querySelector('select').value).toBe('MDR Pakistan Floods (MDRPK001)');
        expect(result.warnings).toEqual([]);
        expect(result.applied).toBe(1);
    });

    it('finds a select relocated to the entry header by the title-dropdown feature', async () => {
        // setupRepeatEntryTitleDropdown() (repeat-sections.js) physically moves a
        // "use as repeat entry title" <select> out of its .form-item-block into the
        // entry header, leaving `field` (queried by data-item-id) with no <select>
        // descendant at all. applyRepeatSlotChoice must fall back to the same
        // findRepeatFieldSelects() lookup repeat-sections.js itself uses for saved
        // drafts, not a bare field.querySelector('select').
        document.body.innerHTML = `
            <div id="repeat-entries-5">
                <div class="repeat-entry" id="repeat-entry-5-1" data-repeat-instance="1">
                    <div class="repeat-entry__label">
                        <select id="relocated-select" data-use-as-repeat-entry-title="true" data-field-item-id="77">
                            <option value="">-- Select --</option>
                            <option value="MDR Pakistan Floods (MDRPK001)">MDR Pakistan Floods (MDRPK001)</option>
                        </select>
                    </div>
                    <div data-item-id="77" class="repeat-entry-title-field--hidden"></div>
                </div>
            </div>`;

        const repeatSections = await import('../../../app/static/js/forms/modules/repeat-sections.js');
        const relocatedSelect = document.getElementById('relocated-select');
        repeatSections.findRepeatFieldSelects.mockReturnValue([relocatedSelect]);
        repeatSections.setSelectValueWithFallback.mockImplementation((select, val) => {
            select.value = val;
        });

        const { applyUprExcelImportPayload } = await importModule();
        const result = await applyUprExcelImportPayload({
            repeat_slots: [{
                repeat_section_id: '5',
                slot_num: 1,
                choice_item_id: '77',
                display_value: 'MDR Pakistan Floods (MDRPK001)',
            }],
        });

        expect(relocatedSelect.value).toBe('MDR Pakistan Floods (MDRPK001)');
        expect(result.warnings).toEqual([]);
        expect(result.applied).toBe(1);
    });

    it('warns when the emergency operation could not be matched even after waiting', async () => {
        document.body.innerHTML = `
            <div id="repeat-entries-5">
                <div class="repeat-entry" id="repeat-entry-5-1" data-repeat-instance="1">
                    <div data-item-id="77">
                        <select data-options-source="calculated">
                            <option value="">-- Select --</option>
                        </select>
                    </div>
                </div>
            </div>`;

        const repeatSections = await import('../../../app/static/js/forms/modules/repeat-sections.js');
        // Options load, but the specific appeal from the workbook isn't in the (now-closed) catalog.
        repeatSections.waitForCalculatedSelectOptions.mockResolvedValue(undefined);
        repeatSections.setSelectValueWithFallback.mockImplementation(() => {
            // Real implementation would leave select.value as '' when no option matches.
        });

        const { applyUprExcelImportPayload } = await importModule();
        const result = await applyUprExcelImportPayload({
            repeat_slots: [{
                repeat_section_id: '5',
                slot_num: 1,
                choice_item_id: '77',
                display_value: 'MDR Archived Operation (MDRXX999)',
            }],
        });

        expect(result.applied).toBe(0);
        expect(result.warnings.some((w) => w.includes('MDR Archived Operation (MDRXX999)'))).toBe(true);
    });
});

describe('applyUprExcelImportPayload — matrices', () => {
    it('warns once when no matrix handler is registered on the page', async () => {
        const { applyUprExcelImportPayload } = await importModule();

        const result = await applyUprExcelImportPayload({ matrices: { 20: { 'row_col': 5 } } });

        expect(result.applied).toBe(0);
        expect(result.warnings.some((w) => w.toLowerCase().includes('matrix'))).toBe(true);
    });

    it('warns when the matrix handler cannot find the target matrix', async () => {
        window.matrixHandler = { setMatrixData: vi.fn().mockReturnValue(false) };
        const { applyUprExcelImportPayload } = await importModule();

        const result = await applyUprExcelImportPayload({ matrices: { 21: { 'row_col': 5 } } });

        expect(result.applied).toBe(0);
        expect(result.warnings.some((w) => (
            (typeof w === 'object' ? w.item_id : w) == 21
            || String(w.message || w).includes('21')
        ))).toBe(true);
    });

    it('reports success with no warnings when the matrix handler applies the data', async () => {
        window.matrixHandler = { setMatrixData: vi.fn().mockReturnValue(true) };
        const { applyUprExcelImportPayload } = await importModule();

        const result = await applyUprExcelImportPayload({ matrices: { 22: { 'row_col': 5 } } });

        expect(result.applied).toBe(1);
        expect(result.warnings).toEqual([]);
        expect(window.matrixHandler.setMatrixData).toHaveBeenCalledWith('22', { row_col: 5 });
    });
});

describe('applyUprExcelImportPayload — dynamic indicators', () => {
    beforeEach(async () => {
        vi.clearAllMocks();
        const dynamicIndicators = await import('../../../app/static/js/forms/modules/dynamic-indicators.js');
        dynamicIndicators.addPendingDynamicIndicatorForImport.mockResolvedValue(null);
    });

    it('applies values to a live field that has no propose-changes button', async () => {
        document.body.innerHTML = `
            <div id="section-container-8">
                <div class="form-item-block" data-item-type="indicator"
                     data-assignment-id="pending_1" data-indicator-bank-id="42">
                    <input name="dynamic_pending_1_total_value">
                </div>
            </div>`;
        const { applyUprExcelImportPayload } = await importModule();

        const result = await applyUprExcelImportPayload({
            dynamic_indicators: [{
                section_id: 8,
                indicator_bank_id: 42,
                value: '1500',
            }],
        });

        expect(result.warnings).toEqual([]);
        expect(result.applied).toBe(1);
        expect(document.querySelector('[name="dynamic_pending_1_total_value"]').value).toBe('1500');
    });

    it('writes first-import values onto the live layout clone, not a detached insert node', async () => {
        document.body.innerHTML = `
            <div id="section-container-8"></div>`;

        const live = document.createElement('div');
        live.className = 'form-item-block';
        live.setAttribute('data-assignment-id', 'pending_abc');
        live.setAttribute('data-pending-assignment-id', 'pending_abc');
        live.setAttribute('data-indicator-bank-id', '42');
        live.innerHTML = '<input name="dynamic_pending_abc_total_value">';
        document.getElementById('section-container-8').appendChild(live);

        const detached = live.cloneNode(true);
        const dynamicIndicators = await import('../../../app/static/js/forms/modules/dynamic-indicators.js');
        dynamicIndicators.addPendingDynamicIndicatorForImport.mockResolvedValue(detached);

        const { applyUprExcelImportPayload } = await importModule();
        const result = await applyUprExcelImportPayload({
            dynamic_indicators: [{
                section_id: 8,
                indicator_bank_id: 42,
                value: '88',
            }],
        });

        expect(detached.isConnected).toBe(false);
        expect(document.querySelector('[name="dynamic_pending_abc_total_value"]').value).toBe('88');
        expect(detached.querySelector('input').value).toBe('');
        expect(result.applied).toBe(1);
        expect(result.warnings).toEqual([]);
    });

    it('falls through an empty disagg_data object to the scalar value', async () => {
        document.body.innerHTML = `
            <div id="section-container-8">
                <div class="form-item-block" data-item-type="indicator"
                     data-assignment-id="9" data-indicator-bank-id="42">
                    <input name="dynamic_9_total_value">
                </div>
            </div>`;
        const { applyUprExcelImportPayload } = await importModule();

        const result = await applyUprExcelImportPayload({
            dynamic_indicators: [{
                section_id: 8,
                indicator_bank_id: 42,
                existing_assignment_id: 9,
                value: '77',
                disagg_data: {},
            }],
        });

        expect(result.applied).toBe(1);
        expect(document.querySelector('[name="dynamic_9_total_value"]').value).toBe('77');
    });
});

describe('applyUprExcelImportPayload — not applicable', () => {
    it('checks the not-applicable box for a core indicator', async () => {
        document.body.innerHTML = `
            <div class="form-item-block" data-item-id="88" data-item-type="indicator">
                <input type="checkbox" name="indicator_88_not_applicable">
                <input name="indicator_88_total_value">
            </div>`;
        const { applyUprExcelImportPayload } = await importModule();

        const result = await applyUprExcelImportPayload({
            fields: { 88: { not_applicable: true } },
        });

        expect(result.applied).toBe(1);
        expect(result.warnings).toEqual([]);
        expect(document.querySelector('[name="indicator_88_not_applicable"]').checked).toBe(true);
        expect(document.querySelector('[name="indicator_88_total_value"]').value).toBe('');
    });
});
