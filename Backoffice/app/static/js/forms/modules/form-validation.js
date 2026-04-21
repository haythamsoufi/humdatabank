import { debugLog } from './debug.js';
import { evaluateConditions } from './conditions.js';
import { getCurrentFieldValue } from './field-management.js';

const MODULE_NAME = 'form_validation';

/**
 * Parse validation condition from attribute (may be double-encoded by template).
 * Always returns an object with .conditions array, or null on parse failure.
 */
function parseValidationConditionToObject(raw) {
    if (raw == null || raw === '') return null;
    let parsed = typeof raw === 'string' ? (() => { try { return JSON.parse(raw); } catch (_) { return null; } })() : raw;
    if (parsed == null) return null;
    if (typeof parsed === 'string') {
        try { parsed = JSON.parse(parsed); } catch (_) { return null; }
    }
    return parsed && typeof parsed === 'object' ? parsed : null;
}

class FormValidator {
    constructor() {
        this.errors = [];
        this.errorFields = new Set();
        this.init();
    }

    init() {
        debugLog(MODULE_NAME, '🔍 FORM VALIDATION: Initializing form validation module');
        this.attachSubmitListeners();
        this.setupRealTimeValidation();
        this.initializePercentageWarnings();
        this.initializeValidationConditions();
    }

    attachSubmitListeners() {
        const form = document.getElementById('focalDataEntryForm');
        if (!form) {
            debugLog(MODULE_NAME, '❌ FORM VALIDATION: Form #focalDataEntryForm not found!');
            return;
        }

        debugLog(MODULE_NAME, '✅ FORM VALIDATION: Found form, attaching submit listener');

        form.addEventListener('submit', (e) => {
            debugLog(MODULE_NAME, '📝 FORM VALIDATION: Form submission attempt detected!');

            // SECURITY NOTICE: Add hidden field to indicate client-side validation occurred
            const clientValidationField = document.createElement('input');
            clientValidationField.type = 'hidden';
            clientValidationField.name = '_client_validation_performed';
            clientValidationField.value = 'true';
            form.appendChild(clientValidationField);

            // Collect hidden fields for server processing before submission
            if (window.collectHiddenFieldsForSubmission) {
                window.collectHiddenFieldsForSubmission();
            }

            // Determine which action triggered the submission
            const submitter = e.submitter;
            const actionValue = submitter ? submitter.value : null;
            const actionName = submitter ? submitter.name : null;

            debugLog(MODULE_NAME, `📝 FORM VALIDATION: Action detected - name: "${actionName}", value: "${actionValue}"`);

            // Only validate for "submit" action, not "save" action
            if (actionName === 'action' && actionValue === 'save') {
                debugLog(MODULE_NAME, '💾 FORM VALIDATION: Save action detected - skipping validation (allowing save)');
                return true;
            }

            if (actionName === 'action' && actionValue === 'submit') {
                debugLog(MODULE_NAME, '📤 FORM VALIDATION: Submit action detected - running validation');
            } else {
                debugLog(MODULE_NAME, '🔍 FORM VALIDATION: Unknown or missing action - running validation as default');
            }

            // Clear previous errors
            this.clearErrors();

            // Validate form (including percentage fields)
            const isValid = this.validateForm();

            if (!isValid) {
                debugLog(MODULE_NAME, `❌ FORM VALIDATION: Form validation failed with ${this.errors.length} errors`);
                e.preventDefault();
                e.stopPropagation();

                // Reset submit button state if FormSubmitGuard changed it to "Saving..."
                // Use full-form reset (submitter can be missing with requestSubmit()/programmatic submits)
                if (window.FormSubmitGuard) {
                    try {
                        if (typeof window.FormSubmitGuard.reset === 'function') {
                            window.FormSubmitGuard.reset(form);
                        } else {
                            const submitButton = e.submitter || form.querySelector('button[type="submit"][data-submit-guard-active="1"]');
                            if (submitButton && typeof window.FormSubmitGuard.resetButton === 'function') {
                                window.FormSubmitGuard.resetButton(submitButton);
                            }
                        }
                        debugLog(MODULE_NAME, '🔄 FORM VALIDATION: Reset submit button state after validation failure');
                    } catch (_) {
                        // no-op
                    }
                }

                this.displayErrors();
                this.scrollToFirstError();
                return false;
            }

            debugLog(MODULE_NAME, '✅ FORM VALIDATION: Form validation passed');
            return true;
        });
    }

    setupRealTimeValidation() {
        // Clear errors when user starts typing/selecting in error fields
        document.addEventListener('input', (e) => {
            if (this.errorFields.has(e.target.name) || this.errorFields.has(e.target.id)) {
                this.clearFieldError(e.target);
            }

            // Real-time validation for percentage fields (show warning, don't clamp)
            if (e.target.getAttribute('data-field-type') === 'percentage') {
                this.validatePercentageField(e.target);
            }

            // Real-time validation for validation conditions
            this.checkValidationConditionForField(e.target);
            // Also check all fields that might reference this field in their validation conditions
            this.checkValidationConditionsForReferencedField(e.target);
        });

        document.addEventListener('change', (e) => {
            if (this.errorFields.has(e.target.name) || this.errorFields.has(e.target.id)) {
                this.clearFieldError(e.target);
            }

            // Validate percentage fields on blur/change
            if (e.target.getAttribute('data-field-type') === 'percentage') {
                this.validatePercentageField(e.target);
            }

            // Real-time validation for validation conditions
            this.checkValidationConditionForField(e.target);
            // Also check all fields that might reference this field in their validation conditions
            this.checkValidationConditionsForReferencedField(e.target);
        });

        // Also validate on blur for percentage fields
        document.addEventListener('blur', (e) => {
            if (e.target.getAttribute('data-field-type') === 'percentage') {
                this.validatePercentageField(e.target);
            }

            // Real-time validation for validation conditions
            this.checkValidationConditionForField(e.target);
            // Also check all fields that might reference this field in their validation conditions
            this.checkValidationConditionsForReferencedField(e.target);
        }, true);
    }

    validatePercentageField(field) {
        // Skip if field is hidden or disabled
        if (this.isFieldHidden(field) || field.disabled) {
            return;
        }

        const value = parseFloat(field.value);

        // Only validate if there's a value
        if (isNaN(value) || field.value.trim() === '') {
            this.clearPercentageWarning(field);
            return;
        }

        // Get field config from data attribute
        let allowOver100 = false;
        const configAttr = field.getAttribute('data-field-config');
        if (configAttr) {
            try {
                const config = JSON.parse(configAttr);
                allowOver100 = config.allow_over_100 === true || config.allow_over_100 === 'true' || config.allow_over_100 === 1 || config.allow_over_100 === '1';
            } catch (e) {
                // Config parsing failed, use default (false)
            }
        }

        // If allow_over_100 is false and value > 100, show warning (but allow input)
        if (!allowOver100 && value > 100) {
            this.showPercentageWarning(field, 'Values above 100% are not allowed for this field. Please enter a value between 0 and 100.');
            field.classList.add('border-yellow-500', 'focus:border-yellow-500', 'focus:ring-yellow-500');
            field.classList.remove('border-gray-300', 'border-red-500', 'focus:border-blue-500', 'focus:ring-blue-500', 'focus:border-red-500', 'focus:ring-red-500');
            // Don't add to errorFields here - we'll validate on submit
        } else {
            // Value is valid, clear any warnings
            this.clearPercentageWarning(field);
            field.classList.remove('border-yellow-500', 'focus:border-yellow-500', 'focus:ring-yellow-500');
        }
    }

    showPercentageWarning(field, message) {
        const warningId = `warning-${field.id || field.name}`;
        let warningDiv = document.getElementById(warningId);

        if (!warningDiv) {
            warningDiv = document.createElement('div');
            warningDiv.id = warningId;
            warningDiv.className = 'text-yellow-600 text-sm mt-1 flex items-center gap-1';

            // Insert after field or field container
            const container = field.closest('.form-item-block') || field.parentElement;
            // Check if there's already an error div, insert before it
            const existingError = container.querySelector(`#error-${field.id || field.name}`);
            if (existingError) {
                container.insertBefore(warningDiv, existingError);
            } else {
                container.appendChild(warningDiv);
            }
        }

        warningDiv.replaceChildren();
        const icon = document.createElement('i');
        icon.className = 'fas fa-exclamation-triangle text-xs';
        const span = document.createElement('span');
        span.textContent = message;
        warningDiv.appendChild(icon);
        warningDiv.appendChild(span);
        warningDiv.style.display = 'flex';
    }

