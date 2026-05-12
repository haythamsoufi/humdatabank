import { debugLog } from './debug.js';

export function initFormatting() {
    setupThousandsSeparatorFormatting();
}

function setupThousandsSeparatorFormatting() {
    const form = document.querySelector('form');
    if (!form) return;

    // Find all number inputs that need formatting
    const numberInputs = form.querySelectorAll('input[type="number"]');
    debugLog('formatting', `Found ${numberInputs.length} number inputs to format`);

    numberInputs.forEach(input => {
        setupNumberInputFormatting(input);
    });
}

export function setupNumberInputFormatting(input) {
    // Don't re-initialize if already set up
    if (input.closest('.number-input-container')) {
        return;
    }

    // Create a container for the input and formatted display
    const container = document.createElement('div');
    container.className = 'number-input-container relative';
    input.parentNode.insertBefore(container, input);
    container.appendChild(input);

    // Ensure input has proper z-index
    input.style.position = 'relative';
    input.style.zIndex = '2';

    // Create the formatted display overlay
    const formattedDisplay = document.createElement('span');
    formattedDisplay.className = 'formatted-number absolute left-0 top-0 w-full h-full flex items-center px-3 bg-white pointer-events-none text-right select-none';
    formattedDisplay.style.zIndex = '1';
    container.appendChild(formattedDisplay);

    // Update the formatted display when the input changes
    function updateFormattedDisplay() {
        const value = input.value;
        if (value === '') {
            formattedDisplay.textContent = '';
            formattedDisplay.style.display = 'none';
        } else {
            try {
                const numValue = parseFloat(value);
                if (!isNaN(numValue)) {
                    formattedDisplay.textContent = formatNumberWithCommas(numValue.toString());
                    formattedDisplay.style.display = document.activeElement === input ? 'none' : 'flex';
                } else {
                    formattedDisplay.textContent = '';
                    input.value = '';
                    formattedDisplay.style.display = 'none';
                }
            } catch (e) {
                debugLog('formatting', `Error formatting number: ${e.message}`);
                formattedDisplay.textContent = '';
                input.value = '';
                formattedDisplay.style.display = 'none';
            }
        }
    }

    // Show/hide formatted display based on focus
    input.addEventListener('focus', () => {
        debugLog('formatting', `Input focused, hiding formatted display`);
        formattedDisplay.style.display = 'none';
    });

    input.addEventListener('blur', () => {
        debugLog('formatting', `Input blurred, showing formatted display if has value`);
        if (input.value === '') {
            formattedDisplay.style.display = 'none';
        } else {
            formattedDisplay.style.display = 'flex';
            updateFormattedDisplay();
        }
    });

    // Add click event to container to ensure input gets focus
    container.addEventListener('click', (e) => {
        // Only focus if the click wasn't already on the input
        if (e.target !== input) {
            debugLog('formatting', `Container clicked, focusing input`);
            input.focus();
        }
    });

    // Add mousedown event to ensure input gets focus even when overlay is visible
    container.addEventListener('mousedown', (e) => {
        // Prevent the mousedown from being processed by the overlay
        if (e.target === formattedDisplay) {
            e.preventDefault();
            debugLog('formatting', `Overlay clicked, focusing input`);
            input.focus();
        }
    });

    // Add additional safety event for touch devices
    container.addEventListener('touchstart', (e) => {
        if (e.target === formattedDisplay || e.target === container) {
            debugLog('formatting', `Touch started, focusing input`);
            input.focus();
        }
    });

    // Add input validation
    input.addEventListener('input', (e) => {
        let value = e.target.value;

        if (value === '') {
            updateFormattedDisplay();
            return;
        }

        const numValue = parseFloat(value);
        if (isNaN(numValue)) {
            e.target.value = '';
            updateFormattedDisplay();
            return;
        }

        const min = parseFloat(e.target.min);
        const max = parseFloat(e.target.max);

        if (!isNaN(min) && numValue < min) {
            e.target.value = min;
        } else if (!isNaN(max) && numValue > max) {
            e.target.value = max;
        } else {
            e.target.value = numValue;
        }

        updateFormattedDisplay();
    });

    // Initial formatting
    updateFormattedDisplay();
}

function formatNumberWithCommas(value) {
    if (!value) return '';

    // Remove any existing commas and handle decimals
    const parts = value.toString().split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');

    return parts.join('.');
}

function removeCommas(value) {
    if (!value) return '';
    return value.replace(/,/g, '');
}

// Export utility functions that might be needed by other modules
export { formatNumberWithCommas, removeCommas };
