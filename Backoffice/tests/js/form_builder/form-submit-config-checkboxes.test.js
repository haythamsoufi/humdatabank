/**
 * Tests for config-checkbox serialization in
 * app/static/js/form_builder/modules/modal/config-checkbox-serializer.js
 *
 * HTML checkboxes are absent from FormData when unchecked. The serializer
 * writes an always-enabled hidden input per checkbox onto the form root
 * (`name="<key>"`, value `"true"` / `"false"`).
 *
 * It must NOT write into `input[name="matrix_config"]` — that is the matrix config
 * field, which is disabled for non-matrix items and dropped from FormData.
 */

import { describe, it, expect } from 'vitest';
import {
    serializeConfigCheckboxes,
    CONFIG_CHECKBOXES,
} from '../../../app/static/js/form_builder/modules/modal/config-checkbox-serializer.js';

function makeModal({ allowOver100 = false, excludeFromCompletion = false } = {}) {
    const modal = document.createElement('div');
    modal.id = 'item-modal';

    const cb1 = document.createElement('input');
    cb1.type = 'checkbox';
    cb1.id = 'item-allow-over-100';
    cb1.checked = allowOver100;
    modal.appendChild(cb1);

    const cb2 = document.createElement('input');
    cb2.type = 'checkbox';
    cb2.id = 'item-exclude-from-completion-rate';
    cb2.checked = excludeFromCompletion;
    modal.appendChild(cb2);

    return modal;
}

function makeForm() {
    const form = document.createElement('form');
    form.id = 'item-modal-form';
    return form;
}

function flagValue(form, key) {
    const field = form.querySelector(`#item-config-flag-${key}`);
    expect(field).not.toBeNull();
    expect(field.disabled).toBe(false);
    expect(field.name).toBe(key);
    return field.value;
}

describe('serializeConfigCheckboxes — exclude_from_completion_rate', () => {
    it('serializes true when checkbox is checked', () => {
        const form = makeForm();
        serializeConfigCheckboxes(makeModal({ excludeFromCompletion: true }), form);
        expect(flagValue(form, 'exclude_from_completion_rate')).toBe('true');
    });

    it('serializes false when checkbox is unchecked', () => {
        const form = makeForm();
        serializeConfigCheckboxes(makeModal({ excludeFromCompletion: false }), form);
        expect(flagValue(form, 'exclude_from_completion_rate')).toBe('false');
    });

    it('transitions true → false when user unchecks', () => {
        const modal = makeModal({ excludeFromCompletion: true });
        const form = makeForm();
        serializeConfigCheckboxes(modal, form);
        modal.querySelector('#item-exclude-from-completion-rate').checked = false;
        serializeConfigCheckboxes(modal, form);
        expect(flagValue(form, 'exclude_from_completion_rate')).toBe('false');
    });

    it('transitions false → true when user checks', () => {
        const modal = makeModal({ excludeFromCompletion: false });
        const form = makeForm();
        serializeConfigCheckboxes(modal, form);
        modal.querySelector('#item-exclude-from-completion-rate').checked = true;
        serializeConfigCheckboxes(modal, form);
        expect(flagValue(form, 'exclude_from_completion_rate')).toBe('true');
    });
});

describe('serializeConfigCheckboxes — allow_over_100', () => {
    it('serializes true when checkbox is checked', () => {
        const form = makeForm();
        serializeConfigCheckboxes(makeModal({ allowOver100: true }), form);
        expect(flagValue(form, 'allow_over_100')).toBe('true');
    });

    it('serializes false when checkbox is unchecked', () => {
        const form = makeForm();
        serializeConfigCheckboxes(makeModal({ allowOver100: false }), form);
        expect(flagValue(form, 'allow_over_100')).toBe('false');
    });
});

