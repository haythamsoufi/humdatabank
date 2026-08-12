/**
 * Regression tests for disagg-dom-apply.js — applying UPR Excel import /
 * AI-opinion disaggregation and yes/no payloads onto entry-form DOM inputs.
 *
 * These lock in three real bugs found during a full reliability review of the
 * UPR Excel import: (1) sex_age values nested under `values.direct` were never
 * unwrapped, (2) yes/no checkboxes were never actually checked, and (3) newly
 * added ("pending") dynamic indicators use a non-numeric temporary id
 * (`pending_<ts>_<rand>`) that a `\d+`-based regex on a sample input name
 * fails to match, so disaggregated values silently never applied to
 * first-time-added emergency/dynamic indicators.
 */
import { describe, it, expect } from 'vitest';

async function importModule() {
    return import('../../../app/static/js/forms/modules/disagg-dom-apply.js');
}

function standardIndicatorBlockHtml(id) {
    return `
    <div class="form-group form-item-block" data-item-id="${id}" data-item-type="indicator">
        <input type="radio" name="indicator_${id}_reporting_mode" value="total">
        <input type="radio" name="indicator_${id}_reporting_mode" value="sex">
        <input type="radio" name="indicator_${id}_reporting_mode" value="age">
        <input type="radio" name="indicator_${id}_reporting_mode" value="sex_age">
        <input type="number" name="indicator_${id}_total_value">
        <input type="number" name="indicator_${id}_indirect_reach">
        <input type="number" name="indicator_${id}_sex_male">
        <input type="number" name="indicator_${id}_sex_female">
        <input type="number" name="indicator_${id}_sex_unknown">
        <input type="number" name="indicator_${id}_age_5_17">
        <input type="number" name="indicator_${id}_age_18_49">
        <input type="number" name="indicator_${id}_sexage_male_5_17">
        <input type="number" name="indicator_${id}_sexage_male_18_49">
        <input type="number" name="indicator_${id}_sexage_female_5_17">
        <input type="number" name="indicator_${id}_sexage_female_18_49">
        <input type="checkbox" name="indicator_${id}_standard_value" value="yes">
        <input type="checkbox" name="indicator_${id}_standard_value" value="no">
        <input type="checkbox" name="indicator_${id}_data_not_available">
    </div>`;
}

function dynamicIndicatorBlockHtml(assignmentId) {
    // Mirrors dynamic_indicator_item.html field-naming: name uses
    // field.dynamic_assignment_id verbatim, which for a not-yet-persisted
    // ("pending") indicator is a non-numeric temp id string.
    return `
    <div class="form-group form-item-block" data-item-id="${assignmentId}" data-item-type="indicator" data-assignment-id="${assignmentId}">
        <input type="radio" name="dynamic_${assignmentId}_reporting_mode" value="total">
        <input type="radio" name="dynamic_${assignmentId}_reporting_mode" value="sex_age">
        <input type="number" name="dynamic_${assignmentId}_total_value">
        <input type="number" name="dynamic_${assignmentId}_indirect_reach">
        <input type="number" name="dynamic_${assignmentId}_sexage_male_5_17">
        <input type="number" name="dynamic_${assignmentId}_sexage_female_5_17">
        <input type="checkbox" name="dynamic_${assignmentId}_standard_value" value="yes">
        <input type="checkbox" name="dynamic_${assignmentId}_standard_value" value="no">
    </div>`;
}

