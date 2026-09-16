// Utilities for form serialization and prefix mapping used by item-modal
import { serializeRule } from './rule-builder-helpers.js';

/** Unwrap a rule stored as JSON, or as a JSON string of JSON (legacy double-encoding). */
export function unwrapStoredRuleJson(raw) {
    if (raw == null) return '';
    let value = String(raw).trim();
    if (!value || value === 'null' || value === '{}') return '';
    for (let i = 0; i < 3; i++) {
        try {
            const parsed = JSON.parse(value);
            if (typeof parsed === 'string') {
                value = parsed.trim();
                continue;
            }
            if (
                parsed
                && typeof parsed === 'object'
                && Array.isArray(parsed.conditions)
                && parsed.conditions.length > 0
            ) {
                return JSON.stringify(parsed);
            }
            return '';
        } catch (_e) {
            return value;
        }
    }
    return '';
}

// Serialize a rule builder element into a string suitable for submit
// Ensures no double-encoding and returns '' when empty/non-meaningful
export function serializeRuleForSubmit(ruleBuilderElement) {
    if (!ruleBuilderElement) return '';
    const data = serializeRule(ruleBuilderElement);
    if (data == null) return '';
    // If already a non-empty string, assume it's a JSON string
    if (typeof data === 'string') {
        const trimmed = data.trim();
        return trimmed ? trimmed : '';
    }
    // Otherwise, stringify the object
    try {
        const json = JSON.stringify(data);
        return json && json !== '{}' ? json : '';
    } catch (_e) {
        return '';
    }
}

// Ensure a hidden input exists on a form and set it to the serialized rule
export function setHiddenRuleField(formElement, fieldName, ruleBuilderElement) {
	if (!formElement || !fieldName) return;
	const value = serializeRuleForSubmit(ruleBuilderElement);
	let field = formElement.querySelector(`input[name="${fieldName}"]`);
	if (!field) {
		field = document.createElement('input');
		field.type = 'hidden';
		field.name = fieldName;
		formElement.appendChild(field);
	}
	field.value = value;
}

/**
 * Ensure a hidden input exists on a form and set its value.
 *
 * @param {HTMLFormElement} formElement
 * @param {string} fieldName
 * @param {string} value
 * @param {{ id?: string, disabled?: boolean }} [options]
 */
export function setHiddenField(formElement, fieldName, value, options = {}) {
	if (!formElement || !fieldName) return;
	let field = options.id
		? formElement.querySelector(`#${options.id}`)
		: formElement.querySelector(`input[name="${fieldName}"]`);
	if (!field) {
		field = document.createElement('input');
		field.type = 'hidden';
		field.name = fieldName;
		if (options.id) field.id = options.id;
		formElement.appendChild(field);
	}
	field.name = fieldName;
	if (options.id) field.id = options.id;
	if (typeof options.disabled === 'boolean') {
		field.disabled = options.disabled;
	}
	field.value = value == null ? '' : String(value);
}

/**
 * Flatten a validation message stored as a duplicate JSON list or a Postgres
 * text-array literal ({"msg","msg"}) back to a single string.
 */
export function coerceStoredValidationMessage(value) {
	if (value == null) return '';
	if (Array.isArray(value)) {
		for (let i = value.length - 1; i >= 0; i -= 1) {
			const part = coerceStoredValidationMessage(value[i]);
			if (part) return part;
		}
		return '';
	}
	const text = String(value).trim();
	if (!text) return '';
	const unwrapped = unwrapDuplicatePgTextArray(text);
	return unwrapped != null ? unwrapped : text;
}

function unwrapDuplicatePgTextArray(raw) {
	if (!raw.startsWith('{') || !raw.endsWith('}') || raw.includes(':')) return null;
	const inner = raw.slice(1, -1);
	const parts = [];
	const re = /"((?:\\.|[^"\\])*)"/g;
	let match;
	while ((match = re.exec(inner)) !== null) {
		parts.push(match[1].replace(/\\"/g, '"'));
	}
	if (parts.length < 2) return null;
	if (parts.every((part) => part === parts[0])) return parts[0];
	return null;
}

/**
 * Write validation_message so FormData/JSON contains a single string.
 *
 * The visible control is a <textarea name="validation_message">. Calling
 * setHiddenField() looks only for input[name=...] and would add a second
 * field; formDataToJson then sends ["msg","msg"], which Postgres stores as
 * {"msg","msg"}.
 *
 * When the textarea is enabled it is the canonical field. Extra hidden
 * copies (from a previous submit in this modal session) are removed.
 * When it is disabled (hidden UI section), a single hidden input is used.
 *
 * @param {HTMLFormElement} form
 * @param {ParentNode} modalElement
 * @param {{ isDisplayOnly?: boolean }} [options]
 */
export function syncValidationMessageForSubmit(form, modalElement, options = {}) {
	if (!form) return;
	const isDisplayOnly = !!options.isDisplayOnly;
	const root = modalElement || form;
	const textarea = root.querySelector('#item-validation-message');
	const translationsInput = root.querySelector('#item-validation-message-translations');

	form.querySelectorAll('input[type="hidden"][name="validation_message"]').forEach((el) => {
		if (el !== textarea) el.remove();
	});

	if (isDisplayOnly) {
		if (textarea) textarea.value = '';
		if (translationsInput) translationsInput.value = '{}';
		return;
	}

	if (textarea && textarea.disabled) {
		setHiddenField(form, 'validation_message', textarea.value);
	}
	if (translationsInput) {
		setHiddenField(form, 'validation_message_translations', translationsInput.value || '{}');
	}
}

// Append a serialized rule into FormData (omit when empty)
export function appendRuleToFormData(formData, fieldName, ruleBuilderElement) {
	if (!formData || !fieldName) return;
	const value = serializeRuleForSubmit(ruleBuilderElement);
	if (value) {
		formData.append(fieldName, value);
	}
}

// Set multiple hidden input fields on a form for array-like values
// Existing matching inputs are removed before adding new ones
export function setMultiHiddenFields(formElement, fieldName, values) {
	if (!formElement || !fieldName) return;
	const nodes = Array.from(formElement.querySelectorAll(`input[name="${fieldName}"]`));
	nodes.forEach(n => n.remove());
	if (!Array.isArray(values) || values.length === 0) return;
	values.forEach(v => {
		const input = document.createElement('input');
		input.type = 'hidden';
		input.name = fieldName;
		input.value = v;
		formElement.appendChild(input);
	});
}
