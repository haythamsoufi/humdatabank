// data-manager.js - Data management and parsing

// Utils is available globally from utils.js

export const DataManager = {
    // Data storage
    data: {
        indicatorBankChoices: [],
        disaggregationChoices: [],
        allTemplateItems: [],
        sectionsWithItems: [],
        questionTypeChoices: [],
        allTemplateSections: [],
        indicatorFieldsConfig: {},
        uniqueIndicatorTypes: [],
        uniqueIndicatorUnits: [],
        conditionTypes: {}
    },

    // Initialize data from DOM
    init: function() {
        Utils.setDebugModule('data-manager');
        this.loadIndicatorBankChoices();
        this.loadDisaggregationChoices();
        this.loadAllTemplateItems();
        this.loadSectionsWithItems();
        this.loadQuestionTypeChoices();
        this.loadAllTemplateSections();
        this.loadIndicatorFieldsConfig();
        this.setupConditionTypes();
    },

    // Load indicator bank choices
    loadIndicatorBankChoices: function() {
        const element = Utils.getElementById('indicator-bank-choices-data');
        if (element) {
            try {
                this.data.indicatorBankChoices = JSON.parse(element.textContent);
                this.extractUniqueTypes();
                this.extractUniqueUnits();
            } catch (e) { console.error('[DataManager] Failed to parse indicator-bank-choices-data JSON', e); }
        }
    },

    // Load disaggregation choices
    loadDisaggregationChoices: function() {
        const element = Utils.getElementById('disaggregation-choices-data');
        if (element) {
            try {
                this.data.disaggregationChoices = JSON.parse(element.textContent);
                Utils.debugLog('Disaggregation Choices loaded:', this.data.disaggregationChoices);
            } catch (e) { console.error('[DataManager] Failed to parse disaggregation-choices-data JSON', e); }
        }
    },

    // Load all template items
    loadAllTemplateItems: function() {
        const element = Utils.getElementById('all-template-items-data');
        if (element) {
            try {
                this.data.allTemplateItems = JSON.parse(element.textContent);
                Utils.debugLog('All Template Items loaded:', this.data.allTemplateItems);
            } catch (e) { console.error('[DataManager] Failed to parse all-template-items-data JSON', e); }
        }
    },

    // Load sections with items
    loadSectionsWithItems: function() {
        const element = Utils.getElementById('sections-with-items-data');
        if (element) {
            try {
                this.data.sectionsWithItems = JSON.parse(element.textContent);
                Utils.debugLog('Sections With Items loaded:', this.data.sectionsWithItems);
            } catch (e) { console.error('[DataManager] Failed to parse sections-with-items-data JSON', e); }
        }
    },

    // Load question type choices
    loadQuestionTypeChoices: function() {
        const element = Utils.getElementById('question-type-choices-data');
        if (element) {
            try {
                this.data.questionTypeChoices = JSON.parse(element.textContent);
                Utils.debugLog('Question Type Choices loaded:', this.data.questionTypeChoices);
            } catch (e) { console.error('[DataManager] Failed to parse question-type-choices-data JSON', e); }
        }
    },

    // Load all template sections
    loadAllTemplateSections: function() {
        const element = Utils.getElementById('all-template-sections-data');
        if (element) {
            try {
                this.data.allTemplateSections = JSON.parse(element.textContent);
                Utils.debugLog('All Template Sections loaded:', this.data.allTemplateSections);
            } catch (e) { console.error('[DataManager] Failed to parse all-template-sections-data JSON', e); }
        }
    },

    // Load indicator fields config
    loadIndicatorFieldsConfig: function() {
        const element = Utils.getElementById('indicator-fields-config-data');
        if (element) {
            try {
                this.data.indicatorFieldsConfig = JSON.parse(element.textContent);
                Utils.debugLog('Indicator Fields Config loaded:', this.data.indicatorFieldsConfig);
            } catch (e) { console.error('[DataManager] Failed to parse indicator-fields-config-data JSON', e); }
        }
    },

    // Extract unique indicator types
    extractUniqueTypes: function() {
        this.data.uniqueIndicatorTypes = [...new Set(
            this.data.indicatorBankChoices
                .map(item => item.type)
                .filter(type => type !== null && type !== undefined && type !== '')
        )];
        Utils.debugLog('Unique Indicator Types:', this.data.uniqueIndicatorTypes);
    },

    // Extract unique indicator units
    extractUniqueUnits: function() {
        this.data.uniqueIndicatorUnits = [...new Set(
            this.data.indicatorBankChoices
                .map(item => item.unit)
                .filter(unit => unit !== null && unit !== undefined && unit !== '')
        )];
        Utils.debugLog('Unique Indicator Units:', this.data.uniqueIndicatorUnits);
    },

    // Setup condition types for rule builder
    setupConditionTypes: function() {
        this.data.conditionTypes = {
            'Number': [
                {value: 'equal_to', label: 'Equal to'},
                {value: 'not_equal_to', label: 'Not equal to'},
                {value: 'greater_than', label: 'Greater than (>)'},
                {value: 'greater_than_or_equal_to', label: 'Greater than or equal to (>=)'},
                {value: 'less_than', label: 'Less than (<)'},
                {value: 'less_than_or_equal_to', label: 'Less than or equal to (<=)'},
                {value: 'is_empty', label: 'Is empty'},
                {value: 'is_not_empty', label: 'Is not empty'}
            ],
            'text': [
                {value: 'equal_to', label: 'Equal to'},
                {value: 'not_equal_to', label: 'Not equal to'},
                {value: 'contains', label: 'Contains'},
                {value: 'not_contains', label: 'Does not contain'},
                {value: 'starts_with', label: 'Starts with'},
                {value: 'ends_with', label: 'Ends with'},
                {value: 'is_empty', label: 'Is empty'},
                {value: 'is_not_empty', label: 'Is not empty'}
            ],
            'textarea': [
                {value: 'equal_to', label: 'Equal to'},
                {value: 'not_equal_to', label: 'Not equal to'},
                {value: 'contains', label: 'Contains'},
                {value: 'not_contains', label: 'Does not contain'},
                {value: 'is_empty', label: 'Is empty'},
                {value: 'is_not_empty', label: 'Is not empty'}
            ],
            'yesno': [
                {value: 'is_yes', label: 'Is Yes'},
                {value: 'is_no', label: 'Is No'},
                {value: 'is_empty', label: 'Is empty (no answer provided)'},
                {value: 'is_not_empty', label: 'Is answered'}
            ],
            'single_choice': [
                {value: 'equal_to', label: 'Is'},
                {value: 'not_equal_to', label: 'Is not'},
                {value: 'is_empty', label: 'Is empty'},
                {value: 'is_not_empty', label: 'Is not empty'}
            ],
            'multiple_choice': [
                {value: 'contains', label: 'Contains'},
                {value: 'not_contains', label: 'Does not contain'},
                {value: 'is_empty', label: 'Is empty'},
                {value: 'is_not_empty', label: 'Is not empty'}
            ],
            'date': [
                {value: 'equal_to', label: 'Is'},
                {value: 'not_equal_to', label: 'Is not'},
                {value: 'greater_than', label: 'Is after'},
                {value: 'greater_than_or_equal_to', label: 'Is on or after'},
                {value: 'less_than', label: 'Is before'},
                {value: 'less_than_or_equal_to', label: 'Is on or before'},
                {value: 'is_empty', label: 'Is empty'},
                {value: 'is_not_empty', label: 'Is not empty'}
            ],
            'document': [
                {value: 'is_uploaded', label: 'Is uploaded'},
                {value: 'is_not_uploaded', label: 'Is not uploaded'}
            ]
        };
    },

    // Get data by key
    getData: function(key) {
        return this.data[key] || null;
    },

    // Get all data
    getAllData: function() {
        return this.data;
    },

    // Get indicator by ID
    getIndicatorById: function(id) {
        return this.data.indicatorBankChoices.find(item => (item.id ?? item.value) == id);
    },

    // Get section by ID
    getSectionById: function(id) {
        return this.data.allTemplateSections.find(section => {
            const sectionId = Array.isArray(section) ? section[0] : (section.id ?? section.value);
            return String(sectionId) === String(id);
        });
    },

    // Get item by ID and type — uses loose equality so string "123" matches numeric 123
    getItemById: function(id, type) {
        if (type === 'indicator') {
            return this.data.allTemplateItems.find(item => item.type === 'indicator' && item.id == id);
        } else if (type === 'question') {
            return this.data.allTemplateItems.find(item => item.type === 'question' && item.id == id);
        } else if (type === 'document') {
            return this.data.allTemplateItems.find(item => item.type === 'document' && item.id == id);
        }
        return null;
    },

    // Get condition types for a given type key.
    // Falls back to a case-insensitive lookup to handle the 'Number' vs 'number' inconsistency.
    getConditionTypes: function(typeKey) {
        if (!typeKey) return [];
        if (this.data.conditionTypes[typeKey]) return this.data.conditionTypes[typeKey];
        const lower = String(typeKey).toLowerCase();
        const key = Object.keys(this.data.conditionTypes).find(k => k.toLowerCase() === lower);
        return key ? this.data.conditionTypes[key] : [];
    },

    // Filter indicators by type and unit
    filterIndicators: function(type = null, unit = null) {
        return this.data.indicatorBankChoices.filter(item => {
            if (type && item.type !== type) return false;
            if (unit && item.unit !== unit) return false;
            return true;
        });
    }
};
