/**
 * Disaggregation checkboxes in the form-builder item modal should default to
 * all selected when an indicator is chosen, and keep ticks only when the same
 * indicator is re-rendered.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import '../../../app/static/js/form_builder/modules/utils.js';
import { DataManager } from '../../../app/static/js/form_builder/modules/data-manager.js';
import { IndicatorItem } from '../../../app/static/js/form_builder/modules/items/indicator.js';

const DISAGG_CHOICES = [
    ['total', 'Total Only'],
    ['sex', 'By Sex'],
    ['age', 'By Age'],
    ['sex_age', 'By Sex and Age'],
];

function mountModalDom() {
    document.body.innerHTML = `
        <form id="item-modal-form">
            <div id="add_item_indicator_disaggregation_options_wrapper" class="hidden">
                <div id="add_item_indicator_allowed_disaggregation_options_container"></div>
            </div>
            <select id="item-indicator-type-select">
                <option value="">All Types</option>
                <option value="Number">Number</option>
            </select>
            <select id="item-indicator-unit-select">
                <option value="">All Units</option>
                <option value="People">People</option>
            </select>
            <select id="item-indicator-bank-select">
                <option value="">Select Indicator...</option>
                <option value="10">People reached</option>
                <option value="20">People trained</option>
            </select>
        </form>
    `;
}

describe('IndicatorItem disaggregation defaults', () => {
    beforeEach(() => {
        IndicatorItem._lastDisaggIndicatorId = null;
        DataManager.data = {
            indicatorBankChoices: [
                { id: 10, name: 'People reached', type: 'Number', unit: 'People' },
                { id: 20, name: 'People trained', type: 'Number', unit: 'People' },
            ],
            disaggregationChoices: DISAGG_CHOICES,
        };
        vi.spyOn(DataManager, 'getIndicatorById').mockImplementation((id) => {
            return DataManager.data.indicatorBankChoices.find((ind) => ind.id === Number(id)) || null;
        });
        mountModalDom();
    });

    afterEach(() => {
        const form = document.getElementById('item-modal-form');
        if (form) IndicatorItem.teardown(form);
        vi.restoreAllMocks();
        document.body.innerHTML = '';
    });

    it('checks every option when populating without preserveSelections', () => {
        const container = document.getElementById('add_item_indicator_allowed_disaggregation_options_container');
        IndicatorItem.populateDisaggregationCheckboxes(container, DISAGG_CHOICES, false);

        const boxes = Array.from(container.querySelectorAll('input[type="checkbox"]'));
        expect(boxes).toHaveLength(4);
        expect(boxes.every((cb) => cb.checked)).toBe(true);
        expect(boxes.map((cb) => cb.value)).toEqual(['total', 'sex', 'age', 'sex_age']);
    });

    it('keeps only previously checked options when preserveSelections is true', () => {
        const container = document.getElementById('add_item_indicator_allowed_disaggregation_options_container');
        IndicatorItem.populateDisaggregationCheckboxes(container, DISAGG_CHOICES, false);
        container.querySelector('#disagg-sex').checked = false;
        container.querySelector('#disagg-age').checked = false;

        IndicatorItem.populateDisaggregationCheckboxes(container, DISAGG_CHOICES, true);

        const checked = Array.from(container.querySelectorAll('input[type="checkbox"]:checked')).map((cb) => cb.value);
        expect(checked).toEqual(['total', 'sex_age']);
    });

    it('selects all options when a disaggregatable indicator is chosen', () => {
        const modal = document.getElementById('item-modal-form');
        IndicatorItem.setupEventListeners(modal);

        const bankSelect = document.getElementById('item-indicator-bank-select');
        bankSelect.value = '10';
        bankSelect.dispatchEvent(new Event('change', { bubbles: true }));

        const boxes = Array.from(document.querySelectorAll(
            '#add_item_indicator_allowed_disaggregation_options_container input[type="checkbox"]'
        ));
        expect(boxes).toHaveLength(4);
        expect(boxes.every((cb) => cb.checked)).toBe(true);
    });

    it('selects all options again when the indicator selection changes', () => {
        const modal = document.getElementById('item-modal-form');
        IndicatorItem.setupEventListeners(modal);

        const bankSelect = document.getElementById('item-indicator-bank-select');
        bankSelect.value = '10';
        bankSelect.dispatchEvent(new Event('change', { bubbles: true }));

        document.getElementById('disagg-sex').checked = false;
        document.getElementById('disagg-age').checked = false;

        bankSelect.value = '20';
        bankSelect.dispatchEvent(new Event('change', { bubbles: true }));

        const boxes = Array.from(document.querySelectorAll(
            '#add_item_indicator_allowed_disaggregation_options_container input[type="checkbox"]'
        ));
        expect(boxes.every((cb) => cb.checked)).toBe(true);
    });

    it('preserves ticks when the same indicator is re-rendered', () => {
        const modal = document.getElementById('item-modal-form');
        IndicatorItem.setupEventListeners(modal);

        const bankSelect = document.getElementById('item-indicator-bank-select');
        bankSelect.value = '10';
        bankSelect.dispatchEvent(new Event('change', { bubbles: true }));

        document.getElementById('disagg-sex').checked = false;
        document.getElementById('disagg-age').checked = false;

        bankSelect.dispatchEvent(new Event('change', { bubbles: true }));

        const checked = Array.from(document.querySelectorAll(
            '#add_item_indicator_allowed_disaggregation_options_container input[type="checkbox"]:checked'
        )).map((cb) => cb.value);
        expect(checked).toEqual(['total', 'sex_age']);
    });
});
