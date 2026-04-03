import { debugLog } from './debug.js';

export function initFormOptimization() {
    debugLog('form-optimization', '🚀 Initializing form optimization...');

    // Add form submission event listener
    const form = document.querySelector('form');
    if (form) {
        form.addEventListener('submit', (e) => {
            // If another handler already blocked submission (client validation, presave intercept, CSRF refresh, etc),
            // do NOT mutate the DOM by removing "name" attributes. Doing so would break the user's next attempt.
            if (e.defaultPrevented) {
                debugLog('form-optimization', '⏭️ Submission already prevented; skipping optimization');
                return;
            }

            // Run optimization but make it reversible if a later submit handler prevents submission.
            // This prevents "stale" removal of name="" from persisting after a validation failure.
            optimizeFormSubmission(form);

            // If later handlers call preventDefault(), restore names on the next tick.
            // On successful submission, navigation/reload cancels this timer.
            setTimeout(() => {
                try {
                    if (e.defaultPrevented) {
                        restoreOptimizedNames(form);
                    }
                } catch (_) { /* no-op */ }
            }, 0);
        });
        debugLog('form-optimization', '✅ Form submission optimization handler attached');
    } else {
        debugLog('form-optimization', '⚠️ No form found - optimization handler not attached');
    }
}

function markRemovedName(input, originalName) {
    try {
        if (!input || !originalName) return;
        // Keep original name so we can restore it if submission is prevented
        input.dataset.ifrcOriginalName = originalName;
    } catch (_) { /* no-op */ }
}

function restoreOptimizedNames(form) {
    if (!form) return;
    let restoredCount = 0;
    const removed = form.querySelectorAll('[data-ifrc-original-name]');
    removed.forEach((el) => {
        try {
            const originalName = el.dataset.ifrcOriginalName;
            if (originalName && !el.getAttribute('name')) {
                el.setAttribute('name', originalName);
                restoredCount++;
            }
            delete el.dataset.ifrcOriginalName;
        } catch (_) { /* no-op */ }
    });
    if (restoredCount > 0) {
        debugLog('form-optimization', `🔁 Restored ${restoredCount} optimized field names after prevented submit`);
    }
}

// Expose restore for other modules (e.g., validation) if needed
window.__ifrcRestoreOptimizedNames = restoreOptimizedNames;

function shouldNeverStripName(name) {
    if (!name) return false;
    // Critical server-side processing relies on these keys existing when present in the DOM.
    // Removing them breaks follow-up submits (especially if the first attempt is prevented).
    if (/^(indicator|dynamic)_\d+_/.test(name)) return true;
    if (/^repeat_\d+_\d+_field_\d+_/.test(name)) return true;
    return false;
}

function optimizeFormSubmission(form) {
    if (!form) return;

    let removedCount = 0;

    // Find all demographic input fields (sex_age, sex, age breakdowns)
    const demographicInputs = form.querySelectorAll('input[name*="_sexage_"], input[name*="_sex_"], input[name*="_age_"]');

    demographicInputs.forEach(input => {
        // Remove empty demographic inputs before submission
        if (!input.value || input.value.trim() === '' || input.value === '0') {
            const originalName = input.name;
            markRemovedName(input, originalName);
            input.removeAttribute('name');
            removedCount++;
            debugLog('form-optimization', `Removed empty demographic field: ${originalName}`);
        }
    });

    // Remove all hidden disaggregation mode inputs (not currently selected)
    const disaggregationContainers = form.querySelectorAll('.disaggregation-inputs[style*="display: none"]');
    disaggregationContainers.forEach(container => {
        const inputs = container.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            if (input.name) {
                const originalName = input.name;
                if (shouldNeverStripName(originalName)) return;
                markRemovedName(input, originalName);
                input.removeAttribute('name');
                removedCount++;
                debugLog('form-optimization', `Removed hidden disaggregation field: ${originalName}`);
            }
        });
    });

    // Remove empty standard form fields
    const allInputs = form.querySelectorAll('input[type="text"], input[type="number"], textarea');
    allInputs.forEach(input => {
        if (input.name && (!input.value || input.value.trim() === '')) {
            // Keep required fields and certain system fields
            if (!input.required &&
                !input.name.includes('csrf_token') &&
                !input.name.includes('reporting_mode') &&
                !input.name.includes('_data_not_available') &&
                !input.name.includes('_not_applicable')) {
                const originalName = input.name;
                if (shouldNeverStripName(originalName)) return;
                markRemovedName(input, originalName);
                input.removeAttribute('name');
                removedCount++;
                debugLog('form-optimization', `Removed empty field: ${originalName}`);
            }
        }
    });

    // Remove unchecked checkboxes (except for required ones)
    const checkboxes = form.querySelectorAll('input[type="checkbox"]:not(:checked)');
    checkboxes.forEach(checkbox => {
        if (checkbox.name &&
            !checkbox.name.includes('csrf_token') &&
            !checkbox.required) {
            const originalName = checkbox.name;
            if (shouldNeverStripName(originalName)) return;
            markRemovedName(checkbox, originalName);
            checkbox.removeAttribute('name');
            removedCount++;
            debugLog('form-optimization', `Removed unchecked checkbox: ${originalName}`);
        }
    });

    debugLog('form-optimization', `Form optimization complete - removed ${removedCount} empty/unused fields`);
}
