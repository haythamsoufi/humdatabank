// Utils is available globally from utils.js
import { DataManager } from '../data-manager.js';
import { attachRuleData } from '../rules/rule-builder-helpers.js';
import { setHiddenRuleField, setMultiHiddenFields } from '../rules/form-serialization.js';
import { MatrixItem } from '../items/matrix.js';
import { QuestionItem } from '../items/question.js';
import { IndicatorItem } from '../items/indicator.js';
import { DocumentItem } from '../items/document.js';
import { PluginItem } from '../items/plugin.js';
import { SharedFields } from '../shared-fields.js';
import { VariableAutocompleteMixin } from './variable-autocomplete.js';
import { AccessibilityMixin } from './accessibility.js';
import { RuleUIMixin } from './rule-ui.js';
import { SectionSelectorMixin } from './section-selector.js';
import { PropertiesMixin } from './properties.js';

export const ItemModal = {
    currentMode: 'add', // 'add' or 'edit'
    currentItemType: 'indicator', // 'indicator', 'question', 'document_field', 'matrix', or 'plugin_*'
    currentQuestionType: null, // when currentItemType === 'question', e.g. 'text', 'number'
    currentItemId: null,
    currentSectionId: null,
    modalElement: null,
    formElement: null,

    // Unified field mapping system
    sharedFields: {
        label: '#item-modal-shared-label',
        description: '#item-modal-shared-description',
        label_translations: '#item-modal-shared-label-translations',
        description_translations: '#item-modal-shared-description-translations'
    },

    // Delegated shared field sync to SharedFields module
    syncSharedToUI: function() { SharedFields.syncSharedToUI(); },
    syncUIToShared: function() { SharedFields.syncUIToShared(); },
    setupFieldSync: function() { SharedFields.setupFieldSync(this.modalElement); },

    ...VariableAutocompleteMixin,
    ...AccessibilityMixin,
    ...RuleUIMixin,
    ...SectionSelectorMixin,
    ...PropertiesMixin,

    // Safe HTML insertion helper for server-provided fragments (plugin templates/builders).
    // Strips scripts, iframes, inline event handlers, and dangerous URL protocols.
    setSanitizedHtml: function(container, html) {
        if (!container) return;
        container.replaceChildren();
        if (typeof html !== 'string' || !html.trim()) return;

        const doc = new DOMParser().parseFromString(html, 'text/html');
        const root = doc.body;
        if (!root) return;

        root.querySelectorAll('script, iframe, object, embed, style, meta, link, base, form').forEach((el) => el.remove());
        root.querySelectorAll('*').forEach((el) => {
            [...el.attributes].forEach((attr) => {
                const name = String(attr.name || '').toLowerCase();
                const value = String(attr.value || '').replace(/[\s\x00-\x1f]/g, '').toLowerCase();
                if (name.startsWith('on')) {
                    el.removeAttribute(attr.name);
                    return;
                }
                if (name === 'href' || name === 'src' || name === 'xlink:href' || name === 'formaction') {
                    if (
                        value.startsWith('javascript:') ||
                        value.startsWith('data:') ||
                        value.startsWith('vbscript:') ||
                        value.startsWith('file:') ||
                        value.startsWith('about:')
                    ) {
                        el.removeAttribute(attr.name);
                    }
                }
            });
        });

        const fragment = document.createDocumentFragment();
        while (root.firstChild) fragment.appendChild(root.firstChild);
        container.appendChild(fragment);
    },

    // Initialize the item modal
    init: function() {
        if (this._initialized) return;
        this._initialized = true;

        this.setupModalEvents();
        this.setupItemTypeToggle();
        this.setupAjaxBeforeSubmitHook();
        this.setupFormSubmission();
        this.setupWindowResize();
        this.setupFieldSync();
        this.setupVariableAutocomplete();
        this.setupSectionSelector();
        this.cacheRuleToggleDefaults();
        // Select2 initialization happens when modal is shown
    },

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
                // Keep local references current (modal DOM might have been swapped).
                this.modalElement = this.modalElement || Utils.getElementById('item-modal') || document.getElementById('item-modal');
                this.formElement = form;
            } catch (_e) {}

            try {
                this.prepareItemModalFormForSubmit(form);
            } catch (e) {
                // Do not throw; allow global handler to surface errors.
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

        // Keep local references current (the modal DOM may be swapped during AJAX refresh).
        try {
            this.modalElement = this.modalElement || Utils.getElementById('item-modal') || document.getElementById('item-modal');
            this.formElement = form;
        } catch (_e) {}

        // Prevent validation errors on hidden required fields
        this.handleFormValidation(form);

        // Ensure we serialize the visible UI into shared hidden fields
        this.syncUIToShared();

        // Ensure we submit exactly one canonical set of shared fields (label/desc/translations)
        this.ensureCanonicalSharedFieldNames(form);

        // Sync section selector to hidden section_id
        try {
            if (this.modalElement) {
                const sectionSelect = this.modalElement.querySelector('#item-section-select');
                const sectionIdInput = this.modalElement.querySelector('#item-modal-section-id');
                if (sectionSelect && sectionIdInput) {
                    sectionIdInput.value = sectionSelect.value;
                }
            }
        } catch (_e) {}

        // Add/ensure item_type hidden input for add mode (and when type changes)
        try {
            let itemTypeInput = form.querySelector('input[name="item_type"]');
            if (!itemTypeInput) {
                itemTypeInput = document.createElement('input');
                itemTypeInput.type = 'hidden';
                itemTypeInput.name = 'item_type';
                form.appendChild(itemTypeInput);
            }
            itemTypeInput.value = this.currentItemType;
        } catch (_e) {}

        // Ensure rules are serialized into hidden inputs
        try {
            if (this.modalElement) {
                const relevanceBuilder = this.modalElement.querySelector('#item-relevance-rule-builder');
                const validationBuilder = this.modalElement.querySelector('#item-validation-rule-builder');
                setHiddenRuleField(form, 'relevance_condition', relevanceBuilder);
                setHiddenRuleField(form, 'validation_condition', validationBuilder);
            }
        } catch (_e) {}

        // For questions, sync question_type into the form-root hidden input
        try {
            if (this.currentItemType === 'question' && this.modalElement) {
                const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
                const value = (questionTypeSelect ? (questionTypeSelect.value || '').trim() : '') || (this.currentQuestionType || '') || '';
                const questionTypeInput = form.querySelector('#item-question-type-input');
                if (questionTypeInput) questionTypeInput.value = value;
            }
        } catch (_e) {}

        // Matrix: ensure config is up to date
        try {
            if (this.currentItemType === 'matrix') {
                MatrixItem.updateConfig(this.modalElement);
            }
        } catch (_e) {}

        // Question (calculated-list): ensure plugin config hidden input is in sync
        try {
            if (this.currentItemType === 'question' && window.CalculatedLists && window.CalculatedLists._serializePluginConfig) {
                const configContainer = document.getElementById('question-plugin-config-container');
                if (configContainer && configContainer.children.length > 0) {
                    window.CalculatedLists._serializePluginConfig(configContainer);
                }
            }
        } catch (_e) {}

        // Plugin: collect config fields into the form before submit
        try {
            if (this.currentItemType && String(this.currentItemType).startsWith('plugin_')) {
                this.collectPluginConfigFields(form);
            }
        } catch (_e) {}

        // Ensure correct action for edit mode
        if (this.currentMode === 'edit') {
            try {
                this.populateEditFormFields();
            } catch (_e) {}
            try {
                form.action = `/admin/items/edit/${this.currentItemId}`;
            } catch (_e) {}
            return;
        }

        // Add mode: ensure action is correct for selected section
        try {
            this.prepareAddFormAction(form);
        } catch (_e) {}
    },

    // Show modal for adding new item (optionalInitialQuestionType: pre-select question type when itemType is 'question')
    showAddModal: function(sectionId, sectionName, itemType = 'indicator', optionalInitialQuestionType = null) {

        this.currentMode = 'add';
        this.currentItemType = itemType;
        this.currentSectionId = sectionId;
        this.currentItemId = null;

        this.modalElement = Utils.getElementById('item-modal');
        this.formElement = Utils.getElementById('item-modal-form');
        if (!this.modalElement || !this.formElement) {
            Utils.showError('Modal elements not found');
            return;
        }
        SharedFields.init(this.modalElement);

        // Reset the form early so subsequent assignments stay in place
        this.resetForm();
        // Reset rule UI/layout from any previous modal usage
        this.resetRuleUIState();

        // Update modal title
        const titleElement = this.modalElement.querySelector('.modal-title');
        if (titleElement) {
            titleElement.replaceChildren();
            const icon = document.createElement('i');
            icon.className = 'fas fa-plus-circle w-6 h-6 mr-2 text-green-600';
            const text = document.createTextNode('Add Item to ');
            const sectionEl = document.createElement('span');
            sectionEl.className = 'font-bold ml-1';
            sectionEl.textContent = String(sectionName || '');
            titleElement.append(icon, text, sectionEl);
        }

        // Set template ID and section ID
        const templateIdInput = Utils.getElementById('item-modal-template-id');
        const sectionIdInput = Utils.getElementById('item-modal-section-id');
        if (templateIdInput && sectionIdInput) {
            templateIdInput.value = window.templateId;
            sectionIdInput.value = sectionId;
        }

        // Populate and set section selector
        const sectionSelect = this.populateSectionSelector();
        if (sectionSelect && sectionId) {
            sectionSelect.value = String(sectionId);
        }
        // Ensure plugin builder "Section" proxies (if any) stay in sync
        this.setupSectionProxyObserver();

        // Set form action - use the correct route with template_id and section_id
        const templateId = window.templateId;
        if (templateId) {
            this.formElement.action = `/admin/templates/${templateId}/sections/${sectionId}/items/new`;
        } else {
            Utils.showError('Template ID not found');
            return;
        }

        // Set default order value for new items
        this.setDefaultOrderValue(sectionId);

        // Show modal first
        Utils.showElement(this.modalElement);

        // Ensure submit button is enabled (AJAX saves may leave it disabled)
        try {
            const submitBtn = Utils.getElementById('item-modal-submit-btn');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.removeAttribute('disabled');
                if (submitBtn.dataset) delete submitBtn.dataset.loadingApplied;
            }
        } catch (_e) {}

        // Show item type and optional question type (after modal is visible)
        this.switchItemType(itemType, optionalInitialQuestionType);
        // Plugin builders may load async; do an early sync pass too
        this.syncSectionProxyDropdowns();
        // Keep nested hidden panels compliant (disable controls in hidden UI)
        try { this.setupHiddenDisableObserver(); } catch (_e) {}

        // Setup ARIA and focus handling
        this.setupModalAria();
        setTimeout(() => {
            this.focusFirstField();
            this.setupFocusTrap();
        }, 50);

        // Check if modal needs scrolling
        this.checkModalScroll();
    },

    // Show modal for editing existing item
    showEditModal: function(itemId, itemType, itemData) {


        this.currentMode = 'edit';
        this.currentItemType = itemType;
        this.currentItemId = itemId;
        this.currentSectionId = itemData.section_id;

        this.modalElement = Utils.getElementById('item-modal');
        this.formElement = Utils.getElementById('item-modal-form');


        if (!this.modalElement || !this.formElement) {

            Utils.showError('Modal elements not found');
            return;
        }
        SharedFields.init(this.modalElement);

        // Update modal title (for questions, show specific type label e.g. "Edit Short text")
        const titleElement = this.modalElement.querySelector('.modal-title');
        if (titleElement) {
            titleElement.replaceChildren();
            const iconEl = document.createElement('i');
            iconEl.className = this.getItemTypeIconClasses(itemType);
            titleElement.appendChild(iconEl);
            const typeLabel = itemType === 'question' ? this.getItemTypeName(itemType, itemData.question_type) : this.getItemTypeName(itemType);
            titleElement.appendChild(document.createTextNode(`Edit ${typeLabel}`));
        }

        // Set form action
        this.formElement.action = `/admin/items/edit/${itemId}`;

        // Reset form first
        this.resetForm();
        // Reset rule UI/layout from any previous edit before hydrating this item
        this.resetRuleUIState();

        // If editing a plugin item, store data BEFORE switching type so setupPluginFields can use it
        if (itemType && itemType.startsWith('plugin_')) {
            this.pendingPluginData = itemData;
        }

        // Show item type and set up fields
        this.switchItemType(itemType);
        this.setupSectionProxyObserver();
        // Keep nested hidden panels compliant (disable controls in hidden UI)
        try { this.setupHiddenDisableObserver(); } catch (_e) {}

        // Initialize Select2 for the modal if needed
        this.initializeModalSelect2();

        // Show modal first, then populate
        Utils.showElement(this.modalElement);

        // Ensure submit button is enabled (AJAX saves may leave it disabled)
        try {
            const submitBtn = Utils.getElementById('item-modal-submit-btn');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.removeAttribute('disabled');
                if (submitBtn.dataset) delete submitBtn.dataset.loadingApplied;
            }
        } catch (_e) {}

        // Populate form with existing data after modal is visible
        setTimeout(() => {
            // Populate section selector first (returns the select element)
            const sectionSelect = this.populateSectionSelector();
            this.populateForm(itemData);
            // Refresh type trigger so it shows question type label (e.g. "Short text") not "Question"
            if (this.currentItemType === 'question') {
                this.updateItemTypeTriggerButton('question');
            }
            // Make sure any plugin-provided "Section" proxy dropdown reflects current section
            this.syncSectionProxyDropdowns();
            // Check if modal needs scrolling after populating
            this.checkModalScroll();
            // Setup ARIA and focus handling once content is populated
            this.setupModalAria();
            this.focusFirstField();
            this.setupFocusTrap();
        }, 100);
    },

    // Initialize Select2 for modal
    initializeModalSelect2: function() {
        // Add null check to prevent errors
        if (!this.modalElement) {
            return;
        }

        if (window.jQuery && window.jQuery.fn.select2) {
            setTimeout(() => {
                const bankSelect = this.modalElement.querySelector('#item-indicator-bank-select');
                if (bankSelect && !$(bankSelect).hasClass('select2-hidden-accessible')) {

                    $(bankSelect).select2({
                        dropdownParent: $(this.modalElement),
                        width: '100%',
                        theme: "default"
                    });
                }
            }, 50);
        }
    },

    // Switch between item types (optionalQuestionType: for question type, pre-select and dispatch change)
    switchItemType: function(itemType, optionalQuestionType) {

        this.currentItemType = itemType;

        // Indirect reach is only meaningful for indicators (and only some of them).
        // When switching away from indicator, force-clear + disable it so hidden checked boxes
        // don't keep submitting and re-enabling the flag.
        try {
            const row = this.modalElement ? this.modalElement.querySelector('#indirect-reach-row') : document.getElementById('indirect-reach-row');
            const cb = row ? row.querySelector('#item-indirect-reach') : document.getElementById('item-indirect-reach');
            if (cb) {
                if (itemType !== 'indicator') {
                    cb.checked = false;
                    cb.disabled = true;
                } else {
                    // Enable by default; the indicator module will disable again if the selected bank indicator doesn't support it.
                    cb.disabled = false;
                }
            }
            const disabilityRow = this.modalElement ? this.modalElement.querySelector('#disability-questions-row') : document.getElementById('disability-questions-row');
            const disabilityCb = disabilityRow ? disabilityRow.querySelector('#item-allow-disability-questions') : document.getElementById('item-allow-disability-questions');
            if (disabilityRow) {
                disabilityRow.style.display = itemType === 'indicator' ? '' : 'none';
            }
            if (disabilityCb) {
                if (itemType !== 'indicator') {
                    disabilityCb.checked = false;
                    disabilityCb.disabled = true;
                } else {
                    disabilityCb.disabled = false;
                }
            }
        } catch (_e) {}

        // When switching to question with a specific type, set select and hidden input so trigger shows correct label and submit sends question_type
        if (itemType === 'question') {
            if (optionalQuestionType) {
                this.currentQuestionType = optionalQuestionType;
                const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
                const questionTypeInput = this.modalElement.querySelector('#item-question-type-input');
                if (questionTypeSelect) {
                    const opt = questionTypeSelect.querySelector(`option[value="${optionalQuestionType}"]`);
                    if (opt) {
                        questionTypeSelect.value = optionalQuestionType;
                        if (questionTypeInput) questionTypeInput.value = optionalQuestionType;
                    }
                }
            } else {
                const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
                this.currentQuestionType = questionTypeSelect ? (questionTypeSelect.value || '').trim() : null;
            }
        } else {
            this.currentQuestionType = null;
        }

        // Update type trigger button (replaces former dropdown)
        this.updateItemTypeTriggerButton(itemType);

        // In edit mode, keep hidden item_type in sync so submit sends the selected type
        if (this.currentMode === 'edit') {
            const itemTypeInput = this.modalElement.querySelector('#item-modal-type');
            if (itemTypeInput) {
                itemTypeInput.value = itemType;
            }
        }

        // Show/hide relevant fields
        this.toggleFieldsVisibility(itemType);

        // Fire change on question type select so options visibility etc. update; ensure hidden input stays in sync
        if (itemType === 'question') {
            const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
            const questionTypeInput = this.modalElement.querySelector('#item-question-type-input');
            // Re-apply the question type value: populateTypeDropdown (called inside toggleFieldsVisibility)
            // uses replaceChildren() which resets the select's value back to '' after we set it above.
            if (questionTypeSelect && optionalQuestionType) {
                const opt = questionTypeSelect.querySelector(`option[value="${optionalQuestionType}"]`);
                if (opt) {
                    questionTypeSelect.value = optionalQuestionType;
                    if (questionTypeInput) questionTypeInput.value = optionalQuestionType;
                }
            }
            if (questionTypeSelect && questionTypeInput) questionTypeInput.value = questionTypeSelect.value || '';
            if (questionTypeSelect && optionalQuestionType) {
                questionTypeSelect.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }

        // Ensure Privacy field is present in Properties section
        try { (window.__clientLog || console.debug)('[ItemModal:Privacy] calling ensurePrivacyField()'); } catch (e) {}
        this.ensurePrivacyField();

        // Ensure Allow Over 100% checkbox for percentage items
        this.ensureAllowOver100Field(itemType);

        // Unique-options-in-section checkbox for choice questions
        this.ensureUniqueOptionsInSectionField(itemType);

        // Repeat entry title dropdown for single choice questions
        this.ensureUseAsRepeatEntryTitleField(itemType);

        // Update submit button
        this.updateSubmitButton(itemType);

        // Enforce invariant: hidden UI => controls disabled (covers nested panels too)
        try { this.enforceHiddenControlsDisabled(this.modalElement); } catch (_e) {}

        // Check if modal needs scrolling after switching types
        if (!this._scrollRafQueued) {
            this._scrollRafQueued = true;
            requestAnimationFrame(() => {
                this._scrollRafQueued = false;
                this.checkModalScroll();
            });
        }
    },

    /**
     * Invariant: if a UI section is hidden, all non-hidden form controls inside it are disabled.
     *
     * - Only re-enables controls we disabled (data-fbDisabledByHidden), preserving other disabled reasons.
     * - Complements item-type switching (which already disables whole type containers) and covers nested panels
     *   toggled by inline scripts (e.g. question options/list-library panes).
     */
    enforceHiddenControlsDisabled: function(rootEl) {
        const root = rootEl || this.modalElement;
        if (!root) return;

        const isActuallyHidden = (el) => {
            if (!el) return true;
            try {
                if (el.closest && el.closest('.hidden')) return true;
                // Fast path: check inline style before forcing a computed style lookup
                const inlineDisplay = el.style && el.style.display;
                const inlineVisibility = el.style && el.style.visibility;
                if (inlineDisplay === 'none' || inlineVisibility === 'hidden') return true;
                if (el.offsetParent === null) return true;
                const style = window.getComputedStyle(el);
                return style.display === 'none' || style.visibility === 'hidden';
            } catch (_e) {
                return false;
            }
        };

        root.querySelectorAll('input, select, textarea, button').forEach((el) => {
            if (!el) return;
            // Don't touch intentionally-submitted hidden inputs
            if (el.tagName.toLowerCase() === 'input' && el.type === 'hidden') return;
            // Keep submit usable
            if (el.type === 'submit') return;

            const hidden = isActuallyHidden(el);
            if (hidden) {
                if (!el.disabled) {
                    try { el.dataset.fbDisabledByHidden = '1'; } catch (_e) {}
                    el.disabled = true;
                }
            } else {
                try {
                    if (el.dataset && el.dataset.fbDisabledByHidden === '1') {
                        el.disabled = false;
                        delete el.dataset.fbDisabledByHidden;
                    }
                } catch (_e) {}
            }
        });
    },

    setupHiddenDisableObserver: function() {
        if (!this.modalElement || typeof MutationObserver === 'undefined') return;

        try {
            if (this._hiddenDisableObserver) this._hiddenDisableObserver.disconnect();
        } catch (_e) {}

        const schedule = () => {
            if (this._hiddenDisableQueued) return;
            this._hiddenDisableQueued = true;
            requestAnimationFrame(() => {
                this._hiddenDisableQueued = false;
                try { this.enforceHiddenControlsDisabled(this.modalElement); } catch (_e) {}
            });
        };

        try {
            this._hiddenDisableObserver = new MutationObserver(() => schedule());
            this._hiddenDisableObserver.observe(this.modalElement, {
                subtree: true,
                childList: true,
                attributes: true,
                attributeFilter: ['class', 'style', 'hidden', 'aria-hidden']
            });
        } catch (_e) {
            this._hiddenDisableObserver = null;
        }

        schedule();
    },

    // Toggle fields visibility based on item type
    toggleFieldsVisibility: function(itemType) {

        const indicatorFields = Utils.getElementById('item-indicator-fields');
        const questionFields = Utils.getElementById('item-question-fields');
        const documentFields = Utils.getElementById('item-document-fields');
        const matrixFields = Utils.getElementById('item-matrix-fields');
        const pluginFieldsContainer = Utils.getElementById('item-plugin-fields-container');


        // Disable/enable inputs helper for a container
        const setContainerDisabled = (container, disabled) => {
            if (!container) return;
            container.querySelectorAll('input, select, textarea, button').forEach(el => {
                if (el.type === 'submit') return;
                el.disabled = !!disabled;
            });
        };

        // Hide all fields first and remove required attributes
        Utils.hideElement(indicatorFields);
        Utils.hideElement(questionFields);
        Utils.hideElement(documentFields);
        Utils.hideElement(matrixFields);
        Utils.hideElement(pluginFieldsContainer);
        // Disable while hidden to avoid native validation on hidden required fields
        setContainerDisabled(indicatorFields, true);
        setContainerDisabled(questionFields, true);
        setContainerDisabled(documentFields, true);
        setContainerDisabled(matrixFields, true);
        setContainerDisabled(pluginFieldsContainer, true);

        // For plugin fields, only try to access them if they exist (after template is loaded)
        const pluginFields = document.getElementById('item-plugin-fields'); // Direct access, no warning
        if (pluginFields) {
            Utils.hideElement(pluginFields);
            setContainerDisabled(pluginFields, true);
        }

        // Remove required attributes from all hidden fields
        if (indicatorFields) {
            indicatorFields.querySelectorAll('[required]').forEach(field => {
                field.removeAttribute('required');
            });
        }
        if (questionFields) {
            questionFields.querySelectorAll('[required]').forEach(field => {
                field.removeAttribute('required');
            });
        }
        if (documentFields) {
            documentFields.querySelectorAll('[required]').forEach(field => {
                field.removeAttribute('required');
            });
        }
        if (matrixFields) {
            matrixFields.querySelectorAll('[required]').forEach(field => {
                field.removeAttribute('required');
            });
        }
        if (pluginFields) {
            pluginFields.querySelectorAll('[required]').forEach(field => {
                field.removeAttribute('required');
            });
        }

        // Show relevant fields and restore required attributes
        if (itemType === 'indicator') {
            try { PluginItem.teardown(this.modalElement); } catch (e) {}
            Utils.showElement(indicatorFields);
            setContainerDisabled(indicatorFields, false);
            // Restore required attributes for indicator fields
            const indicatorBankSelect = indicatorFields.querySelector('#item-indicator-bank-select');
            if (indicatorBankSelect) {
                indicatorBankSelect.setAttribute('required', 'required');
            }
            this.setupIndicatorFields();
        } else if (itemType === 'question') {
            try { MatrixItem.teardown(this.modalElement); } catch (e) {}
            try { PluginItem.teardown(this.modalElement); } catch (e) {}
            Utils.showElement(questionFields);
            setContainerDisabled(questionFields, false);
            // Note: Required attribute for question label is handled dynamically in setupQuestionFields
            // based on the question type (not required for 'blank' type)
            this.setupQuestionFields();
        } else if (itemType === 'document_field') {
            try { MatrixItem.teardown(this.modalElement); } catch (e) {}
            try { QuestionItem.teardown(this.modalElement); } catch (e) {}
            try { IndicatorItem.teardown(this.modalElement); } catch (e) {}
            try { PluginItem.teardown(this.modalElement); } catch (e) {}
            try { DocumentItem.teardown(this.modalElement); } catch (e) {}
            Utils.showElement(documentFields);
            setContainerDisabled(documentFields, false);
            // Restore required attributes for document fields
            const documentLabel = documentFields.querySelector('#item-document-label');
            if (documentLabel) {
                documentLabel.setAttribute('required', 'required');
            }
            this.setupDocumentFields();
        } else if (itemType === 'matrix') {

            try { QuestionItem.teardown(this.modalElement); } catch (e) {}
            try { IndicatorItem.teardown(this.modalElement); } catch (e) {}
            try { PluginItem.teardown(this.modalElement); } catch (e) {}
            Utils.showElement(matrixFields);
            setContainerDisabled(matrixFields, false);
            // Ensure the matrix fields container is visible and accessible
            if (matrixFields) {
                matrixFields.style.display = '';
                matrixFields.classList.remove('hidden');

            }
            // Ensure the matrix label field is focusable
            const matrixLabel = matrixFields.querySelector('#item-matrix-label');
            if (matrixLabel) {
                // Ensure the label field is focusable
                matrixLabel.style.display = '';
                matrixLabel.tabIndex = 0;

            }

            this.setupMatrixFields();
            // Ensure column/row headers translation matrix modals are attached (lazy attachment)
            if (typeof window.attachMatrixColumnHeadersModalLazy === 'function') {
                window.attachMatrixColumnHeadersModalLazy();
            }
            if (typeof window.attachMatrixRowHeadersModalLazy === 'function') {
                window.attachMatrixRowHeadersModalLazy();
            }
        } else if (itemType.startsWith('plugin_')) {
            try { MatrixItem.teardown(this.modalElement); } catch (e) {}
            try { QuestionItem.teardown(this.modalElement); } catch (e) {}
            try { IndicatorItem.teardown(this.modalElement); } catch (e) {}
            Utils.showElement(pluginFieldsContainer);
            setContainerDisabled(pluginFieldsContainer, false);
            PluginItem.setup(this.modalElement, itemType, this.pendingPluginData);
        }

        // Show/hide validation rule section based on item type
        const validationRuleToggle = Utils.getElementById('validation-rule-toggle-section');
        if (itemType === 'document_field') {
            Utils.hideElement(validationRuleToggle);
        } else {
            Utils.showElement(validationRuleToggle);
        }
    },

        // Setup indicator-specific fields (delegated)
    setupIndicatorFields: function() {
        IndicatorItem.setup(this.modalElement);
        this.updateItemTranslationTabLabels('indicator');
        // Setup listener to update allow over 100 checkbox when indicator changes
        this.setupAllowOver100Listener();
        // Update checkbox visibility after setup
        setTimeout(() => this.ensureAllowOver100Field('indicator'), 100);
    },

    // Setup question-specific fields (delegated to QuestionItem)
    setupQuestionFields: function() {

        QuestionItem.setup(this.modalElement);
        const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
        this.updateQuestionFieldLabels(questionTypeSelect ? questionTypeSelect.value : '');
        // Setup listener to update allow over 100 checkbox when question type/unit changes
        this.setupAllowOver100Listener();
        // Update checkbox visibility after setup
        setTimeout(() => this.ensureAllowOver100Field('question'), 100);
    },

    // Setup document-specific fields (delegated)
    setupDocumentFields: function() {
        DocumentItem.setup(this.modalElement);
    },

    // Setup matrix-specific fields (delegated to MatrixItem)
    setupMatrixFields: function() {

        MatrixItem.setup(this.modalElement);
    },


    // Setup plugin-specific fields (migrated to PluginItem)
    setupPluginFields: function(itemType) {
        PluginItem.setup(this.modalElement, itemType, this.pendingPluginData);
    },


    // Switch question field captions/placeholders between standard questions and Blank/Note items
    updateQuestionFieldLabels: function(questionType) {
        if (!this.modalElement) return;

        const isBlank = questionType === 'blank';
        const mode = isBlank ? 'blank' : 'default';

        const labelCaption = this.modalElement.querySelector('#item-question-label-caption');
        const definitionCaption = this.modalElement.querySelector('#item-question-definition-caption');
        const labelInput = this.modalElement.querySelector('#item-question-label');
        const definitionInput = this.modalElement.querySelector('#item-question-definition');

        const applyCaption = (el) => {
            if (!el) return;
            const text = el.dataset[`${mode}Text`] || el.dataset.defaultText;
            if (text) el.textContent = text;
        };

        const applyPlaceholder = (el) => {
            if (!el) return;
            const placeholder = el.dataset[`${mode}Placeholder`] || el.dataset.defaultPlaceholder;
            if (placeholder) el.placeholder = placeholder;
        };

        applyCaption(labelCaption);
        applyCaption(definitionCaption);
        applyPlaceholder(labelInput);
        applyPlaceholder(definitionInput);

        this.updateQuestionLabelRequired(questionType);
        this.updateItemTranslationTabLabels('question', questionType);
    },

    // Align Item Translations modal tab titles with the active item field labels
    updateItemTranslationTabLabels: function(itemContext, questionType) {
        const suffixes = ['labels', 'definitions'];
        suffixes.forEach((suffix) => {
            const tabBtn = document.getElementById(`translation-tab-${suffix}`);
            if (!tabBtn) return;

            let text;
            if (itemContext === 'indicator') {
                text = tabBtn.dataset.indicatorText;
            } else if (questionType === 'blank') {
                text = tabBtn.dataset.questionBlankText || tabBtn.dataset.questionDefaultText;
            } else {
                text = tabBtn.dataset.questionDefaultText;
            }

            if (text) tabBtn.textContent = text;
        });
    },

    // Update question label required attribute based on question type
    updateQuestionLabelRequired: function(questionType) {
        const questionLabel = Utils.getElementById('item-question-label');
        if (!questionLabel) return;

        // Heading is optional for Blank/Note items
        if (questionType === 'blank') {
            questionLabel.removeAttribute('required');

        } else {
            questionLabel.setAttribute('required', 'required');

        }
    },

    // Get item type icon
    getItemTypeIconClasses: function(itemType) {
        if (itemType && typeof itemType === 'string' && itemType.startsWith('plugin_')) {
            return 'fas fa-puzzle-piece w-6 h-6 mr-2 text-orange-600';
        }
        switch (itemType) {
            case 'indicator':
                return 'fas fa-chart-line w-6 h-6 mr-2 text-purple-600';
            case 'question':
                return 'fas fa-question-circle w-6 h-6 mr-2 text-green-600';
            case 'document_field':
                return 'fas fa-file-upload w-6 h-6 mr-2 text-blue-600';
            case 'matrix':
                return 'fas fa-table w-6 h-6 mr-2 text-orange-600';
            default:
                return 'fas fa-plus-circle w-6 h-6 mr-2 text-gray-600';
        }
    },

    // Icon class for a question type value (matches item type picker tiles). UI only.
    getQuestionTypeIcon: function(questionTypeValue) {
        const iconMap = {
            text: 'fa-font',
            textarea: 'fa-align-left',
            number: 'fa-hashtag',
            percentage: 'fa-percent',
            yesno: 'fa-check-square',
            single_choice: 'fa-dot-circle',
            multiple_choice: 'fa-list-check',
            date: 'fa-calendar',
            datetime: 'fa-calendar-alt',
            blank: 'fa-sticky-note'
        };
        const icon = iconMap[questionTypeValue] || 'fa-question-circle';
        return `fas ${icon} text-lg`;
    },

    // Trigger button icon wrapper (bg + text color) and inner icon for "Select Item Type" button
    getItemTypeTriggerButtonStyles: function(itemType) {
        if (itemType && typeof itemType === 'string' && itemType.startsWith('plugin_')) {
            return { wrapper: 'bg-orange-100 text-orange-600', icon: 'fas fa-puzzle-piece text-lg' };
        }
        if (itemType === 'question') {
            const questionTypeValue = this.modalElement && this.modalElement.querySelector('#item-question-type-select')?.value;
            return {
                wrapper: 'bg-green-100 text-green-600',
                icon: this.getQuestionTypeIcon(questionTypeValue || '')
            };
        }
        const map = {
            indicator: { wrapper: 'bg-purple-100 text-purple-600', icon: 'fas fa-chart-line text-lg' },
            document_field: { wrapper: 'bg-blue-100 text-blue-600', icon: 'fas fa-file-upload text-lg' },
            matrix: { wrapper: 'bg-amber-100 text-amber-600', icon: 'fas fa-table text-lg' }
        };
        return map[itemType] || { wrapper: 'bg-gray-100 text-gray-600', icon: 'fas fa-plus-circle text-lg' };
    },

    updateItemTypeTriggerButton: function(itemType) {
        if (!this.modalElement) return;
        const triggerIcon = this.modalElement.querySelector('#item-type-trigger-icon');
        const triggerLabel = this.modalElement.querySelector('#item-type-trigger-label');
        if (!triggerIcon || !triggerLabel) return;
        const styles = this.getItemTypeTriggerButtonStyles(itemType);
        triggerIcon.className = `flex items-center justify-center w-9 h-9 rounded-lg shrink-0 ${styles.wrapper}`;
        const iconEl = triggerIcon.querySelector('i');
        if (iconEl) iconEl.className = styles.icon;
        triggerLabel.textContent = this.getItemTypeName(itemType);
    },

    getItemTypeIcon: function(itemType) {
        const classes = this.getItemTypeIconClasses(itemType);
        return `<i class="${classes}"></i>`;
    },

    // Get label for a question type value (e.g. 'text' -> 'Short text'). UI only; backend still uses question_type.
    getQuestionTypeLabel: function(value) {
        if (!value) return 'Question';
        const choices = (DataManager && typeof DataManager.getData === 'function') ? (DataManager.getData('questionTypeChoices') || []) : [];
        const pair = Array.isArray(choices) && choices.find(c => c && c[0] === value);
        return pair && pair[1] ? String(pair[1]) : 'Question';
    },

    // Get item type name. For 'question', shows the specific type label (e.g. Short text) when optionalQuestionTypeValue is set or when select is set.
    getItemTypeName: function(itemType, optionalQuestionTypeValue) {
        if (itemType && typeof itemType === 'string' && itemType.startsWith('plugin_')) {
            const fieldTypeId = itemType.replace('plugin_', '');
            const customFieldTypesData = document.getElementById('custom-field-types-data');
            if (customFieldTypesData) {
                try {
                    const customFieldTypes = JSON.parse(customFieldTypesData.textContent);
                    const fieldType = customFieldTypes.find(ft => ft.type_id === fieldTypeId);
                    return fieldType ? fieldType.display_name : 'Plugin Field';
                } catch (e) {
                }
            }
            return 'Plugin Field';
        }
        if (itemType === 'question') {
            const value = optionalQuestionTypeValue != null ? optionalQuestionTypeValue : (this.modalElement && this.modalElement.querySelector('#item-question-type-select')?.value);
            return this.getQuestionTypeLabel(value || '');
        }
        switch (itemType) {
            case 'indicator':
                return 'Indicator';
            case 'document_field':
                return 'Document Field';
            case 'matrix':
                return 'Matrix Table';
            default:
                return 'Item';
        }
    },

    // Update submit button
    updateSubmitButton: function(itemType) {
        const submitBtn = Utils.getElementById('item-modal-submit-btn');
        if (submitBtn) {
            const action = this.currentMode === 'add' ? 'Add' : 'Save';
            const typeName = this.getItemTypeName(itemType);
            submitBtn.textContent = `${action} ${typeName}`;
            // Ensure button is usable when reopening the modal after an AJAX save.
            submitBtn.disabled = false;
            submitBtn.removeAttribute('disabled');
            try { delete submitBtn.dataset.loadingApplied; } catch (_e) {}
        }
    },

    // Reset form
    resetForm: function() {
        this.invalidateIsPercentageCache();
        this._pendingAllowOver100Value = undefined;
        this._pendingUniqueOptionsInSection = undefined;
        this._pendingLimitEntriesToOptionCount = undefined;
        this._pendingUseAsRepeatEntryTitle = undefined;
        if (this.formElement) {
            this.formElement.reset();
        }
    },

    // Populate form with existing data (for edit mode)
    populateForm: function(itemData) {


        // This will be implemented based on the specific item type
        if (this.currentItemType.startsWith('plugin_')) {
            // Store the data for population after template loads (plugin template/config load async)
            this.pendingPluginData = itemData;

            // Populate common fields (section, privacy, etc.) immediately for plugin items
            this.populateCommonFields(itemData);

            // IMPORTANT: Also attach saved rules for plugin items.
            // Plugin items rely on the same rule UI, but their config UI loads async,
            // so we must hydrate rules here (this used to "work" only because previous
            // modal state could leak; after fixing reset, we need a real hydrate step).
            const relevanceBuilderEl = this.modalElement.querySelector('#item-relevance-rule-builder');
            if (relevanceBuilderEl) {
                attachRuleData(relevanceBuilderEl, itemData.relevance_condition, 'relevance');
            }
            const validationBuilderEl = this.modalElement.querySelector('#item-validation-rule-builder');
            if (validationBuilderEl) {
                attachRuleData(validationBuilderEl, itemData.validation_condition, 'validation');
            }
            const validationMsgInput = this.modalElement.querySelector('#item-validation-message');
            if (validationMsgInput) {
                validationMsgInput.value = itemData.validation_message || '';
            }

            // Auto-show sections if rules exist
            setTimeout(() => this.autoShowRuleSections(itemData), 0);
        } else {
            switch (this.currentItemType) {
                case 'indicator':

                    this.populateIndicatorForm(itemData);
                    break;
                case 'question':
                    this.currentQuestionType = itemData.question_type || null;
                    this.populateQuestionForm(itemData);
                    break;
                case 'document_field':

                    this.populateDocumentForm(itemData);
                    break;
                case 'matrix':


                    this.populateMatrixForm(itemData);
                    break;
            }
        }


    },

    // Populate indicator form (delegated)
    populateIndicatorForm: function(itemData) {
        IndicatorItem.populateForm(this.modalElement, itemData);
        // Ensure checkbox exists after indicator is populated (so isPercentageItem can check the indicator)
        this.ensureAllowOver100Field('indicator');
        this.populateCommonFields(itemData);
        const relevanceBuilderEl = this.modalElement.querySelector('#item-relevance-rule-builder');
        if (relevanceBuilderEl) {
            attachRuleData(relevanceBuilderEl, itemData.relevance_condition, 'relevance');
        }
        const validationBuilderEl = this.modalElement.querySelector('#item-validation-rule-builder');
        if (validationBuilderEl) {
            attachRuleData(validationBuilderEl, itemData.validation_condition, 'validation');
        }
        const validationMsgInput = this.modalElement.querySelector('#item-validation-message');
        if (validationMsgInput) {
            validationMsgInput.value = itemData.validation_message || '';
        }
        setTimeout(() => this.autoShowRuleSections(itemData), 200);
    },

    // Populate edit form fields before submission (for edit mode)
    populateEditFormFields: function() {
        // Get the form element
        const form = this.modalElement.querySelector('form');
        if (!form) {

            return;
        }

        // Ensure section_id is set before submission (safety check - template should always provide it)
        const sectionIdInput = form.querySelector('#item-modal-section-id');
        if (sectionIdInput && (!sectionIdInput.value || sectionIdInput.value.trim() === '')) {
            // Fallback: use currentSectionId if available (backend will also use existing item's section_id)
            if (this.currentSectionId) {
                sectionIdInput.value = this.currentSectionId;
            }
        }

        // Handle disaggregation options for indicators
        if (this.currentItemType === 'indicator') {
            const disaggContainer = this.modalElement.querySelector('#add_item_indicator_allowed_disaggregation_options_container');
            if (disaggContainer) {
                const fromModal = Array.from(disaggContainer.querySelectorAll('input[type="checkbox"]:checked'))
                    .map(cb => cb.value);
                // Defensive fallback: some handlers build checkboxes via document-scoped selectors.
                const fromDoc = Array.from(document.querySelectorAll('#add_item_indicator_allowed_disaggregation_options_container input[type="checkbox"]:checked'))
                    .map(cb => cb.value);
                // Also include any already-synced hidden values. This is critical because the checkbox
                // container can be temporarily re-rendered/emptied (e.g. during indicator/filter updates),
                // and we must not clear the user's selections on submit.
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

                // Debug: show what we're about to submit (helps diagnose "not saved" reports)
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

        // Handle relevance/validation rules for all item types without double-encoding
        const relevanceBuilder = this.modalElement.querySelector('#item-relevance-rule-builder');
        setHiddenRuleField(form, 'relevance_condition', relevanceBuilder);

        const validationBuilder = this.modalElement.querySelector('#item-validation-rule-builder');
        setHiddenRuleField(form, 'validation_condition', validationBuilder);

        // Handle validation message for all item types
        const validationMessageInput = this.modalElement.querySelector('#item-validation-message');
        if (validationMessageInput) {
            // Update or create hidden field
            let validationMessageField = form.querySelector('input[name="validation_message"]');
            if (!validationMessageField) {
                validationMessageField = document.createElement('input');
                validationMessageField.type = 'hidden';
                validationMessageField.name = 'validation_message';
                form.appendChild(validationMessageField);
            }
            validationMessageField.value = validationMessageInput.value;
        }

        // Handle matrix fields for matrix items
        if (this.currentItemType === 'matrix') {

            // Collect matrix configuration
            MatrixItem.updateConfig(this.modalElement);

        }

        // Handle document fields for document items
        if (this.currentItemType === 'document_field') {
            // Upload-modal toggles (show_language, show_year, entity document repo / cross_assignment_period_reuse, etc.)
            // use native inputs in _item_modal.html; defaults when editing are set in DocumentItem.populateForm.
            try {
                DocumentItem.syncPresetPeriodToHidden(this.modalElement);
            } catch (e) { /* non-fatal */ }

        }

        // Handle plugin configuration for plugin items
        if (this.currentItemType.startsWith('plugin_')) {

            this.collectPluginConfigFields(form);

        }

        // Handle allow_over_100 for percentage items
        const allowOver100Checkbox = this.modalElement.querySelector('#item-allow-over-100');
        if (allowOver100Checkbox) {
            // Update or create hidden field for config
            let configField = form.querySelector('input[name="config"]');
            if (!configField) {
                configField = document.createElement('input');
                configField.type = 'hidden';
                configField.name = 'config';
                form.appendChild(configField);
            }

            // Parse existing config or create new
            let config = {};
            try {
                if (configField.value) {
                    config = JSON.parse(configField.value);
                }
            } catch (e) {
                config = {};
            }

            // Set allow_over_100 in config
            config.allow_over_100 = allowOver100Checkbox.checked;
            configField.value = JSON.stringify(config);
        }

        // Sync UI fields to hidden fields before submit will also run later
    },

    // Populate question form (delegated)
    populateQuestionForm: function(itemData) {
        const sharedLabel = document.querySelector(this.sharedFields.label);
        if (sharedLabel) {
            sharedLabel.value = itemData.label || '';
        }
        this.syncSharedToUI();
        QuestionItem.populateForm(this.modalElement, itemData);
        const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
        this.updateQuestionFieldLabels(questionTypeSelect ? questionTypeSelect.value : (itemData.question_type || ''));
        // Ensure checkbox exists after question type is populated (so isPercentageItem can check the question type)
        this.ensureAllowOver100Field('question');
        this.populateCommonFields(itemData);
        this.ensureUniqueOptionsInSectionField('question');
        this.ensureUseAsRepeatEntryTitleField('question');
        const translationsInput = this.modalElement.querySelector('#item-modal-shared-label-translations');
        if (translationsInput && itemData.label_translations) {
            translationsInput.value = JSON.stringify(itemData.label_translations);
        }
        const definitionTranslationsInput = this.modalElement.querySelector('#item-modal-definition-translations');
        if (definitionTranslationsInput && itemData.definition_translations) {
            definitionTranslationsInput.value = JSON.stringify(itemData.definition_translations);
        }
        const optionsTranslationsInput = this.modalElement.querySelector('#item-question-options-translations-json');
        if (optionsTranslationsInput && itemData.options_translations) {
            optionsTranslationsInput.value = JSON.stringify(itemData.options_translations);
        }
        const validationMsgInputQ = this.modalElement.querySelector('#item-validation-message');
        if (validationMsgInputQ) {
            validationMsgInputQ.value = itemData.validation_message || '';
        }
        this.autoShowRuleSections(itemData);
    },

    // Populate document form
    populateDocumentForm: function(itemData) {


        // Populate shared fields first
        const sharedLabel = document.querySelector(this.sharedFields.label);
        const sharedDescription = document.querySelector(this.sharedFields.description);
        const sharedLabelTranslations = document.querySelector(this.sharedFields.label_translations);
        const sharedDescriptionTranslations = document.querySelector(this.sharedFields.description_translations);

        if (sharedLabel) {
            sharedLabel.value = itemData.label || '';
        }

        if (sharedDescription) {
            sharedDescription.value = itemData.description || '';
        }

        if (sharedLabelTranslations && itemData.label_translations) {
            sharedLabelTranslations.value = JSON.stringify(itemData.label_translations);
        }

        if (sharedDescriptionTranslations && itemData.description_translations) {
            sharedDescriptionTranslations.value = JSON.stringify(itemData.description_translations);
        }

        // Sync shared fields to UI fields
        this.syncSharedToUI();

        // Populate common fields first
        this.populateCommonFields(itemData);

        // Delegate document-specific population - use a small delay to ensure fields are visible
        // The document fields section might not be fully visible yet when this is called
        setTimeout(() => {
            DocumentItem.populateForm(this.modalElement, itemData);
        }, 50);

        // Attach existing rule JSON to builder container for relevance (documents don't have validation)
        const relevanceBuilderElDoc = this.modalElement.querySelector('#item-relevance-rule-builder');
        if (relevanceBuilderElDoc) {
            relevanceBuilderElDoc.setAttribute('data-rule-json', itemData.relevance_condition || '');
        }

        // Auto-show sections if rules exist
        this.autoShowRuleSections(itemData);
    },

    // Populate matrix form
    populateMatrixForm: function(itemData) {


        // Use timeout to ensure matrix fields are visible
        setTimeout(() => {


            // Check if matrix fields container is visible
            const matrixFieldsContainer = this.modalElement.querySelector('#item-matrix-fields');


            // Populate shared fields first
            const sharedLabel = document.querySelector(this.sharedFields.label);
            const sharedDescription = document.querySelector(this.sharedFields.description);
            const sharedLabelTranslations = document.querySelector(this.sharedFields.label_translations);
            const sharedDescriptionTranslations = document.querySelector(this.sharedFields.description_translations);

            if (sharedLabel) {
                sharedLabel.value = itemData.label || '';

            }

            if (sharedDescription) {
                sharedDescription.value = itemData.description || '';

            }

            // Populate translation fields (same as document fields)
            // Matrix items use description_translations (backend may send as definition_translations)
            if (sharedLabelTranslations && itemData.label_translations) {
                sharedLabelTranslations.value = JSON.stringify(itemData.label_translations);
            }

            // Check both definition_translations (from backend) and description_translations for matrix items
            const descriptionTranslations = itemData.definition_translations || itemData.description_translations;
            if (sharedDescriptionTranslations && descriptionTranslations) {
                sharedDescriptionTranslations.value = JSON.stringify(descriptionTranslations);
            }

            // Sync shared fields to UI fields
            this.syncSharedToUI();

            this.populateMatrixFieldsAfterDelay(itemData);
        }, 150);
    },

    populateMatrixFieldsAfterDelay: function(itemData) {
        // Delegate to matrix module for core population, then proceed with shared logic
        MatrixItem.populateForm(this.modalElement, itemData);
        this.populateCommonFields(itemData);
        const relevanceBuilderEl = this.modalElement.querySelector('#item-relevance-rule-builder');
        if (relevanceBuilderEl) {
            attachRuleData(relevanceBuilderEl, itemData.relevance_condition, 'relevance');
        }
        const validationBuilderEl = this.modalElement.querySelector('#item-validation-rule-builder');
        if (validationBuilderEl) {
            attachRuleData(validationBuilderEl, itemData.validation_condition, 'validation');
        }
        this.autoShowRuleSections(itemData);
    },


    populatePluginBasicFields: function(itemData) {


        // Populate plugin-specific fields
        const labelInput = document.getElementById('item-plugin-label');
        const descriptionInput = document.getElementById('item-plugin-description');

        if (labelInput && itemData.label) {
            labelInput.value = itemData.label;

        }

        if (descriptionInput && itemData.description) {
            descriptionInput.value = itemData.description;

        }

        // Populate translation fields
        const labelTranslationsInput = document.getElementById('item-plugin-label-translations');
        const descriptionTranslationsInput = document.getElementById('item-plugin-description-translations');

        if (labelTranslationsInput && itemData.label_translations) {
            labelTranslationsInput.value = JSON.stringify(itemData.label_translations);
        }

        if (descriptionTranslationsInput && itemData.description_translations) {
            descriptionTranslationsInput.value = JSON.stringify(itemData.description_translations);
        }

        // Populate common fields
        this.populateCommonFields(itemData);
    },

    // Populate common fields for all item types
    populateCommonFields: function(itemData) {

        // Common fields that apply to all item types
        const requiredCheckbox = this.modalElement.querySelector('#item-required');
        const orderInput = this.modalElement.querySelector('#item-order');
        const dataNotAvailableCheckbox = this.modalElement.querySelector('#item-allow-data-not-available');
        const notApplicableCheckbox = this.modalElement.querySelector('#item-allow-not-applicable');
        const disabilityQuestionsCheckbox = this.modalElement.querySelector('#item-allow-disability-questions');
        const indirectReachCheckbox = this.modalElement.querySelector('#item-indirect-reach');
        const layoutWidthSelect = this.modalElement.querySelector('#item-layout-column-width');
        const breakAfterCheckbox = this.modalElement.querySelector('#item-layout-break-after');
        const privacySelect = this.modalElement.querySelector('#item-privacy-select');

        if (requiredCheckbox) {
            requiredCheckbox.checked = itemData.is_required === true || itemData.is_required === 'true';
        }

        if (orderInput && itemData.order) {
            orderInput.value = itemData.order;
        }

        if (dataNotAvailableCheckbox) {
            const val = itemData.allow_data_not_available;
            dataNotAvailableCheckbox.checked = val === true || val === 'true' || val === 1 || val === '1';
        }

        if (notApplicableCheckbox) {
            const val2 = itemData.allow_not_applicable;
            notApplicableCheckbox.checked = val2 === true || val2 === 'true' || val2 === 1 || val2 === '1';
        }

        const uniqueOptionsCheckbox = this.modalElement.querySelector('#item-unique-options-in-section');
        if (uniqueOptionsCheckbox) {
            let uniqueVal = false;
            if (itemData && itemData.config && itemData.config.unique_options_in_section !== undefined) {
                uniqueVal = itemData.config.unique_options_in_section === true
                    || itemData.config.unique_options_in_section === 'true'
                    || itemData.config.unique_options_in_section === 1
                    || itemData.config.unique_options_in_section === '1';
            }
            this._pendingUniqueOptionsInSection = uniqueVal;
            uniqueOptionsCheckbox.checked = uniqueVal;
        }

        const repeatTitleCheckbox = this.modalElement.querySelector('#item-use-as-repeat-entry-title');
        if (repeatTitleCheckbox) {
            let repeatTitleVal = false;
            if (itemData && itemData.config && itemData.config.use_as_repeat_entry_title !== undefined) {
                repeatTitleVal = itemData.config.use_as_repeat_entry_title === true
                    || itemData.config.use_as_repeat_entry_title === 'true'
                    || itemData.config.use_as_repeat_entry_title === 1
                    || itemData.config.use_as_repeat_entry_title === '1';
            }
            this._pendingUseAsRepeatEntryTitle = repeatTitleVal;
            repeatTitleCheckbox.checked = repeatTitleVal;
        }

        const limitEntriesCheckbox = this.modalElement.querySelector('#item-limit-entries-to-option-count');
        if (limitEntriesCheckbox) {
            let limitVal = false;
            if (itemData && itemData.config && itemData.config.limit_entries_to_option_count !== undefined) {
                limitVal = itemData.config.limit_entries_to_option_count === true
                    || itemData.config.limit_entries_to_option_count === 'true'
                    || itemData.config.limit_entries_to_option_count === 1
                    || itemData.config.limit_entries_to_option_count === '1';
            }
            this._pendingLimitEntriesToOptionCount = limitVal;
            limitEntriesCheckbox.checked = limitVal;
        }

        if (disabilityQuestionsCheckbox) {
            const valDisability = itemData.allow_disability_questions;
            disabilityQuestionsCheckbox.checked = valDisability === true || valDisability === 'true' || valDisability === 1 || valDisability === '1';
        }

        if (indirectReachCheckbox) {
            const val3 = itemData.indirect_reach;
            indirectReachCheckbox.checked = val3 === true || val3 === 'true' || val3 === 1 || val3 === '1';
        }

        if (layoutWidthSelect && itemData.layout_column_width) {
            layoutWidthSelect.value = itemData.layout_column_width;
        }

        if (breakAfterCheckbox) {
            breakAfterCheckbox.checked = itemData.layout_break_after === true || itemData.layout_break_after === 'true';
        }

        // Privacy (from config or top-level if provided)
        if (privacySelect) {
            let privacyValue = 'ifrc_network';
            try {
                if (itemData) {
                    if (itemData.privacy) {
                        privacyValue = itemData.privacy;
                    } else if (itemData.config && itemData.config.privacy) {
                        privacyValue = itemData.config.privacy;
                    }
                }
            } catch (e) {}
            // Normalize possible variants to expected option values
            if (typeof privacyValue === 'string') {
                const v = privacyValue.trim().toLowerCase();
                if (v === 'public') {
                    privacyValue = 'public';
                } else if (v === 'ifrc network' || v === 'ifrc_network' || v === 'ifrc' || v === 'network') {
                    privacyValue = 'ifrc_network';
                } else {
                    // Fallback to default if unexpected
                    privacyValue = 'ifrc_network';
                }
            } else {
                privacyValue = 'ifrc_network';
            }
            privacySelect.value = privacyValue;
        }

        // Allow Over 100% checkbox (from config)
        let allowOver100 = false;
        if (itemData && itemData.config && itemData.config.allow_over_100 !== undefined) {
            allowOver100 = itemData.config.allow_over_100 === true || itemData.config.allow_over_100 === 'true' || itemData.config.allow_over_100 === 1 || itemData.config.allow_over_100 === '1';
        }

        // Check if checkbox already exists
        let allowOver100Checkbox = this.modalElement.querySelector('#item-allow-over-100');

        // Only call ensureAllowOver100Field if checkbox doesn't exist yet
        if (!allowOver100Checkbox) {
            // Store the value we want to set before recreating
            this._pendingAllowOver100Value = allowOver100;
            this.ensureAllowOver100Field(this.currentItemType);
            // Get the newly created checkbox
            allowOver100Checkbox = this.modalElement.querySelector('#item-allow-over-100');
        }

        if (allowOver100Checkbox) {
            allowOver100Checkbox.checked = allowOver100;
        }

        // Handle hidden fields
        const sectionIdInput = this.modalElement.querySelector('#item-modal-section-id');
        const itemIdInput = this.modalElement.querySelector('#item-modal-id');
        const sectionSelect = this.modalElement.querySelector('#item-section-select');

        // Set section_id from itemData (template should always provide it via data attribute)
        const sectionId = itemData.section_id || this.currentSectionId;
        if (sectionIdInput && sectionId) {
            sectionIdInput.value = sectionId;
        }

        // Also update the visible section selector dropdown
        if (sectionSelect && sectionId) {
            sectionSelect.value = sectionId;
        }

        if (itemIdInput && itemData.id) {
            itemIdInput.value = itemData.id;

        }

        // Add item_type field for edit mode (required by server-side route)
        if (this.currentMode === 'edit') {
            let itemTypeInput = this.modalElement.querySelector('#item-modal-type');
            if (!itemTypeInput) {
                itemTypeInput = document.createElement('input');
                itemTypeInput.type = 'hidden';
                itemTypeInput.id = 'item-modal-type';
                itemTypeInput.name = 'item_type';
                this.formElement.appendChild(itemTypeInput);
            }
            itemTypeInput.value = this.currentItemType;

        }
    },

    // Setup modal events
    setupModalEvents: function() {
        // Close modal events - only for the item modal
        document.addEventListener('click', (e) => {
            if (!this.modalElement) return;
            if ((e.target.classList.contains('close-modal') || e.target.closest('.close-modal')) &&
                this.modalElement &&
                this.modalElement.contains(e.target)) {
                this.closeModal();
            }
        });

        // Escape key to close modal
        document.addEventListener('keydown', (e) => {
            if (!this.modalElement) return;
            if (e.key === 'Escape' && this.modalElement && !this.modalElement.classList.contains('hidden')) {
                this.closeModal();
            }
        });
    },

    // Setup item type toggle (type is changed via tiles picker; hidden item_type may still exist in edit mode)
    setupItemTypeToggle: function() {
        document.addEventListener('change', (e) => {
            if (!this.modalElement || !this.modalElement.contains(e.target)) return;
            if (e.target.name === 'item_type') {
                this.switchItemType(e.target.value);
            }
        });
    },

    cleanupInactiveModalFields: function(form) {
        const activeType = this.currentItemType;
        const activeMode = this.currentMode;


        // Remove fields from inactive item type sections
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
                // Disable all form fields in inactive sections
                const fields = element.querySelectorAll('input, textarea, select, button');
                fields.forEach(field => {
                    if (field.type === 'submit') return;
                    field.disabled = true;
                });

            }
        });

        // For edit mode, also remove fields from the add modal that might be present
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


    // Setup form submission
    setupFormSubmission: function() {
        // Keep native submit preparation very small and centralized:
        // - AJAX path: FormSubmitUI dispatches `formBuilder:beforeAjaxSubmit`, which calls the same prepare method.
        // - Non-AJAX path: we still prepare here, then let the browser submit normally.
        document.addEventListener('submit', (e) => {
            const form = e?.target;
            if (!form || form.id !== 'item-modal-form') return;
            try {
                this.prepareItemModalFormForSubmit(form);
            } catch (err) {
                // Do not block submission; the global AJAX layer will surface errors if needed.
                try { (window.__clientWarn || console.warn)('[ItemModal] submit prepare failed', err); } catch (_e) {}
            }
        });
    },

    /**
     * Ensure the form submits only the canonical shared hidden inputs for common fields.
     *
     * Why:
     * - Some async-loaded UI (notably plugin base template fallback / previously loaded plugin UI)
     *   can leave inputs in the DOM that also use names like `label`, `description`,
     *   `label_translations`, etc.
     * - Multiple inputs with the same name can cause confusing server-side behavior
     *   (different frameworks read first/last value differently; our backend sometimes uses getlist()).
     * - For indicators, this is critical so clearing "Custom Label" actually sends an empty `label`.
     */
    ensureCanonicalSharedFieldNames: function(formEl) {
        try {
            const form = formEl || this.formElement || this.modalElement?.querySelector?.('form');
            if (!form) return;

            const canonical = {
                label: '#item-modal-shared-label',
                indicator_label_override: '#item-modal-indicator-label-override',
                description: '#item-modal-shared-description',
                label_translations: '#item-modal-shared-label-translations',
                description_translations: '#item-modal-shared-description-translations',
                definition_translations: '#item-modal-definition-translations'
            };

            Object.entries(canonical).forEach(([name, selector]) => {
                const keep = form.querySelector(selector);
                if (keep) {
                    // Ensure canonical field has the correct name
                    keep.setAttribute('name', name);
                }
                // Strip the name from any other inputs that share this name
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

    // Handle form validation to prevent errors on hidden required fields
    handleFormValidation: function(form) {
        const isActuallyHidden = (el) => {
            if (!el) return true;
            if (el.closest('.hidden')) return true;
            if (el.offsetParent === null) return true;
            const style = window.getComputedStyle(el);
            return style.display === 'none' || style.visibility === 'hidden';
        };

        // Remove required only from fields that are not actually visible
        const allRequired = form.querySelectorAll('[required]');
        allRequired.forEach(field => {
            if (isActuallyHidden(field)) {
                field.setAttribute('data-was-required', 'true');
                field.removeAttribute('required');
            }
        });

        // Special handling for matrix fields - no longer required
        if (this.currentItemType === 'matrix') {
            const matrixFields = form.querySelector('#item-matrix-fields');
            if (matrixFields && !isActuallyHidden(matrixFields)) {
                const matrixLabel = matrixFields.querySelector('#item-matrix-label');
                // Matrix label is now optional, no need to set required attribute
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


    // Check if modal needs scrolling and apply appropriate styles
    checkModalScroll: function() {
        if (!this.modalElement) return;

        // Get the modal content container
        const modalContent = this.modalElement.querySelector('.relative.p-6');
        if (!modalContent) return;

        // Get viewport height and modal height
        const viewportHeight = window.innerHeight;
        const modalHeight = this.modalElement.offsetHeight;

        // Add some padding to prevent modal from touching screen edges
        const maxHeight = viewportHeight - 40; // 20px padding top and bottom

        if (modalHeight > maxHeight) {
            // Modal is too tall, add scrolling
            modalContent.style.maxHeight = maxHeight + 'px';
            modalContent.style.overflowY = 'auto';
            modalContent.style.overflowX = 'hidden';

            // Add custom scrollbar styling
            modalContent.classList.add('modal-scrollable');


        } else {
            // Modal fits, remove scrolling
            modalContent.style.maxHeight = '';
            modalContent.style.overflowY = '';
            modalContent.style.overflowX = '';
            modalContent.classList.remove('modal-scrollable');


        }
    },

    // Prepare form action for add mode without interfering with submission
    prepareAddFormAction: function(formElement) {
        // Get section ID from selector (which may have been changed) or fallback to currentSectionId
        const sectionSelect = this.modalElement.querySelector('#item-section-select');
        const sectionId = sectionSelect ? sectionSelect.value : this.currentSectionId;

        if (!sectionId) {
            Utils.showError('Please select a section');
            return;
        }

        // All item types use the common route
        const tplId = window.templateId;
        if (!tplId) {
            Utils.showError('Template ID not found');
            return;
        }
        formElement.action = `/admin/templates/${tplId}/sections/${sectionId}/items/new`;

        // Ensure method is POST
        formElement.method = 'POST';
    },

    // Close modal
    closeModal: function() {
        if (this.modalElement) {
            // Stop observing hidden/disabled invariant changes
            if (this._hiddenDisableObserver) {
                try { this._hiddenDisableObserver.disconnect(); } catch (_) {}
                this._hiddenDisableObserver = null;
            }
            // Stop observing DOM mutations for section proxy sync
            if (this._sectionProxyObserver) {
                try { this._sectionProxyObserver.disconnect(); } catch (_) {}
                this._sectionProxyObserver = null;
            }
            // Teardown focus trap and restore previous focus
            this.teardownFocusTrap();
            // Teardown Select2 instances created for this modal to prevent duplicates
            if (window.jQuery && window.jQuery.fn && window.jQuery.fn.select2) {
                const bankSelect = this.modalElement.querySelector('#item-indicator-bank-select');
                if (bankSelect && $(bankSelect).hasClass('select2-hidden-accessible')) {
                    $(bankSelect).select2('destroy');
                }
            }
            // Teardown matrix listeners if present
            try { MatrixItem.teardown(this.modalElement); } catch (e) {}
            try { QuestionItem.teardown(this.modalElement); } catch (e) {}
            try { IndicatorItem.teardown(this.modalElement); } catch (e) {}
            try { DocumentItem.teardown(this.modalElement); } catch (e) {}
            try { PluginItem.teardown(this.modalElement); } catch (e) {}
            // Hide modal element
            Utils.hideElement(this.modalElement);

            // Reset rule sections/builders and layout to avoid state leakage between edits
            this.resetRuleUIState();

            // Finally reset form fields
            this.resetForm();

            // Clear any pending plugin data to avoid stale state on next open
            this.pendingPluginData = null;

            // Reset scrolling styles
            const modalContent = this.modalElement.querySelector('.relative.p-6');
            if (modalContent) {
                modalContent.style.maxHeight = '';
                modalContent.style.overflowY = '';
                modalContent.style.overflowX = '';
                modalContent.classList.remove('modal-scrollable');
            }
        }
    },

    // submitFormData removed; native submission is used

    // Clear validation errors
    clearValidationErrors: function() {
        if (this.formElement) {
            const errorElements = this.formElement.querySelectorAll('.field-error, .text-red-500');
            errorElements.forEach(element => {
                element.remove();
            });
        }
    },

    // Display validation errors
    displayValidationErrors: function(errors, formPrefix) {
        for (const [fieldName, errorMessages] of Object.entries(errors)) {
            const unprefixedFieldName = fieldName.replace(formPrefix, '');
            const fieldElement = this.formElement.querySelector(`[name="${unprefixedFieldName}"], [id*="${unprefixedFieldName}"]`);

            if (fieldElement) {
                const errorElement = document.createElement('p');
                errorElement.className = 'mt-1 text-red-500 text-xs italic field-error';
                errorElement.textContent = Array.isArray(errorMessages) ? errorMessages.join(', ') : errorMessages;

                fieldElement.parentNode.insertBefore(errorElement, fieldElement.nextSibling);
            }
        }
    },

    collectPluginConfigFields: function(formElement) {
        PluginItem.collectConfigFields(this.modalElement, formElement);
    }
};