describe('serializeConfigCheckboxes — form-root hidden inputs', () => {
    it('does not write into the matrix name="matrix_config" field', () => {
        const form = makeForm();
        const matrixConfig = document.createElement('input');
        matrixConfig.type = 'hidden';
        matrixConfig.name = 'matrix_config';
        matrixConfig.id = 'item-matrix-config';
        matrixConfig.value = '{}';
        matrixConfig.disabled = true;
        form.appendChild(matrixConfig);

        serializeConfigCheckboxes(makeModal({ excludeFromCompletion: false }), form);

        expect(matrixConfig.value).toBe('{}');
        expect(matrixConfig.disabled).toBe(true);
        expect(flagValue(form, 'exclude_from_completion_rate')).toBe('false');
    });

    it('re-enables its own hidden input if something disabled it', () => {
        const form = makeForm();
        serializeConfigCheckboxes(makeModal({ excludeFromCompletion: false }), form);
        const field = form.querySelector('#item-config-flag-exclude_from_completion_rate');
        field.disabled = true;
        serializeConfigCheckboxes(makeModal({ excludeFromCompletion: false }), form);
        expect(field.disabled).toBe(false);
        expect(field.value).toBe('false');
    });

    it('does not create a field when the checkbox is absent from the modal', () => {
        const form = makeForm();
        serializeConfigCheckboxes(document.createElement('div'), form);
        expect(form.querySelector('#item-config-flag-exclude_from_completion_rate')).toBeNull();
        expect(form.querySelector('#item-config-flag-allow_over_100')).toBeNull();
    });

    it('is idempotent — repeated calls do not accumulate duplicate fields', () => {
        const modal = makeModal({ excludeFromCompletion: true });
        const form = makeForm();
        serializeConfigCheckboxes(modal, form);
        serializeConfigCheckboxes(modal, form);
        expect(form.querySelectorAll('#item-config-flag-exclude_from_completion_rate').length).toBe(1);
        expect(form.querySelectorAll('[name="exclude_from_completion_rate"]').length).toBe(1);
    });

    it('includes the hidden field in FormData even when the checkbox is unchecked', () => {
        const form = makeForm();
        serializeConfigCheckboxes(makeModal({ excludeFromCompletion: false }), form);
        const fd = new FormData(form);
        expect(fd.get('exclude_from_completion_rate')).toBe('false');
    });

    it('submits a single true/false value, not checkbox on plus hidden true', () => {
        const modal = makeModal({ excludeFromCompletion: true });
        modal.querySelector('#item-exclude-from-completion-rate').name = 'exclude_from_completion_rate';
        const form = makeForm();
        form.appendChild(modal); // checkbox must be inside the form for FormData
        serializeConfigCheckboxes(modal, form);
        const values = [...new FormData(form).getAll('exclude_from_completion_rate')];
        expect(values).toEqual(['true']);
    });
});

describe('CONFIG_CHECKBOXES registry', () => {
    it('contains all six Category-B preserve-existing fields', () => {
        const keys = CONFIG_CHECKBOXES.map(c => c.key);
        expect(keys).toEqual([
            'allow_over_100',
            'exclude_from_completion_rate',
            'unique_options_in_section',
            'limit_entries_to_option_count',
            'use_as_repeat_entry_title',
            'allow_other',
        ]);
    });

    it('every entry has both selector and key', () => {
        CONFIG_CHECKBOXES.forEach(entry => {
            expect(typeof entry.selector).toBe('string');
            expect(entry.selector.startsWith('#')).toBe(true);
            expect(typeof entry.key).toBe('string');
            expect(entry.key.length).toBeGreaterThan(0);
        });
    });
});

describe('regression — unchecked exclude box must reach FormData', () => {
    it('sends false (not absent) when checkbox is unchecked', () => {
        const form = makeForm();
        serializeConfigCheckboxes(makeModal({ excludeFromCompletion: false }), form);
        const fd = new FormData(form);
        expect(fd.has('exclude_from_completion_rate')).toBe(true);
        expect(fd.get('exclude_from_completion_rate')).toBe('false');
    });
});
