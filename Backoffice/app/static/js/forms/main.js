// Main entry point for form functionality
// Core modules — always needed, loaded statically.
import { initFormOptimization } from './modules/form-optimization.js';
import { initMobileNav } from './modules/mobile-nav.js';
import { initFieldManagement } from './modules/field-management.js';
import { initConditions } from './modules/conditions.js';
import { initFormatting } from './modules/formatting.js';
import { initLayout } from './modules/layout.js';
import { initMultiSelect } from './modules/multi-select.js';
import { initQuestionOtherOption } from './modules/question-other-option.js';
import { initCheckboxHandlers, handleYesNoCheckbox } from './modules/checkbox-handlers.js';
import { initDataAvailability } from './modules/data-availability.js';
import { initDisabilityQuestions } from './modules/disability-questions.js';
import { initUniqueSectionOptions } from './modules/unique-section-options.js';
import { initDisaggregationCalculator } from './modules/disaggregation-calculator.js';
import { initializeFormValidation } from './modules/form-validation.js';
import { initAjaxSave, triggerSave, isSavingForm } from './modules/ajax-save.js';
import { initPublicDrafts } from './modules/public-drafts.js';
import { initAuthDrafts, prepareAuthDraftsStore } from './modules/auth-drafts.js';
import { initTooltips } from './modules/tooltips.js';
import { initFormEvents } from './modules/form-events.js';
import { cleanupInputValues, setupNumericInputJsonSupport } from './modules/form-item-utils.js';
import { initAiOpinions } from './modules/ai-opinions.js';
import { debugLog, debugWarn, debugError } from './modules/debug.js';
import { initCompletionGapHighlight, initCompletionRateRefresh, refreshVisibleCompletionRate, applyCompletionRate } from './modules/entry-form-progress.js';
// Heavy feature modules — dynamically imported based on window.__formFeatures flags.
// Stubs ensure safe destructuring even when the flag is false and the module is skipped.

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

    // Kick off entry-bootstrap as early as possible (parallel with module imports).
    // Provides completion_rate + initial auto_load + resolved_variables in one round-trip.
    const gapBtnEarly = document.getElementById('completion-gap-btn');
    const bootstrapAesId = gapBtnEarly && gapBtnEarly.dataset.aesId;
    if (gapBtnEarly?.dataset.completionRate) {
        applyCompletionRate(parseFloat(gapBtnEarly.dataset.completionRate));
    }
    if (bootstrapAesId && !window.__entryBootstrapPromise) {
        const fetchFn = (window.getCsrfAwareFetch && window.getCsrfAwareFetch()) || fetch;
        window.__entryBootstrapPromise = fetchFn(
            `/api/forms/assignment/${bootstrapAesId}/entry-bootstrap`,
            {
                headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
                credentials: 'same-origin',
            }
        )
            .then((r) => (r.ok ? r.json() : null))
            .then((data) => {
                window.__entryBootstrap = data || null;
                if (typeof data?.completion_rate === 'number') {
                    applyCompletionRate(data.completion_rate);
                }
                return data;
            })
            .catch(() => {
                window.__entryBootstrap = null;
                return null;
            });
    }

    // Resolve feature flags. Fall back to loading everything when flags are absent
    // (e.g. preview pages or older entry_form.html without the __formFeatures block).
    const feat = window.__formFeatures || {
        matrix: true, repeat: true, dynamicIndicators: true,
        documents: true, calculatedLists: true, pdfExport: true, excelExport: true,
        discussion: false,
    };

    // Kick off dynamic imports for heavy feature modules concurrently — they run in
    // parallel while core modules initialise below, so they are ready by the time we
    // need them. Using empty-object fallbacks keeps destructuring safe when skipped.
    const [
        { matrixHandler = null } = {},
        { initDynamicIndicators = null } = {},
        { initRepeatSections = null } = {},
        { initDocumentUpload = null } = {},
        { initCalculatedLists = null } = {},
        { initPDFExport = null, initValidationSummaryExport = null } = {},
        { ExcelExportManager = null } = {},
        { initDiscussion = null } = {},
    ] = await Promise.all([
        feat.matrix           ? import('./modules/matrix-handler.js')          : Promise.resolve({}),
        feat.dynamicIndicators? import('./modules/dynamic-indicators.js')      : Promise.resolve({}),
        feat.repeat           ? import('./modules/repeat-sections.js')         : Promise.resolve({}),
        feat.documents        ? import('./modules/document-upload.js')         : Promise.resolve({}),
        feat.calculatedLists  ? import('./modules/calculated-lists-runtime.js'): Promise.resolve({}),
        feat.pdfExport        ? import('./modules/pdf-export.js')              : Promise.resolve({}),
        feat.excelExport      ? import('./modules/excel-export.js')            : Promise.resolve({}),
        feat.discussion       ? import('./modules/discussion.js')              : Promise.resolve({}),
    ]);

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
        if (initDynamicIndicators) safeInit('initDynamicIndicators', () => initDynamicIndicators());
        if (initRepeatSections)    safeInit('initRepeatSections',    () => initRepeatSections());
        safeInit('initMultiSelect', () => initMultiSelect());
        safeInit('initQuestionOtherOption', () => initQuestionOtherOption());
        safeInit('initCheckboxHandlers', () => initCheckboxHandlers());
        safeInit('initDataAvailability', () => initDataAvailability());
        safeInit('initDisabilityQuestions', () => initDisabilityQuestions());
        if (initCalculatedLists)   safeInit('initCalculatedLists',   () => initCalculatedLists());
        safeInit('initUniqueSectionOptions', () => initUniqueSectionOptions());
        safeInit('initDisaggregationCalculator', () => initDisaggregationCalculator());
        safeInit('initTooltips', () => initTooltips());
        if (initDiscussion) safeInit('initDiscussion', () => initDiscussion());

        // Initialize matrix handling (await restore + auto-load + variable lookups so loading gate waits)
        if (matrixHandler) {
            try {
                await matrixHandler.init();
            } catch (e) {
                initErrors.push({ name: 'matrixHandler.init', error: e });
                // eslint-disable-next-line no-console
                console.error('[forms/main] init failed: matrixHandler.init', e);
            }
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
        if (initPDFExport) {
            safeInit('initPDFExport', () => initPDFExport('focalDataEntryForm', 'export-pdf-btn', document.title));
        }

        // Initialize Validation Summary export functionality
        // Button now lives in the chatbot-hover-menu popup (fab-validation-summary-btn)
        if (initValidationSummaryExport) {
            safeInit('initValidationSummaryExport', () => initValidationSummaryExport('focalDataEntryForm', 'fab-validation-summary-btn'));
        }
        safeInit('initAiOpinions', () => initAiOpinions());

        // Initialize Excel export functionality
        if (ExcelExportManager) {
            safeInit('ExcelExportManager', () => {
                const excelExportManager = new ExcelExportManager();
                window.excelExportManager = excelExportManager;
            });
        }

        // Make functions globally available for templates
        window.handleYesNoCheckbox = handleYesNoCheckbox;
        window.triggerSave = triggerSave;
        window.isSavingForm = isSavingForm;

        // Make debug functions globally available
        window.debugLog = debugLog;
        window.debugWarn = debugWarn;
        window.debugError = debugError;

        // Document upload modal and form events
        if (initDocumentUpload) safeInit('initDocumentUpload', () => initDocumentUpload());
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
        try {
            await prepareAuthDraftsStore();
        } catch (e) {
            initErrors.push({ name: 'prepareAuthDraftsStore', error: e });
            // eslint-disable-next-line no-console
            console.error('[forms/main] prepareAuthDraftsStore failed', e);
        }
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

    // Refresh completion rate after save; skip fetch when server already rendered it.
    const completionDisplay = document.getElementById('completion-rate-display');
    const gapBtn = document.getElementById('completion-gap-btn');
    if (completionDisplay && gapBtn && gapBtn.dataset.aesId) {
        const aesId = gapBtn.dataset.aesId;
        initCompletionRateRefresh(aesId);
        const pending = (completionDisplay.textContent || '').trim();
        if (pending === '…' || pending === '' || pending === '—') {
            refreshVisibleCompletionRate(aesId)
                .catch(() => { completionDisplay.textContent = '—'; });
        }
    }

    initCompletionGapHighlight();

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
