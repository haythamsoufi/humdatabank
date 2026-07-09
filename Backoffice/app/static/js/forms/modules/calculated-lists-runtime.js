import { debugLog, debugWarn, debugError } from './debug.js';
import { getFieldValue, getCurrentFieldValue } from './field-management.js';
import { appendOtherOptionToSelect, appendOtherOptionToMultiDropdown } from './question-other-option.js';

const MODULE = 'calculated-lists-runtime';

/** EmOps type-filter tracing (filter DevTools console by "[EmOpsFilter]"). Gated by calculated-lists-runtime debug module. */
function traceEmOpsFilter(fieldId, step, detail) {
    const id = fieldId != null && fieldId !== '' ? String(fieldId) : '?';
    if (detail !== undefined) {
        debugLog(MODULE, `[EmOpsFilter] field=${id} | ${step}`, detail);
    } else {
        debugLog(MODULE, `[EmOpsFilter] field=${id} | ${step}`);
    }
}

function summarizeEmOpsTypes(rows) {
    const counts = {};
    (rows || []).forEach((row) => {
        const t = row && row.type != null ? String(row.type) : '(missing type)';
        counts[t] = (counts[t] || 0) + 1;
    });
    return counts;
}

/** Coerce API/list row values to safe display strings (never "[object Object]"). */
function scalarDisplayText(value) {
    if (value == null || value === '') return '';
    if (typeof value === 'string') {
        const trimmed = value.trim();
        return trimmed === '[object Object]' ? '' : trimmed;
    }
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    if (typeof value === 'object') {
        const name = scalarDisplayText(value.name ?? value.label ?? value.title);
        const code = scalarDisplayText(value.code ?? value.id);
        if (name && code) return `${name} (${code})`;
        return name || code || '';
    }
    const text = String(value);
    return text === '[object Object]' ? '' : text;
}

function formatEmergencyOperationLabel(row) {
    if (!row || typeof row !== 'object') return '';
    const combined = scalarDisplayText(row.name_with_code);
    if (combined) return combined;
    const name = scalarDisplayText(row.name);
    const code = scalarDisplayText(row.code);
    if (name && code) return `${name} (${code})`;
    return name || code || '';
}

function resolveCalculatedListRowDisplay(row, displayColumn, lookupListId) {
    if (lookupListId === 'emergency_operations') {
        const preferred = formatEmergencyOperationLabel(row);
        if (preferred) return preferred;
        if (row && displayColumn && Object.prototype.hasOwnProperty.call(row, displayColumn)) {
            return scalarDisplayText(row[displayColumn]);
        }
        return '';
    }
    if (!row || !displayColumn || !Object.prototype.hasOwnProperty.call(row, displayColumn)) {
        return '';
    }
    return scalarDisplayText(row[displayColumn]);
}

// Deduplication + short-lived cache so concurrent repeat-entry selects that share
// the same lookup URL make exactly ONE network request instead of N.
const _pendingFetches = new Map(); // url → Promise<object>  (in-flight)
const _responseCache  = new Map(); // url → { json, ts }    (completed)
const CACHE_TTL_MS = 30_000;       // 30 s — covers rapid re-renders / Add Entry clicks

function cachedFetch(urlString) {
    const cached = _responseCache.get(urlString);
    if (cached && Date.now() - cached.ts < CACHE_TTL_MS) {
        debugLog(MODULE, `📦 Cache hit for ${urlString}`);
        return Promise.resolve(cached.json);
    }

    const inFlight = _pendingFetches.get(urlString);
    if (inFlight) {
        debugLog(MODULE, `🔗 Sharing in-flight request for ${urlString}`);
        return inFlight;
    }

    const fetchFn = (window.getFetch && window.getFetch()) || fetch;
    const promise = fetchFn(urlString, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(response => {
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return response.json();
        })
        .then(json => {
            _responseCache.set(urlString, { json, ts: Date.now() });
            _pendingFetches.delete(urlString);
            return json;
        })
        .catch(err => {
            _pendingFetches.delete(urlString);
            throw err;
        });

    _pendingFetches.set(urlString, promise);
    return promise;
}

/** Resolve ISO code for the assignment's country (used by Emergency Operations list). */
function resolveAssignedCountryIso() {
    const ctx = window.metadataContext;
    if (ctx) {
        const fromCtx = String(ctx.country_iso || ctx.country_iso2 || '').trim();
        if (fromCtx) {
            return fromCtx.toUpperCase();
        }
    }

    const countryIsoElement = document.querySelector('[data-country-iso]');
    if (countryIsoElement && countryIsoElement.dataset.countryIso) {
        return countryIsoElement.dataset.countryIso.trim().toUpperCase();
    }

    const urlParams = new URLSearchParams(window.location.search);
    const countryParam = urlParams.get('country') || urlParams.get('iso');
    if (countryParam) {
        return countryParam.toUpperCase();
    }

    if (window.countryInfo) {
        const fromInfo = window.countryInfo.iso || window.countryInfo.iso3;
        if (fromInfo) {
            return String(fromInfo).toUpperCase();
        }
    }

    return null;
}

export function initCalculatedLists() {
    debugLog(MODULE, '🚀 Starting calculated lists initialization...');
    debugLog(MODULE, '🔄 Initializing calculated lists runtime support...');

    // Function to check if we're ready to initialize
    const checkAndInit = () => {
        debugLog(MODULE, '🔍 Checking if ready to initialize...');
        debugLog(MODULE, 'DOM ready state:', document.readyState);
        debugLog(MODULE, 'window.existingData available:', !!window.existingData);

        const existingDataReady = window.existingData && typeof window.existingData === 'object';
        if (existingDataReady) {
            const dataKeys = Object.keys(window.existingData);
            debugLog(MODULE, 'existingData keys count:', dataKeys.length);
            debugLog(MODULE, 'existingData sample keys:', dataKeys.slice(0, 5));
        }

        if (document.readyState !== 'loading' && existingDataReady) {
            debugLog(MODULE, '✅ Ready to initialize - existing data available');
            initCalculatedListsCore();
        } else {
            debugLog(MODULE, '⏳ Not ready yet, will retry in 50ms...');
            setTimeout(checkAndInit, 50);
        }
    };

    // Wait for DOM to be fully ready before initializing
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            debugLog(MODULE, '📄 DOM content loaded, checking for existing data...');
            checkAndInit();
        });
    } else {
        // DOM is already ready, check for existing data
        checkAndInit();
    }
}

