// Rule Builder Module
import { DataManager } from '../data-manager.js';
import { conditionTypesMap } from '../../../lib/condition-operators.js';
// Utils is available globally from utils.js

const _t = (k) => (typeof window.t === 'function' ? window.t(k) : k);

// Built-in metadata tokens (available globally from form_builder.html).
// country_iso is a relevance-condition token (assignment country), not a label
// variable, so it is added here rather than in that label list. The stored value
// stays an ISO code; the builder only shows the country name.
function getBuiltInMetadataOptions() {
    const metadata = Array.isArray(window.builtInMetadataVariables) ? window.builtInMetadataVariables : [];
    const conditionTokens = [
        { key: 'country_iso', label: _t('Country') }
    ];
    const seen = new Set(
        metadata.map(m => String(m?.key || '').trim()).filter(Boolean)
    );
    const combined = metadata.slice();
    conditionTokens.forEach(token => {
        if (!seen.has(token.key)) combined.push(token);
    });
    // Map metadata keys to a simple type so the rule builder can choose condition operators.
    const typeByKey = {
        entity_id: 'Number',
        entity_name: 'text',
        entity_name_hierarchy: 'text',
        entity_type: 'text',
        template_name: 'text',
        assignment_period: 'text',
        assignment_year: 'text',
        country_iso: 'text',
        country_iso2: 'text'
    };
    return combined
        .map(m => {
            const key = String(m?.key || '').trim();
            if (!key) return null;
            return {
                key,
                label: String(m?.label || key),
                valueType: typeByKey[key] || 'text'
            };
        })
        .filter(Boolean);
}

/**
 * Resolve a template item (from allTemplateItems) by any id representation.
 *
 * Saved rules commonly store numeric IDs (e.g. "66"), while the in-page
 * `allTemplateItems` list uses prefixed string IDs (e.g. "question_66") AND
 * also exposes `item_id_raw` as the numeric primary key. We should prefer
 * matching on `item_id_raw` when possible to avoid "Unknown Item".
 */
function findTemplateItemByAnyId(allItems, idLike) {
    if (!Array.isArray(allItems) || allItems.length === 0) return null;
    if (idLike === null || idLike === undefined) return null;

    const raw = String(idLike).trim();
    if (!raw) return null;

    // 1) Exact match on the stored id (already prefixed, e.g. "question_66")
    let item = allItems.find(i => i && i.id !== undefined && String(i.id) === raw);
    if (item) return item;

    // 2) Numeric match on item_id_raw (preferred for DB-saved rules)
    const asInt = parseInt(raw, 10);
    if (!Number.isNaN(asInt)) {
        item = allItems.find(i => {
            if (!i) return false;
            const v = i.item_id_raw;
            if (v === null || v === undefined) return false;
            const n = parseInt(String(v), 10);
            return !Number.isNaN(n) && n === asInt;
        });
        if (item) return item;

        // 3) Numeric match by extracting the trailing numeric segment from id
        item = allItems.find(i => {
            const s = i && i.id !== undefined ? String(i.id) : '';
            const m = s.match(/_(\d+)$/);
            return m && parseInt(m[1], 10) === asInt;
        });
        if (item) return item;
    }

    return null;
}

const MEMBERSHIP_TYPES = new Set(['in', 'not_in']);
const EQUAL_TYPES = new Set(['equals', 'equal_to']);
const COUNTRY_METADATA_KEYS = new Set(['country_iso', 'country_iso2']);

let countryCatalog = null;
let countryCatalogPromise = null;

function membershipList(value) {
    const raw = Array.isArray(value) ? value : String(value ?? '').split(',');
    const seen = [];
    raw.forEach((item) => {
        const text = String(item ?? '').trim();
        if (text && !seen.includes(text)) seen.push(text);
    });
    return seen;
}

function formatMembership(value) {
    return `{${membershipList(value).join(', ')}}`;
}

function countryDisplayName(code, isoKey) {
    const normalized = String(code || '').trim().toUpperCase();
    if (!normalized || !Array.isArray(countryCatalog)) return '';
    const field = isoKey === 'country_iso2' ? 'iso2' : 'iso3';
    const row = countryCatalog.find((country) => (
        String(country?.[field] || '').trim().toUpperCase() === normalized
    ));
    return String(row?.localized_name || row?.name || '').trim();
}

function formatCountryMembership(value, isoKey) {
    const codes = membershipList(value);
    const names = codes.map((code) => countryDisplayName(code, isoKey)).filter(Boolean);
    if (names.length === codes.length && names.length) return `{${names.join(', ')}}`;
    if (codes.length === 1) return _t('1 country');
    return `${codes.length} ${_t('countries')}`;
}

function countryConditionPhrase(condition) {
    const isoKey = condition.item_id;
    if (MEMBERSHIP_TYPES.has(condition.condition_type)) {
        const list = formatCountryMembership(condition.value, isoKey);
        return condition.condition_type === 'not_in' ? `is not in ${list}` : `is in ${list}`;
    }
    const name = countryDisplayName(condition.value, isoKey);
    const shown = name ? `"${name}"` : _t('a country');
    if (condition.condition_type === 'not_equals' || condition.condition_type === 'not_equal_to') {
        return `does not equal ${shown}`;
    }
    if (EQUAL_TYPES.has(condition.condition_type)) return `equals ${shown}`;
    return `${condition.condition_type} ${shown}`;
}

/**
 * An OR of "country ISO equals X" lines is one membership test.
 * Collapse those for display and for the rule editor; leave every other rule as stored.
 */
function collapseCountryEquals(rule) {
    if (!rule || !Array.isArray(rule.conditions) || (rule.logic || 'AND') !== 'OR') {
        return rule;
    }
    const groups = new Map();
    rule.conditions.forEach((condition, index) => {
        if (!condition || !EQUAL_TYPES.has(condition.condition_type)) return;
        if (condition.value_field_id !== null && condition.value_field_id !== undefined) return;
        const key = String(condition.item_id || '');
        if (!COUNTRY_METADATA_KEYS.has(key)) return;
        const text = String(condition.value ?? '').trim();
        if (!text) return;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(index);
    });

    const skip = new Set();
    const replacements = new Map();
    groups.forEach((indexes) => {
        if (indexes.length < 2) return;
        const values = [];
        indexes.forEach((index) => {
            const text = String(rule.conditions[index].value).trim();
            if (!values.includes(text)) values.push(text);
            skip.add(index);
        });
        const first = indexes[0];
        skip.delete(first);
        replacements.set(first, {
            item_id: rule.conditions[first].item_id,
            condition_type: 'in',
            value: values
        });
    });
    if (replacements.size === 0) return rule;

    const conditions = [];
    rule.conditions.forEach((condition, index) => {
        if (skip.has(index)) return;
        conditions.push(replacements.get(index) || condition);
    });
    return { ...rule, conditions };
}

