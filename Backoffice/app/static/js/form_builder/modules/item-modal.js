// Utils is available globally from utils.js
import { DataManager } from './data-manager.js';
import { CsrfHandler } from './csrf-handler.js';
import { CalculatedLists } from './calculated-lists.js';
import RuleBuilder from './conditions.js';
import { hasMeaningfulRuleData, attachRuleData, serializeRule } from './rule-builder-helpers.js';
import { getFormPrefix, setHiddenRuleField, appendRuleToFormData, setMultiHiddenFields } from './form-serialization.js';
import { loadBaseTemplate as PluginApiLoadBaseTemplate, renderFieldBuilder as PluginApiRenderFieldBuilder } from './plugin-api.js';
import { MatrixItem } from './items/matrix.js';
import { QuestionItem } from './items/question.js';
import { IndicatorItem } from './items/indicator.js';
import { DocumentItem } from './items/document.js';
import { PluginItem } from './items/plugin.js';
import { SharedFields } from './shared-fields.js';

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

    // Setup variable autocomplete for label fields
    setupVariableAutocomplete: function() {
        // Use event delegation since modal might not be visible when this runs
        document.addEventListener('input', (e) => {
            // Check if the input allows template variables (e.g. labels, default value inputs)
            const allowVariables = (e.target?.dataset?.enableVariables === 'true');

            // Check if the input is a label field (legacy behavior)
            const isLabelField = e.target.hasAttribute('data-field-type') &&
                                e.target.getAttribute('data-field-type') === 'label';
            const isLabelFieldById = ['item-indicator-label', 'item-question-label',
                                     'item-document-label', 'item-matrix-label',
                                     'item-plugin-label'].includes(e.target.id);

            if (!allowVariables && !isLabelField && !isLabelFieldById) return;

            // Check if input is in the item modal
            const modal = e.target.closest('#item-modal');
            if (!modal) return;

            const input = e.target;
            const cursorPos = input.selectionStart;
            const text = input.value;

            // Check if user is typing a variable (starts with [)
            const textBeforeCursor = text.substring(0, cursorPos);
            const lastBracket = textBeforeCursor.lastIndexOf('[');

            if (lastBracket !== -1) {
                const textAfterBracket = textBeforeCursor.substring(lastBracket + 1);
                // Check if we're still inside brackets (no closing bracket yet)
                if (!textAfterBracket.includes(']')) {
                    // Show variable suggestions
                    this.showVariableSuggestions(input, textAfterBracket, lastBracket, modal);
                } else {
                    this.hideVariableSuggestions(modal);
                }
            } else {
                this.hideVariableSuggestions(modal);
            }
        });

        // Handle clicks outside to close suggestions
        document.addEventListener('click', (e) => {
            const modal = e.target.closest('#item-modal');
            if (!modal) {
                // Close suggestions in all modals
                document.querySelectorAll('#item-modal .variable-suggestions').forEach(s => s.remove());
                return;
            }
            const suggestions = modal.querySelectorAll('.variable-suggestions');
            suggestions.forEach(suggestion => {
                if (!suggestion.contains(e.target)) {
                    suggestion.remove();
                }
            });
        });
    },

    showVariableSuggestions: function(input, partialMatch, bracketPos, modal) {
        // Remove existing suggestions
        this.hideVariableSuggestions(modal);

        // Get available variables: metadata, manual template variables, plugin label variables
        const templateVariables = window.templateVariables || {};
        const variableNames = Object.keys(templateVariables);
        const metadata = Array.isArray(window.builtInMetadataVariables) ? window.builtInMetadataVariables : [];
        const pluginVars = Array.isArray(window.pluginLabelVariables) ? window.pluginLabelVariables : [];

        const suggestionsSource = [
            ...metadata.map(m => ({ key: String(m.key || ''), label: String(m.label || ''), kind: 'metadata' })),
            ...variableNames.map(name => ({ key: String(name), label: String(templateVariables?.[name]?.display_name || ''), kind: 'variable' })),
            ...pluginVars.map(p => ({ key: String(p.key || ''), label: String(p.label || ''), kind: 'plugin' })),
        ].filter(s => s.key);

        // Filter variables that match the partial text
        const matches = suggestionsSource.filter(s =>
            s.key.toLowerCase().startsWith(String(partialMatch || '').toLowerCase())
        );

        if (matches.length === 0) return;

        // Create suggestions dropdown
        const suggestions = document.createElement('div');
        suggestions.className = 'variable-suggestions absolute z-50 bg-white border border-gray-300 rounded-md shadow-lg max-h-48 overflow-y-auto';

        matches.slice(0, 50).forEach(({ key, label, kind }) => {
            const item = document.createElement('div');
            item.className = 'px-3 py-2 hover:bg-blue-100 cursor-pointer text-sm';
            const suffix = kind === 'metadata' ? ` — ${label || key}` : (label ? ` — ${label}` : '');
            item.textContent = `[${key}]${suffix}`;
            item.addEventListener('click', () => {
                const text = input.value;
                const textBeforeBracket = text.substring(0, bracketPos);
                const textAfterCursor = text.substring(input.selectionStart);
                input.value = textBeforeBracket + `[${key}]` + textAfterCursor;
                input.focus();
                input.setSelectionRange(bracketPos + key.length + 2, bracketPos + key.length + 2);
                suggestions.remove();
            });
            suggestions.appendChild(item);
        });

        // Position relative to input field
        const inputRect = input.getBoundingClientRect();
        const modalRect = modal.getBoundingClientRect();
        suggestions.style.position = 'absolute';
        suggestions.style.top = (inputRect.bottom - modalRect.top + modal.scrollTop) + 'px';
        suggestions.style.left = (inputRect.left - modalRect.left) + 'px';
        suggestions.style.minWidth = inputRect.width + 'px';
        suggestions.style.maxWidth = '400px';

        modal.appendChild(suggestions);
    },

    hideVariableSuggestions: function(modal) {
        if (!modal) return;
        const suggestions = modal.querySelectorAll('.variable-suggestions');
        suggestions.forEach(suggestion => suggestion.remove());
    },

    // Setup section selector dropdown
    setupSectionSelector: function() {
        // Event listener for section selector changes will be set up when modal is shown
    },

    // Keep "Section" proxy dropdowns inside plugin builders in sync with the main section selector.
    // Plugin builder templates can declare: <select data-section-proxy="true"> (no name attr).
    syncSectionProxyDropdowns: function() {
        if (!this.modalElement) return;

        const mainSelect = this.modalElement.querySelector('#item-section-select');
        if (!mainSelect) return;

        const proxies = Array.from(this.modalElement.querySelectorAll('select[data-section-proxy="true"]'));
        if (proxies.length === 0) return;

        const optionData = Array.from(mainSelect.options).map((opt) => ({
            value: opt.value,
            text: opt.textContent || ''
        }));

        for (const proxy of proxies) {
            // Rebuild options if empty or out of sync (cheap; options count is small)
            const needsRebuild =
                proxy.options.length !== optionData.length ||
                Array.from(proxy.options).some((o, i) => o.value !== optionData[i]?.value || (o.textContent || '') !== optionData[i]?.text);

            if (needsRebuild) {
                proxy.replaceChildren();
                optionData.forEach(({ value, text }) => {
                    const o = document.createElement('option');
                    o.value = value;
                    o.textContent = text;
                    proxy.appendChild(o);
                });
            }

            // Mirror selection
            if (proxy.value !== mainSelect.value) {
                proxy.value = mainSelect.value;
            }

            // Wire one-time change handler
            if (!proxy.dataset.sectionProxyWired) {
                proxy.dataset.sectionProxyWired = 'true';
                proxy.addEventListener('change', () => {
                    // Avoid loops: only write if changed
                    if (mainSelect.value !== proxy.value) {
                        mainSelect.value = proxy.value;
                        // Let existing listeners update hidden field + order
                        mainSelect.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                });
            }
        }
    },

    setupSectionProxyObserver: function() {
        if (!this.modalElement) return;
        // Tear down any existing observer
        if (this._sectionProxyObserver) {
            try { this._sectionProxyObserver.disconnect(); } catch (_) {}
            this._sectionProxyObserver = null;
        }

        // Observe plugin container (where builder HTML is injected) to sync proxies when they appear
        const pluginContainer =
            this.modalElement.querySelector('#plugin-configuration-container') ||
            this.modalElement.querySelector('#item-plugin-fields-container') ||
            this.modalElement;

        let rafQueued = false;
        const scheduleSync = () => {
            if (rafQueued) return;
            rafQueued = true;
            requestAnimationFrame(() => {
                rafQueued = false;
                this.syncSectionProxyDropdowns();
            });
        };

        this._sectionProxyObserver = new MutationObserver(() => scheduleSync());
        try {
            this._sectionProxyObserver.observe(pluginContainer, { childList: true, subtree: true });
        } catch (_) {
            // no-op
        }

        // Also keep proxies updated if the main selector changes (e.g., user changes section in Properties)
        const mainSelect = this.modalElement.querySelector('#item-section-select');
        if (mainSelect && !mainSelect.dataset.sectionProxyMainWired) {
            mainSelect.dataset.sectionProxyMainWired = 'true';
            mainSelect.addEventListener('change', () => this.syncSectionProxyDropdowns());
        }

        // Initial pass
        this.syncSectionProxyDropdowns();
    },

    // Populate section selector dropdown with available sections
    populateSectionSelector: function() {
        if (!this.modalElement) return;

        const sectionSelect = this.modalElement.querySelector('#item-section-select');
        if (!sectionSelect) return;

        // Get sections from DataManager
        const sections = (DataManager && typeof DataManager.getData === 'function')
            ? (DataManager.getData('allTemplateSections') || [])
            : [];

        // Clear existing options except the first placeholder
        sectionSelect.replaceChildren();
        {
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select a section...';
            sectionSelect.appendChild(placeholder);
        }

        // Add sections to dropdown
        sections.forEach(section => {
            // Handle both [id, name] array format and {id, name} object format
            const sectionId = Array.isArray(section) ? section[0] : (section.id || section.value);
            const sectionName = Array.isArray(section) ? section[1] : (section.name || section.label);

            if (sectionId && sectionName) {
                const option = document.createElement('option');
                option.value = String(sectionId);
                option.textContent = sectionName;
                sectionSelect.appendChild(option);
            }
        });

        // Remove existing event listener if any (to avoid duplicates)
        const newSectionSelect = sectionSelect.cloneNode(true);
        sectionSelect.parentNode.replaceChild(newSectionSelect, sectionSelect);

        // Sync with hidden field when dropdown changes
        newSectionSelect.addEventListener('change', (e) => {
            const hiddenSectionId = this.modalElement.querySelector('#item-modal-section-id');
            if (hiddenSectionId) {
                hiddenSectionId.value = e.target.value;
            }

            // Update currentSectionId
            this.currentSectionId = e.target.value;

            // Recalculate default order for the new section (only in add mode)
            if (this.currentMode === 'add' && e.target.value) {
                this.setDefaultOrderValue(e.target.value);
            }
        });

        return newSectionSelect;
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
                this.updateMatrixConfig();
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

        try { (window.__clientLog || console.debug)('[ItemModal:Privacy] switchItemType ->', itemType); } catch (e) {}

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

    // Ensure Privacy dropdown exists in Properties section
    ensurePrivacyField: function() {
        if (!this.modalElement) return;
        const propertiesSection = this.modalElement.querySelector('.mb-3.border-t.border-gray-200.pt-4');
        try { (window.__clientLog || console.debug)('[ItemModal:Privacy] ensurePrivacyField: propertiesSection exists?', !!propertiesSection); } catch (e) {}
        if (!propertiesSection) return;
        const propertiesContent = propertiesSection.querySelector('.grid.grid-cols-2.gap-6.items-center');
        try { (window.__clientLog || console.debug)('[ItemModal:Privacy] ensurePrivacyField: propertiesContent exists?', !!propertiesContent); } catch (e) {}
        if (!propertiesContent) return;
        // Avoid duplicates
        if (propertiesContent.querySelector('#item-privacy-select')) {
            try { (window.__clientLog || console.debug)('[ItemModal:Privacy] ensurePrivacyField: privacy select already present'); } catch (e) {}
            return;
        }
        // Build field container
        const container = document.createElement('div');
        container.className = 'flex flex-col';
        const label = document.createElement('label');
        label.className = 'block text-gray-700 text-sm font-semibold mb-2';
        label.setAttribute('for', 'item-privacy-select');
        label.textContent = 'Privacy';
        const select = document.createElement('select');
        select.name = 'privacy';
        select.id = 'item-privacy-select';
        select.className = 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md';
        // Options
        const optPublic = document.createElement('option');
        optPublic.value = 'public';
        optPublic.textContent = 'Public';
        const optIfrc = document.createElement('option');
        optIfrc.value = 'ifrc_network';
        optIfrc.textContent = 'Organization network';
        select.appendChild(optPublic);
        select.appendChild(optIfrc);
        // Default to Public for new items
        select.value = 'public';
        container.appendChild(label);
        container.appendChild(select);
        // Append to properties content
        propertiesContent.appendChild(container);
        try { (window.__clientLog || console.debug)('[ItemModal:Privacy] ensurePrivacyField: appended select with default value:', select.value); } catch (e) {}
    },

    // Ensure Allow Over 100% checkbox exists in Properties section for percentage items
    ensureAllowOver100Field: function(itemType) {
        (window.__clientLog || console.debug)('[ItemModal:AllowOver100] ensureAllowOver100Field: called with itemType =', itemType);
        if (!this.modalElement) {
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] ensureAllowOver100Field: modalElement not found');
            return;
        }
        const propertiesSection = this.modalElement.querySelector('.mb-3.border-t.border-gray-200.pt-4');
        if (!propertiesSection) {
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] ensureAllowOver100Field: propertiesSection not found');
            return;
        }
        const propertiesContent = propertiesSection.querySelector('.grid.grid-cols-2.gap-6.items-center');
        if (!propertiesContent) {
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] ensureAllowOver100Field: propertiesContent not found');
            return;
        }

        // Check if this is a percentage item
        const isPercentage = this.isPercentageItem(itemType);
        (window.__clientLog || console.debug)('[ItemModal:AllowOver100] ensureAllowOver100Field: isPercentage =', isPercentage);

        // Get existing checkbox and preserve its checked state if present
        const existingCheckbox = propertiesContent.querySelector('#item-allow-over-100');
        let preservedCheckedState = false;
        if (existingCheckbox) {
            preservedCheckedState = existingCheckbox.checked;
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] ensureAllowOver100Field: removing existing checkbox, preserving checked state =', preservedCheckedState);
            existingCheckbox.closest('.flex.flex-col').remove();
        } else if (this._pendingAllowOver100Value !== undefined) {
            // Use pending value if set (from populateCommonFields)
            preservedCheckedState = this._pendingAllowOver100Value;
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] ensureAllowOver100Field: using pending value =', preservedCheckedState);
            this._pendingAllowOver100Value = undefined; // Clear after use
        }

        // Only add checkbox for percentage items
        if (!isPercentage) {
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] ensureAllowOver100Field: not a percentage item, skipping checkbox creation');
            return;
        }

        (window.__clientLog || console.debug)('[ItemModal:AllowOver100] ensureAllowOver100Field: creating checkbox');

        // Build field container
        const container = document.createElement('div');
        container.className = 'flex flex-col';

        const label = document.createElement('label');
        label.className = 'flex items-center cursor-pointer';
        label.setAttribute('for', 'item-allow-over-100');

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.name = 'allow_over_100';
        checkbox.id = 'item-allow-over-100';
        checkbox.className = 'form-checkbox h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500';

        // Preserve checked state if we had an existing checkbox
        if (preservedCheckedState !== undefined) {
            checkbox.checked = preservedCheckedState;
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] ensureAllowOver100Field: restored checked state =', preservedCheckedState);
        }

        const labelText = document.createElement('span');
        labelText.className = 'ml-2 text-sm text-gray-700';
        labelText.textContent = 'Allow values over 100%';

        label.appendChild(checkbox);
        label.appendChild(labelText);
        container.appendChild(label);

        // Append to properties content
        propertiesContent.appendChild(container);
    },

    // Check if the current item is a percentage type
    isPercentageItem: function(itemType) {
        (window.__clientLog || console.debug)('[ItemModal:AllowOver100] isPercentageItem: checking itemType =', itemType);
        if (itemType === 'question') {
            const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
            const unitInput = this.modalElement.querySelector('#item-question-unit');
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] isPercentageItem: questionTypeSelect value =', questionTypeSelect ? questionTypeSelect.value : 'not found');
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] isPercentageItem: unitInput value =', unitInput ? unitInput.value : 'not found');
            if (questionTypeSelect && questionTypeSelect.value === 'percentage') {
                (window.__clientLog || console.debug)('[ItemModal:AllowOver100] isPercentageItem: detected percentage from question type');
                return true;
            }
            if (unitInput && unitInput.value && unitInput.value.toLowerCase().includes('percentage')) {
                (window.__clientLog || console.debug)('[ItemModal:AllowOver100] isPercentageItem: detected percentage from unit');
                return true;
            }
        } else if (itemType === 'indicator') {
            const indicatorTypeSelect = this.modalElement.querySelector('#item-indicator-type-select');
            const indicatorUnitSelect = this.modalElement.querySelector('#item-indicator-unit-select');
            const bankSelect = this.modalElement.querySelector('#item-indicator-bank-select');

            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] isPercentageItem: indicatorTypeSelect value =', indicatorTypeSelect ? indicatorTypeSelect.value : 'not found');
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] isPercentageItem: indicatorUnitSelect value =', indicatorUnitSelect ? indicatorUnitSelect.value : 'not found');
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] isPercentageItem: bankSelect value =', bankSelect ? bankSelect.value : 'not found');

            // Check type/unit selects
            if (indicatorTypeSelect && indicatorTypeSelect.value &&
                indicatorTypeSelect.value.toLowerCase().includes('percentage')) {
                (window.__clientLog || console.debug)('[ItemModal:AllowOver100] isPercentageItem: detected percentage from indicator type');
                return true;
            }
            if (indicatorUnitSelect && indicatorUnitSelect.value &&
                indicatorUnitSelect.value.toLowerCase().includes('percentage')) {
                (window.__clientLog || console.debug)('[ItemModal:AllowOver100] isPercentageItem: detected percentage from indicator unit');
                return true;
            }

            // Check selected indicator from bank
            if (bankSelect && bankSelect.value) {
                const indicatorId = parseInt(bankSelect.value);
                if (indicatorId) {
                    const indicator = DataManager && typeof DataManager.getIndicatorById === 'function'
                        ? DataManager.getIndicatorById(indicatorId)
                        : null;
                    if (indicator) {
                        const indicatorType = (indicator.type || '').toLowerCase();
                        const indicatorUnit = (indicator.unit || '').toLowerCase();
                        (window.__clientLog || console.debug)('[ItemModal:AllowOver100] isPercentageItem: indicator from bank - type =', indicatorType, 'unit =', indicatorUnit);
                        if (indicatorType.includes('percentage') || indicatorUnit.includes('percentage')) {
                            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] isPercentageItem: detected percentage from indicator bank');
                            return true;
                        }
                    }
                }
            }
        }
        (window.__clientLog || console.debug)('[ItemModal:AllowOver100] isPercentageItem: not a percentage item');
        return false;
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
            // Ensure column headers translation matrix modal is attached (lazy attachment)
            if (typeof window.attachMatrixColumnHeadersModalLazy === 'function') {
                window.attachMatrixColumnHeadersModalLazy();
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
        // Setup listener to update allow over 100 checkbox when indicator changes
        this.setupAllowOver100Listener();
        // Update checkbox visibility after setup
        setTimeout(() => this.ensureAllowOver100Field('indicator'), 100);
    },

    // Setup question-specific fields (delegated to QuestionItem)
    setupQuestionFields: function() {

        QuestionItem.setup(this.modalElement);
        // Setup listener to update allow over 100 checkbox when question type/unit changes
        this.setupAllowOver100Listener();
        // Update checkbox visibility after setup
        setTimeout(() => this.ensureAllowOver100Field('question'), 100);
    },

    // Setup listener to update allow over 100 checkbox visibility
    setupAllowOver100Listener: function() {
        if (!this.modalElement) return;

        // Remove existing listener if any
        if (this._allowOver100Handler) {
            this.modalElement.removeEventListener('change', this._allowOver100Handler);
        }

        // Create new handler
        this._allowOver100Handler = (e) => {
            const targetId = e.target.id;
            // Check if it's a relevant field change
            if (targetId === 'item-indicator-bank-select' ||
                targetId === 'item-indicator-type-select' ||
                targetId === 'item-indicator-unit-select' ||
                targetId === 'item-question-type-select' ||
                targetId === 'item-question-unit') {
                // Update checkbox visibility based on current type
                this.ensureAllowOver100Field(this.currentItemType);
            }
        };

        this.modalElement.addEventListener('change', this._allowOver100Handler);
    },

    // Setup document-specific fields (delegated)
    setupDocumentFields: function() {
        DocumentItem.setup(this.modalElement);
    },

    // Setup matrix-specific fields (delegated to MatrixItem)
    setupMatrixFields: function() {

        MatrixItem.setup(this.modalElement);
    },

    // Initialize default matrix structure (delegated)
    initializeDefaultMatrix: function() {
        MatrixItem.initializeDefault(this.modalElement);
    },

    // Setup matrix event listeners (delegated)
    setupMatrixEventListeners: function() {
        MatrixItem.setupEventListeners(this.modalElement);
    },

    // Add new matrix row (delegated)
    addMatrixRow: function(text = '') {
        MatrixItem.addRow(this.modalElement, text);
    },

    // Add new matrix column (delegated)
    addMatrixColumn: function(text = '', type = 'number') {
        MatrixItem.addColumn(this.modalElement, text, type);
    },

    // Remove matrix row (delegated)
    removeMatrixRow: function(button) {
        MatrixItem.removeRow(button);
    },

    // Remove matrix column (delegated)
    removeMatrixColumn: function(button) {
        MatrixItem.removeColumn(button);
    },

    // Move matrix row up or down (delegated)
    moveMatrixRow: function(button, direction) {
        MatrixItem.moveRow(button, direction);
    },

    // Move matrix column up or down (delegated)
    moveMatrixColumn: function(button, direction) {
        MatrixItem.moveColumn(button, direction);
    },

    // Setup matrix display options event listeners (delegated)
    setupMatrixDisplayOptions: function() {
        MatrixItem.setupDisplayOptions(this.modalElement);
    },

    // Setup matrix row mode switching listeners (delegated)
    setupMatrixRowModeListeners: function() {
        MatrixItem.setupRowModeListeners(this.modalElement);
    },

    // Setup matrix list library functionality (delegated)
    setupMatrixListLibrary: function() {
        MatrixItem.setupListLibrary(this.modalElement);
    },

    // Handle matrix list selection (delegated)
    handleMatrixListSelection: function(listId) {
        MatrixItem.handleListSelection(this.modalElement, listId);
    },

    // Add matrix list filter (delegated)
    addMatrixListFilter: function() {
        MatrixItem.addListFilter(this.modalElement);
    },


    // Update matrix configuration JSON (delegated)
    updateMatrixConfig: function() {
        MatrixItem.updateConfig(this.modalElement);
    },

    // Setup plugin-specific fields (migrated to PluginItem)
    setupPluginFields: function(itemType) {
        PluginItem.setup(this.modalElement, itemType, this.pendingPluginData);
    },

    // Load base plugin template with common fields
    loadBasePluginTemplate: function() {
        return new Promise((resolve, reject) => {
            const container = Utils.getElementById('item-plugin-fields-container');
            if (!container) {

                reject('Plugin fields container not found');
                return;
            }

            // Fetch the base plugin template via helper
            PluginApiLoadBaseTemplate()
            .then(html => {
                this.setSanitizedHtml(container, html);


                // Now that the template is loaded, show the plugin fields and set required attributes
                const pluginFields = document.getElementById('item-plugin-fields');
                if (pluginFields) {
                    Utils.showElement(pluginFields);
                    const pluginLabel = pluginFields.querySelector('#item-plugin-label');
                    if (pluginLabel) {
                        pluginLabel.setAttribute('required', 'required');
                    }
                    const pluginDesc = pluginFields.querySelector('#item-plugin-description');
                    // NOTE: Plugin base templates may include inputs with names that collide with the modal's
                    // canonical shared fields (label, description, *_translations). We don't mutate those
                    // names at load-time; instead we enforce canonical shared-field names at submit-time via
                    // `ensureCanonicalSharedFieldNames()` + the global `beforeAjaxSubmit` hook.
                }

                // If we have pending plugin data (from edit mode), populate basic fields now
                if (this.pendingPluginData) {

                    this.populatePluginBasicFields(this.pendingPluginData);
                    // Don't clear pendingPluginData yet - we need it for plugin config population
                }

                resolve();
            })
            .catch(error => {

                // Fallback: create the basic structure manually
                const frag = document.createRange().createContextualFragment(`
                    <div id="item-plugin-fields" class="hidden">
                        <div class="mb-4">
                            <div class="flex items-center justify-between mb-2">
                                <label for="item-plugin-label" class="block text-gray-700 text-sm font-semibold">Field Label</label>
                                <button type="button" id="plugin-translations-btn" class="inline-flex items-center text-blue-600 hover:text-blue-800 text-sm font-medium" title="Add translations">
                                    <i class="fas fa-language w-4 h-4 mr-1"></i>
                                    Translations
                                </button>
                            </div>
                            <textarea id="item-plugin-label" class="shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md" rows="3" placeholder="Field Label" required autocomplete="off"></textarea>
                        </div>
                        <div class="mb-4">
                            <label for="item-plugin-description" class="block text-gray-700 text-sm font-semibold mb-2">Description (Optional)</label>
                            <textarea id="item-plugin-description" class="shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md" rows="3" placeholder="Description (Optional)" autocomplete="off"></textarea>
                        </div>
                        <div id="plugin-configuration-container" class="mb-4">
                            <!-- Plugin configuration fields will be loaded here -->
                        </div>
                        <input type="hidden" id="item-plugin-label-translations" value="{}">
                        <input type="hidden" id="item-plugin-description-translations" value="{}">
                        <input type="hidden" name="plugin_config" id="item-plugin-config" value="{}">
                    </div>
                `);
                container.replaceChildren();
                container.appendChild(frag);

                // Show the plugin fields and set required attributes for fallback case too
                const pluginFields = document.getElementById('item-plugin-fields');
                if (pluginFields) {
                    Utils.showElement(pluginFields);
                    const pluginLabel = pluginFields.querySelector('#item-plugin-label');
                    if (pluginLabel) {
                        pluginLabel.setAttribute('required', 'required');
                    }
                }

                // If we have pending plugin data (from edit mode), populate basic fields now
                if (this.pendingPluginData) {

                    this.populatePluginBasicFields(this.pendingPluginData);
                    // Don't clear pendingPluginData yet - we need it for plugin config population
                }

                resolve();
            });
        });
    },

    // Load plugin configuration fields
    loadPluginConfiguration: function(fieldType, existingConfig = null) {




        // First, load the base plugin template
        this.loadBasePluginTemplate().then(() => {
            // Then load the specific plugin configuration
            const container = Utils.getElementById('plugin-configuration-container');
            if (!container) {

                return;
            }



            // Show loading state
            container.replaceChildren();
            const loading = document.createElement('div');
            loading.className = 'text-gray-500 text-sm';
            loading.textContent = 'Loading configuration...';
            container.appendChild(loading);

            // Fetch configuration from the plugin API via helper
            PluginApiRenderFieldBuilder(fieldType.type_id, existingConfig)
            .then(data => {


                if (data.success) {
                    this.setSanitizedHtml(container, data.html);


                    // DEPRECATED: Inline script execution is a CSP blocker and is deprecated.
                    // The backend currently returns script: None, so this code path is inactive.
                    // Future plugins should use static JS files loaded via <script src="..."> or ES modules.
                    // See: Backoffice/docs/PLUGIN_SCRIPT_MIGRATION_PLAN.md
                    if (data.script) {
                        (window.__clientWarn || console.warn)('[ItemModal] Plugin returned script text, which is deprecated and will be removed. Use static JS files instead.');
                        const script = document.createElement('script');
                        script.textContent = data.script;
                        container.appendChild(script);
                    }
                    if (data.script_url) {
                        const script = document.createElement('script');
                        script.src = data.script_url;
                        script.type = data.script_type || 'text/javascript';
                        script.async = false;
                        container.appendChild(script);
                    }

                    // Load plugin dependencies
                    this.loadPluginDependencies(fieldType);

                    // Integrate plugin options into Properties section immediately
                    this.integratePluginOptionsIntoProperties(fieldType);

                    // Populate existing configuration if provided (after integration)
                    if (existingConfig) {
                        this.populatePluginConfigFields(existingConfig);
                    }

                // Check if modal needs scrolling after loading plugin configuration
                if (!this._scrollRafQueued) {
                    this._scrollRafQueued = true;
                    requestAnimationFrame(() => {
                        this._scrollRafQueued = false;
                        this.checkModalScroll();
                    });
                }


            } else {
                container.replaceChildren();
                const err = document.createElement('div');
                err.className = 'text-red-500 text-sm';
                err.textContent = `Error loading configuration: ${data?.error || ''}`;
                container.appendChild(err);

            }
            })
            .catch(error => {

                container.replaceChildren();
                const err = document.createElement('div');
                err.className = 'text-red-500 text-sm';
                err.textContent = 'Error loading configuration';
                container.appendChild(err);
            });
        }).catch(error => {

        });
    },

    // Populate plugin configuration fields with existing data
    populatePluginConfigFields: function(config) {


        const container = Utils.getElementById('plugin-configuration-container');
        if (!container) {

            return;
        }

        // Populate all form fields in the container with the configuration data
        const configFields = container.querySelectorAll('input, select, textarea');
        configFields.forEach(field => {
            if (field.name && field.name.trim() && config.hasOwnProperty(field.name)) {
                const value = config[field.name];

                if (field.type === 'checkbox') {
                    field.checked = Boolean(value);
                } else if (field.type === 'radio') {
                    field.checked = field.value === value;
                } else {
                    field.value = value;
                }

                // Trigger change event to update any dependent fields
                field.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });

        // Special handling for allowed_geometry_types array field
        if (config.allowed_geometry_types && Array.isArray(config.allowed_geometry_types)) {
            config.allowed_geometry_types.forEach(geometryType => {
                const checkbox = container.querySelector(`[name="allowed_geometry_types_${geometryType}"]`);
                if (checkbox) {
                    checkbox.checked = true;
                }
            });
        }

        // Special handling for operation_types array field
        if (config.operation_types && Array.isArray(config.operation_types)) {
            config.operation_types.forEach(operationType => {
                const checkbox = container.querySelector(`[name="operation_types"][value="${operationType}"]`);
                if (checkbox) {
                    checkbox.checked = true;
                }
            });
        }

        // Also populate any cloned fields in the Properties section
        const propertiesSection = this.modalElement.querySelector('.mb-3.border-t.border-gray-200.pt-4');
        if (propertiesSection) {
            const propertiesContent = propertiesSection.querySelector('.grid.grid-cols-2.gap-6.items-center');
            if (propertiesContent) {
                const propertiesPluginOptions = propertiesContent.querySelectorAll('.plugin-option-to-properties input, .plugin-option-to-properties select, .plugin-option-to-properties textarea');
                propertiesPluginOptions.forEach(field => {
                    if (field.name && field.name.trim() && config.hasOwnProperty(field.name)) {
                        const value = config[field.name];

                        if (field.type === 'checkbox') {
                            field.checked = Boolean(value);
                        } else if (field.type === 'radio') {
                            field.checked = field.value === value;
                        } else {
                            field.value = value;
                        }

                        // Also update the corresponding original field to keep them in sync
                        const originalField = container.querySelector(`[name="${field.name}"]`);
                        if (originalField) {
                            if (originalField.type === 'checkbox') {
                                originalField.checked = Boolean(value);
                            } else if (originalField.type === 'radio') {
                                originalField.checked = originalField.value === value;
                            } else {
                                originalField.value = value;
                            }
                        }
                    }
                });
            }
        }


    },

    // Load plugin dependencies (CSS and JS)
    loadPluginDependencies: function(fieldType) {
        // Load CSS dependencies
        if (fieldType.css_dependencies) {
            fieldType.css_dependencies.forEach(cssUrl => {
                if (!document.querySelector(`link[href="${cssUrl}"]`)) {
                    const link = document.createElement('link');
                    link.rel = 'stylesheet';
                    link.href = cssUrl;
                    document.head.appendChild(link);
                }
            });
        }

        // Load JavaScript dependencies
        if (fieldType.js_dependencies) {
            fieldType.js_dependencies.forEach(jsUrl => {
                if (!document.querySelector(`script[src="${jsUrl}"]`)) {
                    const script = document.createElement('script');
                    script.src = jsUrl;
                    script.async = true;
                    document.head.appendChild(script);
                }
            });
        }
    },

    // Integrate plugin options into Properties section
    integratePluginOptionsIntoProperties: function(fieldType) {


        // Find the Properties section
        const propertiesSection = this.modalElement.querySelector('.mb-3.border-t.border-gray-200.pt-4');
        if (!propertiesSection) {

            return;
        }

        // Find the plugin configuration container
        const pluginContainer = Utils.getElementById('plugin-configuration-container');
        if (!pluginContainer) {

            return;
        }

        // Look for plugin options that should be moved to Properties
        const pluginOptions = pluginContainer.querySelectorAll('.plugin-option-to-properties');

        if (pluginOptions.length === 0) {

            return;
        }



        // Find the Properties content area (the grid container)
        const propertiesContent = propertiesSection.querySelector('.grid.grid-cols-2.gap-6.items-center');
        if (!propertiesContent) {

            return;
        }

        // Remove previously cloned plugin options to avoid duplicates
        propertiesContent.querySelectorAll('.plugin-option-to-properties.plugin-cloned').forEach(el => el.remove());

        // Move each plugin option to the Properties section
        pluginOptions.forEach((option, index) => {


            // Clone the option to avoid DOM manipulation issues
            const clonedOption = option.cloneNode(true);
            clonedOption.classList.add('plugin-cloned');

            // Ensure the cloned option has the same name attribute for form submission
            const originalInput = option.querySelector('input, select, textarea');
            const clonedInput = clonedOption.querySelector('input, select, textarea');
            if (originalInput && clonedInput && originalInput.name) {
                clonedInput.name = originalInput.name;

                // Generate unique ID for cloned input to avoid duplicate IDs
                if (clonedInput.id) {
                    clonedInput.id = clonedInput.id + '-cloned-' + Date.now();
                }

                // Update the label's 'for' attribute if it exists
                const clonedLabel = clonedOption.querySelector('label[for]');
                if (clonedLabel && clonedInput.id) {
                    clonedLabel.setAttribute('for', clonedInput.id);
                }

                // Copy the current value from the original to the cloned field
                if (originalInput.type === 'checkbox') {
                    clonedInput.checked = originalInput.checked;

                } else {
                    clonedInput.value = originalInput.value;

                }
            }

            // Add to Properties section (append at the end)
            propertiesContent.appendChild(clonedOption);

            // Keep the original visible but hidden for form collection
            option.style.visibility = 'hidden';
            option.style.position = 'absolute';
            option.style.left = '-9999px';
        });



        // Set up event listeners to sync values between original and cloned fields
        this.setupPluginOptionSync();

        // Check if modal needs scrolling after integrating plugin options
        if (!this._scrollRafQueued) {
            this._scrollRafQueued = true;
            requestAnimationFrame(() => {
                this._scrollRafQueued = false;
                this.checkModalScroll();
            });
        }
    },

    // Update values of already integrated plugin options
    updateIntegratedPluginOptionValues: function(pluginContainer, propertiesContent) {
        const originalOptions = pluginContainer.querySelectorAll('.plugin-option-to-properties input, .plugin-option-to-properties select, .plugin-option-to-properties textarea');
        const integratedOptions = propertiesContent.querySelectorAll('.plugin-option-to-properties input, .plugin-option-to-properties select, .plugin-option-to-properties textarea');

        // Update integrated options with current values from originals
        originalOptions.forEach((originalField, index) => {
            const integratedField = integratedOptions[index];
            if (integratedField && originalField.name === integratedField.name) {
                if (originalField.type === 'checkbox') {
                    integratedField.checked = originalField.checked;
                } else {
                    integratedField.value = originalField.value;
                }
            }
        });
    },

    // Setup synchronization between original and cloned plugin options
    setupPluginOptionSync: function() {
        const pluginContainer = Utils.getElementById('plugin-configuration-container');
        const propertiesSection = this.modalElement.querySelector('.mb-3.border-t.border-gray-200.pt-4');

        if (!pluginContainer || !propertiesSection) return;

        const propertiesContent = propertiesSection.querySelector('.grid.grid-cols-2.gap-6.items-center');
        if (!propertiesContent) return;

        // Find all plugin options in both locations
        const originalOptions = pluginContainer.querySelectorAll('.plugin-option-to-properties input, .plugin-option-to-properties select, .plugin-option-to-properties textarea');
        const clonedOptions = propertiesContent.querySelectorAll('.plugin-option-to-properties input, .plugin-option-to-properties select, .plugin-option-to-properties textarea');

        // Set up two-way synchronization
        originalOptions.forEach((originalField, index) => {
            const clonedField = clonedOptions[index];
            if (clonedField && originalField.name === clonedField.name) {
                // Sync from original to cloned
                originalField.addEventListener('change', () => {
                    if (clonedField.type === 'checkbox') {
                        clonedField.checked = originalField.checked;
                    } else {
                        clonedField.value = originalField.value;
                    }
                });

                // Sync from cloned to original
                clonedField.addEventListener('change', () => {
                    if (originalField.type === 'checkbox') {
                        originalField.checked = clonedField.checked;
                    } else {
                        originalField.value = clonedField.value;
                    }
                });
            }
        });
    },

    // Setup plugin event listeners
    setupPluginEventListeners: function(fieldType) {
        // Remove existing event listeners from prior target to prevent duplicates
        if (this.pluginChangeHandler && this.pluginChangeHandlerTarget) {
            this.pluginChangeHandlerTarget.removeEventListener('change', this.pluginChangeHandler);
        }

        // Create the event handler function (delegated within the modal)
        this.pluginChangeHandler = (e) => {
            // Placeholder for plugin-specific field change handling
            // Consumers can extend this based on specific plugin needs
        };

        // Scope to modal element when available; fallback to document
        const target = this.modalElement || document;
        target.addEventListener('change', this.pluginChangeHandler);
        this.pluginChangeHandlerTarget = target;
    },

    // Setup indicator event listeners (delegated)
    setupIndicatorEventListeners: function() {
        IndicatorItem.setupEventListeners(this.modalElement);
    },

    // Setup question event listeners (delegated)
    setupQuestionEventListeners: function() {
        QuestionItem.setupEventListeners(this.modalElement);
    },

    // Toggle question options visibility (delegated)
    toggleQuestionOptions: function(questionType) {
        QuestionItem.toggleOptions(this.modalElement, questionType);
    },

    // Setup document event listeners
    setupDocumentEventListeners: function() {
        // No specific events for document fields currently
    },

    // Populate question options (delegated)
    populateQuestionOptions: function(itemData, optionsJsonInput) {
        QuestionItem.populateQuestionOptions(this.modalElement, itemData, optionsJsonInput);
    },



    // Populate indicator dropdowns (delegated)
    populateIndicatorDropdowns: function() {
        IndicatorItem.populateDropdowns(this.modalElement);
    },

    // Update bank select options based on current filters (delegated)
    updateIndicatorBankOptions: function() {
        IndicatorItem.updateBankOptions(this.modalElement);
    },

    // Populate question type dropdown (delegated)
    populateQuestionTypeDropdown: function() {
        QuestionItem.populateTypeDropdown(this.modalElement);
    },

    // (removed) populateSelect moved to QuestionItem or specific modules

    // Populate disaggregation checkboxes
    populateDisaggregationCheckboxes: function(container, disaggregationChoices, preserveSelections = false) {
        if (!container || !disaggregationChoices) return;

        // If preserving selections, get current selections before clearing
        let currentSelections = [];
        if (preserveSelections) {
            const existingCheckboxes = container.querySelectorAll('input[type="checkbox"]:checked');
            currentSelections = Array.from(existingCheckboxes).map(cb => cb.value);
        }

        // Clear existing checkboxes
        container.replaceChildren();

        disaggregationChoices.forEach(choice => {
            const [value, label] = choice;
            const checkboxDiv = document.createElement('div');
            checkboxDiv.className = 'flex items-center';

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `disagg-${value}`;
            checkbox.value = value;
            checkbox.className = 'form-checkbox h-4 w-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500';

            // Restore selection if preserving
            if (preserveSelections && currentSelections.includes(value)) {
                checkbox.checked = true;
            }

            const labelElement = document.createElement('label');
            labelElement.htmlFor = checkbox.id;
            labelElement.className = 'ml-2 text-sm text-gray-700';
            labelElement.textContent = label;

            checkboxDiv.appendChild(checkbox);
            checkboxDiv.appendChild(labelElement);
            container.appendChild(checkboxDiv);
        });


    },





    // Update disaggregation options (delegated)
    updateDisaggregationOptions: function(indicator, preserveSelections = false) {
        IndicatorItem.updateDisaggregationOptions(this.modalElement, indicator, preserveSelections);
    },

    // Update age groups visibility (delegated)
    updateAgeGroupsVisibility: function(indicator) {
        IndicatorItem.updateAgeGroupsVisibility(this.modalElement, indicator);
    },

    // Update indirect reach visibility for indicators (delegated)
    updateIndirectReachVisibility: function(indicator) {
        IndicatorItem.updateIndirectReachVisibility(this.modalElement, indicator);
    },

    // Update filter dropdowns to match the selected indicator (delegated)
    updateFilterDropdownsFromIndicator: function(indicator) {
        IndicatorItem.updateFilterDropdownsFromIndicator(this.modalElement, indicator);
    },

    // Reset filter dropdowns to "All" options (delegated)
    resetFilterDropdowns: function() {
        IndicatorItem.resetFilterDropdowns(this.modalElement);
    },

    // Update indirect reach visibility for questions (delegated)
    updateIndirectReachVisibilityForQuestion: function() {
        QuestionItem.updateIndirectReachVisibility(this.modalElement);
    },

    // Update question label required attribute based on question type
    updateQuestionLabelRequired: function(questionType) {
        const questionLabel = Utils.getElementById('item-question-label');
        if (!questionLabel) return;

        // Question text is not required for 'blank' (Blank/Note) type
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
        if (this.formElement) {
            this.formElement.reset();
        }
    },

    // Cache original rule toggle button labels so we can restore them reliably
    cacheRuleToggleDefaults: function() {
        const modal = Utils.getElementById('item-modal');
        if (!modal) return;
        modal.querySelectorAll('.toggle-rule-builder').forEach((button) => {
            if (!button.dataset.addLabel) {
                button.dataset.addLabel = String(button.textContent || '').trim();
            }
            // Best-effort hide label (primarily for English UI)
            if (!button.dataset.hideLabel) {
                button.dataset.hideLabel = button.dataset.addLabel.replace('Add', 'Hide');
            }
        });
    },

    // Render a rule toggle button with a single icon + single text node
    renderRuleToggleButton: function(button, state /* 'add' | 'hide' */) {
        if (!button) return;
        if (!button.dataset.addLabel) {
            button.dataset.addLabel = String(button.textContent || '').trim();
        }
        if (!button.dataset.hideLabel) {
            button.dataset.hideLabel = button.dataset.addLabel.replace('Add', 'Hide');
        }

        const label = state === 'hide' ? button.dataset.hideLabel : button.dataset.addLabel;
        const iconClass = state === 'hide' ? 'fa-minus-circle' : 'fa-plus-circle';

        let icon = button.querySelector('i');
        if (!icon) {
            icon = document.createElement('i');
        }
        icon.className = `fas ${iconClass} mr-1`;

        // Replace all children to avoid accumulating multiple text nodes
        button.replaceChildren(icon, document.createTextNode(` ${label}`));
    },

    // Reset relevance/validation rule UI to prevent leakage across edits
    resetRuleUIState: function() {
        if (!this.modalElement) return;

        const rightHalf = this.modalElement.querySelector('.modal-right-half');
        const gridContainer = this.modalElement.querySelector('.modal-grid-container');
        const modalContent = this.modalElement.querySelector('.relative.p-6');

        const relevanceSection = this.modalElement.querySelector('#item-relevance-rule-section');
        const validationSection = this.modalElement.querySelector('#item-validation-rule-section');
        const relevanceBuilder = this.modalElement.querySelector('#item-relevance-rule-builder');
        const validationBuilder = this.modalElement.querySelector('#item-validation-rule-builder');

        // Hide sections and right pane
        if (relevanceSection) relevanceSection.classList.add('hidden');
        if (validationSection) validationSection.classList.add('hidden');
        if (rightHalf) rightHalf.classList.add('hidden');

        // Reset layout
        if (gridContainer) {
            gridContainer.classList.remove('md:grid-cols-2');
            gridContainer.classList.add('grid-cols-1');
        }
        if (modalContent) {
            modalContent.classList.remove('max-w-6xl');
            modalContent.classList.remove('max-w-4xl');
            modalContent.classList.add('max-w-xl');
        }

        // Reset toggle buttons back to Add label + plus icon (avoid duplicate text nodes)
        this.modalElement.querySelectorAll('.toggle-rule-builder').forEach((button) => {
            this.renderRuleToggleButton(button, 'add');
        });

        // Clear rule builders
        if (relevanceBuilder) {
            relevanceBuilder.removeAttribute('data-rule-json');
            relevanceBuilder.replaceChildren();
        }
        if (validationBuilder) {
            validationBuilder.removeAttribute('data-rule-json');
            validationBuilder.replaceChildren();
        }
    },

    // Set default order value for new items
    setDefaultOrderValue: function(sectionId) {
        // Find the order input field
        const orderInput = this.modalElement.querySelector('#item-order');
        if (!orderInput) return;

        // Get the current section's items to calculate the next order
        const sectionItems = (DataManager && typeof DataManager.getData === 'function')
            ? (DataManager.getData('sectionsWithItems') || [])
            : (window.sectionsWithItemsForJs || []);
        // Compare IDs robustly (string vs number)
        const currentSection = sectionItems.find(s => String(s.id) === String(sectionId));

        if (currentSection && currentSection.form_items && currentSection.form_items.length > 0) {
            // Find the highest order value in the current section
            const maxOrder = Math.max(...currentSection.form_items.map(item => parseFloat(item.order) || 0));
            const nextOrder = maxOrder + 1;
            orderInput.value = nextOrder;

        } else {
            // If no items in section, start with order 1
            orderInput.value = 1;

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
        (window.__clientLog || console.debug)('[ItemModal:AllowOver100] populateIndicatorForm: called with itemData =', itemData);
        IndicatorItem.populateForm(this.modalElement, itemData);
        // Ensure checkbox exists after indicator is populated (so isPercentageItem can check the indicator)
        (window.__clientLog || console.debug)('[ItemModal:AllowOver100] populateIndicatorForm: calling ensureAllowOver100Field after populating indicator');
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


            // Collect matrix label
            const matrixLabelInput = this.modalElement.querySelector('#item-matrix-label');




            if (matrixLabelInput) {
                // Update the existing label field instead of creating a new one
                matrixLabelInput.value = matrixLabelInput.value; // Ensure the value is set

            } else {

            }

            // Collect matrix description
            const matrixDescriptionInput = this.modalElement.querySelector('#item-matrix-description');
            if (matrixDescriptionInput) {
                // Update the existing description field instead of creating a new one
                matrixDescriptionInput.value = matrixDescriptionInput.value; // Ensure the value is set

            }

            // Collect matrix configuration
            this.updateMatrixConfig();

            // Collect matrix label translations
            const matrixLabelTranslationsInput = this.modalElement.querySelector('#item-matrix-label-translations');
            if (matrixLabelTranslationsInput) {
                // Update the existing field instead of creating a new one
                matrixLabelTranslationsInput.value = matrixLabelTranslationsInput.value; // Ensure the value is set

            }

            // Collect matrix description translations
            const matrixDescriptionTranslationsInput = this.modalElement.querySelector('#item-matrix-description-translations');
            if (matrixDescriptionTranslationsInput) {
                // Update the existing field instead of creating a new one
                matrixDescriptionTranslationsInput.value = matrixDescriptionTranslationsInput.value; // Ensure the value is set

            }


        }

        // Handle document fields for document items
        if (this.currentItemType === 'document_field') {
            // Upload-modal toggles (show_language, show_year, entity document repo / cross_assignment_period_reuse, etc.)
            // use native inputs in _item_modal.html; defaults when editing are set in DocumentItem.populateForm.
            try {
                DocumentItem.syncPresetPeriodToHidden(this.modalElement);
            } catch (e) { /* non-fatal */ }

            // Collect document label
            const documentLabelInput = this.modalElement.querySelector('#item-document-label');



            if (documentLabelInput) {
                // Update the existing label field instead of creating a new one
                documentLabelInput.value = documentLabelInput.value; // Ensure the value is set

            } else {

            }

            // Collect document description
            const documentDescriptionInput = this.modalElement.querySelector('#item-document-description');
            if (documentDescriptionInput) {
                // Update the existing field instead of creating a new one
                documentDescriptionInput.value = documentDescriptionInput.value; // Ensure the value is set

            }

            // Collect document label translations
            const documentLabelTranslationsInput = this.modalElement.querySelector('#item-document-label-translations');
            if (documentLabelTranslationsInput) {
                // Update the existing field instead of creating a new one
                documentLabelTranslationsInput.value = documentLabelTranslationsInput.value; // Ensure the value is set

            }

            // Collect document description translations
            const documentDescriptionTranslationsInput = this.modalElement.querySelector('#item-document-description-translations');
            if (documentDescriptionTranslationsInput) {
                // Update the existing field instead of creating a new one
                documentDescriptionTranslationsInput.value = documentDescriptionTranslationsInput.value; // Ensure the value is set

            }


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
        (window.__clientLog || console.debug)('[ItemModal:AllowOver100] populateQuestionForm: called with itemData =', itemData);

        const sharedLabel = document.querySelector(this.sharedFields.label);
        if (sharedLabel) {
            sharedLabel.value = itemData.label || '';
        }
        this.syncSharedToUI();
        QuestionItem.populateForm(this.modalElement, itemData);
        // Ensure checkbox exists after question type is populated (so isPercentageItem can check the question type)
        (window.__clientLog || console.debug)('[ItemModal:AllowOver100] populateQuestionForm: calling ensureAllowOver100Field after populating question');
        this.ensureAllowOver100Field('question');
        this.populateCommonFields(itemData);
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

    // Removed duplicate populatePluginBasicFields (merged below)

    // Populate plugin basic fields (label, description, translations) - called after base template loads
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

    // Populate plugin form (called for new items or when basic fields are already populated)
    populatePluginForm: function(itemData) {


        // If basic fields haven't been populated yet (new item), populate them
        const labelInput = document.getElementById('item-plugin-label');
        if (labelInput && !labelInput.value && itemData.label) {
            this.populatePluginBasicFields(itemData);
        }

        // Load plugin configuration if we have the field type
        if (this.currentItemType.startsWith('plugin_')) {
            const fieldTypeId = this.currentItemType.replace('plugin_', '');
            const customFieldTypesData = document.getElementById('custom-field-types-data');
            if (customFieldTypesData) {
                try {
                    const customFieldTypes = JSON.parse(customFieldTypesData.textContent);
                    const fieldType = customFieldTypes.find(ft => ft.type_id === fieldTypeId);
                    if (fieldType) {
                        // Get existing plugin configuration from itemData
                        let existingConfig = null;
                        if (itemData.config && itemData.config.plugin_config) {
                            existingConfig = itemData.config.plugin_config;
                        } else if (itemData.plugin_config) {
                            existingConfig = itemData.plugin_config;
                        }

                        // Load the plugin configuration with existing data
                        this.loadPluginConfiguration(fieldType, existingConfig);

                        // After loading, populate the fields with existing configuration
                        if (existingConfig) {
                            setTimeout(() => {
                                this.populatePluginConfigFields(existingConfig);
                            }, 200); // Give time for the plugin to render
                        }
                    }
                } catch (e) {

                }
            }
        }

        // Attach existing rule JSON to builder container
        const relevanceBuilderEl = document.getElementById('item-relevance-rule-builder');
        if (relevanceBuilderEl) {
            relevanceBuilderEl.setAttribute('data-rule-json', itemData.relevance_condition || '');
        }

        // Auto-show sections if rules exist
        this.autoShowRuleSections(itemData);

        // Clear pending data if this was called from the deferred population
        if (this.pendingPluginData === itemData) {
            this.pendingPluginData = null;

        }
    },

    // Populate common fields for all item types
    populateCommonFields: function(itemData) {


        // Common fields that apply to all item types
        const requiredCheckbox = this.modalElement.querySelector('#item-required');
        const orderInput = this.modalElement.querySelector('#item-order');
        const dataNotAvailableCheckbox = this.modalElement.querySelector('#item-allow-data-not-available');
        const notApplicableCheckbox = this.modalElement.querySelector('#item-allow-not-applicable');
        const indirectReachCheckbox = this.modalElement.querySelector('#item-indirect-reach');
        const layoutWidthSelect = this.modalElement.querySelector('#item-layout-column-width');
        const breakAfterCheckbox = this.modalElement.querySelector('#item-layout-break-after');
        const privacySelect = this.modalElement.querySelector('#item-privacy-select');

        try {
            (window.__clientLog || console.debug)('[ItemModal:Privacy] populateCommonFields: privacySelect exists?', !!privacySelect);
        } catch (e) {}

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
                (window.__clientLog || console.debug)('[ItemModal:Privacy] populateCommonFields: incoming item privacy (top-level):', itemData && itemData.privacy);
                (window.__clientLog || console.debug)('[ItemModal:Privacy] populateCommonFields: incoming item privacy (config):', itemData && itemData.config && itemData.config.privacy);
            } catch (e) {}
            try {
                if (itemData) {
                    if (itemData.privacy) {
                        privacyValue = itemData.privacy;
                    } else if (itemData.config && itemData.config.privacy) {
                        privacyValue = itemData.config.privacy;
                    }
                }
            } catch (e) {}
            try { (window.__clientLog || console.debug)('[ItemModal:Privacy] populateCommonFields: resolved privacy before normalize:', privacyValue); } catch (e) {}
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
            try { (window.__clientLog || console.debug)('[ItemModal:Privacy] populateCommonFields: final privacy set:', privacySelect.value); } catch (e) {}
        }

        // Allow Over 100% checkbox (from config)
        (window.__clientLog || console.debug)('[ItemModal:AllowOver100] populateCommonFields: itemData.config =', itemData && itemData.config);
        (window.__clientLog || console.debug)('[ItemModal:AllowOver100] populateCommonFields: currentItemType =', this.currentItemType);

        // Get the value from config first
        let allowOver100 = false;
        if (itemData && itemData.config && itemData.config.allow_over_100 !== undefined) {
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] populateCommonFields: allow_over_100 value =', itemData.config.allow_over_100, 'type =', typeof itemData.config.allow_over_100);
            allowOver100 = itemData.config.allow_over_100 === true || itemData.config.allow_over_100 === 'true' || itemData.config.allow_over_100 === 1 || itemData.config.allow_over_100 === '1';
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] populateCommonFields: resolved allowOver100 =', allowOver100);
        } else {
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] populateCommonFields: allow_over_100 not found in config or config is missing');
        }

        // Check if checkbox already exists
        let allowOver100Checkbox = this.modalElement.querySelector('#item-allow-over-100');
        (window.__clientLog || console.debug)('[ItemModal:AllowOver100] populateCommonFields: checkbox found?', !!allowOver100Checkbox);

        // Only call ensureAllowOver100Field if checkbox doesn't exist yet
        if (!allowOver100Checkbox) {
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] populateCommonFields: checkbox not found, calling ensureAllowOver100Field');
            // Store the value we want to set before recreating
            this._pendingAllowOver100Value = allowOver100;
            this.ensureAllowOver100Field(this.currentItemType);
            // Get the newly created checkbox
            allowOver100Checkbox = this.modalElement.querySelector('#item-allow-over-100');
        }

        if (allowOver100Checkbox) {
            allowOver100Checkbox.checked = allowOver100;
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] populateCommonFields: set checkbox.checked =', allowOver100Checkbox.checked);
        } else {
            (window.__clientLog || console.debug)('[ItemModal:AllowOver100] populateCommonFields: checkbox still not found after ensureAllowOver100Field');
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

    // Remove unused translation fields from DOM to prevent duplicate form data
    cleanupTranslationFields: function(form) {
        const activeType = this.getCurrentItemType();

        // Remove translation fields that don't belong to the active item type
        const translationFields = [
            { selector: '#item-document-label-translations', types: ['document_field'] },
            { selector: '#item-document-description-translations', types: ['document_field'] },
            { selector: '#item-matrix-label-translations', types: ['matrix'] },
            { selector: '#item-matrix-description-translations', types: ['matrix'] }
        ];

        translationFields.forEach(field => {
            const element = form.querySelector(field.selector);
            if (element && !field.types.includes(activeType)) {
                element.remove();
            }
        });
    },

    // Remove or disable duplicate shared fields so only the active section contributes values
    // Removed duplicate cleanupInactiveModalFields (the earlier definition remains)

    cleanupInactiveModalFields: function(form) {
        const activeType = this.getCurrentItemType();
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

    // Helper to get current item type
    getCurrentItemType: function() {
        const fieldContainers = [
            { selector: '#item-indicator-fields', type: 'indicator' },
            { selector: '#item-question-fields', type: 'question' },
            { selector: '#item-document-fields', type: 'document_field' },
            { selector: '#item-matrix-fields', type: 'matrix' },
            { selector: '#item-plugin-fields', type: 'plugin' }
        ];

        for (const container of fieldContainers) {
            const element = document.querySelector(container.selector);
            if (element && !element.classList.contains('hidden')) {
                return container.type === 'plugin' ? this.currentItemType : container.type;
            }
        }
        return 'question'; // Default
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

        // After a short delay, restore required attributes for visible fields
        setTimeout(() => {
            const fieldsToRestore = form.querySelectorAll('[data-was-required]');
            fieldsToRestore.forEach(field => {
                if (!isActuallyHidden(field)) {
                    // Field is visible, restore required attribute
                    field.setAttribute('required', 'required');
                }
                field.removeAttribute('data-was-required');
            });
        }, 100);
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

    // Setup window resize event listener
    setupWindowResize: function() {
        let resizeTimeout;
        window.addEventListener('resize', () => {
            // Debounce resize events to avoid excessive calls
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(() => {
                // Only check scroll if modal is currently visible
                if (this.modalElement && !this.modalElement.classList.contains('hidden')) {
                    this.checkModalScroll();
                }
            }, 250);
        });
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
        formElement.action = `/admin/templates/${window.templateId}/sections/${sectionId}/items/new`;

        // Ensure method is POST
        formElement.method = 'POST';
    },

    // Handle form submission (legacy custom path removed; we rely on native submit)
    handleFormSubmission: function(event) {
        // Intentionally empty; submission handled by setupFormSubmission via native path
        return;
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

    // Setup ARIA attributes for the modal
    setupModalAria: function() {
        if (!this.modalElement) return;
        this.modalElement.setAttribute('role', 'dialog');
        this.modalElement.setAttribute('aria-modal', 'true');
        const titleElement = this.modalElement.querySelector('.modal-title');
        if (titleElement) {
            if (!titleElement.id) {
                titleElement.id = 'item-modal-title';
            }
            this.modalElement.setAttribute('aria-labelledby', titleElement.id);
        }
    },

    // Focus the first meaningful field in the modal
    focusFirstField: function() {
        if (!this.modalElement) return;
        const focusableSelectors = [
            'input:not([type="hidden"]):not([disabled])',
            'select:not([disabled])',
            'textarea:not([disabled])',
            'button:not([disabled])',
            '[tabindex]:not([tabindex="-1"])'
        ].join(',');
        const focusables = Array.from(this.modalElement.querySelectorAll(focusableSelectors))
            .filter(el => el.offsetParent !== null);
        if (focusables.length > 0) {
            try {
                this._previousFocusedElement = document.activeElement;
                focusables[0].focus();
            } catch (e) {}
        }
    },

    // Trap focus within the modal while it's open
    setupFocusTrap: function() {
        if (!this.modalElement || this._focusTrapAttached) return;
        this._focusTrapAttached = true;
        this._focusTrapHandler = (e) => {
            if (e.key !== 'Tab') return;
            const focusableSelectors = [
                'a[href]',
                'button:not([disabled])',
                'textarea:not([disabled])',
                'input:not([type="hidden"]):not([disabled])',
                'select:not([disabled])',
                '[tabindex]:not([tabindex="-1"])'
            ].join(',');
            const nodes = Array.from(this.modalElement.querySelectorAll(focusableSelectors))
                .filter(el => el.offsetParent !== null);
            if (nodes.length === 0) return;
            const first = nodes[0];
            const last = nodes[nodes.length - 1];
            if (e.shiftKey) {
                if (document.activeElement === first) {
                    e.preventDefault();
                    last.focus();
                }
            } else {
                if (document.activeElement === last) {
                    e.preventDefault();
                    first.focus();
                }
            }
        };
        this.modalElement.addEventListener('keydown', this._focusTrapHandler, true);
    },

    // Remove focus trap and restore focus to the element focused before opening
    teardownFocusTrap: function() {
        if (this.modalElement && this._focusTrapAttached && this._focusTrapHandler) {
            this.modalElement.removeEventListener('keydown', this._focusTrapHandler, true);
        }
        this._focusTrapAttached = false;
        this._focusTrapHandler = null;
        if (this._previousFocusedElement && typeof this._previousFocusedElement.focus === 'function') {
            try { this._previousFocusedElement.focus(); } catch (e) {}
        }
        this._previousFocusedElement = null;
    },

    // Append common fields to form data
    // DEPRECATED: kept for reference; add-mode now uses native inputs
    appendCommonFields: function(formData, formPrefix) {
        const orderInput = Utils.getElementById('item-order');
        const requiredCheckbox = Utils.getElementById('item-required');
        const dataNotAvailableCheckbox = Utils.getElementById('item-allow-data-not-available');
        const notApplicableCheckbox = Utils.getElementById('item-allow-not-applicable');
        const indirectReachCheckbox = Utils.getElementById('item-indirect-reach');
        const layoutWidthSelect = Utils.getElementById('item-layout-column-width');
        const breakAfterCheckbox = Utils.getElementById('item-layout-break-after');
        const submitBtn = Utils.getElementById('item-modal-submit-btn');

        // Add item_type - this is required by the backend route
        formData.append('item_type', this.currentItemType);

        if (orderInput) {
            formData.append(`${formPrefix}order`, orderInput.value);
        }

        if (requiredCheckbox) {
            formData.append(`${formPrefix}is_required`, requiredCheckbox.checked);
        }

        if (dataNotAvailableCheckbox) {
            formData.append(`${formPrefix}allow_data_not_available`, dataNotAvailableCheckbox.checked);
        }

        if (notApplicableCheckbox) {
            formData.append(`${formPrefix}allow_not_applicable`, notApplicableCheckbox.checked);
        }

        if (indirectReachCheckbox) {
            formData.append(`${formPrefix}indirect_reach`, indirectReachCheckbox.checked);
        }

        if (layoutWidthSelect) {
            formData.append(`${formPrefix}layout_column_width`, layoutWidthSelect.value);
        }

        if (breakAfterCheckbox) {
            formData.append(`${formPrefix}layout_break_after`, breakAfterCheckbox.checked);
        }

        if (submitBtn) {
            formData.append(`${formPrefix}submit`, submitBtn.textContent);
        }
    },

    // Append indicator fields to form data
    // DEPRECATED: kept for reference; add-mode now uses native inputs
    appendIndicatorFields: function(formData, formPrefix) {
        const bankSelect = Utils.getElementById('item-indicator-bank-select');
        const disaggContainer = Utils.getElementById('add_item_indicator_allowed_disaggregation_options_container');
        const ageGroupsInput = Utils.getElementById('add_item_modal_indicator_age_groups_input');
        const relevanceRuleBuilder = Utils.getElementById('item-relevance-rule-builder');
        const validationRuleBuilder = Utils.getElementById('item-validation-rule-builder');
        const validationMessageInput = Utils.getElementById('item-validation-message');

        if (bankSelect) {
            formData.append(`${formPrefix}indicator_bank_id`, bankSelect.value);
        }

        // Collect disaggregation options
        if (disaggContainer) {




            const selectedDisaggOptions = Array.from(disaggContainer.querySelectorAll('input[type="checkbox"]:checked'))
                .map(cb => cb.value);



            if (selectedDisaggOptions.length > 0) {
                // Always use the prefixed version for new items, unprefixed for edit
                const fieldName = this.currentMode === 'edit' ? 'allowed_disaggregation_options' : `${formPrefix}allowed_disaggregation_options`;


                // Add all options as a single array
                selectedDisaggOptions.forEach(option => {
                    formData.append(fieldName, option);

                });
            } else {

            }

            // Debug: Log all form data

            for (let [key, value] of formData.entries()) {

            }
        } else {

        }

        if (ageGroupsInput) {
            formData.append(`${formPrefix}age_groups_config`, ageGroupsInput.value);
        }

        // Add rule data
        appendRuleToFormData(formData, 'relevance_condition', relevanceRuleBuilder);
        appendRuleToFormData(formData, 'validation_condition', validationRuleBuilder);

        if (validationMessageInput) {
            // Use the correct field name without prefix for validation message
            formData.append('validation_message', validationMessageInput.value);
        }
    },

    // Append question fields to form data (delegated)
    // DEPRECATED: kept for reference; add-mode now uses native inputs
    appendQuestionFields: function(formData, formPrefix) {
        QuestionItem.appendFields(formData, formPrefix, this.modalElement);
    },

    // Append document fields to form data
    // DEPRECATED: kept for reference; add-mode now uses native inputs
    appendDocumentFields: function(formData, formPrefix) {
        const labelInput = Utils.getElementById('item-document-label');
        const descriptionInput = Utils.getElementById('item-document-description');
        const labelTranslationsInput = Utils.getElementById('item-document-label-translations');
        const descriptionTranslationsInput = Utils.getElementById('item-document-description-translations');
        const relevanceRuleBuilder = Utils.getElementById('item-relevance-rule-builder');

        if (labelInput) {
            formData.append(`${formPrefix}label`, labelInput.value);
        }

        if (descriptionInput) {
            formData.append(`${formPrefix}description`, descriptionInput.value);
        }

        // Add translation fields
        if (labelTranslationsInput) {
            formData.append(`${formPrefix}label_translations`, labelTranslationsInput.value);

        }

        if (descriptionTranslationsInput) {
            formData.append(`${formPrefix}description_translations`, descriptionTranslationsInput.value);

        }

        // Add relevance rule data (document fields typically don't have validation rules)
        appendRuleToFormData(formData, 'relevance_condition', relevanceRuleBuilder);
    },

    // Collect plugin fields data
    // DEPRECATED: kept for reference; add-mode now uses native inputs
    appendPluginFields: function(formData, formPrefix) {
        const labelInput = Utils.getElementById('item-plugin-label');
        const descriptionInput = Utils.getElementById('item-plugin-description');
        const labelTranslationsInput = Utils.getElementById('item-plugin-label-translations');
        const descriptionTranslationsInput = Utils.getElementById('item-plugin-description-translations');
        const relevanceRuleBuilder = Utils.getElementById('item-relevance-rule-builder');
        const validationRuleBuilder = Utils.getElementById('item-validation-rule-builder');

        if (labelInput) {
            formData.append(`${formPrefix}label`, labelInput.value);
        }

        if (descriptionInput) {
            formData.append(`${formPrefix}description`, descriptionInput.value);
        }

        // Add translation fields
        if (labelTranslationsInput) {
            formData.append(`${formPrefix}label_translations`, labelTranslationsInput.value);
        }

        if (descriptionTranslationsInput) {
            formData.append(`${formPrefix}description_translations`, descriptionTranslationsInput.value);
        }

        // Dynamically collect all plugin configuration fields
        const pluginConfigContainer = Utils.getElementById('plugin-configuration-container');
        if (pluginConfigContainer) {
            const pluginConfig = {};

            // Collect all form fields from the plugin configuration container
            const configFields = pluginConfigContainer.querySelectorAll('input, select, textarea');
            configFields.forEach(field => {
                if (field.name && field.name.trim()) {
                    if (field.type === 'checkbox' || field.type === 'radio') {
                        if (field.checked) {
                            pluginConfig[field.name] = field.value || true;
                        }
                    } else {
                        pluginConfig[field.name] = field.value;
                    }
                }
            });

            // Also collect any plugin options that were moved to the Properties section
            const propertiesSection = this.modalElement.querySelector('.mb-3.border-t.border-gray-200.pt-4');
            if (propertiesSection) {
                const propertiesContent = propertiesSection.querySelector('.grid.grid-cols-2.gap-6.items-center');
                if (propertiesContent) {
                    const propertiesPluginOptions = propertiesContent.querySelectorAll('.plugin-option-to-properties input, .plugin-option-to-properties select, .plugin-option-to-properties textarea');
                    propertiesPluginOptions.forEach(field => {
                        if (field.name && field.name.trim()) {
                            if (field.type === 'checkbox' || field.type === 'radio') {
                                if (field.checked) {
                                    pluginConfig[field.name] = field.value || true;
                                }
                            } else {
                                pluginConfig[field.name] = field.value;
                            }
                        }
                    });
                }
            }

            // Add the collected plugin configuration as JSON
            formData.append('plugin_config', JSON.stringify(pluginConfig));
        }

        // Add rule data via centralized helper to avoid double-encoding
        appendRuleToFormData(formData, 'relevance_condition', relevanceRuleBuilder);
        appendRuleToFormData(formData, 'validation_condition', validationRuleBuilder);
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

    // Show error message
    showErrorMessage: function(message) {
        const titleElement = this.modalElement.querySelector('.modal-title, h3');
        if (titleElement) {
            const messageElement = document.createElement('p');
            messageElement.className = 'mt-2 text-red-500 text-sm italic';
            messageElement.textContent = `Error: ${message}`;
            titleElement.parentNode.insertBefore(messageElement, titleElement.nextSibling);
        } else {
            window.showAlert(`Error: ${message}`, 'error');
        }
    },


    // Toggle question options visibility (delegated)
    toggleOptionsContainer: function(questionType, showManual) {
        QuestionItem.toggleOptionsContainer(this.modalElement, questionType, showManual);
    },

    // Populate option fields (for manual options)
    populateOptionFields: function(optionsData) {
        // Add null check to prevent errors
        if (!this.modalElement) {

            return;
        }

        const optionsContainer = this.modalElement.querySelector('#item-question-options-container');
        const optionsList = this.modalElement.querySelector('#item-question-options-list');

        if (optionsContainer && optionsList) {
            // Clear existing options
            optionsList.replaceChildren();

            // Add each option using the global function
            if (optionsData && optionsData.length > 0) {
                optionsData.forEach(option => {
                    if (window.addOptionField) {
                        window.addOptionField(optionsList, option);
                    }
                });
            } else {
                // Add one empty field if no options exist
                if (window.addOptionField) {
                    window.addOptionField(optionsList, '');
                }
            }

            // Update the JSON
            if (window.updateOptionsJson) {
                window.updateOptionsJson(optionsList);
            }

            // Make sure options container is visible for choice types
            const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
            if (questionTypeSelect && ['single_choice', 'multiple_choice'].includes(questionTypeSelect.value)) {
                Utils.showElement(optionsContainer);
            }

            // Check if modal needs scrolling after adding options
            if (!this._scrollRafQueued) {
                this._scrollRafQueued = true;
                requestAnimationFrame(() => {
                    this._scrollRafQueued = false;
                    this.checkModalScroll();
                });
            }
        } else {

        }
    },

    // Auto-show rule sections if rules exist
    autoShowRuleSections: function(itemData) {
        // Add null check to prevent errors
        if (!this.modalElement) {

            return;
        }





        const relevanceBuilderEl = this.modalElement.querySelector('#item-relevance-rule-builder');
        const validationRuleBuilder = this.modalElement.querySelector('#item-validation-rule-builder');
        const relevanceSection = this.modalElement.querySelector('#item-relevance-rule-section');
        const validationSection = this.modalElement.querySelector('#item-validation-rule-section');
        const rightHalf = this.modalElement.querySelector('.modal-right-half');
        const modalGrid = this.modalElement.querySelector('.modal-grid-container');
        const modalContent = this.modalElement.closest('.relative.p-6') || this.modalElement.querySelector('.relative.p-6.border.w-full.max-w-xl.shadow-xl.rounded-lg.bg-white');











        let hasVisibleRules = false;

        // Helper function to check if rule data is meaningful
        const hasRuleData = (ruleData) => {
            // Using hasMeaningfulRuleData imported from rule-builder-helpers
            return hasMeaningfulRuleData(ruleData);
        };

        // Handle relevance rules
        if (relevanceBuilderEl && hasRuleData(itemData.relevance_condition)) {


            // Show the relevance section
            if (relevanceSection) {

                Utils.showElement(relevanceSection);



            }

            // Update button text and icon
            const relevanceButton = this.modalElement.querySelector('[data-target="#item-relevance-rule-section"]');

            if (relevanceButton) {
                this.renderRuleToggleButton(relevanceButton, 'hide');
            }

        // Initialize rule builder with existing data
        if (relevanceBuilderEl.innerHTML.trim() === '') {

            try {
                attachRuleData(relevanceBuilderEl, itemData.relevance_condition, 'relevance');
            } catch (e) {}
            } else {

            }

            hasVisibleRules = true;
        } else {

            if (relevanceSection) {
                Utils.hideElement(relevanceSection);
            }
            const relevanceButton = this.modalElement.querySelector('[data-target="#item-relevance-rule-section"]');
            if (relevanceButton) {
                this.renderRuleToggleButton(relevanceButton, 'add');
            }
        }

        // Handle validation rules
        if (validationRuleBuilder && hasRuleData(itemData.validation_condition)) {


            // Show the validation section
            if (validationSection) {

                Utils.showElement(validationSection);



            }

            // Update button text and icon
            const validationButton = this.modalElement.querySelector('[data-target="#item-validation-rule-section"]');

            if (validationButton) {
                this.renderRuleToggleButton(validationButton, 'hide');
            }

        // Initialize rule builder with existing data
        if (validationRuleBuilder.innerHTML.trim() === '') {

            try {
                attachRuleData(validationRuleBuilder, itemData.validation_condition, 'validation');
            } catch (e) {}
            } else {

            }

            hasVisibleRules = true;
        } else {

            if (validationSection) {
                Utils.hideElement(validationSection);
            }
            const validationButton = this.modalElement.querySelector('[data-target="#item-validation-rule-section"]');
            if (validationButton) {
                this.renderRuleToggleButton(validationButton, 'add');
            }
        }

        // Show right half and expand modal layout if there are visible rules
        if (hasVisibleRules && rightHalf && modalGrid && modalContent) {


            Utils.showElement(rightHalf);





            modalGrid.classList.add('md:grid-cols-2');



            modalContent.classList.remove('max-w-xl');
            modalContent.classList.add('max-w-6xl');

        } else if (!hasVisibleRules && rightHalf && modalGrid && modalContent) {

            Utils.hideElement(rightHalf);
            modalGrid.classList.remove('md:grid-cols-2');
            modalContent.classList.remove('max-w-6xl');
            modalContent.classList.add('max-w-xl');
        }

        // Check if modal needs scrolling after layout changes
        if (!this._scrollRafQueued) {
            this._scrollRafQueued = true;
            requestAnimationFrame(() => {
                this._scrollRafQueued = false;
                this.checkModalScroll();
            });
        }
    },

    // Removed duplicate initializeSelect2 (use initializeModalSelect2)

    // Collect plugin configuration fields and add them to the form (delegated)
    collectPluginConfigFields: function(formElement) {
        PluginItem.collectConfigFields(this.modalElement, formElement);
    },

    // Prevent autofill and password manager interference
    preventAutofillInterference: function() {
        // Target fields that commonly get autofilled
        const autofillTargets = [
            '#item-plugin-label',
            '#item-plugin-description',
            '#item-question-label',
            '#item-question-definition'
        ];

        autofillTargets.forEach(selector => {
            const field = this.modalElement.querySelector(selector);
            if (field) {
                // Set multiple attributes to confuse autofill systems
                field.setAttribute('autocomplete', 'new-password');
                field.setAttribute('data-lpignore', 'true');
                field.setAttribute('data-form-type', 'other');
                field.setAttribute('data-1p-ignore', 'true'); // 1Password
                field.setAttribute('data-bwignore', 'true'); // Bitwarden

                // Add event listeners to prevent autofill
                field.addEventListener('focus', function(e) {
                    // Temporarily change type to confuse password managers
                    const originalType = e.target.type;
                    e.target.type = 'password';
                    setTimeout(() => {
                        e.target.type = originalType;
                    }, 10);
                });

                field.addEventListener('input', function(e) {
                    // Clear any autofilled values
                    if (e.target.value && e.target.value.includes('@') && e.target.name === 'label') {
                        // If it looks like an email was autofilled, clear it
                        e.target.value = '';
                    }
                });

                // Add a hidden fake field to trick password managers
                const fakeField = document.createElement('input');
                fakeField.type = 'text';
                fakeField.style.position = 'absolute';
                fakeField.style.left = '-9999px';
                fakeField.style.opacity = '0';
                fakeField.setAttribute('data-lpignore', 'false');
                fakeField.setAttribute('autocomplete', 'username');
                field.parentNode.appendChild(fakeField);
            }
        });
    }
};
