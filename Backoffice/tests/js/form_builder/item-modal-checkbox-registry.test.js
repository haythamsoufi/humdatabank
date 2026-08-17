/**
 * Guardrail: every Category-B (preserve-existing) checkbox must appear in
 * CONFIG_CHECKBOXES so the frontend always sends explicit true/false.
 *
 * Parses _item_modal.html from disk (same approach as the Python guardrail).
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import {
    CONFIG_CHECKBOXES,
} from '../../../app/static/js/form_builder/modules/modal/config-checkbox-serializer.js';

const backofficeRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const itemModalPath = path.join(
    backofficeRoot,
    'app/templates/forms/form_builder/partials/_item_modal.html',
);

const PROPERTIES_START = 'id="item-properties-section"';
const PROPERTIES_END = 'class="item-modal-actions';

/** Category-B keys that must be serialized via CONFIG_CHECKBOXES. */
const PRESERVE_EXISTING_KEYS = new Set([
    'allow_over_100',
    'exclude_from_completion_rate',
    'unique_options_in_section',
    'limit_entries_to_option_count',
    'use_as_repeat_entry_title',
    'allow_other',
]);

/** Map checkbox name → expected CSS selector id in the modal. */
const NAME_TO_SELECTOR_ID = {
    allow_over_100: 'item-allow-over-100',
    exclude_from_completion_rate: 'item-exclude-from-completion-rate',
    unique_options_in_section: 'item-unique-options-in-section',
    limit_entries_to_option_count: 'item-limit-entries-to-option-count',
    use_as_repeat_entry_title: 'item-use-as-repeat-entry-title',
    allow_other: 'item-question-allow-other',
};

function extractPropertiesSection(html) {
    const start = html.indexOf(PROPERTIES_START);
    expect(start).toBeGreaterThanOrEqual(0);
    const end = html.indexOf(PROPERTIES_END, start);
    expect(end).toBeGreaterThan(start);
    return html.slice(start, end);
}

function checkboxNamesInPropertiesSection(html) {
    const section = extractPropertiesSection(html);
    const names = new Set();
    const tagRe = /<input[^>]*type=["']checkbox["'][^>]*>/gi;
    let match;
    while ((match = tagRe.exec(section)) !== null) {
        const nameMatch = match[0].match(/\bname=["']([^"']+)["']/i);
        if (nameMatch) {
            names.add(nameMatch[1]);
        }
    }
    return names;
}

describe('item modal checkbox registry guardrail', () => {
    const html = readFileSync(itemModalPath, 'utf-8');
    const registryKeys = new Set(CONFIG_CHECKBOXES.map((entry) => entry.key));
    const registrySelectors = new Set(CONFIG_CHECKBOXES.map((entry) => entry.selector));

    it('CONFIG_CHECKBOXES covers every Category-B key', () => {
        for (const key of PRESERVE_EXISTING_KEYS) {
            expect(registryKeys.has(key)).toBe(true);
        }
        expect(registryKeys.size).toBe(PRESERVE_EXISTING_KEYS.size);
    });

    it('each CONFIG_CHECKBOXES entry points at the expected modal element id', () => {
        CONFIG_CHECKBOXES.forEach(({ selector, key }) => {
            const expectedId = NAME_TO_SELECTOR_ID[key];
            expect(expectedId).toBeDefined();
            expect(selector).toBe(`#${expectedId}`);
            if (key === 'allow_over_100') {
                // Injected at runtime by properties.js, not in the static template.
                return;
            }
            expect(html).toContain(`id="${expectedId}"`);
        });
    });

    it('properties-panel Category-B checkboxes are all in CONFIG_CHECKBOXES', () => {
        const propertiesNames = checkboxNamesInPropertiesSection(html);
        const categoryBInProperties = [...PRESERVE_EXISTING_KEYS].filter((key) =>
            propertiesNames.has(key),
        );
        categoryBInProperties.forEach((key) => {
            expect(registryKeys.has(key)).toBe(true);
        });
    });

    it('allow_other is serialized even though it lives in question fields, not properties', () => {
        expect(html).toContain('id="item-question-allow-other"');
        expect(registrySelectors.has('#item-question-allow-other')).toBe(true);
    });

    it('allow_over_100 is serialized even though the checkbox is JS-injected', () => {
        expect(registrySelectors.has('#item-allow-over-100')).toBe(true);
    });
});
