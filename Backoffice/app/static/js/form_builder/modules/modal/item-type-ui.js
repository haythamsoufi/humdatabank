import { DataManager } from '../data-manager.js';
import { MatrixItem } from '../items/matrix.js';
import { ImageItem } from '../items/image.js';
import { QuestionItem } from '../items/question.js';
import { IndicatorItem } from '../items/indicator.js';
import { DocumentItem } from '../items/document.js';
import { PluginItem } from '../items/plugin.js';
import { BlankBodyEditor, BlankTranslationEditor } from '../items/blank.js';
import { mountEntryFormHintPanel } from './description-hint-ui.js';

export const ItemTypeUIMixin = {
    switchItemType: function(itemType, optionalQuestionType) {
        this.currentItemType = itemType;

        try {
            const row = this.modalElement ? this.modalElement.querySelector('#indirect-reach-row') : document.getElementById('indirect-reach-row');
            const cb = row ? row.querySelector('#item-indirect-reach') : document.getElementById('item-indirect-reach');
            if (cb) {
                if (itemType !== 'indicator') {
                    cb.checked = false;
                    cb.disabled = true;
                } else {
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

        this.updateItemTypeTriggerButton(itemType);

        if (this.currentMode === 'edit') {
            const itemTypeInput = this.modalElement.querySelector('#item-modal-type');
            if (itemTypeInput) {
                itemTypeInput.value = itemType;
            }
        }

        this.toggleFieldsVisibility(itemType);

        if (itemType === 'question') {
            const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
            const questionTypeInput = this.modalElement.querySelector('#item-question-type-input');
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

        try { (window.__clientLog || console.debug)('[ItemModal:Privacy] calling ensurePrivacyField()'); } catch (e) {}
        this.ensurePrivacyField();
        this.ensureDisplayOnlyPropertyFields(itemType);
        this.ensureMatrixDisplayProperties(itemType);
        this.ensureAllowOver100Field(itemType);
        this.ensureUniqueOptionsInSectionField(itemType);
        this.ensureUseAsRepeatEntryTitleField(itemType);
        this.updateSubmitButton(itemType);

        try { this.enforceHiddenControlsDisabled(this.modalElement); } catch (_e) {}
        this._fillModeManual = null;
        try { this.syncFillContentMode(); } catch (_e) {}
        try { this.syncRightPanel(); } catch (_e) {}
        try { mountEntryFormHintPanel(this.modalElement, itemType); } catch (_e) {}

        if (!this._scrollRafQueued) {
            this._scrollRafQueued = true;
            requestAnimationFrame(() => {
                this._scrollRafQueued = false;
                this.checkModalScroll();
            });
        }
    },

    toggleFieldsVisibility: function(itemType) {
        const indicatorFields = Utils.getElementById('item-indicator-fields');
        const questionFields = Utils.getElementById('item-question-fields');
        const documentFields = Utils.getElementById('item-document-fields');
        const matrixFields = Utils.getElementById('item-matrix-fields');
        const imageFields = Utils.getElementById('item-image-fields');
        const pluginFieldsContainer = Utils.getElementById('item-plugin-fields-container');

        const setContainerDisabled = (container, disabled) => {
            if (!container) return;
            container.querySelectorAll('input, select, textarea, button').forEach(el => {
                if (el.type === 'submit') return;
                el.disabled = !!disabled;
            });
        };

        Utils.hideElement(indicatorFields);
        Utils.hideElement(questionFields);
        Utils.hideElement(documentFields);
        Utils.hideElement(matrixFields);
        Utils.hideElement(imageFields);
        Utils.hideElement(pluginFieldsContainer);
        setContainerDisabled(indicatorFields, true);
        setContainerDisabled(questionFields, true);
        setContainerDisabled(documentFields, true);
        setContainerDisabled(matrixFields, true);
        setContainerDisabled(imageFields, true);
        setContainerDisabled(pluginFieldsContainer, true);

        if (itemType !== 'question') {
            try { QuestionItem.resetOptionsState(this.modalElement); } catch (e) {}
            try { QuestionItem.teardown(this.modalElement); } catch (e) {}
        }

        if (itemType !== 'image') {
            try { ImageItem.teardown(this.modalElement); } catch (e) {}
        }

        const pluginFields = document.getElementById('item-plugin-fields');
        if (pluginFields) {
            Utils.hideElement(pluginFields);
            setContainerDisabled(pluginFields, true);
        }

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
        if (imageFields) {
            imageFields.querySelectorAll('[required]').forEach(field => {
                field.removeAttribute('required');
            });
        }
        if (pluginFields) {
            pluginFields.querySelectorAll('[required]').forEach(field => {
                field.removeAttribute('required');
            });
        }

        if (itemType === 'indicator') {
            try { PluginItem.teardown(this.modalElement); } catch (e) {}
            Utils.showElement(indicatorFields);
            setContainerDisabled(indicatorFields, false);
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
            this.setupQuestionFields();
        } else if (itemType === 'document_field') {
            try { MatrixItem.teardown(this.modalElement); } catch (e) {}
            try { QuestionItem.teardown(this.modalElement); } catch (e) {}
            try { IndicatorItem.teardown(this.modalElement); } catch (e) {}
            try { PluginItem.teardown(this.modalElement); } catch (e) {}
            try { DocumentItem.teardown(this.modalElement); } catch (e) {}
            Utils.showElement(documentFields);
            setContainerDisabled(documentFields, false);
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
            if (matrixFields) {
                matrixFields.style.display = '';
                matrixFields.classList.remove('hidden');
            }
            const matrixLabel = matrixFields.querySelector('#item-matrix-label');
            if (matrixLabel) {
                matrixLabel.style.display = '';
                matrixLabel.tabIndex = 0;
            }

            this.setupMatrixFields();
            if (typeof window.attachMatrixColumnHeadersModalLazy === 'function') {
                window.attachMatrixColumnHeadersModalLazy();
            }
            if (typeof window.attachMatrixRowHeadersModalLazy === 'function') {
                window.attachMatrixRowHeadersModalLazy();
            }
        } else if (itemType === 'image') {
            try { MatrixItem.teardown(this.modalElement); } catch (e) {}
            try { QuestionItem.teardown(this.modalElement); } catch (e) {}
            try { IndicatorItem.teardown(this.modalElement); } catch (e) {}
            try { PluginItem.teardown(this.modalElement); } catch (e) {}
            try { ImageItem.teardown(this.modalElement); } catch (e) {}
            Utils.showElement(imageFields);
            setContainerDisabled(imageFields, false);
            this.setupImageFields();
        } else if (itemType.startsWith('plugin_')) {
            try { MatrixItem.teardown(this.modalElement); } catch (e) {}
            try { QuestionItem.teardown(this.modalElement); } catch (e) {}
            try { IndicatorItem.teardown(this.modalElement); } catch (e) {}
            Utils.showElement(pluginFieldsContainer);
            setContainerDisabled(pluginFieldsContainer, false);
            PluginItem.setup(this.modalElement, itemType, this.pendingPluginData);
            if (typeof window.attachPluginTranslationModalLazy === 'function') {
                window.attachPluginTranslationModalLazy();
            }
        }

        const validationRuleToggle = Utils.getElementById('validation-rule-toggle-section');
        const hideValidation = itemType === 'document_field'
            || this.isDisplayOnlyItemType(itemType, this.currentQuestionType);
        if (hideValidation) {
            Utils.hideElement(validationRuleToggle);
        } else {
            Utils.showElement(validationRuleToggle);
        }
    },

    setupImageFields: function() {
        ImageItem.setup(this.modalElement);
        this.updateItemTranslationTabLabels('image');
    },

    setupIndicatorFields: function() {
        IndicatorItem.setup(this.modalElement);
        this.updateItemTranslationTabLabels('indicator');
        this.setupAllowOver100Listener();
        setTimeout(() => this.ensureAllowOver100Field('indicator'), 100);
    },

    setupQuestionFields: function() {
        QuestionItem.setup(this.modalElement);
        const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
        this.updateQuestionFieldLabels(questionTypeSelect ? questionTypeSelect.value : '');
        this.setupAllowOver100Listener();
        setTimeout(() => this.ensureAllowOver100Field('question'), 100);
    },

    setupDocumentFields: function() {
        DocumentItem.setup(this.modalElement);
    },

    setupMatrixFields: function() {
        this.resetMatrixFieldsState();
        MatrixItem.setup(this.modalElement);
    },

    resetMatrixFieldsState: function() {
        if (!this.modalElement) return;

        const rowsContainer = this.modalElement.querySelector('#matrix-rows-container');
        const columnsContainer = this.modalElement.querySelector('#matrix-columns-container');
        const manualSection = this.modalElement.querySelector('#matrix-manual-rows-section');
        const listLibrarySection = this.modalElement.querySelector('#matrix-list-library-section');
        const manualModeRadio = this.modalElement.querySelector('input[name="matrix_row_mode"][value="manual"]');
        const listSelect = this.modalElement.querySelector('#matrix-list-select');
        const displayColumnWrapper = this.modalElement.querySelector('#matrix-display-column-wrapper');
        const displayColumnSelect = this.modalElement.querySelector('#matrix-list-display-column');
        const groupByWrapper = this.modalElement.querySelector('#matrix-group-by-wrapper');
        const groupBySelect = this.modalElement.querySelector('#matrix-group-by-column');
        const groupControlsWrapper = this.modalElement.querySelector('#matrix-group-controls-wrapper');
        const filtersContainer = this.modalElement.querySelector('#matrix-list-filters-container');
        const filtersInput = this.modalElement.querySelector('#matrix-list-filters-json');
        const pluginConfigContainer = this.modalElement.querySelector('#matrix-plugin-config-container');

        if (rowsContainer) rowsContainer.replaceChildren();
        if (columnsContainer) columnsContainer.replaceChildren();
        if (manualModeRadio) manualModeRadio.checked = true;
        if (manualSection) Utils.showElement(manualSection);
        if (listLibrarySection) Utils.hideElement(listLibrarySection);
        if (listSelect) listSelect.value = '';
        if (displayColumnWrapper) Utils.hideElement(displayColumnWrapper);
        if (displayColumnSelect) {
            displayColumnSelect.replaceChildren();
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select Column...';
            displayColumnSelect.appendChild(placeholder);
        }
        if (groupByWrapper) Utils.hideElement(groupByWrapper);
        if (groupBySelect) {
            groupBySelect.replaceChildren();
            const noGroup = document.createElement('option');
            noGroup.value = '';
            noGroup.textContent = 'No grouping';
            groupBySelect.appendChild(noGroup);
        }
        if (groupControlsWrapper) groupControlsWrapper.classList.add('hidden');
        if (filtersContainer) filtersContainer.replaceChildren();
        if (filtersInput) filtersInput.value = '[]';
        if (pluginConfigContainer) {
            pluginConfigContainer.replaceChildren();
            pluginConfigContainer.style.display = 'none';
        }
    },

    setupPluginFields: function(itemType) {
        PluginItem.setup(this.modalElement, itemType, this.pendingPluginData);
    },

    updateQuestionFieldLabels: function(questionType) {
        if (!this.modalElement) return;

        const isBlank = questionType === 'blank';
        const mode = isBlank ? 'blank' : 'default';

        const labelCaption = this.modalElement.querySelector('#item-question-label-caption');
        const descriptionLabel = this.modalElement.querySelector('#item-question-fields .item-show-description-label');
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
        applyCaption(descriptionLabel);
        applyPlaceholder(labelInput);
        applyPlaceholder(definitionInput);

        // Toggle rich-text editor for Blank/Note
        try {
            BlankBodyEditor.init(this.modalElement);
            if (isBlank) {
                BlankBodyEditor.show();
            } else {
                BlankBodyEditor.hide();
            }
        } catch (_e) {}

        // Toggle rich-text editors in the translation modal's definitions tab
        try {
            if (isBlank) {
                BlankTranslationEditor.enable();
                // Attach a one-time listener to the translations button so that
                // activate() runs after TranslationUtils.populateFields has already
                // populated the textareas (synchronous, fires before our callback).
                const translBtn = this.modalElement.querySelector('#question-translations-btn');
                if (translBtn && !translBtn._blankTransListenerAdded) {
                    translBtn.addEventListener('click', () => {
                        if (BlankTranslationEditor.enabled) {
                            // Use setTimeout(0) to run after the existing click handler
                            // (which calls populateFields) has completed.
                            setTimeout(() => BlankTranslationEditor.activate(), 0);
                        }
                    });
                    translBtn._blankTransListenerAdded = true;
                }
            } else {
                BlankTranslationEditor.disable();
            }
        } catch (_e) {}

        this.currentQuestionType = questionType || null;
        this.updateQuestionLabelRequired(questionType);
        this.updateItemTranslationTabLabels('question', questionType);
        this.ensureDisplayOnlyPropertyFields('question');
        if (questionType !== 'blank') {
            this.ensurePrivacyField();
        }
    },

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

    updateQuestionLabelRequired: function(questionType) {
        const questionLabel = Utils.getElementById('item-question-label');
        if (!questionLabel) return;

        if (questionType === 'blank') {
            questionLabel.removeAttribute('required');
        } else {
            questionLabel.setAttribute('required', 'required');
        }
    },

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
            case 'image':
                return 'fas fa-image w-6 h-6 mr-2 text-teal-600';
            default:
                return 'fas fa-plus-circle w-6 h-6 mr-2 text-gray-600';
        }
    },

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
            matrix: { wrapper: 'bg-amber-100 text-amber-600', icon: 'fas fa-table text-lg' },
            image: { wrapper: 'bg-teal-100 text-teal-600', icon: 'fas fa-image text-lg' }
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

    getQuestionTypeLabel: function(value) {
        if (!value) return 'Question';
        const choices = (DataManager && typeof DataManager.getData === 'function') ? (DataManager.getData('questionTypeChoices') || []) : [];
        const pair = Array.isArray(choices) && choices.find(c => c && c[0] === value);
        return pair && pair[1] ? String(pair[1]) : 'Question';
    },

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
            case 'image':
                return 'Image';
            default:
                return 'Item';
        }
    },

    updateSubmitButton: function(itemType) {
        const submitBtn = Utils.getElementById('item-modal-submit-btn');
        if (submitBtn) {
            const action = this.currentMode === 'add' ? 'Add' : 'Save';
            const typeName = this.getItemTypeName(itemType);
            submitBtn.textContent = `${action} ${typeName}`;
            submitBtn.disabled = false;
            submitBtn.removeAttribute('disabled');
            try { delete submitBtn.dataset.loadingApplied; } catch (_e) {}
        }
    },

    setupItemTypeToggle: function() {
        document.addEventListener('change', (e) => {
            if (!this.modalElement || !this.modalElement.contains(e.target)) return;
            if (e.target.name === 'item_type') {
                this.switchItemType(e.target.value);
            }
        });
    },
};
