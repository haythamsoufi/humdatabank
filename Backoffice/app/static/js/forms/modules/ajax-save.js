// AJAX Save Module - Handle form saving without page reload
import { debugLog } from './debug.js';

const MODULE_NAME = 'ajax-save';

let isSaving = false;
let drainPromise = null; // drains queued save requests
let queuedOptions = null; // merged options for next save run
let saveButton = null;
let form = null;

/**
 * Initialize AJAX save functionality
 */
export function initAjaxSave() {
    debugLog(MODULE_NAME, '🔄 Initializing AJAX Save...');

    // Find the form and save button
    form = document.getElementById('focalDataEntryForm');
    saveButton = document.querySelector('button[name="action"][value="save"]');

    if (!form || !saveButton) {
        debugLog(MODULE_NAME, '❌ Form or save button not found');
        return;
    }

    // Override the save button behavior
    saveButton.addEventListener('click', handleSaveClick);

    debugLog(MODULE_NAME, '✅ AJAX Save initialized');
}

/**
 * Handle save button click
 */
function handleSaveClick(event) {
    event.preventDefault();

    if (isSaving) {
        debugLog(MODULE_NAME, '⏳ Already saving, ignoring click');
        return;
    }

    // Collect hidden fields for server processing before saving
    if (window.collectHiddenFieldsForSubmission) {
        window.collectHiddenFieldsForSubmission();
    }

    // Explicit Save should show normal toast + button loading state
    queueSave({ toast: true, buttonState: true });
}

/**
 * Save the form via AJAX
 */
function mergeSaveOptions(a, b) {
    const ao = a || {};
    const bo = b || {};
    const out = {};

    // buttonState: enable if any caller wants it
    const aBtn = Object.prototype.hasOwnProperty.call(ao, 'buttonState') ? !!ao.buttonState : false;
    const bBtn = Object.prototype.hasOwnProperty.call(bo, 'buttonState') ? !!bo.buttonState : false;
    out.buttonState = aBtn || bBtn;

    // toast: show if any caller wants it; prefer an object toast if provided
    const aHasToast = Object.prototype.hasOwnProperty.call(ao, 'toast');
    const bHasToast = Object.prototype.hasOwnProperty.call(bo, 'toast');
    const aToast = aHasToast ? ao.toast : undefined;
    const bToast = bHasToast ? bo.toast : undefined;

    const pick = (t) => (t && typeof t === 'object') ? t : (t === true ? true : false);
    const pa = pick(aToast);
    const pb = pick(bToast);

    if (pb && typeof pb === 'object') out.toast = pb;
    else if (pa && typeof pa === 'object') out.toast = pa;
    else out.toast = (pa === true) || (pb === true);

    return out;
}