function initCalculatedListsCore() {
    debugLog(MODULE, '🎯 Initializing calculated lists core...');

    // Handle both select elements and multi-select divs
    const selectElements = document.querySelectorAll('select[data-options-source="calculated"]');
    const multiSelectElements = document.querySelectorAll('div[data-options-source="calculated"]');

    debugLog(MODULE, `Found ${selectElements.length} calculated select elements:`, selectElements);
    debugLog(MODULE, `Found ${multiSelectElements.length} calculated multi-select elements:`, multiSelectElements);

    // Log details of each element
    selectElements.forEach((sel, index) => {
        debugLog(MODULE, `Select ${index + 1}:`, {
            id: sel.id,
            name: sel.name,
            lookupListId: sel.dataset.lookupListId,
            displayColumn: sel.dataset.displayColumn,
            filters: sel.dataset.listFilters
        });
    });

    multiSelectElements.forEach((div, index) => {
        debugLog(MODULE, `Multi-select ${index + 1}:`, {
            id: div.id,
            lookupListId: div.dataset.lookupListId,
            displayColumn: div.dataset.displayColumn,
            filters: div.dataset.listFilters
        });
    });

    selectElements.forEach(sel => setupCalculatedSelect(sel));
    multiSelectElements.forEach(div => setupCalculatedMultiSelect(div));

    // Set up a global listener for all form changes to catch missed dependencies
    setupGlobalCalculatedListsListener();

    debugLog(MODULE, '✅ Calculated lists initialization complete');

    // Expose refresh helpers globally so repeat-sections.js can trigger option loads
    // for dynamically cloned calculated-list selects.
    window.refreshCalculatedSelect = refreshCalculatedSelect;
    window.refreshCalculatedMultiSelect = refreshCalculatedMultiSelect;
    window.preserveCalculatedSelectStaleValue = markSelectStaleSavedValue;
    window.syncEmergencyOperationMetadata = syncEmergencyOperationMetadata;
}

function setupGlobalCalculatedListsListener() {
    debugLog(MODULE, '🌐 Setting up global calculated lists listener...');

    // Listen for all form changes
    document.addEventListener('change', (event) => {
        const changedElement = event.target;
        if (!changedElement.matches('input, select, textarea')) return;

        // Get the field ID from the element
        const fieldId = getFieldIdFromElement(changedElement);
        if (!fieldId) return;

        debugLog(MODULE, `🔄 Field ${fieldId} changed, checking for calculated lists that depend on it...`);

        // Find all calculated lists that might depend on this field
        const calculatedElements = document.querySelectorAll('[data-options-source="calculated"]');

        calculatedElements.forEach(element => {
            const filters = element.dataset.listFilters;
            if (!filters) return;

            try {
                const parsedFilters = JSON.parse(filters);
                const dependsOnChangedField = parsedFilters.some(filter =>
                    filter && typeof filter === 'object' &&
                    filter.value_field_id &&
                    filter.value_field_id.toString() === fieldId.toString()
                );

                if (dependsOnChangedField) {
                    debugLog(MODULE, `🎯 Found calculated list ${element.id} that depends on field ${fieldId}, refreshing...`);

                    // Refresh this calculated list
                    if (element.tagName === 'SELECT') {
                        refreshCalculatedSelect(element);
                    } else if (element.tagName === 'DIV') {
                        refreshCalculatedMultiSelect(element);
                    }
                }
            } catch (e) {
                debugWarn(MODULE, `Error checking dependencies for calculated list ${element.id}:`, e);
            }
        });
    });

    debugLog(MODULE, '✅ Global calculated lists listener set up');
}

function getFieldIdFromElement(element) {
    // Try to extract field ID from various naming patterns
    if (element.id && element.id.startsWith('field-')) {
        return element.id.replace('field-', '');
    }

    if (element.name) {
        // Handle field_value[123] pattern
        const match = element.name.match(/field_value\[(\d+)\]/);
        if (match) {
            return match[1];
        }

        // Handle indicator_123_total_value pattern
        const indicatorMatch = element.name.match(/indicator_(\d+)_/);
        if (indicatorMatch) {
            return indicatorMatch[1];
        }

        // Handle dynamic_123_total_value pattern
        const dynamicMatch = element.name.match(/dynamic_(\d+)_/);
        if (dynamicMatch) {
            return dynamicMatch[1];
        }
    }

    return null;
}

function refreshCalculatedSelect(selectElement) {
    const lookupListId = selectElement.dataset.lookupListId;
    const displayColumn = selectElement.dataset.displayColumn;
    let filters = [];

    try {
        filters = JSON.parse(selectElement.dataset.listFilters || '[]');
    } catch (e) {
        debugError(MODULE, `❌ Failed to parse filters for ${selectElement.id}:`, e);
        return;
    }

    if (lookupListId === 'emergency_operations') {
        attachEmergencyMetadataListener(selectElement);
        attachStaleSavedValueListener(selectElement);
    }

    const dependencyIds = filters
        .filter(f => f && typeof f === 'object' && 'value_field_id' in f && f.value_field_id !== null)
        .map(f => f.value_field_id);

    refreshSelectOptions(selectElement, lookupListId, displayColumn, filters, dependencyIds);
}

function refreshCalculatedMultiSelect(multiSelectDiv) {
    const lookupListId = multiSelectDiv.dataset.lookupListId;
    const displayColumn = multiSelectDiv.dataset.displayColumn;
    let filters = [];

    try {
        filters = JSON.parse(multiSelectDiv.dataset.listFilters || '[]');
    } catch (e) {
        debugError(MODULE, `❌ Failed to parse filters for ${multiSelectDiv.id}:`, e);
        return;
    }

    const dependencyIds = filters
        .filter(f => f && typeof f === 'object' && 'value_field_id' in f && f.value_field_id !== null)
        .map(f => f.value_field_id);

    const fieldId = multiSelectDiv.id.replace('field-', '');
    refreshMultiSelectOptions(multiSelectDiv, fieldId, lookupListId, displayColumn, filters, dependencyIds);
}

