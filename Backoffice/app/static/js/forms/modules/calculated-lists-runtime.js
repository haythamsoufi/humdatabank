import { debugLog, debugWarn, debugError } from './debug.js';
import { getFieldValue, getCurrentFieldValue } from './field-management.js';

const MODULE = 'calculated-lists-runtime';

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

        if (document.readyState === 'complete' && existingDataReady) {
            debugLog(MODULE, '✅ Ready to initialize - DOM loaded and existing data available');
            setTimeout(() => initCalculatedListsCore(), 100);
        } else {
            debugLog(MODULE, '⏳ Not ready yet, will retry in 100ms...');
            setTimeout(checkAndInit, 100);
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

    // IMPORTANT: Delay initial refresh to ensure form data is loaded
    setTimeout(() => {
        debugLog(MODULE, '🔄 Performing delayed initial refresh...');
        selectElements.forEach(sel => {
            debugLog(MODULE, `Refreshing ${sel.id} after delay`);
            refreshCalculatedSelect(sel);
        });
        multiSelectElements.forEach(div => {
            debugLog(MODULE, `Refreshing ${div.id} after delay`);
            refreshCalculatedMultiSelect(div);
        });
    }, 500); // Wait 500ms for form data to be loaded

    debugLog(MODULE, '✅ Calculated lists initialization complete');
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
    refresh();
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

    debugLog(MODULE, `🔧 Select value set to: "${selectElement.value}" (events triggered)`);
}

