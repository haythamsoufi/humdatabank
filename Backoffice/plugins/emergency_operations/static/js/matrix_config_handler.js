/**
 * Emergency Operations Config UI Handler
 * Sets up event listeners for the emergency operations configuration panel.
 * Shared by the matrix item modal and the question list-library config panel.
 */

/**
 * Toggle visibility of a wrapper element.
 * @param {HTMLElement|null} wrapper
 * @param {boolean} visible
 */
function _setVisible(wrapper, visible) {
    if (!wrapper) return;
    wrapper.classList.toggle('hidden', !visible);
}

/** Inputs that share a logical config field name (supports per-panel name scoping). */
function _inputsByConfigName(container, baseName) {
    const scoped = container.querySelectorAll(`[data-config-name="${baseName}"]`);
    if (scoped.length) return scoped;
    return container.querySelectorAll(`[name="${baseName}"]`);
}

function _checkedInputByConfigName(container, baseName) {
    return Array.from(_inputsByConfigName(container, baseName)).find(inp => inp.checked) || null;
}

function _inputByConfigNameAndValue(container, baseName, value) {
    return container.querySelector(`[data-config-name="${baseName}"][value="${value}"]`)
        || container.querySelector(`[name="${baseName}"][value="${value}"]`);
}

/**
 * Setup event listeners for emergency operations configuration UI.
 * Called generically when the config panel is injected into any container.
 *
 * @param {HTMLElement} configContainer - Container holding the rendered config HTML
 * @param {Function} updateConfigCallback - Called whenever any config value changes
 */
export function setupEmergencyOperationsConfigUI(configContainer, updateConfigCallback) {
    if (!configContainer || !updateConfigCallback) {
        console.warn('Emergency Operations Config UI: Missing required parameters');
        return;
    }

    // --- Collapsible panel (collapsed by default) ---
    const toggleBtn = configContainer.querySelector('.emops-config-toggle');
    const configBody = configContainer.querySelector('#emops-config-body');
    const chevron = configContainer.querySelector('.emops-config-chevron');

    if (toggleBtn && configBody) {
        toggleBtn.addEventListener('click', () => {
            const expanded = toggleBtn.getAttribute('aria-expanded') === 'true';
            const nextExpanded = !expanded;
            toggleBtn.setAttribute('aria-expanded', nextExpanded ? 'true' : 'false');
            configBody.classList.toggle('hidden', !nextExpanded);
            if (chevron) chevron.classList.toggle('rotate-180', nextExpanded);
        });
    }

    // --- Country source radios ---
    const countrySourceRadios = _inputsByConfigName(configContainer, 'emops_country_source');
    const staticCountryWrapper = configContainer.querySelector('#emops-static-country-wrapper');

    function syncCountryUI() {
        const selected = _checkedInputByConfigName(configContainer, 'emops_country_source');
        _setVisible(staticCountryWrapper, selected && selected.value === 'static');
    }

    countrySourceRadios.forEach(radio => {
        radio.addEventListener('change', () => { syncCountryUI(); updateConfigCallback(); });
    });
    syncCountryUI();

    // --- Timeframe mode radios ---
    const timeframeModeRadios = _inputsByConfigName(configContainer, 'emops_timeframe_mode');
    const staticDatesWrapper = configContainer.querySelector('#emops-static-dates-wrapper');

    function syncTimeframeUI() {
        const selected = _checkedInputByConfigName(configContainer, 'emops_timeframe_mode');
        _setVisible(staticDatesWrapper, !selected || selected.value === 'static');
    }

    timeframeModeRadios.forEach(radio => {
        radio.addEventListener('change', () => { syncTimeframeUI(); updateConfigCallback(); });
    });
    syncTimeframeUI();

    // --- Operation types mutual-exclusion ---
    const operationTypeCheckboxes = _inputsByConfigName(configContainer, 'emops_operation_types');
    if (operationTypeCheckboxes.length > 0) {
        operationTypeCheckboxes.forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const allCheckbox = _inputByConfigNameAndValue(configContainer, 'emops_operation_types', 'All');
                const otherCheckboxes = Array.from(operationTypeCheckboxes).filter(cb => cb.value !== 'All');

                if (e.target.value === 'All') {
                    if (e.target.checked) {
                        otherCheckboxes.forEach(cb => { cb.checked = false; });
                    }
                } else {
                    if (e.target.checked && allCheckbox) {
                        allCheckbox.checked = false;
                    } else if (!e.target.checked) {
                        const anyChecked = otherCheckboxes.some(cb => cb.checked);
                        if (!anyChecked && allCheckbox) {
                            allCheckbox.checked = true;
                        }
                    }
                }
                updateConfigCallback();
            });
        });
    }

    // Generic change/input listeners for remaining inputs (dates, ISO text, show-closed)
    const inputs = configContainer.querySelectorAll('input, select, textarea');
    inputs.forEach(input => {
        if (!input.__emopsHandlerAdded) {
            input.__emopsHandlerAdded = true;
            input.addEventListener('change', () => updateConfigCallback());
            input.addEventListener('input', () => updateConfigCallback());
        }
    });
}

// Make function available globally for dynamic loading
window.setupEmergencyOperationsConfigUI = setupEmergencyOperationsConfigUI;
