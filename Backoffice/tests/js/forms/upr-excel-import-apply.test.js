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
}));

vi.mock('../../../app/static/js/forms/modules/repeat-sections.js', () => ({
    addRepeatEntry: vi.fn(),
    getEffectiveRepeatEntryMax: vi.fn().mockReturnValue(null),
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
        expect(result.warnings.some((w) => w.includes('999'))).toBe(true);
    });

    it('warns when the block exists but has no matching input for the value', async () => {
        document.body.innerHTML = `
            <div class="form-item-block" data-item-id="11" data-item-type="indicator"></div>`;
        const { applyUprExcelImportPayload } = await importModule();

        const result = await applyUprExcelImportPayload({ fields: { 11: { value: '7' } } });

        expect(result.applied).toBe(0);
        expect(result.warnings.some((w) => w.includes('11'))).toBe(true);
    });
});

describe('applyUprExcelImportPayload — emergency operation repeat slots', () => {
    beforeEach(() => {
        vi.clearAllMocks();
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
        expect(result.warnings.some((w) => w.includes('21'))).toBe(true);
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
