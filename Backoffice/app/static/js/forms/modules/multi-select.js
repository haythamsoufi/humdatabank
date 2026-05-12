import { debugLog } from './debug.js';

let multiSelectListenersAdded = false;

export function initMultiSelect() {
    debugLog('multi-select', '\n=== INITIALIZING MULTI-SELECT DROPDOWNS ===');
    initializeMultiSelectDropdowns();
}

function initializeMultiSelectDropdowns() {
    debugLog('multi-select', 'Setting up multi-select dropdowns');

    if (!multiSelectListenersAdded) {
        document.addEventListener('click', function(event) {
            const target = event.target;
            const button = target.closest('.multi-select-btn');

            if (button && !button.disabled && button.getAttribute('data-availability-disabled') !== 'true') {
                debugLog('multi-select', `Button clicked for field ${button.getAttribute('data-field-id')}`);
                event.preventDefault();
                event.stopPropagation();

                const fieldId = button.getAttribute('data-field-id');
                const dropdown = document.querySelector(`.multi-select-dropdown[data-field-id="${fieldId}"]`);

                if (!dropdown) {
                    debugLog('No dropdown found for button:', button);
                    return;
                }

                const isHidden = dropdown.classList.contains('hidden');

                // Close all other dropdowns
                document.querySelectorAll('.multi-select-dropdown').forEach(d => {
                    d.classList.add('hidden');
                });

                if (isHidden) {
                    // Calculate position relative to the button
                    const buttonRect = button.getBoundingClientRect();
                    const dropdown = document.querySelector(`.multi-select-dropdown[data-field-id="${fieldId}"]`);

                    if (dropdown) {
                        // Position dropdown below the button
                        dropdown.style.position = 'fixed';
                        dropdown.style.top = `${buttonRect.bottom + window.scrollY + 4}px`;
                        dropdown.style.left = `${buttonRect.left + window.scrollX}px`;
                        dropdown.style.width = `${buttonRect.width}px`;
                        dropdown.style.zIndex = '9999';

                        // Ensure dropdown doesn't go off-screen
                        const dropdownRect = dropdown.getBoundingClientRect();
                        const viewportHeight = window.innerHeight;
                        const viewportWidth = window.innerWidth;

                        // Adjust if dropdown would go below viewport
                        if (dropdownRect.bottom > viewportHeight) {
                            dropdown.style.top = `${buttonRect.top + window.scrollY - dropdownRect.height - 4}px`;
                        }

                        // Adjust if dropdown would go off right edge
                        if (dropdownRect.right > viewportWidth) {
                            dropdown.style.left = `${viewportWidth - dropdownRect.width - 10}px`;
                        }

                        // Adjust if dropdown would go off left edge
                        if (dropdownRect.left < 0) {
                            dropdown.style.left = '10px';
                        }
                    }

                    dropdown.classList.remove('hidden');
                    debugLog('multi-select', 'Toggled dropdown visibility: true');
                }
            } else if (button && (button.disabled || button.getAttribute('data-availability-disabled') === 'true')) {
                debugLog('multi-select', `Button click blocked - disabled: ${button.disabled}, data-availability-disabled: ${button.getAttribute('data-availability-disabled')}`);
            } else if (!target.closest('.multi-select-dropdown')) {
                document.querySelectorAll('.multi-select-dropdown').forEach(d => {
                    d.classList.add('hidden');
                });
            }
        });

        // Handle checkbox changes in multi-select dropdowns
        document.addEventListener('change', function(e) {
            if (e.target.type === 'checkbox' && e.target.closest('.multi-select-dropdown')) {
                const dropdown = e.target.closest('.multi-select-dropdown');
                const fieldId = dropdown.getAttribute('data-field-id');
                const button = document.querySelector(`.multi-select-btn[data-field-id="${fieldId}"]`);

                // Check if the field is disabled by data availability
                if (button && button.getAttribute('data-availability-disabled') === 'true') {
                    debugLog('multi-select', `Checkbox change blocked for field ${fieldId} - data availability disabled`);
                    // Prevent the change and reset the checkbox
                    e.target.checked = false;
                    e.preventDefault();
                    return;
                }

                debugLog('multi-select', `Checkbox changed for field ${fieldId}`);

                if (button) {
                    updateMultiSelectButtonTextForPair(button, dropdown);
                }
            }
        });

        multiSelectListenersAdded = true;
        debugLog('multi-select', 'Multi-select document listeners added.');
    }

    // Initialize button text for existing selections
    document.querySelectorAll('.multi-select-btn').forEach(button => {
        const fieldId = button.getAttribute('data-field-id');
        const dropdown = document.querySelector(`.multi-select-dropdown[data-field-id="${fieldId}"]`);
        if (dropdown) {
            updateMultiSelectButtonTextForPair(button, dropdown);
        }
    });
}

function updateMultiSelectButtonTextForPair(button, dropdown) {
    if (button && dropdown) {
        const checkedBoxes = dropdown.querySelectorAll('input[type="checkbox"]:checked');
        const textSpan = button.querySelector('.multi-select-text');

        if (textSpan) {
            if (checkedBoxes.length === 0) {
                textSpan.textContent = 'Select options...';
            } else {
                // Get all selected option labels and join them with commas
                const selectedLabels = Array.from(checkedBoxes).map(checkbox =>
                    checkbox.nextElementSibling.textContent.trim()
                );
                textSpan.textContent = selectedLabels.join(', ');
            }
        }
    }
}

// Legacy function for backward compatibility
function updateMultiSelectButtonText(fieldId) {
    const button = document.querySelector(`.multi-select-btn[data-field-id="${fieldId}"]`);
    if (button) {
        const container = button.closest('.form-item-block, .repeat-entry') || button.parentElement;
        const dropdown = container.querySelector('.multi-select-dropdown');
        if (dropdown) {
            updateMultiSelectButtonTextForPair(button, dropdown);
        }
    }
}

// Re-initialize after dynamic content is added (for repeat sections, etc.)
document.addEventListener('repeatEntryAdded', function() {
    initializeMultiSelectDropdowns();
});