function conditionPhrase(condition, allItems) {
    if (COUNTRY_METADATA_KEYS.has(String(condition.item_id || ''))) {
        return countryConditionPhrase(condition);
    }
    let valueDisplay = '';
    if (MEMBERSHIP_TYPES.has(condition.condition_type)) {
        valueDisplay = formatMembership(condition.value);
    } else if (condition.value_field_id !== null && condition.value_field_id !== undefined) {
        const refItem = findTemplateItemByAnyId(allItems, condition.value_field_id);
        valueDisplay = refItem ? `field "${refItem.label}"` : `field ID ${condition.value_field_id}`;
    } else if (condition.value !== null && condition.value !== undefined) {
        valueDisplay = `"${condition.value}"`;
    }

    switch (condition.condition_type) {
        case 'is_empty':
            return 'is empty';
        case 'is_not_empty':
            return 'is not empty';
        case 'equals':
        case 'equal_to':
            return `equals ${valueDisplay}`;
        case 'not_equals':
        case 'not_equal_to':
            return `does not equal ${valueDisplay}`;
        case 'greater_than':
            return `is greater than ${valueDisplay}`;
        case 'greater_than_or_equal_to':
            return `is greater than or equal to ${valueDisplay}`;
        case 'less_than':
            return `is less than ${valueDisplay}`;
        case 'less_than_or_equal_to':
            return `is less than or equal to ${valueDisplay}`;
        case 'contains':
            return `contains ${valueDisplay}`;
        case 'not_contains':
            return `does not contain ${valueDisplay}`;
        case 'in':
            return `is in ${valueDisplay}`;
        case 'not_in':
            return `is not in ${valueDisplay}`;
        default:
            return `${condition.condition_type} ${valueDisplay}`;
    }
}

function loadCountryCatalog() {
    if (countryCatalog) return Promise.resolve(countryCatalog);
    if (!countryCatalogPromise) {
        countryCatalogPromise = fetch('/api/v1/countrymap', {
            credentials: 'same-origin',
            headers: { Accept: 'application/json' }
        })
            .then((response) => (response.ok ? response.json() : []))
            .then((payload) => {
                const rows = Array.isArray(payload) ? payload : (payload && payload.countries) || [];
                countryCatalog = rows;
                return rows;
            })
            .catch(() => {
                countryCatalogPromise = null;
                return [];
            });
    }
    return countryCatalogPromise;
}

function destroyCountrySelect(container) {
    if (!container || !container.querySelectorAll) return;
    container.querySelectorAll('.rule-country-picker').forEach((picker) => {
        if (typeof picker._cleanup === 'function') picker._cleanup();
    });
}

function ensureCountryPickerStyles() {
    if (document.getElementById('rule-country-picker-styles')) return;
    const style = document.createElement('style');
    style.id = 'rule-country-picker-styles';
    style.textContent = `
        .rule-country-controls { display: flex; align-items: center; gap: 0.25rem; }
        .rule-country-toggle, .rule-country-expand {
            height: 2.25rem;
            border: 1px solid #d1d5db;
            border-radius: 0.375rem;
            background: #fff;
            font-size: 0.875rem;
            line-height: 1.25rem;
        }
        .rule-country-toggle {
            flex: 1;
            min-width: 0;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.5rem;
            padding: 0 0.5rem;
            text-align: left;
            color: #111827;
        }
        .rule-country-toggle span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .rule-country-expand {
            flex: none;
            width: 2.25rem;
            color: #4b5563;
        }
        .rule-country-expand.is-open { background: #eff6ff; border-color: #93c5fd; color: #1d4ed8; }
        .rule-country-expand:disabled { opacity: 0.4; cursor: default; }
        .rule-country-panel {
            position: fixed;
            z-index: 80;
            background: #fff;
            border: 1px solid #d1d5db;
            border-radius: 0.375rem;
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.12);
            padding: 0.5rem;
        }
        .rule-country-search {
            display: block;
            width: 100%;
            margin-bottom: 0.5rem;
            padding: 0.35rem 0.5rem;
            border: 1px solid #d1d5db;
            border-radius: 0.375rem;
            font-size: 0.875rem;
        }
        .rule-country-options { max-height: 220px; overflow: auto; }
        .rule-country-option {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.25rem 0.15rem;
            font-size: 0.875rem;
            color: #111827;
        }
        .rule-country-sheet {
            flex: 1 0 100%;
            width: 100%;
            margin: 0.5rem 0 0;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }
        .rule-country-sheet[hidden],
        .rule-country-suggest[hidden] { display: none !important; }
        .rule-country-suggest {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
        }
        .rule-country-suggest button {
            border: 1px solid #d1d5db;
            border-radius: 0.25rem;
            background: #fff;
            padding: 0.15rem 0.45rem;
            font-size: 0.75rem;
            line-height: 1.25rem;
            color: #111827;
        }
        .rule-country-suggest button:hover,
        .rule-country-suggest button.is-active { background: #eff6ff; border-color: #93c5fd; color: #1d4ed8; }
        .rule-country-chips { display: flex; flex-wrap: wrap; gap: 0.35rem; }
        .rule-country-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            padding: 0.1rem 0.35rem;
            border-radius: 0.25rem;
            background: #eff6ff;
            color: #1d4ed8;
            font-size: 0.75rem;
            line-height: 1.25rem;
            white-space: nowrap;
        }
        .rule-country-chip button {
            border: 0;
            background: transparent;
            color: inherit;
            cursor: pointer;
            padding: 0;
            line-height: 1;
        }
    `;
    document.head.appendChild(style);
}

function readStaticRuleValue(valueInput) {
    if (!valueInput) return undefined;
    if (valueInput.multiple) {
        const selected = Array.from(valueInput.selectedOptions)
            .map((option) => option.value.trim())
            .filter(Boolean);
        return selected.length ? selected : undefined;
    }
    if (valueInput.dataset.valueList === 'true') {
        const selected = membershipList(valueInput.value);
        return selected.length ? selected : undefined;
    }
    return valueInput.value ? valueInput.value : undefined;
}

function countryRows(catalog, isoKey) {
    const codeField = isoKey === 'country_iso2' ? 'iso2' : 'iso3';
    const seen = new Set();
    return (catalog || [])
        .filter((country) => country && String(country[codeField] || '').trim())
        .map((country) => {
            const code = String(country[codeField]).trim().toUpperCase();
            const name = String(country.localized_name || country.name || '').trim();
            if (!name) return null;
            return { code, label: name };
        })
        .filter((country) => {
            if (!country || !country.code || seen.has(country.code)) return false;
            seen.add(country.code);
            return true;
        })
        .sort((a, b) => a.label.localeCompare(b.label));
}