async function saveFormOnce(options = {}) {
    if (!form) {
        debugLog(MODULE_NAME, '❌ Form not found');
        throw new Error('Form not found');
    }

    const buttonStateOpt = (options && Object.prototype.hasOwnProperty.call(options, 'buttonState')) ? options.buttonState : undefined;
    const buttonStateEnabled = (buttonStateOpt === undefined) ? true : !!buttonStateOpt;

    isSaving = true;
    if (buttonStateEnabled) updateSaveButtonState(true);
    // Keep original formatted numeric values to restore after sending
    let originalNumericValues = null;

    try {
        debugLog(MODULE_NAME, '💾 Saving form...');

        // Collect matrix data before form submission (for AJAX saves)
        if (window.matrixHandler && typeof window.matrixHandler.collectMatrixData === 'function') {
            window.matrixHandler.collectMatrixData();
            debugLog(MODULE_NAME, '✅ Matrix data collected');
        }

        // Unformat numeric inputs (thousand separators) before collecting FormData
        const numericInputs = Array.from(form.querySelectorAll('input[data-numeric="true"]'));
        originalNumericValues = new Map();
        const unformatFn = (window.__numericUnformat || (v => (v || '').replace(/[\s,\u00A0\u202F]/g, '')));
        numericInputs.forEach(input => {
            originalNumericValues.set(input, input.value);
            try { input.value = unformatFn(input.value); } catch (_) { /* no-op */ }
        });

        // Create FormData from the form (now with raw numeric values)
        const formData = new FormData(form);
        formData.set('action', 'save'); // Ensure action is set to save
        // Mark presave requests so the backend can avoid clearing untouched fields
        // when an empty input is submitted.
        if (options && options.presave === true) {
            formData.set('ifrc_presave', '1');
        }

        // Ensure CSRF token is included
        const csrfToken = form.querySelector('input[name="csrf_token"]');
        if (csrfToken) {
            formData.set('csrf_token', csrfToken.value);
            debugLog(MODULE_NAME, 'CSRF token included in form data');
        } else {
            debugLog(MODULE_NAME, '⚠️ No CSRF token found in form');
        }

        // Determine target URL safely (avoid name collision with form controls)
        const actionAttr = form.getAttribute('action') || window.location.href;
        const targetUrl = actionAttr + (actionAttr.includes('?') ? '&' : '?') + 'ajax=1';

        // Send AJAX request
        debugLog(MODULE_NAME, `Sending request to: ${targetUrl}`);
        debugLog(MODULE_NAME, `Form data keys: ${Array.from(formData.keys())}`);

        const fetchFn = (window.getFetch && window.getFetch()) || fetch;
        const response = await fetchFn(targetUrl, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        debugLog(MODULE_NAME, `Response status: ${response.status}`);
        debugLog(MODULE_NAME, `Response headers: ${Object.fromEntries(response.headers.entries())}`);

        // Try to parse JSON response even if status is not ok (server may return error details in JSON)
        let result;
        const contentType = response.headers.get('Content-Type') || '';
        try {
            const text = await response.text();
            if (contentType.includes('application/json') && text) {
                result = JSON.parse(text);
            } else {
                result = null;
            }
        } catch (parseError) {
            result = null;
        }

        if (result === null && !response.ok) {
            const friendly403 = response.status === 403
                ? 'Save was rejected (403). Refresh the page and try again. If the problem continues, your session or security token may have expired.'
                : `Save failed (${response.status}). Refresh the page and try again, or contact support if it persists.`;
            debugLog(MODULE_NAME, '❌ Save failed:', friendly403);
            showSaveMessage('❌ Save failed: ' + friendly403, 'error');
            throw new Error(friendly403);
        }

        debugLog(MODULE_NAME, `Response result:`, result);

        if (!response.ok) {
            // Server returned an error status, but we have the JSON response
            const errorMessage = result?.message || result?.error || `HTTP error! status: ${response.status}`;
            debugLog(MODULE_NAME, '❌ Save failed:', errorMessage);
            showSaveMessage('❌ Save failed: ' + errorMessage, 'error');
            throw (window.httpErrorSync && window.httpErrorSync(response, errorMessage)) || new Error(errorMessage);
        }

        if (result.success) {
            debugLog(MODULE_NAME, 'Form saved successfully');
            const toastOpt = (options && Object.prototype.hasOwnProperty.call(options, 'toast')) ? options.toast : undefined;
            const toastEnabled = (toastOpt === undefined) ? true : !!toastOpt;
            if (toastEnabled) {
                // Allow custom toast payload, otherwise default
                const msg = (toastOpt && typeof toastOpt === 'object' && toastOpt.message) ? toastOpt.message : 'Progress saved successfully!';
                const type = (toastOpt && typeof toastOpt === 'object' && toastOpt.type) ? toastOpt.type : 'success';
                showSaveMessage(msg, type);
            }

            // Update any data that might have changed
            if (result.data) {
                updateFormData(result.data);
            }

            const isPresave = options && options.presave === true;
            if (!isPresave) {
                stripPendingDocumentUploadInputsFromForm(form);
            }

            // Dispatch formSubmitted event for other modules to listen to
            document.dispatchEvent(new CustomEvent('formSubmitted', {
                detail: { action: 'save', result: result }
            }));

            return { success: true, result };
        } else {
            debugLog(MODULE_NAME, '❌ Save failed:', result.message);
            showSaveMessage('❌ Save failed: ' + (result.message || 'Unknown error'), 'error');
            throw new Error(result.message || 'Save failed');
        }

    } catch (error) {
        debugLog(MODULE_NAME, '❌ Save error:', error);
        debugLog(MODULE_NAME, '❌ Error details:', {
            name: error.name,
            message: error.message,
            stack: error.stack
        });
        // Offline / network failure fallback: save local draft instead of showing a hard error.
        const msg = (error && error.message) ? String(error.message) : '';
        const looksLikeOffline = !navigator.onLine || error?.name === 'TypeError' || msg.includes('Failed to fetch');
        if (looksLikeOffline && window.__ifrcAuthDrafts && typeof window.__ifrcAuthDrafts.saveNow === 'function') {
            try {
                if (typeof window.__ifrcAuthDrafts.setOffline === 'function') {
                    window.__ifrcAuthDrafts.setOffline(true);
                }
                await window.__ifrcAuthDrafts.saveNow();
                showSaveMessage('You are offline. Draft saved locally.', 'warning');
                return { success: true, offline: true };
            } catch (e) {
                // fall through to error
            }
        }
        showSaveMessage('❌ Save failed: ' + msg, 'error');
        throw error;
    } finally {
        // Restore original formatted numeric values and reschedule formatting
        if (originalNumericValues) {
            originalNumericValues.forEach((value, input) => {
                try { input.value = value; } catch (_) { /* no-op */ }
                // Trigger formatting listeners to re-apply display formatting
                try { input.dispatchEvent(new Event('change', { bubbles: true })); } catch (_) { /* no-op */ }
            });
        }

        isSaving = false;
        if (buttonStateEnabled) updateSaveButtonState(false);
    }
}

function queueSave(options = {}) {
    // Merge options into a single queued run; ensures we don't spam toasts
    // but still respect "buttonState" when any caller needs it.
    queuedOptions = mergeSaveOptions(queuedOptions, options);

    debugLog(MODULE_NAME, '📥 queueSave()', { options, mergedQueuedOptions: queuedOptions, isSaving, hasDrain: !!drainPromise });

    if (!drainPromise) {
        drainPromise = (async () => {
            debugLog(MODULE_NAME, '🚰 drain start');
            while (queuedOptions) {
                const opts = queuedOptions;
                queuedOptions = null;
                debugLog(MODULE_NAME, '🚰 drain run save', opts);
                await saveFormOnce(opts);
            }
            debugLog(MODULE_NAME, '🚰 drain end');
            drainPromise = null;
        })();
    }

    return drainPromise;
}

/**
 * Update save button state
 */
function updateSaveButtonState(saving) {
    if (!saveButton) return;

    const icon = saveButton.querySelector('i');
    const text = saveButton.querySelector('span') || saveButton;

    if (saving) {
        saveButton.disabled = true;
        if (icon) {
            icon.className = 'fas fa-spinner fa-spin w-4 h-4 mr-2';
        }
        // Update text content while preserving structure
        const textNode = Array.from(text.childNodes).find(node => node.nodeType === Node.TEXT_NODE);
        if (textNode) {
            textNode.textContent = textNode.textContent.includes('Save') ? 'Saving...' : textNode.textContent;
        }
    } else {
        saveButton.disabled = false;
        if (icon) {
            icon.className = 'fas fa-save w-4 h-4 mr-2';
        }
        // Restore text content
        const textNode = Array.from(text.childNodes).find(node => node.nodeType === Node.TEXT_NODE);
        if (textNode) {
            textNode.textContent = textNode.textContent.replace('Saving...', 'Save');
        }
    }
}

/**
 * Inject a standard IFRC flash message into the existing flash container
 */
function showSaveMessage(message, type = 'success') {
    if (typeof window.showFlashMessage === 'function') {
        window.showFlashMessage(message, type);
    }
}

/**
 * Remove client-side queued document upload controls from the live form after a successful AJAX save.
 * document-upload.js appends hidden file + metadata inputs to the form; without removal, the next
 * Save still includes them in FormData and the server uploads again. Must NOT run for presave
 * (save-before-submit): the following native submit must still post those files.
 */
function stripPendingDocumentUploadInputsFromForm(formEl) {
    if (!formEl) return;
    try {
        formEl.querySelectorAll('input[type="file"][name^="field_value["]').forEach((el) => el.remove());
        formEl.querySelectorAll('input[data-queue-id]').forEach((el) => el.remove());
    } catch (_) {
        /* no-op */
    }
}

function dismissAlert(alert) {
    alert.classList.add('fade-out');
    setTimeout(() => alert.remove(), 300);
}

/**
 * Update form data with new values from server
 */
function updateFormData(data) {
    // Update any fields that might have changed on the server
    // This is for future use if needed
    debugLog(MODULE_NAME, '📊 Updating form data:', data);
}

/**
 * Manually trigger save (for external use)
 */
export function triggerSave() {
    if (!isSaving) {
        queueSave({ toast: true, buttonState: true });
    }
}

/**
 * Save form and return a promise that resolves on success or rejects on failure
 * Used when we need to save before submitting
 */
export async function saveFormBeforeSubmit(options = {}) {
    // Default: presave should not hijack the Save button UI or show "Progress saved..."
    const mergedOptions = {
        toast: false,
        buttonState: false,
        presave: true,
        ...options
    };
    return queueSave(mergedOptions);
}

/**
 * Check if currently saving
 */
export function isSavingForm() {
    return isSaving;
}
