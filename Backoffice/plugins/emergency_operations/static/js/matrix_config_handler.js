/**
 * Emergency Operations Matrix Config UI Handler
 * Sets up event listeners and handles interactions for the emergency operations
 * configuration UI in the matrix item modal.
 */

/**
 * Setup event listeners for emergency operations configuration UI
 * This function is called generically by the matrix item modal when the config UI is loaded
 *
 * @param {HTMLElement} configContainer - The container element with the config UI
 * @param {Function} updateConfigCallback - Callback function to trigger config updates
 */
export function setupEmergencyOperationsConfigUI(configContainer, updateConfigCallback) {
    if (!configContainer || !updateConfigCallback) {
        console.warn('Emergency Operations Config UI: Missing required parameters');
        return;
    }

    // Setup change listeners for all inputs in the config container
    const inputs = configContainer.querySelectorAll('input, select, textarea');
    inputs.forEach(input => {
        input.addEventListener('change', () => updateConfigCallback());
        input.addEventListener('input', () => updateConfigCallback());
    });

    // Special handling for operation types checkboxes
    const operationTypeCheckboxes = configContainer.querySelectorAll('input[name="emops_operation_types"]');
    if (operationTypeCheckboxes.length > 0) {
        operationTypeCheckboxes.forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const allCheckbox = configContainer.querySelector('input[name="emops_operation_types"][value="All"]');
                const otherCheckboxes = Array.from(operationTypeCheckboxes).filter(cb => cb.value !== 'All');

                if (e.target.value === 'All') {
                    // If "All" is checked, uncheck others
                    if (e.target.checked) {
                        otherCheckboxes.forEach(cb => cb.checked = false);
                    }
                } else {
                    // If any other checkbox is checked, uncheck "All"
                    if (e.target.checked && allCheckbox) {
                        allCheckbox.checked = false;
                    }
                    // If all other checkboxes are unchecked, check "All"
                    else if (!e.target.checked) {
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
}

// Make function available globally for dynamic loading
window.setupEmergencyOperationsConfigUI = setupEmergencyOperationsConfigUI;
