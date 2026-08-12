/**
 * Regression tests for repeat-sections.js's loadFieldValue disaggregation matching.
 *
 * Before this fix, a flat sex-mode category like "male" was matched against
 * DOM inputs using a bare `[name*="_male"]` substring selector. Because a
 * repeat-entry indicator that supports BOTH "sex" and "sex_age" reporting
 * modes renders inputs for both containers at once (e.g.
 * "repeat_5_1_field_3_sex_male" AND "repeat_5_1_field_3_sexage_male_5_17"),
 * that loose selector matched every sex_age age-band input for the same sex
 * too — silently overwriting the hidden sex_age breakdown with the flat sex
 * total every time this function ran (on every entry-form page load that
 * hydrates saved repeat-section data, not just Excel import).
 */
import { describe, it, expect, beforeEach } from 'vitest';

async function importModule() {
    return import('../../../app/static/js/forms/modules/repeat-sections.js');
}

function buildRepeatField({ sectionId, instanceNumber, fieldIndex, itemId }) {
    document.body.innerHTML = `
        <div id="repeat-entries-${sectionId}">
            <div class="repeat-entry" data-repeat-instance="${instanceNumber}">
                <div data-item-id="${itemId}">
                    <input type="number" data-numeric="true"
                        name="repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_sex_male">
                    <input type="number" data-numeric="true"
                        name="repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_sex_female">
                    <input type="number" data-numeric="true"
                        name="repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_sexage_male__5">
                    <input type="number" data-numeric="true"
                        name="repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_sexage_male_5_17">
                    <input type="number" data-numeric="true"
                        name="repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_sexage_female__5">
                    <input type="number" data-numeric="true"
                        name="repeat_${sectionId}_${instanceNumber}_field_${fieldIndex}_sexage_female_5_17">
                </div>
            </div>
        </div>`;
    return document.querySelector('.repeat-entry');
}

function valueOf(suffix) {
    return document.querySelector(`input[name$="${suffix}"]`).value;
}

beforeEach(() => {
    document.body.innerHTML = '';
});

describe('loadFieldValue — flat sex-mode category matching', () => {
    it('sets only the sex-mode inputs and leaves sex_age age-band inputs untouched', async () => {
        const { loadFieldValue } = await importModule();
        const repeatEntry = buildRepeatField({ sectionId: 5, instanceNumber: 1, fieldIndex: 3, itemId: 47 });

        loadFieldValue(repeatEntry, '47', { mode: 'sex', values: { male: 100, female: 50 } }, 5, 1);

        expect(valueOf('_sex_male')).toBe('100');
        expect(valueOf('_sex_female')).toBe('50');
        // Regression guard: "_male" is a substring of "_sexage_male_5_17" too —
        // these must stay empty, not silently inherit the flat sex total.
        expect(valueOf('_sexage_male_5_17')).toBe('');
        expect(valueOf('_sexage_male__5')).toBe('');
        expect(valueOf('_sexage_female_5_17')).toBe('');
        expect(valueOf('_sexage_female__5')).toBe('');
    });

    it('still applies a sex_age breakdown correctly via the nested "direct" object', async () => {
        const { loadFieldValue } = await importModule();
        const repeatEntry = buildRepeatField({ sectionId: 5, instanceNumber: 1, fieldIndex: 3, itemId: 47 });

        loadFieldValue(
            repeatEntry,
            '47',
            { mode: 'sex_age', values: { direct: { male__5: 10, male_5_17: 20, female_5_17: 5 } } },
            5,
            1
        );

        expect(valueOf('_sexage_male__5')).toBe('10');
        expect(valueOf('_sexage_male_5_17')).toBe('20');
        expect(valueOf('_sexage_female_5_17')).toBe('5');
        // The flat sex-mode inputs (a different container) must not be touched.
        expect(valueOf('_sex_male')).toBe('');
        expect(valueOf('_sex_female')).toBe('');
    });
});
