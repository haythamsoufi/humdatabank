// Utilities for form serialization and prefix mapping used by item-modal
import { serializeRule } from './rule-builder-helpers.js';

// Map item type and mode to the form field prefix expected by the backend
// For edit mode, most fields are unprefixed
export function getFormPrefix(itemType, isEditMode) {
	if (isEditMode) {
		return '';
	}
	switch (itemType) {
		case 'indicator':
			return 'add_ind_modal-';
		case 'question':
			return 'add_q_modal-';
		case 'document':
			return 'doc_field-';
		// Matrix and plugin items use unprefixed keys in current routes
		case 'matrix':
		default:
			return '';
	}
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
