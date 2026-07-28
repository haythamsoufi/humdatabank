import { setHiddenRuleField, setMultiHiddenFields } from '../rules/form-serialization.js';
import { MatrixItem } from '../items/matrix.js';
import { ImageItem } from '../items/image.js';
import { DocumentItem } from '../items/document.js';
import { PluginItem } from '../items/plugin.js';
import { serializeCarryForwardSources } from './carry-forward.js';
import { clearDisabledDescriptions } from './description-hint-ui.js';

export const FormSubmitMixin = {
    /**
     * Ensure the modal serializes UI state BEFORE the AJAX layer snapshots FormData.
     *
     * This makes submission deterministic even if event-listener registration order changes.
     * The hook is dispatched by FormSubmitUI: `formBuilder:beforeAjaxSubmit`.
     */
    setupAjaxBeforeSubmitHook: function() {
        if (this._beforeAjaxHookAttached) return;
        this._beforeAjaxHookAttached = true;

        document.addEventListener('formBuilder:beforeAjaxSubmit', (evt) => {
            const form = evt && evt.detail ? evt.detail.form : null;
            if (!form || !(form instanceof HTMLFormElement)) return;
            if (form.id !== 'item-modal-form') return;

            try {
                this.modalElement = this.modalElement || Utils.getElementById('item-modal') || document.getElementById('item-modal');
                this.formElement = form;
            } catch (_e) {}

            try {
                this.prepareItemModalFormForSubmit(form);
            } catch (e) {
                try { (window.__clientWarn || console.warn)('[ItemModal] beforeAjaxSubmit prepare failed', e); } catch (_e) {}
            }
        });
    },

    /**
     * Prepare the item modal form for submission by serializing visible UI to canonical inputs.
     * Safe to call multiple times; used by both native submit handler and beforeAjaxSubmit hook.
     */
    prepareItemModalFormForSubmit: function(formEl) {
        const form = formEl || this.formElement;
        if (!form) return;

        try {
            this.modalElement = this.modalElement || Utils.getElementById('item-modal') || document.getElementById('item-modal');
            this.formElement = form;
        } catch (_e) {}

        this.handleFormValidation(form);
        try {
            if (this.modalElement) clearDisabledDescriptions(this.modalElement);
        } catch (_e) {}
        this.syncUIToShared();
        this.ensureCanonicalSharedFieldNames(form);

        try {
            if (this.modalElement) {
                serializeCarryForwardSources(this.modalElement);
            }
        } catch (_e) {}

        try {
            if (this.modalElement) {
                const sectionSelect = this.modalElement.querySelector('#item-section-select');
                const sectionIdInput = this.modalElement.querySelector('#item-modal-section-id');
                if (sectionSelect && sectionIdInput) {
                    sectionIdInput.value = sectionSelect.value;
                }
            }
        } catch (_e) {}

        try {
            let itemTypeInput = form.querySelector('#item-modal-type') || form.querySelector('input[name="item_type"]');
            if (!itemTypeInput) {
                itemTypeInput = document.createElement('input');
                itemTypeInput.type = 'hidden';
                itemTypeInput.id = 'item-modal-type';
                itemTypeInput.name = 'item_type';
                form.appendChild(itemTypeInput);
            }
            itemTypeInput.value = this.currentItemType;
        } catch (_e) {}

        try {
            if (this.modalElement) {
                const relevanceBuilder = this.modalElement.querySelector('#item-relevance-rule-builder');
                const validationBuilder = this.modalElement.querySelector('#item-validation-rule-builder');
                setHiddenRuleField(form, 'relevance_condition', relevanceBuilder);
                const isDisplayOnly = this.isDisplayOnlyItemType
                    && this.isDisplayOnlyItemType(this.currentItemType, this.currentQuestionType);
                if (isDisplayOnly) {
                    const validationCondition = form.querySelector('[name="validation_condition"]');
                    const validationMessage = form.querySelector('[name="validation_message"]');
                    if (validationCondition) validationCondition.value = '';
                    if (validationMessage) validationMessage.value = '';
                } else {
                    setHiddenRuleField(form, 'validation_condition', validationBuilder);
                }
            }
        } catch (_e) {}

        try {
            if (this.currentItemType === 'question' && this.modalElement) {
                const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
                const value = (questionTypeSelect ? (questionTypeSelect.value || '').trim() : '') || (this.currentQuestionType || '') || '';
                const questionTypeInput = form.querySelector('#item-question-type-input');
                if (questionTypeInput) questionTypeInput.value = value;
            }
        } catch (_e) {}

        try {
            if (this.currentItemType === 'matrix') {
                MatrixItem.updateConfig(this.modalElement);
            }
        } catch (_e) {}

        try {
            if (this.currentItemType === 'image') {
                ImageItem.updateConfig(this.modalElement);
            }
        } catch (_e) {}

        try {
            if (this.currentItemType === 'question' && window.CalculatedLists && window.CalculatedLists._serializePluginConfig) {
                const configContainer = document.getElementById('question-plugin-config-container');
                if (configContainer && configContainer.children.length > 0) {
                    window.CalculatedLists._serializePluginConfig(configContainer);
                }
            }
        } catch (_e) {}

        try {
            if (this.currentItemType && String(this.currentItemType).startsWith('plugin_')) {
                this.collectPluginConfigFields(form);
            }
        } catch (_e) {}

        if (this.currentMode === 'edit') {
            try {
                this.populateEditFormFields();
            } catch (_e) {}
            try {
                form.action = `/admin/items/edit/${this.currentItemId}`;
            } catch (_e) {}
            return;
        }

        try {
            this.prepareAddFormAction(form);
        } catch (_e) {}
    },

    populateEditFormFields: function() {
        const form = this.modalElement.querySelector('form');
        if (!form) {
            return;
        }

        const sectionIdInput = form.querySelector('#item-modal-section-id');
        if (sectionIdInput && (!sectionIdInput.value || sectionIdInput.value.trim() === '')) {
            if (this.currentSectionId) {
                sectionIdInput.value = this.currentSectionId;
            }
        }

        if (this.currentItemType === 'indicator') {
            const disaggContainer = this.modalElement.querySelector('#add_item_indicator_allowed_disaggregation_options_container');
            if (disaggContainer) {
                const fromModal = Array.from(disaggContainer.querySelectorAll('input[type="checkbox"]:checked'))
                    .map(cb => cb.value);
                const fromDoc = Array.from(document.querySelectorAll('#add_item_indicator_allowed_disaggregation_options_container input[type="checkbox"]:checked'))
                    .map(cb => cb.value);
                const fromHidden = (() => {
                    try {
                        return Array.from(form.querySelectorAll('input[type="hidden"][name="allowed_disaggregation_options"]'))
                            .map(n => (n && n.value ? String(n.value) : ''))
                            .filter(Boolean);
                    } catch (_e) {
                        return [];
                    }
                })();
                const selectedOptions = Array.from(new Set([...(fromModal || []), ...(fromDoc || []), ...(fromHidden || [])])).filter(Boolean);

                try {
                    const all = Array.from(disaggContainer.querySelectorAll('input[type="checkbox"]')).map(cb => ({ v: cb.value, checked: !!cb.checked }));
                    (window.__clientLog || console.debug)('[ItemModal] serialize disaggregation', {
                        itemId: this.currentItemId,
                        selectedOptions,
                        allCheckboxes: all
                    });
                } catch (_e) {}

                setMultiHiddenFields(form, 'allowed_disaggregation_options', selectedOptions);
            }
        }

        const relevanceBuilder = this.modalElement.querySelector('#item-relevance-rule-builder');
        setHiddenRuleField(form, 'relevance_condition', relevanceBuilder);

        const validationBuilder = this.modalElement.querySelector('#item-validation-rule-builder');
        const isDisplayOnly = this.isDisplayOnlyItemType
            && this.isDisplayOnlyItemType(this.currentItemType, this.currentQuestionType);
        if (isDisplayOnly) {
            const validationCondition = form.querySelector('[name="validation_condition"]');
            const validationMessage = form.querySelector('[name="validation_message"]');
            if (validationCondition) validationCondition.value = '';
            if (validationMessage) validationMessage.value = '';
        } else {
            setHiddenRuleField(form, 'validation_condition', validationBuilder);
        }

        const validationMessageInput = this.modalElement.querySelector('#item-validation-message');
        if (validationMessageInput && !isDisplayOnly) {
            let validationMessageField = form.querySelector('input[name="validation_message"]');
            if (!validationMessageField) {
                validationMessageField = document.createElement('input');
                validationMessageField.type = 'hidden';
                validationMessageField.name = 'validation_message';
                form.appendChild(validationMessageField);
            }
            validationMessageField.value = validationMessageInput.value;
        }

        if (this.currentItemType === 'matrix') {
            MatrixItem.updateConfig(this.modalElement);
        }

        if (this.currentItemType === 'document_field') {
            try {
                DocumentItem.syncPresetPeriodToHidden(this.modalElement);
            } catch (e) { /* non-fatal */ }
        }

        if (this.currentItemType.startsWith('plugin_')) {
            this.collectPluginConfigFields(form);
        }

        const allowOver100Checkbox = this.modalElement.querySelector('#item-allow-over-100');
        if (allowOver100Checkbox) {
            let configField = form.querySelector('input[name="config"]');
            if (!configField) {
                configField = document.createElement('input');
                configField.type = 'hidden';
                configField.name = 'config';
                form.appendChild(configField);
            }

            let config = {};
            try {
                if (configField.value) {
                    config = JSON.parse(configField.value);
                }
            } catch (e) {
                config = {};
            }

            config.allow_over_100 = allowOver100Checkbox.checked;
            configField.value = JSON.stringify(config);
        }
    },

    cleanupInactiveModalFields: function(form) {
        const activeType = this.currentItemType;
        const activeMode = this.currentMode;

        const itemTypeSections = [
            { selector: '#item-indicator-fields', type: 'indicator' },
            { selector: '#item-question-fields', type: 'question' },
            { selector: '#item-document-fields', type: 'document_field' },
            { selector: '#item-matrix-fields', type: 'matrix' },
            { selector: '#item-plugin-fields', type: 'plugin' }
        ];

        itemTypeSections.forEach(section => {
            const element = form.querySelector(section.selector);
            if (element && section.type !== activeType) {
                const fields = element.querySelectorAll('input, textarea, select, button');
                fields.forEach(field => {
                    if (field.type === 'submit') return;
                    field.disabled = true;
                });
            }
        });

        if (activeMode === 'edit') {
            const addModalFields = [
                '#item-document-label',
                '#item-document-description',
                '#item-document-label-translations',
                '#item-document-description-translations'
            ];

            addModalFields.forEach(selector => {
                const element = form.querySelector(selector);
                if (element) {
                    element.disabled = true;
                }
            });
        }
    },

    setupFormSubmission: function() {
        document.addEventListener('submit', (e) => {
            const form = e?.target;
            if (!form || form.id !== 'item-modal-form') return;
            try {
                this.prepareItemModalFormForSubmit(form);
            } catch (err) {
                try { (window.__clientWarn || console.warn)('[ItemModal] submit prepare failed', err); } catch (_e) {}
            }
        });
    },

    ensureCanonicalSharedFieldNames: function(formEl) {
        try {
            const form = formEl || this.formElement || this.modalElement?.querySelector?.('form');
            if (!form) return;

            const canonical = {
                label: '#item-modal-shared-label',
                indicator_label_override: '#item-modal-indicator-label-override',
                description: '#item-modal-shared-description',
                definition: '#item-modal-definition',
                label_translations: '#item-modal-shared-label-translations',
                description_translations: '#item-modal-shared-description-translations',
                definition_translations: '#item-modal-definition-translations',
                item_type: '#item-modal-type',
            };

            Object.entries(canonical).forEach(([name, selector]) => {
                const keep = form.querySelector(selector);
                if (keep) {
                    keep.setAttribute('name', name);
                }
                const duplicates = form.querySelectorAll(`[name="${name}"]`);
                duplicates.forEach((el) => {
                    if (keep && el === keep) return;
                    try { el.removeAttribute('name'); } catch (_e) { el.name = ''; }
                });
            });
        } catch (_e) {
            // no-op
        }
    },

    handleFormValidation: function(form) {
        const isActuallyHidden = (el) => {
            if (!el) return true;
            if (el.closest('.hidden')) return true;
            if (el.offsetParent === null) return true;
            const style = window.getComputedStyle(el);
            return style.display === 'none' || style.visibility === 'hidden';
        };

        const allRequired = form.querySelectorAll('[required]');
        allRequired.forEach(field => {
            if (isActuallyHidden(field)) {
                field.setAttribute('data-was-required', 'true');
                field.removeAttribute('required');
            }
        });

        if (this.currentItemType === 'matrix') {
            const matrixFields = form.querySelector('#item-matrix-fields');
            if (matrixFields && !isActuallyHidden(matrixFields)) {
                const matrixLabel = matrixFields.querySelector('#item-matrix-label');
                void matrixLabel;
            }
        }

        const restoreRequired = () => {
            const fieldsToRestore = form.querySelectorAll('[data-was-required]');
            fieldsToRestore.forEach(field => {
                if (!isActuallyHidden(field)) {
                    field.setAttribute('required', 'required');
                }
                field.removeAttribute('data-was-required');
            });
        };
        form.addEventListener('submit', restoreRequired, { once: true, capture: true });
        setTimeout(restoreRequired, 500);
    },

    prepareAddFormAction: function(formElement) {
        const sectionSelect = this.modalElement.querySelector('#item-section-select');
        const sectionId = sectionSelect ? sectionSelect.value : this.currentSectionId;

        if (!sectionId) {
            Utils.showError('Please select a section');
            return;
        }

        const tplId = window.templateId;
        if (!tplId) {
            Utils.showError('Template ID not found');
            return;
        }
        formElement.action = `/admin/templates/${tplId}/sections/${sectionId}/items/new`;
        formElement.method = 'POST';
    },

    collectPluginConfigFields: function(formElement) {
        PluginItem.collectConfigFields(this.modalElement, formElement);
    },
};
