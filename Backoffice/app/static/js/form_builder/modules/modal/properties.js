import { DataManager } from '../data-manager.js';

export const PropertiesMixin = {
    _isPercentageCache: null,

    isDisplayOnlyItemType: function(itemType, questionType) {
        if (itemType === 'image') return true;
        if (itemType !== 'question') return false;
        const qt = questionType !== undefined && questionType !== null
            ? questionType
            : (this.currentQuestionType || '');
        const resolved = qt || (this.modalElement?.querySelector('#item-question-type-select')?.value) || '';
        return resolved === 'blank';
    },

    ensureDisplayOnlyPropertyFields: function(itemType) {
        if (!this.modalElement) return;
        const hide = this.isDisplayOnlyItemType(itemType, this.currentQuestionType);

        const privacyField = this.modalElement.querySelector('#item-privacy-field');
        const requiredRow = this.modalElement.querySelector('#item-required')?.closest('.item-properties-cell');
        const dnaRow = this.modalElement.querySelector('#item-allow-data-not-available')?.closest('.item-properties-cell');
        const naRow = this.modalElement.querySelector('#item-allow-not-applicable')?.closest('.item-properties-cell');
        const carryForwardRow = this.modalElement.querySelector('#item-carry-forward-row');

        [privacyField, requiredRow, dnaRow, naRow, carryForwardRow].forEach((el) => {
            if (!el) return;
            el.style.display = hide ? 'none' : '';
        });

        const requiredCheckbox = this.modalElement.querySelector('#item-required');
        const dnaCheckbox = this.modalElement.querySelector('#item-allow-data-not-available');
        const naCheckbox = this.modalElement.querySelector('#item-allow-not-applicable');
        const privacySelect = this.modalElement.querySelector('#item-privacy-select');
        const carryForwardCheckbox = this.modalElement.querySelector('#item-carry-forward');

        [requiredCheckbox, dnaCheckbox, naCheckbox, carryForwardCheckbox].forEach((el) => {
            if (!el) return;
            if (hide) {
                el.checked = false;
                el.disabled = true;
            } else {
                el.disabled = false;
            }
        });

        if (privacySelect) {
            if (hide) {
                privacySelect.disabled = true;
            } else {
                privacySelect.disabled = false;
            }
        }

        const validationRuleToggle = this.modalElement.querySelector('#validation-rule-toggle-section');
        const validationSection = this.modalElement.querySelector('#item-validation-rule-section');
        const validationBuilder = this.modalElement.querySelector('#item-validation-rule-builder');
        const validationConditionInput = this.modalElement.querySelector('#item-validation-condition');
        const validationMessageInput = this.modalElement.querySelector('#item-validation-message');

        if (validationRuleToggle) {
            validationRuleToggle.style.display = hide ? 'none' : '';
        }

        if (hide) {
            if (validationSection) Utils.hideElement(validationSection);
            if (validationBuilder) {
                validationBuilder.removeAttribute('data-rule-json');
                validationBuilder.replaceChildren();
            }
            if (validationConditionInput) validationConditionInput.value = '';
            if (validationMessageInput) validationMessageInput.value = '';
            const validationButton = this.modalElement.querySelector('[data-target="#item-validation-rule-section"]');
            if (validationButton && typeof this.renderRuleToggleButton === 'function') {
                this.renderRuleToggleButton(validationButton, 'add');
            }
            try { this.syncRightPanel && this.syncRightPanel(); } catch (_e) {}
        }

        try { this.enforceHiddenControlsDisabled(this.modalElement); } catch (_e) {}
    },

    ensureMatrixDisplayProperties: function(itemType) {
        if (!this.modalElement) return;
        const block = this.modalElement.querySelector('#item-properties-matrix-display');
        if (!block) return;
        block.classList.toggle('hidden', itemType !== 'matrix');
    },

    ensurePrivacyField: function() {
        if (!this.modalElement) return;
        if (this.isDisplayOnlyItemType(this.currentItemType, this.currentQuestionType)) return;
        const propertiesSection = this.modalElement.querySelector('#item-properties-section') || this.modalElement.querySelector('.mb-3.border-t.border-gray-200.pt-4');
        if (!propertiesSection) return;
        const slot = propertiesSection.querySelector('#item-privacy-field');
        if (!slot) return;
        // Avoid duplicates
        if (slot.querySelector('#item-privacy-select')) {
            return;
        }
        const label = document.createElement('label');
        label.className = 'shrink-0 w-20 text-sm font-semibold text-gray-700';
        label.setAttribute('for', 'item-privacy-select');
        label.textContent = 'Privacy';
        const select = document.createElement('select');
        select.name = 'privacy';
        select.id = 'item-privacy-select';
        select.className = 'flex-1 min-w-0 py-1.5 shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm border-gray-300 rounded-md';
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
        slot.appendChild(label);
        slot.appendChild(select);
    },

    ensureAllowOver100Field: function(itemType) {
        if (!this.modalElement) {
            return;
        }
        const propertiesSection = this.modalElement.querySelector('#item-properties-section') || this.modalElement.querySelector('.mb-3.border-t.border-gray-200.pt-4');
        if (!propertiesSection) {
            return;
        }
        const propertiesContent = propertiesSection.querySelector('#item-properties-content') || propertiesSection.querySelector('.grid.grid-cols-2.gap-6.items-center');
        if (!propertiesContent) {
            return;
        }

        // Check if this is a percentage item
        const isPercentage = this.isPercentageItem(itemType);

        // Get existing checkbox and preserve its checked state if present
        const existingCheckbox = propertiesContent.querySelector('#item-allow-over-100');
        let preservedCheckedState = false;
        if (existingCheckbox) {
            preservedCheckedState = existingCheckbox.checked;
            existingCheckbox.closest('.item-properties-cell')?.remove();
        }

        // Only add checkbox for percentage items
        if (!isPercentage) {
            return;
        }

        if (this._pendingAllowOver100Value !== undefined) {
            preservedCheckedState = this._pendingAllowOver100Value;
            this._pendingAllowOver100Value = undefined;
        }

        // Build field container
        const container = document.createElement('div');
        container.className = 'item-properties-cell min-h-[1.5rem] flex items-center';

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

    isChoiceQuestionType: function(questionType) {
        return ['single_choice', 'multiple_choice'].includes(questionType || '');
    },

    ensureUniqueOptionsInSectionField: function(itemType) {
        if (!this.modalElement) return;
        const row = this.modalElement.querySelector('#unique-options-in-section-row');
        const checkbox = this.modalElement.querySelector('#item-unique-options-in-section');
        if (!row || !checkbox) return;

        let questionType = '';
        if (itemType === 'question') {
            const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
            questionType = (questionTypeSelect && questionTypeSelect.value) || this.currentQuestionType || '';
        }

        const show = itemType === 'question' && this.isChoiceQuestionType(questionType);
        row.style.display = show ? '' : 'none';
        if (!show) {
            checkbox.checked = false;
            checkbox.disabled = true;
        } else {
            checkbox.disabled = false;
            if (this._pendingUniqueOptionsInSection !== undefined) {
                checkbox.checked = !!this._pendingUniqueOptionsInSection;
                this._pendingUniqueOptionsInSection = undefined;
            }
        }

        // Wire up change listener once so toggling unique_options re-evaluates the sub-option
        if (!checkbox._limitEntriesChangeListenerAdded) {
            checkbox.addEventListener('change', () => {
                this.ensureLimitEntriesToOptionCountField('question');
            });
            checkbox._limitEntriesChangeListenerAdded = true;
        }

        this.ensureLimitEntriesToOptionCountField(itemType);
    },

    ensureLimitEntriesToOptionCountField: function(itemType) {
        if (!this.modalElement) return;
        const row = this.modalElement.querySelector('#limit-entries-to-option-count-row');
        const checkbox = this.modalElement.querySelector('#item-limit-entries-to-option-count');
        const uniqueCheckbox = this.modalElement.querySelector('#item-unique-options-in-section');
        if (!row || !checkbox || !uniqueCheckbox) return;

        let questionType = '';
        if (itemType === 'question') {
            const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
            questionType = (questionTypeSelect && questionTypeSelect.value) || this.currentQuestionType || '';
        }

        // Show only for single_choice in a repeat section when unique_options_in_section is enabled
        const show = itemType === 'question'
            && questionType === 'single_choice'
            && this.isRepeatSection(this.getActiveSectionId())
            && uniqueCheckbox.checked;

        row.style.display = show ? '' : 'none';
        if (!show) {
            checkbox.checked = false;
            checkbox.disabled = true;
        } else {
            checkbox.disabled = false;
            if (this._pendingLimitEntriesToOptionCount !== undefined) {
                checkbox.checked = !!this._pendingLimitEntriesToOptionCount;
                this._pendingLimitEntriesToOptionCount = undefined;
            }
        }

        // Wire up change listener once so toggling limit_entries re-evaluates the max_other sub-row
        if (!checkbox._maxOtherChangeListenerAdded) {
            checkbox.addEventListener('change', () => this.ensureMaxOtherEntriesField());
            checkbox._maxOtherChangeListenerAdded = true;
        }
        this.ensureMaxOtherEntriesField();
    },

    ensureMaxOtherEntriesField: function() {
        if (!this.modalElement) return;
        const row = this.modalElement.querySelector('#max-other-entries-row');
        const input = this.modalElement.querySelector('#item-max-other-entries');
        const limitCheckbox = this.modalElement.querySelector('#item-limit-entries-to-option-count');
        const allowOtherCheckbox = this.modalElement.querySelector('#item-question-allow-other');
        if (!row || !input || !limitCheckbox || !allowOtherCheckbox) return;

        const show = limitCheckbox.checked && allowOtherCheckbox.checked;
        row.style.display = show ? '' : 'none';
        if (!show) {
            // Reset to default when hidden so stale values don't persist
            input.value = '1';
        } else if (this._pendingMaxOtherEntries !== undefined) {
            input.value = String(this._pendingMaxOtherEntries);
            this._pendingMaxOtherEntries = undefined;
        }

        // Wire the allow_other checkbox change listener once (only when this field is relevant)
        if (!allowOtherCheckbox._maxOtherChangeListenerAdded) {
            allowOtherCheckbox.addEventListener('change', () => this.ensureMaxOtherEntriesField());
            allowOtherCheckbox._maxOtherChangeListenerAdded = true;
        }
    },

    ensureUseAsRepeatEntryTitleField: function(itemType) {
        if (!this.modalElement) return;
        const row = this.modalElement.querySelector('#use-as-repeat-entry-title-row');
        const checkbox = this.modalElement.querySelector('#item-use-as-repeat-entry-title');
        if (!row || !checkbox) return;

        let questionType = '';
        if (itemType === 'question') {
            const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
            questionType = (questionTypeSelect && questionTypeSelect.value) || this.currentQuestionType || '';
        }

        const show = itemType === 'question'
            && questionType === 'single_choice'
            && this.isRepeatSection(this.getActiveSectionId());
        row.style.display = show ? '' : 'none';
        if (!show) {
            checkbox.checked = false;
            checkbox.disabled = true;
        } else {
            checkbox.disabled = false;
            if (this._pendingUseAsRepeatEntryTitle !== undefined) {
                checkbox.checked = !!this._pendingUseAsRepeatEntryTitle;
                this._pendingUseAsRepeatEntryTitle = undefined;
            }
        }
    },

    isPercentageItem: function(itemType) {
        if (this._isPercentageCache !== null && this._isPercentageCache.itemType === itemType) {
            return this._isPercentageCache.result;
        }
        const result = this._computeIsPercentageItem(itemType);
        this._isPercentageCache = { itemType, result };
        return result;
    },

    invalidateIsPercentageCache: function() {
        this._isPercentageCache = null;
    },

    _computeIsPercentageItem: function(itemType) {
        if (itemType === 'question') {
            const questionTypeSelect = this.modalElement.querySelector('#item-question-type-select');
            const unitInput = this.modalElement.querySelector('#item-question-unit');
            if (questionTypeSelect && questionTypeSelect.value === 'percentage') {
                return true;
            }
            if (unitInput && unitInput.value && unitInput.value.toLowerCase().includes('percentage')) {
                return true;
            }
        } else if (itemType === 'indicator') {
            const indicatorTypeSelect = this.modalElement.querySelector('#item-indicator-type-select');
            const indicatorUnitSelect = this.modalElement.querySelector('#item-indicator-unit-select');
            const bankSelect = this.modalElement.querySelector('#item-indicator-bank-select');

            // Check type/unit selects
            if (indicatorTypeSelect && indicatorTypeSelect.value &&
                indicatorTypeSelect.value.toLowerCase().includes('percentage')) {
                return true;
            }
            if (indicatorUnitSelect && indicatorUnitSelect.value &&
                indicatorUnitSelect.value.toLowerCase().includes('percentage')) {
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
                        if (indicatorType.includes('percentage') || indicatorUnit.includes('percentage')) {
                            return true;
                        }
                    }
                }
            }
        }
        return false;
    },

    setupAllowOver100Listener: function() {
        if (!this.modalElement) return;

        // Remove existing listener if any
        if (this._allowOver100Handler) {
            this.modalElement.removeEventListener('change', this._allowOver100Handler);
        }

        // Create new handler
        this._allowOver100Handler = (e) => {
            const targetId = e.target.id;
            if (targetId === 'item-indicator-bank-select' ||
                targetId === 'item-indicator-type-select' ||
                targetId === 'item-indicator-unit-select' ||
                targetId === 'item-question-type-select' ||
                targetId === 'item-question-unit') {
                if (targetId === 'item-question-type-select') {
                    this.updateQuestionFieldLabels(e.target.value);
                }
                this.invalidateIsPercentageCache();
                this.ensureAllowOver100Field(this.currentItemType);
            }
        };

        this.modalElement.addEventListener('change', this._allowOver100Handler);
    },
};