function buildCountryPicker(isoKey, existingValue) {
    ensureCountryPickerStyles();
    const picker = document.createElement('div');
    picker.className = 'rule-country-picker';

    const select = document.createElement('select');
    select.multiple = true;
    select.hidden = true;
    select.className = 'rule-value-input rule-value-countries';
    select.setAttribute('aria-hidden', 'true');

    const controls = document.createElement('div');
    controls.className = 'rule-country-controls';

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'rule-country-toggle';
    const summary = document.createElement('span');
    const caret = document.createElement('i');
    caret.className = 'fas fa-chevron-down';
    caret.setAttribute('aria-hidden', 'true');
    toggle.append(summary, caret);

    const expand = document.createElement('button');
    expand.type = 'button';
    expand.className = 'rule-country-expand';
    expand.title = _t('Show selected countries');
    const expandIcon = document.createElement('i');
    expandIcon.className = 'fas fa-list';
    expandIcon.setAttribute('aria-hidden', 'true');
    expand.appendChild(expandIcon);

    const panel = document.createElement('div');
    panel.className = 'rule-country-panel';
    panel.hidden = true;
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'rule-country-search';
    search.placeholder = _t('Search countries');
    search.setAttribute('aria-label', _t('Search countries'));
    const list = document.createElement('div');
    list.className = 'rule-country-options';
    panel.append(search, list);

    const sheet = document.createElement('div');
    sheet.className = 'rule-country-sheet';
    sheet.hidden = true;
    const addBox = document.createElement('input');
    addBox.type = 'search';
    addBox.className = 'rule-country-search';
    addBox.placeholder = _t('Type to search and add a country');
    addBox.setAttribute('aria-label', _t('Type to search and add a country'));
    const suggest = document.createElement('div');
    suggest.className = 'rule-country-suggest';
    suggest.hidden = true;
    const chips = document.createElement('div');
    chips.className = 'rule-country-chips';
    sheet.append(addBox, suggest, chips);

    controls.append(toggle, expand);
    picker.append(select, controls, panel);
    picker._sheet = sheet;

    const initial = membershipList(existingValue).map((code) => code.toUpperCase());
    let countries = initial.map((code) => ({ code, label: countryDisplayName(code, isoKey) }));
    const chosen = new Set(initial);
    let expanded = false;
    let disposed = false;

    function syncSelect() {
        select.replaceChildren();
        countries.forEach((country) => {
            const option = document.createElement('option');
            option.value = country.code;
            option.textContent = country.label;
            option.selected = chosen.has(country.code);
            select.appendChild(option);
        });
    }

    function renderSummary() {
        const count = chosen.size;
        if (count === 0) summary.textContent = _t('Select countries');
        else if (count === 1) {
            const only = countries.find((country) => chosen.has(country.code));
            summary.textContent = only && only.label ? only.label : _t('1 country');
        } else summary.textContent = `${count} ${_t('countries')}`;
        toggle.setAttribute('aria-expanded', panel.hidden ? 'false' : 'true');
        expand.title = expanded ? _t('Hide selected countries') : _t('Show selected countries');
        expand.classList.toggle('is-open', expanded);
    }

    function renderChips() {
        chips.replaceChildren();
        countries.filter((country) => chosen.has(country.code) && country.label).forEach((country) => {
            const chip = document.createElement('span');
            chip.className = 'rule-country-chip';
            chip.appendChild(document.createTextNode(country.label));
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.textContent = '×';
            remove.setAttribute('aria-label', _t('Remove'));
            remove.addEventListener('click', () => setChecked(country.code, false));
            chip.appendChild(remove);
            chips.appendChild(chip);
        });
    }

    function renderSuggestions() {
        const query = addBox.value.trim().toLowerCase();
        suggest.replaceChildren();
        if (!query) {
            suggest.hidden = true;
            return;
        }
        const matches = countries.filter((country) => (
            country.label
            && !chosen.has(country.code)
            && country.label.toLowerCase().includes(query)
        )).slice(0, 12);
        if (!matches.length) {
            suggest.hidden = true;
            return;
        }
        suggest.hidden = false;
        matches.forEach((country, index) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = country.label;
            if (index === 0) button.classList.add('is-active');
            button.addEventListener('mousedown', (event) => event.preventDefault());
            button.addEventListener('click', () => addCountry(country.code));
            suggest.appendChild(button);
        });
    }

    function addCountry(code) {
        setChecked(code, true);
        addBox.value = '';
        suggest.hidden = true;
        addBox.focus();
    }

    function showSheet(open) {
        expanded = open;
        sheet.hidden = !open;
        if (!open) {
            addBox.value = '';
            suggest.hidden = true;
        }
        renderSummary();
        renderChips();
        if (open) addBox.focus();
    }

    function renderOptions() {
        const query = search.value.trim().toLowerCase();
        list.replaceChildren();
        countries.forEach((country) => {
            if (!country.label) return;
            if (query && !country.label.toLowerCase().includes(query)) return;
            const label = document.createElement('label');
            label.className = 'rule-country-option';
            const box = document.createElement('input');
            box.type = 'checkbox';
            box.value = country.code;
            box.checked = chosen.has(country.code);
            box.addEventListener('change', () => setChecked(country.code, box.checked));
            label.append(box, document.createTextNode(country.label));
            list.appendChild(label);
        });
    }

    function setChecked(code, on) {
        if (on) chosen.add(code);
        else chosen.delete(code);
        syncSelect();
        renderSummary();
        renderChips();
        renderSuggestions();
        const box = list.querySelector(`input[value="${code}"]`);
        if (box) box.checked = on;
    }

    function positionPanel() {
        const rect = toggle.getBoundingClientRect();
        const width = Math.max(rect.width, 280);
        const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
        panel.style.width = `${width}px`;
        panel.style.left = `${left}px`;
        const spaceBelow = window.innerHeight - rect.bottom;
        if (spaceBelow < 240 && rect.top > spaceBelow) {
            panel.style.top = 'auto';
            panel.style.bottom = `${window.innerHeight - rect.top + 4}px`;
        } else {
            panel.style.bottom = 'auto';
            panel.style.top = `${rect.bottom + 4}px`;
        }
    }

    function closePanel() {
        panel.hidden = true;
        renderSummary();
    }

    function openPanel() {
        panel.hidden = false;
        positionPanel();
        renderSummary();
        search.focus();
    }

    function onDocumentClick(event) {
        if (panel.hidden || picker.contains(event.target)) return;
        closePanel();
    }

    function onKeyDown(event) {
        if (event.key === 'Escape' && !panel.hidden) closePanel();
    }

    const dialog = () => picker.closest('[role="dialog"]');
    function onDialogScroll(event) {
        if (panel.hidden || panel.contains(event.target)) return;
        positionPanel();
    }

    function onResize() {
        if (!panel.hidden) positionPanel();
    }

    toggle.addEventListener('click', () => {
        if (panel.hidden) openPanel();
        else closePanel();
    });
    expand.addEventListener('click', () => {
        showSheet(!expanded);
    });
    search.addEventListener('input', renderOptions);
    addBox.addEventListener('input', renderSuggestions);
    addBox.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            const first = suggest.querySelector('button');
            if (first) first.click();
        } else if (event.key === 'Escape') {
            suggest.hidden = true;
        }
    });
    document.addEventListener('click', onDocumentClick);
    document.addEventListener('keydown', onKeyDown);
    window.addEventListener('resize', onResize);

    function bindDialogScroll() {
        if (disposed || picker._scrollBound) return;
        const host = dialog();
        if (!host) return;
        host.addEventListener('scroll', onDialogScroll);
        picker._scrollBound = true;
    }

    picker._cleanup = () => {
        disposed = true;
        document.removeEventListener('click', onDocumentClick);
        document.removeEventListener('keydown', onKeyDown);
        window.removeEventListener('resize', onResize);
        const host = dialog();
        if (host) host.removeEventListener('scroll', onDialogScroll);
        if (sheet.parentNode) sheet.remove();
    };

    function applyCatalog(catalog) {
        if (disposed || !catalog) return;
        const rows = countryRows(catalog, isoKey);
        const known = new Set(rows.map((country) => country.code));
        chosen.forEach((code) => {
            if (!known.has(code)) rows.push({ code, label: countryDisplayName(code, isoKey) || _t('Country') });
        });
        rows.sort((a, b) => a.label.localeCompare(b.label));
        countries = rows;
        syncSelect();
        renderOptions();
        renderSummary();
        renderChips();
        renderSuggestions();
        bindDialogScroll();
    }

    syncSelect();
    renderOptions();
    renderSummary();
    // The caller inserts the picker after this returns. A catalog that is already
    // loaded must still be applied; bailing out while the node is detached left
    // the dropdown with only the countries already selected.
    if (countryCatalog) applyCatalog(countryCatalog);
    else loadCountryCatalog().then(applyCatalog);
    queueMicrotask(bindDialogScroll);
    return picker;
}