describe('applyDisaggToBlock', () => {
    it('unwraps nested values.direct for sex_age mode and checks the mode radio', async () => {
        const { applyDisaggToBlock } = await importModule();
        document.body.innerHTML = standardIndicatorBlockHtml(47);
        const block = document.querySelector('.form-item-block');

        const applied = applyDisaggToBlock(block, {
            mode: 'sex_age',
            values: {
                direct: { male_5_17: 10, female_5_17: 20, male_18_49: 30, female_18_49: 40 },
                indirect: 5,
            },
        });

        expect(applied).toBe(true);
        expect(block.querySelector('[name="indicator_47_reporting_mode"][value="sex_age"]').checked).toBe(true);
        expect(block.querySelector('[name="indicator_47_sexage_male_5_17"]').value).toBe('10');
        expect(block.querySelector('[name="indicator_47_sexage_female_5_17"]').value).toBe('20');
        expect(block.querySelector('[name="indicator_47_sexage_male_18_49"]').value).toBe('30');
        expect(block.querySelector('[name="indicator_47_sexage_female_18_49"]').value).toBe('40');
        expect(block.querySelector('[name="indicator_47_indirect_reach"]').value).toBe('5');
    });

    it('applies flat sex-mode breakdown under values.direct', async () => {
        const { applyDisaggToBlock } = await importModule();
        document.body.innerHTML = standardIndicatorBlockHtml(48);
        const block = document.querySelector('.form-item-block');

        const applied = applyDisaggToBlock(block, {
            mode: 'sex',
            values: { direct: { male: 100, female: 200, unknown: 0 } },
        });

        expect(applied).toBe(true);
        expect(block.querySelector('[name="indicator_48_sex_male"]').value).toBe('100');
        expect(block.querySelector('[name="indicator_48_sex_female"]').value).toBe('200');
    });

    it('applies total mode with a scalar total and indirect reach', async () => {
        const { applyDisaggToBlock } = await importModule();
        document.body.innerHTML = standardIndicatorBlockHtml(49);
        const block = document.querySelector('.form-item-block');

        const applied = applyDisaggToBlock(block, {
            mode: 'total',
            values: { total: 500, indirect: 50 },
        });

        expect(applied).toBe(true);
        expect(block.querySelector('[name="indicator_49_total_value"]').value).toBe('500');
        expect(block.querySelector('[name="indicator_49_indirect_reach"]').value).toBe('50');
    });

    it('applies disaggregated values to a brand-new pending dynamic indicator with a non-numeric temp id', async () => {
        const { applyDisaggToBlock } = await importModule();
        const tempId = 'pending_1700000000000_ab12cd9xy';
        document.body.innerHTML = dynamicIndicatorBlockHtml(tempId);
        const block = document.querySelector('.form-item-block');

        const applied = applyDisaggToBlock(block, {
            mode: 'sex_age',
            values: {
                direct: { male_5_17: 7, female_5_17: 8 },
                indirect: 2,
            },
        });

        expect(applied).toBe(true);
        expect(block.querySelector(`[name="dynamic_${tempId}_reporting_mode"][value="sex_age"]`).checked).toBe(true);
        expect(block.querySelector(`[name="dynamic_${tempId}_sexage_male_5_17"]`).value).toBe('7');
        expect(block.querySelector(`[name="dynamic_${tempId}_sexage_female_5_17"]`).value).toBe('8');
        expect(block.querySelector(`[name="dynamic_${tempId}_indirect_reach"]`).value).toBe('2');
    });

    it('returns false and applies nothing when block or payload is missing', async () => {
        const { applyDisaggToBlock } = await importModule();
        document.body.innerHTML = standardIndicatorBlockHtml(50);
        const block = document.querySelector('.form-item-block');
        expect(applyDisaggToBlock(block, null)).toBe(false);
        expect(applyDisaggToBlock(null, { mode: 'total', values: { total: 1 } })).toBe(false);
        expect(applyDisaggToBlock(block, { mode: '', values: {} })).toBe(false);
    });
});

describe('applyYesNoToBlock', () => {
    it('checks the "yes" box and leaves "no" unchecked', async () => {
        const { applyYesNoToBlock } = await importModule();
        document.body.innerHTML = standardIndicatorBlockHtml(60);
        const block = document.querySelector('.form-item-block');

        const applied = applyYesNoToBlock(block, 'yes');

        expect(applied).toBe(true);
        expect(block.querySelector('[name="indicator_60_standard_value"][value="yes"]').checked).toBe(true);
        expect(block.querySelector('[name="indicator_60_standard_value"][value="no"]').checked).toBe(false);
    });

    it('switches from a previously-checked "yes" to "no"', async () => {
        const { applyYesNoToBlock } = await importModule();
        document.body.innerHTML = standardIndicatorBlockHtml(61);
        const block = document.querySelector('.form-item-block');
        block.querySelector('[name="indicator_61_standard_value"][value="yes"]').checked = true;

        applyYesNoToBlock(block, 'no');

        expect(block.querySelector('[name="indicator_61_standard_value"][value="yes"]').checked).toBe(false);
        expect(block.querySelector('[name="indicator_61_standard_value"][value="no"]').checked).toBe(true);
    });

    it('checks yes/no on a pending dynamic indicator with a non-numeric temp id', async () => {
        const { applyYesNoToBlock } = await importModule();
        const tempId = 'pending_1700000000001_zz9';
        document.body.innerHTML = dynamicIndicatorBlockHtml(tempId);
        const block = document.querySelector('.form-item-block');

        const applied = applyYesNoToBlock(block, 'yes');

        expect(applied).toBe(true);
        expect(block.querySelector(`[name="dynamic_${tempId}_standard_value"][value="yes"]`).checked).toBe(true);
    });

    it('returns false for a value that is neither yes nor no', async () => {
        const { applyYesNoToBlock } = await importModule();
        document.body.innerHTML = standardIndicatorBlockHtml(62);
        const block = document.querySelector('.form-item-block');
        expect(applyYesNoToBlock(block, 'maybe')).toBe(false);
        expect(applyYesNoToBlock(block, '')).toBe(false);
        expect(applyYesNoToBlock(block, null)).toBe(false);
    });
});