function setupCalculatedSelect(selectElement) {
    debugLog(MODULE, `🔧 Setting up calculated select: ${selectElement.id || selectElement.name}`);

    const lookupListId = selectElement.dataset.lookupListId;
    const displayColumn = selectElement.dataset.displayColumn;
    let filters = [];

    debugLog(MODULE, `Lookup List ID: ${lookupListId}`);
    debugLog(MODULE, `Display Column: ${displayColumn}`);
    debugLog(MODULE, `Raw filters: ${selectElement.dataset.listFilters}`);

    try {
        filters = JSON.parse(selectElement.dataset.listFilters || '[]');
        debugLog(MODULE, `Parsed filters:`, filters);
    } catch (e) {
        debugError(MODULE, `❌ Failed to parse filters for ${selectElement.id}:`, e);
        debugWarn(MODULE, 'Failed to parse listFilters for', selectElement, e);
    }

    // Identify dependencies (other field IDs referenced via value_field_id)
    const dependencyIds = filters
        .filter(f => f && typeof f === 'object' && 'value_field_id' in f && f.value_field_id !== null)
        .map(f => f.value_field_id);

    debugLog(MODULE, `Dependencies found:`, dependencyIds);

    const refresh = () => {
        debugLog(MODULE, `🔄 Refreshing options for ${selectElement.id || selectElement.name}`);
        refreshSelectOptions(selectElement, lookupListId, displayColumn, filters, dependencyIds);
    };

    // Attach listeners to dependency fields with retry mechanism
    dependencyIds.forEach(depId => {
        const attachListener = () => {
            const depEl = document.getElementById(`field-${depId}`);
            debugLog(MODULE, `Looking for dependency field: field-${depId}`, depEl);

            if (depEl) {
                const evt = (depEl.tagName.toLowerCase() === 'select' || depEl.type === 'checkbox' || depEl.type === 'radio') ? 'change' : 'input';
                debugLog(MODULE, `Adding ${evt} listener to field-${depId}`);

                depEl.addEventListener(evt, () => {
                    const newValue = getCurrentFieldValue(depId);
                    debugLog(MODULE, `🔔 DEPENDENCY CHANGED! Field ${depId} → new value:`, newValue);
                    debugLog(MODULE, `Triggering refresh for ${selectElement.id || selectElement.name}`);
                    debugLog(MODULE, `🔔 Dependency field ${depId} changed. New value =`, newValue);
                    refresh();
                });

                debugLog(MODULE, `✅ Event listener attached to field-${depId}`);
                return true;
            } else {
                debugWarn(MODULE, `⚠️ Dependency field not found: field-${depId}`);
                return false;
            }
        };

        // Try to attach listener immediately
        if (!attachListener()) {
            // If field not found, try again after a delay
            setTimeout(() => {
                if (!attachListener()) {
                    debugWarn(MODULE, `⚠️ Could not find dependency field after retry: field-${depId}`);
                }
            }, 500);
        }
    });

    // Initial population
    debugLog(MODULE, `Performing initial refresh for ${selectElement.id || selectElement.name}`);
    attachStaleSavedValueListener(selectElement);
    if (lookupListId === 'emergency_operations') {
        attachEmergencyMetadataListener(selectElement);
        // Defer the first EmOps fetch until the field is visible. The response is expensive
        // (~989 ms) and the field is often on a later page or below the fold. Once the first
        // fetch completes the normal dependency-change listeners handle subsequent refreshes.
        deferRefreshUntilVisible(selectElement, refresh);
    } else {
        refresh();
    }
}

/**
 * Defer the first options fetch for a calculated select until the element enters
 * the viewport (IntersectionObserver) or receives focus, whichever comes first.
 * After the first fetch, the observer is disconnected and normal change-event
 * listeners take over.
 *
 * @param {Element} el      The select element to observe.
 * @param {Function} refresh  The zero-argument function that triggers a fetch.
 */
function deferRefreshUntilVisible(el, refresh) {
    let fetched = false;

    function doFetch() {
        if (fetched) return;
        fetched = true;
        debugLog(MODULE, `[deferred] EmOps field now visible/focused, triggering initial refresh for ${el.id || el.name}`);
        if (observer) {
            try { observer.disconnect(); } catch (_) { /* no-op */ }
        }
        el.removeEventListener('focus', onFocus, true);
        refresh();
    }

    // IntersectionObserver fires when the element scrolls into view.
    let observer = null;
    if (typeof IntersectionObserver !== 'undefined') {
        observer = new IntersectionObserver((entries) => {
            if (entries.some(e => e.isIntersecting)) doFetch();
        }, { threshold: 0.1 });
        observer.observe(el);
    }

    // Focus fallback: covers fields on pagination pages that are shown via display:block
    // without a scroll event (IntersectionObserver may fire but selector may be off-screen).
    const onFocus = () => doFetch();
    el.addEventListener('focus', onFocus, true);

    // Safety net: fetch after a short idle period so the field is never left permanently
    // empty if the user never scrolls to it (e.g. single-page forms where intersection
    // fires immediately but page is very tall).
    if (typeof requestIdleCallback !== 'undefined') {
        requestIdleCallback(() => { if (!fetched) doFetch(); }, { timeout: 5000 });
    } else {
        setTimeout(() => { if (!fetched) doFetch(); }, 5000);
    }
}

function setupCalculatedMultiSelect(multiSelectDiv) {
    debugLog(MODULE, `🔧 Setting up calculated multi-select: ${multiSelectDiv.id}`);

    const lookupListId = multiSelectDiv.dataset.lookupListId;
    const displayColumn = multiSelectDiv.dataset.displayColumn;
    let filters = [];

    debugLog(MODULE, `Lookup List ID: ${lookupListId}`);
    debugLog(MODULE, `Display Column: ${displayColumn}`);
    debugLog(MODULE, `Raw filters: ${multiSelectDiv.dataset.listFilters}`);

    try {
        filters = JSON.parse(multiSelectDiv.dataset.listFilters || '[]');
        debugLog(MODULE, `Parsed filters:`, filters);
    } catch (e) {
        debugError(MODULE, `❌ Failed to parse filters for ${multiSelectDiv.id}:`, e);
        debugWarn(MODULE, 'Failed to parse listFilters for', multiSelectDiv, e);
    }

    // Identify dependencies (other field IDs referenced via value_field_id)
    const dependencyIds = filters
        .filter(f => f && typeof f === 'object' && 'value_field_id' in f && f.value_field_id !== null)
        .map(f => f.value_field_id);

    debugLog(MODULE, `Dependencies found:`, dependencyIds);

    const fieldId = multiSelectDiv.id.replace('field-', '');
    const refresh = () => {
        debugLog(MODULE, `🔄 Refreshing multi-select options for ${multiSelectDiv.id}`);
        refreshMultiSelectOptions(multiSelectDiv, fieldId, lookupListId, displayColumn, filters, dependencyIds);
    };

    // Attach listeners to dependency fields with retry mechanism
    dependencyIds.forEach(depId => {
        const attachListener = () => {
            const depEl = document.getElementById(`field-${depId}`);
            debugLog(MODULE, `Looking for dependency field: field-${depId}`, depEl);

            if (depEl) {
                const evt = (depEl.tagName.toLowerCase() === 'select' || depEl.type === 'checkbox' || depEl.type === 'radio') ? 'change' : 'input';
                debugLog(MODULE, `Adding ${evt} listener to field-${depId}`);

                depEl.addEventListener(evt, () => {
                    const newValue = getCurrentFieldValue(depId);
                    debugLog(MODULE, `🔔 DEPENDENCY CHANGED! Field ${depId} → new value:`, newValue);
                    debugLog(MODULE, `Triggering refresh for ${multiSelectDiv.id}`);
                    debugLog(MODULE, `🔔 Dependency field ${depId} changed. New value =`, newValue);
                    refresh();
                });

                debugLog(MODULE, `✅ Event listener attached to field-${depId}`);
                return true;
            } else {
                debugWarn(MODULE, `⚠️ Dependency field not found: field-${depId}`);
                return false;
            }
        };

        // Try to attach listener immediately
        if (!attachListener()) {
            // If field not found, try again after a delay
            setTimeout(() => {
                if (!attachListener()) {
                    debugWarn(MODULE, `⚠️ Could not find dependency field after retry: field-${depId}`);
                }
            }, 500);
        }
    });

    // Initial population
    debugLog(MODULE, `Performing initial refresh for ${multiSelectDiv.id}`);
    refresh();
}