async function refreshSelectOptions(selectElement, lookupListId, displayColumn, filters, dependencyIds) {
    debugLog(MODULE, `🌐 Starting API refresh for ${selectElement.id || selectElement.name}`);
    debugLog(MODULE, `Lookup List ID: ${lookupListId}`);
    debugLog(MODULE, `Display Column: ${displayColumn}`);
    debugLog(MODULE, `Filters:`, filters);
    debugLog(MODULE, `Dependencies:`, dependencyIds);

    // Debug existing data availability
    const fieldId = selectElement.id ? selectElement.id.replace('field-', '') : null;
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

        // Better country detection - look for country fields more systematically
        let countryIso = null;

        // First, try to find country from data-country-iso attribute (most reliable)
        const countryIsoElement = document.querySelector('[data-country-iso]');
        if (countryIsoElement && countryIsoElement.dataset.countryIso) {
            countryIso = countryIsoElement.dataset.countryIso.trim().toUpperCase();
            debugLog(MODULE, `Found country ISO from data-country-iso attribute: ${countryIso}`);
        }

        // If not found in data attribute, try to find country from field values
        if (!countryIso) {
            for (const [key, value] of Object.entries(fieldValues)) {
                if (value && typeof value === 'string') {
                    const trimmedValue = value.trim().toUpperCase();
                    // Check if it's a valid ISO code (2 or 3 characters)
                    if (trimmedValue.length === 2 || trimmedValue.length === 3) {
                        countryIso = trimmedValue;
                        debugLog(MODULE, `Found country ISO from field ${key}: ${countryIso}`);
                        break;
                    }
                }
            }
        }

        // If not found in field values, try to get from URL or page context
        if (!countryIso) {
            // Check if there's a country parameter in the URL
            const urlParams = new URLSearchParams(window.location.search);
            const countryParam = urlParams.get('country') || urlParams.get('iso');
            if (countryParam) {
                countryIso = countryParam.toUpperCase();
                debugLog(MODULE, `Found country ISO from URL: ${countryIso}`);
            }

            // Check if there's country info in the page context
            if (!countryIso && window.countryInfo) {
                countryIso = window.countryInfo.iso || window.countryInfo.iso3;
                if (countryIso) {
                    countryIso = countryIso.toUpperCase();
                    debugLog(MODULE, `Found country ISO from page context: ${countryIso}`);
                }
            }
        }

        if (countryIso) {
            url.searchParams.set('iso', countryIso);
        } else {
            debugLog(MODULE, `No country ISO found, will return all operations`);
        }

        // Add filters for emergency operations (operation types, etc.)
        if (filters && filters.length > 0) {
            url.searchParams.set('filters', JSON.stringify(filters));
        }

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
        debugLog(MODULE, `📡 Making API call...`);
        debugLog(MODULE, '🌐 Fetching', url.toString());

        const fetchFn = (window.getFetch && window.getFetch()) || fetch;
        const response = await fetchFn(url.toString(), {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        debugLog(MODULE, `Response status: ${response.status} ${response.statusText}`);

        if (!response.ok) {
            debugError(MODULE, `❌ API call failed with status ${response.status}`);
            debugWarn(MODULE, `Failed to fetch options for list ${lookupListId}: HTTP ${response.status}`);
            return;
        }

        const json = await response.json();
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
        } else {
            rows = json.rows || [];
        }
        debugLog(MODULE, `Processing ${rows.length} rows`);

        // Get existing value using the fieldId we already have
        let existingValue = '';

        if (fieldId && window.existingData) {
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
            if (row.hasOwnProperty(displayColumn)) {
                const val = row[displayColumn];
                const opt = document.createElement('option');
                opt.value = val;
                opt.textContent = val;
                selectElement.appendChild(opt);
                debugLog(MODULE, `Added option ${idx + 1}: "${val}"`);
                debugLog(MODULE, `   Added option ${idx + 1}:`, val);
            } else {
                debugWarn(MODULE, `⚠️ Row ${idx + 1} missing display column "${displayColumn}":`, row);
            }
        });

        debugLog(MODULE, `✅ Options refreshed. Total ${rows.length} rows, select now has ${selectElement.options.length - 1} options.`);
        debugLog(MODULE, `✅ Options refreshed. Total ${rows.length} rows, select now has ${selectElement.options.length - 1} options.`);

        // Restore previous selection if still valid, otherwise reset
        if (previousValue && Array.from(selectElement.options).some(o => o.value === previousValue)) {
            setSelectValueRobust(selectElement, previousValue);
            debugLog(MODULE, `Restored previous selection: "${previousValue}"`);
            debugLog(MODULE, `✅ Restored previous selection: "${previousValue}"`);

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
        } else {
            selectElement.value = '';
            debugLog(MODULE, `Reset to empty (previous value "${previousValue}" not available)`);
            if (previousValue) {
                debugLog(MODULE, `⚠️ Could not restore previous value "${previousValue}" - not in available options`);
                debugLog(MODULE, `Available options for comparison:`, Array.from(selectElement.options).map(o => o.value));
            }
        }
    } catch (err) {
        debugError(MODULE, `❌ Exception during API call:`, err);
        debugWarn(MODULE, '❌ Exception while fetching options', err);
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
        debugLog(MODULE, `📡 Making multi-select API call...`);
        debugLog(MODULE, '🌐 Fetching', url.toString());

        const fetchFn = (window.getFetch && window.getFetch()) || fetch;
        const response = await fetchFn(url.toString(), {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        debugLog(MODULE, `Response status: ${response.status} ${response.statusText}`);

        if (!response.ok) {
            debugError(MODULE, `❌ Multi-select API call failed with status ${response.status}`);
            debugWarn(MODULE, `Failed to fetch options for list ${lookupListId}: HTTP ${response.status}`);
            return;
        }

        const json = await response.json();
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
            if (row.hasOwnProperty(displayColumn)) {
                const val = row[displayColumn];

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
            } else {
                debugWarn(MODULE, `⚠️ Multi-select row ${idx + 1} missing display column "${displayColumn}":`, row);
            }
        });

        debugLog(MODULE, `✅ Multi-select options refreshed. Total ${rows.length} rows, dropdown now has ${dropdown.children.length} options.`);
        debugLog(MODULE, `✅ Multi-select options refreshed. Total ${rows.length} rows, dropdown now has ${dropdown.children.length} options.`);
    } catch (err) {
        debugError(MODULE, `❌ Exception during multi-select API call:`, err);
        debugWarn(MODULE, '❌ Exception while fetching multi-select options', err);
    }
}
