/**
 * Tests for app/static/js/form_builder/modules/data-manager.js
 *
 * DataManager reads JSON from <script id="..."> elements in the DOM and
 * exposes query helpers.  Tests create those DOM elements in beforeEach
 * and clean them up in afterEach.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

// utils.js must be imported first so window.Utils is available for DataManager
import '../../../app/static/js/form_builder/modules/utils.js';
import { DataManager } from '../../../app/static/js/form_builder/modules/data-manager.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function injectJsonElement(id, data) {
    const el = document.createElement('script');
    el.type = 'application/json';
    el.id = id;
    el.textContent = JSON.stringify(data);
    document.body.appendChild(el);
    return el;
}

function removeElement(id) {
    document.getElementById(id)?.remove();
}

// Reset shared DataManager state before each test
function resetData() {
    DataManager.data = {
        indicatorBankChoices: [],
        disaggregationChoices: [],
        allTemplateItems: [],
        sectionsWithItems: [],
        questionTypeChoices: [],
        allTemplateSections: [],
        indicatorFieldsConfig: {},
        uniqueIndicatorTypes: [],
        uniqueIndicatorUnits: [],
        conditionTypes: {},
    };
}

// ---------------------------------------------------------------------------
// loadIndicatorBankChoices
// ---------------------------------------------------------------------------

describe('DataManager.loadIndicatorBankChoices', () => {
    beforeEach(resetData);
    afterEach(() => removeElement('indicator-bank-choices-data'));

    it('parses choices from the DOM element', () => {
        injectJsonElement('indicator-bank-choices-data', [
            { id: 1, name: 'People reached', type: 'Number', unit: 'people' },
            { id: 2, name: 'Volunteers trained', type: 'Number', unit: 'count' },
        ]);
        DataManager.loadIndicatorBankChoices();
        expect(DataManager.data.indicatorBankChoices).toHaveLength(2);
        expect(DataManager.data.indicatorBankChoices[0].name).toBe('People reached');
    });

    it('leaves data unchanged when element is absent', () => {
        DataManager.data.indicatorBankChoices = [{ id: 99 }];
        DataManager.loadIndicatorBankChoices();
        expect(DataManager.data.indicatorBankChoices).toHaveLength(1);
    });

    it('handles malformed JSON without throwing', () => {
        const el = document.createElement('script');
        el.type = 'application/json';
        el.id = 'indicator-bank-choices-data';
        el.textContent = 'INVALID_JSON';
        document.body.appendChild(el);
        expect(() => DataManager.loadIndicatorBankChoices()).not.toThrow();
    });
});

// ---------------------------------------------------------------------------
// loadDisaggregationChoices
// ---------------------------------------------------------------------------

describe('DataManager.loadDisaggregationChoices', () => {
    beforeEach(resetData);
    afterEach(() => removeElement('disaggregation-choices-data'));

    it('parses disaggregation choices from the DOM element', () => {
        injectJsonElement('disaggregation-choices-data', [
            { id: 'sex', label: 'Sex' },
            { id: 'age', label: 'Age group' },
        ]);
        DataManager.loadDisaggregationChoices();
        expect(DataManager.data.disaggregationChoices).toHaveLength(2);
        expect(DataManager.data.disaggregationChoices[0].id).toBe('sex');
    });
});

// ---------------------------------------------------------------------------
// extractUniqueTypes
// ---------------------------------------------------------------------------

describe('DataManager.extractUniqueTypes', () => {
    beforeEach(resetData);

    it('extracts unique non-empty types', () => {
        DataManager.data.indicatorBankChoices = [
            { type: 'Number' },
            { type: 'text' },
            { type: 'Number' },
            { type: '' },
        ];
        DataManager.extractUniqueTypes();
        expect(DataManager.data.uniqueIndicatorTypes).toContain('Number');
        expect(DataManager.data.uniqueIndicatorTypes).toContain('text');
        expect(DataManager.data.uniqueIndicatorTypes).not.toContain('');
        expect(DataManager.data.uniqueIndicatorTypes.filter(t => t === 'Number')).toHaveLength(1);
    });

    it('filters out null and undefined', () => {
        DataManager.data.indicatorBankChoices = [
            { type: null },
            { type: undefined },
            { type: 'Number' },
        ];
        DataManager.extractUniqueTypes();
        expect(DataManager.data.uniqueIndicatorTypes).toEqual(['Number']);
    });

    it('returns empty array for empty choices', () => {
        DataManager.data.indicatorBankChoices = [];
        DataManager.extractUniqueTypes();
        expect(DataManager.data.uniqueIndicatorTypes).toEqual([]);
    });
});

// ---------------------------------------------------------------------------
// extractUniqueUnits
// ---------------------------------------------------------------------------

describe('DataManager.extractUniqueUnits', () => {
    beforeEach(resetData);

    it('extracts unique non-empty units', () => {
        DataManager.data.indicatorBankChoices = [
            { unit: 'people' },
            { unit: 'percentage' },
            { unit: 'people' },
        ];
        DataManager.extractUniqueUnits();
        expect(DataManager.data.uniqueIndicatorUnits).toContain('people');
        expect(DataManager.data.uniqueIndicatorUnits).toContain('percentage');
        expect(DataManager.data.uniqueIndicatorUnits.filter(u => u === 'people')).toHaveLength(1);
    });
});

// ---------------------------------------------------------------------------
// setupConditionTypes
// ---------------------------------------------------------------------------

describe('DataManager.setupConditionTypes', () => {
    beforeEach(resetData);

    it('populates condition types for known field types', () => {
        DataManager.setupConditionTypes();
        const types = DataManager.data.conditionTypes;
        expect(types).toHaveProperty('Number');
        expect(types).toHaveProperty('text');
        expect(types).toHaveProperty('yesno');
        expect(types).toHaveProperty('single_choice');
        expect(types).toHaveProperty('multiple_choice');
        expect(types).toHaveProperty('date');
        expect(types).toHaveProperty('document');
    });

    it('Number condition types include greater_than and less_than', () => {
        DataManager.setupConditionTypes();
        const values = DataManager.data.conditionTypes['Number'].map(c => c.value);
        expect(values).toContain('greater_than');
        expect(values).toContain('less_than');
    });
});

// ---------------------------------------------------------------------------
// getConditionTypes
// ---------------------------------------------------------------------------

describe('DataManager.getConditionTypes', () => {
    beforeEach(() => {
        resetData();
        DataManager.setupConditionTypes();
    });

    it('returns conditions for an exact key', () => {
        const conditions = DataManager.getConditionTypes('text');
        expect(conditions.length).toBeGreaterThan(0);
        expect(conditions[0]).toHaveProperty('value');
        expect(conditions[0]).toHaveProperty('label');
    });

    it('is case-insensitive (handles "number" vs "Number")', () => {
        const byLower = DataManager.getConditionTypes('number');
        const byUpper = DataManager.getConditionTypes('Number');
        expect(byLower).toEqual(byUpper);
    });

    it('returns empty array for unknown type', () => {
        expect(DataManager.getConditionTypes('nonexistent')).toEqual([]);
    });

    it('returns empty array for null/undefined/empty key', () => {
        expect(DataManager.getConditionTypes(null)).toEqual([]);
        expect(DataManager.getConditionTypes(undefined)).toEqual([]);
        expect(DataManager.getConditionTypes('')).toEqual([]);
    });
});

// ---------------------------------------------------------------------------
// getIndicatorById
// ---------------------------------------------------------------------------

describe('DataManager.getIndicatorById', () => {
    beforeEach(() => {
        resetData();
        DataManager.data.indicatorBankChoices = [
            { id: 10, name: 'People reached', type: 'Number' },
            { id: 20, name: 'Volunteers', type: 'Number' },
        ];
    });

    it('finds an indicator by numeric id', () => {
        const ind = DataManager.getIndicatorById(10);
        expect(ind).toBeTruthy();
        expect(ind.name).toBe('People reached');
    });

    it('finds an indicator by string id (loose equality)', () => {
        const ind = DataManager.getIndicatorById('20');
        expect(ind).toBeTruthy();
        expect(ind.name).toBe('Volunteers');
    });

    it('returns undefined for unknown id', () => {
        expect(DataManager.getIndicatorById(999)).toBeUndefined();
    });
});

// ---------------------------------------------------------------------------
// getItemById
// ---------------------------------------------------------------------------

describe('DataManager.getItemById', () => {
    beforeEach(() => {
        resetData();
        DataManager.data.allTemplateItems = [
            { id: 1, type: 'indicator', label: 'Ind A' },
            { id: 2, type: 'question', label: 'Q1' },
            { id: 3, type: 'document', label: 'Doc1' },
        ];
    });

    it('finds an indicator item', () => {
        expect(DataManager.getItemById(1, 'indicator').label).toBe('Ind A');
    });

    it('finds a question item', () => {
        expect(DataManager.getItemById(2, 'question').label).toBe('Q1');
    });

    it('finds a document item', () => {
        expect(DataManager.getItemById(3, 'document').label).toBe('Doc1');
    });

    it('returns undefined for wrong type (Array.find returns undefined on miss)', () => {
        expect(DataManager.getItemById(1, 'question')).toBeUndefined();
    });

    it('returns null for unknown type', () => {
        expect(DataManager.getItemById(1, 'plugin')).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// filterIndicators
// ---------------------------------------------------------------------------

describe('DataManager.filterIndicators', () => {
    beforeEach(() => {
        resetData();
        DataManager.data.indicatorBankChoices = [
            { id: 1, type: 'Number', unit: 'people' },
            { id: 2, type: 'Number', unit: 'percentage' },
            { id: 3, type: 'text', unit: 'none' },
        ];
    });

    it('returns all when no filter is applied', () => {
        expect(DataManager.filterIndicators()).toHaveLength(3);
    });

    it('filters by type', () => {
        expect(DataManager.filterIndicators('Number')).toHaveLength(2);
        expect(DataManager.filterIndicators('text')).toHaveLength(1);
    });

    it('filters by unit', () => {
        expect(DataManager.filterIndicators(null, 'people')).toHaveLength(1);
        expect(DataManager.filterIndicators(null, 'percentage')).toHaveLength(1);
    });

    it('filters by both type and unit', () => {
        expect(DataManager.filterIndicators('Number', 'people')).toHaveLength(1);
        expect(DataManager.filterIndicators('Number', 'none')).toHaveLength(0);
    });
});

// ---------------------------------------------------------------------------
// getData / getAllData
// ---------------------------------------------------------------------------

describe('DataManager.getData / getAllData', () => {
    beforeEach(resetData);

    it('getData returns the value for a known key', () => {
        DataManager.data.indicatorBankChoices = [{ id: 1 }];
        expect(DataManager.getData('indicatorBankChoices')).toEqual([{ id: 1 }]);
    });

    it('getData returns null for unknown key', () => {
        expect(DataManager.getData('nonexistent_key')).toBeNull();
    });

    it('getAllData returns the full data object', () => {
        const all = DataManager.getAllData();
        expect(all).toHaveProperty('indicatorBankChoices');
        expect(all).toHaveProperty('disaggregationChoices');
    });
});