    clearPercentageWarning(field) {
        const warningId = `warning-${field.id || field.name}`;
        const warningDiv = document.getElementById(warningId);
        if (warningDiv) {
            warningDiv.style.display = 'none';
        }
    }

    initializePercentageWarnings() {
        // Check all percentage fields on page load and show warnings for values > 100%
        const percentageFields = document.querySelectorAll('input[data-field-type="percentage"]');

        percentageFields.forEach(field => {
            // Skip if field is hidden or disabled
            if (this.isFieldHidden(field) || field.disabled) {
                return;
            }

            const value = parseFloat(field.value);

            // Only check if there's a value
            if (isNaN(value) || field.value.trim() === '') {
                return;
            }

            // Get field config from data attribute
            let allowOver100 = false;
            const configAttr = field.getAttribute('data-field-config');
            if (configAttr) {
                try {
                    const config = JSON.parse(configAttr);
                    allowOver100 = config.allow_over_100 === true || config.allow_over_100 === 'true' || config.allow_over_100 === 1 || config.allow_over_100 === '1';
                } catch (e) {
                    // Config parsing failed, use default (false)
                }
            }

            // If allow_over_100 is false and value > 100, show warning
            if (!allowOver100 && value > 100) {
                this.showPercentageWarning(field, 'Values above 100% are not allowed for this field. Please enter a value between 0 and 100.');
                field.classList.add('border-yellow-500', 'focus:border-yellow-500', 'focus:ring-yellow-500');
                field.classList.remove('border-gray-300', 'border-red-500', 'focus:border-blue-500', 'focus:ring-blue-500', 'focus:border-red-500', 'focus:ring-red-500');
            }
        });
    }

    initializeValidationConditions() {
        // Check all fields with validation conditions on page load
        const fieldsWithValidation = document.querySelectorAll('.form-item-block[data-validation-condition]');
        debugLog(MODULE_NAME, `🔍 INITIALIZE VALIDATION: Found ${fieldsWithValidation.length} fields with validation conditions`);

        fieldsWithValidation.forEach((container, index) => {
            const itemId = container.getAttribute('data-item-id');
            const validationCondition = container.getAttribute('data-validation-condition');
            debugLog(MODULE_NAME, `   Field ${index + 1}: itemId=${itemId}, condition=${validationCondition ? validationCondition.substring(0, 100) : 'none'}...`);

            // Skip if container is hidden
            if (this.isFieldHidden(container)) {
                debugLog(MODULE_NAME, `   Field ${itemId} is hidden, skipping`);
                return;
            }

            // Skip if field is empty - don't show validation for empty fields
            if (this.isContainerEmpty(container)) {
                debugLog(MODULE_NAME, `   Field ${itemId} is empty, skipping validation`);
                return;
            }

            const parsedCondition = parseValidationConditionToObject(validationCondition);
            if (parsedCondition && this.shouldSkipValidationCondition(parsedCondition)) {
                debugLog(MODULE_NAME, `   Field ${itemId}: skipping (referenced field empty)`);
                return;
            }

            const primaryField = this.getPrimaryField(container);
            if (primaryField) {
                debugLog(MODULE_NAME, `   Checking validation condition for field ${itemId}`);
                this.checkValidationConditionForField(primaryField);
            } else {
                debugLog(MODULE_NAME, `   Field ${itemId} has no primary field`);
            }
        });
    }

    validateForm() {
        this.errors = [];
        this.errorFields.clear();

        // Validate regular required fields
        this.validateRequiredFields();

        // Validate repeat sections
        this.validateRepeatSections();

        // Validate dynamic indicators
        this.validateDynamicIndicators();

        // Validate public submission fields
        this.validatePublicSubmissionFields();

        // Validate indirect reach fields
        this.validateIndirectReachFields();

        // Validate percentage fields
        this.validatePercentageFields();

        // Validate validation conditions
        this.validateValidationConditions();

        return this.errors.length === 0;
    }

