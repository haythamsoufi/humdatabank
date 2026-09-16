/**
 * Duplicate validation_message fields (textarea + hidden input) are JSON-encoded
 * as ["msg","msg"] and stored by Postgres as {"msg","msg"}.
 */
import { describe, it, expect } from 'vitest';
import { syncValidationMessageForSubmit, coerceStoredValidationMessage } from '../../../app/static/js/form_builder/modules/rules/form-serialization.js';

function makeForm({ message = 'Local Units must be higher than branches', disabled = false, extraHidden = false } = {}) {
    const form = document.createElement('form');
    form.id = 'item-modal-form';

    const textarea = document.createElement('textarea');
    textarea.name = 'validation_message';
    textarea.id = 'item-validation-message';
    textarea.value = message;
    textarea.disabled = disabled;
    form.appendChild(textarea);

    const translations = document.createElement('input');
    translations.type = 'hidden';
    translations.name = 'validation_message_translations';
    translations.id = 'item-validation-message-translations';
    translations.value = '{}';
    form.appendChild(translations);

    if (extraHidden) {
        const hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = 'validation_message';
        hidden.value = message;
        form.appendChild(hidden);
    }

    return form;
}

describe('syncValidationMessageForSubmit', () => {
    it('does not add a hidden copy when the textarea is enabled', () => {
        const form = makeForm();
        syncValidationMessageForSubmit(form, form);

        const named = form.querySelectorAll('[name="validation_message"]');
        expect(named).toHaveLength(1);
        expect(named[0].tagName).toBe('TEXTAREA');
        expect(new FormData(form).getAll('validation_message')).toEqual([
            'Local Units must be higher than branches',
        ]);
    });

    it('removes leftover hidden duplicates so JSON encoding stays a string', () => {
        const form = makeForm({ extraHidden: true });
        syncValidationMessageForSubmit(form, form);

        expect(form.querySelectorAll('[name="validation_message"]')).toHaveLength(1);
        expect(new FormData(form).getAll('validation_message')).toEqual([
            'Local Units must be higher than branches',
        ]);
    });

    it('writes a single hidden field when the textarea is disabled', () => {
        const form = makeForm({ disabled: true });
        syncValidationMessageForSubmit(form, form);

        const submitted = new FormData(form).getAll('validation_message');
        expect(submitted).toEqual(['Local Units must be higher than branches']);
        expect(form.querySelectorAll('input[type="hidden"][name="validation_message"]')).toHaveLength(1);
    });
});

describe('coerceStoredValidationMessage', () => {
    it('unwraps a Postgres array literal of identical strings', () => {
        expect(coerceStoredValidationMessage(
            '{"Local Units must be higher than branches","Local Units must be higher than branches"}',
        )).toBe('Local Units must be higher than branches');
    });

    it('flattens a duplicate list', () => {
        const msg = 'Local Units must be higher than branches';
        expect(coerceStoredValidationMessage([msg, msg])).toBe(msg);
    });
});