function setSelectValueRobust(selectElement, value) {
    debugLog(MODULE, `🔧 Setting select value robustly: "${value}"`);

    // Set the value
    selectElement.value = value;

    // Trigger change event to notify other scripts
    const changeEvent = new Event('change', { bubbles: true });
    selectElement.dispatchEvent(changeEvent);

    // Also trigger input event for good measure
    const inputEvent = new Event('input', { bubbles: true });
    selectElement.dispatchEvent(inputEvent);

    syncEmergencyOperationMetadata(selectElement);

    debugLog(MODULE, `🔧 Select value set to: "${selectElement.value}" (events triggered)`);
}

function resolveCalculatedSelectFieldId(selectElement) {
    if (selectElement.dataset.fieldItemId) {
        return selectElement.dataset.fieldItemId;
    }
    const id = selectElement.id || '';
    const standardMatch = id.match(/^field-(\d+)$/);
    return standardMatch ? standardMatch[1] : null;
}

function parseEmergencyDisplayValue(value) {
    const text = String(value || '').trim();
    if (!text) return null;
    const match = text.match(/^(.+?)\s+\(([^)]+)\)\s*$/);
    if (match) {
        return { name: match[1].trim(), code: match[2].trim() };
    }
    return { name: text, code: '' };
}

function applyEmergencyRowToOption(option, row, displayValue) {
    const name = scalarDisplayText(row?.name);
    const code = scalarDisplayText(row?.code);
    if (name) option.dataset.emergencyName = name;
    if (code) option.dataset.emergencyCode = code;
    if (!option.dataset.emergencyName && !option.dataset.emergencyCode && displayValue) {
        const parsed = parseEmergencyDisplayValue(scalarDisplayText(displayValue));
        if (parsed) {
            if (parsed.name) option.dataset.emergencyName = parsed.name;
            if (parsed.code) option.dataset.emergencyCode = parsed.code;
        }
    }
}

function getEmergencyMetadataHiddenInputName(selectElement) {
    const fieldId = resolveCalculatedSelectFieldId(selectElement);
    const selectName = selectElement.name || '';
    if (selectName.startsWith('repeat_')) {
        return selectName.replace(/_\d+$/, '_emergency_metadata');
    }
    return fieldId ? `field_disagg_metadata[${fieldId}]` : null;
}

function findOrCreateEmergencyMetadataHiddenInput(selectElement) {
    const name = getEmergencyMetadataHiddenInputName(selectElement);
    if (!name) return null;

    const form = selectElement.form || selectElement.closest('form');
    if (!form) return null;

    for (const input of form.querySelectorAll('input[type="hidden"]')) {
        if (input.name === name) return input;
    }

    const hidden = document.createElement('input');
    hidden.type = 'hidden';
    hidden.name = name;
    hidden.value = '';
    form.appendChild(hidden);
    return hidden;
}

function extractEmergencyMetadataFromOption(option) {
    if (!option?.value) return null;

    const name = option.dataset.emergencyName?.trim() || '';
    const code = option.dataset.emergencyCode?.trim() || '';
    if (name || code) {
        if (name === '[object Object]') return null;
        return { name, code };
    }
    return parseEmergencyDisplayValue(option.value);
}

export function syncEmergencyOperationMetadata(selectElement) {
    if (selectElement.dataset.lookupListId !== 'emergency_operations') return;

    const hidden = findOrCreateEmergencyMetadataHiddenInput(selectElement);
    if (!hidden) return;

    if (!selectElement.value) {
        hidden.value = '';
        return;
    }

    const option = selectElement.options[selectElement.selectedIndex];
    const meta = extractEmergencyMetadataFromOption(option);
    hidden.value = meta ? JSON.stringify(meta) : '';
}

function attachEmergencyMetadataListener(selectElement) {
    if (selectElement.dataset.emergencyMetadataListenerAttached === 'true') return;
    selectElement.dataset.emergencyMetadataListenerAttached = 'true';
    selectElement.addEventListener('change', () => syncEmergencyOperationMetadata(selectElement));
}

const STALE_OPTION_SELECTOR = 'option[data-stale-saved-value="true"]';
const STALE_INDICATOR_CLASS = 'calculated-select-stale-indicator';

function getStaleSavedValueMessage() {
    const labels = window.CALCULATED_LIST_LABELS || {};
    return labels.staleSavedValueTooltip
        || 'Saved value is no longer in the current list. It will still be submitted unless you choose another option.';
}

function optionValueExists(selectElement, value) {
    return Array.from(selectElement.options).some((option) => option.value === value);
}

function appendStaleSavedOption(selectElement, value) {
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = value;
    opt.dataset.staleSavedValue = 'true';
    applyEmergencyRowToOption(opt, null, value);
    selectElement.appendChild(opt);
    return opt;
}

function findStaleSavedIndicator(selectElement) {
    const titleWrap = selectElement.closest('.repeat-entry__title-select-wrap');
    if (titleWrap) {
        return titleWrap.querySelector(`.${STALE_INDICATOR_CLASS}`);
    }
    const next = selectElement.nextElementSibling;
    if (next?.classList?.contains(STALE_INDICATOR_CLASS)) {
        return next;
    }
    return selectElement.parentElement?.querySelector(`.${STALE_INDICATOR_CLASS}`) || null;
}