    validateRequiredFields() {
        // Get all form item blocks that might contain required fields
        const formItemBlocks = document.querySelectorAll('.form-item-block[data-item-id]');

        formItemBlocks.forEach(container => {
            // Skip if container is hidden
            if (this.isFieldHidden(container)) {
                return;
            }

            const isRequired = this.isFieldRequired(container);

            if (isRequired) {
                const isEmpty = this.isContainerEmpty(container);

                if (isEmpty) {
                    const fieldLabel = this.getFieldLabel(container);
                    const primaryField = this.getPrimaryField(container);
                    const itemId = container.getAttribute('data-item-id');

                    const error = {
                        field: primaryField || container,
                        container: container,
                        message: `${fieldLabel} is required`,
                        type: 'required'
                    };

                    this.errors.push(error);
                    if (primaryField) {
                        this.errorFields.add(primaryField.name || primaryField.id);
                    }

                    debugLog(MODULE_NAME, `❌ Required form-item-block empty:`);
                    debugLog(MODULE_NAME, `   data-item-id: "${itemId}"`);
                    debugLog(MODULE_NAME, `   Label: "${fieldLabel}"`);
                    debugLog(MODULE_NAME, `   Primary field: ${primaryField ? `${primaryField.tagName}[${primaryField.type}] #${primaryField.id || primaryField.name}` : 'None'}`);
                    debugLog(MODULE_NAME, `   Container HTML:`, container.outerHTML.substring(0, 200) + '...');
                }
            }
        });

        // Also check traditional required fields
        const directRequiredFields = document.querySelectorAll('[required]');
        directRequiredFields.forEach(field => {
            // Skip if already processed as part of a form-item-block
            if (field.closest('.form-item-block[data-item-id]')) {
                return;
            }

            // Skip fields in modals or outside the main form
            if (this.isFieldInModal(field) || !this.isFieldInMainForm(field)) {
                return;
            }

            if (this.isFieldHidden(field)) {
                return;
            }

            if (this.isFieldEmpty(field)) {
                const fieldLabel = this.getFieldLabel(field);
                const error = {
                    field: field,
                    container: field.closest('.form-group') || field.parentElement,
                    message: `${fieldLabel} is required`,
                    type: 'required'
                };

                this.errors.push(error);
                this.errorFields.add(field.name || field.id);

                debugLog(MODULE_NAME, `❌ Required direct field empty:`);
                debugLog(MODULE_NAME, `   Element: ${field.tagName}[${field.type || 'unknown'}]`);
                debugLog(MODULE_NAME, `   ID: "${field.id || 'no-id'}"`);
                debugLog(MODULE_NAME, `   Name: "${field.name || 'no-name'}"`);
                debugLog(MODULE_NAME, `   Label: "${fieldLabel}"`);
                debugLog(MODULE_NAME, `   Value: "${field.value || ''}"`);
            }
        });
    }

    validateRepeatSections() {
        const repeatSections = document.querySelectorAll('[data-section-type="repeat"]');

        repeatSections.forEach(section => {
            // Skip repeat sections hidden by relevance
            if (section.classList.contains('relevance-hidden') || (section.closest && section.closest('.relevance-hidden'))) {
                return;
            }
            const sectionId = section.id.replace('section-container-', '');
            const repeatEntries = section.querySelectorAll('.repeat-entry');

            // Check if repeat section has any entries
            if (repeatEntries.length === 0) {
                // Check if any fields in the original template are required
                const originalFields = section.querySelectorAll('.space-y-6 [required]');
                // Only enforce "at least one entry" when a required field would actually be shown/validated
                const visibleRequiredTemplateFields = Array.from(originalFields).filter(f => !this.isFieldHidden(f) && !f.disabled);
                if (visibleRequiredTemplateFields.length > 0) {
                    const sectionName = section.querySelector('h3, h4')?.textContent?.trim() || 'Repeat Section';
                    this.errors.push({
                        field: section,
                        container: section,
                        message: `${sectionName} requires at least one entry`,
                        type: 'repeat_empty'
                    });
                    debugLog(MODULE_NAME, `❌ Empty repeat section: ${sectionName}`);
                }
                return;
            }

            // Validate each repeat entry
            repeatEntries.forEach((entry, index) => {
                const requiredFields = entry.querySelectorAll('[required]');
                requiredFields.forEach(field => {
                    if (field.disabled || this.isFieldHidden(field)) return;
                    if (this.isFieldEmpty(field)) {
                        const fieldLabel = this.getFieldLabel(field);
                        const error = {
                            field: field,
                            container: entry,
                            message: `${fieldLabel} is required in entry ${index + 1}`,
                            type: 'repeat_required'
                        };

                        this.errors.push(error);
                        this.errorFields.add(field.name || field.id);

                        debugLog(MODULE_NAME, `❌ Required field empty in repeat entry ${index + 1}:`);
                        debugLog(MODULE_NAME, `   Element: ${field.tagName}[${field.type || 'unknown'}]`);
                        debugLog(MODULE_NAME, `   ID: "${field.id || 'no-id'}"`);
                        debugLog(MODULE_NAME, `   Name: "${field.name || 'no-name'}"`);
                        debugLog(MODULE_NAME, `   Label: "${fieldLabel}"`);
                        debugLog(MODULE_NAME, `   Value: "${field.value || ''}"`);
                        debugLog(MODULE_NAME, `   Section: ${section.querySelector('h3, h4')?.textContent?.trim() || 'Unknown'}`);
                    }
                });
            });
        });
    }

    validateDynamicIndicators() {
        const dynamicSections = document.querySelectorAll('[data-section-type="dynamic_indicators"]');

        dynamicSections.forEach(section => {
            const dynamicFields = section.querySelectorAll('[data-assignment-id]');

            dynamicFields.forEach(field => {
                if (this.isFieldHidden(field)) return;

                const fieldContainer = field.closest('.form-item-block');
                const isRequired = this.isFieldRequired(fieldContainer);

                // Treat data availability selections as valid answers and
                // use container-aware emptiness check for dynamic indicators
                if (isRequired && this.isContainerEmpty(fieldContainer)) {
                    const fieldLabel = this.getFieldLabel(field);
                    const error = {
                        field: field,
                        container: fieldContainer,
                        message: `${fieldLabel} is required`,
                        type: 'dynamic_required'
                    };

                    this.errors.push(error);
                    this.errorFields.add(field.name || field.id);

                    debugLog(MODULE_NAME, `❌ Required dynamic indicator empty: ${fieldLabel}`);
                }
            });
        });
    }

    validatePublicSubmissionFields() {
        const submitterSection = document.getElementById('submitter-information-section');
        if (!submitterSection) return;

        const requiredFields = submitterSection.querySelectorAll('[required]');
        requiredFields.forEach(field => {
            // Skip fields in modals or outside the main form
            if (this.isFieldInModal(field) || !this.isFieldInMainForm(field)) {
                return;
            }

            if (this.isFieldHidden(field)) {
                return;
            }

            if (this.isFieldEmpty(field)) {
                const fieldLabel = this.getFieldLabel(field);
                const error = {
                    field: field,
                    container: field.closest('.form-item-block'),
                    message: `${fieldLabel} is required`,
                    type: 'submitter_required'
                };

                this.errors.push(error);
                this.errorFields.add(field.name || field.id);

                debugLog(MODULE_NAME, `❌ Required submitter field empty: ${fieldLabel}`);
            }
        });
    }

    validateIndirectReachFields() {
        // Validate indirect reach fields to ensure they are numeric when present
        const indirectReachFields = document.querySelectorAll('input[name*="_indirect_reach"]');

        indirectReachFields.forEach(field => {
            // Only validate if the field is visible and has a value
            if (!this.isFieldHidden(field) && field.value && field.value.trim() !== '') {
                const value = field.value.trim();

                // Check if it's a valid number
                if (isNaN(value) || value === '') {
                    const label = this.getFieldLabel(field) || 'Indirect reach';
                    this.errors.push({
                        field: field,
                        container: field.closest('.form-item-block'),
                        message: `${label} must be a valid number.`,
                        type: 'indirect_reach_validation'
                    });
                    this.errorFields.add(field.name || field.id);

                    debugLog(MODULE_NAME, `❌ Invalid indirect reach value: ${value}`);
                }
            }
        });
    }

    validatePercentageFields() {
        // Validate percentage fields to ensure values don't exceed 100% when allow_over_100 is false
        const percentageFields = document.querySelectorAll('input[data-field-type="percentage"]');

        percentageFields.forEach(field => {
            // Skip if field is hidden or disabled
            if (this.isFieldHidden(field) || field.disabled) {
                return;
            }

            const value = parseFloat(field.value);

            // Only validate if there's a value
            if (isNaN(value) || field.value.trim() === '') {
                return;
            }

            // Get field config from data attribute
            let allowOver100 = false;
            const configAttr = field.getAttribute('data-field-config');
            if (configAttr) {
                try {
                    const config = JSON.parse(configAttr);
                    allowOver100 = config.allow_over_100 === true || config.allow_over_100 === 'true' || config.allow_over_100 === 1 || config.allow_over_100 === '1';
                } catch (e) {
                    debugLog(MODULE_NAME, `❌ Error parsing field config for percentage field: ${e}`);
                }
            }

            // If allow_over_100 is false and value > 100, show error
            if (!allowOver100 && value > 100) {
                const label = this.getFieldLabel(field) || 'Percentage field';
                this.errors.push({
                    field: field,
                    container: field.closest('.form-item-block') || field.parentElement,
                    message: `${label} cannot exceed 100%.`,
                    type: 'percentage_max_validation'
                });
                this.errorFields.add(field.name || field.id);

                debugLog(MODULE_NAME, `❌ Percentage value exceeds 100%: ${value}% (allow_over_100: ${allowOver100})`);
            }
        });
    }

    validateValidationConditions() {
        // Validate all fields that have validation conditions
        const fieldsWithValidation = document.querySelectorAll('.form-item-block[data-validation-condition]');

        debugLog(MODULE_NAME, `🔍 VALIDATION CONDITIONS: Found ${fieldsWithValidation.length} fields with validation conditions`);

        fieldsWithValidation.forEach(container => {
            // Skip if container is hidden
            if (this.isFieldHidden(container)) {
                return;
            }

            const validationCondition = container.getAttribute('data-validation-condition');
            const validationMessage = container.getAttribute('data-validation-message');
            const itemId = container.getAttribute('data-item-id');

            debugLog(MODULE_NAME, `🔍 VALIDATION CONDITIONS: Field ${itemId}`);
            debugLog(MODULE_NAME, `   Raw validation condition: ${validationCondition}`);
            debugLog(MODULE_NAME, `   Validation message: ${validationMessage}`);

            if (!validationCondition || !itemId) {
                debugLog(MODULE_NAME, `   ⚠️ Missing validation condition or item ID`);
                return;
            }

            // Check if the field has a value - if not, skip validation (don't show error for empty fields)
            if (this.isContainerEmpty(container)) {
                debugLog(MODULE_NAME, `   Field ${itemId} is empty, skipping validation`);
                return;
            }

            const parsedCondition = parseValidationConditionToObject(validationCondition);
            if (!parsedCondition) {
                debugLog(MODULE_NAME, `   ❌ Could not parse validation condition JSON`);
                return;
            }

            // If condition references another field (value_field_id), only run when that field has a value
            if (this.shouldSkipValidationCondition(parsedCondition)) {
                debugLog(MODULE_NAME, `   Field ${itemId}: skipping validation (referenced field is empty)`);
                return;
            }

            try {
                // Evaluate the validation condition - pass the parsed object, not the string
                // For validation conditions, we want the condition to be FALSE (violated) to show an error
                debugLog(MODULE_NAME, `   Calling evaluateConditions with:`, parsedCondition);
                const conditionPassed = evaluateConditions(parsedCondition);
                debugLog(MODULE_NAME, `   Condition evaluation result: ${conditionPassed}`);

                // If condition is false, validation is violated
                if (!conditionPassed) {
                    const fieldLabel = this.getFieldLabel(container);
                    const primaryField = this.getPrimaryField(container);

                    // Get custom validation message or use default
                    let message = validationMessage || `${fieldLabel} validation failed`;
                    try {
                        // Try to parse if it's JSON (might be escaped)
                        const parsedMessage = JSON.parse(validationMessage);
                        if (typeof parsedMessage === 'string') {
                            message = parsedMessage;
                        }
                    } catch (e) {
                        // Not JSON, use as-is
                    }

                    const error = {
                        field: primaryField || container,
                        container: container,
                        message: message,
                        type: 'validation_condition'
                    };

                    this.errors.push(error);
                    if (primaryField) {
                        this.errorFields.add(primaryField.name || primaryField.id);
                    }

                    debugLog(MODULE_NAME, `❌ Validation condition violated for field ${itemId}: ${message}`);
                }
            } catch (e) {
                debugLog(MODULE_NAME, `❌ Error evaluating validation condition for field ${itemId}: ${e}`);
            }
        });
    }

    checkValidationConditionForField(field) {
        // Find the container that has the validation condition
        const container = field.closest('.form-item-block[data-validation-condition]');
        if (!container) {
            return;
        }

        // Skip if container is hidden
        if (this.isFieldHidden(container)) {
            this.clearValidationWarning(container);
            return;
        }

        // Don't show validation error for a field that has no value yet (e.g. Local Units when user only typed in Branches)
        if (this.isContainerEmpty(container)) {
            this.clearValidationWarning(container);
            return;
        }

        const validationCondition = container.getAttribute('data-validation-condition');
        const validationMessage = container.getAttribute('data-validation-message');
        const itemId = container.getAttribute('data-item-id');

        debugLog(MODULE_NAME, `🔍 REAL-TIME VALIDATION: Checking field ${itemId}`);
        debugLog(MODULE_NAME, `   Raw validation condition: ${validationCondition}`);

        if (!validationCondition || !itemId) {
            debugLog(MODULE_NAME, `   ⚠️ Missing validation condition or item ID`);
            return;
        }

            const parsedCondition = parseValidationConditionToObject(validationCondition);
            if (!parsedCondition) {
                debugLog(MODULE_NAME, `   ❌ Could not parse validation condition JSON`);
                return;
            }

            // If condition references another field (value_field_id), only run when that field has a value
            if (this.shouldSkipValidationCondition(parsedCondition)) {
                debugLog(MODULE_NAME, `   Skipping real-time validation (referenced field is empty)`);
                this.clearValidationWarning(container);
                return;
            }

            try {
                // Evaluate the validation condition - pass the parsed object, not the string
                debugLog(MODULE_NAME, `   Calling evaluateConditions with parsedCondition:`, parsedCondition);
                const conditionPassed = evaluateConditions(parsedCondition);
                debugLog(MODULE_NAME, `   Condition evaluation result: ${conditionPassed}`);

                // If condition is false, validation is violated - show warning
                if (!conditionPassed) {
                    // Get custom validation message or use default
                    let message = validationMessage || 'This value does not meet the validation requirements';
                    try {
                        const parsedMessage = JSON.parse(validationMessage);
                        if (typeof parsedMessage === 'string') {
                            message = parsedMessage;
                        }
                    } catch (e) {
                        // Not JSON, use as-is
                    }
                    this.showValidationWarning(container, message);
                } else {
                    this.clearValidationWarning(container);
                }
            } catch (e) {
                debugLog(MODULE_NAME, `❌ Error checking validation condition for field ${itemId}: ${e}`);
            }
    }

    showValidationWarning(container, message) {
        const itemId = container.getAttribute('data-item-id');
        const warningId = `validation-warning-${itemId}`;
        let warningDiv = document.getElementById(warningId);

        // Try to use the existing error-field div if it exists
        const existingErrorDiv = container.querySelector(`#error-field-${itemId}`);
        if (existingErrorDiv) {
            warningDiv = existingErrorDiv;
            warningDiv.id = warningId; // Update ID for consistency
        }

        if (!warningDiv) {
            warningDiv = document.createElement('div');
            warningDiv.id = warningId;
            warningDiv.className = 'text-red-600 text-sm mt-1 flex items-center gap-1';

            // Insert after field or field container
            const primaryField = this.getPrimaryField(container);
            if (primaryField && primaryField.nextSibling) {
                container.insertBefore(warningDiv, primaryField.nextSibling);
            } else {
                container.appendChild(warningDiv);
            }
        }

        warningDiv.replaceChildren();
        const icon = document.createElement('i');
        icon.className = 'fas fa-exclamation-circle text-xs';
        const span = document.createElement('span');
        span.textContent = message;
        warningDiv.appendChild(icon);
        warningDiv.appendChild(span);
        warningDiv.style.display = 'flex';
        warningDiv.className = 'text-red-600 text-sm mt-1 flex items-center gap-1';

        // Add error styling to container and primary field
        container.classList.add('border-red-500', 'bg-red-50');
        container.classList.remove('border-gray-200');

        const primaryField = this.getPrimaryField(container);
        if (primaryField) {
            primaryField.classList.add('border-red-500', 'focus:border-red-500', 'focus:ring-red-500');
            primaryField.classList.remove('border-gray-300', 'focus:border-blue-500', 'focus:ring-blue-500');
        }
    }

    clearValidationWarning(container) {
        const itemId = container.getAttribute('data-item-id');
        if (!itemId) return;

        const warningId = `validation-warning-${itemId}`;
        const warningDiv = document.getElementById(warningId);
        if (warningDiv) {
            warningDiv.style.display = 'none';
        }

        // Also clear the error-field div if it exists
        const errorFieldDiv = container.querySelector(`#error-field-${itemId}`);
        if (errorFieldDiv) {
            errorFieldDiv.style.display = 'none';
        }

        // Remove error styling from container and primary field
        container.classList.remove('border-red-500', 'bg-red-50');
        container.classList.add('border-gray-200');

        const primaryField = this.getPrimaryField(container);
        if (primaryField) {
            primaryField.classList.remove('border-red-500', 'focus:border-red-500', 'focus:ring-red-500');
            primaryField.classList.add('border-gray-300', 'focus:border-blue-500', 'focus:ring-blue-500');
        }
    }

    checkValidationConditionsForReferencedField(changedField) {
        // When a field changes, check all validation conditions that might reference it
        const changedFieldContainer = changedField.closest('.form-item-block');
        if (!changedFieldContainer) return;

        const changedItemId = changedFieldContainer.getAttribute('data-item-id');
        if (!changedItemId) return;

        // Extract numeric ID: prefixed format (question_66) or plain numeric (entry form uses data-item-id="961")
        let numericId = null;
        const match = changedItemId.match(/^(question_|indicator_|document_field_)(\d+)$/);
        if (match) {
            numericId = parseInt(match[2], 10);
        } else if (/^\d+$/.test(String(changedItemId))) {
            numericId = parseInt(changedItemId, 10);
        }

        // Find all fields with validation conditions
        const fieldsWithValidation = document.querySelectorAll('.form-item-block[data-validation-condition]');

        fieldsWithValidation.forEach(container => {
            const validationCondition = container.getAttribute('data-validation-condition');
            if (!validationCondition) return;

            try {
                const conditionData = parseValidationConditionToObject(validationCondition);
                if (!conditionData) return;
                const conditions = conditionData.conditions;
                if (!conditions || !Array.isArray(conditions)) return;

                // Check if any condition references the changed field
                const referencesChangedField = conditions.some(condition => {
                    // Check if condition references the changed field by item_id
                    if (condition.item_id) {
                        // Handle numeric IDs
                        if (numericId && parseInt(condition.item_id, 10) === numericId) {
                            return true;
                        }
                        // Handle prefixed IDs
                        if (condition.item_id === changedItemId) {
                            return true;
                        }
                    }
                    // Check if condition references the changed field by value_field_id
                    if (condition.value_field_id !== null && condition.value_field_id !== undefined) {
                        if (numericId && parseInt(condition.value_field_id, 10) === numericId) {
                            return true;
                        }
                    }
                    return false;
                });

                // If this validation condition references the changed field, re-check it
                if (referencesChangedField) {
                    this.checkValidationConditionForField(this.getPrimaryField(container) || container);
                }
            } catch (e) {
                debugLog(MODULE_NAME, `❌ Error checking validation condition references: ${e}`);
            }
        });
    }

    isFieldHidden(field) {
        // Check if field or its container is hidden.
        //
        // IMPORTANT: Relevance conditions may hide the *layout wrapper* around `.form-item-block`
        // (see `conditions.js` -> setWrapperVisibility). In that case the `.form-item-block` itself
        // remains "display: block" so we must also consider its wrapper/row visibility.
        const container = field && field.closest
            ? field.closest('.form-item-block, .repeat-entry, .disaggregation-inputs')
            : null;
        if (!container) return false;

        // Relevance conditions: always treat as hidden (self or any ancestor)
        if (container.classList.contains('relevance-hidden') || (container.closest && container.closest('.relevance-hidden'))) {
            return true;
        }

        // Check CSS display/visibility on the container itself
        try {
            const computedStyle = window.getComputedStyle(container);
            if (computedStyle.display === 'none' || computedStyle.visibility === 'hidden') return true;
        } catch (_) {
            // ignore
        }

        // Check hidden class on the container itself
        if (container.classList.contains('hidden')) return true;

        // Check the layout wrapper & row that relevance uses to remove gaps.
        // Wrappers created by `layout.js` include both `flex-shrink-0` and `min-w-0`.
        const wrapper = container.parentElement;
        const isLayoutWrapper =
            !!wrapper &&
            wrapper.classList &&
            wrapper.classList.contains('flex-shrink-0') &&
            wrapper.classList.contains('min-w-0');

        const isHiddenByStyleOrClass = (el) => {
            if (!el || !el.classList) return false;
            if (el.classList.contains('relevance-hidden')) return true;
            if (el.classList.contains('hidden')) return true;
            try {
                const cs = window.getComputedStyle(el);
                return cs.display === 'none' || cs.visibility === 'hidden';
            } catch (_) {
                return false;
            }
        };

        if (isLayoutWrapper) {
            if (isHiddenByStyleOrClass(wrapper)) return true;

            // Row is the wrapper's parent; it may be hidden when all wrappers in the row are hidden.
            const rowDiv = wrapper.parentElement;
            if (rowDiv) {
                // Only treat it as a relevance/layout row if it actually contains layout wrappers.
                const looksLikeWrapperRow = rowDiv.querySelector && rowDiv.querySelector('.flex-shrink-0.min-w-0');
                if (looksLikeWrapperRow && isHiddenByStyleOrClass(rowDiv)) return true;
            }
        }

        // Check if parent section is hidden (class-based only).
        //
        // IMPORTANT: Do NOT treat "section display:none" as hidden here because paginated
        // templates hide non-active pages by setting section.style.display='none'. We still
        // must validate required fields across all pages on Submit.
        //
        // Relevance-hidden sections are still skipped via class checks below.
        const section = container.closest('[data-section-type]');
        if (section) {
            if (section.classList.contains('hidden') || section.classList.contains('relevance-hidden')) return true;
        }

        return false;
    }

    ensurePaginatedPageVisibleForElement(element) {
        const sectionsContainer = document.getElementById('sections-container');
        if (!sectionsContainer) return;
        const isPaginated = sectionsContainer.dataset && sectionsContainer.dataset.isPaginated === 'true';
        if (!isPaginated) return;

        const pageHost = element.closest('[data-page-number]');
        if (!pageHost) return;
        const pageNum = parseInt(pageHost.dataset.pageNumber || '1', 10);
        if (!Number.isFinite(pageNum)) return;

        // Prefer the pagination module's API if available (keeps controls/URL in sync)
        if (window.__ifrcPagination && typeof window.__ifrcPagination.showPageByNumber === 'function') {
            window.__ifrcPagination.showPageByNumber(pageNum);
            return;
        }

        // Fallback: emulate pagination by toggling visibility based on page number
        const allPageEls = Array.from(sectionsContainer.querySelectorAll('[data-page-number]'));
        allPageEls.forEach(el => {
            const elPageNum = parseInt(el.dataset.pageNumber || '1', 10);
            el.style.display = (elPageNum === pageNum) ? '' : 'none';
        });
    }

    isFieldInModal(field) {
        // Check if field is inside a modal
        const modal = field.closest('[id$="-modal"], .modal, [role="dialog"]');
        if (modal) {
            debugLog(MODULE_NAME, `⏭️ Skipping field in modal: ${field.name || field.id}`);
            return true;
        }
        return false;
    }

    isFieldInMainForm(field) {
        // Check if field is inside the main form
        const mainForm = document.getElementById('focalDataEntryForm');
        if (!mainForm) {
            // If no main form found, assume it's valid
            return true;
        }

        const isInMainForm = mainForm.contains(field);
        if (!isInMainForm) {
            debugLog(MODULE_NAME, `⏭️ Skipping field outside main form: ${field.name || field.id}`);
        }
        return isInMainForm;
    }

    isFieldRequired(fieldContainer) {
        if (!fieldContainer) return false;

        // Check for required attribute on inputs
        const inputs = fieldContainer.querySelectorAll('input, select, textarea');
        for (const input of inputs) {
            if (input.hasAttribute('required')) return true;
        }

        // Check for required asterisk in label
        const label = fieldContainer.querySelector('label');
        if (label && label.innerHTML.includes('<span class="text-red-500">*</span>')) {
            return true;
        }

        return false;
    }

    isContainerEmpty(container) {
        // Check different types of field containers

        // 0. If data availability is selected, treat as answered
        if (this.isMarkedAsUnavailableOrNotApplicable(container)) {
            return false;
        }

        // Helper: treat element as visible only if it's actually displayed
        const isElementVisible = (el) => {
            if (!el) return false;
            // Fast checks for common patterns
            if (el.classList && el.classList.contains('hidden')) return false;
            // Inline style is not sufficient; use computed style too
            const cs = window.getComputedStyle(el);
            if (!cs) return true;
            if (cs.display === 'none') return false;
            if (cs.visibility === 'hidden') return false;
            return true;
        };

        // 1. Check for matrix containers (matrix tables)
        const matrixContainer = container.querySelector('.matrix-container');
        if (matrixContainer) {
            // Check if matrix has at least one filled cell
            // Check number inputs
            const numberInputs = matrixContainer.querySelectorAll('input[type="number"]');
            const hasNumberValue = Array.from(numberInputs).some(input => {
                const value = input.value?.trim();
                // Consider it filled if there's a value (even if it's 0, as 0 is a valid entry)
                return value !== '' && !isNaN(parseFloat(value)) && isFinite(parseFloat(value));
            });
            if (hasNumberValue) return false;

            // Check checkboxes (tick columns)
            const checkboxes = matrixContainer.querySelectorAll('input[type="checkbox"][data-cell-key]');
            const hasCheckedBox = Array.from(checkboxes).some(cb => cb.checked);
            if (hasCheckedBox) return false;

            // Also check the hidden field value as a fallback
            const hiddenField = matrixContainer.querySelector('input[type="hidden"][name^="field_value"]');
            if (hiddenField && hiddenField.value) {
                try {
                    const matrixData = JSON.parse(hiddenField.value);
                    // Check if there's any actual data (excluding _table metadata)
                    const dataKeys = Object.keys(matrixData).filter(key => key !== '_table');
                    if (dataKeys.length > 0) {
                        // Check if any value is non-zero/non-empty
                        const hasData = dataKeys.some(key => {
                            const value = matrixData[key];
                            if (typeof value === 'object' && value !== null) {
                                // For variable columns, check if they have values
                                return value.value !== undefined && value.value !== null && value.value !== '';
                            }
                            // Consider it filled if there's a value (even if it's 0, as 0 is a valid entry)
                            return value !== undefined && value !== null && value !== '';
                        });
                        if (hasData) return false;
                    }
                } catch (e) {
                    // If JSON parsing fails, ignore and continue with other checks
                }
            }

            // Matrix container exists but has no values
            return true;
        }

        // 2. Check for disaggregation inputs (tables with sex/age breakdown)
        const disaggregationInputs = container.querySelectorAll('.disaggregation-inputs');
        if (disaggregationInputs.length > 0) {
            // Check if any visible disaggregation section has values
            for (const disagSection of disaggregationInputs) {
                // Skip if this is a matrix container (already checked above)
                if (disagSection.classList.contains('matrix-container')) continue;

                // Use computed visibility (not just inline style) to pick the active mode section
                if (isElementVisible(disagSection)) {
                    // numeric-formatting.js converts number inputs to text and marks them data-numeric="true"
                    const inputs = disagSection.querySelectorAll('input[type="number"], input[data-numeric="true"]');
                    const hasValue = Array.from(inputs).some(input => {
                        const value = input.value?.trim();
                        return value && !isNaN(parseFloat(value));
                    });
                    if (hasValue) return false;
                }
            }
            // If we have disaggregation but no values, it's empty
            return true;
        }

        // 3. Check for reporting mode selection
        const reportingModeInputs = container.querySelectorAll('input[name$="_reporting_mode"]');
        if (reportingModeInputs.length > 0) {
            const hasSelectedMode = Array.from(reportingModeInputs).some(input => input.checked);
            if (!hasSelectedMode) return true;

            // If mode is selected, check the corresponding values
            const checkedMode = Array.from(reportingModeInputs).find(input => input.checked);
            if (checkedMode) {
                const modeValue = checkedMode.value;
                const modeInputs = container.querySelector(`[data-mode="${modeValue}"]`);
                if (modeInputs && isElementVisible(modeInputs)) {
                    // numeric-formatting.js converts number inputs to text and marks them data-numeric="true"
                    const inputs = modeInputs.querySelectorAll('input[type="number"], input[data-numeric="true"]');
                    const hasValue = Array.from(inputs).some(input => {
                        const value = input.value?.trim();
                        return value && !isNaN(parseFloat(value));
                    });
                    return !hasValue;
                }
            }
        }

        // 4. Check regular inputs
        const regularInputs = container.querySelectorAll('input:not([name$="_reporting_mode"]), select, textarea');
        for (const input of regularInputs) {
            // Skip inputs inside disaggregation tables (already checked above)
            if (input.closest('.disaggregation-inputs')) continue;

            if (!this.isFieldEmpty(input)) {
                return false;
            }
        }

        // 5. Check for yes/no checkbox groups
        const yesNoGroups = this.getYesNoGroups(container);
        for (const groupName of yesNoGroups) {
            const checkboxes = container.querySelectorAll(`input[name="${groupName}"]`);
            const hasChecked = Array.from(checkboxes).some(cb => cb.checked);
            if (hasChecked) return false;
        }

        return true;
    }

    // Consider a field as answered when either data availability option is checked
    isMarkedAsUnavailableOrNotApplicable(container) {
        if (!container) return false;
        const dna = container.querySelector('input[type="checkbox"][name*="_data_not_available"]:checked');
        const na = container.querySelector('input[type="checkbox"][name*="_not_applicable"]:checked');
        return !!(dna || na);
    }

    getPrimaryField(container) {
        // Find the main input field to focus on for errors

        // 1. Look for text/number inputs first
        let input = container.querySelector('input[type="text"], input[type="number"], input[type="email"], input[type="date"], textarea');
        if (input) return input;

        // 2. Look for select dropdowns
        input = container.querySelector('select');
        if (input) return input;

        // 3. Look for radio buttons
        input = container.querySelector('input[type="radio"]');
        if (input) return input;

        // 4. Look for checkboxes
        input = container.querySelector('input[type="checkbox"]');
        if (input) return input;

        // 5. Look for file inputs
        input = container.querySelector('input[type="file"]');
        if (input) return input;

        // 6. Return first input found
        input = container.querySelector('input');
        if (input) return input;

        return null;
    }

    /**
     * Find the form-item-block container for a given item id (numeric or prefixed).
     * Used to check if a value_field_id referenced field is empty before applying validation.
     */
    getContainerForItemId(itemId) {
        if (itemId == null || itemId === '') return null;
        const idStr = String(itemId).trim();
        const numericId = parseInt(itemId, 10);
        // Entry form uses data-item-id="{{ field.id }}" (numeric id); form builder preview may use prefixed ids
        const possibleIds = [
            idStr,
            `question_${numericId}`,
            `indicator_${numericId}`,
            `document_field_${numericId}`
        ];
        for (const possibleId of possibleIds) {
            if (possibleId === '' || possibleId === 'undefined' || possibleId === 'NaN') continue;
            const container = document.querySelector(`.form-item-block[data-item-id="${possibleId}"]`);
            if (container) return container;
        }
        if (!idStr.match(/^\d+$/)) {
            const container = document.querySelector(`.form-item-block[data-item-id="${itemId}"]`);
            if (container) return container;
        }
        return null;
    }

    /**
     * Return true if this validation condition should be skipped because it references
     * another field (value_field_id) and that field is empty. This avoids showing
     * "branches must be less than local units" when local units is still empty.
     */
    shouldSkipValidationCondition(parsedCondition) {
        const conditions = parsedCondition?.conditions;
        if (!conditions || !Array.isArray(conditions)) return false;
        for (const c of conditions) {
            const valueFieldId = c?.value_field_id;
            if (valueFieldId === null || valueFieldId === undefined) continue;
            const refContainer = this.getContainerForItemId(valueFieldId);
            if (!refContainer) continue;
            if (this.isFieldHidden(refContainer)) return true;
            if (this.isContainerEmpty(refContainer)) {
                debugLog(MODULE_NAME, `   Skipping validation: referenced field (value_field_id: ${valueFieldId}) is empty`);
                return true;
            }
        }
        return false;
    }

    getYesNoGroups(container) {
        // Find checkbox groups that represent yes/no questions
        const checkboxes = container.querySelectorAll('input[type="checkbox"]');
        const groups = new Set();

        checkboxes.forEach(cb => {
            if (cb.value === 'yes' || cb.value === 'no') {
                groups.add(cb.name);
            }
        });

        return Array.from(groups);
    }

    isFieldEmpty(field) {
        // If this field belongs to a container where a data availability option
        // is selected, treat it as not empty (i.e., answered)
        try {
            const container = field.closest ? field.closest('.form-item-block') : null;
            if (container && this.isMarkedAsUnavailableOrNotApplicable(container)) {
                return false;
            }
        } catch (_) { /* no-op */ }

        const fieldType = field.type || field.tagName.toLowerCase();
        const value = field.value?.trim();

        switch (fieldType) {
            case 'checkbox':
                // For yes/no fields, check if any checkbox in the group is checked
                const fieldName = field.name;
                if (fieldName) {
                    const relatedCheckboxes = document.querySelectorAll(`[name="${fieldName}"]`);
                    if (relatedCheckboxes.length > 1) {
                        // Multiple checkboxes with same name (yes/no)
                        return !Array.from(relatedCheckboxes).some(cb => cb.checked);
                    }
                }
                return !field.checked;

            case 'radio':
                const radioName = field.name;
                const checkedRadio = document.querySelector(`[name="${radioName}"]:checked`);
                return !checkedRadio;

            case 'select-one':
            case 'select':
                return !value || value === '';

            case 'file':
                return !field.files || field.files.length === 0;

            case 'number':
                return !value || isNaN(parseFloat(value));

            default:
                return !value;
        }
    }

    getFieldLabel(field) {
        // Try to find label by various methods
        let label = '';

        // If field is a container, look for label inside it
        if (field.classList && field.classList.contains('form-item-block')) {
            const labelEl = field.querySelector('label');
            if (labelEl) {
                label = labelEl.textContent.trim();
            }
        } else {
            // Method 1: Associated label element
            if (field.id) {
                const labelEl = document.querySelector(`label[for="${field.id}"]`);
                if (labelEl) {
                    label = labelEl.textContent.trim();
                }
            }

            // Method 2: Parent container label
            if (!label) {
                const container = field.closest('.form-item-block, .form-group');
                if (container) {
                    const labelEl = container.querySelector('label');
                    if (labelEl) {
                        label = labelEl.textContent.trim();
                    }
                }
            }

            // Method 3: Field name or placeholder
            if (!label) {
                label = field.name || field.placeholder || field.id || 'Field';
            }
        }

        // Clean up label (remove asterisks, numbers, arrows and extra whitespace)
        label = label.replace(/\*/g, '').replace(/^\d+\.\s*/, '').replace(/↳\s*/, '').trim();

        // If label is too long, truncate it
        if (label.length > 60) {
            label = label.substring(0, 57) + '...';
        }

        return label || 'Field';
    }

    displayErrors() {
        debugLog(MODULE_NAME, `🚨 Displaying ${this.errors.length} validation errors:`);

        // Log detailed error information
        this.errors.forEach((error, index) => {
            debugLog(MODULE_NAME, `\nError ${index + 1}:`);
            debugLog(MODULE_NAME, `   Type: ${error.type}`);
            debugLog(MODULE_NAME, `   Message: "${error.message}"`);
            debugLog(MODULE_NAME, `   Field: ${error.field.tagName || 'Container'}[${error.field.type || 'unknown'}]`);
            debugLog(MODULE_NAME, `   Field ID: "${error.field.id || 'no-id'}"`);
            debugLog(MODULE_NAME, `   Field Name: "${error.field.name || 'no-name'}"`);
            if (error.field.getAttribute && error.field.getAttribute('data-item-id')) {
                debugLog(MODULE_NAME, `   data-item-id: "${error.field.getAttribute('data-item-id')}"`);
            }
        });

        // Show flash message for form submission failure
        this.showValidationFlashMessage();

        // Show error summary at top
        this.showErrorSummary();

        // Highlight individual fields
        this.errors.forEach(error => {
            this.highlightFieldError(error);
        });
    }

    showValidationFlashMessage() {
        const errorCount = this.errors.length;
        const message = `Form submission failed: ${errorCount} required field${errorCount > 1 ? 's are' : ' is'} missing. Please correct the highlighted errors below.`;
        this.showFlashMessage(message, 'danger');
    }

    showFlashMessage(message, category = 'info') {
        if (typeof window.showFlashMessage === 'function') {
            window.showFlashMessage(message, category);
        }
    }

    showErrorSummary() {
        // Remove existing error summary
        const existingSummary = document.getElementById('validation-error-summary');
        if (existingSummary) {
            existingSummary.remove();
        }

        // Create error summary using DOM construction
        const summary = document.createElement('div');
        summary.id = 'validation-error-summary';
        summary.className = 'bg-red-50 border-l-4 border-red-400 p-4 mb-6 rounded';

        const flexDiv = document.createElement('div');
        flexDiv.className = 'flex';

        const iconDiv = document.createElement('div');
        iconDiv.className = 'flex-shrink-0';
        const icon = document.createElement('i');
        icon.className = 'fas fa-exclamation-triangle text-red-400';
        iconDiv.appendChild(icon);

        const contentDiv = document.createElement('div');
        contentDiv.className = 'ml-3';

        const heading = document.createElement('h3');
        heading.className = 'text-sm font-medium text-red-800';
        heading.textContent = 'Please correct the following errors:';

        const listContainer = document.createElement('div');
        listContainer.className = 'mt-2 text-sm text-red-700';
        const ul = document.createElement('ul');
        ul.className = 'list-disc list-inside space-y-1';

        this.errors.forEach(error => {
            const li = document.createElement('li');
            const errorBtn = document.createElement('button');
            errorBtn.type = 'button';
            errorBtn.className = 'text-red-600 hover:text-red-800 underline error-link';
            errorBtn.setAttribute('data-field-id', error.field.id || error.field.name || '');
            errorBtn.textContent = error.message;
            li.appendChild(errorBtn);
            ul.appendChild(li);
        });

        listContainer.appendChild(ul);
        contentDiv.appendChild(heading);
        contentDiv.appendChild(listContainer);
        flexDiv.appendChild(iconDiv);
        flexDiv.appendChild(contentDiv);
        summary.appendChild(flexDiv);

        // Insert at top of form
        const form = document.getElementById('focalDataEntryForm');
        if (form) {
            form.insertBefore(summary, form.firstChild);
        } else {
            const container = document.querySelector('.container');
            if (container) {
                container.insertBefore(summary, container.firstChild);
            }
        }

        // Add click handlers for error links
        summary.querySelectorAll('.error-link').forEach(link => {
            link.addEventListener('click', (e) => {
                const fieldId = e.target.dataset.fieldId;
                const field = document.getElementById(fieldId) || document.querySelector(`[name="${fieldId}"]`);
                if (field) {
                    this.scrollToField(field);
                    field.focus();
                }
            });
        });
    }

    highlightFieldError(error) {
        const { field, container, message } = error;

        // Add error styling to container
        if (container) {
            container.classList.add('border-red-500', 'bg-red-50');
            container.classList.remove('border-gray-200');
        }

        // Add error styling to field
        field.classList.add('border-red-500', 'focus:border-red-500', 'focus:ring-red-500');
        field.classList.remove('border-gray-300', 'focus:border-blue-500', 'focus:ring-blue-500');

        // Show error message - use generic message for field display, but keep original message for summary
        this.showFieldErrorMessage(field, 'This field is required');
    }

    showFieldErrorMessage(field, message) {
        const errorId = `error-${field.id || field.name}`;
        let errorDiv = document.getElementById(errorId);

        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.id = errorId;
            errorDiv.className = 'text-red-600 text-sm mt-1';

            // Insert after field or field container
            const container = field.closest('.form-item-block') || field.parentElement;
            container.appendChild(errorDiv);
        }

        errorDiv.textContent = message;
        errorDiv.style.display = 'block';
    }

