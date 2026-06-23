// Main entry point for form functionality
import { initFormOptimization } from './modules/form-optimization.js';
import { initMobileNav } from './modules/mobile-nav.js';
import { initFieldManagement } from './modules/field-management.js';
import { initConditions } from './modules/conditions.js';
import { initFormatting } from './modules/formatting.js';
import { initLayout } from './modules/layout.js';
import { initMultiSelect } from './modules/multi-select.js';
import { initCheckboxHandlers, handleYesNoCheckbox } from './modules/checkbox-handlers.js';
import { initDataAvailability } from './modules/data-availability.js';
import { initDisabilityQuestions } from './modules/disability-questions.js';
import { initUniqueSectionOptions } from './modules/unique-section-options.js';
import { initializeFormValidation } from './modules/form-validation.js';
import { initAjaxSave, triggerSave, isSavingForm } from './modules/ajax-save.js';
import { initAuthDrafts, prepareAuthDraftsStore } from './modules/auth-drafts.js';
import { initTooltips } from './modules/tooltips.js';
import { initFormEvents } from './modules/form-events.js';
import { cleanupInputValues, setupNumericInputJsonSupport } from './modules/form-item-utils.js';
import { debugLog, debugWarn, debugError } from './modules/debug.js';

function hasDom(selector) {
    try {
        return !!document.querySelector(selector);
    } catch (_) {
        return false;
    }
}

async function loadDeferredCompletionRate() {
    const el = document.getElementById('assignment-completion-rate');
    if (!el) return;
    const aesId = el.dataset.aesId;
    if (!aesId) return;

    const fetchFn = (window.getFetch && window.getFetch()) || fetch;
    try {
        const res = await fetchFn(`/api/forms/assignment/${encodeURIComponent(aesId)}/completion-rate`, {
            headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin',
        });
        if (!res.ok) return;
        const data = await res.json();
        const rate = Number(data.completion_rate);
        if (Number.isNaN(rate)) return;

        const valueEl = el.querySelector('[data-completion-value]') || el;
        valueEl.textContent = `${rate.toFixed(1)}%`;
        valueEl.classList.remove('text-gray-500');
        if (rate >= 80) {
            valueEl.classList.add('text-green-700', 'font-semibold');
        } else if (rate >= 25) {
            valueEl.classList.add('text-amber-600', 'font-semibold');
        } else {
            valueEl.classList.add('text-red-600', 'font-semibold');
        }
    } catch (e) {
        debugWarn('main', 'Deferred completion rate load failed', e);
    }
}