function updateStaleSavedValueIndicator(selectElement) {
    const isStale = selectElement.dataset.staleSavedValue === 'true';
    let indicator = findStaleSavedIndicator(selectElement);

    if (!isStale) {
        indicator?.remove();
        selectElement.classList.remove('calculated-select--stale-saved', 'repeat-entry__title-select--stale-saved');
        return;
    }

    if (!indicator) {
        indicator = document.createElement('span');
        indicator.className = STALE_INDICATOR_CLASS;
        indicator.setAttribute('role', 'img');
        indicator.setAttribute('aria-label', getStaleSavedValueMessage());
        const icon = document.createElement('i');
        icon.className = 'fas fa-circle-exclamation';
        icon.setAttribute('aria-hidden', 'true');
        indicator.appendChild(icon);

        const titleWrap = selectElement.closest('.repeat-entry__title-select-wrap');
        if (titleWrap) {
            titleWrap.appendChild(indicator);
        } else {
            selectElement.insertAdjacentElement('afterend', indicator);
        }
    }

    indicator.title = getStaleSavedValueMessage();
    indicator.setAttribute('aria-label', getStaleSavedValueMessage());
    selectElement.classList.add('calculated-select--stale-saved');
    if (selectElement.classList.contains('repeat-entry__title-select')) {
        selectElement.classList.add('repeat-entry__title-select--stale-saved');
    }
}

function clearSelectStaleSavedValue(selectElement) {
    delete selectElement.dataset.staleSavedValue;
    selectElement.querySelectorAll(STALE_OPTION_SELECTOR).forEach((option) => option.remove());
    updateStaleSavedValueIndicator(selectElement);
}

function markSelectStaleSavedValue(selectElement, savedValue) {
    if (!savedValue) return;

    if (!optionValueExists(selectElement, savedValue)) {
        appendStaleSavedOption(selectElement, savedValue);
    }

    selectElement.value = savedValue;
    selectElement.dataset.staleSavedValue = 'true';
    updateStaleSavedValueIndicator(selectElement);
    debugLog(MODULE, `Preserved stale saved value "${savedValue}" with warning indicator`);
}

function handleCalculatedSelectChange(selectElement) {
    const selectedOption = selectElement.options[selectElement.selectedIndex];
    if (!selectedOption || selectedOption.dataset.staleSavedValue === 'true') {
        if (selectElement.value) {
            selectElement.dataset.staleSavedValue = 'true';
            updateStaleSavedValueIndicator(selectElement);
        }
        return;
    }

    clearSelectStaleSavedValue(selectElement);
}

function attachStaleSavedValueListener(selectElement) {
    if (selectElement.dataset.staleListenerAttached === 'true') {
        return;
    }
    selectElement.dataset.staleListenerAttached = 'true';
    selectElement.addEventListener('change', () => handleCalculatedSelectChange(selectElement));
}

