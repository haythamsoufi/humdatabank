// Utils is available globally from utils.js
import { MatrixItem } from '../items/matrix.js';
import { ImageItem } from '../items/image.js';
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
import {
    resetCarryForwardState,
    setupCarryForwardListeners,
} from './carry-forward.js';

export const ItemModal = {
    currentMode: 'add', // 'add' or 'edit'
    currentItemType: 'indicator', // 'indicator', 'question', 'document_field', 'matrix', 'image', or 'plugin_*'
    currentQuestionType: null, // when currentItemType === 'question', e.g. 'text', 'number'
    currentItemId: null,
    currentSectionId: null,
    modalElement: null,
    formElement: null,
    /** Types that open in fill-content mode by default */
    fillContentItemTypes: ['matrix'],
    /** null = follow item-type default; true/false = user override via toggle */
    _fillModeManual: null,

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

    getModalPanel: function() {
        if (!this.modalElement) return null;
        return this.modalElement.querySelector('.item-modal-panel')
            || this.modalElement.querySelector('.relative.p-6');
    },

    isFillContentMode: function() {
        return !!(this.modalElement && this.modalElement.classList.contains('item-modal--fill-content'));
    },

    shouldAutoFillContent: function(itemType) {
        const type = itemType || this.currentItemType;
        return Array.isArray(this.fillContentItemTypes) && this.fillContentItemTypes.indexOf(type) !== -1;
    },

    setFillContentMode: function(enabled) {
        if (!this.modalElement) {
            this.modalElement = Utils.getElementById('item-modal');
        }
        if (!this.modalElement) return;

        const on = !!enabled;
        this.modalElement.classList.toggle('item-modal--fill-content', on);

        const toggleBtn = this.modalElement.querySelector('#item-modal-fill-toggle');
        if (toggleBtn) {
            toggleBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
            const expandLabel = toggleBtn.getAttribute('data-label-expand') || 'Expand to fill content area';
            const compressLabel = toggleBtn.getAttribute('data-label-compress') || 'Exit fill content area';
            const label = on ? compressLabel : expandLabel;
            toggleBtn.setAttribute('title', label);
            toggleBtn.setAttribute('aria-label', label);
        }

        try { this.syncMatrixConfigPanel(); } catch (_e) {}
        this.checkModalScroll();
    },

    syncFillContentMode: function() {
        const enabled = this._fillModeManual != null
            ? this._fillModeManual
            : this.shouldAutoFillContent(this.currentItemType);
        this.setFillContentMode(enabled);
    },

    toggleFillContentMode: function() {
        const next = !this.isFillContentMode();
        this._fillModeManual = next;
        this.setFillContentMode(next);
        try { this.syncRightPanel(); } catch (_e) {}
    },

    /**
     * In fill-content mode, matrix items split the modal into two main
     * columns: the left column keeps the row configuration (row mode, row
     * headers, display options) while the right column holds just the
     * "Column Codes" section. Outside of fill mode (or for other item
     * types) that section stays in its normal place, right after
     * #matrix-columns-anchor.
     */
    syncMatrixConfigPanel: function() {
        if (!this.modalElement) return;
        const columnsSection = this.modalElement.querySelector('#matrix-columns-section');
        const anchor = this.modalElement.querySelector('#matrix-columns-anchor');
        const rightHalf = this.modalElement.querySelector('.modal-right-half');
        if (!columnsSection || !anchor || !rightHalf) return;

        const shouldMoveToRight = this.isFillContentMode() && this.currentItemType === 'matrix';

        if (shouldMoveToRight) {
            if (rightHalf.firstElementChild !== columnsSection) {
                rightHalf.insertBefore(columnsSection, rightHalf.firstChild);
            }
            columnsSection.classList.add('matrix-columns-in-right-panel');
        } else {
            if (columnsSection.previousElementSibling !== anchor) {
                anchor.insertAdjacentElement('afterend', columnsSection);
            }
            columnsSection.classList.remove('matrix-columns-in-right-panel');
        }

        try { this.syncRightPanel(); } catch (_e) {}
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
        this.modalElement = this.modalElement || Utils.getElementById('item-modal');
        setupCarryForwardListeners(this.modalElement);
    },

    showAddModal: function(sectionId, sectionName, itemType = 'indicator', optionalInitialQuestionType = null) {
        this.currentMode = 'add';
        this.currentItemType = itemType;
        this.currentSectionId = sectionId;
        this.currentItemId = null;
        this._fillModeManual = null;

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
        this._fillModeManual = null;

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
        try { resetCarryForwardState(this.modalElement); } catch (_e) {}
        try { QuestionItem.resetOptionsState(this.modalElement); } catch (_e) {}
    },

    setupModalEvents: function() {
        document.addEventListener('click', (e) => {
            if (!this.modalElement) return;
            const fillToggle = e.target.closest('#item-modal-fill-toggle');
            if (fillToggle && this.modalElement.contains(fillToggle)) {
                e.preventDefault();
                this.toggleFillContentMode();
                return;
            }
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

        const modalContent = this.getModalPanel();
        if (!modalContent) return;

        if (this.isFillContentMode()) {
            modalContent.style.maxHeight = '';
            modalContent.style.overflowY = '';
            modalContent.style.overflowX = '';
            modalContent.classList.remove('modal-scrollable');
            return;
        }

        const viewportHeight = window.innerHeight;
        const modalHeight = this.modalElement.offsetHeight;
        const maxHeight = viewportHeight - 40;

        if (modalHeight > maxHeight) {
            modalContent.style.maxHeight = maxHeight + 'px';
            // Use 'scroll' (not 'auto') so the scrollbar track is always present
            // while the modal is capped — avoids left/right content jumps when
            // focus, toolbars, or dropdowns momentarily tip overflow on/off.
            modalContent.style.overflowY = 'scroll';
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
            this.setFillContentMode(false);
            this._fillModeManual = null;
            Utils.hideElement(this.modalElement);
            this.resetRuleUIState();
            this.resetForm();
            this.pendingPluginData = null;

            const modalContent = this.getModalPanel();
            if (modalContent) {
                modalContent.style.maxHeight = '';
                modalContent.style.overflowY = '';
                modalContent.style.overflowX = '';
                modalContent.classList.remove('modal-scrollable');
            }
        }
    },
};