async function initializeEntryForm() {
    const initErrors = [];
    let conditionsReadyPromise = Promise.resolve();
    const safeInit = (name, fn) => {
        try {
            fn();
        } catch (e) {
            initErrors.push({ name, error: e });
            // eslint-disable-next-line no-console
            console.error(`[forms/main] init failed: ${name}`, e);
        }
    };

    const safeInitAsync = async (name, fn) => {
        try {
            await fn();
        } catch (e) {
            initErrors.push({ name, error: e });
            // eslint-disable-next-line no-console
            console.error(`[forms/main] init failed: ${name}`, e);
        }
    };

    try {
        safeInit('setupNumericInputJsonSupport', () => setupNumericInputJsonSupport());
        safeInit('cleanupInputValues(initial)', () => cleanupInputValues());
        safeInit('initMobileNav', () => initMobileNav());
        safeInit('initFieldManagement', () => initFieldManagement());
        safeInit('initConditions', () => {
            const p = initConditions();
            conditionsReadyPromise = (p && typeof p.then === 'function') ? p : Promise.resolve();
        });
        safeInit('initFormatting', () => initFormatting());
        safeInit('initLayout', () => initLayout());

        if (typeof window.__setupNumericFormatting === 'function') {
            try { window.__setupNumericFormatting(); } catch (_) { /* no-op */ }
        }

        setTimeout(() => {
            safeInit('cleanupInputValues(post-layout)', () => cleanupInputValues());
            debugLog('main', '🔄 Post-layout cleanup completed');
        }, 100);

        setTimeout(() => {
            safeInit('cleanupInputValues(final)', () => cleanupInputValues());
            debugLog('main', '🔄 Final cleanup completed');
        }, 500);

        safeInit('initMultiSelect', () => initMultiSelect());
        safeInit('initCheckboxHandlers', () => initCheckboxHandlers());
        safeInit('initDataAvailability', () => initDataAvailability());
        safeInit('initDisabilityQuestions', () => initDisabilityQuestions());
        safeInit('initUniqueSectionOptions', () => initUniqueSectionOptions());
        safeInit('initTooltips', () => initTooltips());

        if (hasDom('[data-section-type="dynamic_indicators"]')) {
            safeInit('initDynamicIndicators', () => {
                import('./modules/dynamic-indicators.js').then(mod => mod.initDynamicIndicators());
            });
        }

        if (hasDom('[data-section-type="repeat"]')) {
            safeInit('initRepeatSections', () => {
                import('./modules/repeat-sections.js').then(mod => mod.initRepeatSections());
            });
        }

        if (hasDom('[data-options-source="calculated"]')) {
            safeInit('initCalculatedLists', () => {
                import('./modules/calculated-lists-runtime.js').then(mod => mod.initCalculatedLists());
            });
        }

        if (hasDom('[data-disaggregation-mode], .disaggregation-container')) {
            safeInit('initDisaggregationCalculator', () => {
                import('./modules/disaggregation-calculator.js').then(mod => mod.initDisaggregationCalculator());
            });
        }

        if (hasDom('[data-matrix-config], .matrix-table-wrapper')) {
            await safeInitAsync('matrixHandler.init', async () => {
                const mod = await import('./modules/matrix-handler.js');
                await mod.matrixHandler.init();
                window.matrixHandler = mod.matrixHandler;
            });
        }

        safeInit('initializeFormValidation', () => initializeFormValidation());
        safeInit('initFormOptimization', () => initFormOptimization());
        safeInit('initAjaxSave', () => initAjaxSave());

        if (document.getElementById('export-pdf-btn')) {
            safeInit('initPDFExport', () => {
                import('./modules/pdf-export.js').then(mod => {
                    mod.initPDFExport('focalDataEntryForm', 'export-pdf-btn', document.title);
                    mod.initValidationSummaryExport('focalDataEntryForm', 'fab-validation-summary-btn');
                });
            });
        }

        if (document.getElementById('fab-validation-summary-btn') || document.getElementById('fab-ai-opinions')) {
            safeInit('initAiOpinions', () => {
                import('./modules/ai-opinions.js').then(mod => mod.initAiOpinions());
            });
        }

        if (document.getElementById('excel-options-btn') || document.getElementById('excel-export-modal')) {
            safeInit('ExcelExportManager', () => {
                import('./modules/excel-export.js').then(mod => {
                    const excelExportManager = new mod.ExcelExportManager();
                    window.excelExportManager = excelExportManager;
                });
            });
        }

        window.handleYesNoCheckbox = handleYesNoCheckbox;
        window.triggerSave = triggerSave;
        window.isSavingForm = isSavingForm;
        window.debugLog = debugLog;
        window.debugWarn = debugWarn;
        window.debugError = debugError;

        if (hasDom('[data-document-field], #document-upload-modal, .document-upload-trigger')) {
            safeInit('initDocumentUpload', () => {
                import('./modules/document-upload.js').then(mod => mod.initDocumentUpload());
            });
        }

        safeInit('initFormEvents', () => initFormEvents());

        safeInit('initPublicDrafts', () => {
            const pubRoot = document.querySelector('[data-is-public-submission="true"]');
            if (pubRoot && pubRoot.dataset.publicToken) {
                import('./modules/public-drafts.js').then(mod => {
                    mod.initPublicDrafts({ publicToken: pubRoot.dataset.publicToken });
                });
            }
        });

        try {
            await prepareAuthDraftsStore();
        } catch (e) {
            initErrors.push({ name: 'prepareAuthDraftsStore', error: e });
            console.error('[forms/main] prepareAuthDraftsStore failed', e);
        }
        safeInit('initAuthDrafts', () => initAuthDrafts());

        try {
            const MAX_WAIT_MS = 25000;
            await Promise.race([
                conditionsReadyPromise,
                new Promise((resolve) => setTimeout(resolve, MAX_WAIT_MS))
            ]);
        } catch (e) {
            initErrors.push({ name: 'initConditions:await', error: e });
            console.error('[forms/main] init failed: initConditions await', e);
        }

        void loadDeferredCompletionRate();
    } finally {
        try {
            document.body.dataset.formInitialized = 'true';
        } catch (e) { /* no-op */ }

        debugLog('main', initErrors.length ? '⚠️ Form initialization completed with errors' : '✅ Form initialization completed successfully');
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeEntryForm);
} else {
    initializeEntryForm();
}