async function refreshSelectOptions(selectElement, lookupListId, displayColumn, filters, dependencyIds) {
    debugLog(MODULE, `🌐 Starting API refresh for ${selectElement.id || selectElement.name}`);
    debugLog(MODULE, `Lookup List ID: ${lookupListId}`);
    debugLog(MODULE, `Display Column: ${displayColumn}`);
    debugLog(MODULE, `Filters:`, filters);
    debugLog(MODULE, `Dependencies:`, dependencyIds);

    // Debug existing data availability
    const fieldId = resolveCalculatedSelectFieldId(selectElement);
    debugLog(MODULE, `🔍 Debugging existing data for field ${fieldId}:`);
    debugLog(MODULE, `window.existingData available:`, !!window.existingData);
    if (window.existingData && fieldId) {
        const existingDataKey = `field_value[${fieldId}]`;
        debugLog(MODULE, `Looking for key: "${existingDataKey}"`);
        debugLog(MODULE, `Value in existingData:`, window.existingData[existingDataKey]);
        debugLog(MODULE, `All field_value keys:`, Object.keys(window.existingData).filter(k => k.includes('field_value')));
    }

    debugLog(MODULE, '🔄 Refreshing options for', selectElement.id || selectElement.name, { lookupListId, displayColumn });

    const fieldValues = {};
    dependencyIds.forEach(id => {
        const val = getCurrentFieldValue(id);
        debugLog(MODULE, `Getting value for dependency ${id}:`, val);
        if (val !== null && val !== undefined && val !== '') {
            fieldValues[id] = val;
        }
    });

    debugLog(MODULE, `Field values for API call:`, fieldValues);

    let url;

    // Handle emergency operations special case
    if (lookupListId === 'emergency_operations') {
        url = new URL('/admin/plugins/emergency_operations/api/list-data', window.location.origin);
        debugLog(MODULE, `Emergency Operations URL: ${url.toString()}`);

        const fieldIdForTrace = resolveCalculatedSelectFieldId(selectElement);
        traceEmOpsFilter(fieldIdForTrace, 'refresh start', {
            selectId: selectElement.id || null,
            displayColumn,
            listFilters: filters,
        });

        // Read plugin config stored on the element by the template (data-plugin-config)
        let pluginConfig = {};
        const rawCfgSelf = selectElement.dataset.pluginConfig;
        const rawCfgClosest = selectElement.closest('[data-plugin-config]')?.dataset.pluginConfig;
        const rawCfg = rawCfgSelf || rawCfgClosest || '{}';
        traceEmOpsFilter(fieldIdForTrace, 'data-plugin-config source', {
            fromSelect: Boolean(rawCfgSelf),
            fromAncestor: Boolean(!rawCfgSelf && rawCfgClosest),
            rawLength: rawCfg.length,
            rawPreview: rawCfg.length > 200 ? `${rawCfg.slice(0, 200)}…` : rawCfg,
        });
        try {
            pluginConfig = JSON.parse(rawCfg);
        } catch (parseErr) {
            traceEmOpsFilter(fieldIdForTrace, 'data-plugin-config parse FAILED', {
                error: parseErr && parseErr.message ? parseErr.message : String(parseErr),
                rawCfg,
            });
        }
        traceEmOpsFilter(fieldIdForTrace, 'parsed question_plugin_config', pluginConfig);

        // --- Country resolution ---
        let countryIso = null;

        const countrySource = pluginConfig.emops_country_source || 'assigned';
        if (countrySource === 'static' && pluginConfig.emops_static_country_iso) {
            // Template designer pinned a specific country
            countryIso = pluginConfig.emops_static_country_iso.trim().toUpperCase();
            debugLog(MODULE, `Using static country ISO from plugin config: ${countryIso}`);
        } else {
            // Default: use the entity/assignment country from page metadata
            countryIso = resolveAssignedCountryIso();
            if (countryIso) {
                debugLog(MODULE, `Found country ISO from assignment metadata: ${countryIso}`);
            }
        }

        if (countryIso) {
            url.searchParams.set('iso', countryIso);
        } else {
            debugLog(MODULE, `No country ISO found, will return all operations`);
        }

        // WAF: pack dates and filter JSON in query_b64 so values like dates and "Emergency Appeal"
        // don't trigger OWASP CRS rules in the URL query string.
        const queryPayload = {};

        // --- Timeframe resolution ---
        const timeframeMode = pluginConfig.emops_timeframe_mode || 'static';

        if (timeframeMode === 'assignment_period') {
            // Derive dates from the assignment period (e.g. "Jan-Jun 2026" → year 2026)
            const periodStr = (window.metadataContext && window.metadataContext.assignment_period) || '';
            const yearMatch = periodStr.match(/\b(20\d{2})\b/);
            if (yearMatch) {
                const year = yearMatch[1];
                // Include operations that were active at any point during the period year:
                // end_date_gt = <year>-01-01 means "still active at the start of the period year"
                queryPayload.end_date__gte = `${year}-01-01`;
                traceEmOpsFilter(fieldIdForTrace, 'timeframe: assignment_period', {
                    periodStr,
                    effectiveEndDateGte: queryPayload.end_date__gte,
                    note: 'Overrides emops_end_date_gt from form builder config',
                    staticConfigEndDate: pluginConfig.emops_end_date_gt || null,
                });
                debugLog(MODULE, `Using assignment period year ${year} for timeframe filter`);
            } else {
                traceEmOpsFilter(fieldIdForTrace, 'timeframe: assignment_period (no year parsed)', {
                    periodStr,
                    metadataContext: window.metadataContext || null,
                });
                debugLog(MODULE, `Could not extract year from period "${periodStr}", no timeframe filter applied`);
            }
        } else {
            // Static dates configured in the form builder
            if (pluginConfig.emops_end_date_gt) {
                queryPayload.end_date__gte = pluginConfig.emops_end_date_gt;
            }
            traceEmOpsFilter(fieldIdForTrace, 'timeframe: static', {
                effectiveEndDateGte: queryPayload.end_date__gte || null,
            });
            // Note: start_date is not supported by the list-data endpoint directly;
            // it is handled via the filters array below.
        }

        // Translate operation-type and show-closed plugin config into row filters
        // (the list-data endpoint already processes a 'filters' JSON array)
        const extraFilters = [];

        const configTypes = pluginConfig.emops_operation_types;
        traceEmOpsFilter(fieldIdForTrace, 'emops_operation_types raw', {
            value: configTypes,
            typeof: typeof configTypes,
            isArray: Array.isArray(configTypes),
        });
        if (configTypes) {
            const types = Array.isArray(configTypes) ? configTypes : [configTypes];
            const hasAll = types.includes('All');
            if (!hasAll && types.length > 0) {
                extraFilters.push({ field: 'type', op: 'eq', value: types[0] });
                traceEmOpsFilter(fieldIdForTrace, 'type filter applied', {
                    filter: extraFilters[extraFilters.length - 1],
                    note: types.length > 1
                        ? `Only first of ${types.length} selected types is used (eq filter)`
                        : 'Single type selected',
                });
            } else {
                traceEmOpsFilter(fieldIdForTrace, 'type filter SKIPPED', {
                    reason: hasAll ? 'includes All' : 'empty types array',
                    types,
                });
            }
        } else {
            traceEmOpsFilter(fieldIdForTrace, 'type filter SKIPPED', {
                reason: 'emops_operation_types missing or falsy in plugin config',
            });
        }

        const showClosed = pluginConfig.emops_show_closed_operations;
        traceEmOpsFilter(fieldIdForTrace, 'emops_show_closed_operations', {
            value: showClosed,
            typeof: typeof showClosed,
            isArray: Array.isArray(showClosed),
        });
        const hideClosed = showClosed === false
            || showClosed === '0'
            || showClosed === 0
            || (Array.isArray(showClosed) && showClosed.length === 0);
        if (hideClosed) {
            extraFilters.push({ field: 'status', op: 'ne', value: 'Closed' });
            traceEmOpsFilter(fieldIdForTrace, 'status filter applied (hide closed)', extraFilters[extraFilters.length - 1]);
        } else {
            traceEmOpsFilter(fieldIdForTrace, 'status filter SKIPPED (showing closed ops)', { showClosed });
        }

        // Merge with any existing row-level filters
        const allFilters = [...extraFilters, ...(filters || [])];
        traceEmOpsFilter(fieldIdForTrace, 'merged filters', {
            extraFilters,
            listFilters: filters,
            allFilters,
        });
        if (allFilters.length > 0) {
            queryPayload.filters = allFilters;
        }

        traceEmOpsFilter(fieldIdForTrace, 'query payload (pre-b64)', queryPayload);

        if (Object.keys(queryPayload).length > 0) {
            const queryB64 = btoa(unescape(encodeURIComponent(JSON.stringify(queryPayload))));
            url.searchParams.set('query_b64', queryB64);
        }

        traceEmOpsFilter(fieldIdForTrace, 'request URL', {
            iso: url.searchParams.get('iso'),
            hasQueryB64: url.searchParams.has('query_b64'),
            url: url.toString(),
        });

    } else if (lookupListId === 'reporting_currency') {
        // Core system list: Reporting Currency
        url = new URL(`/api/forms/lookup-lists/${lookupListId}/options`, window.location.origin);
        debugLog(MODULE, `Reporting Currency URL: ${url.toString()}`);

        // Pass ACS id from the page if available to resolve local currency
        try {
            const aesHolder = document.querySelector('[data-aes-id]');
            const aesId = aesHolder ? aesHolder.getAttribute('data-aes-id') : null;
            if (aesId) url.searchParams.set('aes_id', aesId);
        } catch (e) { /* no-op */ }

        // Also pass URL iso/country if present
        const urlParams = new URLSearchParams(window.location.search);
        const countryParam = urlParams.get('country') || urlParams.get('iso');
        if (countryParam) {
            url.searchParams.set('iso', countryParam.toUpperCase());
        }

        // No filters/field_values needed; backend ignores them
    } else {
        url = new URL(`/api/forms/lookup-lists/${lookupListId}/options`, window.location.origin);
        debugLog(MODULE, `Base URL: ${url.toString()}`);

        url.searchParams.set('filters', JSON.stringify(filters));
        if (Object.keys(fieldValues).length > 0) {
            url.searchParams.set('field_values', JSON.stringify(fieldValues));
        }
    }

    debugLog(MODULE, `Final API URL: ${url.toString()}`);
    debugLog(MODULE, `URL params:`, Array.from(url.searchParams.entries()));

    try {
        debugLog(MODULE, `📡 Making API call (or sharing cached/in-flight response)...`);
        debugLog(MODULE, '🌐 Fetching', url.toString());

        const json = await cachedFetch(url.toString());
        debugLog(MODULE, `✅ API response received:`, json);
        debugLog(MODULE, '⬇️  API response', json);

        if (!json.success) {
            debugError(MODULE, `❌ API returned success=false:`, json);
            debugWarn(MODULE, 'API responded with success=false', json);
            return;
        }

        // Handle different response formats
        let rows = [];
        if (lookupListId === 'emergency_operations') {
            rows = json.data || [];
            const typeCounts = summarizeEmOpsTypes(rows);
            traceEmOpsFilter(fieldId, 'API response rows', {
                count: rows.length,
                typeCounts,
                sample: rows.slice(0, 5).map((r) => ({
                    name: r.name,
                    code: r.code,
                    type: r.type,
                    status: r.status,
                    end_date: r.end_date,
                })),
            });
            const expectedTypeFilter = (() => {
                try {
                    const raw = selectElement.dataset.pluginConfig
                        || selectElement.closest('[data-plugin-config]')?.dataset.pluginConfig
                        || '{}';
                    const cfg = JSON.parse(raw);
                    const types = cfg.emops_operation_types;
                    const arr = Array.isArray(types) ? types : (types ? [types] : []);
                    if (arr.length && !arr.includes('All')) return arr[0];
                } catch (_) { /* no-op */ }
                return null;
            })();
            if (expectedTypeFilter) {
                const unexpected = rows.filter((r) => String(r.type || '') !== String(expectedTypeFilter));
                if (unexpected.length > 0) {
                    traceEmOpsFilter(fieldId, 'UNEXPECTED types in response (filter may not be applied server-side)', {
                        expectedType: expectedTypeFilter,
                        unexpectedCount: unexpected.length,
                        unexpectedTypes: summarizeEmOpsTypes(unexpected),
                        examples: unexpected.slice(0, 3).map((r) => ({ name: r.name, type: r.type, status: r.status })),
                    });
                } else {
                    traceEmOpsFilter(fieldId, 'all rows match expected type filter', { expectedType: expectedTypeFilter });
                }
            }
        } else {
            rows = json.rows || [];
        }
        debugLog(MODULE, `Processing ${rows.length} rows`);

        // Get existing value using the fieldId we already have
        let existingValue = '';

        if (selectElement.dataset.pendingValue) {
            existingValue = selectElement.dataset.pendingValue;
        } else if (fieldId && window.existingData) {
            const existingDataKey = `field_value[${fieldId}]`;
            existingValue = window.existingData[existingDataKey] || '';
            debugLog(MODULE, `Existing saved value for field ${fieldId}:`, existingValue);
        }

        // Fallback to current select value if no existing data
        const previousValue = existingValue || selectElement.value;
        debugLog(MODULE, `Previous selected value: "${previousValue}"`);

        // Clear existing options
        selectElement.replaceChildren();
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = 'Select...';
        selectElement.appendChild(placeholder);
        debugLog(MODULE, `Added placeholder option`);

        rows.forEach((row, idx) => {
            const val = resolveCalculatedListRowDisplay(row, displayColumn, lookupListId);
            if (!val) {
                debugWarn(MODULE, `⚠️ Row ${idx + 1} has no display value (column "${displayColumn}"):`, row);
                return;
            }
            const opt = document.createElement('option');
            opt.value = val;
            opt.textContent = val;
            if (lookupListId === 'emergency_operations') {
                applyEmergencyRowToOption(opt, row, val);
            }
            selectElement.appendChild(opt);
            debugLog(MODULE, `Added option ${idx + 1}: "${val}"`);
            debugLog(MODULE, `   Added option ${idx + 1}:`, val);
        });

        debugLog(MODULE, `✅ Options refreshed. Total ${rows.length} rows, select now has ${selectElement.options.length - 1} options.`);
        debugLog(MODULE, `✅ Options refreshed. Total ${rows.length} rows, select now has ${selectElement.options.length - 1} options.`);

        // Append "Other" option for calculated lists that have allow_other enabled
        appendOtherOptionToSelect(selectElement);

        // Restore previous selection if still valid, otherwise preserve stale saved values
        if (previousValue && optionValueExists(selectElement, previousValue)) {
            clearSelectStaleSavedValue(selectElement);
            setSelectValueRobust(selectElement, previousValue);
            delete selectElement.dataset.pendingValue;
            if (window.revealRepeatEntryTitleSelect) {
                window.revealRepeatEntryTitleSelect(selectElement);
            }
            debugLog(MODULE, `Restored previous selection: "${previousValue}"`);
            debugLog(MODULE, `✅ Restored previous selection: "${previousValue}"`);
            syncEmergencyOperationMetadata(selectElement);

            // Add verification that the value actually stuck
            setTimeout(() => {
                const actualValue = selectElement.value;
                debugLog(MODULE, `Verification: Select value after 100ms: "${actualValue}"`);
                if (actualValue !== previousValue) {
                    debugWarn(MODULE, `⚠️ Value was reset! Expected "${previousValue}" but got "${actualValue}"`);
                    debugWarn(MODULE, `⚠️ Attempting to restore again...`);
                    setSelectValueRobust(selectElement, previousValue);

                    // Final verification
                    setTimeout(() => {
                        const finalValue = selectElement.value;
                        debugLog(MODULE, `Final verification: Select value after 200ms: "${finalValue}"`);
                        if (finalValue !== previousValue) {
                            debugError(MODULE, `❌ Failed to restore value. Something is overriding our selection.`);
                            debugError(MODULE, `❌ Available options:`, Array.from(selectElement.options).map(o => ({value: o.value, text: o.text})));
                        } else {
                            debugLog(MODULE, `✅ Value successfully restored on retry: "${finalValue}"`);
                        }
                    }, 100);
                } else {
                    debugLog(MODULE, `✅ Value verification successful: "${actualValue}"`);
                }
            }, 100);
        } else if (previousValue) {
            markSelectStaleSavedValue(selectElement, previousValue);
            delete selectElement.dataset.pendingValue;
            attachStaleSavedValueListener(selectElement);
            if (window.revealRepeatEntryTitleSelect) {
                window.revealRepeatEntryTitleSelect(selectElement);
            }
            debugLog(MODULE, `⚠️ Saved value "${previousValue}" is not in current API options — preserved with warning`);
        } else {
            clearSelectStaleSavedValue(selectElement);
            selectElement.value = '';
            debugLog(MODULE, 'Reset to empty (no previous value)');
        }

        if (window.applyUniqueSectionOptions) {
            window.applyUniqueSectionOptions(selectElement.closest('[data-collapsible-id]') || document);
        }

        if (selectElement.dataset.useAsRepeatEntryTitle === 'true' && window.revealRepeatEntryTitleSelect) {
            window.revealRepeatEntryTitleSelect(selectElement);
        }

        syncEmergencyOperationMetadata(selectElement);
    } catch (err) {
        debugError(MODULE, `❌ Exception during API call:`, err);
        debugWarn(MODULE, '❌ Exception while fetching options', err);
        if (selectElement.dataset.useAsRepeatEntryTitle === 'true' && window.revealRepeatEntryTitleSelect) {
            window.revealRepeatEntryTitleSelect(selectElement);
        }
    }
}

