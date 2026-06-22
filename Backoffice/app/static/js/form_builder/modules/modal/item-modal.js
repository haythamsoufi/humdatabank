// Utils is available globally from utils.js
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
import { HiddenControlsMixin } from './hidden-controls.js';
import { FormSubmitMixin } from './form-submit.js';
import { ItemTypeUIMixin } from './item-type-ui.js';
import { FormPopulationMixin } from './form-population.js';
import { ValidationMixin } from './validation.js';

export const ItemModal = {
    currentMode: 'add', // 'add' or 'edit'
    currentItemType: 'indicator', // 'indicator', 'question', 'document_field', 'matrix', or 'plugin_*'
    currentQuestionType: null, // when currentItemType === 'question', e.g. 'text', 'number'
    currentItemId: null,
    currentSectionId: null,
    modalElement: null,
    formElement: null,

    sharedFields: {
        label: '#item-modal-shared-label',
        description: '#item-modal-shared-description',
        label_translations: '#item-modal-shared-label-translations',
        description_translations: '#item-modal-shared-description-translations'
    },

    syncSharedToUI: function() { SharedFields.syncSharedToUI(); },
    syncUIToShared: function() { SharedFields.syncUIToShared(); },
    setupFieldSync: function() { SharedFields.setupFieldSync(this.modalElement); },

    ...VariableAutocompleteMixin,
    ...AccessibilityMixin,
    ...RuleUIMixin,
    ...SectionSelectorMixin,
    ...PropertiesMixin,
    ...HiddenControlsMixin,
    ...FormSubmitMixin,
    ...ItemTypeUIMixin,
    ...FormPopulationMixin,
    ...ValidationMixin,

    // Safe HTML insertion helper for server-provided fragments (plugin templates/builders).
    setSanitizedHtml: function(container, html) {
        Utils.setSanitizedHtml(container, html);
    },

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
    },

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

        this.resetForm();
        this.resetRuleUIState();

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

        const templateIdInput = Utils.getElementById('item-modal-template-id');
        const sectionIdInput = Utils.getElementById('item-modal-section-id');
        if (templateIdInput && sectionIdInput) {
            templateIdInput.value = window.templateId;
            sectionIdInput.value = sectionId;
        }

        const sectionSelect = this.populateSectionSelector();
        if (sectionSelect && sectionId) {
            sectionSelect.value = String(sectionId);
        }
        this.setupSectionProxyObserver();

        const templateId = window.templateId;
        if (templateId) {
            this.formElement.action = `/admin/templates/${templateId}/sections/${sectionId}/items/new`;
        } else {
            Utils.showError('Template ID not found');
            return;
        }

        this.setDefaultOrderValue(sectionId);
        Utils.showElement(this.modalElement);

        try {
            const submitBtn = Utils.getElementById('item-modal-submit-btn');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.removeAttribute('disabled');
                if (submitBtn.dataset) delete submitBtn.dataset.loadingApplied;
            }
        } catch (_e) {}

        this.switchItemType(itemType, optionalInitialQuestionType);
        this.syncSectionProxyDropdowns();
        try { this.setupHiddenDisableObserver(); } catch (_e) {}

        this.setupModalAria();
        setTimeout(() => {
            this.focusFirstField();
            this.setupFocusTrap();
        }, 50);

        this.checkModalScroll();
    },

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

        const titleElement = this.modalElement.querySelector('.modal-title');
        if (titleElement) {
            titleElement.replaceChildren();
            const iconEl = document.createElement('i');
            iconEl.className = this.getItemTypeIconClasses(itemType);
            titleElement.appendChild(iconEl);
            const typeLabel = itemType === 'question' ? this.getItemTypeName(itemType, itemData.question_type) : this.getItemTypeName(itemType);
            titleElement.appendChild(document.createTextNode(`Edit ${typeLabel}`));
        }

        this.formElement.action = `/admin/items/edit/${itemId}`;
        this.resetForm();
        this.resetRuleUIState();

        if (itemType && itemType.startsWith('plugin_')) {
            this.pendingPluginData = itemData;
        }

        this.switchItemType(itemType);
        this.setupSectionProxyObserver();
        try { this.setupHiddenDisableObserver(); } catch (_e) {}

        this.initializeModalSelect2();
        Utils.showElement(this.modalElement);

        try {
            const submitBtn = Utils.getElementById('item-modal-submit-btn');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.removeAttribute('disabled');
                if (submitBtn.dataset) delete submitBtn.dataset.loadingApplied;
            }
        } catch (_e) {}

        setTimeout(() => {
            const sectionSelect = this.populateSectionSelector();
            void sectionSelect;
            this.populateForm(itemData);
            if (this.currentItemType === 'question') {
                this.updateItemTypeTriggerButton('question');
            }
            this.syncSectionProxyDropdowns();
            this.checkModalScroll();
            this.setupModalAria();
            this.focusFirstField();
            this.setupFocusTrap();
        }, 100);
    },

    initializeModalSelect2: function() {
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

    resetForm: function() {
        this.invalidateIsPercentageCache();
        this._pendingAllowOver100Value = undefined;
        this._pendingUniqueOptionsInSection = undefined;
        this._pendingLimitEntriesToOptionCount = undefined;
        this._pendingUseAsRepeatEntryTitle = undefined;
        if (this.formElement) {
            this.formElement.reset();
        }
        try { QuestionItem.resetOptionsState(this.modalElement); } catch (_e) {}
    },

    setupModalEvents: function() {
        document.addEventListener('click', (e) => {
            if (!this.modalElement) return;
            if ((e.target.classList.contains('close-modal') || e.target.closest('.close-modal')) &&
                this.modalElement &&
                this.modalElement.contains(e.target)) {
                this.closeModal();
            }
        });

        document.addEventListener('keydown', (e) => {
            if (!this.modalElement) return;
            if (e.key === 'Escape' && this.modalElement && !this.modalElement.classList.contains('hidden')) {
                this.closeModal();
            }
        });
    },

    checkModalScroll: function() {
        if (!this.modalElement) return;

        const modalContent = this.modalElement.querySelector('.relative.p-6');
        if (!modalContent) return;

        const viewportHeight = window.innerHeight;
        const modalHeight = this.modalElement.offsetHeight;
        const maxHeight = viewportHeight - 40;

        if (modalHeight > maxHeight) {
            modalContent.style.maxHeight = maxHeight + 'px';
            modalContent.style.overflowY = 'auto';
            modalContent.style.overflowX = 'hidden';
            modalContent.classList.add('modal-scrollable');
        } else {
            modalContent.style.maxHeight = '';
            modalContent.style.overflowY = '';
            modalContent.style.overflowX = '';
            modalContent.classList.remove('modal-scrollable');
        }
    },

    closeModal: function() {
        if (this.modalElement) {
            if (this._hiddenDisableObserver) {
                try { this._hiddenDisableObserver.disconnect(); } catch (_) {}
                this._hiddenDisableObserver = null;
            }
            if (this._sectionProxyObserver) {
                try { this._sectionProxyObserver.disconnect(); } catch (_) {}
                this._sectionProxyObserver = null;
            }
            this.teardownFocusTrap();
            if (window.jQuery && window.jQuery.fn && window.jQuery.fn.select2) {
                const bankSelect = this.modalElement.querySelector('#item-indicator-bank-select');
                if (bankSelect && $(bankSelect).hasClass('select2-hidden-accessible')) {
                    $(bankSelect).select2('destroy');
                }
            }
            try { MatrixItem.teardown(this.modalElement); } catch (e) {}
            try { QuestionItem.teardown(this.modalElement); } catch (e) {}
            try { IndicatorItem.teardown(this.modalElement); } catch (e) {}
            try { DocumentItem.teardown(this.modalElement); } catch (e) {}
            try { PluginItem.teardown(this.modalElement); } catch (e) {}
            Utils.hideElement(this.modalElement);
            this.resetRuleUIState();
            this.resetForm();
            this.pendingPluginData = null;

            const modalContent = this.modalElement.querySelector('.relative.p-6');
            if (modalContent) {
                modalContent.style.maxHeight = '';
                modalContent.style.overflowY = '';
                modalContent.style.overflowX = '';
                modalContent.classList.remove('modal-scrollable');
            }
        }
    },
};
