import { hasMeaningfulRuleData, attachRuleData } from '../rules/rule-builder-helpers.js';

export const RuleUIMixin = {
    cacheRuleToggleDefaults: function() {
        const modal = Utils.getElementById('item-modal');
        if (!modal) return;
        modal.querySelectorAll('.toggle-rule-builder').forEach((button) => {
            if (!button.dataset.addLabel) {
                button.dataset.addLabel = String(button.textContent || '').trim();
            }
            if (!button.dataset.hideLabel) {
                const replaced = button.dataset.addLabel.replace(/\bAdd\b/, 'Hide');
                button.dataset.hideLabel = replaced !== button.dataset.addLabel ? replaced : button.dataset.addLabel;
            }
        });
    },

    syncRightPanel: function() {
        if (!this.modalElement) return;
        const rightHalf = this.modalElement.querySelector('.modal-right-half');
        const gridContainer = this.modalElement.querySelector('.modal-grid-container');
        const modalContent = this.getModalPanel
            ? this.getModalPanel()
            : this.modalElement.querySelector('.item-modal-panel') || this.modalElement.querySelector('.relative.p-6');
        if (!rightHalf || !gridContainer || !modalContent) return;

        const hasVisible = Array.from(rightHalf.children).some((ch) =>
            !ch.classList.contains('hidden') && ch.style.display !== 'none'
        );
        const fillMode = typeof this.isFillContentMode === 'function' && this.isFillContentMode();

        if (hasVisible) {
            Utils.showElement(rightHalf);
            gridContainer.classList.add('md:grid-cols-2');
            gridContainer.classList.remove('grid-cols-1');
            if (!fillMode) {
                modalContent.classList.remove('max-w-xl', 'max-w-lg', 'max-w-4xl');
                modalContent.classList.add('max-w-6xl');
            }
        } else {
            Utils.hideElement(rightHalf);
            gridContainer.classList.remove('md:grid-cols-2');
            gridContainer.classList.add('grid-cols-1');
            if (!fillMode) {
                modalContent.classList.remove('max-w-6xl', 'max-w-4xl', 'max-w-lg');
                modalContent.classList.add('max-w-xl');
            }
        }

        if (!this._scrollRafQueued) {
            this._scrollRafQueued = true;
            requestAnimationFrame(() => {
                this._scrollRafQueued = false;
                this.checkModalScroll();
            });
        }
    },

    renderRuleToggleButton: function(button, state /* 'add' | 'hide' */) {
        if (!button) return;
        if (!button.dataset.addLabel) {
            button.dataset.addLabel = String(button.textContent || '').trim();
        }
        if (!button.dataset.hideLabel) {
            const replaced = button.dataset.addLabel.replace(/\bAdd\b/, 'Hide');
            button.dataset.hideLabel = replaced !== button.dataset.addLabel ? replaced : button.dataset.addLabel;
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

    resetRuleUIState: function() {
        if (!this.modalElement) return;

        const rightHalf = this.modalElement.querySelector('.modal-right-half');
        const gridContainer = this.modalElement.querySelector('.modal-grid-container');
        const modalContent = this.getModalPanel
            ? this.getModalPanel()
            : this.modalElement.querySelector('.item-modal-panel') || this.modalElement.querySelector('.relative.p-6');

        const relevanceSection = this.modalElement.querySelector('#item-relevance-rule-section');
        const validationSection = this.modalElement.querySelector('#item-validation-rule-section');
        const relevanceBuilder = this.modalElement.querySelector('#item-relevance-rule-builder');
        const validationBuilder = this.modalElement.querySelector('#item-validation-rule-builder');

        // Hide sections and right pane (full Utils hide clears inline display + disable markers)
        if (relevanceSection) Utils.hideElement(relevanceSection);
        if (validationSection) Utils.hideElement(validationSection);
        if (rightHalf) Utils.hideElement(rightHalf);

        // Reset layout
        if (gridContainer) {
            gridContainer.classList.remove('md:grid-cols-2');
            gridContainer.classList.add('grid-cols-1');
        }
        if (modalContent && !(typeof this.isFillContentMode === 'function' && this.isFillContentMode())) {
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

    autoShowRuleSections: function(itemData) {
        // Add null check to prevent errors
        if (!this.modalElement) {

            return;
        }

        const relevanceBuilderEl = this.modalElement.querySelector('#item-relevance-rule-builder');
        const validationRuleBuilder = this.modalElement.querySelector('#item-validation-rule-builder');
        const relevanceSection = this.modalElement.querySelector('#item-relevance-rule-section');
        const validationSection = this.modalElement.querySelector('#item-validation-rule-section');

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

        } else {

            if (relevanceSection) {
                Utils.hideElement(relevanceSection);
            }
            const relevanceButton = this.modalElement.querySelector('[data-target="#item-relevance-rule-section"]');
            if (relevanceButton) {
                this.renderRuleToggleButton(relevanceButton, 'add');
            }
        }

        // Handle validation rules (skipped for display-only items)
        const isDisplayOnly = this.isDisplayOnlyItemType && this.isDisplayOnlyItemType(
            this.currentItemType,
            this.currentQuestionType || (this.modalElement?.querySelector('#item-question-type-select')?.value)
        );

        if (isDisplayOnly) {
            if (validationSection) Utils.hideElement(validationSection);
            if (validationRuleBuilder) {
                validationRuleBuilder.removeAttribute('data-rule-json');
                validationRuleBuilder.replaceChildren();
            }
            const validationButton = this.modalElement.querySelector('[data-target="#item-validation-rule-section"]');
            if (validationButton && typeof this.renderRuleToggleButton === 'function') {
                this.renderRuleToggleButton(validationButton, 'add');
            }
        } else if (validationRuleBuilder && hasRuleData(itemData.validation_condition)) {


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

        } else {

            if (validationSection) {
                Utils.hideElement(validationSection);
            }
            const validationButton = this.modalElement.querySelector('[data-target="#item-validation-rule-section"]');
            if (validationButton) {
                this.renderRuleToggleButton(validationButton, 'add');
            }
        }

        this.syncRightPanel();
    },
};