async function refreshMultiSelectOptions(multiSelectDiv, fieldId, lookupListId, displayColumn, filters, dependencyIds) {
    debugLog(MODULE, `🌐 Starting multi-select API refresh for ${multiSelectDiv.id}`);
    debugLog(MODULE, `Field ID: ${fieldId}`);
    debugLog(MODULE, `Lookup List ID: ${lookupListId}`);
    debugLog(MODULE, `Display Column: ${displayColumn}`);
    debugLog(MODULE, `Filters:`, filters);
    debugLog(MODULE, `Dependencies:`, dependencyIds);

    debugLog(MODULE, '🔄 Refreshing options for', multiSelectDiv.id, { lookupListId, displayColumn });

    const fieldValues = {};
    dependencyIds.forEach(id => {
        const val = getCurrentFieldValue(id);
        debugLog(MODULE, `Getting value for dependency ${id}:`, val);
        if (val !== null && val !== undefined && val !== '') {
            fieldValues[id] = val;
        }
    });

    debugLog(MODULE, `Field values for API call:`, fieldValues);

    let url;
    if (lookupListId === 'reporting_currency') {
        url = new URL(`/api/forms/lookup-lists/${lookupListId}/options`, window.location.origin);
        debugLog(MODULE, `Reporting Currency (multi) URL: ${url.toString()}`);
        try {
            const aesHolder = document.querySelector('[data-aes-id]');
            const aesId = aesHolder ? aesHolder.getAttribute('data-aes-id') : null;
            if (aesId) url.searchParams.set('aes_id', aesId);
        } catch (e) { /* no-op */ }
        const urlParams = new URLSearchParams(window.location.search);
        const countryParam = urlParams.get('country') || urlParams.get('iso');
        if (countryParam) {
            url.searchParams.set('iso', countryParam.toUpperCase());
        }
    } else {
        url = new URL(`/api/forms/lookup-lists/${lookupListId}/options`, window.location.origin);
        debugLog(MODULE, `Base URL: ${url.toString()}`);
        url.searchParams.set('filters', JSON.stringify(filters));
        if (Object.keys(fieldValues).length > 0) {
            url.searchParams.set('field_values', JSON.stringify(fieldValues));
        }
    }

    debugLog(MODULE, `Final API URL: ${url.toString()}`);

    try {
        debugLog(MODULE, `📡 Making multi-select API call (or sharing cached/in-flight response)...`);
        debugLog(MODULE, '🌐 Fetching', url.toString());

        const json = await cachedFetch(url.toString());
        debugLog(MODULE, `✅ Multi-select API response received:`, json);
        debugLog(MODULE, '⬇️  API response', json);

        if (!json.success) {
            debugError(MODULE, `❌ Multi-select API returned success=false:`, json);
            debugWarn(MODULE, 'API responded with success=false', json);
            return;
        }

        const rows = json.rows || [];
        debugLog(MODULE, `Processing ${rows.length} rows for multi-select`);

        // Find the dropdown container
        const dropdown = multiSelectDiv.querySelector('.multi-select-dropdown');
        if (!dropdown) {
            debugError(MODULE, `❌ Could not find dropdown container for multi-select ${multiSelectDiv.id}`);
            debugWarn(MODULE, 'Could not find dropdown container for multi-select', multiSelectDiv);
            return;
        }

        debugLog(MODULE, `Found dropdown container:`, dropdown);

        // Get existing selected values from server data
        let existingValues = [];
        if (fieldId && window.existingData) {
            const existingDataKey = `field_value[${fieldId}]`;
            const existingData = window.existingData[existingDataKey];
            if (Array.isArray(existingData)) {
                existingValues = existingData;
            } else if (existingData && typeof existingData === 'string') {
                existingValues = [existingData];
            }
            debugLog(MODULE, `Existing saved values for field ${fieldId}:`, existingValues);
        }

        // Fallback to currently selected values if no existing data
        if (existingValues.length === 0) {
            dropdown.querySelectorAll('input[type="checkbox"]:checked').forEach(checkbox => {
                existingValues.push(checkbox.value);
            });
        }

        debugLog(MODULE, `Previously selected values:`, existingValues);

        // Clear existing options
        dropdown.replaceChildren();
        debugLog(MODULE, `Cleared existing options`);

        rows.forEach((row, idx) => {
            const val = resolveCalculatedListRowDisplay(row, displayColumn, lookupListId);
            if (!val) {
                debugWarn(MODULE, `⚠️ Multi-select row ${idx + 1} has no display value (column "${displayColumn}"):`, row);
                return;
            }

            const optionDiv = document.createElement('div');
            optionDiv.className = 'px-3 py-2 hover:bg-gray-100 cursor-pointer';

            const label = document.createElement('label');
            label.className = 'inline-flex items-center cursor-pointer w-full';

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.name = `field_value[${fieldId}]`;
            checkbox.value = val;
            checkbox.className = 'form-checkbox h-4 w-4 text-green-600 border-gray-300 rounded focus:ring-green-500';

            // Restore selection if this value was previously selected
            if (existingValues.includes(val)) {
                checkbox.checked = true;
                debugLog(MODULE, `Restored selection for: "${val}"`);
                debugLog(MODULE, `✅ Restored multi-select selection: "${val}"`);
            }

            const span = document.createElement('span');
            span.className = 'ml-2 text-sm text-gray-700';
            span.textContent = val;

            label.appendChild(checkbox);
            label.appendChild(span);
            optionDiv.appendChild(label);
            dropdown.appendChild(optionDiv);

            debugLog(MODULE, `Added multi-select option ${idx + 1}: "${val}"`);
            debugLog(MODULE, `   Added multi-select option ${idx + 1}:`, val);
        });

        debugLog(MODULE, `✅ Multi-select options refreshed. Total ${rows.length} rows, dropdown now has ${dropdown.children.length} options.`);
        debugLog(MODULE, `✅ Multi-select options refreshed. Total ${rows.length} rows, dropdown now has ${dropdown.children.length} options.`);

        // Append "Other" option for calculated lists that have allow_other enabled
        appendOtherOptionToMultiDropdown(dropdown, fieldId);

        if (window.applyUniqueSectionOptions) {
            window.applyUniqueSectionOptions(multiSelectDiv.closest('[data-collapsible-id]') || document);
        }
    } catch (err) {
        debugError(MODULE, `❌ Exception during multi-select API call:`, err);
        debugWarn(MODULE, '❌ Exception while fetching multi-select options', err);
    }
}
