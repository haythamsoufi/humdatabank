// Question item logic extracted from item-modal.js
// Depends on global Utils and uses DataManager, CalculatedLists, and template helpers if present

import { DataManager } from '../data-manager.js';
import { SelectHelper, RuleHelper } from './shared.js';
import { appendRuleToFormData } from '../form-serialization.js';

export const QuestionItem = {
    setup(modalElement) {
        this.populateTypeDropdown(modalElement);
        this.setupEventListeners(modalElement);
        // Initial label required state and options containers
        const typeSelect = modalElement.querySelector('#item-question-type-select');
        const currentType = typeSelect ? typeSelect.value : '';
        this.updateQuestionLabelRequired(modalElement, currentType);
        this.initializeOptionsVisibility(modalElement);
        this.updateIndirectReachVisibility(modalElement);
    },

    appendFields(formData, formPrefix, modalElement) {
        const labelInput = Utils.getElementById('item-question-label');
        const typeSelect = Utils.getElementById('item-question-type-select');
        const unitInput = Utils.getElementById('item-question-unit');
        const definitionInput = Utils.getElementById('item-question-definition');
        const optionsInput = Utils.getElementById('item-question-options-json');
        const relevanceRuleBuilder = Utils.getElementById('item-relevance-rule-builder');
        const validationRuleBuilder = Utils.getElementById('item-validation-rule-builder');
        const validationMessageInput = Utils.getElementById('item-validation-message');
        if (labelInput) formData.append(`${formPrefix}label`, labelInput.value);
        if (typeSelect) formData.append(`${formPrefix}question_type`, typeSelect.value);
        if (unitInput) formData.append(`${formPrefix}unit`, unitInput.value);
        if (definitionInput) formData.append(`${formPrefix}definition`, definitionInput.value);
        if (optionsInput) formData.append(`${formPrefix}options_json`, optionsInput.value);
        const sourceRadios = document.getElementsByName('options_source');
        let selectedSource = 'manual';
        sourceRadios.forEach(r => { if (r.checked) selectedSource = r.value; });
        formData.append(`${formPrefix}options_source`, selectedSource);
        if (selectedSource === 'calculated') {
            const listSelect = Utils.getElementById('item-calculated-list-select');
            const displayColSelect = Utils.getElementById('item-calculated-list-display-column');
            const filtersJsonInput = Utils.getElementById('item-calculated-list-filters-json');
            if (window.CalculatedLists && window.CalculatedLists.updateFiltersJson) window.CalculatedLists.updateFiltersJson();
            if (listSelect) formData.append(`${formPrefix}lookup_list_id`, listSelect.value);
            if (displayColSelect) formData.append(`${formPrefix}list_display_column`, displayColSelect.value);
            if (filtersJsonInput) formData.append(`${formPrefix}list_filters_json`, filtersJsonInput.value || '[]');
        }
        // Use centralized helper to avoid double-encoding and omit when empty
        appendRuleToFormData(formData, 'relevance_condition', relevanceRuleBuilder);
        appendRuleToFormData(formData, 'validation_condition', validationRuleBuilder);
        if (validationMessageInput) formData.append('validation_message', validationMessageInput.value);
        const translationsInput = Utils.getElementById('item-modal-translations');
        if (translationsInput) formData.append(`${formPrefix}label_translations`, translationsInput.value);
        const definitionTranslationsInput = Utils.getElementById('item-modal-definition-translations');
        if (definitionTranslationsInput) formData.append(`${formPrefix}definition_translations`, definitionTranslationsInput.value);
        const optionsTranslationsInput = Utils.getElementById('item-question-options-translations-json');
        if (optionsTranslationsInput) formData.append(`${formPrefix}options_translations_json`, optionsTranslationsInput.value);
    },

    teardown(modalElement) {
        if (!modalElement) return;
        if (modalElement._questionChangeHandler) {
            document.removeEventListener('change', modalElement._questionChangeHandler);
            modalElement._questionChangeHandler = null;
        }
        if (modalElement._questionInputHandler) {
            document.removeEventListener('input', modalElement._questionInputHandler);
            modalElement._questionInputHandler = null;
        }
    },

    populateTypeDropdown(modalElement) {
        const typeSelect = modalElement.querySelector('#item-question-type-select');
        if (!typeSelect) return;
        const types = DataManager.getData('questionTypeChoices');
        SelectHelper.populateSelect(typeSelect, types || []);
    },

    setupEventListeners(modalElement) {
        // Remove existing
        this.teardown(modalElement);

        modalElement._questionChangeHandler = (e) => {
            const id = e.target.id;
            if (id === 'item-question-type-select') {
                const optionsContainer = modalElement.querySelector('#item-question-options-container');
                const optionsInput = modalElement.querySelector('#item-question-options-json');
                if (typeof window.toggleOptionsInputVisibility === 'function') {
                    window.toggleOptionsInputVisibility(e.target.value, optionsContainer, optionsInput);
                }
                this.updateIndirectReachVisibility(modalElement);
                this.updateQuestionLabelRequired(modalElement, e.target.value);
            }

            if (e.target.name === 'options_source') {
                const source = e.target.value;
                const manualContainer = modalElement.querySelector('#item-question-options-container');
                const listContainer = modalElement.querySelector('#item-question-calculated-list-container');
                if (source === 'manual') {
                    Utils.showElement(manualContainer);
                    Utils.hideElement(listContainer);
                    Utils.hideElement(modalElement.querySelector('#item-calculated-display-column-wrapper'));
                } else {
                    Utils.hideElement(manualContainer);
                    Utils.showElement(listContainer);
                }
            }

            if (id === 'item-calculated-list-select') {
                if (window.CalculatedLists && window.CalculatedLists.handleListSelection) {
                    window.CalculatedLists.handleListSelection(e.target);
                }
            }
        };

        modalElement._questionInputHandler = (e) => {
            if (e.target.id === 'item-question-unit') {
                this.updateIndirectReachVisibility(modalElement);
            }
        };

        document.addEventListener('change', modalElement._questionChangeHandler);
        document.addEventListener('input', modalElement._questionInputHandler);
    },

    initializeOptionsVisibility(modalElement) {
        const typeSelect = modalElement.querySelector('#item-question-type-select');
        const currentType = typeSelect ? typeSelect.value : '';
        const manualContainer = modalElement.querySelector('#item-question-options-container');
        const listContainer = modalElement.querySelector('#item-question-calculated-list-container');
        const defaultSource = modalElement.querySelector('input[name="options_source"]:checked')?.value || 'manual';
        const isChoiceType = ['single_choice', 'multiple_choice'].includes(currentType);
        if (!isChoiceType) {
            Utils.hideElement(manualContainer);
            Utils.hideElement(listContainer);
        } else {
            if (defaultSource === 'manual') {
                Utils.showElement(manualContainer);
                Utils.hideElement(listContainer);
                Utils.hideElement(modalElement.querySelector('#item-calculated-display-column-wrapper'));
            } else {
                Utils.hideElement(manualContainer);
                Utils.showElement(listContainer);
            }
        }
    },

    toggleOptions(modalElement, questionType) {
        const optionsContainer = modalElement.querySelector('#item-question-options-container');
        if (!optionsContainer) return;
        const requiresOptions = ['single_choice', 'multiple_choice'].includes(questionType);
        if (requiresOptions) {
            Utils.showElement(optionsContainer);
        } else {
            Utils.hideElement(optionsContainer);
        }
    },

    toggleOptionsContainer(modalElement, questionType, showManual) {
        const manualContainer = modalElement.querySelector('#item-question-options-container');
        const listContainer = modalElement.querySelector('#item-question-calculated-list-container');
        const optionsSourceContainer = modalElement.querySelector('#options-source-container');
        if (!optionsSourceContainer) return;
        if (showManual) {
            Utils.showElement(manualContainer);
            Utils.hideElement(listContainer);
            Utils.hideElement(modalElement.querySelector('#item-calculated-display-column-wrapper'));
        } else {
            Utils.hideElement(manualContainer);
            Utils.showElement(listContainer);
        }
    },

    populateQuestionOptions(modalElement, itemData, optionsJsonInput) {
        let optionsData = [];
        if (itemData.options_json) {
            try {
                if (Array.isArray(itemData.options_json)) {
                    optionsData = itemData.options_json;
                } else if (typeof itemData.options_json === 'string') {
                    const trimmed = itemData.options_json.trim();
                    if (!trimmed || trimmed === '[]' || trimmed === 'null' || trimmed === 'undefined') {
                        optionsData = [];
                    } else if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
                        optionsData = JSON.parse(trimmed);
                    } else {
                        optionsData = [trimmed];
                    }
                }
            } catch (_) {
                optionsData = [];
            }
        }
        if (!Array.isArray(optionsData)) optionsData = [];
        if (optionsJsonInput) optionsJsonInput.value = JSON.stringify(optionsData);
        const optionsContainer = modalElement.querySelector('#item-question-options-container');
        const optionsList = modalElement.querySelector('#item-question-options-list');
        if (optionsContainer && optionsList) {
            optionsList.replaceChildren();
            if (optionsData.length > 0) {
                optionsData.forEach(option => { if (window.addOptionField) window.addOptionField(optionsList, option); });
            } else {
                if (window.addOptionField) window.addOptionField(optionsList, '');
            }
            if (window.updateOptionsJson) window.updateOptionsJson(optionsList);
            const questionTypeSelect = modalElement.querySelector('#item-question-type-select');
            if (questionTypeSelect && ['single_choice', 'multiple_choice'].includes(questionTypeSelect.value)) {
                Utils.showElement(optionsContainer);
            }
            setTimeout(() => window.ItemModal && window.ItemModal.checkModalScroll && window.ItemModal.checkModalScroll(), 100);
        }
    },

    populateOptionFields(modalElement, optionsData) {
        if (!modalElement) return;
        const optionsContainer = modalElement.querySelector('#item-question-options-container');
        const optionsList = modalElement.querySelector('#item-question-options-list');
        if (!optionsContainer || !optionsList) return;
        optionsList.replaceChildren();
        if (optionsData && optionsData.length > 0) {
            optionsData.forEach(option => {
                if (window.addOptionField) {
                    window.addOptionField(optionsList, option);
                }
            });
        } else {
            if (window.addOptionField) {
                window.addOptionField(optionsList, '');
            }
        }
        if (window.updateOptionsJson) {
            window.updateOptionsJson(optionsList);
        }
        const questionTypeSelect = modalElement.querySelector('#item-question-type-select');
        if (questionTypeSelect && ['single_choice', 'multiple_choice'].includes(questionTypeSelect.value)) {
            Utils.showElement(optionsContainer);
        }
    },

    updateIndirectReachVisibility(modalElement) {
        const indirectReachRow = modalElement.querySelector('#indirect-reach-row');
        if (!indirectReachRow) return;
        const typeSelect = modalElement.querySelector('#item-question-type-select');
        const unitInput = modalElement.querySelector('#item-question-unit');
        if (!typeSelect || !unitInput) return;
        const questionType = (typeSelect.value || '').toLowerCase();
        const unit = (unitInput.value || '').toLowerCase();
        const shouldShow = questionType === 'number' && ['volunteers', 'staff', 'people'].includes(unit);
        if (shouldShow) {
            Utils.showElement(indirectReachRow);
        } else {
            Utils.hideElement(indirectReachRow);
        }
    },

    updateQuestionLabelRequired(modalElement, questionType) {
        const questionLabel = modalElement.querySelector('#item-question-label');
        if (!questionLabel) return;
        if (questionType === 'blank') {
            questionLabel.removeAttribute('required');
        } else {
            questionLabel.setAttribute('required', 'required');
        }
    },

    populateForm(modalElement, itemData) {
        // Basic question fields
        const typeSelect = modalElement.querySelector('#item-question-type-select');
        const unitInput = modalElement.querySelector('#item-question-unit');
        const definitionInput = modalElement.querySelector('#item-question-definition');
        if (unitInput && itemData.unit) unitInput.value = itemData.unit;
        if (definitionInput && itemData.definition) definitionInput.value = itemData.definition;

        if (typeSelect && itemData.question_type) {
            const optionExists = Array.from(typeSelect.options).some(opt => opt.value === itemData.question_type);
            if (optionExists) {
                typeSelect.value = itemData.question_type;
                const questionTypeInput = modalElement.querySelector('#item-question-type-input');
                if (questionTypeInput) questionTypeInput.value = itemData.question_type;
                this.updateQuestionLabelRequired(modalElement, itemData.question_type);
                typeSelect.dispatchEvent(new Event('change'));
                if (typeof window.updateOptionsVisibility === 'function') {
                    window.updateOptionsVisibility();
                }
            }
        }

        const optionsSource = itemData.options_source;
        if (optionsSource === 'manual') {
            this.toggleOptionsContainer(modalElement, itemData.question_type, true);
            const manualRadio = modalElement.querySelector('input[name="options_source"][value="manual"]');
            if (manualRadio) {
                manualRadio.checked = true;
                manualRadio.dispatchEvent(new Event('change'));
            }
            let optionsData = itemData.options || itemData.options_json;
            if (typeof optionsData === 'string') {
                const trimmed = optionsData.trim();
                if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
                    try { optionsData = JSON.parse(trimmed); } catch (_) { optionsData = []; }
                } else if (trimmed) {
                    optionsData = [trimmed];
                } else {
                    optionsData = [];
                }
            }
            if (!Array.isArray(optionsData)) optionsData = [];
            const optionsJsonInput = modalElement.querySelector('#item-question-options-json');
            if (optionsJsonInput) optionsJsonInput.value = JSON.stringify(optionsData);
            this.populateOptionFields(modalElement, optionsData);
            setTimeout(() => {
                if (manualRadio) manualRadio.dispatchEvent(new Event('change', { bubbles: true }));
                if (typeSelect) typeSelect.dispatchEvent(new Event('change', { bubbles: true }));
            }, 100);
        } else if (optionsSource === 'calculated') {
            this.toggleOptionsContainer(modalElement, itemData.question_type, false);
            const calculatedRadio = modalElement.querySelector('input[name="options_source"][value="calculated"]');
            if (calculatedRadio) {
                calculatedRadio.checked = true;
                calculatedRadio.dispatchEvent(new Event('change'));
            }
            const listContainer = modalElement.querySelector('#item-question-calculated-list-container');
            Utils.showElement(listContainer);
            const calculatedListSelect = modalElement.querySelector('#item-calculated-list-select');
            if (calculatedListSelect && itemData.lookup_list_id) {
                // Check if the option exists before setting the value
                const optionExists = Array.from(calculatedListSelect.options).some(opt => opt.value === String(itemData.lookup_list_id));
                if (optionExists) {
                    calculatedListSelect.value = itemData.lookup_list_id;
                    // Directly call handleListSelection to ensure columns are populated
                    if (window.CalculatedLists && window.CalculatedLists.handleListSelection) {
                        window.CalculatedLists.handleListSelection(calculatedListSelect);
                    } else {
                        // Fallback: dispatch change event if handleListSelection is not available
                        calculatedListSelect.dispatchEvent(new Event('change'));
                    }
                } else {
                    console.warn('List option not found for lookup_list_id:', itemData.lookup_list_id);
                }
            }
            // Use a longer timeout to ensure handleListSelection has completed
            setTimeout(() => {
                const displayColSelect = modalElement.querySelector('#item-calculated-list-display-column');
                const displayColWrapper = modalElement.querySelector('#item-calculated-display-column-wrapper');
                if (displayColSelect && itemData.list_display_column) {
                    const optionExists = Array.from(displayColSelect.options).some(opt => opt.value === itemData.list_display_column);
                    if (!optionExists) {
                        // If option doesn't exist, try to get columns from the selected list option
                        let columnLabel = itemData.list_display_column;
                        const listSelect = modalElement.querySelector('#item-calculated-list-select');
                        if (listSelect && listSelect.selectedOptions && listSelect.selectedOptions[0]) {
                            try {
                                const columns = JSON.parse(listSelect.selectedOptions[0].dataset.columns || '[]');
                                const matchingColumn = columns.find(col => col.name === itemData.list_display_column);
                                if (matchingColumn && matchingColumn.label) {
                                    columnLabel = matchingColumn.label;
                                }
                            } catch (_) {}
                        }
                        // Add the missing option
                        const option = document.createElement('option');
                        option.value = itemData.list_display_column;
                        option.textContent = columnLabel;
                        displayColSelect.appendChild(option);
                    }
                    // Set the display column value
                    displayColSelect.value = itemData.list_display_column;
                    if (displayColWrapper) Utils.showElement(displayColWrapper);
                }
                // Populate filters after display column is set
                const filtersData = itemData.list_filters_json || itemData.filters_json;
                if (filtersData && window.CalculatedLists && window.CalculatedLists.populateFilters) {
                    window.CalculatedLists.populateFilters(filtersData);
                }
            }, 300);
        } else {
            const manualContainer = modalElement.querySelector('#item-question-options-container');
            const listContainer = modalElement.querySelector('#item-question-calculated-list-container');
            Utils.showElement(manualContainer);
            Utils.hideElement(listContainer);
        }

        this.updateIndirectReachVisibility(modalElement);
    }
};
