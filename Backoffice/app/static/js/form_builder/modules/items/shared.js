// Shared helpers for item modules

export const SelectHelper = {
    populateSelect(selectElement, options) {
        if (!selectElement || !options) return;
        const firstOption = selectElement.querySelector('option');
        selectElement.replaceChildren();
        if (firstOption) selectElement.appendChild(firstOption);
        options.forEach(option => {
            let value, label;
            if (Array.isArray(option) && option.length >= 2) {
                [value, label] = option;
            } else if (typeof option === 'object') {
                value = option.value;
                label = option.label;
            } else {
                value = option;
                label = option;
            }
            if (value === undefined || label === undefined) return;
            const optionElement = document.createElement('option');
            optionElement.value = value;
            optionElement.textContent = label;
            selectElement.appendChild(optionElement);
        });
    }
};

export const RuleHelper = {
    serialize(builderEl) {
        if (!builderEl) return {};
        try {
            return window.RuleBuilder ? window.RuleBuilder.serializeRuleBuilder(builderEl) : {};
        } catch (_) {
            return {};
        }
    }
};
