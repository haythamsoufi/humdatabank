// Main entry point for form functionality
import { initFormOptimization } from './modules/form-optimization.js';
import { initMobileNav } from './modules/mobile-nav.js';
import { initFieldManagement } from './modules/field-management.js';
import { initConditions } from './modules/conditions.js';
import { initDynamicIndicators } from './modules/dynamic-indicators.js';
import { initFormatting } from './modules/formatting.js';
import { initRepeatSections } from './modules/repeat-sections.js';
import { initLayout } from './modules/layout.js';
import { initMultiSelect } from './modules/multi-select.js';
import { initCheckboxHandlers, handleYesNoCheckbox } from './modules/checkbox-handlers.js';
import { initDataAvailability } from './modules/data-availability.js';
import { initCalculatedLists } from './modules/calculated-lists-runtime.js';
import { initDisaggregationCalculator } from './modules/disaggregation-calculator.js';
import { initializeFormValidation } from './modules/form-validation.js';
import { initPDFExport, initValidationSummaryExport } from './modules/pdf-export.js';
import { ExcelExportManager } from './modules/excel-export.js';
import { initAjaxSave, triggerSave, isSavingForm } from './modules/ajax-save.js';
import { initPublicDrafts } from './modules/public-drafts.js';
import { initAuthDrafts } from './modules/auth-drafts.js';
import { initDocumentUpload } from './modules/document-upload.js';
import { initTooltips } from './modules/tooltips.js';
import { initFormEvents } from './modules/form-events.js';
import { matrixHandler } from './modules/matrix-handler.js';
import { cleanupInputValues, setupNumericInputJsonSupport } from './modules/form-item-utils.js';
import { initAiOpinions } from './modules/ai-opinions.js';
import { debugLog, debugWarn, debugError } from './modules/debug.js';