    clearFieldError(field) {
        const container = field.closest('.form-item-block, .form-group');

        // Remove error styling from container
        if (container) {
            container.classList.remove('border-red-500', 'bg-red-50');
            container.classList.add('border-gray-200');
        }

        // Remove error styling from field
        field.classList.remove('border-red-500', 'focus:border-red-500', 'focus:ring-red-500', 'border-yellow-500', 'focus:border-yellow-500', 'focus:ring-yellow-500');
        field.classList.add('border-gray-300', 'focus:border-blue-500', 'focus:ring-blue-500');

        // Hide error message
        const errorId = `error-${field.id || field.name}`;
        const errorDiv = document.getElementById(errorId);
        if (errorDiv) {
            errorDiv.style.display = 'none';
        }

        // Clear percentage warning if it's a percentage field
        if (field.getAttribute('data-field-type') === 'percentage') {
            this.clearPercentageWarning(field);
        }

        // Remove from error fields set
        this.errorFields.delete(field.name);
        this.errorFields.delete(field.id);
    }

    clearErrors() {
        // Remove error summary
        const summary = document.getElementById('validation-error-summary');
        if (summary) {
            summary.remove();
        }

        // Remove validation flash messages (those created by this module)
        const flashMessages = document.querySelectorAll('.alert.alert-danger');
        flashMessages.forEach(msg => {
            const messageText = msg.querySelector('.alert-message')?.textContent || '';
            if (messageText.includes('Form submission failed:') && messageText.includes('required field')) {
                msg.remove();
            }
        });

        // Clear field errors
        this.errorFields.forEach(fieldIdentifier => {
            const field = document.getElementById(fieldIdentifier) ||
                         document.querySelector(`[name="${fieldIdentifier}"]`);
            if (field) {
                this.clearFieldError(field);
            }
        });

        // Clear existing error divs
        document.querySelectorAll('[id^="error-field-"], [id^="error-"]').forEach(errorDiv => {
            errorDiv.style.display = 'none';
        });

        this.errors = [];
        this.errorFields.clear();
    }

