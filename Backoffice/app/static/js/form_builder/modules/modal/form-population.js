import { attachRuleData } from '../rules/rule-builder-helpers.js';
import { MatrixItem } from '../items/matrix.js';
import { QuestionItem } from '../items/question.js';
import { IndicatorItem } from '../items/indicator.js';
import { DocumentItem } from '../items/document.js';

function parseBool(val) {
    return val === true || val === 'true' || val === 1 || val === '1';
}

export const FormPopulationMixin = {
    populateForm: function(itemData) {
        if (this.currentItemType.startsWith('plugin_')) {
            this.pendingPluginData = itemData;
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

    populateIndicatorForm: function(itemData) {
        IndicatorItem.populateForm(this.modalElement, itemData);
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

    populateQuestionForm: function(itemData) {
        const sharedLabel = document.querySelector(this.sharedFields.label);
        if (sharedLabel) {
            sharedLabel.value = itemData.label || '';
        }
        this.syncSharedToUI();
        QuestionItem.populateForm(this.modalElement, itemData);
        const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
        this.updateQuestionFieldLabels(questionTypeSelect ? questionTypeSelect.value : (itemData.question_type || ''));
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

    populateDocumentForm: function(itemData) {
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

        this.syncSharedToUI();
        this.populateCommonFields(itemData);

        setTimeout(() => {
            DocumentItem.populateForm(this.modalElement, itemData);
        }, 50);

        const relevanceBuilderElDoc = this.modalElement.querySelector('#item-relevance-rule-builder');
        if (relevanceBuilderElDoc) {
            attachRuleData(relevanceBuilderElDoc, itemData.relevance_condition, 'relevance');
        }
        const validationBuilderElDoc = this.modalElement.querySelector('#item-validation-rule-builder');
        if (validationBuilderElDoc) {
            attachRuleData(validationBuilderElDoc, itemData.validation_condition, 'validation');
        }
        const validationMsgInputDoc = this.modalElement.querySelector('#item-validation-message');
        if (validationMsgInputDoc) {
            validationMsgInputDoc.value = itemData.validation_message || '';
        }

        this.autoShowRuleSections(itemData);
    },

    populateMatrixForm: function(itemData) {
        setTimeout(() => {
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

            const descriptionTranslations = itemData.definition_translations || itemData.description_translations;
            if (sharedDescriptionTranslations && descriptionTranslations) {
                sharedDescriptionTranslations.value = JSON.stringify(descriptionTranslations);
            }

            this.syncSharedToUI();
            this.populateMatrixFieldsAfterDelay(itemData);
        }, 150);
    },

    populateMatrixFieldsAfterDelay: function(itemData) {
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
        const labelInput = document.getElementById('item-plugin-label');
        const descriptionInput = document.getElementById('item-plugin-description');

        if (labelInput && itemData.label) {
            labelInput.value = itemData.label;
        }

        if (descriptionInput && itemData.description) {
            descriptionInput.value = itemData.description;
        }

        const labelTranslationsInput = document.getElementById('item-plugin-label-translations');
        const descriptionTranslationsInput = document.getElementById('item-plugin-description-translations');

        if (labelTranslationsInput && itemData.label_translations) {
            labelTranslationsInput.value = JSON.stringify(itemData.label_translations);
        }

        if (descriptionTranslationsInput && itemData.description_translations) {
            descriptionTranslationsInput.value = JSON.stringify(itemData.description_translations);
        }

        this.populateCommonFields(itemData);
    },

    populateCommonFields: function(itemData) {
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
            requiredCheckbox.checked = parseBool(itemData.is_required);
        }

        if (orderInput && itemData.order) {
            orderInput.value = itemData.order;
        }

        if (dataNotAvailableCheckbox) {
            dataNotAvailableCheckbox.checked = parseBool(itemData.allow_data_not_available);
        }

        if (notApplicableCheckbox) {
            notApplicableCheckbox.checked = parseBool(itemData.allow_not_applicable);
        }

        const uniqueOptionsCheckbox = this.modalElement.querySelector('#item-unique-options-in-section');
        if (uniqueOptionsCheckbox) {
            const uniqueVal = (itemData && itemData.config && itemData.config.unique_options_in_section !== undefined)
                ? parseBool(itemData.config.unique_options_in_section)
                : false;
            this._pendingUniqueOptionsInSection = uniqueVal;
            uniqueOptionsCheckbox.checked = uniqueVal;
        }

        const repeatTitleCheckbox = this.modalElement.querySelector('#item-use-as-repeat-entry-title');
        if (repeatTitleCheckbox) {
            const repeatTitleVal = (itemData && itemData.config && itemData.config.use_as_repeat_entry_title !== undefined)
                ? parseBool(itemData.config.use_as_repeat_entry_title)
                : false;
            this._pendingUseAsRepeatEntryTitle = repeatTitleVal;
            repeatTitleCheckbox.checked = repeatTitleVal;
        }

        const limitEntriesCheckbox = this.modalElement.querySelector('#item-limit-entries-to-option-count');
        if (limitEntriesCheckbox) {
            const limitVal = (itemData && itemData.config && itemData.config.limit_entries_to_option_count !== undefined)
                ? parseBool(itemData.config.limit_entries_to_option_count)
                : false;
            this._pendingLimitEntriesToOptionCount = limitVal;
            limitEntriesCheckbox.checked = limitVal;
        }

        if (disabilityQuestionsCheckbox) {
            disabilityQuestionsCheckbox.checked = parseBool(itemData.allow_disability_questions);
        }

        if (indirectReachCheckbox) {
            indirectReachCheckbox.checked = parseBool(itemData.indirect_reach);
        }

        if (layoutWidthSelect && itemData.layout_column_width) {
            layoutWidthSelect.value = itemData.layout_column_width;
        }

        if (breakAfterCheckbox) {
            breakAfterCheckbox.checked = parseBool(itemData.layout_break_after);
        }

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
            if (typeof privacyValue === 'string') {
                const v = privacyValue.trim().toLowerCase();
                if (v === 'public') {
                    privacyValue = 'public';
                } else if (v === 'ifrc network' || v === 'ifrc_network' || v === 'ifrc' || v === 'network') {
                    privacyValue = 'ifrc_network';
                } else {
                    privacyValue = 'ifrc_network';
                }
            } else {
                privacyValue = 'ifrc_network';
            }
            privacySelect.value = privacyValue;
        }

        const allowOver100 = (itemData && itemData.config && itemData.config.allow_over_100 !== undefined)
            ? parseBool(itemData.config.allow_over_100)
            : false;

        let allowOver100Checkbox = this.modalElement.querySelector('#item-allow-over-100');

        if (!allowOver100Checkbox) {
            this._pendingAllowOver100Value = allowOver100;
            this.ensureAllowOver100Field(this.currentItemType);
            allowOver100Checkbox = this.modalElement.querySelector('#item-allow-over-100');
        }

        if (allowOver100Checkbox) {
            allowOver100Checkbox.checked = allowOver100;
        }

        const sectionIdInput = this.modalElement.querySelector('#item-modal-section-id');
        const itemIdInput = this.modalElement.querySelector('#item-modal-id');
        const sectionSelect = this.modalElement.querySelector('#item-section-select');

        const sectionId = itemData.section_id || this.currentSectionId;
        if (sectionIdInput && sectionId) {
            sectionIdInput.value = sectionId;
        }

        if (sectionSelect && sectionId) {
            sectionSelect.value = sectionId;
        }

        if (itemIdInput && itemData.id) {
            itemIdInput.value = itemData.id;
        }

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
};