async function initializeEntryForm() {
    const initErrors = [];
    let conditionsReadyPromise = Promise.resolve();
    const safeInit = (name, fn) => {
        try {
            fn();
        } catch (e) {
            initErrors.push({ name, error: e });
            // Always log so we can diagnose "stuck loading" issues quickly.
            // eslint-disable-next-line no-console
            console.error(`[forms/main] init failed: ${name}`, e);
        }
    };

    try {
        // Set up global numeric input JSON support FIRST
        safeInit('setupNumericInputJsonSupport', () => setupNumericInputJsonSupport());

        // Clean up any existing numeric inputs that might have JSON values
        safeInit('cleanupInputValues(initial)', () => cleanupInputValues());

        // Core functionality modules
        safeInit('initMobileNav', () => initMobileNav());
        safeInit('initFieldManagement', () => initFieldManagement());
        safeInit('initConditions', () => {
            // initConditions returns a Promise that resolves once API-backed plugin variables
            // are available and initial relevance checks are stable.
            const p = initConditions();
            conditionsReadyPromise = (p && typeof p.then === 'function') ? p : Promise.resolve();
        });
        safeInit('initFormatting', () => initFormatting());
        safeInit('initLayout', () => initLayout());

        // Re-initialize numeric formatting after layout: initLayout uses cloneNode(true)
        // which copies attributes but drops all per-input event listeners (sanitizer,
        // focus/blur formatters). The global delegated handlers cover most cases, but
        // re-running setup restores per-input listeners for focus-unformat behaviour.
        if (typeof window.__setupNumericFormatting === 'function') {
            try { window.__setupNumericFormatting(); } catch (_) { /* no-op */ }
        }

        // Clean up again after layout initialization to catch any dynamically created fields
        setTimeout(() => {
            safeInit('cleanupInputValues(post-layout)', () => cleanupInputValues());
            debugLog('main', '🔄 Post-layout cleanup completed');
        }, 100);

        // Additional cleanup after all modules are initialized
        setTimeout(() => {
            safeInit('cleanupInputValues(final)', () => cleanupInputValues());
            debugLog('main', '🔄 Final cleanup completed');
        }, 500);

        // Feature modules
        safeInit('initDynamicIndicators', () => initDynamicIndicators());
        safeInit('initRepeatSections', () => initRepeatSections());
        safeInit('initMultiSelect', () => initMultiSelect());
        safeInit('initCheckboxHandlers', () => initCheckboxHandlers());
        safeInit('initDataAvailability', () => initDataAvailability());
        safeInit('initCalculatedLists', () => initCalculatedLists());
        safeInit('initDisaggregationCalculator', () => initDisaggregationCalculator());
        safeInit('initTooltips', () => initTooltips());

        // Initialize matrix handling (await restore + auto-load + variable lookups so loading gate waits)
        try {
            await matrixHandler.init();
        } catch (e) {
            initErrors.push({ name: 'matrixHandler.init', error: e });
            // eslint-disable-next-line no-console
            console.error('[forms/main] init failed: matrixHandler.init', e);
        }

        // Make matrixHandler globally available for AJAX save
        window.matrixHandler = matrixHandler;

        // Form validation - initialize last
        safeInit('initializeFormValidation', () => initializeFormValidation());

        // Form submission optimization MUST run after validation/presubmit handlers,
        // otherwise it can strip "name" attributes before validation runs and break follow-up submits.
        safeInit('initFormOptimization', () => initFormOptimization());

        // Initialize AJAX save functionality
        safeInit('initAjaxSave', () => initAjaxSave());

        // Initialize PDF export functionality
        safeInit('initPDFExport', () => initPDFExport('focalDataEntryForm', 'export-pdf-btn', document.title));

        // Initialize Validation Summary export functionality
        // Button now lives in the chatbot-hover-menu popup (fab-validation-summary-btn)
        safeInit('initValidationSummaryExport', () => initValidationSummaryExport('focalDataEntryForm', 'fab-validation-summary-btn'));
        safeInit('initAiOpinions', () => initAiOpinions());

        // Initialize Excel export functionality
        safeInit('ExcelExportManager', () => {
            const excelExportManager = new ExcelExportManager();
            window.excelExportManager = excelExportManager;
        });

        // Make functions globally available for templates
        window.handleYesNoCheckbox = handleYesNoCheckbox;
        window.triggerSave = triggerSave;
        window.isSavingForm = isSavingForm;

        // Make debug functions globally available
        window.debugLog = debugLog;
        window.debugWarn = debugWarn;
        window.debugError = debugError;

        // Document upload modal and form events
        safeInit('initDocumentUpload', () => initDocumentUpload());
        safeInit('initFormEvents', () => initFormEvents());

        // Initialize public drafts only for public forms
        safeInit('initPublicDrafts', () => {
            const pubRoot = document.querySelector('[data-is-public-submission]');
            if (pubRoot && pubRoot.dataset.isPublicSubmission === 'true') {
                const token = pubRoot.dataset.publicToken;
                if (token) {
                    initPublicDrafts({ publicToken: token });
                }
            }
        });

        // Local drafts for authenticated forms (offline-friendly local save/restore)
        safeInit('initAuthDrafts', () => initAuthDrafts());

        // Wait for initial relevance stabilization (plugin variables like EO1 can arrive via API).
        // Do NOT block forever; the entry-form loader fallback will still handle extreme cases.
        try {
            const MAX_WAIT_MS = 25000;
            await Promise.race([
                conditionsReadyPromise,
                new Promise((resolve) => setTimeout(resolve, MAX_WAIT_MS))
            ]);
        } catch (e) {
            initErrors.push({ name: 'initConditions:await', error: e });
            // eslint-disable-next-line no-console
            console.error('[forms/main] init failed: initConditions await', e);
        }
    } finally {
        // Always mark as initialized so the UI gate can open; never leave the user stuck on the loader.
        try {
            document.body.dataset.formInitialized = 'true';
        } catch (e) { /* no-op */ }

        debugLog('main', initErrors.length ? '⚠️ Form initialization completed with errors' : '✅ Form initialization completed successfully');
    }

    // Debug: Scan all calculated total fields after everything loads
    // To enable debug scanning, use: window.debug.enableScan() then window.debug.scanCalculatedTotals()
    // setTimeout(() => {
    //     debugCalculatedTotalFields();
    // }, 1000);
}

// Initialize all modules when DOM is ready (and also handle late module loading)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeEntryForm);
} else {
    initializeEntryForm();
}