    scrollToFirstError() {
        if (this.errors.length === 0) return;

        const firstError = this.errors[0];
        this.scrollToField(firstError.field);

        // Focus the field after scrolling
        setTimeout(() => {
            firstError.field.focus();
        }, 500);
    }

    /** Find the scrollable container (main element or window). */
    getScrollableContainer(element) {
        // Prefer a scrollable <main> container if present; fallback to window.
        const mainElement =
            document.querySelector('main[style*="overflow-y"]') ||
            document.querySelector('main');

        if (mainElement) {
            const isScrollable = mainElement.scrollHeight > mainElement.clientHeight;
            if (isScrollable) return mainElement;
        }

        return window;
    }

    scrollToField(field) {
        const container = field.closest('.form-item-block, .repeat-entry') || field;

        // If paginated, ensure the field's page is visible before scrolling
        try {
            this.ensurePaginatedPageVisibleForElement(container);
        } catch (_) { /* no-op */ }

        // Close mobile navigation if open
        const mobileNav = document.getElementById('section-navigation-sidebar');
        const overlay = document.getElementById('mobile-nav-overlay');
        if (mobileNav && overlay) {
            mobileNav.classList.add('-translate-x-full');
            overlay.classList.add('hidden');
            document.body.classList.remove('overflow-hidden');
        }

        // Scroll to field with "near top" protection and without over-scrolling.
        // Use CSS scroll-margin-top when present; fallback to 100px.
        // Also supports pages where <main> is the scroll container (not window).
        setTimeout(() => {
            const scrollContainer = this.getScrollableContainer(container);
            const isMainContainer = scrollContainer !== window;

            const rect = container.getBoundingClientRect();
            const computed = window.getComputedStyle(container);
            const scrollMarginTop = parseInt(computed.scrollMarginTop || '0', 10) || 100;
            const paddingBottom = 16;

            let targetTop;

            if (isMainContainer) {
                const containerRect = scrollContainer.getBoundingClientRect();
                const visibleTop = containerRect.top + scrollMarginTop;
                const visibleBottom = containerRect.bottom - paddingBottom;

                if (rect.top < visibleTop) {
                    // Scroll up just enough to show the element below the header offset
                    const topRel = rect.top - containerRect.top;
                    targetTop = Math.max(0, scrollContainer.scrollTop + topRel - scrollMarginTop);
                } else if (rect.bottom > visibleBottom) {
                    // Scroll down just enough to show the bottom
                    const delta = rect.bottom - visibleBottom;
                    targetTop = Math.max(0, scrollContainer.scrollTop + delta);
                } else {
                    // Already in view; avoid any scroll to prevent "over-scrolling"
                    return;
                }

                scrollContainer.scrollTo({ top: targetTop, behavior: 'smooth' });
            } else {
                const visibleTop = scrollMarginTop;
                const visibleBottom = window.innerHeight - paddingBottom;

                if (rect.top < visibleTop) {
                    targetTop = Math.max(0, window.pageYOffset + rect.top - scrollMarginTop);
                } else if (rect.bottom > visibleBottom) {
                    const delta = rect.bottom - visibleBottom;
                    targetTop = Math.max(0, window.pageYOffset + delta);
                } else {
                    return;
                }

                window.scrollTo({ top: targetTop, behavior: 'smooth' });
            }
        }, 50);
    }

