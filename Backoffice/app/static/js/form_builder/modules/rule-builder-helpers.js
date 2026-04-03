// Utilities to work with the rule builder DOM blocks used in the item modal
// Depends on RuleBuilder from conditions.js being globally available via import where used

import RuleBuilder from './conditions.js';

// Determine whether a rule payload has meaningful content
export function hasMeaningfulRuleData(ruleData) {
    if (!ruleData) {
        return false;
    }
    if (typeof ruleData === 'string') {
        try {
            let cleanData = ruleData;
            if (ruleData.includes('\"')) {
                cleanData = ruleData.replace(/\\"/g, '"');
            }
            const parsed = JSON.parse(cleanData);
            return Boolean(
                parsed && typeof parsed === 'object' &&
                Object.keys(parsed).length > 0 &&
                parsed.conditions && Array.isArray(parsed.conditions) &&
                parsed.conditions.length > 0
            );
        } catch (e) {
            return ruleData.includes('"conditions"') && ruleData.includes('"logic"');
        }
    }
    if (typeof ruleData === 'object') {
        return Boolean(
            ruleData && Object.keys(ruleData).length > 0 &&
            ruleData.conditions && Array.isArray(ruleData.conditions) &&
            ruleData.conditions.length > 0
        );
    }
    return false;
}

// Serialize a rule builder element into JSON using the shared RuleBuilder
export function serializeRule(builderElement) {
    return RuleBuilder.serializeRuleBuilder(builderElement);
}

// Attach rule data into a builder container (via data attribute) and optionally render
export function attachRuleData(builderElement, ruleData, kind) {
    if (!builderElement) return;
    builderElement.setAttribute('data-rule-json', ruleData || '');
    if (builderElement.innerHTML.trim() === '') {
        try {
            RuleBuilder.renderRuleBuilder(builderElement, ruleData, kind);
        } catch (e) {
            // ignore rendering failures; UI code can retry later
        }
    }
}