export const RuleBuilder = {
    // Initialize rule displays in the template list
    initializeRuleDisplays() {
        const ruleElements = document.querySelectorAll('.rule-display');
        ruleElements.forEach((element) => {
            const ruleJson = element.getAttribute('data-rule-json');
            const ruleType = element.getAttribute('data-rule-type');

            if (ruleJson && ruleJson !== 'null' && ruleJson !== '{}' && ruleJson.trim() !== '') {
                try {
                    const humanText = this.parseRuleToText(ruleJson, ruleType);
                    element.textContent = humanText;
                    element.title = humanText;
                } catch (error) {
                    element.textContent = 'Error parsing rule';
                }
            } else {
                element.textContent = 'No rule defined';
            }
        });
        if (!countryCatalog) {
            loadCountryCatalog().then((rows) => {
                if (rows && rows.length) this.initializeRuleDisplays();
            });
        }
    },

_setCountryCatalog(rows) {
    countryCatalog = Array.isArray(rows) ? rows : null;
    countryCatalogPromise = null;
},

    // Parse rule JSON to human-readable text
    parseRuleToText(ruleJson, ruleType) {
        try {
            const parsed = typeof ruleJson === 'string' ? JSON.parse(ruleJson) : ruleJson;
            const rule = collapseCountryEquals(parsed);

            if (!rule || !rule.conditions || rule.conditions.length === 0) {
                return 'No conditions defined';
            }

            const conditions = rule.conditions.map(condition => {
                const allItems = DataManager.getData('allTemplateItems') || [];
                const metadataOptions = getBuiltInMetadataOptions();

                // Handle both numeric IDs and prefixed IDs
                let item = null;
                let measureName = '';

                // Built-in metadata condition. Country rules keep an ISO code in
                // storage and show the country name here.
                if (condition.item_id && COUNTRY_METADATA_KEYS.has(String(condition.item_id))) {
                    return `${_t('Country')} ${conditionPhrase(condition, allItems)}`;
                }
                if (condition.item_id && typeof condition.item_id === 'string') {
                    const meta = metadataOptions.find(m => m.key === condition.item_id);
                    if (meta) {
                        return `${meta.label} ${conditionPhrase(condition, allItems)}`;
                    }
                }

                if (condition.item_id && typeof condition.item_id === 'string' && condition.item_id.startsWith('plugin_')) {
                    // Plugin item ids can be:
                    // - "plugin_123" (base plugin item)
                    // - "plugin_123_measure_id" (a plugin measure)
                    const parts = condition.item_id.split('_');
                    if (parts.length >= 3) {
                        // Treat as plugin measure: base id = "plugin_123"
                        const baseFieldId = parts.slice(0, 2).join('_');
                        item = findTemplateItemByAnyId(allItems, baseFieldId);

                        const measureId = parts.slice(2).join('_');
                        if (item && item.plugin_measures) {
                            const measure = item.plugin_measures.find(m => m.id === measureId);
                            measureName = measure ? measure.name : measureId;
                        }
                    } else {
                        // Base plugin item: resolve as-is
                        item = findTemplateItemByAnyId(allItems, condition.item_id);
                    }
                } else {
                    // Numeric IDs (common) or already-prefixed IDs: resolve via helper
                    item = findTemplateItemByAnyId(allItems, condition.item_id);
                }

                let itemLabel = 'Unknown Item';
                if (item) {
                    itemLabel = item.label;
                    if (measureName) {
                        itemLabel = `${itemLabel} (${measureName})`;
                    }
                }

                return `${itemLabel} ${conditionPhrase(condition, allItems)}`;
            });

            const logic = rule.logic || 'AND';
            return conditions.join(` ${logic} `);
        } catch (error) {
            return 'Invalid rule format';
        }
    },

    // Render rule builder UI
    renderRuleBuilder(containerElement, ruleJson, ruleType, currentItemId = null) {
        if (!containerElement) {
            return;
        }

        // Add CSS for dropdown styling
        if (!document.getElementById('rule-builder-dropdown-styles')) {
            const style = document.createElement('style');
            style.id = 'rule-builder-dropdown-styles';
            style.textContent = `
                .rule-item-select option {
                    white-space: normal;
                    word-wrap: break-word;
                    padding: 8px;
                    line-height: 1.4;
                }
                .rule-item-select {
                    max-width: 300px !important;
                }
                .rule-item-select option[data-is-current-item="true"] {
                    font-style: italic;
                    background-color: #f0f9ff;
                }
            `;
            document.head.appendChild(style);
        }

        containerElement.replaceChildren();
        const root = document.createElement('div');
        root.className = 'space-y-4';

        const logicRow = document.createElement('div');
        logicRow.className = 'flex items-center space-x-2';
        const logicLabel = document.createElement('label');
        logicLabel.className = 'text-sm font-medium text-gray-700';
        logicLabel.textContent = 'Logic:';
        const logicSelect = document.createElement('select');
        logicSelect.className = 'form-select text-sm border-gray-300 rounded-md rule-logic-select';
        ['AND', 'OR'].forEach((v) => {
            const opt = document.createElement('option');
            opt.value = v;
            opt.textContent = v;
            logicSelect.appendChild(opt);
        });
        logicRow.append(logicLabel, logicSelect);

        const conditionsContainer = document.createElement('div');
        conditionsContainer.className = 'rule-conditions-container';

        const addConditionBtn = document.createElement('button');
        addConditionBtn.type = 'button';
        addConditionBtn.className =
            'inline-flex items-center px-3 py-1 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 add-condition-btn';
        {
            const icon = document.createElement('i');
            icon.className = 'fas fa-plus w-3 h-3 mr-1';
            addConditionBtn.append(icon, document.createTextNode(' Add Condition'));
        }

        root.append(logicRow, conditionsContainer, addConditionBtn);
        containerElement.appendChild(root);

        // Initialize with existing rule data if provided
        if (ruleJson) {
            try {
                let rule;
                if (typeof ruleJson === 'string') {
                    try {
                        rule = JSON.parse(ruleJson);

                        // Check if the result is still a string (double-encoded JSON)
                        if (typeof rule === 'string') {
                            try {
                                rule = JSON.parse(rule);
                            } catch (secondParseError) {
                                // If it's still a string and not valid JSON, treat it as a malformed rule
                                rule = null;
                            }
                        }
                    } catch (parseError) {
                        rule = null; // Set to null instead of fallback to string
                    }
                } else {
                    rule = ruleJson;
                }

                // Only proceed if we have a valid rule object
                if (rule && typeof rule === 'object' && rule !== null) {
                    rule = collapseCountryEquals(rule);
                    if (rule.logic) {
                        logicSelect.value = rule.logic;
                    }

                    if (rule.conditions && rule.conditions.length > 0) {
                        rule.conditions.forEach((condition, index) => {
                            this.addConditionLine(conditionsContainer, ruleType, condition, currentItemId);
                        });
                    }
                }
            } catch (error) {
                // Silently handle parsing errors
            }
        }

        // Add event listeners
        addConditionBtn.addEventListener('click', () => {
            this.addConditionLine(conditionsContainer, ruleType, null, currentItemId);
        });
    },

    // Add a new condition line to the rule builder
    addConditionLine(conditionsContainer, ruleType, conditionData = null, currentItemId = null) {
        if (!conditionsContainer) {
            return;
        }

        const conditionDiv = document.createElement('div');
        conditionDiv.className = 'flex items-center space-x-2 mb-2 condition-line';
        const itemSelect = document.createElement('select');
        itemSelect.className = 'form-select block w-1/3 text-sm border-gray-300 rounded-md rule-item-select';
        itemSelect.style.maxWidth = '300px';
        {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = _t('Select Item...');
            itemSelect.appendChild(opt);
        }

        const conditionTypeSelect = document.createElement('select');
        conditionTypeSelect.className = 'form-select block w-1/4 text-sm border-gray-300 rounded-md rule-condition-type-select';
        {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'Select Condition...';
            conditionTypeSelect.appendChild(opt);
        }

        const valueContainer = document.createElement('div');
        valueContainer.className = 'w-1/3 rule-value-container';
        const valueInput = document.createElement('input');
        valueInput.type = 'text';
        valueInput.className = 'form-input block w-full text-sm border-gray-300 rounded-md rule-value-input';
        valueInput.placeholder = 'Value';
        valueContainer.appendChild(valueInput);

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'remove-condition-btn fb-icon-btn fb-icon-btn--danger';
        {
            const icon = document.createElement('i');
            icon.className = 'fas fa-times-circle w-5 h-5';
            removeBtn.appendChild(icon);
        }

        conditionDiv.append(itemSelect, conditionTypeSelect, valueContainer, removeBtn);

        conditionsContainer.appendChild(conditionDiv);

        // Add event listeners
        removeBtn.addEventListener('click', () => {
            destroyCountrySelect(conditionDiv);
            conditionDiv.remove();
        });

        // Populate item select and set up change handlers
        this.populateItemSelect(itemSelect, ruleType, currentItemId);

        // Set up change handlers
        itemSelect.addEventListener('change', () => {
            this.updateConditionTypeSelect(conditionTypeSelect, valueContainer, itemSelect.value, ruleType);
        });

        conditionTypeSelect.addEventListener('change', () => {
            this.updateValueInput(valueContainer, itemSelect.value, conditionTypeSelect.value, null, null, currentItemId);
        });

        // Populate with existing data if provided
        if (conditionData) {
            let itemIdForDropdown = conditionData.item_id || '';
            let foundMatch = false;

            // First, try to set the value directly (in case it's already in the correct format)
            if (itemIdForDropdown) {
                itemSelect.value = itemIdForDropdown;
                if (itemSelect.value === itemIdForDropdown) {
                    foundMatch = true;
                }
            }

            // If direct match failed and it's a numeric ID, try to find the prefixed option
            if (!foundMatch && itemIdForDropdown && !isNaN(itemIdForDropdown)) {
                const options = itemSelect.querySelectorAll('option');
                for (const option of options) {
                    if (option.value && option.value.includes(`_${itemIdForDropdown}`)) {
                        itemSelect.value = option.value;
                        foundMatch = true;
                        break;
                    }
                }
            }

            // If we found a match, update the dependent fields
            if (foundMatch && itemSelect.value) {
                this.updateConditionTypeSelect(conditionTypeSelect, valueContainer, itemSelect.value, ruleType);

                // Set condition type after a brief delay to ensure the dropdown is populated
                setTimeout(() => {
                    if (conditionData.condition_type) {
                        conditionTypeSelect.value = conditionData.condition_type;

                        // Always update the value input, regardless of whether there's a value
                        // This ensures no-value conditions are handled properly
                        // Check if this condition uses a field reference (value_field_id) or static value
                        const valueFieldId = conditionData.value_field_id !== null && conditionData.value_field_id !== undefined
                            ? conditionData.value_field_id
                            : null;
                        this.updateValueInput(valueContainer, itemSelect.value, conditionData.condition_type, conditionData.value, valueFieldId, currentItemId);
                    }
                }, 50);
            }
        }
    },

    // Populate item select dropdown
    populateItemSelect(selectElement, ruleType, currentItemId = null) {
        const allItems = DataManager.getData('allTemplateItems') || [];
        const metadataOptions = getBuiltInMetadataOptions();

        // Clear existing options
        selectElement.replaceChildren();
        {
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = _t('Select Item...');
            selectElement.appendChild(placeholder);
        }

        // Add Metadata group first
        if (metadataOptions.length > 0) {
            const og = document.createElement('optgroup');
            og.label = 'Metadata';
            metadataOptions.forEach(meta => {
                const opt = document.createElement('option');
                opt.value = meta.key; // store as token key (e.g. "entity_name")
                opt.textContent = `${meta.label}`;
                opt.dataset.itemType = meta.valueType;
                opt.dataset.itemModel = 'metadata';
                og.appendChild(opt);
            });
            selectElement.appendChild(og);
        }

        // Get items to use (either original or reloaded)
        let itemsToUse = allItems;

        // If no items are available, try to force reload the data
        if (allItems.length === 0) {
            DataManager.loadAllTemplateItems();
            const reloadedItems = DataManager.getData('allTemplateItems') || [];
            if (reloadedItems.length > 0) {
                itemsToUse = reloadedItems;
            }
        }

        // Helper function to create an option element
        const createOption = (item, isCurrentItem = false) => {
            if (item.item_model !== 'plugin') {
                const option = document.createElement('option');
                option.value = item.id;

                // Extract the numeric ID from the prefixed format for display
                let displayId = item.id;
                const match = item.id.match(/^(question_|indicator_|document_field_|matrix_|form_item_)(\d+)$/);
                if (match) {
                    displayId = match[2]; // Use just the numeric part
                }

                // Handle item type display - use item_model as fallback for document fields
                let displayType = item.type || item.item_model || 'Unknown';
                if (displayType === 'null' || displayType === null) {
                    // For document fields, use a more descriptive type
                    if (item.id && item.id.startsWith('document_field_')) {
                        displayType = 'Document';
                    } else if (item.id && item.id.startsWith('question_')) {
                        displayType = 'Question';
                    } else if (item.id && item.id.startsWith('indicator_')) {
                        displayType = 'Indicator';
                    } else if (item.id && item.id.startsWith('matrix_')) {
                        displayType = 'Matrix';
                    } else if (item.id && item.id.startsWith('form_item_')) {
                        // For form_item_ prefix, try to infer type from item.type or use a generic name
                        displayType = item.type || 'Item';
                    } else {
                        displayType = 'Item';
                    }
                }

                // Override specific item_model values for better display
                if (displayType === 'document_field' || displayType === 'Document Field') {
                    displayType = 'Document';
                } else if (displayType === 'question' || displayType === 'Question') {
                    displayType = 'Question';
                } else if (displayType === 'indicator' || displayType === 'Indicator') {
                    displayType = 'Indicator';
                } else if (displayType === 'matrix' || displayType === 'Matrix') {
                    displayType = 'Matrix';
                } else if (displayType === 'form_item') {
                    // For form_item model, use the actual type if available, otherwise use a generic name
                    displayType = item.type || 'Item';
                }

                // Format: "ID: Type: Label" (e.g., "66: Question: If answered yes...")
                // Truncate very long labels to prevent dropdown from being too wide
                let displayLabel = item.label;
                if (displayLabel.length > 80) {
                    displayLabel = displayLabel.substring(0, 77) + '...';
                }

                let textContent = `${displayId}: ${displayType}: ${displayLabel}`;
                if (isCurrentItem) {
                    // Add "(Current item)" in italic style indicator
                    textContent = `→ ${textContent} (Current item)`;
                    option.style.fontStyle = 'italic';
                    option.dataset.isCurrentItem = 'true';
                }

                option.textContent = textContent;
                option.dataset.itemType = item.type || item.item_model || '';
                option.dataset.itemModel = item.item_model || item.model || '';
                option.title = `${displayId}: ${displayType}: ${item.label}${isCurrentItem ? ' (Current item)' : ''}`;
                return option;
            } else {
                // Handle plugin items and their measures
                const pluginType = item.plugin_type || 'unknown';
                const measures = item.plugin_measures || [];
                const options = [];

                // Add the main plugin item
                const pluginOption = document.createElement('option');
                pluginOption.value = item.id;
                const displayPluginType = pluginType.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
                let pluginText = `${item.id.replace('plugin_', '')}: Plugin (${displayPluginType}): ${item.label}`;
                if (isCurrentItem) {
                    pluginText = `→ ${pluginText} (Current item)`;
                    pluginOption.style.fontStyle = 'italic';
                    pluginOption.dataset.isCurrentItem = 'true';
                }
                pluginOption.textContent = pluginText;
                pluginOption.dataset.itemType = 'plugin';
                pluginOption.dataset.itemModel = 'plugin';
                pluginOption.dataset.pluginType = pluginType;
                pluginOption.title = `${item.id.replace('plugin_', '')}: Plugin (${displayPluginType}): ${item.label}${isCurrentItem ? ' (Current item)' : ''}`;
                options.push(pluginOption);

                // Add each measure as a separate option
                measures.forEach(measure => {
                    const measureOption = document.createElement('option');
                    measureOption.value = `${item.id}_${measure.id}`;
                    let measureText = `${item.id.replace('plugin_', '')}: ${measure.name}: ${item.label}`;
                    if (isCurrentItem) {
                        measureText = `→ ${measureText} (Current item)`;
                        measureOption.style.fontWeight = 'bold';
                        measureOption.style.fontStyle = 'italic';
                        measureOption.dataset.isCurrentItem = 'true';
                    }
                    measureOption.textContent = measureText;
                    measureOption.dataset.itemType = 'plugin_measure';
                    measureOption.dataset.itemModel = 'plugin_measure';
                    measureOption.dataset.pluginType = pluginType;
                    measureOption.dataset.measureId = measure.id;
                    measureOption.dataset.dataAttribute = measure.data_attribute;
                    measureOption.dataset.valueType = measure.value_type;
                    measureOption.title = `${item.id.replace('plugin_', '')}: ${measure.name}: ${measure.description}${isCurrentItem ? ' (Current item)' : ''}`;
                    options.push(measureOption);
                });

                return options;
            }
        };

        // Separate current item from others
        const currentItem = currentItemId ? itemsToUse.find(item => item.id === currentItemId) : null;
        const otherItems = itemsToUse.filter(item => !currentItemId || item.id !== currentItemId);

        // Add current item first if it exists
        if (currentItem) {
            const currentOptions = createOption(currentItem, true);
            const optionsArray = Array.isArray(currentOptions) ? currentOptions : [currentOptions];
            optionsArray.forEach(opt => {
                selectElement.appendChild(opt);
            });
        }

        // Add all other items
        otherItems.forEach(item => {
            const options = createOption(item, false);
            if (Array.isArray(options)) {
                options.forEach(opt => selectElement.appendChild(opt));
            } else {
                selectElement.appendChild(options);
            }
        });
    },

    // Update condition type select based on selected item
    updateConditionTypeSelect(selectElement, valueContainer, selectedItemId, ruleType) {
        if (!selectElement) return;

        // Retrieve meta info from the selected option
        const selectedOption = selectElement.closest('div.condition-line')?.querySelector(`.rule-item-select option[value="${selectedItemId}"]`);
        const itemType = selectedOption?.dataset.itemType;
        const itemModel = selectedOption?.dataset.itemModel;

        let applicableConditionTypes = [];

        if (itemModel === 'metadata') {
            // Metadata tokens behave like simple text/number values
            if (itemType === 'Number') {
                applicableConditionTypes = conditionTypesMap['Number'];
            } else {
                applicableConditionTypes = conditionTypesMap['text'];
            }
        } else if (itemModel === 'indicator') {
            switch (itemType) {
                case 'yesno':
                case 'YesNo':
                case 'yes_no':
                    applicableConditionTypes = conditionTypesMap['yesno'];
                    break;
                case 'text':
                    applicableConditionTypes = conditionTypesMap['text'];
                    break;
                case 'date':
                    applicableConditionTypes = conditionTypesMap['date'];
                    break;
                default:
                    applicableConditionTypes = conditionTypesMap['Number'];
            }
        } else if (itemModel === 'question') {
            switch (itemType) {
                case 'number':
                    applicableConditionTypes = conditionTypesMap['Number'];
                    break;
                case 'yesno':
                case 'YesNo':
                case 'yes_no':
                    applicableConditionTypes = conditionTypesMap['yesno'];
                    break;
                case 'text':
                    applicableConditionTypes = conditionTypesMap['text'];
                    break;
                case 'single_choice':
                    applicableConditionTypes = conditionTypesMap['single_choice'];
                    break;
                case 'multiple_choice':
                    applicableConditionTypes = conditionTypesMap['multiple_choice'];
                    break;
                case 'textarea':
                    applicableConditionTypes = conditionTypesMap['textarea'];
                    break;
                default:
                    applicableConditionTypes = conditionTypesMap['text'];
            }
        } else if (itemModel === 'document_field') {
            applicableConditionTypes = conditionTypesMap['document'];
        } else if (itemModel === 'plugin' || itemModel === 'plugin_measure') {
            // Handle plugin items and their measures
            const valueType = selectedOption?.dataset.valueType || 'number';
            if (valueType === 'number') {
                applicableConditionTypes = conditionTypesMap['Number'];
            } else {
                applicableConditionTypes = conditionTypesMap['text'];
            }
        } else {
            // Fallback
            applicableConditionTypes = conditionTypesMap['text'];
        }

        // Populate select options
        selectElement.replaceChildren();
        {
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select Condition...';
            selectElement.appendChild(placeholder);
        }
        applicableConditionTypes.forEach(type => {
            const option = document.createElement('option');
            option.value = type.value;
            option.textContent = type.label;
            selectElement.appendChild(option);
        });
    },

    // Update value input based on condition type
    updateValueInput(containerElement, selectedItemId, selectedConditionType, existingValue = null, existingValueFieldId = null, currentItemId = null) {
        if (!containerElement) return;

        // Identify selected option meta
        const conditionLine = containerElement.closest('.condition-line');
        const itemSelect = conditionLine?.querySelector('.rule-item-select');
        const selectedOption = itemSelect?.querySelector(`option[value="${selectedItemId}"]`);
        const itemType = selectedOption?.dataset.itemType;
        const itemModel = selectedOption?.dataset.itemModel;

        destroyCountrySelect(containerElement);
        if (conditionLine) {
            conditionLine.style.flexWrap = '';
            conditionLine.style.alignItems = '';
        }
        containerElement.style.flex = '';
        containerElement.style.width = '';
        containerElement.style.minWidth = '';

        // Special no-value conditions
        const noValueConditions = ['is_empty', 'is_not_empty', 'is_yes', 'is_no'];
        if (noValueConditions.includes(selectedConditionType)) {
            containerElement.replaceChildren();
            const span = document.createElement('span');
            span.className = 'text-gray-500 text-sm';
            span.textContent = 'No value needed';
            containerElement.appendChild(span);
            return;
        }

        if (MEMBERSHIP_TYPES.has(selectedConditionType)) {
            containerElement.replaceChildren();
            if (COUNTRY_METADATA_KEYS.has(selectedItemId)) {
                if (conditionLine) conditionLine.style.alignItems = 'flex-start';
                const picker = buildCountryPicker(selectedItemId, existingValue);
                containerElement.appendChild(picker);
                if (conditionLine && picker._sheet) {
                    conditionLine.insertAdjacentElement('afterend', picker._sheet);
                }
                return;
            }
            const listInput = document.createElement('input');
            listInput.type = 'text';
            listInput.placeholder = _t('Separate values with commas');
            listInput.className = 'form-input block w-full text-sm border-gray-300 rounded-md rule-value-input';
            listInput.dataset.valueList = 'true';
            const existingList = membershipList(existingValue);
            if (existingList.length) listInput.value = existingList.join(', ');
            containerElement.appendChild(listInput);
            return;
        }

        containerElement.style.flex = '';
        containerElement.style.width = '';
        containerElement.style.minWidth = '';
        // Clear container first
        containerElement.replaceChildren();

        // Create wrapper for value source selection
        const valueWrapper = document.createElement('div');
        valueWrapper.className = 'w-full space-y-2';

        // Create dropdown to select between static value and field reference
        const valueSourceSelect = document.createElement('select');
        valueSourceSelect.className = 'form-select block w-full text-sm border-gray-300 rounded-md rule-value-source-select mb-2';

        const customValueOpt = document.createElement('option');
        customValueOpt.value = 'static';
        customValueOpt.textContent = 'Static value';
        valueSourceSelect.appendChild(customValueOpt);

        const fieldRefOpt = document.createElement('option');
        fieldRefOpt.value = 'field';
        fieldRefOpt.textContent = 'Field reference';
        valueSourceSelect.appendChild(fieldRefOpt);

        // Create field reference dropdown (hidden initially)
        const fieldRefSelect = document.createElement('select');
        fieldRefSelect.className = 'form-select block w-full text-sm border-gray-300 rounded-md rule-value-field-select';
        fieldRefSelect.style.display = 'none';

        // Populate field reference dropdown
        const allItems = DataManager.getData('allTemplateItems') || [];
        const placeholderOpt = document.createElement('option');
        placeholderOpt.value = '';
        placeholderOpt.textContent = 'Select field...';
        fieldRefSelect.appendChild(placeholderOpt);

        allItems.forEach(item => {
            // Don't include the current item or the item being compared
            if (currentItemId && item.id === currentItemId) return;
            if (selectedItemId && item.id === selectedItemId) return;

            if (item.item_model !== 'plugin') {
                const option = document.createElement('option');
                option.value = item.id;

                // Extract numeric ID for display
                let displayId = item.id;
                const match = item.id.match(/^(question_|indicator_|document_field_|matrix_|form_item_)(\d+)$/);
                if (match) {
                    displayId = match[2];
                }

                let displayType = item.type || item.item_model || 'Unknown';
                if (displayType === 'null' || displayType === null) {
                    if (item.id && item.id.startsWith('document_field_')) {
                        displayType = 'Document';
                    } else if (item.id && item.id.startsWith('question_')) {
                        displayType = 'Question';
                    } else if (item.id && item.id.startsWith('indicator_')) {
                        displayType = 'Indicator';
                    } else if (item.id && item.id.startsWith('matrix_')) {
                        displayType = 'Matrix';
                    } else if (item.id && item.id.startsWith('form_item_')) {
                        // For form_item_ prefix, try to infer type from item.type or use a generic name
                        displayType = item.type || 'Item';
                    }
                }

                // Override specific item_model values for better display
                if (displayType === 'document_field' || displayType === 'Document Field') {
                    displayType = 'Document';
                } else if (displayType === 'question' || displayType === 'Question') {
                    displayType = 'Question';
                } else if (displayType === 'indicator' || displayType === 'Indicator') {
                    displayType = 'Indicator';
                } else if (displayType === 'matrix' || displayType === 'Matrix') {
                    displayType = 'Matrix';
                } else if (displayType === 'form_item') {
                    // For form_item model, use the actual type if available, otherwise use a generic name
                    displayType = item.type || 'Item';
                }

                let displayLabel = item.label;
                if (displayLabel.length > 60) {
                    displayLabel = displayLabel.substring(0, 57) + '...';
                }

                option.textContent = `${displayId}: ${displayType}: ${displayLabel}`;
                fieldRefSelect.appendChild(option);
            }
        });

        // Build appropriate input/select for static value
        let valueInput;

        // Yes/No select for yesno items
        if ((itemModel === 'question' && itemType === 'yesno') || (itemModel === 'indicator' && itemType === 'yesno')) {
            valueInput = document.createElement('select');
            valueInput.className = 'form-select block w-full text-sm border-gray-300 rounded-md rule-value-input';

            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select Option...';
            valueInput.appendChild(placeholder);

            const yesOpt = document.createElement('option');
            yesOpt.value = 'yes';
            yesOpt.textContent = _t('Yes');
            if (existingValue === 'yes') yesOpt.selected = true;
            valueInput.appendChild(yesOpt);

            const noOpt = document.createElement('option');
            noOpt.value = 'no';
            noOpt.textContent = _t('No');
            if (existingValue === 'no') noOpt.selected = true;
            valueInput.appendChild(noOpt);
        } else if (itemModel === 'question' && (itemType === 'single_choice' || itemType === 'multiple_choice')) {
            // Choice list select
            valueInput = document.createElement('select');
            valueInput.className = 'form-select block w-full text-sm border-gray-300 rounded-md rule-value-input';

            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select Option...';
            valueInput.appendChild(placeholder);

            // Retrieve question options
            const questionItem = allItems.find(i => i.id == selectedItemId);
            const optionsArray = questionItem?.options || [];
            optionsArray.forEach(opt => {
                const optEl = document.createElement('option');
                optEl.value = opt;
                optEl.textContent = opt;
                if (existingValue === opt) optEl.selected = true;
                valueInput.appendChild(optEl);
            });
        } else if (itemModel === 'indicator' || (itemModel === 'question' && itemType === 'number')) {
            // Number input
            valueInput = document.createElement('input');
            valueInput.type = 'number';
            valueInput.placeholder = 'Enter value...';
            valueInput.className = 'form-input block w-full text-sm border-gray-300 rounded-md rule-value-input';
            if (existingValue !== null && existingValue !== undefined) valueInput.value = existingValue;
        } else {
            // Default text input
            valueInput = document.createElement('input');
            valueInput.type = 'text';
            valueInput.placeholder = 'Enter value...';
            valueInput.className = 'form-input block w-full text-sm border-gray-300 rounded-md rule-value-input';
            if (existingValue !== null && existingValue !== undefined) valueInput.value = existingValue;
        }

        // Handle existing value: determine if it's a field reference or static value
        if (existingValueFieldId !== null && existingValueFieldId !== undefined) {
            // This is a field reference
            valueSourceSelect.value = 'field';
            fieldRefSelect.style.display = 'block';
            valueInput.style.display = 'none';

            // Find and select the matching field
            const options = fieldRefSelect.querySelectorAll('option');
            for (const option of options) {
                if (option.value) {
                    const match = option.value.match(/^(question_|indicator_|document_field_|matrix_|form_item_)(\d+)$/);
                    if (match && parseInt(match[2], 10) === parseInt(existingValueFieldId, 10)) {
                        fieldRefSelect.value = option.value;
                        break;
                    }
                }
            }
        } else {
            // This is a static value
            valueSourceSelect.value = 'static';
            fieldRefSelect.style.display = 'none';
            valueInput.style.display = 'block';
        }

        // Handle value source change
        valueSourceSelect.addEventListener('change', () => {
            if (valueSourceSelect.value === 'field') {
                fieldRefSelect.style.display = 'block';
                valueInput.style.display = 'none';
                valueInput.value = '';
            } else {
                fieldRefSelect.style.display = 'none';
                valueInput.style.display = 'block';
                fieldRefSelect.value = '';
            }
        });

        valueWrapper.appendChild(valueSourceSelect);
        valueWrapper.appendChild(fieldRefSelect);
        valueWrapper.appendChild(valueInput);
        containerElement.appendChild(valueWrapper);
    },

    // Serialize rule builder to JSON
    serializeRuleBuilder(containerElement) {
        if (!containerElement) return null;

        const logicSelect = containerElement.querySelector('.rule-logic-select');
        const conditionLines = containerElement.querySelectorAll('.condition-line');

        const conditions = [];
        conditionLines.forEach(line => {
            const itemSelect = line.querySelector('.rule-item-select');
            const conditionTypeSelect = line.querySelector('.rule-condition-type-select');
            const valueSourceSelect = line.querySelector('.rule-value-source-select');
            const valueInput = line.querySelector('.rule-value-input');
            const valueFieldSelect = line.querySelector('.rule-value-field-select');

            if (itemSelect.value && conditionTypeSelect.value) {
                // Extract numeric ID from prefixed format (e.g., "question_66" -> "66" or "form_item_967" -> "967")
                let itemId = itemSelect.value;
                const match = itemId.match(/^(question_|indicator_|document_field_|matrix_|form_item_)(\d+)$/);
                if (match) {
                    itemId = match[2]; // Use just the numeric part
                }

                const condition = {
                    item_id: itemId,
                    condition_type: conditionTypeSelect.value
                };

                // Check if using field reference or static value
                if (valueSourceSelect && valueSourceSelect.value === 'field' && valueFieldSelect && valueFieldSelect.value) {
                    // Field reference selected - extract numeric ID
                    let fieldId = valueFieldSelect.value;
                    const fieldMatch = fieldId.match(/^(question_|indicator_|document_field_|matrix_|form_item_)(\d+)$/);
                    if (fieldMatch) {
                        fieldId = parseInt(fieldMatch[2], 10);
                    }
                    condition.value_field_id = fieldId;
                } else {
                    const staticValue = readStaticRuleValue(valueInput);
                    if (staticValue !== undefined) {
                        condition.value = staticValue;
                    }
                }

                conditions.push(condition);
            }
        });

        if (conditions.length === 0) return null;

        const ruleObject = {
            logic: logicSelect.value || 'AND',
            conditions: conditions
        };

        return JSON.stringify(ruleObject);
    },

    // Handle rule builder toggle
    handleRuleBuilderToggle(button, modal) {
        const targetSelector = button.getAttribute('data-target');
        const targetElement = modal.querySelector(targetSelector);
        const rightHalf = modal.querySelector('.modal-right-half');

        if (!targetElement || !rightHalf) return;

        // Toggle visibility
        Utils.toggleElement(targetElement);

        // Hide the right half if no rules are visible
        const visibleRules = rightHalf.querySelectorAll('.rule-section:not(.hidden), div[id$="-rule-section"]:not(.hidden)');
        if (visibleRules.length === 0) {
            Utils.hideElement(rightHalf);
            modal.classList.remove('md:grid-cols-2');
            // Revert modal width when no rule sections are visible
            const modalContent = modal.closest('.relative.p-6');
            if (modalContent) {
                modalContent.classList.remove('max-w-6xl');
                modalContent.classList.remove('max-w-4xl');
                modalContent.classList.add('max-w-xl');
            }
        } else {
            Utils.showElement(rightHalf);
            modal.classList.add('md:grid-cols-2');
            // Expand modal width when a rule section is shown
            const modalContent = modal.closest('.relative.p-6');
            if (modalContent) {
                modalContent.classList.remove('max-w-xl');
                modalContent.classList.remove('max-w-4xl');
                modalContent.classList.add('max-w-6xl');
            }
        }

        // Initialize rule builder if not already initialized
        const ruleBuilder = targetElement.querySelector('.rule-builder') || targetElement.querySelector('[id$="-rule-builder"]');
        if (ruleBuilder && ruleBuilder.innerHTML.trim() === '') {
            const ruleType = targetSelector.includes('validation') ? 'validation' : 'relevance';
            // Attempt to retrieve pre-existing rule JSON stored on the element
            let existingRuleJson = ruleBuilder.getAttribute('data-rule-json');
            if (existingRuleJson && existingRuleJson.trim() !== '' && existingRuleJson !== 'null' && existingRuleJson !== '{}') {
                try {
                    // Ensure parsable JSON – leave as string for renderRuleBuilder
                    JSON.parse(existingRuleJson);
            } catch (error) {
                existingRuleJson = null;
            }
            } else {
                existingRuleJson = null;
            }

            // Get current item ID from ItemModal and convert to prefixed format
            let currentItemId = null;
            if (window.ItemModal && window.ItemModal.currentItemId) {
                const numericId = window.ItemModal.currentItemId;
                const itemType = window.ItemModal.currentItemType || 'question';

                // Convert to prefixed format based on item type
                if (itemType === 'indicator') {
                    currentItemId = `indicator_${numericId}`;
                } else if (itemType === 'question') {
                    currentItemId = `question_${numericId}`;
                } else if (itemType === 'document_field') {
                    currentItemId = `document_field_${numericId}`;
                } else if (itemType === 'matrix') {
                    currentItemId = `matrix_${numericId}`;
                } else if (itemType && itemType.startsWith('plugin_')) {
                    currentItemId = `plugin_${numericId}`;
                } else {
                    // Try to find the item in allTemplateItems to get the correct prefix
                    const allItems = DataManager.getData('allTemplateItems') || [];
                    const foundItem = allItems.find(item => {
                        const match = item.id && item.id.match(/^.+_(\d+)$/);
                        return match && parseInt(match[1], 10) === parseInt(numericId, 10);
                    });
                    if (foundItem) {
                        currentItemId = foundItem.id;
                    } else {
                        // Fallback to question_ prefix
                        currentItemId = `question_${numericId}`;
                    }
                }
            }

            this.renderRuleBuilder(ruleBuilder, existingRuleJson, ruleType, currentItemId);
        }
    }
};

// Export for use in main.js
export default RuleBuilder;