    // Debug helpers
    debugValidation() {
        debugLog(MODULE_NAME, '🔍 Running comprehensive validation debug...');

        // Debug form item blocks
        const formItemBlocks = document.querySelectorAll('.form-item-block[data-item-id]');
        debugLog(MODULE_NAME, `\n📋 Found ${formItemBlocks.length} form item blocks:`);

        formItemBlocks.forEach((container, index) => {
            const itemId = container.getAttribute('data-item-id');
            const label = this.getFieldLabel(container);
            const isRequired = this.isFieldRequired(container);
            const isHidden = this.isFieldHidden(container);
            const isEmpty = isRequired ? this.isContainerEmpty(container) : 'N/A';
            const primaryField = this.getPrimaryField(container);

            debugLog(MODULE_NAME, `\n${index + 1}. Container [data-item-id="${itemId}"]:`);
            debugLog(MODULE_NAME, `   Label: "${label}"`);
            debugLog(MODULE_NAME, `   Required: ${isRequired}`);
            debugLog(MODULE_NAME, `   Hidden: ${isHidden}`);
            debugLog(MODULE_NAME, `   Empty: ${isEmpty}`);
            debugLog(MODULE_NAME, `   Primary field: ${primaryField ? `${primaryField.tagName}[${primaryField.type || 'unknown'}] #${primaryField.id || primaryField.name}` : 'None'}`);

            if (isRequired && !isHidden && isEmpty) {
                debugLog(MODULE_NAME, `   ❌ VALIDATION ERROR: This field is required but empty`);
            }
        });

        // Debug direct required fields
        const directRequiredFields = document.querySelectorAll('[required]');
        debugLog(MODULE_NAME, `\n📋 Found ${directRequiredFields.length} fields with 'required' attribute:`);

        directRequiredFields.forEach((field, index) => {
            const inFormBlock = field.closest('.form-item-block[data-item-id]');
            const inModal = this.isFieldInModal(field);
            const inMainForm = this.isFieldInMainForm(field);
            const isHidden = this.isFieldHidden(field);
            const isEmpty = this.isFieldEmpty(field);
            const label = this.getFieldLabel(field);

            debugLog(MODULE_NAME, `\n${index + 1}. Field ${field.tagName}[${field.type || 'unknown'}]:`);
            debugLog(MODULE_NAME, `   ID: "${field.id || 'no-id'}"`);
            debugLog(MODULE_NAME, `   Name: "${field.name || 'no-name'}"`);
            debugLog(MODULE_NAME, `   Label: "${label}"`);
            debugLog(MODULE_NAME, `   In form block: ${!!inFormBlock}`);
            debugLog(MODULE_NAME, `   In modal: ${inModal}`);
            debugLog(MODULE_NAME, `   In main form: ${inMainForm}`);
            debugLog(MODULE_NAME, `   Hidden: ${isHidden}`);
            debugLog(MODULE_NAME, `   Empty: ${isEmpty}`);
            debugLog(MODULE_NAME, `   Value: "${field.value || ''}"`);

            const shouldValidate = !inFormBlock && !inModal && inMainForm && !isHidden;
            debugLog(MODULE_NAME, `   Should validate: ${shouldValidate}`);

            if (shouldValidate && isEmpty) {
                debugLog(MODULE_NAME, `   ❌ VALIDATION ERROR: This required field is empty`);
            }
        });

        // Summary
        const totalErrors = this.countValidationErrors();
        debugLog(MODULE_NAME, `\n📊 VALIDATION SUMMARY:`);
        debugLog(MODULE_NAME, `   Total potential errors: ${totalErrors}`);
        debugLog(MODULE_NAME, `   Use validateForm() to see actual validation results`);
    }

    countValidationErrors() {
        let errorCount = 0;

        // Count form item block errors
        const formItemBlocks = document.querySelectorAll('.form-item-block[data-item-id]');
        formItemBlocks.forEach(container => {
            if (!this.isFieldHidden(container) && this.isFieldRequired(container) && this.isContainerEmpty(container)) {
                errorCount++;
            }
        });

        // Count direct required field errors
        const directRequiredFields = document.querySelectorAll('[required]');
        directRequiredFields.forEach(field => {
            if (!field.closest('.form-item-block[data-item-id]') &&
                !this.isFieldInModal(field) &&
                this.isFieldInMainForm(field) &&
                !this.isFieldHidden(field) &&
                this.isFieldEmpty(field)) {
                errorCount++;
            }
        });

        return errorCount;
    }

    // Method to manually trigger validation (for testing)
    validateNow() {
        this.clearErrors();
        const isValid = this.validateForm();

        if (!isValid) {
            this.displayErrors();
            this.scrollToFirstError();
        }

        return isValid;
    }

    // Helper method to check if a repeat section would cause validation errors
    wouldRepeatSectionCauseError(section) {
        const repeatEntries = section.querySelectorAll('.repeat-entry');
        const originalRequired = section.querySelectorAll('.space-y-6 [required]');

        // If no entries but has required fields in template
        if (repeatEntries.length === 0 && originalRequired.length > 0) {
            return true;
        }

        // Check each repeat entry for missing required fields
        for (const entry of repeatEntries) {
            const requiredFields = entry.querySelectorAll('[required]');
            for (const field of requiredFields) {
                if (this.isFieldEmpty(field)) {
                    return true;
                }
            }
        }

        return false;
    }
}

// Initialize the validator
let formValidator;

export function initializeFormValidation() {
    debugLog(MODULE_NAME, '🚀 FORM VALIDATION: initializeFormValidation() called');
    if (!formValidator) {
        debugLog(MODULE_NAME, '🚀 FORM VALIDATION: Creating new FormValidator instance');
        formValidator = new FormValidator();
        debugLog(MODULE_NAME, '✅ Form validation module initialized');

        // Make validator available globally for debugging
        window.formValidator = formValidator;
        window.debugValidation = () => formValidator.debugValidation();
        window.validateForm = () => formValidator.validateNow();

        // Add comprehensive diagnostic functions
        window.checkFormValidation = () => {
            debugLog(MODULE_NAME, '🔍 FORM VALIDATION DIAGNOSTIC:');
            debugLog(MODULE_NAME, '- FormValidator exists:', !!window.formValidator);
            debugLog(MODULE_NAME, '- Form element exists:', !!document.getElementById('focalDataEntryForm'));
            debugLog(MODULE_NAME, '- Debug config:', window.debug?.getConfig());

            const form = document.getElementById('focalDataEntryForm');
            if (form) {
                debugLog(MODULE_NAME, '- Form listeners:', getEventListeners ? getEventListeners(form) : 'Use DevTools to check');
                debugLog(MODULE_NAME, '- Required fields found:', document.querySelectorAll('[required]').length);
                debugLog(MODULE_NAME, '- Form item blocks found:', document.querySelectorAll('.form-item-block[data-item-id]').length);
            }

            return {
                validator: !!window.formValidator,
                form: !!form,
                debugEnabled: window.debug?.getConfig()?.modules?.form_validation
            };
        };
    } else {
        debugLog(MODULE_NAME, 'ℹ️ FORM VALIDATION: FormValidator already exists');
    }
    return formValidator;
}

export { FormValidator };
